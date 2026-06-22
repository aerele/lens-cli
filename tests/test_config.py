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


def test_unknown_threshold_falls_back_to_default(tmp_path):
    (tmp_path / ".lens.yml").write_text("block:\n  threshold: Critical\n")  # wrong case
    assert load_repo_config(tmp_path).threshold == DEFAULT_THRESHOLD


def test_malformed_yaml_falls_back_to_defaults(tmp_path):
    (tmp_path / ".lens.yml").write_text("block: {threshold: critical\n")  # unbalanced brace
    cfg = load_repo_config(tmp_path)
    assert cfg.threshold == DEFAULT_THRESHOLD
    assert cfg.fail_open is True


def test_repo_config_has_no_server_field():
    # The server must NOT be configurable from the committed .lens.yml.
    from lens_cli.config import RepoConfig

    assert not hasattr(RepoConfig(), "server")


def test_save_credentials_escapes_special_chars(tmp_path, monkeypatch):
    import lens_cli.config as cfgmod

    monkeypatch.setattr(cfgmod, "CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.delenv("LENS_API_KEY", raising=False)
    monkeypatch.delenv("LENS_API_URL", raising=False)
    # A value containing a quote would corrupt naive f-string TOML.
    cfgmod.save_credentials("https://lens.aerele.in", 'lens_pat_a"b')
    creds = cfgmod.load_credentials()
    assert creds is not None
    assert creds.api_key == 'lens_pat_a"b'
