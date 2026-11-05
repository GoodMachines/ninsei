"""Layer B: the owner's build shows in the room as the agent building, with a step count and nothing else."""
import asyncio
import importlib
import importlib.util
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from ninsei_engine.engine import _build_claim
from ninsei_engine.store import Store

from test_engine import read, run, setup_room, wait_for, world  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[1]
OID = "a" * 64
OTHER = "b" * 64


@pytest.fixture
def hooks(tmp_path, monkeypatch):
    name = "ninsei_plugin_hooks_t"
    spec = importlib.util.spec_from_file_location(name, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    pkg = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, pkg)
    spec.loader.exec_module(pkg)
    mod = importlib.import_module(name + ".ninsei_hooks")
    store = Store(tmp_path / "ninsei.db")
    store.set("offers", {OID: {"status": "building", "room": "r", "title": "Pixel Sorter"},
                         OTHER: {"status": "ready", "room": "r", "title": "Old"}})
    monkeypatch.setattr(mod, "_loader", SimpleNamespace(
        load_engine=lambda: SimpleNamespace(db_path_if_present=lambda: tmp_path / "ninsei.db")))
    monkeypatch.setattr(mod, "_conn", None)
    monkeypatch.setattr(mod, "_sessions", {})
    yield mod, store
    for m in [m for m in sys.modules if m.startswith(name)]:
        monkeypatch.delitem(sys.modules, m, raising=False)


def test_hooks_track_only_an_accepted_offer_and_keep_only_a_count(hooks, tmp_path):
    mod, store = hooks
    line = '::ninsei-offer{id="%s"}' % OID
    assert mod.pre_llm_call(session_id="s0", user_message="unrelated chat") is None
    assert store.build_progress() == {}
    assert mod.pre_llm_call(session_id="s1", user_message="Build a toy...\n" + line) is None
    assert store.build_progress()[OID]["state"] == "working"
    for _ in range(2):  # a pre_tool_call hook must never return a directive: it could block the tool
        assert mod.pre_tool_call(session_id="s1", tool_name="write_file", args={"path": "/Users/x/secret.txt"}) is None
    assert store.build_progress()[OID]["steps"] == 2
    mod.on_human_input_request(session_id="s1", kind="approval")
    assert store.build_progress()[OID]["state"] == "waiting"
    mod.on_human_input_resolved(session_id="s1", kind="approval", outcome="approved")
    mod.post_llm_call(session_id="s1")
    assert store.build_progress()[OID] == {**store.build_progress()[OID], "state": "paused", "steps": 2}
    # nothing about the tools is kept anywhere in the file
    db = sqlite3.connect(str(tmp_path / "ninsei.db"))
    rows = db.execute("SELECT * FROM build_progress").fetchall()
    assert all("write_file" not in str(r) and "secret" not in str(r) for r in rows)
    # an offer that isn't being built (or a line pasted in another chat) lights up nothing
    mod.pre_llm_call(session_id="s2", user_message='::ninsei-offer{id="%s"}' % OTHER)
    mod.pre_tool_call(session_id="s0")
    assert set(store.build_progress()) == {OID}
    # once the offer is done, the session stops counting
    offers = store.get("offers")
    offers[OID]["status"] = "ready"
    store.set("offers", offers)
    mod.pre_tool_call(session_id="s1")
    assert store.build_progress()[OID]["steps"] == 2 and "s1" not in mod._sessions


def test_hooks_never_raise_without_a_store(hooks, monkeypatch):
    mod, _ = hooks
    monkeypatch.setattr(mod, "_loader", SimpleNamespace(load_engine=lambda: SimpleNamespace(db_path_if_present=lambda: None)))
    monkeypatch.setattr(mod, "_conn", None)
    assert mod.pre_llm_call(session_id="s", user_message='::ninsei-offer{id="%s"}' % OID) is None
    assert mod.pre_tool_call(session_id=None) is None


def test_build_claim_takes_only_an_id_a_count_and_a_flag():
    assert _build_claim({"offer": OID, "step": 4, "wait": True, "tool": "terminal"}) == {"offer": OID, "step": 4, "wait": True}
    assert _build_claim({"offer": OID, "step": 10**9, "wait": "yes"}) == {"offer": OID, "step": 999, "wait": False}
    assert _build_claim({"offer": OID, "step": True}) == {"offer": OID, "step": 0, "wait": False}
    assert _build_claim({"offer": "../x", "step": 1}) is None
    assert _build_claim("building") is None


def _agent(engine, room, owner_pk):
    for p in read(engine, engine.members, room):
        if p["pk"] == owner_pk:
            return p["agents"][0] if p["agents"] else None
    return None


async def test_the_room_sees_the_agent_building(world):  # noqa: F811
    _, engines, _ = world
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    for who, text in ((maya, "pixel sorting is so good"), (sam, "pixel sorting with shaders?"),
                      (maya, "I keep thinking about pixel sorting")):
        await run(who, who.post, room, text)
        await asyncio.sleep(0.1)
    assert await wait_for(lambda: any(m["t"] == "offer" for m in read(sam, sam.messages, room)), 10)
    offer = [m for m in read(maya, maya.messages, room) if m["t"] == "offer"][0]
    owner = maya if offer["owner"] == maya._identity()["person_pk"] else sam
    other = sam if owner is maya else maya
    owner_pk = owner._identity()["person_pk"]
    await run(owner, owner.answer_offer, offer["id"], True, "Make it tiny.")

    db = sqlite3.connect(str(owner.store.path))
    db.execute("INSERT INTO build_progress VALUES (?, 's', 3, 'working', ?)", (offer["id"], time.time()))
    db.commit()
    seen = lambda: (_agent(other, room, owner_pk) or {}).get("build")
    assert await wait_for(lambda: seen() == {"title": offer["title"], "step": 3, "wait": False}, 8)
    assert _agent(other, room, owner_pk)["state"] == "activity: working"
    assert read(owner, owner.members, room) and _agent(owner, room, owner_pk)["build"]["step"] == 3

    db.execute("UPDATE build_progress SET state='waiting', updated_at=?", (time.time(),))
    db.commit()
    assert await wait_for(lambda: (seen() or {}).get("wait") is True, 8)
    assert _agent(other, room, owner_pk)["state"] == "system: waiting"

    db.execute("UPDATE build_progress SET state='working', updated_at=?", (time.time(),))
    db.commit()
    assert await wait_for(lambda: (seen() or {}).get("wait") is False, 8)
    owner.build_path(offer["id"]).write_text("<html><body>toy</body></html>")
    assert await wait_for(lambda: seen() is None and _agent(other, room, owner_pk)["state"] == "activity: idle", 8)
    assert owner.store.build_progress() == {}


async def test_a_build_claim_for_someone_elses_offer_is_not_shown(world):  # noqa: F811
    _, engines, _ = world
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    sam_agent = sam._identity()["agent_pk"]
    assert await wait_for(lambda: read(maya, lambda: sam_agent in maya.presence.get(room, {})), 8)

    async def forge():
        p = maya.presence[room][sam_agent]
        p["build"] = {"offer": OID, "step": 5, "wait": False}  # no offer with this id from Sam's agent
    await asyncio.wrap_future(maya.call(forge))
    assert (_agent(maya, room, sam._identity()["person_pk"]) or {}).get("build") is None


def test_every_registered_hook_is_declared_and_disclosed(hooks):
    mod, _ = hooks
    import re
    declared = lambda path: set(re.search(r"provides_hooks: \[([^\]]*)\]", path.read_text()).group(1).replace(" ", "").split(","))
    readme = (ROOT / "README.md").read_text()
    pr = (ROOT / "submission" / "catalog-pr.md").read_text()
    names = set(mod.HOOKS)
    assert declared(ROOT / "plugin.yaml") == names
    assert declared(ROOT / "submission" / "ninsei.yaml") == names
    for name in names:
        assert f"`{name}`" in readme and f"`{name}`" in pr, name
