from io import StringIO

from rich.console import Console

import lens_cli.render as render_mod
from lens_cli.render import render_findings, should_block


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


def _render_output(monkeypatch, findings, blocking, **kwargs):
    output = StringIO()
    monkeypatch.setattr(
        render_mod,
        "_console",
        Console(file=output, color_system=None, force_terminal=False, width=120),
    )
    render_findings(findings, blocking, **kwargs)
    return output.getvalue()


def test_summary_explains_cli_and_full_audit_coverage(monkeypatch):
    finding = _f()
    output = _render_output(
        monkeypatch,
        [finding],
        [finding],
        files_scanned=2,
        categories=None,
    )
    normalized = " ".join(output.split())

    assert "Checked 2 staged files" in normalized
    assert "security, ERPNext, framework, performance, code quality" in normalized
    assert "whole-repository context; dead code, test coverage" in normalized
    assert "cross-file and reachability analysis" in normalized
    assert "LLM validation" in normalized
    assert "https://lens.aerele.in/audits/new?utm_source=lens-cli" in normalized
    assert "lens audit --deep" not in normalized


def test_summary_respects_selected_categories_and_singular_counts(monkeypatch):
    finding = _f()
    output = _render_output(
        monkeypatch,
        [finding],
        [finding],
        files_scanned=1,
        categories=["security"],
    )

    assert "Checked 1 staged file · 1 finding · 1 blocking" in output
    assert "Staged-file coverage: security static checks." in output
    assert "Lens blocked this commit: 1 blocking finding." in output


def test_clean_scan_still_promotes_full_audit_without_overclaiming(monkeypatch):
    output = _render_output(
        monkeypatch,
        [],
        [],
        files_scanned=3,
        categories=None,
    )

    assert "no findings on staged files" in output
    assert "Checked 3 staged files · 0 findings · 0 blocking" in output
    assert "Full audit adds: whole-repository context" in output
