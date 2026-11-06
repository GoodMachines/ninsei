"""Card activity: first/posts per member come from events held locally, nothing new is published."""
import asyncio
import json
import time

from ninsei_engine import engine as eng_mod
from ninsei_engine import nostr
from ninsei_engine.engine import Engine

ROOM = "ab" * 8


def _pair():
    o, a = nostr.new_secret(), nostr.new_secret()
    return o, a, nostr.pubkey(o), nostr.pubkey(a)


def _person_ev(sk, content, at):
    return nostr.build_event(sk, eng_mod.KIND_ROOM, json.dumps(content), [["h", ROOM]], created_at=at)


def _agent_ev(osk, ask, content, at):
    return nostr.build_event(ask, eng_mod.KIND_ROOM, json.dumps(content),
                             [["h", ROOM], ["owner", nostr.pubkey(osk), nostr.owner_binding(osk, nostr.pubkey(ask))]],
                             created_at=at)


def _engine(tmp_path):
    e = Engine(tmp_path / "e", lambda: None, relays=[], lock=False)
    e.events[ROOM] = {}
    return e


def _add(e, ev):
    asyncio.run(e._on_event(ev, "relay"))
    assert ev["id"] in e.events[ROOM]


def _by_name(members):
    out = {}
    for m in members:
        out[m["name"]] = m
        for a in m["agents"]:
            out[a["name"]] = a
    return out


def test_first_and_posts_for_a_person_and_their_agent(tmp_path):
    e = _engine(tmp_path)
    osk, ask, opk, apk = _pair()
    t = int(time.time()) - 5000
    _add(e, _person_ev(osk, {"t": "join", "name": "Maya"}, t))
    _add(e, _person_ev(osk, {"t": "msg", "name": "Maya", "text": "hi"}, t + 100))
    _add(e, _person_ev(osk, {"t": "msg", "name": "Maya", "text": "again"}, t + 200))
    _add(e, _agent_ev(osk, ask, {"t": "join", "name": "Ada"}, t - 50))
    _add(e, _agent_ev(osk, ask, {"t": "msg", "name": "Ada", "text": "hello"}, t + 300))
    m = _by_name(e.members(ROOM))
    assert m["Maya"]["first"] == t and m["Maya"]["posts"] == 2
    assert m["Ada"]["first"] == t - 50 and m["Ada"]["posts"] == 1


def test_a_presence_only_agent_has_no_first_and_no_posts(tmp_path):
    e = _engine(tmp_path)
    osk, ask, opk, apk = _pair()
    t = int(time.time()) - 100
    _add(e, _person_ev(osk, {"t": "join", "name": "Sam"}, t))
    e.presence[ROOM] = {apk: {"name": "Pip", "owner": opk, "state": "activity: idle", "at": time.time(), "face": {}}}
    m = _by_name(e.members(ROOM))
    assert m["Pip"]["first"] is None and m["Pip"]["posts"] == 0
    assert m["Sam"]["first"] == t and m["Sam"]["posts"] == 0


def test_a_person_known_only_from_presence_has_null_first(tmp_path):
    e = _engine(tmp_path)
    osk, ask, opk, apk = _pair()
    e.presence[ROOM] = {apk: {"name": "Pip", "owner": opk, "state": "activity: idle", "at": time.time(), "face": {}}}
    person = next(m for m in e.members(ROOM) if m["pk"] == opk)
    assert person["first"] is None and person["posts"] == 0


def test_a_hidden_person_and_their_agent_do_not_appear_or_count(tmp_path):
    e = _engine(tmp_path)
    osk, ask, opk, apk = _pair()
    t = int(time.time()) - 100
    _add(e, _person_ev(osk, {"t": "msg", "name": "Bo", "text": "x"}, t))
    _add(e, _agent_ev(osk, ask, {"t": "msg", "name": "Bot", "text": "y"}, t + 1))
    asyncio.run(e.hide_person(opk, "Bo"))
    names = _by_name(e.members(ROOM))
    assert "Bo" not in names and "Bot" not in names
    # even if a stray event of theirs were still held, it must not be counted
    ev = _person_ev(osk, {"t": "msg", "name": "Bo", "text": "z"}, t + 2)
    e.events[ROOM][ev["id"]] = ev
    assert all(m["pk"] != opk for m in e.members(ROOM))
