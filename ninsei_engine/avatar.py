"""Profile pictures from strangers: validation by hand, with no image library and no new package.

A picture reaches every viewer's screen as the bytes of an <img>, supplied by someone we have never met, so
nothing is stored or shown until it passes every check here. `check_avatar` takes the data URI a picture event
carries and returns `(mime, bytes)`, or None for anything it does not fully understand (dropped silently).

What is checked: the data-URI prefix (webp, jpeg or png only, nothing after the type), strict base64, the
decoded size, the declared type against the magic bytes, the structure of the file (PNG chunks with their CRCs
up to IEND, WebP RIFF chunks, JPEG segments up to the frame header and an end marker), and the width and height
read from the header (at most MAX_DIM). Animation is refused (an APNG or animated WebP). SVG and every other type
are refused by the prefix check alone.

These checks cannot promise that a decoder will not choke on a deliberately malformed stream (libwebp's 2023
lossless-decoder bug is the reminder): that is why the Settings switch "Show profile pictures: Nobody" exists, and
why a picture is only ever drawn through <img>, never inlined.

`find_metadata` is for the sender's own side: the engine refuses to publish a picture that still carries EXIF,
XMP, IPTC or text chunks, so a photo's GPS position never goes out even if a client skipped the
re-encode the UI always does (a canvas redraw keeps pixels only).
"""
from __future__ import annotations

import base64
import binascii
import struct
import zlib
from typing import Optional

MAX_BYTES = 48 * 1024        # decoded image bytes
MAX_DIM = 512                # width and height, from the file's own header
MAX_URI = 4 * ((MAX_BYTES + 2) // 3) + 40   # the longest legal data URI, so oversize is refused before decoding
MIN_BYTES = 20
PREFIXES = {"data:image/webp;base64,": "image/webp", "data:image/jpeg;base64,": "image/jpeg",
            "data:image/png;base64,": "image/png"}

PNG_SIG = b"\x89PNG\r\n\x1a\n"
# parts that carry metadata a photo can hold (EXIF with its GPS position, XMP, IPTC, text, a time), refused on
# the sender's side
_PNG_META = {b"eXIf", b"tEXt", b"iTXt", b"zTXt", b"tIME"}
_WEBP_META = {b"EXIF", b"XMP "}
_JPEG_META = {0xE1: "EXIF or XMP", 0xED: "IPTC", 0xFE: "a comment"}


def _png_dims(b: bytes) -> Optional[tuple[int, int, set]]:
    """(width, height, chunk types) of a PNG whose chunks all fit, whose CRCs hold, whose first is a 13-byte
    IHDR and whose last is an IEND with nothing after it. None otherwise."""
    if not b.startswith(PNG_SIG):
        return None
    pos, n, seen, first = len(PNG_SIG), len(b), set(), True
    w = h = 0
    while pos + 12 <= n:
        (size,) = struct.unpack(">I", b[pos:pos + 4])
        typ = b[pos + 4:pos + 8]
        end = pos + 8 + size
        if size > n or end + 4 > n or not typ.isalpha():
            return None
        if struct.unpack(">I", b[end:end + 4])[0] != zlib.crc32(b[pos + 4:end]) & 0xFFFFFFFF:
            return None
        if first:
            if typ != b"IHDR" or size != 13:
                return None
            w, h = struct.unpack(">II", b[pos + 8:pos + 16])
            first = False
        elif typ == b"IHDR" or typ == b"acTL":   # a second header, or an animation
            return None
        seen.add(typ)
        pos = end + 4
        if typ == b"IEND":
            return (w, h, seen) if size == 0 and pos == n and b"IDAT" in seen else None
    return None


def _webp_dims(b: bytes) -> Optional[tuple[int, int, set]]:
    """(width, height, chunk types) of a still WebP: RIFF size exact, chunks walked to the end, and the image
    chunk's own dimensions (VP8 lossy, VP8L lossless, or VP8X's canvas plus its image) read by hand."""
    if len(b) < 20 or b[:4] != b"RIFF" or b[8:12] != b"WEBP":
        return None
    if struct.unpack("<I", b[4:8])[0] + 8 != len(b):
        return None
    pos, n, seen = 12, len(b), set()
    canvas: Optional[tuple[int, int]] = None
    image: Optional[tuple[int, int]] = None
    while pos < n:
        if pos + 8 > n:
            return None
        typ = b[pos:pos + 4]
        (size,) = struct.unpack("<I", b[pos + 4:pos + 8])
        body = b[pos + 8:pos + 8 + size]
        if len(body) != size or typ in (b"ANIM", b"ANMF"):
            return None
        if not seen and typ == b"VP8X":
            if size < 10 or body[0] & 0x02:      # animation flag
                return None
            canvas = (int.from_bytes(body[4:7], "little") + 1, int.from_bytes(body[7:10], "little") + 1)
        elif typ == b"VP8 " and image is None:
            if size < 10 or body[3:6] != b"\x9d\x01\x2a" or body[0] & 1:   # start code; bit 0 clear = a key frame
                return None
            image = (struct.unpack("<H", body[6:8])[0] & 0x3FFF, struct.unpack("<H", body[8:10])[0] & 0x3FFF)
        elif typ == b"VP8L" and image is None:
            if size < 5 or body[0] != 0x2F:
                return None
            bits = int.from_bytes(body[1:5], "little")
            image = ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        seen.add(typ)
        pos += 8 + size + (size & 1)        # chunks are padded to an even size
    if pos != n or image is None:
        return None
    if canvas is not None and canvas != image:
        return None
    return image[0], image[1], seen


_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _jpeg_dims(b: bytes) -> Optional[tuple[int, int, set]]:
    """(width, height, marker numbers seen) of a JPEG: segments walked from SOI to the scan, a frame header
    found on the way, and the end-of-image marker last."""
    if len(b) < 4 or b[:3] != b"\xff\xd8\xff" or b[-2:] != b"\xff\xd9":
        return None
    pos, n, seen = 2, len(b), set()
    dims: Optional[tuple[int, int]] = None
    while pos + 4 <= n:
        if b[pos] != 0xFF:
            return None
        marker = b[pos + 1]
        if marker == 0xFF:                  # fill byte
            pos += 1
            continue
        if marker == 0x00 or marker == 0xD8:
            return None
        (size,) = struct.unpack(">H", b[pos + 2:pos + 4])
        if size < 2 or pos + 2 + size > n:
            return None
        seen.add(marker)
        if marker in _SOF:
            if size < 8:
                return None
            if dims is not None:
                return None
            h, w = struct.unpack(">HH", b[pos + 5:pos + 9])
            dims = (w, h)
        if marker == 0xDA:                  # the scan: entropy-coded data follows, up to the end marker
            return (dims[0], dims[1], seen) if dims else None
        pos += 2 + size
    return None


_READERS = {"image/png": _png_dims, "image/webp": _webp_dims, "image/jpeg": _jpeg_dims}


def read_image(data: bytes, mime: str) -> Optional[tuple[int, int, set]]:
    """(width, height, parts seen) when `data` is a well-formed still image of the declared type and at most
    MAX_DIM square, else None. The declared type must be the one the magic bytes show."""
    reader = _READERS.get(mime)
    if reader is None or not isinstance(data, (bytes, bytearray)) or not (MIN_BYTES <= len(data) <= MAX_BYTES):
        return None
    got = reader(bytes(data))
    if got is None or not (1 <= got[0] <= MAX_DIM and 1 <= got[1] <= MAX_DIM):
        return None
    return got


def check_avatar(uri) -> Optional[tuple[str, bytes]]:
    """A picture event's data URI -> (mime, bytes) when every check passes, else None."""
    if not isinstance(uri, str) or len(uri) > MAX_URI:
        return None
    for prefix, mime in PREFIXES.items():
        if uri.startswith(prefix):
            body = uri[len(prefix):]
            break
    else:
        return None
    if not body or not body.isascii() or len(body) > MAX_URI or len(body) % 4:
        return None
    try:
        data = base64.b64decode(body, validate=True)
    except (binascii.Error, ValueError):
        return None
    if base64.b64encode(data).decode("ascii") != body:   # no stray bits in the padding, no alternate spellings
        return None
    return (mime, data) if read_image(data, mime) else None


def data_uri(mime: str, data: bytes) -> str:
    """The canonical data URI for validated bytes: what the UI is given, never the stranger's own string."""
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def find_metadata(data: bytes, mime: str) -> Optional[str]:
    """For a picture I am about to publish: the name of a metadata part it still carries, or None. A canvas
    re-encode keeps none, so this only ever stops a picture that skipped the re-encode. (A colour profile is
    not refused: it says nothing about where or with what the picture was taken.)"""
    got = read_image(data, mime)
    if got is None:
        return "not a picture Ninsei can read"
    parts = got[2]
    if mime == "image/jpeg":
        for marker, name in _JPEG_META.items():
            if marker in parts:
                return name
        return None
    meta = _PNG_META if mime == "image/png" else _WEBP_META
    for typ in sorted(parts & meta):
        return typ.decode("ascii").strip()
    return None
