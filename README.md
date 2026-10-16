# lens-cli

Run the [Lens](https://lens.aerele.in) code audit at `git commit` time.

`lens-cli` is a thin client. It sends your **git-staged files** to the Lens API,
which runs the static audit engine and returns findings. The audit engine never
runs on your machine, and only staged files (not your whole app) leave it.

## Install

```bash
pipx install git+https://github.com/aerele/lens-cli
lens login           # paste a personal API key from lens.aerele.in -> Profile -> API keys
lens whoami          # verify you're logged in
```

`lens login` stores the key in `~/.config/lens/config.toml` (mode 600). In CI,
set `LENS_API_KEY` (and `LENS_API_URL` for a self-hosted Lens) instead.

For the pre-commit hook below you don't need a global install: the pre-commit
framework builds `lens-cli` for you from the pinned ref.

## Commands

| Command | What it does |
|---|---|
| `lens login` | Validate an API key and save it to `~/.config/lens/config.toml`. |
| `lens whoami` | Print the email of the account the key belongs to. |
| `lens scan` | Audit the git-staged files. Exits non-zero if anything crosses the threshold. This is what the pre-commit hook runs. |
| `lens scan --diff BASE` | Audit the files changed on `HEAD` since it forked from `BASE` (e.g. `origin/develop`), instead of staged files. For CI on a pull request; see [Use in CI](#use-in-ci). |
| `lens scan --json` | Same scan, as a versioned JSON envelope on stdout (see [JSON output](#json-output)). |

Auth resolution order: `LENS_API_KEY` / `LENS_API_URL` environment variables
first (best for CI), then `~/.config/lens/config.toml`. If neither is present,
`lens scan` prints a notice and exits 0 (it never blocks a teammate who hasn't
set up Lens yet).

## Use as a pre-commit hook

Add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/aerele/lens-cli
    rev: v0.2.0
    hooks:
      - id: lens-scan
```

Then `pre-commit install`. On every commit, `lens scan` checks the staged files
and blocks the commit if any finding crosses the configured threshold.

## Use in CI

`lens scan --diff BASE` audits every file a branch changed, the same checks the
hook runs on staged files, so it fits a pull-request job:

```yaml
# GitHub Actions
- uses: actions/checkout@v4
  with:
    fetch-depth: 0              # --diff needs the merge base
- run: pipx install git+https://github.com/aerele/lens-cli@v0.3.0
- run: lens scan --diff origin/${{ github.base_ref }} --json > lens.json
  env:
    LENS_API_KEY: ${{ secrets.LENS_API_KEY }}
```

Set `fail_open: false` in `.lens.yml` if a Lens outage should fail the job
(exit `3`) rather than pass it. A `BASE` that can't be resolved, or a shallow
clone with no merge base, always exits `2` instead of passing with nothing
scanned.

`--diff` is still a changed-files scan, not a whole-repository audit: rules
that need the full repo don't run (see [CLI coverage vs full audit](#cli-coverage-vs-full-audit)).

## Configure per repo — `.lens.yml`

```yaml
block:
  threshold: trusted-critical        # trusted-critical (default) | critical | warning | off
  categories: [security, framework-fitness]  # optional: scan/block only these categories
fail_open: true                      # allow the commit if the server is unreachable
timeout_seconds: 15
ignore:
  - "**/tests/**"
```

- **threshold** controls what *blocks* a commit. The default, `trusted-critical`,
  only blocks on high-confidence critical findings. Everything else is printed as
  advice but never blocks.
- **fail_open** (default true): a network or server error warns and lets the
  commit through, so a flaky connection never wedges `git commit`.
- The Lens **server** is set by your credentials (`LENS_API_URL` or `lens login`),
  not by `.lens.yml`. `.lens.yml` is committed to the repo, so letting it pick the
  server would let a cloned repo redirect your API key to another host.

Bypass a single commit with `git commit --no-verify`.

## How it decides (exit codes)

Exit codes are stable, so CI can tell "found problems" from "couldn't run":

| Code | Meaning |
|---|---|
| `0` | Passed, skipped, or a failure let through by `fail_open` |
| `1` | A finding crosses the blocking threshold |
| `2` | Authentication problem (invalid/revoked key, not logged in) or bad usage |
| `3` | Server unreachable, rate-limited, or errored |

With `fail_open: true` (the default), `lens scan` turns `2` and `3` into `0` so
a broken Lens setup never wedges `git commit`; set `fail_open: false` in CI to
see them. `lens login` and `lens whoami` always return `2` / `3` on failure.

| Situation | Exit | Commit |
|---|---|---|
| A finding crosses `threshold` | `1` | blocked |
| Findings exist but none cross the threshold | `0` | proceeds (findings printed as advice) |
| No findings | `0` | proceeds |
| Not configured (no key) | `0` | proceeds (notice printed) |
| No scannable staged files | `0` | proceeds |
| Key rejected by the server | `0` if `fail_open: true` (default), else `2` | |
| Server unreachable / errored / rate-limited | `0` if `fail_open: true` (default), else `3` | |
| Run outside a git repo | `0` | proceeds (skipped) |

**Threshold meanings:** `off` blocks nothing · `trusted-critical` (default)
blocks only high-confidence critical findings · `critical` blocks every critical
· `warning` blocks criticals and warnings.

Valid category values are `security`, `erpnext-conventions`,
`framework-fitness`, `performance`, and `code-quality`. Omit `categories` to
run all five.

## CLI coverage vs full audit

A clean CLI result means the staged files passed the checks that are sound with
partial repository context. It is not a clean bill of health for the whole app.

| Lens CLI covers on staged files | Full Lens audit additionally covers |
|---|---|
| Security rules such as injection, unsafe whitelisted endpoints, permission bypasses, and hardcoded secrets | Every applicable file in the repository, not only the current staged `.py`, `.js`, and `.json` files |
| ERPNext and framework rules for database writes, controller overrides, child tables, hooks, scheduler events, lifecycle recursion, DocType JSON, and translations | Whole-app dead-code rules: `unused-function`, `unused-class`, and reachability-aware prioritisation |
| Performance rules that are safe with changed-file context, including query-in-loop and repeated database-call patterns | Test-coverage rules: `untested-custom-app`, `doctype-untested`, and `doctype-stub-tests-only` |
| Client-side checks for unsafe form events and invalid `frappe.call` / `frm.call` targets visible in the staged set | Index-hygiene rules: `over-indexed-write-heavy-field` and `missing-index-on-read-heavy-field` |
| Code-quality checks for exception handling, imports, mutable defaults, commented code, duplicate blocks, and parse errors | Cross-file classification for `get-doc-in-loop`, permission bypasses, and nested-loop queries; LLM validation; weighted 0-100 score; prioritised HTML/PDF report |

The normal terminal output includes this boundary in its scan summary and links
directly to the hosted full-audit flow. `lens scan --json` leaves the summary
out and emits only the JSON envelope.

## JSON output

`lens scan --json` writes exactly one JSON object to stdout on every run,
including skips and errors; human-readable notices go to stderr. The envelope
is versioned by `schema`. Fields are only ever added within a schema version;
a breaking change bumps it.

```json
{
  "schema": 1,
  "status": "blocked",
  "exit_code": 1,
  "reason": null,
  "target": {"type": "staged"},
  "error": null,
  "scan_mode": "changed-files",
  "engine_version": "0.1.0+rules.225da1a4c770",
  "summary": {
    "files_scanned": 3,
    "findings": 2,
    "blocking": 1,
    "threshold": "trusted-critical",
    "categories": null
  },
  "findings": [
    {
      "rule_id": "...", "severity": "critical", "category": "security",
      "file": "app/api.py", "line": 42, "message": "...", "trusted": true,
      "blocking": true
    }
  ]
}
```

- `status`: `passed` · `blocked` · `skipped` · `error`.
- `reason` (when `skipped`): `not-configured` · `not-a-git-repo` · `no-files`.
- `target`: `{"type": "staged"}` or `{"type": "diff", "base": "origin/develop"}`.
- `error` (when `error`): `{"kind": "auth" | "server" | "usage", "message": str, "fail_open": bool}`.
- `scan_mode` / `engine_version` come from the server and are `null` when no
  scan ran. Treat `engine_version` as a cache key, not a behaviour guarantee.
- Each finding carries the server's fields as sent (`line` may be `null` for
  file-level findings; newer servers add more, such as `fix`) plus `blocking`.

## Privacy

Only the **git-staged** `.py`, `.js`, and `.json` files are sent to the Lens
server, never your whole repo. Symlinks are never followed, so a staged symlink
can't ship a file from outside the repo. Files over 512 KB and non-UTF-8 files
are skipped. To keep code on your own infrastructure, point `LENS_API_URL` at a
self-hosted Lens. A large commit is sent in batches of at most 300 files / 5 MB
(the server's per-request limits), and one blocking finding in any batch
blocks the commit.

## What this is not

The pre-commit scan is a **fast static check**: no LLM validation, scoring, or
report. For the full LLM-validated, scored audit, share your Frappe app repo at
https://lens.aerele.in/audits/new.

## Develop

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
```
