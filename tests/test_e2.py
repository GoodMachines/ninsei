"""Chat polish, second half (Batch E2) on the engine side: mute and per-room agent chattiness, renaming a room (only
its creator, with proof of work), message links, and the relay retry time the "Reconnecting" banner counts down."""
import json

import pytest

from ninsei_engine import engine as eng_mod
from ninsei_engine import nostr
from ninsei_engine.engine import Engine, KIND_META, parse_room_link, room_id_for
from test_engine import StubLLM, quiet, read, run, setup_room, wait_for, world  # noqa: F401  (fixture re-export)
from test_hostile import bare, ROOM  # noqa: F401  (fixture re-export)


def room_entry(e, room):
    return next(r for r in read(e, e.snapshot)["rooms"] if r["id"] == room)


# ---- mute and chattiness per room -------------------------------------------------------------------------------

async def test_mute_and_chattiness_are_per_room_remembered_and_forgotten_on_leaving(world):
    _, engines, _ = world
    room = await setup_room(engines)
    maya = engines["Maya"]
    other = (await run(maya, maya.create_room, "second", "", []))["id"]
    assert (room_entry(maya, room)["muted"], room_entry(maya, room)["chattiness"]) == (False, "")
    out = read(maya, maya.set_room_pref, room, True, "lively")
    assert out == {"room": room, "muted": True, "chattiness": "lively"}
    assert (room_entry(maya, room)["muted"], room_entry(maya, room)["chattiness"]) == (True, "lively")
    assert (room_entry(maya, other)["muted"], room_entry(maya, other)["chattiness"]) == (False, "")   # the other room is untouched
    # a settings save (the Settings page) keeps them
    maya.save_settings({"chattiness": "normal", "display_name": "Maya"})
    assert room_entry(maya, room)["muted"] is True
    # each can be taken back on its own: "" follows Settings again
    read(maya, maya.set_room_pref, room, None, "")
    assert (room_entry(maya, room)["muted"], room_entry(maya, room)["chattiness"]) == (True, "")
    read(maya, maya.set_room_pref, room, False, None)
    assert maya.settings()["room_prefs"] == {}
    read(maya, maya.set_room_pref, other, True, None)
    await run(maya, maya.leave_room, other)
    assert maya.settings()["room_prefs"] == {}                       # leaving forgets the room's setting


async def test_room_prefs_refuse_rooms_you_are_not_in_and_unknown_levels(world):
    _, engines, _ = world
    room = await setup_room(engines)
    maya = engines["Maya"]
    with pytest.raises(ValueError):
        read(maya, maya.set_room_pref, "f" * 16, True, None)
    with pytest.raises(ValueError):
        read(maya, maya.set_room_pref, room, None, "shouty")
    assert maya.settings()["room_prefs"] == {}


def test_stored_room_prefs_are_cleaned_whatever_they_hold():
    clean = eng_mod._clean_room_prefs
    assert clean(None) == {} and clean([1]) == {} and clean("x") == {}
    junk = {"a": {"muted": "yes", "chattiness": "wild"}, "b": "x", "c": {"muted": True}, 5: {"muted": True},
            "d": {"chattiness": "quiet", "extra": 1}}
    assert clean(junk) == {"c": {"muted": True}, "d": {"chattiness": "quiet"}}
    many = {f"r{i}": {"muted": True} for i in range(eng_mod.MAX_ROOM_PREFS + 50)}
    assert len(clean(many)) == eng_mod.MAX_ROOM_PREFS


async def test_a_rooms_own_chattiness_beats_the_global_one_in_both_directions(world, monkeypatch):
    _, engines, llms = world
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    monkeypatch.setattr(eng_mod.random, "random", lambda: 0.0)       # every chatty roll fires, so only the level decides
    assert await wait_for(lambda: read(maya, maya._others_here, room))
    # global quiet (the fixture's) says nothing; the room's lively override joins in
    assert read(maya, maya.room_chattiness, room) == "quiet"
    read(maya, maya.set_room_pref, room, None, "lively")
    assert read(maya, maya.room_chattiness, room) == "lively"
    await run(sam, sam.post, room, "just thinking out loud here")
    assert await wait_for(lambda: llms["Maya"].calls.count("ninsei.reply") == 1)
    await quiet(maya, sam)
    # global lively, but this room quiet: nothing, even though the roll would fire
    maya.save_settings({"chattiness": "lively"})
    read(maya, maya.set_room_pref, room, None, "quiet")
    assert read(maya, maya.room_chattiness, room) == "quiet"
    calls = llms["Maya"].calls.count("ninsei.reply")
    assert await wait_for(lambda: read(maya, maya._can_post, room))
    await run(sam, sam.post, room, "another idle thought")
    await quiet(maya, sam)
    assert llms["Maya"].calls.count("ninsei.reply") == calls
    # and an owner's own question is only answered when the room is not quiet
    await run(maya, maya.post, room, "does anybody know a good palette tool?")
    await quiet(maya, sam)
    assert llms["Maya"].calls.count("ninsei.reply") == calls


# ---- message links ------------------------------------------------------------------------------------------------

def test_a_room_link_reads_as_a_room_and_an_optional_message():
    room, ev = "203f22bcfd1b4b2f", "a" * 64
    assert parse_room_link(f"ninsei:{room}") == (room, "")
    assert parse_room_link(f"ninsei:{room}#{ev}") == (room, ev)
    assert parse_room_link(f"  NINSEI:{room.upper()}#{ev.upper()} ") == (room, ev)
    assert parse_room_link(room) == (room, "")
    assert parse_room_link(f"ninsei:{room}#nothex") == (room, "")
    assert parse_room_link(f"ninsei:{room}#{'a' * 63}") == (room, "")
    assert parse_room_link(None) == ("", "") and parse_room_link("zzz # nothing") == ("", "")
    assert parse_room_link("x" * 10_000)[0] == ""                    # bounded, never an error


async def test_joining_by_a_message_link_joins_the_room_and_keeps_its_id_intact(world):
    _, engines, _ = world
    maya, sam = engines["Maya"], engines["Sam"]
    meta = await run(maya, maya.create_room, "linked", "", [])
    mid = (await run(maya, maya.post, meta["id"], "look here"))["id"]
    joined = await run(sam, sam.join_room, f"ninsei:{meta['id']}#{mid}")
    assert joined["id"] == meta["id"]
    assert any(r["id"] == meta["id"] for r in read(sam, sam.snapshot)["rooms"])
    assert await wait_for(lambda: any(m["id"] == mid for m in read(sam, sam.messages, meta["id"])))


# ---- rename and describe ------------------------------------------------------------------------------------------

async def test_only_the_creator_renames_and_everyone_sees_it_with_proof_of_work(world):
    relay, engines, _ = world
    room = await setup_room(engines)          # Maya created it
    maya, sam = engines["Maya"], engines["Sam"]
    assert room_entry(maya, room)["mine"] is True and room_entry(sam, room)["mine"] is False
    with pytest.raises(ValueError, match="only the person who made this room"):
        await run(sam, sam.edit_room, room, "Sam's room", "mine now")
    out = await run(maya, maya.edit_room, room, "  shader  club  2 ", "all about glow")
    assert out["name"] == "shader  club  2" and out["about"] == "all about glow"
    assert await wait_for(lambda: room_entry(sam, room)["name"] == "shader  club  2")
    assert read(sam, sam.room_meta, room)["about"] == "all about glow"
    assert room_entry(maya, room)["name"] == "shader  club  2"
    # what went out: the same replaceable slot, signed by the creator's key, with at least 12 bits of work, the nonce kept
    mine = [e for e in relay.events.values() if e["kind"] == KIND_META and ["d", f"ninsei/room/{room}"] in e["tags"]]
    newest = max(mine, key=lambda e: e["created_at"])
    assert newest["pubkey"] == read(maya, maya._identity)["person_pk"]
    assert nostr.leading_zero_bits(newest["id"]) >= 12
    body = json.loads(newest["content"])
    assert body["name"] == "shader  club  2" and room_id_for(newest["pubkey"], body["nonce"]) == room
    assert room_entry(maya, room)["name"] == "shader  club  2"      # a later poll of the relay doesn't undo it
    # and a second rename is newer again, even inside the same second
    await run(maya, maya.edit_room, room, "third name", "")
    assert await wait_for(lambda: room_entry(sam, room)["name"] == "third name")


async def test_a_rename_needs_a_name_and_a_joined_room_and_is_paced(world):
    _, engines, _ = world
    room = await setup_room(engines)
    maya = engines["Maya"]
    with pytest.raises(ValueError):
        await run(maya, maya.edit_room, room, "   ", "x")
    with pytest.raises(ValueError):
        await run(maya, maya.edit_room, "f" * 16, "x", "")
    with pytest.raises(ValueError):
        await run(maya, maya.edit_room, room, "​‮", "")      # only invisible characters is no name
    for _ in range(eng_mod.CLICKS_PER_MIN):
        await run(maya, maya.edit_room, room, "club", "d")
    with pytest.raises(ValueError, match="Slow down"):
        await run(maya, maya.edit_room, room, "club again", "d")


async def test_a_room_saved_without_its_nonce_finds_it_on_the_relays_to_rename(world):
    _, engines, _ = world
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    meta = dict(read(maya, maya.room_meta, room))
    meta.pop("nonce", None)
    maya.store.save_room(room, meta)                                   # an install from before the nonce was kept
    assert "nonce" not in read(maya, maya.room_meta, room)
    await run(maya, maya.edit_room, room, "found it", "")
    assert await wait_for(lambda: room_entry(sam, room)["name"] == "found it")


async def test_metadata_signed_by_someone_else_is_still_ignored_and_a_junk_nonce_is_harmless(bare):
    e, _ = bare()
    other = nostr.new_secret()
    meta = {"id": ROOM, "nonce": ["not", "a", "string"], "name": "hijack", "about": "x" * 5000}
    ev = nostr.build_event(other, KIND_META, json.dumps(meta), [["d", f"ninsei/room/{ROOM}"]], pow_bits=0, created_at=2_000_000_000)
    await e._on_event(ev, "live")
    assert e.room_meta(ROOM)["name"] == "test room"
    with pytest.raises(ValueError, match="only the person who made this room"):
        await e.edit_room(ROOM, "mine", "")


# ---- reconnecting -------------------------------------------------------------------------------------------------

async def test_the_snapshot_says_when_each_down_relay_tries_again(tmp_path):
    e = Engine(tmp_path / "x", lambda: StubLLM("Ada"), relays=["ws://127.0.0.1:1"], lock=False, timescale=0.05)
    e.save_settings({"display_name": "Maya", "agent_name": "Ada", "onboarded": True})
    e.start()
    try:
        def down():
            rs = read(e, e.snapshot)["relays"]
            return rs and rs[0]["state"] == "backoff" and rs[0]["retry_s"] >= 1
        assert await wait_for(down)
        rs = read(e, e.snapshot)["relays"][0]
        assert 1 <= rs["retry_s"] <= 3 and rs["error"]
    finally:
        import asyncio
        await asyncio.to_thread(e.stop)
