"""A face (and the avatar riding in it) published BEFORE this install started must still arrive.

The real order at startup: Engine.reconnect() makes a new RelayPool, calls pool.start() and at once _resubscribe(),
which runs _art_subscribe(). No relay socket is open yet, so the pool's one-shot catch-up query has nobody to ask
and returns [] at once; the live `art` subscription starts at now and never replays older events; and the authors
are then recorded as asked. This drives the real RelayPool against a local fake relay (127.0.0.1, never a real one)
that holds an older face event and honours `since`, like a real relay."""
import asyncio
import json
import time

from websockets.asyncio.server import serve

from ninsei_engine.engine import ART_FACE_D, ART_POW, KIND_META, clean_avatar
from ninsei_engine.relays import RelayPool
from test_hostile import Key, ROOM, bare, settle  # noqa: F401  (fixture re-export)
from test_pictures import art, meet

FULL = {"v": 1, "p": "p12"}


async def until(cond, timeout=15.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        await asyncio.sleep(0.05)
    return bool(cond())


def matches(ev, f):
    return (ev["kind"] in f.get("kinds", [ev["kind"]]) and ev["pubkey"] in f.get("authors", [ev["pubkey"]])
            and ev["created_at"] >= f.get("since", 0)
            and all(any(t[0] == k[1] and t[1] in vals for t in ev["tags"]) for k, vals in f.items() if k.startswith("#")))


async def relay_holding(events, delay=0.3):
    """A relay that stores events, answers REQs from them (honouring kinds, authors, #d and since) and is slow to
    accept: a connection starts only after `delay`, as a real handshake does."""
    async def handler(ws):
        async for raw in ws:
            m = json.loads(raw)
            if m[0] == "REQ":
                for ev in events:
                    if any(matches(ev, f) for f in m[2:]):
                        await ws.send(json.dumps(["EVENT", m[1], ev]))
                await ws.send(json.dumps(["EOSE", m[1]]))
    srv = await serve(handler, "127.0.0.1", 0)
    return srv, f"ws://127.0.0.1:{srv.sockets[0].getsockname()[1]}"


async def test_a_face_published_before_startup_arrives_when_the_relay_connects_after_the_art_query(bare):
    e, _ = bare()
    maya = Key("maya")
    older = art(maya, "face", {"face": {"hue": 200}, "avatar": FULL}, created_at=int(time.time()) - 3600)
    assert older["kind"] == KIND_META and older["id"].startswith("0")   # proof of work was mined
    srv, url = await relay_holding([older])
    await meet(e, maya, "Maya")                      # already seen in a room: allowed to have a picture
    assert maya.ppk in e._art_ok
    try:
        e.pool = RelayPool([url], outbox=e.store)    # the real pool, as reconnect() builds it
        e.pool.start()                               # connecting is a task: nothing is open yet
        assert not e.pool._ws                        # the order under test: the art query starts before any socket
        await e._resubscribe()                       # _art_subscribe runs here (it used to return [] at once)
        assert await e.pool.wait_open(5.0)           # the relay connects a moment later
        await until(lambda: (e._art_view(maya.ppk) or {}).get("avatar"))
        assert (e._art_view(maya.ppk) or {}).get("avatar") == clean_avatar(FULL), "the older face never arrived"
        assert e.people_art([maya.ppk]).get(maya.ppk, {}).get("avatar") == clean_avatar(FULL)
    finally:
        await e.pool.stop()
        srv.close()
        await asyncio.wait_for(srv.wait_closed(), 5)


async def test_control_the_same_event_is_accepted_when_handed_over_directly(bare):
    """Guards the test above: the event passes every receiving check, so only its delivery can fail there."""
    e, _ = bare()
    maya = Key("maya")
    await meet(e, maya, "Maya")
    assert e._take_art(art(maya, "face", {"face": {"hue": 200}, "avatar": FULL}, created_at=int(time.time()) - 3600))
    assert e.people_art([maya.ppk])[maya.ppk]["avatar"] == clean_avatar(FULL)
