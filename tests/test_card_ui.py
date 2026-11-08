"""Card visuals: the card number and name sizing helpers in ui/35_card.js, run through node, plus
source checks that the pointer tilt respects reduced motion and ignores touch."""
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
CARD = (ROOT / "ui" / "35_card.js").read_text()

needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def _fn(src: str, name: str) -> str:
    """One top-level function's source, from `function name(` to its closing brace."""
    start = src.index("function " + name + "(")
    return src[start:src.index("\n}\n", start) + 3]


def _const(src: str, name: str) -> str:
    m = re.search(r"^const " + name + r" = .*$", src, re.M)
    return m.group(0) + "\n"


def _run(js: str, tz: str = "UTC"):
    out = subprocess.run([NODE, "-e", js], capture_output=True, text=True, check=True, env={**os.environ, "TZ": tz})
    return json.loads(out.stdout)


@needs_node
def test_card_serial_is_the_start_of_the_key():
    js = _fn(CARD, "cardSerial") + """
const pk = '3f2a9c1b77e0' + 'ab'.repeat(26)
console.log(JSON.stringify([cardSerial(pk), cardSerial(pk.toUpperCase()), cardSerial('3F2A9C1B77E0'),
  cardSerial(null), cardSerial(undefined), cardSerial(''), cardSerial('3f2a9c1b77e'), cardSerial('zz2a9c1b77e0' + 'ab'.repeat(26)),
  cardSerial('3f2a9c1b77e0<b>'), cardSerial(' 3f2a9c1b77e0'), cardSerial(123456789012345), cardSerial(['3f2a9c1b77e0']),
  cardSerial({ toString() { return '3f2a9c1b77e0' } })]))"""
    out = _run(js)
    assert out[:3] == ["3F2A·9C1B·77E0"] * 3
    assert out[3:] == [""] * 10


@needs_node
def test_key_groups_split_a_whole_key_only():
    js = _fn(CARD, "keyGroups") + """
const pk = '0123456789abcdef'.repeat(4)
console.log(JSON.stringify([keyGroups(pk), keyGroups(pk.slice(1)), keyGroups(pk + '0'), keyGroups(null), keyGroups('g'.repeat(64))]))"""
    whole, short, long_, none, bad = _run(js)
    assert whole == ["0123456789ABCDEF"] * 4
    assert short == long_ == none == bad == []


@needs_node
def test_name_size_steps_down_for_long_names():
    longest = "x" * 32  # _name_ok in ninsei_engine/engine.py caps names at 32 characters
    js = _fn(CARD, "nameSize") + f"""
console.log(JSON.stringify([nameSize('Ada'), nameSize('Twelve Chars'), nameSize('Thirteen char'), nameSize('Alexandrinaa'),
  nameSize('a b c d e f g h i j k'), nameSize('{longest}'), nameSize('Wolfeschlegelstein'), nameSize(null), nameSize(undefined),
  nameSize(''), nameSize(42), nameSize({{}}), nameSize('   Ada   '), nameSize('😀'.repeat(12)), nameSize('😀'.repeat(13))]))"""
    out = _run(js)
    assert out == ["l", "l", "m", "m", "s", "s", "s", "l", "l", "l", "l", "m", "l", "m", "s"]


def test_the_engine_name_limit_is_what_the_card_was_sized_for():
    from ninsei_engine.engine import _name_ok
    assert len(_name_ok("x" * 100, "?")) == 32


@needs_node
def test_activity_reads_engine_fields_and_ignores_junk():
    src = _const(CARD, "DAY_NAMES") + _const(CARD, "MONTH_NAMES") + _fn(CARD, "fmtDay") + _fn(CARD, "postCount") + _fn(CARD, "activityText")
    js = src + """
const ts = Date.UTC(new Date().getUTCFullYear(), 10, 6, 12) / 1000
console.log(JSON.stringify([activityText(ts, 42), activityText(ts, 1), activityText(null, 0), activityText(null, null),
  activityText(undefined, undefined), activityText('1700000000', '5'), activityText(-1, 2.5), activityText(NaN, -3),
  fmtDay(Date.UTC(2020, 0, 1, 12) / 1000), fmtDay(1e20)]))"""
    out = _run(js)
    assert out[0].startswith("First seen here ") and out[0].endswith(" 6 Nov. 42 messages here.")
    assert out[1].endswith("1 message here.")
    assert out[2] == "0 messages here."
    assert out[3:8] == [""] * 5
    assert out[8] == "Wed 1 Jan 2020"
    assert out[9] == ""


def test_tilt_respects_reduced_motion_and_ignores_touch():
    tilt = _fn(CARD, "useCardTilt")
    assert "motion.reduced()" in tilt
    assert "e.pointerType === 'touch'" in tilt
    # every listener added is removed, and the springs stop, on unmount
    for ev in ("pointermove", "pointerleave", "pointercancel"):
        assert "addEventListener('" + ev in tilt and "removeEventListener('" + ev in tilt
    assert "sx.stop()" in tilt and "sy.stop()" in tilt and "glow.stop()" in tilt
    assert "useState" not in tilt  # springs write to the DOM, never React state


def test_flip_is_accessible_and_the_back_is_hidden_from_screen_readers():
    card = _fn(CARD, "IdCard")
    assert "role: interactive ? 'button'" in card and "'aria-pressed': interactive ? flipped" in card
    assert "e.key === 'Enter' || e.key === ' '" in card
    assert "className: 'h-idcard h-idcard-back', 'aria-hidden': true" in card
    assert "'Flip card'" in _fn(CARD, "ProfileSheet")
    # the Settings and onboarding previews stay non-interactive
    setup = (ROOT / "ui" / "40_setup.js").read_text()
    assert setup.count("jsx(IdCard,") == 2 and "interactive" not in setup


def test_card_number_copy_never_claims_proof():
    for fn in ("agentSheet", "personSheet", "cardNumberRow"):
        text = _fn(CARD, fn).lower()
        assert "prove" not in text and "verified" not in text and "guarantee" not in text


def test_card_number_is_a_label_not_proof_and_points_to_the_full_key():
    # 12 hex characters (48 bits) can be ground to match a target's, so the copy must never invite
    # a check on the number alone: it names the number a label and sends people to the full key
    row = _fn(CARD, "cardNumberRow")
    assert "is short for" in row and "compare the full key on the back of the card" in row
    for fn in ("agentSheet", "personSheet"):
        text = _fn(CARD, fn)
        assert "Read it to a friend" not in text and "start of" not in text and "Ask the owner to compare" not in text
    assert "—" not in row


def test_holding_enter_or_space_flips_the_card_once():
    card = _fn(CARD, "IdCard")
    assert "e.repeat" in card and "if (!e.repeat) flip()" in card


def test_the_full_key_can_be_copied_from_the_sheet():
    # the card's stage is user-select:none (a click turns it), so a button is the way to copy the key
    row = _fn(CARD, "cardNumberRow")
    assert "P.copy(" in row and "'Copy key'" in row and "groups.length ?" in row
    style = (ROOT / "ui" / "20_style.js").read_text()
    assert "h-idcard-stage[data-interactive=true]{cursor:pointer;-webkit-user-select:none;user-select:none}" in style


# ---- card images and card actions (ui/36_cardimage.js, cardActions in ui/35_card.js) ----------------

IMAGE = (ROOT / "ui" / "36_cardimage.js").read_text()
# the whole image file runs in node: it only declares functions and constants (the page's DOM is touched
# only when a function is called); nameSize comes from the card file
IMAGE_JS = _fn(CARD, "nameSize") + IMAGE

HOSTILE = "</text><script>alert(1)</script>&\"'"
SVG_NS = "{http://www.w3.org/2000/svg}"


def _svg(opts_js: str) -> str:
    return _run(IMAGE_JS + f"console.log(JSON.stringify(cardSvg({opts_js})))")


@needs_node
def test_oklch_to_hex_matches_the_browsers_own_conversion():
    js = IMAGE_JS + """
console.log(JSON.stringify([oklchToHex(1, 0, 0), oklchToHex(0, 0, 0), oklchToHex(0.5, 0, 0), oklchToHex(0.6, 0.19, 28),
  oklchToHex(0.4, 0.2, 260), oklchToHex(0.96, 0.07, 200), oklchToHex(0.7, 0.15, 150),
  oklchToHex(0.9, 0.4, 320), oklchToHex(5, 5, 90), oklchToHex(-2, 0.3, 10), oklchToHex(0.6, -0.2, 400),
  oklchToHex(NaN, 0.1, 10), oklchToHex(undefined, undefined, undefined), oklchToHex('x', 'y', 'z'), oklchToHex(0.6, 0.1, Infinity)]))"""
    out = _run(js)
    # the first eight are what Chrome gives for the same oklch() (checked in a browser)
    assert out[:8] == ["#ffffff", "#000000", "#636363", "#da4339", "#0038b0", "#baffff", "#4cb86a", "#ff47ff"]
    # out-of-gamut and nonsense input still gives a valid colour
    assert out[9] == "#000000" and out[11] == "#000000"
    assert all(re.fullmatch(r"#[0-9a-f]{6}", c) for c in out)


@needs_node
def test_css_color_reads_what_browsers_hand_back():
    js = IMAGE_JS + """
console.log(JSON.stringify([cssColor('oklch(0.94 0.045 28)'), cssColor('oklch(94% 0.045 28 / 50%)'), cssColor('rgb(10, 20, 30)'),
  cssColor('rgba(10, 20, 30, 0.25)'), cssColor('color(srgb 0.5 0.25 1 / 0.5)'), cssColor('#fa0'), cssColor('#11223380'),
  cssColor('none'), cssColor(''), cssColor(null), cssColor('url(#x)'), cssColor('red'), cssColor('rgb(a b c)')]))"""
    out = _run(js)
    assert out[0] == {"hex": "#ffe1db", "a": 1}
    assert out[1] == {"hex": "#ffe1db", "a": 0.5}
    assert out[2] == {"hex": "#0a141e", "a": 1}
    assert out[3] == {"hex": "#0a141e", "a": 0.25}
    assert out[4] == {"hex": "#8040ff", "a": 0.5}
    assert out[5] == {"hex": "#ffaa00", "a": 1}
    assert out[6]["hex"] == "#112233" and abs(out[6]["a"] - 0.502) < 0.01
    assert out[7:] == [None] * 6


@needs_node
def test_card_svg_with_hostile_text_is_well_formed_and_inert():
    face = '<g style="fill:#fff"><circle cx="20" cy="20" r="10" style="fill:#fff;stroke:none"/></g>'
    svg = _svg("{ hue: 28, hue2: 200, name: %s, tag: 'Agent', serial: '3F2A·9C1B·77E0', fields: [['Owner', %s], ['Model', %s, true]], faces: [{ inner: %s, left: 0, top: 0, size: 100, front: true }] }"
               % (json.dumps(HOSTILE), json.dumps("<b onload=x>&Co"), json.dumps("a\"><img src=x onerror=alert(2)>'&"), json.dumps(face)))
    root = ET.fromstring(svg)  # well-formed XML, or this raises
    assert root.tag == SVG_NS + "svg" and root.get("width") == "1200" and root.get("height") == "750"
    assert "<script" not in svg.lower() and "foreignobject" not in svg.lower()
    # the only absolute URL is the namespace
    assert "http" not in svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
    for el in root.iter():
        for attr, value in el.attrib.items():
            assert not attr.lower().startswith("on"), attr
            assert "href" not in attr.lower()
            assert not re.search(r"url\((?!#)", value)
        assert el.tag.replace(SVG_NS, "") in {"svg", "defs", "g", "rect", "circle", "path", "text", "radialGradient", "linearGradient", "stop", "pattern",
                                              "mask", "filter", "clipPath", "feDropShadow", "feComponentTransfer", "feFuncR", "feFuncG", "feFuncB", "feColorMatrix"}
    # the hostile text is there, as text: escaped in the markup, upper-cased like the card's CSS does
    assert "&lt;/TEXT&gt;&lt;SCRIPT" in svg
    texts = [t.text for t in root.iter(SVG_NS + "text")]
    assert any(t and t.startswith("</TEXT><SCRIPT") for t in texts)
    assert "&lt;B ONLOAD=X&gt;" in svg
    assert any(t and t.startswith('A"><IMG') for t in texts)
    assert root.find(".//" + SVG_NS + "circle[@r='10']") is not None  # the face made it in


@needs_node
def test_card_svg_refuses_faces_that_are_not_plain_shapes():
    bad = ["<script>alert(1)</script>", "<g onclick=\"x()\"><circle r=\"1\"/></g>", "<foreignObject><div/></foreignObject>",
           "<image href=\"https://example.com/a.png\"/>", "<use xlink:href=\"#a\"/>", "<circle r=\"1\" style=\"fill:url(https://e.com/x)\"/>",
           "<circle r=\"1\" style=\"fill:url(//e.com/x)\"/>", "<style>@import 'x'</style>", "<a href=\"javascript:alert(1)\"><circle r=\"1\"/></a>",
           "<circle r=\"1\"><animate attributeName=\"r\"/></circle>", "", None, 42]
    ok = '<circle cx="1" cy="1" r="1" style="fill:url(#ncbg)"/>'
    js = IMAGE_JS + f"""
const bad = {json.dumps(bad)}
const marks = bad.map((m, i) => cardSvg({{ hue: 10, name: 'A', tag: 'Agent', faces: [{{ inner: m, left: 0, top: 0, size: 100, front: true }}] }}).includes('viewBox="0 0 64 64"'))
const good = cardSvg({{ hue: 10, name: 'A', tag: 'Agent', faces: [{{ inner: {json.dumps(ok)}, left: 0, top: 0, size: 100, front: true }}] }}).includes('viewBox="0 0 64 64"')
console.log(JSON.stringify([marks, good, faceMarkup('<g xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></g>')]))"""
    marks, good, cleaned = _run(js)
    assert marks == [False] * len(bad)
    assert good is True
    assert cleaned == "<g><path d=\"M0 0\"/></g>"  # the namespace is stripped, the shapes stay


@needs_node
def test_card_svg_copes_with_odd_input():
    odd = "\u0000\u0007bad\ud800 name \n\t" + "x" * 500
    for opts in ("{}", "{ name: %s, tag: %s, fields: [[%s, %s]], serial: %s }" % ((json.dumps(odd),) * 5),
                 "{ hue: 'x', name: null, fields: [null, ['a'], ['b', null], ['c', 'd']], faces: 'nope' }",
                 "{ name: 'Ada', initial: '\\ud83d', hue: 1e9 }", "{ name: 'Ada', initial: 'A', measure: () => NaN }"):
        svg = _svg(opts)
        ET.fromstring(svg)
        assert len(svg) < 60000  # long names are cut, not drawn in full
    # the initial is drawn when there are no faces
    assert ">A</text>" in _svg("{ name: 'Ada', initial: 'A', hue: 20 }")


@needs_node
def test_card_text_wraps_in_two_lines_and_never_overflows():
    js = IMAGE_JS + """
const w = s => Array.from(s).length * 10
console.log(JSON.stringify([wrapLines('ADA LOVELACE', 100, 2, w), wrapLines('THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG', 100, 2, w),
  wrapLines('X'.repeat(35), 100, 2, w), wrapLines('', 100, 2, w), wrapLines('   ', 100, 2, w), fitText('SHORT', 100, w), fitText('A'.repeat(30), 100, w),
  wrapLines('😀'.repeat(30), 100, 2, w)]))"""
    out = _run(js)
    assert out[0] == ["ADA", "LOVELACE"]
    for lines in (out[1], out[2], out[7]):
        assert len(lines) == 2 and lines[-1].endswith("…")
        assert all(len(list(line)) <= 10 for line in lines)
    assert out[3] == out[4] == [""]
    assert out[5] == "SHORT" and out[6].endswith("…") and len(out[6]) <= 10


@needs_node
def test_card_filename_is_lowercase_letters_digits_and_hyphens():
    js = IMAGE_JS + """
console.log(JSON.stringify([cardFilename('Ada'), cardFilename('Ada Lovelace'), cardFilename('Zoë  O\\'Neil!'), cardFilename('../../etc/passwd'),
  cardFilename(''), cardFilename(null), cardFilename('日本語'), cardFilename('x'.repeat(100)), cardFilename('<b>&"')]))"""
    out = _run(js)
    assert out[:4] == ["ninsei-ada-card.png", "ninsei-ada-lovelace-card.png", "ninsei-zoe-o-neil-card.png", "ninsei-etc-passwd-card.png"]
    assert out[4] == out[5] == out[6] == "ninsei-card-card.png"
    assert out[7] == "ninsei-" + "x" * 40 + "-card.png"
    assert all(re.fullmatch(r"ninsei-[a-z0-9-]+-card\.png", n) for n in out)


@needs_node
def test_card_actions_offer_edit_on_your_own_agent_and_hide_only_on_others():
    js = _fn(CARD, "cardActions") + """
const ME = 'a'.repeat(64), MYAGENT = 'b'.repeat(64), OTHER = 'c'.repeat(64), THEIRAGENT = 'd'.repeat(64)
const snap = { me: { pk: ME, agent: { pk: MYAGENT } } }
const owner = { pk: OTHER, name: 'Sam' }
const r = [
  cardActions({ kind: 'agent', pk: MYAGENT }, { agent: { pk: MYAGENT, yours: true }, owner: { pk: ME, name: 'Me', you: true } }, snap),
  cardActions({ kind: 'agent', pk: MYAGENT }, {}, snap),
  cardActions({ kind: 'agent', pk: THEIRAGENT }, { agent: { pk: THEIRAGENT }, owner }, snap),
  cardActions({ kind: 'agent', pk: THEIRAGENT }, { agent: { pk: THEIRAGENT } }, snap),
  cardActions({ kind: 'agent', pk: THEIRAGENT }, { agent: { pk: THEIRAGENT }, owner: { pk: ME, name: 'Me', you: true } }, snap),
  cardActions({ kind: 'person', pk: ME, name: 'Me' }, { person: { pk: ME, name: 'Me', you: true } }, snap),
  cardActions({ kind: 'person', pk: ME, name: 'Me' }, {}, snap),
  cardActions({ kind: 'person', pk: OTHER, name: 'Sam' }, { person: { pk: OTHER, name: 'Sam' } }, snap),
  cardActions({ kind: 'person', pk: OTHER, name: 'Sam' }, {}, snap),
  cardActions({ kind: 'person', pk: 7, name: 'Sam' }, {}, snap),
  cardActions({ kind: 'person', pk: OTHER }, {}, { me: null })
]
console.log(JSON.stringify(r))"""
    out = _run(js)
    sam = {"pk": "c" * 64, "name": "Sam"}
    # `message` (private message) goes where `hide` does: to a person, or an agent's owner; never to yourself
    assert out[0] == {"edit": True, "hide": None, "message": None}
    assert out[1] == {"edit": True, "hide": None, "message": None}
    assert out[2] == {"edit": False, "hide": sam, "message": sam}
    assert out[3] == {"edit": False, "hide": None, "message": None}  # owner unknown: no hide on an agent card
    assert out[4] == {"edit": False, "hide": None, "message": None}
    assert out[5] == out[6] == {"edit": False, "hide": None, "message": None}  # never on your own person card
    assert out[7] == out[8] == {"edit": False, "hide": sam, "message": sam}
    assert out[9] == {"edit": False, "hide": None, "message": None}
    assert out[10]["hide"] == {"pk": "c" * 64, "name": "them"} and out[10]["message"] == out[10]["hide"]


def test_actions_hide_the_way_the_people_column_does():
    sheet = _fn(CARD, "ProfileSheet")
    room = (ROOT / "ui" / "50_room.js").read_text()
    assert "'/people/hide', { pk: act.hide.pk, name: act.hide.name }" in sheet
    assert "'Hid ' + act.hide.name + ' and their agent. Undo in Settings.'" in sheet
    assert "'/people/hide', { pk: p.pk, name: p.name }, 'Hid ' + p.name + ' and their agent. Undo in Settings.'" in room
    # the buttons are the sheet's, and the layer gets what it needs from the App
    app = (ROOT / "ui" / "80_app.js").read_text()
    assert "jsx(ProfileLayer, { room: showRoom ? room : null, snap, store, openSettings," in app
    assert "if (P.kind === 'dashboard') go('settings'); else P.openSettings()" in app
    assert "P.kind === 'dashboard'" in app and "P.openSettings()" in app


def test_edit_face_focuses_the_face_editor_in_settings():
    sheet = _fn(CARD, "ProfileSheet")
    assert "wantFaceEditor()" in sheet and "props.onClose()" in sheet and "props.openSettings" in sheet
    setup = (ROOT / "ui" / "40_setup.js").read_text()
    assert "useFaceEditorFocus()" in setup and "id: 'h-facepicker'" in setup
    parts = (ROOT / "ui" / "30_parts.js").read_text()
    assert "getElementById('h-facepicker')" in parts and "motion.reduced()" in parts


def test_both_platforms_can_save_a_file():
    for tail in ("desktop_tail.js", "dashboard_tail.js"):
        src = (ROOT / "ui" / "platform" / tail).read_text()
        assert re.search(r"^\s*saveFile\b", src, re.M), tail
    save = _fn(IMAGE, "anchorSave")
    assert "createObjectURL" in save and "a.download = filename" in save and "revokeObjectURL" in save


def test_card_image_code_stays_inside_the_lint_and_the_rules():
    banned = "<" + "script"
    for path in ("ui/36_cardimage.js", "ui/35_card.js", "desktop/plugin.js", "dashboard/dist/index.js"):
        assert banned not in (ROOT / path).read_text().lower(), path
    # no network, no foreign objects and no external references anywhere in the picture code
    for needle in ("fetch(", "XMLHttpRequest", "foreignObject", "innerHTML", "<image", "xlink:href"):
        assert needle not in IMAGE, needle
    assert IMAGE.count("http") == 1 and "http://www.w3.org/2000/svg" in IMAGE  # the SVG namespace, nothing else
    # the picture is built from the same model the card renders from
    assert "cardModel(props)" in _fn(CARD, "IdCard") and "cardModel(props)" in _fn(IMAGE, "cardImage")
