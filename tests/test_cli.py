from typer.testing import CliRunner

import lens_cli.cli as climod
from lens_cli.cli import app
from lens_cli.config import Credentials, RepoConfig

runner = CliRunner()


def _patch_common(monkeypatch, tmp_path, repo_cfg):
    monkeypatch.setattr(climod, "load_credentials", lambda: Credentials("https://x", "k"))
    monkeypatch.setattr(climod, "git_repo_root", lambda: tmp_path)
    monkeypatch.setattr(climod, "staged_files", lambda: [])
    monkeypatch.setattr(
        climod, "collect_payload", lambda *a, **k: [{"path": "a.py", "content": "x=1\n"}]
    )
    monkeypatch.setattr(climod, "load_repo_config", lambda root: repo_cfg)


def test_scan_blocks_on_trusted_critical(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path, RepoConfig())

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def scan(self, files, categories):
            return {
                "findings": [
                    {
                        "rule_id": "r",
                        "severity": "critical",
                        "category": "security",
                        "trusted": True,
                        "file": "a.py",
                        "line": 1,
                        "message": "bad",
                    }
                ],
                "scan_mode": "changed-files",
                "engine_version": "static",
            }

    monkeypatch.setattr(climod, "LensClient", FakeClient)
    result = runner.invoke(app, ["scan"])
    assert result.exit_code == 1


def test_scan_passes_when_no_blocking(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path, RepoConfig())

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def scan(self, files, categories):
            return {"findings": [], "scan_mode": "changed-files", "engine_version": "static"}

    monkeypatch.setattr(climod, "LensClient", FakeClient)
    result = runner.invoke(app, ["scan"])
    assert result.exit_code == 0
    assert "Lens CLI summary" in result.output
    assert "Checked 1 staged file" in result.output


def test_scan_json_stays_machine_readable(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path, RepoConfig())

    response = {
        "findings": [],
        "scan_mode": "changed-files",
        "engine_version": "static",
    }

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def scan(self, files, categories):
            return response

    monkeypatch.setattr(climod, "LensClient", FakeClient)
    result = runner.invoke(app, ["scan", "--json"])

    assert result.exit_code == 0
    assert "Lens CLI summary" not in result.output
    assert '"scan_mode": "changed-files"' in result.output


def test_scan_fail_open_on_network_error(monkeypatch, tmp_path):
    from lens_cli.client import LensNetworkError

    _patch_common(monkeypatch, tmp_path, RepoConfig(fail_open=True))

    class FailClient:
        def __init__(self, *a, **k):
            pass

        def scan(self, files, categories):
            raise LensNetworkError("down")

    monkeypatch.setattr(climod, "LensClient", FailClient)
    result = runner.invoke(app, ["scan"])
    assert result.exit_code == 0  # fail open allows the commit


def test_scan_fail_closed_blocks_on_network_error(monkeypatch, tmp_path):
    from lens_cli.client import LensNetworkError

    _patch_common(monkeypatch, tmp_path, RepoConfig(fail_open=False))

    class FailClient:
        def __init__(self, *a, **k):
            pass

        def scan(self, files, categories):
            raise LensNetworkError("down")

    monkeypatch.setattr(climod, "LensClient", FailClient)
    result = runner.invoke(app, ["scan"])
    assert result.exit_code == 1  # fail closed blocks the commit


def test_scan_not_configured_skips(monkeypatch):
    monkeypatch.setattr(climod, "load_credentials", lambda: None)
    result = runner.invoke(app, ["scan"])
    assert result.exit_code == 0


def test_scan_skips_outside_git_repo(monkeypatch):
    from lens_cli.collect import GitError

    monkeypatch.setattr(climod, "load_credentials", lambda: Credentials("https://x", "k"))

    def boom():
        raise GitError("not a git repository (or no commits yet).")

    monkeypatch.setattr(climod, "git_repo_root", boom)
    result = runner.invoke(app, ["scan"])
    assert result.exit_code == 0  # graceful skip, no traceback


def _finding(path, severity="warning", trusted=False):
    return {
        "rule_id": "r",
        "severity": severity,
        "category": "security",
        "trusted": trusted,
        "file": path,
        "line": 1,
        "message": "bad",
    }


def test_scan_sends_large_payload_in_batches_and_merges(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path, RepoConfig())
    payload = [{"path": f"f{i:03}.py", "content": "x=1\n"} for i in range(301)]
    monkeypatch.setattr(climod, "collect_payload", lambda *a, **k: payload)
    calls = []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def scan(self, files, categories):
            calls.append(len(files))
            # Only the second batch has a blocking finding.
            crit = len(calls) == 2
            return {
                "findings": [_finding(files[0]["path"], "critical" if crit else "warning", crit)],
                "scan_mode": "changed-files",
                "engine_version": "static",
            }

    monkeypatch.setattr(climod, "LensClient", FakeClient)
    result = runner.invoke(app, ["scan"])

    assert calls == [300, 1]
    assert result.exit_code == 1  # a blocking finding in any batch blocks
    assert "Checked 301 staged files · 2 findings · 1 blocking" in result.output


def test_scan_json_merges_batches(monkeypatch, tmp_path):
    import json

    _patch_common(monkeypatch, tmp_path, RepoConfig())
    payload = [{"path": f"f{i:03}.py", "content": "x=1\n"} for i in range(301)]
    monkeypatch.setattr(climod, "collect_payload", lambda *a, **k: payload)

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def scan(self, files, categories):
            return {
                "findings": [_finding(files[0]["path"])],
                "scan_mode": "changed-files",
                "engine_version": "static",
            }

    monkeypatch.setattr(climod, "LensClient", FakeClient)
    result = runner.invoke(app, ["scan", "--json"])

    out = json.loads(result.output)
    assert out["scan_mode"] == "changed-files"
    assert [f["file"] for f in out["findings"]] == ["f000.py", "f300.py"]


def test_scan_failed_batch_fails_whole_scan(monkeypatch, tmp_path):
    from lens_cli.client import LensNetworkError

    _patch_common(monkeypatch, tmp_path, RepoConfig(fail_open=False))
    payload = [{"path": f"f{i:03}.py", "content": "x=1\n"} for i in range(301)]
    monkeypatch.setattr(climod, "collect_payload", lambda *a, **k: payload)
    calls = []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def scan(self, files, categories):
            calls.append(len(files))
            if len(calls) == 2:
                raise LensNetworkError("Lens rate limit reached; retry in 5s")
            return {"findings": [], "scan_mode": "changed-files", "engine_version": "static"}

    monkeypatch.setattr(climod, "LensClient", FakeClient)
    result = runner.invoke(app, ["scan"])

    assert result.exit_code == 1
    assert "rate limit reached; retry in 5s" in result.output
    assert "Blocking" in result.output
