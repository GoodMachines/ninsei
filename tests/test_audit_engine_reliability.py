"""Audit fixes, engine reliability and games group: names after a history replay, game ranking after a
restart, per-room history requests, one game start at a time, a failed boot, leaving a room, the outbox row
written before the send, and which vote options are yours.

Most tests drive a bare Engine (no thread, no relays) on the test loop, as in test_hostile.py."""
import asyncio
import fcntl
import gc
import hashlib
import json
import os
import sqlite3
import threading
import time

import pytest

from ninsei_engine import game, nostr
from ninsei_engine import engine as eng_mod
from ninsei_engine.engine import (CONTESTED, HISTORY_FILTERS_PER_SUB, KIND_LIVE, KIND_ROOM, ROOM_HISTORY_LIMIT,
                                  Engine, EngineLocked, RoomLeft, _claim_token, open_fake)
from ninsei_engine.relays import RelayPool
from ninsei_engine.store import Store
from test_engine import StubLLM, wait_for
from test_hostile import ROOM, FakePool, Key, bare, own_person_event, settle  # noqa: F401  (fixture re-export)

BUSY = "bb" * 8


class RoomPool(FakePool):
    """A fake pool that also takes subscriptions, so leaving a room and resubscribing work on a bare engine."""

    def __init__(self):
        super().__init__()
        self.subs = {}
        self.queries = []

    async def subscribe(self, sub_id, filters, handler, **kw):
        self.subs[sub_id] = filters

    async def unsubscribe(self, sub_id):
        self.subs.pop(sub_id, None)

    async def query(self, filters, timeout=4.0):
        self.queries.append(filters)
        return []


def say(who, text, created_at=None, name=None):
    return who.person({"t": "msg", "name": name or "Sam", "text": text}, created_at=created_at)


# --- #9: a replay can't hand a name to whoever sorts first -------------------------------------------

async def test_backdated_history_cannot_take_a_name_from_its_real_holder(bare):
    e, _ = bare()
    sam, mal = Key("sam"), Key("mal")
    now = int(time.time())
    real = say(sam, "real sam", now - 86400)
    fake = say(mal, "backdated", now - 2 * 86400)
    for ev in sorted([real, fake], key=lambda x: x["created_at"]):  # what join_room does: oldest first
        await e._on_event(ev, "history")
    assert e._names_reg(ROOM)["p:sam"] == CONTESTED  # two keys, no live word: nobody holds it yet
    msgs = {m["text"]: m for m in e.messages(ROOM)}
    assert msgs["real sam"]["impostor"]["real"] is None and msgs["backdated"]["impostor"]["real"] is None
    # the real Sam speaks live: the name is theirs, and the backdated lines are now plainly not
    await e._on_event(say(sam, "i am here"), "relay")
    assert e._names_reg(ROOM)["p:sam"] == sam.ppk
    msgs = {m["text"]: m for m in e.messages(ROOM)}
    assert not msgs["real sam"].get("impostor") and not msgs["i am here"].get("impostor")
    assert msgs["backdated"]["impostor"]["real"] == sam.ppk


async def test_a_name_used_by_one_key_in_history_is_held(bare):
    e, _ = bare()
    sam = Key("sam")
    await e._on_event(say(sam, "hello", int(time.time()) - 5000), "history")
    assert e._names_reg(ROOM)["p:sam"] == sam.ppk


async def test_a_backdated_post_unseats_a_history_only_holder_but_not_a_live_one(bare):
    e, _ = bare()
    ann, ann_mal, bob, bob_mal = Key("ann"), Key("ann-mal"), Key("bob"), Key("bob-mal")
    old = int(time.time()) - 5000
    await e._on_event(say(ann, "hi", old, "Ann"), "history")
    await e._on_event(say(bob, "hi", old, "Bob"), "history")
    await e._on_event(say(bob, "live now", name="Bob"), "relay")  # Bob shows the name live
    await e._on_event(say(ann_mal, "replay", old - 10, "Ann"), "history")
    await e._on_event(say(bob_mal, "replay", old - 10, "Bob"), "history")
    reg = e._names_reg(ROOM)
    assert reg["p:ann"] == CONTESTED  # nobody had shown it live
    assert reg["p:bob"] == bob.ppk  # settled by a live post, so a replay can't touch it


async def test_first_use_seeding_marks_a_shared_name_contested(bare):
    e, _ = bare()
    sam, mal = Key("sam"), Key("mal")
    now = int(time.time())
    for ev in (say(mal, "a", now - 9000), say(sam, "b", now - 8000)):
        e.events[ROOM][ev["id"]] = ev  # events already stored, no registry yet
    reg = e._names_reg(ROOM)
    assert reg["p:sam"] == CONTESTED


async def test_a_contested_mark_does_not_fill_the_registry(bare, monkeypatch):
    monkeypatch.setattr(eng_mod, "MAX_NAMES", 4)
    e, _ = bare()
    reg = e._names_reg(ROOM)
    for i in range(4):
        reg[f"p:name{i}"] = CONTESTED
    sam = Key("sam")
    await e._on_event(say(sam, "hello", name="Sam"), "relay")
    assert e._names_reg(ROOM).get("p:sam") == sam.ppk  # contested marks were the first to make room


# --- #10: arrival order is kept across a restart -----------------------------------------------------

async def _two_starts(e, real_host, thief, thief_src="relay"):
    await e._on_event(real_host.agent({"t": "tales_start", "gid": "real", "rounds": 3, "seq": 1}), "relay")
    await e._on_event(thief.agent({"t": "tales_start", "gid": "fake", "rounds": 3, "seq": 1},
                                  created_at=int(time.time()) - 5), thief_src)


async def test_a_backdated_start_cannot_take_over_after_a_restart(bare):
    e, _ = bare(ts=1.0)
    host, thief = Key("host"), Key("thief")
    await _two_starts(e, host, thief)
    assert e.game_view(ROOM)["gid"] == "real"
    e.store.close()
    e2 = Engine(e.data_dir, lambda: StubLLM("Ada"), lock=False, timescale=1.0, relays=[])
    e2.store.set("commons_offered", True)
    try:
        await e2._boot()
        assert e2.game_view(ROOM)["gid"] == "real" and e2.game_view(ROOM)["host"] == host.apk
    finally:
        for t in list(e2._tasks):
            t.cancel()
        await asyncio.gather(*e2._tasks, return_exceptions=True)
        await e2.pool.stop()
        e2.store.close()


async def test_a_start_with_no_known_arrival_never_outranks_one_that_arrived_live(bare):
    e, _ = bare(ts=1.0)
    host, thief = Key("host"), Key("thief")
    await _two_starts(e, host, thief, thief_src="history")  # the thief's has no arrival, only a backdated date
    assert e.game_view(ROOM)["gid"] == "real"


def test_store_keeps_arrival_times_and_upgrades_an_old_database(tmp_path):
    path = tmp_path / "old" / "ninsei.db"
    path.parent.mkdir(mode=0o700)
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE events (id TEXT PRIMARY KEY, room TEXT, kind INTEGER, pubkey TEXT, "
               "created_at INTEGER, json TEXT NOT NULL)")
    old = {"id": "a" * 64, "pubkey": "b" * 64, "kind": KIND_ROOM, "created_at": int(time.time()), "content": "{}",
           "tags": [], "sig": ""}
    db.execute("INSERT INTO events VALUES(?,?,?,?,?,?)", (old["id"], ROOM, KIND_ROOM, old["pubkey"], old["created_at"],
                                                          json.dumps(old)))
    db.commit()
    db.close()
    s = Store(path)
    try:
        assert [x["id"] for x in s.room_events(ROOM)] == [old["id"]] and s.room_arrivals(ROOM) == {}
        new = {**old, "id": "c" * 64}
        s.add_event(ROOM, new, 1234.5)
        s.add_event(ROOM, {**old, "id": "d" * 64}, None)  # a history pull: no arrival
        assert s.room_arrivals(ROOM) == {new["id"]: 1234.5}
    finally:
        s.close()


# --- #17: each room asks for its own history ---------------------------------------------------------

def _mini_relay(stored):
    """A relay that applies each filter's limit to what that filter matches, as real ones do."""
    async def subscribe(sub_id, filters, handler, **kw):
        for f in filters:
            if f["kinds"] != [KIND_ROOM]:
                continue
            hit = [ev for ev in stored if nostr.tag_values(ev, "h")[0] in f["#h"] and ev["created_at"] >= f["since"]]
            hit.sort(key=lambda ev: ev["created_at"], reverse=True)
            for ev in hit[: f.get("limit", len(hit))]:
                await handler(ev, "relay")
    return subscribe


def _room_event(room, pk, created_at, text):
    body = json.dumps({"t": "msg", "name": "A", "text": text})
    return {"id": hashlib.sha256(f"{room}{pk}{created_at}{text}".encode()).hexdigest(), "pubkey": pk,
            "created_at": created_at, "kind": KIND_ROOM, "tags": [["h", room]], "content": body, "sig": ""}


async def test_a_busy_room_cannot_starve_a_quiet_one_on_resubscribe(bare):
    e, _ = bare()
    e.store.save_room(BUSY, {"id": BUSY, "name": "busy"})
    e.events[BUSY] = {}
    now = int(time.time())
    pk = "a" * 64
    busy = [_room_event(BUSY, pk, now - 3600 - i, f"b{i}") for i in range(700)]
    quiet = [_room_event(ROOM, pk, now - 7200 - i, f"q{i}") for i in range(3)]  # older than every busy event
    e.pool.subscribe = _mini_relay(busy + quiet)
    e.pool.unsubscribe = RoomPool().unsubscribe
    await e._resubscribe()
    assert {ev["id"] for ev in quiet} <= set(e.events[ROOM])  # one shared limit of 500 never let these through
    assert len(e.events[BUSY]) == ROOM_HISTORY_LIMIT


async def test_every_joined_room_gets_its_own_history_filter_in_bounded_requests(bare):
    e, _ = bare()
    e.pool = RoomPool()
    rooms = [f"{i:016x}" for i in range(1, 21)]
    for r in rooms:
        e.store.save_room(r, {"id": r, "name": r})
    await e._resubscribe()
    assert [f["kinds"] for f in e.pool.subs.pop("dm")] == [[1059]]  # the private-message request is its own, one filter
    assert all(f["kinds"] == [30078] and len(f["authors"]) <= 50 for f in e.pool.subs.pop("art"))  # so is the pictures-and-faces one
    hist = [f for fs in e.pool.subs.values() for f in fs if f["kinds"] == [KIND_ROOM]]
    assert sorted(f["#h"][0] for f in hist) == sorted([ROOM] + rooms) and all(len(f["#h"]) == 1 for f in hist)
    assert all(f["limit"] <= ROOM_HISTORY_LIMIT for f in hist)
    assert all(sum(f["kinds"] == [KIND_ROOM] for f in fs) <= HISTORY_FILTERS_PER_SUB for fs in e.pool.subs.values())
    assert len(e.pool.subs) == 3 and "rooms" in e.pool.subs  # 21 rooms, 8 to a request
    for r in rooms:  # leave most of them: the requests that held only left rooms are closed
        await e.leave_room(r)
    assert set(e.pool.subs) - {"dm", "art"} == {"rooms"}


async def test_unhide_asks_for_each_rooms_history_separately(bare):
    e, _ = bare()
    e.pool = RoomPool()
    e.store.save_room(BUSY, {"id": BUSY, "name": "busy"})
    e.events[BUSY] = {}
    await e.unhide_person("f" * 64)
    asked = [f for fs in e.pool.queries for f in fs if f["kinds"] == [KIND_ROOM]]   # (and one for gift wraps)
    assert sorted(f["#h"][0] for f in asked) == sorted([ROOM, BUSY]) and all(f["limit"] <= 300 for f in asked)


# --- #18: one start at a time ------------------------------------------------------------------------

class GatedLLM(StubLLM):
    """Holds the question-writing call until the test lets it go."""

    def __init__(self, name):
        super().__init__(name)
        self.gate = threading.Event()

    def complete(self, messages, **k):
        if k.get("purpose") == "ninsei.tales.questions":
            self.gate.wait(20)
        return super().complete(messages, **k)


async def test_two_concurrent_starts_make_one_game(bare):
    llm = GatedLLM("Ada")
    e, _ = bare(llm=llm)
    first = asyncio.ensure_future(e.start_tales(ROOM, 1))
    assert await wait_for(lambda: ROOM in e._starting_games)
    second = asyncio.ensure_future(e.start_tales(ROOM, 1))
    third = asyncio.ensure_future(e.start_tales(ROOM, 1, mode="agent"))
    for t in (second, third):  # refused while the first is still writing its questions
        with pytest.raises(ValueError, match="already running"):
            await t
    llm.gate.set()
    assert "gid" in await first
    starts = [ev for ev in e.pool.sent if json.loads(ev["content"]).get("t") == "tales_start"]
    assert len(starts) == 1 and len(e._host_games) == 1 and not e._starting_games
    with pytest.raises(ValueError, match="already running"):  # and a hosted game counts before its start is in view
        await e.start_tales(ROOM, 1)
    await e._end_hosted(ROOM)


async def test_a_failed_start_frees_the_room(bare):
    llm = StubLLM("Ada")
    e, _ = bare(llm=llm)
    orig = llm.complete
    llm.complete = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("model down")) \
        if k.get("purpose") == "ninsei.tales.questions" else orig(*a, **k)
    with pytest.raises(Exception):
        await e.start_tales(ROOM, 1)
    assert not e._starting_games
    llm.complete = orig
    assert "gid" in await e.start_tales(ROOM, 1)
    await e._end_hosted(ROOM)


# --- #34: a failed boot lets go of everything --------------------------------------------------------

def _lock_fds() -> int:
    """Open descriptors that point at an engine.lock file (macOS: F_GETPATH; elsewhere /proc/self/fd)."""
    n = 0
    for fd in os.listdir("/dev/fd"):
        try:
            if hasattr(fcntl, "F_GETPATH"):
                path = fcntl.fcntl(int(fd), fcntl.F_GETPATH, b"\0" * 1024).split(b"\0")[0].decode()
            else:
                path = os.readlink(f"/proc/self/fd/{fd}")
        except (OSError, ValueError):
            continue
        n += path.endswith("engine.lock")
    return n


async def test_a_failed_boot_releases_the_lock_for_the_next_engine(tmp_path, monkeypatch):
    real_boot = Engine._boot

    async def boom(self):
        raise RuntimeError("boom")
    monkeypatch.setattr(Engine, "_boot", boom)
    first = Engine(tmp_path / "d", lambda: StubLLM("Ada"), relays=[], lock=True)  # stays referenced: no GC rescue
    with pytest.raises(RuntimeError, match="boom"):
        first.start()
    assert first.loop.is_closed() and first._lock_file is None
    monkeypatch.setattr(Engine, "_boot", real_boot)
    second = Engine(tmp_path / "d", lambda: StubLLM("Ada"), relays=[], lock=True)
    second.save_settings({"display_name": "Maya", "agent_name": "Ada", "onboarded": False})
    try:
        second.start()  # before the fix: EngineLocked "already running in another Hermes process (own pid)"
    finally:
        await asyncio.to_thread(second.stop)


async def test_a_refused_lock_closes_what_the_engine_opened(tmp_path):
    holder = Engine(tmp_path / "d", lambda: StubLLM("Ada"), relays=[], lock=True)
    holder.save_settings({"onboarded": False})
    holder.start()
    gc.collect()
    gc.disable()  # a leak must not be hidden by a collection
    try:
        before = _lock_fds()
        assert before == 1
        loser = Engine(tmp_path / "d", lambda: StubLLM("Ada"), relays=[], lock=True)
        with pytest.raises(EngineLocked):
            loser.start()
        assert loser._lock_file is None and _lock_fds() == before
    finally:
        gc.enable()
        await asyncio.to_thread(holder.stop)


# --- #35: leaving a room stops what was going to it --------------------------------------------------

class SlowReplyLLM(StubLLM):
    def __init__(self, name):
        super().__init__(name)
        self.started = threading.Event()
        self.gate = threading.Event()

    def complete(self, messages, **k):
        if k.get("purpose") == "ninsei.reply":
            self.started.set()
            self.gate.wait(20)
        return super().complete(messages, **k)


async def test_a_room_left_mid_reply_gets_no_reply(bare):
    llm = SlowReplyLLM("Ada")
    e, _ = bare(llm=llm)
    e.pool = RoomPool()
    pk = e._identity()["agent_pk"]
    await e._on_event(own_person_event(e, {"t": "msg", "text": "Ada, are you there?", "mentions": [pk]}), "relay")
    assert await wait_for(llm.started.is_set)  # the model call is running
    await e.leave_room(ROOM)
    llm.gate.set()
    await settle(e)
    assert not [ev for ev in e.pool.sent if json.loads(ev["content"]).get("t") == "msg" and ev["pubkey"] == pk]
    assert e.agent_state == "activity: idle" and not e.last_error


async def test_publishing_into_a_left_room_is_refused(bare):
    e, _ = bare()
    e.pool = RoomPool()
    await e.leave_room(ROOM)
    with pytest.raises(RoomLeft):
        await e._publish_room(ROOM, True, {"t": "msg", "text": "hello?"})
    with pytest.raises(RoomLeft):
        await e.post(ROOM, "hello?")
    assert not e.pool.sent


async def test_leaving_drops_the_rooms_drafts_and_offers(bare):
    e, _ = bare()
    e.pool = RoomPool()
    oid = e.store.queue_draft(ROOM, "queued while I was here", "tool")
    other = e.store.queue_draft(BUSY, "for another room", "tool")
    e.store.set("offers", {"o1": {"room": ROOM, "status": "open", "at": time.time(), "task": "t", "title": "T"},
                           "o2": {"room": BUSY, "status": "open", "at": time.time(), "task": "t", "title": "T"}})
    await e.leave_room(ROOM)
    assert [d["id"] for d in e.store.drafts()] == [other]
    offers = e.store.get("offers")
    assert offers["o1"]["status"] == "dropped" and offers["o2"]["status"] == "open"
    assert [o["id"] for o in e.snapshot()["offers"]] == ["o2"]
    with pytest.raises(RoomLeft):
        await e.answer_offer("o1", True)
    assert oid


async def test_a_draft_for_a_left_room_is_not_marked_sent(bare):
    e, _ = bare()
    e.pool = RoomPool()
    oid = e.store.queue_draft(ROOM, "late", "tool")
    e.store.forget_room(ROOM)  # the room goes away between the draft and the click
    with pytest.raises(RoomLeft):
        await e.send_draft(oid)
    assert not e.pool.sent and not e.store.drafts()
    row = e.store._db.execute("SELECT status FROM outbox WHERE id=?", (oid,)).fetchone()
    assert row[0] == "discarded"  # not "sent": nothing was


# --- #39: the outbox row exists before anything is sent ----------------------------------------------

async def test_an_event_has_its_outbox_row_before_the_send_starts(bare):
    e, _ = bare()
    ev = await e._publish_room(ROOM, False, {"t": "msg", "text": "hi"})
    assert e.store.event_outbox_status(ev["id"]) == "pending"  # the spawned send hasn't even run yet


async def test_presence_never_gets_an_outbox_row(bare):
    e, _ = bare()
    ev = await e._publish_room(ROOM, True, {"t": "presence", "state": "activity: idle"}, kind=KIND_LIVE)
    assert e.store.event_outbox_status(ev["id"]) is None


async def test_a_send_cancelled_by_quitting_is_resent_after_a_restart(bare):
    e, _ = bare()
    e.pool = RelayPool([], outbox=e.store)  # the real pool: its publish queues the row itself, if it ever starts
    ev = await e._publish_room(ROOM, False, {"t": "msg", "text": "sent just before quit"})
    for t in list(e._tasks):  # stop() cancels the engine's tasks before the publish task has run a step
        t.cancel()
    await asyncio.gather(*e._tasks, return_exceptions=True)
    assert e.pool.delivery(ev["id"]) == "pending"
    e.store.close()
    fresh = Store(e.data_dir / "ninsei.db")
    try:
        pool = RelayPool([], outbox=fresh)
        assert pool.delivery(ev["id"]) == "pending" and ev["id"] in pool._outbox  # loaded to be resent
    finally:
        fresh.close()


# --- #19: your options are blocked by who wrote them, not by how the text compares -------------------

def _vote_events(host, gid, mode, options, claims):
    out = [host.agent({"t": "tales_start", "gid": gid, "rounds": 1, "seq": 1, "mode": mode}),
           host.agent({"t": "tales_round", "gid": gid, "n": 1, "q": "?", "secs": 45,
                       "ends_at": time.time() + 45, "seq": 2, "mode": mode})]
    vote = {"t": "tales_vote_open", "gid": gid, "n": 1, "options": options, "ends_at": time.time() + 30, "secs": 30,
            "seq": 3, "mode": mode}
    if claims is not None:
        vote["claims"] = claims
    return out, host.agent(vote)


async def _my_fake(e, host, gid, text, as_agent=False):
    """Publish my answer sealed to `host`'s agent key; returns (event, nonce). The nonce comes back only by
    opening my own event, as game_view does."""
    ev = await e._publish_fake(ROOM, as_agent, gid, 1, text, host.apk)
    ident = e._identity()
    opened = open_fake(ident["agent_sk"] if as_agent else ident["person_sk"], host.apk, json.loads(ev["content"])["enc"])
    return ev, opened["nonce"]


async def test_a_lucky_match_does_not_block_the_true_answer(bare):
    e, _ = bare(ts=1.0)
    host = Key("host")
    pre, vote = _vote_events(host, "g1", "tales", [], None)
    for ev in pre:
        await e._on_event(ev, "relay")
    _ev, nonce = await _my_fake(e, host, "g1", "Paris")  # lucky: the true answer is "paris", so no option is mine
    options = [{"id": "opt1", "text": "paris"}, {"id": "opt2", "text": "Lyon"}]
    claims = {"opt1": [_claim_token("opt1", "decoy")], "opt2": [_claim_token("opt2", "f" * 32)]}
    _, vote = _vote_events(host, "g1", "tales", options, claims)
    await e._on_event(vote, "relay")
    g = e.game_view(ROOM)
    assert g["phase"] == "vote" and g["blocked"] == [] and "claims" not in g
    assert g["my_fake"] == "Paris"  # shown from my own sealed answer, opened locally
    # and a fake that did land in an option blocks exactly that option
    claims["opt2"].append(_claim_token("opt2", nonce))
    _, vote2 = _vote_events(host, "g1", "tales", options, claims)
    vote2 = host.agent({**json.loads(vote2["content"]), "seq": 4})
    await e._on_event(vote2, "relay")
    assert e.game_view(ROOM)["blocked"] == ["opt2"]


async def test_who_is_the_agent_blocks_by_author_not_by_similar_text(bare):
    e, _ = bare(ts=1.0)
    host, bob = Key("host"), Key("bob")
    pre, _ = _vote_events(host, "g2", "agent", [], None)
    for ev in pre:
        await e._on_event(ev, "relay")
    _ev, nonce = await _my_fake(e, host, "g2", "oat latte")
    bobs, bobs_nonce = bob.fake(host.apk, "g2", 1, "Oat latte.", agent=True)  # Bob's agent, nearly the same text
    await e._on_event(bobs, "relay")
    options = [{"id": "mine1", "text": "oat latte"}, {"id": "bobs1", "text": "Oat latte."}]
    claims = {"mine1": [_claim_token("mine1", nonce)], "bobs1": [_claim_token("bobs1", bobs_nonce)]}
    _, vote = _vote_events(host, "g2", "agent", options, claims)
    await e._on_event(vote, "relay")
    assert e.game_view(ROOM)["blocked"] == ["mine1"]  # Bob's can be flagged


async def test_a_host_without_claims_gets_exact_text_in_agent_mode_and_normalised_in_tales(bare):
    e, _ = bare(ts=1.0)
    host = Key("host")
    pre, _ = _vote_events(host, "g3", "agent", [], None)
    for ev in pre:
        await e._on_event(ev, "relay")
    await _my_fake(e, host, "g3", "oat latte")
    options = [{"id": "a1", "text": "oat latte"}, {"id": "a2", "text": "Oat latte."}]
    _, vote = _vote_events(host, "g3", "agent", options, None)
    await e._on_event(vote, "relay")
    assert e.game_view(ROOM)["blocked"] == ["a1"]
    # Tall Tales merges equal fakes into one option, so there a normalised match is still right
    host2 = Key("host2")
    pre, _ = _vote_events(host2, "g4", "tales", [], None)
    e2, _ = bare("Maya2", "Ada2", ts=1.0)
    for ev in pre:
        await e2._on_event(ev, "relay")
    await _my_fake(e2, host2, "g4", "Oat Latte.")
    _, vote = _vote_events(host2, "g4", "tales", [{"id": "t1", "text": "oat latte"}, {"id": "t2", "text": "tea"}], None)
    await e2._on_event(vote, "relay")
    assert e2.game_view(ROOM)["blocked"] == ["t1"]


def test_option_claims_are_per_fake_padded_and_in_option_order():
    options = [{"id": "t", "text": "truth"}, {"id": "o2", "text": "c"}, {"id": "o1", "text": "a or b"}]
    author_of = {"o1": "a,b", "o2": "c"}
    nonces = {"a": "aa" * 16, "b": "bb" * 16, "c": "cc" * 16}
    claims = Engine._option_claims(options, author_of, nonces)
    assert list(claims) == ["t", "o2", "o1"]  # the options' order: the truth is not the odd one at the end
    assert claims["o1"] == sorted([_claim_token("o1", nonces["a"]), _claim_token("o1", nonces["b"])])
    assert _claim_token("o2", nonces["c"]) in claims["o2"]
    assert {len(v) for v in claims.values()} == {2}  # every option carries as many tokens as the fullest
    real = {_claim_token(o["id"], x) for o in options for x in nonces.values()}
    assert not set(claims["t"]) & real and all(v == sorted(v) for v in claims.values())
    agent = Engine._option_claims(options[1:], author_of, nonces)  # agent mode: no truth
    assert set(agent) == {"o1", "o2"}


async def test_the_host_posts_claims_and_a_lucky_hosts_view_blocks_the_truth(bare, monkeypatch):
    monkeypatch.setattr(game, "FAKE_SECONDS", 2400)
    monkeypatch.setattr(game, "VOTE_SECONDS", 2400)
    e, _ = bare(ts=0.02)
    mal = Key("mal")
    await e._on_event(mal.agent({"t": "presence", "name": "Mal", "state": "activity: idle"}, kind=KIND_LIVE), "relay")
    gid = (await e.start_tales(ROOM, 1))["gid"]
    assert await wait_for(lambda: (e.game_view(ROOM) or {}).get("phase") == "fakes")
    n = e.game_view(ROOM)["n"]
    await e.submit_fake(ROOM, gid, n, "three")  # the host's own owner guesses the real answer: lucky
    host_pk = e._identity()["agent_pk"]
    four_nonces = []
    for agent in (False, True):
        ev, nonce = mal.fake(host_pk, gid, n, "four", agent=agent)
        four_nonces.append(nonce)
        await e._on_event(ev, "relay")
    assert await wait_for(lambda: (e.game_view(ROOM) or {}).get("phase") == "vote")

    def sent_votes():
        return [c for c in (json.loads(ev["content"]) for ev in e.pool.sent) if c.get("t") == "tales_vote_open"]

    # the host applies its own event locally first (the view flips at once) and sends it from a spawned task
    assert await wait_for(sent_votes)
    vote = sent_votes()[-1]
    texts = {o["text"]: o["id"] for o in vote["options"]}
    assert set(texts) == {"three", "four", "Ada five"}  # the host's agent plays too
    assert {_claim_token(texts["four"], x) for x in four_nonces} == set(vote["claims"][texts["four"]])
    truth = vote["claims"][texts["three"]]  # padded to as many tokens as the merged "four" has
    assert len(truth) == 2 and not set(truth) & {_claim_token(texts["three"], x) for x in four_nonces}
    # the lucky rule: the truth carries the lucky writer's token, so to them it reads as their own answer
    assert set(e.game_view(ROOM)["blocked"]) == {texts["three"], texts["Ada five"]}  # + my own agent's fake
    await e._end_hosted(ROOM)
