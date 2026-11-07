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
-- A conversation partner. `accepted` is unused since friends-only DMs (it is always 1); who may write to me lives
-- in dm_friends. `last_read` is an arrival time: what came after it, from the peer, is unread.
CREATE TABLE IF NOT EXISTS dm_peers (
  peer TEXT PRIMARY KEY, accepted INTEGER NOT NULL DEFAULT 0, first_at REAL NOT NULL, last_read REAL NOT NULL DEFAULT 0);
-- Friends. Each side's latest word: `mine` / `theirs` is 1 after that person sent a friend request or accept,
-- 0 after a removal; `*_at` is that event's own date (a stale event is dropped). Friends = both 1. A request I
-- have not answered = theirs 1, mine 0. `ignored_at` is when I ignored their request (local; remembered 30 days).
-- A row with both 0 is a tombstone that keeps an older replayed event from coming back.
CREATE TABLE IF NOT EXISTS dm_friends (
  peer TEXT PRIMARY KEY, mine INTEGER NOT NULL DEFAULT 0, mine_at INTEGER NOT NULL DEFAULT 0,
  theirs INTEGER NOT NULL DEFAULT 0, theirs_at INTEGER NOT NULL DEFAULT 0,
  ignored_at REAL NOT NULL DEFAULT 0, first_at REAL NOT NULL, since REAL NOT NULL DEFAULT 0);
-- Gift wraps already opened (or refused): a restart or a relay replaying history costs one lookup, not a decryption.
CREATE TABLE IF NOT EXISTS dm_wraps (id TEXT PRIMARY KEY, at REAL NOT NULL);
-- What people in my rooms look like: a profile picture (kind 'avatar', the image bytes, already checked by
-- avatar.py) or a built face (kind 'face', JSON). One row per (person, kind): the newest event wins, and an
-- empty one ("I removed it") is kept as a row with no data so an older copy can't bring it back.
CREATE TABLE IF NOT EXISTS person_art (
  pk TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, created_at INTEGER NOT NULL,
  mime TEXT NOT NULL DEFAULT '', data BLOB, arrived_at REAL NOT NULL, PRIMARY KEY (pk, kind));
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

# private messages kept on disk (like EVENT_ROOM_CAP for rooms): per conversation and in all
DM_PER_PEER = 500
DM_TOTAL = 5000
# friends: unanswered requests (the oldest gives way), people I have friended or asked, tombstones, ignores
FRIEND_REQUESTS = 50
FRIENDS_MAX = 200
FRIEND_TOMBSTONES = 200
FRIEND_IGNORES = 500
FRIEND_IGNORE_DAYS = 30
DM_WRAP_MEMORY = 20000    # gift wrap ids remembered

# people's pictures and faces kept on disk (most recently received first; mine are never dropped)
ART_AVATARS = 300         # picture rows that hold bytes (at most 48 KB each)
ART_ROWS = 1200           # all rows: faces, and the empty ones that mark a removed picture


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
        self._migrate_friends()
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

    def _migrate_friends(self) -> None:
        """Once: conversations I had accepted (written to first, accepted, or met in a room: the old, too easy
        "known" rule) become friends; every other conversation, a stranger's request, is dropped with its
        messages. Nothing but the engine's own `friend_*` calls creates a friend after this."""
        with self._lock:
            if self._db.execute("SELECT 1 FROM kv WHERE k='dm_friends_v1'").fetchone():
                return
            now = time.time()
            self._db.execute(
                "INSERT OR IGNORE INTO dm_friends(peer, mine, mine_at, theirs, theirs_at, first_at, since) "
                "SELECT peer, 1, ?, 1, ?, first_at, ? FROM dm_peers WHERE accepted=1", (int(now), int(now), now))
            self._db.execute("DELETE FROM dm_messages WHERE peer NOT IN (SELECT peer FROM dm_friends)")
            self._db.execute("DELETE FROM dm_peers WHERE peer NOT IN (SELECT peer FROM dm_friends)")
            self._db.execute("INSERT OR REPLACE INTO kv(k, v) VALUES('dm_friends_v1', '1')")
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # --- people's pictures and faces ---------------------------------------------------------------
    def art_put(self, pk: str, kind: str, eid: str, created_at: int, mime: str, data: Optional[bytes],
                arrived_at: float, keep: str = "") -> list[tuple[str, str]]:
        """Store the newest picture or face of one person (replacing the older row), then drop the oldest
        received rows beyond the caps. Returns the (pk, kind) pairs dropped; `keep` (my own key) is never one."""
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO person_art(pk,kind,id,created_at,mime,data,arrived_at) VALUES(?,?,?,?,?,?,?)",
                             (pk, kind, eid, created_at, mime, data, arrived_at))
            gone: list[tuple[str, str]] = []
            for where, cap in (("kind='avatar' AND data IS NOT NULL", ART_AVATARS), ("1=1", ART_ROWS)):
                rows = self._db.execute(f"SELECT pk,kind FROM person_art WHERE pk<>? AND {where} "
                                        "ORDER BY arrived_at DESC LIMIT -1 OFFSET ?", (keep, cap)).fetchall()
                for rpk, rkind in rows:
                    self._db.execute("DELETE FROM person_art WHERE pk=? AND kind=?", (rpk, rkind))
                    gone.append((rpk, rkind))
            self._db.commit()
        return gone

    def art_get(self, pk: str, kind: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute("SELECT id,created_at,mime,data FROM person_art WHERE pk=? AND kind=?", (pk, kind)).fetchone()
        return {"id": row[0], "created_at": row[1], "mime": row[2], "data": row[3]} if row else None

    def art_index(self) -> list[dict]:
        """Every row without its picture bytes (a face is small and comes whole), for the engine's memory."""
        with self._lock:
            rows = self._db.execute("SELECT pk,kind,id,created_at,mime,LENGTH(data),"
                                    "CASE WHEN kind='face' THEN data END FROM person_art").fetchall()
        return [{"pk": r[0], "kind": r[1], "id": r[2], "created_at": r[3], "mime": r[4], "size": r[5] or 0, "data": r[6]} for r in rows]

    def art_forget(self, pk: str) -> None:
        """Delete everything held of one person (hiding them)."""
        with self._lock:
            self._db.execute("DELETE FROM person_art WHERE pk=?", (pk,))
            self._db.commit()

    def art_forget_others(self, kind: str, mine: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM person_art WHERE kind=? AND pk<>?", (kind, mine))
            self._db.commit()

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
               wrap: Optional[str] = None) -> str:
        """Store one message. Returns "added" or "duplicate" (this rumor is already here). Who may be stored is
        the engine's call (friends only); this keeps the caps: past DM_PER_PEER in one conversation the oldest
        go, and past DM_TOTAL the biggest conversation loses its oldest, so one can't push everyone else's out."""
        with self._lock:
            if self._db.execute("SELECT 1 FROM dm_messages WHERE id=?", (id,)).fetchone():
                return "duplicate"
            if self._db.execute("SELECT 1 FROM dm_peers WHERE peer=?", (peer,)).fetchone() is None:
                self._db.execute("INSERT INTO dm_peers(peer, accepted, first_at, last_read) VALUES(?,1,?,?)",
                                 (peer, arrived_at, arrived_at if sender != peer else 0))
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

    def dm_messages(self, peer: str, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, sender, text, created_at, arrived_at, wrap FROM dm_messages WHERE peer=? "
                "ORDER BY created_at DESC, arrived_at DESC, id DESC LIMIT ?", (peer, limit)).fetchall()
        return [dict(zip(("id", "sender", "text", "created_at", "arrived_at", "wrap"), r)) for r in reversed(rows)]

    def dm_threads(self, limit: int = 100) -> list[dict]:
        """Every friend and every conversation that still has messages, newest first: {peer, friend, unread,
        last_ts}. Counts only; the text of the newest unread message comes from `dm_newest_unread`, for the alert."""
        with self._lock:
            rows = self._db.execute(
                "SELECT c.peer, COALESCE(p.last_read, 0), "
                "(SELECT COUNT(*) FROM dm_messages m WHERE m.peer=c.peer AND m.sender=c.peer AND m.arrived_at>COALESCE(p.last_read, 0)), "
                "COALESCE((SELECT MAX(created_at) FROM dm_messages m WHERE m.peer=c.peer), 0) AS last_ts, "
                "EXISTS(SELECT 1 FROM dm_friends f WHERE f.peer=c.peer AND f.mine=1 AND f.theirs=1), "
                "COALESCE((SELECT f.since FROM dm_friends f WHERE f.peer=c.peer), 0) AS since "
                "FROM (SELECT peer FROM dm_friends WHERE mine=1 AND theirs=1 "
                "      UNION SELECT peer FROM dm_peers WHERE EXISTS(SELECT 1 FROM dm_messages m WHERE m.peer=dm_peers.peer)) c "
                "LEFT JOIN dm_peers p ON p.peer=c.peer "
                "ORDER BY last_ts DESC, since DESC, c.peer LIMIT ?", (limit,)).fetchall()
        return [{"peer": r[0], "last_read": r[1], "unread": r[2], "last_ts": r[3], "friend": bool(r[4])} for r in rows]

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
        """Delete a conversation from this computer (the other person's copy, and relays', are theirs). A friend
        stays a friend."""
        with self._lock:
            n = self._db.execute("DELETE FROM dm_messages WHERE peer=?", (peer,)).rowcount
            self._db.execute("DELETE FROM dm_peers WHERE peer=?", (peer,))
            self._db.commit()
        return n

    # --- friends (see the dm_friends table) ---------------------------------------------------------
    @staticmethod
    def _friend_dict(r) -> dict:
        keys = ("peer", "mine", "mine_at", "theirs", "theirs_at", "ignored_at", "first_at", "since")
        d = dict(zip(keys, r))
        d["mine"], d["theirs"] = bool(d["mine"]), bool(d["theirs"])
        return d

    def friend_get(self, peer: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute("SELECT peer, mine, mine_at, theirs, theirs_at, ignored_at, first_at, since "
                                   "FROM dm_friends WHERE peer=?", (peer,)).fetchone()
        return self._friend_dict(row) if row else None

    def friend_rel(self, peer: str, now: Optional[float] = None) -> str:
        """"friend", "sent" (I asked, they haven't said yes), "request" (they asked, I haven't answered), or "".
        An ignored request is "" (it is remembered, not shown)."""
        r = self.friend_get(peer)
        if not r:
            return ""
        if r["mine"] and r["theirs"]:
            return "friend"
        if r["mine"]:
            return "sent"
        if r["theirs"] and not self._ignoring(r, now):
            return "request"
        return ""

    @staticmethod
    def _ignoring(r: dict, now: Optional[float] = None) -> bool:
        return bool(r["ignored_at"]) and (now if now is not None else time.time()) - r["ignored_at"] < FRIEND_IGNORE_DAYS * 86400

    def friend_event(self, peer: str, *, side: str, action: str, at: int, now: Optional[float] = None) -> str:
        """Apply one friend event, atomically. `side` is "theirs" (a rumor from them) or "mine" (my own action,
        or the copy my other install sent); `action` is "yes" (a request or an accept) or "remove"; `at` is the
        event's own date, already clamped to now. Returns "applied", "dropped" (ignored person, stale, nothing to
        remove: handled, no change) or "limit" (no room for one more unanswered request, and this one is older than
        all of them: the caller must NOT record the wrap as handled)."""
        now = now if now is not None else time.time()
        with self._lock:
            self._friend_prune(now)
            r = self.friend_get(peer)
            if side == "theirs" and r and self._ignoring(r, now):
                return "dropped"                       # ignored people can neither ask again nor withdraw and ask
            if r and at < r[side + "_at"]:
                return "dropped"                       # older than what that side already said
            if action == "remove":
                if not r or not (r["mine"] or r["theirs"]):
                    return "dropped"                   # nothing to end (and a stranger's removal costs no row)
                self._db.execute(f"UPDATE dm_friends SET mine=0, theirs=0, {side}_at=?, since=0 WHERE peer=?", (at, peer))
                self._db.commit()
                return "applied"
            if side == "theirs":
                if r is None or not (r["mine"] or r["theirs"]):
                    (n,) = self._db.execute("SELECT COUNT(*) FROM dm_friends WHERE theirs=1 AND mine=0 AND ignored_at=0").fetchone()
                    if n >= FRIEND_REQUESTS:
                        old = self._db.execute("SELECT peer, theirs_at FROM dm_friends WHERE theirs=1 AND mine=0 AND ignored_at=0 "
                                               "ORDER BY theirs_at, first_at, peer LIMIT 1").fetchone()
                        if at < old[1]:
                            return "limit"
                        self._db.execute("DELETE FROM dm_friends WHERE peer=?", (old[0],))   # the oldest unanswered request gives way
                if r is None:
                    self._db.execute("INSERT INTO dm_friends(peer, theirs, theirs_at, first_at) VALUES(?,1,?,?)", (peer, at, now))
                else:
                    self._db.execute("UPDATE dm_friends SET theirs=1, theirs_at=?, ignored_at=0, since=CASE WHEN mine=1 THEN ? ELSE 0 END "
                                     "WHERE peer=?", (at, now, peer))
            else:
                if not (r and r["mine"]):
                    (n,) = self._db.execute("SELECT COUNT(*) FROM dm_friends WHERE mine=1").fetchone()
                    if n >= FRIENDS_MAX:
                        return "limit"
                if r is None:
                    self._db.execute("INSERT INTO dm_friends(peer, mine, mine_at, first_at) VALUES(?,1,?,?)", (peer, at, now))
                else:
                    self._db.execute("UPDATE dm_friends SET mine=1, mine_at=?, ignored_at=0, since=CASE WHEN theirs=1 THEN ? ELSE 0 END "
                                     "WHERE peer=?", (at, now, peer))
            self._db.commit()
            return "applied"

    def _friend_prune(self, now: float) -> None:
        """Forget old ignores, cap the ignore list and the tombstones (the oldest first)."""
        self._db.execute("UPDATE dm_friends SET ignored_at=0 WHERE ignored_at>0 AND ignored_at<?",
                         (now - FRIEND_IGNORE_DAYS * 86400,))
        self._db.execute("DELETE FROM dm_friends WHERE mine=0 AND theirs=0 AND ignored_at=0 AND peer NOT IN ("
                         "SELECT peer FROM dm_friends WHERE mine=0 AND theirs=0 AND ignored_at=0 "
                         "ORDER BY MAX(mine_at, theirs_at) DESC LIMIT ?)", (FRIEND_TOMBSTONES,))
        self._db.execute("DELETE FROM dm_friends WHERE ignored_at>0 AND mine=0 AND peer NOT IN ("
                         "SELECT peer FROM dm_friends WHERE ignored_at>0 AND mine=0 ORDER BY ignored_at DESC LIMIT ?)",
                         (FRIEND_IGNORES,))

    def friend_ignore(self, peer: str, now: Optional[float] = None) -> bool:
        """Ignore their request: local and silent. They stay ignored for FRIEND_IGNORE_DAYS."""
        now = now if now is not None else time.time()
        with self._lock:
            cur = self._db.execute("UPDATE dm_friends SET ignored_at=? WHERE peer=? AND theirs=1 AND mine=0", (now, peer))
            self._db.commit()
            return cur.rowcount > 0

    def friend_forget(self, peer: str) -> None:
        """Forget everything about a person (hiding them)."""
        with self._lock:
            self._db.execute("DELETE FROM dm_friends WHERE peer=?", (peer,))
            self._db.commit()

    def friend_lists(self, now: Optional[float] = None) -> dict:
        """{"requests": [{peer, at}] newest first (unanswered, not ignored), "sent": [peer], "friends": [peer]}."""
        now = now if now is not None else time.time()
        with self._lock:
            rows = self._db.execute("SELECT peer, mine, theirs, theirs_at, ignored_at FROM dm_friends "
                                    "WHERE mine=1 OR theirs=1 ORDER BY theirs_at DESC, peer").fetchall()
        out: dict = {"requests": [], "sent": [], "friends": []}
        for peer, mine, theirs, at, ign in rows:
            if mine and theirs:
                out["friends"].append(peer)
            elif mine:
                out["sent"].append(peer)
            elif not (ign and now - ign < FRIEND_IGNORE_DAYS * 86400):
                out["requests"].append({"peer": peer, "at": at})
        return out

    def dm_counts(self) -> dict:
        with self._lock:
            (msgs,) = self._db.execute("SELECT COUNT(*) FROM dm_messages").fetchone()
            (peers,) = self._db.execute("SELECT COUNT(*) FROM dm_peers").fetchone()
        return {"messages": msgs, "peers": peers}
