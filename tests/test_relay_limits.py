"""Relays that rate-limit us, presence traffic, and joining a code nobody is using.

Found 2026-11-06 with an outside probe: relay.damus.io held 3 of shader club's 44 events and answered
"banned: too many rate-limit violations, try again later". The pool kept sending to it (every presence beat,
every state change), which keeps a per-IP ban going for every install on that network, and it marked a
durable event "failed" when the only answer was a rate limit.
"""
import asyncio
import json

import pytest
from websockets.asyncio.server import serve

from ninsei_engine import engine as engine_mod
from ninsei_engine import nostr
from ninsei_engine.engine import KIND_LIVE
from ninsei_engine.relays import RelayPool, transient
from test_hostile import ROOM, FakePool, bare  # noqa: F401  (fixture re-export)

SK = "1" * 64


async def until(cond, timeout=30.0):
    end = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < end:
        if cond():
            return True
        await asyncio.sleep(0.02)
    return cond()


async def _server(handler):
    srv = await serve(handler, "127.0.0.1", 0)
    return srv, f"ws://127.0.0.1:{srv.sockets[0].getsockname()[1]}"


def _limited_relay(reject_first: int, reason="rate-limited: slow down"):
    """A relay that refuses the first `reject_first` events with `reason`, then takes everything."""
    got = []

    async def handler(ws):
        async for raw in ws:
            m = json.loads(raw)
            if m[0] == "EVENT":
                got.append(m[1]["id"])
                ok = len(got) > reject_first
                await ws.send(json.dumps(["OK", m[1]["id"], ok, "" if ok else reason]))
            elif m[0] == "REQ":
                await ws.send(json.dumps(["EOSE", m[1]]))
    return handler, got


@pytest.mark.parametrize("reason", [
    "rate-limited: slow down there chief",
    "banned: too many rate-limit violations, try again later",
    "error: rate limit exceeded",
    "slow down",
])
def test_rate_limit_replies_are_transient(reason):
    assert transient(reason)


@pytest.mark.parametrize("reason", [
    "invalid: bad event id or signature", "blocked: not on the allow list", "pow: difficulty 20 needed",
    "duplicate: already have this event", "", "ninsei:disconnected",
])
def test_real_rejections_are_not(reason):
    assert not transient(reason)


async def test_a_rate_limited_relay_gets_nothing_until_it_cools_then_the_queue_is_resent():
    handler, got = _limited_relay(reject_first=1)
    srv, url = await _server(handler)
    pool = RelayPool([url], cool_base=0.4, cool_max=2.0)
    pool.start()
    try:
        assert await pool.wait_open(30)
        ev1 = nostr.build_event(SK, 4242, "one", [["h", "r"]])
        await pool.publish(ev1, wait=30)
        assert pool.delivery(ev1["id"]) == "pending"     # "not now" is not "never"
        assert pool.cooling(url) > 0 and pool.status[url].rate_limited == 1
        ev2 = nostr.build_event(SK, 4242, "two", [["h", "r"]])
        beat = nostr.build_event(SK, KIND_LIVE, "beat", [["h", "r"]])
        await pool.publish(ev2, wait=0.05)
        await pool.publish(beat, wait=0.05)
        assert got == [ev1["id"]]                        # nothing sent while it cools
        assert await until(lambda: pool.delivery(ev1["id"]) == "sent" and pool.delivery(ev2["id"]) == "sent")
        assert beat["id"] not in got                     # an old beat is never resent
        assert pool.cooling(url) == 0
    finally:
        await pool.stop()
        srv.close()
        await asyncio.wait_for(srv.wait_closed(), 5)


async def test_a_relay_that_keeps_limiting_waits_longer_each_time():
    handler, got = _limited_relay(reject_first=10**6)
    srv, url = await _server(handler)
    pool = RelayPool([url], cool_base=0.2, cool_max=0.8)
    pool.start()
    try:
        assert await pool.wait_open(30)
        await pool.publish(nostr.build_event(SK, 4242, "a", [["h", "r"]]), wait=30)
        first = pool.cooling(url)
        assert 0 < first <= 0.2
        assert await until(lambda: pool.status[url].rate_limited >= 2)   # the flush after cooling is refused too
        assert 0.2 < pool.cooling(url) <= 0.4
        assert await until(lambda: pool.status[url].rate_limited >= 4)
        assert pool.cooling(url) <= 0.8                  # capped
    finally:
        await pool.stop()
        srv.close()
        await asyncio.wait_for(srv.wait_closed(), 5)


async def test_a_real_rejection_is_still_final_and_does_not_cool():
    handler, _ = _limited_relay(reject_first=1, reason="invalid: nope")
    srv, url = await _server(handler)
    pool = RelayPool([url], cool_base=5)
    pool.start()
    try:
        assert await pool.wait_open(30)
        ev = nostr.build_event(SK, 4242, "x", [["h", "r"]])
        await pool.publish(ev, wait=30)
        assert pool.delivery(ev["id"]) == "failed" and pool.cooling(url) == 0
    finally:
        await pool.stop()
        srv.close()
        await asyncio.wait_for(srv.wait_closed(), 5)


async def test_a_rate_limit_notice_cools_the_relay_too():
    got = []

    async def handler(ws):
        async for raw in ws:
            m = json.loads(raw)
            if m[0] == "EVENT":
                got.append(m[1]["id"])
                await ws.send(json.dumps(["NOTICE", "rate-limited: you are noisy"]))
    srv, url = await _server(handler)
    pool = RelayPool([url], cool_base=30)
    pool.start()
    try:
        assert await pool.wait_open(30)
        await pool.publish(nostr.build_event(SK, 4242, "a", [["h", "r"]]), wait=0.2)
        assert await until(lambda: pool.cooling(url) > 0)
        await pool.publish(nostr.build_event(SK, 4242, "b", [["h", "r"]]), wait=0.05)
        assert len(got) == 1
    finally:
        await pool.stop()
        srv.close()
        await asyncio.wait_for(srv.wait_closed(), 5)


# --- presence traffic --------------------------------------------------------------------------------------

def test_presence_is_a_minute_and_absence_allows_two_missed_beats():
    assert engine_mod.PRESENCE_EVERY == 60 and engine_mod.ABSENT_AFTER > 2 * engine_mod.PRESENCE_EVERY


async def test_a_burst_of_state_changes_costs_at_most_two_beats_per_room(bare):  # noqa: F811
    e, _ = bare(ts=0.05)                       # gap: 5 s * 0.05 = 0.25 s
    beats = lambda: [ev for ev in e.pool.sent if ev["kind"] == KIND_LIVE]  # noqa: E731
    for i in range(12):
        e._set_state("activity: working", f"step {i}")
    assert await until(lambda: len(beats()) == 2, 5)
    await asyncio.sleep(0.5)  # fixed-wait-ok: proves no further beat arrives after the gap
    assert len(beats()) == 2
    assert json.loads(beats()[-1]["content"])["state"] == "activity: working"


# --- joining a code nobody uses ----------------------------------------------------------------------------

class QueryPool(FakePool):
    def __init__(self, found=()):
        super().__init__()
        self.found = list(found)

    async def query(self, filters, timeout=4.0):
        return [ev for ev in self.found if ev["kind"] in filters[0].get("kinds", [])]

    async def subscribe(self, *a, **k):
        pass

    async def unsubscribe(self, *a, **k):
        pass


async def test_joining_a_code_with_nothing_on_my_relays_says_so(bare):  # noqa: F811
    e, _ = bare()
    e.pool = QueryPool()
    meta = await e.join_room("ninsei:0123456789abcdef")
    assert meta["found"] is False and meta["id"] == "0123456789abcdef"


async def test_joining_a_room_with_history_is_found(bare):  # noqa: F811
    from test_hostile import Key
    e, _ = bare()
    k = Key("stranger")
    msg = nostr.build_event(k.psk, 4242, json.dumps({"t": "msg", "text": "hi"}), [["h", "fedcba9876543210"]])
    e.pool = QueryPool([msg])
    meta = await e.join_room("fedcba9876543210")
    assert meta["found"] is True


async def test_a_relay_that_refuses_the_connection_with_429_waits_like_a_rate_limit():
    from websockets.datastructures import Headers
    from websockets.http11 import Response
    tries = []

    def refuse(conn, request):
        tries.append(1)
        return Response(429, "Too Many Requests", Headers(), b"")
    srv = await serve(lambda ws: None, "127.0.0.1", 0, process_request=refuse)
    url = f"ws://127.0.0.1:{srv.sockets[0].getsockname()[1]}"
    pool = RelayPool([url], backoff_base=0.01, backoff_max=0.05, cool_base=30)
    pool.start()
    try:
        assert await until(lambda: pool.cooling(url) > 0)
        await asyncio.sleep(0.3)  # fixed-wait-ok: plain backoff would have retried several times by now
        assert len(tries) == 1 and pool.status[url].backoff >= 29
    finally:
        await pool.stop()
        srv.close()
        await asyncio.wait_for(srv.wait_closed(), 5)


# --- review fixes, 2026-11-07 ---------------------------------------------------------------------------------

async def test_the_wait_still_doubles_against_a_relay_that_refills_an_allowance():
    """It accepts one event per window and refuses the rest: the accepted one must not reset the doubling."""
    stamps = []

    async def handler(ws):
        async for raw in ws:
            m = json.loads(raw)
            if m[0] == "EVENT":
                now = asyncio.get_running_loop().time()
                ok = not [t for t in stamps if now - t < 0.5]
                if ok:
                    stamps.append(now)
                await ws.send(json.dumps(["OK", m[1]["id"], ok, "" if ok else "rate-limited: slow down"]))
            elif m[0] == "REQ":
                await ws.send(json.dumps(["EOSE", m[1]]))
    srv, url = await _server(handler)
    pool = RelayPool([url], cool_base=0.1, cool_max=5.0, flush_gap=0)
    pool.start()
    try:
        assert await pool.wait_open(30)
        for i in range(8):
            await pool.publish(nostr.build_event(SK, 4242, f"m{i}", [["h", "r"]]), wait=0.2)
        assert await until(lambda: pool._cool_step.get(url, 0) >= 3)
    finally:
        await pool.stop()
        srv.close()
        await asyncio.wait_for(srv.wait_closed(), 5)


async def test_a_backlog_is_resent_paced_and_stops_when_the_relay_says_slow_down():
    handler, got = _limited_relay(reject_first=1)
    srv, url = await _server(handler)
    pool = RelayPool([url], cool_base=0.3, flush_gap=0.1)
    pool.start()
    try:
        assert await pool.wait_open(30)
        evs = [nostr.build_event(SK, 4242, f"q{i}", [["h", "r"]]) for i in range(4)]
        for ev in evs:
            await pool.publish(ev, wait=0.2)
        assert await until(lambda: all(pool.delivery(e["id"]) == "sent" for e in evs))
        # one refused, three skipped while cooling, then four resent one at a time
        assert len(got) == 5
    finally:
        await pool.stop()
        srv.close()
        await asyncio.wait_for(srv.wait_closed(), 5)


async def test_a_drop_while_cooling_reconnects_at_once_so_reads_go_on():
    conns = []

    async def handler(ws):
        conns.append(asyncio.get_running_loop().time())
        async for raw in ws:
            m = json.loads(raw)
            if m[0] == "EVENT":
                await ws.send(json.dumps(["OK", m[1]["id"], False, "rate-limited: slow down"]))
                await ws.close()
                return
            if m[0] == "REQ":
                await ws.send(json.dumps(["EOSE", m[1]]))
    srv, url = await _server(handler)
    pool = RelayPool([url], cool_base=60, backoff_base=0.01, backoff_max=0.05)
    pool.start()
    try:
        assert await pool.wait_open(30)
        await pool.publish(nostr.build_event(SK, 4242, "x", [["h", "r"]]), wait=5)
        assert pool.cooling(url) > 50
        assert await until(lambda: len(conns) >= 2, 5)   # not 60 s later
    finally:
        await pool.stop()
        srv.close()
        await asyncio.wait_for(srv.wait_closed(), 5)


async def test_a_publish_that_settles_after_a_flush_delivered_it_stays_sent():
    got_a = []

    async def relay_a(ws):   # refuses the first event as rate-limited, then takes everything
        async for raw in ws:
            m = json.loads(raw)
            if m[0] == "EVENT":
                got_a.append(m[1]["id"])
                ok = len(got_a) > 1
                await ws.send(json.dumps(["OK", m[1]["id"], ok, "" if ok else "rate-limited: slow down"]))
            elif m[0] == "REQ":
                await ws.send(json.dumps(["EOSE", m[1]]))

    async def relay_b(ws):   # open, never answers an EVENT
        async for raw in ws:
            m = json.loads(raw)
            if m[0] == "REQ":
                await ws.send(json.dumps(["EOSE", m[1]]))
    sa, ua = await _server(relay_a)
    sb, ub = await _server(relay_b)
    pool = RelayPool([ua, ub], cool_base=0.3)
    pool.start()
    try:
        assert await pool.wait_open(30, at_least=2)
        await pool.publish(nostr.build_event(SK, 4242, "zero", [["h", "r"]]), wait=0.2)
        e = nostr.build_event(SK, 4242, "E", [["h", "r"]])
        await pool.publish(e, wait=1.5)     # A cools, B is silent; A's flush after the cool delivers E meanwhile
        assert e["id"] in got_a and pool.delivery(e["id"]) == "sent" and e["id"] not in pool._outbox
    finally:
        await pool.stop()
        sa.close()
        await asyncio.wait_for(sa.wait_closed(), 5)
        sb.close()
        await asyncio.wait_for(sb.wait_closed(), 5)


def test_the_probe_survives_hostile_events():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("relay_probe", Path(__file__).parent.parent / "scripts/relay_probe.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    evs = [{"pubkey": "a", "content": json.dumps({"t": []})}, {"pubkey": ["x"], "content": json.dumps({"t": {}})},
           {"pubkey": "b", "content": json.dumps({"t": "msg\x1b[2J"})}, {"content": "[1, 2]"}, "junk", None,
           {"pubkey": "c", "content": json.dumps({"t": "msg"})}]
    out = probe.summarize(evs)
    assert "\x1b" not in out and "5 events from 3 keys" in out
