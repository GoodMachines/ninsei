"""NIP-44 v2 encryption (https://github.com/nostr-protocol/nips/blob/master/44.md), pure Python.

Hermes ships no crypto library, so this uses only the standard library and nostr.py's secp256k1:
ECDH (shared x-coordinate), HKDF-SHA256, ChaCha20 (RFC 8439), HMAC-SHA256 over nonce + ciphertext, the
NIP-44 padding and a base64 payload with version byte 2. Tests check it against the official vectors
(tests/data/nip44_vectors.json) and the RFC 8439 ChaCha20 vectors.

Ninsei encrypts game answers to the host's agent key. Messages are short, so speed doesn't matter.
Plaintexts are capped at 65535 bytes (the spec lets an implementation set its own maximum): this module
never writes or accepts the extended 6-byte length prefix.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import struct
from functools import lru_cache

from . import nostr

VERSION = 2
MIN_PLAINTEXT = 1
MAX_PLAINTEXT = 65535
MIN_PAYLOAD = 132                               # base64 chars, before decoding (spec: DoS guard)
MAX_DATA = 1 + 32 + 2 + 65536 + 32               # version, nonce, u16 prefix + padded 65535 bytes, MAC
MAX_PAYLOAD = 4 * -(-MAX_DATA // 3)              # the same, in base64 chars
_SALT = b"nip44-v2"


class Nip44Error(ValueError):
    """Any reason a payload can't be made or read: bad key, version, length, padding or MAC."""


# --- primitives ---------------------------------------------------------------------------------

def _hkdf_extract(ikm: bytes, salt: bytes) -> bytes:
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def _hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    out, block, i = b"", b"", 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([i]), hashlib.sha256).digest()
        out += block
        i += 1
    return out[:length]


_M32 = 0xFFFFFFFF


def _rotl(v: int, c: int) -> int:
    return ((v << c) & _M32) | (v >> (32 - c))


def _quarter(s: list, a: int, b: int, c: int, d: int) -> None:
    s[a] = (s[a] + s[b]) & _M32
    s[d] = _rotl(s[d] ^ s[a], 16)
    s[c] = (s[c] + s[d]) & _M32
    s[b] = _rotl(s[b] ^ s[c], 12)
    s[a] = (s[a] + s[b]) & _M32
    s[d] = _rotl(s[d] ^ s[a], 8)
    s[c] = (s[c] + s[d]) & _M32
    s[b] = _rotl(s[b] ^ s[c], 7)


def chacha20_block(key: bytes, counter: int, nonce: bytes) -> bytes:
    """RFC 8439 section 2.3: one 64-byte keystream block."""
    if len(key) != 32 or len(nonce) != 12 or not 0 <= counter <= _M32:
        raise Nip44Error("bad chacha20 key, nonce or counter")
    init = [0x61707865, 0x3320646E, 0x79622D32, 0x6B206574, *struct.unpack("<8I", key), counter,
            *struct.unpack("<3I", nonce)]
    s = list(init)
    for _ in range(10):
        _quarter(s, 0, 4, 8, 12)
        _quarter(s, 1, 5, 9, 13)
        _quarter(s, 2, 6, 10, 14)
        _quarter(s, 3, 7, 11, 15)
        _quarter(s, 0, 5, 10, 15)
        _quarter(s, 1, 6, 11, 12)
        _quarter(s, 2, 7, 8, 13)
        _quarter(s, 3, 4, 9, 14)
    return struct.pack("<16I", *((x + y) & _M32 for x, y in zip(s, init)))


def chacha20(key: bytes, nonce: bytes, data: bytes, counter: int = 0) -> bytes:
    """RFC 8439 section 2.4: XOR data with the keystream. NIP-44 starts the counter at 0."""
    out = bytearray(len(data))
    for i in range(0, len(data), 64):
        block = chacha20_block(key, counter + i // 64, nonce)
        chunk = data[i:i + 64]
        out[i:i + len(chunk)] = bytes(x ^ y for x, y in zip(chunk, block))
    return bytes(out)


# --- NIP-44 v2 ----------------------------------------------------------------------------------

def calc_padded_len(unpadded_len: int) -> int:
    if unpadded_len <= 32:
        return 32
    next_power = 1 << ((unpadded_len - 1).bit_length())   # 1 << (floor(log2(len - 1)) + 1)
    chunk = 32 if next_power <= 256 else next_power // 8
    return chunk * ((unpadded_len - 1) // chunk + 1)


def _pad(plaintext: str) -> bytes:
    raw = plaintext.encode("utf-8")
    if not MIN_PLAINTEXT <= len(raw) <= MAX_PLAINTEXT:
        raise Nip44Error("invalid plaintext length")
    return struct.pack(">H", len(raw)) + raw + bytes(calc_padded_len(len(raw)) - len(raw))


def _unpad(padded: bytes) -> str:
    if len(padded) < 2:
        raise Nip44Error("invalid padding")
    n = struct.unpack(">H", padded[:2])[0]
    body = padded[2:2 + n]
    if n == 0 or len(body) != n or len(padded) != 2 + calc_padded_len(n):
        raise Nip44Error("invalid padding")   # a zero prefix (extended format) lands here too: not accepted
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        raise Nip44Error("invalid utf-8") from None


def _secret_int(sk_hex: str) -> int:
    if not nostr.is_hex(sk_hex, 32):
        raise Nip44Error("invalid private key")
    d = int(sk_hex, 16)
    if not 1 <= d <= nostr.N - 1:
        raise Nip44Error("invalid private key")
    return d


@lru_cache(maxsize=256)
def _conversation_key_cached(sk_hex: str, pk_hex: str) -> bytes:
    d = _secret_int(sk_hex)
    if not nostr.is_hex(pk_hex, 32):
        raise Nip44Error("invalid public key")
    pt = nostr._lift_x(int(pk_hex, 16))
    if pt is None or pt[0] == 0:
        raise Nip44Error("invalid public key")   # not on the curve (twist points, no square root)
    shared = nostr.point_mul(pt, d)
    if shared is None:
        raise Nip44Error("invalid shared point")
    return _hkdf_extract(shared[0].to_bytes(32, "big"), _SALT)


def conversation_key(sk_hex: str, pk_hex: str) -> bytes:
    """conv(a, B) == conv(b, A). Cached: each is a pure-Python scalar multiply, and views ask often."""
    if not isinstance(sk_hex, str) or not isinstance(pk_hex, str):
        raise Nip44Error("keys must be hex strings")
    return _conversation_key_cached(sk_hex, pk_hex)


def message_keys(conv_key: bytes, nonce: bytes) -> tuple[bytes, bytes, bytes]:
    if len(conv_key) != 32:
        raise Nip44Error("invalid conversation_key length")
    if len(nonce) != 32:
        raise Nip44Error("invalid nonce length")
    keys = _hkdf_expand(conv_key, nonce, 76)
    return keys[0:32], keys[32:44], keys[44:76]


def _mac(key: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    if len(nonce) != 32:
        raise Nip44Error("AAD must be 32 bytes")
    return hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()


def encrypt(plaintext: str, conv_key: bytes, nonce: bytes | None = None) -> str:
    """The base64 payload. `nonce` is for test vectors only: leave it out and a fresh random one is used."""
    nonce = secrets.token_bytes(32) if nonce is None else nonce
    ck, cn, hk = message_keys(conv_key, nonce)
    ciphertext = chacha20(ck, cn, _pad(plaintext))
    return base64.b64encode(bytes([VERSION]) + nonce + ciphertext + _mac(hk, nonce, ciphertext)).decode("ascii")


def _decode_payload(payload) -> tuple[bytes, bytes, bytes]:
    if not isinstance(payload, str) or not payload or payload[0] == "#":
        raise Nip44Error("unknown encryption version")
    if not MIN_PAYLOAD <= len(payload) <= MAX_PAYLOAD:
        raise Nip44Error("invalid payload size")
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise Nip44Error("invalid base64") from None
    if not 99 <= len(data) <= MAX_DATA:
        raise Nip44Error("invalid data size")
    if data[0] != VERSION:
        raise Nip44Error(f"unknown encryption version {data[0]}")
    return data[1:33], data[33:-32], data[-32:]


def decrypt(payload: str, conv_key: bytes) -> str:
    nonce, ciphertext, mac = _decode_payload(payload)
    ck, cn, hk = message_keys(conv_key, nonce)
    if not hmac.compare_digest(_mac(hk, nonce, ciphertext), mac):
        raise Nip44Error("invalid MAC")
    return _unpad(chacha20(ck, cn, ciphertext))
