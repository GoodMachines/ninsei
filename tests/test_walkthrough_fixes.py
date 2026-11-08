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


ROOM_JS = src("50_room.js")
GAMES_MENU = fn(ROOM_JS, "GamesMenu") + """
const P = { listen: () => () => {} }
globalThis.document = {}
const useEnter = () => ({ current: null })
function gameName(m) { return m === 'agent' ? 'Who\\u2019s the Agent?' : 'Tall Tales' }
"""


@needs_node
def test_the_games_menu_says_so_when_you_are_alone_and_offers_the_code_but_still_starts():
    r = run_node(GAMES_MENU + """
const calls = []
const notesOf = r => { const l = []; find(r.tree, n => { if (n.props && n.props['data-alone']) l.push(n); return false }); return l }
const alone = mount(GamesMenu, { onClose() {}, onStart: m => calls.push('start:' + m), onShare: () => calls.push('share'), gameOn: false, alone: true })
const notes = notesOf(alone)
const texts = notes.map(n => text(n))
notes.forEach(n => button(n, 'Share code').props.onClick())
const rows = []
find(alone.tree, n => { if (n.props && n.props.className === 'h-gm') rows.push(n); return false })
rows.forEach(g => button(g, 'Start').props.onClick())
const company = mount(GamesMenu, { onClose() {}, onStart() {}, onShare() {}, gameOn: false, alone: false })
const running = mount(GamesMenu, { onClose() {}, onStart() {}, onShare() {}, gameOn: true, alone: true })
out({ texts, calls, quiet: notesOf(company).length, during: notesOf(running).length })
""")
    assert len(r["texts"]) == 2
    assert r["texts"][0].startswith("Best with 2 or more people. Share the room code to invite someone.")
    assert "Share the room code to invite someone" in r["texts"][1] and "Share code" in r["texts"][1]
    assert r["calls"].count("share") == 2 and r["calls"].count("start:tales") == 1 and "start:agent" in r["calls"]
    assert r["quiet"] == 0 and r["during"] == 0


COMPOSER_JS = __import__("test_e1_ui").COMPOSER + "const isHere = p => !!p.here\nconst copyRoomCode = () => {}\n"


@needs_node
def test_the_games_menu_is_told_you_are_alone_until_another_person_is_here():
    r = run_node(COMPOSER_JS + """
const room = members => ({ id: 'r1', name: 'club', members })
const me = { pk: 'me', name: 'Jordan', you: true, here: true, agents: [{ pk: 'a', name: 'Pixel', yours: true }] }
const sam = { pk: 's', name: 'Sam', here: false, agents: [] }
const samHere = Object.assign({}, sam, { here: true })
const alone = async members => {
  const r = mount(Composer, { store: {}, room: room(members), gamesReq: 1 }); await settle()
  return find(r.tree, n => n.type === GamesMenu).props.alone
}
out({ alone: await alone([me]), awaySam: await alone([me, sam]), hereSam: await alone([me, samHere]) })
""")
    assert r == {"alone": True, "awaySam": True, "hereSam": False}


@needs_node
def test_say_hi_fills_an_empty_box_with_the_agents_mention_and_keeps_a_draft_you_already_typed():
    r = run_node(COMPOSER_JS + """
const room = { id: 'r1', name: 'club', members: [] }
const r = mount(Composer, { store: {}, room, fillReq: { text: '@Pixel ', n: 1 } })
await settle()
const filled = area(r).props.value
DRAFTS.clear()
const two = { id: 'r2', name: 'two', members: [] }
const typed = mount(Composer, { store: {}, room: two })
area(typed).props.onChange(ev('already typing')); await settle()
typed.update({ store: {}, room: two, fillReq: { text: '@Pixel ', n: 1 } }); await settle()
out({ filled, kept: area(typed).props.value })
""")
    assert r == {"filled": "@Pixel ", "kept": "already typing"}


@needs_node
def test_a_room_with_nothing_said_gets_a_starter_panel_with_three_actions():
    r = run_node(fn(ROOM_JS, "mentionCandidates") + fn(ROOM_JS, "RoomStarter") + """
function EmptyState() {}
const isHere = p => !!p.here
const copied = []
const copyRoomCode = room => copied.push(room.id)
const calls = []
const room = { id: 'r1', name: 'club', members: [{ pk: 'me', you: true, name: 'Jordan', agents: [{ pk: 'a', name: 'Pixel', yours: true }] }] }
const tree = RoomStarter({ room, snap: { settings: { agent_name: 'Pixel' } }, onSay: t => calls.push('say:' + t), onGames: () => calls.push('games') })
const labels = []
find(tree.props.action, n => { if (n.type === K.Button) labels.push(text(n)); return false })
const act = l => find(tree.props.action, n => n.type === K.Button && text(n) === l).props.onClick()
act('Play Tall Tales'); act('Say hi to Pixel'); act('Share the room code')
out({ labels, calls, copied })
""")
    assert r["labels"] == ["Play Tall Tales", "Say hi to Pixel", "Share the room code"]
    assert r["calls"] == ["games", "say:@Pixel "] and r["copied"] == ["r1"]


def test_the_timeline_draws_the_starter_in_place_of_an_empty_timeline_and_the_controller_is_labelled():
    assert "RoomStarter" in fn(ROOM_JS, "Timeline")
    comp = fn(ROOM_JS, "Composer")
    assert "'aria-label': 'Games'" in comp and "K.Tip, { label: 'Games'" in comp
