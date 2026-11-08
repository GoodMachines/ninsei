"""Pixel faces for agents and premade portraits for people, run under node with the shared hooks harness: the pixel
renderer's determinism and bounds, the portrait list the page ships (the same ids as the engine's), the avatar model's
cleaning (the same as the engine's), who shows what (picture, portrait, older face, initial), the portrait picker's
keyboard and labels, Surprise me, the agent builder's keys, and the card export."""
import json
import random
import pathlib
import re

from ninsei_engine import engine
from ninsei_engine.engine import clean_avatar
from test_audit_ui import PARTS, STYLE, const, fn, needs_node, run, src

UI = pathlib.Path(__file__).resolve().parents[1] / "ui"
PRESETS_JSON = pathlib.Path(__file__).resolve().parents[1] / "docs/media/src/presets/presets.json"

PIXEL, MEDIA, MODEL, BUILDER, FACE, CARDIMG, LOOK, SETUP = (
    src(n) for n in ("12_pixel.js", "05_media.js", "14_avatar.js", "33_builder.js", "10_face.js", "36_cardimage.js",
                     "32_look.js", "40_setup.js"))

# everything the renderers need, and nothing else: the colour maths from the card export, then the modules
ART = ("const cx = (...a) => a.filter(Boolean).join(' ')\n" + "".join(fn(CARDIMG, n) for n in ("rgbHex", "clamp01", "oklabToRgb", "oklchToHex"))
       + PIXEL + MEDIA + MODEL)
SHAPES = engine.FACE_SHAPES


# --- the model: the page and the engine agree ---------------------------------------------------------------------------

@needs_node
def test_the_page_ships_exactly_the_portraits_the_engine_knows():
    rows = json.loads(PRESETS_JSON.read_text())
    got = run(ART + "out(PERSON_PRESETS.map(p => [p.id, p.alt, p.src.slice(0, 23), p.src.length]))")
    assert [g[0] for g in got] == [r["id"] for r in rows] == list(engine.AV_PRESETS)       # same ids in the same order
    assert [g[1] for g in got] == [r["alt"] for r in rows] and all(g[1].strip() for g in got)
    assert all(g[2] == "data:image/webp;base64," and g[3] < 12000 for g in got)            # a small inline WebP each


@needs_node
def test_the_page_cleans_an_avatar_exactly_as_the_engine_does():
    rng = random.Random(7)
    ids = list(engine.AV_PRESETS)
    junk = [None, "x", 5, [], {}, {"v": 1}, {"v": 2, "p": "p01"}, {"v": "1", "p": "p01"}, {"v": True, "p": "p01"}, {"v": 1, "p": "p99"},
            {"v": 1, "p": None}, {"v": 1, "p": ["p01"]}, {"v": 1, "p": "P01"}, {"v": 1, "p": " p01"}, {"v": 1, "sk": 3, "hs": "bun"}]
    cases = junk + [{"v": 1, "p": rng.choice(ids), "extra": rng.random()} for _ in range(40)]
    got = run(ART + "out(" + json.dumps(cases) + ".map(cleanAvatar))")
    assert got == [clean_avatar(c) for c in cases]
    assert sum(1 for g in got if g) == 40                                                     # the junk is all refused, nothing stands in


@needs_node
def test_surprise_me_picks_another_known_portrait_and_can_reach_them_all():
    r = run(ART + """
let seed = 5; const rand = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647 }
const ids = PERSON_PRESETS.map(p => p.id)
const picks = Array.from({ length: 3000 }, () => surprisePreset('p03', rand))
out({ never: picks.includes('p03'), seen: new Set(picks).size, known: picks.every(x => ids.includes(x)), from_none: ids.includes(surprisePreset('', rand)) })
""")
    assert r["never"] is False and r["known"] and r["from_none"] and r["seen"] == len(engine.AV_PRESETS) - 1


# --- the renderer -------------------------------------------------------------------------------------------------------

DRAW_ALL = ART + """
const faces = []
for (const shape of %s) for (const acc of %s) for (const pattern of %s) faces.push({ shape, acc, pattern, eyes: 'round', mouth: 'smile', hue: 200, hue2: 30 })
for (const shape of %s) for (const eyes of %s) for (const mouth of %s) faces.push({ shape, eyes, mouth, acc: 'none', pattern: 'none', hue: 120, hue2: 300 })
const agents = faces.map(f => { const a = pxAgent(f, 'open'); return [a.base, a.eyes, a.blink, a.mouth, a.talk, a.acc, a.under] })
""" % (json.dumps(SHAPES), json.dumps(engine.FACE_ACCS), json.dumps(engine.FACE_PATTERNS), json.dumps(SHAPES),
       json.dumps(engine.FACE_EYES), json.dumps(engine.FACE_MOUTHS))


@needs_node
def test_the_same_settings_always_draw_the_same_pixels():
    js = DRAW_ALL + "out({ agents: require('crypto').createHash('sha256').update(JSON.stringify(agents)).digest('hex'), n: agents.length })"
    one, two = run(js), run(js)
    assert one == two and one["n"] == len(SHAPES) * (len(engine.FACE_ACCS) * len(engine.FACE_PATTERNS) + len(engine.FACE_EYES) * len(engine.FACE_MOUTHS))
    # and different settings draw different pixels: every agent option changes the drawing
    r = run(ART + """
const base = { shape: 'round', eyes: 'round', mouth: 'smile', acc: 'none', pattern: 'none', hue: 200, hue2: 30 }
const key = f => { const a = pxAgent(f, 'open'); return JSON.stringify([a.base, a.eyes, a.mouth, a.acc]) }
const opts = { shape: %s, eyes: %s, mouth: %s, acc: %s, pattern: %s }
out(Object.entries(opts).map(([k, list]) => new Set(list.map(v => key(Object.assign({}, base, { [k]: v })))).size === list.length))
""" % (json.dumps(SHAPES), json.dumps(engine.FACE_EYES), json.dumps(engine.FACE_MOUTHS), json.dumps(engine.FACE_ACCS), json.dumps(engine.FACE_PATTERNS)))
    assert r == [True] * 5


@needs_node
def test_every_agent_part_stays_inside_the_grid_with_its_outline():
    r = run(ART + """
const off = []
const check = (what, g) => { for (let i = 0; i < g.length; i++) if (g[i]) { const x = i %% 64, y = (i / 64) | 0; if (x < 1 || y < 1 || x > 62 || y > 62) { off.push(what); return } } }
for (const shape of %s) {
  const body = pxAgentBody(shape)
  check(shape, body.g)
  for (const acc of %s) check(shape + '/' + acc, pxAccessory(acc, body))
  for (const eyes of %s) for (const frame of ['open', 'closed', 'half', 'happy', 'x', 'big', 'wary']) check(shape + '/' + eyes + '/' + frame, pxEyes(eyes, frame, body.b))
  for (const mouth of %s.concat(['talk', 'smirk', 'o', 'frown', 'grin'])) check(shape + '/' + mouth, pxMouth(mouth, body.b))
}
out(off)
""" % (json.dumps(SHAPES), json.dumps(engine.FACE_ACCS), json.dumps(engine.FACE_EYES), json.dumps(engine.FACE_MOUTHS)))
    assert r == []


@needs_node
def test_stamped_parts_are_clipped_at_the_edge_never_wrapped_onto_the_next_row():
    r = run(ART + """
const g = pxGrid()
pxMap(g, ['aaaa', 'bbbb'], 62, 0)          // two cells hang off the right edge
pxMap(g, ['cc'], -1, 5)                    // one off the left
const at = (grid, x, y) => grid[y * 64 + x] ? String.fromCharCode(grid[y * 64 + x]) : ''
out({ right: [at(g, 62, 0), at(g, 63, 0), at(g, 0, 1), at(g, 1, 1), at(g, 62, 1)], left: [at(g, 0, 5), at(g, 63, 4)], count: g.filter(Boolean).length })
""")
    assert r["right"] == ["a", "a", "", "", "b"] and r["left"] == ["c", ""] and r["count"] == 5


@needs_node
def test_crisp_edges_only_at_whole_multiples_of_the_grid():
    r = run(ART + "out([24, 40, 64, 96, 128, 120].map(s => pxCrisp(s)).concat([pxCrisp(96, 96), pxCrisp(128, 96), pxCrisp(192, 96)]))")
    assert r == [False, False, True, False, True, False, True, False, True]


# --- who shows what ----------------------------------------------------------------------------------------------------

PERSON_MARK = ART + fn(PARTS, "PersonMark") + """
const PeopleContext = {}
function useContext() { return globalThis.CTX }
function PersonPhoto() {}; function PersonFace() {}; function Initial() {}
function useAvatarUri(pk, v) { return pk && v ? (globalThis.URIS[pk + ':' + v] || '') : '' }
const kind = n => n.type === PersonPhoto ? 'photo' : n.type === PersonAvatar ? 'avatar' : n.type === PersonFace ? 'face' : 'letter'
const shown = (ctx, props) => { globalThis.CTX = ctx; return kind(PersonMark(props)) }
"""


@needs_node
def test_a_picture_comes_first_then_the_portrait_then_an_older_face_then_the_initial():
    r = run(PERSON_MARK + """
globalThis.URIS = { ['p1:v1']: 'data:image/webp;base64,AAAA' }
const MINE = { v: 1, p: 'p05' }, FACE = { hue: 10 }
const people = { p1: { av: 'v1', avatar: MINE, face: FACE }, p2: { avatar: MINE, face: FACE }, p3: { face: FACE }, p4: {},
  p5: { avatar: { v: 2, p: 'p05' }, face: FACE }, p6: { avatar: 'junk' }, p7: { avatar: { v: 1, p: 'p99' } }, p8: { avatar: { v: 1, p: 'p99' }, face: FACE } }
const on = { show: true, people }, off = { show: false, people }
out({
  all: shown(on, { pk: 'p1', name: 'A' }), picsOff: shown(off, { pk: 'p1', name: 'A' }), avatar: shown(on, { pk: 'p2', name: 'B' }),
  face: shown(on, { pk: 'p3', name: 'C' }), letter: shown(on, { pk: 'p4', name: 'D' }),
  newerVersion: shown(on, { pk: 'p5', name: 'E' }), junk: shown(on, { pk: 'p6', name: 'F' }),
  unknownId: shown(on, { pk: 'p7', name: 'G' }), unknownIdThenFace: shown(on, { pk: 'p8', name: 'H' }),
  lookalike: shown(on, { pk: 'p1', name: 'A', flagged: true }), lookalikeAvatar: shown(on, { pk: 'p2', name: 'B', flagged: true }),
  preview: shown(off, { pk: 'me', name: 'Me', art: { avatar: MINE } })
})
""")
    assert r["all"] == "photo" and r["picsOff"] == "avatar" and r["avatar"] == "avatar"
    assert r["face"] == "face" and r["letter"] == "letter"
    assert r["newerVersion"] == "face" and r["junk"] == "letter"       # an avatar this page can't read is skipped
    assert r["unknownId"] == "letter" and r["unknownIdThenFace"] == "face"   # an id this page lacks is never swapped for another portrait
    assert r["lookalike"] == r["lookalikeAvatar"] == "letter"          # a lookalike never wears someone's portrait
    assert r["preview"] == "avatar"


@needs_node
def test_the_portrait_is_an_image_that_is_described_only_when_asked():
    r = run(ART + """
const img = n => n.props.children
const plain = PersonAvatar({ avatar: { v: 1, p: 'p03' }, size: 24 }), told = PersonAvatar({ avatar: { v: 1, p: 'p03' }, size: 128, describe: true })
out({ plain: [plain.props.className, plain.props.style, img(plain).type, img(plain).props.alt, img(plain).props.src === PERSON_PRESETS[2].src],
      told: [img(told).props.alt, told.props['aria-hidden'], told.props.role], none: PersonAvatar({ avatar: { v: 1, p: 'p99' } }), none2: PersonAvatar({ avatar: null }) })
""")
    assert r["plain"] == ["h-pav", {"width": 24, "height": 24}, "img", "", True]       # beside a name: decoration, empty alt
    assert r["told"][0].startswith("Smiling woman with long black hair") and r["told"][1:] == [None, None]
    assert r["none"] is None and r["none2"] is None


def test_portraits_are_clipped_to_the_same_circle_as_other_avatars():
    assert ".h-pav{display:inline-grid;flex:none;border-radius:50%;overflow:hidden}" in STYLE
    assert ".h-pav img{display:block;width:100%;height:100%;object-fit:cover" in STYLE
    assert "jsx(PersonAvatar, { avatar: art.avatar, size, className: props.className })" in PARTS
    assert "jsx(PersonAvatar, { avatar: props.art.avatar, size: 120 })" in src("35_card.js")


def test_the_layered_person_builder_is_gone():


    assert not (UI / "15_person_art.js").exists()
    text = "".join(f.read_text() for f in UI.glob("*.js") if f.name != "05_media.js")
    for gone in ("AvatarEditor", "randomAvatar", "avSwatch", "AV_SKIN", "AV_HAIR", "AV_ART", "ToggleGrid", "avArt("):
        assert gone not in text, gone
    for gone in ("AV_SKIN", "AV_HAIR", "AV_ACCS", "AV_PICKS", "AV_DEFAULT"):
        assert not hasattr(engine, gone), gone


# --- the builders ------------------------------------------------------------------------------------------------------

BUILDER_JS = ART + fn(BUILDER, "OptionGrid") + fn(BUILDER, "LayerTabs") + """
// call a component once, outside a mounted tree (its hooks get a fresh slot each time)
const call = (C, p) => { cur = { hooks: [], i: 0, effects: [], schedule() {} }; return C(p) }
const keyDown = (node, key) => { let stopped = false; node.props.onKeyDown({ key, preventDefault() { stopped = true } }); return stopped }
"""


@needs_node
def test_option_grid_arrows_choose_within_a_layer_and_only_the_chosen_one_is_checked():
    r = run(BUILDER_JS + """
let value = 'b'; const got = []
const opts = ['a', 'b', 'c', 'd'].map(id => ({ id, label: id.toUpperCase(), render: () => null }))
const grid = v => call(OptionGrid, { label: 'L', options: opts, value: v, onChange: x => got.push(x) })
const g = grid('b')
const handled = ['ArrowRight', 'ArrowLeft', 'Home', 'End', 'Tab'].map(k => keyDown(g, k))
const radios = g.props.children.map(b => [b.props['aria-checked'], b.props.tabIndex, b.props['aria-label'], b.props.role])
const none = grid(999); keyDown(none, 'ArrowRight'); keyDown(grid('d'), 'ArrowRight'); keyDown(grid('a'), 'ArrowLeft')
out({ got, handled, radios, group: [g.props.role, g.props['aria-label']], noneChecked: none.props.children.map(b => b.props['aria-checked']),
      noneFocus: none.props.children.map(b => b.props.tabIndex) })
""")
    assert r["got"] == ["c", "a", "a", "d", "a", "a", "d"]       # right, left, home, end; then from nothing, wrap at both ends
    assert r["handled"] == [True, True, True, True, False]         # Tab leaves the group
    assert r["radios"] == [[False, -1, "A", "radio"], [True, 0, "B", "radio"], [False, -1, "C", "radio"], [False, -1, "D", "radio"]]
    assert r["group"] == ["radiogroup", "L"]
    assert r["noneChecked"] == [False] * 4 and r["noneFocus"] == [0, -1, -1, -1]   # a slider hue: no swatch claims it


@needs_node
def test_layer_tabs_follow_the_tabs_pattern():
    r = run(BUILDER_JS + """
const got = []
const layers = [{ key: 'sk', label: 'Skin' }, { key: 'hs', label: 'Hair' }, { key: 'fh', label: 'Facial hair' }]
const t = call(LayerTabs, { id: 'x', label: 'Avatar layers', layers, value: 'hs', onChange: k => got.push(k) })
;['ArrowRight', 'ArrowLeft', 'Home', 'End'].forEach(k => keyDown(t, k))
keyDown(call(LayerTabs, { id: 'x', label: 'A', layers, value: 'fh', onChange: k => got.push(k) }), 'ArrowRight')
out({ got, role: t.props.role, tabs: t.props.children.map(b => [b.props.role, b.props.id, b.props['aria-controls'], b.props['aria-selected'], b.props.tabIndex]) })
""")
    assert r["got"] == ["fh", "sk", "sk", "fh", "sk"]
    assert r["role"] == "tablist"
    assert r["tabs"][1] == ["tab", "x-tab-hs", "x-panel", True, 0] and r["tabs"][0][3:] == [False, -1]


PICKER_JS = BUILDER_JS + fn(BUILDER, "PresetPicker") + fn(BUILDER, "usePreviewPop") + """
function Initial() {}
"""


@needs_node
def test_the_picker_is_one_radio_group_of_every_portrait_labelled_from_its_alt_text():
    r = run(PICKER_JS + """
const changes = []
const pick = (value, extra) => call(PresetPicker, Object.assign({ value, name: 'Maya', onChange: a => changes.push(a) }, extra || {}))
const walk = (n, test, acc = []) => { if (n && typeof n === "object") { if (test(n)) acc.push(n); [].concat(n.props ? n.props.children : []).forEach(c => walk(c, test, acc)) } return acc }
const picker = pick({ v: 1, p: 'p09' })
const grid = walk(picker, n => n.type === OptionGrid)[0]
const radios = call(OptionGrid, grid.props)
const opts = radios.props.children
keyDown(radios, 'ArrowRight'); keyDown(radios, 'ArrowLeft'); keyDown(radios, 'Home'); keyDown(radios, 'End')
const unset = call(OptionGrid, walk(pick(null), n => n.type === OptionGrid)[0].props)
keyDown(unset, 'ArrowRight')
out({ n: opts.length, role: radios.props.role, label: radios.props['aria-label'], labels: opts.map(b => b.props['aria-label']), checked: opts.map(b => b.props['aria-checked']).indexOf(true),
      tab: opts.map(b => b.props.tabIndex).indexOf(0), changes,
      unsetChecked: unset.props.children.some(b => b.props['aria-checked']), unsetFocus: unset.props.children.map(b => b.props.tabIndex).indexOf(0) })
""")
    assert r["n"] == len(engine.AV_PRESETS) and r["role"] == "radiogroup" and r["label"] == "Portraits"
    alts = [x["alt"] for x in json.loads(PRESETS_JSON.read_text())]
    assert r["labels"] == alts                                                         # every option named by its alt text
    assert r["checked"] == 8 and r["tab"] == 8                                          # p09 is chosen and holds the tab stop
    assert r["changes"] == [{"v": 1, "p": "p10"}, {"v": 1, "p": "p08"}, {"v": 1, "p": "p01"}, {"v": 1, "p": engine.AV_PRESETS[-1]}, {"v": 1, "p": "p01"}]
    assert r["unsetChecked"] is False and r["unsetFocus"] == 0                          # with none chosen nothing is checked; the first is reachable


@needs_node
def test_the_picker_shows_the_initial_until_someone_picks_and_surprise_me_is_a_button_press():
    r = run(PICKER_JS + """
const walk = (n, test, acc = []) => { if (n && typeof n === "object") { if (test(n)) acc.push(n); [].concat(n.props ? n.props.children : []).forEach(c => walk(c, test, acc)) } return acc }
const changes = []
const none = call(PresetPicker, { value: null, name: 'Maya', onChange: a => changes.push(a) })
const set = call(PresetPicker, { value: { v: 1, p: 'p20' }, name: 'Maya', onChange: a => changes.push(a) })
const preview = t => walk(t, n => n.props && n.props.className === 'h-pp-preview')[0].props.children
const caption = t => walk(t, n => n.props && n.props.className && String(n.props.className).includes('h-pp-cap'))[0].props
const surprise = walk(set, n => n.props && n.props.children === 'Surprise me')[0]
const before = changes.length
surprise.props.onClick()
out({ noneChild: preview(none).props.children.type === Initial, noneCaption: caption(none).children, setPreview: preview(set).props.describe,
      setCaption: caption(set).children, silent: before === 0, changed: changes, live: caption(set)['aria-live'] })
""")
    assert r["noneChild"] and r["noneCaption"] == "No portrait chosen" and r["silent"]            # nothing is assigned by rendering
    assert r["setPreview"] is True and r["setCaption"].startswith("Smiling man with locs") and r["live"] == "polite"
    assert len(r["changed"]) == 1 and r["changed"][0]["v"] == 1 and r["changed"][0]["p"] in engine.AV_PRESETS and r["changed"][0]["p"] != "p20"


def test_onboarding_assigns_no_portrait_and_both_forms_use_the_picker():
    ob, st = fn(SETUP, "Onboarding"), fn(SETUP, "SettingsForm")
    assert "person_avatar: cleanAvatar(s.person_avatar)," in ob and "randomPreset" not in ob and "surprisePreset" not in ob
    assert "person_avatar: person_avatar || {}" in ob                      # what the preview showed is what goes out; none clears it
    assert "person_avatar: cleanAvatar(s.person_avatar)," in st
    look = fn(LOOK, "PersonLook")
    assert "jsx(PresetPicker," in look and "onAvatar(null)" in look and "Use my initial instead" in look and "Use a photo instead" in look
    assert "Surprise me" in fn(BUILDER, "PresetPicker")


def test_the_picker_wraps_on_narrow_pages_and_respects_reduced_motion():
    assert ".h-pp{display:flex;flex-wrap:wrap;" in STYLE and ".h-pp-grid{flex:1 1 260px;min-width:0;grid-template-columns:repeat(auto-fill,minmax(60px,1fr))" in STYLE
    assert ".h-pp-grid .h-bld-opt[data-on=true]{box-shadow:0 0 0 2px var(--h-accent)}" in STYLE
    assert "@container (max-width: 440px){.h-pp-side{flex-direction:row;" in STYLE
    assert ".h-bld-tabs button:focus-visible,.h-bld-opt:focus-visible{outline:2px solid var(--h-accent)" in STYLE      # focus is visible on every option
    assert "@media (prefers-reduced-motion: reduce){.h-bld-opt{transition:none}" in STYLE
    assert "if (!el || motion.reduced()) return" in fn(BUILDER, "usePreviewPop") and "usePreviewPop(" in fn(BUILDER, "PresetPicker")


def test_the_agent_builder_still_wraps_its_tabs():
    assert ".h-bld-tabs{display:flex;flex-wrap:wrap;" in STYLE
    assert ".h-bld-wrap{container-type:inline-size}" in STYLE and "@container (max-width: 440px)" in STYLE


# --- agent faces: still the same component ---------------------------------------------------------------------------------

def test_the_face_keeps_its_states_reactions_and_reduced_motion():
    face = fn(FACE, "Face")
    assert "pxAgentFrames(state, expr)" in face and "'data-state': state, 'data-expr': expr || undefined" in face
    assert "state === 'speaking' && !expr" in face and "art.blink &&" in face
    for anim in ("pf-blink-o", "pf-blink-c", "pf-talk-r", "pf-talk-t", "pf-bob", "pf-glance", "pf-scan", "pf-shake", "pf-hop"):
        assert "@keyframes " + anim + "{" in STYLE, anim
    assert "@media (prefers-reduced-motion: reduce){.hf *{animation:none!important" in STYLE and ".hf-still *{animation:none!important}" in STYLE
    assert ".pf-ec,.pf-mt{opacity:0}" in STYLE                     # with motion off, the open eyes and resting mouth show


@needs_node
def test_a_states_frames_pick_the_eyes_and_mouth_it_shows():
    r = run(ART + "out([['idle'], ['speaking'], ['waiting'], ['error'], ['absent'], ['idle', 'smug'], ['idle', 'caught'], ['idle', 'happy'], ['idle', 'wary'], ['idle', 'perk']].map(a => pxAgentFrames(a[0], a[1])))")
    assert r[0] == {"eyes": "open", "mouth": None} and r[3] == {"eyes": "x", "mouth": "frown"}
    assert [x["eyes"] for x in r[5:]] == ["half", "big", "happy", "wary", "big"]


# --- the card export --------------------------------------------------------------------------------------------------------

@needs_node
def test_the_card_export_uses_the_faces_own_view_box_and_refuses_anything_else():
    r = run(fn(CARDIMG, "faceBox") + "out(['0 0 64 64', '7 4 50 50', ' 14  16 36 36 ', '0 0 0 64', '0 0 64', 'a b c d', null, '0 0 64 64\"/><script>', '1e3 0 -5 5'].map(faceBox))")
    assert r == ["0 0 64 64", "7 4 50 50", "14 16 36 36", "0 0 64 64", "0 0 64 64", "0 0 64 64", "0 0 64 64", "0 0 64 64", "0 0 64 64"]
    assert "faceBox(f.vb)" in CARDIMG and "heroParts(o.faces" in CARDIMG and "heroParts(o.faces" in src("34_scanner.js") and 'viewBox="0 0 40 40"' not in CARDIMG


@needs_node
def test_the_card_export_embeds_a_portrait_by_id_only_and_keeps_photos_and_foreign_images_out():
    r = run(ART + const(CARDIMG, "FACE_SHAPES") + "".join(fn(CARDIMG, n) for n in ("faceMarkup", "faceBox", "heroParts")) + """
const HERO_CLIP = ''
const evil = 'data:image/webp;base64,EVIL'
const parts = heroParts([
  { preset: 'p05', left: 5, top: 5, size: 90, front: true },
  { preset: 'p99', left: 0, top: 0, size: 100, front: true },                        // an id the page doesn't ship
  { preset: 'p01', src: evil, inner: '<image href="' + evil + '"/>', left: 0, top: 0, size: 100 },   // a src or markup the card carries is never read
  { img: evil, left: 0, top: 0, size: 100 },
  { inner: '<path d="M0 0"/>', vb: '0 0 64 64', left: 0, top: 0, size: 100, front: true }
], 100, 200, 300, 'dim')
out({ n: parts.length, parts: parts.map(p => p.replace(/href="[^"]*"/, 'href=…')), href: parts.map(p => (p.match(/href="([^"]*)"/) || [])[1]),
      src: [PERSON_PRESETS[4].src, PERSON_PRESETS[0].src], none: heroParts([{ img: evil }], 0, 0, 100, 'd').length })
""")
    assert r["n"] == 3 and r["none"] == 0                                              # unknown id and a bare image drop out
    assert r["href"][2] == r["src"][0] and r["href"][1] == r["src"][1]                  # p05 (drawn last: first in the list is on top), p01 from the table
    assert not any("EVIL" in (h or "") for h in r["href"])                             # the card never gets a src it carried itself
    assert r["parts"][2].startswith('<image x="115" y="215" width="270" height="270"') and 'clip-path="url(#hpclip)"' in r["parts"][2]
    assert 'filter="url(#dim)"' in r["parts"][1] and 'filter="url(#dim)"' not in r["parts"][2]    # only the ones behind the front are dimmed
    assert "img[data-preset]" in CARDIMG and "HERO_CLIP" in src("34_scanner.js")
