"""The `lens` command-line interface."""
from __future__ import annotations

import json

import typer
from rich.console import Console

from lens_cli.client import LensAuthError, LensClient, LensNetworkError
from lens_cli.collect import collect_payload, git_repo_root, staged_files
from lens_cli.config import (
    Credentials,
    load_credentials,
    load_repo_config,
    save_credentials,
)
from lens_cli.render import render_findings, should_block

app = typer.Typer(help="Lens code audit, at git commit time.")
_console = Console()


@app.command()
def login(
    api_key: str = typer.Option(..., prompt="Lens API key", hide_input=True),
    server: str = typer.Option("https://lens.aerele.in", help="Lens server URL"),
) -> None:
    """Validate an API key and store it for future runs."""
    client = LensClient(Credentials(server, api_key))
    try:
        me = client.whoami()
    except (LensAuthError, LensNetworkError) as e:
        _console.print(f"[red]Login failed: {e}[/red]")
        raise typer.Exit(code=1)
    save_credentials(server, api_key)
    _console.print(f"[green]Logged in as {me.get('email')}.[/green]")


@app.command()
def whoami() -> None:
    """Print the email of the authenticated Lens account."""
    creds = load_credentials()
    if creds is None:
        _console.print("[yellow]Not logged in. Run `lens login`.[/yellow]")
        raise typer.Exit(code=1)
    try:
        me = LensClient(creds).whoami()
    except (LensAuthError, LensNetworkError) as e:
        _console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)
    _console.print(me.get("email", "unknown"))


@app.command()
def scan(
    all_files: bool = typer.Option(False, "--all", help="Scan all staged files (default)."),
    as_json: bool = typer.Option(False, "--json", help="Emit raw JSON instead of a table."),
) -> None:
    """Run a fast static audit on git-staged files (the pre-commit entry point)."""
    creds = load_credentials()
    if creds is None:
        # Never block an un-onboarded teammate who just installed the hook.
        _console.print("[yellow]Lens not configured. Run `lens login`. Skipping.[/yellow]")
        raise typer.Exit(code=0)

    root = git_repo_root()
    repo_cfg = load_repo_config(root)
    files = staged_files()
    payload = collect_payload(root, files, repo_cfg.ignore)
    if not payload:
        raise typer.Exit(code=0)

    client = LensClient(creds, timeout=repo_cfg.timeout_seconds)
    try:
        result = client.scan(payload, repo_cfg.categories)
    except LensAuthError as e:
        _console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=0 if repo_cfg.fail_open else 1)
    except (LensNetworkError, Exception) as e:  # noqa: BLE001 - fail-open is the point
        verb = "Skipping" if repo_cfg.fail_open else "Blocking"
        _console.print(f"[yellow]Lens unreachable ({e}). {verb}.[/yellow]")
        raise typer.Exit(code=0 if repo_cfg.fail_open else 1)

    findings = result.get("findings", [])
    blocking = should_block(findings, repo_cfg.threshold, repo_cfg.categories)
    if as_json:
        _console.print_json(json.dumps(result))
    else:
        render_findings(findings, blocking)
    raise typer.Exit(code=1 if blocking else 0)
