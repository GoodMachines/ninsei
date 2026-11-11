"""Private rooms: invite-only rooms whose events are encrypted with a key only the members hold
(docs/private-rooms-design.md).

The rules under test: nobody without the key can read a private room or post into it; the room is never listed; the
only way in is a friend's invite, which carries the key inside the gift wrap; a key from an invite is a candidate
until the creator's own metadata opens with it; an older Ninsei drops the invite instead of opening a room it cannot
read; the limits on room events apply to the decrypted text."""
import asyncio
import json

import pytest

from ninsei_engine import dm, nip44, nostr
from ninsei_engine.engine import (KIND_LIVE, KIND_META, KIND_ROOM, PRIVATE_CIPHER_MAX, ROOM_KEYS_KV, Engine,
                                  room_conv_key)
from test_dm import exchange_setup
from test_engine import StubLLM, read, run, wait_for, world  # noqa: F401  (fixture re-export)
from test_hostile import Key

OTHER = "0123456789abcdef"
KEY = "ab" * 32


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    from ninsei_engine import engine as eng_mod

    async def fake(host, port):
        return ["93.184.216.34"]
    monkeypatch.setattr(eng_mod, "_resolve", fake)


def texts(e, room):
    return [m.get("text") for m in read(e, lambda: e.messages_view(room)[0]) if m.get("t") == "msg"]


def on_relay(relay, room):
    return [e for e in relay.events.values()
            if room in nostr.tag_values(e, "h") or f"ninsei/room/{room}" in nostr.tag_values(e, "d")]


async def private_room(engines, name="secret garden"):
    """Maya and Sam are friends; Maya makes a private room, says one thing and invites Sam, who joins."""
    maya, sam = engines["Maya"], engines["Sam"]
    await exchange_setup(engines)
    room = (await run(maya, maya.create_room, name, "where we plan", ["shaders"], True))["id"]
    await run(maya, maya.post, room, "the plan is tacos")
    await run(maya, maya.room_invite, room, [sam._identity()["person_pk"]])
    assert await wait_for(lambda: any(i["room"] == room for i in read(sam, sam.dm_summary)["invites"]))
    return room


# ---- the invite on the wire --------------------------------------------------------------------------------------

def test_a_private_invite_has_its_own_mark_and_carries_exactly_one_key():
    a, b = Key("a"), Key("b")
    rumor = dm.make_invite_rumor(a.ppk, b.ppk, OTHER, ["wss://nos.lol"], key=KEY)
    assert ["ninsei", "private_invite"] in rumor["tags"] and ["key", KEY] in rumor["tags"] and rumor["content"] == ""
    # an older Ninsei accepts only the marks it knows, so this one is "unsupported" there and nothing opens
    assert ["ninsei", dm.ROOM_INVITE] not in rumor["tags"]
    verdict, msg = dm.unwrap(b.psk, b.ppk, dm.wrap_for(a.psk, b.ppk, rumor))
    assert verdict == dm.OK and msg["type"] == dm.ROOM_INVITE and msg["key"] == KEY and msg["room"] == OTHER
    assert msg["text"] == ""
    with pytest.raises(ValueError):
        dm.make_invite_rumor(a.ppk, b.ppk, OTHER, [], key="not a key")


@pytest.mark.parametrize("keys", [[], [["key", "AB" * 32]], [["key", "ab" * 31]], [["key", KEY], ["key", KEY]],
                                  [["key", KEY, "extra"]], [["key", 7]]])
def test_a_private_invite_with_a_missing_or_malformed_key_is_garbage(keys):
    a, b = Key("a"), Key("b")
    rumor = dm.make_invite_rumor(a.ppk, b.ppk, OTHER, ["wss://nos.lol"], key=KEY)
    rumor["tags"] = [t for t in rumor["tags"] if t[0] != "key"] + keys
    rumor["id"] = nostr.event_id(rumor)
    assert dm.unwrap(b.psk, b.ppk, dm.wrap_for(a.psk, b.ppk, rumor)) == (dm.GARBAGE, None)


def test_a_key_tag_on_a_plain_invite_is_ignored():
    a, b = Key("a"), Key("b")
    rumor = dm.make_invite_rumor(a.ppk, b.ppk, OTHER, ["wss://nos.lol"])
    rumor["tags"].append(["key", KEY])
    rumor["id"] = nostr.event_id(rumor)
    verdict, msg = dm.unwrap(b.psk, b.ppk, dm.wrap_for(a.psk, b.ppk, rumor))
    assert verdict == dm.OK and "key" not in msg


def test_a_room_key_is_bound_to_its_room():
    assert room_conv_key(KEY, OTHER) != room_conv_key(KEY, "fedcba9876543210")
    assert len(room_conv_key(KEY, OTHER)) == 32


# ---- two installs ------------------------------------------------------------------------------------------------

async def test_a_private_room_is_readable_by_its_members_and_by_nobody_else(world):
    relay, engines, llms = world
    maya, sam = engines["Maya"], engines["Sam"]
    room = await private_room(engines)
    key = read(maya, lambda: maya._rkeys[room])

    # what the relay holds: nothing readable. No name, no words, no key, no Lobby tag.
    held = on_relay(relay, room)
    assert {e["kind"] for e in held} >= {KIND_META, KIND_ROOM}
    blob = json.dumps(list(relay.events.values()))
    assert "tacos" not in blob and "secret garden" not in blob and "where we plan" not in blob and key not in blob
    [meta] = [e for e in held if e["kind"] == KIND_META]
    assert nostr.tag_values(meta, "t") == [] and not meta["content"].startswith("{")
    for e in held:
        with pytest.raises(ValueError):
            json.loads(e["content"])

    # Sam's invite says it is private and shows the name the creator gave it, read with the invite's key
    assert await wait_for(lambda: read(sam, sam.dm_summary)["invites"][0]["room_name"] == "secret garden")
    [inv] = read(sam, sam.dm_summary)["invites"]
    assert inv["private"] is True
    assert read(sam, lambda: sam.is_private(room)) is False         # a candidate key only: he hasn't joined
    # a key nothing has proven says nothing: the same invite reads "not private" until the metadata opened with it
    read(sam, lambda: sam._proven.clear())
    assert read(sam, sam.dm_summary)["invites"][0]["private"] is False
    read(sam, lambda: sam._proven.setdefault(room, None))

    # he joins by the invite and reads what was said before he came; both ways work from here
    out = await run(sam, sam.join_room, room)
    assert out["found"] and out["private"] is True and out["name"] == "secret garden"
    assert read(sam, lambda: sam.is_private(room)) and read(sam, lambda: sam._rkeys[room]) == key
    assert await wait_for(lambda: "the plan is tacos" in texts(sam, room))
    await run(sam, sam.post, room, "I'll bring salsa")
    assert await wait_for(lambda: "I'll bring salsa" in texts(maya, room))
    assert "salsa" not in json.dumps(list(relay.events.values()))

    # both people and both agents are there: agents are in by default and their beats are encrypted too
    assert await wait_for(lambda: len(read(maya, maya.members, room)) == 2
                          and all(p["agents"] for p in read(maya, maya.members, room)))
    beats = [e for e in on_relay(relay, room) if e["kind"] == KIND_LIVE]
    for e in beats:
        with pytest.raises(ValueError):
            json.loads(e["content"])

    # the room view: marked private, and no code or link to hand around
    snap = read(sam, sam.snapshot, room, False)
    assert snap["room"]["private"] is True and snap["room"]["code"] == "" and snap["room"]["invite_link"] == ""
    assert [r["private"] for r in snap["rooms"] if r["id"] == room] == [True]


async def test_someone_without_the_key_sees_nothing_and_cannot_post(world, tmp_path):
    relay, engines, _ = world
    maya, sam = engines["Maya"], engines["Sam"]
    room = await private_room(engines)
    await run(sam, sam.join_room, room)
    eve = Engine(tmp_path / "Eve", lambda: StubLLM("Imp"), relays=[relay.url], lock=False, timescale=0.05)
    eve.save_settings({"display_name": "Eve", "agent_name": "Imp", "interests": ["shaders"], "onboarded": True,
                       "chattiness": "quiet"})
    eve.start()
    try:
        assert await asyncio.wrap_future(eve.call(eve.pool.wait_open, 30))
        # the Lobby and "Browse all" never list it, and a preview by id finds no room
        assert room not in [r["id"] for r in (await run(eve, eve.browse_rooms))["rooms"]]
        assert room not in [r["id"] for r in (await run(eve, eve.refresh_lobby))["rooms"]]
        pre = await run(eve, eve.room_preview, f"ninsei:{room}")
        assert pre["found"] is False and pre["msgs"] == 0 and "secret" not in pre["name"]
        # she knows the id anyway (it is on every event) and joins by it: an empty room with no name
        await run(eve, eve.join_room, room)
        assert read(eve, lambda: eve.is_private(room)) is False
        assert texts(eve, room) == [] and "secret" not in read(eve, eve.room_name, room)
        # what she posts is plain text under the room's tag: the members' clients drop it
        before = (len(read(maya, lambda: maya.events[room])), len(read(sam, lambda: sam.events[room])))
        await run(eve, eve.post, room, "let me in")
        assert await wait_for(lambda: any("let me in" in e["content"] for e in on_relay(relay, room)))
        [hers] = [e for e in on_relay(relay, room) if "let me in" in e["content"]]
        await run(maya, maya._on_event, hers, "test")       # handed over directly too, so nothing rests on timing
        await run(sam, sam._on_event, hers, "test")
        assert "let me in" not in texts(maya, room) and "let me in" not in texts(sam, room)
        assert (len(read(maya, lambda: maya.events[room])), len(read(sam, lambda: sam.events[room]))) == before
        assert all(p["name"] != "Eve" for p in read(maya, maya.members, room))
    finally:
        await asyncio.to_thread(eve.stop)


async def test_a_rename_reaches_members_and_stays_encrypted(world):
    relay, engines, _ = world
    maya, sam = engines["Maya"], engines["Sam"]
    room = await private_room(engines)
    await run(sam, sam.join_room, room)
    await run(maya, maya.edit_room, room, "taco tuesday", "new plan")
    assert await wait_for(lambda: read(sam, sam.room_name, room) == "taco tuesday")
    assert read(sam, sam.room_meta, room).get("private") is True
    assert "taco tuesday" not in json.dumps(list(relay.events.values()))
    with pytest.raises(Exception):
        await run(sam, sam.edit_room, room, "mine now", "")           # still only the creator


async def test_reactions_and_edits_fit_their_limits_on_the_decrypted_text(world):
    _, engines, _ = world
    maya, sam = engines["Maya"], engines["Sam"]
    room = await private_room(engines)
    await run(sam, sam.join_room, room)
    assert await wait_for(lambda: "the plan is tacos" in texts(sam, room))
    target = next(m["id"] for m in read(sam, lambda: sam.messages_view(room)[0]) if m.get("text") == "the plan is tacos")
    await run(sam, sam.react, room, target, "👍")
    assert await wait_for(lambda: any(m["id"] == target and m.get("reactions")
                                      for m in read(maya, lambda: maya.messages_view(room)[0])))


async def test_leaving_keeps_the_key_as_a_spare_and_rejoin_proves_it_again(world):
    _, engines, _ = world
    maya, sam = engines["Maya"], engines["Sam"]
    room = await private_room(engines)
    await run(sam, sam.join_room, room)
    key = read(sam, lambda: sam._rkeys[room])
    await run(sam, sam.leave_room, room)
    assert read(sam, lambda: sam.is_private(room)) is False and read(sam, lambda: sam._spare[room]) == [key]
    assert read(sam, lambda: sam.store.get(ROOM_KEYS_KV)) == {}
    [left] = [r for r in read(sam, sam.left_rooms) if r["id"] == room]
    await run(sam, sam.join_room, left["code"])
    assert read(sam, lambda: sam._rkeys[room]) == key
    assert await wait_for(lambda: "the plan is tacos" in texts(sam, room))


async def test_the_key_survives_a_restart(world, tmp_path):
    _, engines, _ = world
    maya = engines["Maya"]
    room = (await run(maya, maya.create_room, "kept", "", [], True))["id"]
    key = read(maya, lambda: maya._rkeys[room])
    again = Engine(maya.data_dir, lambda: StubLLM("Ada"), relays=[], lock=False)   # the same data, never started
    assert again._rkeys == {room: key} and again.is_private(room)


# ---- a key from an invite proves nothing by itself ---------------------------------------------------------------

async def test_a_made_up_key_for_a_public_room_changes_nothing(world):
    _, engines, _ = world
    maya, sam = engines["Maya"], engines["Sam"]
    await exchange_setup(engines)
    room = (await run(maya, maya.create_room, "open house", "", ["shaders"]))["id"]
    await run(maya, maya.post, room, "everyone welcome")
    # a friend's private invite to a public room, with a key they made up
    rumor = dm.make_invite_rumor(maya._identity()["person_pk"], sam._identity()["person_pk"], room, [], key=KEY)
    wrap = dm.wrap_for(maya._identity()["person_sk"], sam._identity()["person_pk"], rumor)
    assert await run(sam, sam._dm_process, wrap) == dm.OK
    assert read(sam, lambda: sam._spare.get(room)) == [KEY]
    # the invite is never labelled private: nothing has proven the key, and the name lookup finds a public room
    assert await wait_for(lambda: read(sam, sam.dm_summary)["invites"][0]["room_name"] == "open house")
    [inv] = read(sam, sam.dm_summary)["invites"]
    assert inv["private"] is False
    pre = await run(sam, sam.room_preview, f"ninsei:{room}")
    assert pre["found"] and pre["private"] is False
    out = await run(sam, sam.join_room, room)
    assert out["found"] and not out.get("private") and read(sam, lambda: sam.is_private(room)) is False
    assert read(sam, lambda: sam._spare.get(room)) is None                 # the made-up key is forgotten
    assert await wait_for(lambda: "everyone welcome" in texts(sam, room))
    await run(sam, sam.post, room, "hi all")
    assert await wait_for(lambda: "hi all" in texts(maya, room))        # he posted plain text, not ciphertext


async def test_a_key_for_a_room_i_am_already_in_is_never_kept(world):
    _, engines, _ = world
    maya, sam = engines["Maya"], engines["Sam"]
    shared = await exchange_setup(engines)
    room = shared if isinstance(shared, str) else next(iter(read(sam, sam.store.rooms)))
    rumor = dm.make_invite_rumor(maya._identity()["person_pk"], sam._identity()["person_pk"], room, [], key=KEY)
    wrap = dm.wrap_for(maya._identity()["person_sk"], sam._identity()["person_pk"], rumor)
    await run(sam, sam._dm_process, wrap)
    assert read(sam, lambda: sam._spare.get(room)) is None and read(sam, lambda: sam.is_private(room)) is False


async def test_a_private_room_whose_metadata_cannot_be_found_is_not_joined_blind(world):
    _, engines, _ = world
    sam = engines["Sam"]
    read(sam, lambda: sam._learn_key(OTHER, KEY))
    with pytest.raises(Exception, match="private room"):
        await run(sam, sam.join_room, OTHER)
    assert OTHER not in read(sam, sam.store.rooms)


async def test_a_private_event_that_is_too_big_to_try_is_dropped_before_any_decryption(world, monkeypatch):
    _, engines, _ = world
    maya = engines["Maya"]
    room = (await run(maya, maya.create_room, "caps", "", [], True))["id"]
    calls = []
    real = nip44.decrypt
    monkeypatch.setattr(nip44, "decrypt", lambda *a: calls.append(1) or real(*a))
    big = nostr.build_event(Key("x").psk, KIND_ROOM, "A" * (PRIVATE_CIPHER_MAX + 1), [["h", room]])
    n = len(read(maya, lambda: maya.events[room]))
    await run(maya, maya._on_event, big, "test")
    assert calls == [] and len(read(maya, lambda: maya.events[room])) == n
