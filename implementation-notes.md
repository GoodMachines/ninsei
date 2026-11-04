# Implementation notes

Decisions not in the brief, tradeoffs and surprises, newest last.

## 2026-11-04
- **Neighbours the brief didn't list:** `huddo` (people + agents in one group chat, hosted on api.huddo.ai, MCP) and `index-network` (agents matching people by interest) are already in the catalog. Hearth's differentiators are therefore: native Desktop UI, no server ($0), budgets in code, the offer → build → Share loop, games.
- **Transport spike:** results are in PLAN.md. Pure-Python BIP-340 signing works, and no new Python deps are needed: Hermes's runtime env (Python 3.14, under `~/.hermes/installs/.../venv`) already has websockets 15, aiohttp, cryptography. Note `~/.hermes/hermes-agent/venv` is a stale 3.11 env and is not what Hermes runs on.
- **Process model spike:** under `hermes dashboard --isolated`, `register(ctx)` and `dashboard/plugin_api.py` share a PID, and `ctx.llm` works from a route (via `asyncio.to_thread`). `plugin_api.py` is imported by file path as `hermes_dashboard_plugin_hearth`, so relative imports don't work. Both halves load the engine through `_loader.py` under one private module name, `hearth_room_engine`. The no-core-override lint only flags `sys.modules[...]` writes to Hermes module names, so this is allowed.
- **Test profiles:** `hearthmaya` was cloned from default, with plugins trimmed to just `hearth`. The repo is symlinked into `~/.hermes/profiles/hearthmaya/plugins/hearth`. The default profile's config is unchanged (checked).
- **Rules on multiple entries:** not found publicly. The typeform only shows a start page; question for Justin.
- **Game:** switched from trivia to a bluffing game (Tall Tales) after review. The fake-answer mechanic is an old parlour-game genre; names and content are original.
