"""Agents must actually answer (Justin's live game, 2026-11-07).

The host's own agent plays: its fake is written with the questions, sealed to itself like any answer, and counts
for the host's team under the same rules (the team can't vote for it, the lucky rule, only present players).
Other agents no longer wait 2-7 s before writing, and an agent with no answer says so in the game panel.
Plus the "How to play" panel and the Games menu, run under node like the other UI tests."""
import json
import random

import pytest

from ninsei_engine import brain as brain_mod
from ninsei_engine import engine as engine_mod
from ninsei_engine import game
from ninsei_engine.engine import KIND_LIVE, SEALED_CHARS, _gave_up_claim, open_fake
from test_audit_ui import ROOT, TALES, ROOM as ROOM_JS, fn, needs_node, run as run_node, const
from test_engine import Result, StubLLM, Usage, wait_for
from test_game_secrecy import HubPool, _fakes, _presence, _vote_open
from test_hostile import ROOM, Key, bare, settle  # noqa: F401  (fixture re-export)


class Llm(StubLLM):
    """The stub, with the host's question call and each agent's fake under the test's control."""

    def __init__(self, name, fake_for_question="", fake_reply=None):
        super().__init__(name)
        self.fake_for_question, self.fake_reply = fake_for_question, fake_reply

    def complete(self, messages, max_tokens=None, purpose=None, task=None, **kw):
        if purpose == "ninsei.tales.questions":
            self.calls.append(purpose)
            q = {"q": "Octopuses have how many hearts?", "a": "three"}
            if self.fake_for_question is not None:
                q["fake"] = self.fake_for_question
            return Result(json.dumps({"questions": [q]}), Usage(90))
        if purpose == "ninsei.tales.fake" and self.fake_reply is not None:
            self.calls.append(purpose)
            return Result(self.fake_reply, Usage(20))
        return super().complete(messages, max_tokens, purpose, task, **kw)


async def _table(bare, host_llm, sam_llm=None):
    """Maya (host, agent Ada), Sam (agent Bo) and Eve, who hears everything and plays no part."""
    host, _ = bare("Maya", "Ada", ts=0.02, llm=host_llm)
    sam, _ = bare("Sam", "Bo", ts=0.02, llm=sam_llm or Llm("Bo", None))
    eve, _ = bare("Eve", "Evi", ts=0.02)
    hub = [host, sam, eve]
    host.pool, sam.pool = HubPool(hub), HubPool(hub)
    eve.brain.available = lambda: False
    for e in (host, sam):
        for other in hub:
            if other is not e:
                await other._on_event(_presence(e), "relay")
    return host, sam, eve


def _long(monkeypatch):
    monkeypatch.setattr(game, "FAKE_SECONDS", 2400)   # a phase ends when everyone is in
    monkeypatch.setattr(game, "VOTE_SECONDS", 2400)


def _host_fake_events(eve, host):
    pk = host._identity()["agent_pk"]
    return [ev for ev in _fakes(eve) if ev["pubkey"] == pk]


async def test_the_hosts_agent_plays_with_a_fake_written_alongside_the_questions(bare, monkeypatch):
    _long(monkeypatch)
    llm = Llm("Ada", "five")
    host, sam, eve = await _table(bare, llm)
    gid = (await host.start_tales(ROOM, 1))["gid"]
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "fakes")
    await sam.submit_fake(ROOM, gid, 1, "seven")
    await host.submit_fake(ROOM, gid, 1, "nine")
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "vote")
    texts = {o["text"] for o in eve.game_view(ROOM)["options"]}
    assert texts == {"three", "five", "seven", "nine", "Bo hearts"}
    assert "ninsei.tales.fake" not in llm.calls   # no extra model call: it came with the questions
    assert llm.calls.count("ninsei.tales.questions") == 1
    # sealed to itself like any answer: one event, one size, nothing readable to Eve, only the host opens it
    [ev] = _host_fake_events(eve, host)
    c = json.loads(ev["content"])
    assert len(c["enc"]) == SEALED_CHARS and "five" not in ev["content"] and "text" not in c
    ident = host._identity()
    assert open_fake(ident["agent_sk"], ident["agent_pk"], c["enc"])["text"] == "five"
    assert open_fake(eve._identity()["agent_sk"], ident["agent_pk"], c["enc"]) is None
    # nothing about the question list reached the room with the fake in it
    assert not any('"fake"' in e["content"] and '"a"' in e["content"] for e in host.pool.sent)
    await host._end_hosted(ROOM)
    await settle(host)


async def test_the_hosts_agent_fake_follows_the_secrecy_rules(bare, monkeypatch):
    """Equal decoy-padded claim counts, the host's team can't vote for it (Maya's vote is refused, Sam's counts
    for Maya's team), and the host person's own view blocks it."""
    _long(monkeypatch)
    host, sam, eve = await _table(bare, Llm("Ada", "five"))
    gid = (await host.start_tales(ROOM, 1))["gid"]
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "fakes")
    await sam.submit_fake(ROOM, gid, 1, "seven")
    await host.submit_fake(ROOM, gid, 1, "nine")
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "vote")
    vote = _vote_open(eve)
    by_text = {o["text"]: o["id"] for o in vote["options"]}
    assert len({len(v) for v in vote["claims"].values()}) == 1 and list(vote["claims"]) == [o["id"] for o in vote["options"]]
    assert by_text["five"] in host.game_view(ROOM)["blocked"]       # Maya sees it as her team's
    assert by_text["five"] not in sam.game_view(ROOM)["blocked"] and by_text["five"] not in eve.game_view(ROOM)["blocked"]
    await host.submit_vote(ROOM, gid, 1, by_text["five"])            # a modified client: the host refuses it
    await sam.submit_vote(ROOM, gid, 1, by_text["five"])             # Sam is fooled by Maya's agent
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "end")
    scores = eve.game_view(ROOM)["scores"]
    maya, sam_pk = host._identity()["person_pk"], sam._identity()["person_pk"]
    assert scores == {maya: 1}, scores    # Maya +1 for fooling Sam; her own vote for her agent gave her nothing
    reveal = [json.loads(ev["content"]) for ev in eve.events[ROOM].values()
              if json.loads(ev["content"]).get("t") == "tales_reveal"][-1]
    assert reveal["authors"][by_text["five"]] == host._identity()["agent_pk"] and reveal["lucky"] == []
    await settle(host)


async def test_a_host_fake_equal_to_the_truth_is_dropped_and_gets_no_lucky_point(bare, monkeypatch):
    _long(monkeypatch)
    llm = Llm("Ada", "Three.", fake_reply="THREE")      # the question's fake AND the retry both match the truth
    host, sam, eve = await _table(bare, llm)
    gid = (await host.start_tales(ROOM, 1))["gid"]
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "fakes")
    await sam.submit_fake(ROOM, gid, 1, "seven")
    await host.submit_fake(ROOM, gid, 1, "nine")
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "vote", timeout=30)
    options = eve.game_view(ROOM)["options"]
    assert sorted(o["text"] for o in options) == ["Bo hearts", "nine", "seven", "three"]   # one truth, nobody's twin of it
    assert not _host_fake_events(eve, host)
    truth = next(o["id"] for o in options if o["text"] == "three")
    await sam.submit_vote(ROOM, gid, 1, truth)
    await host.submit_vote(ROOM, gid, 1, truth)
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "end")
    reveal = [json.loads(ev["content"]) for ev in eve.events[ROOM].values()
              if json.loads(ev["content"]).get("t") == "tales_reveal"][-1]
    assert reveal["lucky"] == []
    await settle(host)


async def test_a_host_fake_equal_to_the_truth_is_replaced_by_one_more_try(bare, monkeypatch):
    _long(monkeypatch)
    llm = Llm("Ada", "three", fake_reply="a pair")
    host, sam, eve = await _table(bare, llm)
    gid = (await host.start_tales(ROOM, 1))["gid"]
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "fakes")
    await sam.submit_fake(ROOM, gid, 1, "seven")
    await host.submit_fake(ROOM, gid, 1, "nine")
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "vote", timeout=30)
    assert sorted(o["text"] for o in eve.game_view(ROOM)["options"]) == ["Bo hearts", "a pair", "nine", "seven", "three"]
    assert llm.calls.count("ninsei.tales.fake") == 1
    await host._end_hosted(ROOM)
    await settle(host)


async def test_a_missing_host_fake_is_asked_for_when_the_round_opens(bare, monkeypatch):
    _long(monkeypatch)
    llm = Llm("Ada", "", fake_reply="a pair")           # the question call gave no fake
    host, sam, eve = await _table(bare, llm)
    gid = (await host.start_tales(ROOM, 1))["gid"]
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "fakes")
    await sam.submit_fake(ROOM, gid, 1, "seven")
    await host.submit_fake(ROOM, gid, 1, "nine")
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "vote", timeout=30)
    assert "a pair" in {o["text"] for o in eve.game_view(ROOM)["options"]}
    await host._end_hosted(ROOM)
    await settle(host)


async def test_only_present_players_count_beside_the_hosts_agent(bare, monkeypatch):
    _long(monkeypatch)
    host, sam, eve = await _table(bare, Llm("Ada", "five"))
    mal = Key("mal")    # never sent a presence beat: not here
    gid = (await host.start_tales(ROOM, 1))["gid"]
    assert await wait_for(lambda: (host.game_view(ROOM) or {}).get("phase") == "fakes")
    ev, _ = mal.fake(host._identity()["agent_pk"], gid, 1, "ghost answer", agent=True)
    for e in (host, eve):
        await e._on_event(ev, "relay")
    await sam.submit_fake(ROOM, gid, 1, "seven")
    await host.submit_fake(ROOM, gid, 1, "nine")
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "vote")
    assert {o["text"] for o in eve.game_view(ROOM)["options"]} == {"three", "five", "seven", "nine", "Bo hearts"}
    await host._end_hosted(ROOM)
    await settle(host)


async def test_who_is_the_agent_still_counts_the_hosts_agent_once(bare, monkeypatch):
    _long(monkeypatch)
    host, sam, eve = await _table(bare, Llm("Ada", "five"))
    gid = (await host.start_tales(ROOM, 1, mode="agent"))["gid"]
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "fakes")
    await sam.submit_fake(ROOM, gid, 1, "toast")
    await host.submit_fake(ROOM, gid, 1, "eggs")
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "vote", timeout=30)
    assert len(_host_fake_events(eve, host)) == 1
    await host._end_hosted(ROOM)
    await settle(host)


# --- the other agents: no wait, more room to think, and a visible "couldn't answer" -------------------------

def test_a_thinking_model_gets_a_thousand_tokens_and_the_jitter_is_a_hair():
    assert brain_mod.GAME_TOKENS == 1000
    assert 0 < engine_mod.FAKE_JITTER <= 0.5


async def test_agents_write_their_fakes_with_no_two_to_seven_second_wait(bare, monkeypatch):
    waits = []
    real = random.uniform
    monkeypatch.setattr(engine_mod.random, "uniform", lambda a, b: waits.append((a, b)) or real(a, b))
    host, sam, eve = await _table(bare, Llm("Ada", "five"))
    await host.start_tales(ROOM, 1)
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") in ("vote", "reveal", "end"), timeout=30)
    assert any(f.get("n") == 1 and f.get("t") == "tales_fake" for f in
               (json.loads(ev["content"]) for ev in _fakes(eve))), "Bo's fake is in"
    assert waits and all(a == 0 and b <= 0.5 for a, b in waits), waits
    await host._end_hosted(ROOM)
    await settle(host)


@pytest.mark.parametrize("reply", ["", "As an AI language model I can't play this game."])
async def test_an_agent_that_cant_answer_shows_couldnt_answer(bare, reply):
    bo = Llm("Bo", None, fake_reply=reply)
    host, sam, eve = await _table(bare, Llm("Ada", "five"), bo)
    await host.start_tales(ROOM, 1)

    def bo_status():
        view = host.game_view(ROOM) or {}
        return {a["name"]: a["status"] for a in view.get("agents", [])}.get("Bo")
    assert await wait_for(lambda: bo_status() == "gave_up", timeout=30), bo_status()
    assert sam._gave_up and sam._gave_up[1] == 1
    view = host.game_view(ROOM)
    assert {a["name"]: a["status"] for a in view["agents"]}["Ada"] == "answered"
    # the status names nobody's option and carries no text
    assert set(next(a for a in view["agents"] if a["name"] == "Bo")) == {"pk", "name", "status", "yours"}
    await host._end_hosted(ROOM)
    await settle(host)


async def test_an_agent_with_no_model_budget_or_error_also_says_so(bare):
    class Boom(Llm):
        def complete(self, *a, purpose=None, **k):
            if purpose == "ninsei.tales.fake":
                raise RuntimeError("provider down")
            return super().complete(*a, purpose=purpose, **k)
    host, sam, eve = await _table(bare, Llm("Ada", "five"), Boom("Bo", None))
    await host.start_tales(ROOM, 1)
    assert await wait_for(lambda: sam._gave_up is not None, timeout=30)
    assert await wait_for(lambda: any(a["status"] == "gave_up" for a in (host.game_view(ROOM) or {}).get("agents", [])),
                          timeout=30)
    await host._end_hosted(ROOM)
    await settle(host)


def test_a_gave_up_claim_is_only_a_game_id_and_a_round_number():
    assert _gave_up_claim({"gid": "abc", "n": 2}) == ("abc", 2)
    for bad in (None, "x", [], {}, {"gid": 5, "n": 1}, {"gid": "g" * 33, "n": 1}, {"gid": "g", "n": 0},
                {"gid": "g", "n": game.MAX_ROUNDS + 1}, {"gid": "g", "n": True}, {"gid": "g", "n": "1"},
                {"gid": ["g"], "n": 1}, {"gid": "g", "n": 1.5}):
        assert _gave_up_claim(bad) is None, bad


async def test_hostile_gave_up_fields_and_lookalike_names_change_nothing(bare):
    e, _ = bare(ts=0.02)
    host = Key("host")
    await e._on_event(host.agent({"t": "tales_start", "gid": "g", "rounds": 1, "seq": 1}), "relay")
    await e._on_event(host.agent({"t": "tales_round", "gid": "g", "n": 1, "q": "?", "secs": 45, "seq": 2,
                                  "ends_at": __import__("time").time() + 45}), "relay")
    for i, junk in enumerate([["x"], "y" * 5000, {"gid": 7, "n": {}}, {"gid": "g", "n": 10**9}, 12, None,
                              {"gid": "g", "n": 1}]):
        k = Key(f"bot{i}")
        await e._on_event(k.agent({"t": "presence", "name": "Botty", "state": "activity: idle", "gave_up": junk},
                                  kind=KIND_LIVE), "relay")
    view = e.game_view(ROOM)
    states = [a["status"] for a in view["agents"] if not a["yours"]]
    assert states.count("gave_up") <= 1 and len(view["agents"]) <= 24
    assert all(set(a) == {"pk", "name", "status", "yours"} for a in view["agents"])
    # the first key to use the name holds it; the rest are shown by their short key, never as "Botty"
    named = [a["name"] for a in view["agents"] if not a["yours"]]
    assert named.count("Botty") <= 1


# --- the explainer and the Games menu ----------------------------------------------------------------------

RULES = {"fake": game.FAKE_SECONDS, "vote": game.VOTE_SECONDS, "reveal": game.REVEAL_SECONDS, "rounds": 3}


async def test_the_view_carries_the_rules_the_clock_runs_on(bare, monkeypatch):
    _long(monkeypatch)
    host, sam, eve = await _table(bare, Llm("Ada", "five"))
    await host.start_tales(ROOM, 2)   # the stub writes one question, so one round
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "fakes")
    assert eve.game_view(ROOM)["rules"] == {"fake": 2400, "vote": 2400, "reveal": game.REVEAL_SECONDS, "rounds": 1}
    await host._end_hosted(ROOM)
    await settle(host)


@needs_node
def test_how_to_play_copy_states_the_real_numbers_and_points():
    js = fn(TALES, "howToLines") + f"""
const rules = {json.dumps(RULES)}
const flat = mode => howToLines(mode, rules).map(r => r.join(': ')).join('\\n')
out({{ tales: flat('tales'), agent: flat('agent') }})
"""
    r = run_node(js)
    for mode in ("tales", "agent"):
        text = r[mode]
        assert f"{game.FAKE_SECONDS} seconds" in text and f"{game.VOTE_SECONDS} seconds" in text
        assert f"{game.REVEAL_SECONDS} seconds" in text and "3 rounds" in text and "sealed" in text.lower()
    t = r["tales"]
    # points as scored in game.score_round: 2 for the truth, 1 per person fooled, 1 lucky
    assert "2 points" in t and "1 point for you" in t and "1 lucky point" in t and "can’t vote for your team" in t
    a = r["agent"]
    assert "1 point for you" in a and "1 point for the answer’s team" in a


@needs_node
def test_how_to_play_shows_once_per_game_then_sits_behind_a_button():
    js = (fn(TALES, "gameName") + const(TALES, "GAME_NAME") + fn(TALES, "howToLines") + fn(TALES, "HowToPlay")
          + fn(TALES, "hostShown") + fn(TALES, "TallTales") + """
function FakePhase() {}; function FlagPhase() {}; function VotePhase() {}; function WhoRevealPhase() {}; function RevealPhase() {}
function Scoreboard() {}; function Countdown() {}; function AgentStatus() {}
const Ring = function Ring() {}
const seen = {}
const P = { prefs: { get: (k, d) => (k in seen ? seen[k] : d), set: (k, v) => { seen[k] = v } } }
const useNow = () => 0
const g = over => Object.assign({ gid: 'g1', n: 1, rounds: 3, phase: 'fakes', ends_at: 0, mode: 'tales', host_name: 'Ada',
  rules: { fake: 45, vote: 30, reveal: 9, rounds: 3 } }, over)
const props = game => ({ store: {}, room: {}, game, book: {} })
const panel = r => !!find(r.tree, n => n.type === HowToPlay)
const first = mount(TallTales, props(g()))
const shownFirst = panel(first)
const hdr = !!button(first.tree, 'How to play')
find(first.tree, n => n.type === HowToPlay).props.onClose(); await settle()
const closed = !panel(first)
const second = mount(TallTales, props(g({ gid: 'g2' })))          // same install, same game mode: not shown again
const shownAgain = panel(second)
button(second.tree, 'How to play').props.onClick(); await settle()
const reopened = panel(second)
const other = mount(TallTales, props(g({ mode: 'agent', gid: 'g3' })))   // another game: its first time
const shownOther = panel(other)
out({ shownFirst, hdr, closed, shownAgain, reopened, shownOther, seen })
""")
    r = run_node(js)
    assert r["shownFirst"] and r["hdr"] and r["closed"]
    assert not r["shownAgain"] and r["reopened"] and r["shownOther"]
    assert r["seen"] == {"howto.tales": True}


@needs_node
def test_each_game_in_the_menu_starts_only_from_its_own_start_button():
    js = (fn(ROOM_JS, "GamesMenu") + """
const started = []
const P = { listen: () => () => {} }
globalThis.document = {}
const useEnter = () => ({ current: null })
function gameName(m) { return m === 'agent' ? 'Who is the Agent' : 'Tall Tales' }
const r = mount(GamesMenu, { onClose() {}, onStart: m => started.push(m), gameOn: false })
const groups = []
find(r.tree, n => { if (n.props && n.props.className === 'h-gm') groups.push(n); return false })
const rows = groups.map(g => ({ text: text(g), start: !!button(g, 'Start') }))
// clicking the row's name or blurb starts nothing
groups.forEach(g => { const name = find(g, n => n.type === 'b'); if (name && name.props.onClick) name.props.onClick() })
const before = started.slice()
groups.forEach(g => button(g, 'Start').props.onClick())
const busy = mount(GamesMenu, { onClose() {}, onStart() {}, gameOn: true })
const off = []
find(busy.tree, n => { if (n.type === K.Button && text(n) === 'Start') off.push(n.props.disabled); return false })
out({ rows, before, started, off })
""")
    r = run_node(js)
    assert len(r["rows"]) == 2 and all(x["start"] for x in r["rows"])
    assert r["before"] == [] and r["started"] == ["tales", "agent"]
    assert r["off"] == [True, True]


def test_the_tales_panel_never_labels_the_options_in_the_agent_status():
    # the status chips read presence and public answer events only, never the sealed text or an option id
    s = (ROOT / "ui" / "60_tales.js").read_text()
    chunk = s[s.index("function AgentStatus"):s.index("function TallTales")]
    assert "options" not in chunk and "authors" not in chunk and "reveal" not in chunk
