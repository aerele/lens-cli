# Changelog

All notable changes to `lens-cli` are documented here. This project follows
[Semantic Versioning](https://semver.org).

## Unreleased

- Send large commits to the server in batches (at most 300 files / 5 MB each,
  the server's per-request limits) instead of failing with HTTP 413, which
  under the default `fail_open: true` let the commit through unscanned.
- Explain scan failures: name the server's size limit on 413, report the
  rate limit (and `Retry-After`, when sent) on 429, show the server's reason
  on 401 (e.g. revoked key vs expired token), and include the server's detail
  on other errors.
- **Breaking for CI scripts:** stable exit codes. `0` pass/skip, `1` blocking
  findings, `2` auth or usage problem, `3` server error. `fail_open: true` (the
  default) still exits `0` on errors, so pre-commit behaviour is unchanged;
  with `fail_open: false`, auth and server failures now exit `2` / `3` instead
  of `1`. `lens login` / `lens whoami` exit `2` / `3` instead of `1`.
- **Breaking for `--json` consumers:** `lens scan --json` now emits a versioned
  envelope (`{"schema": 1, "status", "exit_code", "summary", "findings", ...}`)
  instead of the raw server response, on every run including skips and errors.
  Findings gain a `blocking` flag. Notices go to stderr so stdout is pure JSON.
- Add `lens scan --diff BASE`: audit the files changed on `HEAD` since it
  forked from `BASE`, for CI on a pull request. An unresolvable base or a
  missing merge base exits `2` regardless of `fail_open`. The JSON envelope
  gains `target`.

## v0.2.0 — 2026-09-04

- Support the current nested `/api/auth/me` response while remaining compatible
  with older Lens servers, fixing `lens login` and `lens whoami`.
- Add a post-scan summary that distinguishes staged-file static coverage from
  the whole-repository, cross-file, LLM validation, scoring, and reporting
  available in a full Lens audit.
- Link the terminal summary directly to the hosted full-audit flow while
  keeping `lens scan --json` machine-readable.
- Document the CLI/full-audit rule boundary, valid category values, command
  behavior, exit codes, and privacy controls.

## v0.1.0

First release.

- `lens scan` — audit git-staged `.py`/`.js`/`.json` files via the Lens API and
  block the commit on findings that cross a configurable threshold.
- `lens login` / `lens whoami` — store and verify a personal API key.
- `.pre-commit-hooks.yaml` providing the `lens-scan` hook for the pre-commit
  framework.
- `.lens.yml` per-repo config: `block.threshold`, `block.categories`,
  `fail_open`, `timeout_seconds`, `ignore`.
- Privacy and safety: only staged files leave the machine; symlinks are never
  followed; the server is taken from your credentials, not from repo-committed
  config; credentials are written to a `0600` file.
