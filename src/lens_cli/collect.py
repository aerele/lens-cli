"""Collect git-staged files into a scan payload."""
from __future__ import annotations

import subprocess
from fnmatch import fnmatch
from pathlib import Path

SCANNABLE_SUFFIXES = {".py", ".js", ".json"}
_MAX_FILE_BYTES = 512 * 1024


def git_repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(out.stdout.strip())


def staged_files() -> list[Path]:
    """Relative paths of git-staged added/copied/modified files."""
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [Path(line) for line in out.stdout.splitlines() if line.strip()]


def collect_payload(root: Path, files: list[Path], ignore: list[str]) -> list[dict]:
    """Read scannable staged files into ``[{"path", "content"}]``.

    Filters to scannable suffixes, drops ignore-glob matches, oversized files,
    and anything that isn't valid UTF-8 text.
    """
    payload: list[dict] = []
    for rel in files:
        if rel.suffix not in SCANNABLE_SUFFIXES:
            continue
        rel_str = rel.as_posix()
        if any(fnmatch(rel_str, pat) for pat in ignore):
            continue
        abs_path = root / rel
        if not abs_path.is_file() or abs_path.stat().st_size > _MAX_FILE_BYTES:
            continue
        try:
            content = abs_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        payload.append({"path": rel_str, "content": content})
    return payload
