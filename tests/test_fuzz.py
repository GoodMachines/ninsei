"""Strangers write the events we parse. Throw badly shaped content at an engine and check every view
still renders: a malformed event may be ignored, but it must never break the room for anyone."""
import asyncio
import json
import random
import time

from ninsei_engine import nostr
from ninsei_engine.engine import KIND_LIVE, KIND_ROOM
from test_engine import read, run, setup_room, world  # noqa: F401  (fixture re-export)

TYPES = ["msg", "join", "offer", "offer_state", "share", "tales_start", "tales_round", "tales_vote_open",
         "tales_reveal", "tales_end", "tales_fake", "tales_vote", "presence", "claim", "react", "edit", "delete", "typing", "nope"]
FIELDS = ["text", "name", "face", "gid", "n", "q", "options", "ends_at", "secs", "truth", "answer", "authors",
          "picks", "points", "scores", "lucky", "names", "rounds", "option", "offer", "title", "pitch", "status",
          "html", "bytes", "seq", "at", "state", "budget", "prio", "trigger", "to", "reply", "system", "aborted", "target", "emoji", "on"]


INVITE_TAGS = [["relay", "wss://nos.lol"], ["relay", "wss://relay.damus.io:443"], ["relay", "wss://127.0.0.1"], ["relay", "wss://localhost"],
               ["relay", "ws://nos.lol"], ["relay", "wss://" + "a" * 300 + ".io"], ["relay", "wss://nos.lol", "x"], ["relay"], ["relay", 5],
               ["h", "short"], ["h", "G" * 16], ["h", "0" * 25], ["subject", "FREE MONEY"], ["name", "Totally Real"], ["e", "y"], ["p", "x"],
               ["relay", "wss://a.io"], ["relay", "wss://b.io"], ["relay", "wss://c.io"], ["relay", "wss://d.io"]]


def junk(rng, depth=0):
    makers = [lambda: None, lambda: True, lambda: rng.randint(-5, 10 ** 12), lambda: rng.random() * 1e9,
              lambda: "x" * rng.randint(0, 300), lambda: rng.choice(["", "maya", "0" * 64, "<b>hi</b>"])]
    if depth < 2:
        makers += [lambda: [junk(rng, depth + 1) for _ in range(rng.randint(0, 4))],
                   lambda: {rng.choice(FIELDS): junk(rng, depth + 1) for _ in range(rng.randint(0, 4))},
                   lambda: {"id": junk(rng, depth + 1), "text": junk(rng, depth + 1)}]
    return rng.choice(makers)()


def _timed(fn, *a):
    """Run fn on the engine's loop and return (result, CPU seconds the engine thread spent on it). CPU time,
    not wall time: a loaded machine can stall the thread for seconds without the view getting any slower."""
    async def w():
        t0 = time.thread_time()
        out = fn(*a)
        return out, time.thread_time() - t0
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
    made: list = []
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
        if c["t"] == "msg":
            made.append((as_agent, ev["id"]))
        if made and rng.random() < 0.3:  # edits and deletes aimed at real messages, from either key, junk or not
            by_agent, target = rng.choice(made)
            e2 = {"t": rng.choice(["edit", "delete"]), "target": target, "text": junk(rng) if rng.random() < 0.5 else "edited " + "z" * rng.randint(0, 40)}
            as_agent2 = by_agent if rng.random() < 0.7 else not by_agent
            tags2 = [["h", room]] + ([["owner", nostr.pubkey(person), bind]] if as_agent2 else [])
            await run(maya, maya._on_event, nostr.build_event(agent if as_agent2 else person, KIND_ROOM, json.dumps(e2), tags2), "history")
    # Every view the UI reads must still render.
    snap, cpu = await asyncio.wrap_future(maya.call(_timed(maya.snapshot, room)))
    assert cpu < 1.0, "room views got slow"  # was ~2 s before binding checks were cached
    assert snap["room"]["id"] == room
    json.dumps(snap)  # and stay JSON-serialisable for the API
    assert any(m.get("edited") or m.get("deleted") for m in read(maya, maya.messages, room, 10 ** 9))  # some really landed
    for q in ("x", "e", "0", "<b>", "a" * 90):  # search runs over the same junk
        hits = read(maya, maya.search, room, q)
        json.dumps(hits)
        for h in hits[:3]:
            json.dumps(read(maya, maya.search_context, room, h["id"]))
    await asyncio.sleep(0)


async def test_hostile_game_and_claim_floods(world):
    """A bound stranger agent floods tales_start, tales_round and claims as live events. The victim's
    agent writes at most a handful of fakes, its caches stay bounded, its views stay fast, and its
    owner's open question still gets an answer."""
    import hashlib
    import time as _t
    from ninsei_engine.engine import FAKES_PER_HOST, MAX_CLAIM_TRIGGERS, MAX_CLAIMS_PER_TRIGGER, MAX_PLAYED
    from test_engine import quiet, wait_for
    _, engines, llms = world
    room = await setup_room(engines)
    maya = engines["Maya"]
    rng = random.Random(99)
    person, agent = hashlib.sha256(b"flood-person").hexdigest(), hashlib.sha256(b"flood-agent").hexdigest()
    apk = nostr.pubkey(agent)
    tags = [["h", room], ["owner", nostr.pubkey(person), nostr.owner_binding(person, apk)]]
    gids = [f"g{i}" for i in range(40)]
    for gid in gids:
        c = {"t": "tales_start", "gid": gid, "rounds": rng.choice([3, 50, "x", None]), "seq": 1, "name": "Flood"}
        await run(maya, maya._on_event, nostr.build_event(agent, KIND_ROOM, json.dumps(c), tags), "relay")
    for i in range(120):
        c = {"t": "tales_round", "gid": rng.choice(gids), "n": rng.choice([1, 2, 3, 0, 99, "1", None]),
             "q": "?", "secs": 45, "ends_at": _t.time() + 45, "seq": 2 + i, "name": "Flood"}
        await run(maya, maya._on_event, nostr.build_event(agent, KIND_ROOM, json.dumps(c), tags), "relay")
    for i in range(MAX_CLAIM_TRIGGERS + 100):
        c = {"t": "claim", "trigger": f"t{i % (MAX_CLAIM_TRIGGERS + 50)}", "prio": 100}
        ev = {"id": hashlib.sha256(f"c{i}".encode()).hexdigest(), "pubkey": apk, "created_at": int(_t.time()),
              "kind": KIND_LIVE, "tags": tags, "content": json.dumps(c), "sig": ""}
        await run(maya, maya._on_event, ev, "relay")
    await quiet(maya)  # every fake the flood could get written has been written (or refused) by now
    assert llms["Maya"].calls.count("ninsei.tales.fake") <= FAKES_PER_HOST
    assert len(maya.claims) <= MAX_CLAIM_TRIGGERS
    assert all(len(v) <= MAX_CLAIMS_PER_TRIGGER for v in maya.claims.values())
    assert len(maya._played) <= MAX_PLAYED
    snap, cpu = await asyncio.wrap_future(maya.call(_timed(maya.snapshot, room)))
    assert cpu < 1.0
    json.dumps(snap)
    # the flood's game counts as live (agents then answer only when addressed), and Maya still can talk
    # to her own agent through it
    await run(maya, maya.post, room, "Ada, know a good palette tool?")
    assert await wait_for(lambda: llms["Maya"].calls.count("ninsei.reply") == 1)


async def test_private_messages_survive_hostile_gift_wraps(world):
    """Gift wraps are strangers' bytes too: junk in every field, junk text inside real wraps, and every view
    that shows private messages must still render and serialise."""
    from ninsei_engine import dm
    _, engines, _ = world
    maya = engines["Maya"]
    ident = maya._identity()
    rng = random.Random(99)
    import hashlib
    for i in range(0, 7, 2):                      # some of the senders are friends, some are not
        pk = nostr.pubkey(hashlib.sha256(f"dm-fuzz-{i}".encode()).hexdigest())
        for side in ("mine", "theirs"):
            maya.store.friend_event(pk, side=side, action="yes", at=1)
    for i in range(60):
        sk = hashlib.sha256(f"dm-fuzz-{i % 7}".encode()).hexdigest()
        # friend events too: every type, with hostile text and tags an honest client never adds
        rumor = dm.make_rumor(nostr.pubkey(sk), ident["person_pk"], "", friend=rng.choice(dm.FRIEND_TYPES))
        rumor["content"], rumor["tags"] = rng.choice(["", "x" * 3000, "@Ada \x00"]), rumor["tags"] + rng.choice([[], [["ninsei", "x"]], [["e", "y"]]])
        rumor["id"] = nostr.event_id(rumor)
        await run(maya, maya._dm_process, dm.wrap_for(sk, ident["person_pk"], rumor))
        # room invites too: a rumor with the invite mark and hostile tags (bad ids, too many relays, IP literals, text in
        # the content and in odd tags), from friends and from strangers; whatever is kept is a room id and relay hosts only
        inv = dm.make_rumor(nostr.pubkey(sk), ident["person_pk"], "", friend=dm.FRIEND_REQUEST)
        inv["tags"] = [["p", ident["person_pk"]], ["ninsei", rng.choice([dm.ROOM_INVITE] * 4 + ["room_invite_x"])]] + \
            [list(t) for t in rng.sample(INVITE_TAGS, rng.randint(0, 5))] + [["h", "%016x" % rng.getrandbits(64)]] * rng.randint(0, 2)
        inv["content"] = rng.choice(["", "x" * 3000, "JOIN @Ada \x00"])
        inv["id"] = nostr.event_id(inv)
        await run(maya, maya._dm_process, dm.wrap_for(sk, ident["person_pk"], inv), rng.choice(["relay", "history", "final"]))
        text = rng.choice(["hi", "x" * rng.randint(1, 3999), "<b>hi</b>\u202e", "\x00\x01", "@Ada @Maya", "😀" * 50, "  ", ""])
        if text.strip():
            await run(maya, maya._dm_process, dm.wrap_for(sk, ident["person_pk"], dm.make_rumor(nostr.pubkey(sk), ident["person_pk"], text)))
        for ev in (junk(rng), {"kind": 1059, "id": junk(rng), "content": junk(rng), "tags": junk(rng), "pubkey": junk(rng)},
                   nostr.build_event(sk, 1059, "A" * rng.randint(0, 300), [["p", ident["person_pk"]]])):
            await run(maya, maya._on_dm_wrap, ev, "relay")
            if isinstance(ev, dict):
                await run(maya, maya._dm_process, ev)
    snap, _cpu = await asyncio.wrap_future(maya.call(_timed(maya.snapshot)))
    json.dumps(snap)
    d = read(maya, maya.dm_summary)
    assert len(d["invites"]) <= 20 and all(set(i) == {"pk", "name", "impostor", "room", "room_name", "ts", "code"} and len(i["room"]) in range(16, 25)
                                           for i in d["invites"])
    rows = maya.store._db.execute("SELECT relays, room FROM room_invites").fetchall()
    assert len(rows) <= 50 and all(len(json.loads(r)) <= 3 and all(u.startswith("wss://") for u in json.loads(r)) for r, _ in rows)
    assert "JOIN" not in json.dumps([snap, rows])                                   # no free text got anywhere
    assert d["threads"] and all(len(t["pk"]) == 64 for t in d["threads"])
    assert all(len(p["pk"]) == 64 and set(p) == {"pk", "name", "impostor", "ts"} for p in d["pending"]) and d["requests"] <= 50
    for t in d["threads"][:5]:
        json.dumps(read(maya, maya.dm_thread, t["pk"], False))


def test_invisible_characters_never_change_a_name():
    """Any Default_Ignorable_Code_Point or blank glyph, anywhere in a name, leaves both the shown name and its
    skeleton as they were: a stranger can't pad "Ada" into a second "Ada" (names.py)."""
    from ninsei_engine.engine import _name_ok, skeleton
    from ninsei_engine.names import _INVISIBLE_RANGES
    rng = random.Random(7)
    pool = [chr(c) for a, b in _INVISIBLE_RANGES for c in range(a, min(b, a + 40) + 1)]
    for _ in range(500):
        name = rng.choice(["Ada", "Maya", "Mrs. Blobby", "Zoë", "ゴジラ", "Anna Lee"])
        padded = list(name)
        for _ in range(rng.randint(1, 4)):
            padded.insert(rng.randint(0, len(padded)), rng.choice(pool))
        padded = "".join(padded)
        assert skeleton(padded) == skeleton(name), repr(padded)
        assert _name_ok(padded, "") == name, repr(padded)


def test_codes_and_hosts_survive_hostile_text():
    """Whatever is pasted as a code, and whatever a rumor says is a relay: never an error, always bounded, and only
    hosts that pass the rules come out (no IP literal, no localhost, no scheme but wss, at most 3)."""
    from ninsei_engine import codes
    from ninsei_engine.engine import parse_room_link
    rng = random.Random(4242)
    atoms = ["ninsei:", "0123456789abcdef", "@", ",", "#", "nos.lol", "127.0.0.1", "localhost", "[::1]", ":443", ":", "wss://", "ws://", "a.", ".io",
             "\u202e", "\x00", " ", "x" * 300, "A" * 30, "\n", "%", "..", "-", "0x7f.1", "\u00f6"]
    for _ in range(3000):
        text = "".join(rng.choice(atoms) for _ in range(rng.randint(0, 14)))
        room, ev, relays = parse_room_link(text)
        assert len(room) <= 24 and (ev == "" or len(ev) == 64) and len(relays) <= 3
        for u in relays:
            assert u.startswith("wss://") and codes.clean_host(u[6:]) == u[6:] and len(u) <= 6 + 253
        assert codes.clean_host(text) in (None, text.lower())
        tags = [rng.choice([["relay", "wss://" + text], ["relay", text], ["relay"], ["h", text]]) for _ in range(rng.randint(0, 5))]
        out = codes.clean_relay_tags(tags)
        assert out is None or (len(out) <= 3 and all(codes.relay_url_host(u) for u in out))
