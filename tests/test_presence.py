"""A person's status, the agent while the owner is away, and a budget strangers can't drain.

Bare engines (no thread, no relays) on the test loop, as in test_hostile.py. conftest starts every engine with its
owner at the screen; a test about being away sets `_last_open_at = _last_focused_at = 0.0` itself."""
import asyncio
import json
import threading
import time

import pytest

from ninsei_engine import engine as eng_mod
from ninsei_engine import nostr
from ninsei_engine.engine import (ABSENT_AFTER, IDLE_FOCUS, IDLE_OPEN, KIND_LIVE, PRESENT_FOCUS, STRANGER_REPLIES, Engine,
                                  _person_claim, _share_ok)
from ninsei_engine.store import Store
from test_engine import Result, StubLLM, Usage, wait_for
from test_game_secrecy import HubPool, _presence
from test_hostile import ROOM, Key, bare, own_person_event, settle  # noqa: F401  (fixture re-export)

ROOM2, ROOM3 = "1111222233334444", "5555666677778888"


def away(e):
    """The owner has not had Ninsei open since the engine started."""
    e._last_open_at = e._last_focused_at = 0.0


def seen(e, focused_ago=None, open_ago=None):
    now = time.time()
    e._last_focused_at = 0.0 if focused_ago is None else now - focused_ago
    e._last_open_at = 0.0 if open_ago is None else now - open_ago


def beats(e):
    return [json.loads(ev["content"]) for ev in e.pool.sent if ev["kind"] == KIND_LIVE
            and json.loads(ev["content"]).get("t") == "presence"]


def beat(key, person="__none__", state="activity: idle", name="Bo", at=None):
    c = {"t": "presence", "name": name, "state": state}
    if person != "__none__":
        c["person"] = person
    return nostr.build_event(key.ask, KIND_LIVE, json.dumps(c), [["h", ROOM], ["owner", key.ppk, key.bind]], created_at=at)


# --- the automatic status ---------------------------------------------------------------------------------------

async def test_automatic_status_follows_the_two_times(bare):
    e, _ = bare()
    away(e)
    assert e.auto_status() == "away"                       # nothing since the engine started
    seen(e, focused_ago=PRESENT_FOCUS - 5, open_ago=PRESENT_FOCUS - 5)
    assert e.auto_status() == "present"
    seen(e, focused_ago=PRESENT_FOCUS + 5, open_ago=5)
    assert e.auto_status() == "idle"                       # open now, but not focused for 3 minutes
    seen(e, focused_ago=IDLE_FOCUS - 5, open_ago=IDLE_OPEN + 5)
    assert e.auto_status() == "idle"                       # not open for 15 minutes, but focused within 30
    seen(e, focused_ago=IDLE_FOCUS + 5, open_ago=IDLE_OPEN + 5)
    assert e.auto_status() == "away"
    seen(e, focused_ago=None, open_ago=IDLE_OPEN - 5)
    assert e.auto_status() == "idle"                       # open, never focused


async def test_here_records_open_always_and_focused_only_when_focused(bare):
    e, _ = bare()
    away(e)
    e.here(False)
    assert e._last_open_at > 0 and e._last_focused_at == 0.0
    assert e.auto_status() == "idle"
    e.here(True)
    assert e._last_focused_at > 0 and e.auto_status() == "present"


async def test_a_post_or_typing_counts_as_activity_whichever_client_sent_it(bare):
    e, _ = bare()
    away(e)
    await e.post(ROOM, "hello")
    assert e._last_focused_at > 0
    away(e)
    e.events[ROOM] = e.events.get(ROOM, {})
    await e.typing_signal(ROOM)
    assert e._last_focused_at > 0


# --- manual status ----------------------------------------------------------------------------------------------

async def test_a_manual_status_holds_only_while_the_owner_is_around(bare):
    e, _ = bare()
    e.save_settings({"status_mode": "dnd"})
    seen(e, focused_ago=None, open_ago=60)
    assert e.person_status() == "dnd"
    seen(e, focused_ago=None, open_ago=IDLE_OPEN + 60)
    assert e.person_status() == "away"                     # not around any more: the manual choice lapses
    for mode in ("present", "idle"):
        e.save_settings({"status_mode": mode})
        seen(e, open_ago=10)
        assert e.person_status() == mode
        seen(e, open_ago=IDLE_OPEN + 10)
        assert e.person_status() == "away"


async def test_invisible_always_shows_away_and_auto_follows_the_clock(bare):
    e, _ = bare()
    e.save_settings({"status_mode": "invisible"})
    seen(e, focused_ago=1, open_ago=1)
    assert e.person_status() == "away" and e.auto_status() == "present"
    e.save_settings({"status_mode": "auto"})
    assert e.person_status() == "present"


async def test_unknown_modes_and_shares_are_cleaned(bare):
    e, _ = bare()
    e.save_settings({"status_mode": "bogus", "away_mode": "loud", "stranger_share": 0.6})
    s = e.settings()
    assert (s["status_mode"], s["away_mode"], s["stranger_share"]) == ("auto", "named", 0.5)
    e.save_settings({"stranger_share": 0.1})
    assert e.settings()["stranger_share"] == 0.25
    assert _share_ok("x") == 0.5 and _share_ok(float("nan")) == 0.5 and _share_ok(9) == 0.75


# --- published in the beat ---------------------------------------------------------------------------------------

async def test_the_status_rides_in_the_existing_presence_beat(bare):
    e, _ = bare()
    seen(e, focused_ago=1, open_ago=1)
    await e._presence_once()
    await settle(e)
    (b,) = beats(e)
    assert b["person"] == "present"
    assert [ev["kind"] for ev in e.pool.sent] == [KIND_LIVE]   # no separate event
    e.save_settings({"status_mode": "invisible"})
    await settle(e)
    assert beats(e)[-1]["person"] == "away"


async def test_a_status_change_costs_at_most_one_extra_beat_per_gap(bare):
    e, _ = bare(ts=0.1)                                       # the 30 s gap is 3 s here
    seen(e, focused_ago=1, open_ago=1)
    await e._presence_once()
    await settle(e)
    n = len(beats(e))
    e._status_beat_at = 0.0
    e.save_settings({"status_mode": "dnd"})
    assert await wait_for(lambda: len(beats(e)) == n + 1)
    assert beats(e)[-1]["person"] == "dnd"
    e.save_settings({"status_mode": "invisible"})              # a second change inside the gap...
    e.save_settings({"status_mode": "idle"})                   # ...and a third
    await asyncio.sleep(0.2)   # fixed-wait-ok: absence of a beat inside a 3 s gap
    assert len(beats(e)) == n + 1                              # waits for the gap, sends nothing yet
    assert e._status_beat_waiting                              # exactly one waiter, not one per change
    await wait_for(lambda: len(beats(e)) == n + 2, timeout=6)
    assert beats(e)[-1]["person"] == "idle"                    # and says what is true by then
    await settle(e)
    assert len(beats(e)) == n + 2


async def test_no_extra_beat_when_nothing_changed(bare):
    e, _ = bare()
    seen(e, focused_ago=1, open_ago=1)
    await e._presence_once()
    await settle(e)
    n = len(beats(e))
    e.here(True)
    e.here(True)
    e.save_settings({"line": "same status"})
    await settle(e)
    assert len(beats(e)) == n


# --- received ---------------------------------------------------------------------------------------------------

async def test_received_status_is_parsed_strictly(bare):
    e, _ = bare()
    bo = Key("bo")
    for given, parsed in (("present", "present"), ("idle", "idle"), ("dnd", "dnd"), ("away", "away"),
                          ("Present", None), ("online", None), ("", None), (7, None), (["present"], None), (None, None)):
        await e._on_event(beat(bo, given, at=int(time.time())), "relay")
        assert e.presence[ROOM][bo.apk]["person"] == parsed, given
        assert _person_claim(given) == parsed
    await e._on_event(beat(bo), "relay")                       # no field at all: an older client
    assert e.presence[ROOM][bo.apk]["person"] is None


async def test_members_show_each_person_by_their_own_status_apart_from_their_agent(bare):
    e, _ = bare()
    await e._presence_once()                                   # my own beat: I am a member too
    await settle(e)
    a, b, c, d = Key("a"), Key("b"), Key("c"), Key("d")
    for k, person, name in ((a, "present", "Pia"), (b, "idle", "Ian"), (c, "dnd", "Dee"), (d, "away", "Abe")):
        await e._on_event(k.person({"t": "msg", "name": name, "text": "hi"}), "relay")
        await e._on_event(beat(k, person, state="activity: idle", name=name + "'s agent"), "relay")
    by = {m["name"]: m for m in e.members(ROOM)}
    assert {n: by[n]["status"] for n in ("Pia", "Ian", "Dee", "Abe")} == {"Pia": "present", "Ian": "idle", "Dee": "dnd", "Abe": "away"}
    assert all(by[n]["online"] for n in ("Pia", "Ian", "Dee", "Abe"))   # their agents are all up, whatever the person is
    order = [m["name"] for m in e.members(ROOM)]
    assert e.members(ROOM)[0]["you"] and order[1] == "Pia"      # me, then present
    assert order.index("Pia") < min(order.index("Ian"), order.index("Dee")) < order.index("Abe")


async def test_a_beat_without_a_status_is_unknown_and_shows_as_the_old_online_away(bare):
    e, _ = bare()
    old, gone = Key("old"), Key("gone")
    await e._on_event(old.person({"t": "msg", "name": "Olly", "text": "hi"}), "relay")
    await e._on_event(beat(old), "relay")
    await e._on_event(gone.person({"t": "msg", "name": "Gail", "text": "hi"}), "relay")
    by = {m["name"]: m for m in e.members(ROOM)}
    assert by["Olly"]["status"] == "unknown" and by["Olly"]["online"] is True
    assert by["Gail"]["status"] == "away" and by["Gail"]["online"] is False


async def test_no_fresh_beat_at_all_is_away(bare):
    e, _ = bare()
    k = Key("k")
    await e._on_event(k.person({"t": "msg", "name": "Kit", "text": "hi"}), "relay")
    await e._on_event(beat(k, "present"), "relay")
    assert {m["name"]: m["status"] for m in e.members(ROOM)}["Kit"] == "present"
    e.presence[ROOM][k.apk]["at"] = time.time() - ABSENT_AFTER - 1
    assert {m["name"]: m["status"] for m in e.members(ROOM)}["Kit"] == "away"


async def test_the_room_list_counts_people_present_or_idle(bare):
    e, _ = bare()
    keys = [Key(s) for s in "abcdef"]
    for k, person, name in zip(keys, ("present", "idle", "dnd", "away", None, None), ("A", "B", "C", "D", "E", "F")):
        await e._on_event(k.person({"t": "msg", "name": name, "text": "hi"}), "relay")
        await e._on_event(beat(k, person or "__none__"), "relay")
    # A and B by status, E by the old rule (a beat with no status); C is dnd, D away, and F is an agent too, so counted
    seen(e, focused_ago=1, open_ago=1)
    room = next(r for r in e.snapshot()["rooms"] if r["id"] == ROOM)
    assert room["online"] == 1 + 2 + 2                           # me, A and B, and E and F (old clients)


async def test_a_friend_gets_a_status_from_any_room_we_share(bare):
    e, _ = bare()
    e.store.save_room(ROOM2, {"id": ROOM2, "name": "second"})
    friend = Key("friend")
    ev = nostr.build_event(friend.ask, KIND_LIVE, json.dumps({"t": "presence", "name": "Fay", "state": "activity: idle",
                                                              "person": "dnd"}),
                           [["h", ROOM2], ["owner", friend.ppk, friend.bind]])
    e.events.setdefault(ROOM2, {})
    e._on_live(ROOM2, ev, json.loads(ev["content"]))
    e.store.friend_event(friend.ppk, side="mine", action="yes", at=int(time.time()) - 5)
    e.store.friend_event(friend.ppk, side="theirs", action="yes", at=int(time.time()) - 5)
    assert e.store.dm_threads(), "a friend has a row"
    assert e._status_map()[friend.ppk] == ("dnd", True)
    assert e._status_map(ROOM).get(friend.ppk) is None           # not in the first room
    rows = e.dm_summary()["threads"]
    assert rows and rows[0]["status"] == "dnd" and rows[0]["online"] is True


# --- away_mode --------------------------------------------------------------------------------------------------

def claims(e):
    return [json.loads(ev["content"]) for ev in e.pool.sent if json.loads(ev["content"]).get("t") == "claim"]


async def named(e, k, text="Ada, what do you think?"):
    await e._on_event(k.person({"t": "msg", "name": "Mal", "text": text}), "relay")
    await settle(e)


async def test_away_named_answers_only_a_person_who_names_it(bare):
    e, llm = bare()
    e.save_settings({"chattiness": "lively"})
    away(e)
    mal = Key("mal")
    await named(e, mal, "just chatting about shaders")
    assert llm.calls == [] and claims(e) == []                  # no chattiness roll, no claim
    await named(e, mal)
    assert llm.calls.count("ninsei.reply") == 1                 # named: answered
    sam = Key("sam")
    await e._on_event(beat(sam, "away", name="Bo"), "relay")
    await e._on_event(sam.agent({"t": "msg", "name": "Bo", "text": "Ada, hello from an agent"}), "relay")
    await settle(e)
    assert llm.calls.count("ninsei.reply") == 1                 # an agent naming it is not a person naming it


async def test_away_named_answers_a_reply_to_its_own_message(bare):
    e, llm = bare()
    away(e)
    mine = e._identity()
    await e._publish_room(ROOM, True, {"t": "msg", "text": "something earlier"})
    await settle(e)
    mid = [ev for ev in e.pool.sent if ev["pubkey"] == mine["agent_pk"]][-1]
    e.events[ROOM][mid["id"]] = mid
    mal = Key("mal")
    await e._on_event(mal.person({"t": "msg", "name": "Mal", "text": "why though?", "reply": mid["id"]},
                                 tags=[["e", mid["id"], "", "reply"]]), "relay")
    await settle(e)
    assert llm.calls.count("ninsei.reply") == 1


async def test_away_quiet_answers_no_one_but_the_owner_and_claims_nothing(bare):
    e, llm = bare()
    e.save_settings({"away_mode": "quiet"})
    away(e)
    await named(e, Key("mal"))
    assert llm.calls == [] and claims(e) == []                   # no reply and no floor claim
    assert e.agent_state == "activity: idle"
    await e._on_event(own_person_event(e, {"t": "msg", "text": "Ada, you there?"}), "relay")
    await settle(e)
    assert llm.calls.count("ninsei.reply") == 1                  # my owner is always answered


async def test_away_chat_is_todays_behaviour(bare):
    e, llm = bare()
    e.save_settings({"away_mode": "chat"})
    away(e)
    await named(e, Key("mal"))
    assert llm.calls.count("ninsei.reply") == 1


@pytest.mark.parametrize("mode", ["quiet", "named", "chat"])
async def test_at_the_screen_nothing_changes_in_any_mode(bare, mode):
    e, llm = bare()
    e.save_settings({"away_mode": mode})
    await named(e, Key("m" + mode), "Ada, hi")
    assert llm.calls.count("ninsei.reply") == 1


async def test_away_follows_the_local_rule_not_the_published_status(bare):
    e, llm = bare()
    e.save_settings({"status_mode": "present", "away_mode": "quiet"})
    away(e)
    assert e.person_status() == "away" and e.owner_away()
    e.save_settings({"status_mode": "invisible"})
    seen(e, open_ago=5)
    assert e.person_status() == "away" and not e.owner_away()    # invisible, yet at the screen: not away
    await named(e, Key("mal"))
    assert llm.calls.count("ninsei.reply") == 1
    seen(e, open_ago=IDLE_OPEN + 5)
    e._last_spoke.clear()
    await named(e, Key("mal2"))
    assert llm.calls.count("ninsei.reply") == 1                  # away by the rule: quiet


async def test_away_no_offers_in_named_or_quiet_but_chat_drafts_them(bare):
    for mode, drafts in (("named", 0), ("quiet", 0), ("chat", 1)):
        e, llm = bare(f"M{mode}")
        e.save_settings({"away_mode": mode, "offers": True})
        away(e)
        await e._maybe_offer(ROOM, "pixels")
        await settle(e)
        assert llm.calls.count("ninsei.offer") == drafts, mode


async def _table(bare, ts=0.02):
    host, _ = bare("Maya", "Ada", ts=ts)
    sam, _ = bare("Sam", "Bo", ts=ts)
    hub = [host, sam]
    host.pool, sam.pool = HubPool(hub), HubPool(hub)
    for e in (host, sam):
        for other in hub:
            if other is not e:
                await other._on_event(_presence(e), "relay")
    return host, sam


@pytest.mark.parametrize("mode,fakes", [("chat", 1), ("quiet", 0)])
async def test_game_turns_chat_plays_quiet_does_not(bare, monkeypatch, mode, fakes):
    from ninsei_engine import game
    monkeypatch.setattr(game, "FAKE_SECONDS", 2400)
    monkeypatch.setattr(game, "VOTE_SECONDS", 2400)
    host, sam = await _table(bare)
    host.save_settings({"away_mode": mode})
    away(host)
    await sam.start_tales(ROOM, 1, mode="agent")

    def answered():
        return [ev for ev in host.pool.sent if json.loads(ev["content"]).get("t") == "tales_fake"]
    if fakes:
        assert await wait_for(lambda: len(answered()) == fakes)
    else:
        assert await wait_for(lambda: (host.game_view(ROOM) or {}).get("phase") == "fakes")
        await asyncio.sleep(0.5)   # fixed-wait-ok: absence of an answer, once the round is open
    assert len(answered()) == fakes
    assert not any(json.loads(ev["content"]).get("gave_up") for ev in host.pool.sent)   # our choice, not a failure
    await sam._end_hosted(ROOM)
    await settle(host)
    await settle(sam)


# --- the stranger share: the store ------------------------------------------------------------------------------

def test_a_stranger_reservation_checks_both_limits_in_one_transaction(tmp_path):
    s = Store(tmp_path / "x.db")
    assert s.reserve("chat", 600, 1000, 500) is None and s.refused == "share"    # fits the total, not the share
    assert s.reserve("chat", 600, 500, 1000) is None and s.refused == "total"
    t = s.reserve("chat", 400, 1000, 500)
    assert t and s.stranger_used() == 400
    assert s.reserve("chat", 200, 1000, 500) is None          # 600 > 500: share
    assert s.reserve("chat", 600, 1000) is not None           # an owner call: the total only
    assert s.stranger_used() == 400 and sum(s.budget_used().values()) == 1000
    assert s.reserve("chat", 1, 1000) is None                 # the total is full for everyone
    s.settle(t, 50)   # fixed-wait-ok: Store.settle records real usage, it is not a wait
    assert s.stranger_used() == 50
    assert s.reserve("chat", 450, 1100, 500) is not None
    s.close()


def test_concurrent_stranger_reservations_cannot_overshoot_the_share(tmp_path):
    s = Store(tmp_path / "x.db")
    won, lock = [], threading.Lock()

    def go():
        t = s.reserve("chat", 70, 100_000, 1000)
        if t:
            with lock:
                won.append(t)
    threads = [threading.Thread(target=go) for _ in range(60)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(won) == 1000 // 70 and s.stranger_used() == 70 * (1000 // 70) <= 1000
    s.close()


def test_concurrent_mixed_calls_keep_the_total_and_the_share(tmp_path):
    s = Store(tmp_path / "x.db")
    results = {"o": 0, "s": 0}
    lock = threading.Lock()

    def go(i):
        stranger = i % 2 == 0
        t = s.reserve("chat", 100, 1000, 300 if stranger else None)
        if t:
            with lock:
                results["s" if stranger else "o"] += 100
    threads = [threading.Thread(target=go, args=(i,)) for i in range(40)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results["s"] <= 300 and results["s"] + results["o"] <= 1000
    assert sum(s.budget_used().values()) == results["s"] + results["o"] and s.stranger_used() == results["s"]
    s.close()


def test_an_old_database_gains_the_stranger_column(tmp_path):
    import sqlite3
    db = sqlite3.connect(str(tmp_path / "old.db"))
    db.executescript("CREATE TABLE ledger (id TEXT PRIMARY KEY, day TEXT NOT NULL, category TEXT NOT NULL, "
                     "reserved INTEGER NOT NULL, used INTEGER, created_at REAL NOT NULL, settled_at REAL);")
    db.execute("INSERT INTO ledger VALUES('a', date('now'), 'chat', 10, 10, 1, 1)")
    db.commit()
    db.close()
    s = Store(tmp_path / "old.db")
    assert s.stranger_used() == 0 and s.reserve("chat", 5, 100, 50)
    s.close()


# --- the stranger share: the engine -----------------------------------------------------------------------------

class Heavy(StubLLM):
    """Each reply is billed 400 tokens."""

    def complete(self, messages, max_tokens=None, purpose=None, task=None, **kw):
        self.calls.append(purpose)
        return Result(f"{self.name} says hello", Usage(400))


def small_budget(e, daily=1000, share=0.5, msgs=60):
    e.save_settings({"budget_daily": daily, "stranger_share": share, "msgs_daily": msgs})


async def addressed(e, k, room, text="Ada, hello?"):
    ev = nostr.build_event(k.psk, 4242, json.dumps({"t": "msg", "name": "Mal", "text": text}), [["h", room]])
    e.events.setdefault(room, {})
    await e._on_event(ev, "relay")
    await settle(e)


def rooms3(e):
    from ninsei_engine.topics import TopicTracker
    for r in (ROOM2, ROOM3):
        e.store.save_room(r, {"id": r, "name": r})
        e.events[r] = {}
        e.topics[r] = TopicTracker()


async def test_a_troll_across_rooms_cannot_pass_the_share_and_the_owner_is_still_answered(bare):
    e, llm = bare(llm=Heavy("Ada"))
    rooms3(e)
    small_budget(e, daily=4000, share=0.5)
    troll = Key("troll")
    for i in range(6):
        for room in (ROOM, ROOM2, ROOM3):
            e._last_spoke.clear()
            e._recent_posts.clear()
            e._rate.clear()                                   # the per-team and per-room caps are not what is tested
            await addressed(e, troll, room, f"Ada, question {i}?")
    used = e.store.stranger_used()
    assert 0 < used <= 2000, used                              # never past half of 4,000
    assert not any(json.loads(ev["content"]).get("system") for ev in e.pool.sent)   # and said nothing about it in rooms
    assert e.agent_state != "system: waiting"
    before = llm.calls.count("ninsei.reply")
    assert before < 18                                         # most of the troll's messages were refused
    e._last_spoke.clear()
    e._recent_posts.clear()
    await e._on_event(own_person_event(e, {"t": "msg", "text": "Ada, you there?"}), "relay")
    await settle(e)
    assert llm.calls.count("ninsei.reply") == before + 1       # my owner's message is answered afterwards
    assert e.store.stranger_used() == used                     # and is not counted as the strangers'
    bv = e.budget_view()
    assert bv["others"]["spent"] is True or bv["others"]["used"] <= bv["others"]["limit"]
    assert bv["others"]["used"] == used and bv["used"] == used + 400


async def test_owner_calls_are_never_counted_as_stranger(bare):
    e, llm = bare(llm=Heavy("Ada"))
    for i in range(3):
        e._last_spoke.clear()
        await e._on_event(own_person_event(e, {"t": "msg", "text": f"Ada, again {i}?"}), "relay")
        await settle(e)
    assert llm.calls.count("ninsei.reply") == 3
    assert e.store.stranger_used() == 0 and sum(e.store.budget_used().values()) == 1200


async def test_a_chattiness_reply_to_someone_else_is_a_stranger_call(bare):
    e, llm = bare(llm=Heavy("Ada"))
    e.save_settings({"chattiness": "lively"})
    import random
    random.seed(1)
    orig = eng_mod.random.random
    eng_mod.random.random = lambda: 0.0                       # the roll always lands
    try:
        await named(e, Key("mal"), "anyone have thoughts on shaders")
    finally:
        eng_mod.random.random = orig
    assert llm.calls.count("ninsei.reply") == 1               # priority 20: nobody named it
    assert e.store.stranger_used() == 400


async def test_the_share_halves_while_the_owner_is_away(bare):
    e, _ = bare()
    small_budget(e, daily=1000, share=0.5)
    assert e._share_now() == 0.5 and e.budget_view()["others"]["limit"] == 500
    away(e)
    assert e._share_now() == 0.25 and e.budget_view()["others"]["limit"] == 250
    assert e.budget_view()["others"]["away"] is True
    small_budget(e, daily=1000, share=0.75)
    assert e._share_now() == 0.375
    # and a stranger call is held to the halved share
    away(e)
    e.save_settings({"away_mode": "chat", "stranger_share": 0.25})
    assert e._share_now() == 0.125
    assert e.store.reserve("chat", 100, 1000, int(1000 * e._share_now())) is not None
    assert e.store.reserve("chat", 100, 1000, int(1000 * e._share_now())) is None


async def test_the_owner_keeps_at_least_the_rest_of_the_budget(bare):
    e, _ = bare()
    small_budget(e, daily=1000, share=0.75)
    token = eng_mod._TRIGGER.set("stranger")
    try:
        assert e._reserve("chat", 750)                             # a stranger's call, up to their share
        assert e._reserve("chat", 1) is None and e._refused == "share"   # and no more
    finally:
        eng_mod._TRIGGER.reset(token)
    assert e.store.reserve("chat", 250, 1000) is not None          # the owner still has the rest


async def test_messages_by_strangers_are_capped_at_the_share_and_the_owner_still_speaks(bare):
    e, llm = bare()
    e.save_settings({"msgs_daily": 8, "stranger_share": 0.25, "budget_daily": 1_000_000})
    troll = Key("troll")
    for i in range(6):
        e._last_spoke.clear()
        e._rate.clear()
        await addressed(e, troll, ROOM, f"Ada, message {i}?")
    assert llm.calls.count("ninsei.reply") == 2                  # int(8 * 0.25)
    assert e._said_today() == 2 and e._said_strangers() == 2
    assert not any(json.loads(ev["content"]).get("system") for ev in e.pool.sent)   # silent
    assert e.agent_state != "system: waiting"
    e._last_spoke.clear()
    await e._on_event(own_person_event(e, {"t": "msg", "text": "Ada, hello"}), "relay")
    await settle(e)
    assert llm.calls.count("ninsei.reply") == 3 and e._said_today() == 3 and e._said_strangers() == 2   # an owner message is not theirs
    assert e.budget_view()["others"]["spent"] is True
    away(e)
    assert e._stranger_msgs_left() == int(8 * 0.125) - 2           # halves while away


async def test_a_stranger_message_stops_at_the_total_cap_with_the_old_notice(bare):
    e, llm = bare()
    e.save_settings({"msgs_daily": 2, "stranger_share": 0.75, "budget_daily": 1_000_000})
    for i in range(2):
        e._last_spoke.clear()
        await e._on_event(own_person_event(e, {"t": "msg", "text": f"Ada, {i}"}), "relay")
        await settle(e)
    e._last_spoke.clear()
    await addressed(e, Key("mal"), ROOM, "Ada, and me?")
    assert any(json.loads(ev["content"]).get("system") == "budget" for ev in e.pool.sent)   # the total is a different story


# --- who counts as a stranger: each call site ------------------------------------------------------------------

async def test_an_offer_draft_is_a_stranger_call(bare):
    e, llm = bare()
    await e._maybe_offer(ROOM, "pixels")
    await settle(e)
    assert llm.calls.count("ninsei.offer") == 1 and e.store.stranger_used() > 0


async def test_hosting_is_the_owners_and_playing_someone_elses_game_is_a_strangers(bare, monkeypatch):
    from ninsei_engine import game
    monkeypatch.setattr(game, "FAKE_SECONDS", 2400)
    monkeypatch.setattr(game, "VOTE_SECONDS", 2400)
    host, sam = await _table(bare)
    gid = (await host.start_tales(ROOM, 1))["gid"]           # questions: Maya's own call
    assert await wait_for(lambda: sam.store.stranger_used() > 0 or "ninsei.tales.fake" in sam.brain._llm().calls)
    assert await wait_for(lambda: sam.store.stranger_used() > 0)
    assert host.store.stranger_used() == 0 and sum(host.store.budget_used().values()) > 0   # hosting: the owner's
    assert sam.store.stranger_used() > 0                                                     # Bo plays Maya's game: a stranger's
    await host._end_hosted(ROOM)
    await settle(host)
    await settle(sam)


async def test_the_stranger_share_spent_means_no_game_turn_and_no_gave_up(bare, monkeypatch):
    from ninsei_engine import game
    monkeypatch.setattr(game, "FAKE_SECONDS", 2400)
    monkeypatch.setattr(game, "VOTE_SECONDS", 2400)
    host, sam = await _table(bare)
    sam.save_settings({"budget_daily": 1000})
    assert sam.store.reserve("chat", 500, 1000, 500)          # others have used all of theirs
    await host.start_tales(ROOM, 1)
    assert await wait_for(lambda: (sam.game_view(ROOM) or {}).get("phase") == "fakes")
    await asyncio.sleep(0.5)   # fixed-wait-ok: absence of a game turn, once the round is open
    assert sam.store.stranger_used() == 500
    assert not any(json.loads(ev["content"]).get("gave_up") for ev in sam.pool.sent)
    assert sam.agent_state != "system: waiting"
    await host._end_hosted(ROOM)
    await settle(host)
    await settle(sam)


# --- the page ---------------------------------------------------------------------------------------------------

async def test_the_snapshot_carries_status_budget_split_and_settings(bare):
    e, _ = bare()
    await e._presence_once()
    await settle(e)
    snap = e.snapshot(ROOM)
    assert snap["status"] == {"mode": "auto", "shown": "present", "auto": "present", "around": True}
    assert {"status_mode", "away_mode", "stranger_share"} <= set(snap["settings"])
    assert snap["settings"]["away_mode"] == "named" and snap["settings"]["stranger_share"] == 0.5
    assert set(snap["budget"]["others"]) == {"used", "limit", "share", "away", "msgs", "msgs_limit", "spent"}
    me = next(m for m in snap["room"]["members"] if m["you"])
    assert me["status"] == "present"


async def test_the_routes_take_the_new_settings_and_here():
    import importlib.util
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "dashboard" / "plugin_api.py").read_text()
    assert '@router.post("/here")' in src and "class HereIn" in src and "eng.here" in src
    for field in ("status_mode", "away_mode", "stranger_share"):
        assert f"    {field}:" in src
