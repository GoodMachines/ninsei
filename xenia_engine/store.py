"""Local state in one SQLite file under the plugin's data dir: settings, identity keys, room history,
the budget ledger and the outbox. One connection, guarded by a lock, used from the engine thread and
from `xenia_say` in other processes (WAL mode makes that safe)."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY, room TEXT, kind INTEGER, pubkey TEXT, created_at INTEGER, json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS events_room ON events(room, created_at);
CREATE TABLE IF NOT EXISTS rooms (id TEXT PRIMARY KEY, meta TEXT NOT NULL, joined_at INTEGER, last_read INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS ledger (
  id TEXT PRIMARY KEY, day TEXT NOT NULL, category TEXT NOT NULL, reserved INTEGER NOT NULL,
  used INTEGER, created_at REAL NOT NULL, settled_at REAL);
CREATE INDEX IF NOT EXISTS ledger_day ON ledger(day);
CREATE TABLE IF NOT EXISTS outbox (
  id TEXT PRIMARY KEY, room TEXT NOT NULL, text TEXT NOT NULL, origin TEXT, status TEXT NOT NULL, created_at REAL NOT NULL);
-- Signed events no relay has acknowledged yet (the relay pool resends them on reconnect).
CREATE TABLE IF NOT EXISTS event_outbox (
  id TEXT PRIMARY KEY, json TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
-- The private line: the owner and their own full Hermes, never published. Only the local UI writes
-- 'owner' rows; only the gateway adapter writes 'hermes' rows. Nothing that reads relays touches it.
CREATE TABLE IF NOT EXISTS private_line (
  id TEXT PRIMARY KEY, role TEXT NOT NULL, text TEXT NOT NULL, status TEXT NOT NULL,
  reply_to TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS private_line_status ON private_line(role, status);
CREATE INDEX IF NOT EXISTS private_line_time ON private_line(created_at);
-- Build progress, written by Xenia's Hermes hooks in whatever process runs the owner's build chat
-- (xenia_hooks.py). Coarse on purpose: a step count and a state, never tool names or contents.
CREATE TABLE IF NOT EXISTS build_progress (
  offer TEXT PRIMARY KEY, session TEXT NOT NULL, steps INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL, updated_at REAL NOT NULL);
"""

# private line limits: one owner message, one stored reply
LINE_OWNER_MAX = 8000
LINE_REPLY_MAX = 64000
LINE_GATEWAY_FRESH = 45   # seconds: the adapter heartbeats every 10
LINE_TYPING_FRESH = 12    # seconds: the gateway re-sends typing every few seconds while it works


# room history kept on disk: age window (matches the engine's HISTORY_DAYS) and a per-room hard cap
EVENT_HISTORY_DAYS = 3
EVENT_ROOM_CAP = 1500
EVENT_PRUNE_EVERY = 100   # adds between cheap prune passes


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        # The database holds the person's and agent's Nostr secret keys: owner-only, files and folder.
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        self._lock = threading.RLock()
        old_umask = os.umask(0o077)
        try:
            self._db = sqlite3.connect(str(self.path), check_same_thread=False, timeout=10)
            self._db.execute("PRAGMA journal_mode=WAL")
        finally:
            os.umask(old_umask)
        for suffix in ("", "-wal", "-shm"):  # tighten files an earlier version created
            f = Path(str(self.path) + suffix)
            if f.exists():
                os.chmod(f, 0o600)
        self._db.executescript(SCHEMA)
        self._db.commit()
        self.event_history_days = EVENT_HISTORY_DAYS
        self.event_room_cap = EVENT_ROOM_CAP
        self._adds = 0
        self.prune_events()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # --- kv ---------------------------------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._db.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._db.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                             (key, json.dumps(value)))
            self._db.commit()

    # --- events -----------------------------------------------------------------------------------
    def add_event(self, room: str, ev: dict) -> bool:
        with self._lock:
            cur = self._db.execute(
                "INSERT OR IGNORE INTO events(id,room,kind,pubkey,created_at,json) VALUES(?,?,?,?,?,?)",
                (ev["id"], room, ev["kind"], ev["pubkey"], ev["created_at"], json.dumps(ev)))
            self._db.commit()
            added = cur.rowcount > 0
            if added:
                self._adds += 1
                if self._adds % EVENT_PRUNE_EVERY == 0:
                    self.prune_events(room)
            return added

    def prune_events(self, room: Optional[str] = None) -> int:
        """Drop events older than the history window and keep only the newest `event_room_cap` per room."""
        cutoff = int(time.time() - self.event_history_days * 86400)
        removed = 0
        with self._lock:
            removed += self._db.execute("DELETE FROM events WHERE created_at < ?", (cutoff,)).rowcount
            rooms = [room] if room else [r[0] for r in self._db.execute("SELECT DISTINCT room FROM events")]
            for r in rooms:
                removed += self._db.execute(
                    "DELETE FROM events WHERE room=? AND id NOT IN (SELECT id FROM events WHERE room=? "
                    "ORDER BY created_at DESC, id DESC LIMIT ?)", (r, r, self.event_room_cap)).rowcount
            self._db.commit()
        return removed

    def room_events(self, room: str, limit: int = 400) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT json FROM events WHERE room=? ORDER BY created_at DESC, id DESC LIMIT ?",
                (room, limit)).fetchall()
        return [json.loads(r[0]) for r in reversed(rows)]

    # --- rooms ------------------------------------------------------------------------------------
    def save_room(self, room_id: str, meta: dict) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO rooms(id,meta,joined_at) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET meta=excluded.meta",
                (room_id, json.dumps(meta), int(time.time())))
            self._db.commit()

    def forget_room(self, room_id: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM rooms WHERE id=?", (room_id,))
            self._db.execute("DELETE FROM events WHERE room=?", (room_id,))
            self._db.commit()

    def rooms(self) -> dict[str, dict]:
        with self._lock:
            rows = self._db.execute("SELECT id, meta, last_read FROM rooms ORDER BY joined_at").fetchall()
        return {r[0]: {**json.loads(r[1]), "last_read": r[2]} for r in rows}

    def mark_read(self, room_id: str, ts: int) -> None:
        with self._lock:
            self._db.execute("UPDATE rooms SET last_read=MAX(last_read, ?) WHERE id=?", (ts, room_id))
            self._db.commit()

    # --- budget ledger ----------------------------------------------------------------------------
    def budget_used(self, day: Optional[str] = None) -> dict[str, int]:
        day = day or today()
        with self._lock:
            rows = self._db.execute(
                "SELECT category, SUM(COALESCE(used, reserved)) FROM ledger WHERE day=? GROUP BY category",
                (day,)).fetchall()
        return {r[0]: int(r[1] or 0) for r in rows}

    def reserve(self, category: str, tokens: int, limit: int) -> Optional[str]:
        """Atomically reserve `tokens` against today's limit. Returns a ticket, or None if it won't fit."""
        day = today()
        with self._lock:
            (spent,) = self._db.execute(
                "SELECT COALESCE(SUM(COALESCE(used, reserved)),0) FROM ledger WHERE day=?", (day,)).fetchone()
            if spent + tokens > limit:
                return None
            tid = uuid.uuid4().hex
            self._db.execute("INSERT INTO ledger(id,day,category,reserved,created_at) VALUES(?,?,?,?,?)",
                             (tid, day, category, tokens, time.time()))
            self._db.commit()
            return tid

    def settle(self, ticket: str, used: int) -> None:
        with self._lock:
            self._db.execute("UPDATE ledger SET used=?, settled_at=? WHERE id=?", (int(used), time.time(), ticket))
            self._db.commit()

    # --- outbox -----------------------------------------------------------------------------------
    def queue_draft(self, room: str, text: str, origin: str) -> str:
        oid = uuid.uuid4().hex[:12]
        with self._lock:
            self._db.execute("INSERT INTO outbox(id,room,text,origin,status,created_at) VALUES(?,?,?,?,?,?)",
                             (oid, room, text, origin, "draft", time.time()))
            self._db.commit()
        return oid

    def drafts(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id,room,text,origin,created_at FROM outbox WHERE status='draft' ORDER BY created_at").fetchall()
        return [dict(zip(("id", "room", "text", "origin", "created_at"), r)) for r in rows]

    def set_draft_status(self, oid: str, status: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute("SELECT id,room,text FROM outbox WHERE id=? AND status='draft'", (oid,)).fetchone()
            if not row:
                return None
            self._db.execute("UPDATE outbox SET status=? WHERE id=?", (status, oid))
            self._db.commit()
        return {"id": row[0], "room": row[1], "text": row[2]}

    # --- event outbox (signed events waiting for a relay to acknowledge them) ---------------------
    def event_outbox_put(self, ev: dict, status: str = "pending") -> None:
        now = time.time()
        with self._lock:
            self._db.execute(
                "INSERT INTO event_outbox(id,json,status,created_at,updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at",
                (ev["id"], json.dumps(ev), status, now, now))
            self._db.commit()

    def event_outbox_set(self, eid: str, status: str) -> None:
        with self._lock:
            self._db.execute("UPDATE event_outbox SET status=?, updated_at=? WHERE id=?", (status, time.time(), eid))
            self._db.commit()

    def event_outbox_status(self, eid: str) -> Optional[str]:
        with self._lock:
            row = self._db.execute("SELECT status FROM event_outbox WHERE id=?", (eid,)).fetchone()
        return row[0] if row else None

    def event_outbox_pending(self) -> list[tuple[dict, float]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT json, created_at FROM event_outbox WHERE status='pending' ORDER BY created_at").fetchall()
        return [(json.loads(r[0]), r[1]) for r in rows]

    def event_outbox_prune(self, older_than: float) -> None:
        """Forget finished (sent/failed) rows older than `older_than` seconds."""
        with self._lock:
            self._db.execute("DELETE FROM event_outbox WHERE status!='pending' AND updated_at < ?",
                             (time.time() - older_than,))
            self._db.commit()

    # --- private line (you and your own Hermes; see xenia_platform.py) ---------------------------
    _LINE_COLS = ("id", "role", "text", "status", "reply_to", "created_at", "updated_at")

    def _line_row(self, row) -> dict:
        return dict(zip(self._LINE_COLS, row))

    def line_post_owner(self, text: str) -> dict:
        """The owner typed this in the local Xenia UI. Queued for the gateway adapter to deliver."""
        text = str(text or "").strip()[:LINE_OWNER_MAX]
        if not text:
            raise ValueError("empty message")
        now = time.time()
        row = (uuid.uuid4().hex[:16], "owner", text, "queued", None, now, now)
        with self._lock:
            self._db.execute("INSERT INTO private_line(id,role,text,status,reply_to,created_at,updated_at) "
                             "VALUES(?,?,?,?,?,?,?)", row)
            self._db.commit()
        return self._line_row(row)

    def line_claim_owner(self, limit: int = 20) -> list[dict]:
        """Atomically take queued owner messages (queued -> delivered), oldest first."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id,role,text,status,reply_to,created_at,updated_at FROM private_line "
                "WHERE role='owner' AND status='queued' ORDER BY created_at LIMIT ?", (limit,)).fetchall()
            out = []
            now = time.time()
            for r in rows:
                cur = self._db.execute("UPDATE private_line SET status='delivered', updated_at=? "
                                       "WHERE id=? AND status='queued'", (now, r[0]))
                if cur.rowcount:
                    out.append({**self._line_row(r), "status": "delivered", "updated_at": now})
            self._db.commit()
        return out

    def line_set_status(self, mid: str, status: str) -> None:
        with self._lock:
            self._db.execute("UPDATE private_line SET status=?, updated_at=? WHERE id=?", (status, time.time(), mid))
            self._db.commit()

    def line_add_reply(self, text: str, reply_to: Optional[str] = None) -> dict:
        """A message from the owner's Hermes, written by the gateway adapter. Private: never published."""
        now = time.time()
        row = (uuid.uuid4().hex[:16], "hermes", str(text or "")[:LINE_REPLY_MAX], "new", reply_to, now, now)
        with self._lock:
            self._db.execute("INSERT INTO private_line(id,role,text,status,reply_to,created_at,updated_at) "
                             "VALUES(?,?,?,?,?,?,?)", row)
            self._db.execute("DELETE FROM kv WHERE k='line_typing'")
            self._db.commit()
        return self._line_row(row)

    def line_edit_reply(self, mid: str, text: str) -> bool:
        with self._lock:
            cur = self._db.execute("UPDATE private_line SET text=?, updated_at=? WHERE id=? AND role='hermes'",
                                   (str(text or "")[:LINE_REPLY_MAX], time.time(), mid))
            self._db.commit()
            return cur.rowcount > 0

    def line_get(self, mid: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute("SELECT id,role,text,status,reply_to,created_at,updated_at FROM private_line "
                                   "WHERE id=?", (mid,)).fetchone()
        return self._line_row(row) if row else None

    def line_messages(self, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id,role,text,status,reply_to,created_at,updated_at FROM private_line "
                "ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [self._line_row(r) for r in reversed(rows)]

    def line_reply_to_draft(self, reply_id: str, room: str) -> dict:
        """"Post to room": one of your Hermes's replies becomes a room draft. Nothing is published here;
        the owner sends (or edits, or discards) the draft from the room's tray like any other."""
        msg = self.line_get(reply_id)
        if not msg or msg["role"] != "hermes":
            raise ValueError("That reply is not in your private line.")
        rooms = self.rooms()
        if room not in rooms:
            raise ValueError("You are not in that room.")
        full = msg["text"].strip()
        if not full:
            raise ValueError("That reply is empty.")
        return {"draft": self.queue_draft(room, full[:1200], "your Hermes"), "room": room,
                "room_name": rooms[room].get("name", ""), "truncated": len(full) > 1200}

    def line_heartbeat(self) -> None:
        self.set("line_gateway_at", time.time())

    def line_typing(self, on: bool) -> None:
        if on:
            self.set("line_typing", time.time())
        else:
            with self._lock:
                self._db.execute("DELETE FROM kv WHERE k='line_typing'")
                self._db.commit()

    def line_mark_read(self) -> None:
        self.set("line_read_at", time.time())

    def build_progress(self) -> dict[str, dict]:
        with self._lock:
            rows = self._db.execute("SELECT offer, steps, state, updated_at FROM build_progress").fetchall()
        return {r[0]: {"steps": int(r[1]), "state": r[2], "at": float(r[3])} for r in rows}

    def build_progress_drop(self, offer: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM build_progress WHERE offer=?", (offer,))
            self._db.commit()

    def line_summary(self) -> dict:
        """Small and stable enough to sit in every /state snapshot: it changes only when the thread does."""
        now = time.time()
        with self._lock:
            n, last_at = self._db.execute("SELECT COUNT(*), MAX(updated_at) FROM private_line").fetchone()
            (queued,) = self._db.execute(
                "SELECT COUNT(*) FROM private_line WHERE role='owner' AND status='queued'").fetchone()
        read_at = self.get("line_read_at", 0) or 0
        with self._lock:
            (unread,) = self._db.execute(
                "SELECT COUNT(*) FROM private_line WHERE role='hermes' AND created_at>?", (read_at,)).fetchone()
        return {"count": n, "rev": f"{n}:{last_at or 0:.3f}", "queued": queued, "unread": unread,
                "typing": now - (self.get("line_typing", 0) or 0) < LINE_TYPING_FRESH,
                "gateway": now - (self.get("line_gateway_at", 0) or 0) < LINE_GATEWAY_FRESH}
