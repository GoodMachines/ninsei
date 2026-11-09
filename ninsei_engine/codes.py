"""Where a room lives: the relay hosts a room code and a room invite may carry.

A code is `ninsei:<room>` or `ninsei:<room>@host,host#<event>`, an invite carries the same hosts as `relay` tags
(`wss://host`). Both are a stranger's text, pasted from anywhere, so a host has to pass the same strict check wherever
it is read. Connecting to a relay shows it your IP address, so a code never connects anywhere by itself: the Join
preview lists the hosts you don't use yet and waits for a press.

Pure functions of their input (no clock, no storage, no network), shared by the engine, `dm.py` and the tests.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

MAX_CODE_HOSTS = 3          # relay hosts one code or invite carries
MAX_HOST = 253              # characters of one host (a DNS name's own limit), with or without its port

# Suffixes that never name a public relay: the machine itself or a private network. A code is pasted from anywhere,
# and it must not aim your install at your own network (`wss://printer.local`, `wss://nas.lan`).
_PRIVATE_SUFFIXES = frozenset({
    "localhost", "local", "localdomain", "internal", "lan", "home", "corp", "intranet", "private", "arpa", "onion",
    "invalid", "test", "example"})
# What "trimming" a pasted code means, spelled out so the page (ui/00_core.js `trimCode`) can use the very same set: Python's
# str.strip() also removes U+001C-U+001F and U+0085 but not U+FEFF, JavaScript's .trim() the reverse. Whitespace plus
# U+FEFF (a byte order mark pasted in front of a code), nothing else; a control character left after that is refused.
TRIM_CHARS = ("\t\n\x0b\x0c\r \xa0\u1680" + "".join(chr(c) for c in range(0x2000, 0x200B))
              + "\u2028\u2029\u202f\u205f\u3000\ufeff")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_TLD = re.compile(r"[a-z]{2,63}|xn--[a-z0-9-]{1,59}")   # real TLDs are letters: this refuses 1.2.3.4, 127.1 and 0x7f.0x1


def trim(text: Any) -> str:
    """`text` without the whitespace and byte order marks at either end (TRIM_CHARS); `""` for anything but text."""
    return text.strip(TRIM_CHARS) if isinstance(text, str) else ""


def clean_host(host: Any) -> Optional[str]:
    """`host` or `host:port` lowercased, or None. A host is dotted DNS labels (letters, digits and hyphens), at most
    253 characters, with a lettered top-level name that is not a private or local one, and an optional port (1-65535).
    IP addresses of any spelling, `localhost`, anything with a path, a user, brackets or a scheme fail."""
    if not isinstance(host, str):
        return None
    h = host.lower()
    if not h or len(h) > MAX_HOST or h.count(":") > 1 or _CONTROL.search(h):
        return None
    name, _, port = h.partition(":")
    if ":" in h and not (port.isascii() and port.isdigit() and 1 <= len(port) <= 5 and 1 <= int(port) <= 65535):
        return None
    labels = name.split(".")
    if len(labels) < 2 or not all(_LABEL.fullmatch(x) for x in labels[:-1]) or not _TLD.fullmatch(labels[-1]):
        return None
    if labels[-1] in _PRIVATE_SUFFIXES:
        return None
    return h


def clean_hosts(items: Iterable[Any], limit: int = MAX_CODE_HOSTS) -> list[str]:
    """The valid hosts among `items` (each trimmed first, as the page does), in order, without repeats, at most `limit`. A bad
    one is dropped silently."""
    out: list[str] = []
    for x in items:
        h = clean_host(trim(x) if isinstance(x, str) else x)
        if h and h not in out:
            out.append(h)
            if len(out) >= limit:
                break
    return out


def host_url(host: str) -> str:
    """The relay address of a clean host: always `wss://`."""
    return "wss://" + host


def relay_url_host(url: Any) -> Optional[str]:
    """The clean host of `wss://host[:port]` (a trailing slash is fine), else None: a path, `ws://` or a host that
    fails the rules can't be written into a code. A strict form of the same check, for tags and for my own list."""
    if not isinstance(url, str) or not url.startswith("wss://") or len(url) > MAX_HOST + 7:
        return None
    return clean_host(url[6:].rstrip("/")) if "/" not in url[6:].rstrip("/") else None


def clean_relay_tags(tags: Any) -> Optional[list[str]]:
    """The `wss://` URLs in a rumor's `relay` tags, or None when the rumor is malformed: more than MAX_CODE_HOSTS
    `relay` tags, or one that isn't exactly `["relay", "wss://<clean host>"]`. (A rumor with anything odd is dropped
    whole, where a pasted code just loses its bad hosts: the sender of a rumor is an app, a code was typed or edited.)"""
    urls: list[str] = []
    n = 0
    for t in tags:
        if not (isinstance(t, list) and t and t[0] == "relay"):
            continue
        n += 1
        if n > MAX_CODE_HOSTS or len(t) != 2 or not isinstance(t[1], str) or t[1][:6].lower() != "wss://":
            return None
        host = clean_host(t[1][6:])
        if host is None:
            return None
        if host_url(host) not in urls:
            urls.append(host_url(host))
    return urls
