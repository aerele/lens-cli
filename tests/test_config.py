from lens_cli.config import DEFAULT_THRESHOLD, load_credentials, load_repo_config


def test_repo_config_defaults(tmp_path):
    cfg = load_repo_config(tmp_path)  # no .lens.yml
    assert cfg.threshold == DEFAULT_THRESHOLD
    assert cfg.fail_open is True
    assert cfg.timeout_seconds == 15
    assert cfg.categories is None
    assert cfg.ignore == []


def test_repo_config_override(tmp_path):
    (tmp_path / ".lens.yml").write_text(
        "block:\n"
        "  threshold: critical\n"
        "  categories: [security]\n"
        "fail_open: false\n"
        "timeout_seconds: 5\n"
        "ignore:\n"
        "  - 'tests/**'\n"
    )
    cfg = load_repo_config(tmp_path)
    assert cfg.threshold == "critical"
    assert cfg.categories == ["security"]
    assert cfg.fail_open is False
    assert cfg.timeout_seconds == 5
    assert cfg.ignore == ["tests/**"]


def test_credentials_from_env(monkeypatch):
    monkeypatch.setenv("LENS_API_KEY", "lens_pat_envkey")
    monkeypatch.setenv("LENS_API_URL", "http://localhost:8000")
    creds = load_credentials()
    assert creds is not None
    assert creds.api_key == "lens_pat_envkey"
    assert creds.api_url == "http://localhost:8000"
