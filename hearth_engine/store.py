"""Local state in one SQLite file under the plugin's data dir: settings, identity keys, room history,
the budget ledger and the outbox. One connection, guarded by a lock, used from the engine thread and
from `hearth_say` in other processes (WAL mode makes that safe)."""
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
"""


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
            return cur.rowcount > 0

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
