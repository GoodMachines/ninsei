"""Pixel faces for agents and pixel avatars for people, run under node with the shared hooks harness: the renderer's
determinism and bounds, the avatar model's cleaning (the same as the engine's), who shows what (picture, avatar,
older face, initial), the builders' keyboard and Randomize/Reset, and the card export's view box."""
import json
import random
import re

from ninsei_engine import engine
from ninsei_engine.engine import clean_avatar
from test_audit_ui import PARTS, STYLE, fn, needs_node, run, src

PIXEL, MODEL, PERSON_ART, BUILDER, FACE, CARDIMG, LOOK, SETUP = (
    src(n) for n in ("12_pixel.js", "14_avatar.js", "15_person_art.js", "33_builder.js", "10_face.js", "36_cardimage.js",
                     "32_look.js", "40_setup.js"))

# everything the renderers need, and nothing else: the colour maths from the card export, then the two modules
ART = ("const cx = (...a) => a.filter(Boolean).join(' ')\n" + "".join(fn(CARDIMG, n) for n in ("rgbHex", "clamp01", "oklabToRgb", "oklchToHex"))
       + PIXEL + MODEL + PERSON_ART)
SHAPES = engine.FACE_SHAPES


def js_list(text, name):
    return json.loads(re.search(r"^const " + name + r" = (\[.*\])$", text, re.M).group(1).replace("'", '"'))


# --- the model: the page and the engine agree ---------------------------------------------------------------------------

def test_the_avatar_options_are_the_same_lists_on_the_page_and_in_the_engine():
    for name in ("AV_FACES", "AV_HAIR", "AV_HAIR_COLOURS", "AV_EYES", "AV_BROWS", "AV_MOUTHS", "AV_FACIAL", "AV_BUILDS", "AV_TOPS",
                 "AV_TOP_COLOURS", "AV_ACCS"):
        assert js_list(MODEL, name) == getattr(engine, name), name
    assert "const AV_SKIN = 10 " in MODEL and engine.AV_SKIN == 10
    assert "const AV_ACC_GROUPS = [['round-glasses', 'square-glasses'], ['beanie', 'headscarf']]" in MODEL
    assert engine.AV_ACC_GROUPS == [["round-glasses", "square-glasses"], ["beanie", "headscarf"]]


@needs_node
def test_the_page_cleans_an_avatar_exactly_as_the_engine_does():
    rng = random.Random(7)
    pool = {"sk": [0, 3, 9, 10, -1, 2.5, True, "3", None], "v": [1, 1, 1, 1, 2, "1", True, None, 0]}
    for key, opts in engine.AV_PICKS.items():
        pool[key] = opts + ["", "nope", 5, None, opts[0].upper()]
    accs = engine.AV_ACCS + ["cape", 3, None]
    cases = [None, [], "x", 5, {}, {"v": 1}, {"v": 2, "hs": "bun"}]
    for _ in range(300):
        c = {k: rng.choice(v) for k, v in pool.items() if rng.random() < 0.8}
        r = rng.random()
        c["ac"] = rng.sample(accs, rng.randint(0, 5)) if r < 0.7 else ("beanie" if r < 0.8 else accs * 3)
        if rng.random() < 0.2:
            c["extra"] = {"img": "data:"}
        cases.append(c)
    got = run(ART + "out(" + json.dumps(cases) + ".map(cleanAvatar))")
    assert got == [clean_avatar(c) for c in cases]
    assert run(ART + "out(AV_DEFAULT)") == clean_avatar({"v": 1})


@needs_node
def test_randomize_only_makes_clean_avatars_and_uses_every_option():
    r = run(ART + """
let seed = 1; const rand = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647 }
const all = Array.from({ length: 400 }, () => randomAvatar(rand))
out({ all, clean: all.every(a => JSON.stringify(cleanAvatar(a)) === JSON.stringify(a)) })
""")
    assert r["clean"]
    assert all(clean_avatar(a) == a for a in r["all"])
    seen = {k: {a[k] for a in r["all"]} for k in engine.AV_PICKS}
    assert all(seen[k] == set(v) for k, v in engine.AV_PICKS.items())
    assert {a["sk"] for a in r["all"]} == set(range(10))


# --- the renderer -------------------------------------------------------------------------------------------------------

DRAW_ALL = ART + """
const faces = []
for (const shape of %s) for (const acc of %s) for (const pattern of %s) faces.push({ shape, acc, pattern, eyes: 'round', mouth: 'smile', hue: 200, hue2: 30 })
for (const shape of %s) for (const eyes of %s) for (const mouth of %s) faces.push({ shape, eyes, mouth, acc: 'none', pattern: 'none', hue: 120, hue2: 300 })
const agents = faces.map(f => { const a = pxAgent(f, 'open'); return [a.base, a.eyes, a.blink, a.mouth, a.talk, a.acc, a.under] })
let seed = 3; const rand = () => { seed = (seed * 16807) %% 2147483647; return seed / 2147483647 }
const people = Array.from({ length: 60 }, () => avArt(randomAvatar(rand)).paths)
""" % (json.dumps(SHAPES), json.dumps(engine.FACE_ACCS), json.dumps(engine.FACE_PATTERNS), json.dumps(SHAPES),
       json.dumps(engine.FACE_EYES), json.dumps(engine.FACE_MOUTHS))


@needs_node
def test_the_same_settings_always_draw_the_same_pixels():
    js = DRAW_ALL + "out({ agents: require('crypto').createHash('sha256').update(JSON.stringify([agents, people])).digest('hex'), n: agents.length })"
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
const rle = pxRle('10:70a/3b')             // a row longer than the grid
const at = (grid, x, y) => grid[y * 64 + x] ? String.fromCharCode(grid[y * 64 + x]) : ''
out({ right: [at(g, 62, 0), at(g, 63, 0), at(g, 0, 1), at(g, 1, 1), at(g, 62, 1)], left: [at(g, 0, 5), at(g, 63, 4)],
      rle: [at(rle, 63, 10), at(rle, 0, 11), at(rle, 2, 11), at(rle, 3, 11)], count: g.filter(Boolean).length })
""")
    assert r["right"] == ["a", "a", "", "", "b"] and r["left"] == ["c", ""] and r["count"] == 5
    assert r["rle"] == ["a", "b", "b", ""]


def test_every_stored_hair_drawing_fits_the_grid_without_clipping():
    art = re.search(r"const AV_HAIR_ART = \{(.*?)\n\}", PERSON_ART, re.S).group(1)
    rows = dict(re.findall(r"^\s*'?([a-z]+)'?: '([^']*)',?$", art, re.M))
    assert set(rows) == set(engine.AV_HAIR) - {"buzz", "bald"}                    # buzz is drawn in code; bald has none
    for name, text in rows.items():
        top, body = text.split(":", 1)
        lines = body.split("/")
        assert int(top) >= 0 and int(top) + len(lines) <= 64, name
        for line in lines:
            assert sum(int(n or 1) for n, _ in re.findall(r"(\d*)(\D)", line)) <= 64, name
        assert re.fullmatch(r"[0-9.A-Za-z/]*", body), name                         # plain text: run lengths and slot letters


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
def test_a_picture_comes_first_then_the_pixel_avatar_then_an_older_face_then_the_initial():
    r = run(PERSON_MARK + """
globalThis.URIS = { ['p1:v1']: 'data:image/webp;base64,AAAA' }
const MINE = { v: 1, hs: 'bun' }, FACE = { hue: 10 }
const people = { p1: { av: 'v1', avatar: MINE, face: FACE }, p2: { avatar: MINE, face: FACE }, p3: { face: FACE }, p4: {},
  p5: { avatar: { v: 2, hs: 'bun' }, face: FACE }, p6: { avatar: 'junk' } }
const on = { show: true, people }, off = { show: false, people }
out({
  all: shown(on, { pk: 'p1', name: 'A' }), picsOff: shown(off, { pk: 'p1', name: 'A' }), avatar: shown(on, { pk: 'p2', name: 'B' }),
  face: shown(on, { pk: 'p3', name: 'C' }), letter: shown(on, { pk: 'p4', name: 'D' }),
  newerVersion: shown(on, { pk: 'p5', name: 'E' }), junk: shown(on, { pk: 'p6', name: 'F' }),
  lookalike: shown(on, { pk: 'p1', name: 'A', flagged: true }), lookalikeAvatar: shown(on, { pk: 'p2', name: 'B', flagged: true }),
  preview: shown(off, { pk: 'me', name: 'Me', art: { avatar: MINE } })
})
""")
    assert r["all"] == "photo" and r["picsOff"] == "avatar" and r["avatar"] == "avatar"
    assert r["face"] == "face" and r["letter"] == "letter"
    assert r["newerVersion"] == "face" and r["junk"] == "letter"       # an avatar this page can't read is skipped
    assert r["lookalike"] == r["lookalikeAvatar"] == "letter"          # a lookalike never wears someone's avatar
    assert r["preview"] == "avatar"


@needs_node
def test_the_avatar_drawing_is_labelled_only_when_asked_and_comes_closer_when_small():
    r = run(ART + """
const svg = n => n.props.children
const small = PersonAvatar({ avatar: { v: 1 }, size: 24 }), big = PersonAvatar({ avatar: { v: 1 }, size: 128, label: 'Maya’s avatar' })
const crop = PersonAvatar({ avatar: { v: 1 }, size: 64, view: AV_ART.views.face })
out({ small: [svg(small).props.viewBox, small.props['aria-hidden'], small.props.role], big: [svg(big).props.viewBox, big.props['aria-label'], big.props.role],
      crop: svg(crop).props.viewBox, none: svg(PersonAvatar({ avatar: null, size: 128 })).props.children.length })
""")
    assert r["small"] == ["7 4 50 50", True, None] and r["big"] == ["0 0 64 64", "Maya’s avatar", "img"]
    assert r["crop"] == "14 16 36 36" and r["none"] == 4


def test_the_person_renderer_is_one_module_behind_a_small_interface():
    # the editor reaches the drawing only through PersonAvatar, AV_ART and avSwatch, so the art can be replaced
    for name in ("AV_SKIN_TONES", "AV_HAIR_TONES", "AV_TOP_TONES", "avGrid", "avArt", "AV_HAIR_ART", "AV_INK"):
        assert name not in BUILDER and name not in PARTS and name not in LOOK and name not in SETUP, name
        assert name not in MODEL, name
    assert "AV_ART.views.face" in BUILDER and "avSwatch('sk', k)" in BUILDER
    assert "function PersonAvatar(" in PERSON_ART and "function cleanAvatar(" in MODEL and "function cleanAvatar(" not in PERSON_ART


# --- the builders ------------------------------------------------------------------------------------------------------

BUILDER_JS = ART + fn(BUILDER, "OptionGrid") + fn(BUILDER, "ToggleGrid") + fn(BUILDER, "LayerTabs") + """
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


@needs_node
def test_extras_are_toggles_and_one_of_a_kind_replaces_the_other():
    r = run(BUILDER_JS + fn(BUILDER, "AvatarEditor") + fn(BUILDER, "avOptLabel") + fn(BUILDER, "BuilderShell") + fn(BUILDER, "usePreviewPop") + """
const AV_FACE_VIEW = AV_ART.views.face
""" + re.search(r"^const AV_LABEL = \{.*?^\}\n", BUILDER, re.S | re.M).group(0) + re.search(r"^const AV_LAYERS = \[.*?^\]\n", BUILDER, re.S | re.M).group(0) + """
let tabSet = null
function useState(v) { return ['ac', x => { tabSet = x }] }
const changes = []
const ed = AvatarEditor({ value: { v: 1, ac: ['headscarf', 'earrings'] }, onChange: a => changes.push(a), name: 'Maya' })
const shell = ed.props
const toggles = shell.panel
toggles.props.onToggle('beanie'); toggles.props.onToggle('earrings'); toggles.props.onToggle('round-glasses')
const pressed = toggles.props.value
shell.actions[1].props.onClick()
out({ changes, pressed, kinds: [toggles.type === ToggleGrid, shell.layers.map(l => l.label)], labels: toggles.props.options.map(o => o.label) })
""")
    beanie, earrings_off, glasses, reset = r["changes"]
    assert beanie["ac"] == ["earrings", "beanie"]            # the headscarf comes off when the beanie goes on
    assert earrings_off["ac"] == ["headscarf"] and glasses["ac"] == ["round-glasses", "earrings", "headscarf"]
    assert reset == clean_avatar({"v": 1}) and r["pressed"] == ["earrings", "headscarf"]
    assert r["kinds"][0] and "Facial hair" in r["kinds"][1] and "Round glasses" in r["labels"]


def test_onboarding_starts_from_a_random_avatar_that_is_saved_and_settings_never_makes_one_up():
    ob, st = fn(SETUP, "Onboarding"), fn(SETUP, "SettingsForm")
    assert "person_avatar: cleanAvatar(s.person_avatar) || (s.person_face ? null : randomAvatar())" in ob
    assert "person_avatar: person_avatar || {}" in ob                      # what the preview showed is what goes out
    assert "randomAvatar" not in st and "person_avatar: cleanAvatar(s.person_avatar)," in st
    assert "onAvatar(null)" in fn(LOOK, "PersonLook") and "Use my initial instead" in fn(LOOK, "PersonLook")
    assert "Use a photo instead" in fn(LOOK, "PersonLook")


def test_the_builders_wrap_their_tabs_and_respect_reduced_motion():
    assert ".h-bld-tabs{display:flex;flex-wrap:wrap;" in STYLE
    assert ".h-bld-wrap{container-type:inline-size}" in STYLE and "@container (max-width: 440px)" in STYLE
    assert "@media (prefers-reduced-motion: reduce){.h-bld-opt{transition:none}" in STYLE
    assert "if (!el || motion.reduced()) return" in fn(BUILDER, "usePreviewPop")
    assert ".h-bld-tabs button:focus-visible,.h-bld-opt:focus-visible{outline:2px solid var(--h-accent)" in STYLE


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
    assert "faceBox(f.vb)" in CARDIMG and "faceBox(f.vb)" in src("34_scanner.js") and 'viewBox="0 0 40 40"' not in CARDIMG
