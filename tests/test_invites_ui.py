"""Invites and room links, the page side, run under node with the shared hooks harness: hosts read the way the engine reads
them, the Join preview and "Add and look again", the Invite dialog, Copy invite link, the sidebar's Invites row and list,
invite lines in a conversation, the toasts (an invite, someone joined your room) and Cmd+K's Rejoin."""
import json
import re

from ninsei_engine import codes
from test_audit_ui import APP, CARD, CORE, ROOM, fn, needs_node, run, src
from test_dm_ui import EXTRA, dm_js

def afn(text, name):
    """`fn` for an async function (it returns the source from the word `function`)."""
    return "async " + fn(text, name)


TOOLS = src("52_tools.js")
DM = src("57_dm.js")
ROOM_ID = "203f22bcfd1b4b2f"

HOSTS_JS = re.search(r"const PRIVATE_SUFFIXES = new Set\(\[.*?\]\)\n", CORE, re.S).group(0) \
    + "".join(fn(CORE, n) for n in ("trimCode", "cleanHost", "cleanHosts", "parseRoomLink", "roomLinkAt", "relayHost", "fmtAgo", "previewActivity", "cleanSnippet"))


# ---- hosts: the page and the engine read them the same way -------------------------------------------------------------

GOOD = ["nos.lol", "relay.damus.io", "a.b.c.example.com", "nos.lol:443", "NOS.LOL", "xn--bcher-kva.example.dev", "relay-1.example.org:8080", "x.io"]
BAD = ["", "localhost", "foo.localhost", "nos", "127.0.0.1", "10.0.0.1", "192.168.1.1:7777", "1.2.3.4", "0x7f.0x1", "127.1", "2130706433", "[::1]",
       "::1", "[2001:db8::1]:443", "nos.lol/path", "user@nos.lol", "wss://nos.lol", "ws://nos.lol", "nos.lol:", "nos.lol:0", "nos.lol:99999",
       "nos.lol:12:3", "nos..lol", ".nos.lol", "nos.lol.", "-a.nos.lol", "a-.nos.lol", "nos .lol", "nos.lol\n", "\x1fnos.lol", "nos.lol\x85", "nos\x00.lol", "nos.lol\ufeff", "printer.local", "nas.lan",
       "box.internal", "a" * 64 + ".lol", ("a." * 130) + "lol", "nos.l0l", "nos.123", "nös.lol"]


@needs_node
def test_the_page_accepts_and_refuses_the_same_hosts_as_the_engine():
    r = run(HOSTS_JS + "const hosts = %s\nout(hosts.map(h => cleanHost(h)))" % json.dumps(GOOD + BAD))
    assert r == [codes.clean_host(h) for h in GOOD + BAD]
    assert [x for x in r[:len(GOOD)]] == [h.lower() for h in GOOD] and all(x is None for x in r[len(GOOD):])


@needs_node
def test_the_page_reads_a_code_with_hosts_like_parse_room_link():
    ev = "b" * 64
    cases = [f"ninsei:{ROOM_ID}", f"ninsei:{ROOM_ID}@nos.lol,relay.damus.io", f"ninsei:{ROOM_ID}@nos.lol#{ev}", f"  NINSEI:{ROOM_ID.upper()}@NOS.LOL:443#{ev.upper()}  ",
             f"ninsei:{ROOM_ID}@nos.lol,127.0.0.1,localhost,[::1],bad host,relay.damus.io", f"ninsei:{ROOM_ID}@127.0.0.1,localhost,ws://nos.lol",
             f"ninsei:{ROOM_ID}@a.io,b.io,c.io,d.io,e.io", ROOM_ID, "@nos.lol", "hello", f"ninsei:{ROOM_ID}#nothex", f"ninsei:{ROOM_ID}@" + ("a." * 5000) + "io",
             # what each side trims: whitespace and U+FEFF, and nothing else (str.strip() and .trim() each differ from that)
             "\ufeff" + f"ninsei:{ROOM_ID}@nos.lol", f"\x1c\x1d ninsei:{ROOM_ID}@nos.lol \x1e\x1f", f"\x85ninsei:{ROOM_ID}@nos.lol", f"ninsei:{ROOM_ID}@nos.lol\x85",
             f"\xa0\u2003ninsei:{ROOM_ID}@nos.lol\u3000\ufeff", f"ninsei:{ROOM_ID}@nos.lol,\ufeffrelay.damus.io", f"ninsei:{ROOM_ID}@\x1cnos.lol,\x1frelay.damus.io",
             f"ninsei:{ROOM_ID}@nos.lol#{ev}\ufeff", f"ninsei:{ROOM_ID}@nos.lol#\x1f{ev}", f"ninsei:{ROOM_ID}\x1f@nos.lol", f"ninsei:{ROOM_ID}\ufeff@nos.lol",
             f"\u200bninsei:{ROOM_ID}@nos.lol", f"ninsei:{ROOM_ID}@\u180enos.lol", f"ninsei:{ROOM_ID}@nos.lol\u0000", f"{ROOM_ID}\n\ufeff"]
    r = run(HOSTS_JS + "const cases = %s\nout(cases.map(c => parseRoomLink(c)).concat([parseRoomLink(null), parseRoomLink('x'.repeat(5000))]))" % json.dumps(cases))
    from ninsei_engine.engine import parse_room_link
    want = [dict(zip(("room", "event", "hosts"), (a, b, [u[6:] for u in c]))) for a, b, c in (parse_room_link(x) for x in cases + [None, "x" * 5000])]
    assert r == want


@needs_node
def test_a_link_in_a_message_keeps_its_hosts_and_a_closing_full_stop_is_not_part_of_it():
    rich = "".join(fn(CORE, n) for n in ("squashName", "mentionNames", "mentionParts", "linkAt", "emphasisCloses", "richInline", "richParts")) + HOSTS_JS + "const RICH_MAX_LINKS = 20\n"
    r = run(rich + """
const room = '203f22bcfd1b4b2f', ev = 'a'.repeat(64)
const rooms = t => richParts(t, []).flatMap(b => b.tokens || []).filter(x => x.t === 'room').map(x => [x.text, x.room, x.event])
out({ hosts: rooms('join ninsei:' + room + '@nos.lol,relay.damus.io please'), stop: rooms('here ninsei:' + room + '@nos.lol.'), withEv: rooms('ninsei:' + room + '@nos.lol#' + ev + '.'),
      plain: rooms('see ninsei:' + room + '. ok'), bare: rooms('ninsei:' + room) })
""")
    room, ev = ROOM_ID, "a" * 64
    assert r["hosts"] == [[f"ninsei:{room}@nos.lol,relay.damus.io", room, ""]]
    assert r["stop"] == [[f"ninsei:{room}@nos.lol", room, ""]]                       # the full stop ends the sentence, not the host
    assert r["withEv"] == [[f"ninsei:{room}@nos.lol#{ev}", room, ev]]
    assert r["plain"] == [[f"ninsei:{room}", room, ""]] and r["bare"] == [[f"ninsei:{room}", room, ""]]


# ---- the Join preview -------------------------------------------------------------------------------------------------

JOIN_JS = HOSTS_JS + fn(APP, "JoinDialog") + """
function Modal() {}; function Chips() {}
const wantJump = (...a) => { globalThis.JUMP = a }
const toasts = [], posts = [], calls = []
globalThis.P = { setTimeout: f => { const t = setTimeout(f, 0); return () => clearTimeout(t) }, toast: (k, m) => toasts.push(m),
  rest: async path => { calls.push(path); const a = ANSWERS.shift(); if (a instanceof Error) throw a; return a } }
let ANSWERS = []
const answer = o => Object.assign({ id: '%(room)s', found: true, reached: true, name: 'Dune club', about: 'sand and sound', interests: ['synths', 'demoscene'],
  msgs: 4, talkers: 3, last: Date.now() / 1000 - 720, joined: false, unknown_relays: [] }, o || {})
const store = { post: async (p, b) => { posts.push([p, b]); if (p === '/rooms/join') return { id: '%(room)s', found: true }; if (p === '/relays/add') return { added: ['wss://relay.example.org'], relays: [] }; return {} } }
""" % {"room": ROOM_ID}


@needs_node
def test_the_join_dialog_shows_what_the_room_is_before_the_button_and_the_relays_it_would_add():
    r = run(JOIN_JS + """
const code = 'ninsei:%(room)s@nos.lol,relay.example.org'
ANSWERS = [answer({ unknown_relays: ['wss://relay.example.org'] }), answer()]
const done = []
const root = mount(JoinDialog, { store, initial: code, onClose() {}, onDone: id => done.push(id) })
await settle()
const found = { calls: calls.slice(), text: text(root.tree), chips: find(root.tree, n => n.type === Chips).props.items, button: text(button(root.tree, 'Join')) }
await button(root.tree, 'Add and look again').props.onClick()
await settle()
const after = { calls: calls.slice(), posts: posts.slice(), text: text(root.tree), toasts: toasts.slice() }
await button(root.tree, 'Join').props.onClick()
await settle()
out({ found, after, posts, done, jump: globalThis.JUMP || null })
""" % {"room": ROOM_ID})
    code = f"ninsei:{ROOM_ID}@nos.lol,relay.example.org"
    f = r["found"]
    assert f["calls"] == ["/rooms/preview?code=" + code.replace(":", "%3A").replace("@", "%40").replace(",", "%2C")]
    assert "Dune club" in f["text"] and "sand and sound" in f["text"] and "3 people talked today · last message 12 min ago" in f["text"]
    assert f["chips"] == ["synths", "demoscene"] and f["button"] == "Join"
    assert "Also on: relay.example.org" in f["text"] and "Add and look again" in f["text"] and "Nothing connects to these until you press" in f["text"]
    # the press adds the code's relays (one POST, with the code) and looks again; the "Also on" row is gone
    assert r["after"]["posts"] == [["/relays/add", {"code": code}]] and len(r["after"]["calls"]) == 2
    assert "Also on" not in r["after"]["text"] and r["after"]["toasts"] == ["Added relay.example.org to your relays."]
    assert r["posts"][-1] == ["/rooms/join", {"room": code}] and r["done"] == [ROOM_ID]


@needs_node
def test_the_preview_alone_adds_no_relay_and_joins_nothing():
    r = run(JOIN_JS + """
ANSWERS = [answer({ unknown_relays: ['wss://a.example.org', 'wss://b.example.org:8443'] })]
const root = mount(JoinDialog, { store, initial: 'ninsei:%(room)s@a.example.org,b.example.org:8443', onClose() {}, onDone() {} })
await settle()
out({ posts, text: text(root.tree) })
""" % {"room": ROOM_ID})
    assert r["posts"] == [] and "Also on: a.example.org, b.example.org:8443" in r["text"]


@needs_node
def test_a_room_you_are_in_says_so_and_the_button_reads_open_without_joining_again():
    r = run(JOIN_JS + """
ANSWERS = [answer({ joined: true })]
const done = []
const root = mount(JoinDialog, { store, initial: '%(room)s', onClose() {}, onDone: id => done.push(id) })
await settle()
const label = text(button(root.tree, 'Open'))
await button(root.tree, 'Open').props.onClick()
out({ label, text: text(root.tree), posts, done })
""" % {"room": ROOM_ID})
    assert r["label"] == "Open" and "You are already in this room." in r["text"] and r["posts"] == [] and r["done"] == [ROOM_ID]


@needs_node
def test_nothing_found_says_so_and_no_answer_from_relays_says_that_instead():
    r = run(JOIN_JS + """
ANSWERS = [answer({ found: false, name: 'Room 2030', about: '', interests: [], msgs: 0, talkers: 0, last: 0, unknown_relays: ['wss://relay.example.org'] }),
           answer({ found: false, reached: false })]
const a = mount(JoinDialog, { store, initial: 'ninsei:%(room)s@relay.example.org', onClose() {}, onDone() {} })
await settle()
const none = text(a.tree)
const b = mount(JoinDialog, { store, initial: '%(room)s', onClose() {}, onDone() {} })
await settle()
out({ none, silent: text(b.tree), join: !!button(b.tree, 'Join') })
""" % {"room": ROOM_ID})
    assert "Nothing on your relays for this code." in r["none"] and "Also on: relay.example.org" in r["none"]       # the hosts stay offered
    assert "Couldn’t reach your relays" in r["silent"] and "Nothing on your relays" not in r["silent"] and r["join"]


@needs_node
def test_a_failed_preview_never_blocks_joining_and_a_short_code_asks_nothing():
    r = run(JOIN_JS + """
ANSWERS = [new Error('timeout')]
const root = mount(JoinDialog, { store, initial: 'ninsei:%(room)s', onClose() {}, onDone() {} })
await settle()
const failed = text(root.tree)
await button(root.tree, 'Join').props.onClick()
await settle()
const n = calls.length
const short = mount(JoinDialog, { store, initial: 'ninsei:abc', onClose() {}, onDone() {} })
await settle()
out({ failed, posts, short: calls.length - n, shortText: text(short.tree) })
""" % {"room": ROOM_ID})
    assert "You can still join" in r["failed"] and r["posts"][-1][0] == "/rooms/join" and r["short"] == 0 and "Looking" not in r["shortText"]


@needs_node
def test_a_preview_of_an_old_code_is_never_shown_under_a_new_one():
    r = run(JOIN_JS + """
ANSWERS = [answer({ name: 'First room' }), answer({ name: 'Second room', id: '0123456789abcdef' })]
const root = mount(JoinDialog, { store, initial: '%(room)s', onClose() {}, onDone() {} })
await settle()
find(root.tree, n => n.type === K.Input).props.onChange({ target: { value: 'ninsei:0123456789abcdef' } })
await Promise.resolve(); await Promise.resolve()                       // one render, before the new look is back
const during = text(root.tree)                         // the old answer is not for this code
await settle(); await settle()
out({ during, now: text(root.tree) })
""" % {"room": ROOM_ID})
    assert "First room" not in r["during"] and "Second room" in r["now"]


# ---- Share code, Copy invite link, the Invite dialog ----------------------------------------------------------------

@needs_node
def test_share_code_copies_the_engines_code_with_its_hosts_and_the_link_is_the_web_page():
    r = run(afn(ROOM, "copyRoomCode") + afn(ROOM, "copyInviteLink") + """
const copied = [], toasts = []
globalThis.P = { copy: async t => { copied.push(t); return true }, toast: (k, m) => toasts.push([k, m]) }
const room = { id: '%(room)s', code: 'ninsei:%(room)s@nos.lol,relay.damus.io', invite_link: 'https://goodmachines.ai/ninsei/join#%(room)s@nos.lol,relay.damus.io' }
await copyRoomCode(room); await copyInviteLink(room); await copyRoomCode({ id: '%(room)s' }); await copyInviteLink({ id: 'x' })
out({ copied, toasts })
""" % {"room": ROOM_ID})
    assert r["copied"] == [f"ninsei:{ROOM_ID}@nos.lol,relay.damus.io", f"https://goodmachines.ai/ninsei/join#{ROOM_ID}@nos.lol,relay.damus.io", f"ninsei:{ROOM_ID}"]
    assert len(r["toasts"]) == 3 and all(t[0] == "info" for t in r["toasts"])
    # the link is built from the code the engine makes, so the two can never disagree; and a message link carries the hosts too
    assert "props.roomCode || 'ninsei:' + props.roomId" in ROOM and "roomCode: room.code" in ROOM


@needs_node
def test_an_invites_join_is_titled_by_who_sent_it_and_goes_back_to_join_by_code_once_the_code_changes():
    r = run(JOIN_JS + """
ANSWERS = [answer({}), answer({})]
const root = mount(JoinDialog, { store, initial: '%(room)s', from: { name: 'Sam', room: 'pixel arcade' }, onClose() {}, onDone() {} })
await settle()
const invited = { title: root.tree.props.title, desc: root.tree.props.description }
find(root.tree, n => n.type === K.Input).props.onChange({ target: { value: '%(room)sx' } })
await settle()
const plain = mount(JoinDialog, { store, initial: '%(room)s', onClose() {}, onDone() {} })
await settle()
out({ invited, edited: root.tree.props.title, plain: plain.tree.props.title })
""" % {"room": ROOM_ID})
    assert r["invited"]["title"] == "Sam invited you to pixel arcade" and "Nothing joins until you press Join" in r["invited"]["desc"]
    assert r["edited"] == "Join by code" and r["plain"] == "Join by code"


INVITE_JS = afn(ROOM, "copyInviteLink") + fn(ROOM, "InviteDialog") + """
function Modal() {}; function PersonMark() {}
const INVITE_FILTER_FROM = 8, INVITE_MAX = 10
const copied = [], toasts = [], posts = [], closed = []
globalThis.P = { copy: async t => { copied.push(t); return true }, toast: (k, m) => toasts.push(m) }
const store = { post: async (p, b) => { posts.push([p, b]); return { sent: b.friends.length } } }
const pk = n => String(n).padStart(64, '0')
const friend = (n, name, extra) => Object.assign({ pk: pk(n), name, friend: true, impostor: false, unread: 0, ts: 1 }, extra || {})
const room = { id: '%(room)s', name: 'demoscene', members: [{ pk: pk(2), online: true }, { pk: pk(3), online: false }], invite_link: 'https://goodmachines.ai/ninsei/join#%(room)s@nos.lol' }
const box = (root, name) => find(root.tree, n => n.type === 'input' && n.props['aria-label'] === 'Invite ' + name)
""" % {"room": ROOM_ID}


@needs_node
def test_the_invite_dialog_lists_friends_marks_those_in_the_room_and_sends_one_route_call():
    r = run(INVITE_JS + """
const snap = { dms: { threads: [friend(1, 'Ann'), friend(2, 'Bo'), friend(3, 'Cy'), friend(4, 'Old', { friend: false })] } }
const root = mount(InviteDialog, { store, snap, room, onClose: () => closed.push(1) })
const names = () => []
const t = text(root.tree)
const sendBtn = () => button(root.tree, 'Send invite')
const first = { text: t, ann: !!box(root, 'Ann'), bo: !!box(root, 'Bo'), cy: !!box(root, 'Cy'), old: !!box(root, 'Old'), filter: !!find(root.tree, n => n.type === K.Input), disabled: !!sendBtn().props.disabled }
box(root, 'Ann').props.onChange(); box(root, 'Cy').props.onChange()
await settle()
const label = text(button(root.tree, 'Send 2 invites'))
await button(root.tree, 'Send 2 invites').props.onClick()
await settle()
const link = find(root.tree, n => n.type === K.Button && text(n).includes('Copy invite link'))
await link.props.onClick()
out({ first, label, posts, closed, toasts, copied, desc: root.tree.props.description })
""")
    f = r["first"]
    assert f["ann"] and f["cy"] and not f["bo"] and not f["old"] and f["disabled"] and not f["filter"]            # in the room: no box; not a friend: not listed
    # Cy joined once but isn't here now (they may have left): they can be invited, and say nothing about the room
    assert "in this room" in f["text"] and "Old" not in f["text"] and "Copy invite link" in f["text"]
    assert "never sees it" in r["desc"]                                                                          # said once, in the dialog's own words
    assert r["label"] == "Send 2 invites" and r["posts"] == [["/rooms/invite", {"room": ROOM_ID, "friends": [f"{1:064d}", f"{3:064d}"]}]]
    assert r["closed"] == [1] and r["toasts"] == ["2 invites sent.", "Invite link copied. It shows how to get Ninsei, then how to join this room."]
    assert r["copied"] == ["https://goodmachines.ai/ninsei/join#" + ROOM_ID + "@nos.lol"]


@needs_node
def test_a_long_friend_list_gets_a_filter_and_no_more_than_ten_can_be_picked():
    r = run(INVITE_JS + """
const threads = Array.from({ length: 14 }, (_, i) => friend(10 + i, 'Friend' + String.fromCharCode(65 + i)))
const root = mount(InviteDialog, { store, snap: { dms: { threads } }, room: Object.assign({}, room, { members: [] }), onClose() {} })
const filter = find(root.tree, n => n.type === K.Input)
for (let i = 0; i < 12; i++) { const b = box(root, 'Friend' + String.fromCharCode(65 + i)); if (!b.props.disabled) b.props.onChange(); await settle() }
const checked = threads.filter(t => box(root, t.name).props.checked).length
const eleventhDisabled = !!box(root, 'FriendK').props.disabled
filter.props.onChange({ target: { value: 'friendn' } })
await settle()
const shown = threads.filter(t => box(root, t.name)).map(t => t.name)
filter.props.onChange({ target: { value: 'zzz' } })
await settle()
out({ hasFilter: !!filter, checked, eleventhDisabled, shown, none: text(root.tree).includes('No friend called that.'), cap: text(root.tree).includes('Up to 10 at a time.') })
""")
    assert r["hasFilter"] and r["checked"] == 10 and r["eleventhDisabled"] and r["shown"] == ["FriendN"] and r["none"]


@needs_node
def test_no_friends_says_how_to_make_one_and_the_send_button_waits():
    r = run(INVITE_JS + """
const root = mount(InviteDialog, { store, snap: { dms: { threads: [] } }, room, onClose() {} })
out({ text: text(root.tree), disabled: !!button(root.tree, 'Send invite').props.disabled })
""")
    assert "No friends yet" in r["text"] and r["disabled"] is True


def test_the_header_has_an_invite_button_next_to_share_code_and_cards_and_conversations_have_invite_to_a_room():
    head = fn(ROOM, "RoomHeader")
    assert head.index("'Share code'") < head.index("'Invite'") and "jsx(InviteDialog, { store, snap, room" in head.replace("inviting && ", "")
    assert "'Invite to a room'" in CARD and "props.openInvite(act.message.pk, act.message.name)" in CARD and "=== 'friend'" in CARD.split("inviteThem,")[0][-300:]
    assert "'Invite ' + name + ' to a room'" in DM and "props.onInvite(pk, name)" in DM
    assert "'/rooms/invite'" in fn(APP, "InviteToRoomDialog") and "friends: [pk]" in fn(APP, "InviteToRoomDialog")


@needs_node
def test_inviting_from_a_card_or_conversation_picks_one_of_my_rooms_and_sends_the_same_route_call():
    r = run(fn(APP, "InviteToRoomDialog") + fn(CORE, "cleanSnippet") + """
function Modal() {}
const posts = [], closed = []
const store = { post: async (p, b, ok) => { posts.push([p, b, ok]); return { sent: 1 } } }
const rooms = [{ id: '%(room)s', name: 'demoscene' }, { id: '1'.repeat(16), name: 'synths' }]
const root = mount(InviteToRoomDialog, { store, snap: { rooms }, pk: 'a'.repeat(64), name: 'Kit', onClose: () => closed.push(1) })
const rows = []
;(function walk(n) { if (!n || typeof n !== 'object') return; if (Array.isArray(n)) return n.forEach(walk); if (n.props && n.props.className === 'h-navrow') rows.push(n); [].concat((n.props && n.props.children) || []).forEach(walk) })(root.tree)
await rows[1].props.onClick()
const none = mount(InviteToRoomDialog, { store, snap: { rooms: [] }, pk: 'a'.repeat(64), name: 'Kit', onClose() {} })
out({ labels: rows.map(x => text(x)), posts, closed, none: text(none.tree) })
""" % {"room": ROOM_ID})
    assert r["labels"] == ["#demoscene", "#synths"] and r["posts"] == [["/rooms/invite", {"room": "1" * 16, "friends": ["a" * 64]}, "Invited Kit to synths."]]
    assert r["closed"] == [1] and "aren’t in any rooms" in r["none"]


# ---- the sidebar, the list and the conversation ---------------------------------------------------------------------

INVITES = [{"pk": "a" * 64, "name": "Kit", "impostor": False, "room": ROOM_ID, "room_name": "demoscene", "ts": 5, "code": f"ninsei:{ROOM_ID}@nos.lol"},
           {"pk": "b" * 64, "name": "npub1fake…", "impostor": True, "room": "1" * 16, "room_name": "a room", "ts": 6, "code": "ninsei:" + "1" * 16}]


@needs_node
def test_the_sidebar_has_one_invites_row_with_a_count_and_it_opens_the_list():
    r = run(dm_js("""
const DM_INVITES = 'invites'
const store = { dm: () => 'invites', setDm: pk => { globalThis.SET = pk } }
let went = null
const tree = DmRail({ store, snap: { dms: { threads: [], requests: 0, pending: [], invites: %s, rev: 1 } }, view: 'dm', go: v => { went = v } })
const rows = []
;(function walk(n) { if (!n || typeof n !== 'object') return; if (Array.isArray(n)) return n.forEach(walk)
  if (n.props && n.props.className === 'h-navrow') rows.push(n); (n.props && [].concat(n.props.children || [])).forEach(walk) })(tree)
rows[0].props.onClick()
const none = text(DmRail({ store, snap: { dms: { threads: [], requests: 0, pending: [], invites: [] } }, view: 'lobby', go() {} }))
const empty = DmRail({ store, snap: { dms: { threads: [], requests: 0, pending: [] } }, view: 'lobby', go() {} })
out({ labels: rows.map(x => text(x).trim()), on: rows.map(x => x.props['data-on']), set: globalThis.SET, went,
      count: find(rows[0], n => n.props && n.props.className === 'h-mentions').props['aria-label'], none, emptyHint: text(empty) })
""" % json.dumps(INVITES)))
    assert r["labels"] == ["Invites2"] and r["on"] == [True] and r["set"] == "invites" and r["went"] == "dm" and r["count"] == "2 room invites"
    assert "Invites" not in r["none"] and "Add friend" in r["none"]


@needs_node
def test_the_invites_list_joins_through_the_preview_and_ignores_silently():
    r = run(EXTRA + fn(CORE, "cleanSnippet") + fn(DM, "DmInvites") + """
function PersonMark() {}
const posts = [], joins = []
const store = { post: async (p, b, ok) => { posts.push([p, b, ok]); return {} } }
const root = mount(DmInvites, { store, snap: { dms: { invites: %s } }, onJoin: (code, room) => joins.push([code, room]) })
const t = text(root.tree)
await button(root.tree, 'Join').props.onClick()
await find(root.tree, n => n.type === K.Button && n.props['aria-label'] === 'Ignore the invite from Kit').props.onClick()
const empty = mount(DmInvites, { store, snap: { dms: { invites: [] } }, onJoin() {} })
out({ t, joins, posts, empty: text(empty.tree) })
""" % json.dumps(INVITES))
    assert "demoscene" in r["t"] and "from Kit" in r["t"] and "not verified · from npub1fake…" in r["t"] and "a room" in r["t"] and "no message" in r["t"]
    assert r["joins"] == [[f"ninsei:{ROOM_ID}@nos.lol", ROOM_ID]]                       # the code with its hosts, so the preview can offer them
    assert r["posts"] == [["/invite/ignore", {"pk": "a" * 64, "room": ROOM_ID}, "Ignored. Kit isn’t told."]] and "No invites right now." in r["empty"]


@needs_node
def test_a_conversation_shows_who_invited_whom_with_join_only_while_it_waits():
    r = run(dm_js("") + fn(DM, "InviteLine") + """
const joins = []
const line = (m, friend) => { const el = DmItem({ it: { kind: 'invite', key: 'i', m }, animate: false, friend, onJoin: (c, r) => joins.push([c, r]) })
  const inner = find(el, n => n.type === InviteLine); const tree = InviteLine(inner.props); return { text: text(tree), join: find(tree, n => n.type === K.Button), status: tree.props['data-invite'] } }
const base = { room: '%(room)s', room_name: 'demoscene', code: 'ninsei:%(room)s@nos.lol' }
const theirs = line(Object.assign({ mine: false, name: 'Kit', status: 'new' }, base), 'Kit')
const mine = line(Object.assign({ mine: true, name: 'You', status: 'sent' }, base), 'Kit')
const joined = line(Object.assign({ mine: false, name: 'Kit', status: 'joined' }, base), 'Kit')
const ignored = line(Object.assign({ mine: false, name: 'Kit', status: 'ignored' }, base), 'Kit')
const unknown = line(Object.assign({ mine: false, name: 'Kit', status: 'new' }, base, { room_name: '' }), 'Kit')
theirs.join.props.onClick()
out({ theirs: theirs.text, mine: mine.text, mineJoin: !!mine.join, joined: !!joined.join, ignored: !!ignored.join, unknown: unknown.text, joins })
""" % {"room": ROOM_ID})
    assert r["theirs"] == "Kit invited you to demoscene" + "Join" and r["mine"] == "You invited Kit to demoscene" and not r["mineJoin"]
    assert not r["joined"] and not r["ignored"] and r["unknown"].startswith("Kit invited you to a room")
    assert r["joins"] == [[f"ninsei:{ROOM_ID}@nos.lol", ROOM_ID]]
    assert "(it.kind === 'msg' || it.kind === 'invite')" in fn(DM, "DmView")


# ---- the toasts ---------------------------------------------------------------------------------------------------------

ALERTS = """
const toasts = [], os = [], timers = []
let NOW = 1e12
Date.now = () => NOW
globalThis.P = { toast: (k, m) => toasts.push(m), osNotify: o => os.push(o),
  setTimeout: (f, ms) => { const t = { f, ms }; timers.push(t); return () => { const i = timers.indexOf(t); if (i >= 0) timers.splice(i, 1) } } }
function nav() { return { set(v) { globalThis.NAVSET = v } } }
let listener = null
const store = { subscribe: fn => { listener = fn; return () => { listener = null } }, isShowing: () => false, setRoom() {}, setDm(pk) { globalThis.DMPK = pk } }
const off = mentionAlerts(store)
const inv = (pk, name, room, room_name, extra) => Object.assign({ pk, name, impostor: false, room, room_name, ts: 1 }, extra || {})
const snapI = (invites, status) => ({ snap: { rooms: [], settings: { status_mode: status || 'auto' }, dms: { threads: [], pending: [], invites } } })
const join = (id, room, name, room_name) => ({ id, room, name, room_name: room_name || 'shader club', ts: 1 })
const snapJ = (joins, rooms, status) => ({ snap: { rooms: rooms || [{ id: 'r1', name: 'shader club', muted: false }], settings: { status_mode: status || 'auto' }, joins, dms: { threads: [], pending: [] } } })
"""


@needs_node
def test_an_invite_toast_names_who_and_which_room_once_per_sender_every_thirty_seconds_and_counts_several():
    r = run(fn(CORE, "cleanSnippet") + fn(CORE, "mentionAlerts") + "const INVITE_TOAST_MS = 30000, JOIN_TOAST_MS = 30000\n" + ALERTS + """
const k1 = inv('k', 'Kit', 'r1', 'demoscene'), k2 = inv('k', 'Kit', 'r2', 'synths', { ts: 2 }), k3 = inv('k', 'Kit', 'r3', 'chiptune', { ts: 3 }), k4 = inv('k', 'Kit', 'r4', 'dub', { ts: 4 })
listener(snapI([k1]))                                                    // first load: only the baseline
const first = toasts.length
listener(snapI([k1]))                                                    // the same: nothing
const same = toasts.length
listener(snapI([k1, k2]))                                                // new: by name and room
listener(snapI([k1, k2, k3]))                                            // a second from the same sender inside 30 s: listed, not toasted
const quick = toasts.slice()
NOW += 31000
listener(snapI([k1, k2, k3, k4]))
const later = toasts.slice()
listener(snapI([k4, inv('a', 'Ann', 'r5', 'a room', { ts: 5 }), inv('b', 'Bo', 'r6', 'glitch', { ts: 6 }), inv('c', 'Cy', 'r7', 'dub', { ts: 7 })]))
const several = toasts.slice(later.length)
os.forEach(o => o.onActivate())
out({ first, same, quick, later, several, os: os.map(o => [o.title, o.body]), dmpk: globalThis.DMPK, navset: globalThis.NAVSET })
""")
    assert r["first"] == 0 and r["same"] == 0 and r["quick"] == ["Kit invited you to synths"] and r["later"] == ["Kit invited you to synths", "Kit invited you to dub"]
    assert r["several"] == ["3 room invites"]
    assert [o[1] for o in r["os"]] == ["Open Ninsei to answer."] * 3 and r["os"][0][0] == "Kit invited you to synths" and r["dmpk"] == "invites" and r["navset"] == "dm"


@needs_node
def test_an_invite_from_a_lookalike_is_flagged_and_do_not_disturb_silences_it_without_replaying_later():
    r = run(fn(CORE, "cleanSnippet") + fn(CORE, "mentionAlerts") + "const INVITE_TOAST_MS = 30000, JOIN_TOAST_MS = 30000\n" + ALERTS + """
listener(snapI([]))
listener(snapI([inv('x', 'npub1fake…', 'r1', 'demoscene', { impostor: true })]))
const flagged = toasts.slice()
listener(snapI([inv('x', 'npub1fake…', 'r1', 'demoscene', { impostor: true }), inv('k', 'Kit', 'r2', 'synths', { ts: 2 })], 'dnd'))
const dnd = toasts.length
listener(snapI([inv('x', 'npub1fake…', 'r1', 'demoscene', { impostor: true }), inv('k', 'Kit', 'r2', 'synths', { ts: 2 })], 'auto'))   // leaving the mode replays nothing
out({ flagged, dnd, after: toasts.length })
""")
    assert r["flagged"] == ["Someone not verified (npub1fake…) invited you to demoscene"] and r["dnd"] == 1 and r["after"] == 1


@needs_node
def test_someone_joined_your_room_names_one_person_counts_several_and_skips_muted_rooms_and_the_first_load():
    r = run(fn(CORE, "cleanSnippet") + fn(CORE, "mentionAlerts") + "const INVITE_TOAST_MS = 30000, JOIN_TOAST_MS = 30000\n" + ALERTS + """
const j1 = join('j1', 'r1', 'Sam')
listener(snapJ([j1]))                                         // already there on first load: baseline
const first = toasts.length
listener(snapJ([j1, join('j2', 'r1', 'Sam')]))                // the first join of a quiet spell: by name
const named = toasts.slice()
listener(snapJ([j1, join('j2', 'r1', 'Sam'), join('j3', 'r1', 'Olu')]))     // inside 30 s: counted, told when the spell ends
NOW += 5000
listener(snapJ([join('j4', 'r1', 'Mo')]))
const quiet = toasts.length
const pending = timers.length
timers.shift().f()                                            // the spell ends
const summary = toasts.slice(named.length)
// a muted room, and do not disturb: nothing, and nothing replayed
NOW += 40000
listener(snapJ([join('j5', 'r1', 'Al')], [{ id: 'r1', name: 'shader club', muted: true }]))
listener(snapJ([join('j5', 'r1', 'Al'), join('j6', 'r1', 'Bea')], undefined, 'dnd'))
const silent = toasts.length
// several at once in a quiet room: one count, no name
NOW += 40000
listener(snapJ([join('j7', 'r1', 'Cy'), join('j8', 'r1', 'Di'), join('j9', 'r1', 'Ed')]))
const together = toasts.slice(silent)
off()
out({ first, named, quiet, pending, summary, silent, together, left: timers.length, os: os.length })
""")
    assert r["first"] == 0 and r["named"] == ["Sam joined shader club"]
    assert r["quiet"] == 1 and r["pending"] == 1 and r["summary"] == ["3 people joined shader club"]       # Olu and Mo after Sam
    assert r["silent"] == 2 and r["together"] == ["3 people joined shader club"] and r["left"] == 0         # stopping cancels the timer
    assert r["os"] == 0                                                                                      # never a desktop notification


@needs_node
def test_a_join_name_is_cleaned_like_every_other_toast():
    r = run(fn(CORE, "cleanSnippet") + fn(CORE, "mentionAlerts") + "const INVITE_TOAST_MS = 30000, JOIN_TOAST_MS = 30000\n" + ALERTS + """
listener(snapJ([]))
listener(snapJ([join('j1', 'r1', 'Sam\\u202e\\u200b evil\\n' + 'x'.repeat(100), 'club\\u202e' + 'y'.repeat(100))]))
out(toasts)
""")
    assert len(r) == 1 and "\u202e" not in r[0] and "\u200b" not in r[0] and "\n" not in r[0] and len(r[0]) < 120


# ---- Cmd+K and Rejoin -------------------------------------------------------------------------------------------------

@needs_node
def test_rooms_you_left_are_listed_last_as_rejoin_and_picking_one_opens_the_preview_with_its_code():
    r = run(fn(CORE, "foldText") + fn(CORE, "fuzzyScore") + fn(TOOLS, "switcherItems") + fn(TOOLS, "filterSwitcher") + """
const snap = { rooms: [{ id: 'r1', name: 'demoscene' }, { id: 'r2', name: 'synth club', muted: false }],
  dms: { threads: [{ pk: 'a'.repeat(64), name: 'Kit', friend: true }], requests: 0, invites: [{ pk: 'a'.repeat(64) }, { pk: 'b'.repeat(64) }] },
  left: [{ id: 'r9', name: 'demoscene old', code: 'ninsei:%(room)s@nos.lol' }, { id: 'r8', name: 'shader sketchbook', code: 'ninsei:' + '1'.repeat(16) }] }
const all = switcherItems(snap)
const kinds = all.map(i => [i.kind, i.label])
const scene = filterSwitcher(all, 'scene').map(i => i.label)        // a live room and a left room match: live first
const rejoin = all.filter(i => i.kind === 'rejoin').map(i => [i.label, i.sub, i.code])
const typed = filterSwitcher(all, 'shader').map(i => [i.kind, i.label])
const none = switcherItems({ rooms: [], dms: {} })
out({ kinds, scene, rejoin, typed, noneLeft: none.filter(i => i.kind === 'rejoin').length, noInvites: none.some(i => i.kind === 'invites') })
""" % {"room": ROOM_ID})
    assert r["kinds"][-2:] == [["rejoin", "Rejoin demoscene old"], ["rejoin", "Rejoin shader sketchbook"]]
    assert ["invites", "Room invites"] in r["kinds"] and r["scene"] == ["demoscene", "Rejoin demoscene old"]
    assert r["rejoin"][0] == ["Rejoin demoscene old", "Left room", f"ninsei:{ROOM_ID}@nos.lol"] and r["typed"] == [["rejoin", "Rejoin shader sketchbook"]]
    assert r["noneLeft"] == 0 and r["noInvites"] is False
    app = fn(APP, "App")
    assert "it.kind === 'rejoin') { setJoinFrom(null); setJoinFor(it.code) }" in app and "it.kind === 'invites'" in app and "DM_INVITES" in app


@needs_node
def test_the_page_and_the_engine_trim_exactly_the_same_characters():
    """Every character of the Basic Multilingual Plane, at both ends of a word: the two sides strip the same set (whitespace and
    U+FEFF), so a pasted code reads the same wherever it is parsed. Python's str.strip() and JavaScript's .trim() disagree on
    U+001C-U+001F and U+0085 (Python only) and U+FEFF (JavaScript only)."""
    chars = [chr(c) for c in range(0x10000) if not 0xD800 <= c < 0xE000]
    r = run(HOSTS_JS + "const chars = %s\nout(chars.map(c => trimCode(c + 'ab' + c)))" % json.dumps(chars))
    assert r == [codes.trim(c + "ab" + c) for c in chars]
    stripped = {c for c, out in zip(chars, r) if out == "ab"}
    assert "\ufeff" in stripped and "\xa0" in stripped and "\n" in stripped and "\u2003" in stripped
    assert not stripped & {"\x1c", "\x1d", "\x1e", "\x1f", "\x85", "\u180e", "\u200b", "\x00"}
    assert not {c for c in stripped if not (c.isspace() or c == "\ufeff")}
