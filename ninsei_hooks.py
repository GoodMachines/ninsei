"""Hermes hooks that let a room see your agent building the toy it offered.

A toy gets built in the owner's own Hermes chat (the CLI, Desktop or the private line), which is a
different process from the Ninsei engine. These hooks run inside that chat's process. They spot the
build session by the private build key the build prompt carries (the offer id is public, so it can't), and from then
on record coarse progress for that offer in Ninsei's SQLite file:

* `pre_llm_call`: a turn starts, so the build is working (and an unknown session is matched here).
* `pre_tool_call`: one more step. The count is all that's kept: never the tool's name or arguments.
* `on_human_input_request` / `_resolved`: the build waits on the owner (an approval, a question).
* `post_llm_call`: the turn ended.

The engine reads the table and shows the agent as building, with the step count, to the room.

Every hook returns None (a `pre_tool_call` dict could block a tool, and these must never steer the
agent) and swallows its own errors: a broken progress write must not break the owner's chat. Only
offers the owner accepted (status "building" in the store) are tracked, so a pasted or quoted offer
line, or a message that only knows the public id, can't light up anything else.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from typing import Any, Optional

from . import _loader

log = logging.getLogger("ninsei.hooks")

# The offer id is public in the room, so it can't tie a session to a build. The build prompt carries a key
# made when the owner accepted (private, kept in the store): only a session that was given it is tracked.
BUILD_KEY = re.compile(r'ninsei build key \(private\): ([0-9a-f]{32})\b')
MAX_STEPS = 999

_lock = threading.Lock()
_sessions: dict[str, str] = {}      # session id -> offer id, for this process
_conn: Optional[sqlite3.Connection] = None

_SCHEMA = ("CREATE TABLE IF NOT EXISTS build_progress (offer TEXT PRIMARY KEY, session TEXT NOT NULL, "
           "steps INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL, updated_at REAL NOT NULL)")


def _db() -> Optional[sqlite3.Connection]:
    """Ninsei's store, only if it already exists in this profile. Never creates it, never starts the engine."""
    global _conn
    if _conn is None:
        path = _loader.load_engine().db_path_if_present()
        if path is None:
            return None
        _conn = sqlite3.connect(str(path), timeout=2, check_same_thread=False)
        _conn.execute(_SCHEMA)
        _conn.commit()
    return _conn


def _building(db: sqlite3.Connection, offer: str) -> bool:
    row = db.execute("SELECT v FROM kv WHERE k='offers'").fetchone()
    try:
        offers = json.loads(row[0]) if row else {}
        return isinstance(offers, dict) and (offers.get(offer) or {}).get("status") == "building"
    except (ValueError, AttributeError):
        return False


def _offer_for(session_id: Any, text: Any = None, db: Optional[sqlite3.Connection] = None) -> Optional[str]:
    if not isinstance(session_id, str) or not session_id:
        return None
    offer = _sessions.get(session_id)
    if offer is None and isinstance(text, str) and db is not None:
        m = BUILD_KEY.search(text)
        if m:
            offer = _offer_with_key(db, m.group(1))
    return offer


def _offer_with_key(db: sqlite3.Connection, key: str) -> Optional[str]:
    row = db.execute("SELECT v FROM kv WHERE k='offers'").fetchone()
    try:
        offers = json.loads(row[0]) if row else {}
        for oid, o in offers.items():
            if isinstance(o, dict) and o.get("status") == "building" and o.get("build_key") == key:
                return oid
    except (ValueError, AttributeError):
        pass
    return None


def _record(session_id: Any, *, text: Any = None, state: Optional[str] = None, step: bool = False) -> None:
    try:
        with _lock:
            # These hooks run on every turn of every Hermes chat: only a known build session, or a message that
            # carries a build key, loads the engine and opens the store.
            if not isinstance(session_id, str) or not session_id:
                return
            if session_id not in _sessions and not (isinstance(text, str) and BUILD_KEY.search(text)):
                return
            db = _db()
            if db is None:
                return
            offer = _offer_for(session_id, text, db)
            if offer is None:
                return
            if not _building(db, offer):        # finished, shared or declined: stop tracking this session
                _sessions.pop(session_id, None)
                return
            _sessions[session_id] = offer
            now = time.time()
            db.execute("INSERT INTO build_progress (offer, session, steps, state, updated_at) VALUES (?, ?, 0, ?, ?) "
                       "ON CONFLICT(offer) DO NOTHING", (offer, session_id, state or "working", now))
            db.execute("UPDATE build_progress SET session=?, steps=MIN(steps + ?, ?), state=COALESCE(?, state), "
                       "updated_at=? WHERE offer=?", (session_id, 1 if step else 0, MAX_STEPS, state, now, offer))
            db.commit()
    except Exception:  # progress is decoration: never let it break the owner's chat
        log.debug("ninsei build progress write failed", exc_info=True)


def _text(value: Any) -> Any:
    if isinstance(value, list):  # multimodal turns: keep the text parts
        return "\n".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in value)
    return value


def pre_llm_call(session_id: Any = None, user_message: Any = None, **_kw) -> None:
    _record(session_id, text=_text(user_message), state="working")
    return None


def pre_tool_call(session_id: Any = None, **_kw) -> None:
    _record(session_id, state="working", step=True)
    return None


def on_human_input_request(session_id: Any = None, **_kw) -> None:
    _record(session_id, state="waiting")
    return None


def on_human_input_resolved(session_id: Any = None, **_kw) -> None:
    _record(session_id, state="working")
    return None


def post_llm_call(session_id: Any = None, **_kw) -> None:
    _record(session_id, state="paused")
    return None


HOOKS = {
    "pre_llm_call": pre_llm_call,
    "pre_tool_call": pre_tool_call,
    "on_human_input_request": on_human_input_request,
    "on_human_input_resolved": on_human_input_resolved,
    "post_llm_call": post_llm_call,
}


def register(ctx) -> None:
    if not hasattr(ctx, "register_hook"):
        return
    for name, fn in HOOKS.items():
        ctx.register_hook(name, fn)
