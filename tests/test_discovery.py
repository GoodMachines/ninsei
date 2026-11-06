"""Finding people on day one: Commons, the Lobby's "active now" order, and hiding someone."""
import asyncio
import json

from ninsei_engine import engine as eng_mod
from ninsei_engine import nostr
from ninsei_engine.engine import COMMONS_EVENT, COMMONS_ID, Engine, KIND_META, room_id_for

from test_engine import StubLLM, quiet, read, run, setup_room, wait_for, world  # noqa: F401  (fixture)


def test_bundled_commons_is_signed_by_its_creator():
    assert COMMONS_EVENT and COMMONS_ID
    assert nostr.check_event(COMMONS_EVENT)
    c = json.loads(COMMONS_EVENT["content"])
    assert room_id_for(COMMONS_EVENT["pubkey"], c["nonce"]) == COMMONS_ID
    assert nostr.leading_zero_bits(COMMONS_EVENT["id"]) >= 12  # the Lobby's spam guard would drop it otherwise


def test_a_tampered_commons_file_is_ignored(tmp_path):
    f = tmp_path / "commons.json"
    f.write_text(json.dumps(dict(COMMONS_EVENT, content=COMMONS_EVENT["content"].replace("Commons", "Pwned"))))
    assert eng_mod._load_commons(f) == (None, "")
    f.write_text("{not json")
    assert eng_mod._load_commons(f) == (None, "")


async def test_setup_joins_commons_once_and_leaving_sticks(world):
    _, engines, _ = world
    maya = engines["Maya"]
    # the fixture onboards before start, so boot already joined it
    assert await wait_for(lambda: COMMONS_ID in read(maya, maya.store.rooms))
    assert read(maya, maya.store.rooms)[COMMONS_ID]["name"] == "Commons"
    await run(maya, maya.leave_room, COMMONS_ID)
    await run(maya, maya.ensure_commons)
    assert COMMONS_ID not in read(maya, maya.store.rooms)


async def test_not_onboarded_means_no_commons_yet(tmp_path):
    from local_relay import LocalRelay
    async with LocalRelay(port=0) as relay:
        e = Engine(tmp_path / "new", lambda: StubLLM("X"), relays=[relay.url], lock=False, timescale=0.05)
        e.start()
        try:
            await run(e, e.ensure_commons)
            assert COMMONS_ID not in read(e, e.store.rooms)
            e.save_settings({"display_name": "Kim", "agent_name": "Kit", "onboarded": True})
            await run(e, e.ensure_commons)
            assert COMMONS_ID in read(e, e.store.rooms)
        finally:
            await asyncio.to_thread(e.stop)


async def test_lobby_lists_commons_and_puts_active_rooms_first(world):
    _, engines, _ = world
    maya, sam = engines["Maya"], engines["Sam"]
    # a perfect interest match that nobody talks in, and a room off Sam's interests where people are talking
    await run(maya, maya.create_room, "quiet match", "", ["shaders", "synths"])
    busy = await run(maya, maya.create_room, "busy room", "", ["birding"])
    await run(maya, maya.post, busy["id"], "anyone seen a heron today?")
    lobby = await run(sam, sam.refresh_lobby)
    names = [r["name"] for r in lobby["rooms"]]
    assert "Commons" in names
    b = next(r for r in lobby["rooms"] if r["name"] == "busy room")
    assert b["live"] and b["msgs"] >= 1 and b["talkers"] == 1
    assert names.index("busy room") < names.index("quiet match")


async def test_hiding_someone_removes_them_and_their_agent_and_unhide_brings_them_back(world):
    _, engines, llms = world
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    sam_pk = sam._identity()["person_pk"]
    await run(sam, sam.post, room, "hello from sam")
    assert await wait_for(lambda: any(m["text"] == "hello from sam" for m in read(maya, maya.messages, room)))

    await run(maya, maya.hide_person, sam_pk, "Sam")
    assert not any(m["text"] == "hello from sam" for m in read(maya, maya.messages, room))
    assert all(p["pk"] != sam_pk for p in read(maya, maya.members, room))
    assert [h["name"] for h in read(maya, maya.hidden_people)] == ["Sam"]

    # while hidden: Sam addressing Ada gets no reply and costs Maya nothing
    before = len(llms["Maya"].calls)
    sent = await run(sam, sam.post, room, "Ada, are you there?")
    # Maya's pool marks an event seen just before handing it to the engine, and the hidden check returns
    # without yielding, so once the id is seen the engine has already refused it. Then nothing may be running.
    assert await wait_for(lambda: read(maya, lambda: sent["id"] in maya.pool._seen))
    await quiet(maya)
    assert len(llms["Maya"].calls) == before
    assert not any("are you there" in m["text"] for m in read(maya, maya.messages, room))

    await run(maya, maya.unhide_person, sam_pk)
    assert await wait_for(lambda: any(m["text"] == "hello from sam" for m in read(maya, maya.messages, room)))


async def test_you_cannot_hide_yourself_or_a_garbage_key(world):
    _, engines, _ = world
    maya = engines["Maya"]
    for pk in (maya._identity()["person_pk"], "not-a-key"):
        try:
            await run(maya, maya.hide_person, pk, "x")
        except ValueError:
            continue
        raise AssertionError("hide_person accepted " + pk)
