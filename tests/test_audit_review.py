"""Review of the audit fixes (2026-11-06): nine confirmed findings on the fixes themselves.

1. a future-dated flood can't trim a live game or real history out of memory
2. people seen before a game take the 24 voting seats before throwaway keys
3. every filter counts toward the per-request cap
4. an empty relay list says offline and asks before saving
5. EOSE then close doesn't reset the reconnect backoff
6. an offer that expired is really expired
7. ARCHITECTURE.md stays near 1,500 words (pinned in test_audit_docs.py)
8. a game hidden while it ran shows its end
9. the Desktop spinner honours reduced motion
"""
import asyncio
import json
import time
from pathlib import Path

import pytest

from start_helpers import started

from ninsei_engine.engine import (HISTORY_FILTERS_PER_SUB, KIND_LIVE, KIND_META, KIND_ROOM, MAX_PLAYERS,
                                  MAX_ROOM_EVENTS, OFFER_TTL)
from ninsei_engine.relays import RelayPool
from test_audit_engine_reliability import RoomPool
from test_audit_engine_trust import raw_event
from test_audit_relays_platform import _server, until
from test_audit_ui import CORE, SETUP, APP, TALES, const, fn, needs_node, run
from test_hostile import ROOM, Key, bare, own_person_event, settle  # noqa: F401  (fixture re-export)

ROOT = Path(__file__).resolve().parent.parent
OID = "cd" * 32


# --- 1: a flood from a few keys can't erase a live game or the room's real history ------------------------------

async def test_a_future_dated_flood_cannot_trim_a_live_game_or_real_history(bare):
    e, _ = bare(ts=1.0)
    host, sam = Key("host"), Key("sam")
    await e._on_event(host.agent({"t": "tales_start", "gid": "live", "rounds": 3, "seq": 1, "name": "Hal"}), "relay")
    await e._on_event(host.agent({"t": "tales_round", "gid": "live", "n": 1, "q": "?", "secs": 45,
                                  "ends_at": time.time() + 45, "seq": 2, "name": "Hal"}), "relay")
    real = [sam.person({"t": "msg", "name": "Sam", "text": f"real {i}"}) for i in range(4)]
    real.append(sam.agent({"t": "tales_fake", "gid": "live", "n": 1, "text": "a fake", "name": "Bo"}))
    mine = [own_person_event(e, {"t": "msg", "text": f"mine {i}"}) for i in range(3)]
    for ev in real + mine:
        await e._on_event(ev, "relay")
    await settle(e)
    flooders = [f"{i + 1:064x}" for i in range(3)]  # a few keys, to stay under any relay's per-key limit
    now = int(time.time())
    for i in range(MAX_ROOM_EVENTS + 200):
        await e._on_event(raw_event(flooders[i % 3], {"t": "msg", "name": "Mal", "text": f"f{i}"}, now + 50,
                                    seed=str(i)), "relay")
    await settle(e)
    assert len(e.events[ROOM]) <= MAX_ROOM_EVENTS
    g = e.game_view(ROOM)
    assert g and g["gid"] == "live" and g["phase"] != "end"
    assert all(ev["id"] in e.events[ROOM] for ev in real + mine)
    # what the trim let go of is gone from disk too, and a history pull can't put it back
    gone = list(e._trimmed[ROOM])
    on_disk = {x["id"] for x in e.store.room_events(ROOM, 10_000)}
    assert gone and not (set(gone) & on_disk) and all(ev["id"] in on_disk for ev in real + mine)
    first = raw_event(flooders[0], {"t": "msg", "name": "Mal", "text": "f0"}, now + 50, seed="0")
    assert first["id"] in gone
    await e._on_event(first, "history")
    assert first["id"] not in e.events[ROOM]


async def test_the_trim_takes_the_heaviest_authors_first_and_ranks_by_arrival(bare):
    e, _ = bare()
    now = int(time.time())
    quiet, loud = f"{7:064x}", f"{8:064x}"
    evs = [raw_event(quiet, {"t": "msg", "text": f"q{i}"}, now - 3000 + i) for i in range(5)]
    evs += [raw_event(loud, {"t": "msg", "text": f"l{i}"}, now + 50, seed=str(i)) for i in range(20)]
    for ev in evs:
        e._arrived[ev["id"]] = now  # every one arrived now; the loud ones only claim a future date
    out = e._fair_drop(evs, 10)
    assert len(out) == 10 and all(ev["pubkey"] == loud for ev in out)
    # equal shares: the oldest goes first, whatever its author dated it
    a = raw_event(quiet, {"t": "msg", "text": "a"}, now + 50)
    b = raw_event(loud, {"t": "msg", "text": "b"}, now - 10)
    e._arrived[a["id"]], e._arrived[b["id"]] = now - 100, now - 5
    assert e._fair_drop([a, b], 1) == [a]


# --- 2: Sybil voters can't push real players out of the 24 seats ---------------------------------------------------

async def test_people_seen_before_the_game_take_the_seats_first(bare):
    e, _ = bare()
    real = [Key(f"real{i}") for i in range(6)]
    for i, k in enumerate(real):
        await e._on_event(k.person({"t": "join", "name": f"R{i}"}), "relay")
    await settle(e)
    regulars = e._regulars(ROOM)
    assert {k.ppk for k in real} <= regulars and e._identity()["person_pk"] in regulars
    sybils = [f"{i + 100:064x}" for i in range(30)]  # each one a person with a bound agent beating presence
    voters = [k.ppk for k in real] + sybils
    for seed in ("s1", "s2", "s3"):
        out = e._round_voters({pk: {"option": "x"} for pk in voters}, set(voters), {}, seed, regulars)
        assert len(out) == MAX_PLAYERS and {k.ppk for k in real} <= set(out)
        fakes = e._round_answers({pk: "fake" for pk in voters}, set(voters), {}, seed, regulars)
        assert len(fakes) == MAX_PLAYERS and {k.ppk for k in real} <= set(fakes)


async def test_a_hosted_game_remembers_who_was_there_before_it_started(bare):
    e, _ = bare()
    early, late = Key("early"), Key("late")
    await e._on_event(early.person({"t": "join", "name": "Early"}), "relay")
    gid = (await started(e, ROOM, 1))["gid"]
    await e._on_event(late.person({"t": "join", "name": "Late"}), "relay")
    regulars = e._host_games[gid]["regulars"]
    assert early.ppk in regulars and late.ppk not in regulars


# --- 3: the live and metadata filters count toward the per-request cap --------------------------------------------

async def test_no_request_carries_more_than_the_filter_cap(bare):
    e, _ = bare()
    e.pool = RoomPool()
    rooms = [f"{i:016x}" for i in range(1, 10)]
    for i, r in enumerate(rooms):  # nine rooms, each made by someone else
        e.store.save_room(r, {"id": r, "name": r, "creator": f"{i + 1:064x}"})
    await e._resubscribe()
    assert all(len(fs) <= HISTORY_FILTERS_PER_SUB for fs in e.pool.subs.values())
    every = [f for fs in e.pool.subs.values() for f in fs]
    assert sum(f["kinds"] == [KIND_LIVE] for f in every) == 1
    assert any(f["kinds"] == [KIND_LIVE] for f in e.pool.subs["rooms"])
    metas = [f for f in every if f["kinds"] == [KIND_META] and "ninsei/avatar" not in f.get("#d", [])]   # not the pictures request
    assert {a for f in metas for a in f.get("authors", [])} == {f"{i + 1:064x}" for i in range(9)}
    assert sorted(f["#h"][0] for f in every if f["kinds"] == [KIND_ROOM]) == sorted([ROOM] + rooms)


# --- 5: a relay that answers EOSE and closes at once is not a healthy connection ------------------------------------

async def test_backoff_keeps_growing_for_a_relay_that_sends_eose_and_closes():
    async def handler(ws):
        async for raw in ws:
            m = json.loads(raw)
            if m[0] == "REQ":
                await ws.send(json.dumps(["EOSE", m[1]]))
                await ws.close()
                return
    srv, url = await _server(handler)
    pool = RelayPool([url], backoff_base=0.01, backoff_max=0.16)
    await pool.subscribe("s", [{"kinds": [1]}], lambda ev, u: None)
    pool.start()
    try:
        assert await until(lambda: pool.status[url].backoff >= 0.16)
    finally:
        await pool.stop()
        srv.close()
        await asyncio.wait_for(srv.wait_closed(), 5)


# --- 6: an expired offer is expired everywhere ------------------------------------------------------------------------

def _offer(status="open", age=0.0):
    return {OID: {"room": ROOM, "topic": "t", "title": "T", "task": "x", "status": status, "at": time.time() - age}}


async def test_an_expired_or_answered_offer_cannot_be_accepted(bare):
    e, _ = bare()
    e.store.set("offers", _offer(age=2 * 86400))
    with pytest.raises(ValueError, match="expired"):
        await e.answer_offer(OID, True)
    e.store.set("offers", _offer(status="declined"))
    with pytest.raises(ValueError, match="already answered"):
        await e.answer_offer(OID, True)
    assert not e.pool.sent


async def test_expiry_is_posted_to_the_room_once(bare):
    e, _ = bare()
    e.store.set("offers", _offer(age=OFFER_TTL + 60))
    await e._announce_expired()
    await e._announce_expired()
    await settle(e)
    assert e.store.get("offers")[OID]["status"] == "expired"
    states = [json.loads(ev["content"]) for ev in e.pool.sent]
    states = [c for c in states if c.get("t") == "offer_state"]
    assert states == [{"at": states[0]["at"], "name": "Maya", "t": "offer_state", "offer": OID, "state": "expired"}]


async def test_others_see_an_unanswered_offer_expire_after_a_day(bare):
    e, _ = bare()
    maker = Key("maker")
    old = maker.agent({"t": "offer", "topic": "t", "title": "Old", "pitch": "p", "name": "Bo"},
                      created_at=int(time.time()) - OFFER_TTL - 600)
    new = maker.agent({"t": "offer", "topic": "t", "title": "New", "pitch": "p", "name": "Bo"})
    await e._on_event(old, "history")
    await e._on_event(new, "relay")
    await settle(e)
    state = {m["title"]: m["state"] for m in e.messages(ROOM) if m["t"] == "offer"}
    assert state == {"Old": "expired", "New": "open"}


def test_offer_cards_have_copy_for_expired_and_dropped():
    room = (ROOT / "ui" / "50_room.js").read_text()
    for needle in ("state === 'expired'", "state === 'dropped'", "m.state === 'expired'",
                   "Expired: nobody answered it within a day.", "Dropped when you left the room."):
        assert needle in room, needle


# --- 4: an empty relay list is offline, and Settings says so -------------------------------------------------------

SETTINGS_JS = lambda: (fn(SETUP, "parseCount") + const(SETUP, "BUDGET_MAX") + const(SETUP, "MSGS_MAX")
                       + fn(SETUP, "limitError") + fn(SETUP, "SettingsForm") + fn(SETUP, "capFirst") + fn(SETUP, "budgetOption") + fn(SETUP, "budgetOptions")
                       + fn(SETUP, "useKeepAboveBar") + fn(CORE, "repliesFor") + fn(CORE, "repliesWords") + fn(CORE, "repliesLeftWords") + const(CORE, "REPLY_TOKENS_GUESS") + """
function Field() {}; function Seg() {}; function VibePresets() {}; function IdCard() {}; function FacePicker() {}; function BudgetRing() {}; const AWAY_CHOICES = []; const OTHERS_SPENT = ''; function othersLine() { return '' }
function InterestInput() {}; function Notice() {}; function PersonLook() {}; const cleanAvatar = a => a || null
function HermesPicker() {}; function PersonaField() {}; function applyProposal() {}
K.Toggle = function Toggle() {}
const useFaceEditorFocus = () => {}
const faceFor = f => f || {}
const shortModel = m => m; const stateWord = s => s; const STATE_LABEL = {}
const fmtTokens = n => String(n); const fmtAgo = () => ''
const BUDGET_PRESETS = [40000]
function snapWith(relays) {
  return { me: { pk: 'p', agent: { pk: 'a', state: 'idle', model: '' } }, relays: [], hidden: [],
    budget: { used: 0, limit: 40000, by: {} },
    settings: { display_name: 'Maya', line: '', agent_name: 'Ada', vibe: '', face: {}, interests: [],
      budget_daily: 40000, msgs_daily: 60, chattiness: 'quiet', relays } }
}
const textarea = tree => find(tree, n => n.type === 'textarea')
""")


@needs_node
def test_clearing_the_relays_asks_before_going_offline_and_offline_is_shown():
    r = run(SETTINGS_JS() + """
const posts = []
const store = { post: async (path, body) => { posts.push(body) } }
const on = mount(SettingsForm, { store, snap: snapWith(['wss://relay.example']) })
const onlineNotice = text(on.tree).includes('Offline')
textarea(on.tree).props.onChange({ target: { value: '  ' } })
await settle()
button(on.tree, 'Save changes').props.onClick()
await settle()
const asked = text(on.tree)
const postedFirst = posts.length
button(on.tree, 'Save and go offline').props.onClick()
await settle()
const off = mount(SettingsForm, { store, snap: snapWith([]) })
out({ onlineNotice, asked, postedFirst, saved: posts.map(p => p.relays), offline: text(off.tree) })
""")
    assert not r["onlineNotice"]
    assert r["postedFirst"] == 0, "the first press only asks"
    assert "Saving takes your agent offline" in r["asked"]
    assert r["saved"] == [[]]
    assert "Offline: no relays set" in r["offline"]
    app = fn(APP, "App") if "function App(" in APP else APP
    assert "Offline: no relays set, so nothing leaves this machine." in app


# --- 8: a game hidden while running shows its end -------------------------------------------------------------------

def test_the_end_of_a_game_brings_a_hidden_panel_back():
    tales = fn(TALES, "TallTales")
    assert "game.phase === 'fakes' || game.phase === 'vote' || game.phase === 'end') setHidden(false)" in tales
    # the end-to-end check is test_audit_ui::test_hidden_game_panel_leaves_a_show_bar_and_a_new_action_phase_restores_it


# --- 9: the Desktop spinner honours reduced motion ------------------------------------------------------------------

def test_desktop_spinner_stops_with_reduced_motion():
    needle = "spinning: !!props.spinning && !motion.reduced()"
    assert needle in (ROOT / "ui" / "platform" / "desktop_tail.js").read_text()
    assert needle in (ROOT / "desktop" / "plugin.js").read_text()
