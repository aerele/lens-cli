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
