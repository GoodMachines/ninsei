"""Typing indicators, profile pictures and built faces for people: what an engine sends, what it accepts from
strangers and what the UI is told. Image bytes are built by hand (see test_avatar.py for every check on its own)."""
import asyncio
import json
import random
import time

import pytest

from ninsei_engine import avatar, nostr
from ninsei_engine.engine import (ART_AUTHORS, ART_AVATAR_D, ART_FACE_D, ART_POW, KIND_LIVE, KIND_META, KIND_ROOM,
                                  TYPING_GAP, TYPING_PER_MIN, TYPING_SHOW, Engine, clean_face)
from test_avatar import jpeg, png, riff, uri, vp8l, wchunk, vp8x
from test_engine import read, run, setup_room, wait_for, world  # noqa: F401  (fixture re-export)
from test_hostile import FakePool, Key, ROOM, bare, own_person_event, settle  # noqa: F401  (fixture re-export)

PNG = uri(png(), "image/png")
WEBP = uri(riff(vp8l(80, 80)), "image/webp")
JPG = uri(jpeg(), "image/jpeg")


class ArtPool(FakePool):
    """Records subscriptions as well as publishes."""

    def __init__(self):
        super().__init__()
        self.subs = []
        self.unsubs = []

    async def subscribe(self, sub_id, filters, handler, **kw):
        self.subs.append((sub_id, filters))

    async def unsubscribe(self, sub_id):
        self.unsubs.append(sub_id)

    def eose_count(self, sub_id):
        return 0


def art(key, kind, content, created_at=None, pow_bits=ART_POW, agent=False):
    """A picture or face event as a client would publish it (no `t` tag, replaceable, proof of work)."""
    d = ART_AVATAR_D if kind == "avatar" else ART_FACE_D
    tags = [["d", d]] + ([["owner", key.ppk, key.bind]] if agent else [])
    return nostr.build_event(key.ask if agent else key.psk, KIND_META, content if isinstance(content, str) else json.dumps(content),
                             tags, pow_bits=pow_bits, created_at=created_at)


async def meet(e, key, name="Mal"):
    """The key says something in the room (history: no reply from my agent)."""
    await e._on_event(key.person({"t": "msg", "text": "hi", "name": name, "at": time.time()}), "history")


async def out(e):
    """What the engine has published so far (its sends are spawned tasks: let them finish first)."""
    await settle(e)
    return e.pool.sent


# --- typing: what I send -----------------------------------------------------------------------------------------

async def test_typing_goes_out_as_one_ephemeral_event_only_while_someone_is_here(bare):
    e, _ = bare()
    assert (await e.typing_signal(ROOM)) == {"sent": False, "why": "nobody else is here"}   # alone: nothing to tell
    assert await out(e) == []
    mal = Key("mal")
    now = time.time()
    e.presence[ROOM] = {mal.apk: {"state": "activity: idle", "budget": None, "at": now, "owner": mal.ppk, "name": "Bo", "face": None,
                                  "build": None, "vibe": "", "model": ""}}
    assert (await e.typing_signal(ROOM)) == {"sent": True}
    ev = (await out(e))[-1]
    assert ev["kind"] == KIND_LIVE == 21042 and nostr.tag_values(ev, "h") == [ROOM] and ev["pubkey"] == e._identity()["person_pk"]
    assert json.loads(ev["content"])["t"] == "typing" and not nostr.first_tag(ev, "owner")   # a person's, never the agent's
    assert e.store.event_outbox_status(ev["id"]) is None                                    # ephemeral: never queued
    assert e.typing.get(ROOM, {}) == {}                                                      # my own signal never shows me


async def test_typing_is_paced_per_room_and_capped_per_minute_overall(bare, monkeypatch):
    e, _ = bare()
    mal = Key("mal")
    rooms = [ROOM] + [f"{i:016x}" for i in range(1, 20)]
    for r in rooms[1:]:
        e.store.save_room(r, {"id": r, "name": r})
        e.events[r] = {}
    for r in rooms:
        e.presence[r] = {mal.apk: {"state": "activity: idle", "budget": None, "at": time.time(), "owner": mal.ppk, "name": "Bo",
                                   "face": None, "build": None, "vibe": "", "model": ""}}
    assert (await e.typing_signal(ROOM))["sent"]
    assert (await e.typing_signal(ROOM)) == {"sent": False, "why": "just sent one"}   # one per TYPING_GAP in a room
    e._typing_at[ROOM] -= TYPING_GAP + 0.1
    assert (await e.typing_signal(ROOM))["sent"]
    sent = 2
    for r in rooms[1:]:                                                               # other rooms are separate...
        res = await e.typing_signal(r)
        sent += res["sent"]
        if not res["sent"]:
            assert res["why"] == "too many signals this minute"                       # ...up to TYPING_PER_MIN overall
    assert sent == TYPING_PER_MIN and len([x for x in await out(e) if x["kind"] == KIND_LIVE]) == TYPING_PER_MIN


async def test_typing_in_a_room_i_am_not_in_or_before_setup_sends_nothing(bare):
    e, _ = bare()
    assert (await e.typing_signal("0" * 16))["sent"] is False
    assert (await e.typing_signal(5))["sent"] is False  # a junk room id is no crash
    e.save_settings({"onboarded": False})
    assert (await e.typing_signal(ROOM))["sent"] is False
    assert await out(e) == []


# --- typing: what I show ---------------------------------------------------------------------------------------------

async def test_a_typing_person_is_shown_by_their_room_name_for_a_few_seconds(bare):
    e, llm = bare()
    mal = Key("mal")
    await meet(e, mal, "Mal")
    await e._on_event(mal.person({"t": "typing", "at": time.time(), "name": "Someone Else"}, kind=KIND_LIVE), "relay")
    assert e.typing_view(ROOM) == [{"pk": mal.ppk, "name": "Mal", "impostor": False}]   # the name book, not the event's own name
    e.typing[ROOM][mal.ppk] = time.time() - TYPING_SHOW - 0.5
    assert e.typing_view(ROOM) == []                                                     # gone after TYPING_SHOW
    await settle(e)
    assert llm.calls == [] and not e._tasks                                              # nothing woke: no reply, no model
    assert e.snapshot(ROOM)["room"]["typing"] == []


async def test_typing_never_makes_anyone_a_member_or_claims_a_name(bare):
    e, _ = bare()
    ghost = Key("ghost")
    await e._on_event(ghost.person({"t": "typing", "name": "Maya", "at": time.time()}, kind=KIND_LIVE), "relay")
    assert e.typing_view(ROOM) == []                      # a key that never said who it is is not shown
    assert ghost.ppk not in {p["pk"] for p in e.members(ROOM)}
    assert e._names_reg(ROOM) == {} or not any(v == ghost.ppk for v in e._names_reg(ROOM).values())
    assert ghost.ppk not in e._art_ok


async def test_a_lookalike_is_flagged_while_typing_and_a_hidden_person_never_shows(bare):
    e, _ = bare()
    real, fake = Key("real"), Key("fake")
    await e._on_event(real.person({"t": "msg", "text": "hi", "name": "Sam"}), "relay")        # live: Sam holds the name
    await e._on_event(fake.person({"t": "msg", "text": "me too", "name": "Sam"}), "relay")
    await settle(e)
    for k in (real, fake):
        await e._on_event(k.person({"t": "typing", "at": time.time()}, kind=KIND_LIVE), "relay")
    view = {t["pk"]: t for t in e.typing_view(ROOM)}
    assert view[real.ppk]["impostor"] is False and view[fake.ppk]["impostor"] is True and view[fake.ppk]["name"] == "Sam"
    await e.hide_person(real.ppk, "Sam")
    assert real.ppk not in {t["pk"] for t in e.typing_view(ROOM)}
    await e._on_event(real.person({"t": "typing", "at": time.time()}, kind=KIND_LIVE), "relay")
    assert real.ppk not in e.typing.get(ROOM, {})


async def test_typing_ends_when_the_message_arrives_and_ignores_agents_replays_and_floods(bare):
    e, _ = bare()
    mal = Key("mal")
    await meet(e, mal, "Mal")
    await e._on_event(mal.person({"t": "typing", "at": time.time()}, kind=KIND_LIVE), "relay")
    assert len(e.typing_view(ROOM)) == 1
    await e._on_event(mal.person({"t": "msg", "text": "there", "name": "Mal", "at": time.time()}, created_at=int(time.time()) + 1), "history")
    assert e.typing_view(ROOM) == []                     # sent it: no longer typing
    # an agent's typing, an old typing event, and one from a room I'm not in
    await e._on_event(mal.agent({"t": "typing", "at": time.time()}, kind=KIND_LIVE), "relay")
    await e._on_event(mal.person({"t": "typing", "at": time.time()}, kind=KIND_LIVE, created_at=int(time.time()) - 60), "relay")
    assert e.typing.get(ROOM, {}) == {}
    # a flood of keys: tracked people stay bounded
    for i in range(80):
        k = Key(f"flood{i}")
        await e._on_event(k.person({"t": "typing"}, kind=KIND_LIVE), "relay")
    assert len(e.typing[ROOM]) <= 32


# --- pictures: what an engine accepts ----------------------------------------------------------------------------------

async def test_a_picture_from_a_person_in_my_room_is_kept_and_served(bare):
    e, _ = bare()
    mal = Key("mal")
    await meet(e, mal)
    ev = art(mal, "avatar", {"img": PNG})
    assert e._take_art(ev) is True
    view = e._art_view(mal.ppk)
    assert view == {"av": ev["id"][:12]}
    got = e.avatars([mal.ppk])
    assert got == {mal.ppk: {"v": ev["id"][:12], "uri": PNG}}   # rebuilt from the checked bytes, same canonical text
    row = e.store.art_get(mal.ppk, "avatar")
    assert row["mime"] == "image/png" and bytes(row["data"]) == png()


async def test_pictures_from_keys_never_seen_in_a_room_or_without_proof_of_work_are_dropped(bare):
    e, _ = bare()
    stranger, mal = Key("stranger"), Key("mal")
    assert e._take_art(art(stranger, "avatar", {"img": PNG})) is False        # never seen in any room
    assert e._art == {}
    await meet(e, mal)
    assert e._take_art(art(mal, "avatar", {"img": PNG}, pow_bits=0)) is False  # no proof of work (almost surely < 12 bits)
    ev = art(mal, "avatar", {"img": PNG}, pow_bits=0)
    while nostr.leading_zero_bits(ev["id"]) >= ART_POW:   # make sure the unlucky 1-in-4096 case can't pass
        ev = art(mal, "avatar", {"img": PNG}, pow_bits=0, created_at=ev["created_at"] - 1)
    assert e._take_art(ev) is False
    assert e._art == {} and e.store.art_index() == []
    # a join alone makes a key "seen in a room"; a reaction does not
    jk, rk = Key("joiner"), Key("reactor")
    await e._on_event(jk.person({"t": "join", "name": "Jo"}), "history")
    await e._on_event(rk.person({"t": "react", "target": "0" * 64, "emoji": "👍", "on": True}), "history")
    assert e._take_art(art(jk, "avatar", {"img": PNG})) is True
    assert e._take_art(art(rk, "avatar", {"img": PNG})) is False


async def test_an_agents_key_never_gets_a_picture_or_face_and_a_hidden_person_is_dropped_and_forgotten(bare):
    e, _ = bare()
    mal, hid = Key("mal"), Key("hid")
    await meet(e, mal)
    await meet(e, hid, "Hid")
    assert e._take_art(art(mal, "avatar", {"img": PNG}, agent=True)) is False    # an `owner` tag: an agent's key
    assert e._take_art(art(mal, "face", {"face": {"hue": 10}}, agent=True)) is False
    assert e._take_art(art(hid, "avatar", {"img": PNG})) is True
    assert e._take_art(art(hid, "face", {"face": {"hue": 10}})) is True
    await e.hide_person(hid.ppk, "Hid")
    assert hid.ppk not in e._art and e.store.art_index() == [] and e.avatars([hid.ppk]) == {}
    assert e._art_view(hid.ppk) == {}
    assert e._take_art(art(hid, "avatar", {"img": WEBP}, created_at=int(time.time()) + 5)) is False   # and stays dropped
    assert e.store.art_get(hid.ppk, "avatar") is None


async def test_the_newest_picture_wins_and_an_empty_one_removes_it(bare):
    e, _ = bare()
    mal = Key("mal")
    await meet(e, mal)
    t = int(time.time()) - 100
    e1, e2, e3 = art(mal, "avatar", {"img": PNG}, created_at=t), art(mal, "avatar", {"img": WEBP}, created_at=t + 10), art(mal, "avatar", {"img": ""}, created_at=t + 20)
    assert e._take_art(e1) and e._take_art(e2)
    assert e.avatars([mal.ppk])[mal.ppk]["uri"] == WEBP
    assert e._take_art(e1) is False                      # the older one replayed: ignored
    assert e._take_art(e3) is True                       # removal
    assert e._art_view(mal.ppk) == {} and e.avatars([mal.ppk]) == {}
    assert e._take_art(e2) is False and e._art_view(mal.ppk) == {}   # the picture it replaced can't come back
    assert e._take_art(art(mal, "avatar", {"img": JPG}, created_at=t + 30)) is True
    assert e.avatars([mal.ppk])[mal.ppk]["uri"] == JPG


async def test_on_a_tie_the_lowest_id_wins_as_nip01_says(bare):
    e, _ = bare()
    mal = Key("mal")
    await meet(e, mal)
    t = int(time.time()) - 50
    a, b = sorted([art(mal, "avatar", {"img": PNG}, created_at=t), art(mal, "avatar", {"img": WEBP}, created_at=t)], key=lambda x: x["id"])
    assert e._take_art(b) and e._take_art(a)             # the lower id replaces the higher
    assert e._art_view(mal.ppk)["av"] == a["id"][:12]
    assert e._take_art(b) is False


@pytest.mark.parametrize("img", [
    "data:image/svg+xml;base64,PHN2Zy8+", "data:image/gif;base64,R0lGODlh", "http://example.com/x.png", "javascript:alert(1)", "x" * 100,
    5, ["a"], {"a": 1}, True, "data:image/png;base64,!!!!", uri(png(513, 64), "image/png"), uri(png(1 << 30, 1 << 30), "image/png"),
    uri(riff(vp8l(16000, 16000)), "image/webp"), uri(jpeg(70000 % 65536 + 600, 10), "image/jpeg"), uri(jpeg(), "image/png"),
    uri(png(idat=bytes(range(256)) * 250), "image/png"),  # over 48 KB
])
async def test_hostile_pictures_are_dropped_and_never_replace_a_good_one(bare, img):
    e, _ = bare()
    mal = Key("mal")
    await meet(e, mal)
    t = int(time.time()) - 100
    assert e._take_art(art(mal, "avatar", {"img": PNG}, created_at=t))
    assert e._take_art(art(mal, "avatar", {"img": img}, created_at=t + 50)) is False
    assert e.avatars([mal.ppk])[mal.ppk]["uri"] == PNG


async def test_odd_content_shapes_are_dropped_and_checked_by_size_before_parsing(bare, monkeypatch):
    e, _ = bare()
    mal = Key("mal")
    await meet(e, mal)
    t = int(time.time()) - 100
    assert e._take_art(art(mal, "avatar", {"img": PNG}, created_at=t))
    for i, junk in enumerate(['[1,2]', 'null', '"s"', '{', '5', json.dumps({"img": PNG, "extra": 1})[:20], json.dumps({"other": 1}),
                              json.dumps({"img": ["x"]}), json.dumps({"img": 7})]):
        # {"other": 1} or {"img": 7}: not a valid picture, not an empty one either
        assert e._take_art(art(mal, "avatar", junk, created_at=t + 1 + i)) is False
    assert e.avatars([mal.ppk])[mal.ppk]["uri"] == PNG
    called = []
    monkeypatch.setattr(avatar, "check_avatar", lambda u: called.append(1))
    huge = art(mal, "avatar", json.dumps({"img": "A" * 200_000}), created_at=t + 60)
    assert e._take_art(huge) is False and not called      # refused on size alone: no parsing, no base64
    # a face event over a kilobyte
    assert e._take_art(art(mal, "face", json.dumps({"face": {"hue": 1, "pad": "x" * 2000}}))) is False


async def test_faces_are_reduced_to_known_options_and_junk_faces_are_dropped(bare):
    e, _ = bare()
    mal = Key("mal")
    await meet(e, mal)
    t = int(time.time()) - 100
    wild = {"hue": "999999999999", "shape": "<script>", "eyes": "visor", "mouth": 7, "acc": "halo", "pattern": ["x"], "img": "data:", "card": "scanner"}
    assert e._take_art(art(mal, "face", {"face": wild}, created_at=t))
    f = e._art_view(mal.ppk)["face"]
    assert f == clean_face(wild) and f["shape"] == "round" and f["eyes"] == "visor" and f["acc"] == "halo" and "img" not in f
    for i, bad in enumerate(['"face"', '[1]', '{"face": "x"}', '{"face": 5}', '{"face": [1]}', '{"nope": 1}']):
        assert e._take_art(art(mal, "face", bad, created_at=t + 1 + i)) is False
    assert e._take_art(art(mal, "face", {"face": None}, created_at=t + 20)) is True    # taking it away
    assert e._art_view(mal.ppk) == {}


async def test_pictures_off_means_no_stranger_bytes_are_kept_and_on_asks_again(bare):
    e, _ = bare()
    e.pool = ArtPool()
    mal = Key("mal")
    await meet(e, mal)
    t = int(time.time()) - 50
    assert e._take_art(art(mal, "avatar", {"img": PNG}, created_at=t))
    assert e._take_art(art(mal, "face", {"face": {"hue": 77}}, created_at=t))
    e.save_settings({"show_avatars": "nobody"})
    assert e.store.art_get(mal.ppk, "avatar") is None and e._art_view(mal.ppk).get("av") is None
    assert e._art_view(mal.ppk)["face"]["hue"] == 77 and e.avatars([mal.ppk]) == {}      # a built face is not an image
    assert e._take_art(art(mal, "avatar", {"img": WEBP}, created_at=t + 1)) is False        # not kept while off
    assert e._take_art(art(mal, "face", {"face": {"hue": 78}}, created_at=t + 1)) is True
    e._art_sent = ("x",)
    e.save_settings({"show_avatars": "everyone"})
    assert e._art_sent is None                                                              # the next request asks again
    assert e._take_art(art(mal, "avatar", {"img": WEBP}, created_at=int(time.time()) + 3)) is True
    assert e.settings()["show_avatars"] == "everyone"
    e.save_settings({"show_avatars": "bogus"})
    assert e.settings()["show_avatars"] == "everyone"


async def test_avatars_serves_at_most_eight_and_only_what_is_valid(bare):
    e, _ = bare()
    keys = [Key(f"k{i}") for i in range(12)]
    for k in keys:
        await meet(e, k, f"K{keys.index(k)}")
        assert e._take_art(art(k, "avatar", {"img": PNG}))
    out = e.avatars([k.ppk for k in keys])
    assert len(out) == 8
    assert e.avatars(["nothex", 5, None, {"a": 1}, "0" * 64]) == {}
    assert e.avatars("not a list") == {} and e.avatars(None) == {}
    # a row that no longer matches the version in memory is not served
    e.store.art_put(keys[0].ppk, "avatar", "f" * 64, 1, "image/png", png(), time.time())
    assert keys[0].ppk not in e.avatars([keys[0].ppk])


async def test_storage_is_capped_and_my_own_picture_is_never_pushed_out(bare, monkeypatch):
    from ninsei_engine import store as store_mod
    monkeypatch.setattr(store_mod, "ART_AVATARS", 5)
    e, _ = bare()
    e.save_settings({"onboarded": True})
    await e.set_avatar(PNG)
    me = e._identity()["person_pk"]
    for i in range(9):
        k = Key(f"cap{i}")
        await meet(e, k, f"Cap{i}")
        assert e._take_art(art(k, "avatar", {"img": WEBP}))
    kept = [r for r in e.store.art_index() if r["kind"] == "avatar" and r["size"]]
    assert len(kept) == 6 and any(r["pk"] == me for r in kept)      # five of others, and mine
    assert sum(1 for pk, h in e._art.items() if "avatar" in h and pk != me) == 5   # memory follows the store


# --- publishing my own ---------------------------------------------------------------------------------------------------

async def test_my_picture_is_published_as_a_replaceable_event_with_proof_of_work_and_no_lobby_tag(bare):
    e, _ = bare()
    res = await e.set_avatar(PNG)
    ev = (await out(e))[-1]
    assert ev["id"] == res["id"] and ev["kind"] == KIND_META and nostr.tag_values(ev, "d") == [ART_AVATAR_D]
    assert nostr.leading_zero_bits(ev["id"]) >= ART_POW and nostr.check_event(ev)
    assert nostr.tag_values(ev, "t") == []                               # the lobby's `#t ninsei` query must never match it
    assert json.loads(ev["content"]) == {"img": PNG}
    me = e._identity()["person_pk"]
    assert e._art_view(me)["av"] == ev["id"][:12] and e.avatars([me])[me]["uri"] == PNG   # mine is served at once
    assert e.store.event_outbox_status(ev["id"]) in ("pending", "sent")                     # durable, like a card
    assert (await e.set_avatar(PNG)) == {"ok": True, "unchanged": True}                     # nothing sent for the same picture
    n = len(await out(e))
    await e.set_avatar("")                                                                  # removal is an empty one
    assert json.loads((await out(e))[-1]["content"]) == {"img": ""} and len(e.pool.sent) == n + 1
    assert e._art_view(me).get("av") is None
    assert (await e.set_avatar("")) == {"ok": True, "unchanged": True}


async def test_my_picture_must_be_a_checked_picture_without_metadata(bare):
    e, _ = bare()
    for bad in ("data:image/svg+xml;base64,PHN2Zy8+", "nonsense", uri(png(600, 600), "image/png"), None, 5):
        with pytest.raises(ValueError):
            await e.set_avatar(bad)
    with pytest.raises(ValueError, match="EXIF"):
        await e.set_avatar(uri(jpeg(extra=[(0xE1, b"Exif\0\0MM\0*" + b"\0" * 20)]), "image/jpeg"))
    with pytest.raises(ValueError, match="tEXt"):
        await e.set_avatar(uri(png(extra=[(b"tEXt", b"GPS\0 here")]), "image/png"))
    assert await out(e) == []
    e.save_settings({"onboarded": False})
    with pytest.raises(ValueError, match="setup"):
        await e.set_avatar(PNG)


async def test_changes_to_my_picture_and_face_are_paced(bare):
    e, _ = bare()
    imgs = [uri(png(32 + i, 32), "image/png") for i in range(6)]
    for i in range(5):
        await e.set_avatar(imgs[i])
    with pytest.raises(ValueError, match="Slow down"):
        await e.set_avatar(imgs[5])
    e.save_settings({"person_face": {"hue": 3}})
    with pytest.raises(ValueError, match="Slow down"):
        await e.publish_face()


async def test_my_face_is_published_once_per_change_and_can_be_taken_away(bare):
    e, _ = bare()
    assert (await e.publish_face()) == {"sent": False, "unchanged": True}      # never chose one: nothing to say
    assert await out(e) == []
    e.save_settings({"person_face": {"hue": 120, "shape": "tall", "eyes": "visor", "bogus": 1}})
    face = e.settings()["person_face"]
    assert face == clean_face({"hue": 120, "shape": "tall", "eyes": "visor"})
    res = await e.publish_face()
    ev = (await out(e))[-1]
    assert res["sent"] and ev["kind"] == KIND_META and nostr.tag_values(ev, "d") == [ART_FACE_D] and nostr.leading_zero_bits(ev["id"]) >= ART_POW
    assert nostr.tag_values(ev, "t") == [] and json.loads(ev["content"]) == {"face": face}
    assert (await e.publish_face()) == {"sent": False, "unchanged": True}
    e.save_settings({"person_face": {}})                                        # "use my initial"
    assert e.settings()["person_face"] is None
    await e.publish_face()
    assert json.loads((await out(e))[-1]["content"]) == {"face": None}
    assert e._art_view(e._identity()["person_pk"]) == {}
    e.save_settings({"person_face": "nonsense"})
    assert e.settings()["person_face"] is None


# --- what the UI is told ---------------------------------------------------------------------------------------------------

async def test_the_snapshot_lists_art_for_me_the_room_and_my_conversations_but_never_for_lookalikes_or_requests(bare):
    e, _ = bare()
    e.save_settings({"person_face": {"hue": 50}})
    real, fake, dm_friend, stranger = Key("real"), Key("fake"), Key("friend"), Key("stranger")
    await e._on_event(real.person({"t": "msg", "text": "hi", "name": "Sam"}), "relay")
    await e._on_event(fake.person({"t": "msg", "text": "me too", "name": "Sam"}), "relay")
    await meet(e, dm_friend, "Fran")
    await settle(e)
    for k in (real, fake, dm_friend):
        e._take_art(art(k, "avatar", {"img": PNG}))
        e._take_art(art(k, "face", {"face": {"hue": 200}}))
    me = e._identity()["person_pk"]
    # a conversation with Fran (met in a room: accepted) and with a stranger (a request, who has a picture on the relays too)
    now = time.time()
    e.store.dm_add(id="a" * 64, peer=dm_friend.ppk, sender=dm_friend.ppk, text="hi", created_at=int(now), arrived_at=now, accepted=True, wrap=None)
    e.store.dm_add(id="b" * 64, peer=stranger.ppk, sender=stranger.ppk, text="psst", created_at=int(now), arrived_at=now, accepted=False, wrap=None)
    e._take_art(art(stranger, "avatar", {"img": PNG}))   # never seen in a room: not stored in the first place
    snap = e.snapshot(ROOM)
    people = snap["people"]
    assert people[me]["face"]["hue"] == 50
    assert real.ppk in people and people[real.ppk]["av"] and people[real.ppk]["face"]["hue"] == 200
    assert dm_friend.ppk in people and {t["pk"] for t in snap["dms"]["threads"]} == {dm_friend.ppk, stranger.ppk}
    assert fake.ppk not in people                       # a lookalike of "Sam" gets neither picture nor face
    assert stranger.ppk not in people
    json.dumps(snap)
    assert len(json.dumps(people)) < 2000                # small: versions and faces, never image bytes
    assert PNG not in json.dumps(snap)


async def test_art_never_reaches_a_model_or_an_agents_transcript(bare):
    e, llm = bare()
    mal = Key("mal")
    await meet(e, mal)
    e._take_art(art(mal, "avatar", {"img": PNG}))
    e._take_art(art(mal, "face", {"face": {"hue": 9}}))
    assert PNG.split(",")[1][:40] not in json.dumps([l.__dict__ if hasattr(l, "__dict__") else str(l) for l in e._transcript(ROOM)])
    await e._on_event(mal.person({"t": "msg", "text": "@Ada hello", "name": "Mal", "at": time.time()}), "relay")
    await settle(e)
    sent = json.dumps(llm.calls)
    assert "data:image" not in sent
    import inspect
    from ninsei_engine import brain
    assert "avatar" not in inspect.getsource(brain).lower() and "person_art" not in inspect.getsource(brain)


# --- the subscription -------------------------------------------------------------------------------------------------------

async def test_the_art_subscription_asks_for_the_people_of_my_rooms_in_small_filters(bare):
    e, _ = bare()
    e.pool = ArtPool()
    me = e._identity()["person_pk"]
    keys = [Key(f"p{i}") for i in range(ART_AUTHORS + 40)]
    for i, k in enumerate(keys):
        await e._on_event(k.person({"t": "msg", "text": "x", "name": f"P{i}", "at": time.time()}, created_at=int(time.time()) - 1000 + i), "history")
    hidden = keys[-1]
    await e.hide_person(hidden.ppk, "P")
    await e._art_subscribe()
    (sid, filters), = e.pool.subs
    assert sid == "art" and len(filters) <= 8
    authors = [a for f in filters for a in f["authors"]]
    assert authors[0] == me and len(authors) == len(set(authors)) == ART_AUTHORS and hidden.ppk not in authors
    assert all(len(f["authors"]) <= 50 and f["kinds"] == [KIND_META] and f["#d"] == [ART_AVATAR_D, ART_FACE_D] for f in filters)
    assert keys[-2].ppk in authors and keys[0].ppk not in authors      # the newest activity first; the oldest are left out
    await e._art_subscribe()
    assert len(e.pool.subs) == 1                                         # nothing changed: no second request
    newcomer = Key("newcomer")
    await e._on_event(newcomer.person({"t": "msg", "text": "x", "name": "New", "at": time.time()}), "history")
    await e._art_subscribe()
    assert len(e.pool.subs) == 2 and newcomer.ppk in [a for f in e.pool.subs[-1][1] for a in f["authors"]]


async def test_leaving_every_room_stops_the_art_subscription(bare):
    e, _ = bare()
    e.pool = ArtPool()
    await e._resubscribe()
    assert any(s == "art" for s, _ in e.pool.subs)
    e.store.forget_room(ROOM)
    await e._resubscribe()
    assert "art" in e.pool.unsubs


# --- hostile junk through the front door ---------------------------------------------------------------------------------------

async def test_random_junk_art_events_never_break_an_engine(bare):
    e, _ = bare()
    mal = Key("mal")
    await meet(e, mal)
    rng = random.Random(7)
    t = int(time.time())
    for i in range(150):
        kind = rng.choice(["avatar", "face"])
        field = "img" if kind == "avatar" else "face"
        val = rng.choice([None, True, 5, 1.5, "", "x" * rng.randint(0, 80), [], {}, {"a": 1}, PNG[:rng.randint(0, 120)], {"hue": rng.random() * 1e9}, [PNG]])
        content = rng.choice([json.dumps({field: val}), "[1]", "null", "{", "", json.dumps({field: val, "z": 1})])
        tags = [["d", rng.choice([ART_AVATAR_D, ART_FACE_D, "x", ""])]] + ([["owner", "zz", "yy"]] if rng.random() < 0.1 else [])
        ev = nostr.build_event(rng.choice([mal.psk, mal.ask]), KIND_META, content, tags, pow_bits=rng.choice([0, ART_POW]), created_at=t - rng.randint(0, 5000))
        await e._on_event(ev, "relay")
    json.dumps(e.snapshot(ROOM))
    json.dumps(e.avatars([mal.ppk]))


# --- two installs over a local relay ---------------------------------------------------------------------------------------------

async def test_two_installs_see_each_others_picture_face_and_typing(world):
    relay, engines, _ = world
    maya, sam = engines["Maya"], engines["Sam"]
    room = await setup_room(engines)
    maya_pk = read(maya, lambda: maya._identity()["person_pk"])
    # say something so Sam has seen Maya in the room, then change the picture and the face
    await run(maya, maya.post, room, "hello")
    assert await wait_for(lambda: maya_pk in read(sam, lambda: sam._art_ok))
    await run(maya, maya.set_avatar, PNG)
    maya.save_settings({"person_face": {"hue": 140, "eyes": "visor"}})
    await run(maya, maya.publish_face)
    # Sam's engine asks for Maya's pictures on its own (debounced) once she is seen in the room
    assert await wait_for(lambda: read(sam, sam.avatars, [maya_pk]).get(maya_pk, {}).get("uri") == PNG), "the picture never arrived"
    assert await wait_for(lambda: "face" in read(sam, sam.snapshot, room)["people"].get(maya_pk, {}))
    people = read(sam, sam.snapshot, room)["people"]
    assert people[maya_pk]["face"]["hue"] == 140 and people[maya_pk]["face"]["eyes"] == "visor" and people[maya_pk]["av"]
    # a new picture replaces the old one on the other side too (the live subscription delivers it)
    await run(maya, maya.set_avatar, WEBP)
    assert await wait_for(lambda: read(sam, sam.avatars, [maya_pk]).get(maya_pk, {}).get("uri") == WEBP)
    # removal
    await run(maya, maya.set_avatar, "")
    assert await wait_for(lambda: not read(sam, sam.avatars, [maya_pk]))
    # typing: shown to Sam while Maya's agent and Sam's agent beat in the room, gone when her message arrives
    assert await wait_for(lambda: read(maya, maya._others_here, room))
    assert (await run(maya, maya.typing_signal, room))["sent"]
    assert await wait_for(lambda: [t["name"] for t in read(sam, sam.snapshot, room)["room"]["typing"]] == ["Maya"])
    await run(maya, maya.post, room, "done")
    assert await wait_for(lambda: read(sam, sam.snapshot, room)["room"]["typing"] == [])
