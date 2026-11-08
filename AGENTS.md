# Agent notes

- Read `ARCHITECTURE.md` first: how the parts connect, the trust model and known pitfalls.
- `PLAN.md` is the hackathon plan; `implementation-notes.md` logs decisions as they happen.
- Tests: `.venv/bin/python -m pytest -q` (separate venv, not Hermes's).
- Before calling anything done: `hermes plugins validate .` must pass.
- Never change Justin's real Hermes profiles or gateways. Live tests use the throwaway profiles `xeniamaya` / `xeniasam` only, plus `xeniaeve` for the demo's impostor seat (Justin's OK, 2026-11-08).
- The repo is public at GoodMachines/ninsei (Justin's OK, 2026-11-07); pushing tested commits to `main` is fine. No catalog PR, X post or form submission until Justin says so. Before the catalog PR opens, `.venv/bin/python scripts/check_submission.py` must print "ready" (Hermes's own catalog validator accepts the placeholder sha).
