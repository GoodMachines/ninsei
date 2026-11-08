"""Game answers stay secret until the reveal (2026-11-06).

Every answer (`tales_fake`) is NIP-44 v2 encrypted to the host's agent key, and the host's vote-open claim
tokens come from a nonce sealed inside each answer. So before the reveal only the host can read answers, and
only a writer can recognise their own option. Covers the NIP-44 implementation (official vectors, RFC 8439
ChaCha20), the sealed answer format, and hosted rounds watched by an outside engine that hears everything."""
import asyncio
import base64
import hashlib
import json
import time
from pathlib import Path

import pytest

from ninsei_engine import game, nip44, nostr
from ninsei_engine.engine import (KIND_LIVE, FAKE_SEALED_BYTES, SEALED_CHARS, Engine, _claim_token, open_fake,
                                  open_vote, seal_fake, seal_vote)
from test_engine import StubLLM, wait_for
from start_helpers import started
from test_hostile import ROOM, FakePool, Key, bare, settle  # noqa: F401  (fixture re-export)

VECTORS = json.loads((Path(__file__).parent / "data" / "nip44_vectors.json").read_text())["v2"]
VALID, INVALID = VECTORS["valid"], VECTORS["invalid"]


# --- NIP-44 v2: the official vectors (paulmillr/nip44, see the file header) ------------------------------

def test_vectors_are_the_published_ones():
    head = json.loads((Path(__file__).parent / "data" / "nip44_vectors.json").read_text())
    assert head["source"].startswith("https://raw.githubusercontent.com/paulmillr/nip44/")
    assert len(VALID["get_conversation_key"]) == 35 and len(VALID["encrypt_decrypt"]) == 10
    assert len(INVALID["decrypt"]) == 12 and len(INVALID["get_conversation_key"]) == 8


@pytest.mark.parametrize("v", VALID["get_conversation_key"], ids=lambda v: v["sec1"][:8])
def test_conversation_key(v):
    assert nip44.conversation_key(v["sec1"], v["pub2"]).hex() == v["conversation_key"]


def test_message_keys():
    ck = bytes.fromhex(VALID["get_message_keys"]["conversation_key"])
    for v in VALID["get_message_keys"]["keys"]:
        keys = nip44.message_keys(ck, bytes.fromhex(v["nonce"]))
        assert [k.hex() for k in keys] == [v["chacha_key"], v["chacha_nonce"], v["hmac_key"]]


def test_calc_padded_len():
    for unpadded, padded in VALID["calc_padded_len"]:
        assert nip44.calc_padded_len(unpadded) == padded


@pytest.mark.parametrize("v", VALID["encrypt_decrypt"], ids=lambda v: v["nonce"][:8])
def test_encrypt_decrypt(v):
    pub1, pub2 = nostr.pubkey(v["sec1"]), nostr.pubkey(v["sec2"])
    ck = nip44.conversation_key(v["sec1"], pub2)
    assert ck.hex() == v["conversation_key"]
    assert nip44.encrypt(v["plaintext"], ck, bytes.fromhex(v["nonce"])) == v["payload"]
    back = nip44.conversation_key(v["sec2"], pub1)  # the other side derives the same key
    assert back == ck and nip44.decrypt(v["payload"], back) == v["plaintext"]


@pytest.mark.parametrize("v", VALID["encrypt_decrypt_long_msg"], ids=lambda v: str(v["repeat"]))
def test_encrypt_decrypt_long_msg(v):
    text = v["pattern"] * v["repeat"]
    assert hashlib.sha256(text.encode()).hexdigest() == v["plaintext_sha256"]
    ck = bytes.fromhex(v["conversation_key"])
    payload = nip44.encrypt(text, ck, bytes.fromhex(v["nonce"]))
    assert hashlib.sha256(payload.encode()).hexdigest() == v["payload_sha256"]
    assert nip44.decrypt(payload, ck) == text


@pytest.mark.parametrize("v", INVALID["get_conversation_key"], ids=lambda v: v["note"])
def test_invalid_conversation_key(v):
    with pytest.raises(nip44.Nip44Error):
        nip44.conversation_key(v["sec1"], v["pub2"])


@pytest.mark.parametrize("v", INVALID["decrypt"], ids=lambda v: v["note"])
def test_invalid_decrypt(v):
    with pytest.raises(nip44.Nip44Error):
        nip44.decrypt(v["payload"], bytes.fromhex(v["conversation_key"]))


def test_invalid_plaintext_lengths():
    ck = bytes(32)
    for n in [0] + INVALID["encrypt_msg_lengths"]:
        with pytest.raises(nip44.Nip44Error):
            nip44.encrypt("a" * n, ck)
    nip44.encrypt("a" * nip44.MAX_PLAINTEXT, ck)  # our own cap, below the spec's extended prefix


# --- RFC 8439 ChaCha20 ------------------------------------------------------------------------------------

KEY = bytes(range(32))


def test_chacha20_block_rfc8439_2_3_2():
    block = nip44.chacha20_block(KEY, 1, bytes.fromhex("000000090000004a00000000"))
    assert block.hex() == ("10f1e7e4d13b5915500fdd1fa32071c4c7d1f4c733c068030422aa9ac3d46c4e"
                           "d2826446079faa0914c2d705d98b02a2b5129cd1de164eb9cbd083e8a2503c4e")


def test_chacha20_encrypt_rfc8439_2_4_2():
    plain = (b"Ladies and Gentlemen of the class of '99: If I could offer you only one tip for the future, "
             b"sunscreen would be it.")
    out = nip44.chacha20(KEY, bytes.fromhex("000000000000004a00000000"), plain, counter=1)
    assert out.hex() == ("6e2e359a2568f98041ba0728dd0d6981e97e7aec1d4360c20a27afccfd9fae0b"
                         "f91b65c5524733ab8f593dabcd62b3571639d624e65152ab8f530c359f0861d8"
                         "07ca0dbf500d6a6156a38e088a22b65e52bc514d16ccf806818ce91ab7793736"
                         "5af90bbf74a35be6b40b8eedf2785e42874d")
    assert nip44.chacha20(KEY, bytes.fromhex("000000000000004a00000000"), out, counter=1) == plain


def test_chacha20_rfc8439_a2_vector_1():
    out = nip44.chacha20(bytes(32), bytes(12), bytes(64))
    assert out.hex() == ("76b8e0ada0f13d90405d6ae55386bd28bdd219b8a08ded1aa836efcc8b770dc7"
                         "da41597c5157488d7724e03fb8d84a376a43b8f41518a11cc387b669b2ee6586")


# --- round trip, tampering, the sealed answer format ------------------------------------------------------

def test_round_trip_both_ways():
    a, b = nostr.new_secret(), nostr.new_secret()
    ck = nip44.conversation_key(a, nostr.pubkey(b))
    for text in ("a", "three hearts", "ゴジラ 🦖", "x" * 5000):
        payload = nip44.encrypt(text, ck)
        assert nip44.decrypt(payload, nip44.conversation_key(b, nostr.pubkey(a))) == text
    assert nip44.encrypt("same", ck) != nip44.encrypt("same", ck)  # a fresh nonce every time


def test_tampered_or_misdirected_payloads_are_rejected():
    a, b, c = nostr.new_secret(), nostr.new_secret(), nostr.new_secret()
    ck = nip44.conversation_key(a, nostr.pubkey(b))
    payload = nip44.encrypt("the real answer", ck)
    raw = bytearray(base64.b64decode(payload))
    for i in (1, 40, len(raw) - 40, len(raw) - 1):  # nonce, ciphertext, ciphertext end, MAC
        bad = bytearray(raw)
        bad[i] ^= 1
        with pytest.raises(nip44.Nip44Error, match="MAC"):
            nip44.decrypt(base64.b64encode(bytes(bad)).decode(), ck)
    for version in (0, 1, 3):
        bad = bytearray(raw)
        bad[0] = version
        with pytest.raises(nip44.Nip44Error, match="version"):
            nip44.decrypt(base64.b64encode(bytes(bad)).decode(), ck)
    with pytest.raises(nip44.Nip44Error):
        nip44.decrypt(payload[:100], ck)                     # truncated
    with pytest.raises(nip44.Nip44Error):
        nip44.decrypt("#" + payload[1:], ck)                 # a future encoding
    with pytest.raises(nip44.Nip44Error, match="MAC"):
        nip44.decrypt(payload, nip44.conversation_key(c, nostr.pubkey(b)))  # someone else's key
    for junk in (None, 7, "", "é" * 200, "A" * 200):
        with pytest.raises(nip44.Nip44Error):
            nip44.decrypt(junk, ck)


def test_sealed_answers_open_only_for_writer_and_host_and_are_all_one_size():
    writer, host, eve = Key("writer"), Key("host"), Key("eve")
    sizes = set()
    for text in ("a", "x" * 80, "\u0001" * 80, "🦖" * 80, '"\\' * 40):
        enc, nonce = seal_fake(writer.psk, host.apk, text)
        sizes.add(len(enc))
        assert nostr.is_hex(nonce, 16)
        assert open_fake(host.ask, writer.ppk, enc) == {"text": text[:80], "nonce": nonce}   # the host
        assert open_fake(writer.psk, host.apk, enc) == {"text": text[:80], "nonce": nonce}  # the writer
        assert open_fake(eve.ask, writer.ppk, enc) is None and open_fake(eve.ask, host.apk, enc) is None
        assert len(json.dumps({"text": text, "nonce": nonce, "pad": ""}, ensure_ascii=False).encode()) < FAKE_SEALED_BYTES
    assert len(sizes) == 1  # the length of a sealed answer says nothing about its text
    for junk in (None, 3, {"enc": "x"}, "not base64 at all", "A" * 944):
        assert open_fake(host.ask, writer.ppk, junk) is None
    # a well-formed payload with the wrong inside is "no answer" too
    ck = nip44.conversation_key(writer.psk, host.apk)
    for inner in ("[]", '{"text": 5, "nonce": "' + "ab" * 16 + '"}', '{"text": "x", "nonce": "short"}', "not json"):
        assert open_fake(host.ask, writer.ppk, nip44.encrypt(inner, ck)) is None


def test_sealed_votes_open_only_for_voter_and_host_and_are_all_one_size():
    voter, host, eve = Key("voter"), Key("host"), Key("eve")
    ids = [f"{i:08x}" for i in range(12)]
    cases = [("0000000a", None), ("", []), ("", ids[:1]), ("", ids)]
    sizes = set()
    for option, agents in cases:
        enc = seal_vote(voter.psk, host.apk, option, agents)
        sizes.add(len(enc))
        want = {"option": option, "agents": list(agents or [])}
        assert open_vote(host.ask, voter.ppk, enc) == want and open_vote(voter.psk, host.apk, enc) == want
        assert open_vote(eve.ask, voter.ppk, enc) is None and not (option and option in enc)
    assert sizes == {SEALED_CHARS}  # neither the pick nor the number of flags shows
    assert len(seal_fake(voter.psk, host.apk, "x")[0]) == SEALED_CHARS  # and votes look like answers
    # ids that aren't option-shaped are dropped, so nothing can grow a vote past the fixed size
    enc = seal_vote(voter.psk, host.apk, "\u0001" * 16, ["🦖" * 16, '"' * 16, "ok"])
    assert open_vote(host.ask, voter.ppk, enc) == {"option": "", "agents": ["ok"]}


def test_an_unpaired_surrogate_seals_instead_of_raising():
    """A model reply can carry a lone surrogate; on the agent path the call is already paid for by then."""
    writer, host = Key("writer"), Key("host")
    enc, nonce = seal_fake(writer.psk, host.apk, "a\ud800b")
    assert open_fake(host.ask, writer.ppk, enc) == {"text": "a?b", "nonce": nonce}
    enc = seal_vote(writer.psk, host.apk, "o1\udfff", ["o2", "\ud800"])
    assert open_vote(host.ask, writer.ppk, enc) == {"option": "", "agents": ["o2"]}  # no longer id-shaped: dropped


def _count_decrypts(monkeypatch):
    calls = []
    real = nip44.decrypt

    def counting(payload, ck):
        calls.append(len(payload))
        return real(payload, ck)

    monkeypatch.setattr(nip44, "decrypt", counting)
    return calls


def _big_sealed(k, host_pk, body, size=20_000):
    """A payload the sender really sealed to the host (the MAC passes), just far bigger than any answer."""
    payload = nip44.encrypt(json.dumps(dict(body, pad="0" * size)), nip44.conversation_key(k.psk, host_pk))
    assert len(payload) > SEALED_CHARS
    return payload


async def test_a_flood_of_sealed_answers_or_votes_costs_one_decrypt_per_author(bare, monkeypatch):
    """A present player holds the conversation key, so every payload they seal passes the MAC: before, 200
    big ones stalled the host for seconds. Now only each author's latest event is opened, and only if it is
    exactly the sealed size."""
    e, _ = bare(ts=1.0)
    host_pk, t0 = e._identity()["agent_pk"], int(time.time()) - 500
    big, last_ok = Key("big"), Key("lastok")
    for i in range(40):
        for k in (big, last_ok):
            for t, body in (("tales_fake", {"text": "x", "nonce": "ab" * 16}), ("tales_vote", {"option": "o1"})):
                enc = _big_sealed(k, host_pk, body)
                await e._on_event(k.person({"t": t, "gid": "g", "n": 1, "enc": enc}, created_at=t0 + i), "relay")
    fake, nonce = last_ok.fake(host_pk, "g", 1, "the latest")
    fake = last_ok.person(json.loads(fake["content"]), created_at=t0 + 100)
    await e._on_event(fake, "relay")
    await e._on_event(last_ok.vote(host_pk, "g", 1, "o2", created_at=t0 + 100), "relay")
    assert sum(1 for ev in e.events[ROOM].values() if ev["pubkey"] == big.ppk) == 80
    e._opened.clear()
    calls = _count_decrypts(monkeypatch)
    assert e._round_sealed(ROOM, "g", 1) == {last_ok.ppk} and calls == []
    assert e._round_sealed(ROOM, "g", 1, "tales_vote") == {last_ok.ppk} and calls == []
    who = {big.ppk, last_ok.ppk}
    assert e._round_fakes(ROOM, "g", 1, who) == {last_ok.ppk: {"text": "the latest", "nonce": nonce}}
    assert calls == [SEALED_CHARS]  # one decrypt for the one author whose latest answer is the right size
    assert e._round_votes(ROOM, "g", 1, who, {}, "seed", frozenset()) == {last_ok.ppk: {"option": "o2", "agents": []}}
    assert calls == [SEALED_CHARS] * 2
    # a sealed-size answer that isn't the latest is never opened either
    calls.clear()
    e._opened.clear()
    older, _ = last_ok.fake(host_pk, "g", 1, "older")
    await e._on_event(last_ok.person(json.loads(older["content"]), created_at=t0 + 50), "relay")
    assert e._round_fakes(ROOM, "g", 1, who)[last_ok.ppk]["text"] == "the latest" and len(calls) == 1


# --- hosted rounds, watched from outside -------------------------------------------------------------------

class HubPool(FakePool):
    """Everything one engine publishes reaches every other engine in the hub, as through a relay."""

    def __init__(self, hub):
        super().__init__()
        self.hub = hub

    async def publish(self, ev, wait=4.0):
        self.sent.append(ev)
        for other in list(self.hub):
            if other.pool is not self:
                await other._on_event(ev, "relay")
        return {}


def _presence(e):
    ident = e._identity()
    content = {"t": "presence", "name": e.settings()["agent_name"], "state": "activity: idle"}
    return nostr.build_event(ident["agent_sk"], KIND_LIVE, json.dumps(content),
                             [["h", ROOM], ["owner", ident["person_pk"], ident["binding"]]])


def _fakes(e):
    return [ev for ev in e.events[ROOM].values() if json.loads(ev["content"]).get("t") == "tales_fake"]


def _vote_open(e):
    opens = [json.loads(ev["content"]) for ev in e.events[ROOM].values()
             if json.loads(ev["content"]).get("t") == "tales_vote_open"]
    return opens[-1] if opens else None


async def _three(bare):
    """A host (Maya and her agent Ada), a player (Sam and his agent Bo), and Eve, who hears every event but
    plays no part: an outside observer with a client of her own."""
    host, _ = bare("Maya", "Ada", ts=0.02)
    sam, _ = bare("Sam", "Bo", ts=0.02)
    eve, _ = bare("Eve", "Evi", ts=0.02)
    hub = [host, sam, eve]
    host.pool, sam.pool = HubPool(hub), HubPool(hub)  # Eve keeps a FakePool: she hears all and says nothing
    eve.brain.available = lambda: False
    for e in hub:
        for other in hub:
            if other is not e and e is not eve:
                await other._on_event(_presence(e), "relay")
    return host, sam, eve


def _eve_sees_no_answer(eve, host, answers):
    """What an outside observer can check during the vote: every answer is an opaque blob of one size, her
    keys can't open any, and the claim tokens match nothing she can compute from public data."""
    fakes = _fakes(eve)
    host_pk = host._identity()["agent_pk"]
    ident = eve._identity()
    assert fakes
    for ev in fakes:
        c = json.loads(ev["content"])
        assert set(c) <= {"t", "gid", "n", "enc", "at", "name", "face"} and "text" not in c
        assert not any(a in ev["content"] for a in answers)
        assert open_fake(ident["agent_sk"], host_pk, c["enc"]) is None
        assert open_fake(ident["agent_sk"], ev["pubkey"], c["enc"]) is None
    assert len({len(json.loads(ev["content"])["enc"]) for ev in fakes}) == 1
    vote = _vote_open(eve)
    options, claims = vote["options"], vote["claims"]
    assert list(claims) == [o["id"] for o in options]          # no odd one out at the end
    assert len({len(v) for v in claims.values()}) == 1         # every option carries as many tokens
    public = [ev["id"] for ev in fakes] + [ev["pubkey"] for ev in fakes] + \
             [json.loads(ev["content"])["enc"] for ev in fakes]
    guesses = {_claim_token(o["id"], x) for o in options for x in public}
    assert not guesses & {t for v in claims.values() for t in v}
    view = eve.game_view(ROOM)
    assert view["blocked"] == [] and view["my_fake"] == ""
    return options


def _eve_sees_no_vote(eve, options):
    """Every vote is an opaque blob of one size: who voted shows, what they picked doesn't."""
    votes = [ev for ev in eve.events[ROOM].values() if json.loads(ev["content"]).get("t") == "tales_vote"]
    assert votes
    for ev in votes:
        c = json.loads(ev["content"])
        assert set(c) <= {"t", "gid", "n", "enc", "at", "name", "face"} and len(c["enc"]) == SEALED_CHARS
        assert not any(o["id"] in ev["content"] for o in options)
    return len(votes)


async def test_a_hosted_tall_tales_round_is_secret_until_the_reveal(bare, monkeypatch):
    monkeypatch.setattr(game, "FAKE_SECONDS", 2400)  # phases end when every present player is in
    monkeypatch.setattr(game, "VOTE_SECONDS", 2400)
    host, sam, eve = await _three(bare)
    gid = (await started(host, ROOM, 1))["gid"]
    assert await wait_for(lambda: (sam.game_view(ROOM) or {}).get("phase") == "fakes")
    await sam.submit_fake(ROOM, gid, 1, "seven")
    await host.submit_fake(ROOM, gid, 1, "Bo hearts")  # the same as Bo's: one option, two writers
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "vote")
    assert len(_fakes(eve)) == 4 and eve.game_view(ROOM)["fakes_in"] == 4  # Maya, Ada, Sam, Bo
    options = _eve_sees_no_answer(eve, host, ("seven", "Bo hearts"))
    by_text = {o["text"]: o["id"] for o in options}
    assert set(by_text) == {"three", "seven", "Bo hearts", "Ada five"}
    assert {len(v) for v in _vote_open(eve)["claims"].values()} == {2}  # the truth has two decoys too
    # each player still knows their own: Sam's team wrote "seven" and (Bo) "Bo hearts"; Maya wrote "Bo hearts"
    sv, hv = sam.game_view(ROOM), host.game_view(ROOM)
    assert set(sv["blocked"]) == {by_text["seven"], by_text["Bo hearts"]} and sv["my_fake"] == "seven"
    assert set(hv["blocked"]) == {by_text["Bo hearts"], by_text["Ada five"]} and hv["my_fake"] == "Bo hearts"
    await sam.submit_vote(ROOM, gid, 1, by_text["three"])
    assert await wait_for(lambda: eve.game_view(ROOM)["votes_in"] == 1)
    assert _eve_sees_no_vote(eve, options) == 1  # sealed to the host: Sam's pick isn't public
    assert eve.game_view(ROOM)["my_vote"] == "" and sam.game_view(ROOM)["my_vote"] == by_text["three"]
    await host.submit_vote(ROOM, gid, 1, by_text["seven"])  # Maya is fooled by Sam
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "end")
    assert _eve_sees_no_vote(eve, options) == 2
    sam_pk = sam._identity()["person_pk"]
    assert eve.game_view(ROOM)["scores"] == {sam_pk: 3}  # 2 for the truth, 1 for fooling Maya
    reveal = [json.loads(ev["content"]) for ev in eve.events[ROOM].values()
              if json.loads(ev["content"]).get("t") == "tales_reveal"][-1]
    assert reveal["truth"] == by_text["three"] and reveal["authors"][by_text["seven"]] == sam_pk
    await settle(host)


async def test_a_lucky_match_reads_as_your_own_answer_and_cant_be_voted_for(bare, monkeypatch):
    """Sam's answer matches the truth. To him the truth is marked as his (so an unmarked option with his own
    text can't tell him it's the truth), the host refuses his team's vote for it, and he keeps the lucky point.
    To everyone else the truth looks like any other option."""
    monkeypatch.setattr(game, "FAKE_SECONDS", 2400)
    monkeypatch.setattr(game, "VOTE_SECONDS", 2400)
    host, sam, eve = await _three(bare)
    gid = (await started(host, ROOM, 1))["gid"]
    assert await wait_for(lambda: (sam.game_view(ROOM) or {}).get("phase") == "fakes")
    await sam.submit_fake(ROOM, gid, 1, "Three")  # the truth is "three": lucky
    await host.submit_fake(ROOM, gid, 1, "nine")
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "vote")
    options = _eve_sees_no_answer(eve, host, ("Three", "nine"))
    by_text = {o["text"]: o["id"] for o in options}
    truth = by_text["Three"]
    sv, hv = sam.game_view(ROOM), host.game_view(ROOM)
    assert truth in sv["blocked"] and by_text["nine"] not in sv["blocked"]
    # the truth goes out in the lucky writer's spelling, as a merged fake goes out in its first writer's:
    # the host's "three" next to Sam's token would tell a modified client it's the truth
    for view in (sv, hv, eve.game_view(ROOM)):
        assert {o["id"]: o["text"] for o in view["options"]}[truth] == "Three"
    assert truth not in hv["blocked"] and set(hv["blocked"]) == {by_text["nine"], by_text["Ada five"]}
    await sam.submit_vote(ROOM, gid, 1, truth)  # a modified client votes for it anyway: the host refuses it
    await host.submit_vote(ROOM, gid, 1, truth)
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "end")
    sam_pk, maya_pk = sam._identity()["person_pk"], host._identity()["person_pk"]
    scores = eve.game_view(ROOM)["scores"]
    assert scores.get(sam_pk) == 1  # the lucky point only: his vote for the truth didn't count
    assert scores.get(maya_pk) == 2  # 2 for the truth
    await settle(host)


async def test_a_hosted_whos_the_agent_round_hides_who_wrote_what(bare, monkeypatch):
    monkeypatch.setattr(game, "FAKE_SECONDS", 2400)
    monkeypatch.setattr(game, "VOTE_SECONDS", 2400)
    host, sam, eve = await _three(bare)
    gid = (await started(host, ROOM, 1, mode="agent"))["gid"]
    assert await wait_for(lambda: (sam.game_view(ROOM) or {}).get("phase") == "fakes")
    await sam.submit_fake(ROOM, gid, 1, "toast")
    await host.submit_fake(ROOM, gid, 1, "eggs")
    assert await wait_for(lambda: (eve.game_view(ROOM) or {}).get("phase") == "vote")
    options = _eve_sees_no_answer(eve, host, ("toast", "eggs", "cold pizza"))
    by_text = {o["text"]: o["id"] for o in options}
    assert set(by_text) == {"toast", "eggs", "cold pizza probably (Ada)", "cold pizza probably (Bo)"}
    assert set(sam.game_view(ROOM)["blocked"]) == {by_text["toast"], by_text["cold pizza probably (Bo)"]}
    assert set(host.game_view(ROOM)["blocked"]) == {by_text["eggs"], by_text["cold pizza probably (Ada)"]}
    await sam.submit_vote(ROOM, gid, 1, "", [by_text["cold pizza probably (Ada)"]])
    assert await wait_for(lambda: sam.game_view(ROOM)["my_picks"] == [by_text["cold pizza probably (Ada)"]])
    await host.submit_vote(ROOM, gid, 1, "", [])
    assert await wait_for(lambda: bool((eve.game_view(ROOM) or {}).get("reveal")))
    assert _eve_sees_no_vote(eve, options) == 2  # one flag or none: the same size, nothing readable
    rv = eve.game_view(ROOM)["reveal"]  # the host opened the flags: they show in the reveal
    assert rv["picks"].get(by_text["cold pizza probably (Ada)"]) == [sam._identity()["person_pk"]]
    kinds = {o["text"]: eve.game_view(ROOM)["reveal"]["kinds"][o["id"]] for o in options}
    assert kinds == {"toast": "person", "eggs": "person",
                     "cold pizza probably (Ada)": "agent", "cold pizza probably (Bo)": "agent"}
    await host._end_hosted(ROOM)


async def test_the_host_ignores_plaintext_and_misdirected_answers(bare):
    e, _ = bare(ts=0.02)  # default phase lengths, scaled: the fakes phase ends on its clock
    old, stray = Key("old"), Key("stray")
    for k in (old, stray):
        await e._on_event(k.agent({"t": "presence", "name": "Oldbot", "state": "activity: idle"}, kind=KIND_LIVE),
                          "relay")
    gid = (await started(e, ROOM, 1))["gid"]
    assert await wait_for(lambda: (e.game_view(ROOM) or {}).get("phase") == "fakes")
    await e.submit_fake(ROOM, gid, 1, "nine")
    await e._on_event(old.person({"t": "tales_fake", "gid": gid, "n": 1, "text": "plain answer", "name": "Old"}),
                      "relay")
    await e._on_event(old.agent({"t": "tales_fake", "gid": gid, "n": 1, "text": "plain bot", "name": "Oldbot"}),
                      "relay")
    await e._on_event(stray.fake(Key("elsewhere").apk, gid, 1, "sealed to someone else")[0], "relay")
    assert await wait_for(lambda: (e.game_view(ROOM) or {}).get("phase") == "vote")
    view = e.game_view(ROOM)
    assert {o["text"] for o in view["options"]} == {"three", "nine", "Ada five"}
    assert view["fakes_in"] == 3  # mine and the misdirected one are sealed; plaintext isn't counted or shown
    assert "plain answer" not in json.dumps(view)
    truth = next(o["id"] for o in view["options"] if o["text"] == "three")
    # an old client's plaintext vote for the truth isn't a vote: not counted, not scored
    await e._on_event(old.person({"t": "tales_vote", "gid": gid, "n": 1, "option": truth, "name": "Old"}), "relay")
    assert e.game_view(ROOM)["votes_in"] == 0
    assert await wait_for(lambda: (e.game_view(ROOM) or {}).get("phase") == "end", timeout=30)
    reveal = [json.loads(ev["content"]) for ev in e.events[ROOM].values()
              if json.loads(ev["content"]).get("t") == "tales_reveal"][-1]
    assert reveal["picks"] == {} and old.ppk not in reveal["points"]


async def test_my_own_answer_and_blocks_survive_a_restart(bare):
    e, _ = bare(ts=1.0)
    host = Key("host")
    await e._on_event(host.agent({"t": "tales_start", "gid": "g", "rounds": 1, "seq": 1}), "relay")
    await e._on_event(host.agent({"t": "tales_round", "gid": "g", "n": 1, "q": "?", "secs": 45, "seq": 2,
                                  "ends_at": time.time() + 45}), "relay")
    await e.submit_fake(ROOM, "g", 1, "a long walk")
    mine = _fakes(e)[0]
    opened = open_fake(host.ask, e._identity()["person_pk"], json.loads(mine["content"])["enc"])  # as the host
    assert opened["text"] == "a long walk"
    options = [{"id": "o1", "text": "a long walk"}, {"id": "o2", "text": "the truth"}]
    me = e._identity()["person_pk"]
    claims = Engine._option_claims(options, {"o1": me}, {me: opened["nonce"]})
    await e._on_event(host.agent({"t": "tales_vote_open", "gid": "g", "n": 1, "options": options, "claims": claims,
                                  "secs": 30, "ends_at": time.time() + 30, "seq": 3}), "relay")
    assert e.game_view(ROOM)["blocked"] == ["o1"]
    await e.submit_vote(ROOM, "g", 1, "o2")
    vote = [ev for ev in e.events[ROOM].values() if json.loads(ev["content"]).get("t") == "tales_vote"][0]
    sealed = json.loads(vote["content"])
    assert "option" not in sealed and len(sealed["enc"]) == SEALED_CHARS and e.game_view(ROOM)["my_vote"] == "o2"
    e.store.close()
    e2 = Engine(e.data_dir, lambda: StubLLM("Ada"), lock=False, timescale=1.0, relays=[])
    e2.store.set("commons_offered", True)
    try:
        await e2._boot()
        view = e2.game_view(ROOM)
        assert view["blocked"] == ["o1"] and view["my_fake"] == "a long walk"
        assert view["my_vote"] == "o2" and view["votes_in"] == 1  # reopened from my own sealed vote
    finally:
        for t in list(e2._tasks):
            t.cancel()
        await asyncio.gather(*e2._tasks, return_exceptions=True)
        await e2.pool.stop()
        e2.store.close()


def test_a_lucky_writer_cant_tell_the_truth_from_their_own_fake_in_the_raw_event():
    """Review 2026-11-07: the truth showed the host's spelling while a fake shows its first writer's, so a
    lucky writer who posted first could spot the truth by their token on an option not spelled their way."""
    import secrets as _s
    from ninsei_engine import game as _g
    from ninsei_engine.engine import Engine as _E, _claim_token as _tok
    guess = "pArIs"
    for truth in ("Paris", "Rome"):
        fakes = {"A": guess, "C": "Lyon", "D": "Marseille"}
        nonces = {pk: _s.token_hex(16) for pk in fakes}
        options, truth_id, author_of, lucky = _g.build_options(truth, fakes, _s.token_hex(16))
        claims = _E._option_claims(options, author_of, nonces, truth_id, lucky)
        mine = [o for o in options if _tok(o["id"], nonces["A"]) in claims[o["id"]]]
        assert len(mine) == 1 and mine[0]["text"] == guess      # the same either way
