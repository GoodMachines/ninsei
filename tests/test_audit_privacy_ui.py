"""Audit fixes, privacy and UI group: what a card, a build or a link can make public or misleading."""
import importlib
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from ninsei_engine import toy
from ninsei_engine.store import Store
from test_audit_engine_trust import OID, RecordingLLM, _ready_offer
from test_audit_ui import STYLE, needs_node, run as run_js
from test_chat_a2 import rich_js
from test_hostile import ROOM, bare, settle  # noqa: F401  (fixture re-export)
from start_helpers import started

ROOT = Path(__file__).resolve().parents[1]


# --- the model id on the wire is the short form the owner's card shows --------------------------------

async def test_a_model_path_is_published_as_its_last_segment(bare, monkeypatch):
    e, _ = bare()
    e.save_settings({"onboarded": True, "agent_name": "Ada", "card_details": True})
    e.store.set("model_last", "/Users/jane/models/qwen3-8b.gguf")
    sent = []

    async def capture(room, as_agent, content, **kw):
        sent.append(content)
        return {}
    monkeypatch.setattr(e, "_publish_room", capture)
    monkeypatch.setattr(e.store, "rooms", lambda: {ROOM: {}})
    await e._presence_once()
    live = [c for c in sent if c.get("t") == "presence"]
    assert live and live[-1]["model"] == "qwen3-8b.gguf"
    assert "justinperea" not in json.dumps(sent)
    e.store.set("model_last", "nous/hermes-5")
    await e._presence_once()
    assert [c for c in sent if c.get("t") == "presence"][-1]["model"] == "hermes-5"


# --- Tall Tales topics are the interests as published ------------------------------------------------

async def test_questions_use_the_published_interests_not_later_edits(bare):
    llm = RecordingLLM("Ada")
    e, _ = bare(llm=llm)
    e.save_settings({"display_name": "Ada", "interests": ["music"]})
    e.store.save_room(ROOM, {"id": ROOM, "name": "test room", "interests": ["synths"]})

    class Pool:
        async def publish(self, ev):
            return {"r": (True, "")}
    e.pool = Pool()
    await e.publish_card()
    e.save_settings({"interests": ["music", "bankruptcy"]})   # edited, not republished
    await started(e, ROOM, 1)
    assert "music" in llm.prompts[-1] and "bankruptcy" not in llm.prompts[-1]
    await e._end_hosted(ROOM)


# --- the toy share scan flags what the build prompt itself hands the model ---------------------------

@pytest.mark.parametrize("html", [
    "<!-- saved to /Users/jane/.hermes/plugin-data/ninsei/builds/ab/index.html -->",
    "<!-- /home/justin/x -->", "<p>mail me: justin@example.com</p>",
    "<img src='https://x.example/a?token=abcdef123456'>",
])
def test_scan_secrets_flags_home_paths_emails_and_secret_urls(html):
    assert toy.scan_secrets(html)


def test_scan_secrets_leaves_an_ordinary_toy_alone():
    assert toy.scan_secrets("<html><canvas></canvas><script>let a = x / 2; // see ~ notes\nconst v = '1.2'</script></html>") == []


async def test_share_asks_before_publishing_a_home_path(bare):
    e, _ = bare()
    html = b"<html><!-- saved to /Users/jane/.hermes/x --></html>"
    _ready_offer(e, html)
    rep = e.build_report(OID)
    assert rep["secrets"]
    with pytest.raises(ValueError):
        await e.share_build(OID, "T", False, rep["sha256"])
    out = await e.share_build(OID, "T", True, rep["sha256"])
    assert out["id"]
    await settle(e)


# --- a text-direction mark can't make a link show another address -----------------------------------

@needs_node
def test_an_address_with_a_direction_mark_is_not_a_link():
    r = run_js(rich_js() + """
const links = t => richParts(t, []).flatMap(b => b.tokens || []).filter(x => x.t === 'link').map(x => x.text)
out({ inside: links('see https://a.evil/moc.knab\\u202e//:sptth'), isolate: links('x https://a.com/\\u2066y'),
      plain: links('see \\u202e https://a.com/ok') })
""")
    assert r["inside"] == [] and r["isolate"] == []
    assert r["plain"] == ["https://a.com/ok"]   # the mark before it is isolated away by the style, below


def test_links_are_drawn_isolated_from_the_text_around_them():
    rule = [ln for ln in STYLE.splitlines() if ln.startswith(".h-link{")]
    assert rule and "unicode-bidi:isolate" in rule[0] and "direction:ltr" in rule[0]


# --- the build hooks follow the private key, not the public offer id ---------------------------------

KEY = "c" * 32


@pytest.fixture
def hooks(tmp_path, monkeypatch):
    name = "ninsei_plugin_hooks_p"
    spec = importlib.util.spec_from_file_location(name, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    pkg = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, pkg)
    spec.loader.exec_module(pkg)
    mod = importlib.import_module(name + ".ninsei_hooks")
    store = Store(tmp_path / "ninsei.db")
    store.set("offers", {OID: {"status": "building", "room": "r", "title": "T", "build_key": KEY}})
    monkeypatch.setattr(mod, "_loader", SimpleNamespace(
        load_engine=lambda: SimpleNamespace(db_path_if_present=lambda: tmp_path / "ninsei.db")))
    monkeypatch.setattr(mod, "_conn", None)
    monkeypatch.setattr(mod, "_sessions", {})
    yield mod, store
    for m in [m for m in sys.modules if m.startswith(name)]:
        monkeypatch.delitem(sys.modules, m, raising=False)


def test_a_message_that_only_knows_the_public_offer_id_attaches_nothing(hooks):
    mod, store = hooks
    mod.pre_llm_call(session_id="other", user_message='::ninsei-offer{id="%s"}' % OID)
    mod.pre_tool_call(session_id="other")
    mod.pre_llm_call(session_id="other2", user_message="ninsei build key (private): " + "d" * 32)
    assert store.build_progress() == {}
    mod.pre_llm_call(session_id="mine", user_message="Build...\nninsei build key (private): " + KEY)
    mod.pre_tool_call(session_id="mine")
    assert store.build_progress()[OID]["steps"] == 1


async def test_accepting_an_offer_mints_a_key_that_only_the_build_prompt_carries(bare):
    e, _ = bare()
    e.store.save_room(ROOM, {"id": ROOM, "name": "r"})
    e.store.set("offers", {OID: {"room": ROOM, "topic": "t", "title": "T", "task": "A toy.", "status": "open",
                                 "at": time.time()}})
    out = await e.answer_offer(OID, True)
    key = e.store.get("offers")[OID]["build_key"]
    assert len(key) == 32 and f"ninsei build key (private): {key}" in out["prompt"]
    await settle(e)
