"""Ninsei as a Hermes gateway platform: the private line between you and your own Hermes.

The Ninsei page has a private thread, "Your Hermes". What you type there reaches your full Hermes agent
(tools, memory, approvals) through the gateway, exactly like a message to your Telegram bot would, and its
replies come back into the same thread. The thread is never published to relays.

The trust split, which is the point of this file:

* Inbound is only what the owner typed in the local Ninsei UI. The UI's route writes an 'owner' row to the
  local store (`private_line` table, owner-only file); this adapter takes queued 'owner' rows and nothing
  else. Room messages, other people and other agents never enter this table, so they can't reach the
  tool-enabled agent, not even quoted. Room context gets in only if the owner pastes it.
* Outbound is only the private thread. `send()` writes a 'hermes' row. Nothing here can publish: this module
  never imports the engine, the relay client or the signer, and never calls get_engine(). To say something
  in a room, the owner presses "Post to room" in the UI, which queues a draft they send themselves.
* Process boundary: the Ninsei engine (relays, room brain) runs in the dashboard or Desktop backend and holds
  `engine.lock`; this adapter runs in the gateway process and meets it only through the SQLite store (WAL).

This module imports gateway classes at the top, so it's loaded lazily, from the adapter factory in
`register()`, only inside a gateway.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from gateway.config import Platform
from gateway.platforms.base import BasePlatformAdapter, SendResult
from gateway.platforms.event import MessageEvent, MessageType

from . import _loader

log = logging.getLogger("ninsei.platform")

PLATFORM_NAME = "ninsei"
CHAT_ID = "private"          # one global thread: reads as "Ninsei · private line" in the session list
CHAT_NAME = "Ninsei · private line"
OWNER_ID = "owner"           # the only sender this platform has
POLL_SECONDS = 1.0           # a local, indexed SQLite read; cheap enough to keep the line feeling live
HEARTBEAT_SECONDS = 10.0
REPLY_CHUNK = 60000          # one stored reply holds at most 64,000 characters (store.LINE_REPLY_MAX)


def split_reply(content: str, splitter=None, size: int = REPLY_CHUNK) -> list[str]:
    """A long reply as several thread messages, each under the store's cap, so nothing is cut silently.
    Uses Hermes's own `truncate_message` (it keeps code fences intact and numbers the parts) when given."""
    content = str(content or "")
    if len(content) <= size:
        return [content]
    if splitter is not None:
        try:
            parts = [p for p in splitter(content, size) if p]
            if parts and all(len(p) <= size + 64 for p in parts):
                return parts
        except Exception:
            pass
    parts, rest = [], content
    while len(rest) > size:   # fallback: break at a line end when there is one in the back half
        cut = rest.rfind("\n", size // 2, size)
        cut = cut + 1 if cut > 0 else size
        parts.append(rest[:cut])
        rest = rest[cut:]
    return parts + ([rest] if rest else [])


def open_store():
    """The same store file the engine uses (the active profile's plugin data). Never starts the engine."""
    pkg = _loader.load_engine()
    from importlib import import_module
    Store = import_module(pkg.__name__ + ".store").Store
    path = pkg.db_path_if_present()
    if path is None:
        path = pkg.data_dir() / "ninsei.db"
    return Store(path)


class NinseiAdapter(BasePlatformAdapter):
    """Private line adapter: local store in, local store out."""

    serial_receive_loop = True  # the poll loop hands messages over one at a time, in order
    splits_long_messages = True  # send() cuts a long reply into thread messages itself (max_message_length is 0)

    def __init__(self, config, store_factory=open_store, *, autopoll: bool = True, **_kw):
        super().__init__(config=config, platform=Platform(PLATFORM_NAME))
        self._store_factory = store_factory
        self._store = None
        self._autopoll = autopoll   # False: no background loop, the caller drives poll_once (tests)
        self._task: Optional[asyncio.Task] = None
        self._poll_lock = asyncio.Lock()   # one poll at a time, so hand-over stays serial and in order
        self._last_beat = 0.0
        self._handler_set: Optional[bool] = None   # None until the gateway installs or withdraws its handler

    def set_message_handler(self, handler) -> None:
        """The gateway withdraws the handler (None) while it drains or restarts; then handle_message drops
        everything silently, so this adapter stops claiming owner messages until a handler is back."""
        self._handler_set = handler is not None
        super().set_message_handler(handler)

    def _can_dispatch(self) -> bool:
        if self._handler_set is not None:
            return self._handler_set
        return getattr(self, "_message_handler", True) is not None

    # -- lifecycle ---------------------------------------------------------------------------------
    async def connect(self, *, is_reconnect: bool = False) -> bool:
        try:
            self._store = await asyncio.to_thread(self._store_factory)
        except Exception as e:
            log.error("[ninsei] could not open the Ninsei store: %s", e)
            return False
        self._mark_connected()
        # a previous run that died between claiming and handing over left messages half-way: send them again
        await asyncio.to_thread(self._store.line_requeue)
        await asyncio.to_thread(self._store.line_heartbeat)
        self._last_beat = time.monotonic()
        if self._autopoll:
            self._task = asyncio.create_task(self._poll_loop())
        try:
            self._wire_plugin_handlers(None)
        except Exception:
            pass
        log.info("[ninsei] private line connected")
        return True

    async def disconnect(self) -> None:
        self._mark_disconnected()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        if self._store is not None:
            store, self._store = self._store, None
            try:
                await asyncio.to_thread(store.line_requeue)   # claimed by a cancelled poll, never handed over
            except Exception:
                pass
            await asyncio.to_thread(store.close)

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                return
            except Exception as e:  # a locked or briefly unreadable db: try again next tick
                log.debug("[ninsei] poll failed: %s", e)
            await asyncio.sleep(POLL_SECONDS)

    async def poll_once(self) -> int:
        """Deliver every queued owner message to the gateway. Returns how many. Calls never overlap: a
        second caller waits for the first, so two batches are never handed over at the same time."""
        async with self._poll_lock:
            return await self._poll_locked()

    async def _poll_locked(self) -> int:
        store = self._store
        if store is None:
            return 0
        if time.monotonic() - self._last_beat >= HEARTBEAT_SECONDS:
            await asyncio.to_thread(store.line_heartbeat)
            self._last_beat = time.monotonic()
        if not self._can_dispatch():
            return 0   # the gateway is draining: leave owner messages queued instead of dropping them
        msgs = await asyncio.to_thread(store.line_claim_owner, 20, "claimed")
        pending = list(msgs)
        current = None
        delivered = 0
        try:
            while pending:
                m = pending[0]
                if not self._can_dispatch():
                    break
                current = self.build_event(m, await asyncio.to_thread(self._owner_name))
                try:
                    await self.handle_message(current)
                except Exception as e:
                    log.warning("[ninsei] gateway refused a private-line message: %s", e)
                    await asyncio.to_thread(store.line_set_status, m["id"], "failed")
                    pending.pop(0)
                    current = None
                    continue
                if not self._can_dispatch():
                    break   # the handler went away during the call: it may have dropped the message
                await asyncio.to_thread(store.line_set_status, m["id"], "delivered")
                pending.pop(0)
                current = None
                delivered += 1
        finally:
            # Anything not handed over (a drain, or this task cancelled mid-batch) goes back in the queue.
            if pending and current is not None and getattr(current, "_gateway_accepted", False) is True:
                store.line_set_status(pending[0]["id"], "delivered")   # accepted before the cancel landed
                pending.pop(0)
            if pending:
                store.line_requeue([p["id"] for p in pending])
        return delivered

    # -- inbound -----------------------------------------------------------------------------------
    def _owner_name(self) -> str:
        try:
            s = self._store.get("settings") or {}
            return str(s.get("display_name") or "").strip()[:40] or "You"
        except Exception:
            return "You"

    def build_event(self, m: dict, owner_name: str = "You") -> MessageEvent:
        """An owner row -> the gateway's inbound shape. Only ever called with role 'owner' rows."""
        if m.get("role") != "owner":
            raise ValueError("only the owner's own messages are inbound")
        text = m["text"]
        source = self.build_source(chat_id=CHAT_ID, chat_name=CHAT_NAME, chat_type="dm",
                                   user_id=OWNER_ID, user_name=owner_name, message_id=m["id"])
        return MessageEvent(
            text=text,
            message_type=MessageType.COMMAND if text.startswith("/") else MessageType.TEXT,
            user_id=OWNER_ID, user_name=owner_name, source=source, message_id=m["id"],
            raw_message={"ninsei_line_id": m["id"]},
            timestamp=datetime.fromtimestamp(float(m["created_at"]), tz=timezone.utc))

    # -- outbound: the private thread only ---------------------------------------------------------
    async def send(self, chat_id: str, content: str, reply_to: Optional[str] = None,
                   metadata: Optional[dict[str, Any]] = None) -> SendResult:
        if self._store is None:
            return SendResult(success=False, error="Ninsei private line is not connected")
        if not str(content or "").strip():
            return SendResult(success=True, message_id=None)
        try:
            first = None
            for part in split_reply(content, getattr(self, "truncate_message", None)):
                row = await asyncio.to_thread(self._store.line_add_reply, part, reply_to)
                first = first or row
        except Exception as e:
            return SendResult(success=False, error=str(e))
        return SendResult(success=True, message_id=first["id"])

    async def edit_message(self, chat_id: str, message_id: str, content: str, *, finalize: bool = False) -> SendResult:
        if self._store is None:
            return SendResult(success=False, error="Ninsei private line is not connected")
        ok = await asyncio.to_thread(self._store.line_edit_reply, message_id, content)
        return SendResult(success=ok, message_id=message_id if ok else None, error=None if ok else "unknown message")

    async def send_typing(self, chat_id: str, metadata=None) -> None:
        if self._store is not None:
            await asyncio.to_thread(self._store.line_typing, True)

    async def stop_typing(self, chat_id: str) -> None:
        if self._store is not None:
            await asyncio.to_thread(self._store.line_typing, False)

    async def get_chat_info(self, chat_id: str) -> dict:
        return {"name": CHAT_NAME, "type": "dm"}


async def standalone_send(pconfig, chat_id, message, *, thread_id=None, media_files=None, force_document=False,
                          store_factory=open_store) -> dict:
    """Cron results (`deliver=ninsei`) from a process without the live gateway: same private thread."""
    try:
        store = await asyncio.to_thread(store_factory)
        try:
            row = None
            for part in split_reply(message):
                added = await asyncio.to_thread(store.line_add_reply, part)
                row = row or added
        finally:
            await asyncio.to_thread(store.close)
    except Exception as e:
        return {"error": f"Ninsei private line: {e}"}
    return {"success": True, "platform": PLATFORM_NAME, "chat_id": CHAT_ID, "message_id": row["id"]}
