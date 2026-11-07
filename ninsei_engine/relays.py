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
import re
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
FAILED_KEEP_S = 4 * 24 * 3600   # a failed row outlives the 3-day event history, or the message would read "sent"
RESUME_MARGIN_S = 300       # a resubscribe asks for this much before the newest event (relays' clocks drift,
                            # and `_seen` already dedupes what comes twice)
BACKOFF_BASE_S = 1.0        # reconnect delay: doubles from here to BACKOFF_MAX_S ...
BACKOFF_MAX_S = 30.0
HEALTHY_AFTER_S = 30.0      # ... and resets only after a connection stayed this long, or delivered an EVENT/EOSE
TRAFFIC_MIN_S = 5.0         # and stayed at least this long (an EOSE then a close is the same hot loop as no reply)
SYNTH = "ninsei:"            # prefix on locally made (not relay-sent) OK results
COOL_BASE_S = 60.0          # a relay that says we're over its rate limit gets no events from us for this long,
COOL_MAX_S = 30 * 60.0      # doubling up to this while it keeps saying so. Reads go on.
FLUSH_GAP_S = 0.25          # between resent events: a backlog sent in one burst trips the limit it waited out
# NIP-01 asks for "rate-limited:"; damus answers "banned: too many rate-limit violations, try again later".
# Sending on through either keeps a per-IP ban alive for every install behind that IP, so we wait instead.
_BUSY_STATUS = re.compile(r"HTTP (?:429|503)\b")
_TRANSIENT = re.compile(r"^\s*rate-limited\b|rate[\s-]*limit|slow\s*down|try again later", re.I)


def transient(reason: str) -> bool:
    """A refusal that means "not now" rather than "never": the event is retried, never marked failed."""
    return bool(_TRANSIENT.search(reason or ""))


def _ephemeral(ev: dict) -> bool:
    """Kinds 20000-29999 are never stored by relays and are stale in a minute, so they never go in the outbox."""
    kind = ev.get("kind")
    return isinstance(kind, int) and 20000 <= kind < 30000


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
    backoff: float = 0.0   # seconds the next reconnect waits (before jitter)
    rate_limited: int = 0  # times this relay told us to slow down


class RelayPool:
    def __init__(self, urls: list[str], *, max_seen: int = 20000, outbox=None,
                 outbox_max: int = OUTBOX_MAX, outbox_ttl: float = OUTBOX_TTL_S,
                 backoff_base: float = BACKOFF_BASE_S, backoff_max: float = BACKOFF_MAX_S,
                 healthy_after: float = HEALTHY_AFTER_S, traffic_min: float = TRAFFIC_MIN_S,
                 cool_base: float = COOL_BASE_S, cool_max: float = COOL_MAX_S, flush_gap: float = FLUSH_GAP_S):
        """`outbox` is an optional Store; with it, unacknowledged events survive a restart."""
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._healthy_after = healthy_after
        self._traffic_min = traffic_min
        self._cool_base = cool_base
        self._cool_max = cool_max
        self._cool_until: dict[str, float] = {}   # url -> monotonic time it may get events again
        self._cool_step: dict[str, int] = {}
        self._limited_at: dict[str, float] = {}   # url -> monotonic time of its last "slow down"
        self._flush_gap = flush_gap
        self._got_traffic: dict[str, bool] = {}
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
        self._inflight: dict[str, int] = {}   # ids waiting on their first relay answers (shown as sent, not pending)
        if self._store is not None:
            try:
                keep = max(self._outbox_ttl, getattr(self._store, "event_history_days", 3) * 86400, FAILED_KEEP_S)
                self._store.event_outbox_prune(keep)
                stale = []
                for ev, ts in self._store.event_outbox_pending():
                    if _ephemeral(ev):   # beats and claims an older version queued: useless now
                        stale.append(ev["id"])
                        continue
                    self._outbox[ev["id"]] = (ev, ts)
                    self._delivery[ev["id"]] = "pending"
                if stale:
                    self._store.event_outbox_drop(stale)
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
        delay = self._backoff_base
        st = self.status[url]
        while not self._stopped:
            st.state = "connecting"
            opened = None
            busy = False
            try:
                async with websockets.connect(url, open_timeout=8, ping_interval=25, ping_timeout=20,
                                              max_size=2 ** 20) as ws:
                    self._ws[url] = ws
                    st.state, st.last_error = "open", ""
                    opened = time.monotonic()
                    self._got_traffic[url] = False   # the delay resets later, once this connection proves useful
                    for sub in list(self._subs.values()):
                        await self._send_req(url, ws, sub)
                    self._spawn_flush(url, ws)
                    async for raw in ws:
                        await self._on_message(url, raw)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # network errors are normal: back off and retry
                st.last_error = type(e).__name__ + (f": {e}" if str(e) else "")
                if _BUSY_STATUS.search(str(e)):
                    busy = True
                    self._cool(url)   # "too many requests" / "unavailable" at the door: wait as for a rate limit
            finally:
                self._ws.pop(url, None)
                for fut in self._pending_ok.pop(url, {}).values():
                    if not fut.done():
                        fut.set_result((False, SYNTH + "disconnected"))
            if self._stopped:
                break
            up = time.monotonic() - opened if opened is not None else 0.0
            if opened is not None and (up >= self._healthy_after
                                       or (self._got_traffic.get(url) and up >= self._traffic_min)):
                # a connection that worked: reconnect promptly. Traffic alone isn't enough: a relay that
                # answers EOSE and drops the socket at once would reset the delay on every round.
                delay = self._backoff_base
            # turned away at the door: wait out the cool. Any other drop reconnects as usual, so reads go on.
            st.state, st.backoff = "backoff", max(delay, self.cooling(url)) if busy else delay
            await asyncio.sleep(st.backoff * (0.7 + random.random() * 0.6))
            delay = min(delay * 2, self._backoff_max)

    # --- inbound --------------------------------------------------------------------------------
    async def _on_message(self, url: str, raw) -> None:
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            return
        if not isinstance(msg, list) or not msg:
            return
        typ = msg[0]
        if typ in ("EVENT", "EOSE"):
            self._got_traffic[url] = True
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
            sub.newest = max(sub.newest, min(created, int(_now())))   # a future-dated event must not push `since` ahead
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
                if time.monotonic() - self._limited_at.get(url, float("-inf")) > self._cool_max:
                    # no "slow down" for a long while: the next limit starts small again. Not on the first
                    # accepted event after a wait: a relay that refills an allowance accepts a few, then refuses.
                    self._cool_step.pop(url, None)
            else:
                st.rejected += 1
                st.last_reject = str(msg[3] if len(msg) > 3 else "")[:120]
                if transient(st.last_reject):
                    self._cool(url)
            if fut and not fut.done():
                fut.set_result((bool(msg[2]), str(msg[3] if len(msg) > 3 else "")))
        elif typ == "EOSE" and len(msg) >= 2:
            sub = self._subs.get(msg[1])
            if sub:
                sub.eose.add(url)
        elif typ == "NOTICE" and len(msg) >= 2 and isinstance(msg[1], str) and transient(msg[1]):
            self.status[url].last_reject = msg[1][:120]
            self._cool(url)
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

    # --- rate limits ----------------------------------------------------------------------------
    def cooling(self, url: str) -> float:
        """Seconds until this relay gets events from us again (0 when it isn't cooling)."""
        return max(0.0, self._cool_until.get(url, 0.0) - time.monotonic())

    def _cool(self, url: str) -> None:
        self._limited_at[url] = time.monotonic()
        if self.cooling(url) or self._stopped:
            return   # the other answers to a burst land after the first one already started the wait
        step = self._cool_step.get(url, 0)
        wait = min(self._cool_base * (2 ** step), self._cool_max)
        self._cool_step[url] = step + 1
        self._cool_until[url] = time.monotonic() + wait
        self.status[url].rate_limited += 1
        log.info("ninsei: %s asked us to slow down; no events to it for %.0f s", url, wait)
        t = asyncio.ensure_future(self._after_cool(url, wait))
        self._flush_tasks.add(t)
        t.add_done_callback(self._flush_tasks.discard)

    async def _after_cool(self, url: str, wait: float) -> None:
        await asyncio.sleep(wait)
        ws = self._ws.get(url)
        if ws is not None and not self.cooling(url):
            self._spawn_flush(url, ws)   # what nobody else took is still queued: try this relay again

    # --- subscriptions --------------------------------------------------------------------------
    async def _send_req(self, url: str, ws, sub: Subscription) -> None:
        filters = []
        for f in sub.filters:
            f2 = dict(f)
            if sub.newest and "since" in f2:  # resume where we left off, with room for clock skew
                f2["since"] = min(max(int(f2["since"]), sub.newest - RESUME_MARGIN_S), int(_now()))
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
        A durable event gets its pending outbox row BEFORE the wait for relay answers, so quitting (or a
        cancelled task) inside that wait still leaves it to be resent on the next start. If no relay accepts
        it (none open, no answer), it stays queued and is resent when a relay (re)connects; see `delivery`.
        Ephemeral kinds (presence, claims) are fire and forget and never queued."""
        self._queue(ev)
        self._inflight[ev["id"]] = self._inflight.get(ev["id"], 0) + 1
        try:
            out = await self._send_all(ev, wait)
        finally:
            n = self._inflight.get(ev["id"], 1) - 1
            if n > 0:
                self._inflight[ev["id"]] = n
            else:
                self._inflight.pop(ev["id"], None)
        self._settle(ev, out)
        return out

    async def _send_all(self, ev: dict, wait: float, only: Optional[dict] = None) -> dict[str, tuple[bool, str]]:
        self.mark_seen(ev["id"])
        futs: dict[str, asyncio.Future] = {}
        payload = json.dumps(["EVENT", ev])
        loop = asyncio.get_running_loop()
        for url, ws in list((only or self._ws).items()):
            if self.cooling(url):
                continue   # it said slow down: sending anyway only extends the ban
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
        if event_id in self._inflight:
            return "sent"   # still inside the first ack wait: not yet a reason to alarm the owner
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

    def _queue(self, ev: dict) -> None:
        """Record a durable event as pending (memory and disk) before it is first sent. Idempotent."""
        eid = ev["id"]
        if _ephemeral(ev) or eid in self._outbox:
            return
        self._outbox[eid] = (ev, _now())
        self._delivery[eid] = "pending"
        if self._store is not None:
            try:
                self._store.event_outbox_put(ev, "pending")
            except Exception:
                log.exception("ninsei: outbox write failed")
        while len(self._outbox) > self._outbox_max:   # full: the oldest gives way
            old = next(iter(self._outbox))
            self._outbox.pop(old)
            self._set_delivery(old, "failed")

    def _settle(self, ev: dict, out: dict[str, tuple[bool, str]]) -> None:
        eid = ev["id"]
        if _ephemeral(ev):
            return
        if any(ok for ok, _ in out.values()):
            self._outbox.pop(eid, None)
            self._delivery[eid] = "sent"
            self._store_call("event_outbox_drop", [eid])   # unknown ids read as "sent": no row to keep
            return
        # nobody accepted it. A real rejection from a relay is final; silence or a dead socket is retried.
        answered = [msg for _, msg in out.values() if not msg.startswith(SYNTH) and not transient(msg)]
        if answered:
            self._outbox.pop(eid, None)
            self._delivery[eid] = "failed"
            self._store_call("event_outbox_put", ev, "failed")
            return
        if eid not in self._outbox and self._delivery.get(eid) not in ("failed", "sent"):
            self._queue(ev)   # a path that skipped publish (a flush of an evicted event stays failed)
        if eid in self._outbox:
            self._delivery[eid] = "pending"

    def _store_call(self, name: str, *args) -> None:
        if self._store is None:
            return
        try:
            getattr(self._store, name)(*args)
        except Exception:
            log.exception("ninsei: outbox write failed")

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
            if self._ws.get(url) is not ws or self.cooling(url):
                return   # gone, or it said slow down: the flush after the cool picks up from here
            out = await self._send_all(ev, 4.0, only={url: ws})
            if eid in self._outbox:
                self._settle(ev, out)
            await asyncio.sleep(self._flush_gap)

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
