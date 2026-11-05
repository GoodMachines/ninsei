"""Helpers for shared toys: the CSP every toy renders under, a secret scan for the share dialog,
and the size rules for publishing one."""
from __future__ import annotations

import json
import re

# Applied to every toy before it renders (backend output and, again, in the UI), so a hostile peer's
# HTML can't phone home even after the viewer presses Run. The iframe sandbox is the second layer.
TOY_CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
           "img-src data: blob:; font-src data:")
CSP_META = f'<meta http-equiv="Content-Security-Policy" content="{TOY_CSP}">'

SHARE_SERIALIZED_LIMIT = 48_000   # bytes of serialized event content; relays and peers cap near 64 KB
OFFER_ID_RE = re.compile(r"^[0-9a-f]{64}$")

# Only HTML whitespace may come before the doctype. `\s` would also skip NBSP or a BOM, which the HTML
# parser treats as text: the meta would then land in <body>, where browsers ignore a CSP.
_DOCTYPE = re.compile(r"^[\t\n\f\r ]*<!doctype[^>]*>", re.I)


def inject_csp(html: str) -> str:
    """Put the CSP meta before anything else in the document (after a doctype, so layout mode is kept)."""
    html = html or ""
    m = _DOCTYPE.match(html)
    if m:
        return html[:m.end()] + CSP_META + html[m.end():]
    return CSP_META + html


_SECRET_PATTERNS = [
    ("a private key block (-----BEGIN)", re.compile(r"-----BEGIN")),
    ("an Anthropic-style key (sk-ant-)", re.compile(r"sk-ant-")),
    ("an API key (sk-)", re.compile(r"\bsk-[A-Za-z0-9_-]{8,}")),
    ("a Nostr secret key (nsec1)", re.compile(r"nsec1[0-9a-z]{20,}")),
    ("a GitHub token (ghp_)", re.compile(r"ghp_[A-Za-z0-9]{10,}")),
    ("a Slack token (xox)", re.compile(r"xox[abprs]-?[A-Za-z0-9-]{6,}")),
    ("an AWS key id (AKIA)", re.compile(r"AKIA[0-9A-Z]{12,}")),
    ("a long hex string next to \"key\" or \"token\"",
     re.compile(r"(?:key|token)\W{0,12}[0-9a-fA-F]{32,}|[0-9a-fA-F]{32,}\W{0,12}(?:key|token)", re.I)),
]


def scan_secrets(html: str) -> list[str]:
    """Human-readable names for each secret-looking pattern found in the source."""
    text = html or ""
    return [label for label, rx in _SECRET_PATTERNS if rx.search(text)]


def serialized_size(content: dict) -> int:
    """Bytes the event content will take on the wire (UTF-8, no ASCII escaping)."""
    return len(json.dumps(content, ensure_ascii=False).encode("utf-8"))
