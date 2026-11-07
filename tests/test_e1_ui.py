"""Chat polish, first half (Batch E1), the page side, run under node with the shared hooks harness: day lines,
older messages, where you were, full dates on hover, the faint just-sent message with Retry and Discard, drafts,
the Up arrow and :shortcode: emoji."""
import pytest

from test_audit_ui import CORE, ROOM, STYLE, block, composer_js, fn, needs_node, run
from test_chat_a2 import TIMELINE_HOOKS, TIMELINE_PRELUDE
from test_dm_ui import DM, dm_js

DAYS = "".join(fn(CORE, n) for n in ("dayLabel", "dayKey", "fmtFull"))


# ---- days and dates -----------------------------------------------------------------------------------------------

@needs_node
def test_day_labels_are_today_yesterday_then_the_date_and_the_year_only_when_it_is_not_this_one():
    r = run(DAYS + """
const now = new Date(2026, 10, 7, 15, 0)
const at = (y, mo, d, h) => new Date(y, mo, d, h || 9, 0).getTime() / 1000
out({ today: dayLabel(at(2026, 10, 7, 0), now), late: dayLabel(at(2026, 10, 7, 23), now),
      yesterday: dayLabel(at(2026, 10, 6, 23), now), earlier: dayLabel(at(2026, 10, 3), now),
      lastYear: dayLabel(at(2025, 11, 30), now), bad: dayLabel(NaN, now), badKey: dayKey(undefined),
      sameDay: dayKey(at(2026, 10, 7, 1)) === dayKey(at(2026, 10, 7, 23)), nextDay: dayKey(at(2026, 10, 7, 23)) !== dayKey(at(2026, 10, 8, 0)),
      full: fmtFull(at(2026, 10, 3)), badFull: fmtFull('x') })
""")
    assert r["today"] == "Today" and r["late"] == "Today" and r["yesterday"] == "Yesterday"
    assert "Nov" in r["earlier"] and "3" in r["earlier"] and "2026" not in r["earlier"]       # "Tue, Nov 3" in en-US
    assert "2025" in r["lastYear"] and r["bad"] == "" and r["badKey"] == ""
    assert r["sameDay"] and r["nextDay"]
    assert "2026" in r["full"] and "November" in r["full"] and ":" in r["full"] and r["badFull"] == ""


@needs_node
def test_a_day_line_goes_before_the_first_item_of_each_day_and_breaks_a_run_of_one_speaker():
    r = run(fn(ROOM, "groupItems") + DAYS + """
const t = (d, h) => new Date(2026, 10, d, h, 0).getTime() / 1000
const m = (id, ts, extra) => Object.assign({ id, ts, t: 'msg', pk: 'p', text: id }, extra)
const items = groupItems([m('a', t(5, 9)), m('b', t(5, 9) + 30), m('c', t(6, 9)), { id: 'j', ts: t(7, 8), t: 'join', name: 'Z' }, m('d', t(7, 9))], 0)
out({ kinds: items.map(i => i.kind === 'day' ? 'day' : i.m ? i.m.id : i.kind), firsts: items.filter(i => i.kind === 'msg').map(i => i.first),
      keys: items.filter(i => i.kind === 'day').map(i => i.key), newAfterDay: groupItems([m('x', t(5, 9)), m('y', t(6, 9))], t(5, 10)).map(i => i.kind) })
""")
    assert r["kinds"] == ["day", "a", "b", "day", "c", "day", "joins", "d"]
    assert r["firsts"] == [True, False, True, True]               # the speaker's run starts over after a day line
    assert len(set(r["keys"])) == 3
    assert r["newAfterDay"] == ["day", "msg", "day", "new", "msg"]   # the New line sits between the day line and its message


def test_every_time_label_carries_the_full_date_on_hover():
    msg = fn(ROOM, "Message")
    assert "title: fmtFull(m.ts), children: fmtTime(m.ts)" in msg and msg.count("fmtFull(m.ts)") >= 2     # header and gutter
    assert "'Edited ' + fmtFull(m.edited_at || m.ts)" in fn(ROOM, "MessageBody")
    assert "title: fmtFull(m.ts), children: fmtWhen(m.ts)" in fn(ROOM, "SearchRow")
    assert "title: fmtFull(props.ts)" in fn(ROOM, "DayLine")
    for sel in (".h-day{", ".h-gtime{", ".h-msg:hover .h-gtime", ".h-sr-day{", ".h-earlier{", ".h-msg[data-faint=true]"):
        assert sel in STYLE, sel


# ---- older messages -----------------------------------------------------------------------------------------------

@needs_node
def test_older_pages_join_the_snapshot_without_a_gap_or_a_repeat_as_the_window_slides():
    r = run(fn(CORE, "mergeOlder") + """
const mk = ids => ids.map(id => ({ id }))
const ids = l => l.map(m => m.id)
const older = mk(['a', 'b'])
// nothing loaded: nothing to keep
const none = mergeOlder([], mk(['c', 'd']), mk(['d', 'e']))
// the window slid by one (c left it): c joins the older run
const slid = ids(mergeOlder(older, mk(['c', 'd', 'e']), mk(['d', 'e', 'f'])))
// an item that is in both is shown once, in the snapshot
const dup = ids(mergeOlder(mk(['a', 'b', 'c']), mk(['d']), mk(['c', 'd'])))
// the same snapshot again changes nothing
const same = ids(mergeOlder(older, mk(['c', 'd']), mk(['c', 'd'])))
out({ none: none.length, slid, dup, same })
""")
    assert r["none"] == 0 and r["slid"] == ["a", "b", "c"] and r["dup"] == ["a", "b"] and r["same"] == ["a", "b"]


@needs_node
def test_load_earlier_fetches_the_page_before_the_oldest_and_keeps_the_view_where_it_was():
    js = fn(ROOM, "groupItems") + fn(ROOM, "Timeline") + fn(ROOM, "JumpPill") + TIMELINE_PRELUDE + TIMELINE_HOOKS + """
const m = (id, ts) => ({ id, ts, t: 'msg', pk: 'p', name: 'Zed', text: id })
const asked = []
globalThis.P = { toast() {}, rest: async path => { asked.push(path); return { messages: [m('o1', 1), m('o2', 2)], more: false } } }
const room = { id: 'r', earlier: true, messages: [m('a', 10), m('b', 11)], members: [] }
const props = r => ({ store: {}, snap: { me: { pk: 'p', name: 'Me' } }, room: r, book: {}, newAfter: 0 })
const root = mount(Timeline, props(room))
const scroll = () => find(root.tree, n => n.props && n.props.className === 'h-scroll')
const ids = () => root.tree && find(root.tree, n => n.props && n.props.role === 'log').props.children.flat().filter(c => c && c.type === TimelineItem).map(c => c.props.it.m && c.props.it.m.id).filter(Boolean)
const btn = () => find(root.tree, n => n.type === EarlierButton)
const el = { scrollHeight: 1000, scrollTop: 10, clientHeight: 400, querySelector: () => null, getBoundingClientRect: () => ({ top: 0 }) }
scroll().props.ref.current = el
const hadButton = !!btn()
btn().props.onClick()          // the page is asked for, then the list grows by 2 items (200px taller)
el.scrollHeight = 1200
await settle()
const asked1 = asked.slice()
root.update(props(room))
await settle()
out({ hadButton, asked: asked1, ids: ids(), top: el.scrollTop, buttonAfter: !!btn(), animated: find(root.tree, n => n.props && n.props.role === 'log').props.children.flat().filter(c => c && c.type === TimelineItem).map(c => c.props.animate) })
"""
    r = run(js)
    assert r["hadButton"] is True
    assert r["asked"] == ["/messages/earlier?room=r&before=a"]
    assert r["ids"] == ["o1", "o2", "a", "b"] and r["buttonAfter"] is False   # the page said there is nothing older
    assert r["top"] == 210                                                    # 10 + the 200px that came in above
    assert not any(r["animated"])                                             # history never animates in


@needs_node
def test_scrolling_to_the_top_loads_earlier_messages_once_at_a_time():
    js = fn(ROOM, "useScrollKeeper") + """
const useLayoutEffect = useEffect
const SCROLLED = new Map()
let loads = 0, release = null
function Probe(props) { return { k: useScrollKeeper('k', true, props.msgs, true, () => { loads++; return new Promise(r => { release = r }) }) } }
const root = mount(Probe, { msgs: [{ id: 'a' }, { id: 'b' }] })
const el = { scrollHeight: 2000, scrollTop: 30, clientHeight: 500, querySelector: () => null, getBoundingClientRect: () => ({ top: 0 }) }
root.tree.k.scroller.current = el
root.tree.k.onScroll(); root.tree.k.onScroll(); await settle()          // twice at the top: one request
const during = loads
release(true); await settle()
el.scrollTop = 900; root.tree.k.onScroll(); await settle()               // away from the top: nothing
el.scrollTop = 5; root.tree.k.onScroll(); await settle()
out({ during, after: loads })
"""
    r = run(js)
    assert r == {"during": 1, "after": 2}


# ---- where you were -----------------------------------------------------------------------------------------------

def _probe(extra):
    return fn(ROOM, "useScrollKeeper") + """
const useLayoutEffect = useEffect
const SCROLLED = new Map()
function Probe(props) { return { k: useScrollKeeper(props.k, true, props.msgs, false, null) } }
const line = top => ({ getBoundingClientRect: () => ({ top }) })
const fake = (withLine) => ({ scrollHeight: 2000, scrollTop: 0, clientHeight: 500, querySelector: sel => (withLine && sel === '[data-newline]' ? line(300) : null), getBoundingClientRect: () => ({ top: 50 }) })
// the first render has no element yet (the page draws it after); a render with a new key places the list again
async function open(key, el, msgs) {
  const root = mount(Probe, { k: 'start', msgs })
  root.tree.k.scroller.current = el
  root.update({ k: key, msgs })
  await settle()
  return root
}
""" + extra


@needs_node
def test_a_room_opens_at_the_new_line_else_where_you_left_it_else_at_the_end():
    r = run(_probe("""
const msgs = [{ id: 'a' }]
const withLine = fake(true); await open('r1', withLine, msgs)
const noLine = fake(false); await open('r2', noLine, msgs)
SCROLLED.set('r3', { top: 640, stick: false })
const back = fake(true); await open('r3', back, msgs)                 // remembered beats the New line
SCROLLED.set('r4', { top: 1500, stick: true })
const atEnd = fake(true); await open('r4', atEnd, msgs)               // left at the bottom, new ones since: the line
const roots = mount(Probe, { k: 'r5', msgs }); const el5 = fake(false); roots.tree.k.scroller.current = el5
el5.scrollTop = 700; roots.tree.k.onScroll()                          // scrolling is remembered under the room's key (once placed)
out({ line: withLine.scrollTop, end: noLine.scrollTop, back: back.scrollTop, atEnd: atEnd.scrollTop })
"""))
    assert r == {"line": 222, "end": 2000, "back": 640, "atEnd": 222}      # 300 - 50 - 28 for the line


@needs_node
def test_leaving_a_room_remembers_the_scroll_position_and_a_room_at_the_bottom_is_remembered_as_following():
    r = run(fn(ROOM, "useScrollKeeper") + """
const useLayoutEffect = useEffect
const SCROLLED = new Map()
function Probe(props) { return { k: useScrollKeeper(props.k, true, props.msgs, false, null) } }
const root = mount(Probe, { k: 'start', msgs: [{ id: 'a' }] })
const el = { scrollHeight: 2000, scrollTop: 0, clientHeight: 500, querySelector: () => null, getBoundingClientRect: () => ({ top: 0 }) }
root.tree.k.scroller.current = el
root.update({ k: 'room', msgs: [{ id: 'a' }, { id: 'b' }] }); await settle()   // first render with an element: placed at the end
el.scrollTop = 800; root.tree.k.onScroll()
const up = JSON.stringify(SCROLLED.get('room'))
el.scrollTop = 1490; root.tree.k.onScroll()
out({ up, bottom: JSON.stringify(SCROLLED.get('room')) })
""")
    assert r["up"] == '{"top":800,"stick":false}' and r["bottom"] == '{"top":1490,"stick":true}'


# ---- sending: faint at once, Retry and Discard --------------------------------------------------------------------

OUTBOX = "".join(fn(CORE, n) for n in ("outboxSet", "useOutbox", "outboxSend", "outboxSweep", "outboxItem")) + """
const OUTBOX = new Map(), OUTBOX_FNS = new Set(); let OUTBOX_N = 0
"""


@needs_node
def test_a_sent_message_is_there_at_once_and_becomes_posted_then_leaves_when_the_room_has_it():
    r = run(OUTBOX + """
let release
const sends = outboxSend('r', 'hello', { id: 'q', name: 'Maya', text: 'earlier' }, () => new Promise(res => { release = res }))
await settle()
const first = OUTBOX.get('r').map(e => [e.state, e.text])
const item = outboxItem(OUTBOX.get('r')[0], { pk: 'me', name: 'Justin' })
release({ id: 'e1' }); await sends
const posted = OUTBOX.get('r').map(e => [e.state, e.id])
outboxSweep('r', new Set(['zzz']))           // the room doesn't have it yet: it stays
const stays = OUTBOX.get('r').length
outboxSweep('r', new Set(['e1']))
out({ first, item, posted, stays, gone: !OUTBOX.has('r') })
""")
    assert r["first"] == [["sending", "hello"]]
    it = r["item"]
    assert it["mine"] and it["optimistic"] and it["delivery"] == "sending" and it["name"] == "Justin" and it["pk"] == "me"
    assert it["reply_to"] == "q" and it["quote"]["name"] == "Maya" and it["t"] == "msg" and it["role"] == "person"
    assert r["posted"] == [["posted", "e1"]] and r["stays"] == 1 and r["gone"] is True


@needs_node
def test_a_refused_send_becomes_a_failed_message_that_can_be_retried_or_discarded():
    r = run(OUTBOX + """
await outboxSend('r', 'nope', null, () => Promise.reject(new Error('refused')))
const e = OUTBOX.get('r')[0]
const item = outboxItem(e, { pk: 'me', name: 'J' })
outboxSet('r', l => l.filter(x => x.tmp !== e.tmp))
out({ state: e.state, delivery: item.delivery, local: item.local, left: OUTBOX.has('r') })
""")
    assert r == {"state": "failed", "delivery": "failed", "local": True, "left": False}


MESSAGE_JS = "".join(fn(ROOM, n) for n in ("Message", "MessageBody", "MessageEditor", "MessageBar", "DeleteConfirm", "QuoteLine")) + fn(CORE, "fmtFull") + """
const useEnter = () => ({ current: null }); const useLayoutEffect = useEffect
globalThis.P = { listen: () => () => {}, setTimeout: f => { f(); return () => {} } }; globalThis.document = {}
const SPRING = { pop: {}, calm: {} }; const motion = { reduced: () => true }
const cx = (...a) => a.filter(Boolean).join(' ')
function ProfileButton() {}; function Face() {}; function Initial() {}; function PersonMark() {}; function RichText() {}; function ImpostorChip() {}; function ReactionPicker() {}; function ReactionChips() {}; function Modal() {}
const faceFor = () => ({ hue: 1 }); const fmtTime = () => '10:00'
K.Tip = function Tip() {}
"""


@needs_node
def test_a_message_that_is_going_out_is_faint_and_a_failed_one_offers_retry_and_discard():
    r = run(MESSAGE_JS + """
const base = { id: 'm1', name: 'Me', role: 'person', pk: 'p', text: 'hi', ts: 1, mine: true }
const get = (extra, props) => mount(Message, Object.assign({ m: Object.assign({}, base, extra), first: true, book: {} }, props || {}))
const root = tree => find(tree, n => n.props && n.props.className && /h-msg/.test(n.props.className))
const faintOf = r => root(r.tree).props['data-faint'] === true
const sending = get({ delivery: 'sending', optimistic: true }, { store: {} })
const pending = get({ delivery: 'pending' })
const calls = []
const failed = get({ delivery: 'failed' }, { onRetry: m => calls.push('retry:' + m.id), onDiscard: m => calls.push('discard:' + m.id) })
const retry = button(failed.tree, 'Retry'), discard = button(failed.tree, 'Discard')
retry.props.onClick(); discard.props.onClick()
const local = get({ delivery: 'failed', local: true }, { onRetry() {}, onDiscard() {} })
const sent = get({}, { onRetry() {}, onDiscard() {} })
const plain = get({ delivery: 'failed' })
out({ sendingFaint: faintOf(sending), busy: root(sending.tree).props['aria-busy'], pendingFaint: faintOf(pending), failedFaint: faintOf(failed), sentFaint: faintOf(sent),
      calls, hasBar: !!find(sending.tree, n => n.type === MessageBar), noRetryOnSent: !button(sent.tree, 'Retry'), noRetryWithoutHandler: !button(plain.tree, 'Retry'),
      localText: text(find(local.tree, n => n.props && n.props.className && /h-failrow/.test(n.props.className))), failedAlert: find(failed.tree, n => n.props && n.props.className && /h-failrow/.test(n.props.className)).props.role })
""")
    assert r["sendingFaint"] is True and r["busy"] is True and r["pendingFaint"] is True
    assert r["failedFaint"] is False and r["sentFaint"] is False
    assert r["calls"] == ["retry:m1", "discard:m1"] and r["failedAlert"] == "alert"
    assert r["hasBar"] is False                      # nothing to react to or reply to until the room has it
    assert r["noRetryOnSent"] and r["noRetryWithoutHandler"] and r["localText"].startswith("Not sent.")


@needs_node
def test_a_message_that_just_went_through_settles_to_full_strength_on_a_spring():
    r = run(MESSAGE_JS.replace("const motion = { reduced: () => true }", """
const springs = []
const motion = { reduced: () => false, spring: o => { springs.push([o.from, o.to]); o.onUpdate(0.75); o.onRest && o.onRest(); return { stop() {} } } }""") + """
const el = { style: { opacity: 'x' } }
const m = d => ({ id: 'm1', name: 'Me', role: 'person', pk: 'p', text: 'hi', ts: 1, mine: true, delivery: d })
const root = mount(Message, { m: m('sending'), first: true, book: {} })
// the page attaches the element; the next render sees the message as delivered
find(root.tree, n => n.props && n.props.className && /h-msg/.test(n.props.className)).props.ref.current = el
root.update({ m: m(undefined), first: true, book: {} })
await settle()
const history = mount(Message, { m: m(undefined), first: true, book: {} })     // a message that was never faint does not animate
out({ springs, opacity: el.style.opacity })
""")
    assert r["springs"] == [[0.5, 1]] and r["opacity"] == ""


@needs_node
def test_retry_and_discard_post_to_the_engine_for_a_message_it_has_and_resend_a_local_one():
    js = fn(ROOM, "RoomView") + OUTBOX + """
const useLayoutEffect = useEffect; const useMemo = f => f()
const HOTKEYS = { search: null }; function RoomHeader() {}; function SearchPanel() {}; function Timeline() {}; function Notice() {}; function TallTales() {}; function DraftTray() {}; function TypingLine() {}; function Composer() {}
function nameBook() { return {} }
const posts = []
const store = { showing: () => () => {}, post: async (path, body) => { posts.push([path, body]); return { id: 'e9' } } }
const room = { id: 'r1', name: 'club', messages: [], members: [] }
const snap = { rooms: [{ id: 'r1', last_read: 0 }], me: { pk: 'me', name: 'J' }, drafts: [] }
const root = mount(RoomView, { store, snap, room })
const tl = find(root.tree, n => n.type === Timeline), comp = find(root.tree, n => n.type === Composer)
tl.props.onRetry({ id: 'e1' }); tl.props.onDiscard({ id: 'e2' })
await comp.props.onSubmit('hello', null); await settle()
outboxSet('r1', l => l.map(e => Object.assign({}, e, { state: 'failed' })))
const local = OUTBOX.get('r1')[0]
tl.props.onRetry({ id: local.tmp, local: true }); await settle()
tl.props.onDiscard({ id: OUTBOX.get('r1').find(e => e.state !== 'failed') ? 'none' : 'none', local: true })
out({ posts })
"""
    r = run(js)
    assert r["posts"][:2] == [["/post/retry", {"room": "r1", "id": "e1"}], ["/post/discard", {"room": "r1", "id": "e2"}]]
    assert r["posts"][2] == ["/post", {"room": "r1", "text": "hello"}]
    assert r["posts"][3] == ["/post", {"room": "r1", "text": "hello"}]        # the local retry sends the same words again


# ---- drafts -------------------------------------------------------------------------------------------------------

COMPOSER = composer_js() + fn(ROOM, "mentionCandidates") + fn(ROOM, "Composer") + "".join(
    fn(CORE, n) for n in ("squashName", "mentionNames", "mentionParts", "mentionQuery", "mentionMatches")) + """
function useMemo(f) { return f() }
const useLayoutEffect = useEffect
function Face() {}; function PersonMark() {}; function typingPing() {}; function GamesMenu() {}; function gameName(m) { return m }
K.Tip = function Tip() {}
const area = r => find(r.tree, n => n.type === 'textarea')
const ev = (value, caret) => ({ target: { value, selectionStart: caret == null ? value.length : caret } })
const key = (k, extra) => Object.assign({ key: k, shiftKey: false, nativeEvent: { isComposing: false }, preventDefault() { this.prevented = true }, stopPropagation() {} }, extra || {})
"""


@needs_node
def test_unsent_text_is_kept_per_room_and_per_private_conversation_and_cleared_when_sent():
    r = run(COMPOSER + """
const stored = {}
globalThis.P = { setTimeout: f => { f(); return () => {} }, prefs: { get: (k, d) => (k in stored ? JSON.parse(stored[k]) : d), set: (k, v) => { stored[k] = JSON.stringify(v) } } }
const room = id => ({ id, name: id, members: [] })
const sent = []
const one = mount(Composer, { store: {}, room: room('r1'), onSubmit: (t, r) => sent.push(t) })
area(one).props.onChange(ev('half a thou')); await settle()
const dmBox = mount(Composer, { store: {}, room: room('dm-x'), dm: { onSend: t => sent.push('dm:' + t), placeholder: 'p', max: 2000 } })
area(dmBox).props.onChange(ev('private draft')); await settle()
const back = mount(Composer, { store: {}, room: room('r1') })                      // you came back to the room
const other = mount(Composer, { store: {}, room: room('r2') })
const dmBack = mount(Composer, { store: {}, room: room('dm-x'), dm: { onSend() {}, placeholder: 'p', max: 2000 } })
one.update(one.props)                                                               // (mount() points the setters at the newest root)
area(one).props.onKeyDown(key('Enter')); await settle()                              // send: the draft is gone
const after = mount(Composer, { store: {}, room: room('r1') })
DRAFTS.clear()                                                                     // a restart: only the page's storage remains
const restarted = mount(Composer, { store: {}, room: room('dm-x'), dm: { onSend() {}, placeholder: 'p', max: 2000 } })
out({ back: area(back).props.value, other: area(other).props.value, dm: area(dmBack).props.value, sent, after: area(after).props.value,
      restarted: area(restarted).props.value, keys: Object.keys(JSON.parse(stored.drafts)) })
""")
    assert r["back"] == "half a thou" and r["other"] == "" and r["dm"] == "private draft"
    assert r["sent"] == ["half a thou"] and r["after"] == ""
    assert r["restarted"] == "private draft" and r["keys"] == ["dm-x"]


@needs_node
def test_drafts_survive_storage_that_throws_and_are_capped():
    r = run(fn(CORE, "draftGet") + fn(CORE, "draftSet") + """
const DRAFTS = new Map(), DRAFT_MAX = 20, DRAFT_KEEP = 3, draftDirty = new Set(); let draftStop = null
globalThis.P = { setTimeout: f => { f(); return () => {} }, prefs: { get() { throw new Error('private window') }, set() { throw new Error('quota') } } }
draftSet('a', 'x'.repeat(50))
const mem = draftGet('a')                                    // storage throws: still there, and cut to the cap
let store = {}
globalThis.P = { setTimeout: f => { f(); return () => {} }, prefs: { get: (k, d) => store[k] || d, set: (k, v) => { store[k] = v } } }
for (const k of ['k1', 'k2', 'k3', 'k4', 'k5']) draftSet(k, 'text ' + k)
draftSet('k2', '')
out({ mem: mem.length, keys: Object.keys(store.drafts), fresh: draftGet('never-seen') })
""")
    assert r["mem"] == 20 and r["keys"] == ["k3", "k4", "k5"] and r["fresh"] == ""    # the newest three, the empty one gone


# ---- the Up arrow -------------------------------------------------------------------------------------------------

@needs_node
def test_the_up_arrow_in_an_empty_composer_asks_to_edit_the_last_message_and_nothing_else_does():
    r = run(COMPOSER + """
globalThis.P = { setTimeout: () => () => {}, prefs: { get: (k, d) => d, set() {} } }
const room = { id: 'r1', name: 'club', members: [] }
let asked = 0, found = true
const box = mount(Composer, { store: {}, room, onSubmit() {}, onEditLast: () => { asked++; return found } })
const up = (opts) => { const e = key('ArrowUp', opts); area(box).props.onKeyDown(e); return e.prevented === true }
const empty = up()
found = false; const nothing = up(); found = true       // no message of yours to edit: the key does its usual thing
const withShift = up({ shiftKey: true })
area(box).props.onChange(ev('typed')); await settle()
const withText = up()
area(box).props.onChange(ev('')); await settle()
const dmBox = mount(Composer, { store: {}, room: { id: 'dm-x', name: 'Sam', members: [] }, dm: { onSend() {}, placeholder: 'p', max: 2000 } })
const e2 = key('ArrowUp'); area(dmBox).props.onKeyDown(e2)
out({ empty, nothing, withShift, withText, asked, dmPrevented: e2.prevented === true })
""")
    assert r == {"empty": True, "nothing": False, "withShift": False, "withText": False, "asked": 2, "dmPrevented": False}


@needs_node
def test_your_last_message_opens_its_editor_when_asked_and_only_yours_and_the_room_view_picks_it():
    r = run(MESSAGE_JS + """
const base = { id: 'm1', name: 'Me', role: 'person', pk: 'p', text: 'hi', ts: 1, mine: true }
let done = 0, focused = 0
const asked = mount(Message, { m: base, first: true, book: {}, store: {}, roomId: 'r', editReq: { id: 'm1', n: 1 }, onEditDone: () => { done++ }, onFocusComposer: () => { focused++ } })
await settle()
const editor = find(asked.tree, n => n.type === MessageEditor)
editor.props.onCancel(); await settle()                                  // Escape after an Up arrow: back to the composer
const other = mount(Message, { m: Object.assign({}, base, { id: 'm2' }), first: true, book: {}, store: {}, roomId: 'r', editReq: { id: 'm1', n: 1 }, onEditDone() { done += 100 } })
const theirs = mount(Message, { m: Object.assign({}, base, { mine: false }), first: true, book: {}, store: {}, roomId: 'r', editReq: { id: 'm1', n: 1 }, onEditDone() { done += 100 } })
await settle()
out({ opened: !!editor, done, focused, otherOpened: !!find(other.tree, n => n.type === MessageEditor), theirsOpened: !!find(theirs.tree, n => n.type === MessageEditor) })
""")
    assert r == {"opened": True, "done": 1, "focused": 1, "otherOpened": False, "theirsOpened": False}
    view = fn(ROOM, "RoomView")
    assert "m.t === 'msg' && m.mine && m.role === 'person' && !m.deleted && !m.system" in view
    assert "onEditLast" in view and "editReq" in fn(ROOM, "Timeline")


# ---- :shortcode: emoji --------------------------------------------------------------------------------------------

@needs_node
def test_shortcodes_match_by_prefix_first_and_never_inside_times_words_or_urls():
    r = run(fn(CORE, "shortcodeQuery") + fn(CORE, "shortcodeMatches") + fn(CORE, "shortcodeClosed") + block(CORE, "EMOJI_SHORTCODES") + """
const q = (t, c) => shortcodeQuery(t, c == null ? t.length : c)
out({ fire: q('hey :fi'), start: q(':fi'), one: q('hey :f'), time: q('at 10:30'), digits: q('look :30'), word: q('foo:bar'), url: q('see http://x'), paren: q('(:smi'), upper: q('x :FIRE'),
      mid: q('hey :fi there', 7), after: q('hey :fire stop'),
      m: shortcodeMatches('fi').map(x => x.code), none: shortcodeMatches('qqqq').length, limit: shortcodeMatches('e', 3).length, thumbs: shortcodeMatches('thumbsu').map(x => x.emoji),
      closed: shortcodeClosed('go :fire:'), notACode: shortcodeClosed('go :notacode:'), t: shortcodeClosed('12:30:45'), size: EMOJI_SHORTCODES.length })
""")
    assert r["fire"] == {"at": 4, "q": "fi"} and r["start"] == {"at": 0, "q": "fi"} and r["one"] is None
    assert r["time"] is None and r["digits"] is None and r["word"] is None and r["url"] is None
    assert r["paren"] == {"at": 1, "q": "smi"} and r["upper"] == {"at": 2, "q": "fire"}
    assert r["mid"] == {"at": 4, "q": "fi"} and r["after"] is None
    assert r["m"][0] == "fire" and "fire" in r["m"] and r["none"] == 0 and r["limit"] == 3 and r["thumbs"] == ["👍"]
    assert r["closed"] == {"at": 3, "emoji": "🔥"} and r["notACode"] is None and r["t"] is None
    assert r["size"] >= 150


@needs_node
def test_the_composer_offers_emoji_after_a_colon_and_two_letters_and_enter_inserts_the_character():
    r = run(COMPOSER + """
globalThis.P = { setTimeout: () => () => {}, prefs: { get: (k, d) => d, set() {} } }
const room = { id: 'r1', name: 'club', members: [] }
const posts = []
const box = mount(Composer, { store: {}, room, onSubmit: t => posts.push(t) })
const menu = () => find(box.tree, n => n.type === SuggestMenu)
area(box).props.onChange(ev('hey :f')); await settle()
const shortOne = !!menu()
area(box).props.onChange(ev('hey :fir')); await settle()
const opts = menu().props.options.map(o => o.name)
const label = menu().props.label, expanded = area(box).props['aria-expanded']
area(box).props.onKeyDown(key('Enter')); await settle()
const after = area(box).props.value
const closedMenu = !menu()
area(box).props.onChange(ev('then :tada:')); await settle()               // typed out in full: converted at once
const typed = area(box).props.value
area(box).props.onChange(ev('x :smi')); await settle()
area(box).props.onKeyDown(key('Escape')); await settle()                   // Escape dismisses; the text stays
const dismissed = [!menu(), area(box).props.value]
area(box).props.onChange(ev('at 10:30')); await settle()
const time = !menu()
area(box).props.onChange(ev('go :bug')); await settle()
area(box).props.onKeyDown(key('ArrowDown')); area(box).props.onKeyDown(key('ArrowUp')); area(box).props.onKeyDown(key('Tab')); await settle()
const tabbed = area(box).props.value
const dmBox = mount(Composer, { store: {}, room: { id: 'dm-x', name: 'Sam', members: [] }, dm: { onSend() {}, placeholder: 'p', max: 2000 } })
area(dmBox).props.onChange(ev('hi :par')); await settle()
out({ shortOne, opts, label, expanded, after, closedMenu, typed, dismissed, time, tabbed, dm: !!find(dmBox.tree, n => n.type === SuggestMenu) })
""")
    assert r["shortOne"] is False                                     # one letter is not enough
    assert r["opts"][0] == ":fire:" and r["label"] == "Emoji" and r["expanded"] is True
    assert r["after"] == "hey 🔥 " and r["closedMenu"] is True
    assert r["typed"] == "then 🎉" and r["dismissed"] == [True, "x :smi"] and r["time"] is True
    assert r["tabbed"] == "go 🐛 "
    assert r["dm"] is True                                            # also in private messages


def test_the_mention_menu_and_the_emoji_menu_are_one_component():
    comp = fn(ROOM, "Composer")
    assert comp.count("jsx(SuggestMenu,") == 1 and "h-ac-opt" in fn(ROOM, "SuggestMenu") and "h-ac-opt" not in comp
    assert "role: 'combobox'" in comp and "'aria-activedescendant'" in comp


# ---- private conversations ----------------------------------------------------------------------------------------

@needs_node
def test_a_private_conversation_loads_earlier_messages_by_cursor_and_keeps_what_you_sent_faint():
    js = dm_js("""
const pk = 'a'.repeat(64)
globalThis.window = { }
const m = (id, ts, mine) => ({ id, ts, t: 'msg', pk, mine: !!mine, name: 'Sam', text: id })
const asked = []
globalThis.P = { toast() {}, setTimeout: f => { f(); return () => {} }, prefs: { get: (k, d) => d, set() {} }, listen: () => () => {},
  rest: async path => { asked.push(path)
    if (path.includes('before=')) return { messages: [m('old1', 1), m('old2', 2)], earlier: false }
    return { pk, name: 'Sam', impostor: false, friend: true, rel: 'friend', earlier: true, messages: [m('m1', 10), m('m2', 11)] } } }
const store = { dm: () => pk, setDm() {}, showing: () => () => {}, isShowing: () => true, post: async (path, body) => { asked.push(path); return { id: 'srv' } } }
const root = mount(DmView, { store, snap: { me: { pk: 'me', name: 'Justin' }, dms: { rev: 1 } }, pk })
await settle()
const ids = () => find(root.tree, n => n.props && n.props.role === 'log').props.children.flat().filter(c => c && c.type === DmItem && c.props.it.kind === 'msg').map(c => c.props.it.m.id)
const btn = () => find(root.tree, n => n.type === EarlierButton)
const before = ids()
const el = { scrollHeight: 500, scrollTop: 0, clientHeight: 300, querySelector: () => null, getBoundingClientRect: () => ({ top: 0 }) }
find(root.tree, n => n.props && n.props.className === 'h-scroll').props.ref.current = el
btn().props.onClick(); await settle()
const after = ids()
const comp = find(root.tree, n => n.type === Composer)
comp.props.dm.onSend('hello'); await settle()
out({ before, after, asked, hasButton: !!btn(), sentShown: ids().length })
""")
    r = run(js)
    assert r["before"] == ["m1", "m2"] and r["after"] == ["old1", "old2", "m1", "m2"] and r["hasButton"] is False
    assert r["asked"][1] == "/dm?pk=" + "a" * 64 + "&read=0&before=m1"
    assert "/dm/send" in r["asked"] and r["sentShown"] >= 4


def test_the_private_view_shares_the_scroll_and_day_line_pieces_with_rooms():
    dmv = fn(DM, "DmView")
    for piece in ("useEarlier(", "useScrollKeeper(", "outboxSend(", "EarlierButton", "'/dm/retry'", "'/dm/discard'"):
        assert piece in dmv, piece
    assert "DayLine" in fn(DM, "DmItem") and "groupItems(msgs, 0)" in dmv
