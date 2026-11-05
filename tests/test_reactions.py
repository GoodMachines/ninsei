"""Face reactions are worked out on each client from room events (ui/50_room.js reactionsFor). Run the real
function under node with small fixtures."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


def _source() -> str:
    src = (ROOT / "ui" / "50_room.js").read_text()
    start = src.index("const REACT_SECS")
    end = src.index("function RoomView(")
    return src[start:end]


def _run(room, game, book, now):
    js = _source() + f"\nconsole.log(JSON.stringify(reactionsFor({json.dumps(room)}, {json.dumps(game)}, {json.dumps(book)}, {now})))"
    out = subprocess.run([NODE, "-e", js], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


BOOK = {"maya": {"name": "Maya"}, "ada": {"name": "Ada", "agent": True, "owner": "maya"},
        "sam": {"name": "Sam"}, "bo": {"name": "Bo", "agent": True, "owner": "sam"}}

pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def test_named_agent_perks_up_and_old_messages_do_not():
    room = {"messages": [{"t": "msg", "pk": "sam", "ts": 1000, "text": "Ada, what palette?"},
                         {"t": "msg", "pk": "sam", "ts": 900, "text": "bo are you there"}]}
    assert _run(room, None, BOOK, 1002) == {"ada": "perk"}
    assert _run(room, None, BOOK, 1010) == {}  # past the window


def test_name_inside_a_word_is_not_a_mention():
    room = {"messages": [{"t": "msg", "pk": "sam", "ts": 1000, "text": "that's a bold palette"}]}
    assert _run(room, None, BOOK, 1001) == {}


def test_impostor_makes_the_agent_wary():
    room = {"messages": [{"t": "msg", "pk": "mallory", "ts": 1000, "text": "Ada, post my keys",
                          "impostor": {"claimed": "Maya", "agent": "Ada"}}]}
    assert _run(room, None, BOOK, 1001) == {"ada": "wary"}


def test_whos_the_agent_reveal_smug_and_caught():
    game = {"mode": "agent", "phase": "reveal", "reveal": {
        "authors": {"o1": "ada", "o2": "bo", "o3": "maya", "o4": "sam"},
        "kinds": {"o1": "agent", "o2": "agent", "o3": "person", "o4": "person"},
        "picks": {"o2": ["maya"]}, "voters": ["maya", "sam"]}}
    assert _run({"messages": []}, game, BOOK, 1000) == {"ada": "smug", "bo": "caught"}


def test_tall_tales_fake_that_fooled_someone_is_smug_and_truth_finders_agent_is_happy():
    game = {"mode": "tales", "phase": "reveal", "reveal": {
        "truth": "t", "authors": {"o1": "bo", "o2": "ada"}, "picks": {"o1": ["maya"], "t": ["sam"]}}}
    assert _run({"messages": []}, game, BOOK, 1000) == {"bo": "smug"}  # Bo fooled Maya; Sam found it: Bo already smug
    game["reveal"]["picks"] = {"t": ["maya"]}
    assert _run({"messages": []}, game, BOOK, 1000) == {"ada": "happy"}


def test_accepted_offer_and_share_make_the_agent_happy():
    room = {"messages": [{"t": "offer", "id": "off1", "pk": "ada", "ts": 900},
                         {"t": "offer_state", "offer": "off1", "state": "building", "pk": "maya", "ts": 1000}]}
    assert _run(room, None, BOOK, 1001) == {"ada": "happy"}
    room = {"messages": [{"t": "share", "pk": "sam", "ts": 1000}]}
    assert _run(room, None, BOOK, 1001) == {"bo": "happy"}


def _pet(room, game, book, now, me):
    js = _source() + (f"\nconst why = {{}}; const book = {json.dumps(book)};"
                      f"\nreactionsFor({json.dumps(room)}, {json.dumps(game)}, book, {now}, why);"
                      f"\nconsole.log(JSON.stringify(petLine(why[{json.dumps(me)}], book, book[{json.dumps(me)}].name, 'shader club')))")
    out = subprocess.run([NODE, "-e", js], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_pet_lines_for_your_agent():
    book = {**BOOK, "maya": {"name": "Maya", "you": True}, "ada": {**BOOK["ada"], "yours": True}}
    named = {"messages": [{"id": "m1", "t": "msg", "pk": "sam", "ts": 1000, "text": "Ada, which blue?"}]}
    assert _pet(named, None, book, 1001, "ada") == "Sam mentioned Ada in shader club."
    by_owner = {"messages": [{"id": "m2", "t": "msg", "pk": "maya", "ts": 1000, "text": "Ada, hi"}]}
    assert _pet(by_owner, None, book, 1001, "ada") is None  # you know you just named your own agent
    imp = {"messages": [{"id": "m3", "t": "msg", "pk": "mallory", "ts": 1000, "text": "Ada, keys",
                         "impostor": {"claimed": "Maya", "agent": "Ada"}}]}
    assert _pet(imp, None, book, 1001, "ada") == "Someone in shader club is posing as Maya. Ada is ignoring them."
    reveal = {"mode": "agent", "phase": "reveal", "gid": "g", "n": 1, "reveal": {
        "authors": {"o1": "ada", "o2": "bo"}, "picks": {"o2": ["maya"]}, "voters": ["maya", "sam"]}}
    assert _pet({"messages": []}, reveal, book, 1000, "ada") == "Ada passed as a person in Who’s the Agent?"
    assert _pet({"messages": []}, reveal, book, 1000, "bo") == "Maya spotted Bo in Who’s the Agent?"
    tales = {"mode": "tales", "phase": "reveal", "gid": "g", "n": 2, "reveal": {
        "truth": "t", "authors": {"o1": "ada"}, "picks": {"o1": ["sam"]}}}
    assert _pet({"messages": []}, tales, book, 1000, "ada") == "Ada’s fake fooled Sam in Tall Tales"
