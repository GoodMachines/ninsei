"""The page side of the room, mention, picture and walkthrough review fixes, run under node with the shared hooks
harness (and CSS checks where a test can't draw): lookalike links, pasted room links, reaction pickers, plain
quotes, the emoji menu, "Load earlier" staying true, Discard on a pending message, the narrow room header."""
import re

from test_audit_ui import CORE, ROOM, STYLE, const, fn, needs_node, run
from test_chat_a2 import rich_js
from test_e1_ui import COMPOSER, MESSAGE_JS


# ---- 6: a link's text is where it goes -----------------------------------------------------------------------------

@needs_node
def test_a_lookalike_domain_is_shown_in_its_punycode_form_so_the_text_matches_where_the_link_goes():
    r = run(rich_js() + """
const link = t => { const l = richParts(t, [])[0].tokens.find(x => x.t === 'link'); return l && { text: l.text, href: l.href } }
out({ idn: link('https://аpple.com/login'), plain: link('https://apple.com/login?a=1'), path: link('https://example.com/日本'),
      port: link('https://аpple.com:8443/x'), noPath: link('see https://аpple.com.'), swedish: link('https://bücher.de/') })
""")
    assert r["idn"] == {"text": "https://xn--pple-43d.com/login", "href": "https://xn--pple-43d.com/login"}
    assert r["plain"]["text"] == "https://apple.com/login?a=1"
    assert r["path"]["text"] == "https://example.com/日本"           # the host is ASCII: the text stays as typed
    assert r["port"]["text"] == "https://xn--pple-43d.com:8443/x"
    assert r["noPath"]["text"] == "https://xn--pple-43d.com"                 # trailing punctuation still stays out of it
    assert r["swedish"]["text"] == "https://xn--bcher-kva.de/"


# ---- 8: pasted room links ------------------------------------------------------------------------------------------

@needs_node
def test_parse_room_link_in_the_page_cuts_at_the_first_non_hex_character_like_the_engine():
    r = run(fn(CORE, "parseRoomLink") + """
const ev = 'ab'.repeat(32)
out({ a: parseRoomLink('ninsei:0123456789abcdef please join'), b: parseRoomLink('  0123456789ABCDEF  '), c: parseRoomLink('hello'),
      d: parseRoomLink('ninsei:0123456789abcdef#' + ev), e: parseRoomLink('ninsei:0123456789abcdefzzabc') })
""")
    assert r["a"] == {"room": "0123456789abcdef", "event": ""} and r["b"]["room"] == "0123456789abcdef"
    assert r["c"] == {"room": "", "event": ""} and r["d"]["event"] == "ab" * 32
    assert r["e"]["room"] == "0123456789abcdef"


# ---- 20: reaction pickers ------------------------------------------------------------------------------------------

@needs_node
def test_only_one_reaction_picker_is_open_at_a_time():
    r = run(MESSAGE_JS + "const PICKER = { close: null }\n" + """
const open = [], bars = []
const mk = id => {
  const setPicking = v => { open.push([id, v]) }
  return mount(MessageBar, { m: { id, name: 'X' }, picking: false, setPicking, mine: [], onPick() {} })
}
const a = mk('a'), b = mk('b')
const trigger = r => find(r.tree, n => n.type === 'button' && n.props['aria-label'] === 'Add a reaction')
trigger(a).props.onClick()
trigger(b).props.onClick()
out({ open })
""")
    assert r["open"] == [["a", True], ["a", False], ["b", True]]            # opening b closes a first


@needs_node
def test_a_picker_closes_on_escape_and_on_an_outside_press_but_not_on_its_own_trigger():
    r = run(fn(ROOM, "ReactionPicker") + """
globalThis.document = {}
const inside = { id: 'in' }, trigger = { id: 'tr' }
const useEnter = () => ({ current: { contains: n => n === inside } })
const REACTION_LIST = ['a', 'b']
const listeners = []
globalThis.P = { listen: (t, ev, fn, opts) => { listeners.push({ ev, fn, opts }); return () => {} } }
let closed = 0
mount(ReactionPicker, { mine: [], trigger: { current: { contains: n => n === trigger } }, onClose: () => { closed++ }, onPick() {} })
const on = ev => listeners.find(l => l.ev === ev)
const esc = { key: 'Escape', preventDefault() {}, stopPropagation() {} }
on('keydown').fn(esc)
const afterEsc = closed
on('pointerdown').fn({ target: inside })
on('pointerdown').fn({ target: trigger })
const afterInside = closed
on('pointerdown').fn({ target: { id: 'out' } })
out({ afterEsc, afterInside, afterOutside: closed, capture: !!(on('keydown').opts && on('keydown').opts.capture) })
""")
    assert r == {"afterEsc": 1, "afterInside": 1, "afterOutside": 2, "capture": True}


def test_the_hover_bar_leaves_the_quote_above_a_continued_message_alone():
    assert "'data-quoted': !!m.quote || undefined" in fn(ROOM, "Message")
    assert ".h-msg[data-quoted=true]:not([data-first=true]){padding-top:17px}" in STYLE   # the bar sits in this strip, above the quote


# ---- 21: quotes are plain text -----------------------------------------------------------------------------------

@needs_node
def test_a_quote_shows_plain_text_without_markers():
    r = run(fn(ROOM, "QuoteLine") + """
const ImpostorChip = function ImpostorChip() {}
K.Icon = function Icon() {}
const quote = t => { const root = mount(QuoteLine, { quote: { id: 'q', name: 'Ann', text: t, role: 'person' } })
  return text(find(root.tree, n => n.props && n.props.className === 'h-quote-t')) }
out({ cut: quote('**walkthr'), pair: quote('**bold** and __under__ and ~~gone~~ `code`'), link: quote('see [the docs](https://x.example/a?b=1) now'),
      gt: quote('> quoted\\n> twice'), plain: quote('just words, 2 * 3 = 6') })
""")
    assert r["cut"] == "walkthr" and r["pair"] == "bold and under and gone code"
    assert r["link"] == "see the docs now" and r["gt"] == "quoted twice" and r["plain"] == "just words, 2 * 3 = 6"


# ---- 22: the emoji menu --------------------------------------------------------------------------------------------

@needs_node
def test_completing_a_shortcode_before_an_existing_space_adds_no_second_space():
    r = run(COMPOSER + """
globalThis.P = { setTimeout: () => () => {}, prefs: { get: (k, d) => d, set() {} } }
const box = mount(Composer, { store: {}, room: { id: 'r1', name: 'club', members: [] }, onSubmit() {} })
area(box).props.onChange(ev('hey :fir there', 8)); await settle()
area(box).props.onKeyDown(key('Enter')); await settle()
const mid = area(box).props.value
area(box).props.onChange(ev('end :fir')); await settle()
area(box).props.onKeyDown(key('Tab')); await settle()
out({ mid, end: area(box).props.value })
""")
    assert r["mid"] == "hey \U0001F525 there" and r["end"] == "end \U0001F525 "


# ---- 4: "Load earlier" pages catch up ---------------------------------------------------------------------------------

@needs_node
def test_loaded_earlier_pages_are_asked_for_again_when_the_room_changes_and_show_a_delete():
    js = (fn(CORE, "mergeOlder") + fn(CORE, "earlierState") + const(CORE, "EARLIER") + const(CORE, "EARLIER_CAP")
          + fn(ROOM, "useEarlier").replace("EARLIER_REFRESH_MS", "5") + """
function useMemo(f) { return f() }
globalThis.P = { toast() {} }
const m = (id, extra) => Object.assign({ id, ts: 1, t: 'msg', text: id }, extra)
const snap = () => [m('s1'), m('s2')]
let asked = [], fresh = [m('o1'), m('o2', { deleted: true, text: '' })]
const fetchPage = async id => ({ messages: [m('o1'), m('o2')], more: false })
const refetch = async (since, id) => { asked.push([since, id]); return { messages: fresh, more: false } }
function T(props) { return useEarlier('room', props.snap, true, fetchPage, props.refetch, props.rev) }
const root = mount(T, { snap: snap(), refetch, rev: 1 })
await root.tree.load(); await settle()
const loaded = root.tree.msgs.map(x => x.id + ':' + (x.deleted ? 'deleted' : x.text))
root.update({ snap: snap(), refetch, rev: 2 })
await new Promise(r => setTimeout(r, 60)); await settle()
const after = root.tree.msgs.map(x => x.id + ':' + (x.deleted ? 'deleted' : x.text))
// a private conversation passes no refetch: nothing is asked
const roomAsked = asked.slice(); EARLIER.delete('dm'); asked = []
function D(props) { return useEarlier('dm', props.snap, true, fetchPage) }
const dm = mount(D, { snap: snap() })
await dm.tree.load(); dm.update({ snap: snap() }); await new Promise(r => setTimeout(r, 60))
out({ loaded, after, asked: roomAsked, dmAsked: asked.length })
""")
    r = run(js)
    assert r["loaded"] == ["o1:o1", "o2:o2", "s1:s1", "s2:s2"]
    assert r["after"] == ["o1:o1", "o2:deleted", "s1:s1", "s2:s2"]
    assert r["asked"] == [[1, "s1"]] and r["dmAsked"] == 0


# ---- 5: Discard also on a message still waiting ----------------------------------------------------------------------

@needs_node
def test_a_message_waiting_for_a_relay_offers_discard_but_not_retry():
    r = run(MESSAGE_JS + """
const base = { id: 'm1', name: 'Me', role: 'person', pk: 'p', text: 'hi', ts: 1, mine: true, delivery: 'pending' }
const calls = []
const root = mount(Message, { m: base, first: true, book: {}, onRetry() {}, onDiscard: m => calls.push(m.id) })
const d = button(root.tree, 'Discard')
d && d.props.onClick()
out({ has: !!d, retry: !!button(root.tree, 'Retry'), calls })
""")
    assert r == {"has": True, "retry": False, "calls": ["m1"]}


# ---- 23: the room header at phone width ---------------------------------------------------------------------------------

def test_the_room_header_stacks_cleanly_under_the_narrow_breakpoint():
    narrow = STYLE[STYLE.index("@container (max-width: 720px)"):]
    narrow = narrow[:narrow.index(".h-composer{padding-bottom")]
    # the title block takes a whole row (name and count, then the topic), so the action buttons wrap to their own row
    assert re.search(r"\.h-head\{[^}]*flex-wrap:wrap", narrow)
    assert ".h-head>.h-grow{flex:1 1 100%" in narrow
    # and the name keeps at least 16 characters before it truncates
    assert ".h-head>.h-grow h2{min-width:16ch}" in narrow
    # nothing in the header is positioned over the timeline
    head = re.search(r"\.h-head\{display:flex[^}]*\}", STYLE).group(0)
    assert "position:absolute" not in head and "height:" not in head.replace("min-height", "")
    assert "<div className=\"h-head\"" not in ROOM and "className: 'h-head'" in fn(ROOM, "RoomHeader")
