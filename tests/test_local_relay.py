import asyncio
import json

import pytest
from websockets.asyncio.client import connect

from ninsei_engine import nostr
from local_relay import LocalRelay


@pytest.fixture
async def relay():
    async with LocalRelay(port=0) as r:
        yield r


async def rx(ws, timeout=15.0):
    return json.loads(await asyncio.wait_for(ws.recv(), timeout))


async def publish(ws, ev):
    await ws.send(json.dumps(["EVENT", ev]))
    return await rx(ws)


async def req(ws, sub, *filters):
    await ws.send(json.dumps(["REQ", sub, *filters]))
    out = []
    while True:
        m = await rx(ws)
        if m[0] == "EOSE":
            return out
        out.append(m[2])


async def test_publish_ok_and_duplicate(relay):
    sk = nostr.new_secret()
    ev = nostr.build_event(sk, 1, "hi")
    async with connect(relay.url) as ws:
        assert await publish(ws, ev) == ["OK", ev["id"], True, ""]
        ok = await publish(ws, ev)
        assert ok[2] is True and ok[3].startswith("duplicate:")


async def test_req_tag_filter_and_eose(relay):
    sk = nostr.new_secret()
    a = nostr.build_event(sk, 1, "a", [["t", "x"]], created_at=100)
    b = nostr.build_event(sk, 1, "b", [["t", "y"]], created_at=101)
    c = nostr.build_event(sk, 1, "c", [["t", "x"]], created_at=102)
    async with connect(relay.url) as ws:
        for e in (a, b, c):
            await publish(ws, e)
        got = await req(ws, "s1", {"#t": ["x"]})
        assert [e["id"] for e in got] == [c["id"], a["id"]]  # newest first
        assert [e["id"] for e in await req(ws, "s2", {"#t": ["x"], "limit": 1})] == [c["id"]]
        assert [e["id"] for e in await req(ws, "s3", {"since": 101, "until": 101})] == [b["id"]]
        assert await req(ws, "s4", {"authors": ["00" * 32]}) == []
        assert len(await req(ws, "s5", {"ids": [a["id"]], "kinds": [1]})) == 1


async def test_live_forwarding_and_close(relay):
    sk = nostr.new_secret()
    async with connect(relay.url) as sub, connect(relay.url) as pub:
        assert await req(sub, "live", {"kinds": [1]}) == []
        ev = nostr.build_event(sk, 1, "live")
        await publish(pub, ev)
        m = await rx(sub)
        assert m[:2] == ["EVENT", "live"] and m[2]["id"] == ev["id"]
        await sub.send(json.dumps(["CLOSE", "live"]))
        # The relay handles one connection's messages in order: once this REQ's EOSE is back, CLOSE is done.
        assert await req(sub, "sync", {"kinds": [2]}) == []
        await publish(pub, nostr.build_event(sk, 1, "after close"))
        with pytest.raises(asyncio.TimeoutError):
            await rx(sub, 0.2)


async def test_ephemeral_not_stored_but_forwarded(relay):
    sk = nostr.new_secret()
    async with connect(relay.url) as sub, connect(relay.url) as pub:
        await req(sub, "e", {"kinds": [20001]})
        ev = nostr.build_event(sk, 20001, "eph")
        assert (await publish(pub, ev))[2] is True
        assert (await rx(sub))[2]["id"] == ev["id"]
        assert await req(pub, "q", {"kinds": [20001]}) == []
    assert ev["id"] not in relay.events


async def test_replaceable_and_parameterized(relay):
    sk = nostr.new_secret()
    old = nostr.build_event(sk, 10002, "old", created_at=100)
    new = nostr.build_event(sk, 10002, "new", created_at=200)
    stale = nostr.build_event(sk, 10002, "stale", created_at=50)
    p1 = nostr.build_event(sk, 30001, "p1", [["d", "a"]], created_at=100)
    p2 = nostr.build_event(sk, 30001, "p2", [["d", "b"]], created_at=100)
    p1b = nostr.build_event(sk, 30001, "p1b", [["d", "a"]], created_at=150)
    async with connect(relay.url) as ws:
        for e in (old, new, stale, p1, p2, p1b):
            await publish(ws, e)
        assert [e["content"] for e in await req(ws, "r", {"kinds": [10002]})] == ["new"]
        assert sorted(e["content"] for e in await req(ws, "p", {"kinds": [30001]})) == ["p1b", "p2"]


async def test_tie_keeps_lower_id(relay):
    sk = nostr.new_secret()
    evs = [nostr.build_event(sk, 10002, c, created_at=100) for c in ("x", "y")]
    async with connect(relay.url) as ws:
        for e in evs:
            await publish(ws, e)
        got = await req(ws, "t", {"kinds": [10002]})
    assert [e["id"] for e in got] == [min(e["id"] for e in evs)]


async def test_invalid_sig_rejected(relay):
    ev = nostr.build_event(nostr.new_secret(), 1, "x")
    bad = dict(ev, content="tampered")
    async with connect(relay.url) as ws:
        ok = await publish(ws, bad)
        assert ok[0] == "OK" and ok[2] is False and ok[3].startswith("invalid:")
        assert await req(ws, "s", {"kinds": [1]}) == []


async def test_too_large():
    async with LocalRelay(port=0, max_message_size=2048) as relay:
        ev = nostr.build_event(nostr.new_secret(), 1, "x" * 5000)
        async with connect(relay.url) as ws:
            assert await publish(ws, ev) == ["OK", ev["id"], False, "invalid: too large"]


async def test_restart_same_port_keeps_events(relay):
    ev = nostr.build_event(nostr.new_secret(), 1, "persist")
    url = relay.url
    async with connect(url) as ws:
        await publish(ws, ev)
    await relay.stop()
    with pytest.raises(OSError):
        await connect(url, open_timeout=0.5)
    await relay.start()
    assert relay.url == url
    async with connect(url) as ws:
        assert [e["id"] for e in await req(ws, "s", {"ids": [ev["id"]]})] == [ev["id"]]


async def test_drop_and_delay():
    sk = nostr.new_secret()
    async with LocalRelay(port=0, drop_rate=1.0) as relay:
        async with connect(relay.url) as sub, connect(relay.url) as pub:
            await req(sub, "d", {"kinds": [1]})
            await publish(pub, nostr.build_event(sk, 1, "dropped"))
            with pytest.raises(asyncio.TimeoutError):
                await rx(sub, 0.2)
    async with LocalRelay(port=0, delay_ms=1000) as relay:  # far past the 0.1 s "not yet" window, even under load
        async with connect(relay.url) as sub, connect(relay.url) as pub:
            await req(sub, "d", {"kinds": [1]})
            await publish(pub, nostr.build_event(sk, 1, "slow"))
            with pytest.raises(asyncio.TimeoutError):
                await rx(sub, 0.1)
            assert (await rx(sub))[2]["content"] == "slow"
