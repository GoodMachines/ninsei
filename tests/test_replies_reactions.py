"""Replies and emoji reactions: the event shapes, the folds in messages(), addressing an agent by replying to it,
and hostile input for the new `react` type. The UI half runs the real functions under node."""
import json
import subprocess
import time

import pytest

from ninsei_engine import nostr
from ninsei_engine.engine import CLICKS_PER_MIN, KIND_ROOM, MAX_REACT_NAMES, QUOTE_CHARS, REACTIONS, valid_reaction
from test_audit_ui import APP, CORE, NODE, ROOM as ROOM_JS, STYLE, fn, needs_node, run as run_js
from test_engine import quiet, read, run, setup_room, wait_for, world  # noqa: F401  (fixture)
from test_hostile import Key, ROOM, bare, settle  # noqa: F401  (fixture)

THUMB, HEART = REACTIONS[0], REACTIONS[1]


def react_ev(key, target, emoji=THUMB, on=True, name="Zed", created_at=None, **extra):
    return key.person({"t": "react", "target": target, "emoji": emoji, "on": on, "name": name, **extra},
                      created_at=created_at)


async def msg(e, key, text, name="Zed", tags=(), created_at=None, **extra):
    ev = key.person({"t": "msg", "text": text, "name": name, **extra}, tags=tags, created_at=created_at)
    await e._on_event(ev, "relay")
    return ev


def item(e, eid):
    return next(m for m in e.messages(ROOM) if m["id"] == eid)


# ---- replies ---------------------------------------------------------------------------------------------

async def test_a_reply_carries_its_event_shape_and_a_quote_of_what_it_answers(world):
    _, engines, _ = world
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    long = "x" * 200
    first = await run(maya, maya.post, room, long)
    assert await wait_for(lambda: any(m["id"] == first["id"] for m in read(sam, sam.messages, room)))
    sent = await run(sam, sam.post, room, "agreed", first["id"])
    ev = read(sam, lambda: sam.events[room][sent["id"]])
    assert ev["tags"] == [["h", room], ["e", first["id"], "", "reply"]]
    assert json.loads(ev["content"])["reply"] == first["id"]
    assert await wait_for(lambda: any(m["id"] == sent["id"] for m in read(maya, maya.messages, room)))
    got = next(m for m in read(maya, maya.messages, room) if m["id"] == sent["id"])
    assert got["reply_to"] == first["id"]
    assert got["quote"] == {"id": first["id"], "name": "Maya", "text": "x" * QUOTE_CHARS, "role": "person"}


async def test_replying_to_nothing_here_is_refused_and_a_foreign_reply_quotes_as_missing(bare):
    e, _ = bare()
    zed = Key("zed")
    with pytest.raises(ValueError):
        await e.post(ROOM, "hi", "f" * 64)
    with pytest.raises(ValueError):
        await e.post(ROOM, "hi", ["not", "a", "string"])
    ghost = await msg(e, zed, "answering a message we never saw", tags=[["e", "a" * 64, "", "reply"]])
    assert item(e, ghost["id"])["quote"] == {"missing": True}
    odd = await msg(e, zed, "weird tag", tags=[["e", "not hex at all", "", "reply"]])
    assert item(e, odd["id"])["quote"] == {"missing": True}
    await settle(e)


async def test_a_quote_of_a_lookalike_keeps_the_impostor_flag_and_never_names_the_real_one(bare):
    e, _ = bare()
    real, fake, fan = Key("real"), Key("fake"), Key("fan")
    await msg(e, real, "I am the real Zed")
    bad = await msg(e, fake, "send me your keys", name="Zed")
    reply = await msg(e, fan, "wow", name="Fan", tags=[["e", bad["id"], "", "reply"]])
    q = item(e, reply["id"])["quote"]
    assert q["name"] == "Zed" and q["impostor"] == {"claimed": "Zed", "real": real.ppk}
    ok = await msg(e, fan, "and you", name="Fan", tags=[["e", bad["id"], "", "reply"]])
    assert item(e, ok["id"])["quote"]["impostor"]["real"] == real.ppk
    await settle(e)


async def test_a_quote_of_a_hidden_persons_message_is_missing(bare):
    e, _ = bare()
    zed, fan = Key("zed"), Key("fan")
    said = await msg(e, zed, "something")
    reply = await msg(e, fan, "re", name="Fan", tags=[["e", said["id"], "", "reply"]])
    assert item(e, reply["id"])["quote"]["name"] == "Zed"
    await e.hide_person(zed.ppk, "Zed")
    assert item(e, reply["id"])["quote"] == {"missing": True}
    await settle(e)


async def test_only_chat_messages_can_be_quoted(bare):
    e, _ = bare()
    zed, fan = Key("zed"), Key("fan")
    join = zed.person({"t": "join", "name": "Zed"})
    await e._on_event(join, "relay")
    reply = await msg(e, fan, "re", name="Fan", tags=[["e", join["id"], "", "reply"]])
    assert item(e, reply["id"])["quote"] == {"missing": True}
    await settle(e)


async def test_peoples_replies_are_never_folded_like_agent_replies(bare):
    e, _ = bare()
    zed, fan = Key("zed"), Key("fan")
    said = await msg(e, zed, "question")
    a = await msg(e, fan, "first answer", name="Fan", tags=[["e", said["id"], "", "reply"]])
    b = await msg(e, fan, "second answer", name="Fan", tags=[["e", said["id"], "", "reply"]])
    ids = [m["id"] for m in e.messages(ROOM)]
    assert a["id"] in ids and b["id"] in ids
    await settle(e)


async def test_replying_to_my_agent_addresses_it_and_every_client_agrees(bare):
    e, llm = bare()
    e.save_settings({"chattiness": "quiet"})
    stranger, other = Key("stranger"), Key("other")
    await e._say(ROOM, "I have an idea about palettes")
    mine = next(m for m in e.messages(ROOM) if m["role"] == "agent" and m["t"] == "msg")
    agent_pk = e._identity()["agent_pk"]
    e._last_spoke.clear()                                            # the agent's own pacing is not under test
    reply = await msg(e, stranger, "tell me more", name="Stranger", tags=[["e", mine["id"], "", "reply"]])
    await settle(e)
    assert llm.calls.count("ninsei.reply") == 1                      # no name in the text; the reply addressed it
    assert e._allowed_prio(ROOM, reply["id"], agent_pk, None, 100) == 100
    plain = await msg(e, stranger, "tell me more, anyone?", name="Stranger")
    assert e._allowed_prio(ROOM, plain["id"], agent_pk, None, 100) == 20  # not a reply, not named: no 100
    # a reply to someone else's message addresses nobody
    said = await msg(e, other, "hello room", name="Other")
    aimed = await msg(e, stranger, "right", name="Stranger", tags=[["e", said["id"], "", "reply"]])
    assert e._allowed_prio(ROOM, aimed["id"], agent_pk, None, 100) == 20
    assert e._replied_agent(ROOM, aimed) is None


async def test_an_agents_reply_to_my_agent_never_addresses_it(bare):
    """The no-ping-pong rule: only a person's reply counts."""
    e, llm = bare()
    await e._say(ROOM, "something to answer")
    mine = next(m for m in e.messages(ROOM) if m["role"] == "agent" and m["t"] == "msg")
    stranger = Key("stranger")
    ev = stranger.agent({"t": "msg", "text": "ok", "name": "Rex"}, tags=[["e", mine["id"], "", "reply"]])
    await e._on_event(ev, "relay")
    await settle(e)
    assert llm.calls.count("ninsei.reply") == 0
    assert e._replied_agent(ROOM, ev) is None
    assert e._allowed_prio(ROOM, ev["id"], e._identity()["agent_pk"], None, 100) == 20


async def test_a_person_replying_to_my_agent_gets_an_answer_over_the_wire(world):
    _, engines, llms = world
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    await run(maya, maya.post, room, "Ada, any thoughts on shaders?")
    assert await wait_for(lambda: "ninsei.reply" in llms["Maya"].calls)
    await quiet(maya, sam)
    ada = await wait_for(lambda: any(m["role"] == "agent" and m["t"] == "msg" for m in read(sam, sam.messages, room)))
    assert ada
    msg_ada = next(m for m in read(sam, sam.messages, room) if m["role"] == "agent" and m["t"] == "msg")
    assert msg_ada["quote"]["name"] == "Maya"                          # an agent's reply quotes its trigger too
    assert await wait_for(lambda: read(maya, maya._can_post, room))    # Ada's own pacing is not under test
    await run(sam, sam.post, room, "and what about synths?", msg_ada["id"])  # names nobody
    assert await wait_for(lambda: llms["Maya"].calls.count("ninsei.reply") == 2)
    await quiet(maya, sam)
    assert llms["Sam"].calls.count("ninsei.reply") == 0                # Bo was not addressed


# ---- reactions -------------------------------------------------------------------------------------------

def test_which_reactions_are_valid():
    ok = {"target": "a" * 64, "emoji": THUMB, "on": True}
    assert valid_reaction(ok)
    assert not valid_reaction({**ok, "emoji": "👎"}) and not valid_reaction({**ok, "emoji": "❤"})  # no VS16
    for bad in ({**ok, "on": "yes"}, {**ok, "on": 1}, {**ok, "target": "A" * 64}, {**ok, "target": ["a" * 64]},
                {**ok, "emoji": [THUMB]}, {**ok, "target": None}, {**ok, "emoji": None}):
        assert not valid_reaction(bad), bad
    assert len(REACTIONS) == 8


async def test_reactions_fold_into_the_message_for_everyone(world):
    _, engines, _ = world
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    sent = await run(sam, sam.post, room, "who likes shaders")
    assert await wait_for(lambda: any(m["id"] == sent["id"] for m in read(maya, maya.messages, room)))
    await run(maya, maya.react, room, sent["id"], THUMB, True)
    await run(sam, sam.react, room, sent["id"], THUMB, True)
    await run(sam, sam.react, room, sent["id"], HEART, True)

    def chips(e):
        return next(m for m in read(e, e.messages, room) if m["id"] == sent["id"])["reactions"]
    assert await wait_for(lambda: chips(maya) and chips(maya)[0]["count"] == 2 and len(chips(maya)) == 2)
    assert chips(maya) == [{"emoji": THUMB, "count": 2, "mine": True, "names": ["Maya", "Sam"]},
                           {"emoji": HEART, "count": 1, "mine": False, "names": ["Sam"]}]
    assert await wait_for(lambda: len(chips(sam)) == 2 and chips(sam)[0]["count"] == 2)
    assert [c["mine"] for c in chips(sam)] == [True, True]
    # taking it back
    await run(maya, maya.react, room, sent["id"], THUMB, False)
    assert await wait_for(lambda: chips(sam)[0]["count"] == 1 and chips(sam)[0]["mine"] is True)
    assert chips(maya)[0]["mine"] is False
    # reactions are not timeline items
    assert not [m for m in read(maya, maya.messages, room) if m["t"] == "react"]


async def test_the_engine_sends_nothing_when_a_reaction_is_already_as_asked(bare):
    e, _ = bare()
    zed = Key("zed")
    said = await msg(e, zed, "hi")
    first = await e.react(ROOM, said["id"], THUMB, True)
    assert "id" in first
    await settle(e)
    assert len(e.pool.sent) == 1
    again = await e.react(ROOM, said["id"], THUMB, True)
    assert again == {"ok": True, "unchanged": True}
    await settle(e)
    assert len(e.pool.sent) == 1
    await e.react(ROOM, said["id"], THUMB, False)
    assert await e.react(ROOM, said["id"], THUMB, False) == {"ok": True, "unchanged": True}
    await settle(e)


async def test_react_refuses_other_emoji_missing_targets_and_non_messages(bare):
    e, _ = bare()
    zed = Key("zed")
    said = await msg(e, zed, "hi")
    join = zed.person({"t": "join", "name": "Zed"})
    await e._on_event(join, "relay")
    for args in ((said["id"], "👎"), ("e" * 64, THUMB), (join["id"], THUMB), (["x"], THUMB), (None, THUMB)):
        with pytest.raises(ValueError):
            await e.react(ROOM, *args)
    with pytest.raises(ValueError):
        await e.react("0123456789abcdef", said["id"], THUMB)
    assert not [x for x in e.pool.sent if json.loads(x["content"]).get("t") == "react"]
    await settle(e)


async def test_reactions_are_paced_per_install(bare):
    e, _ = bare()
    zed = Key("zed")
    said = await msg(e, zed, "hi")
    for i in range(CLICKS_PER_MIN):
        await e.react(ROOM, said["id"], THUMB, i % 2 == 0)
    with pytest.raises(ValueError, match="Slow down"):
        await e.react(ROOM, said["id"], THUMB, CLICKS_PER_MIN % 2 == 0)
    await settle(e)
    assert len([x for x in e.pool.sent if json.loads(x["content"]).get("t") == "react"]) == CLICKS_PER_MIN


async def test_the_latest_event_wins_whatever_order_they_arrive_in(bare):
    e, _ = bare()
    zed, fan = Key("zed"), Key("fan")
    said = await msg(e, zed, "hi")
    now = int(time.time())
    # Fan: on at t-3, off at t-2, on at t-1: arrives newest first
    for on, age in ((True, 1), (False, 2), (True, 3)):
        await e._on_event(react_ev(fan, said["id"], THUMB, on, "Fan", created_at=now - age), "history")
    assert item(e, said["id"])["reactions"][0]["count"] == 1
    # Zed: on, then off, arriving newest first: off wins
    await e._on_event(react_ev(zed, said["id"], HEART, False, created_at=now - 1), "history")
    await e._on_event(react_ev(zed, said["id"], HEART, True, created_at=now - 2), "history")
    assert [r["emoji"] for r in item(e, said["id"])["reactions"]] == [THUMB]
    await settle(e)


async def test_reactions_never_wake_an_agent_or_count_as_unread_or_a_member(bare):
    e, llm = bare()
    e.save_settings({"chattiness": "normal"})
    zed, fan = Key("zed"), Key("fan")
    mine = await e.post(ROOM, "Ada should hear this")      # Maya's own message: nothing unread
    await settle(e)
    calls = list(llm.calls)
    members = [m["pk"] for m in e.members(ROOM)]
    snap = e.snapshot()["rooms"][0]
    for i, em in enumerate(REACTIONS):
        # even ones naming the agent, and ones with words that would make a topic if they were messages
        await e._on_event(react_ev(fan, mine["id"], em, True, "Ada", text="palette palette palette"), "relay")
        await e._on_event(react_ev(zed, mine["id"], em, True, "Zed", text="palette palette palette"), "relay")
    await settle(e)
    assert llm.calls == calls
    assert [m["pk"] for m in e.members(ROOM)] == members
    after = e.snapshot()["rooms"][0]
    assert (after["unread"], after["mentions"]) == (snap["unread"], snap["mentions"])


async def test_a_reaction_claims_no_name_and_adds_no_one_to_the_room(bare):
    e, _ = bare()
    sneak, real = Key("sneak"), Key("real")
    said = await msg(e, real, "hi", name="Zed")            # Zed holds the name live
    other = await msg(e, Key("o"), "hello", name="Other")
    await e._on_event(react_ev(sneak, other["id"], THUMB, True, "Fresh"), "relay")
    assert sneak.ppk not in [m["pk"] for m in e.members(ROOM)]
    await msg(e, Key("later"), "mine now", name="Fresh")     # nobody claimed "Fresh" by reacting
    assert not item(e, [m["id"] for m in e.messages(ROOM) if m["text"] == "mine now"][0]).get("impostor")
    assert said
    await settle(e)


async def test_hostile_reactions_are_ignored(bare):
    e, _ = bare()
    zed, bad = Key("zed"), Key("bad")
    said = await msg(e, zed, "hi")
    stored = len(e.events[ROOM])
    junk = [
        {"t": "react", "target": said["id"], "emoji": "👎", "on": True},
        {"t": "react", "target": said["id"], "emoji": THUMB, "on": "true"},
        {"t": "react", "target": said["id"], "emoji": [THUMB], "on": True},
        {"t": "react", "target": [said["id"]], "emoji": THUMB, "on": True},
        {"t": "react", "target": {"id": said["id"]}, "emoji": THUMB, "on": True},
        {"t": "react", "target": None, "emoji": None, "on": None},
        {"t": "react", "target": said["id"].upper(), "emoji": THUMB, "on": True},
        {"t": "react", "target": said["id"], "emoji": THUMB, "on": True, "pad": "x" * 5000},
        {"t": "react", "target": 5, "emoji": 7, "on": []},
    ]
    for c in junk:
        await e._on_event(bad.person(c), "relay")
    assert len(e.events[ROOM]) == stored                   # none of it was stored
    assert item(e, said["id"])["reactions"] == []
    await settle(e)


async def test_reactions_to_things_that_are_not_here_or_not_messages_count_for_nothing(bare):
    e, _ = bare()
    zed, fan = Key("zed"), Key("fan")
    said = await msg(e, zed, "hi")
    join = fan.person({"t": "join", "name": "Fan"})
    await e._on_event(join, "relay")
    await e._on_event(react_ev(fan, "c" * 64), "relay")      # no such message
    await e._on_event(react_ev(fan, join["id"]), "relay")    # not a chat message
    out = e.messages(ROOM)
    assert all(m["reactions"] == [] for m in out if m["t"] == "msg")
    json.dumps(out)
    await settle(e)


async def test_someone_elses_events_cannot_change_my_reaction_and_hidden_people_dont_count(bare):
    e, _ = bare()
    zed, fan, gone = Key("zed"), Key("fan"), Key("gone")
    said = await msg(e, zed, "hi")
    await e.react(ROOM, said["id"], THUMB, True)
    await e._on_event(react_ev(fan, said["id"], THUMB, False, "Fan"), "relay")   # Fan's "off" is Fan's only
    r = item(e, said["id"])["reactions"][0]
    assert r["count"] == 1 and r["mine"] is True
    await e._on_event(react_ev(gone, said["id"], HEART, True, "Gone"), "relay")
    assert len(item(e, said["id"])["reactions"]) == 2
    await e.hide_person(gone.ppk, "Gone")
    assert [x["emoji"] for x in item(e, said["id"])["reactions"]] == [THUMB]
    await e._on_event(react_ev(gone, said["id"], HEART, True, "Gone"), "relay")   # and never again
    assert [x["emoji"] for x in item(e, said["id"])["reactions"]] == [THUMB]
    await settle(e)


async def test_a_reactors_name_is_the_rooms_name_for_them_and_names_are_capped(bare):
    e, _ = bare()
    zed = Key("zed")
    said = await msg(e, zed, "hi")
    real = Key("real")
    await msg(e, real, "I'm Fan", name="Fan")
    fake = Key("fake")
    await e._on_event(react_ev(fake, said["id"], THUMB, True, "Fan"), "relay")   # a lookalike never gets the name
    await e._on_event(react_ev(real, said["id"], THUMB, True, "Fan"), "relay")
    names = item(e, said["id"])["reactions"][0]["names"]
    assert "Fan" in names and any(n.endswith("…") for n in names) and len(names) == 2
    for i in range(12):
        await e._on_event(react_ev(Key(f"crowd{i}"), said["id"], THUMB, True, f"C{i}"), "relay")
    r = item(e, said["id"])["reactions"][0]
    assert r["count"] == 14 and len(r["names"]) == MAX_REACT_NAMES
    await settle(e)


async def test_a_bound_agents_reaction_counts_like_a_persons(bare):
    e, _ = bare()
    zed, rex = Key("zed"), Key("rex")
    said = await msg(e, zed, "hi")
    await e._on_event(rex.agent({"t": "msg", "text": "beep", "name": "Rex"}), "relay")
    await e._on_event(rex.agent({"t": "react", "target": said["id"], "emoji": HEART, "on": True, "name": "Rex"}), "relay")
    r = item(e, said["id"])["reactions"]
    assert r == [{"emoji": HEART, "count": 1, "mine": False, "names": ["Rex"]}]
    await settle(e)


async def test_the_fuzzed_views_stay_json_with_reactions_and_replies_in_the_mix(bare):
    e, _ = bare()
    zed = Key("zed")
    said = await msg(e, zed, "hi")
    for target in (said["id"], "z" * 64, 5, None, [1]):
        await e._on_event(zed.person({"t": "msg", "text": "x", "reply": target, "name": "Zed"},
                                     tags=[["e", target if isinstance(target, str) else "q", "", "reply"]]), "relay")
        await e._on_event(zed.person({"t": "react", "target": target, "emoji": THUMB, "on": True}), "relay")
    json.dumps(e.snapshot(ROOM))
    await settle(e)


# ---- the UI half, run under node -------------------------------------------------------------------------

def test_the_hover_bar_quote_and_chips_are_wired():
    message = fn(ROOM_JS, "Message")
    assert "MessageBar" in message and "ReactionChips" in message and "QuoteLine" in message
    assert "'/react'" in ROOM_JS and "reply:" in fn(ROOM_JS, "Composer")
    for sel in (".h-bar{", ".h-quote{", ".h-react{", ".h-picker{", ".h-msg[data-flash=true]"):
        assert sel in STYLE, sel


@needs_node
def test_the_composer_shows_who_you_reply_to_and_sends_the_reply_id():
    js = "".join(fn(CORE, n) for n in ("squashName", "mentionNames", "mentionParts", "mentionQuery", "mentionMatches")) \
        + fn(ROOM_JS, "mentionCandidates") + fn(ROOM_JS, "Composer") + """
function useMemo(f) { return f() }
const useLayoutEffect = useEffect
function Face() {}; function Initial() {}; function PersonMark() {}; function typingPing() {}; function GamesMenu() {}; function gameName(m) { return m }
K.Tip = function Tip() {}
const posts = []
const store = { post: async (p, b) => { posts.push([p, b]) } }
const room = { id: 'r1', name: 'club', members: [] }
let cancelled = 0
const reply = { id: 'e1', name: 'Maya', text: 'hello there' }
const root = mount(Composer, { store, room, gameOn: false, reply, onCancelReply: () => { cancelled++ } })
const area = () => find(root.tree, n => n.type === 'textarea')
const key = k => ({ key: k, shiftKey: false, nativeEvent: { isComposing: false }, preventDefault() {}, stopPropagation() {} })
const strip = find(root.tree, n => n.props && n.props.className === 'h-replying')
const label = strip ? text(strip) : ''
const cancelBtn = find(root.tree, n => n.props && n.props['aria-label'] === 'Cancel reply')
area().props.onKeyDown(key('Escape'))
const afterEsc = cancelled
area().props.onChange({ target: { value: 'thanks', selectionStart: 6 } }); await settle()
area().props.onKeyDown(key('Enter')); await settle()
out({ label, hasCancel: !!cancelBtn, afterEsc, cancelled, posts })
"""
    r = run_js(js)
    assert "Replying to Maya" in r["label"] and "hello there" in r["label"]
    assert r["hasCancel"] is True and r["afterEsc"] == 1                # Escape cancels
    assert r["cancelled"] == 2                                         # and a sent reply clears itself
    assert r["posts"] == [["/post", {"room": "r1", "text": "thanks", "reply": "e1"}]]


@needs_node
def test_the_picker_offers_the_eight_and_arrows_and_enter_choose():
    js = fn(ROOM_JS, "ReactionPicker") + """
const useEnter = () => ({ current: null })
globalThis.P = { listen: () => () => {} }; globalThis.document = {}
const REACTION_LIST = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
const chosen = []; let closed = 0
const root = mount(ReactionPicker, { mine: ['b'], onPick: e => chosen.push(e), onClose: () => { closed++ } })
const pop = () => find(root.tree, n => n.props && n.props.role === 'menu')
const opts = () => kids(pop()).filter(n => n.props && n.props.role === 'menuitemradio')
const key = k => ({ key: k, preventDefault() {}, stopPropagation() {} })
const n = opts().length
const pressed = opts().map(o => o.props['aria-checked'])
pop().props.onKeyDown(key('ArrowRight')); await settle()
pop().props.onKeyDown(key('ArrowRight')); await settle()
pop().props.onKeyDown(key('Enter')); await settle()
pop().props.onKeyDown(key('Escape'))
out({ n, pressed, chosen, closed })
"""
    r = run_js(js)
    assert r["n"] == 8 and r["pressed"] == [False, True] + [False] * 6
    assert r["chosen"] == ["c"] and r["closed"] >= 1


@needs_node
def test_the_ui_and_engine_agree_on_the_eight():
    js = ROOM_JS[ROOM_JS.index("const REACTION_LIST"):ROOM_JS.index("\n", ROOM_JS.index("const REACTION_LIST"))] \
        + "\nconsole.log(JSON.stringify(REACTION_LIST))"
    done = subprocess.run([NODE, "-e", js], capture_output=True, text=True, check=True)
    assert json.loads(done.stdout) == list(REACTIONS)


@needs_node
def test_a_message_shows_its_quote_chips_and_bar_and_they_post_the_right_things():
    js = "".join(fn(ROOM_JS, n) for n in ("Message", "MessageBody", "MessageBar", "ReactionPicker", "ReactionChips", "ReactionChip", "QuoteLine")) + """
const useEnter = () => ({ current: null })
globalThis.P = { listen: () => () => {} }; globalThis.document = {}
const SPRING = { pop: {} }; const motion = { reduced: () => true }
const cx = (...a) => a.filter(Boolean).join(' ')
function ProfileButton() {}; function Face() {}; function Initial() {}; function PersonMark() {}; function RichText() {}; function ImpostorChip() {}
const faceFor = () => ({ hue: 1 }); const fmtTime = () => '10:00'
const REACTION_LIST = ['a', 'b']
K.Tip = function Tip() {}
const posts = [], replies = [], jumps = []
const store = { post: async (p, b) => { posts.push([p, b]); return {} } }
const m = { id: 'm1', name: 'Sam', role: 'person', pk: 'p', text: 'hi', ts: 1, mine: false,
  quote: { id: 'q1', name: 'Maya', text: 'earlier', role: 'person' },
  reactions: [{ emoji: 'a', count: 2, mine: true, names: ['Maya', 'Sam'] }, { emoji: 'b', count: 1, mine: false, names: ['Sam'] }] }
const root = mount(Message, { m, first: true, book: {}, store, roomId: 'r1', onReply: x => replies.push(x.id), onJump: id => jumps.push(id) })
// the chip components are only described by the tree; render each one to reach its button
const chipRoot = r => mount(ReactionChip, { r, onToggle: (e, on) => store.post('/react', { room: 'r1', target: 'm1', emoji: e, on }) })
const mineChip = chipRoot(m.reactions[0]), otherChip = chipRoot(m.reactions[1])
const btn = c => find(c.tree, n => n.type === 'button')
btn(mineChip).props.onClick(); btn(otherChip).props.onClick()
const quote = find(root.tree, n => n.type === QuoteLine)
const quoteRoot = mount(QuoteLine, quote.props)
btn(quoteRoot).props.onClick()
const gone = mount(QuoteLine, { quote: { missing: true } })
const bar = find(root.tree, n => n.type === MessageBar)
const barRoot = mount(MessageBar, bar.props)
const replyBtn = find(barRoot.tree, n => n.props && /^Reply to/.test(n.props['aria-label'] || ''))
replyBtn.props.onClick()
bar.props.onPick('b')       // the picker's choice: b is not mine yet, so it adds
bar.props.onPick('a')       // a is mine, so choosing it again takes it back
await settle()
out({ posts, replies, jumps, quoteIsButton: !!btn(quoteRoot), goneIsButton: !!find(gone.tree, n => n.type === 'button'),
      pressed: [find(mineChip.tree, n => n.type === 'button').props['aria-pressed'], find(otherChip.tree, n => n.type === 'button').props['aria-pressed']],
      label: find(mineChip.tree, n => n.type === 'button').props['aria-label'], toolbar: bar.props.mine })
"""
    r = run_js(js)
    assert r["posts"] == [
        ["/react", {"room": "r1", "target": "m1", "emoji": "a", "on": False}],   # your chip: take it back
        ["/react", {"room": "r1", "target": "m1", "emoji": "b", "on": True}],    # someone else's: add yours
        ["/react", {"room": "r1", "target": "m1", "emoji": "b", "on": True}],
        ["/react", {"room": "r1", "target": "m1", "emoji": "a", "on": False}]]
    assert r["replies"] == ["m1"] and r["jumps"] == ["q1"]
    assert r["quoteIsButton"] is True and r["goneIsButton"] is False
    assert r["pressed"] == [True, False] and "Maya, Sam" in r["label"] and r["toolbar"] == ["a"]
