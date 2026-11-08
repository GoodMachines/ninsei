"""Fixes from the fresh-eyes walkthrough (2026-11-07): a finished game's scoreboard and pinned card, the
how-to panel, the games menu note, the starter panel, the status popover, budget words, pending friend
requests and the Lobby's browse-all list."""
import json
import time

from ninsei_engine import game
from test_audit_ui import ROOT, fn, needs_node, run as run_node, src
from test_engine import wait_for
from test_game_agents import Llm, _long, _table
from test_hostile import ROOM, bare, settle  # noqa: F401  (fixture re-export)

TALES = src("60_tales.js")


async def test_final_scores_list_only_teams_that_took_part_and_a_late_joiner_gets_no_card(bare, monkeypatch):
    _long(monkeypatch)
    host, sam, eve = await _table(bare, Llm("Ada", "five"))
    gid = (await host.start_tales(ROOM, 1))["gid"]
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "fakes")
    await sam.submit_fake(ROOM, gid, 1, "seven")
    await host.submit_fake(ROOM, gid, 1, "nine")
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "vote")
    truth = next(o["id"] for o in eve.game_view(ROOM)["options"] if o["text"] == "three")
    await sam.submit_vote(ROOM, gid, 1, truth)
    await host.submit_vote(ROOM, gid, 1, truth)
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "end", timeout=30)
    g = eve.game_view(ROOM)
    maya, sam_pk, eve_pk = (x._identity()["person_pk"] for x in (host, sam, eve))
    # Eve wrote and voted nothing: she is not a player, and the board has nobody who did not play
    assert sorted(g["players"]) == sorted([maya, sam_pk]) and eve_pk not in g["players"]
    assert eve_pk not in g["scores"]
    # a room joined before the game ended still pins it; one joined after the end does not
    eve.store._db.execute("UPDATE rooms SET joined_at=? WHERE id=?", (int(g["last_at"]) - 5, ROOM))
    assert eve.snapshot(ROOM)["room"]["game"]["gid"] == gid
    eve.store._db.execute("UPDATE rooms SET joined_at=? WHERE id=?", (int(g["last_at"]) + 5, ROOM))
    assert eve.snapshot(ROOM)["room"]["game"] is None
    await settle(host)


@needs_node
def test_the_scoreboard_never_lists_a_team_that_did_not_play():
    r = run_node("const nameBook = () => ({})\n" + fn(TALES, "teamName") + fn(TALES, "Scoreboard") + """
const room = { members: [{ pk: 'me', you: true }] }
const game = { scores: { a: 3 }, players: ['a', 'b'], team_names: { a: 'Jordan', b: 'Pia', me: 'Me' } }
const row = Scoreboard({ game, room })
out(row.props.children.map(c => c.props.children[0].props.children))
""")
    assert r == ["Jordan", "Pia"]


HOWTO_HARNESS = (fn(TALES, "gameName") + __import__("test_audit_ui").const(TALES, "GAME_NAME") + fn(TALES, "howToLines")
                 + fn(TALES, "HowToPlay") + fn(TALES, "TallTales") + """
function FakePhase() {}; function FlagPhase() {}; function VotePhase() {}; function WhoRevealPhase() {}; function RevealPhase() {}
function Scoreboard() {}; function Countdown() {}; function AgentStatus() {}
const Ring = function Ring() {}
const seen = {}
const P = { prefs: { get: (k, d) => (k in seen ? seen[k] : d), set: (k, v) => { seen[k] = v } } }
const useNow = () => 0
const g = over => Object.assign({ gid: 'g1', n: 1, rounds: 3, phase: 'fakes', q: 'How many hearts?', ends_at: 0, mode: 'tales',
  host_name: 'Ada', rules: { fake: 45, vote: 30, reveal: 9, rounds: 3 } }, over)
const props = game => ({ store: {}, room: {}, game, book: {} })
// where the panel sits among the game panel's children: before or after the question and the answer box
const order = r => {
  const kids = (r.tree.props.children || []).flat(2).filter(Boolean)
  const at = t => kids.findIndex(k => k.type === t)
  const q = kids.findIndex(k => k.props && k.props.className === 'h-tales-q')
  return { how: at(HowToPlay), q, body: at(FakePhase) }
}
""")


@needs_node
def test_how_to_play_opens_during_the_countdown_and_never_covers_the_question_mid_round():
    r = run_node(HOWTO_HARNESS + """
const starting = mount(TallTales, props(g({ phase: 'starting', n: 0, q: '' })))
const s = order(starting)
const startOpen = find(starting.tree, n => n.type === HowToPlay).props
starting.update(props(g()))                  // the round begins while it is still unread
await settle()
const mid = mount(TallTales, props(g()))     // another install, first time, joined mid-round
const m = order(mid)
const midProps = find(mid.tree, n => n.type === HowToPlay).props
button(mid.tree, 'How to play').props.onClick()   // the button after it was dismissed would reopen below too
await settle()
out({ s, startCompact: !!startOpen.compact, m, midCompact: !!midProps.compact, afterRound: order(starting), roundCompact: !!find(starting.tree, n => n.type === HowToPlay).props.compact })
""")
    assert r["s"]["how"] == 1 and not r["startCompact"]            # during "starting": full panel right under the header
    assert r["m"]["how"] > r["m"]["q"] and r["midCompact"]          # mid-round: collapsed, below the question
    assert r["afterRound"]["how"] > r["afterRound"]["q"] and r["roundCompact"]   # the round starting moves it down


@needs_node
def test_the_how_to_play_button_reopens_it_below_the_answer_box():
    r = run_node(HOWTO_HARNESS + """
seen['howto.tales'] = true
const r = mount(TallTales, props(g()))
const none = !find(r.tree, n => n.type === HowToPlay)
button(r.tree, 'How to play').props.onClick()
await settle()
const o = order(r)
out({ none, below: o.how > o.q, compact: !!find(r.tree, n => n.type === HowToPlay).props.compact })
""")
    assert r["none"] and r["below"] and not r["compact"]
