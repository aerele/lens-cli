# Changelog

All notable changes to `lens-cli` are documented here. This project follows
[Semantic Versioning](https://semver.org).

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
