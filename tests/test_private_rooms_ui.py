"""Private rooms, the page side (docs/private-rooms-design.md), run under node with the shared hooks harness: the
Private switch on New room, the lock in the header and the sidebar, no code or link to copy in a private room, and
the Join preview and invite lines saying a room is private."""
from test_audit_ui import APP, ROOM, fn, needs_node, run
from test_invites_ui import DM, JOIN_JS, ROOM_ID, afn


@needs_node
def test_new_room_has_a_private_switch_that_drops_the_interests_and_says_what_private_means():
    r = run(fn(APP, "NewRoomDialog") + """
function Modal() {}; function Field() {}; function InterestInput() {}
const posts = []
const store = { post: async (p, b, toast) => { posts.push([p, b, toast]); return { id: 'r1' } } }
const snap = { settings: { interests: ['shaders', 'synths'] } }
const root = mount(NewRoomDialog, { store, snap, onClose() {}, onDone() {} })
const modal = () => find(root.tree, n => n.type === Modal).props.description
const pub = { desc: modal(), interests: !!find(root.tree, n => n.type === InterestInput), toggle: find(root.tree, n => n.type === K.Toggle).props }
find(root.tree, n => n.type === K.Input && n.props.id === 'h-nr-name').props.onChange({ target: { value: 'the plan' } })
find(root.tree, n => n.type === K.Toggle).props.onChange(true)
await settle()
const priv = { desc: modal(), interests: !!find(root.tree, n => n.type === InterestInput), checked: find(root.tree, n => n.type === K.Toggle).props.checked }
await button(root.tree, 'Create room').props.onClick()
await settle()
out({ pub: { desc: pub.desc, interests: pub.interests, label: pub.toggle.label, about: pub.toggle.description, checked: pub.toggle.checked }, priv, posts })
""")
    assert "Rooms are public" in r["pub"]["desc"] and r["pub"]["interests"] is True and r["pub"]["checked"] is False
    assert r["pub"]["label"] == "Private room"
    # what the switch promises, and what it does not: agents read it, and who posts stays visible
    assert "Invite-only and encrypted" in r["pub"]["about"] and "agents can read it" in r["pub"]["about"]
    assert "who posts in it and when" in r["pub"]["about"]
    assert "not listed anywhere" in r["priv"]["desc"] and r["priv"]["interests"] is False and r["priv"]["checked"] is True
    assert r["posts"] == [["/rooms", {"name": "the plan", "about": "", "interests": [], "private": True}, "Private room created"]]


@needs_node
def test_a_private_room_has_no_code_to_copy():
    r = run(afn(ROOM, "copyRoomCode") + """
const copied = [], toasts = []
globalThis.P = { copy: async t => { copied.push(t); return true }, toast: (k, m) => toasts.push(m) }
await copyRoomCode({ id: '%(room)s', private: true, code: '' })
out({ copied, toasts })
""" % {"room": ROOM_ID})
    assert r["copied"] == [] and r["toasts"] == ["A private room has no code. Use Invite to bring a friend in."]
    head = fn(ROOM, "RoomHeader")
    assert "!room.private && jsx(K.Tip, { label: 'Copy the code people use to join'" in head     # no Share code button
    assert "room.private && jsx(K.Tip, { label: 'Private: only invited people can enter or read this room'" in head
    assert "!room.private && jsx(K.Button, { variant: 'secondary', size: 'sm', onClick: () => copyRoomCode(room)" in fn(ROOM, "RoomStarter")
    assert "onShare: room.private ? null : () => copyRoomCode(room)" in ROOM and "props.onShare && jsx(K.Button" in ROOM


@needs_node
def test_the_join_preview_says_a_room_is_private_and_who_can_read_it():
    r = run(JOIN_JS + """
const code = 'ninsei:%(room)s@nos.lol'
ANSWERS = [answer({ private: true, interests: [] })]
const input = t => !!find(t, n => n.type === K.Input)
const root = mount(JoinDialog, { store, initial: code, from: { name: 'Sam', room: 'the plan' }, onClose() {}, onDone() {} })
const before = input(root.tree)          // nothing says private yet: the code shows while the preview loads
await settle()
const priv = text(root.tree), privInput = input(root.tree)
await button(root.tree, 'Join').props.onClick()
await settle()
// the invite already said private (the invites list knows): no code field at any point
ANSWERS = [answer({ private: true, interests: [] })]
const known = mount(JoinDialog, { store, initial: code, from: { name: 'Sam', room: 'the plan', private: true }, onClose() {}, onDone() {} })
const knownInput = input(known.tree)
await settle()
// a code typed by hand keeps its field, private or not
ANSWERS = [answer({ private: true, interests: [] })]
const typed = mount(JoinDialog, { store, initial: code, onClose() {}, onDone() {} })
await settle()
ANSWERS = [answer()]
const pub = mount(JoinDialog, { store, initial: code, from: { name: 'Sam', room: 'the plan' }, onClose() {}, onDone() {} })
await settle()
out({ before, priv, privInput, knownInput, knownAfter: input(known.tree), typedInput: input(typed.tree), typed: text(typed.tree), posts,
  pub: text(pub.tree), pubInput: input(pub.tree) })
""" % {"room": ROOM_ID})
    assert "Private: only invited people can enter or read it. Members’ agents can read it too." in r["priv"]
    # a private room has no code, so an invite to one shows no code field; Join still sends the invite's code
    assert r["before"] is True and r["privInput"] is False
    assert r["knownInput"] is False and r["knownAfter"] is False
    assert r["posts"] == [["/rooms/join", {"room": "ninsei:%s@nos.lol" % ROOM_ID}]]
    assert r["typedInput"] is True and "Private:" in r["typed"]
    assert "Private:" not in r["pub"] and r["pubInput"] is True      # an invite to a public room is unchanged


def test_an_invite_passes_private_through_to_the_join_dialog():
    assert "props.onJoin(m.code, m.room, m.impostor ? '' : m.name, m.room_name, !!m.private)" in fn(DM, "InviteLine")
    assert "props.onJoin(i.code, i.room, i.impostor ? '' : i.name, i.room_name, !!i.private)" in fn(DM, "DmInvites")
    assert "setJoinFrom(from ? { name: from, room: roomName || '', private: !!priv } : null)" in APP
    assert APP.count("onJoin: (code, room, from, name, priv) => openLink(room, '', code, from, name, priv)") == 2


def test_the_sidebar_and_invites_mark_a_private_room():
    assert "r.private ? jsx('span', { className: 'h-hash', role: 'img', 'aria-label': 'Private room'" in APP
    line = fn(DM, "InviteLine")
    assert "name: m.private ? 'lock' : 'link'" in line and "(m.private ? ' (private)' : '')" in line
    assert "(i.private ? 'private room · ' : '')" in fn(DM, "DmInvites")
    # the invite dialog says the invite is the way in, and that the friend needs a Ninsei that knows private rooms
    dialog = fn(ROOM, "InviteDialog")
    assert "carries this room’s key: it is the only way in" in dialog and "They need the newest Ninsei to see it." in dialog
