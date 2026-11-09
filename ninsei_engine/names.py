"""How a name or a label reads to a person: the one folding every identity check uses.

Two strings that look the same must compare the same. That takes two steps, and every check (held names,
the impostor flag, "not verified", the transcript sanitizer's labels) goes through these helpers rather
than its own copy:

- invisible characters go: controls, format characters, line and paragraph separators, every
  Default_Ignorable_Code_Point (Hangul fillers among them) and blank glyphs such as U+2800;
- look-alike letters fold to Latin (Cyrillic О, Greek Υ), for comparing, never for display.
"""
from __future__ import annotations

import re
import unicodedata

# Unicode's Default_Ignorable_Code_Point (DerivedCoreProperties.txt), plus blank glyphs that draw nothing
# but are ordinary symbols (U+2800 BRAILLE PATTERN BLANK, U+1D159 MUSICAL SYMBOL NULL NOTEHEAD). Python's unicodedata has no property lookup, so
# the ranges are listed; tests pin the ones that have been used against us.
_INVISIBLE_RANGES = (
    (0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5),
    (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F), (0x2800, 0x2800),
    (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3), (0x1D159, 0x1D159), (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF),
)
_INVISIBLE_RE = re.compile("[" + "".join(
    re.escape(chr(a)) if a == b else f"{re.escape(chr(a))}-{re.escape(chr(b))}" for a, b in _INVISIBLE_RANGES) + "]")
_HIDDEN_CATS = ("Cc", "Cf", "Zl", "Zp")


def invisible(ch: str) -> bool:
    """Draws nothing (or only changes how a neighbour draws): never part of what a reader sees."""
    return unicodedata.category(ch) in _HIDDEN_CATS or _INVISIBLE_RE.match(ch) is not None


def strip_invisible(text: str) -> str:
    return "".join(ch for ch in text if not invisible(ch))


def name_ok(name, fallback: str) -> str:
    """A display name as shown: invisible characters removed, trimmed, at most 32 characters."""
    return strip_invisible(str(name or "")).strip()[:32] or fallback


# Latin letter small capitals, to the letter they show.
SMALL_CAPITALS = {
    "\u1d00": "a", "\u0299": "b", "\u1d04": "c", "\u1d05": "d", "\u1d07": "e", "\ua730": "f", "\u0262": "g",
    "\u029c": "h", "\u026a": "i", "\u1d0a": "j", "\u1d0b": "k", "\u029f": "l", "\u1d0d": "m", "\u0274": "n",
    "\u1d0f": "o", "\u1d18": "p", "\ua7af": "q", "\u0280": "r", "\ua731": "s", "\u1d1b": "t", "\u1d1c": "u",
    "\u1d20": "v", "\u1d21": "w", "\u028f": "y", "\u1d22": "z",
}
# Capitals that look like Latin ones but casefold to something that doesn't (Greek Υ -> υ, Μ -> μ).
_CONFUSABLE_CAPS = {
    "Α": "a", "Β": "b", "Ε": "e", "Ζ": "z", "Η": "h", "Ι": "i", "Κ": "k", "Μ": "m", "Ν": "n", "Ο": "o",
    "Ρ": "p", "Τ": "t", "Υ": "y", "Χ": "x",
    "А": "a", "В": "b", "Е": "e", "К": "k", "М": "m", "Н": "h", "О": "o", "Р": "p", "С": "c", "Т": "t",
    "У": "y", "Х": "x", "Ѕ": "s", "І": "i", "Ј": "j", "Ү": "y", "Ԝ": "w", "Ԛ": "q",
}
# Letters that look like Latin ones. Applied after casefolding, so lowercase forms only.
_CONFUSABLE_LETTERS = {
    # Cyrillic
    "а": "a", "в": "b", "е": "e", "ё": "e", "г": "r", "к": "k", "м": "m", "н": "h", "о": "o", "п": "n",
    "р": "p", "с": "c", "т": "t", "у": "y", "х": "x", "ѕ": "s", "і": "i", "ї": "i", "ј": "j", "һ": "h",
    "ԁ": "d", "ԛ": "q", "ԝ": "w", "ӏ": "i", "ɡ": "g", "ь": "b", "ү": "y",
    # Greek
    "α": "a", "β": "b", "ε": "e", "η": "n", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "τ": "t",
    "υ": "u", "χ": "x", "γ": "y", "ϲ": "c", "ϳ": "j", "ζ": "z",
    # Latin small capitals: they read as capitals ("ʏᴏᴜʀ ᴏᴡɴᴇʀ") but have no case of their own
    **SMALL_CAPITALS,
}
# Digits and marks that pass for letters; i, l and 1 all read as one stroke. Names only: in running text
# these are punctuation the sanitizer has its own rules for.
_CONFUSABLE_MARKS = {"0": "o", "1": "i", "l": "i", "|": "i", "!": "i", "3": "e", "5": "s", "$": "s", "@": "a"}
_CAPS = str.maketrans(_CONFUSABLE_CAPS)
# Look-alikes that NFKC would turn into something that no longer looks Latin (lunate sigma ϲ/Ϲ -> σ/Σ): mapped first.
_BEFORE_NFKC = str.maketrans({"\u03f2": "c", "\u03f9": "C"})
# One pass of str.translate, so a look-alike's target goes through the marks too: small-capital ʟ -> "l" -> "i",
# the same as a real L. tests/test_identity_folding.py checks every entry against its Latin letter.
_SKELETON = str.maketrans({**{k: _CONFUSABLE_MARKS.get(v, v) for k, v in _CONFUSABLE_LETTERS.items()}, **_CONFUSABLE_MARKS})


def skeleton(name) -> str:
    """The comparable form of a display name: NFKC, nothing invisible, no combining or separator characters,
    casefolded, look-alike letters mapped to Latin, separators dropped. Two names with the same skeleton are
    the same name to a reader, so impostor and name-holder checks compare these, never raw strings."""
    s = unicodedata.normalize("NFKC", strip_invisible(str(name or "")).translate(_BEFORE_NFKC))
    s = unicodedata.normalize("NFKD", s)  # split accents off so they can be dropped below
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] not in ("C", "M", "Z") and not ch.isspace()
                and not invisible(ch))
    s = s.translate(_CAPS).casefold().translate(_SKELETON)
    s = re.sub(r"[_.\-'’`\"]", "", s)
    return s.replace("rn", "m").replace("vv", "w")


def _fold_char(ch: str) -> str:
    c = _CONFUSABLE_CAPS.get(ch)
    if c:
        return c
    low = ch.lower()
    low = low if len(low) == 1 else ch
    return _CONFUSABLE_LETTERS.get(low, low)


def fold_letters(text: str) -> str:
    """`text` with every letter lowercased and look-alike letters mapped to Latin, one character for one,
    so a match in the result is at the same place in `text`. For spotting role words ("YОUR ОWNER" in
    Cyrillic) without rewriting what a person wrote."""
    return "".join(_fold_char(ch) for ch in text)


# Digits that spell a label word ("Y0UR 0WN3R"). Only for spotting labels: as a fold for names (skeleton) or
# for text that is shown, they would turn "R2D2 007" into letters.
_LABEL_DIGITS = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t"})


def fold_label(text: str) -> str:
    """fold_letters, plus digits read as the letters they stand in for. One character for one, so a match is
    at the same place in `text`. Every check for a role word ("your owner", "agent of", "unverified") uses this."""
    return fold_letters(text).translate(_LABEL_DIGITS)


def lower_look(text: str) -> str:
    """`text` so it reads as lowercase: str.lower, and small capitals (which have no lowercase) as Latin."""
    return "".join(SMALL_CAPITALS.get(ch) or ch.lower() for ch in text)


def sub_folded(pattern: re.Pattern, repl, text: str) -> str:
    """re.sub, matching against fold_label(text) and replacing the same span of the original text."""
    out, last = [], 0
    for m in pattern.finditer(fold_label(text)):
        out.append(text[last:m.start()])
        out.append(repl(text[m.start():m.end()]))
        last = m.end()
    out.append(text[last:])
    return "".join(out)
