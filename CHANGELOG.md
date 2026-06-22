# Changelog

All notable changes to `lens-cli` are documented here. This project follows
[Semantic Versioning](https://semver.org).

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
