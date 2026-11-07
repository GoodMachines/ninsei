"""Audit docs and integration (items 9, 11, 23, 30, 41-47, and the bad-owner-tag gap left open by item 3).

The docs are what a reviewer and a user trust, so each test pins a sentence the code made true, or forbids
one the code made false.
"""
import json
import re
from pathlib import Path

from ninsei_engine import nostr
from ninsei_engine.engine import KIND_LIVE, KIND_ROOM

from test_hostile import ROOM, Key, bare, settle  # noqa: F401  (fixture re-export)

ROOT = Path(__file__).resolve().parents[1]


def text(*names: str) -> str:
    return "\n".join((ROOT / n).read_text() for n in names)


README, ARCH = "README.md", "ARCHITECTURE.md"
PR, ENTRY, DEMO = "submission/catalog-pr.md", "submission/ninsei.yaml", "submission/demo-script.md"
PUBLISHED = (README, ARCH, PR, ENTRY)


# --- item 11: what a toy can still reach --------------------------------------------------------------

def test_no_text_says_a_toy_cannot_reach_the_network():
    false_claims = ("can't reach the network", "can't make network requests", "blocks network requests",
                    "can't make network requests", "can’t fetch from the network", "can't fetch from the network")
    for f in (*PUBLISHED, "ui/50_room.js"):
        body = text(f)
        for claim in false_claims:
            assert claim not in body, (f, claim)


def test_every_published_text_says_webrtc_is_not_blocked():
    for f in PUBLISHED:
        assert "WebRTC" in text(f), f
    assert "does not block WebRTC" in text(README) and "does not block WebRTC" in text(PR)
    assert "**It does not block WebRTC:**" in text(ARCH)
    assert text("ui/50_room.js").count("WebRTC connection") == 2   # the share dialog and the shared toy card


# --- item 9: names --------------------------------------------------------------------------------------

def test_names_docs_describe_the_live_rule_and_contested_history():
    readme, arch = text(README), text(ARCH)
    assert "a name belongs to the first key that says something under it," not in readme
    assert "saying something under it live" in readme and "nobody holds it" in readme
    assert "**live**" in arch and "`CONTESTED`" in arch


# --- item 23: the vibe is not private -------------------------------------------------------------------

def test_vibe_is_never_described_as_private():
    assert "Only you see its vibe" not in text("ui/35_card.js")
    assert "can repeat it" in text("ui/35_card.js") and "can repeat it there" in text("ui/40_setup.js")
    assert "can repeat it if asked" in text(README) and "it is not private" in text(ARCH)


# --- item 30: what leaves the machine ---------------------------------------------------------------------

def test_what_leaves_lists_beats_offer_decisions_game_moves_joins_and_both_switches():
    readme = text(README).split("- What leaves your machine", 1)[1].split("\n- ", 1)[0]
    for needle in ("status beat to each room you're in, every minute", "your yes or no", "votes and agent flags",
                   "join message for every room", "Show my agent's vibe and model on its card",
                   "Show my agent's budget to the room"):
        assert needle in readme, needle
    pr = text(PR)
    for needle in ("status beat to each joined room every minute", "accept or decline", "votes and flags", "every room joined"):
        assert needle in pr, needle


# --- items 41, 42, 43: catalog wording ---------------------------------------------------------------------

def test_catalog_scopes_the_random_boundary_to_the_build_prompt():
    pr = text(PR)
    assert "inside boundary lines that change on every call" not in pr
    assert "The build prompt also fences room quotes between random boundary lines" in pr


def test_catalog_entry_does_not_call_the_hooks_read_only():
    entry = text(ENTRY)
    assert "read-only" not in entry and "observe-only" in entry and "SQLite" in entry


def test_owner_messages_are_not_described_as_unlimited():
    for f in (PR, "ninsei_engine/engine.py"):
        assert "never limited" not in text(f), f
    assert "pacing" in text(PR) and "pacing" in text(ARCH)


# --- items 44-47: README and ARCHITECTURE facts ----------------------------------------------------------

def test_huddo_is_not_called_a_matching_tool():
    readme = text(README)
    assert "Huddo and index-network match people" not in readme
    assert "Huddo also puts people and agents in one chat" in readme


def test_architecture_has_no_stale_floor_issue_and_the_right_at_unit():
    arch = text(ARCH)
    assert "open issue" not in arch and "`_allowed_prio`" in arch
    assert "millisecond stamp" not in arch and "Unix seconds with millisecond precision" in arch


def test_rooms_for_you_says_active_rooms_come_first():
    readme = text(README)
    assert "suggests up to three rooms that match your interests" not in readme
    assert "rooms where people are talking today first" in readme
    assert "r.live || (r.overlap || []).length" in text("ui/70_lobby.js")   # the rule the sentence describes


def test_architecture_stays_near_its_budget():
    """ARCHITECTURE.md is read first by every agent: rewrite it, don't append to it. The budget is about
    1,500 words; trim the file to fit, never raise this cap to fit the file."""
    assert len(text(ARCH).split()) <= 1500


def test_docs_have_no_em_dashes():
    for f in (*PUBLISHED, DEMO):
        assert "—" not in text(f), f


# --- integration: item 3's open gap, an owner tag whose binding fails ----------------------------------

async def test_an_event_with_a_broken_owner_tag_is_dropped(bare):
    e, _ = bare()
    mallory = Key("mallory")
    await e.hide_person(mallory.ppk, "Mallory")
    bad = []
    for owner in (mallory.ppk.upper(), mallory.ppk[:8] + " " + mallory.ppk[8:], Key("someone").ppk):
        tags = [["h", ROOM], ["owner", owner, mallory.bind]]
        ev = nostr.build_event(mallory.ask, KIND_ROOM, json.dumps({"t": "msg", "text": "back", "name": "Rex"}), tags)
        beat = nostr.build_event(mallory.ask, KIND_LIVE, json.dumps({"t": "presence", "name": "Rex", "state": "x"}), tags)
        await e._on_event(ev, "relay")
        await e._on_event(beat, "relay")
        bad.append(ev["id"])
    await settle(e)
    assert not set(bad) & set(e.events[ROOM])
    assert mallory.apk not in (e.presence.get(ROOM) or {})
    # a valid binding from someone who isn't hidden still arrives
    sam = Key("sam")
    ok = sam.agent({"t": "msg", "text": "hi", "name": "Bo"})
    await e._on_event(ok, "relay")
    await settle(e)
    assert ok["id"] in e.events[ROOM]
    assert re.fullmatch(r"[0-9a-f]{64}", ok["id"])
