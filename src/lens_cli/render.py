"""Findings rendering and blocking-threshold logic."""
from __future__ import annotations

from rich.console import Console

_console = Console()
_FUNNEL = (
    "This is a fast static check. For the full LLM-validated, scored report, "
    "run `lens audit --deep` or visit lens.aerele.in."
)


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


def render_findings(findings: list[dict], blocking: list[dict]) -> None:
    if not findings:
        _console.print("[green]Lens: no findings on staged files.[/green]")
        _console.print(f"[dim]{_FUNNEL}[/dim]")
        return
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
            f"\n[red]Lens blocked this commit: {len(blocking)} critical finding(s).[/red]"
        )
        _console.print(
            "Fix them, widen the threshold in .lens.yml, or commit with "
            "--no-verify to bypass."
        )
    _console.print(f"[dim]{_FUNNEL}[/dim]")
