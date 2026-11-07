"""Profile pictures from strangers (ninsei_engine/avatar.py): every check on its own, with images built by hand
(there is no image library here, and the checks parse headers themselves)."""
import base64
import struct
import zlib

import pytest

from ninsei_engine import avatar
from ninsei_engine.avatar import MAX_BYTES, check_avatar, data_uri, find_metadata


# --- builders: just enough structure for the header walkers -------------------------------------------

def png_chunk(typ: bytes, body: bytes = b"") -> bytes:
    return struct.pack(">I", len(body)) + typ + body + struct.pack(">I", zlib.crc32(typ + body) & 0xFFFFFFFF)


def png(w=64, h=64, extra=(), idat=None, after=b"", iend=True) -> bytes:
    ihdr = png_chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    idat = png_chunk(b"IDAT", zlib.compress(b"\x00" * 30) if idat is None else idat)
    return avatar.PNG_SIG + ihdr + b"".join(png_chunk(t, b) for t, b in extra) + idat + (png_chunk(b"IEND") if iend else b"") + after


def riff(*chunks: bytes) -> bytes:
    body = b"WEBP" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def wchunk(typ: bytes, body: bytes) -> bytes:
    return typ + struct.pack("<I", len(body)) + body + (b"\x00" if len(body) & 1 else b"")


def vp8(w=64, h=64) -> bytes:
    return wchunk(b"VP8 ", b"\x10\x02\x00" + b"\x9d\x01\x2a" + struct.pack("<HH", w, h) + b"\x00" * 12)


def vp8l(w=64, h=64) -> bytes:
    bits = (w - 1) | ((h - 1) << 14)
    return wchunk(b"VP8L", b"\x2f" + struct.pack("<I", bits) + b"\x00" * 12)


def vp8x(w=64, h=64, flags=0) -> bytes:
    return wchunk(b"VP8X", bytes([flags]) + b"\x00\x00\x00" + (w - 1).to_bytes(3, "little") + (h - 1).to_bytes(3, "little"))


def jpeg(w=64, h=64, extra=(), eoi=True) -> bytes:
    def seg(marker, body):
        return bytes([0xFF, marker]) + struct.pack(">H", len(body) + 2) + body
    sof = seg(0xC0, b"\x08" + struct.pack(">HH", h, w) + b"\x01\x01\x11\x00")
    return (b"\xff\xd8" + seg(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00") + b"".join(seg(m, b) for m, b in extra)
            + seg(0xDB, b"\x00" + b"\x10" * 64) + sof + seg(0xC4, b"\x00" + b"\x00" * 16 + b"\x00")
            + seg(0xDA, b"\x01\x01\x00\x00\x3f\x00") + b"\x12\x34\x56\x78" * 4 + (b"\xff\xd9" if eoi else b""))


def uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


GOOD = {"image/png": png(), "image/jpeg": jpeg(), "image/webp": riff(vp8l())}


# --- good pictures ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("mime", sorted(GOOD))
def test_a_well_formed_picture_of_each_allowed_type_passes(mime):
    got = check_avatar(uri(GOOD[mime], mime))
    assert got == (mime, GOOD[mime])
    assert check_avatar(data_uri(*got)) == got   # the canonical URI the UI is given reads back the same


def test_every_webp_flavour_passes():
    for body in (riff(vp8()), riff(vp8l()), riff(vp8x(64, 64), vp8l(64, 64)), riff(vp8x(64, 64, 0x10), vp8(64, 64), wchunk(b"ALPH", b"\x00" * 3))):
        assert check_avatar(uri(body, "image/webp")) is not None


def test_dimensions_are_read_from_the_header_and_may_be_up_to_512():
    assert avatar.read_image(png(512, 512), "image/png")[:2] == (512, 512)
    assert avatar.read_image(riff(vp8(300, 200)), "image/webp")[:2] == (300, 200)
    assert avatar.read_image(riff(vp8l(7, 512)), "image/webp")[:2] == (7, 512)
    assert avatar.read_image(jpeg(1, 400), "image/jpeg")[:2] == (1, 400)


# --- the prefix: only webp, jpeg and png ------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "data:image/svg+xml;base64," + base64.b64encode(b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>").decode(),
    "data:image/svg+xml;utf8,<svg/>", "data:image/gif;base64," + base64.b64encode(b"GIF89a" + b"\0" * 30).decode(),
    "data:image/jpg;base64," + base64.b64encode(jpeg()).decode(),                 # not the registered type name
    "data:image/png;charset=utf-8;base64," + base64.b64encode(png()).decode(),     # nothing may follow the type
    "data:image/PNG;base64," + base64.b64encode(png()).decode(),
    "DATA:image/png;base64," + base64.b64encode(png()).decode(),
    " data:image/png;base64," + base64.b64encode(png()).decode(),
    "data:text/html;base64," + base64.b64encode(b"<script>x</script>" + b"\0" * 20).decode(),
    "data:image/png," + "x" * 40, "https://example.com/a.png", "javascript:alert(1)", "//evil/a.png", "", "data:", "data:image/png;base64,",
])
def test_other_types_urls_and_scripts_are_refused_by_the_prefix(bad):
    assert check_avatar(bad) is None


@pytest.mark.parametrize("bad", [None, 5, 1.5, True, {}, [], ["data:image/png;base64,AAAA"], b"data:image/png;base64,AAAA", {"img": "x"}])
def test_anything_that_is_not_a_string_is_refused(bad):
    assert check_avatar(bad) is None


# --- base64, size ------------------------------------------------------------------------------------------

def test_bad_base64_is_refused():
    good = base64.b64encode(png()).decode()
    p = "data:image/png;base64,"
    assert check_avatar(p + good) is not None
    assert check_avatar(p + good[:-1]) is None                 # unpadded or cut
    assert check_avatar(p + good + "=") is None
    assert check_avatar(p + good[:10] + "!" + good[11:]) is None
    assert check_avatar(p + good[:8] + "\n" + good[8:]) is None   # whitespace the decoder would skip
    assert check_avatar(p + good[:8] + " " + good[8:]) is None
    assert check_avatar(p + "é" * 40) is None
    # the same bytes spelled with different bits in the padding are not the canonical spelling
    raw = next(r for r in (png(idat=zlib.compress(b"\x00" * 30) + b"\x00" * k) for k in range(3)) if len(r) % 3)
    enc = base64.b64encode(raw).decode()
    i = len(enc.rstrip("="))
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    twisted = enc[:i - 1] + alphabet[alphabet.index(enc[i - 1]) ^ 1] + enc[i:]
    assert twisted != enc and base64.b64decode(twisted) == raw
    assert check_avatar(p + enc) is not None and check_avatar(p + twisted) is None


def test_oversize_pictures_are_refused_before_and_after_decoding():
    big = png(idat=zlib.compress(b"\x01\x02\x03" * 1) + bytes(range(256)) * 200)   # an IDAT of ~50 KB of noise
    assert len(big) > MAX_BYTES
    assert check_avatar(uri(big, "image/png")) is None
    edge = png(idat=bytes(range(256)) * ((MAX_BYTES - 100) // 256))
    assert len(edge) <= MAX_BYTES and check_avatar(uri(edge, "image/png")) is not None
    assert check_avatar("data:image/png;base64," + "A" * 2_000_000) is None     # refused on length alone
    assert check_avatar(uri(b"\x89PNG", "image/png")) is None                    # and tiny ones


# --- magic bytes and structure -------------------------------------------------------------------------------

def test_the_declared_type_must_match_the_bytes():
    for have in GOOD:
        for declared in GOOD:
            assert (check_avatar(uri(GOOD[have], declared)) is not None) == (have == declared)
    assert check_avatar(uri(b"GIF89a" + b"\0" * 40, "image/png")) is None
    assert check_avatar(uri(b"<svg xmlns='http://www.w3.org/2000/svg'/>" + b" " * 20, "image/webp")) is None


@pytest.mark.parametrize("w,h", [(513, 64), (64, 513), (4000, 4000), (0, 64), (64, 0), (2 ** 31, 2 ** 31), (65535, 65535)])
def test_dimensions_beyond_512_or_zero_in_the_png_header_are_refused(w, h):
    assert check_avatar(uri(png(w, h), "image/png")) is None


@pytest.mark.parametrize("w,h", [(513, 64), (64, 513), (16383, 16383), (4096, 4096)])
def test_dimensions_beyond_512_in_a_webp_header_are_refused(w, h):
    for body in (riff(vp8(w, h)), riff(vp8l(w, h)), riff(vp8x(w, h), vp8l(w, h))):
        assert check_avatar(uri(body, "image/webp")) is None


@pytest.mark.parametrize("w,h", [(513, 64), (64, 513), (65535, 65535), (0, 10)])
def test_dimensions_beyond_512_in_a_jpeg_header_are_refused(w, h):
    assert check_avatar(uri(jpeg(w, h), "image/jpeg")) is None


def test_a_webp_canvas_that_disagrees_with_its_image_is_refused():
    assert check_avatar(uri(riff(vp8x(64, 64), vp8l(65, 64)), "image/webp")) is None
    assert check_avatar(uri(riff(vp8x(4000, 4000), vp8l(64, 64)), "image/webp")) is None


def test_structure_that_does_not_hold_together_is_refused():
    # a PNG: wrong CRC, no IEND, trailing bytes, a second IHDR, no IDAT, truncated
    ok = png()
    assert check_avatar(uri(ok[:40] + bytes([ok[40] ^ 1]) + ok[41:], "image/png")) is None
    assert check_avatar(uri(png(iend=False), "image/png")) is None
    assert check_avatar(uri(png(after=b"<?php ?>"), "image/png")) is None
    assert check_avatar(uri(ok[:-9], "image/png")) is None
    assert check_avatar(uri(png(extra=[(b"IHDR", b"\0" * 13)]), "image/png")) is None
    # a WebP: wrong RIFF size, trailing bytes, cut short, not a RIFF at all
    w = riff(vp8l())
    assert check_avatar(uri(w + b"\x00", "image/webp")) is None
    assert check_avatar(uri(w[:-3], "image/webp")) is None
    assert check_avatar(uri(w[:4] + struct.pack("<I", 5) + w[8:], "image/webp")) is None
    assert check_avatar(uri(b"RIFX" + w[4:], "image/webp")) is None
    assert check_avatar(uri(riff(wchunk(b"EXIF", b"\0" * 30)), "image/webp")) is None   # no image chunk
    # a JPEG: no end marker, trailing bytes, no frame header, a segment that runs past the end
    j = jpeg()
    assert check_avatar(uri(jpeg(eoi=False), "image/jpeg")) is None
    assert check_avatar(uri(j + b"zzzz", "image/jpeg")) is None
    assert check_avatar(uri(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 30 + b"\xff\xd9", "image/jpeg")) is None
    assert check_avatar(uri(b"\xff\xd8\xff\xe0\xff\xf0" + b"\x00" * 30 + b"\xff\xd9", "image/jpeg")) is None


def test_animation_is_refused():
    assert check_avatar(uri(png(extra=[(b"acTL", b"\0" * 8)]), "image/png")) is None                       # APNG
    assert check_avatar(uri(riff(vp8x(64, 64, 0x02), vp8l()), "image/webp")) is None                     # animation flag
    assert check_avatar(uri(riff(vp8x(64, 64), wchunk(b"ANIM", b"\0" * 6), wchunk(b"ANMF", b"\0" * 20)), "image/webp")) is None


# --- metadata, on the sender's side ----------------------------------------------------------------------------

def test_a_picture_with_metadata_is_found_before_it_is_published():
    assert find_metadata(png(), "image/png") is None and find_metadata(riff(vp8l()), "image/webp") is None and find_metadata(jpeg(), "image/jpeg") is None
    assert find_metadata(png(extra=[(b"eXIf", b"MM\0*" + b"\0" * 10)]), "image/png") == "eXIf"
    assert find_metadata(png(extra=[(b"tEXt", b"GPS\0here")]), "image/png") == "tEXt"
    assert find_metadata(jpeg(extra=[(0xE1, b"Exif\0\0MM\0*" + b"\0" * 10)]), "image/jpeg") == "EXIF or XMP"
    assert find_metadata(jpeg(extra=[(0xED, b"Photoshop 3.0\0")]), "image/jpeg") == "IPTC"
    assert find_metadata(jpeg(extra=[(0xFE, b"made at home")]), "image/jpeg") == "a comment"
    assert find_metadata(riff(vp8x(64, 64, 0x08), vp8l(), wchunk(b"EXIF", b"MM\0*" + b"\0" * 10)), "image/webp") == "EXIF"
    assert find_metadata(riff(vp8x(64, 64, 0x04), vp8l(), wchunk(b"XMP ", b"<x/>")), "image/webp") == "XMP"
    assert find_metadata(b"nonsense", "image/png") is not None
    # a colour profile alone is not a privacy leak
    assert find_metadata(jpeg(extra=[(0xE2, b"ICC_PROFILE\0\1\1" + b"\0" * 20)]), "image/jpeg") is None
    # a picture with metadata still passes the RECEIVING checks (only the sender refuses it)
    assert check_avatar(uri(png(extra=[(b"tEXt", b"GPS\0here")]), "image/png")) is not None
