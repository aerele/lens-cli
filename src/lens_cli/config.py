"""Credential storage and per-repo configuration for the Lens CLI."""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

import yaml

try:  # py311+
    import tomllib
except ModuleNotFoundError:  # py310
    import tomli as tomllib

DEFAULT_THRESHOLD = "trusted-critical"
DEFAULT_SERVER = "https://lens.aerele.in"
CONFIG_PATH = Path.home() / ".config" / "lens" / "config.toml"


@dataclass
class Credentials:
    api_url: str
    api_key: str


@dataclass
class RepoConfig:
    server: str = DEFAULT_SERVER
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
    # Hand-written minimal TOML keeps us off a toml-writer dependency.
    CONFIG_PATH.write_text(f'api_url = "{api_url}"\napi_key = "{api_key}"\n')
    CONFIG_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600


def load_repo_config(repo_root: Path) -> RepoConfig:
    path = repo_root / ".lens.yml"
    if not path.exists():
        return RepoConfig()
    data = yaml.safe_load(path.read_text()) or {}
    block = data.get("block", {}) or {}
    return RepoConfig(
        server=data.get("server", DEFAULT_SERVER),
        threshold=block.get("threshold", DEFAULT_THRESHOLD),
        categories=block.get("categories"),
        fail_open=bool(data.get("fail_open", True)),
        timeout_seconds=int(data.get("timeout_seconds", 15)),
        ignore=list(data.get("ignore", []) or []),
    )
