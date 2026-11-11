"""Regression tests for the relay pool, store and topic tracker reliability fixes (review findings 3, 6, 10)."""
import asyncio
import json
import time

import pytest

from ninsei_engine import nostr, relays
from ninsei_engine.relays import RelayPool, Subscription
from ninsei_engine.store import Store
from ninsei_engine.topics import TopicTracker
from local_relay import LocalRelay


def count_checks(monkeypatch):
    calls = {"n": 0}
    real = nostr.check_event

    def counted(ev):
        calls["n"] += 1
        return real(ev)

    monkeypatch.setattr(nostr, "check_event", counted)
    return calls


async def until(cond, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        await asyncio.sleep(0.05)
    return cond()


def feed(pool, sub_id, ev, url="ws://x"):
    return pool._on_message(url, json.dumps(["EVENT", sub_id, ev]))


def offline_pool(**kw):
    return RelayPool(["ws://x"], **kw)


# --- finding 3: verify once, remember bad ids, flood limit ---------------------------------------
async def test_query_verifies_each_event_once_across_relays_and_calls(monkeypatch):
    sk = nostr.new_secret()
    evs = [nostr.build_event(sk, 1, f"m{i}", [["t", "x"]]) for i in range(5)]
    async with LocalRelay(port=0) as a, LocalRelay(port=0) as b:
        for r in (a, b):
            for e in evs:
                r.events[e["id"]] = e
        pool = RelayPool([a.url, b.url])
        pool.start()
        try:
            assert await pool.wait_open(30, at_least=2)
            calls = count_checks(monkeypatch)
            got = await pool.query([{"kinds": [1]}], timeout=30)
            assert {e["id"] for e in got} == {e["id"] for e in evs}
            assert calls["n"] == 5          # not 10: the second relay's copies skip verification
            await pool.query([{"kinds": [1]}], timeout=30)
            assert calls["n"] == 5          # and a repeat query doesn't re-verify either
        finally:
            await pool.stop()


async def test_cached_id_still_rejects_a_forged_copy(monkeypatch):
    sk = nostr.new_secret()
    ev = nostr.build_event(sk, 1, "real")
    pool = offline_pool()
    got = []
    pool._subs["s"] = Subscription("s", [{}], lambda e, u: got.append(e), dedupe=False)
    await feed(pool, "s", ev)
    forged = dict(ev, content="evil")   # same id, different content
    await feed(pool, "s", forged)
    assert [e["content"] for e in got] == ["real"]


async def test_failed_verification_is_remembered(monkeypatch):
    ev = nostr.build_event(nostr.new_secret(), 1, "x")
    bad = dict(ev, sig="00" * 64)
    pool = offline_pool()
    pool._subs["s"] = Subscription("s", [{}], lambda e, u: None)
    calls = count_checks(monkeypatch)
    for _ in range(5):
        await feed(pool, "s", bad)
    assert calls["n"] == 1 and (bad["id"], bad["sig"]) in pool._bad


async def test_junk_sig_copy_cannot_censor_the_real_event():
    """A hostile relay replays a real event's content with a junk signature first. The genuine
    copy (same id, valid sig) from an honest relay must still be accepted."""
    ev = nostr.build_event(nostr.new_secret(), 1, "real")
    junk = dict(ev, sig="00" * 64)
    pool = offline_pool()
    got = []
    pool._subs["s"] = Subscription("s", [{}], lambda e, u: got.append(e))
    await feed(pool, "s", junk)
    await feed(pool, "s", ev)
    assert [e["sig"] for e in got] == [ev["sig"]]


async def test_bad_id_memory_is_bounded(monkeypatch):
    monkeypatch.setattr(relays, "MAX_BAD", 20)
    monkeypatch.setattr(relays, "BAD_STRIKES", 10 ** 9)
    pool = offline_pool()
    pool._subs["s"] = Subscription("s", [{}], lambda e, u: None)
    sk = nostr.new_secret()
    for i in range(60):
        await feed(pool, "s", dict(nostr.build_event(sk, 1, str(i)), sig="00" * 64))
    assert len(pool._bad) <= 21


async def test_relay_flooding_forgeries_is_muted(monkeypatch):
    monkeypatch.setattr(relays, "BAD_STRIKES", 5)
    sk = nostr.new_secret()
    pool = offline_pool()
    got = []
    pool._subs["s"] = Subscription("s", [{}], lambda e, u: got.append(e))
    for i in range(5):
        await feed(pool, "s", dict(nostr.build_event(sk, 1, f"f{i}"), sig="00" * 64))
    calls = count_checks(monkeypatch)
    await feed(pool, "s", nostr.build_event(sk, 1, "good, but from a muted relay"))
    assert calls["n"] == 0 and got == []
    assert "muted" in pool.status["ws://x"].last_error
    pool._muted_until["ws://x"] = 0   # the mute expires
    await feed(pool, "s", nostr.build_event(sk, 1, "good again"))
    assert len(got) == 1


# --- finding 6: future-dated events -------------------------------------------------------------
async def test_future_dated_event_is_dropped_and_does_not_move_since():
    sk = nostr.new_secret()
    pool = offline_pool()
    got = []
    sub = Subscription("s", [{"kinds": [1], "since": 100}], lambda e, u: got.append(e))
    pool._subs["s"] = sub
    now = int(time.time())
    ok = nostr.build_event(sk, 1, "now", created_at=now)
    await feed(pool, "s", ok)
    await feed(pool, "s", nostr.build_event(sk, 1, "year 2099", created_at=now + 70 * 365 * 86400))
    await feed(pool, "s", nostr.build_event(sk, 1, "an hour ahead", created_at=now + 3600))
    assert [e["content"] for e in got] == ["now"]
    assert sub.newest == now
    await feed(pool, "s", nostr.build_event(sk, 1, "skewed clock", created_at=now + 30))
    assert [e["content"] for e in got] == ["now", "skewed clock"]


async def test_future_dated_events_dropped_from_one_shot_query():
    sk = nostr.new_secret()
    now = int(time.time())
    far = nostr.build_event(sk, 1, "far", created_at=now + 86400)
    near = nostr.build_event(sk, 1, "near", created_at=now)
    async with LocalRelay(port=0) as r:
        r.events.update({far["id"]: far, near["id"]: near})
        pool = RelayPool([r.url])
        pool.start()
        try:
            assert await pool.wait_open(30)
            got = await pool.query([{"kinds": [1]}], timeout=30)
            assert [e["content"] for e in got] == ["near"]
        finally:
            await pool.stop()


# --- finding 3: store ---------------------------------------------------------------------------
def ev_at(sk, text, ts):
    return nostr.build_event(sk, 1, text, [["h", "r"]], created_at=ts)


def test_store_prunes_old_events_on_open_and_caps_rooms(tmp_path):
    sk = nostr.new_secret()
    now = int(time.time())
    st = Store(tmp_path / "x.db")
    old = ev_at(sk, "old", now - 10 * 86400)
    st.add_event("r", old)
    st.add_event("r", ev_at(sk, "new", now - 10))
    st.close()
    st = Store(tmp_path / "x.db")   # opening prunes the history window
    assert [e["content"] for e in st.room_events("r")] == ["new"]
    st.event_room_cap = 50
    for i in range(130):
        st.add_event("r", ev_at(sk, f"m{i}", now - 5 + (i % 5)))
    st.prune_events()
    assert len(st.room_events("r", 10_000)) == 50
    st.close()


def test_store_cap_runs_during_normal_adds(tmp_path, monkeypatch):
    from ninsei_engine import store as store_mod
    monkeypatch.setattr(store_mod, "EVENT_PRUNE_EVERY", 10)
    sk = nostr.new_secret()
    st = Store(tmp_path / "x.db")
    st.event_room_cap = 25
    now = int(time.time())
    for i in range(100):
        st.add_event("r", ev_at(sk, f"m{i}", now - 100 + i))
    n = len(st.room_events("r", 10_000))
    assert n <= 25 + 10
    assert st.room_events("r", 1)[0]["content"] == "m99"   # the newest survive
    st.close()


def test_forget_room_deletes_its_events(tmp_path):
    sk = nostr.new_secret()
    st = Store(tmp_path / "x.db")
    st.save_room("r", {"name": "R"})
    st.save_room("keep", {"name": "K"})
    st.add_event("r", ev_at(sk, "a", int(time.time())))
    st.add_event("keep", ev_at(sk, "b", int(time.time())))
    st.forget_room("r")
    assert st.room_events("r") == [] and len(st.room_events("keep")) == 1
    st.close()


def test_topic_tracker_hits_are_bounded(monkeypatch):
    from ninsei_engine import topics
    monkeypatch.setattr(topics, "MAX_TERMS", 100)
    t = TopicTracker()
    for i in range(400):
        t.add("a", f"zq{i:04d}x zr{i:04d}y", ts=1000 + i)
    assert len(t._hits) <= 100
    for _ in range(300):
        t.add("a", "hammered", ts=2000)
    assert len(t._hits["hammered"]) <= topics.MAX_HITS
    # a huge message mints a bounded number of terms
    assert len(topics.terms(" ".join(f"w{i}abc" for i in range(5000)))) <= 2 * topics.MAX_WORDS
    # detection still works
    t2 = TopicTracker()
    t2.add("a", "pottery wheel", ts=1)
    t2.add("b", "pottery wheel", ts=2)
    assert "pottery wheel" in t2.add("a", "pottery wheel", ts=3)


# --- finding 10: outbox -------------------------------------------------------------------------
async def test_message_published_while_relay_down_arrives_after_restart(tmp_path):
    sk = nostr.new_secret()
    async with LocalRelay(port=0) as relay:
        pool = RelayPool([relay.url], outbox=Store(tmp_path / "x.db"))
        pool.start()
        try:
            assert await pool.wait_open(30)
            await relay.stop()
            assert await until(lambda: pool.open_count() == 0)
            ev = nostr.build_event(sk, 1, "sent into the void")
            await pool.publish(ev, wait=0.5)
            assert pool.delivery(ev["id"]) == "pending"
            assert ev["id"] not in relay.events
            await relay.start()
            assert await until(lambda: ev["id"] in relay.events)
            assert await until(lambda: pool.delivery(ev["id"]) == "sent")
        finally:
            await pool.stop()


async def test_pending_event_survives_an_app_restart(tmp_path):
    sk = nostr.new_secret()
    db = tmp_path / "x.db"
    ev = nostr.build_event(sk, 1, "persisted")
    pool1 = RelayPool(["ws://127.0.0.1:1"], outbox=Store(db))   # nothing listens here
    await pool1.publish(ev, wait=0.2)
    assert pool1.delivery(ev["id"]) == "pending"
    await pool1.stop()
    pool1._store.close()
    async with LocalRelay(port=0) as relay:
        pool2 = RelayPool([relay.url], outbox=Store(db))
        assert pool2.delivery(ev["id"]) == "pending"
        pool2.start()
        try:
            assert await until(lambda: ev["id"] in relay.events)
            assert await until(lambda: pool2.delivery(ev["id"]) == "sent")
        finally:
            await pool2.stop()


async def test_accepted_event_is_sent_and_rejected_event_is_failed():
    sk = nostr.new_secret()
    async with LocalRelay(port=0, max_message_size=2048) as relay:
        pool = RelayPool([relay.url])
        pool.start()
        try:
            assert await pool.wait_open(30)
            good = nostr.build_event(sk, 1, "small")
            big = nostr.build_event(sk, 1, "x" * 5000)
            await pool.publish(good, wait=30)  # returns at the relay's OK; the wait only bounds a hang
            await pool.publish(big, wait=30)
            assert pool.delivery(good["id"]) == "sent"
            assert pool.delivery(big["id"]) == "failed"
            assert not pool._outbox   # a real rejection is final, not retried forever
        finally:
            await pool.stop()


async def test_outbox_is_capped_and_expires(tmp_path):
    sk = nostr.new_secret()
    pool = RelayPool(["ws://127.0.0.1:1"], outbox=Store(tmp_path / "x.db"), outbox_max=2)
    evs = [nostr.build_event(sk, 1, f"m{i}") for i in range(3)]
    for e in evs:
        await pool.publish(e, wait=0.1)
    assert [pool.delivery(e["id"]) for e in evs] == ["failed", "pending", "pending"]

    async with LocalRelay(port=0) as relay:
        p2 = RelayPool([relay.url], outbox_ttl=0.05)
        old = nostr.build_event(sk, 1, "stale")
        p2._outbox[old["id"]] = (old, time.time() - 5)
        p2._delivery[old["id"]] = "pending"
        p2.start()
        try:
            assert await p2.wait_open(30)
            assert await until(lambda: p2.delivery(old["id"]) == "failed")
            assert old["id"] not in relay.events
        finally:
            await p2.stop()


# --- 2026-11-11: a message stuck on "Not delivered yet" while the public relays were slow -----------
class _QuietSocket:
    """A relay socket that takes the event and answers later (or never)."""
    def __init__(self):
        self.sent = []

    async def send(self, payload):
        self.sent.append(payload)


async def test_an_acceptance_after_the_wait_still_marks_the_event_delivered(tmp_path):
    # Busy relays took 25-60 s to answer; the 4 s wait had given up, and the late OK was thrown away.
    sk = nostr.new_secret()
    pool = RelayPool(["ws://x"], outbox=Store(tmp_path / "x.db"))
    pool._ws["ws://x"] = _QuietSocket()
    ev = nostr.build_event(sk, 1, "hi")
    await pool.publish(ev, wait=0.05)
    assert pool.delivery(ev["id"]) == "pending"
    await pool._on_message("ws://x", json.dumps(["OK", ev["id"], True, ""]))
    assert pool.delivery(ev["id"]) == "sent"
    assert not pool._outbox
    assert pool._store.event_outbox_status(ev["id"]) is None   # no row left to resend on the next start


async def test_a_late_rejection_or_unknown_id_changes_nothing():
    sk = nostr.new_secret()
    pool = RelayPool(["ws://x"])
    pool._ws["ws://x"] = _QuietSocket()
    ev = nostr.build_event(sk, 1, "hi")
    await pool.publish(ev, wait=0.05)
    await pool._on_message("ws://x", json.dumps(["OK", ev["id"], False, "blocked: no"]))
    assert pool.delivery(ev["id"]) == "pending"   # another relay may still take it
    await pool._on_message("ws://x", json.dumps(["OK", "ab" * 32, True, ""]))
    assert "ab" * 32 not in pool._delivery


async def test_a_socket_dropping_mid_send_does_not_stop_the_other_relays():
    # The reader resolves a dropped relay's pending answers ("disconnected") before send() raises; setting the
    # result again raised InvalidStateError, which skipped every relay after it and left the event pending.
    sk = nostr.new_secret()
    pool = RelayPool(["ws://a", "ws://b"])
    ev = nostr.build_event(sk, 1, "hi")

    class Dropping:
        async def send(self, payload):
            for fut in pool._pending_ok.pop("ws://a", {}).values():
                fut.set_result((False, relays.SYNTH + "disconnected"))
            raise ConnectionError("keepalive ping timeout")

    class Accepting(_QuietSocket):
        async def send(self, payload):
            await super().send(payload)
            asyncio.get_running_loop().call_soon(
                lambda: asyncio.ensure_future(pool._on_message("ws://b", json.dumps(["OK", ev["id"], True, ""]))))

    b = Accepting()
    pool._ws["ws://a"] = Dropping()
    pool._ws["ws://b"] = b
    out = await pool.publish(ev, wait=2)
    assert b.sent, "the relay after the dropped one never got the event"
    assert out["ws://b"] == (True, "")
    assert pool.delivery(ev["id"]) == "sent"
