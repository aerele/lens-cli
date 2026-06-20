from lens_cli.render import should_block


def _f(**kw):
    base = {
        "rule_id": "r",
        "severity": "critical",
        "category": "security",
        "trusted": True,
        "file": "a.py",
        "line": 1,
        "message": "m",
    }
    base.update(kw)
    return base


def test_trusted_critical_blocks_only_trusted():
    findings = [_f(trusted=True), _f(trusted=False)]
    blocked = should_block(findings, "trusted-critical", None)
    assert len(blocked) == 1
    assert blocked[0]["trusted"] is True


def test_off_never_blocks():
    assert should_block([_f()], "off", None) == []


def test_critical_threshold_ignores_trusted_flag():
    findings = [_f(trusted=False), _f(severity="warning", trusted=False)]
    assert len(should_block(findings, "critical", None)) == 1


def test_warning_threshold_includes_warnings():
    findings = [_f(severity="warning", trusted=False)]
    assert len(should_block(findings, "warning", None)) == 1


def test_category_narrowing():
    findings = [_f(category="security"), _f(category="performance")]
    assert len(should_block(findings, "critical", ["security"])) == 1
