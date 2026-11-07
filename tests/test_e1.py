"""Chat polish, first half (Batch E1) on the engine side: older messages by cursor, the "sending" state, and
Retry / Discard for a message no relay took, in a room and in a private conversation."""
import json

import pytest

from ninsei_engine import engine as eng_mod
from test_engine import read, run, setup_room, wait_for, world  # noqa: F401  (fixture re-export)
from test_dm import exchange_setup

LONG = "x" * 1200          # a 1.7 KB frame: over the 1.5 KB the relay is told to accept below
SMALL, BIG = 1500, 128 * 1024
DMX, DMY = "x" * 2000, "y" * 2000   # the composer's longest private message: a wrap of about 6 KB


def shown(e, room):
    return {m["id"]: m for m in read(e, e.messages, room)}


async def test_the_room_snapshot_carries_120_and_older_ones_load_by_cursor(world):
    _, engines, _ = world
    room = await setup_room(engines)
    maya = engines["Maya"]
    ids = [(await run(maya, maya.post, room, f"line {i}"))["id"] for i in range(260)]
    snap = read(maya, maya.snapshot, room, False)["room"]
    assert len(snap["messages"]) == 120 and snap["earlier"] is True
    assert [m["id"] for m in snap["messages"] if m["t"] == "msg"][-1] == ids[-1]
    first = snap["messages"][0]["id"]
    page = read(maya, maya.messages_before, room, first)
    assert len(page["messages"]) == 100 and page["more"] is True
    again = read(maya, maya.messages_before, room, page["messages"][0]["id"])
    assert again["more"] is False and len(again["messages"]) <= 100
    # the pages and the snapshot join up with no gap and no repeat
    every = [m["id"] for m in again["messages"]] + [m["id"] for m in page["messages"]] + [m["id"] for m in snap["messages"]]
    assert len(every) == len(set(every)) and every == [m["id"] for m in read(maya, maya.messages, room, 10 ** 6)][-len(every):]
    # an id that isn't here, or garbage, is an empty page and never an error
    assert read(maya, maya.messages_before, room, "nope") == {"messages": [], "more": False}
    assert read(maya, maya.messages_before, room, ["x"]) == {"messages": [], "more": False}
    assert read(maya, maya.messages_before, room, first, "many")["messages"].__len__() == 100
    small = read(maya, maya.snapshot, room, False)["room"]
    assert small["earlier"] is True


async def test_a_short_room_has_nothing_earlier(world):
    _, engines, _ = world
    room = await setup_room(engines)
    maya = engines["Maya"]
    await run(maya, maya.post, room, "hi")
    assert read(maya, maya.snapshot, room, False)["room"]["earlier"] is False


async def test_a_message_no_relay_took_can_be_retried_once_and_discarded(world, monkeypatch):
    relay, engines, _ = world
    monkeypatch.setattr(eng_mod, "SENDING_SECONDS", 0)
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    relay.max_message_size = SMALL
    mid = (await run(maya, maya.post, room, LONG))["id"]
    assert await wait_for(lambda: shown(maya, room).get(mid, {}).get("delivery") == "failed")
    assert mid not in relay.events
    # still turned down: retrying keeps it failed, and never makes a second message
    await run(maya, maya.retry_post, room, mid)
    assert await wait_for(lambda: shown(maya, room)[mid].get("delivery") == "failed")
    # the relay takes it now: the same event arrives, once, and Sam sees one message
    relay.max_message_size = BIG
    await run(maya, maya.retry_post, room, mid)
    assert await wait_for(lambda: "delivery" not in shown(maya, room)[mid] and mid in relay.events)
    assert [m["id"] for m in read(maya, maya.messages, room) if m["text"] == LONG] == [mid]
    assert await wait_for(lambda: [m["id"] for m in read(sam, sam.messages, room) if m["text"] == LONG] == [mid])
    with pytest.raises(ValueError, match="delivered"):
        await run(maya, maya.retry_post, room, mid)
    with pytest.raises(ValueError, match="delivered"):
        await run(maya, maya.discard_post, room, mid)
    # a second one that fails is discarded: gone from the view and the outbox, and never sent
    relay.max_message_size = SMALL
    gone = (await run(maya, maya.post, room, LONG + "!"))["id"]
    assert await wait_for(lambda: shown(maya, room).get(gone, {}).get("delivery") == "failed")
    await run(maya, maya.discard_post, room, gone)
    assert gone not in shown(maya, room) and read(maya, maya.store.event_outbox_status, gone) is None
    relay.max_message_size = BIG
    after = (await run(maya, maya.post, room, "after"))["id"]               # sent and seen by Sam, so a resend would have shown
    assert await wait_for(lambda: after in shown(sam, room))
    assert gone not in relay.events and gone not in shown(sam, room)
    with pytest.raises(ValueError):
        await run(maya, maya.discard_post, room, gone)


async def test_retry_and_discard_refuse_what_is_not_mine(world, monkeypatch):
    relay, engines, _ = world
    monkeypatch.setattr(eng_mod, "SENDING_SECONDS", 0)
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    theirs = (await run(sam, sam.post, room, "from sam"))["id"]
    assert await wait_for(lambda: theirs in shown(maya, room))
    for fn in (maya.retry_post, maya.discard_post):
        for target in (theirs, "f" * 64, 5, None):
            with pytest.raises(ValueError):
                await run(maya, fn, room, target)
        with pytest.raises(ValueError):
            await run(maya, fn, "nope", theirs)


async def test_a_fresh_message_reads_sending_not_failed(world):
    relay, engines, _ = world
    room = await setup_room(engines)
    maya = engines["Maya"]
    relay.delay_ms = 600                                   # the relay is slow to say OK
    mid = (await run(maya, maya.post, room, "slow one"))["id"]
    assert await wait_for(lambda: shown(maya, room)[mid].get("delivery") == "sending")
    assert await wait_for(lambda: "delivery" not in shown(maya, room)[mid])


async def test_a_private_message_no_relay_took_can_be_retried_and_discarded(world, monkeypatch):
    relay, engines, _ = world
    monkeypatch.setattr(eng_mod, "SENDING_SECONDS", 0)
    await exchange_setup(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    maya_pk, sam_pk = maya._identity()["person_pk"], sam._identity()["person_pk"]

    def thread(e, pk):
        return {m["id"]: m for m in read(e, e.dm_thread, pk, False)["messages"]}

    relay.max_message_size = 3000
    mid = (await run(maya, maya.dm_send, sam_pk, DMX))["id"]
    assert await wait_for(lambda: thread(maya, sam_pk).get(mid, {}).get("delivery") == "failed")
    await run(maya, maya.dm_retry, sam_pk, mid)
    assert await wait_for(lambda: thread(maya, sam_pk)[mid].get("delivery") == "failed")
    relay.max_message_size = BIG
    await run(maya, maya.dm_retry, sam_pk, mid)
    assert await wait_for(lambda: "delivery" not in thread(maya, sam_pk)[mid])
    assert await wait_for(lambda: [m["text"] for m in thread(sam, maya_pk).values()] == [DMX])
    assert list(thread(maya, sam_pk)) == [mid]
    for fn in (maya.dm_retry, maya.dm_discard):
        with pytest.raises(ValueError, match="delivered"):
            await run(maya, fn, sam_pk, mid)
    relay.max_message_size = 3000
    gone = (await run(maya, maya.dm_send, sam_pk, DMY))["id"]
    assert await wait_for(lambda: thread(maya, sam_pk).get(gone, {}).get("delivery") == "failed")
    await run(maya, maya.dm_discard, sam_pk, gone)
    assert gone not in thread(maya, sam_pk)
    # not someone else's message, not another conversation's, not a made-up id
    theirs = (await run(sam, sam.dm_send, maya_pk, "hi"))["id"]
    assert await wait_for(lambda: theirs in thread(maya, sam_pk))
    for fn in (maya.dm_retry, maya.dm_discard):
        for pk, target in ((sam_pk, theirs), (maya_pk, mid), (sam_pk, "z" * 64), (sam_pk, None)):
            with pytest.raises(ValueError):
                await run(maya, fn, pk, target)


async def test_older_private_messages_load_by_cursor(world):
    _, engines, _ = world
    maya = engines["Maya"]
    peer = "e" * 64
    me = maya._identity()["person_pk"]
    st = maya.store
    for i in range(450):
        st.dm_add(id=f"{i:064x}", peer=peer, sender=peer if i % 2 else me, text=f"m{i}", created_at=1000 + i, arrived_at=float(i))
    first = read(maya, maya.dm_thread, peer, False)
    assert len(first["messages"]) == 200 and first["earlier"] is True and first["messages"][-1]["text"] == "m449"
    p1 = read(maya, maya.dm_thread, peer, False, first["messages"][0]["id"])
    assert len(p1["messages"]) == 100 and p1["earlier"] is True and p1["messages"][-1]["text"] == "m249"
    p2 = read(maya, maya.dm_thread, peer, False, p1["messages"][0]["id"])
    assert len(p2["messages"]) == 100 and p2["earlier"] is True
    p3 = read(maya, maya.dm_thread, peer, False, p2["messages"][0]["id"])
    assert len(p3["messages"]) == 50 and p3["earlier"] is False and p3["messages"][0]["text"] == "m0"
    assert read(maya, maya.dm_thread, peer, False, "q" * 64)["messages"] == []
    assert read(maya, maya.dm_thread, peer, False, p3["messages"][0]["id"])["earlier"] is False
