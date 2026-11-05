"""A pool of Nostr relay connections: publish to all, subscribe on all, dedupe by event id.

Runs on the engine's own asyncio loop. Each relay gets one websocket with jittered reconnect backoff.
Subscriptions are remembered and replayed after a reconnect with `since` moved up to the newest event
seen, so a dropped relay doesn't replay the whole room or miss the gap.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

import websockets

from . import nostr

log = logging.getLogger("ninsei.relays")

EventHandler = Callable[[dict, str], Awaitable[None] | None]

FUTURE_SKEW_S = 60          # events dated further ahead than this are dropped (and never move `newest`)
MAX_VERIFIED = 20000        # remembered ids whose signature we already checked
MAX_BAD = 5000              # remembered ids that failed verification
BAD_STRIKES = 40            # bad events from one relay within BAD_WINDOW_S ...
BAD_WINDOW_S = 10.0
BAD_MUTE_S = 30.0           # ... and we ignore that relay's events for this long
OUTBOX_MAX = 200            # unacknowledged events kept for resend
OUTBOX_TTL_S = 24 * 3600    # after this an undelivered event is "failed"
SYNTH = "ninsei:"            # prefix on locally made (not relay-sent) OK results


def _now() -> float:
    return time.time()


@dataclass
class Subscription:
    sub_id: str
    filters: list[dict]
    handler: EventHandler
    newest: int = 0  # newest created_at seen, for `since` on resubscribe
    eose: set[str] = field(default_factory=set)
    dedupe: bool = True  # live subs dedupe across relays; one-shot queries keep their own set
    seen_ids: Optional[set] = None  # one-shot queries: ids already collected (skip before verifying)


@dataclass
class RelayStatus:
    url: str
    state: str = "idle"  # idle | connecting | open | backoff
    last_error: str = ""
    ok: int = 0
    rejected: int = 0
    last_reject: str = ""


class RelayPool:
    def __init__(self, urls: list[str], *, max_seen: int = 20000, outbox=None,
                 outbox_max: int = OUTBOX_MAX, outbox_ttl: float = OUTBOX_TTL_S):
        """`outbox` is an optional Store; with it, unacknowledged events survive a restart."""
        self.urls = list(dict.fromkeys(u.strip() for u in urls if u.strip()))
        self.status = {u: RelayStatus(u) for u in self.urls}
        self._ws: dict[str, object] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._subs: dict[str, Subscription] = {}
        self._seen: dict[str, float] = {}
        self._max_seen = max_seen
        self._pending_ok: dict[str, dict[str, asyncio.Future]] = {}
        self._stopped = False
        self._verified: dict[str, None] = {}   # ids whose signature passed (insertion-ordered, bounded)
        self._bad: dict[tuple, None] = {}      # (id, sig) pairs that failed verification (bounded)
        self._strikes: dict[str, list[float]] = {}
        self._muted_until: dict[str, float] = {}
        self._store = outbox
        self._outbox_max = outbox_max
        self._outbox_ttl = outbox_ttl
        self._outbox: dict[str, tuple[dict, float]] = {}   # id -> (event, first queued at)
        self._delivery: dict[str, str] = {}
        self._flush_tasks: set[asyncio.Task] = set()
        if self._store is not None:
            try:
                self._store.event_outbox_prune(self._outbox_ttl)
                for ev, ts in self._store.event_outbox_pending():
                    self._outbox[ev["id"]] = (ev, ts)
                    self._delivery[ev["id"]] = "pending"
            except Exception:
                log.exception("ninsei: could not load the event outbox")

    # --- lifecycle ------------------------------------------------------------------------------
    def start(self) -> None:
        for url in self.urls:
            if url not in self._tasks:
                self._tasks[url] = asyncio.ensure_future(self._run(url))

    async def stop(self) -> None:
        self._stopped = True
        for t in self._tasks.values():
            t.cancel()
        for t in list(self._flush_tasks):
            t.cancel()
        for ws in list(self._ws.values()):
            try:
                await ws.close()
            except Exception:
                pass
        self._tasks.clear()
        self._ws.clear()

    def open_count(self) -> int:
        return sum(1 for s in self.status.values() if s.state == "open")

    async def wait_open(self, timeout: float = 8.0, at_least: int = 1) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.open_count() >= min(at_least, len(self.urls)):
                return True
            await asyncio.sleep(0.05)
        return self.open_count() > 0

    async def _run(self, url: str) -> None:
        delay = 1.0
        st = self.status[url]
        while not self._stopped:
            st.state = "connecting"
            try:
                async with websockets.connect(url, open_timeout=8, ping_interval=25, ping_timeout=20,
                                              max_size=2 ** 20) as ws:
                    self._ws[url] = ws
                    st.state, st.last_error = "open", ""
                    delay = 1.0
                    for sub in list(self._subs.values()):
                        await self._send_req(url, ws, sub)
                    self._spawn_flush(url, ws)
                    async for raw in ws:
                        await self._on_message(url, raw)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # network errors are normal: back off and retry
                st.last_error = type(e).__name__ + (f": {e}" if str(e) else "")
            finally:
                self._ws.pop(url, None)
                for fut in self._pending_ok.pop(url, {}).values():
                    if not fut.done():
                        fut.set_result((False, SYNTH + "disconnected"))
            if self._stopped:
                break
            st.state = "backoff"
            await asyncio.sleep(delay * (0.7 + random.random() * 0.6))
            delay = min(delay * 2, 30.0)

    # --- inbound --------------------------------------------------------------------------------
    async def _on_message(self, url: str, raw) -> None:
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            return
        if not isinstance(msg, list) or not msg:
            return
        typ = msg[0]
        if typ == "EVENT" and len(msg) >= 3:
            sub = self._subs.get(msg[1])
            ev = msg[2]
            if sub is None or not isinstance(ev, dict):
                return
            eid = ev.get("id")
            if not isinstance(eid, str) or (sub.dedupe and eid in self._seen):
                return
            if sub.seen_ids is not None and eid in sub.seen_ids:
                return   # one-shot query: already collected from another relay
            if self._muted_until.get(url, 0) > time.monotonic() or (eid, ev.get("sig")) in self._bad:
                return
            created = ev.get("created_at")
            if not isinstance(created, int) or created > _now() + FUTURE_SKEW_S:
                return   # a future-dated event must not move `since` or reach handlers
            if not self._verify(url, ev):
                return
            if sub.seen_ids is not None:
                sub.seen_ids.add(eid)
            if sub.dedupe:
                self._remember(eid)
            sub.newest = max(sub.newest, created)
            try:
                res = sub.handler(ev, url)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                log.exception("ninsei: event handler failed")
        elif typ == "OK" and len(msg) >= 3:
            fut = self._pending_ok.get(url, {}).pop(msg[1], None)
            st = self.status[url]
            if msg[2]:
                st.ok += 1
            else:
                st.rejected += 1
                st.last_reject = str(msg[3] if len(msg) > 3 else "")[:120]
            if fut and not fut.done():
                fut.set_result((bool(msg[2]), str(msg[3] if len(msg) > 3 else "")))
        elif typ == "EOSE" and len(msg) >= 2:
            sub = self._subs.get(msg[1])
            if sub:
                sub.eose.add(url)
        elif typ == "CLOSED" and len(msg) >= 2:
            self.status[url].last_error = f"subscription closed: {msg[2] if len(msg) > 2 else ''}"[:120]

    def _verify(self, url: str, ev: dict) -> bool:
        """Full check, but the signature (the slow part) only once per id. A repeat still has its id
        recomputed, so a forged copy of a known id can't ride on the earlier verification."""
        eid = ev["id"]
        if eid in self._verified:
            try:
                return nostr.event_id(ev) == eid and isinstance(ev.get("content"), str) \
                    and isinstance(ev.get("tags"), list) and isinstance(ev.get("kind"), int)
            except Exception:
                return False
        if nostr.check_event(ev):
            self._verified[eid] = None
            if len(self._verified) > MAX_VERIFIED:
                for k in list(self._verified)[: MAX_VERIFIED // 4]:
                    self._verified.pop(k, None)
            return True
        # Keyed by (id, sig), never id alone: the id doesn't cover the signature, so a hostile relay
        # could replay a real event's content with a junk sig and get the genuine copy suppressed.
        sig = ev.get("sig")
        if isinstance(sig, str):
            self._bad[(eid, sig)] = None
        if len(self._bad) > MAX_BAD:
            for k in list(self._bad)[: MAX_BAD // 4]:
                self._bad.pop(k, None)
        now = time.monotonic()
        hits = [t for t in self._strikes.get(url, []) if t > now - BAD_WINDOW_S] + [now]
        self._strikes[url] = hits
        if len(hits) >= BAD_STRIKES:   # a relay flooding forgeries: stop spending CPU on it for a while
            self._muted_until[url] = now + BAD_MUTE_S
            self._strikes[url] = []
            self.status[url].last_error = "muted: sent many invalid events"
        return False

    def _remember(self, eid: str) -> None:
        self._seen[eid] = time.monotonic()
        if len(self._seen) > self._max_seen:
            for k in list(self._seen)[: self._max_seen // 4]:
                self._seen.pop(k, None)

    def mark_seen(self, eid: str) -> None:
        """Events we publish ourselves are handled locally; don't process their echo twice."""
        self._remember(eid)

    # --- subscriptions --------------------------------------------------------------------------
    async def _send_req(self, url: str, ws, sub: Subscription) -> None:
        filters = []
        for f in sub.filters:
            f2 = dict(f)
            if sub.newest and "since" in f2:  # resume where we left off (minus a little for clock skew)
                f2["since"] = max(int(f2["since"]), sub.newest - 30)
            filters.append(f2)
        try:
            await ws.send(json.dumps(["REQ", sub.sub_id, *filters]))
        except Exception as e:
            self.status[url].last_error = f"req failed: {e}"

    async def subscribe(self, sub_id: str, filters: list[dict], handler: EventHandler) -> None:
        sub = Subscription(sub_id, filters, handler)
        old = self._subs.get(sub_id)
        if old:
            sub.newest = old.newest
        self._subs[sub_id] = sub
        for url, ws in list(self._ws.items()):
            await self._send_req(url, ws, sub)

    async def unsubscribe(self, sub_id: str) -> None:
        if self._subs.pop(sub_id, None) is None:
            return
        for ws in list(self._ws.values()):
            try:
                await ws.send(json.dumps(["CLOSE", sub_id]))
            except Exception:
                pass

    def eose_count(self, sub_id: str) -> int:
        sub = self._subs.get(sub_id)
        return len(sub.eose) if sub else 0

    # --- publish --------------------------------------------------------------------------------
    async def publish(self, ev: dict, *, wait: float = 4.0) -> dict[str, tuple[bool, str]]:
        """Send to every open relay; return {url: (accepted, message)} for the ones that answered.
        If no relay accepts it (none open, no answer), the event goes in the outbox and is resent when a
        relay (re)connects; see `delivery`."""
        out = await self._send_all(ev, wait)
        self._settle(ev, out)
        return out

    async def _send_all(self, ev: dict, wait: float, only: Optional[dict] = None) -> dict[str, tuple[bool, str]]:
        self.mark_seen(ev["id"])
        futs: dict[str, asyncio.Future] = {}
        payload = json.dumps(["EVENT", ev])
        loop = asyncio.get_running_loop()
        for url, ws in list((only or self._ws).items()):
            fut = loop.create_future()
            self._pending_ok.setdefault(url, {})[ev["id"]] = fut
            futs[url] = fut
            try:
                await ws.send(payload)
            except Exception as e:
                fut.set_result((False, f"{SYNTH}send failed: {e}"))
        if not futs:
            return {}
        await asyncio.wait(futs.values(), timeout=wait)
        out = {}
        for url, fut in futs.items():
            if fut.done():
                out[url] = fut.result()
            else:
                self._pending_ok.get(url, {}).pop(ev["id"], None)
        return out

    # --- outbox / delivery ----------------------------------------------------------------------
    def delivery(self, event_id: str) -> str:
        """"sent" (a relay accepted it), "pending" (queued, will be resent) or "failed" (rejected by the
        relays that answered, expired, or pushed out of a full outbox). Unknown ids report "sent": only
        events this pool failed to deliver are ever tracked as anything else."""
        st = self._delivery.get(event_id)
        if st is None and self._store is not None:
            st = self._store.event_outbox_status(event_id)
        return st or "sent"

    def _set_delivery(self, eid: str, status: str) -> None:
        self._delivery[eid] = status
        if len(self._delivery) > 2000:
            for k in [k for k, v in self._delivery.items() if v != "pending"][:500]:
                self._delivery.pop(k, None)
        if self._store is not None:
            try:
                self._store.event_outbox_set(eid, status)
            except Exception:
                log.exception("ninsei: outbox write failed")

    def _settle(self, ev: dict, out: dict[str, tuple[bool, str]]) -> None:
        eid = ev["id"]
        if any(ok for ok, _ in out.values()):
            if eid in self._outbox or eid in self._delivery:
                self._outbox.pop(eid, None)
                self._set_delivery(eid, "sent")
            return
        # nobody accepted it. A real rejection from a relay is final; silence or a dead socket is retried.
        answered = [msg for _, msg in out.values() if not msg.startswith(SYNTH)]
        if answered:
            self._outbox.pop(eid, None)
            self._delivery[eid] = "failed"
            if self._store is not None:
                self._store.event_outbox_put(ev, "failed")
            return
        if eid not in self._outbox:
            self._outbox[eid] = (ev, _now())
            if self._store is not None:
                try:
                    self._store.event_outbox_put(ev, "pending")
                except Exception:
                    log.exception("ninsei: outbox write failed")
            while len(self._outbox) > self._outbox_max:   # full: the oldest gives way
                old = next(iter(self._outbox))
                self._outbox.pop(old)
                self._set_delivery(old, "failed")
        self._delivery[eid] = "pending"

    def _spawn_flush(self, url: str, ws) -> None:
        if not self._outbox:
            return
        t = asyncio.ensure_future(self._flush(url, ws))
        self._flush_tasks.add(t)
        t.add_done_callback(self._flush_tasks.discard)

    async def _flush(self, url: str, ws) -> None:
        """Resend every unacknowledged event to a relay that just connected."""
        now = _now()
        for eid, (ev, queued) in list(self._outbox.items()):
            if now - queued > self._outbox_ttl:
                self._outbox.pop(eid, None)
                self._set_delivery(eid, "failed")
                continue
            if self._ws.get(url) is not ws:
                return
            out = await self._send_all(ev, 4.0, only={url: ws})
            if eid in self._outbox:
                self._settle(ev, out)

    async def query(self, filters: list[dict], *, timeout: float = 4.0) -> list[dict]:
        """One-shot fetch: subscribe, collect until every open relay sent EOSE (or timeout), close."""
        got: dict[str, dict] = {}
        sub_id = "q" + format(random.getrandbits(40), "x")

        def collect(ev, _url):
            got[ev["id"]] = ev

        # one-shot queries must not be deduped against live traffic
        sub = Subscription(sub_id, filters, collect, dedupe=False, seen_ids=set())
        self._subs[sub_id] = sub
        targets = list(self._ws.items())
        for url, ws in targets:
            await self._send_req(url, ws, sub)
        end = time.monotonic() + timeout
        while time.monotonic() < end and len(sub.eose) < len(targets):
            await asyncio.sleep(0.05)
        await self.unsubscribe(sub_id)
        return sorted(got.values(), key=lambda e: e["created_at"])
