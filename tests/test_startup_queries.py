"""One-shot queries at startup: `pool.start()` only schedules the connections, and the engine asks at once (the
art catch-up in `_resubscribe`, the Lobby's first refresh, a join or a profile right after launch). A query must
wait for relays still on their first connection, say whether anyone answered (`query_ex`), and a caller must not
record "nothing there" when nobody was asked. Local relays only (127.0.0.1), never a real one."""
import asyncio
import json
import socket
import time
from types import SimpleNamespace

from ninsei_engine import nostr
from ninsei_engine.engine import APP_TAG, ART_FACE_D, KIND_META, clean_avatar, room_id_for
from ninsei_engine.relays import RelayPool
from local_relay import LocalRelay
from test_hostile import Key, ROOM, bare, settle  # noqa: F401  (fixture re-export)
from test_pictures import ArtPool, art, meet

FULL = {"v": 1, "p": "p12"}


async def until(cond, timeout=15.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        await asyncio.sleep(0.05)
    return bool(cond())


def dead_url():
    """A local port nothing listens on: connecting is refused at once."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"ws://127.0.0.1:{port}"


def room_meta(key, name, nonce="n1", interests=("synths",)):
    rid = room_id_for(key.ppk, nonce)
    tags = [["d", f"ninsei/room/{rid}"], ["t", APP_TAG]] + [["t", i] for i in interests]
    return rid, nostr.build_event(key.psk, KIND_META, json.dumps({"name": name, "nonce": nonce}), tags, pow_bits=12)


def card(key, line):
    tags = [["d", "ninsei/card"], ["t", APP_TAG], ["t", "synths"]]
    return nostr.build_event(key.psk, KIND_META, json.dumps({"name": "Card", "line": line}), tags, pow_bits=12)


class QPool(ArtPool):
    """A pool that answers one-shot queries as told: `answered` is who sent EOSE (empty: nobody did)."""

    def __init__(self, answered=(), events=()):
        super().__init__()
        self.answered = set(answered)
        self.events = list(events)
        self.queries = []
        self.relay_queries = []
        self.relay_events = {}
        self.relay_done = {}

    async def query_ex(self, filters, timeout=4.0):
        self.queries.append(filters)
        return list(self.events), set(self.answered)

    async def query(self, filters, timeout=4.0):
        return (await self.query_ex(filters, timeout=timeout))[0]

    async def query_relay(self, url, filters, timeout=8.0, needs_auth=False):
        self.relay_queries.append((url, filters))
        return list(self.relay_events.get(url, [])), self.relay_done.get(url, True)

    def cooling(self, url):
        return 0.0

    async def wait_open(self, timeout=8.0, at_least=1):
        return await until(lambda: bool(self.answered), timeout)

    def open_count(self):
        return len(self.answered)


def is_open(*urls):
    return {u: SimpleNamespace(state="open", retry_at=0.0) for u in urls}


# --- the pool -----------------------------------------------------------------------------------------------

async def test_a_query_started_before_any_connection_is_answered_once_a_relay_connects():
    k = Key("q")
    ev = nostr.build_event(k.psk, 1, "older", [["t", "x"]], created_at=int(time.time()) - 3600)
    async with LocalRelay(port=0) as relay:
        relay.events[ev["id"]] = ev
        pool = RelayPool([relay.url])
        pool.start()
        try:
            assert not pool._ws                                       # nothing is open: start() only scheduled it
            got, answered = await pool.query_ex([{"kinds": [1]}], timeout=10)
            assert [e["id"] for e in got] == [ev["id"]] and answered == {relay.url}
            assert len(relay.req_log) == 1                            # still one REQ to that relay
            assert [e["id"] for e in await pool.query([{"kinds": [1]}], timeout=10)] == [ev["id"]]
        finally:
            await pool.stop()


async def test_a_query_does_not_wait_out_its_timeout_for_a_relay_that_already_failed_and_says_nobody_answered():
    pool = RelayPool([dead_url()], backoff_base=30.0)
    pool.start()
    try:
        assert await until(lambda: pool.status[pool.urls[0]].state == "backoff", 10)
        t = time.monotonic()
        got, answered = await pool.query_ex([{"kinds": [1]}], timeout=10)
        assert got == [] and answered == set() and time.monotonic() - t < 2
    finally:
        await pool.stop()


async def test_a_query_on_a_pool_that_never_started_returns_at_once():
    pool = RelayPool([dead_url()])
    t = time.monotonic()
    assert await pool.query_ex([{"kinds": [1]}], timeout=10) == ([], set())
    assert time.monotonic() - t < 1


# --- the art catch-up ---------------------------------------------------------------------------------------

async def test_an_unanswered_art_catch_up_is_retried_once_and_nobody_is_marked_asked(bare):
    e, _ = bare()
    maya = Key("maya")
    await meet(e, maya, "Maya")
    e.loop = asyncio.get_running_loop()   # from here _art_soon schedules (on the engine's loop)
    e.pool = QPool()                      # no relay answers
    await e._art_subscribe()
    assert len(e.pool.queries) == 1 and e._art_relays == {}
    assert e._art_sent and maya.ppk in e._art_sent              # the live request went out
    assert e._art_waiting                                       # and the one retry is scheduled
    await settle(e)                                             # the retry ran, nobody answered again ...
    assert len(e.pool.queries) == 2 and e._art_relays == {}
    assert not e._art_waiting and not e._tasks                  # ... and no third one: no retry storm
    await e._art_subscribe()                                    # the next reason to ask (a join) asks again
    assert len(e.pool.queries) == 3 and len(e.pool.subs) == 1   # the live request is not resent


async def test_a_retried_catch_up_takes_the_face_once_a_relay_answers(bare):
    e, _ = bare()
    maya = Key("maya")
    await meet(e, maya, "Maya")
    e.loop = asyncio.get_running_loop()
    older = art(maya, "face", {"face": {"hue": 200}, "avatar": FULL}, created_at=int(time.time()) - 3600)
    e.pool = QPool()
    await e._art_subscribe()
    assert e._art_waiting
    e.pool.answered, e.pool.events = {"wss://a"}, [older]       # a relay connects before the retry
    await settle(e)
    assert e._art_view(maya.ppk).get("avatar") == clean_avatar(FULL)
    assert maya.ppk in e._art_relays["wss://a"] and not e._art_retried


async def test_an_answered_but_empty_catch_up_is_marked_asked_and_never_retried(bare):
    e, _ = bare()
    maya = Key("maya")
    await meet(e, maya, "Maya")
    e.loop = asyncio.get_running_loop()
    e.pool = QPool(answered={"wss://a"})                        # the relay answered: it holds nothing for them
    await e._art_subscribe()
    assert len(e.pool.queries) == 1 and maya.ppk in e._art_relays["wss://a"] and not e._art_waiting
    await e._art_subscribe()
    assert len(e.pool.queries) == 1                             # nothing changed: nothing sent
    e.pool.status = is_open("wss://a")
    e._art_touch()
    await settle(e)
    assert e.pool.relay_queries == []                           # steady state: the minute tick sends nothing


async def test_a_relay_that_connects_after_the_catch_up_is_asked_once_by_the_minute_tick(bare):
    e, _ = bare()
    maya = Key("maya")
    await meet(e, maya, "Maya")
    older = art(maya, "face", {"face": {"hue": 200}, "avatar": FULL}, created_at=int(time.time()) - 3600)
    e.pool = QPool(answered={"wss://a"})                        # only relay A was open for the catch-up
    await e._art_subscribe()
    assert e._art_view(maya.ppk).get("avatar") is None          # and A doesn't hold the face
    e.pool.status = is_open("wss://a", "wss://b")               # B came up later; only B has it
    e.pool.relay_events["wss://b"] = [older]
    e._art_touch()
    await settle(e)
    assert [u for u, _ in e.pool.relay_queries] == ["wss://b"]
    assert maya.ppk in [a for f in e.pool.relay_queries[0][1] for a in f["authors"]]
    assert e._art_view(maya.ppk).get("avatar") == clean_avatar(FULL)
    e._art_touch()
    await settle(e)
    assert len(e.pool.relay_queries) == 1                       # caught up: no second ask


async def test_a_relay_whose_own_catch_up_failed_waits_before_it_is_asked_again(bare):
    e, _ = bare()
    maya = Key("maya")
    await meet(e, maya, "Maya")
    e.pool = QPool(answered={"wss://a"})
    await e._art_subscribe()
    e.pool.status = is_open("wss://a", "wss://b")
    e.pool.relay_done["wss://b"] = False                        # B times out (no EOSE)
    e._art_touch()
    await settle(e)
    assert maya.ppk not in e._art_relays.get("wss://b", set())  # not answered: not marked
    e._art_touch()
    await settle(e)
    assert len(e.pool.relay_queries) == 1                       # and not asked again every minute


async def test_forgetting_a_person_forgets_who_was_asked_about_them(bare):
    e, _ = bare()
    maya = Key("maya")
    await meet(e, maya, "Maya")
    e.pool = QPool(answered={"wss://a"})
    await e._art_subscribe()
    assert maya.ppk in e._art_relays["wss://a"]
    e._art_forget(maya.ppk)
    assert maya.ppk not in e._art_relays["wss://a"]


# --- the Lobby, Browse all, joining by code, profiles ------------------------------------------------------

async def test_the_lobby_refreshed_right_after_start_shows_the_relays_rooms(bare):
    e, _ = bare()
    e.save_settings({"interests": ["synths"]})
    rid, meta = room_meta(Key("host"), "Pop-up")
    async with LocalRelay(port=0) as relay:
        relay.events[meta["id"]] = meta
        e.pool = RelayPool([relay.url])
        e.pool.start()
        try:
            lobby = await e.refresh_lobby()                       # the dashboard's first call, at once
            assert rid in {r["id"] for r in lobby["rooms"]} and lobby["at"] > 0
        finally:
            await e.pool.stop()


async def test_a_lobby_refresh_nobody_answered_keeps_at_zero_and_retries_once(bare):
    e, _ = bare()
    e.save_settings({"interests": ["synths"]})
    rid, meta = room_meta(Key("host"), "Pop-up")
    e.pool = QPool()
    lobby = await e.refresh_lobby()
    assert lobby["at"] == 0                                     # the Lobby asks again next time it opens
    retries = [t for t in e._tasks if t.get_coro().__name__ == "_lobby_again"]
    assert len(retries) == 1
    await e.refresh_lobby()
    assert len([t for t in e._tasks if t.get_coro().__name__ == "_lobby_again"]) == 1   # one retry, not one each
    e.pool.answered, e.pool.events = {"wss://a"}, [meta]        # a relay opens
    await settle(e)
    assert rid in {r["id"] for r in e.lobby["rooms"]} and e.lobby["at"] > 0


async def test_browse_all_nobody_answered_gives_the_cooldown_back(bare):
    e, _ = bare()
    rid, meta = room_meta(Key("host"), "Pop-up")
    e.pool = QPool()
    out = await e.browse_rooms()
    assert out["rooms"] == [] and out["wait"] == 0
    e.pool.answered, e.pool.events = {"wss://a"}, [meta]
    out = await e.browse_rooms()                                # straight away: not held back by a cooldown
    assert out["cached"] is False and [r["id"] for r in out["rooms"]] == [rid]
    assert len(e.pool.queries) == 2


def test_the_lobby_says_no_relay_answered_rather_than_a_zero_second_wait():
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "ui" / "70_lobby.js").read_text()
    assert "browse.unanswered && jsx(" in src and "browse.cached && !browse.unanswered" in src


async def test_a_join_nobody_answered_is_not_reported_as_not_found(bare):
    e, _ = bare()
    e.pool = QPool()
    out = await e.join_room("0123456789abcdef")
    assert out["found"] is not False                            # the relays weren't asked, so nothing was "not found"
    e.pool.answered = {"wss://a"}
    out = await e.join_room("fedcba9876543210")
    assert out["found"] is False                                # asked and answered with nothing: say so


async def test_a_join_right_after_start_finds_the_rooms_name(bare):
    e, _ = bare()
    rid, meta = room_meta(Key("host"), "Pop-up")
    async with LocalRelay(port=0) as relay:
        relay.events[meta["id"]] = meta
        e.pool = RelayPool([relay.url])
        e.pool.start()
        try:
            out = await e.join_room(rid)
            assert out["found"] is True and out["name"] == "Pop-up"
        finally:
            await e.pool.stop()


async def test_a_profile_opened_right_after_start_shows_the_card(bare):
    e, _ = bare()
    k = Key("carder")
    c = card(k, "makes synths")
    async with LocalRelay(port=0) as relay:
        relay.events[c["id"]] = c
        e.pool = RelayPool([relay.url])
        e.pool.start()
        try:
            assert (await e.profile(k.ppk)).get("line") == "makes synths"
        finally:
            await e.pool.stop()
