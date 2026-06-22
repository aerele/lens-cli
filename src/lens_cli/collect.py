"""Collect git-staged files into a scan payload."""
from __future__ import annotations

import subprocess
from fnmatch import fnmatch
from pathlib import Path

SCANNABLE_SUFFIXES = {".py", ".js", ".json"}
_MAX_FILE_BYTES = 512 * 1024


class GitError(Exception):
    """Raised when a git command fails or git is unavailable."""


def _git(args: list[str]) -> str:
    try:
        out = subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True
        )
    except FileNotFoundError as e:
        raise GitError("git is not installed or not on PATH.") from e
    except subprocess.CalledProcessError as e:
        raise GitError("not a git repository (or no commits yet).") from e
    return out.stdout


def git_repo_root() -> Path:
    return Path(_git(["rev-parse", "--show-toplevel"]).strip())


def staged_files() -> list[Path]:
    """Relative paths of git-staged added/copied/modified files."""
    out = _git(["diff", "--cached", "--name-only", "--diff-filter=ACM"])
    return [Path(line) for line in out.splitlines() if line.strip()]


def collect_payload(root: Path, files: list[Path], ignore: list[str]) -> list[dict]:
    """Read scannable staged files into ``[{"path", "content"}]``.

    Filters to scannable suffixes, drops ignore-glob matches, oversized files,
    and anything that isn't valid UTF-8 text.
    """
    payload: list[dict] = []
    root_resolved = root.resolve()
    for rel in files:
        if rel.suffix not in SCANNABLE_SUFFIXES:
            continue
        rel_str = rel.as_posix()
        if any(fnmatch(rel_str, pat) for pat in ignore):
            continue
        abs_path = root / rel
        # Never follow symlinks: a staged symlink (e.g. config.json ->
        # ~/.aws/credentials) would otherwise upload the target's content.
        if abs_path.is_symlink():
            continue
        # Defense in depth: the resolved path must stay inside the repo.
        try:
            abs_path.resolve().relative_to(root_resolved)
        except ValueError:
            continue
        if not abs_path.is_file() or abs_path.stat().st_size > _MAX_FILE_BYTES:
            continue
        try:
            content = abs_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        payload.append({"path": rel_str, "content": content})
    return payload
