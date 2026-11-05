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

    def __init__(self, config, store_factory=open_store, **_kw):
        super().__init__(config=config, platform=Platform(PLATFORM_NAME))
        self._store_factory = store_factory
        self._store = None
        self._task: Optional[asyncio.Task] = None
        self._last_beat = 0.0

    # -- lifecycle ---------------------------------------------------------------------------------
    async def connect(self, *, is_reconnect: bool = False) -> bool:
        try:
            self._store = await asyncio.to_thread(self._store_factory)
        except Exception as e:
            log.error("[ninsei] could not open the Ninsei store: %s", e)
            return False
        self._mark_connected()
        await asyncio.to_thread(self._store.line_heartbeat)
        self._last_beat = time.monotonic()
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
        """Deliver every queued owner message to the gateway. Returns how many."""
        store = self._store
        if store is None:
            return 0
        if time.monotonic() - self._last_beat >= HEARTBEAT_SECONDS:
            await asyncio.to_thread(store.line_heartbeat)
            self._last_beat = time.monotonic()
        msgs = await asyncio.to_thread(store.line_claim_owner)
        for m in msgs:
            event = self.build_event(m, await asyncio.to_thread(self._owner_name))
            try:
                await self.handle_message(event)
            except Exception as e:
                log.warning("[ninsei] gateway refused a private-line message: %s", e)
                await asyncio.to_thread(store.line_set_status, m["id"], "failed")
        return len(msgs)

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
            row = await asyncio.to_thread(self._store.line_add_reply, content, reply_to)
        except Exception as e:
            return SendResult(success=False, error=str(e))
        return SendResult(success=True, message_id=row["id"])

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
            row = await asyncio.to_thread(store.line_add_reply, message)
        finally:
            await asyncio.to_thread(store.close)
    except Exception as e:
        return {"error": f"Ninsei private line: {e}"}
    return {"success": True, "platform": PLATFORM_NAME, "chat_id": CHAT_ID, "message_id": row["id"]}
