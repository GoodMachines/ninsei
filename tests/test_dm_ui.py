"""The private-message screens, run under node with the shared hooks harness: the sidebar section, a
conversation (load, send, request banner), the Requests list, the alerts and the card's Message button."""
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
function nav() { return { set(v) { globalThis.NAVSET = v } } }
const errText = e => String(e && e.message || e)
const fmtAgo = () = > 'now'
"""
EXTRA = EXTRA.replace("() = >", "() =>")


def dm_js(body: str) -> str:
    return EXTRA + fn(CORE, "cleanSnippet") + fn(CORE, "mentionAlerts") + fn(DM, "DmRail") + fn(DM, "useDmThread") + fn(DM, "DmView") \
        + fn(DM, "DmItem") + fn(DM, "DmRequests") + "const DM_REQUESTS = 'requests'\n" + body


THREADS = [{"pk": "a" * 64, "name": "Sam", "impostor": False, "request": False, "unread": 2, "ts": 5},
           {"pk": "b" * 64, "name": "npub1xyz…", "impostor": False, "request": True, "unread": 1, "ts": 6}]


@needs_node
def test_the_sidebar_lists_conversations_with_unread_dots_and_one_requests_row():
    js = dm_js("""
const store = { dm: () => 'a'.repeat(64), setDm: pk => { globalThis.SET = pk } }
const snap = { dms: { threads: %s, unread: 2, requests: 1, rev: 1 } }
let went = null
const tree = DmRail({ store, snap, view: 'dm', go: v => { went = v } })
const rows = []
;(function walk(n) { if (!n || typeof n !== 'object') return; if (Array.isArray(n)) return n.forEach(walk)
  if (n.props && n.props.className === 'h-navrow') rows.push(n); (n.props && [].concat(n.props.children || [])).forEach(walk) })(tree)
const labels = rows.map(r => text(r).trim())
const dot = find(rows[0], n => n.props && n.props.className === 'h-dot')
rows[0].props.onClick()
const afterRow = [globalThis.SET, went]
rows[1].props.onClick()
out({ labels, on: rows.map(r => r.props['data-on']), dot: dot && dot.props['aria-label'], afterRow, afterReq: [globalThis.SET, went],
      req: find(rows[1], n => n.props && n.props.className === 'h-mentions').props['aria-label'] })
""" % __import__("json").dumps(THREADS))
    r = run(js)
    assert r["labels"] == ["Sam", "Requests1"] and r["on"] == [True, False]      # the request is not in the list of conversations
    assert r["dot"] == "2 unread private messages" and r["req"] == "1 message request"
    assert r["afterRow"] == ["a" * 64, "dm"] and r["afterReq"] == ["requests", "dm"]


@needs_node
def test_a_conversation_loads_sends_through_the_dm_route_and_has_no_games_or_mentions():
    js = dm_js("""
const calls = []
const pk = 'a'.repeat(64)
globalThis.window = { }
globalThis.P = { rest: async (path, o) => { calls.push([path, o && o.body]); return { pk, name: 'Sam', impostor: false, request: false, messages: [{ id: 'm1', ts: 1, t: 'msg', pk, mine: false, name: 'Sam', text: 'hi' }] } },
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
def test_a_conversation_not_on_screen_loads_without_marking_it_read_and_a_request_shows_accept_and_hide():
    js = dm_js("""
const calls = []
const pk = 'b'.repeat(64)
globalThis.window = { }
globalThis.P = { rest: async path => { calls.push(path); return { pk, name: 'npub1xyz…', impostor: false, request: true, messages: [] } }, listen: () => () => {} }
const store = { dm: () => pk, setDm(v) { calls.push('setDm:' + v) }, showing: () => () => {}, isShowing: () => false,
  post: async (path, body) => { calls.push([path, body]); return {} } }
const root = mount(DmView, { store, snap: { dms: { rev: 1 } }, pk })
await settle()
const accept = button(root.tree, 'Accept')
const hide = button(root.tree, 'Hide')
await accept.props.onClick()
await hide.props.onClick()
out({ calls, banner: !!accept && !!hide, navset: globalThis.NAVSET })
""")
    r = run(js)
    assert r["calls"][0] == "/dm?pk=" + "b" * 64 + "&read=0"
    assert ["/dm/accept", {"pk": "b" * 64}] in r["calls"]
    assert ["/people/hide", {"pk": "b" * 64, "name": "npub1xyz…"}] in r["calls"]
    assert "setDm:" in r["calls"] and r["navset"] == "lobby"                      # hiding closes the conversation


@needs_node
def test_requests_list_never_shows_what_a_stranger_wrote():
    js = dm_js("""
const posts = []
globalThis.P = {}
const store = { setDm: pk => posts.push(['open', pk]), post: async (p, b) => { posts.push([p, b]); return {} } }
const tree = DmRequests({ store, snap: { dms: { threads: %s } } })
const all = text(tree)
await button(tree, 'Accept').props.onClick()
button(tree, 'Open').props.onClick()
out({ all, posts })
""" % __import__("json").dumps(THREADS + [{"pk": "c" * 64, "name": "x", "request": True, "unread": 3, "ts": 1, "last_unread": {"id": "z", "text": "SECRET TEXT", "ts": 1}}]))
    r = run(js)
    assert "SECRET TEXT" not in r["all"] and "npub1xyz…" in r["all"]
    assert ["/dm/accept", {"pk": "b" * 64}] in r["posts"] and ["open", "b" * 64] in r["posts"]


ALERT = """
const toasts = [], os = []
globalThis.P = { toast: (k, m) => toasts.push(m), osNotify: o => os.push(o) }
function nav() { return { set(v) { globalThis.NAVSET = v } } }
let listener = null, showing = false
const store = { subscribe: fn => { listener = fn; return () => { listener = null } }, isShowing: id => showing === id, setRoom() {}, setDm(pk) { globalThis.DMPK = pk } }
const off = mentionAlerts(store)
const t = (pk, name, unread, extra) => Object.assign({ pk, name, impostor: false, request: false, unread, ts: 1, last_unread: unread ? { id: 'id' + pk + unread, text: 'hi there', ts: 1 } : undefined }, extra || {})
const snap = threads => ({ snap: { rooms: [], dms: { threads } } })
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
listener(snap([t('s1', 'Sam', 3), t('s2', 'x', 1, { name: 'npub1fake…', impostor: true }), t('s3', 'npub1new…', 1, { request: true, last_unread: { id: 'r1', text: '', ts: 1 } })]))
listener(snap([t('s1', 'Sam', 3), t('s3', 'npub1new…', 2, { request: true, last_unread: { id: 'r2', text: '', ts: 1 } })]))   // a request again: not again
os.forEach(o => o.onActivate())
off()
out({ first, afterRise, toasts, os: os.map(o => [o.title, o.body]), dmpk: globalThis.DMPK, navset: globalThis.NAVSET })
"""
    r = run(js)
    assert r["first"] == 0
    assert r["afterRise"] == ['Sam sent you a private message: "hi there"']
    assert r["toasts"][1].startswith("Someone not verified (npub1fake…) sent you a private message")
    assert "Mallory" not in " ".join(r["toasts"])                                        # a lookalike never shows as the real name
    assert r["toasts"][2] == "npub1new… wants to message you" and len(r["toasts"]) == 3  # a request: name only, once
    assert r["os"][2][1] == "Open Ninsei to see it." and r["navset"] == "dm" and r["dmpk"] == "s3"


def test_a_message_button_is_on_other_peoples_cards_and_goes_to_their_conversation():
    assert "message: p.you ? null" in CARD and "act.message && props.openDm" in CARD
    assert "openDm" in APP and "store.setDm(pk); go('dm')" in APP
    assert "DmRail" in APP and "DmView" in APP and "DmAbout" in APP
    # nothing of the room's message actions leaks into a conversation: Message is drawn without a store
    assert "jsx(Message, { m: props.it.m, first: props.it.first, book: {} })" in DM


def test_the_composer_in_dm_mode_has_no_games_no_mentions_and_the_room_composer_is_unchanged():
    comp = fn(ROOM, "Composer")
    assert "const dm = props.dm" in comp and "!dm && jsxs('div', { style: { position: 'relative' }, children: [" in comp
    assert "cands = useMemo(() => dm ? [] : mentionCandidates(room)" in comp and "if (dm) await dm.onSend(t)" in comp
    assert "store.post('/post', body)" in comp
