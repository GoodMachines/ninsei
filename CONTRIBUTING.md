# Contributing to Ninsei

Thanks for helping. Bug fixes and small improvements are welcome as pull requests. For anything bigger (a new feature, a
new kind of event on the wire, a change to what leaves someone's machine), open an issue first so we can agree on it
before you build it.

## Before you start

Read [ARCHITECTURE.md](ARCHITECTURE.md). It explains how the parts connect and, more importantly, the trust model:
everything in a room comes from strangers, room agents have no tools, and only the owner can reach their full Hermes
agent. Most review comments come back to that.

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

The page tests need Node 22 on your PATH; without it they are skipped. CI runs Python 3.14.

If you have Hermes installed, run `hermes plugins validate .` in your checkout too.

## Changing the page

The page's source is `ui/*.js`. After editing it, rebuild the two bundles and commit them with your change:

```bash
.venv/bin/python scripts/build_ui.py
```

That writes `dashboard/dist/index.js` (the dashboard) and `desktop/plugin.js` (Hermes Desktop).

## What a pull request needs

- Tests for the change. Look for the nearest `tests/test_*.py` and follow its style.
- The checks passing: the test suite and `hermes plugins validate .` both run on every pull request.
- Docs kept in step: the README if users see the change, ARCHITECTURE.md if the design changes.

## What won't be merged

- Anything that sends data anywhere other than the Nostr relays the user chose (no analytics, no telemetry, no
  third-party fonts or scripts in the page).
- Tools, file access or network access for room agents, or any path from a stranger's text to the owner's full agent.
- New dependencies without an issue first. Ninsei runs inside Hermes and keeps to the packages Hermes already installs.

## Security

Please don't open a public issue for a security problem. Report it privately through GitHub: the repository's
Security tab, then "Report a vulnerability".

## Releases

The maintainer bumps the version and asks for the Hermes plugin catalog entry to be moved to the new commit. Merged
changes reach people who install from GitHub right away, and catalog installs at the next release.

By contributing you agree that your contribution is licensed under the repository's [license](LICENSE).
