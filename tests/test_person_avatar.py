"""A person's avatar (the id of a premade portrait) on the engine side: clean_avatar's strict cleaning, settings, the avatar riding in the face
event (size, round trip, what an older client sees, taking it away), what the UI is told (never for a lookalike),
pacing, and the stored form surviving a restart."""
import json
import time
from pathlib import Path

import pytest

from ninsei_engine import nostr
from ninsei_engine.engine import ART_FACE_BYTES, ART_FACE_D, AV_PRESETS, KIND_META, _art_want, clean_avatar, clean_face
from test_hostile import Key, ROOM, bare, settle  # noqa: F401  (fixture re-export)
from test_pictures import art, meet, out

ROOT = Path(__file__).resolve().parents[1]
FULL = {"v": 1, "p": "p12"}


# --- clean_avatar -------------------------------------------------------------------------------------------------------

def test_only_a_version_one_object_naming_a_known_preset_is_an_avatar():
    for junk in (None, "x", 5, [], [{"v": 1}], {}, {"p": "p01"}, {"v": 2, "p": "p01"}, {"v": "1", "p": "p01"}, {"v": True, "p": "p01"},
                 {"v": 1.0, "p": "p01"}, {"v": 0, "p": "p01"}):
        assert clean_avatar(junk) is None, junk


def test_an_unknown_preset_is_no_avatar_never_a_default_portrait():
    for p in (None, 1, True, ["p01"], {"p": "p01"}, "", "P01", " p01", "p01 ", "p1", "p00", "p35", "p999", "../p01", "<b>", "p01\u200b", "sk"):
        assert clean_avatar({"v": 1, "p": p}) is None, p
    assert clean_avatar({"v": 1}) is None and clean_avatar({"v": 1, "sk": 3, "hs": "bun"}) is None   # phase 1's layers are gone
    assert clean_avatar({"v": 1, "p": "p01"}) == {"v": 1, "p": "p01"} and clean_avatar(FULL) == FULL


def test_other_keys_are_dropped_and_cleaning_is_idempotent():
    got = clean_avatar({"v": 1, "p": "p07", "img": "data:image/png;base64,AAAA", "name": "x", "sk": 3})
    assert got == {"v": 1, "p": "p07"} and list(got) == ["v", "p"]
    assert clean_avatar(got) == got
    assert all(clean_avatar({"v": 1, "p": p}) == {"v": 1, "p": p} for p in AV_PRESETS)


def test_the_engines_preset_ids_are_exactly_the_portraits_the_page_ships():
    rows = json.loads((ROOT / "docs/media/src/presets/presets.json").read_text())
    assert list(AV_PRESETS) == [r["id"] for r in rows]                                  # same ids, same order
    assert len(set(AV_PRESETS)) == len(AV_PRESETS) >= 32
    for r in rows:
        assert (ROOT / "docs/media/src/presets" / (r["id"] + ".png")).is_file() and r["alt"].strip()


# --- settings ------------------------------------------------------------------------------------------------------------

async def test_settings_keep_a_clean_avatar_and_anything_else_clears_it(bare):
    e, _ = bare()
    assert e.settings()["person_avatar"] is None                                       # never made up: nothing until built
    e.save_settings({"person_avatar": dict(FULL, junk=1)})
    assert e.settings()["person_avatar"] == FULL and "junk" not in e.settings()["person_avatar"]
    for clear in ({}, None, "x", {"v": 2}, {"v": 1, "p": "nope"}):
        e.save_settings({"person_avatar": FULL})
        e.save_settings({"person_avatar": clear})
        assert e.settings()["person_avatar"] is None, clear
    e.save_settings({"person_avatar": FULL, "display_name": "Maya"})
    assert e.snapshot(ROOM)["settings"]["person_avatar"] == clean_avatar(FULL)


# --- the wire ----------------------------------------------------------------------------------------------------------------

async def test_the_avatar_rides_in_the_face_event_and_reads_back_the_same_on_another_install(bare):
    e, _ = bare()
    face = clean_face({"hue": 200, "shape": "tall", "eyes": "visor", "mouth": "grin", "acc": "headphones", "pattern": "freckles"})
    e.save_settings({"person_face": face, "person_avatar": FULL})
    res = await e.publish_face()
    ev = (await out(e))[-1]
    assert res["sent"] and ev["kind"] == KIND_META and nostr.tag_values(ev, "d") == [ART_FACE_D]
    body = json.loads(ev["content"])
    assert body == {"face": face, "avatar": clean_avatar(FULL)}
    assert len(ev["content"]) < ART_FACE_BYTES / 2                                      # a preset id plus a face: well under
    assert " " not in ev["content"]                                                      # compact
    # another install, meeting me in a room, takes the same event content and shows the same avatar
    other, _ = bare("Sam", "Bo")
    maya = Key("maya")
    await meet(other, maya, "Maya")
    assert other._take_art(art(maya, "face", ev["content"]))
    assert other._art_view(maya.ppk) == {"face": face, "avatar": clean_avatar(FULL)}
    # what a client from before avatars reads: the "face" key, exactly as it always was
    assert clean_face(body["face"]) == face


async def test_a_face_alone_goes_out_exactly_as_before_so_an_upgrade_does_not_republish(bare):
    e, _ = bare()
    face = clean_face({"hue": 120})
    assert _art_want(face, None) == json.dumps(face, sort_keys=True)                    # the stored form from before avatars
    assert _art_want(None, None) == ""
    e.save_settings({"person_face": face})
    e.store.set("face_sent", json.dumps(face, sort_keys=True))                           # what an older version recorded
    assert (await e.publish_face()) == {"sent": False, "unchanged": True}
    e.save_settings({"person_avatar": FULL})                                             # building an avatar is a change
    assert (await e.publish_face())["sent"]
    assert (await e.publish_face()) == {"sent": False, "unchanged": True}
    e.save_settings({"person_avatar": {}})                                               # "use my initial instead"
    assert (await e.publish_face())["sent"]
    assert json.loads((await out(e))[-1]["content"]) == {"face": face}


async def test_an_avatar_without_a_face_and_taking_both_away(bare):
    e, _ = bare()
    e.save_settings({"person_avatar": FULL})
    await e.publish_face()
    assert json.loads((await out(e))[-1]["content"]) == {"face": None, "avatar": clean_avatar(FULL)}
    me = e._identity()["person_pk"]
    assert e._art_view(me) == {"avatar": clean_avatar(FULL)}
    mal = Key("mal")
    await meet(e, mal)
    t = int(time.time()) - 100
    assert e._take_art(art(mal, "face", {"face": None, "avatar": FULL}, created_at=t))
    assert e._art_view(mal.ppk) == {"avatar": clean_avatar(FULL)}
    assert e._take_art(art(mal, "face", {"face": None}, created_at=t + 1))                # taking it away
    assert e._art_view(mal.ppk) == {}


async def test_junk_avatars_never_show_and_a_later_version_reads_as_none(bare):
    e, _ = bare()
    mal = Key("mal")
    await meet(e, mal)
    t = int(time.time()) - 100
    face = {"hue": 40}
    assert e._take_art(art(mal, "face", {"face": face, "avatar": "x"}, created_at=t))   # a good face with a junk avatar
    assert e._art_view(mal.ppk) == {"face": clean_face(face)}
    odd = Key("odd")
    await meet(e, odd, "Odd")
    assert e._take_art(art(odd, "face", {"face": face, "avatar": {"v": 1, "p": "p99"}}, created_at=t))     # unknown preset: no avatar, no stand-in
    assert e._art_view(odd.ppk) == {"face": clean_face(face)}
    assert e._take_art(art(mal, "face", {"face": face, "avatar": FULL}, created_at=t + 1))
    assert e._art_view(mal.ppk)["avatar"] == clean_avatar(FULL)
    # a newer client's avatar this version can't read: their newest word still replaces what was shown
    assert e._take_art(art(mal, "face", {"face": None, "avatar": {"v": 2, "parts": [1]}}, created_at=t + 2))
    assert e._art_view(mal.ppk) == {}
    for i, bad in enumerate(['{"avatar": 5, "other": 1}', '{"face": "x", "avatar": {"v": 1}}', '{"nope": 1}']):
        assert e._take_art(art(mal, "face", bad, created_at=t + 3 + i)) is False
    big = json.dumps({"face": face, "avatar": dict(FULL, pad="x" * ART_FACE_BYTES)})
    assert e._take_art(art(mal, "face", big, created_at=t + 9)) is False                # size is checked before parsing


async def test_a_lookalike_gets_no_avatar_and_neither_does_an_agents_key(bare):
    e, _ = bare()
    real, fake = Key("real"), Key("fake")
    await e._on_event(real.person({"t": "msg", "text": "hi", "name": "Sam"}), "relay")
    await e._on_event(fake.person({"t": "msg", "text": "me too", "name": "Sam"}), "relay")
    await settle(e)
    for k in (real, fake):
        assert e._take_art(art(k, "face", {"face": None, "avatar": FULL}))
    people = e.snapshot(ROOM)["people"]
    assert people[real.ppk]["avatar"] == clean_avatar(FULL)
    assert fake.ppk not in people                                                        # copying Sam's avatar gains nothing
    assert e.people_art([real.ppk, fake.ppk], flagged=[fake.ppk]) == {real.ppk: {"avatar": clean_avatar(FULL)}}
    assert e._take_art(art(real, "face", {"face": None, "avatar": FULL}, agent=True)) is False


async def test_the_stored_avatar_survives_a_restart_and_old_rows_still_load(bare):
    e, _ = bare()
    mal, old = Key("mal"), Key("old")
    await meet(e, mal)
    await meet(e, old, "Old")
    assert e._take_art(art(mal, "face", {"face": {"hue": 5}, "avatar": FULL}))
    assert e._take_art(art(old, "face", {"face": {"hue": 6}}))                            # stored the old way: the face alone
    assert json.loads(bytes(e.store.art_get(old.ppk, "face")["data"])) == clean_face({"hue": 6})
    before = {pk: e._art_view(pk) for pk in (mal.ppk, old.ppk)}
    e._art.clear()
    e._art_load()
    assert {pk: e._art_view(pk) for pk in (mal.ppk, old.ppk)} == before
    assert before[mal.ppk]["avatar"] == clean_avatar(FULL) and "avatar" not in before[old.ppk]


async def test_changing_only_the_avatar_is_paced_like_a_face(bare):
    e, _ = bare()
    for i in range(5):
        e.save_settings({"person_avatar": dict(FULL, p=AV_PRESETS[i])})
        await e.publish_face()
    e.save_settings({"person_avatar": dict(FULL, p=AV_PRESETS[0])})
    await e.check_looks_pace({"person_avatar": dict(FULL, p=AV_PRESETS[4])})                         # what was last sent: no change, no refusal
    with pytest.raises(ValueError, match="Slow down"):
        await e.check_looks_pace({"person_avatar": dict(FULL, p=AV_PRESETS[8])})
    with pytest.raises(ValueError, match="Slow down"):
        await e.check_looks_pace({"person_face": {"hue": 9}})                             # the face rides in the same event
    assert e.settings()["person_avatar"]["p"] == AV_PRESETS[0]                                      # a refused check changes nothing saved
