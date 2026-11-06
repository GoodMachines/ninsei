"""Agent cards and the richer face editor: faces are built only from known options on both sides of the
wire, the vibe and model are published only when the owner opts in, and a person's card reads only a
properly signed interest card."""
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from ninsei_engine import engine as eng_mod
from ninsei_engine import nostr
from ninsei_engine.brain import Brain
from ninsei_engine.engine import Engine, clean_face

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


class Res:
    def __init__(self, model="anthropic/claude-sonnet-5-5"):
        self.text, self.model, self.usage = "ok", model, None


class LLM:
    def __init__(self, model="anthropic/claude-sonnet-5-5"):
        self.model = model

    def complete(self, messages, **_):
        return Res(self.model)


def _js_list(src: str, name: str) -> list:
    m = re.search(r"const " + name + r" = (\[[^\]]*\])", src)
    return json.loads(m.group(1).replace("'", '"'))


def test_face_options_match_between_engine_and_ui():
    core = (ROOT / "ui" / "00_core.js").read_text()
    assert _js_list(core, "SHAPES") == eng_mod.FACE_SHAPES
    assert _js_list(core, "FACE_EYES") == eng_mod.FACE_EYES
    assert _js_list(core, "FACE_MOUTHS") == eng_mod.FACE_MOUTHS
    assert _js_list(core, "FACE_ACCS") == eng_mod.FACE_ACCS
    assert _js_list(core, "FACE_PATTERNS") == eng_mod.FACE_PATTERNS


@pytest.mark.parametrize("bad", [None, "x", 5, [], {"hue": "nan"}, {"hue": 10 ** 400}, {"shape": "<svg>", "eyes": {"a": 1},
                                 "acc": "javascript:", "pattern": None, "hue2": "x", "mouth": 3}])
def test_clean_face_keeps_only_known_options(bad):
    f = clean_face(bad)
    assert set(f) == {"hue", "shape", "eyes", "mouth", "acc", "pattern", "hue2"}
    assert 0 <= f["hue"] < 360 and 0 <= f["hue2"] < 360
    assert f["shape"] in eng_mod.FACE_SHAPES and f["eyes"] in eng_mod.FACE_EYES and f["mouth"] in eng_mod.FACE_MOUTHS
    assert f["acc"] in eng_mod.FACE_ACCS and f["pattern"] in eng_mod.FACE_PATTERNS


def test_a_chosen_face_round_trips_through_settings(tmp_path):
    e = Engine(tmp_path / "e", lambda: None, relays=[], lock=False)
    face = {"hue": 400, "shape": "bean", "eyes": "visor", "mouth": "cat", "acc": "headphones", "pattern": "freckles", "hue2": -20}
    assert e.save_settings({"face": face})["face"] == {"hue": 40, "shape": "bean", "eyes": "visor", "mouth": "cat",
                                                      "acc": "headphones", "pattern": "freckles", "hue2": 340}


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_the_ui_reads_a_hostile_face_as_defaults():
    core = (ROOT / "ui" / "00_core.js").read_text()
    src = core[core.index("const SHAPES"):core.index("const BUDGET_PRESETS")] + core[core.index("function faceFor("):core.index("function fmtTokens(")]
    js = src + """
const out = [faceFor({ hue: 'x', shape: 'evil', eyes: '<img>', mouth: 7, acc: {}, pattern: 'spots', hue2: -30 }, 'abcdef12'),
             faceFor(null, 'abcdef12'), faceFor('string', 'abcdef12')]
console.log(JSON.stringify(out))"""
    hostile, empty, string = json.loads(subprocess.run([NODE, "-e", js], capture_output=True, text=True, check=True).stdout)
    assert hostile["eyes"] == "dot" and hostile["mouth"] == "smile" and hostile["acc"] == "none"
    assert hostile["pattern"] == "spots" and hostile["hue2"] == 330 and hostile["shape"] in eng_mod.FACE_SHAPES
    assert empty == string


async def test_the_brain_remembers_the_model_that_ran(tmp_path):
    e = Engine(tmp_path / "e", lambda: LLM(), relays=[], lock=False)
    e.save_settings({"onboarded": True})
    await e.brain._complete("chat", [{"role": "user", "content": "hi"}], 20, "reply")
    assert e.store.get("model_last") == "anthropic/claude-sonnet-5-5"
    weird = Brain(lambda: LLM(model="x" * 500 + "<b>"), lambda c, n: "t", lambda t, n: None, on_model=e._note_model)
    await weird._complete("chat", [{"role": "user", "content": "hi"}], 20, "reply")
    assert e.store.get("model_last") == "x" * 60


async def test_vibe_and_model_are_published_only_when_the_owner_opts_in(tmp_path, monkeypatch):
    e = Engine(tmp_path / "e", lambda: LLM(), relays=[], lock=False)
    e.save_settings({"onboarded": True, "agent_name": "Ada", "vibe": "dry wit, loves colour"})
    e.store.set("model_last", "nous/hermes-5")
    sent = []

    async def capture(room, as_agent, content, **kw):
        sent.append(content)
        return {}
    e.pool = object()
    monkeypatch.setattr(e, "_publish_room", capture)
    monkeypatch.setattr(e.store, "rooms", lambda: {"ab" * 8: {}})
    await e._presence_once()
    assert sent and sent[-1]["t"] == "presence" and "vibe" not in sent[-1] and "model" not in sent[-1]
    e.save_settings({"card_details": True})
    await e._presence_once()
    assert sent[-1]["vibe"] == "dry wit, loves colour" and sent[-1]["model"] == "nous/hermes-5"


def test_a_peers_shared_model_and_vibe_are_cleaned(tmp_path):
    e = Engine(tmp_path / "e", lambda: None, relays=[], lock=False)
    room = "cd" * 8
    owner_sk, agent_sk = nostr.new_secret(), nostr.new_secret()
    owner_pk, agent_pk = nostr.pubkey(owner_sk), nostr.pubkey(agent_sk)
    content = {"t": "presence", "name": "Bo", "state": "activity: idle", "at": time.time(),
               "vibe": "v" * 500, "model": "evil<script>/m‮" + "x" * 100}
    ev = nostr.build_event(agent_sk, eng_mod.KIND_LIVE, json.dumps(content),
                           [["h", room], ["owner", owner_pk, nostr.owner_binding(owner_sk, agent_pk)]])
    e.events[room] = {}
    import asyncio
    asyncio.run(e._on_event(ev, "live"))
    p = e.presence[room][agent_pk]
    assert len(p["vibe"]) == 200
    assert p["model"] == ("evilscript/m" + "x" * 100)[:60]
    assert not re.search(r"[<>‮]", p["model"])


async def test_profile_reads_the_lobby_copy_and_refuses_bad_keys(tmp_path):
    e = Engine(tmp_path / "e", lambda: None, relays=[], lock=False)
    pk = "ef" * 32
    e.lobby = {"people": [{"pk": pk, "name": "Sam", "line": "synths", "interests": ["synths"], "at": 5}]}
    assert await e.profile(pk) == {"line": "synths", "interests": ["synths"], "at": 5}
    assert await e.profile("../../etc") == {}
    assert await e.profile("AB" * 32) == {}
    e._hidden.add(pk)
    assert await e.profile(pk) == {}


def test_the_profile_route_exists():
    api = (ROOT / "dashboard" / "plugin_api.py").read_text()
    assert '@router.get("/profile")' in api and "card_details: Optional[bool]" in api
