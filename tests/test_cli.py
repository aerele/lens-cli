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
    assert result.exit_code == 3  # fail closed: server error, distinct from findings


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

    assert result.exit_code == 3
    assert "rate limit reached; retry in 5s" in result.output
    assert "Blocking" in result.output


def _client_returning(findings):
    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def scan(self, files, categories):
            return {
                "findings": findings,
                "scan_mode": "changed-files",
                "engine_version": "0.1.0+rules.abc",
            }

    return FakeClient


def _client_raising(exc):
    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def scan(self, files, categories):
            raise exc

    return FakeClient


def test_scan_fail_closed_auth_error_exits_2(monkeypatch, tmp_path):
    from lens_cli.client import LensAuthError

    _patch_common(monkeypatch, tmp_path, RepoConfig(fail_open=False))
    monkeypatch.setattr(climod, "LensClient", _client_raising(LensAuthError("Invalid token.")))
    result = runner.invoke(app, ["scan"])
    assert result.exit_code == 2


def test_scan_fail_open_auth_error_exits_0(monkeypatch, tmp_path):
    from lens_cli.client import LensAuthError

    _patch_common(monkeypatch, tmp_path, RepoConfig(fail_open=True))
    monkeypatch.setattr(climod, "LensClient", _client_raising(LensAuthError("Invalid token.")))
    result = runner.invoke(app, ["scan"])
    assert result.exit_code == 0


def test_scan_json_envelope_on_block(monkeypatch, tmp_path):
    import json

    _patch_common(monkeypatch, tmp_path, RepoConfig())
    warn = _finding("a.py")
    crit = {**_finding("a.py", "critical", True), "fix": "Use frappe.get_doc()."}
    monkeypatch.setattr(climod, "LensClient", _client_returning([warn, crit]))
    result = runner.invoke(app, ["scan", "--json"])

    assert result.exit_code == 1
    out = json.loads(result.stdout)
    assert out["schema"] == 1
    assert out["status"] == "blocked"
    assert out["exit_code"] == 1
    assert out["error"] is None
    assert out["engine_version"] == "0.1.0+rules.abc"
    assert out["summary"] == {
        "files_scanned": 1,
        "findings": 2,
        "blocking": 1,
        "threshold": "trusted-critical",
        "categories": None,
    }
    assert [f["blocking"] for f in out["findings"]] == [False, True]
    # Server fields pass through untouched, including ones added later.
    assert out["findings"][1]["fix"] == "Use frappe.get_doc()."


def test_scan_json_envelope_on_pass(monkeypatch, tmp_path):
    import json

    _patch_common(monkeypatch, tmp_path, RepoConfig())
    monkeypatch.setattr(climod, "LensClient", _client_returning([]))
    result = runner.invoke(app, ["scan", "--json"])

    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert (out["status"], out["findings"]) == ("passed", [])


def test_scan_json_envelope_on_server_error_keeps_stdout_pure(monkeypatch, tmp_path):
    import json

    from lens_cli.client import LensNetworkError

    _patch_common(monkeypatch, tmp_path, RepoConfig(fail_open=True))
    monkeypatch.setattr(climod, "LensClient", _client_raising(LensNetworkError("down")))
    result = runner.invoke(app, ["scan", "--json"])

    assert result.exit_code == 0
    out = json.loads(result.stdout)  # the notice went to stderr, not stdout
    assert out["status"] == "error"
    assert out["error"] == {"kind": "server", "message": "down", "fail_open": True}
    assert "could not run" in result.stderr


def test_scan_json_envelope_when_not_configured(monkeypatch):
    import json

    monkeypatch.setattr(climod, "load_credentials", lambda: None)
    result = runner.invoke(app, ["scan", "--json"])

    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert (out["status"], out["reason"]) == ("skipped", "not-configured")


def test_scan_json_envelope_when_no_scannable_files(monkeypatch, tmp_path):
    import json

    _patch_common(monkeypatch, tmp_path, RepoConfig())
    monkeypatch.setattr(climod, "collect_payload", lambda *a, **k: [])
    result = runner.invoke(app, ["scan", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["reason"] == "no-files"


def test_whoami_not_logged_in_exits_2(monkeypatch):
    monkeypatch.setattr(climod, "load_credentials", lambda: None)
    assert runner.invoke(app, ["whoami"]).exit_code == 2


def test_whoami_server_error_exits_3(monkeypatch):
    from lens_cli.client import LensNetworkError

    monkeypatch.setattr(climod, "load_credentials", lambda: Credentials("https://x", "k"))

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def whoami(self):
            raise LensNetworkError("down")

    monkeypatch.setattr(climod, "LensClient", FakeClient)
    assert runner.invoke(app, ["whoami"]).exit_code == 3


def test_scan_diff_scans_changed_files(monkeypatch, tmp_path):
    import json

    _patch_common(monkeypatch, tmp_path, RepoConfig())
    seen = {}

    def fake_changed(base):
        seen["base"] = base
        return []

    def boom():
        raise AssertionError("staged_files must not be used with --diff")

    monkeypatch.setattr(climod, "changed_files", fake_changed)
    monkeypatch.setattr(climod, "staged_files", boom)
    monkeypatch.setattr(climod, "LensClient", _client_returning([]))
    result = runner.invoke(app, ["scan", "--diff", "origin/develop", "--json"])

    assert result.exit_code == 0
    assert seen["base"] == "origin/develop"
    out = json.loads(result.stdout)
    assert out["target"] == {"type": "diff", "base": "origin/develop"}


def test_scan_diff_terminal_output_talks_about_changed_files(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path, RepoConfig())
    monkeypatch.setattr(climod, "changed_files", lambda base: [])
    crit = _finding("a.py", "critical", True)
    monkeypatch.setattr(climod, "LensClient", _client_returning([crit]))
    result = runner.invoke(app, ["scan", "--diff", "origin/develop"])

    assert result.exit_code == 1
    assert "Checked 1 changed file" in result.output
    assert "Lens found 1 blocking finding" in result.output
    assert "--no-verify" not in result.output  # not a commit in CI


def test_scan_diff_bad_base_is_usage_error_even_when_fail_open(monkeypatch, tmp_path):
    import json

    from lens_cli.collect import GitError

    _patch_common(monkeypatch, tmp_path, RepoConfig(fail_open=True))

    def bad(base):
        raise GitError(f"cannot resolve --diff base {base!r}")

    monkeypatch.setattr(climod, "changed_files", bad)
    result = runner.invoke(app, ["scan", "--diff", "origin/nope", "--json"])

    assert result.exit_code == 2
    out = json.loads(result.stdout)
    assert out["status"] == "error"
    assert out["error"]["kind"] == "usage"
    assert "origin/nope" in result.stderr


def test_scan_json_target_defaults_to_staged(monkeypatch, tmp_path):
    import json

    _patch_common(monkeypatch, tmp_path, RepoConfig())
    monkeypatch.setattr(climod, "LensClient", _client_returning([]))
    result = runner.invoke(app, ["scan", "--json"])
    assert json.loads(result.stdout)["target"] == {"type": "staged"}
