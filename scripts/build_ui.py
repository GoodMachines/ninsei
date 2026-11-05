#!/usr/bin/env python3
"""Build Xenia's two UI files from the one shared source in ui/.

    python3 scripts/build_ui.py          # writes desktop/plugin.js and dashboard/dist/index.js
    python3 scripts/build_ui.py --check  # exits 1 if either output is out of date

No bundler and no npm: the shared files (ui/*.js, in name order) are plain JavaScript written
against two small interfaces, `P` (platform: fetch, timers, toasts, clipboard, storage, animation
loop) and `K` (UI kit). Each output is the platform's prelude, the shared source, and the
platform's adapter, concatenated as-is so reviewers read exactly what runs:

  desktop/plugin.js        ESM for Hermes Desktop: ui/platform/desktop_head.js + ui/*.js + desktop_tail.js
  dashboard/dist/index.js  IIFE for `hermes dashboard`: ui/platform/dashboard_head.js + ui/*.js + dashboard_tail.js

It also refuses to write output that uses JSX syntax or imports anything besides the Desktop SDK
and React, the two things a disk plugin cannot do.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui"
PLATFORM = UI / "platform"

TARGETS = {
    "desktop": (ROOT / "desktop" / "plugin.js", "desktop_head.js", "desktop_tail.js"),
    "dashboard": (ROOT / "dashboard" / "dist" / "index.js", "dashboard_head.js", "dashboard_tail.js"),
}

ALLOWED_IMPORTS = {"@hermes/plugin-sdk", "react", "react/jsx-runtime"}
IMPORT_RE = re.compile(r"^\s*import\b[^'\"]*['\"]([^'\"]+)['\"]", re.M)
JSX_RE = re.compile(r"(?:return|=>|\()\s*<[A-Za-z]")


def shared_sources() -> list[Path]:
    return sorted(p for p in UI.glob("*.js") if p.is_file())


def build(kind: str) -> str:
    _out, head, tail = TARGETS[kind]
    parts = [(PLATFORM / head).read_text(encoding="utf-8").rstrip() + "\n"]
    for src in shared_sources():
        parts.append(f"\n// ===== ui/{src.name} " + "=" * max(4, 86 - len(src.name)) + "\n\n")
        parts.append(src.read_text(encoding="utf-8").rstrip() + "\n")
    parts.append("\n// ===== platform " + "=" * 80 + "\n\n")
    parts.append((PLATFORM / tail).read_text(encoding="utf-8").rstrip() + "\n")
    return "".join(parts)


def lint(kind: str, text: str) -> list[str]:
    problems = []
    for spec in IMPORT_RE.findall(text):
        if kind == "dashboard" or spec not in ALLOWED_IMPORTS:
            problems.append(f"{kind}: import of {spec!r} is not allowed")
    if JSX_RE.search(text):
        problems.append(f"{kind}: looks like JSX syntax; disk plugins load uncompiled, use jsx()")
    return problems


def main() -> int:
    check = "--check" in sys.argv[1:]
    stale, problems = [], []
    for kind, (out, _h, _t) in TARGETS.items():
        text = build(kind)
        problems += lint(kind, text)
        if check:
            if not out.exists() or out.read_text(encoding="utf-8") != text:
                stale.append(str(out.relative_to(ROOT)))
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)} ({len(text.encode()) // 1024} KB)")
    for p in problems:
        print("error:", p, file=sys.stderr)
    for s in stale:
        print("out of date:", s, "(run python3 scripts/build_ui.py)", file=sys.stderr)
    return 1 if problems or stale else 0


if __name__ == "__main__":
    sys.exit(main())
