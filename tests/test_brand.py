"""The Black Ice brand pieces stay wired in: the Lobby art, the wordmark, the icons and the theme."""
import base64
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MEDIA = (ROOT / "ui/05_media.js").read_text()


def _lobby_webp() -> bytes:
    m = re.search(r"const LOBBY_ART = 'data:image/webp;base64,([A-Za-z0-9+/=]+)'", MEDIA)
    assert m, "ui/05_media.js must define LOBBY_ART as a WebP data URI"
    return base64.b64decode(m.group(1))


def test_the_lobby_art_is_a_small_webp():
    data = _lobby_webp()
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    assert len(data) < 64 * 1024, "the art rides in both bundles; keep it small"


def test_the_lobby_art_is_up_to_date_with_its_source():
    if not shutil.which("magick"):
        pytest.skip("ImageMagick not installed")
    r = subprocess.run([sys.executable, str(ROOT / "scripts/build_media.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr or r.stdout


def test_hermes_scanner_reads_the_inline_art_as_media():
    hermes = Path.home() / ".hermes/hermes-agent"
    if not (hermes / "tools/plugin_guard_context.py").exists():
        pytest.skip("Hermes not installed here")
    sys.path.insert(0, str(hermes))
    try:
        from tools.plugin_guard_context import is_base64_media
    finally:
        sys.path.remove(str(hermes))
    line = next(l for l in MEDIA.splitlines() if l.startswith("const LOBBY_ART"))
    assert is_base64_media(line)


def test_the_empty_lobby_shows_the_art_with_its_text():
    lobby = (ROOT / "ui/70_lobby.js").read_text()
    assert "art: LOBBY_ART, title: 'No public rooms yet'" in lobby
    tools = (ROOT / "ui/52_tools.js").read_text()
    assert "className: 'h-empty-art', src: props.art, alt: ''" in tools  # decorative: the title carries it


def test_the_wordmark_is_labelled_and_in_the_sidebar():
    parts = (ROOT / "ui/30_parts.js").read_text()
    assert "role: 'img', 'aria-label': 'Ninsei'" in parts
    assert "jsx(Wordmark, { height: 13 })" in (ROOT / "ui/80_app.js").read_text()


def test_hearth_era_icons_and_theme_are_gone():
    tail = (ROOT / "ui/platform/desktop_tail.js").read_text()
    assert "codicon: 'radio-tower'" in tail and "'home'" not in tail
    assert "lamplight" not in tail and "Black Ice" in tail
    assert json.loads((ROOT / "dashboard/manifest.json").read_text())["icon"] == "Zap"
    for f in ("ui/65_cards.js", "ui/80_app.js"):
        assert "name: 'home'" not in (ROOT / f).read_text()
