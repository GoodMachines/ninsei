"""The private-message screens, run under node with the shared hooks harness: the sidebar section (friends, then
Requests), a conversation (load, send, the not-friends banner), the friend requests list, the alerts and the card's
Add friend / Request sent / Message button."""
import json
import re

import pytest

from test_audit_ui import CARD, CORE, ROOM, STYLE, fn, needs_node, run, src

DM = src("57_dm.js")
APP = src("80_app.js")

# the hooks the harness lacks, and the pieces DmView draws that these tests don't need to render
EXTRA = """
const useLayoutEffect = useEffect
const useMemo = f => f()
const Fragment2 = Fragment
function Initial() {}; function PersonMark() {}; function typingPing() {}; function Notice() {}; function Modal() {}; function Composer() {}; function Message() {}
function NotVerified() {}; function groupItems(msgs) { return msgs.map(m => ({ kind: 'msg', key: m.id, m, first: true })) }
function useEnter() { return null }
function EmptyState() {}
function nav() { return { set(v) { globalThis.NAVSET = v } } }
const errText = e => String(e && e.message || e)
const fmtAgo = () = > 'now'
"""
EXTRA = EXTRA.replace("() = >", "() =>")


# what DmView takes from core and the room file: older messages, scroll memory and the faint just-sent messages
DM_HOOKS = "".join(fn(ROOM, n) for n in ("useEarlier", "useScrollKeeper", "EarlierButton")) + "".join(
    fn(CORE, n) for n in ("mergeOlder", "earlierState", "outboxSet", "useOutbox", "outboxSend", "outboxSweep", "outboxItem")) + """
const EARLIER = new Map(), SCROLLED = new Map(), OUTBOX = new Map(), OUTBOX_FNS = new Set(), EARLIER_CAP = 1500
let OUTBOX_N = 0
const NO_MSGS = []
function DayLine() {}
"""


def dm_js(body: str) -> str:
    return EXTRA + DM_HOOKS + fn(CORE, "cleanSnippet") + fn(CORE, "mentionAlerts") + fn(DM, "DmRail") + fn(DM, "useDmThread") + fn(DM, "DmView") \
        + fn(DM, "DmItem") + fn(DM, "DmRequests") + fn(CARD, "FriendAction") + "const DM_REQUESTS = 'requests'\n" + body


THREADS = [{"pk": "a" * 64, "name": "Sam", "impostor": False, "friend": True, "unread": 2, "ts": 5},
           {"pk": "b" * 64, "name": "Olu", "impostor": False, "friend": False, "unread": 0, "ts": 6}]
PENDING = [{"pk": "c" * 64, "name": "npub1xyz…", "impostor": False, "ts": 7},
           {"pk": "d" * 64, "name": "npub1fake…", "impostor": True, "ts": 8}]


@needs_node
def test_the_sidebar_lists_friends_with_unread_dots_and_one_requests_row():
    js = dm_js("""
const store = { dm: () => 'a'.repeat(64), setDm: pk => { globalThis.SET = pk } }
const snap = { dms: { threads: %s, unread: 2, requests: 2, pending: %s, rev: 1 } }
let went = null
const tree = DmRail({ store, snap, view: 'dm', go: v => { went = v } })
const rows = []
;(function walk(n) { if (!n || typeof n !== 'object') return; if (Array.isArray(n)) return n.forEach(walk)
  if (n.props && n.props.className === 'h-navrow') rows.push(n); (n.props && [].concat(n.props.children || [])).forEach(walk) })(tree)
const labels = rows.map(r => text(r).trim())
const dot = find(rows[0], n => n.props && n.props.className === 'h-dot')
rows[0].props.onClick()
const afterRow = [globalThis.SET, went]
rows[2].props.onClick()
const empty = text(DmRail({ store, snap: { dms: { threads: [], requests: 0, pending: [] } }, view: 'lobby', go() {} }))
out({ labels, on: rows.map(r => r.props['data-on']), dot: dot && dot.props['aria-label'], afterRow, afterReq: [globalThis.SET, went],
      req: find(rows[2], n => n.props && n.props.className === 'h-mentions').props['aria-label'], empty })
""" % (json.dumps(THREADS), json.dumps(PENDING)))
    r = run(js)
    assert r["labels"] == ["Sam", "Olunot friends", "Requests2"] and r["on"] == [True, False, False]   # a former friend is marked
    assert r["dot"] == "2 unread private messages" and r["req"] == "2 friend requests"
    assert r["afterRow"] == ["a" * 64, "dm"] and r["afterReq"] == ["requests", "dm"]
    assert "Add friend" in r["empty"]


@needs_node
def test_a_conversation_loads_sends_through_the_dm_route_and_has_no_games_or_mentions():
    js = dm_js("""
const calls = []
const pk = 'a'.repeat(64)
globalThis.window = { }
globalThis.P = { rest: async (path, o) => { calls.push([path, o && o.body]); return { pk, name: 'Sam', impostor: false, friend: true, rel: 'friend', messages: [{ id: 'm1', ts: 1, t: 'msg', pk, mine: false, name: 'Sam', text: 'hi' }] } },
  listen: () => () => {} }
const store = { dm: () => pk, setDm() {}, showing: () => () => {}, isShowing: () => true, post: async (path, body) => { calls.push([path, body]); return {} } }
const root = mount(DmView, { store, snap: { dms: { rev: 1 } }, pk })
await settle()
const comp = find(root.tree, n => n.type === Composer)
await comp.props.dm.onSend('hello Sam')
out({ calls, hasComposer: !!comp, placeholder: comp.props.dm.placeholder, max: comp.props.dm.max, room: comp.props.room,
      msgs: root.tree && !!find(root.tree, n => n.type === DmItem) })
""")
    r = run(js)
    assert r["calls"][0] == ["/dm?pk=" + "a" * 64, None]                          # loaded and marked read (it is on screen)
    assert ["/dm/send", {"pk": "a" * 64, "text": "hello Sam"}] in r["calls"]
    assert r["placeholder"] == "Message Sam (private)" and r["max"] == 2000 and r["room"]["members"] == []
    assert r["msgs"] is True


@needs_node
def test_a_conversation_not_on_screen_loads_without_marking_it_read():
    js = dm_js("""
const calls = []
const pk = 'b'.repeat(64)
globalThis.window = { }
globalThis.P = { rest: async path => { calls.push(path); return { pk, name: 'Olu', impostor: false, friend: true, rel: 'friend', messages: [] } }, listen: () => () => {} }
const store = { dm: () => pk, setDm(v) { calls.push('setDm:' + v) }, showing: () => () => {}, isShowing: () => false, post: async () => ({}) }
const root = mount(DmView, { store, snap: { dms: { rev: 1 } }, pk })
await settle()
out({ calls })
""")
    assert run(js)["calls"][0] == "/dm?pk=" + "b" * 64 + "&read=0"


def conversation(rel, friend=False):
    return dm_js("""
const calls = []
const pk = 'b'.repeat(64)
globalThis.window = { }
globalThis.P = { rest: async path => { calls.push(path); return { pk, name: 'Olu', impostor: false, friend: %s, rel: '%s', messages: [{ id: 'm1', ts: 1, t: 'msg', pk, mine: false, name: 'Olu', text: 'before' }] } }, listen: () => () => {} }
const store = { dm: () => pk, setDm(v) { calls.push('setDm:' + v) }, showing: () => () => {}, isShowing: () => true,
  post: async (path, body, ok) => { calls.push([path, body]); return {} } }
const root = mount(DmView, { store, snap: { dms: { rev: 1 } }, pk })
await settle()
const composer = find(root.tree, n => n.type === Composer)
""" % ("true" if friend else "false", rel))


@needs_node
def test_a_conversation_with_someone_who_is_not_a_friend_has_no_composer_and_offers_the_next_step():
    r = run(conversation("") + """
const add = button(root.tree, 'Add friend')
await add.props.onClick()
const hide = button(root.tree, 'Hide')
await hide.props.onClick()
out({ calls, composer: !!composer, add: !!add, accept: !!button(root.tree, 'Accept'), msgs: !!find(root.tree, n => n.type === DmItem), navset: globalThis.NAVSET })
""")
    assert r["composer"] is False and r["add"] is True and r["accept"] is False and r["msgs"] is True       # old messages stay readable
    assert ["/friend/request", {"pk": "b" * 64}] in r["calls"]
    assert ["/people/hide", {"pk": "b" * 64, "name": "Olu"}] in r["calls"] and r["navset"] == "lobby"
    sent = run(conversation("sent") + "out({ composer: !!composer, add: !!button(root.tree, 'Add friend'), cancel: !!button(root.tree, 'Cancel request'), t: text(root.tree) })")
    assert sent["composer"] is False and sent["add"] is False and sent["cancel"] is True and "You asked Olu to be friends" in sent["t"]
    asked = run(conversation("request") + """
await button(root.tree, 'Accept').props.onClick()
await button(root.tree, 'Ignore').props.onClick()
out({ calls, composer: !!composer, navset: globalThis.NAVSET })
""")
    assert ["/friend/accept", {"pk": "b" * 64}] in asked["calls"] and ["/friend/ignore", {"pk": "b" * 64}] in asked["calls"]
    assert asked["composer"] is False and asked["navset"] == "lobby"


@needs_node
def test_a_friend_conversation_has_the_composer_and_remove_friend_asks_first():
    r = run(conversation("friend", True) + """
const rm = find(root.tree, n => n.type === K.Button && n.props['aria-label'] === 'Remove Olu from your friends')
const beforeAsk = calls.length
const modal = find(root.tree, n => n.type === Modal && n.props.title === 'Remove Olu from your friends?')
const confirm = modal.props.footer.find(f => text(f).includes('Remove friend'))
await confirm.props.onClick()
out({ composer: !!composer, rm: !!rm, beforeAsk, posted: calls.filter(c => Array.isArray(c)), banner: !!button(root.tree, 'Add friend') })
""")
    assert r["composer"] is True and r["rm"] is True and r["banner"] is False
    assert r["posted"] == [["/friend/remove", {"pk": "b" * 64}]]                    # nothing is sent until it is confirmed


@needs_node
def test_requests_list_has_only_who_is_asking_and_accept_ignore_hide():
    js = dm_js("""
const posts = []
globalThis.P = {}
const store = { post: async (p, b) => { posts.push([p, b]); return {} } }
const tree = DmRequests({ store, snap: { dms: { threads: [], pending: %s } } })
const all = text(tree)
const by = label => find(tree, n => n.type === K.Button && n.props['aria-label'] === label)
await by('Accept npub1xyz…').props.onClick()
await by('Ignore npub1xyz…').props.onClick()
await by('Hide npub1xyz…').props.onClick()
const none = text(DmRequests({ store, snap: { dms: { pending: [] } } }))
out({ all, posts, none })
""" % json.dumps(PENDING + [{"pk": "e" * 64, "name": "x", "impostor": False, "ts": 1, "text": "SECRET TEXT", "last_unread": {"text": "SECRET TEXT"}}]))
    r = run(js)
    assert "SECRET TEXT" not in r["all"] and "npub1xyz…" in r["all"] and "not verified" in r["all"] and "no message" in r["all"]
    assert r["posts"] == [["/friend/accept", {"pk": "c" * 64}], ["/friend/ignore", {"pk": "c" * 64}], ["/people/hide", {"pk": "c" * 64, "name": "npub1xyz…"}]]
    assert "No requests right now." in r["none"]


@needs_node
def test_the_card_shows_add_friend_request_sent_accept_or_message_by_friend_state():
    js = dm_js("""
const posts = []
const store = { post: async (p, b, ok) => { posts.push([p, b, ok]); return {} } }
const pk = 'f'.repeat(64)
const seen = {}
let msg = 0
for (const rel of ['', 'sent', 'request', 'friend']) {
  const el = FriendAction({ rel, name: 'Maya', pk, store, onMessage: () => { msg++ } })
  seen[rel || 'none'] = { label: text(el), disabled: !!(el && el.props.disabled) }
  if (rel !== 'sent' && el.props.onClick) await el.props.onClick()
}
const noStore = FriendAction({ rel: '', name: 'Maya', pk, store: null, onMessage: null })
const noOpen = FriendAction({ rel: 'friend', name: 'Maya', pk, store, onMessage: null })
out({ seen, posts, msg, noStore, noOpen })
""")
    r = run(js)
    assert {k: v["label"] for k, v in r["seen"].items()} == {"none": "Add friend", "sent": "Request sent", "request": "Accept Maya", "friend": "Message Maya"}
    assert r["seen"]["sent"]["disabled"] is True and r["seen"]["none"]["disabled"] is False
    assert r["posts"] == [["/friend/request", {"pk": "f" * 64}, "Friend request sent to Maya."],
                          ["/friend/accept", {"pk": "f" * 64}, "Maya is now your friend."]] and r["msg"] == 1
    assert r["noStore"] is None and r["noOpen"] is None                            # nothing to press: no button


ALERT = """
const toasts = [], os = []
globalThis.P = { toast: (k, m) => toasts.push(m), osNotify: o => os.push(o) }
function nav() { return { set(v) { globalThis.NAVSET = v } } }
let listener = null, showing = false
const store = { subscribe: fn => { listener = fn; return () => { listener = null } }, isShowing: id => showing === id, setRoom() {}, setDm(pk) { globalThis.DMPK = pk } }
const off = mentionAlerts(store)
const t = (pk, name, unread, extra) => Object.assign({ pk, name, impostor: false, friend: true, unread, ts: 1, last_unread: unread ? { id: 'id' + pk + unread, text: 'hi there', ts: 1 } : undefined }, extra || {})
const req = (pk, name, extra) => Object.assign({ pk, name, impostor: false, ts: 1 }, extra || {})
const snap = (threads, pending) => ({ snap: { rooms: [], dms: { threads, pending: pending || [] } } })
"""


@needs_node
def test_a_private_message_alert_fires_for_a_rise_you_are_not_looking_at_and_never_on_first_load():
    js = fn(CORE, "cleanSnippet") + fn(CORE, "mentionAlerts") + ALERT + """
listener(snap([t('s1', 'Sam', 1)]))                     // first load: baseline only
const first = toasts.length
listener(snap([t('s1', 'Sam', 1)]))                     // no change
listener(snap([t('s1', 'Sam', 2)]))                     // a rise
const afterRise = toasts.slice()
listener(snap([t('s1', 'Sam', 2)]))                     // the same one is not announced twice
showing = 'dm:s1'
listener(snap([t('s1', 'Sam', 3)]))                     // looking at it: quiet
showing = false
listener(snap([t('s1', 'Sam', 3), t('s2', 'Mallory', 1, { impostor: true, name: 'npub1fake…' })]))   // a new conversation, a lookalike
os.forEach(o => o.onActivate())
off()
out({ first, afterRise, toasts, os: os.map(o => [o.title, o.body]), dmpk: globalThis.DMPK, navset: globalThis.NAVSET })
"""
    r = run(js)
    assert r["first"] == 0
    assert r["afterRise"] == ['Sam sent you a private message: "hi there"']
    assert r["toasts"][1].startswith("Someone not verified (npub1fake…) sent you a private message")
    assert "Mallory" not in " ".join(r["toasts"])                                        # a lookalike never shows as the real name
    assert len(r["toasts"]) == 2 and r["navset"] == "dm" and r["dmpk"] == "s2"


@needs_node
def test_a_friend_request_alert_is_by_name_once_and_never_on_first_load_and_a_lookalike_is_not_the_real_name():
    js = fn(CORE, "cleanSnippet") + fn(CORE, "mentionAlerts") + ALERT + """
listener(snap([], [req('r0', 'Ola')]))                  // first load: baseline only
const first = toasts.length
listener(snap([], [req('r0', 'Ola'), req('r1', 'Maya')]))
listener(snap([], [req('r0', 'Ola'), req('r1', 'Maya')]))                       // the same request is not announced twice
listener(snap([], [req('r0', 'Ola'), req('r1', 'Maya'), req('r2', 'npub1fake…', { impostor: true, claimed: 'Maya R' })]))
listener(snap([], [req('r0', 'Ola'), req('r2', 'npub1fake…', { impostor: true })]))     // one answered, then back again: no repeat
listener(snap([], [req('r0', 'Ola'), req('r1', 'Maya'), req('r2', 'npub1fake…', { impostor: true })]))
os.forEach(o => o.onActivate())
out({ first, toasts, os: os.map(o => [o.title, o.body]), dmpk: globalThis.DMPK, navset: globalThis.NAVSET })
"""
    r = run(js)
    assert r["first"] == 0 and r["toasts"] == ["Maya wants to be friends", "Someone not verified (npub1fake…) wants to be friends"]
    assert "Maya R" not in " ".join(r["toasts"]) and r["navset"] == "dm" and r["dmpk"] == "requests"


def test_the_friend_button_is_on_other_peoples_cards_and_a_friend_goes_to_their_conversation():
    assert "message: p.you ? null" in CARD and "jsx(FriendAction" in CARD and "onMessage: props.openDm ? messageThem : null" in CARD
    assert "openDm" in APP and "store.setDm(pk); go('dm')" in APP
    assert "DmRail" in APP and "DmView" in APP and "DmAbout" in APP
    # nothing of the room's message actions leaks into a conversation: Message is drawn without a store
    assert "jsx(Message, { m: props.it.m, first: props.it.first, book: {}, onRetry: props.onRetry, onDiscard: props.onDiscard })" in DM


def test_the_composer_in_dm_mode_has_no_games_no_mentions_and_the_room_composer_is_unchanged():
    comp = fn(ROOM, "Composer")
    assert "const dm = props.dm" in comp and "!dm && jsxs('div', { style: { position: 'relative' }, children: [" in comp
    assert "cands = useMemo(() => dm ? [] : mentionCandidates(room)" in comp and "if (dm) dm.onSend(t)" in comp
    assert "props.onSubmit(t, reply)" in comp and "store.post('/post', reply ? { room: room.id, text: t, reply: reply.id } : { room: room.id, text: t })" in comp
