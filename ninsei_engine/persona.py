"""The room agent's personality: importing it from a Hermes profile, cleaning it, and warning about private
details in it.

Everything here is read-only. A profile's `SOUL.md` is read once (at most 64 KB) when the owner picks it; the
profile is never written, and no other file in it is opened. The text becomes the `persona` setting, which goes
into the agent's own prompts and nowhere else (never a beat, card, lobby entry or room event).
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Optional

PERSONA_MAX = 1500
SOUL_READ_MAX = 64 * 1024
FLAGS_MAX = 20
_PROFILE_YAML_MAX = 16 * 1024


# --- cleaning ----------------------------------------------------------------------------------------

def clean_persona(text: Any) -> str:
    """Control and format characters out (zero-width joiners, bidi overrides), line endings and whitespace
    tidied. Newlines stay, since a profile's personality is often a few short paragraphs."""
    t = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    t = "".join(ch for ch in t if ch == "\n" or unicodedata.category(ch) not in ("Cc", "Cf", "Zl", "Zp"))
    t = "\n".join(re.sub(r" {2,}", " ", ln).strip() for ln in t.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def cut_persona(text: Any, limit: int = PERSONA_MAX) -> tuple[str, bool]:
    """Clean `text` and cut it to `limit` characters on a sentence or line boundary where one sits in the
    back half of the window (else at the last space). Returns (text, truncated)."""
    t = clean_persona(text)
    if len(t) <= limit:
        return t, False
    window = t[:limit]
    cut = max((m.end() for m in re.finditer(r"[.!?…](?=\s|$)|\n", window)), default=0)
    if cut < limit // 2:
        cut = window.rfind(" ")
        if cut < limit // 2:
            cut = limit
    return window[:cut].strip(), True


_TAG = re.compile(r"<(\s*/?\s*persona\b)", re.I)


def fence(text: Any) -> str:
    """The persona as it goes into a prompt: cleaned again (the engine may be handed anything), cut to the
    limit, and with any `<persona>` or `</persona>` made harmless so the text can't close its own block."""
    t = unicodedata.normalize("NFKC", cut_persona(text)[0])
    return _TAG.sub(r"‹\1", t)


# --- the private-detail scan -------------------------------------------------------------------------

_KEYS = re.compile(
    r"\bsk-[A-Za-z0-9_-]{16,}|\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}|\bxox[abp]-[A-Za-z0-9-]{10,}"
    r"|\bAKIA[0-9A-Z]{16}\b|\bnsec1[02-9ac-hj-np-z]{20,}|\b[0-9a-fA-F]{32,}\b"
    r"|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_URL_SECRET = re.compile(r"https?://[^\s<>\"')]*[?&;](?:token|key|secret|password)=[^\s<>\"')]*", re.I)
_HOME = re.compile(r"/Users/[^\s/\"'`]+|/home/[^\s/\"'`]+|(?<![\w.])~/[^\s\"'`]*|[A-Za-z]:\\Users\\[^\s\\\"'`]+")
_IPV4 = re.compile(r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\d.])")
_PHONE = re.compile(r"(?<![\w.])\+?\(?\d[\d\s().-]{7,}\d(?![\w])")
_ADDRESS = re.compile(r"\b\d{1,6}\s+(?:[A-Z][a-z]+\s+){1,3}(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Lane|Ln|Dr|Drive|Ct|Way)\b")
_SENSITIVE_LINE = re.compile(r"password|passcode|social security", re.I)

_KIND_ORDER = ("url_secret", "key", "email", "home_path", "ip", "address", "phone", "sensitive_line")


def _short(s: str, n: int = 80) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def scan_private(text: Any) -> list[dict]:
    """What in `text` looks private: [{"kind", "text"}], at most 20, never more than one per exact match. It
    only informs: the owner decides. A key is shown by its first characters, so the warning never repeats a
    whole secret."""
    t = str(text or "")
    out: list[dict] = []
    taken: list[tuple[int, int]] = []

    def add(kind: str, m: "re.Match[str]", shown: Optional[str] = None) -> None:
        if len(out) >= FLAGS_MAX:
            return
        if any(m.start() < b and a < m.end() for a, b in taken):   # a URL's token is one finding, not three
            return
        taken.append((m.start(), m.end()))
        item = {"kind": kind, "text": shown if shown is not None else _short(m.group(0))}
        if item not in out:
            out.append(item)

    for m in _URL_SECRET.finditer(t):
        add("url_secret", m)
    for m in _KEYS.finditer(t):
        add("key", m, m.group(0)[:8] + "…")
    for m in _EMAIL.finditer(t):
        add("email", m)
    for m in _HOME.finditer(t):
        add("home_path", m)
    for m in _IPV4.finditer(t):
        add("ip", m)
    for m in _ADDRESS.finditer(t):
        add("address", m)
    for m in _PHONE.finditer(t):
        if 10 <= sum(ch.isdigit() for ch in m.group(0)) <= 15:
            add("phone", m)
    for ln in t.split("\n"):
        if _SENSITIVE_LINE.search(ln) and len(out) < FLAGS_MAX:
            item = {"kind": "sensitive_line", "text": _short(ln.strip())}
            if item not in out:
                out.append(item)
    out.sort(key=lambda f: _KIND_ORDER.index(f["kind"]))
    return out[:FLAGS_MAX]


# --- Hermes profiles (read only) ---------------------------------------------------------------------

def default_home() -> Path:
    """The default Hermes home (the one that holds `profiles/`)."""
    try:
        from hermes_constants import get_default_hermes_root
        return Path(get_default_hermes_root())
    except Exception:
        pass
    env = os.environ.get("HERMES_HOME")
    if env:
        p = Path(env)
        return p.parent.parent if p.parent.name == "profiles" else p
    return Path.home() / ".hermes"


def _yaml_value(text: str, key: str) -> str:
    """One top-level `key: value` from profile.yaml, without a YAML parser (no new packages)."""
    m = re.search(r"^" + re.escape(key) + r"[ \t]*:[ \t]*(.*)$", text, re.M)
    if not m:
        return ""
    parts = [m.group(1).strip()]
    for ln in text[m.end():].split("\n")[1:]:      # a long value wraps onto indented lines; YAML folds them to spaces
        if not ln.strip() or ln[0] not in " \t":
            break
        parts.append(ln.strip())
    v = " ".join(p for p in parts if p)
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        q = v[0]
        v = v[1:-1]
        if q == "'":
            v = v.replace("''", "'")
    return v.strip()


def _read_small(path: Path, cap: int) -> str:
    try:
        if not path.is_file():
            return ""
        with open(path, "rb") as f:
            return f.read(cap).decode("utf-8", "replace")
    except OSError:
        return ""


# Hermes's own rule for what counts as a profile folder (its profiles module `_iter_named_profile_dirs`,
# and `named_profile_has_identity`), copied here so the plugin imports nothing private.
_PROFILE_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_IDENTITY_MARKERS = ("config.yaml", ".env", "SOUL.md", "profile.yaml", "auth.json", "state.db")


def _has_identity(path: Path) -> bool:
    """A folder is a profile only if it holds one of Hermes's marker files (a dangling symlink counts)."""
    try:
        return any((path / m).is_file() or (path / m).is_symlink() for m in _IDENTITY_MARKERS)
    except OSError:
        return False


def _is_deleted(path: Path) -> bool:
    """`hermes profile delete` leaves a tombstone at profiles/.deleted/<name>."""
    try:
        return (path.parent / ".deleted" / path.name).exists()
    except OSError:
        return False


def _scanned_profiles() -> list[dict]:
    """The profile list, read straight from the folders with Hermes's own membership rule: the default home
    (if it exists), then each folder under `profiles/` with a valid id, an identity marker and no tombstone,
    in sorted order. Folders without a marker (cron/log leftovers, "ghost" shells) are not profiles."""
    home = default_home()
    found = []
    if home.is_dir():
        found.append((home, "default", True))
    root = home / "profiles"
    try:
        entries = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    except OSError:
        entries = []
    found += [(p, p.name, False) for p in entries
              if p.name != "default" and _PROFILE_ID.fullmatch(p.name) and _has_identity(p) and not _is_deleted(p)]
    out = []
    for path, name, is_default in found:
        meta = _read_small(path / "profile.yaml", _PROFILE_YAML_MAX)
        out.append({"name": name, "path": path, "default": is_default,
                    "display_name": _yaml_value(meta, "display_name"), "description": _yaml_value(meta, "description")})
    return out


def _soul_path(path: Path) -> Path:
    return path / "SOUL.md"


def _has_personality(path: Path) -> bool:
    try:
        p = _soul_path(path)
        return p.is_file() and p.stat().st_size > 0   # size only: the list never reads a file's contents
    except OSError:
        return False


def profile_records() -> list[dict]:
    """Hermes's profiles with their paths (internal), from a read-only scan of the Hermes home."""
    seen, out = set(), []
    for r in _scanned_profiles():
        if r["name"] not in seen:
            seen.add(r["name"])
            out.append(r)
    return out


def list_profiles(current: Optional[str]) -> list[dict]:
    """What the picker shows: name, display name, description, whether there is a personality, and whether
    Ninsei runs in this one. No file contents."""
    return [{"name": r["name"], "display_name": r["display_name"][:64], "description": r["description"][:200],
             "has_personality": _has_personality(r["path"]), "current": r["name"] == current,
             "is_default": r["default"]} for r in profile_records()]


def read_soul(path: Path) -> str:
    """`SOUL.md` of a profile, at most 64 KB, and only if it really sits inside that profile's folder (a
    symlink out of it reads as empty)."""
    p = _soul_path(path)
    try:
        if not p.resolve().is_relative_to(path.resolve()):
            return ""
    except OSError:
        return ""
    return _read_small(p, SOUL_READ_MAX).lstrip("\ufeff")


_YOU_ARE = re.compile(
    r"^[ \t]*(?:#+[ \t]*)?(?i:you are|you're)[ \t]+[*_]*([A-Z][^\n,.*_]*?)[*_]*[ \t]*(?:,|\.|[ \t]+built by\b|$)",
    re.M)


def soul_name(soul: str) -> str:
    """A name from a leading "You are <Name>" (to a comma, a period or " built by"), else "". Only a short
    capitalised name counts: "You are A careful assistant" is a description, not a name."""
    m = _YOU_ARE.search(soul[:600])
    if not m:
        return ""
    name = m.group(1).strip()
    words = name.split()
    if not words or len(words) > 3 or words[0].lower() in ("a", "an", "the"):
        return ""
    return name


def fallback_name(profile: str) -> str:
    return re.sub(r"[-_]+", " ", profile).strip().title()
