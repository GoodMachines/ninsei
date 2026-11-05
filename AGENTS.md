# Agent notes

- Read `ARCHITECTURE.md` first: how the parts connect, the trust model and known pitfalls.
- `PLAN.md` is the hackathon plan; `implementation-notes.md` logs decisions as they happen.
- Tests: `.venv/bin/python -m pytest -q` (separate venv, not Hermes's).
- Before calling anything done: `hermes plugins validate .` must pass.
- Never change Justin's real Hermes profiles or gateways. Live tests use the throwaway profiles `xeniamaya` / `xeniasam` only.
- No pushing, GitHub repo, catalog PR, X post or form submission until Justin says so.
