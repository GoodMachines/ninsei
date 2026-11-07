"""Private messages between two people: NIP-17 on top of NIP-59 gift wraps and NIP-44 encryption.

    rumor  kind 14, unsigned, pubkey = the sender, one `p` tag = the other person, content = plain text
    seal   kind 13, signed by the sender, NIP-44 encrypted to the receiver, no tags
    wrap   kind 1059, signed by a one-time random key, NIP-44 encrypted to the receiver, tag ["p", receiver]

Both `created_at`s on the seal and the wrap are random, up to two days in the past; the rumor's is the real
one. A copy is wrapped to the sender too, so their other installs see what they sent.

Everything here is a pure function of its inputs (no clock, no storage, no engine state), so it can run on a
worker thread. Everything that arrives is a stranger's: sizes are bounded BEFORE any crypto, and anything
that fails any check is dropped with a one-word verdict and no detail.

People only: nothing in this module, or anything that calls it, ever reaches a model.
"""
from __future__ import annotations

import json
import secrets
import time
from typing import Any, Callable, Optional

from . import nip44, nostr

KIND_RUMOR = 14
KIND_SEAL = 13
KIND_WRAP = 1059
TWO_DAYS = 2 * 86400

MAX_TEXT = 4000          # characters of a message we keep (other apps send longer ones: those are dropped)
SEND_TEXT = 2000         # characters Ninsei's own composer sends in one message
# What a 4000-character message can legally weigh at each layer, with room to spare: 16 KB of rumor JSON
# (4000 four-byte characters), padded, base64'd, wrapped twice. Anything bigger is refused before decrypting.
MAX_RUMOR_BYTES = 20_000
MAX_SEAL_CONTENT = 30_000    # characters of the seal's encrypted payload
MAX_WRAP_CONTENT = 40_000    # characters of the wrap's encrypted payload
MAX_SEAL_BYTES = 36_000      # the decrypted seal JSON

OK = "ok"
NOT_MINE = "not_mine"        # not addressed to my key (a relay sent it anyway, or a stray)
GARBAGE = "garbage"          # won't decrypt, isn't JSON, wrong shape or kind, bad signature or id
FORGED = "forged"            # the seal's key and the rumor's key differ: someone claiming to be someone else
OVERSIZE = "oversize"
UNSUPPORTED = "unsupported"  # a valid message of a kind or shape Ninsei doesn't show (group chats, files, reactions)
HIDDEN = "hidden"            # from someone I hid


def _json(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def past(now: Optional[float] = None) -> int:
    """A random moment in the two days before `now` (NIP-17: seal and wrap times must not reveal when it was sent)."""
    return int(now if now is not None else time.time()) - secrets.randbelow(TWO_DAYS)


def make_rumor(sender_pk: str, peer_pk: str, text: str, now: Optional[int] = None) -> dict:
    """The unsigned kind 14 message. It has an `id` (the hash of its fields) and no `sig`."""
    rumor = {"pubkey": sender_pk, "created_at": int(now if now is not None else time.time()), "kind": KIND_RUMOR,
             "tags": [["p", peer_pk]], "content": text}
    rumor["id"] = nostr.event_id(rumor)
    return rumor


def make_seal(sender_sk: str, receiver_pk: str, rumor: dict) -> dict:
    content = nip44.encrypt(_json(rumor), nip44.conversation_key(sender_sk, receiver_pk))
    return nostr.build_event(sender_sk, KIND_SEAL, content, [], created_at=past())


def make_wrap(seal: dict, receiver_pk: str) -> dict:
    one_time = nostr.new_secret()
    content = nip44.encrypt(_json(seal), nip44.conversation_key(one_time, receiver_pk))
    return nostr.build_event(one_time, KIND_WRAP, content, [["p", receiver_pk]], created_at=past())


def wrap_for(sender_sk: str, receiver_pk: str, rumor: dict) -> dict:
    """One rumor, sealed and wrapped for one receiver. A message to someone else is two of these: one for them
    and one for the sender's own key (each seal is encrypted to its own receiver)."""
    return make_wrap(make_seal(sender_sk, receiver_pk, rumor), receiver_pk)


def _tags_ok(tags: Any) -> bool:
    return isinstance(tags, list) and len(tags) <= 64 and all(
        isinstance(t, list) and len(t) <= 8 and all(isinstance(x, str) and len(x) <= 512 for x in t) for t in tags)


def wrap_shape_ok(ev: Any) -> bool:
    """Cheap checks only, before the wrap is queued: a dict of the right kind with canonical hex id and key and
    a payload that is not larger than any real message could be. Costs no crypto."""
    return (isinstance(ev, dict) and ev.get("kind") == KIND_WRAP and isinstance(ev.get("content"), str)
            and len(ev["content"]) <= MAX_WRAP_CONTENT and nostr.is_hex(ev.get("id"), 32)
            and nostr.is_hex(ev.get("pubkey"), 32) and _tags_ok(ev.get("tags"))
            and isinstance(ev.get("created_at"), int))


def unwrap(my_sk: str, my_pk: str, wrap: Any,
           hidden: Callable[[str], bool] = lambda pk: False) -> tuple[str, Optional[dict]]:
    """Open a gift wrap meant for me. Returns (verdict, message): the message is
    {"id", "sender", "peer", "text", "created_at"} only when the verdict is OK, where `peer` is the other
    person in the conversation (the sender, or for my own copy the receiver). The relay pool has already
    checked the wrap's signature; this checks its shape and id again because it is cheap.

    Order matters: sizes, then who it is for, then the wrap's layer, then the seal's signature (only after the
    sender is known not to be hidden: a hidden person's wraps cost one decryption), then the rumor, whose key must
    be the seal's key. Any exception from any layer is "garbage"."""
    try:
        if not wrap_shape_ok(wrap):
            return GARBAGE, None
        if nostr.event_id(wrap) != wrap["id"]:
            return GARBAGE, None
        if my_pk not in nostr.tag_values(wrap, "p"):
            return NOT_MINE, None                      # NIP-59: the wrap is addressed by its p tag
        seal_json = nip44.decrypt(wrap["content"], nip44.conversation_key(my_sk, wrap["pubkey"]))
        if len(seal_json.encode("utf-8")) > MAX_SEAL_BYTES:
            return OVERSIZE, None
        seal = json.loads(seal_json)
        if not (isinstance(seal, dict) and seal.get("kind") == KIND_SEAL and seal.get("tags") == []
                and isinstance(seal.get("content"), str) and nostr.is_hex(seal.get("pubkey"), 32)):
            return GARBAGE, None                       # NIP-59: a seal has no tags
        if len(seal["content"]) > MAX_SEAL_CONTENT:
            return OVERSIZE, None
        sender = seal["pubkey"]
        if sender != my_pk and hidden(sender):
            return HIDDEN, None
        if not nostr.check_event(seal):                # id and the sender's signature
            return GARBAGE, None
        rumor_json = nip44.decrypt(seal["content"], nip44.conversation_key(my_sk, sender))
        if len(rumor_json.encode("utf-8")) > MAX_RUMOR_BYTES:
            return OVERSIZE, None
        rumor = json.loads(rumor_json)
        if not isinstance(rumor, dict) or "sig" in rumor:
            return GARBAGE, None                       # NIP-59: the inner event is never signed
        if rumor.get("pubkey") != sender:
            return FORGED, None                        # NIP-17: else any sender could speak as anyone
        if rumor.get("kind") != KIND_RUMOR:
            return UNSUPPORTED, None
        if not (nostr.is_hex(rumor.get("id"), 32) and isinstance(rumor.get("created_at"), int)
                and isinstance(rumor.get("content"), str) and _tags_ok(rumor.get("tags"))):
            return GARBAGE, None
        if nostr.event_id(rumor) != rumor["id"]:
            return GARBAGE, None
        if len(rumor["content"]) > MAX_TEXT:
            return OVERSIZE, None
        if not rumor["content"].strip():
            return GARBAGE, None
        # One conversation between two people. The people in it are the sender and every `p` tag; any other
        # shape (a group, a note to self, a message that isn't about me) is not shown.
        tos = set(nostr.tag_values(rumor, "p"))
        if any(not nostr.is_hex(p, 32) for p in tos) or len(tos) != 1:
            return UNSUPPORTED, None
        (to,) = tos
        if sender == my_pk:
            if to == my_pk:
                return UNSUPPORTED, None
            peer = to                                  # my own copy: the conversation is with its receiver
        else:
            if to != my_pk:
                return NOT_MINE, None                  # a message between two other people
            peer = sender
        return OK, {"id": rumor["id"], "sender": sender, "peer": peer, "text": rumor["content"],
                    "created_at": rumor["created_at"]}
    except (nip44.Nip44Error, ValueError, TypeError, KeyError, AttributeError, RecursionError, UnicodeError):
        return GARBAGE, None
