"""Nostr primitives: BIP-340 Schnorr keys and signatures, event building and checking, NIP-13 proof of work.

Pure Python on purpose: Hermes ships no secp256k1 library, and Ninsei signs a handful of events per
minute, so speed doesn't matter. Verification follows BIP-340 exactly (tests use the official vectors).
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from functools import lru_cache
from typing import Any, Iterable, Optional

P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
     0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)

Point = Optional[tuple[int, int]]


# Jacobian coordinates keep scalar multiplication fast enough in pure Python (no modular inverse per add).
def _to_jac(pt):
    return (pt[0], pt[1], 1)


def _from_jac(j) -> Point:
    if j is None or j[2] == 0:
        return None
    zinv = pow(j[2], P - 2, P)
    z2 = zinv * zinv % P
    return (j[0] * z2 % P, j[1] * z2 * zinv % P)


def _jdouble(j):
    if j is None:
        return None
    x, y, z = j
    if y == 0:
        return None
    s = 4 * x * y * y % P
    m = 3 * x * x % P
    nx = (m * m - 2 * s) % P
    ny = (m * (s - nx) - 8 * y * y * y * y) % P
    nz = 2 * y * z % P
    return (nx, ny, nz)


def _jadd(a, b):
    if a is None:
        return b
    if b is None:
        return a
    x1, y1, z1 = a
    x2, y2, z2 = b
    z1z1 = z1 * z1 % P
    z2z2 = z2 * z2 % P
    u1 = x1 * z2z2 % P
    u2 = x2 * z1z1 % P
    s1 = y1 * z2 * z2z2 % P
    s2 = y2 * z1 * z1z1 % P
    if u1 == u2:
        return _jdouble(a) if s1 == s2 else None
    h = (u2 - u1) % P
    r = (s2 - s1) % P
    h2 = h * h % P
    h3 = h * h2 % P
    nx = (r * r - h3 - 2 * u1 * h2) % P
    ny = (r * (u1 * h2 - nx) - s1 * h3) % P
    nz = h * z1 * z2 % P
    return (nx, ny, nz)


def point_mul(pt: Point, k: int) -> Point:
    if pt is None:
        return None
    acc = None
    add = _to_jac(pt)
    while k:
        if k & 1:
            acc = _jadd(acc, add)
        add = _jdouble(add)
        k >>= 1
    return _from_jac(acc)


def point_add(a: Point, b: Point) -> Point:
    return _from_jac(_jadd(_to_jac(a) if a else None, _to_jac(b) if b else None))


def _lift_x(x: int) -> Point:
    if x >= P:
        return None
    y_sq = (pow(x, 3, P) + 7) % P
    y = pow(y_sq, (P + 1) // 4, P)
    if pow(y, 2, P) != y_sq:
        return None
    return (x, y if y % 2 == 0 else P - y)


_HEX = re.compile(r"[0-9a-f]*")


def is_hex(value: Any, nbytes: int) -> bool:
    """Is value canonical NIP-01 hex: lowercase, exactly nbytes long, nothing else? Keys, ids and signatures
    from strangers must pass this before anything compares them: bytes.fromhex also takes uppercase and
    spaces, so a lenient parse would let one key arrive under many spellings (and slip past Hide)."""
    return isinstance(value, str) and len(value) == 2 * nbytes and _HEX.fullmatch(value) is not None


def _tagged(tag: str, msg: bytes) -> bytes:
    th = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(th + th + msg).digest()


def _b(x: int) -> bytes:
    return x.to_bytes(32, "big")


def _i(b: bytes) -> int:
    return int.from_bytes(b, "big")


def new_secret() -> str:
    return _b(secrets.randbelow(N - 1) + 1).hex()


def pubkey(sk_hex: str) -> str:
    pt = point_mul(G, _i(bytes.fromhex(sk_hex)))
    return _b(pt[0]).hex()


def sign(sk_hex: str, msg: bytes, aux: Optional[bytes] = None) -> bytes:
    d0 = _i(bytes.fromhex(sk_hex))
    if not 1 <= d0 <= N - 1:
        raise ValueError("secret key out of range")
    pt = point_mul(G, d0)
    d = d0 if pt[1] % 2 == 0 else N - d0
    aux = secrets.token_bytes(32) if aux is None else aux
    t = _b(d ^ _i(_tagged("BIP0340/aux", aux)))
    k0 = _i(_tagged("BIP0340/nonce", t + _b(pt[0]) + msg)) % N
    if k0 == 0:
        raise ValueError("nonce is zero")
    r = point_mul(G, k0)
    k = k0 if r[1] % 2 == 0 else N - k0
    e = _i(_tagged("BIP0340/challenge", _b(r[0]) + _b(pt[0]) + msg)) % N
    return _b(r[0]) + _b((k + e * d) % N)


def verify(pk_hex: str, msg: bytes, sig: bytes) -> bool:
    if not is_hex(pk_hex, 32) or not isinstance(sig, (bytes, bytearray)) or len(sig) != 64:
        return False
    pk = bytes.fromhex(pk_hex)
    pt = _lift_x(_i(pk))
    r, s = _i(sig[:32]), _i(sig[32:])
    if pt is None or r >= P or s >= N:
        return False
    e = _i(_tagged("BIP0340/challenge", sig[:32] + pk + msg)) % N
    rr = point_add(point_mul(G, s), point_mul(pt, N - e))
    return rr is not None and rr[1] % 2 == 0 and rr[0] == r


# --- events -----------------------------------------------------------------------------------

def _serialize(pk: str, created_at: int, kind: int, tags: list, content: str) -> bytes:
    return json.dumps([0, pk, created_at, kind, tags, content], separators=(",", ":"),
                      ensure_ascii=False).encode()


def event_id(ev: dict) -> str:
    return hashlib.sha256(_serialize(ev["pubkey"], ev["created_at"], ev["kind"], ev["tags"], ev["content"])).hexdigest()


def leading_zero_bits(hex_id: str) -> int:
    n = 0
    for ch in hex_id:
        v = int(ch, 16)
        if v == 0:
            n += 4
            continue
        return n + (4 - v.bit_length())
    return n


def build_event(sk_hex: str, kind: int, content: str, tags: Optional[list] = None,
                pow_bits: int = 0, created_at: Optional[int] = None) -> dict:
    pk = pubkey(sk_hex)
    tags = [list(t) for t in (tags or [])]
    ts = int(created_at if created_at is not None else time.time())
    if pow_bits > 0:  # NIP-13: grind a nonce tag until the id has enough leading zero bits
        nonce_tag = ["nonce", "0", str(pow_bits)]
        tags.append(nonce_tag)
        i = 0
        while True:
            nonce_tag[1] = str(i)
            eid = hashlib.sha256(_serialize(pk, ts, kind, tags, content)).hexdigest()
            if leading_zero_bits(eid) >= pow_bits:
                break
            i += 1
    else:
        eid = hashlib.sha256(_serialize(pk, ts, kind, tags, content)).hexdigest()
    sig = sign(sk_hex, bytes.fromhex(eid))
    return {"id": eid, "pubkey": pk, "created_at": ts, "kind": kind, "tags": tags,
            "content": content, "sig": sig.hex()}


def check_event(ev: Any) -> bool:
    """Shape, id and signature check. Never trust an event from a relay before this passes."""
    try:
        if not isinstance(ev, dict):
            return False
        if not (isinstance(ev.get("content"), str) and isinstance(ev.get("tags"), list)
                and isinstance(ev.get("kind"), int) and isinstance(ev.get("created_at"), int)):
            return False
        if any(not isinstance(t, list) or not all(isinstance(x, str) for x in t) for t in ev["tags"]):
            return False
        if not (is_hex(ev.get("id"), 32) and is_hex(ev.get("pubkey"), 32) and is_hex(ev.get("sig"), 64)):
            return False   # one canonical spelling per key, or a hidden person comes back in capitals
        if event_id(ev) != ev.get("id"):
            return False
        return verify(ev["pubkey"], bytes.fromhex(ev["id"]), bytes.fromhex(ev["sig"]))
    except (KeyError, ValueError, TypeError):
        return False


def tag_values(ev: dict, name: str) -> list[str]:
    return [t[1] for t in ev.get("tags", []) if len(t) > 1 and t[0] == name]


def first_tag(ev: dict, name: str) -> Optional[list[str]]:
    for t in ev.get("tags", []):
        if t and t[0] == name:
            return t
    return None


# --- owner/agent binding ----------------------------------------------------------------------
# The person's key signs the agent's pubkey; the agent's events carry that signature in an `owner` tag
# and are themselves signed by the agent key, so the claim runs both ways and cannot be replayed onto
# another agent.

def _bind_msg(agent_pk: str) -> bytes:
    return hashlib.sha256(b"ninsei-bind:v1:" + bytes.fromhex(agent_pk)).digest()


def owner_binding(owner_sk: str, agent_pk: str) -> str:
    return sign(owner_sk, _bind_msg(agent_pk)).hex()


def check_binding(owner_pk: str, agent_pk: str, sig_hex: str) -> bool:
    """Is sig_hex the owner's signature binding this agent key? Inputs come from strangers' tags."""
    if not (is_hex(owner_pk, 32) and is_hex(agent_pk, 32) and is_hex(sig_hex, 64)):
        return False   # an owner key in another spelling would bind the agent to a key nobody compares equal
    return _check_binding_cached(owner_pk, agent_pk, sig_hex)


@lru_cache(maxsize=4096)
def _check_binding_cached(owner_pk: str, agent_pk: str, sig_hex: str) -> bool:
    # Views ask about the same few (owner, agent, sig) triples for every event they show, and each
    # Schnorr verify costs ~3 ms in pure Python. The answer is a pure function of the inputs.
    try:
        return verify(owner_pk, _bind_msg(agent_pk), bytes.fromhex(sig_hex))
    except ValueError:
        return False


# --- bech32 npub, for display only --------------------------------------------------------------

_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _polymod(values: Iterable[int]) -> int:
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if ((b >> i) & 1) else 0
    return chk


def npub(pk_hex: str) -> str:
    data, acc, bits = [], 0, 0
    for byte in bytes.fromhex(pk_hex):
        acc = (acc << 8) | byte
        bits += 8
        while bits >= 5:
            bits -= 5
            data.append((acc >> bits) & 31)
    if bits:
        data.append((acc << (5 - bits)) & 31)
    hrp = "npub"
    exp = [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]
    pm = _polymod(exp + data + [0] * 6) ^ 1
    checksum = [(pm >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(_CHARSET[d] for d in data + checksum)
