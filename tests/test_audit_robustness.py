"""Audit fixes, robustness group: non-finite numbers in strangers' game events, concurrent reconnects, a hung
model call, supervised background loops, stopping the engine at exit, an unhashable relay `sig`."""
import asyncio
import json
import sys
import threading
import time
import types
from pathlib import Path

import pytest

from ninsei_engine import brain as brain_mod
from ninsei_engine import engine as eng_mod
from ninsei_engine import nostr
from ninsei_engine.engine import Engine
from ninsei_engine.relays import RelayPool
from test_engine import wait_for
from test_hostile import ROOM, FakePool, Key, bare, settle  # noqa: F401  (fixture re-export)

INF = "1e999"


def raw_agent(k, content_json: str, created_at=None):
    """An agent event whose content is written by hand, so it can hold numbers json.dumps would refuse."""
    tags = [["h", ROOM], ["owner", k.ppk, k.bind]]
    return nostr.build_event(k.ask, eng_mod.KIND_ROOM, content_json, tags, created_at=created_at)


# --- non-finite numbers ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,events", [
    ("rounds", ['{"t":"tales_start","gid":"g","rounds":%s,"seq":1}' % INF]),
    ("seq", ['{"t":"tales_start","gid":"g","rounds":3,"seq":1}',
             '{"t":"tales_round","gid":"g","n":1,"q":"?","secs":30,"ends_at":5,"seq":%s}' % INF]),
    ("scores", ['{"t":"tales_start","gid":"g","rounds":3,"seq":1}',
                '{"t":"tales_round","gid":"g","n":1,"q":"?","secs":30,"ends_at":5,"seq":2}',
                '{"t":"tales_reveal","gid":"g","n":1,"scores":{"a":%s},"points":{"a":-%s},"seq":3}' % (INF, INF)]),
    ("ends_at", ['{"t":"tales_start","gid":"g","rounds":3,"seq":1}',
                 '{"t":"tales_round","gid":"g","n":1,"q":"?","secs":30,"ends_at":%s,"seq":2}' % INF]),
    ("nan", ['{"t":"tales_start","gid":"g","rounds":3,"seq":1}',
             '{"t":"tales_round","gid":"g","n":1,"q":"?","secs":NaN,"ends_at":NaN,"seq":2}']),
    ("huge", ['{"t":"tales_start","gid":"g","rounds":3,"seq":1}',
              '{"t":"tales_round","gid":"g","n":1,"q":"?","secs":30,"ends_at":1e300,"seq":2}',
              '{"t":"tales_reveal","gid":"g","n":1,"scores":{"a":%s},"seq":3}' % ("9" * 400)]),
])
async def test_nonfinite_numbers_never_break_the_view(bare, name, events):
    e, _ = bare(ts=1.0)
    host = Key("host")
    for c in events:
        await e._on_event(raw_agent(host, c), "relay")
    e.game_view(ROOM)
    e._game_running(ROOM)
    json.dumps(e.snapshot(ROOM), allow_nan=False)


def test_content_rejects_nonfinite_at_the_parse():
    e = Engine.__new__(Engine)
    e._cc = {}
    assert e._content({"id": "a", "content": '{"x": 1e999}'}) == {}
    assert e._content({"id": "b", "content": '{"x": NaN}'}) == {}
    assert e._content({"id": "c", "content": '{"x": 1.5}'}) == {"x": 1.5}


# --- reconnect ------------------------------------------------------------------------------------

class SlowPool(FakePool):
    made = []

    def __init__(self):
        super().__init__()
        self.stopped = 0
        SlowPool.made.append(self)

    def start(self):
        pass

    async def stop(self):
        await asyncio.sleep(0.05)
        self.stopped += 1


async def test_concurrent_reconnects_leave_no_live_pool(bare):
    e, _ = bare()
    SlowPool.made = []
    e._new_pool = lambda: SlowPool()
    e.pool = SlowPool()

    async def noresub(wait_art=True):
        pass
    e._resubscribe = noresub
    await asyncio.gather(e.reconnect(), e.reconnect())
    live = [p for p in SlowPool.made if p.stopped == 0]
    assert live == [e.pool]


# --- model deadline -------------------------------------------------------------------------------

async def test_a_hung_model_call_times_out_and_frees_its_slot(monkeypatch):
    monkeypatch.setattr(brain_mod, "MODEL_TIMEOUT_S", 0.2)
    release = threading.Event()

    class Hung:
        def complete(self, messages, max_tokens=None, purpose=None, **_):
            release.wait(5)
            return types.SimpleNamespace(text="late", usage=None, model=None)
    settled = []
    b = brain_mod.Brain(lambda: Hung(), lambda cat, est: "t", lambda t, used: settled.append(used))
    t0 = time.monotonic()
    try:
        with pytest.raises(asyncio.TimeoutError):
            await b._complete("reply", [{"role": "user", "content": "hi"}], 50, "reply")
        assert time.monotonic() - t0 < 2
        assert settled and settled[0] > 0   # a timeout is billed the estimate
    finally:
        release.set()


# --- supervised loops -----------------------------------------------------------------------------

async def test_presence_loop_survives_an_exception(bare, monkeypatch):
    e, _ = bare()
    monkeypatch.setattr(eng_mod, "PRESENCE_EVERY", 0.01)
    calls = []

    async def once(only=None):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
    e._presence_once = once
    task = asyncio.ensure_future(e._presence_loop())
    try:
        await wait_for(lambda: len(calls) >= 3, 10)
        assert not task.done()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_build_watcher_survives_an_exception(bare, monkeypatch):
    e, _ = bare()
    real_sleep = asyncio.sleep

    async def fast(_s):
        await real_sleep(0.01)
    monkeypatch.setattr(eng_mod.asyncio, "sleep", fast)
    calls = []

    def offers():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("sqlite locked")
        return {}
    e._offers = offers

    async def no_expiry():
        pass
    e._announce_expired = no_expiry
    task = asyncio.ensure_future(e._watch_builds())
    try:
        await wait_for(lambda: len(calls) >= 3, 10)
        assert not task.done()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


# --- stop at exit ---------------------------------------------------------------------------------

def test_the_engine_is_stopped_at_process_exit(monkeypatch):
    import atexit
    import importlib
    pkg = importlib.import_module("ninsei_engine")
    registered = []
    monkeypatch.setattr(atexit, "register", lambda fn, *a, **k: registered.append(fn))
    stopped = []

    class FakeEngine:
        def __init__(self, *a, **k):
            pass

        def start(self):
            pass

        def stop(self):
            stopped.append(1)
    monkeypatch.setattr(pkg, "_engine", None)
    monkeypatch.setattr(pkg, "_exit_hooked", False, raising=False)
    monkeypatch.setattr(pkg, "data_dir", lambda: Path("/nonexistent"))
    monkeypatch.setattr(eng_mod, "Engine", FakeEngine)
    pkg.get_engine()
    pkg.get_engine()
    assert len(registered) == 1
    registered[0]()
    registered[0]()
    assert len(stopped) == 1   # stopping twice is harmless: only the first reaches the engine


# --- unhashable sig -------------------------------------------------------------------------------

async def test_unhashable_sig_does_not_raise_in_the_read_loop():
    url = "ws://127.0.0.1:1"
    pool = RelayPool([url])
    got = []

    async def handler(ev, u):
        got.append(ev)
    await pool.subscribe("s", [{}], handler)
    ev = {"id": "ab" * 32, "sig": [], "created_at": int(time.time()), "kind": 1, "tags": [], "content": "",
          "pubkey": "cd" * 32}
    await pool._on_message(url, json.dumps(["EVENT", "s", ev]))
    assert got == []
    await pool.stop()


# --- integers too big for a float -----------------------------------------------------------------

BIG = "9" * 400


async def test_a_400_digit_at_in_a_message_never_breaks_the_snapshot(bare):
    e, _ = bare(ts=1.0)
    k = Key("bigat")
    await e._on_event(raw_agent(k, '{"t":"msg","name":"Big","text":"hi","at":%s}' % BIG), "relay")
    await e._on_event(raw_agent(k, '{"t":"msg","name":"Big","text":"ok","at":1}'), "relay")
    json.dumps(e.snapshot(ROOM), allow_nan=False)
    assert "hi" not in [m["text"] for m in e.messages(ROOM)]   # refused at the parse, so never stored


async def test_a_400_digit_budget_in_a_beat_never_breaks_the_snapshot(bare):
    e, _ = bare(ts=1.0)
    k = Key("bigbudget")
    ev = nostr.build_event(k.ask, eng_mod.KIND_LIVE, '{"t":"presence","name":"Big","budget":%s}' % BIG,
                           [["h", ROOM], ["owner", k.ppk, k.bind]])
    await e._on_event(ev, "relay")
    json.dumps(e.snapshot(ROOM), allow_nan=False)


def test_content_rejects_huge_integers_at_the_parse():
    e = Engine.__new__(Engine)
    e._cc = {}
    assert e._content({"id": "a", "content": '{"x": %s}' % BIG}) == {}
    assert e._content({"id": "b", "content": '{"x": -%s}' % BIG}) == {}
    assert e._content({"id": "c", "content": '{"x": 123456789012345}'}) == {"x": 123456789012345}


def test_order_and_budget_share_survive_a_huge_int():
    assert eng_mod._budget_share(10 ** 400) is None
    e = Engine.__new__(Engine)
    e._cc = {"x": {"at": 10 ** 400}}
    assert e._order({"id": "x", "created_at": 5, "content": "{}"})[1] == 5.0


# --- the host's own timeout -----------------------------------------------------------------------

async def test_the_model_call_passes_its_timeout_to_hosts_that_take_one():
    seen = []

    class Current:   # PluginLlm.complete's shape: keyword-only timeout and task
        def complete(self, messages, *, max_tokens=None, timeout=None, purpose=None, task=None):
            seen.append(timeout)
            return types.SimpleNamespace(text="ok", usage=None, model=None)

    class Older:     # an older host: no timeout argument, which must not break the call
        def complete(self, messages, max_tokens=None, purpose=None):
            seen.append("older")
            return types.SimpleNamespace(text="ok", usage=None, model=None)
    for llm in (Current(), Older()):
        b = brain_mod.Brain(lambda llm=llm: llm, lambda cat, est: "t", lambda t, used: None)
        assert await b._complete("reply", [{"role": "user", "content": "hi"}], 50, "reply") == "ok"
    assert seen == [brain_mod.MODEL_TIMEOUT_S, "older"]
