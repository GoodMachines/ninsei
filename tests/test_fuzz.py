"""Strangers write the events we parse. Throw badly shaped content at an engine and check every view
still renders: a malformed event may be ignored, but it must never break the room for anyone."""
import asyncio
import json
import random

from hearth_engine import nostr
from hearth_engine.engine import KIND_LIVE, KIND_ROOM
from test_engine import read, run, setup_room, world  # noqa: F401  (fixture re-export)

TYPES = ["msg", "join", "offer", "offer_state", "share", "tales_start", "tales_round", "tales_vote_open",
         "tales_reveal", "tales_end", "tales_fake", "tales_vote", "presence", "claim", "nope"]
FIELDS = ["text", "name", "face", "gid", "n", "q", "options", "ends_at", "secs", "truth", "answer", "authors",
          "picks", "points", "scores", "lucky", "names", "rounds", "option", "offer", "title", "pitch", "status",
          "html", "bytes", "seq", "at", "state", "budget", "prio", "trigger", "to", "reply", "system", "aborted"]


def junk(rng, depth=0):
    makers = [lambda: None, lambda: True, lambda: rng.randint(-5, 10 ** 12), lambda: rng.random() * 1e9,
              lambda: "x" * rng.randint(0, 300), lambda: rng.choice(["", "maya", "0" * 64, "<b>hi</b>"])]
    if depth < 2:
        makers += [lambda: [junk(rng, depth + 1) for _ in range(rng.randint(0, 4))],
                   lambda: {rng.choice(FIELDS): junk(rng, depth + 1) for _ in range(rng.randint(0, 4))},
                   lambda: {"id": junk(rng, depth + 1), "text": junk(rng, depth + 1)}]
    return rng.choice(makers)()


def _wrap(fn, *a):
    async def w():
        return fn(*a)
    return w


async def test_views_survive_malformed_events(world):
    _, engines, _ = world
    room = await setup_room(engines)
    maya = engines["Maya"]
    rng = random.Random(1234)
    import hashlib  # fixed keys: a failure must reproduce
    person, agent = (hashlib.sha256(b"fuzz-person").hexdigest(), hashlib.sha256(b"fuzz-agent").hexdigest())
    apk = nostr.pubkey(agent)
    bind = nostr.owner_binding(person, apk)
    gid = "fuzzgid"
    for i in range(300):
        c = {rng.choice(FIELDS): junk(rng) for _ in range(rng.randint(0, 8))}
        c["t"] = rng.choice(TYPES)
        if rng.random() < 0.5:
            c["gid"] = gid
        content = json.dumps(c) if rng.random() < 0.9 else rng.choice(["[1,2]", "null", "{", "\"s\""])
        as_agent = rng.random() < 0.6
        tags = [["h", room]] + ([["owner", nostr.pubkey(person), bind]] if as_agent else [])
        kind = KIND_LIVE if rng.random() < 0.2 else KIND_ROOM
        ev = nostr.build_event(agent if as_agent else person, kind, content, tags)
        await run(maya, maya._on_event, ev, "history")  # "history": no reactions, no model calls
    # Every view the UI reads must still render.
    import time as _t
    t0 = _t.time()
    snap = await asyncio.wrap_future(maya.call(_wrap(maya.snapshot, room)))
    assert _t.time() - t0 < 1.0, "room views got slow"  # was ~2 s before binding checks were cached
    assert snap["room"]["id"] == room
    json.dumps(snap)  # and stay JSON-serialisable for the API
    await asyncio.sleep(0)
