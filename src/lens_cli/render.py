"""Findings rendering and blocking-threshold logic."""
from __future__ import annotations

from rich.console import Console

_console = Console()
_FULL_AUDIT_URL = (
    "https://lens.aerele.in/audits/new"
    "?utm_source=lens-cli"
)
_CATEGORY_LABELS = {
    "security": "security",
    "erpnext-conventions": "ERPNext",
    "framework-fitness": "framework",
    "performance": "performance",
    "code-quality": "code quality",
}


def _crosses(f: dict, threshold: str) -> bool:
    sev = f.get("severity")
    if threshold == "off":
        return False
    if threshold == "trusted-critical":
        return sev == "critical" and bool(f.get("trusted"))
    if threshold == "critical":
        return sev == "critical"
    if threshold == "warning":
        return sev in ("critical", "warning")
    return False


def should_block(
    findings: list[dict], threshold: str, categories: list[str] | None
) -> list[dict]:
    """Return the subset of findings that should fail the commit."""
    blocking = [f for f in findings if _crosses(f, threshold)]
    if categories:
        cats = set(categories)
        blocking = [f for f in blocking if f.get("category") in cats]
    return blocking


def _coverage_labels(categories: list[str] | None) -> str:
    selected = _CATEGORY_LABELS if categories is None else categories
    labels = [_CATEGORY_LABELS.get(category, category) for category in selected]
    return ", ".join(labels) if labels else "no categories enabled"


def _plural(count: int, singular: str) -> str:
    return singular if count == 1 else f"{singular}s"


def render_scan_summary(
    findings: list[dict],
    blocking: list[dict],
    *,
    files_scanned: int,
    categories: list[str] | None,
) -> None:
    """Explain the changed-file result and the value of a full Lens audit."""
    _console.print("\n[bold]Lens CLI summary[/bold]")
    _console.print(
        f"Checked {files_scanned} staged {_plural(files_scanned, 'file')} · "
        f"{len(findings)} {_plural(len(findings), 'finding')} · "
        f"{len(blocking)} blocking"
    )
    _console.print(
        f"Staged-file coverage: {_coverage_labels(categories)} static checks."
    )
    _console.print(
        "[dim]Full audit adds: whole-repository context; dead code, test coverage "
        "and index hygiene; cross-file and reachability analysis; LLM validation; "
        "a 0-100 score and shareable HTML/PDF report.[/dim]"
    )
    _console.print(
        f"[bold cyan]Audit the full app:[/bold cyan] "
        f"[link={_FULL_AUDIT_URL}]{_FULL_AUDIT_URL}[/link]"
    )


def render_findings(
    findings: list[dict],
    blocking: list[dict],
    *,
    files_scanned: int,
    categories: list[str] | None,
) -> None:
    if not findings:
        _console.print("[green]Lens: no findings on staged files.[/green]")
    else:
        blocking_ids = {id(f) for f in blocking}
        for f in findings:
            tag = "[red]BLOCK[/red]" if id(f) in blocking_ids else "[yellow]warn[/yellow]"
            loc = f"{f.get('file')}:{f.get('line')}" if f.get("line") else f.get("file")
            _console.print(
                f"{tag} [bold]{f.get('rule_id')}[/bold] ({f.get('severity')}) {loc}\n"
                f"    {f.get('message')}"
            )
        if blocking:
            _console.print(
                f"\n[red]Lens blocked this commit: {len(blocking)} "
                f"{_plural(len(blocking), 'blocking finding')}.[/red]"
            )
            _console.print(
                "Fix them, widen the threshold in .lens.yml, or commit with "
                "--no-verify to bypass."
            )
    render_scan_summary(
        findings,
        blocking,
        files_scanned=files_scanned,
        categories=categories,
    )
