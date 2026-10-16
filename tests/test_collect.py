import pytest
from pathlib import Path

from lens_cli.collect import GitError, batch_payload, changed_files, collect_payload


def test_collect_filters_and_ignores(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.txt").write_text("nope\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "t.py").write_text("y = 2\n")

    files = [Path("a.py"), Path("b.txt"), Path("tests/t.py")]
    payload = collect_payload(tmp_path, files, ignore=["tests/**"])

    paths = {p["path"] for p in payload}
    assert paths == {"a.py"}  # .txt filtered out, tests/** ignored
    assert payload[0]["content"] == "x = 1\n"


def test_collect_skips_missing_files(tmp_path):
    payload = collect_payload(tmp_path, [Path("ghost.py")], ignore=[])
    assert payload == []


def test_collect_includes_js_and_json(tmp_path):
    (tmp_path / "m.js").write_text("var a = 1;\n")
    (tmp_path / "d.json").write_text("{}\n")
    payload = collect_payload(tmp_path, [Path("m.js"), Path("d.json")], ignore=[])
    assert {p["path"] for p in payload} == {"m.js", "d.json"}


def test_collect_skips_symlinks(tmp_path):
    # A staged symlink (even a scannable suffix) must never be followed, so a
    # link to a secret file can't exfiltrate the target's content.
    secret = tmp_path / "secret_outside"
    secret.write_text("SECRET")
    link = tmp_path / "evil.json"
    link.symlink_to(secret)
    payload = collect_payload(tmp_path, [Path("evil.json")], ignore=[])
    assert payload == []


def _item(path, size=1):
    return {"path": path, "content": "x" * size}


def test_batch_payload_single_batch_when_under_limits():
    payload = [_item("b.py"), _item("a.py")]
    batches = batch_payload(payload)
    assert [[f["path"] for f in b] for b in batches] == [["a.py", "b.py"]]


def test_batch_payload_splits_on_file_count():
    payload = [_item(f"f{i:03}.py") for i in range(7)]
    batches = batch_payload(payload, max_files=3)
    assert [len(b) for b in batches] == [3, 3, 1]


def test_batch_payload_splits_on_bytes():
    payload = [_item("a.py", 40), _item("b.py", 40), _item("c.py", 40)]
    batches = batch_payload(payload, max_bytes=100)
    assert [[f["path"] for f in b] for b in batches] == [["a.py", "b.py"], ["c.py"]]


def test_batch_payload_counts_utf8_bytes_not_chars():
    # "é" is 2 bytes in UTF-8; the server measures encoded size.
    payload = [{"path": "a.py", "content": "é" * 30}, {"path": "b.py", "content": "é" * 30}]
    assert len(batch_payload(payload, max_bytes=100)) == 2


def test_batch_payload_default_caps_match_server():
    payload = [_item(f"f{i:04}.py") for i in range(301)]
    assert [len(b) for b in batch_payload(payload)] == [300, 1]


def test_batch_payload_empty():
    assert batch_payload([]) == []


def _git_repo(path, monkeypatch):
    import subprocess

    def git(*args):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (path / "base.py").write_text("x = 1\n")
    git("add", ".")
    git("commit", "-q", "-m", "base")
    monkeypatch.chdir(path)
    return git


def test_changed_files_lists_branch_changes_since_fork(tmp_path, monkeypatch):
    git = _git_repo(tmp_path, monkeypatch)
    git("checkout", "-q", "-b", "feature")
    (tmp_path / "new.py").write_text("y = 2\n")
    (tmp_path / "base.py").write_text("x = 3\n")
    git("add", ".")
    git("commit", "-q", "-m", "feature")
    # A later commit on main must not show up: the diff is from the fork point.
    git("checkout", "-q", "main")
    (tmp_path / "main_only.py").write_text("z = 1\n")
    git("add", ".")
    git("commit", "-q", "-m", "main moves on")
    git("checkout", "-q", "feature")

    assert sorted(p.as_posix() for p in changed_files("main")) == ["base.py", "new.py"]


def test_changed_files_skips_deleted(tmp_path, monkeypatch):
    git = _git_repo(tmp_path, monkeypatch)
    git("checkout", "-q", "-b", "feature")
    git("rm", "-q", "base.py")
    git("commit", "-q", "-m", "delete")

    assert changed_files("main") == []


def test_changed_files_unknown_base(tmp_path, monkeypatch):
    _git_repo(tmp_path, monkeypatch)
    with pytest.raises(GitError, match="cannot resolve --diff base 'origin/nope'"):
        changed_files("origin/nope")


def test_changed_files_rejects_option_like_base(tmp_path, monkeypatch):
    _git_repo(tmp_path, monkeypatch)
    with pytest.raises(GitError, match="invalid --diff base"):
        changed_files("--output=/tmp/x")
