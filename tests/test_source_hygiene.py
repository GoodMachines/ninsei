"""No invisible characters typed into the source: write them as escapes ("\\u200b"), never literally.

Hermes's install scanner rates a literal format character (a BOM, a zero-width space, a bidi override) in a plugin's
code as a HIGH injection finding and refuses the update with a CAUTION verdict (persona.py's "\\ufeff", 2026-11-07).
They are also how a reviewer gets fooled about what code says. Tests that need them spell them as escapes too."""
import subprocess
import unicodedata
from pathlib import Path

from ninsei_engine import names

ROOT = Path(__file__).resolve().parent.parent
TEXT = (".py", ".js", ".md", ".yaml", ".yml", ".json", ".css", ".html", ".txt", ".toml", ".ini")


def _tracked():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    return [ROOT / f for f in out if f.endswith(TEXT)]


def invisible(line: str) -> list:
    # The scanner's format characters, plus what the engine itself treats as invisible (Hangul fillers, U+2800):
    # a literal one in a test reads as an empty string to a reviewer. U+FE0F is an emoji's own style selector.
    return sorted({f"U+{ord(c):04X}" for c in line
                   if unicodedata.category(c) in ("Cf", "Zl", "Zp") or (unicodedata.category(c) == "Cc" and c != "\t")
                   or (names.invisible(c) and c not in "\t\ufe0e\ufe0f")})


def test_the_check_sees_what_the_scanner_flags():
    assert invisible("x.lstrip(\"\ufeff\")") == ["U+FEFF"]
    assert invisible("a\u200bb \u202e") == ["U+200B", "U+202E"]
    assert invisible('x.lstrip("\\ufeff")  # an escape is fine') == []
    assert invisible("Ada\u3164 \u2800") == ["U+2800", "U+3164"]
    assert invisible("\u2764\ufe0f") == []


def test_no_tracked_text_file_has_a_literal_invisible_character():
    found = []
    for p in _tracked():
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            bad = invisible(line)
            if bad:
                found.append(f"{p.relative_to(ROOT)}:{i}: {', '.join(bad)}")
    assert not found, "write these as \\u escapes:\n" + "\n".join(found)
