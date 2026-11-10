# Agent notes

- Read `ARCHITECTURE.md` first: how the parts connect, the trust model and known pitfalls.
- `PLAN.md` is the hackathon plan; `implementation-notes.md` logs decisions as they happen.
- Tests: `.venv/bin/python -m pytest -q` (separate venv, not Hermes's).
- Before calling anything done: `hermes plugins validate .` must pass.
- Never change Justin's real Hermes profiles or gateways. Live tests use the throwaway profiles `xeniamaya` / `xeniasam` only, plus `xeniaeve` for the demo's impostor seat (Justin's OK, 2026-11-08).
- The repo is public at GoodMachines/ninsei and in the Hermes plugin catalog (accepted 2026-11-10). `main` is protected: changes go in by pull request, and the `checks` workflow (tests plus `hermes plugins validate .`) must pass. Merging a tested PR is fine. A release is a version bump plus a PR to NousResearch/hermes-agent moving `plugin-catalog/ninsei.yaml` to the new commit; open that, an X post or a form submission only when Justin says so. Outside contributors: see CONTRIBUTING.md.
