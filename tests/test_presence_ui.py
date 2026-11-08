"""The page side of people's status, the away setting and the stranger share, run under node with the shared hooks
harness: the /here signal and its throttle, the status dot and its words, the picker in the sidebar header, do not
disturb on alerts, the settings and the budget card's "by others" line."""
from test_audit_ui import APP, CORE, ROOM, SETUP, STYLE, fn, needs_node, run, src
from test_audit_ui import CARD

TOOLS = src("52_tools.js")
PARTS = src("30_parts.js")
FACE = src("10_face.js")
DM = src("57_dm.js")


def const_block(text, name):
    start = text.index("const " + name + " = ")
    end = text.index("\n}\n", start) + 3 if text[start:].split("\n", 1)[0].rstrip().endswith("{") else text.index("\n]\n", start) + 3
    return text[start:end]


STATUS_FNS = "const STATUS_LABEL = { present: 'Present', idle: 'Idle', dnd: 'Do not disturb', away: 'Away', online: 'Online' }\n" \
    + fn(CORE, "statusKey") + "const isHere = p => { const k = statusKey(p); return k === 'present' || k === 'idle' || k === 'online' }\n"


def test_the_page_words_match_the_engines_statuses():
    assert "const STATUS_LABEL = { present: 'Present', idle: 'Idle', dnd: 'Do not disturb', away: 'Away', online: 'Online' }" in CORE
    assert "const isHere = p => { const k = statusKey(p); return k === 'present' || k === 'idle' || k === 'dnd' || k === 'online' }" in CORE


@needs_node
def test_a_status_dot_says_its_word_and_an_unknown_one_falls_back_to_online_away():
    r = run(STATUS_FNS + """
out({ present: statusKey({ status: 'present', online: false }), dnd: statusKey({ status: 'dnd', online: true }),
      away: statusKey({ status: 'away', online: true }),
      unknownOn: statusKey({ status: 'unknown', online: true }), unknownOff: statusKey({ status: 'unknown', online: false }),
      none: statusKey({ online: true }), junk: statusKey({ status: 'Present', online: false }), nothing: statusKey(null),
      here: [{ status: 'present' }, { status: 'idle' }, { status: 'dnd' }, { status: 'away', online: true }, { status: 'unknown', online: true }, { online: false }].map(isHere) })
""")
    assert r["present"] == "present" and r["dnd"] == "dnd" and r["away"] == "away"
    assert r["unknownOn"] == "online" and r["unknownOff"] == "away" and r["none"] == "online"
    assert r["junk"] == "away" and r["nothing"] == "away"
    assert r["here"] == [True, True, False, False, True, False]    # dnd is not "here"; away stays away even with a live agent


@needs_node
def test_the_status_dot_carries_a_label_and_a_title_never_colour_alone():
    r = run(STATUS_FNS + fn(PARTS, "StatusDot") + """
const dot = p => StatusDot({ p }).props
out(['present', 'idle', 'dnd', 'away'].map(s => { const d = dot({ status: s }); return [d['data-s'], d['aria-label'], d.title, d.role] }).concat([[dot({ status: 'unknown', online: true })['aria-label']]]))
""")
    assert r[:4] == [["present", "Present", "Present", "img"], ["idle", "Idle", "Idle", "img"],
                     ["dnd", "Do not disturb", "Do not disturb", "img"], ["away", "Away", "Away", "img"]]
    assert r[4] == ["Online"]
    assert ".h-presence[data-s=idle]" in STYLE and ".h-presence[data-s=dnd]" in STYLE


HERE_JS = "const NINSEI_VIEW = '[data-ninsei-view]'\n" + "".join(
    f"const {n} = {v}\n" for n, v in (("HERE_EVERY_MS", 30000), ("HERE_MIN_MS", 10000), ("HERE_ACTIVE_MS", 150000)))


def here_harness():
    return HERE_JS + fn(CORE, "hereSignals") + """
let t = 1000000
Date.now = () => t
const timers = []
const calls = []
const listeners = {}
const doc = { visibilityState: 'visible', hasFocus: () => true }
const win = {}
globalThis.document = doc
globalThis.window = win
globalThis.P = {
  rest: async (path, o) => { calls.push([t, path, o.method, o.body.focused]); return {} },
  listen: (target, type, fn, opts) => { (listeners[(target === doc ? 'doc:' : 'win:') + type] = listeners[(target === doc ? 'doc:' : 'win:') + type] || []).push(fn); return () => {} },
  setTimeout: (fn, ms) => { const x = { at: t + ms, fn, live: true }; timers.push(x); return () => { x.live = false } }
}
const advance = ms => { const end = t + ms; for (;;) { const nxt = timers.filter(x => x.live).sort((a, b) => a.at - b.at)[0]; if (!nxt || nxt.at > end) break; t = nxt.at; nxt.live = false; nxt.fn() } t = end }
const fire = (k, e) => (listeners[k] || []).forEach(f => f(e))
"""


@needs_node
def test_here_posts_at_once_then_every_30_seconds_and_at_most_one_per_10_seconds():
    r = run(here_harness() + """
const stop = hereSignals({})
const first = calls.slice()
advance(29000)
const early = calls.length
advance(2000)
const after30 = calls.length
for (let i = 0; i < 20; i++) { fire('doc:keydown'); advance(100) }       // typing a lot, for two seconds
const burst = calls.length - after30
advance(9000)
const trailing = calls.length - after30                                   // the one the burst saved up
stop()
const n = calls.length
advance(120000)
out({ first, early, after30, burst, trailing, stoppedQuiet: calls.length === n, gaps: calls.map((c, i) => i ? c[0] - calls[i - 1][0] : 99999).slice(1) })
""")
    assert r["first"][0][1:] == ["/here", "POST", True] and len(r["first"]) == 1
    assert r["early"] == 1 and r["after30"] == 2                          # one right away, then the 30 s beat
    assert r["burst"] <= 1                                                 # a burst of typing: not one call per key
    assert all(g >= 10000 for g in r["gaps"])                              # never closer than 10 s
    assert r["stoppedQuiet"] is True                                       # unmounting stops it


@needs_node
def test_here_sends_on_a_focus_or_visibility_change_and_stays_quiet_while_hidden():
    r = run(here_harness() + """
const stop = hereSignals({})
advance(10500)
fire('win:focus')
const onFocus = calls.length
doc.visibilityState = 'hidden'
advance(11000)
fire('doc:visibilitychange')
advance(31000)
const hidden = calls.length
doc.visibilityState = 'visible'
fire('doc:visibilitychange')
stop()
out({ onFocus, hidden, afterShow: calls.length, last: calls[calls.length - 1] })
""")
    assert r["onFocus"] == 2 and r["hidden"] == 2                         # nothing is sent while the document is hidden
    assert r["afterShow"] == 3 and r["last"][1:] == ["/here", "POST", True]


@needs_node
def test_a_window_nobody_touched_reports_open_not_focused():
    r = run(here_harness() + """
const stop = hereSignals({})
advance(31000); advance(31000); advance(31000); advance(31000); advance(31000)    // 2.5 minutes, then a bit more, untouched
advance(31000)
const quietMin = calls[calls.length - 1][3]
fire('doc:pointerdown')
advance(11000)
const touched = calls[calls.length - 1][3]
doc.hasFocus = () => false
fire('win:blur')
advance(31000)
const blurred = calls[calls.length - 1][3]
stop()
out({ first: calls[0][3], quietMin, touched, blurred })
""")
    assert r["first"] is True                                              # opening it counts as a touch
    assert r["quietMin"] is False                                          # over HERE_ACTIVE_MS untouched: open, not focused
    assert r["touched"] is True and r["blurred"] is False


@needs_node
def test_only_use_inside_a_ninsei_view_counts_and_a_view_that_is_not_on_screen_reports_nothing():
    r = run(here_harness() + """
const view = { getClientRects: () => [{}] }
doc.querySelectorAll = sel => sel === NINSEI_VIEW ? [view] : []
const inNinsei = { target: { closest: sel => sel === NINSEI_VIEW ? view : null } }
const elsewhere = { target: { closest: () => null } }
const stop = hereSignals({})
advance(31000); advance(31000); advance(31000); advance(31000); advance(31000); advance(31000)   // untouched: open, not focused
const quiet = calls[calls.length - 1][3]
fire('doc:keydown', elsewhere); fire('doc:pointerdown', elsewhere); fire('doc:scroll', { target: doc })   // the rest of Hermes
advance(11000)
const afterElsewhere = calls[calls.length - 1][3]
fire('doc:pointerdown', inNinsei)
advance(11000)
const afterInside = calls[calls.length - 1][3]
const n = calls.length
view.getClientRects = () => []                   // the docked tab is hidden, or another tab is in front
advance(120000)
const whileHidden = calls.length - n
view.getClientRects = () => [{}]
advance(31000)
stop()
out({ quiet, afterElsewhere, afterInside, whileHidden, resumed: calls.length > n })
""")
    assert r["quiet"] is False and r["afterElsewhere"] is False       # typing elsewhere in Hermes is not use of Ninsei
    assert r["afterInside"] is True
    assert r["whileHidden"] == 0 and r["resumed"] is True             # nothing is sent while no Ninsei view is on screen


@needs_node
def test_desktop_reports_only_while_a_view_is_mounted_and_not_from_plugin_start():
    tail = src("platform/desktop_tail.js")
    assert "ctx.onDispose(hereSignals(store))" not in tail and "viewMounted(store)" in tail
    assert "P.viewMounted ? P.viewMounted(store)" in APP
    r = run("let started = 0, stopped = 0\nconst hereSignals = () => { started++; return () => { stopped++ } }\n"
            + tail[tail.index("let hereViews"):tail.index("function makePlatform")]
            + "const P = { " + tail[tail.index("    viewMounted(store) {"):tail.index("    // the profile Desktop")].rstrip().rstrip(",") + " }\n"
            + """
const none = [started, stopped]
const page = P.viewMounted({}), dock = P.viewMounted({})        // the page and the docked tab, both up
const both = [started, stopped]
page()
const one = [started, stopped]
dock()
const zero = [started, stopped]
const again = P.viewMounted({}); again()
out({ none, both, one, zero, final: [started, stopped] })
""")
    assert r["none"] == [0, 0] and r["both"] == [1, 0]
    assert r["one"] == [1, 0] and r["zero"] == [1, 1] and r["final"] == [2, 2]


def test_here_is_installed_on_both_platforms():
    assert "hereSignals(store)" in src("platform/dashboard_tail.js") and "hereSignals(store)" in src("platform/desktop_tail.js")
    assert "const HERE_EVERY_MS = 30000" in CORE and "const HERE_MIN_MS = 10000" in CORE


# ---- do not disturb ---------------------------------------------------------------------------------------------

@needs_node
def test_do_not_disturb_silences_toasts_and_os_notifications_but_not_the_counts_and_does_not_replay_after():
    js = fn(CORE, "cleanSnippet") + fn(CORE, "mentionAlerts") + """
const toasts = [], os = []
globalThis.P = { toast: (k, m) => toasts.push([k, m]), osNotify: o => os.push(o) }
function nav() { return { set() {} } }
let listener = null
const store = { subscribe: fn => { listener = fn; return () => {} }, isShowing: () => false, setRoom() {}, setDm() {} }
mentionAlerts(store)
const lm = id => ({ id, name: 'Sam', text: 'hi @maya', ts: 1 })
const snap = (mode, mentions, dm, req) => ({ snap: { settings: { status_mode: mode },
  rooms: [{ id: 'r1', name: 'Club', mentions, last_mention: lm('e' + mentions) }],
  dms: { threads: [{ pk: 'p1', name: 'Fay', unread: dm, last_unread: { id: 'd' + dm, text: 'yo' } }], pending: req ? [{ pk: 'q' + req, name: 'Rae' }] : [] } } })
listener(snap('auto', 1, 0, 0))                          // baseline
listener(snap('auto', 2, 1, 1))                          // all three announced
const loud = [toasts.length, os.length]
listener(snap('dnd', 3, 2, 2))                           // in dnd: none of them
const quietNow = [toasts.length, os.length]
listener(snap('auto', 3, 2, 2))                          // leaving dnd replays nothing
out({ loud, quietNow, after: [toasts.length, os.length] })
"""
    from test_chat_a2 import run_js
    r = run_js(js)
    assert r["loud"] == [3, 3] and r["quietNow"] == [3, 3] and r["after"] == [3, 3]


def test_the_alert_code_gates_every_toast_on_dnd():
    body = fn(CORE, "mentionAlerts")
    assert body.count("if (dnd) continue") == 2 and "fresh.length && !dnd" in body
    assert "status_mode === 'dnd'" in body


# ---- the picker -------------------------------------------------------------------------------------------------

PICKER_JS = const_block(TOOLS, "STATUS_CHOICES") + fn(TOOLS, "MyStatus") + fn(TOOLS, "StatusMenu") + STATUS_FNS + """
const useEnter = () => ({ current: null })
const usePopover = () => {}      // placed by usePopover: tested in test_walkthrough_fixes.py
const STATE_LABEL = { idle: 'idle', working: 'thinking', speaking: 'speaking', waiting: 'waiting', error: 'error', absent: 'away' }
const stateWord = s => String(s || '').split(':').pop().trim()
globalThis.P = { listen: () => () => {}, setTimeout: f => { f(); return () => {} } }
globalThis.document = { activeElement: null }
K.Icon = function Icon() {}
"""


def make_snap(mode="auto", shown="present"):
    return """{ me: { name: 'Maya', agent: { name: 'Ada', state: 'activity: idle' } }, status: { mode: '%s', shown: '%s', auto: 'present', around: true } }""" % (mode, shown)


@needs_node
def test_the_sidebar_line_is_a_button_that_opens_a_picker_with_five_choices_and_their_words():
    r = run(PICKER_JS + """
const posts = []
const store = { post: async (p, b) => { posts.push([p, b]); return {} } }
const root = mount(MyStatus, { store, snap: %s })
const btn = find(root.tree, n => n.type === 'button' && n.props['aria-haspopup'] === 'menu')
const label = btn.props['aria-label']
const shownText = text(btn)
btn.props.onClick(); await settle()
const menu = find(root.tree, n => n.type === StatusMenu)
const m = mount(StatusMenu, menu.props)
const items = []
;(function walk(n) { if (!n || typeof n !== 'object') return; if (Array.isArray(n)) return n.forEach(walk); if (n.props && n.props.role === 'menuitemradio') items.push(n); kids(n).forEach(walk) })(m.tree)
const names = items.map(i => text(i))
items[3].props.onClick()
await settle()
out({ label, shownText, names, posts, checked: items.map(i => i.props['aria-checked']) })
""" % make_snap("auto", "present"))
    assert "You show as Present" in r["label"] and "Maya & Ada" in r["shownText"] and "idle" in r["shownText"]
    assert [n.split("Show")[0].split("You")[0].split("People")[0][:12] for n in r["names"]][0].startswith("Automatic")
    assert r["checked"] == [True, False, False, False, False]
    assert r["posts"] == [["/settings", {"status_mode": "dnd"}]]
    joined = " | ".join(r["names"])
    assert "Do not disturb" in joined and "Invisible" in joined
    assert "You show as away. Your agent still works." in joined                  # the one line the spec gives for Invisible


def test_every_choice_has_a_one_line_explanation_and_the_header_is_the_picker():
    block = const_block(TOOLS, "STATUS_CHOICES")
    for word in ("auto", "present", "idle", "dnd", "invisible"):
        assert f"id: '{word}'" in block
    assert block.count("hint:") == 5 and "You show as away. Your agent still works." in block
    assert "jsx(MyStatus, { store, snap })" in APP and "' · ' + STATE_LABEL[stateWord(a.state)] })" not in APP
    assert "Escape" in fn(TOOLS, "StatusMenu") and "pointerdown" in fn(TOOLS, "StatusMenu")


# ---- room list, members, cards, direct messages -----------------------------------------------------------------

def test_the_lists_use_the_status_dot_and_count_who_is_here():
    assert "jsx(StatusDot, { p })" in ROOM and "(room.members || []).filter(isHere).length" in ROOM
    assert "' here'" in APP and "' online'" not in APP and "r.online + ' here'" in APP
    assert "jsx(StatusDot, { p: t })" in DM and "t.friend !== false" in DM
    assert "['Status', STATUS_LABEL[statusKey(p)]]" in CARD and "'In the room'" not in CARD
    assert "STATUS_LABEL[statusKey(p)]" in ROOM       # the word beside the dot in the members list


# ---- settings ---------------------------------------------------------------------------------------------------

def test_settings_has_the_away_choice_the_share_and_the_others_line():
    assert "When I’m away, my agent…" in SETUP
    for label in ("Answers only when named", "Stays quiet", "Chats as usual"):
        assert label in SETUP
    assert "Others can use" in SETUP and "A quarter" in SETUP and "Half" in SETUP and "Three quarters" in SETUP
    assert "now({ away_mode: v })" in SETUP and "now({ stranger_share: v })" in SETUP
    assert "othersLine(snap.budget)" in SETUP and "OTHERS_SPENT" in SETUP
    assert "Others used their share today; your agent still answers you." in FACE


@needs_node
def test_the_budget_card_says_how_much_others_used_and_the_plain_words_when_their_share_is_gone():
    r = run("const fmtTokens = n => n >= 1000 ? Math.round(n / 1000) + 'k' : String(n)\n" + fn(FACE, "othersLine") + """
out([othersLine({ others: { used: 8000 } }), othersLine({ others: { used: 0 } }), othersLine({}), othersLine(null)])
""")
    assert r == ["8k of it by others", "", "", ""]
