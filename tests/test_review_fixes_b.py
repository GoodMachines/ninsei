"""Regression tests for the room, mention, picture, typing and game review findings (review-room.md,
review-art.md and the live walkthrough). Each one failed before its fix."""
import json
import time

import pytest

from ninsei_engine import avatar, nostr
from ninsei_engine import engine as eng
from ninsei_engine.engine import KIND_LIVE, KIND_ROOM, parse_room_link
from test_audit_ui import CORE, fn, needs_node, run as run_js
from test_avatar import jpeg, png, riff, uri, vp8, vp8l, vp8x, wchunk
from test_engine import Result, StubLLM, Usage, read, run, setup_room, wait_for, world, quiet  # noqa: F401  (fixture)
from test_hostile import FakePool, Key, ROOM, bare, own_person_event, settle  # noqa: F401  (fixture)
from test_pictures import ArtPool, art, meet, PNG

ROOM2 = "bbbbbbbbbbbbbbbb"


class PendPool(FakePool):
    """A pool whose sends have not reached a relay: delivery is what a test says, discards are recorded."""

    def __init__(self):
        super().__init__()
        self.state = {}
        self.discarded = []

    async def publish(self, ev, wait=4.0):
        self.sent.append(ev)
        self.state[ev["id"]] = "pending"
        return {}

    def delivery(self, event_id):
        return self.state.get(event_id, "sent")

    def discard(self, event_id):
        if self.state.get(event_id, "sent") == "sent":
            return False
        self.state.pop(event_id, None)
        self.discarded.append(event_id)
        return True


def presence(pk_owner, name, at=None):
    return {"state": "activity: idle", "budget": None, "at": at or time.time(), "owner": pk_owner, "name": name,
            "face": None, "build": None, "vibe": "", "model": ""}


# ---- 1 and 2: who a message names -------------------------------------------------------------------------------

async def test_a_common_word_agent_name_does_not_take_the_floor_on_my_messages(world):
    _, engines, llms = world
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    maya.save_settings({"chattiness": "normal"})
    sam_agent = read(sam, sam._identity)["agent_pk"]
    assert await wait_for(lambda: sam_agent in read(maya, lambda: dict(maya.presence.get(room, {}))))

    def rename():
        maya.presence[room][sam_agent]["name"] = "the"   # what Sam's next presence beat would carry
    read(maya, rename)
    out = await run(maya, maya.post, room, "what is the plan?")
    ev = read(maya, lambda: maya.events[room][out["id"]])
    assert json.loads(ev["content"])["mentions"] == []
    assert await wait_for(lambda: any(m["role"] == "agent" and m["t"] == "msg" for m in read(maya, maya.messages, room)))
    await quiet(maya, sam)
    assert llms["Sam"].calls.count("ninsei.reply") == 0 and llms["Maya"].calls.count("ninsei.reply") == 1


async def test_post_lists_an_agent_only_for_an_explicit_at_name_it_holds_or_a_reply_to_it(bare):
    e, _ = bare()
    bo, zed = Key("bo"), Key("zed")
    e.presence[ROOM] = {bo.apk: presence(bo.ppk, "Bo"), zed.apk: presence(zed.ppk, "Zed")}
    await e._on_event(bo.agent({"t": "msg", "text": "hi", "name": "Bo"}), "relay")        # Bo holds "Bo"
    await e._on_event(zed.agent({"t": "msg", "text": "hi", "name": "Zed"}), "relay")

    async def mentions(text, **kw):
        out = await e.post(ROOM, text, **kw)
        return json.loads(e.events[ROOM][out["id"]]["content"])["mentions"]
    assert await mentions("what do you think @Bo?") == [bo.apk]
    assert await mentions("bo, zed: anyone?") == []                      # no `@`: nobody is listed
    assert set(await mentions("@Zed @Bo")) == {zed.apk, bo.apk}
    e.presence[ROOM][zed.apk]["name"] = "the"
    assert await mentions("@the plan") == []                             # a common word is never an at-name
    e.presence[ROOM][zed.apk]["name"] = "Bo"                             # a name another key holds
    assert await mentions("@Bo only") == [bo.apk]
    reply_to = next(i for i, x in e.events[ROOM].items() if x["pubkey"] == zed.apk and e._content(x).get("t") == "msg")
    assert zed.apk in await mentions("no at here", reply=reply_to)       # a reply addresses its agent


async def test_a_mentions_list_a_stranger_fills_addresses_nobody(bare):
    e, _ = bare()
    me = e._identity()["agent_pk"]
    mal, bo = Key("mal"), Key("bo")
    e.presence[ROOM] = {bo.apk: presence(bo.ppk, "Bo")}
    await e._on_event(bo.agent({"t": "msg", "text": "hi", "name": "Bo"}), "relay")
    ev = mal.person({"t": "msg", "text": "harmless words", "name": "Mal", "mentions": [me, bo.apk]})
    await e._on_event(ev, "relay")
    c = e._content(ev)
    assert e._addressed(ROOM, ev, c) is False
    assert e._allowed_prio(ROOM, ev["id"], bo.apk, bo.ppk, 100) == 20
    named = mal.person({"t": "msg", "text": "Ada, are you there?", "name": "Mal", "mentions": []})
    await e._on_event(named, "relay")
    assert e._addressed(ROOM, named, e._content(named)) is True          # plain naming of my own agent still works


# ---- 3: an agent in a person's name ----------------------------------------------------------------------------

async def test_an_agent_alert_says_whose_agent_it_is_and_an_agent_in_a_persons_name_is_flagged(world):
    _, engines, _ = world
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    sam.save_settings({"agent_name": "Maya"})
    await run(sam, sam._say, room, "@Maya your card is broken")
    assert await wait_for(lambda: any(m["role"] == "agent" and "card" in m["text"] for m in read(maya, maya.messages, room)))
    snap = read(maya, lambda: maya.snapshot(None, False))
    lm = next(x for x in snap["rooms"] if x["id"] == room)["last_mention"]
    assert lm["name"] == "Maya" and lm["role"] == "agent" and lm["owner_name"] == "Sam"
    assert lm["impostor"] is True                                          # it wears my own name
    m = next(m for m in read(maya, maya.messages, room) if m["role"] == "agent" and "card" in m["text"])
    assert m["impostor"]


async def test_an_agent_named_like_a_person_held_in_the_room_is_flagged_but_an_owners_own_name_is_not(bare):
    e, _ = bare()
    ann, mal = Key("ann"), Key("mal")
    await e._on_event(ann.person({"t": "msg", "text": "hi", "name": "Ann"}), "relay")
    await e._on_event(mal.agent({"t": "msg", "text": "hi", "name": "Ann"}), "relay")        # Mal's agent calls itself Ann
    msgs = {m["pk"]: m for m in e.messages(ROOM)}
    assert msgs[mal.apk]["impostor"] and msgs[mal.apk]["impostor"]["claimed"] == "Ann"
    assert msgs[mal.apk]["impostor"]["real"] == ann.ppk
    assert not msgs[ann.ppk].get("impostor")
    e2, _ = bare(name="Sam")
    await e2._on_event(ann.person({"t": "msg", "text": "hi", "name": "Ann"}), "relay")
    await e2._on_event(ann.agent({"t": "msg", "text": "me too", "name": "Ann"}), "relay")   # Ann's own agent, her own name
    assert not any(m.get("impostor") for m in e2.messages(ROOM))


@needs_node
def test_alert_text_in_the_page_names_the_owner_of_an_agent():
    r = run_js(fn(CORE, "cleanSnippet") + fn(CORE, "mentionAlerts") + """
const toasts = [], listeners = []
globalThis.P = { toast: (k, t) => toasts.push(t), osNotify: null }
const store = { subscribe: f => { listeners.push(f); return () => {} }, isShowing: () => false }
globalThis.nav = () => ({ set() {} })
mentionAlerts(store)
const room = n => ({ id: 'r', name: 'club', mentions: n, last_mention: { id: 'm' + n, name: 'Ada', impostor: false, role: 'agent', owner_name: "Maya", text: 'hi' } })
listeners[0]({ snap: { rooms: [room(0)], dms: {} } })
listeners[0]({ snap: { rooms: [room(1)], dms: {} } })
out({ toasts })
""")
    assert r["toasts"] == ["Ada (Maya's agent) mentioned you in club: \"hi\""]


# ---- 4: "Load earlier" pages stay true ---------------------------------------------------------------------------

async def test_earlier_pages_pick_up_a_delete_and_a_hide_made_after_they_were_loaded(bare):
    e, _ = bare()
    ann, bob = Key("ann"), Key("bob")
    base = int(time.time()) - 5000
    ids = {}
    for i in range(300):
        k = ann if i % 2 else bob
        ev = k.person({"t": "msg", "text": f"line {i}", "name": "Ann" if k is ann else "Bob"}, created_at=base + i)
        ids[i] = ev["id"]
        await e._on_event(ev, "history")
    shown, earlier = e.messages_view(ROOM)
    assert earlier and len(shown) == eng.MESSAGES_SHOWN
    first = shown[0]["id"]
    page = e.messages_before(ROOM, first, 100)["messages"]
    assert [m["text"] for m in page if m["id"] == ids[101]] == ["line 101"]
    # a delete (by the author, Ann) and a hide (Bob) come after the page was loaded
    await e._on_event(ann.person({"t": "delete", "target": ids[101]}, created_at=base + 200), "relay")
    again = e.messages_before(ROOM, first, 100, since_ts=page[0]["ts"])
    got = {m["id"]: m for m in again["messages"]}
    assert got[ids[101]].get("deleted") and not got[ids[101]].get("text")
    assert got[ids[100]]["text"] == "line 100"
    await e.hide_person(bob.ppk, "Bob")
    first = e.messages_view(ROOM)[0][0]["id"]                              # the first item as the snapshot says now
    after = e.messages_before(ROOM, first, 100, since_ts=1)["messages"]
    assert all(m["pk"] != bob.ppk for m in after) and any(m["pk"] == ann.ppk for m in after)
    assert e.messages_before(ROOM, "nope", 100, since_ts=5) == {"messages": [], "more": False}


# ---- 5 and 6: delete, edit and discard on a message no relay has -----------------------------------------------

def retractions(sent, target):
    """What went out to take `target` back: the room `delete` events and the kind 5 requests naming it."""
    dels = [x for x in sent if x["kind"] == KIND_ROOM and json.loads(x["content"]).get("t") == "delete"
            and json.loads(x["content"]).get("target") == target]
    k5 = [x for x in sent if x["kind"] == 5 and target in nostr.tag_values(x, "e")]
    return dels, k5


async def test_delete_of_an_undelivered_message_stops_resending_it_and_still_retracts_it(bare):
    # "pending" or "failed" can't prove no relay stored it (one may have kept it without answering), so the
    # delete event and the kind 5 request go out anyway; the original is never sent again
    e, _ = bare()
    e.pool = PendPool()
    out = await e.post(ROOM, "my home address is 1 Main St")
    await settle(e)
    res = await e.delete(ROOM, out["id"])
    await settle(e)
    assert res["discarded"] is True
    assert out["id"] in e.pool.discarded and out["id"] not in e.events[ROOM]
    assert [x["id"] for x in e.pool.sent].count(out["id"]) == 1           # the one first attempt, never resent
    dels, k5 = retractions(e.pool.sent, out["id"])
    assert len(dels) == 1 and len(k5) == 1 and k5[0]["pubkey"] == e._identity()["person_pk"]
    await e._on_event(next(x for x in e.pool.sent if x["id"] == out["id"]), "relay")   # a relay copy
    assert out["id"] not in e.events[ROOM]


async def test_edit_of_an_undelivered_message_posts_the_edited_words_as_a_new_message(bare):
    e, _ = bare()
    e.pool = PendPool()
    out = await e.post(ROOM, "typo hre")
    await settle(e)
    new = await e.edit(ROOM, out["id"], "typo here")
    assert new["reposted"] is True and new["id"] != out["id"]
    texts = [m["text"] for m in e.messages(ROOM)]
    assert texts == ["typo here"] and out["id"] in e.pool.discarded
    await settle(e)
    assert not any(x["kind"] == KIND_ROOM and json.loads(x["content"]).get("t") == "edit" for x in e.pool.sent)
    dels, k5 = retractions(e.pool.sent, out["id"])                        # the typo is retracted in case a relay kept it
    assert len(dels) == 1 and len(k5) == 1


async def test_a_delivered_message_is_still_edited_and_deleted_the_normal_way(bare):
    e, _ = bare()
    out = await e.post(ROOM, "hello")
    assert "id" in await e.edit(ROOM, out["id"], "hello there")
    await e.delete(ROOM, out["id"])
    await settle(e)
    kinds = [json.loads(x["content"]).get("t", "") if x["kind"] == KIND_ROOM else x["kind"] for x in e.pool.sent]
    assert kinds == ["msg", "edit", "delete", 5]


async def test_discarding_a_message_also_drops_my_agents_undelivered_reply_and_remembers_the_id(bare):
    e, _ = bare()
    e.pool = PendPool()
    ident = e._identity()
    out = await e.post(ROOM, "something private")
    await settle(e)
    reply = nostr.build_event(ident["agent_sk"], KIND_ROOM,
                              json.dumps({"t": "msg", "text": "you said something private", "name": "Ada", "at": time.time()}),
                              [["h", ROOM], ["owner", ident["person_pk"], ident["binding"]], ["e", out["id"], "", "reply"]])
    await e._on_event(reply, "local")
    e.pool.state[reply["id"]] = "pending"
    await e.discard_post(ROOM, out["id"])
    assert reply["id"] in e.pool.discarded and reply["id"] not in e.events[ROOM] and out["id"] not in e.events[ROOM]
    await settle(e)
    dels, k5 = retractions(e.pool.sent, out["id"])
    assert len(dels) == 1 and len(k5) == 1
    _, agent_k5 = retractions(e.pool.sent, reply["id"])                  # my agent's reply: a kind 5 from the agent key
    assert len(agent_k5) == 1 and agent_k5[0]["pubkey"] == ident["agent_pk"]
    original = next(x for x in e.pool.sent if x["id"] == out["id"])
    await e._on_event(original, "relay")                                  # a relay hands the message back
    assert out["id"] not in e.events[ROOM]


# ---- 8: pasted room links, future read marks --------------------------------------------------------------------

def test_parse_room_link_cuts_at_the_first_character_that_is_not_hex():
    assert parse_room_link("ninsei:0123456789abcdef please join") == ("0123456789abcdef", "")
    assert parse_room_link("  0123456789ABCDEF  ")[0] == "0123456789abcdef"
    assert parse_room_link("ninsei:0123456789abcdefzzabc")[0] == "0123456789abcdef"
    assert parse_room_link("hello") == ("", "")
    ev = "ab" * 32
    assert parse_room_link(f"ninsei:0123456789abcdef#{ev}") == ("0123456789abcdef", ev)


async def test_a_future_dated_message_never_pushes_the_read_mark_past_now(bare):
    e, _ = bare()
    now = int(time.time())
    e.store.mark_read(ROOM, now + 59)
    assert e.store.rooms()[ROOM]["last_read"] <= now
    ann = Key("ann")
    await e._on_event(ann.person({"t": "msg", "text": "from the future", "name": "Ann"}, created_at=now + 59), "relay")
    e.snapshot(ROOM)                                                       # opening the room marks it read
    assert e.store.rooms()[ROOM]["last_read"] <= int(time.time())
    out = await e.post(ROOM, "mine")
    assert e.store.rooms()[ROOM]["last_read"] <= int(time.time()) and out["id"]


# ---- 19: an @ to someone who isn't here --------------------------------------------------------------------------

async def test_an_owner_message_at_naming_someone_absent_does_not_wake_my_agent_through_the_alone_rule(bare):
    e, llm = bare()
    e.save_settings({"chattiness": "normal"})
    ada = Key("zoe")
    await e._on_event(ada.person({"t": "msg", "text": "hi", "name": "Zoe"}, created_at=int(time.time()) - 600), "history")
    await e._on_event(own_person_event(e, {"t": "msg", "text": "@Zoe what do you think of this?"}), "local")
    await settle(e)
    assert "ninsei.reply" not in llm.calls
    await e._on_event(own_person_event(e, {"t": "msg", "text": "what do you think of this?"}), "local")
    await settle(e)
    assert llm.calls.count("ninsei.reply") == 1                           # alone, no `@`: still answered


# ---- 10 and 12: pictures are asked for once, and can come back --------------------------------------------------

class QueryArtPool(ArtPool):
    """ArtPool that records how each subscription was made and what was queried, and applies the real pool's dedupe."""

    def __init__(self):
        super().__init__()
        self.kw = []
        self.queries = []
        self.stored = []
        self.seen = set()
        self.handlers = {}

    async def subscribe(self, sub_id, filters, handler, **kw):
        self.subs.append((sub_id, filters))
        self.kw.append(kw)
        self.handlers[sub_id] = (handler, kw.get("dedupe", True))

    async def query(self, filters, timeout=4.0):
        self.queries.append(filters)
        wanted = {a for f in filters for a in f["authors"]}
        return [ev for ev in self.stored if ev["pubkey"] in wanted]

    async def deliver(self, sub_id, ev):
        """What RelayPool does with an EVENT: a deduping subscription never sees an id twice."""
        handler, dedupe = self.handlers[sub_id]
        if dedupe and ev["id"] in self.seen:
            return
        self.seen.add(ev["id"])
        await handler(ev, "relay")


async def test_the_live_art_subscription_starts_at_now_and_new_people_get_one_query_for_just_them(bare):
    e, _ = bare()
    e.pool = QueryArtPool()
    for i in range(60):
        await meet(e, Key(f"p{i}"), f"P{i}")
    await e._art_subscribe()
    assert len(e.pool.queries) == 1 and e.pool.kw[-1] == {"dedupe": False}
    assert all("since" in f and f["since"] >= int(time.time()) - 2 for f in e.pool.subs[-1][1])
    asked = [a for f in e.pool.queries[0] for a in f["authors"]]
    assert len(asked) == 61                                                # the first time: everyone, once
    ghost = Key("ghost")
    await e._on_event(ghost.agent({"t": "presence", "state": "activity: idle", "name": "G", "at": time.time()}, kind=KIND_LIVE), "relay")
    await e._art_subscribe()
    assert len(e.pool.queries) == 2
    assert [a for f in e.pool.queries[1] for a in f["authors"]] == [ghost.ppk]   # just the newcomer
    assert all("since" in f for f in e.pool.subs[-1][1])                   # the live one never replays history
    await e._art_subscribe()
    assert len(e.pool.queries) == 2 and len(e.pool.subs) == 2              # nothing new: nothing asked


async def test_a_join_or_leave_does_not_replay_every_picture(bare):
    e, _ = bare()
    e.pool = QueryArtPool()
    for i in range(20):
        await meet(e, Key(f"p{i}"), f"P{i}")
    await e._resubscribe()
    first = len(e.pool.queries)
    assert first == 1
    e.store.save_room(ROOM2, {"id": ROOM2, "name": "second"})
    e.events[ROOM2] = {}
    await e._resubscribe()                                                  # a join: same people, same pool
    await e._resubscribe()
    assert len(e.pool.queries) == first


async def test_pictures_come_back_after_nobody_then_everyone(bare):
    e, _ = bare()
    e.pool = QueryArtPool()
    mal = Key("mal")
    await meet(e, mal)
    await e._art_subscribe()
    e.save_settings({"show_avatars": "nobody"})
    ev = art(mal, "avatar", {"img": PNG})
    e.pool.stored = [ev]
    await e.pool.deliver("art", ev)                                         # arrives while pictures are off: dropped
    assert e._art_view(mal.ppk).get("av") is None
    e.save_settings({"show_avatars": "everyone"})
    e._art_shown_changed("everyone")
    await e._art_subscribe()                                                # the re-ask: a query, and the live REQ again
    assert e._art_view(mal.ppk).get("av")
    # and through the live subscription: the pool has seen this id, but the art subscription takes every copy
    mal2 = Key("mal2")
    await meet(e, mal2, "Mal2")
    await e._art_subscribe()
    e.save_settings({"show_avatars": "nobody"})
    ev2 = art(mal2, "avatar", {"img": PNG})
    await e.pool.deliver("art", ev2)
    e.save_settings({"show_avatars": "everyone"})
    await e.pool.deliver("art", ev2)
    assert e._art_view(mal2.ppk).get("av")


# ---- 11 and 13: a hostile host's game costs nothing but what we spend --------------------------------------------

async def _round(e, host, gid, n):
    await e._on_event(host.agent({"t": "tales_start", "gid": gid, "rounds": 5, "seq": 1, "name": "Hal"}), "relay")
    await e._on_event(host.agent({"t": "tales_round", "gid": gid, "n": n, "of": 5, "q": "?", "secs": 45,
                                  "ends_at": time.time() + 45, "seq": n + 1, "name": "Hal"}), "relay")
    await settle(e)


def _beats(e):
    return [x for x in e.pool.sent if x["kind"] == KIND_LIVE and json.loads(x["content"]).get("t") == "presence"]


async def test_hitting_my_own_cap_announces_nothing_and_forces_no_beats(bare):
    e, llm = bare()
    e._rate_ok = lambda k, *a: False if k.startswith("fake:") else type(e)._rate_ok(e, k, *a)
    for gi in range(4):
        await _round(e, Key(f"host{gi}"), f"g{gi}", 1)
    assert llm.calls == [] and e._gave_up is None and _beats(e) == []


class EmptyLLM(StubLLM):
    def complete(self, messages, max_tokens=None, purpose=None, task=None, **_):
        self.calls.append(purpose)
        return Result("", Usage(5))


async def test_gave_up_goes_only_to_the_games_room_and_only_when_the_model_gave_nothing(bare):
    e, llm = bare(llm=EmptyLLM("Ada"))
    e.store.save_room(ROOM2, {"id": ROOM2, "name": "other"})
    e.events[ROOM2] = {}
    await _round(e, Key("hostA"), "g1", 1)
    assert llm.calls.count("ninsei.tales.fake") == 2                       # the empty reply was retried once
    assert e._gave_up and e._gave_up[2] == ROOM
    beats = _beats(e)
    assert beats and all(nostr.tag_values(b, "h") == [ROOM] for b in beats if json.loads(b["content"]).get("gave_up"))
    assert not any(nostr.tag_values(b, "h") == [ROOM2] and json.loads(b["content"]).get("gave_up") for b in beats)


async def test_the_empty_reply_retry_counts_against_the_rooms_stranger_cap_and_is_skipped_near_it(bare):
    e, llm = bare(llm=EmptyLLM("Ada"))
    await _round(e, Key("hostA"), "g1", 1)
    assert len(e._rate[f"strangers:{ROOM}"]) == 2                          # the call and its retry
    e2, llm2 = bare(name="Sam", llm=EmptyLLM("Bo"))
    e2._rate[f"strangers:{ROOM}"] = [time.time()] * (eng.ROOM_STRANGER_CALLS - 2)
    await _round(e2, Key("hostB"), "g2", 1)
    assert llm2.calls.count("ninsei.tales.fake") == 1                      # nearly full: no retry


# ---- 14: the metadata check is an allow-list ----------------------------------------------------------------------

def seg(m, body):
    import struct
    return bytes([0xFF, m]) + struct.pack(">H", len(body) + 2) + body


EXIF = b"Exif\x00\x00MM\x00*" + b"GPS 40.7N 74.0W" * 3


@pytest.mark.parametrize("mime,data", [
    ("image/jpeg", jpeg()[:-2] + seg(0xE1, EXIF) + b"\xff\xd9"),                                  # EXIF after the scan
    ("image/jpeg", jpeg()[:-2] + b"\xff\xd9" + b"\xff\xd8" + seg(0xE1, EXIF) + jpeg()[2:]),        # a second image appended
    ("image/jpeg", jpeg(extra=[(0xE2, b"MPF\x00" + b"x" * 40)])),                                  # APP2 that is not a profile
    ("image/jpeg", jpeg(extra=[(0xEC, b"Ducky")])),                                                # any other APPn
    ("image/webp", riff(vp8x(64, 64, 0x08), vp8l(), wchunk(b"exif", EXIF))),                       # lowercase chunk name
    ("image/webp", riff(vp8x(64, 64, 0x08), vp8l())),                                              # VP8X claims EXIF
    ("image/webp", riff(vp8x(64, 64, 0x04), vp8l())),                                              # ... or XMP
    ("image/png", png(extra=[(b"prVt", EXIF)])),                                                   # a private chunk
    ("image/png", png(extra=[(b"sBIT", b"\x08\x08\x08")])),                                        # not on the list
])
def test_find_metadata_refuses_everything_off_the_allow_list(mime, data):
    assert avatar.find_metadata(data, mime)


@pytest.mark.parametrize("mime,data", [
    ("image/jpeg", jpeg()),
    ("image/jpeg", jpeg(extra=[(0xE2, b"ICC_PROFILE\x00\x01\x01" + b"p" * 30)])),
    ("image/png", png(extra=[(b"gAMA", b"\x00\x00\xb1\x8f"), (b"sRGB", b"\x00"), (b"pHYs", b"\x00" * 9), (b"tRNS", b"\x00\x00")])),
    ("image/webp", riff(vp8l())),
    ("image/webp", riff(vp8())),
    ("image/webp", riff(vp8x(64, 64, 0x20), wchunk(b"ICCP", b"p" * 8), vp8l())),
])
def test_find_metadata_passes_the_plain_parts_and_a_colour_profile(mime, data):
    assert avatar.find_metadata(data, mime) is None


def test_a_jpeg_with_a_second_image_after_the_first_is_not_a_picture():
    two = jpeg()[:-2] + b"\xff\xd9" + jpeg()[2:]
    assert avatar.check_avatar(uri(two, "image/jpeg")) is None
    assert avatar.check_avatar(uri(jpeg(), "image/jpeg")) is not None


# ---- 15: a picture's whole event stays under 60,000 bytes ---------------------------------------------------------

async def test_the_biggest_allowed_picture_makes_an_event_under_60000_bytes(bare):
    e, _ = bare()
    base = len(png(idat=b""))
    big = png(idat=bytes(avatar.MAX_BYTES - base))
    assert len(big) == avatar.MAX_BYTES
    got = await e.set_avatar(uri(big, "image/png"))
    await settle(e)
    ev = next(x for x in e.pool.sent if x["id"] == got["id"])
    assert len(json.dumps(ev)) < 60000
    over = png(idat=bytes(avatar.MAX_BYTES - base + 1))
    with pytest.raises(ValueError):
        await e.set_avatar(uri(over, "image/png"))


# ---- 16: a delete takes two pace slots -----------------------------------------------------------------------------

async def test_a_delete_takes_two_pace_slots(bare):
    e, _ = bare()
    ids = [(await e.post(ROOM, f"m{i}"))["id"] for i in range(12)]
    for i in ids[:eng.CLICKS_PER_MIN // 2]:
        await e.delete(ROOM, i)
    with pytest.raises(ValueError, match="Slow down"):
        await e.delete(ROOM, ids[eng.CLICKS_PER_MIN // 2])
    await settle(e)
    sent_kinds = [x["kind"] for x in e.pool.sent]
    assert sent_kinds.count(5) == eng.CLICKS_PER_MIN // 2                  # ten kind 5 requests, not twenty


# ---- 17: the seen-people set is a bounded LRU ---------------------------------------------------------------------

async def test_new_people_still_get_pictures_when_the_seen_set_is_full(bare, monkeypatch):
    monkeypatch.setattr(eng, "ART_OK_MAX", 3)
    e, _ = bare()
    keys = [Key(f"k{i}") for i in range(6)]
    for i, k in enumerate(keys):
        await meet(e, k, f"K{i}")
    assert len(e._art_ok) == 3 and keys[-1].ppk in e._art_ok and keys[0].ppk not in e._art_ok
    assert e._take_art(art(keys[-1], "avatar", {"img": PNG})) is True      # a newcomer is not locked out
    assert e._take_art(art(keys[0], "avatar", {"img": PNG})) is False      # the idlest one gave way


# ---- 18: a face refused by the pace saves nothing --------------------------------------------------------------------

async def test_a_face_the_pace_refuses_is_refused_before_anything_is_saved(bare):
    e, _ = bare()
    face = {"hue": 120}
    clean = eng.clean_face(face)
    assert clean
    e._rate["art"] = [time.time()] * eng.ART_PUBLISH_PER_10MIN
    with pytest.raises(ValueError, match=r"Try again in \d+ min"):
        await e.check_face_pace(face)
    e.store.set("face_sent", json.dumps(clean, sort_keys=True))             # the same face as already published: no pace
    await e.check_face_pace(face)


async def test_the_settings_route_refuses_a_too_soon_face_without_saving(world):
    pytest.importorskip("fastapi")
    import importlib.util
    import pathlib
    _, engines, _ = world
    e = engines["Maya"]
    spec = importlib.util.spec_from_file_location("ninsei_api_b", pathlib.Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py")
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)

    async def engine():
        return e
    api._engine = engine
    read(e, lambda: e._rate.__setitem__("art", [time.time()] * eng.ART_PUBLISH_PER_10MIN))
    with pytest.raises(Exception) as err:
        await api.settings(api.Settings(display_name="Changed", person_face={"hue": 40}))
    assert "Try again in" in str(getattr(err.value, "detail", err.value))
    assert e.settings()["display_name"] == "Maya"


def test_the_settings_route_checks_the_face_pace_before_it_saves_anything():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py").read_text()
    body = src[src.index("async def settings("):src.index("async def people_hide") if "async def people_hide" in src else None]
    assert body.index("eng.check_looks_pace") < body.index("eng.save_settings")
    assert "since_ts: int = Query(0, ge=0)" in src and "eng.messages_before, room, before, limit, since_ts" in src
