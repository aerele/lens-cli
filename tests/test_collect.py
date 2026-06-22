from pathlib import Path

from lens_cli.collect import collect_payload


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
