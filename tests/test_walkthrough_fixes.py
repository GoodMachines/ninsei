"""Fixes from the fresh-eyes walkthrough (2026-11-07): a finished game's scoreboard and pinned card, the
how-to panel, the games menu note, the starter panel, the status popover, budget words, pending friend
requests and the Lobby's browse-all list."""
import json
import time

from ninsei_engine import game
from test_audit_ui import ROOT, const, fn, needs_node, run as run_node, src
from test_engine import wait_for
from test_game_agents import Llm, _long, _table
from test_hostile import ROOM, bare, settle  # noqa: F401  (fixture re-export)

TALES = src("60_tales.js")
CORE = src("00_core.js")
LABELS = fn(CORE, "squashName") + fn(CORE, "shownName") + fn(CORE, "withHostNames") + fn(CORE, "whoLabel")


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
    r = run_node("const nameBook = () => ({})\n" + LABELS + fn(TALES, "teamName") + fn(TALES, "Scoreboard") + """
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


TOOLS_JS = src("52_tools.js")
CORE_JS = src("00_core.js")
POPOVER_JS = fn(CORE_JS, "clamp") + fn(TOOLS_JS, "placePopover") + fn(TOOLS_JS, "usePopover") + """
const useLayoutEffect = useEffect
"""


@needs_node
def test_a_popover_stays_inside_the_page_flipping_or_shifting_and_never_narrower_than_280():
    r = run_node(POPOVER_JS + """
const page = { left: 0, top: 0, right: 900, bottom: 600 }
const at = (a, h) => placePopover(Object.assign({ top: 0, bottom: 0 }, a), { width: 300, height: h || 260 }, page)
out({
  narrowSidebar: at({ left: 14, right: 144, top: 20, bottom: 36 }),        // a 130px column: the popover is wider than its anchor
  rightEdge: at({ left: 800, right: 890, top: 20, bottom: 36 }),           // would overflow right: shifts left
  bottomEdge: at({ left: 14, right: 144, top: 560, bottom: 576 }),         // no room below: flips above
  tall: at({ left: 14, right: 144, top: 300, bottom: 316 }, 900),          // taller than either side: takes the bigger side, scrolls
  tinyPage: placePopover({ left: 5, right: 60, top: 10, bottom: 26 }, { width: 300, height: 200 }, { left: 0, top: 0, right: 250, bottom: 400 })
})
""")
    n = r["narrowSidebar"]
    assert n["width"] >= 280 and n["left"] == 14 and n["top"] == 42 and not n["flipped"]
    e = r["rightEdge"]
    assert e["left"] + e["width"] <= 900 - 8 and e["left"] >= 8
    b = r["bottomEdge"]
    assert b["flipped"] and b["top"] + 260 <= 560 - 6 and b["top"] >= 8
    t = r["tall"]
    assert t["maxHeight"] < 900 and t["top"] >= 8 and t["top"] + t["maxHeight"] <= 600 - 8
    assert r["tinyPage"]["width"] == 250 - 16        # the room cannot give 280: it takes what there is, inside the page


@needs_node
def test_the_status_popover_is_placed_before_paint_from_where_its_containing_block_really_is():
    r = run_node(POPOVER_JS + """
globalThis.window = {}
globalThis.document = { documentElement: { clientWidth: 1000, clientHeight: 700 } }
globalThis.P = { listen: (t, type, fn) => { listened.push(type); return () => {} } }
const listened = []
const page = { getBoundingClientRect: () => ({ left: 100, top: 50, right: 1000, bottom: 650 }) }
const anchor = { current: { getBoundingClientRect: () => ({ left: 120, right: 250, top: 70, bottom: 86 }), closest: sel => (sel === '.h-page' ? page : null) } }
// parked at 0,0 the popover lands at (100, 50): its containing block starts there, whatever element that is
const el = { style: {}, offsetWidth: 300, scrollHeight: 280, getBoundingClientRect: () => ({ left: 100, top: 50 }) }
const el2 = { style: {}, offsetWidth: 300, scrollHeight: 280, getBoundingClientRect: () => ({ left: 0, top: 0 }) }   // the viewport
function Probe(props) { usePopover(props.ref, props.anchor); return null }
mount(Probe, { ref: { current: el }, anchor })
mount(Probe, { ref: { current: el2 }, anchor })
out({ style: el.style, style2: el2.style, listened })
""")
    s = r["style"]
    assert s["left"] == "20px" and s["top"] == "42px" and s["width"] == "300px"   # (120-100, 86+6-50)
    s2 = r["style2"]
    assert s2["left"] == "120px" and s2["top"] == "92px"                           # the same spot on screen
    assert r["listened"] == ["resize", "resize"]


def test_the_status_picker_is_a_popover_not_an_inline_block():
    menu = fn(TOOLS_JS, "StatusMenu")
    assert "usePopover(ref, props.anchor)" in menu and "h-menu h-pop" in menu and "h-menu-down" not in menu
    css = src("20_style.js")
    pop = [ln for ln in css.splitlines() if ln.startswith(".h-pop{")][0]
    assert "position:fixed" in pop and "min-width:280px" in pop
    assert ".h-mystatus .h-menu{position:static" not in css       # 0c9643e's inline version is gone


def _close(e, ticket, used):
    e.store.settle(ticket, used)      # the ledger call that records what a model call really cost


# ---- budget words ----------------------------------------------------------------------------------------------

def test_a_call_in_flight_is_held_not_used_so_the_shown_use_never_drops_when_it_settles(bare):
    e, _ = bare()
    e.save_settings({"budget_daily": 10000, "msgs_daily": 60})
    _close(e, e.store.reserve("chat", 100, 10000), 100)            # 100 tokens really spent
    ticket = e.store.reserve("chat", 1200, 10000)                       # a reply is on its way, holding 1,200
    mid = e.budget_view()
    assert mid["used"] == 100 and mid["held"] == 1200 and mid["by"] == {"chat": 100}
    assert e.store.budget_used() == {"chat": 1300}                      # the limit still counts the hold
    _close(e, ticket, 600)                                         # it cost less than the hold
    after = e.budget_view()
    assert after["used"] == 700 and after["held"] == 0 and after["used"] >= mid["used"]   # only ever goes up


def test_replies_a_day_come_from_what_replies_really_cost_and_are_capped_by_the_message_limit(bare):
    from ninsei_engine.engine import REPLY_TOKENS_GUESS
    e, _ = bare()
    e.save_settings({"budget_daily": 40000, "msgs_daily": 60})
    first = e.budget_view()
    assert first["reply_tokens"] == REPLY_TOKENS_GUESS and first["replies"]["per_day"] == 40   # 40,000 / 1,000
    for used in (500, 700, 600):                                        # three settled replies, 600 on average
        _close(e, e.store.reserve("chat", 1000, 40000), used)
    v = e.budget_view()
    assert v["reply_tokens"] == 600 and v["replies"]["per_day"] == 60   # 66 by tokens, but 60 messages a day is the cap
    assert v["replies"]["left"] == min(60, (40000 - 1800) // 600)
    e.save_settings({"budget_daily": 6000, "msgs_daily": 60})
    assert e.budget_view()["replies"]["per_day"] == 10
    assert e.store.typical_reply_tokens(1000, lo=300, hi=500) == 500    # one odd, huge call can't make it silly


@needs_node
def test_the_budget_card_says_replies_not_a_percent_and_the_ring_has_no_number():
    core = src("00_core.js")
    r = run_node(fn(core, "repliesFor") + fn(core, "dailyReplies") + fn(core, "repliesWords") + const(core, "REPLY_TOKENS_GUESS") + """
out({ words: [0, 1, 40, 60].map(repliesWords), engine: dailyReplies({ limit: 40000, replies: { per_day: 60 } }),
      fallback: dailyReplies({ limit: 20000 }), typical: repliesFor(40000, { reply_tokens: 500 }), preset: repliesFor(100000) })
""")
    assert r["words"] == ["less than a reply a day", "about 1 reply a day", "about 40 replies a day", "about 60 replies a day"]
    assert r["engine"] == 60 and r["fallback"] == 20 and r["typical"] == 80 and r["preset"] == 100
    card = fn(ROOM_JS, "MyAgentCard")
    assert "Math.round((snap.budget.pct" not in card and "BudgetRing, { budget: snap.budget, size: 30, stroke: 3 })" in card
    assert "repliesWords(dailyReplies(snap.budget))" in card and "reserved for a reply in progress" in card
    assert "repliesWords(dailyReplies(snap.budget))" in fn(src("80_app.js"), "StatusChip")


def test_the_pages_reply_guess_is_the_engines():
    from ninsei_engine.engine import REPLY_TOKENS_GUESS
    assert f"const REPLY_TOKENS_GUESS = {REPLY_TOKENS_GUESS}\n" in src("00_core.js")


# ---- a friend request I sent shows as pending -------------------------------------------------------------------

async def test_a_request_i_sent_is_listed_as_pending_until_answered_and_cancelling_clears_it(bare):
    from test_hostile import Key
    e, _ = bare()
    k = Key("pending")
    assert e.dm_summary()["sent"] == []
    await e.friend_request(k.ppk)
    [row] = e.dm_summary()["sent"]
    assert row["pk"] == k.ppk and row["ts"] > 0 and row["impostor"] is False and row["name"]
    assert e.dm_summary()["requests"] == 0 and e.dm_summary()["pending"] == []   # not someone's request to me
    await e.friend_remove(k.ppk)                                                  # Cancel request
    assert e.dm_summary()["sent"] == []
    await settle(e)
    for t in list(e._dm_later):     # my own copy is held back a few seconds: not this test's business
        t.cancel()


async def test_a_request_that_was_accepted_is_a_friend_not_pending(bare):
    import test_dm
    from ninsei_engine import dm
    from test_hostile import Key
    e, _ = bare()
    k = Key("accepts")
    await e.friend_request(k.ppk)
    await e._dm_process(test_dm.friend_wrap(e, k, dm.FRIEND_ACCEPT))
    s = e.dm_summary()
    assert s["sent"] == [] and s["rel"][k.ppk] == "friend"
    await settle(e)
    for t in list(e._dm_later):
        t.cancel()


DM_JS = src("57_dm.js")


@needs_node
def test_the_direct_messages_list_shows_a_sent_request_as_pending_and_opens_its_conversation_to_cancel():
    r = run_node("""
function PersonMark() {}; function StatusDot() {}
const DM_REQUESTS = 'requests'
""" + fn(DM_JS, "DmRail") + """
const pk = 'e'.repeat(64)
const opened = []
const store = { dm: () => '', setDm: p => opened.push(p) }
const rows = snap => { const l = []; find(DmRail({ store, snap, view: 'lobby', go() {} }), n => { if (n.props && n.props.className === 'h-navrow') l.push(n); return false }); return l }
const snap = { dms: { threads: [], requests: 0, pending: [], sent: [{ pk, name: 'Maya', impostor: false, ts: 3 }] } }
const [row] = rows(snap)
row.props.onClick()
const hint = text(DmRail({ store, snap, view: 'lobby', go() {} })).includes('Add friend')
const lonely = text(DmRail({ store, snap: { dms: { threads: [], requests: 0, pending: [], sent: [] } }, view: 'lobby', go() {} })).includes('Add friend')
out({ label: row.props['aria-label'], shown: text(row), opened, hint, lonely })
""")
    assert r["label"] == "Maya, friend request pending" and "Maya" in r["shown"] and "pending" in r["shown"]
    assert r["opened"] == ["e" * 64] and not r["hint"] and r["lonely"]
    assert "Cancel request" in DM_JS                 # the conversation view's button, which takes the request back


# ---- the Lobby: unjoined rooms first, and Browse all public rooms -------------------------------------------------

from test_engine import read, run, world  # noqa: E402,F401  (fixture)


async def test_browse_all_asks_the_relays_once_per_open_filters_like_the_lobby_and_keeps_a_cooldown(world):
    from ninsei_engine import engine as eng_mod
    _, engines, _ = world
    maya, sam = engines["Maya"], engines["Sam"]
    made = await run(maya, maya.create_room, "shader club", "", ["shaders"])
    queries = []
    real = sam.pool.query_ex   # the engine's queries go through query_ex (it says whether any relay answered)

    async def counting(filters, **kw):
        queries.append(filters)
        return await real(filters, **kw)

    sam.pool.query_ex = counting
    out = await run(sam, sam.browse_rooms)
    names = [r["name"] for r in out["rooms"]]
    assert "shader club" in names and "Commons" in names and out["cached"] is False
    assert len(queries) == 1                                        # one query, nothing else (no activity query)
    [f] = queries[0]
    assert f["kinds"] == [eng_mod.KIND_META] and f["#t"] == [eng_mod.APP_TAG] and f["limit"] == eng_mod.BROWSE_LIMIT
    assert f["since"] >= int(time.time()) - eng_mod.BROWSE_DAYS * 86400 - 5        # bounded in time and in size
    assert all(set(r) >= {"id", "name", "interests", "overlap", "joined"} for r in out["rooms"])
    again = await run(sam, sam.browse_rooms)                        # straight away: the cooldown answers, the relays don't
    assert again["cached"] is True and again["wait"] >= 1 and len(queries) == 1
    assert [r["id"] for r in again["rooms"]] == [r["id"] for r in out["rooms"]]
    assert made["id"] in {r["id"] for r in again["rooms"]}


async def test_browse_all_drops_an_unproven_or_forged_room_and_a_hidden_creator(bare):
    import json as _json
    from ninsei_engine import engine as eng_mod, nostr
    from test_hostile import Key
    e, _ = bare()
    k = Key("browser")
    rid = eng_mod.room_id_for(k.ppk, "n1")

    def meta(nonce, rid_, bits=12):
        return nostr.build_event(k.psk, eng_mod.KIND_META, _json.dumps({"name": "Pop-up", "nonce": nonce}),
                                 [["d", "ninsei/room/" + rid_], ["t", eng_mod.APP_TAG], ["t", "synths"]], pow_bits=bits)

    class Pool:
        def __init__(self, evs):
            self.evs = evs

        async def query(self, filters, **kw):
            return self.evs

    e.pool = Pool([meta("n1", rid), meta("forged", rid), meta("n2", eng_mod.room_id_for(k.ppk, "n2"), bits=0)])
    out = await e.browse_rooms()
    assert [r["id"] for r in out["rooms"]] == [rid]                 # the forged id and the unproven one are gone
    e._browse_at = -1e9
    e._hidden = {k.ppk}
    assert (await e.browse_rooms())["rooms"] == []                  # a hidden creator's rooms are left out


def test_the_route_exists_and_the_lobby_lists_unjoined_rooms_first_and_browses_only_on_open():
    assert '@router.post("/lobby/browse")' in (ROOT / "dashboard" / "plugin_api.py").read_text()
    lobby = src("70_lobby.js")
    r = run_node(fn(lobby, "byActivity") + fn(lobby, "byJoined") + fn(lobby, "lobbyRooms") + """
const snap = { rooms: [{ id: 'a' }], lobby: { rooms: [
  { id: 'a', name: 'joined, live', live: true, overlap: ['x'] }, { id: 'b', name: 'shader club', overlap: [] }, { id: 'c', name: 'live one', live: true, overlap: [] }] } }
out(lobbyRooms(snap).map(r => r.id))
""")
    assert r == ["c", "b", "a"]                                     # not joined first (live before quiet), joined last
    body = fn(lobby, "Lobby")
    assert "/lobby/browse" in body and "if (next && !browse) loadAll()" in body
    assert "setInterval" not in body and "setTimeout" not in body   # not polled, not in the background


def test_the_popover_measures_its_containing_block_instead_of_assuming_one():
    """Found live 2026-11-07: assuming `.h-page` was the fixed popover's containing block put the status picker
    under the dashboard's own nav. It must park at 0,0 and offset from where that actually landed."""
    src = (ROOT / "ui/52_tools.js").read_text()
    body = src[src.index("function usePopover"):src.index("function usePopover") + 2000]
    assert "const origin = el.getBoundingClientRect ? el.getBoundingClientRect()" in body
    assert "pos.left - origin.left" in body and "pos.top - origin.top" in body
    assert "base.left" not in body


async def test_a_retired_test_room_is_left_out_of_the_lobby_and_browse_all(bare, monkeypatch):
    import json as _json
    from ninsei_engine import engine as eng_mod, nostr
    from test_hostile import Key
    e, _ = bare()
    e.save_settings({"interests": ["synths"]})
    k = Key("tester")
    keep, gone = eng_mod.room_id_for(k.ppk, "a"), eng_mod.room_id_for(k.ppk, "b")

    def meta(nonce, rid):
        return nostr.build_event(k.psk, eng_mod.KIND_META, _json.dumps({"name": "Room " + nonce, "nonce": nonce}),
                                 [["d", "ninsei/room/" + rid], ["t", eng_mod.APP_TAG], ["t", "synths"]], pow_bits=12)

    class Pool:
        async def query(self, filters, **kw):
            return [meta("a", keep), meta("b", gone)]

    e.pool = Pool()
    monkeypatch.setattr(eng_mod, "RETIRED_ROOMS", frozenset({gone}))
    assert {r["id"] for r in (await e.browse_rooms())["rooms"]} == {keep}
    assert gone not in {r["id"] for r in (await e.refresh_lobby())["rooms"]}
    assert keep in {r["id"] for r in (await e.refresh_lobby())["rooms"]}


def test_the_shipped_retired_list_holds_only_room_ids():
    from ninsei_engine import engine as eng_mod
    assert eng_mod.RETIRED_ROOMS and all(len(r) == 16 and int(r, 16) >= 0 for r in eng_mod.RETIRED_ROOMS)
    assert eng_mod.COMMONS_ID not in eng_mod.RETIRED_ROOMS


@needs_node
def test_a_lookalike_seat_never_wears_the_real_name_in_a_game_label():
    """Live repro: a third seat renamed itself "Maya" (agent Echo); the room flags it, the scoreboard did not."""
    r = run_node(LABELS + fn(TALES, "teamName") + fn(TALES, "Scoreboard") + fn(CORE, "nameBook") + """
const room = { members: [
  { pk: 'maya', name: 'Maya', agents: [{ pk: 'ada', name: 'Ada' }] },
  { pk: 'fake', name: 'Maya', impostor: true, agents: [{ pk: 'echo', name: 'Echo' }] },
  { pk: 'sam', name: 'Sam', you: true, agents: [] }] }
const book = nameBook(room, null)
// team_names comes from the engine and carries the claimed name bare: the book's flag still wins
const game = { scores: { maya: 2, fake: 1 }, players: ['maya', 'fake'], team_names: { maya: 'Maya', fake: 'Maya', gone: 'Maya', left: 'Ivy' } }
const row = Scoreboard({ game, room })
out({ board: row.props.children.map(c => c.props.children[0].props.children),
  gone: teamName(game, book, 'gone'), left: teamName(game, book, 'left'),
  who: whoLabel(book, 'fake'), echo: whoLabel(book, 'echo'), real: whoLabel(book, 'maya'),
  host: whoLabel(withHostNames(book, { x: 'Maya' }), 'x') })
""")
    assert r["board"] == ["Maya + Ada", "Maya (not verified) + Echo"]
    assert r["gone"] == "Maya (not verified)" and r["left"] == "Ivy"
    assert r["who"] == "Maya (not verified)" and r["echo"] == "Echo (Maya (not verified)'s agent)"
    assert r["real"] == "Maya" and r["host"] == "Maya (not verified)"


def test_every_game_name_goes_through_the_shared_label_helpers():
    assert "withHostNames" in fn(TALES, "teamName") and "shownName" in fn(TALES, "teamName")
    assert "rv.names" not in TALES.replace("withHostNames(props.book, rv.names)", "")
    assert "book[pk].name" not in TALES and ".name ||" not in fn(TALES, "teamName")


def test_team_names_flag_a_lookalike_with_the_rooms_own_rule():
    from ninsei_engine.engine import Engine
    who = {"ident": {"person_pk": "me"}, "my_name": "Sam", "person": {"a": "Maya", "b": "Maya"}}
    eng = Engine.__new__(Engine)
    eng._holder = lambda w, n, agent=False: "a"
    assert eng._flagged_name(who, "a") == "Maya" and eng._flagged_name(who, "b") == "Maya (not verified)"
