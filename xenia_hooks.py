"""Hermes hooks that let a room see your agent building the toy it offered.

A toy gets built in the owner's own Hermes chat (the CLI, Desktop or the private line), which is a
different process from the Xenia engine. These hooks run inside that chat's process. They spot the
build session by the offer line the build prompt asks for (`::xenia-offer{id="..."}`), and from then
on record coarse progress for that offer in Xenia's SQLite file:

* `pre_llm_call`: a turn starts, so the build is working (and an unknown session is matched here).
* `pre_tool_call`: one more step. The count is all that's kept: never the tool's name or arguments.
* `on_human_input_request` / `_resolved`: the build waits on the owner (an approval, a question).
* `post_llm_call`: the turn ended.

The engine reads the table and shows the agent as building, with the step count, to the room.

Every hook returns None (a `pre_tool_call` dict could block a tool, and these must never steer the
agent) and swallows its own errors: a broken progress write must not break the owner's chat. Only
offers the owner accepted (status "building" in the store) are tracked, so a pasted or quoted offer
line can't light up anything else.
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

log = logging.getLogger("xenia.hooks")

OFFER_LINE = re.compile(r'::xenia-offer\{id="([0-9a-f]{64})"\}')
MAX_STEPS = 999

_lock = threading.Lock()
_sessions: dict[str, str] = {}      # session id -> offer id, for this process
_conn: Optional[sqlite3.Connection] = None

_SCHEMA = ("CREATE TABLE IF NOT EXISTS build_progress (offer TEXT PRIMARY KEY, session TEXT NOT NULL, "
           "steps INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL, updated_at REAL NOT NULL)")


def _db() -> Optional[sqlite3.Connection]:
    """Xenia's store, only if it already exists in this profile. Never creates it, never starts the engine."""
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


def _offer_for(session_id: Any, text: Any = None) -> Optional[str]:
    if not isinstance(session_id, str) or not session_id:
        return None
    offer = _sessions.get(session_id)
    if offer is None and isinstance(text, str):
        m = OFFER_LINE.search(text)
        offer = m.group(1) if m else None
    return offer


def _record(session_id: Any, *, text: Any = None, state: Optional[str] = None, step: bool = False) -> None:
    try:
        with _lock:
            offer = _offer_for(session_id, text)
            if offer is None:
                return
            db = _db()
            if db is None:
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
        log.debug("xenia build progress write failed", exc_info=True)


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
