"""A shared toy may show only its own page (ui/30_parts.js TOY_GUARD + toyGuard, wired into K.Toy and
withCsp on both platforms). The state machine runs under node; the wiring is checked in the sources and
the built bundles. The in-frame script was checked against navigating and prototype-patching toys in
headless Chrome (implementation-notes.md, 2026-11-06)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
KEY = "ab" * 16


def _guard_src() -> str:
    src = (ROOT / "ui" / "30_parts.js").read_text()
    start = src.index("function toyGuard(")
    end = src.index("\n}\n", start) + 3
    return src[start:end]


def _run(steps):
    """steps: 'hello', 'load', 'proof', 'badproof', 'timeout'. Returns the guard's calls in order."""
    js = _guard_src() + f"""
const out = []; let timer = null
const g = toyGuard({json.dumps(KEY)}, () => out.push('show'), () => out.push('leave'), fn => {{ timer = fn }}, () => out.push('stuck'))
for (const s of {json.dumps(steps)}) {{
  if (s === 'hello') out.push('key:' + g.hello())
  else if (s === 'load') g.load()
  else if (s === 'proof') g.message('ninsei-toy-loaded:' + {json.dumps(KEY)})
  else if (s === 'badproof') g.message('ninsei-toy-loaded:' + 'cd'.repeat(16))
  else if (s === 'timeout') timer && timer()
}}
console.log(JSON.stringify(out))"""
    out = subprocess.run([NODE, "-e", js], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


@needs_node
def test_a_toy_is_shown_once_its_own_page_proves_it_loaded_in_either_order():
    assert _run(["hello", "load", "proof"]) == [f"key:{KEY}", "show"]
    assert _run(["hello", "proof", "load"]) == [f"key:{KEY}", "show"]


@needs_node
def test_the_key_is_handed_out_once():
    assert _run(["hello", "hello"]) == [f"key:{KEY}", "key:null"]


@needs_node
def test_a_second_load_closes_the_toy():
    assert _run(["hello", "load", "proof", "load"]) == [f"key:{KEY}", "show", "leave"]


@needs_node
def test_a_page_that_loads_without_the_key_is_never_shown():
    # navigating before its own page finishes: only the new page's load is reported
    assert _run(["hello", "load", "badproof", "timeout"]) == [f"key:{KEY}", "stuck"]


@needs_node
def test_a_slow_honest_toy_still_appears_after_the_stuck_notice():
    assert _run(["hello", "load", "timeout", "proof"]) == [f"key:{KEY}", "stuck", "show"]


@needs_node
def test_a_proof_after_a_navigation_does_not_reopen_the_toy():
    assert _run(["hello", "load", "load", "proof"]) == [f"key:{KEY}", "leave"]


def test_both_platforms_wire_the_guard():
    for f in ("desktop_tail.js", "dashboard_tail.js"):
        src = (ROOT / "ui" / "platform" / f).read_text()
        toy = src[src.index("Toy"):]
        toy = toy[:toy.index("\n  }") if f == "desktop_tail.js" else toy.index("\n")]
        assert "onLoad: props.onLoad" in toy and "ref: props.frameRef" in toy, f
    parts = (ROOT / "ui" / "30_parts.js").read_text()
    assert re.search(r"jsx\(K\.Toy, \{[^}]*onLoad: \(\) => guard\.current\.load\(\), frameRef: frame", parts)
    room = (ROOT / "ui" / "50_room.js").read_text()
    assert "jsx(ToyFrame, { html: build.frame || ''" in room   # the preview runs the guarded document
    for bundle in (ROOT / "desktop" / "plugin.js", ROOT / "dashboard" / "dist" / "index.js"):
        assert "function toyGuard(" in bundle.read_text(), bundle.name


def test_the_desktop_bundle_carries_no_script_markup():
    """`hermes plugins validate` refuses `<script` anywhere in desktop/plugin.js; the guard lives in the backend."""
    assert "<script" not in (ROOT / "desktop" / "plugin.js").read_text()


def test_the_backend_puts_the_guard_first_in_every_toy_frame():
    from ninsei_engine import toy
    out = toy.inject_csp("<!DOCTYPE html><script>evil()</script>", guard=True)
    assert out.startswith("<!DOCTYPE html>" + toy.CSP_META + toy.TOY_GUARD)
    assert out.index(toy.TOY_GUARD) < out.index("evil()")
    assert toy.inject_csp("<p>x", guard=True).startswith(toy.CSP_META + toy.TOY_GUARD)
    assert toy.TOY_GUARD not in toy.inject_csp("<p>x")   # the source view stays the toy's own


def test_the_in_frame_script_keeps_its_own_copies_before_the_toy_runs():
    from ninsei_engine import toy
    for needle in ('B=F.bind.bind(F.call)', 'D(M,"source").get', 'D(M,"data").get',
                   'B(Event.prototype.stopImmediatePropagation)', '},true)', 'd.length===32'):
        assert needle in toy.TOY_GUARD, needle
    parts = (ROOT / "ui" / "30_parts.js").read_text()
    assert "padStart(2, '0')" in parts and "new Uint8Array(16)" in parts   # the key is 32 hex characters
