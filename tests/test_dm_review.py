"""Regression tests for the review of private messages and friends (review-dm, 2026-11-07): a removed friend coming
back, relays pairing sender and receiver by timing, history lost behind junk wraps, throwaway keys evicting real
requests, lookalike requesters, same-second ties, words before a yes, friends past 100, deleted conversations
coming back, and a relay that asks for a login forever."""
import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from ninsei_engine import dm, engine as eng, nostr, store as store_mod
from ninsei_engine.relays import RelayPool
from test_dm import RecPool, befriend, friend_wrap, settle, speak, wrap_to
from test_hostile import FakePool, Key, bare  # noqa: F401  (fixture re-export)


def my_copy(e, peer, kind, at):
    """My own copy of a friend event, as my other install wraps it to me."""
    ident = e._identity()
    return dm.wrap_for(ident["person_sk"], ident["person_pk"], dm.make_rumor(ident["person_pk"], peer, "", at, friend=kind))


# ---- 1. a removed friend comes back ---------------------------------------------------------------------------------

async def test_my_removal_arriving_before_any_row_still_wins_over_my_older_accept(bare):
    """A second install reads history in no order: my removal first, then the request and my older accept."""
    e, _ = bare()
    x = Key("ex")
    now = int(time.time())
    assert await e._dm_process(my_copy(e, x.ppk, dm.FRIEND_REMOVE, now - 10)) == dm.DROPPED
    row = e.store.friend_get(x.ppk)
    assert row and row["mine_at"] == now - 10 and not row["mine"]                 # kept as my dated "no"
    await e._dm_process(friend_wrap(e, x, dm.FRIEND_REQUEST, now=now - 100))
    assert await e._dm_process(my_copy(e, x.ppk, dm.FRIEND_ACCEPT, now - 90)) == dm.DROPPED
    assert e.store.friend_rel(x.ppk) != "friend"
    assert await e._dm_process(wrap_to(e, x, "I'm back")) == dm.NOT_FRIEND


async def test_a_flood_of_throwaway_tombstones_cannot_push_out_my_no(bare, monkeypatch):
    """201 throwaway request+remove pairs, and a wrap record pushed past its cap: my old accept replayed by anyone
    still loses to my newer removal."""
    monkeypatch.setattr(store_mod, "DM_WRAP_MEMORY", 5)
    e, _ = bare()
    x = Key("ex2")
    now = int(time.time())
    my_accept = my_copy(e, x.ppk, dm.FRIEND_ACCEPT, now - 5000)
    await e._dm_process(friend_wrap(e, x, dm.FRIEND_REQUEST, now=now - 5001))
    await e._dm_process(my_accept)
    assert e.store.friend_rel(x.ppk) == "friend"
    await e._dm_process(my_copy(e, x.ppk, dm.FRIEND_REMOVE, now - 4000))
    for i in range(201):
        k = Key(f"syb{i}")
        await e._dm_process(friend_wrap(e, k, dm.FRIEND_REQUEST, now=now - 3))
        await e._dm_process(friend_wrap(e, k, dm.FRIEND_REMOVE, now=now - 2))
    assert e.store.friend_get(x.ppk)["mine_at"] == now - 4000                     # my word is never evicted
    assert not e.store.dm_wrap_seen(my_accept["id"])                              # (the wrap record is gone)
    e._dm_seen.clear()
    assert await e._dm_process(my_accept) == dm.DROPPED                           # older than my "no"
    await e._dm_process(friend_wrap(e, x, dm.FRIEND_REQUEST, now=now))
    assert e.store.friend_rel(x.ppk) == "request"                                 # they may ask; I haven't said yes


async def test_hiding_turns_my_yes_into_a_dated_no(bare):
    e, _ = bare()
    x = Key("hid")
    now = int(time.time())
    e.pool = RecPool()
    my_accept = my_copy(e, x.ppk, dm.FRIEND_ACCEPT, now - 50)
    await e._dm_process(friend_wrap(e, x, dm.FRIEND_REQUEST, now=now - 60))
    await e._dm_process(my_accept)
    await e.hide_person(x.ppk, "X")
    await e.unhide_person(x.ppk)
    e.store.dm_wrap_unmark(my_accept["id"])
    e._dm_seen.clear()
    assert await e._dm_process(my_accept) == dm.DROPPED and e.store.friend_rel(x.ppk) != "friend"


# ---- 2. relays pairing sender and receiver -------------------------------------------------------------------------

async def test_my_own_copy_goes_out_later_than_theirs_but_is_in_the_outbox_at_once(bare, monkeypatch):
    e, _ = bare(ts=1.0)
    monkeypatch.setattr(eng, "DM_SELF_COPY_DELAY", (5, 90))
    k = Key("pal")
    befriend(e, k)
    me = e._identity()["person_pk"]
    await e.dm_send(k.ppk, "hello")
    await asyncio.sleep(0.2)
    sent = [w for w in e.pool.sent if w["kind"] == 1059]
    assert [w["tags"] for w in sent] == [[["p", k.ppk]]]                           # only theirs so far
    assert len(e._dm_later) == 1
    pending = {ev["id"] for ev, _ in e.store.event_outbox_pending()}
    mine = [ev for ev, _ in e.store.event_outbox_pending() if ev["tags"] == [["p", me]]]
    assert len(mine) == 1 and mine[0]["id"] in pending                            # survives a quit before the delay
    for t in list(e._dm_later):
        t.cancel()


def test_the_readme_and_the_about_panel_say_what_a_relay_can_see():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    readme = (root / "README.md").read_text()
    about = (root / "ui" / "57_dm.js").read_text()
    assert "can't tell who sent it" not in readme and "tell who sent it" not in about
    for text in (readme, about):
        assert "timing" in text
    assert "your person key" in readme and "who your friends are is not published anywhere" not in readme
    assert "won't be sent again" in readme


# ---- 3. paging past junk wraps ---------------------------------------------------------------------------------------

class PagingPool(FakePool):
    """One relay holding `events`; `query_relay` answers like a relay: newest first, `since`/`until`, `limit`."""

    def __init__(self, events, url="wss://one.example", cap=None, keep_order=False):
        super().__init__()
        self.keep_order = keep_order
        self.url = url
        self.urls = [url]
        self.events = list(events)
        self.cap = cap
        self.status = {url: SimpleNamespace(retry_at=1.0, state="open")}
        self.pages = []

    def eosed(self, sid, url):
        return True

    def eose_count(self, sid):
        return 1

    async def subscribe(self, *a, **kw):
        pass

    async def unsubscribe(self, sid):
        pass

    async def query_relay(self, url, filters, timeout=8.0, needs_auth=False):
        f = filters[0]
        self.pages.append(dict(f))
        hits = [ev for ev in self.events if f.get("since", 0) <= ev["created_at"] <= f.get("until", 1 << 40)]
        if not self.keep_order:
            hits.sort(key=lambda ev: (-ev["created_at"], ev["id"]))
        return hits[: min(f["limit"], self.cap or f["limit"])], True


def junk(i, at):
    """A wrap to me that won't open: looks right, costs one decryption, recorded as garbage."""
    from ninsei_engine import nostr
    return nostr.build_event(nostr.new_secret(), 1059, "AAAA" + "x" * 40, [["p", JUNK_TO[0]]], created_at=at)


JUNK_TO = [""]


async def run_pass(e, **kw):
    e._dm_queue = asyncio.Queue(maxsize=eng.DM_QUEUE_MAX)
    worker = asyncio.ensure_future(e._dm_worker())
    try:
        await asyncio.wait_for(e._dm_pass(**kw), 60)
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


async def test_a_pass_pages_back_past_400_junk_wraps_and_finds_the_real_one(bare, monkeypatch):
    monkeypatch.setattr(eng, "DM_PACE_S", 0)
    e, _ = bare()
    JUNK_TO[0] = e._identity()["person_pk"]
    k = Key("real-friend")
    befriend(e, k)
    now = int(time.time())
    real = wrap_to(e, k, "behind the junk")                                     # dated up to two days back
    flood = [junk(i, now - i % 50) for i in range(450)]
    e.pool = PagingPool(flood + [real])
    await run_pass(e)
    assert [m["text"] for m in e.store.dm_messages(k.ppk)] == ["behind the junk"]
    assert len(e.pool.pages) >= 2 and "until" in e.pool.pages[1]
    assert e._dm_reached == {e.pool.url: 1.0}                                    # read to the end: may move `since`
    e._dm_touch()
    assert abs(e.store.get("dm_since_relays")[e.pool.url] - time.time()) < 5


async def test_a_relay_whose_pages_run_out_keeps_its_since_and_others_move_theirs(bare, monkeypatch):
    monkeypatch.setattr(eng, "DM_PACE_S", 0)
    monkeypatch.setattr(eng, "DM_PAGES", 2)
    e, _ = bare()
    JUNK_TO[0] = e._identity()["person_pk"]
    now = int(time.time())
    e.store.set("dm_since_relays", {"wss://one.example": now - 100})
    e.pool = PagingPool([junk(i, now - i) for i in range(30)], cap=10)            # a relay that caps replies at 10
    await run_pass(e)
    assert all(p["since"] == now - 100 - eng.DM_SINCE_MARGIN for p in e.pool.pages)   # its own since, less the margin
    assert e._dm_reached == {}                                                   # 2 pages of 10 didn't reach it
    e._dm_touch()
    assert e.store.get("dm_since_relays") == {"wss://one.example": now - 100}


async def test_an_overflow_or_a_reconnect_starts_a_new_pass_and_holds_since(bare, monkeypatch):
    e, _ = bare()
    k = Key("flooded")
    befriend(e, k)
    e.pool = PagingPool([])
    e._dm_queue = asyncio.Queue(maxsize=1)
    lost = wrap_to(e, k, "dropped by the queue")
    await e._on_dm_wrap(wrap_to(e, k, "first"), "live")
    await e._on_dm_wrap(lost, "live")
    assert e._dm_dropped
    e._dm_reached = {e.pool.url: 1.0}
    started = []
    monkeypatch.setattr(e, "_dm_pass", lambda full=False: started.append(full) or asyncio.sleep(0))
    e._dm_touch()
    assert started == [False] and e.store.get("dm_since_relays") is None
    e._dm_dropped = False
    e._dm_queue = asyncio.Queue()
    e.pool.status[e.pool.url].retry_at = 2.0                                     # it reconnected since its pass
    e._dm_repass_at = 0
    e._dm_touch()
    assert started == [False, False] and e._dm_reached == {}
    await settle(e)


async def test_history_in_any_order_lets_in_what_was_written_after_the_yes_only(bare, monkeypatch):
    """A second install restoring: the messages come before the friend events in the pages."""
    monkeypatch.setattr(eng, "DM_PACE_S", 0)
    e, _ = bare()
    k = Key("restored")
    now = int(time.time())
    before = wrap_to(e, k, "words before a yes", now=now - 3000)
    after = wrap_to(e, k, "after we were friends", now=now - 100)
    their_req = friend_wrap(e, k, dm.FRIEND_REQUEST, now=now - 2000)
    my_accept = my_copy(e, k.ppk, dm.FRIEND_ACCEPT, now - 1000)
    e.pool = PagingPool([before, after, their_req, my_accept], keep_order=True)   # messages first in the page
    await run_pass(e)
    assert [m["text"] for m in e.store.dm_messages(k.ppk)] == ["after we were friends"]


# ---- 4. throwaway requests ---------------------------------------------------------------------------------------

async def test_a_request_pushed_out_by_throwaways_can_come_back_and_known_people_go_last(bare):
    e, _ = bare()
    real, known = Key("real"), Key("known")
    await speak(e, known, name="Olu")                                             # seen in a room I'm in
    now = int(time.time())
    w_real = friend_wrap(e, real, dm.FRIEND_REQUEST, now=now - 60)
    w_known = friend_wrap(e, known, dm.FRIEND_REQUEST, now=now - 120)              # the oldest of all
    assert await e._dm_process(w_real) == dm.OK and await e._dm_process(w_known) == dm.OK
    for i in range(50):
        await e._dm_process(friend_wrap(e, Key(f"s{i}"), dm.FRIEND_REQUEST, now=now))
    pending = {p["pk"] for p in e.dm_summary()["pending"]}
    assert real.ppk not in pending and known.ppk in pending                       # strangers give way first
    assert not e.store.dm_wrap_seen(w_real["id"]) and w_real["id"] not in e._dm_seen   # it can come back
    stranger = next(p["pk"] for p in e.dm_summary()["pending"] if p["pk"] != known.ppk)
    await e.friend_ignore(stranger)                                               # one slot frees up
    assert await e._dm_process(w_real) == dm.OK
    assert real.ppk in {p["pk"] for p in e.dm_summary()["pending"]}


# ---- 5. lookalike requester ------------------------------------------------------------------------------------------

async def test_a_requester_using_a_friends_name_or_mine_is_flagged_wherever_they_spoke(bare):
    e, _ = bare()
    maya_r, fake, me_too = Key("maya-real"), Key("maya-fake"), Key("me-too")
    await speak(e, maya_r, name="Rebeca")
    befriend(e, maya_r)
    assert e.dm_summary()["threads"][0]["name"] == "Rebeca"
    e.events[next(iter(e.events))].clear()                                        # Rebeca hasn't spoken lately
    e._holder_seen.clear()
    from ninsei_engine.topics import TopicTracker
    other = "f" * 16
    e.events[other] = {}
    e.topics[other] = TopicTracker()
    e.store.save_room(other, {"id": other, "name": "elsewhere"})
    for k, name in ((fake, "Rebéca"), (me_too, "Maya")):
        ev = nostr.build_event(k.psk, 4242, json.dumps({"t": "msg", "text": "hi", "name": name}), [["h", other]])
        await e._on_event(ev, "relay")
        await e._dm_process(friend_wrap(e, k, dm.FRIEND_REQUEST))
    s = e.dm_summary()
    pend = {p["pk"]: p for p in s["pending"]}
    assert pend[fake.ppk]["impostor"] and pend[fake.ppk]["name"] != "Rebéca"
    assert pend[me_too.ppk]["impostor"] and pend[me_too.ppk]["name"] != "Maya"
    assert [t["name"] for t in s["threads"]] == ["Rebeca"]                         # the real friend keeps the name


# ---- 6. same-second tie --------------------------------------------------------------------------------------------

async def test_cancel_then_add_friend_in_the_same_second_keeps_its_order_everywhere(bare):
    from test_hostile import settle as settle_tasks
    a, _ = bare("A")
    k = Key("peer")
    await a.friend_request(k.ppk)
    await a.friend_remove(k.ppk)
    await a.friend_request(k.ppk)
    assert a.store.friend_rel(k.ppk) == "sent"
    await settle(a)
    to_peer = [w for w in a.pool.sent if w["kind"] == 1059 and w["tags"] == [["p", k.ppk]]]
    ev = [dm.unwrap(k.psk, k.ppk, w)[1] for w in to_peer]
    ats = [o["created_at"] for o in ev]
    assert ats == sorted(ats) and len(set(ats)) == 3                              # strictly increasing
    st = a.store
    p = "f" * 64
    for o in sorted(ev, key=lambda o: o["type"] == dm.FRIEND_REMOVE):             # the worst arrival order
        st.friend_event(p, side="theirs", action="remove" if o["type"] == dm.FRIEND_REMOVE else "yes", at=o["created_at"])
    assert st.friend_rel(p) == "request"                                          # the peer sees the last word: yes
    del settle_tasks


# ---- 8. friends past 100 -------------------------------------------------------------------------------------------

async def test_all_two_hundred_friends_are_in_the_sidebar(bare):
    e, _ = bare()
    keys = [Key(f"many{i}") for i in range(store_mod.FRIENDS_MAX)]
    for k in keys:
        befriend(e, k)
    old = Key("old-thread")
    e.store.dm_add(id="a" * 64, peer=old.ppk, sender=old.ppk, text="old", created_at=int(time.time()), arrived_at=time.time())
    threads = e.dm_summary()["threads"]
    assert {k.ppk for k in keys} <= {t["pk"] for t in threads}


# ---- 9. deleted conversations --------------------------------------------------------------------------------------

async def test_a_deleted_conversation_stays_deleted_when_relays_replay_it(bare):
    e, _ = bare()
    k = Key("deleted")
    befriend(e, k)
    w = wrap_to(e, k, "delete me", now=int(time.time()) - 30)
    assert await e._dm_process(w) == dm.OK
    await e.dm_forget(k.ppk)
    e.store.dm_wrap_unmark(w["id"])                                               # the handled-wrap record is gone
    e._dm_seen.clear()
    await e._dm_process(w)
    assert e.store.dm_messages(k.ppk) == []
    await e.dm_send(k.ppk, "a new start")                                         # what comes after is kept
    assert [m["text"] for m in e.store.dm_messages(k.ppk)] == ["a new start"]
    await settle(e)


# ---- 10. AUTH loop ---------------------------------------------------------------------------------------------------

async def test_a_relay_gets_at_most_three_logins_in_ten_minutes():
    url = "ws://127.0.0.1:1"
    pool = RelayPool([url])
    pool.set_auth(lambda u, c: {"kind": 22242, "id": "%064x" % abs(hash(c)), "content": c})
    sent = []

    class Ws:
        async def send(self, raw):
            msg = json.loads(raw)
            sent.append(msg)
            if msg[0] == "AUTH":
                asyncio.get_running_loop().call_soon(
                    lambda: asyncio.ensure_future(pool._on_message(url, json.dumps(["OK", msg[1]["id"], True, ""]))))

    ws = Ws()
    pool._ws[url] = ws
    await pool.subscribe("dm", [{"kinds": [1059]}], lambda *a: None, resume=False, needs_auth=True)
    for i in range(6):
        await pool._on_message(url, json.dumps(["AUTH", f"challenge-{i}"]))
        await pool._on_message(url, json.dumps(["CLOSED", "dm", "auth-required: log in"]))
        for _ in range(20):
            await asyncio.sleep(0.01)
    assert len([m for m in sent if m[0] == "AUTH"]) == 3
    assert "paused" in pool.status[url].last_error
    assert pool._auth_paused(url) and url in pool._auth_resume                     # asked again once the window passes
    pool._stopped = True
    for t in list(pool._flush_tasks):
        t.cancel()
    await asyncio.gather(*pool._flush_tasks, return_exceptions=True)
    events, done = await pool.query_relay(url, [{"kinds": [1059]}], needs_auth=True)
    assert (events, done) == ([], False)                                         # paging waits out the pause too
