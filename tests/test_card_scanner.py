"""The Scanner card style: the choice rides with the face (cleaned on both sides, junk reads as the Member
card), the nebula is a pure function of the key, the drift loop respects reduced motion and stops, and the
saved image of a Scanner card is as inert as the Member one."""
import asyncio
import base64
import json
import re
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

import pytest

from ninsei_engine import engine as eng_mod
from ninsei_engine.engine import Engine, clean_face

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

CORE = (ROOT / "ui" / "00_core.js").read_text()
SCANNER = (ROOT / "ui" / "34_scanner.js").read_text()
CARD = (ROOT / "ui" / "35_card.js").read_text()
IMAGE = (ROOT / "ui" / "36_cardimage.js").read_text()
SVG_NS = "{http://www.w3.org/2000/svg}"
HOSTILE = "</text><script>alert(1)</script>&\"'"


def _fn(src: str, name: str) -> str:
    start = src.index("function " + name + "(")
    return src[start:src.index("\n}\n", start) + 3]


def _js_list(src: str, name: str) -> list:
    m = re.search(r"const " + name + r" = (\[[^\]]*\])", src)
    return json.loads(m.group(1).replace("'", '"'))


# the core's option lists and faceFor, the card's nameSize, then the whole scanner and image files: they only
# declare functions and constants, so they run in node (the DOM is touched only when a function is called)
JS = (CORE[CORE.index("const SHAPES"):CORE.index("const BUDGET_PRESETS")] + _fn(CORE, "clamp") + _fn(CORE, "stateWord") + _fn(CORE, "faceFor")
      + _fn(CARD, "nameSize") + SCANNER + IMAGE)


def _run(js: str):
    out = subprocess.run([NODE, "-e", JS + js], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _png() -> str:
    """A real 1x1 PNG as a data URL, like the one the page's canvas makes."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(b"\x00\x10\x20\x40")) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(raw).decode()


# ---- the choice travels with the face ------------------------------------------------------------

def test_card_options_match_between_engine_and_ui():
    assert _js_list(CORE, "FACE_CARDS") == eng_mod.FACE_CARDS == ["member", "scanner"]
    # the face editor offers exactly these, and Member stays the default (first)
    parts = (ROOT / "ui" / "30_parts.js").read_text()
    assert "FACE_CARDS.map(o =>" in parts and "onClick: () => set({ card: o })" in parts


@pytest.mark.parametrize("bad", ["SCANNER", "Scanner ", "<script>", "javascript:", 5, None, ["scanner"], {"scanner": 1}, "", "holo"])
def test_clean_face_turns_junk_into_the_member_card(bad):
    assert clean_face({"hue": 10, "card": bad})["card"] == "member"


def test_clean_face_keeps_the_scanner():
    assert clean_face({"hue": 10, "card": "scanner"})["card"] == "scanner"
    assert clean_face({"card": "member"})["card"] == "member"
    assert clean_face(None)["card"] == "member"


def test_the_style_is_saved_and_older_faces_gain_the_default(tmp_path):
    e = Engine(tmp_path / "e", lambda: None, relays=[], lock=False)
    assert e.settings()["face"]["card"] == "member"
    assert e.save_settings({"face": {"hue": 200, "shape": "tall", "card": "scanner"}})["face"]["card"] == "scanner"
    assert e.settings()["face"]["card"] == "scanner"
    # a face stored before the key existed reads as the Member card
    stored = e.store.get("settings")
    stored["face"] = {"hue": 200, "shape": "tall", "eyes": "dot", "mouth": "smile", "acc": "none", "pattern": "none", "hue2": 350}
    e.store.set("settings", stored)
    assert e.settings()["face"]["card"] == "member" and e.settings()["face"]["shape"] == "tall"
    assert e.save_settings({"face": {"hue": 1, "card": "<b>"}})["face"]["card"] == "member"


async def test_a_published_face_carries_the_card_style(tmp_path, monkeypatch):
    e = Engine(tmp_path / "e", lambda: None, relays=[], lock=False)
    e.save_settings({"onboarded": True, "agent_name": "Ada", "face": {"hue": 255, "shape": "soft", "card": "scanner"}})
    sent = []

    class Pool:
        async def publish(self, ev, wait=None):
            sent.append(json.loads(ev["content"]))
    e.pool = Pool()
    monkeypatch.setattr(e.store, "rooms", lambda: {"ab" * 8: {}})
    await e._presence_once()
    await asyncio.sleep(0)
    assert sent and sent[-1]["t"] == "presence" and sent[-1]["face"]["card"] == "scanner"
    # and the snapshot the UI reads has it too
    assert e.settings()["face"]["card"] == "scanner"


def test_a_received_face_keeps_its_style_until_the_ui_cleans_it(tmp_path):
    from ninsei_engine import nostr
    e = Engine(tmp_path / "e", lambda: None, relays=[], lock=False)
    room = "cd" * 8
    owner_sk, agent_sk = nostr.new_secret(), nostr.new_secret()
    owner_pk = nostr.pubkey(owner_sk)
    agent_pk = nostr.pubkey(agent_sk)
    for card in ("scanner", "<img src=x onerror=alert(1)>"):
        content = {"t": "presence", "name": "Bo", "state": "activity: idle", "at": 0, "face": {"hue": 120, "card": card}}
        ev = nostr.build_event(agent_sk, eng_mod.KIND_LIVE, json.dumps(content),
                               [["h", room], ["owner", owner_pk, nostr.owner_binding(owner_sk, agent_pk)]])
        e.events[room] = {}
        asyncio.run(e._on_event(ev, "live"))
        assert e.presence[room][agent_pk]["face"]["card"] == card  # the engine passes faces through; faceFor cleans them


@needs_node
def test_the_ui_reads_a_hostile_style_as_the_member_card():
    out = _run("""
console.log(JSON.stringify([faceFor({ card: 'scanner' }, 'ab').card, faceFor({ card: 'SCANNER' }, 'ab').card, faceFor({ card: '<img onerror=x>' }, 'ab').card,
  faceFor({ card: ['scanner'] }, 'ab').card, faceFor({ card: { toString() { return 'scanner' } } }, 'ab').card, faceFor(null, 'ab').card, faceFor('scanner', 'ab').card]))""")
    assert out == ["scanner", "member", "member", "member", "member", "member", "member"]
    # the card picks its style from the cleaned face, never from the raw value
    assert "card: faceFor(props.face, props.pk).card" in _fn(CARD, "cardModel")
    assert "model.card === 'scanner'" in _fn(CARD, "IdCard")


@needs_node
def test_the_led_follows_the_real_state():
    out = _run("""
console.log(JSON.stringify([scanLed({ kind: 'agent', state: 'activity: idle' }), scanLed({ kind: 'agent', state: 'activity: speaking' }),
  scanLed({ kind: 'agent', state: 'system: absent' }), scanLed({ kind: 'agent' }), scanLed({ kind: 'agent', state: 'system: absent', warn: true }),
  scanLed({ kind: 'person', online: true }), scanLed({ kind: 'person', online: false }), scanLed({ kind: 'person', online: true, warn: true })]))""")
    assert out == ["green", "green", "amber", "green", "red", "green", "amber", "red"]
    assert "online: !!p.online" in _fn(CARD, "personSheet")


# ---- the nebula --------------------------------------------------------------------------------

@needs_node
def test_the_nebula_is_the_keys_own_and_never_changes():
    a, b = "3f2a9c1b77e0" * 5 + "abcd", "5a17be02" * 8
    out = _run(f"""
const f = (pk, t) => {{ const r = nebulaField(pk, 48, 25, t); return {{ w: r.w, h: r.h, d: Array.from(r.d), m: Array.from(r.m) }} }}
console.log(JSON.stringify([f('{a}', 0), f('{a}', 0), f('{b}', 0), f('{a}', 30), f(null, 0), f(42, 0), f({{}}, NaN),
  nebulaField('{a}', 0, -3, 0).d.length, nebulaField('{a}', 1e9, 'x', 0).d.length]))""")
    first, again, other, later, none, number, obj, small, big = out
    assert first == again  # deterministic for a key
    assert first["w"] == 48 and first["h"] == 25 and len(first["d"]) == len(first["m"]) == 48 * 25
    for f in (first, other, later, none, number, obj):
        assert all(0 <= x <= 1 for x in f["d"] + f["m"])
    diff = sum(abs(x - y) for x, y in zip(first["d"], other["d"])) / len(first["d"])
    assert diff > 0.05  # another key, another nebula
    drift = sum(abs(x - y) for x, y in zip(first["d"], later["d"])) / len(first["d"])
    assert 0 < drift < diff  # time moves it, gently
    # it has both dark space and bright cores, not a flat wash
    assert min(first["d"]) < 0.05 and max(first["d"]) > 0.6
    assert small == 48 and big == 256 * 25  # 0 is the default width, -3 rows is one row


@needs_node
def test_the_palette_is_valid_for_every_hue():
    out = _run("""
const ok = []
for (const h of [0, 40, 92, 150, 210, 255, 300, 340, -20, 400, NaN, 'x']) {
  const lut = scannerLut(h, h + 150)
  ok.push(lut.length === 64 * 16 * 3 && Array.from(lut).every(v => Number.isInteger(v) && v >= 0 && v <= 255))
}
const lut = scannerLut(255, 40)
const at = (d, m) => Array.from(lut.slice((d * 16 + m) * 3, (d * 16 + m) * 3 + 3))
console.log(JSON.stringify([ok, at(0, 0), at(63, 15), at(40, 0), at(40, 15)]))""")
    ok, dark, hot, cool, warm = out
    assert all(ok)
    assert sum(dark) < 80 and dark[2] > dark[0]  # deep navy under everything
    assert min(hot) > 220  # the hottest cells are near white
    assert cool[2] > cool[0]  # a blue agent's body is blue...
    assert warm[0] > warm[2]  # ...and its hot cores turn orange


def test_the_drift_loop_respects_reduced_motion_and_stops():
    loop = _fn(SCANNER, "useNebula")
    assert "if (still || motion.reduced()) return" in loop  # one static frame with reduced motion
    assert "IntersectionObserver" in loop and "document.hidden" in SCANNER[SCANNER.index("const nebulaIdle"):SCANNER.index("function nebulaFrame")]
    # on unmount: the nebula leaves the shared loop, listeners and observers go
    assert "NEBULAS.delete(e)" in loop and "offVis()" in loop and "io.disconnect()" in loop
    assert "useState" not in loop  # frames go to the canvas, never React state
    power = _fn(CARD, "useScreenPowerOn")
    assert "motion.reduced()" in power and "s.stop()" in power and "useState" not in power


def test_there_is_one_nebula_loop_for_the_whole_page():
    # a loop per mount left a dispose handler (and the mount's canvases) behind on Desktop every time a sheet opened
    assert SCANNER.count("P.loop(") == 1
    assert "P.loop(" not in _fn(SCANNER, "useNebula") and "P.loop(" in _fn(SCANNER, "nebulaWake")
    # the card hands its turned-over state to the front screen
    assert "scannerFront(model, Object.assign({}, props, { label, flipped }), hero)" in _fn(CARD, "IdCard")
    assert "flipped: props.flipped" in _fn(SCANNER, "scannerFront")


NEBULA_RIG = """
let loops = 0, wakes = 0, puts = 0, listeners = 0, draw = null, idle = null
const P = { loop(d, i) { loops++; draw = d; idle = i; return { wake() { wakes++ }, dispose() {} } },
  listen() { listeners++; return () => { listeners-- } } }
const motion = { reduced: () => false }
const document = { hidden: false }
const observers = new Set()
class IntersectionObserver { constructor(cb) { this.cb = cb; observers.add(this) } observe() {} disconnect() { observers.delete(this) } }
let cur = null
function useRef(v) { const i = cur.i++; if (!cur.slots[i]) cur.slots[i] = { current: v }; return cur.slots[i] }
function useEffect(fn, deps) {
  const i = cur.i++, old = cur.slots[i]
  if (old && deps && deps.every((d, k) => Object.is(d, old.deps[k]))) return
  if (old && old.cleanup) old.cleanup()
  cur.slots[i] = { deps, cleanup: fn() }
}
const canvas = () => ({ getContext: () => ({ createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4) }), putImageData() { puts++ } }) })
function mount() {
  const m = { slots: [], i: 0, a: { current: canvas() }, b: { current: canvas() } }
  m.render = (flipped, still) => { cur = m; m.i = 0; useNebula(m.a, m.b, 'ab'.repeat(32), 255, 40, !!still, 1, flipped) }
  m.unmount = () => m.slots.forEach(s => s && typeof s.cleanup === 'function' && s.cleanup())
  return m
}
"""


@needs_node
def test_nebulas_share_one_loop_and_park_when_not_seen():
    out = _run(NEBULA_RIG + """
const log = {}
for (let i = 0; i < 200; i++) { const m = mount(); m.render(false); m.render(false); m.unmount() }
log.loops = loops; log.left = NEBULAS.size; log.listeners = listeners; log.observers = observers.size
const m = mount()
m.render(false)
log.live = NEBULAS.size; log.idleLive = idle()
let before = puts; draw(1000); log.drewLive = puts - before          // both canvases painted
// turned to the back: the front keeps "intersecting", but nothing is drawn and the loop is idle
m.render(true)
log.idleFlipped = idle(); before = puts; draw(2000); log.drewFlipped = puts - before
// turned back: the loop wakes and it draws again
const w = wakes
m.render(false)
log.wokeOnFlipBack = wakes - w; log.idleBack = idle(); before = puts; draw(3000); log.drewBack = puts - before
// off screen, and a hidden page
observers.forEach(o => o.cb([{ isIntersecting: false }]))
log.idleOffscreen = idle()
observers.forEach(o => o.cb([{ isIntersecting: true }]))
document.hidden = true; log.idleHidden = idle(); document.hidden = false
// a card that starts on its back never draws; reduced motion and `still` never register
const back = mount(); back.render(true); m.unmount()
log.backOnly = NEBULAS.size; log.idleBackOnly = idle()
back.unmount()
const n = NEBULAS.size
motion.reduced = () => true; const r = mount(); r.render(false)
motion.reduced = () => false; const st = mount(); st.render(false, true)
log.stillAdded = NEBULAS.size - n; log.loopsEnd = loops
console.log(JSON.stringify(log))""")
    assert out["loops"] == 1 and out["loopsEnd"] == 1  # 200 mounts, one P.loop
    assert out["left"] == 0 and out["listeners"] == 0 and out["observers"] == 0  # nothing left behind
    assert out["live"] == 1 and out["idleLive"] is False and out["drewLive"] == 2
    assert out["idleFlipped"] is True and out["drewFlipped"] == 0
    assert out["wokeOnFlipBack"] >= 1 and out["idleBack"] is False and out["drewBack"] == 2
    assert out["idleOffscreen"] is True and out["idleHidden"] is True
    assert out["backOnly"] == 1 and out["idleBackOnly"] is True  # `back` is registered but parked
    assert out["stillAdded"] == 0


# ---- the saved image ---------------------------------------------------------------------------

def _scanner_svg(opts_js: str) -> str:
    return _run(f"console.log(JSON.stringify(scannerSvg({opts_js})))")


SCANNER_TAGS = {"svg", "defs", "g", "rect", "circle", "path", "text", "radialGradient", "linearGradient", "stop", "pattern", "clipPath", "filter",
                "ellipse", "feGaussianBlur", "feMerge", "feMergeNode", "feDropShadow", "feComponentTransfer", "feFuncR", "feFuncG", "feFuncB", "image"}


def _check_inert(svg: str) -> ET.Element:
    root = ET.fromstring(svg)  # well-formed XML, or this raises
    assert root.tag == SVG_NS + "svg" and root.get("width") == "1200" and root.get("height") == "750"
    low = svg.lower()
    assert "<script" not in low and "foreignobject" not in low and "javascript:" not in low
    # no URL anywhere but the namespace (base64 has no ':', so this can't be fooled by the picture's bytes)
    assert not re.search(r"https?:", svg.replace('xmlns="http://www.w3.org/2000/svg"', ""))
    for el in root.iter():
        tag = el.tag.replace(SVG_NS, "")
        assert tag in SCANNER_TAGS, tag
        for attr, value in el.attrib.items():
            assert not attr.lower().startswith("on"), attr
            if "href" in attr.lower():
                assert tag == "image" and attr == "href" and re.fullmatch(r"data:image/png;base64,[A-Za-z0-9+/]+={0,2}", value), (tag, attr)
            assert not re.search(r"url\((?!#)", value)
    return root


@needs_node
def test_scanner_svg_with_hostile_text_is_well_formed_and_inert():
    face = '<g style="fill:#fff"><circle cx="20" cy="20" r="10" style="fill:#fff;stroke:none"/></g>'
    png = _png()
    svg = _scanner_svg("{ hue: 255, hue2: 40, pk: %s, led: 'green', nebula: %s, name: %s, tag: 'Agent', serial: '3F2A·9C1B·77E0', "
                       "fields: [['Owner', %s], ['Model', %s, true]], faces: [{ inner: %s, left: 0, top: 0, size: 100, front: true }] }"
                       % (json.dumps("ab" * 32), json.dumps(png), json.dumps(HOSTILE), json.dumps("<b onload=x>&Co"),
                          json.dumps("a\"><img src=x onerror=alert(2)>'&"), json.dumps(face)))
    root = _check_inert(svg)
    images = list(root.iter(SVG_NS + "image"))
    assert len(images) == 1 and images[0].get("href") == png  # our own nebula, and only that
    assert "&lt;/TEXT&gt;&lt;SCRIPT" in svg
    texts = [t.text for t in root.iter(SVG_NS + "text")]
    assert any(t and t.startswith("</TEXT><SCRIPT") for t in texts)
    assert "&lt;B ONLOAD=X&gt;" in svg
    assert any(t and t.startswith('A"><IMG') for t in texts)
    assert "ID 3F2A·9C1B·77E0" in texts
    assert root.find(".//" + SVG_NS + "circle[@r='10']") is not None  # the face made it in


@needs_node
@pytest.mark.parametrize("nebula", ["https://example.com/a.png", "//example.com/a.png", "data:image/svg+xml;base64,PHN2Zz4=",
                                    "data:image/png;base64,AAA\" onload=\"alert(1)", "data:image/png;base64,AA==#x", "data:text/html,<b>",
                                    "javascript:alert(1)", "", None, 42, ["data:image/png;base64,AAAA"]])
def test_scanner_svg_takes_only_its_own_png(nebula):
    svg = _scanner_svg("{ hue: 10, name: 'A', tag: 'Agent', nebula: %s }" % json.dumps(nebula))
    root = _check_inert(svg)
    assert list(root.iter(SVG_NS + "image")) == []


@needs_node
def test_scanner_svg_refuses_faces_that_are_not_plain_shapes_and_copes_with_odd_input():
    bad = ["<script>alert(1)</script>", "<foreignObject><div/></foreignObject>", "<image href=\"https://example.com/a.png\"/>",
           "<g onclick=\"x()\"><circle r=\"1\"/></g>", "<circle r=\"1\" style=\"fill:url(https://e.com/x)\"/>"]
    out = _run(f"""
const bad = {json.dumps(bad)}
console.log(JSON.stringify(bad.map(m => scannerSvg({{ hue: 10, name: 'A', tag: 'Agent', faces: [{{ inner: m, left: 0, top: 0, size: 100, front: true }}] }}))))""")
    for svg in out:
        _check_inert(svg)
        assert 'viewBox="0 0 40 40"' not in svg
    odd = "\u0000\u0007bad\ud800 name \n\t" + "x" * 500
    for opts in ("{}", "{ name: %s, tag: %s, fields: [[%s, %s]], serial: %s, led: %s, pk: %s }" % ((json.dumps(odd),) * 7),
                 "{ hue: 'x', name: null, fields: [null, ['a'], ['b', null], ['c', 'd']], faces: 'nope', warn: 1 }",
                 "{ name: 'Ada', initial: '\\ud83d', hue: 1e9 }", "{ name: 'Ada', initial: 'Q', measure: () => NaN, warn: true, led: 'red' }"):
        svg = _scanner_svg(opts)
        _check_inert(svg)
        assert len(svg) < 60000
    assert ">Q</text>" in _scanner_svg("{ name: 'Ada', initial: 'Q', hue: 20 }")


def test_the_scanner_code_stays_inside_the_lint_and_the_rules():
    banned = "<" + "script"
    for path in ("ui/34_scanner.js", "desktop/plugin.js", "dashboard/dist/index.js"):
        assert banned not in (ROOT / path).read_text().lower(), path
    for needle in ("fetch(", "XMLHttpRequest", "foreignObject", "innerHTML", "xlink:href"):
        assert needle not in SCANNER, needle
    assert SCANNER.count("http") == 1 and "http://www.w3.org/2000/svg" in SCANNER
    # the one <image is the nebula, behind the data-URL check
    assert SCANNER.count("<image") == 1 and "if (scanPngOk(o.nebula))" in _fn(SCANNER, "scannerSvg")
    # the image file itself still never draws an <image>; it hands Scanner cards to scannerSvg
    assert "<image" not in IMAGE and "scannerSvg(" in _fn(IMAGE, "cardImage")


# ---- legibility ------------------------------------------------------------------------------------

STYLE = (ROOT / "ui" / "20_style.js").read_text()


def _css_rules(selector_part: str):
    """(selector, body) for every rule in the style sheet whose selector mentions `selector_part`."""
    for m in re.finditer(r"([^{}`]+)\{([^{}]*)\}", STYLE):
        if selector_part in m.group(1):
            yield m.group(1).strip(), m.group(2)


def test_scanner_text_never_drops_below_a_readable_pixel_size():
    # a bare cqw size is a few pixels on a phone-width card (about 319px in the Webapp at 375px); small text needs a floor
    seen = 0
    for selector, body in _css_rules(".h-scan"):
        for m in re.finditer(r"(?<![-\w])font-size:([^;}]+)", body):
            size = m.group(1).strip()
            cq = re.findall(r"([\d.]+)cqw", size)
            if not cq or float(cq[0]) >= 3.2:
                continue  # big text (name, values) stays readable at 3.2cqw even on a narrow card
            seen += 1
            floor = re.match(r"(?:max|clamp)\(([\d.]+)px,", size)
            assert floor and float(floor.group(1)) >= 7.5, (selector, size)
    assert seen == 7  # labels, ID, tag, brand, back key, about, back value


def _luminance(hex_color: str) -> float:
    c = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_the_bezel_brand_is_a_visible_engraving_in_both_renderers():
    metal = "#2b3036"  # the strip's middle stop, in the CSS and in scannerSvg
    css = next(body for sel, body in _css_rules(".h-scan-brand") if sel == ".h-scan-brand")
    ink = re.search(r"color:(#[0-9a-f]{6})", css).group(1)
    assert _contrast(ink, metal) >= 2.0, ink
    assert re.search(r"text-shadow:0 1px 0 #[0-9a-f]{6}", css)  # a dark edge one pixel down
    svg = re.search(r"out\.push\(text\(lx \+ 2\.6 \* U, cy \+ 1\.6 \* U \* 0\.36, 'NINSEI', \{[^}]*fill: '(#[0-9a-f]{6})'", SCANNER)
    assert svg and _contrast(svg.group(1), metal) >= 2.0 and "opacity" not in svg.group(0)


def test_labels_and_the_card_number_have_backing_on_the_screen():
    # full-strength labels, the ID in the bright ink on a dark pill, a scrim under the name and the fields (both renderers)
    label = next(body for sel, body in _css_rules(".h-scan-label") if sel == ".h-scan-label")
    assert "opacity" not in label
    ident = next(body for sel, body in _css_rules(".h-scan-id") if sel == ".h-scan-id")
    assert "color:var(--scan-ink)" in ident and re.search(r"background:oklch\(0\.\d+ [\d.]+ \d+ / \.\d+\)", ident)
    assert next(body for sel, body in _css_rules(".h-scan-scrim") if sel == ".h-scan-scrim")
    front = _fn(SCANNER, "scannerFront")
    assert front.index("h-scan-scrim") < front.index("h-scan-box") < front.index("h-scan-top")  # under the box and the text
    svg = _fn(SCANNER, "scannerSvg")
    assert 'fill="url(#nsscrim)"' in svg and 'fill="url(#nsscrimn)"' in svg
    assert svg.index("nsscrim)") < svg.index("const bs =")  # the scrims go down before the box and the text
    assert "opacity: 0.85" not in svg  # field labels are full strength
    assert svg.index("fill-opacity=\"0.72\"") < svg.index("idText, {")  # the pill goes down before the number
