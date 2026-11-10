"""Audit #11 (code part): WebRTC and shared toys.

What is and is not blocked, checked in Chrome 156 (Electron 44 is Chromium 152) on 2026-11-06:
- No CSP stops WebRTC in any browser. `webrtc 'block'` is in the CSP3 draft; Chrome ignores it ("Unrecognized
  Content-Security-Policy directive"). With the old policy and with the new one, an RTCPeerConnection in a
  sandboxed srcdoc frame still sent a UDP packet (a STUN binding request) to an address the toy chose, so the
  viewer's IP and any data can leave. The directive stays in the string for the day a browser honours it.
- TOY_GUARD hides RTCPeerConnection, webkitRTCPeerConnection and RTCDataChannel in the toy's own page. That
  stopped a direct `new RTCPeerConnection()` (0 packets). A toy that builds a child frame with `srcdoc` still
  gets that frame's own constructors (1 packet), so this is best effort.
Those two facts are what the README, ARCHITECTURE.md and the catalog text must say.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from ninsei_engine import toy

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

HEADS = ("ui/platform/desktop_head.js", "ui/platform/dashboard_head.js")
BUILT = ("desktop/plugin.js", "dashboard/dist/index.js")
_CSP_LINE = re.compile(r"const TOY_CSP = \"([^\"]*)\"")


def _head_csp(rel: str) -> str:
    m = _CSP_LINE.search((ROOT / rel).read_text())
    assert m, rel
    return m.group(1)


def test_the_backend_and_both_ui_copies_carry_the_same_csp():
    for rel in HEADS:
        assert _head_csp(rel) == toy.TOY_CSP, rel
    for rel in BUILT:
        assert f'const TOY_CSP = "{toy.TOY_CSP}"' in (ROOT / rel).read_text(), rel
    assert toy.CSP_META == f'<meta http-equiv="Content-Security-Policy" content="{toy.TOY_CSP}">'


def test_the_csp_keeps_everything_shut_and_adds_the_webrtc_directive():
    directives = [d.strip() for d in toy.TOY_CSP.split(";")]
    assert "default-src 'none'" in directives
    assert "webrtc 'block'" in directives
    assert "connect-src" not in toy.TOY_CSP and "unsafe-eval" not in toy.TOY_CSP   # nothing opened up
    assert "'self'" not in toy.TOY_CSP


def test_the_csp_comment_says_it_does_not_stop_webrtc():
    src = (ROOT / "ninsei_engine" / "toy.py").read_text()
    assert "does NOT stop WebRTC" in src and "best effort" in src


def test_the_desktop_bundle_still_has_no_script_markup():
    """`hermes plugins validate` refuses `<script` in desktop/plugin.js; the neutering lives in the backend guard."""
    for rel in HEADS + BUILT:
        assert "<script" not in (ROOT / rel).read_text(), rel


def test_the_guard_hides_the_webrtc_constructors_before_anything_else_runs():
    g = toy.TOY_GUARD
    for name in ("RTCPeerConnection", "webkitRTCPeerConnection", "RTCDataChannel"):
        assert f'"{name}"' in g, name
    assert g.index("defineProperty") < g.index("addEventListener")   # before the handshake listeners exist
    assert g.startswith("<script>") and g.endswith("</script>") and g.count("<script") == 1


_HARNESS = """
const sent = [], listeners = {}
const { port1, port2 } = new MessageChannel()   // node only accepts a MessagePort as an event's source
port1.postMessage = m => sent.push(m)
globalThis.parent = port1
globalThis.addEventListener = (t, f) => { (listeners[t] = listeners[t] || []).push(f) }
"""


def _run_guard(setup: str, after: str) -> dict:
    body = toy.TOY_GUARD[len("<script>"):-len("</script>")]
    js = _HARNESS + setup + "\n;" + body + ";" + after + "\nconsole.log(JSON.stringify(result)); port1.close(); port2.close()"
    out = subprocess.run([NODE, "-"], input=js, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@needs_node
def test_the_guard_removes_the_constructors_and_a_toy_cannot_put_them_back():
    got = _run_guard(
        "for (const n of ['RTCPeerConnection', 'webkitRTCPeerConnection', 'RTCDataChannel', 'Keep'])"
        " globalThis[n] = function Real() {}\n",
        """
const tryRestore = n => { try { globalThis[n] = function Fake() {} } catch (_) {}
  try { Object.defineProperty(globalThis, n, { value: 1 }) } catch (_) {}; try { delete globalThis[n] } catch (_) {}
  return typeof globalThis[n] }
const result = { types: ['RTCPeerConnection', 'webkitRTCPeerConnection', 'RTCDataChannel', 'Keep'].map(n => typeof globalThis[n]),
  restored: ['RTCPeerConnection', 'webkitRTCPeerConnection', 'RTCDataChannel'].map(tryRestore), sent }""")
    assert got["types"] == ["undefined", "undefined", "undefined", "function"]   # only the three are touched
    assert got["restored"] == ["undefined"] * 3
    assert got["sent"] == ["ninsei-toy-hello"]   # the handshake still starts


@needs_node
def test_the_guard_handshake_still_works_with_and_without_the_constructors():
    after = """
const fire = (t, ev) => (listeners[t] || []).forEach(f => f(ev))
const real = (ev, trusted) => { Object.defineProperty(ev, 'isTrusted', { get: () => trusted }); return ev }
const key = 'cd'.repeat(16)
fire('message', real(new MessageEvent('message', { data: key, source: port1 }), true))
fire('load', real(new Event('load'), true))
const result = { sent }"""
    for setup in ("", "globalThis.RTCPeerConnection = function () {}\nglobalThis.RTCDataChannel = function () {}\n"):
        assert _run_guard(setup, after)["sent"] == ["ninsei-toy-hello", "ninsei-toy-loaded:" + "cd" * 16]


@needs_node
def test_a_failing_neuter_cannot_break_the_handshake():
    """If a constructor can't be redefined (frozen global), the guard must still say hello."""
    got = _run_guard("Object.defineProperty(globalThis, 'RTCPeerConnection', { value: function () {}, configurable: false })\n",
                     "\nconst result = { sent }")
    assert got["sent"] == ["ninsei-toy-hello"]
