"""Minimal in-memory NIP-01 Nostr relay for tests and local runs.

CLI:      python tests/local_relay.py --port 7447 [--drop 0.1] [--delay-ms 50]
Library:  async with LocalRelay(port=0) as relay: relay.url   # ws://127.0.0.1:<port>

`relay.stop()` / `relay.start()` bounce the server on the same port (stored events survive), and
`drop_rate` / `delay_ms` (settable at any time) make live deliveries lossy or slow.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from websockets.asyncio.server import serve  # noqa: E402
from websockets.exceptions import ConnectionClosed  # noqa: E402

from xenia_engine.nostr import check_event  # noqa: E402


def _is_replaceable(kind: int) -> bool:
    return kind in (0, 3) or 10000 <= kind < 20000


def _is_ephemeral(kind: int) -> bool:
    return 20000 <= kind < 30000


def _is_param_replaceable(kind: int) -> bool:
    return 30000 <= kind < 40000


def _d_tag(ev: dict) -> str:
    for t in ev["tags"]:
        if t and t[0] == "d":
            return t[1] if len(t) > 1 else ""
    return ""


def matches(ev: dict, flt: dict) -> bool:
    if "ids" in flt and ev["id"] not in flt["ids"]:
        return False
    if "authors" in flt and ev["pubkey"] not in flt["authors"]:
        return False
    if "kinds" in flt and ev["kind"] not in flt["kinds"]:
        return False
    if "since" in flt and ev["created_at"] < flt["since"]:
        return False
    if "until" in flt and ev["created_at"] > flt["until"]:
        return False
    for key, vals in flt.items():
        if len(key) == 2 and key[0] == "#":
            have = {t[1] for t in ev["tags"] if len(t) > 1 and t[0] == key[1]}
            if not have.intersection(vals):
                return False
    return True


def _newer(a: dict, b: dict) -> bool:
    """True if event a supersedes b (newer created_at; tie: lower id)."""
    if a["created_at"] != b["created_at"]:
        return a["created_at"] > b["created_at"]
    return a["id"] < b["id"]


class LocalRelay:
    def __init__(self, host: str = "127.0.0.1", port: int = 0, *, max_message_size: int = 128 * 1024,
                 drop_rate: float = 0.0, delay_ms: int = 0, seed: Optional[int] = None):
        self.host = host
        self.port = port
        self.max_message_size = max_message_size
        self.drop_rate = drop_rate
        self.delay_ms = delay_ms
        self.events: dict[str, dict] = {}
        self._rng = random.Random(seed)
        self._server = None
        self._conns: set = set()
        self._subs: dict = {}  # ws -> {sub_id: [filters]}
        self._tasks: set[asyncio.Task] = set()

    # -- lifecycle ----------------------------------------------------------------------------
    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    async def start(self) -> "LocalRelay":
        self._server = await serve(self._handle, self.host, self.port,
                                   max_size=self.max_message_size * 4, ping_interval=None)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        for ws in list(self._conns):
            await ws.close()
        await self._server.wait_closed()
        self._server = None
        for t in list(self._tasks):
            t.cancel()
        self._tasks.clear()

    async def restart(self) -> "LocalRelay":
        await self.stop()
        return await self.start()

    async def __aenter__(self) -> "LocalRelay":
        return await self.start()

    async def __aexit__(self, *exc) -> None:
        await self.stop()

    # -- protocol -----------------------------------------------------------------------------
    async def _handle(self, ws) -> None:
        self._conns.add(ws)
        self._subs[ws] = {}
        try:
            async for raw in ws:
                await self._on_message(ws, raw)
        except ConnectionClosed:
            pass
        finally:
            self._conns.discard(ws)
            self._subs.pop(ws, None)

    async def _send(self, ws, msg: list) -> None:
        try:
            await ws.send(json.dumps(msg, separators=(",", ":")))
        except ConnectionClosed:
            pass

    async def _on_message(self, ws, raw) -> None:
        if len(raw) > self.max_message_size:
            eid = ""
            try:
                m = json.loads(raw)
                if isinstance(m, list) and len(m) > 1 and isinstance(m[1], dict):
                    eid = str(m[1].get("id", ""))
            except ValueError:
                pass
            await self._send(ws, ["OK", eid, False, "invalid: too large"])
            return
        try:
            msg = json.loads(raw)
            assert isinstance(msg, list) and msg
        except (ValueError, AssertionError):
            await self._send(ws, ["NOTICE", "invalid: bad message"])
            return
        kind = msg[0]
        if kind == "EVENT" and len(msg) >= 2:
            await self._on_event(ws, msg[1])
        elif kind == "REQ" and len(msg) >= 2 and isinstance(msg[1], str):
            await self._on_req(ws, msg[1], [f for f in msg[2:] if isinstance(f, dict)])
        elif kind == "CLOSE" and len(msg) >= 2:
            self._subs.get(ws, {}).pop(msg[1], None)
        else:
            await self._send(ws, ["NOTICE", "invalid: unknown message"])

    async def _on_event(self, ws, ev) -> None:
        eid = ev.get("id", "") if isinstance(ev, dict) else ""
        if not check_event(ev):
            await self._send(ws, ["OK", eid, False, "invalid: bad event id or signature"])
            return
        if ev["id"] in self.events:
            await self._send(ws, ["OK", eid, True, "duplicate: already have this event"])
            return
        if _is_ephemeral(ev["kind"]):
            await self._send(ws, ["OK", eid, True, ""])
            self._fanout(ev)
            return
        if not self._store(ev):
            await self._send(ws, ["OK", eid, True, "duplicate: superseded by a newer event"])
            return
        await self._send(ws, ["OK", eid, True, ""])
        self._fanout(ev)

    def _store(self, ev: dict) -> bool:
        k = ev["kind"]
        if _is_replaceable(k) or _is_param_replaceable(k):
            d = _d_tag(ev) if _is_param_replaceable(k) else None
            for old in list(self.events.values()):
                if old["pubkey"] == ev["pubkey"] and old["kind"] == k and \
                        (d is None or _d_tag(old) == d):
                    if not _newer(ev, old):
                        return False
                    del self.events[old["id"]]
        self.events[ev["id"]] = ev
        return True

    async def _on_req(self, ws, sub_id: str, filters: list[dict]) -> None:
        self._subs[ws][sub_id] = filters
        seen: set[str] = set()
        for flt in filters:
            hits = sorted((e for e in self.events.values() if matches(e, flt)),
                          key=lambda e: (-e["created_at"], e["id"]))
            if "limit" in flt:
                hits = hits[: max(0, int(flt["limit"]))]
            for e in hits:
                if e["id"] not in seen:
                    seen.add(e["id"])
                    await self._send(ws, ["EVENT", sub_id, e])
        await self._send(ws, ["EOSE", sub_id])

    def _fanout(self, ev: dict) -> None:
        for ws, subs in list(self._subs.items()):
            for sub_id, filters in list(subs.items()):
                if any(matches(ev, f) for f in filters):
                    if self.drop_rate and self._rng.random() < self.drop_rate:
                        continue
                    self._spawn(self._deliver(ws, sub_id, ev))

    async def _deliver(self, ws, sub_id: str, ev: dict) -> None:
        if self.delay_ms:
            await asyncio.sleep(self.delay_ms / 1000)
        if sub_id in self._subs.get(ws, {}):
            await self._send(ws, ["EVENT", sub_id, ev])

    def _spawn(self, coro) -> None:
        t = asyncio.ensure_future(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)


async def _main() -> None:
    ap = argparse.ArgumentParser(description="Minimal in-memory Nostr relay")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7447)
    ap.add_argument("--drop", type=float, default=0.0, help="fraction of live deliveries to drop")
    ap.add_argument("--delay-ms", type=int, default=0)
    ap.add_argument("--max-size", type=int, default=128 * 1024)
    a = ap.parse_args()
    async with LocalRelay(a.host, a.port, max_message_size=a.max_size, drop_rate=a.drop,
                          delay_ms=a.delay_ms) as relay:
        print(f"local relay on {relay.url}", flush=True)
        await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
