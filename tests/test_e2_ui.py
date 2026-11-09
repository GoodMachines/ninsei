"""Chat polish, second half (Batch E2), the page side, run under node with the shared hooks harness: mute, chattiness and
rename in the room menu, the quick switcher, copy text and message links, the reconnecting banner, empty states,
spring dots, and the narrow layout."""
import pytest

from test_audit_ui import CORE, ROOM, STYLE, APP, fn, needs_node, run, src
from test_e1_ui import MESSAGE_JS

TOOLS = src("52_tools.js")
CORE_FNS = "".join(fn(CORE, n) for n in ("foldText", "fuzzyScore", "parseRoomLink", "relaysDown", "wantJump"))

TOOLS_PRELUDE = """
const useEnter = () => ({ current: null }); function useMemo(f) { return f() }; const useLayoutEffect = useEffect
const cx = (...a) => a.filter(Boolean).join(' ')
const SPRING = { pop: {}, calm: {}, enter: {} }; const motion = { reduced: () => true }
function Modal() {}; function Field() {}; function Notice() {}; function PersonMark() {}; function PersonMark2() {}
const PENDING_JUMP = { room: '', id: '', until: 0 }, JUMP_WATCH = new Set()
const CHATTY_LABEL = { quiet: 'Quiet', normal: 'Normal', lively: 'Lively' }
function useNow() { return 100 }
K.Tip = function Tip() {}
globalThis.P = { listen: () => () => {}, setTimeout: f => { f(); return () => {} } }
globalThis.document = { activeElement: null }
"""


# ---- links ----------------------------------------------------------------------------------------------------------

@needs_node
def test_a_ninsei_link_in_a_message_is_a_room_token_whose_text_is_the_link_itself():
    rich = "".join(fn(CORE, n) for n in ("squashName", "mentionNames", "mentionParts", "linkAt", "roomLinkAt", "emphasisCloses", "richInline", "richParts")) + "const RICH_MAX_LINKS = 20\n"
    r = run(rich + """
const room = '203f22bcfd1b4b2f', ev = 'a'.repeat(64)
const rooms = t => richParts(t, []).flatMap(b => b.tokens || []).filter(x => x.t === 'room').map(x => [x.text, x.room, x.event])
out({ plain: rooms('see ninsei:' + room + ' ok'), msg: rooms('here: ninsei:' + room + '#' + ev + '.'), upper: rooms('NINSEI:' + room.toUpperCase()),
      inWord: rooms('xninsei:' + room), short: rooms('ninsei:abc'), tooLong: rooms('ninsei:' + room + '0'), badEv: rooms('ninsei:' + room + '#zz'),
      many: rooms(('ninsei:' + room + ' ').repeat(40)).length, masked: rooms('[open](ninsei:' + room + ')') })
""")
    room, ev = "203f22bcfd1b4b2f", "a" * 64
    assert r["plain"] == [["ninsei:" + room, room, ""]]
    assert r["msg"] == [["ninsei:%s#%s" % (room, ev), room, ev]]                         # the closing "." is not part of it
    assert r["upper"][0][1] == room
    assert r["inWord"] == [] and r["short"] == [] and r["tooLong"] == []
    assert r["badEv"] == [["ninsei:" + room, room, ""]]                                  # a bad message id is just the room
    assert r["many"] == 20                                                                # the same cap as web links
    assert r["masked"][0][0] == "ninsei:" + room                                          # the text is still the address


@needs_node
def test_the_page_reads_codes_and_links_the_way_the_engine_does():
    r = run(CORE_FNS + """
const room = '203f22bcfd1b4b2f', ev = 'b'.repeat(64)
out({ a: parseRoomLink('ninsei:' + room), b: parseRoomLink(' ninsei:' + room + '#' + ev + ' '), c: parseRoomLink(room), d: parseRoomLink('ninsei:' + room + '#nope'),
      e: parseRoomLink(null), f: parseRoomLink('x'.repeat(5000)).room })
""")
    room, ev = "203f22bcfd1b4b2f", "b" * 64
    assert r["a"] == {"room": room, "event": "", "hosts": []} and r["b"] == {"room": room, "event": ev, "hosts": []} and r["c"]["room"] == room
    assert r["d"] == {"room": room, "event": "", "hosts": []} and r["e"] == {"room": "", "event": "", "hosts": []} and r["f"] == ""


def test_room_links_open_inside_ninsei_and_a_stranger_room_only_opens_the_join_dialog():
    assert "t.t === 'room'" in fn(ROOM, "richNode") and "useContext(LinkContext)" in fn(ROOM, "RoomLink")
    link = fn(APP, "App")
    assert "setJoinFor(code || room" in link and "if (!joined)" in link                            # never joins on a click
    assert "wantJump(room, event)" in link and "wantJump(meta.id, link.event)" in fn(APP, "JoinDialog")


@needs_node
def test_copy_text_and_copy_link_are_in_the_hover_bar_and_copy_the_right_things():
    r = run(MESSAGE_JS + """
const copied = [], toasts = []
globalThis.P = { listen: () => () => {}, setTimeout: f => { f(); return () => {} }, copy: async t => { copied.push(t); return true }, toast: (k, m) => toasts.push(m) }
const id = 'c'.repeat(64)
const m = { id, name: 'Zed', role: 'person', pk: 'p', text: 'hello *there*', ts: 1, mine: false }
const root = mount(Message, { m, first: true, book: {}, store: {}, roomId: 'r1' + '0'.repeat(14) })
const bar = find(root.tree, n => n.type === MessageBar)
const mb = mount(MessageBar, bar.props)
const t = find(mb.tree, n => n.props && n.props['aria-label'] === 'Copy message text'), l = find(mb.tree, n => n.props && n.props['aria-label'] === 'Copy link to this message')
await t.props.onClick(); await l.props.onClick()
const noStore = mount(Message, { m, first: true, book: {} })
out({ copied, hasBoth: !!t && !!l, toasts: toasts.length, none: !find(noStore.tree, n => n.type === MessageBar) })
""")
    assert r["hasBoth"] and r["copied"] == ["hello *there*", "ninsei:r1" + "0" * 14 + "#" + "c" * 64] and r["toasts"] == 2 and r["none"]


@needs_node
def test_a_long_press_on_touch_shows_the_message_actions_and_a_mouse_press_does_not():
    r = run(MESSAGE_JS + """
const m = { id: 'm1', name: 'Zed', role: 'person', pk: 'p', text: 'hi', ts: 1, mine: false }
const root = mount(Message, { m, first: true, book: {}, store: {}, roomId: 'r' })
const node = () => find(root.tree, n => n.props && n.props.className && /h-msg/.test(n.props.className))
const before = node().props['data-bar']
node().props.onPointerDown({ pointerType: 'mouse', clientX: 1, clientY: 1 }); await settle()
const mouse = node().props['data-bar']
node().props.onPointerDown({ pointerType: 'touch', clientX: 1, clientY: 1 }); await settle()
out({ before, mouse, touch: node().props['data-bar'] })
""")
    assert not r["before"] and not r["mouse"] and r["touch"] is True


# ---- mute, chattiness, rename ---------------------------------------------------------------------------------------

def tools_js(*names):
    return TOOLS_PRELUDE + "const HOTKEYS = { search: null }\n" + "".join(fn(TOOLS, n) for n in names)


@needs_node
def test_the_room_menu_mutes_sets_chattiness_and_offers_rename_only_to_the_creator():
    r = run(tools_js("RoomMenu") + """
const posts = [], closes = []
const store = { post: async (path, body) => { posts.push([path, body]); return {} } }
const room = { id: 'r1' }
const snap = { settings: { chattiness: 'lively' } }
const mount1 = rm => mount(RoomMenu, { store, room, rm, snap, anchor: { current: null }, onClose: b => closes.push(b), onEdit: () => closes.push('edit') })
const items = tree => { const out = []; find(tree, n => { if (n.type === 'button') out.push(n); return false }); return out }
const label = b => text(b)
const mine = mount1({ muted: false, chattiness: '', mine: true })
const labels = items(mine.tree).map(label)
const click = (tree, part) => items(tree).find(b => label(b).includes(part)).props.onClick()
click(mine.tree, 'Mute this room'); click(mine.tree, 'Quiet'); click(mine.tree, 'Follow Settings'); click(mine.tree, 'Rename')
const muted = mount1({ muted: true, chattiness: 'quiet', mine: false })
const mlabels = items(muted.tree).map(label)
const checked = items(muted.tree).filter(b => b.props['aria-checked']).map(label)
click(muted.tree, 'Unmute')
out({ labels, mlabels, posts, closes, checked, roles: items(mine.tree).map(b => b.props.role) })
""")
    assert r["labels"][0].startswith("Mute this room") and any(x.startswith("Follow Settings (lively)") for x in r["labels"])
    assert any(x.startswith("Rename") for x in r["labels"]) and not any(x.startswith("Rename") for x in r["mlabels"])
    assert r["mlabels"][0].startswith("Unmute this room")
    assert r["posts"] == [["/rooms/prefs", {"room": "r1", "muted": True}], ["/rooms/prefs", {"room": "r1", "chattiness": "quiet"}],
                          ["/rooms/prefs", {"room": "r1", "chattiness": ""}], ["/rooms/prefs", {"room": "r1", "muted": False}]]
    assert "edit" in r["closes"] and r["checked"] == ["Quiet" + r["checked"][0][5:]]
    assert set(r["roles"]) == {"menuitem", "menuitemradio"}


@needs_node
def test_the_menu_moves_with_arrow_keys_and_escape_closes_it_and_hands_focus_back():
    r = run(tools_js("RoomMenu") + """
const closes = []
const root = mount(RoomMenu, { store: {}, room: { id: 'r' }, rm: { mine: false }, snap: { settings: {} }, anchor: { current: null }, onClose: b => closes.push(b), onEdit() {} })
const menu = () => find(root.tree, n => n.props && n.props.role === 'menu')
const tab = () => [].concat(...[0].map(() => { const o = []; find(root.tree, n => { if (n.type === 'button' && n.props.tabIndex === 0) o.push(text(n)); return false }); return o }))
const first = tab()[0]
const key = k => { let stopped = false; menu().props.onKeyDown({ key: k, preventDefault() {}, stopPropagation() { stopped = true } }); return stopped }
key('ArrowDown'); root.update(root.props); const second = tab()[0]
key('ArrowUp'); root.update(root.props); const back = tab()[0]
key('End'); root.update(root.props); const last = tab()[0]
const stopped = key('Escape')
out({ first, second, back, last, closes, stopped })
""")
    assert r["first"].startswith("Mute") and r["second"] != r["first"] and r["back"] == r["first"] and r["last"].startswith("Lively")
    assert r["closes"] == [True] and r["stopped"] is True


@needs_node
def test_renaming_posts_the_new_words_and_stays_open_when_the_engine_refuses():
    r = run(tools_js("RoomEditDialog") + """
const posts = []; let closed = 0, refuse = false
const store = { post: async (path, body, ok) => { posts.push([path, body, ok]); if (refuse) throw new Error('no'); return {} } }
const root = mount(RoomEditDialog, { store, room: { id: 'r1', name: 'club', about: 'old' }, onClose: () => closed++ })
const dlg = () => root.tree
const inputs = []; find(dlg(), n => { if (n.type === K.Input) inputs.push(n); return false })
inputs[0].props.onChange({ target: { value: '  Shaders  ' } }); inputs[1].props.onChange({ target: { value: 'glow' } })
await settle()
const save = () => button(root.tree, 'Sav')
inputs[0].props.onChange({ target: { value: ' ' } })
await settle()
const disabledWhenEmpty = save().props.disabled
inputs[0].props.onChange({ target: { value: '  Shaders  ' } }); await settle()
await save().props.onClick(); await settle()
refuse = true
await save().props.onClick(); await settle()
out({ posts, closed, disabledWhenEmpty })
""")
    assert r["posts"][0] == ["/rooms/edit", {"room": "r1", "name": "Shaders", "about": "glow"}, "Room updated"]
    assert r["disabledWhenEmpty"] is True and r["closed"] == 1                       # the refused second save did not close it


def test_rename_is_in_the_menu_only_for_rooms_you_made_and_the_snapshot_says_which():
    assert "if (rm.mine)" in fn(TOOLS, "RoomMenu")
    header = fn(ROOM, "RoomHeader")
    assert "RoomMenu" in header and "RoomEditDialog" in header and "'aria-haspopup': 'menu'" in header and "Room options" in header


# ---- alerts and badges for a muted room -----------------------------------------------------------------------------

@needs_node
def test_a_muted_room_makes_no_toast_and_no_os_notification_but_other_rooms_and_dms_still_do():
    r = run(fn(CORE, "cleanSnippet") + fn(CORE, "mentionAlerts") + """
function nav() { return { set() {} } }
const toasts = [], os = []
globalThis.P = { toast: (k, m) => toasts.push(m), osNotify: o => os.push(o.title) }
let listener
const store = { subscribe: fn => { listener = fn; return () => {} }, isShowing: () => false, setRoom() {}, setDm() {} }
mentionAlerts(store)
const room = (id, name, mentions, muted) => ({ id, name, mentions, muted, last_mention: mentions ? { id: 'm' + mentions + id, name: 'Zed', text: 'hey', ts: 1 } : null })
const snap = (a, b, dm) => ({ snap: { rooms: [room('a', 'Quiet room', a, true), room('b', 'Loud room', b, false)], dms: { threads: [{ pk: 'p', name: 'Olu', unread: dm, last_unread: dm ? { id: 'd' + dm, text: 'yo' } : null }], pending: [] } } })
listener(snap(0, 0, 0))                        // the first snapshot is only the baseline
listener(snap(1, 1, 1))
out({ toasts, os })
""")
    assert len(r["toasts"]) == 2 and len(r["os"]) == 2
    assert all("Quiet room" not in t for t in r["toasts"] + r["os"])
    assert any("Loud room" in t for t in r["toasts"]) and any("private message" in t for t in r["toasts"])


def test_a_muted_room_in_the_sidebar_is_dimmed_with_a_quiet_dot_and_no_count():
    rail = fn(APP, "Rail")
    assert "r.muted ? (r.unread > 0 && jsx('span', { className: 'h-dot h-dot-quiet'" in rail
    assert "r.unread && !r.muted ? 600" in rail and "'aria-label': 'Muted'" in rail
    assert ".h-navrow .h-dot-quiet{" in STYLE


# ---- quick switcher -------------------------------------------------------------------------------------------------

@needs_node
def test_fuzzy_matching_wants_the_letters_in_order_and_prefers_starts_and_runs():
    r = run(CORE_FNS + fn(TOOLS, "switcherItems") + fn(TOOLS, "filterSwitcher") + """
const snap = { rooms: [{ id: 'r1', name: 'Shader Club' }, { id: 'r2', name: 'synth lab', muted: true }, { id: 'r3', name: 'Café racers' }],
  dms: { threads: [{ pk: 'a', name: 'Maya', friend: true }, { pk: 'b', name: 'Olu', friend: false }], requests: 2 } }
const items = switcherItems(snap)
const names = q => filterSwitcher(items, q).map(i => i.label)
out({ all: names(''), sc: names('sc'), lab: names('lab'), cafe: names('cafe'), none: names('zzz'), settings: names('set'), maya: filterSwitcher(items, 'may').map(i => [i.kind, i.id]),
      noMatchScore: fuzzyScore('xyz', 'abc'), prefix: fuzzyScore('sh', 'Shader') > fuzzyScore('sh', 'Mesh'), kinds: items.map(i => i.kind) })
""")
    assert r["all"] == ["Lobby", "Your Hermes", "Settings", "Shader Club", "synth lab", "Café racers", "Maya", "Olu", "Friend requests"]
    assert r["sc"] == ["Shader Club"] and r["lab"] == ["synth lab"]
    assert r["cafe"] == ["Café racers"]                                 # no accents
    assert r["none"] == [] and r["noMatchScore"] == -1 and r["prefix"] is True
    assert r["settings"] == ["Settings"] and r["maya"] == [["dm", "a"]]
    assert r["kinds"][:3] == ["lobby", "hermes", "settings"] and r["kinds"][-1] == "requests"


@needs_node
def test_the_switcher_filters_as_you_type_goes_with_enter_and_closes_with_escape():
    r = run(tools_js("switcherItems", "filterSwitcher", "QuickSwitcher") + CORE_FNS + """
const picked = [], closed = []
const snap = { rooms: [{ id: 'r1', name: 'Shader Club' }, { id: 'r2', name: 'Synth lab' }], dms: { threads: [], requests: 0 } }
const root = mount(QuickSwitcher, { snap, onPick: i => picked.push(i.key), onClose: () => closed.push(1) })
const input = () => find(root.tree, n => n.type === 'input')
const opts = () => { const o = []; find(root.tree, n => { if (n.props && n.props.role === 'option') o.push(text(n)); return false }); return o }
const ev = k => ({ key: k, preventDefault() {}, stopPropagation() {}, nativeEvent: {} })
const start = opts().length
input().props.onChange({ target: { value: 'syn' } }); await settle(); root.update(root.props)
const filtered = opts()
input().props.onKeyDown(ev('Enter'))
input().props.onChange({ target: { value: '' } }); await settle(); root.update(root.props)
input().props.onKeyDown(ev('ArrowDown')); root.update(root.props)
input().props.onKeyDown(ev('ArrowDown')); root.update(root.props)
const sel = find(root.tree, n => n.props && n.props.role === 'option' && n.props['aria-selected'] === true)
input().props.onKeyDown(ev('Enter'))
input().props.onKeyDown(ev('Escape'))
input().props.onChange({ target: { value: 'qqq' } }); await settle(); root.update(root.props)
const none = !!find(root.tree, n => n.props && n.props.role === 'status')
out({ start, filtered, picked, selId: sel && sel.props.id, closed, none, dialog: root.tree.props.children.props.role, label: input().props['aria-label'] })
""")
    assert r["start"] == 5 and len(r["filtered"]) == 1 and "Synth lab" in r["filtered"][0]
    assert r["picked"] == ["r-r2", "settings"] and r["selId"] == "h-qs-2"    # two arrows down from the first row reach the third
    assert r["closed"] == [1] and r["none"] is True and r["dialog"] == "dialog" and r["label"] == "Go to"


# ---- keyboard ownership ---------------------------------------------------------------------------------------------

def test_cmd_k_and_cmd_f_belong_to_ninsei_only_while_focus_is_inside_it():
    app = fn(APP, "App")
    assert "r.contains(a)" in app and "live.current" in app                   # focus (or the last click) must be inside the page
    assert "e.metaKey || e.ctrlKey" in app and "e.altKey || e.shiftKey" in app
    assert "HOTKEYS.search &&" in app and "capture: true" in app
    assert "HOTKEYS.search = openSearch" in fn(ROOM, "RoomView")
    # Escape closes search only when nothing nearer took it: another dialog, a drawer, or a handler that prevented it
    view = fn(ROOM, "RoomView")
    assert "e.defaultPrevented" in view and "role=dialog" in view and "data-nav=open" in view


# ---- reconnecting banner, empty states, springs ---------------------------------------------------------------------

@needs_node
def test_the_banner_shows_only_when_every_relay_is_down_and_never_for_the_cleared_offline_case():
    r = run(CORE_FNS + """
const relay = (state, extra) => Object.assign({ url: 'wss://x', state, error: '', retry_s: 0 }, extra)
const snap = (relays, set) => ({ relays, settings: { relays: set || ['wss://x'] } })
out({ allDown: relaysDown(snap([relay('backoff', { retry_s: 12 }), relay('backoff', { retry_s: 4 })])), oneUp: relaysDown(snap([relay('backoff'), relay('open')])),
      firstTry: relaysDown(snap([relay('connecting')])), retrying: relaysDown(snap([relay('connecting', { error: 'OSError' }), relay('backoff', { retry_s: 7 })])),
      offline: relaysDown(snap([], [])), clearedButStatus: relaysDown(snap([relay('backoff')], [])), idle: relaysDown(snap([relay('idle')])), none: relaysDown(null) })
""")
    assert r["allDown"] == {"retry": 4} and r["oneUp"] is None and r["firstTry"] is None
    assert r["retrying"] == {"retry": 7} and r["offline"] is None and r["clearedButStatus"] is None and r["idle"] is None and r["none"] is None


@needs_node
def test_the_banner_counts_down_and_says_when_it_is_trying_now():
    r = run(TOOLS_PRELUDE + fn(TOOLS, "ReconnectBanner") + """
function useNow() { return globalThis.NOW }
const msg = (retry, now) => { globalThis.NOW = now; const root = mount(ReconnectBanner, { snap: {}, retry }); return text(find(root.tree, n => n.type === Notice)) }
const t = Date.now() / 1000
out({ later: msg(30, t + 5), now: msg(3, t + 60) })
""")
    assert r["later"].startswith("Reconnecting to relays…") and "next try in 2" in r["later"] and "trying now" in r["now"]


def test_the_app_draws_the_banner_from_relays_down_and_clears_it_by_itself():
    app = fn(APP, "App")
    assert "relaysDown(snap)" in app and "ReconnectBanner" in app and "!st.error" in app


def test_new_rooms_dms_search_and_lobby_have_proper_empty_states():
    assert "RoomStarter" in fn(ROOM, "Timeline") and "EmptyState" in fn(ROOM, "RoomStarter")
    assert "Nothing found for" in fn(ROOM, "SearchPanel")
    assert "No friends yet" in fn(src("57_dm.js"), "DmEmpty")
    assert "No public rooms yet" in src("70_lobby.js")


def test_typing_dots_and_menus_move_on_springs_and_not_a_css_loop():
    assert "animation:h-breathe" not in STYLE and "@keyframes h-breathe" not in STYLE
    dots = fn(CORE, "Dots")
    assert "motion.spring" in dots and "motion.reduced()" in dots
    for name in ("TypingRow", "Thinking"):
        assert "jsx(Dots, {})" in fn(ROOM, name)
    assert "useEnter(true)" in fn(ROOM, "SuggestMenu") and "useEnter(true)" in fn(ROOM, "GamesMenu")
    assert "useEnter(true)" in fn(TOOLS, "QuickSwitcher") and "useEnter(true)" in fn(TOOLS, "RoomMenu")


# ---- narrow layout --------------------------------------------------------------------------------------------------

def test_below_720px_the_sidebar_is_a_drawer_and_people_a_bottom_sheet_with_touch_sized_actions():
    assert "@container (max-width: 720px)" in STYLE
    narrow = STYLE[STYLE.index("@container (max-width: 720px)"):]
    narrow = narrow[:narrow.index("\n.h-grid{position:relative}")]
    for needle in (".h-left{display:none}", ".h-grid[data-nav=open] .h-left{display:block;position:absolute", ".h-navbar{display:flex",
                   ".h-grid[data-people=open] .h-right{left:0;right:0;top:auto", "env(safe-area-inset-bottom)"):
        assert needle in narrow, needle
    assert "@media (pointer:coarse){.h-bar-btn{" in STYLE
    app = fn(APP, "App")
    assert "'data-nav': drawer ? 'open' : 'closed'" in app and "useSlide(leftRef, drawer" in app and "NavBar" in app
    assert "setDrawer(false)" in app and "h-scrim-nav" in app and "!embedded && jsx(NavBar" in app
    assert ".h-navbar{display:none}" in STYLE and STYLE.index(".h-navbar{display:none}") < STYLE.index("@container (max-width: 720px)")


@needs_node
def test_the_nav_bar_has_a_labelled_menu_button_and_a_switcher_button():
    r = run(TOOLS_PRELUDE + fn(TOOLS, "NavBar") + """
const calls = []
const root = mount(NavBar, { open: false, onToggle: () => calls.push('menu'), onSwitch: () => calls.push('go') })
const btns = []; find(root.tree, n => { if (n.type === K.Button) btns.push(n); return false })
btns.forEach(b => b.props.onClick())
out({ labels: btns.map(b => b.props['aria-label']), expanded: btns[0].props['aria-expanded'], calls })
""")
    assert r["labels"] == ["Open the sidebar", "Go to…"] and r["expanded"] is False and r["calls"] == ["menu", "go"]
