"""Local state in one SQLite file under the plugin's data dir: settings, identity keys, room history,
the budget ledger and the outbox. One connection, guarded by a lock, used from the engine thread and
from `ninsei_say` in other processes (WAL mode makes that safe)."""
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
-- Private messages between two people (NIP-17), decrypted. One row per rumor id, so the copy wrapped to
-- myself and the copy my other install sent are one message. `peer` is the other person; `sender` is the
-- peer or me. `wrap` is the gift wrap I sent to the peer (its delivery status lives in event_outbox).
-- Readable by the user account only, like the keys above. Only the engine writes these tables, and nothing
-- that reaches a model or the gateway reads them.
CREATE TABLE IF NOT EXISTS dm_messages (
  id TEXT PRIMARY KEY, peer TEXT NOT NULL, sender TEXT NOT NULL, text TEXT NOT NULL,
  created_at INTEGER NOT NULL, arrived_at REAL NOT NULL, wrap TEXT);
CREATE INDEX IF NOT EXISTS dm_messages_peer ON dm_messages(peer, created_at);
-- A conversation partner: accepted (I wrote first, I accepted, or I have met them in a room) or a request.
-- `last_read` is an arrival time: what came after it, from the peer, is unread.
CREATE TABLE IF NOT EXISTS dm_peers (
  peer TEXT PRIMARY KEY, accepted INTEGER NOT NULL DEFAULT 0, first_at REAL NOT NULL, last_read REAL NOT NULL DEFAULT 0);
-- Gift wraps already opened (or refused): a restart or a relay replaying history costs one lookup, not a decryption.
CREATE TABLE IF NOT EXISTS dm_wraps (id TEXT PRIMARY KEY, at REAL NOT NULL);
-- Build progress, written by Ninsei's Hermes hooks in whatever process runs the owner's build chat
-- (ninsei_hooks.py). Coarse on purpose: a step count and a state, never tool names or contents.
CREATE TABLE IF NOT EXISTS build_progress (
  offer TEXT PRIMARY KEY, session TEXT NOT NULL, steps INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL, updated_at REAL NOT NULL);
"""

# private line limits: one owner message, one stored reply
LINE_OWNER_MAX = 8000
LINE_REPLY_MAX = 64000
LINE_CUT_NOTE = "\n\n[Ninsei cut this reply here: it is longer than 64,000 characters.]"
LINE_GATEWAY_FRESH = 45   # seconds: the adapter heartbeats every 10
LINE_TYPING_FRESH = 12    # seconds: the gateway re-sends typing every few seconds while it works


# room history kept on disk: age window (matches the engine's HISTORY_DAYS) and a per-room hard cap
EVENT_HISTORY_DAYS = 3
EVENT_ROOM_CAP = 1500
EVENT_PRUNE_EVERY = 100   # adds between cheap prune passes

# private messages kept on disk (like EVENT_ROOM_CAP for rooms): per conversation, for a sender not yet
# accepted (a request), how many such senders, and in all
DM_PER_PEER = 500
DM_PER_REQUEST = 20
DM_REQUEST_PEERS = 20
DM_TOTAL = 5000
DM_WRAP_MEMORY = 20000    # gift wrap ids remembered


def cap_reply(text: str) -> str:
    """A stored reply is at most LINE_REPLY_MAX characters. A longer one is cut with a visible note, so a
    reader never mistakes the cut for the end. (The gateway adapter splits long replies before they get here.)"""
    text = str(text or "")
    if len(text) <= LINE_REPLY_MAX:
        return text
    return text[:LINE_REPLY_MAX - len(LINE_CUT_NOTE)] + LINE_CUT_NOTE


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
        cols = {r[1] for r in self._db.execute("PRAGMA table_info(events)")}
        if "arrived_at" not in cols:  # databases from before arrival times were kept
            try:
                self._db.execute("ALTER TABLE events ADD COLUMN arrived_at REAL")
            except sqlite3.OperationalError:  # another process (ninsei_say) added it first
                pass
        self._db.commit()
        self.event_history_days = EVENT_HISTORY_DAYS
        self.event_room_cap = EVENT_ROOM_CAP
        self._adds = 0
        self._dm_wrap_adds = 0
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
    def add_event(self, room: str, ev: dict, arrived_at: Optional[float] = None) -> bool:
        """Store a room event. `arrived_at` is when it reached us live (None for a history pull, which has no
        real arrival time): the engine ranks games and name holders by it, so it has to survive a restart."""
        with self._lock:
            cur = self._db.execute(
                "INSERT OR IGNORE INTO events(id,room,kind,pubkey,created_at,json,arrived_at) VALUES(?,?,?,?,?,?,?)",
                (ev["id"], room, ev["kind"], ev["pubkey"], ev["created_at"], json.dumps(ev), arrived_at))
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

    def drop_events(self, ids: list[str]) -> None:
        if not ids:
            return
        with self._lock:
            self._db.executemany("DELETE FROM events WHERE id=?", [(i,) for i in ids])
            self._db.commit()

    def room_arrivals(self, room: str, limit: int = 400) -> dict[str, float]:
        """event id -> when it reached us live, for the same newest `limit` events `room_events` returns.
        Events stored without one (a history pull, or rows from before arrival times were kept) are absent."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id, arrived_at FROM events WHERE room=? ORDER BY created_at DESC, id DESC LIMIT ?",
                (room, limit)).fetchall()
        return {r[0]: float(r[1]) for r in reversed(rows) if r[1] is not None}

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

    def event_outbox_drop(self, ids: list[str]) -> None:
        """Delete rows outright (an accepted event needs none: unknown ids read as sent)."""
        if not ids:
            return
        with self._lock:
            self._db.executemany("DELETE FROM event_outbox WHERE id=?", [(i,) for i in ids])
            self._db.commit()

    def event_outbox_prune(self, older_than: float) -> None:
        """Forget finished (sent/failed) rows older than `older_than` seconds."""
        with self._lock:
            self._db.execute("DELETE FROM event_outbox WHERE status!='pending' AND updated_at < ?",
                             (time.time() - older_than,))
            self._db.commit()

    # --- private line (you and your own Hermes; see ninsei_platform.py) ---------------------------
    _LINE_COLS = ("id", "role", "text", "status", "reply_to", "created_at", "updated_at")

    def _line_row(self, row) -> dict:
        return dict(zip(self._LINE_COLS, row))

    def line_post_owner(self, text: str) -> dict:
        """The owner typed this in the local Ninsei UI. Queued for the gateway adapter to deliver."""
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

    def line_claim_owner(self, limit: int = 20, to: str = "delivered") -> list[dict]:
        """Atomically take queued owner messages (queued -> `to`), oldest first. The gateway adapter claims
        into "claimed" and marks a message "delivered" only once the gateway accepted it; `line_requeue`
        puts a claimed one back."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id,role,text,status,reply_to,created_at,updated_at FROM private_line "
                "WHERE role='owner' AND status='queued' ORDER BY created_at LIMIT ?", (limit,)).fetchall()
            out = []
            now = time.time()
            for r in rows:
                cur = self._db.execute("UPDATE private_line SET status=?, updated_at=? "
                                       "WHERE id=? AND status='queued'", (to, now, r[0]))
                if cur.rowcount:
                    out.append({**self._line_row(r), "status": to, "updated_at": now})
            self._db.commit()
        return out

    def line_requeue(self, ids: Optional[list[str]] = None) -> int:
        """Put claimed-but-undispatched owner messages back in the queue (all of them when `ids` is None,
        for a restarted adapter whose previous run died mid-batch). Returns how many went back."""
        with self._lock:
            if ids is None:
                cur = self._db.execute("UPDATE private_line SET status='queued', updated_at=? "
                                       "WHERE role='owner' AND status='claimed'", (time.time(),))
                n = cur.rowcount
            else:
                n = 0
                for mid in ids:
                    n += self._db.execute("UPDATE private_line SET status='queued', updated_at=? "
                                          "WHERE id=? AND role='owner' AND status='claimed'",
                                          (time.time(), mid)).rowcount
            self._db.commit()
        return n

    def line_set_status(self, mid: str, status: str) -> None:
        with self._lock:
            self._db.execute("UPDATE private_line SET status=?, updated_at=? WHERE id=?", (status, time.time(), mid))
            self._db.commit()

    def line_add_reply(self, text: str, reply_to: Optional[str] = None) -> dict:
        """A message from the owner's Hermes, written by the gateway adapter. Private: never published."""
        now = time.time()
        row = (uuid.uuid4().hex[:16], "hermes", cap_reply(text), "new", reply_to, now, now)
        with self._lock:
            self._db.execute("INSERT INTO private_line(id,role,text,status,reply_to,created_at,updated_at) "
                             "VALUES(?,?,?,?,?,?,?)", row)
            self._db.execute("DELETE FROM kv WHERE k='line_typing'")
            self._db.commit()
        return self._line_row(row)

    def line_edit_reply(self, mid: str, text: str) -> bool:
        with self._lock:
            cur = self._db.execute("UPDATE private_line SET text=?, updated_at=? WHERE id=? AND role='hermes'",
                                   (cap_reply(text), time.time(), mid))
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

    # --- private messages (NIP-17; see dm.py and the engine's dm_* methods) --------------------------
    def dm_wrap_seen(self, wid: str) -> bool:
        with self._lock:
            return self._db.execute("SELECT 1 FROM dm_wraps WHERE id=?", (wid,)).fetchone() is not None

    def dm_wrap_mark(self, wid: str) -> None:
        with self._lock:
            cur = self._db.execute("INSERT OR IGNORE INTO dm_wraps(id, at) VALUES(?,?)", (wid, time.time()))
            if cur.rowcount:
                self._dm_wrap_adds += 1
                if self._dm_wrap_adds % 200 == 0:
                    self._db.execute("DELETE FROM dm_wraps WHERE id NOT IN "
                                     "(SELECT id FROM dm_wraps ORDER BY at DESC LIMIT ?)", (DM_WRAP_MEMORY,))
            self._db.commit()

    def dm_add(self, *, id: str, peer: str, sender: str, text: str, created_at: int, arrived_at: float,
               wrap: Optional[str] = None, accepted: bool = False) -> str:
        """Store one message. Returns "added", "duplicate" (this rumor is already here) or "limit" (a request
        sender over their caps). `accepted` says whether this conversation is one I have said yes to (or
        have a reason to): a stranger gets DM_PER_REQUEST messages, and there is room for DM_REQUEST_PEERS of
        them. Past DM_PER_PEER in one conversation the oldest go; past DM_TOTAL the biggest conversation
        loses its oldest, so one sender can't push everyone else's out."""
        with self._lock:
            if self._db.execute("SELECT 1 FROM dm_messages WHERE id=?", (id,)).fetchone():
                return "duplicate"
            row = self._db.execute("SELECT accepted FROM dm_peers WHERE peer=?", (peer,)).fetchone()
            ok = bool(accepted or (row and row[0]))
            if row is None:
                if not ok:
                    (n,) = self._db.execute("SELECT COUNT(*) FROM dm_peers WHERE accepted=0").fetchone()
                    if n >= DM_REQUEST_PEERS:
                        return "limit"
                self._db.execute("INSERT INTO dm_peers(peer, accepted, first_at, last_read) VALUES(?,?,?,?)",
                                 (peer, 1 if ok else 0, arrived_at, arrived_at if sender != peer else 0))
            elif ok and not row[0]:
                self._db.execute("UPDATE dm_peers SET accepted=1 WHERE peer=?", (peer,))
            if not ok:
                (n,) = self._db.execute("SELECT COUNT(*) FROM dm_messages WHERE peer=?", (peer,)).fetchone()
                if n >= DM_PER_REQUEST:
                    return "limit"
            self._db.execute("INSERT INTO dm_messages(id, peer, sender, text, created_at, arrived_at, wrap) "
                             "VALUES(?,?,?,?,?,?,?)", (id, peer, sender, text, created_at, arrived_at, wrap))
            self._db.execute("DELETE FROM dm_messages WHERE peer=? AND id NOT IN (SELECT id FROM dm_messages "
                             "WHERE peer=? ORDER BY created_at DESC, arrived_at DESC, id DESC LIMIT ?)",
                             (peer, peer, DM_PER_PEER))
            while True:
                (total,) = self._db.execute("SELECT COUNT(*) FROM dm_messages").fetchone()
                if total <= DM_TOTAL:
                    break
                big = self._db.execute("SELECT peer FROM dm_messages GROUP BY peer ORDER BY COUNT(*) DESC LIMIT 1").fetchone()
                self._db.execute("DELETE FROM dm_messages WHERE id IN (SELECT id FROM dm_messages WHERE peer=? "
                                 "ORDER BY created_at, arrived_at, id LIMIT ?)", (big[0], total - DM_TOTAL))
            self._db.commit()
            return "added"

    def dm_accept(self, peer: str) -> bool:
        with self._lock:
            cur = self._db.execute("UPDATE dm_peers SET accepted=1 WHERE peer=?", (peer,))
            self._db.commit()
            return cur.rowcount > 0

    def dm_peer(self, peer: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute("SELECT accepted, first_at, last_read FROM dm_peers WHERE peer=?", (peer,)).fetchone()
        return {"accepted": bool(row[0]), "first_at": row[1], "last_read": row[2]} if row else None

    def dm_messages(self, peer: str, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, sender, text, created_at, arrived_at, wrap FROM dm_messages WHERE peer=? "
                "ORDER BY created_at DESC, arrived_at DESC, id DESC LIMIT ?", (peer, limit)).fetchall()
        return [dict(zip(("id", "sender", "text", "created_at", "arrived_at", "wrap"), r)) for r in reversed(rows)]

    def dm_threads(self, limit: int = 100) -> list[dict]:
        """Every conversation, newest first: {peer, accepted, unread, last_ts}. Counts only; the text of the
        newest unread message comes from `dm_newest_unread`, for the alert."""
        with self._lock:
            rows = self._db.execute(
                "SELECT p.peer, p.accepted, p.first_at, p.last_read, "
                "(SELECT COUNT(*) FROM dm_messages m WHERE m.peer=p.peer AND m.sender=p.peer AND m.arrived_at>p.last_read), "
                "COALESCE((SELECT MAX(created_at) FROM dm_messages m WHERE m.peer=p.peer), 0) AS last_ts "
                "FROM dm_peers p WHERE EXISTS (SELECT 1 FROM dm_messages m WHERE m.peer=p.peer) "
                "ORDER BY last_ts DESC, p.peer LIMIT ?", (limit,)).fetchall()
        return [{"peer": r[0], "accepted": bool(r[1]), "first_at": r[2], "last_read": r[3], "unread": r[4], "last_ts": r[5]}
                for r in rows]

    def dm_newest_unread(self, peer: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute(
                "SELECT m.id, m.text, m.created_at FROM dm_messages m JOIN dm_peers p ON p.peer=m.peer "
                "WHERE m.peer=? AND m.sender=m.peer AND m.arrived_at>p.last_read "
                "ORDER BY m.arrived_at DESC, m.id DESC LIMIT 1", (peer,)).fetchone()
        return {"id": row[0], "text": row[1], "ts": row[2]} if row else None

    def dm_mark_read(self, peer: str) -> None:
        with self._lock:
            self._db.execute("UPDATE dm_peers SET last_read=MAX(last_read, COALESCE("
                             "(SELECT MAX(arrived_at) FROM dm_messages WHERE peer=?), 0)) WHERE peer=?", (peer, peer))
            self._db.commit()

    def dm_forget(self, peer: str) -> int:
        """Delete a conversation from this computer (the other person's copy, and relays', are theirs)."""
        with self._lock:
            n = self._db.execute("DELETE FROM dm_messages WHERE peer=?", (peer,)).rowcount
            self._db.execute("DELETE FROM dm_peers WHERE peer=?", (peer,))
            self._db.commit()
        return n

    def dm_counts(self) -> dict:
        with self._lock:
            (msgs,) = self._db.execute("SELECT COUNT(*) FROM dm_messages").fetchone()
            (peers,) = self._db.execute("SELECT COUNT(*) FROM dm_peers").fetchone()
        return {"messages": msgs, "peers": peers}
