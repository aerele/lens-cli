"""Credential storage and per-repo configuration for the Lens CLI."""
from __future__ import annotations

import json
import os
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

try:  # py311+
    import tomllib
except ModuleNotFoundError:  # py310
    import tomli as tomllib

DEFAULT_THRESHOLD = "trusted-critical"
DEFAULT_SERVER = "https://lens.aerele.in"
VALID_THRESHOLDS = {"off", "trusted-critical", "critical", "warning"}
CONFIG_PATH = Path.home() / ".config" / "lens" / "config.toml"


def _warn(msg: str) -> None:
    print(f"lens: {msg}", file=sys.stderr)


@dataclass
class Credentials:
    api_url: str
    api_key: str


@dataclass
class RepoConfig:
    # NOTE: the server is intentionally NOT configurable from .lens.yml. That
    # file is committed to the repo, so a malicious/cloned repo could otherwise
    # redirect your API key to an attacker. The server comes only from your
    # own credentials (LENS_API_URL env or ~/.config/lens/config.toml).
    threshold: str = DEFAULT_THRESHOLD
    categories: list[str] | None = None
    fail_open: bool = True
    timeout_seconds: int = 15
    ignore: list[str] = field(default_factory=list)


def load_credentials() -> Credentials | None:
    """Resolve credentials from env (CI-friendly) then the config file."""
    env_key = os.environ.get("LENS_API_KEY")
    env_url = os.environ.get("LENS_API_URL")
    if env_key:
        return Credentials(api_url=env_url or DEFAULT_SERVER, api_key=env_key)
    if CONFIG_PATH.exists():
        data = tomllib.loads(CONFIG_PATH.read_text())
        if data.get("api_key"):
            return Credentials(
                api_url=data.get("api_url", DEFAULT_SERVER), api_key=data["api_key"]
            )
    return None


def save_credentials(api_url: str, api_key: str) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Hand-written minimal TOML keeps us off a toml-writer dependency. TOML
    # basic-string escaping is a subset of JSON's, so json.dumps produces a
    # valid, fully-escaped string and prevents a stray quote/newline in a value
    # from corrupting the file or injecting keys.
    CONFIG_PATH.write_text(
        f"api_url = {json.dumps(api_url.strip())}\n"
        f"api_key = {json.dumps(api_key.strip())}\n"
    )
    CONFIG_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600


def load_repo_config(repo_root: Path) -> RepoConfig:
    path = repo_root / ".lens.yml"
    if not path.exists():
        return RepoConfig()
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        _warn(f".lens.yml is not valid YAML ({e.__class__.__name__}); using defaults.")
        return RepoConfig()
    if not isinstance(data, dict):
        _warn(".lens.yml must be a mapping; using defaults.")
        return RepoConfig()
    block = data.get("block", {}) or {}

    threshold = block.get("threshold", DEFAULT_THRESHOLD)
    if threshold not in VALID_THRESHOLDS:
        _warn(
            f"unknown block.threshold {threshold!r} in .lens.yml "
            f"(expected one of {sorted(VALID_THRESHOLDS)}); using {DEFAULT_THRESHOLD!r}."
        )
        threshold = DEFAULT_THRESHOLD

    return RepoConfig(
        threshold=threshold,
        categories=block.get("categories"),
        fail_open=bool(data.get("fail_open", True)),
        timeout_seconds=int(data.get("timeout_seconds", 15)),
        ignore=list(data.get("ignore", []) or []),
    )
