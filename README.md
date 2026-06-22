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

## Use as a pre-commit hook

Add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/aerele/lens-cli
    rev: v0.1.0
    hooks:
      - id: lens-scan
```

Then `pre-commit install`. On every commit, `lens scan` checks the staged files
and blocks the commit if any finding crosses the configured threshold.

## Configure per repo — `.lens.yml`

```yaml
block:
  threshold: trusted-critical        # trusted-critical (default) | critical | warning | off
  categories: [security, framework]  # optional: only block on these categories
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

## What this is not

The pre-commit scan is a **fast static check**: no LLM validation, scoring, or
report. For the full LLM-validated, scored audit, share your Frappe app repo on
the Lens platform at lens.aerele.in.

## Develop

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
```
