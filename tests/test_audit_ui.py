"""UI audit fixes (items 12, 20-22, 31, 40, 48-54): the real component functions from ui/*.js run
under node with a tiny hooks runtime, plus source checks for CSS and wiring a test can't render."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def src(name: str) -> str:
    return (ROOT / "ui" / name).read_text()


CORE, ROOM, APP, TALES, CARD, SETUP, LOBBY, STYLE, PARTS = (
    src(n) for n in ("00_core.js", "50_room.js", "80_app.js", "60_tales.js", "35_card.js", "40_setup.js",
                     "70_lobby.js", "20_style.js", "30_parts.js"))


def fn(text: str, name: str) -> str:
    """One top-level function's source, from `function name(` to its closing brace."""
    start = text.index("function " + name + "(")
    return text[start:text.index("\n}\n", start) + 3]


def const(text: str, name: str) -> str:
    return re.search(r"^const " + name + r" = .*$", text, re.M).group(0) + "\n"


# A hooks runtime small enough to read: state, refs and effects with dependency lists, re-rendered
# on a microtask. jsx() makes plain objects, so a test walks the tree and calls onClick itself.
HARNESS = r"""
let cur = null
const Fragment = Symbol('F')
const jsx = (type, props, key) => ({ type, props: props || {}, key })
const jsxs = jsx
function useState(init) {
  const h = cur.hooks, i = cur.i++
  if (!(i in h)) h[i] = { v: typeof init === 'function' ? init() : init }
  const slot = h[i]
  return [slot.v, nv => { const v = typeof nv === 'function' ? nv(slot.v) : nv; if (!Object.is(v, slot.v)) { slot.v = v; cur.schedule() } }]
}
function useRef(v) { const h = cur.hooks, i = cur.i++; if (!(i in h)) h[i] = { current: v }; return h[i] }
function useCallback(f) { return f }
function useEffect(fn, deps) {
  const h = cur.hooks, i = cur.i++
  const slot = h[i] || (h[i] = { ran: false, deps: undefined, cleanup: null })
  const changed = !slot.ran || !deps || deps.some((d, k) => !Object.is(d, slot.deps[k]))
  if (changed) cur.effects.push(() => { if (slot.cleanup) slot.cleanup(); slot.ran = true; slot.deps = deps; slot.cleanup = fn() || null })
}
function mount(Comp, props) {
  const root = { hooks: [], i: 0, effects: [], props, tree: null, queued: false }
  const render = () => {
    root.queued = false; root.i = 0; cur = root
    root.tree = Comp(root.props)
    const fx = root.effects.splice(0); fx.forEach(f => f())
  }
  root.schedule = () => { if (!root.queued) { root.queued = true; queueMicrotask(render) } }
  root.update = p => { root.props = p; render() }
  render()
  return root
}
const settle = async () => { for (let i = 0; i < 6; i++) await new Promise(r => setTimeout(r, 0)) }
const kids = n => [].concat((n && n.props && n.props.children) || [], (n && n.props && n.props.footer) || [])
function find(node, pred) {
  if (!node || typeof node !== 'object') return null
  if (Array.isArray(node)) { for (const c of node) { const f = find(c, pred); if (f) return f } return null }
  if (pred(node)) return node
  for (const c of kids(node)) { const f = find(c, pred); if (f) return f }
  return null
}
function text(node) {
  if (node == null || node === false) return ''
  if (typeof node !== 'object') return String(node)
  if (Array.isArray(node)) return node.map(text).join('')
  return kids(node).map(text).join('')
}
const button = (tree, label) => find(tree, n => n.type === K.Button && text(n).includes(label))
const K = { Button: function Button() {}, Input: function Input() {}, Icon: function Icon() {}, Dialog: function Dialog() {} }
const out = o => console.log(JSON.stringify(o))
"""


def run(js: str):
    done = subprocess.run([NODE, "-e", "(async () => {\n" + HARNESS + js + "\n})().catch(e => { console.error(e); process.exit(1) })"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


SHARE_JS = lambda: (fn(CORE, "errText") + fn(CORE, "errStatus") + fn(ROOM, "shareChanged") + fn(ROOM, "ShareDialog") + """
function Modal() {}; function Notice() {}; function Field() {}; function ToyFrame() {}
const fmtBytes = n => n + ' B'
const BUILD = { html: '<p>a</p>', frame: '<p>a</p>', bytes: 9, serialized_bytes: 20, limit: 48000, fits: true, secrets: [], sha256: 'aaa' }
function setup(builds, postFails) {
  const posts = []; let closed = 0, served = 0
  globalThis.P = { rest: async () => builds[Math.min(served++, builds.length - 1)] }
  const store = { post: async (path, body) => { posts.push([path, body]); if (postFails) throw new Error('no'); return {} } }
  const root = mount(ShareDialog, { m: { id: 'o1', title: 'Toy' }, store, room: { name: 'club' }, onClose: () => { closed++ } })
  return { root, posts, closed: () => closed }
}
""")


@needs_node
def test_share_preview_waits_for_run_and_the_share_carries_the_reviewed_hash():
    js = SHARE_JS() + """
const t = setup([BUILD], false)
await settle()
const before = !!find(t.root.tree, n => n.type === ToyFrame)
const hasRun = !!button(t.root.tree, 'Run preview')
button(t.root.tree, 'Run preview').props.onClick()
await settle()
const running = !!find(t.root.tree, n => n.type === ToyFrame)
await button(t.root.tree, 'Share this file').props.onClick()
await settle()
out({ before, hasRun, running, posts: t.posts, closed: t.closed() })
"""
    r = run(js)
    assert r["before"] is False and r["hasRun"] is True, "the preview must not run before Run preview is pressed"
    assert r["running"] is True
    assert r["posts"] == [["/offers/share", {"offer": "o1", "title": "Toy", "confirm_secrets": False, "sha256": "aaa"}]]
    assert r["closed"] == 1


@needs_node
def test_share_refetches_when_the_file_changed_and_asks_for_a_new_review():
    js = SHARE_JS() + """
const v2 = Object.assign({}, BUILD, { sha256: 'bbb', secrets: ['an sk- key'] })
const t = setup([BUILD, v2], true)
await settle()
button(t.root.tree, 'Run preview').props.onClick()
await settle()
await button(t.root.tree, 'Share this file').props.onClick()
await settle()
const notices = []
find(t.root.tree, n => { if (n.type === Notice) notices.push(text(n)); return false })
out({ changed: notices.some(x => x.includes('changed since you reviewed')), secretNotice: notices.some(x => x.includes('secret')),
  running: !!find(t.root.tree, n => n.type === ToyFrame), closed: t.closed(), posts: t.posts.length,
  next: text(button(t.root.tree, 'Share').props.children) })
"""
    r = run(js)
    assert r["changed"] and r["secretNotice"], "the new file's scan must show before anything is shared"
    assert r["running"] is False, "a changed toy must not keep running under the old review"
    assert r["closed"] == 0 and r["posts"] == 1
    assert r["next"] == "Share this file", "a blanket 'Share anyway' from the old file must not carry over"


@needs_node
def test_share_failure_with_the_same_file_does_not_claim_it_changed():
    js = SHARE_JS() + """
const t = setup([BUILD], true)
await settle()
await button(t.root.tree, 'Share this file').props.onClick()
await settle()
const notices = []
find(t.root.tree, n => { if (n.type === Notice) notices.push(text(n)); return false })
out({ changed: notices.some(x => x.includes('changed since')), closed: t.closed() })
"""
    r = run(js)
    assert r == {"changed": False, "closed": 0}


@needs_node
def test_hidden_game_panel_leaves_a_show_bar_and_a_new_action_phase_restores_it():
    js = (fn(TALES, "gameName") + const(TALES, "GAME_NAME") + fn(TALES, "TallTales") + """
function FakePhase() {}; function FlagPhase() {}; function VotePhase() {}; function WhoRevealPhase() {}; function RevealPhase() {}
function Scoreboard() {}; function Countdown() {}
const useNow = () => 0
const g = (over) => Object.assign({ gid: 'g1', n: 1, rounds: 3, phase: 'vote', ends_at: 0, mode: 'tales', host_name: 'Ada' }, over)
const full = r => !!find(r.tree, n => n.type === Scoreboard)
const props = game => ({ store: {}, room: {}, game, book: {} })
const r = mount(TallTales, props(g()))
const shown = full(r)
button(r.tree, 'Hide').props.onClick()
await settle()
const bar = text(r.tree)
const barHasShow = !!button(r.tree, 'Show game')
button(r.tree, 'Show game').props.onClick()
await settle()
const back = full(r)
button(r.tree, 'Hide').props.onClick()
await settle()
r.update(props(g({ phase: 'reveal' })))
await settle()
const stayedHidden = !full(r) && !!button(r.tree, 'Show game')
r.update(props(g({ n: 2, phase: 'fakes' })))
await settle()
const restored = full(r)
button(r.tree, 'Hide').props.onClick()
await settle()
r.update(props(g({ n: 2, phase: 'end' })))
await settle()
const endShown = full(r) && !!button(r.tree, 'Close')
button(r.tree, 'Close').props.onClick()
await settle()
out({ shown, bar, barHasShow, back, stayedHidden, restored, endShown, endedGone: r.tree === null })
""")
    r = run(js)
    assert r["shown"] and r["barHasShow"] and r["back"]
    assert "Tall Tales is running" in r["bar"]
    assert r["stayedHidden"], "a reveal needs nothing from you, so a hidden panel stays hidden"
    assert r["restored"], "a new round that wants an answer or a vote brings the panel back"
    assert r["endShown"], "a game hidden while it ran shows its final scores, with Close, when it ends"
    assert r["endedGone"], "a finished game closed with Close stays closed"


@needs_node
def test_answer_box_takes_focus_only_from_nothing_or_from_inside_the_game_panel():
    js = fn(TALES, "wantsFocus") + """
const body = {}, root = {}, composer = {}, inGame = {}
globalThis.document = { body, documentElement: root }
const panel = { contains: x => x === inGame }
const box = { closest: sel => sel === '.h-tales' ? panel : null }
out([wantsFocus(body, box), wantsFocus(null, box), wantsFocus(root, box), wantsFocus(composer, box), wantsFocus(inGame, box)])
"""
    assert run(js) == [True, True, True, False, True]
    assert "autoFocus" not in fn(TALES, "FakePhase")


@needs_node
def test_tab_stays_inside_the_profile_sheet():
    js = fn(CARD, "tabTarget") + """
const a = {}, b = {}, c = {}, outside = {}
const items = [a, b, c]
out([tabTarget(items, c, false) === a, tabTarget(items, a, true) === c, tabTarget(items, b, false), tabTarget(items, b, true),
  tabTarget(items, outside, false) === a, tabTarget(items, outside, true) === c, tabTarget([], a, false)])
"""
    assert run(js) == [True, True, None, None, True, True, None]


@needs_node
def test_chained_profile_sheets_keep_the_first_opener():
    js = fn(CARD, "ProfileLayer") + """
function ProfileSheet() {}
const ProfileContext = { Provider: function Provider() {} }
const btnA = { id: 'name' }, inSheet = { id: 'agent button inside sheet' }, btnB = { id: 'another' }
globalThis.document = { activeElement: btnA }
const r = mount(ProfileLayer, { children: null, snap: {}, store: {}, room: null })
const open = r.tree.props.value
open({ pk: 'p1' }); await settle()
document.activeElement = inSheet            // the sheet's own button is focused when the next card opens
open({ pk: 'a1' }); await settle()
const sheet = find(r.tree, n => n.type === ProfileSheet)
const first = sheet.props.opener.current
sheet.props.onClose(); await settle()
const closed = !find(r.tree, n => n.type === ProfileSheet)
document.activeElement = btnB
open({ pk: 'p2' }); await settle()
const second = find(r.tree, n => n.type === ProfileSheet).props.opener.current
out({ first: first.id, closed, second: second.id })
"""
    assert run(js) == {"first": "name", "closed": True, "second": "another"}
    # focus is restored only to a button that is still on the page
    assert "back.isConnected" in fn(CARD, "ProfileSheet")


@needs_node
def test_lobby_open_and_join_switch_to_the_room_view():
    js = fn(LOBBY, "openRoom") + """
const log = []
globalThis.nav = () => ({ set: v => log.push('nav:' + v) })
openRoom({ setRoom: id => log.push('room:' + id) }, 'abc')
out(log)
"""
    assert run(js) == ["room:abc", "nav:room"]
    lobby = fn(LOBBY, "Lobby")
    assert "store.setRoom" not in lobby and lobby.count("openRoom(store, r.id)") == 2
    assert "openRoom(store, id)" in fn(APP, "Welcome")


@needs_node
def test_limit_fields_reject_empty_and_non_numbers_instead_of_saving_zero():
    js = fn(SETUP, "parseCount") + const(SETUP, "BUDGET_MAX") + const(SETUP, "MSGS_MAX") + fn(SETUP, "limitError") + """
out([parseCount(''), parseCount('  '), parseCount('abc'), parseCount('12.5'), parseCount('-3'), parseCount(null), parseCount(undefined),
  parseCount('0'), parseCount(' 40000 '), parseCount(60),
  limitError('', BUDGET_MAX, 'tokens', '40000'), limitError('0', BUDGET_MAX, 'tokens', '40000'), limitError('2001', MSGS_MAX, 'messages', '60'),
  limitError('2000', MSGS_MAX, 'messages', '60')])
"""
    r = run(js)
    assert r[:6] == [None] * 6 and r[6] is None
    assert r[7:10] == [0, 40000, 60]
    assert r[10].startswith("Enter a whole number of tokens")
    assert r[11] == "" and r[13] == ""
    assert "most is 2,000" in r[12]
    form = fn(SETUP, "SettingsForm")
    assert "parseInt(form" not in form and "|| 0" not in form
    assert "!!budgetErr || !!msgsErr" in form and "if (budgetErr || msgsErr) return" in form


def test_onboarding_tells_you_commons_is_public_and_scopes_the_nothing_published_hint():
    on = fn(SETUP, "Onboarding")
    assert "Nothing is published" not in on
    assert "Your interest card is published only if you choose" in on
    assert "Commons" in on and "public Nostr relays" in on
    assert "'globe'" in on[on.index("Commons") - 120:on.index("Commons")]


def test_drawer_closes_on_view_room_change_escape_scrim_and_button():
    app = fn(APP, "App")
    assert "useEffect(() => { setPeople(false) }, [view, roomKey])" in app
    assert "key === 'Escape'" in app and "closePeople" in app and "h-scrim" in app and "h-right-close" in app
    assert "peopleFrom" in app and "back.focus" in app, "focus returns to the button that opened the drawer"
    assert "onPeople: togglePeople" in app
    # the scrim and close button exist only while the drawer shows
    assert re.search(r"\.h-grid\[data-people=open\] \.h-scrim\{display:block", STYLE)
    assert re.search(r"\.h-grid\[data-people=open\] \.h-right-bar\{display:flex", STYLE)
    assert re.search(r"^\.h-scrim,\.h-right-bar\{display:none\}", STYLE, re.M)


def test_publish_card_explains_why_it_is_disabled():
    card = fn(LOBBY, "CardSection")
    assert "noInterests" in card and "id: 'h-card-hint'" in card and "'aria-describedby': noInterests ? 'h-card-hint'" in card
    assert "Settings" in card


def test_reduced_motion_covers_thinking_and_spinner():
    m = re.search(r"@media \(prefers-reduced-motion: reduce\)\{\.h-thinking\{animation:none\}\.hx \.h-spin\{animation:none!important\}\}", STYLE)
    assert m
    assert STYLE.index(".h-thinking{display:flex") < m.start(), "the override must come after the rule it overrides"


def test_presence_is_announced():
    person = fn(ROOM, "Person")
    assert "role: 'img', 'aria-label': p.online ? 'online' : 'away'" in person
    assert "h-sr" in APP and "' online'" in APP, "the rail's count says what it counts"
    assert ".h-sr{position:absolute" in STYLE


def test_profile_sheet_focuses_close_and_traps_tab():
    sheet = fn(CARD, "ProfileSheet")
    assert "tabIndex: -1" not in sheet
    assert "close.current.querySelector('button')" in sheet and "tabTarget(" in sheet and "'Tab'" in sheet


def test_built_outputs_carry_the_fixes():
    for rel in ("desktop/plugin.js", "dashboard/dist/index.js"):
        built = (ROOT / rel).read_text()
        for needle in ("Run preview", "shareChanged", "tabTarget", "openRoom", "limitError", "h-right-close", "Show game"):
            assert needle in built, f"{rel} is missing {needle}: run python3 scripts/build_ui.py"
