"""Is a room really on the public relays? Ask each relay directly, from outside Ninsei.

    python scripts/relay_probe.py ninsei:4fb0f7726213f49e [--hours 24] [--relay wss://...]

Read-only: no keys, no Ninsei state, nothing published. For each relay it prints how many of the room's
events it holds, from how many keys, and by type. A relay holding far fewer than the others is dropping or
refusing our events: Settings > Relays in Ninsei shows the reason it gave (a rate limit shows as "Resting").
Run it from another machine or network to check what a stranger would see.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import uuid
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ninsei_engine.engine import DEFAULT_RELAYS, KIND_ROOM  # noqa: E402


def room_id(code: str) -> str:
    room = re.sub(r"[^a-f0-9]", "", code.lower().replace("ninsei:", ""))[:24]
    if not room:
        raise SystemExit("that doesn't look like a room code (ninsei:<hex>)")
    return room


def _type_of(e) -> str:
    """The event's `t`, printable: anyone can post to a room, so any field can be any type or text."""
    try:
        t = json.loads(e.get("content") or "{}").get("t", "?")
    except (ValueError, AttributeError, TypeError):
        return "?"
    return re.sub(r"[^\x21-\x7e]", "?", t)[:24] if isinstance(t, str) else "?"


def summarize(events: list) -> str:
    events = [e for e in events if isinstance(e, dict)]
    keys = {e.get("pubkey") for e in events if isinstance(e.get("pubkey"), str)}
    kinds: dict[str, int] = {}
    for e in events:
        t = _type_of(e)
        kinds[t] = kinds.get(t, 0) + 1
    by_type = ", ".join(f"{k} {v}" for k, v in sorted(kinds.items()))
    return f"{len(events):4} events from {len(keys)} keys" + (f"  ({by_type})" if by_type else "")


async def ask(url: str, room: str, since: int, timeout: float = 10.0) -> tuple[str, list[dict] | None, str]:
    sub = uuid.uuid4().hex[:8]
    flt = {"kinds": [KIND_ROOM], "#h": [room], "since": since, "limit": 500}
    try:
        async with websockets.connect(url, open_timeout=timeout, max_size=2 ** 22) as ws:
            await ws.send(json.dumps(["REQ", sub, flt]))
            events = []
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout))
                if msg[0] == "EVENT" and len(msg) > 2:
                    events.append(msg[2])
                elif msg[0] == "EOSE":
                    return url, events, ""
                elif msg[0] in ("CLOSED", "NOTICE"):
                    return url, events, f"{msg[0]}: {msg[-1]}"
    except Exception as e:  # report every relay, whatever happened to one
        return url, None, f"{type(e).__name__}: {e}"


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("code", help="room code, like ninsei:4fb0f7726213f49e")
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--relay", action="append", help="relay to ask (repeatable); default: Ninsei's defaults")
    args = ap.parse_args()
    room = room_id(args.code)
    relays = args.relay or DEFAULT_RELAYS
    since = int(time.time() - args.hours * 3600)
    results = await asyncio.gather(*(ask(u, room, since) for u in relays))
    best = max((len(evs) for _, evs, _ in results if evs is not None), default=0)
    width = max(len(u) for u in relays)
    print(f"room {room}, last {args.hours:g} h")
    for url, evs, note in results:
        line = "   unreachable" if evs is None else summarize(evs)
        flag = "" if evs is not None and len(evs) == best else "  <- missing events" if evs is not None else ""
        print(f"  {url:{width}}  {line}{flag}" + (f"  [{note}]" if note else ""))
    if best == 0:
        print("No relay has anything for this room in that window: check the code, the window, or the relays.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
