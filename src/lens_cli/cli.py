"""The `lens` command-line interface."""
from __future__ import annotations

import json
from typing import NoReturn

import typer
from rich.console import Console

from lens_cli.client import LensAuthError, LensClient, LensNetworkError
from lens_cli.collect import (
    GitError,
    batch_payload,
    changed_files,
    collect_payload,
    git_repo_root,
    staged_files,
)
from lens_cli.config import (
    Credentials,
    RepoConfig,
    load_credentials,
    load_repo_config,
    save_credentials,
)
from lens_cli.render import render_findings, should_block

app = typer.Typer(help="Lens code audit, at git commit time.")
_console = Console()

# Exit codes (stable; see README). fail_open turns EXIT_AUTH / EXIT_SERVER
# into EXIT_OK so a broken Lens setup never wedges `git commit`.
EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_AUTH = 2
EXIT_USAGE = 2
EXIT_SERVER = 3

# Version of the `lens scan --json` envelope. Bump only on a breaking change;
# adding fields does not need a bump.
JSON_SCHEMA = 1


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
        raise typer.Exit(code=EXIT_AUTH if isinstance(e, LensAuthError) else EXIT_SERVER)
    save_credentials(server, api_key)
    _console.print(f"[green]Logged in as {me.get('email')}.[/green]")


@app.command()
def whoami() -> None:
    """Print the email of the authenticated Lens account."""
    creds = load_credentials()
    if creds is None:
        _console.print("[yellow]Not logged in. Run `lens login`.[/yellow]")
        raise typer.Exit(code=EXIT_AUTH)
    try:
        me = LensClient(creds).whoami()
    except (LensAuthError, LensNetworkError) as e:
        _console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=EXIT_AUTH if isinstance(e, LensAuthError) else EXIT_SERVER)
    _console.print(me.get("email", "unknown"))


def _emit_json(
    status: str,
    exit_code: int,
    *,
    findings: list[dict] | None = None,
    blocking: list[dict] | None = None,
    files_scanned: int = 0,
    repo_cfg: RepoConfig | None = None,
    result: dict | None = None,
    error: dict | None = None,
    reason: str | None = None,
    diff_base: str | None = None,
) -> None:
    findings = findings or []
    blocking_ids = {id(f) for f in blocking or []}
    typer.echo(
        json.dumps(
            {
                "schema": JSON_SCHEMA,
                "status": status,
                "exit_code": exit_code,
                "reason": reason,
                "target": (
                    {"type": "diff", "base": diff_base}
                    if diff_base
                    else {"type": "staged"}
                ),
                "error": error,
                "scan_mode": (result or {}).get("scan_mode"),
                "engine_version": (result or {}).get("engine_version"),
                "summary": {
                    "files_scanned": files_scanned,
                    "findings": len(findings),
                    "blocking": len(blocking_ids),
                    "threshold": repo_cfg.threshold if repo_cfg else None,
                    "categories": repo_cfg.categories if repo_cfg else None,
                },
                "findings": [
                    {**f, "blocking": id(f) in blocking_ids} for f in findings
                ],
            },
            indent=2,
        )
    )


@app.command()
def scan(
    as_json: bool = typer.Option(
        False, "--json", help="Emit a versioned JSON envelope instead of a table."
    ),
    diff: str | None = typer.Option(
        None,
        "--diff",
        metavar="BASE",
        help="Scan files changed on HEAD since it forked from BASE "
        "(e.g. origin/develop) instead of staged files. For CI on a PR.",
    ),
) -> None:
    """Run a fast static audit on git-staged files (the pre-commit entry point)."""
    # With --json, stdout carries only the envelope; notices go to stderr.
    notice = Console(stderr=True) if as_json else _console

    def skip(reason: str, message: str) -> NoReturn:
        if message:
            notice.print(f"[yellow]{message}[/yellow]")
        if as_json:
            _emit_json("skipped", EXIT_OK, reason=reason, diff_base=diff)
        raise typer.Exit(code=EXIT_OK)

    creds = load_credentials()
    if creds is None:
        # Never block an un-onboarded teammate who just installed the hook.
        skip("not-configured", "Lens not configured. Run `lens login`. Skipping.")

    try:
        root = git_repo_root()
    except GitError as e:
        skip("not-a-git-repo", f"lens scan skipped: {e}")
    if diff is None:
        files = staged_files()
    else:
        try:
            files = changed_files(diff)
        except GitError as e:
            # An explicit --diff base that doesn't work is a usage error: fail
            # loudly rather than pass CI with nothing scanned.
            notice.print(f"[red]lens scan: {e}[/red]")
            if as_json:
                _emit_json(
                    "error",
                    EXIT_USAGE,
                    error={"kind": "usage", "message": str(e), "fail_open": False},
                    diff_base=diff,
                )
            raise typer.Exit(code=EXIT_USAGE)

    repo_cfg = load_repo_config(root)
    payload = collect_payload(root, files, repo_cfg.ignore)
    if not payload:
        skip("no-files", "")

    # Only the network call is fail-open. Rendering + thresholding run AFTER the
    # try so a bug there surfaces instead of being mistaken for "server down".
    # The server caps each request (file count + bytes), so a large commit is
    # sent in batches; any failed batch fails the whole scan.
    client = LensClient(creds, timeout=repo_cfg.timeout_seconds)
    try:
        results = [
            client.scan(batch, repo_cfg.categories) for batch in batch_payload(payload)
        ]
    except (LensAuthError, LensNetworkError) as e:
        kind, code = ("auth", EXIT_AUTH) if isinstance(e, LensAuthError) else ("server", EXIT_SERVER)
        code = EXIT_OK if repo_cfg.fail_open else code
        verb = "Skipping" if repo_cfg.fail_open else "Blocking"
        if kind == "auth":
            notice.print(f"[red]{e}[/red]")
        else:
            notice.print(f"[yellow]Lens scan could not run ({e}). {verb}.[/yellow]")
        if as_json:
            _emit_json(
                "error",
                code,
                files_scanned=len(payload),
                repo_cfg=repo_cfg,
                error={"kind": kind, "message": str(e), "fail_open": repo_cfg.fail_open},
                diff_base=diff,
            )
        raise typer.Exit(code=code)

    result = {**results[0], "findings": [f for r in results for f in r.get("findings", [])]}
    findings = result["findings"]
    blocking = should_block(findings, repo_cfg.threshold, repo_cfg.categories)
    code = EXIT_BLOCKED if blocking else EXIT_OK
    if as_json:
        _emit_json(
            "blocked" if blocking else "passed",
            code,
            findings=findings,
            blocking=blocking,
            files_scanned=len(payload),
            repo_cfg=repo_cfg,
            result=result,
            diff_base=diff,
        )
    else:
        render_findings(
            findings,
            blocking,
            files_scanned=len(payload),
            categories=repo_cfg.categories,
            scope="changed" if diff else "staged",
        )
    raise typer.Exit(code=code)
