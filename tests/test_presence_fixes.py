"""Regression tests for the review of the status / away / stranger-share work. Each one failed before its fix."""
import ast
import asyncio
import json
import re
import threading
import time
from pathlib import Path

from conftest import _no_public_relays, _owner_at_the_screen  # noqa: F401  (autouse fixtures)
from ninsei_engine import engine as eng_mod
from ninsei_engine import nostr
from ninsei_engine.engine import IDLE_OPEN, KIND_LIVE, PACE_LIMIT, PACE_OWNER_RESERVE, _plays_claim
from test_engine import Result, StubLLM, Usage, wait_for
from start_helpers import started
from test_hostile import ROOM, Key, bare, own_person_event, settle  # noqa: F401
from test_presence import Heavy, ROOM2, ROOM3, _table, away, claims, rooms3, seen, small_budget


def stranger_row(e, tokens):
    t = e.store.reserve("chat", tokens, 10**9, 10**9)
    e.store.settle(t, tokens)


def said_by(e, room):
    return [json.loads(x["content"]) for x in e.pool.sent if x["kind"] == eng_mod.KIND_ROOM
            and json.loads(x["content"]).get("t") == "msg" and nostr.first_tag(x, "h")[1] == room]


# ---- 1: a call that cannot fit the share never claims the floor ----------------------------------------------------

async def test_no_claim_when_the_share_left_cannot_fit_the_call(bare, monkeypatch):
    e, llm = bare(llm=Heavy("Ada"))
    small_budget(e, daily=4000, share=0.25)          # others may use 1,000
    stranger_row(e, 900)                             # 100 left: more than 0, less than any reply's estimate
    assert not e._strangers_spent()
    e.save_settings({"chattiness": "lively"})
    monkeypatch.setattr(eng_mod.random, "random", lambda: 0.0)
    mal = Key("mal")
    for i in range(3):
        e._last_spoke.clear(); e._recent_posts.clear(); e._rate.clear()
        await e._on_event(mal.person({"t": "msg", "name": "Mal", "text": f"shaders are neat {i}"}), "relay")
        await settle(e)
    assert llm.calls == [] and claims(e) == []        # no call, and no claim for one either


async def test_the_estimate_the_check_uses_is_the_one_reserve_asks_for(bare):
    e, llm = bare(llm=Heavy("Ada"))
    ev = Key("mal").person({"t": "msg", "name": "Mal", "text": "Ada, hi?"})
    await e._on_event(ev, "relay")
    await settle(e)
    need = e.brain.reply_estimate(e.persona(), "your owner", e._transcript(ROOM), e._line(ROOM, ev))
    seen_est = []
    real = e.store.reserve
    e.store.reserve = lambda cat, tokens, *a: (seen_est.append(tokens), real(cat, tokens, *a))[1]
    await e.brain.reply(e.persona(), "your owner", e._transcript(ROOM), e._line(ROOM, ev))
    assert seen_est == [need]


async def test_a_share_refusal_latches_until_the_day_rolls_over_or_the_limit_grows(bare, monkeypatch):
    e, llm = bare(llm=Heavy("Ada"))
    small_budget(e, daily=4000, share=0.25)
    stranger_row(e, 900)
    monkeypatch.setattr(e.brain, "reply_estimate", lambda *a: 1)   # let the pre-check pass: the reservation refuses
    await e._on_event(Key("mal").person({"t": "msg", "name": "Mal", "text": "Ada, hello?"}), "relay")
    await settle(e)
    assert e._refused == "share" and say_nothing(e)
    assert e._strangers_spent()                                   # 100 tokens are left, yet others are done today
    small_budget(e, daily=8000, share=0.25)
    assert not e._strangers_spent()                               # a bigger limit lifts it
    small_budget(e, daily=4000, share=0.25)
    assert e._strangers_spent()
    monkeypatch.setattr(eng_mod, "today", lambda: "2999-01-01")
    assert not e._strangers_spent()                               # the next day starts clean


def say_nothing(e):
    return not [x for x in e.pool.sent if x["kind"] == eng_mod.KIND_ROOM]


async def test_an_offer_that_cannot_fit_the_share_makes_no_claim(bare):
    e, llm = bare(llm=Heavy("Ada"))
    small_budget(e, daily=4000, share=0.25)
    stranger_row(e, 990)
    await e._maybe_offer(ROOM, "pixels")
    await settle(e)
    assert llm.calls == [] and claims(e) == []


# ---- 2: the owner always has a model-call slot ---------------------------------------------------------------------

class Slow(StubLLM):
    def __init__(self, name):
        super().__init__(name)
        self.gate = threading.Event()

    def complete(self, messages, max_tokens=None, purpose=None, task=None, **kw):
        self.calls.append(purpose)
        if "ask about me" not in messages[-1]["content"]:
            self.gate.wait(10)
        return Result(f"{self.name} says hi", Usage(50))


async def test_strangers_cannot_hold_every_model_slot_so_the_owner_is_answered(bare):
    e, llm = bare(llm=Slow("Ada"))
    rooms3(e)
    mal, bob = Key("mal"), Key("bob")
    for k, room in ((mal, ROOM2), (bob, ROOM3)):
        ev = nostr.build_event(k.psk, 4242, json.dumps({"t": "msg", "name": "M", "text": "Ada, hi?"}), [["h", room]])
        await e._on_event(ev, "relay")
    assert await wait_for(lambda: e._inflight == 1)
    assert e._inflight_strangers == 1
    await e._on_event(own_person_event(e, {"t": "msg", "text": "Ada, ask about me, you there?"}), "relay")
    assert await wait_for(lambda: llm.calls.count("ninsei.reply") == 2)    # the owner's call ran beside the stranger's
    llm.gate.set()
    await settle(e)
    assert e._inflight == 0 and e._inflight_strangers == 0
    assert said_by(e, ROOM)                                                   # and it was answered


# ---- 3: the owner always has room in the pacing window --------------------------------------------------------------

async def test_strangers_cannot_fill_the_pacing_window_so_the_owner_is_answered(bare):
    e, llm = bare(llm=Heavy("Ada"))
    rooms3(e)
    small_budget(e, daily=100000, share=0.75)
    e.save_settings({"offers": False})
    trolls = [Key(f"t{i}") for i in range(PACE_LIMIT)]
    for i, k in enumerate(trolls):
        e._last_spoke.clear(); e._rate.clear()
        room = (ROOM2, ROOM3)[i % 2]
        ev = nostr.build_event(k.psk, 4242, json.dumps({"t": "msg", "name": f"Troll{i}", "text": f"Ada, question {i}?"}), [["h", room]])
        await e._on_event(ev, "relay")
        await settle(e)
    assert llm.calls.count("ninsei.reply") == PACE_LIMIT - PACE_OWNER_RESERVE    # others stop short of the limit
    e._last_spoke.clear()
    await e._on_event(own_person_event(e, {"t": "msg", "text": "Ada, you there?"}), "relay")
    await settle(e)
    assert llm.calls.count("ninsei.reply") == PACE_LIMIT - PACE_OWNER_RESERVE + 1    # my owner is answered
    # and the total cap stays: relays limit per IP
    for _ in range(PACE_OWNER_RESERVE):
        e._last_spoke.clear()
        await e._on_event(own_person_event(e, {"t": "msg", "text": "Ada, again?"}), "relay")
        await settle(e)
    assert len(e._recent_posts) <= PACE_LIMIT


# ---- 4/5: presence beats -------------------------------------------------------------------------------------------

async def test_a_one_room_beat_does_not_mark_the_status_published_for_every_room(bare):
    e, _ = bare()
    rooms3(e)
    e.here(True)
    await e._presence_once()
    await settle(e)
    assert e._person_pub == "present"
    n0 = len(e.pool.sent)
    e._last_focused_at = time.time() - 200            # drifted to idle
    await e._presence_once(only=ROOM)                 # e.g. a game turn it gave up on
    assert e._person_pub == "present"                 # the other two rooms have not heard "idle"
    e._status_check()                                 # so the change still earns its one extra beat
    await settle(e)
    told = {nostr.first_tag(x, "h")[1]: json.loads(x["content"]).get("person")
            for x in e.pool.sent[n0:] if x["kind"] == KIND_LIVE}
    assert told == {ROOM: "idle", ROOM2: "idle", ROOM3: "idle"}


# ---- 6/7: "named" only plays games that were running when the owner left; the host is told -------------------------

def tales_rounds(e):
    return [ev for ev in e.events[ROOM].values() if json.loads(ev["content"]).get("t") == "tales_round"]


def answered(e):
    return [ev for ev in e.pool.sent if json.loads(ev["content"]).get("t") == "tales_fake"]


async def test_named_does_not_play_a_game_that_started_after_the_owner_left(bare, monkeypatch):
    from ninsei_engine import game
    monkeypatch.setattr(game, "FAKE_SECONDS", 2400)
    monkeypatch.setattr(game, "VOTE_SECONDS", 2400)
    host, sam = await _table(bare)
    host.save_settings({"away_mode": "named"})
    away(host)
    await started(sam, ROOM, 1, mode="agent")
    assert await wait_for(lambda: tales_rounds(host))
    await settle(host)
    assert answered(host) == [] and host._plays_in(ROOM) is False
    # the host was told, in a beat for this room, so it does not wait out the round for an agent that won't write
    assert await wait_for(lambda: any(b.get("plays") is False for b in
                                      (json.loads(x["content"]) for x in host.pool.sent if x["kind"] == KIND_LIVE)))
    assert not any(json.loads(ev["content"]).get("gave_up") for ev in host.pool.sent)
    await sam._end_hosted(ROOM)
    await settle(host)
    await settle(sam)


async def test_an_agent_that_sits_out_shows_as_sitting_out_not_writing(bare, monkeypatch):
    """Found live 2026-11-07: the host closed the round without waiting for Bo, but its panel still said "writing"."""
    from ninsei_engine import game
    monkeypatch.setattr(game, "FAKE_SECONDS", 2400)
    monkeypatch.setattr(game, "VOTE_SECONDS", 2400)
    host, sam = await _table(bare)
    host.save_settings({"away_mode": "named"})
    away(host)
    await started(sam, ROOM, 1, mode="agent")
    assert await wait_for(lambda: tales_rounds(host))
    await settle(host)
    status = lambda e, pk: next((a["status"] for a in (e.game_view(ROOM) or {}).get("agents", []) if a["pk"] == pk), None)
    mine = host._identity()["agent_pk"]
    assert status(host, mine) == "sitting_out"                          # my own panel says it too
    assert await wait_for(lambda: status(sam, mine) == "sitting_out")  # the game's host, from the beat
    await sam._end_hosted(ROOM)
    await settle(host)
    await settle(sam)


async def test_named_keeps_playing_the_game_that_was_running_when_the_owner_left(bare, monkeypatch):
    from ninsei_engine import game
    monkeypatch.setattr(game, "FAKE_SECONDS", 24000)
    monkeypatch.setattr(game, "VOTE_SECONDS", 24000)
    host, sam = await _table(bare)
    host.save_settings({"away_mode": "named"})
    gate = asyncio.Event()
    real = host._play_round

    async def gated(*a, **k):
        await gate.wait()
        return await real(*a, **k)
    monkeypatch.setattr(host, "_play_round", gated)
    await started(sam, ROOM, 1, mode="agent")
    assert await wait_for(lambda: tales_rounds(host))
    for ev in host.events[ROOM].values():             # the game began long before the owner left
        if json.loads(ev["content"]).get("t") == "tales_start":
            host._arrived[ev["id"]] = time.time() - 300
            ev["created_at"] = int(time.time()) - 300
    seen(host, open_ago=IDLE_OPEN + 100)
    gate.set()
    assert await wait_for(lambda: len(answered(host)) == 1)
    assert host._plays_in(ROOM) is True
    host._touch(True)                                  # back: the record is forgotten
    assert host._away_games is None
    await sam._end_hosted(ROOM)
    await settle(host)
    await settle(sam)


async def test_the_beat_carries_plays_false_only_when_the_agent_will_not_take_turns(bare):
    e, _ = bare()
    e.save_settings({"away_mode": "quiet"})
    assert "plays" not in json.loads((await _beat_after(e))["content"])    # at the screen: it plays whatever the setting
    away(e)
    assert json.loads((await _beat_after(e))["content"])["plays"] is False
    e.save_settings({"away_mode": "chat"})
    assert "plays" not in json.loads((await _beat_after(e))["content"])
    e.save_settings({"away_mode": "quiet"})
    e._touch(True)                                       # owner at the screen: it plays whatever the setting
    assert "plays" not in json.loads((await _beat_after(e))["content"])


async def _beat_after(e):
    n = len(e.pool.sent)
    await e._presence_once()
    await settle(e)
    return [x for x in e.pool.sent[n:] if x["kind"] == KIND_LIVE][-1]


def test_plays_is_parsed_strictly_as_a_bool():
    assert _plays_claim(False) is False and _plays_claim(True) is True
    for junk in (0, 1, "false", None, [], {}, "no"):
        assert _plays_claim(junk) is None


async def test_a_host_does_not_wait_for_an_agent_that_said_it_does_not_play(bare):
    host, sam = await _table(bare)
    room = ROOM
    me = host._identity()["agent_pk"]
    ppk = sam._identity()["agent_pk"]
    people, agents = host._present_players(room, me)
    assert ppk in agents and sam._identity()["person_pk"] in people
    assert ppk in host._waiting_on(room, people, agents)
    host.presence[room][ppk]["plays"] = False
    waits = host._waiting_on(room, people, agents)
    assert ppk not in waits and sam._identity()["person_pk"] not in waits       # nor for its owner, who is away
    assert host._waiting_on(room, people, agents, agents_too=False) == people - {sam._identity()["person_pk"]}
    host.presence[room][ppk]["plays"] = None                                    # an older host/client: waits as before
    assert ppk in host._waiting_on(room, people, agents)


# ---- 8: state and the message count ------------------------------------------------------------------------------

async def test_two_stranger_messages_cannot_both_take_the_last_share_slot(bare):
    e, llm = bare()
    rooms3(e)
    small_budget(e, daily=100000, share=0.5, msgs=2)          # others may say 1 message
    await asyncio.gather(e._say(ROOM, "one", stranger=True), e._say(ROOM2, "two", stranger=True))
    assert e._said_strangers() == 1 and e._said_today() == 1  # the second saw the first's slot, not the old count
    assert e.agent_state != "activity: working"
    assert len([1 for r in (ROOM, ROOM2) for _ in said_by(e, r)]) == 1


async def test_a_message_slot_is_given_back_when_the_publish_does_not_happen(bare):
    e, _ = bare()
    n0 = e._said_today()
    try:
        await e._say("0000000000000000", "hello")             # not a joined room: RoomLeft
    except eng_mod.RoomLeft:
        pass
    assert e._said_today() == n0 and e._said_strangers() == 0
    assert e.agent_state != "activity: speaking"


async def test_the_state_is_not_left_at_working_when_the_message_share_closes_during_the_call(bare, monkeypatch):
    e, llm = bare(llm=Heavy("Ada"))
    small_budget(e, daily=100000, share=0.5, msgs=2)
    real = e.brain.reply

    async def reply(*a, **k):
        text = await real(*a, **k)
        e.store.set("said", {"day": eng_mod.today(), "n": 1, "ns": 1})   # another reply took the last one meanwhile
        return text
    monkeypatch.setattr(e.brain, "reply", reply)
    await e._on_event(Key("mal").person({"t": "msg", "name": "Mal", "text": "Ada, hi?"}), "relay")
    await settle(e)
    assert llm.calls.count("ninsei.reply") == 1
    assert e.agent_state == "activity: idle"


# ---- 9: every model call names its trigger -----------------------------------------------------------------------

async def test_the_default_trigger_is_the_safe_one_and_my_own_game_is_charged_to_my_owner(bare):
    import pytest
    assert eng_mod._TRIGGER.get() == "stranger"
    e, llm = bare(llm=Heavy("Ada"))
    small_budget(e, daily=100000, share=0.25)
    stranger_row(e, 25000)                                    # others' share is used up exactly
    with pytest.raises(ValueError) as err:                    # (the stub's text is not JSON: no questions)
        await started(e, ROOM, 1, mode="tales")
    assert "budget" not in str(err.value) and "ninsei.tales.questions" in llm.calls
    assert e.store.stranger_used() == 25000                   # the questions were my owner's, not others'


# Every `self.brain.<method>(...)` call in engine.py, by enclosing function, and what it must say. A new call site
# fails this test until it is classified here; classify it by who triggered the call, and set _TRIGGER to match.
BRAIN_CALLS = {
    ("_maybe_reply", "available"): None,
    ("_maybe_reply", "reply_estimate"): None,
    ("_maybe_reply", "reply"): '_TRIGGER.set("stranger" if stranger else "owner")',
    ("_maybe_offer", "available"): None,
    ("_maybe_offer", "offer_estimate"): None,
    ("_maybe_offer", "offer"): '_TRIGGER.set("stranger")',
    ("start_tales", "available"): None,
    ("_start_tales", "questions"): '_triggered("owner")',
    ("_answer_as_host", "fake"): '_triggered("owner")',
    ("_answer_as_host", "human_answer"): '_triggered("owner")',
    ("_play_round", "available"): None,
    ("_play_round", "human_answer"): '_TRIGGER.set("stranger")',
    ("_play_round", "fake"): '_TRIGGER.set("stranger")',
    ("status", "available"): None,
}


def brain_call_sites():
    tree = ast.parse((Path(eng_mod.__file__)).read_text())
    out = {}
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for n in ast.walk(fn):
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Attribute) and n.value.attr == "brain" \
                        and isinstance(n.value.value, ast.Name) and n.value.value.id == "self":
                    out.setdefault((fn.name, n.attr), ast.get_source_segment(Path(eng_mod.__file__).read_text(), fn))
    return out


def test_every_brain_call_site_is_classified_and_names_its_trigger():
    sites = brain_call_sites()
    # a method of the same name nested in a different function is a different site, so match on the enclosing one
    unknown = {k for k in sites if k not in BRAIN_CALLS and k[0] not in ("status_view", "snapshot", "_snapshot")
               and k[1] != "available"}
    assert not unknown, f"classify these in BRAIN_CALLS (who triggers the call?): {sorted(unknown)}"
    for (fn, method), marker in BRAIN_CALLS.items():
        if marker is None or (fn, method) not in sites:
            continue
        assert marker in sites[(fn, method)], f"{fn} calls brain.{method} without {marker}"
    for (fn, method), marker in BRAIN_CALLS.items():
        if marker is not None:
            assert (fn, method) in sites, f"BRAIN_CALLS lists {fn}.{method}, which is gone: update the table"
