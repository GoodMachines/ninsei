"""The page side of pictures, faces and typing, under node: the picture encode loop, the crop, the avatar cache, which
of picture, face and letter a person gets, the typing line and its pacing, and that every place a person
appears goes through one component."""
import re

import pytest

from test_audit_ui import CORE, ROOM, SETUP, STYLE, composer_js, fn, const, needs_node, run, src

PARTS = src("30_parts.js")
FACE = src("10_face.js")
LOOK = src("32_look.js")
CARD = src("35_card.js")
DM = src("57_dm.js")
LOBBY = src("70_lobby.js")
APP = src("80_app.js")
LINE = src("55_line.js")

ENCODE = (fn(CORE, "clamp") + fn(CORE, "dataUriBytes") + fn(CORE, "avatarCrop") + fn(CORE, "encodeAvatar")
          + const(CORE, "AVATAR_PX") + const(CORE, "AVATAR_BYTES") + const(CORE, "AVATAR_TYPES") + const(CORE, "AVATAR_QUALITY"))


def b64len(n: int) -> str:
    """A data URI body that decodes to exactly n bytes."""
    import base64
    return base64.b64encode(b"x" * n).decode()


@needs_node
def test_the_encode_loop_lowers_quality_until_the_picture_fits_and_prefers_webp():
    js = ENCODE + """
const sizes = { 0.92: 70000, 0.85: 60000, 0.78: 51000, 0.7: 47000, 0.6: 30000 }
const asked = []
const canvas = { toDataURL(type, q) { asked.push([type, q]); return 'data:' + type + ';base64,' + 'A'.repeat(Math.ceil(sizes[q] / 3) * 4) } }
const uri = encodeAvatar(canvas, 48 * 1024)
out({ asked, type: uri.slice(0, 22), bytes: dataUriBytes(uri), ok: dataUriBytes(uri) <= 48 * 1024 })
"""
    r = run(js)
    assert r["asked"] == [["image/webp", 0.92], ["image/webp", 0.85], ["image/webp", 0.78], ["image/webp", 0.7]]
    assert r["type"] == "data:image/webp;base64" and r["ok"]


@needs_node
def test_a_browser_that_cannot_make_webp_falls_back_to_jpeg_and_never_sends_a_png():
    js = ENCODE + """
const asked = []
// an old Safari: asked for webp it answers with a PNG, whatever was asked
const canvas = { toDataURL(type, q) { asked.push([type, q]); return type === 'image/webp' ? 'data:image/png;base64,AAAA' : 'data:image/jpeg;base64,' + 'A'.repeat(4000) } }
const uri = encodeAvatar(canvas, 48 * 1024)
// nothing fits
const huge = { toDataURL(type) { return 'data:' + type + ';base64,' + 'A'.repeat(200000) } }
const none = encodeAvatar(huge, 48 * 1024)
const throws = encodeAvatar({ toDataURL() { throw new Error('tainted') } }, 48 * 1024)
const junk = encodeAvatar({ toDataURL() { return 5 } }, 48 * 1024)
out({ asked: asked.map(a => a[0]), head: uri.slice(0, 23), none, throws, junk })
"""
    r = run(js)
    assert r["asked"] == ["image/webp", "image/jpeg"]       # webp once (a PNG answer ends that type), then jpeg
    assert r["head"] == "data:image/jpeg;base64," and r["none"] is None and r["throws"] is None and r["junk"] is None


@needs_node
def test_the_crop_is_a_centred_square_with_zoom_and_pan_that_stay_inside_the_photo():
    js = ENCODE + """
out([avatarCrop(400, 200, 1, 0, 0), avatarCrop(400, 200, 2, 0, 0), avatarCrop(400, 200, 1, 1, 0), avatarCrop(400, 200, 2, 1, 1),
     avatarCrop(400, 200, 2, -9, 9), avatarCrop(100, 100, 9, 0, 0), avatarCrop(100, 300, 1, 0, 1)])
"""
    a, b, c, d, e, f, g = run(js)
    assert a == {"sx": 100, "sy": 0, "sw": 200, "sh": 200}          # the largest centred square
    assert b == {"sx": 150, "sy": 50, "sw": 100, "sh": 100}          # zoom 2: its centre
    assert c["sx"] == 200 and c["sx"] + c["sw"] <= 400               # panned to the right edge, not past it
    assert d == {"sx": 300, "sy": 100, "sw": 100, "sh": 100}
    assert e == {"sx": 300, "sy": 100, "sw": 100, "sh": 100} or (e["sx"] >= 0 and e["sy"] + e["sh"] <= 200)
    assert f["sw"] == 25                                              # zoom is capped at 4
    assert g == {"sx": 0, "sy": 200, "sw": 100, "sh": 100}


@needs_node
def test_the_cache_asks_in_batches_keeps_pictures_by_version_and_refuses_anything_that_is_not_an_image():
    js = fn(CORE, "avatarFlush") + fn(CORE, "avatarWant") + fn(CORE, "useAvatarUri") + """
const AVATAR_CACHE = new Map()
const AVATAR_ASK = { keys: new Map(), timer: null, tries: new Map() }
const calls = []
const timers = []
globalThis.P = {
  setTimeout: (f, ms) => { timers.push(f); return () => {} },
  rest: async path => { calls.push(path); return { avatars: { [PK1]: { v: 'v1', uri: 'data:image/png;base64,AAAA' }, [PK2]: { v: 'v1', uri: 'javascript:alert(1)' } } } }
}
const PK1 = 'a'.repeat(64), PK2 = 'b'.repeat(64), PK3 = 'c'.repeat(64)
function Show(props) { return useAvatarUri(props.pk, props.v) }
const r1 = mount(Show, { pk: PK1, v: 'v1' }), r1b = mount(Show, { pk: PK1, v: 'v1' }), r2 = mount(Show, { pk: PK2, v: 'v1' }), r3 = mount(Show, { pk: PK3, v: 'v1' })
const before = [r1.tree, r2.tree]
timers.splice(0).forEach(f => f())     // the 40 ms batch timer
await settle()
const none = mount(Show, { pk: '', v: '' })
r1.update(r1.props); r2.update(r2.props); r3.update(r3.props); r1b.update(r1b.props)
out({ before, calls, one: r1.tree, same: r1b.tree, notAnImage: r2.tree, missing: r3.tree, skipped: none.tree, size: AVATAR_CACHE.size })
"""
    r = run(js)
    assert r["before"] == ["", ""]                                     # nothing until the fetch is back
    assert len(r["calls"]) == 1 and r["calls"][0].startswith("/avatars?pks=") and r["calls"][0].count(",") == 2   # one request, three people
    assert r["one"] == r["same"] == "data:image/png;base64,AAAA"
    assert r["notAnImage"] == "" and r["missing"] == "" and r["skipped"] == ""   # a javascript: URI is never handed to an <img>


PERSON_MARK = (fn(PARTS, "PersonMark") + """
const PeopleContext = {}
function useContext() { return globalThis.CTX }
function PersonPhoto() {}; function PersonFace() {}; function Initial() {}
const AVATAR_CACHE = new Map(); const AVATAR_ASK = { keys: new Map(), timer: null, tries: new Map() }
function useAvatarUri(pk, v) { return pk && v ? (globalThis.URIS[pk + ':' + v] || '') : '' }
const kind = n => n.type === PersonPhoto ? 'photo' : n.type === PersonFace ? 'face' : 'letter'
""")


@needs_node
def test_a_person_gets_their_picture_else_their_face_else_the_letter():
    js = PERSON_MARK + """
const FACE = { hue: 10 }
globalThis.URIS = { ['p1:v1']: 'data:image/webp;base64,AAAA' }
const shown = (ctx, props) => { globalThis.CTX = ctx; return kind(PersonMark(props)) }
const on = { show: true, people: { p1: { av: 'v1', face: FACE }, p2: { face: FACE }, p3: {} } }
out({
  both: shown(on, { pk: 'p1', name: 'A' }), face: shown(on, { pk: 'p2', name: 'B' }), letter: shown(on, { pk: 'p3', name: 'C' }), unknown: shown(on, { pk: 'zz', name: 'D' }),
  off: shown({ show: false, people: on.people }, { pk: 'p1', name: 'A' }),
  offNoFace: shown({ show: false, people: { p1: { av: 'v1' } } }, { pk: 'p1', name: 'A' }),
  flagged: shown(on, { pk: 'p1', name: 'A', flagged: true }),
  notLoaded: shown(on, { pk: 'p2', name: 'B', art: { av: 'v9', face: FACE } }),
  preview: shown({ show: false, people: {} }, { pk: 'me', name: 'Me', art: { uri: 'data:image/webp;base64,BBBB' } }),
  explicitNone: shown(on, { pk: 'p1', name: 'A', art: null }),
  size: PersonMark({ pk: 'p2', name: 'B', size: 40 }).props.size
})
"""
    r = run(js)
    assert r["both"] == "photo" and r["face"] == "face" and r["letter"] == "letter" and r["unknown"] == "letter"
    assert r["off"] == "face" and r["offNoFace"] == "letter"           # pictures off: faces and letters only
    assert r["flagged"] == "letter"                                      # a lookalike never wears a picture or face
    assert r["notLoaded"] == "face"                                      # until the picture arrives, the face stands in
    assert r["preview"] == "photo"                                       # Settings previews a picture the switch would hide
    assert r["explicitNone"] == "letter" and r["size"] == 40


def test_every_place_a_person_appears_goes_through_the_one_component():
    # gutters, @ menu, member list, typing line, DM rail and header and requests, lobby, the private line's own side
    assert "PersonMark, { pk: m.pk" in fn(ROOM, "Message")
    assert "PersonMark, { pk: c.pk" in fn(ROOM, "Composer")
    assert "PersonMark, { pk: p.pk" in fn(ROOM, "Person")
    assert "PersonMark, { pk: t.pk" in fn(ROOM, "TypingRow")
    assert "PersonMark, { pk: t.pk" in fn(DM, "DmRail") and "PersonMark, { pk, name" in fn(DM, "DmView") and "PersonMark, { pk: t.pk" in fn(DM, "DmRequests")
    assert "PersonMark, { pk: p.pk" in fn(LOBBY, "LobbyPerson")
    assert "PersonMark, { pk: snap.me.pk" in fn(LINE, "LineMessage")
    assert "PersonHero" in fn(CARD, "IdCard") and "PeopleContext" in fn(CARD, "ProfileSheet")
    # nobody draws the bare letter for a person any more except PersonMark's own fallback and the test stubs
    for name, text in (("50_room.js", ROOM), ("57_dm.js", DM), ("70_lobby.js", LOBBY), ("55_line.js", LINE), ("35_card.js", CARD)):
        assert "jsx(Initial" not in text, name
    assert "jsx(Initial" in fn(PARTS, "PersonMark")
    # and the whole page sits inside the provider that carries the snapshot's `people`
    assert "PeopleContext.Provider" in APP and "snap.people" in APP


def test_a_picture_is_only_ever_an_img_of_a_data_uri_the_engine_rebuilt():
    ph = fn(PARTS, "PersonPhoto")
    assert "jsx('img', { src: props.uri" in ph and "alt: ''" in ph and "referrerPolicy: 'no-referrer'" in ph
    for name, text in (("00_core", CORE), ("30_parts", PARTS), ("32_look", LOOK), ("35_card", CARD), ("50_room", ROOM)):
        assert "dangerouslySetInnerHTML" not in text and "innerHTML" not in text, name
    # the cache accepts a data:image/ URI only
    assert "hit.uri.indexOf('data:image/') === 0" in fn(CORE, "avatarFlush")
    # a person's picture is not drawn into the saved card image
    assert "never in anything exported" in CARD or "stays out of anything that gets exported" in CARD


# --- typing --------------------------------------------------------------------------------------------------------------

@needs_node
def test_the_typing_line_names_people_and_flags_lookalikes():
    js = fn(CORE, "joinNames") + fn(CORE, "typingText") + """
const t = (...n) => n.map(x => typeof x === 'string' ? { name: x } : x)
out([typingText([]), typingText(t('Maya')), typingText(t('Maya', 'Sam')), typingText(t('Maya', 'Sam', 'Lee')), typingText(t('a', 'b', 'c', 'd')),
     typingText(t({ name: 'Sam', impostor: true })), typingText(null), typingText([{}]), typingText(t('<b>x</b>'))])
"""
    r = run(js)
    assert r == ["", "Maya is typing…", "Maya and Sam are typing…", "Maya, Sam and Lee are typing…", "Several people are typing…",
                 "Sam (not verified) is typing…", "", "Someone is typing…", "<b>x</b> is typing…"]   # text, never markup


@needs_node
def test_typing_pings_at_most_once_per_five_seconds_per_room_and_never_shows_a_failure():
    js = const(CORE, "TYPING_SENT") + fn(CORE, "typingPing") + """
const calls = []
globalThis.P = { rest: (path, o) => { calls.push([path, o.body.room]); return Promise.reject(new Error('nope')) } }
const a = typingPing('r1', 100000), b = typingPing('r1', 102000), c = typingPing('r2', 102000), d = typingPing('r1', 105001), e = typingPing('', 109000)
await settle()
out({ sent: [a, b, c, d, e], calls })
"""
    r = run(js)
    assert r["sent"] == [True, False, True, True, False]
    assert r["calls"] == [["/typing", "r1"], ["/typing", "r2"], ["/typing", "r1"]]


@needs_node
def test_the_composer_signals_typing_only_for_room_text_and_never_in_a_private_conversation():
    js = fn(CORE, "clamp") + """
const calls = []
function typingPing(id) { calls.push(id) }
""" + composer_js() + fn(ROOM, "mentionCandidates") + fn(ROOM, "Composer") + """
function mentionQuery() { return null }; function mentionMatches() { return [] }
function useMemo(f) { return f() }
const useLayoutEffect = useEffect
function PersonMark() {}; function Face() {}; function GamesMenu() {}; function gameName(m) { return m }
K.Tip = function Tip() {}
const room = { id: 'r1', name: 'club', members: [] }
const ev = v => ({ target: { value: v, selectionStart: v.length } })
const talk = mount(Composer, { store: {}, room, gameOn: false })
const area = r => find(r.tree, n => n.type === 'textarea')
area(talk).props.onChange(ev('')); area(talk).props.onChange(ev('   ')); area(talk).props.onChange(ev('hel')); area(talk).props.onChange(ev('hello'))
const priv = mount(Composer, { store: {}, room: { id: 'dm-x', name: 'Sam', members: [] }, dm: { onSend() {}, placeholder: 'p', max: 2000 } })
area(priv).props.onChange(ev('secret'))
out(calls)
"""
    assert run(js) == ["r1", "r1"]        # words in a room (the pacing is typingPing's); nothing for blanks or a private message


def test_the_typing_line_is_always_in_the_page_so_the_composer_never_jumps():
    tl = fn(ROOM, "TypingLine")
    assert "role: 'status'" in tl and "'aria-live': 'polite'" in tl and "h-typingline" in tl
    assert ".h-typingline{min-height:" in STYLE
    assert "useEnter(true)" in fn(ROOM, "TypingRow")              # it eases in on a spring, not a CSS fade
    assert "jsx(TypingLine, { list: room.typing })" in fn(ROOM, "RoomView")
    # polling quickens while someone is typing, so the line is not two seconds late
    assert "room.typing" in fn(CORE, "createStore")


# --- the picker and the settings -----------------------------------------------------------------------------------------

def test_the_picker_says_what_is_public_and_what_is_stripped_and_takes_only_rasters():
    for words in ("Public and permanent", "relays or other apps may keep old pictures forever", "EXIF", "GPS location", "original file is never uploaded"):
        assert words in LOOK, words
    assert "image/png,image/jpeg,image/webp,image/gif" in LOOK and "svg" not in LOOK.split("PICTURE_FILE =")[1].split("\n")[0]
    assert "encodeAvatar(canvas.current, AVATAR_BYTES)" in LOOK and "props.onUse(uri)" in LOOK
    # the original file is read by the page only: nothing posts `file`
    assert "FormData" not in LOOK and not re.search(r"\bupload\s*:|P\.upload|\.upload\(", LOOK)


def test_onboarding_holds_the_picture_until_setup_is_finished_and_settings_publishes_at_once():
    ob = fn(SETUP, "Onboarding")
    assert "avatar: ''" in ob and "store.post('/avatar', { img: avatar })" in ob
    assert ob.index("store.post('/settings'") < ob.index("store.post('/avatar'")   # nothing about you goes out before setup
    assert "stage: true" in ob and "person_face: person_face || {}" in ob
    st = fn(SETUP, "SettingsForm")
    assert "store.post('/avatar', { img }" in st and "show_avatars" in st and "Everyone in my rooms" in st and "'Nobody'" in st or "label: 'Nobody'" in st
    assert "noCard: true" in LOOK                                    # no card style in the person's face picker
    assert "!props.noCard" in fn(PARTS, "FacePicker")


def test_the_pieces_are_styled_without_a_tint_and_hidden_pictures_stay_in_a_circle():
    for sel in (".h-pface,.h-photo{", ".h-photo img{", ".h-idcard-hero .h-pface", ".h-crop-view{", ".h-typingrow{"):
        assert sel in STYLE, sel
    assert "var(--tint)" not in STYLE.split(".h-pface,.h-photo{")[1].split("\n")[0]
    assert "hf-still" in fn(FACE, "PersonFace")                       # a person's face holds still: no agent blinking
