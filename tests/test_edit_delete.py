"""Edit and delete your own messages: event shapes, who may touch what, and how edits and deletes flow through
quotes, search, mention counts, reactions, agent transcripts and the rest of the views."""
import json
import time

import pytest

from ninsei_engine import nostr
from ninsei_engine.engine import CLICKS_PER_MIN, KIND_ROOM, REACTIONS, valid_edit
from test_audit_ui import CORE, ROOM as ROOM_JS, STYLE, fn, needs_node, run as run_js
from test_engine import quiet, read, run, setup_room, wait_for, world  # noqa: F401  (fixture)
from test_hostile import Key, ROOM, bare, settle  # noqa: F401  (fixture)

THUMB = REACTIONS[0]


def edit_ev(key, target, text, name="Zed", created_at=None, **extra):
    return key.person({"t": "edit", "target": target, "text": text, "name": name, **extra}, created_at=created_at)


def delete_ev(key, target, name="Zed", created_at=None, **extra):
    return key.person({"t": "delete", "target": target, "name": name, **extra}, created_at=created_at)


async def msg(e, key, text, name="Zed", tags=(), created_at=None, **extra):
    ev = key.person({"t": "msg", "text": text, "name": name, **extra}, tags=tags, created_at=created_at)
    await e._on_event(ev, "relay")
    return ev


def item(e, eid):
    return next(m for m in e.messages(ROOM) if m["id"] == eid)


def has(e, eid):
    return any(m["id"] == eid for m in e.messages(ROOM))


# ---- shapes and the engine calls ------------------------------------------------------------------------

def test_which_edits_and_deletes_are_well_formed():
    t = "a" * 64
    assert valid_edit({"t": "edit", "target": t, "text": "hi"})
    assert valid_edit({"t": "delete", "target": t})
    for bad in ({"t": "edit", "target": t}, {"t": "edit", "target": t, "text": "  "}, {"t": "edit", "target": t, "text": 5},
                {"t": "edit", "target": t.upper(), "text": "x"}, {"t": "delete", "target": [t]}, {"t": "delete"},
                {"t": "msg", "target": t, "text": "x"}):
        assert not valid_edit(bad)


async def test_an_edit_publishes_its_shape_and_the_item_shows_the_new_words(bare):
    e, _ = bare()
    first = await e.post(ROOM, "teh plan")
    sent = await e.edit(ROOM, first["id"], "  the plan  ")
    ev = e.events[ROOM][sent["id"]]
    c = json.loads(ev["content"])
    assert (c["t"], c["target"], c["text"]) == ("edit", first["id"], "the plan")
    assert ev["tags"] == [["h", ROOM]] and ev["pubkey"] == e._identity()["person_pk"]
    m = item(e, first["id"])
    assert m["text"] == "the plan" and m["edited"] is True and m["edited_at"] == ev["created_at"]
    assert not any(x["id"] == sent["id"] for x in e.messages(ROOM))        # never its own timeline item
    again = await e.edit(ROOM, first["id"], "the plan")                       # same words: nothing is sent
    assert again == {"ok": True, "unchanged": True}
    await settle(e)
    assert len([x for x in e.pool.sent if json.loads(x["content"])["t"] == "edit"]) == 1
    with pytest.raises(ValueError):
        await e.edit(ROOM, first["id"], "   ")
    await settle(e)


async def test_a_delete_publishes_the_room_event_and_a_nip09_request_from_the_same_key(bare):
    e, _ = bare()
    first = await e.post(ROOM, "oops")
    sent = await e.delete(ROOM, first["id"])
    await settle(e)
    c = json.loads(e.events[ROOM][sent["id"]]["content"])
    assert (c["t"], c["target"]) == ("delete", first["id"])
    req = next(x for x in e.pool.sent if x["kind"] == 5)
    assert req["tags"] == [["e", first["id"]], ["k", "4242"]] and req["pubkey"] == e._identity()["person_pk"]
    assert nostr.check_event(req)                                          # signed, id and all
    m = item(e, first["id"])
    assert m["deleted"] is True and m["text"] == "" and "edited" not in m and m["reply_to"] is None
    with pytest.raises(ValueError, match="already deleted"):
        await e.delete(ROOM, first["id"])
    with pytest.raises(ValueError, match="already deleted"):
        await e.edit(ROOM, first["id"], "back again")


async def test_only_my_own_person_messages_can_be_changed_and_only_chat_messages(bare):
    e, _ = bare()
    zed = Key("zed")
    theirs = await msg(e, zed, "not yours")
    await e._say(ROOM, "I am an agent line")
    mine_agent = next(m for m in e.messages(ROOM) if m["role"] == "agent" and m["t"] == "msg")
    join = zed.person({"t": "join", "name": "Zed"})
    await e._on_event(join, "relay")
    for target in (theirs["id"], mine_agent["id"], join["id"], "f" * 64, ["x"], None):
        with pytest.raises(ValueError):
            await e.edit(ROOM, target, "nope")
        with pytest.raises(ValueError):
            await e.delete(ROOM, target)
    with pytest.raises(ValueError):
        await e.edit("not-a-room", theirs["id"], "x")
    await settle(e)
    assert not [x for x in e.pool.sent if x["kind"] == 5 or json.loads(x["content"]).get("t") in ("edit", "delete")]


async def test_edits_and_deletes_share_the_click_pace(bare):
    e, _ = bare()
    first = await e.post(ROOM, "v0")
    for i in range(CLICKS_PER_MIN):
        await e.edit(ROOM, first["id"], f"v{i + 1}")
    with pytest.raises(ValueError, match="Slow down"):
        await e.edit(ROOM, first["id"], "one too many")
    with pytest.raises(ValueError, match="Slow down"):
        await e.delete(ROOM, first["id"])
    await settle(e)
    assert not [x for x in e.pool.sent if x["kind"] == 5]
    assert item(e, first["id"])["text"] == f"v{CLICKS_PER_MIN}"


# ---- who may change what, received over the wire ----------------------------------------------------------

async def test_someone_elses_edit_or_delete_of_a_message_is_ignored(bare):
    e, _ = bare()
    zed, bad = Key("zed"), Key("bad")
    said = await msg(e, zed, "mine, says Zed")
    await e._on_event(edit_ev(bad, said["id"], "hijacked", "Bad"), "relay")
    await e._on_event(delete_ev(bad, said["id"], "Bad"), "relay")
    m = item(e, said["id"])
    assert m["text"] == "mine, says Zed" and "edited" not in m and "deleted" not in m
    await e._on_event(edit_ev(zed, said["id"], "fixed by Zed"), "relay")      # the author can
    assert item(e, said["id"])["text"] == "fixed by Zed"
    await settle(e)


async def test_my_own_message_cannot_be_changed_by_a_stranger_even_by_my_own_agents_key_or_theirs(bare):
    e, _ = bare()
    mine = await e.post(ROOM, "keep this")
    stranger = Key("stranger")
    await e._on_event(edit_ev(stranger, mine["id"], "gone"), "relay")
    await e._on_event(delete_ev(stranger, mine["id"]), "relay")
    # an agent's own edit event: agents never edit or delete, so it is never stored
    stored = len(e.events[ROOM])
    await e._on_event(stranger.agent({"t": "edit", "target": mine["id"], "text": "x", "name": "Rex"}), "relay")
    await e._on_event(stranger.agent({"t": "delete", "target": mine["id"], "name": "Rex"}), "relay")
    assert len(e.events[ROOM]) == stored                                   # nothing from the agent was stored
    assert item(e, mine["id"])["text"] == "keep this"
    await settle(e)


async def test_an_agents_own_message_cannot_be_edited_or_deleted_even_by_its_owner(bare):
    e, _ = bare()
    stranger = Key("stranger")
    said = stranger.agent({"t": "msg", "text": "agent speaking", "name": "Rex"})
    await e._on_event(said, "relay")
    await e._on_event(edit_ev(stranger, said["id"], "owner rewrites the agent"), "relay")   # person key != agent key
    await e._on_event(stranger.agent({"t": "edit", "target": said["id"], "text": "self edit", "name": "Rex"}), "relay")
    await e._on_event(stranger.agent({"t": "delete", "target": said["id"], "name": "Rex"}), "relay")
    m = item(e, said["id"])
    assert m["text"] == "agent speaking" and "edited" not in m and "deleted" not in m
    await settle(e)


async def test_an_edit_of_something_that_is_not_a_chat_message_changes_nothing(bare):
    e, _ = bare()
    zed = Key("zed")
    join = zed.person({"t": "join", "name": "Zed"})
    await e._on_event(join, "relay")
    offer = Key("o").agent({"t": "offer", "title": "T", "pitch": "P", "topic": "x", "name": "Rex"})
    await e._on_event(offer, "relay")
    await e._on_event(edit_ev(zed, join["id"], "rewritten join"), "relay")
    await e._on_event(delete_ev(zed, join["id"]), "relay")
    await e._on_event(edit_ev(zed, "c" * 64, "no such target"), "relay")
    out = e.messages(ROOM)
    assert all("edited" not in m and "deleted" not in m for m in out)
    assert next(m for m in out if m["id"] == join["id"])["t"] == "join"
    json.dumps(out)
    await settle(e)


async def test_hostile_edits_and_deletes_are_dropped_before_they_are_stored(bare):
    e, _ = bare()
    zed = Key("zed")
    said = await msg(e, zed, "hi")
    stored = len(e.events[ROOM])
    t = said["id"]
    junk = [
        {"t": "edit", "target": t, "text": 5}, {"t": "edit", "target": t, "text": ["x"]}, {"t": "edit", "target": t},
        {"t": "edit", "target": t, "text": "   "}, {"t": "edit", "target": [t], "text": "x"},
        {"t": "edit", "target": t.upper(), "text": "x"}, {"t": "edit", "target": None, "text": None},
        {"t": "edit", "target": t, "text": "x" * 20000}, {"t": "delete", "target": 5},
        {"t": "delete", "target": {"id": t}}, {"t": "delete", "target": t, "pad": "x" * 20000}, {"t": "delete"},
    ]
    for c in junk:
        await e._on_event(zed.person(c), "relay")
    assert len(e.events[ROOM]) == stored
    m = item(e, said["id"])
    assert m["text"] == "hi" and "edited" not in m and "deleted" not in m
    await settle(e)


async def test_a_huge_edit_that_slips_under_the_size_cap_is_clipped_to_a_message(bare):
    e, _ = bare()
    zed = Key("zed")
    said = await msg(e, zed, "short")
    await e._on_event(edit_ev(zed, said["id"], "y" * 5000), "relay")
    assert item(e, said["id"])["text"] == "y" * 1200
    await settle(e)


async def test_the_latest_edit_wins_in_any_arrival_order_and_a_delete_beats_every_edit(bare):
    e, _ = bare()
    zed = Key("zed")
    now = int(time.time())
    said = await msg(e, zed, "v0", created_at=now - 10)
    for text, age in (("v3", 1), ("v1", 3), ("v2", 2)):                       # arrives newest first, then scrambled
        await e._on_event(edit_ev(zed, said["id"], text, created_at=now - age), "history")
    assert item(e, said["id"])["text"] == "v3"
    # an edit that arrives before its message still applies once the message is here
    early = zed.person({"t": "msg", "text": "late arrival", "name": "Zed"}, created_at=now - 20)
    await e._on_event(edit_ev(zed, early["id"], "edited first", created_at=now - 19), "history")
    await e._on_event(early, "history")
    assert item(e, early["id"])["text"] == "edited first"
    # a delete is final even when an older-looking edit shows up after it
    await e._on_event(delete_ev(zed, said["id"], created_at=now - 5), "history")
    await e._on_event(edit_ev(zed, said["id"], "v4", created_at=now - 1), "relay")
    m = item(e, said["id"])
    assert m["deleted"] is True and m["text"] == ""
    await settle(e)


async def test_hidden_people_cannot_edit_or_delete_and_hiding_rolls_back_their_changes(bare):
    e, _ = bare()
    zed = Key("zed")
    fan = Key("fan")
    said = await msg(e, fan, "original", name="Fan")
    await e.hide_person(zed.ppk, "Zed")
    await e._on_event(edit_ev(zed, said["id"], "from a hidden key"), "relay")
    assert zed.ppk not in [x["pubkey"] for x in e.events[ROOM].values()]
    assert item(e, said["id"])["text"] == "original"
    await settle(e)


# ---- through the views ------------------------------------------------------------------------------------

async def test_an_edit_claims_no_name_adds_no_member_and_wakes_no_agent(bare):
    e, llm = bare()
    e.save_settings({"chattiness": "normal"})
    zed, sneak = Key("zed"), Key("sneak")
    said = await msg(e, zed, "plain words", name="Zed")
    await settle(e)
    calls, members = list(llm.calls), [m["pk"] for m in e.members(ROOM)]
    await e._on_event(edit_ev(zed, said["id"], "Ada, what do you think about palette palette palette?", name="Fresh"), "relay")
    await e._on_event(edit_ev(sneak, said["id"], "x", name="Brand New"), "relay")
    await e._on_event(delete_ev(sneak, said["id"], name="Brand New"), "relay")
    await settle(e)
    assert llm.calls == calls                                              # nothing was asked of the model
    assert [m["pk"] for m in e.members(ROOM)] == members
    await msg(e, Key("later"), "taking it", name="Fresh")                  # "Fresh" was never claimed by an edit
    assert not [m for m in e.messages(ROOM) if m["text"] == "taking it"][0].get("impostor")
    # and the edited words do not count as naming the agent for floor priority
    assert e._allowed_prio(ROOM, said["id"], e._identity()["agent_pk"], None, 100) == 20


async def test_an_edit_never_adds_a_mention_badge_alert_or_highlight(bare):
    e, _ = bare()
    zed = Key("zed")
    said = await msg(e, zed, "hello there")
    before = e.snapshot()["rooms"][0]
    assert (before["unread"], before["mentions"]) == (1, 0) and "last_mention" not in before
    await e._on_event(edit_ev(zed, said["id"], "hello there @Maya"), "relay")
    after = e.snapshot()["rooms"][0]
    assert (after["unread"], after["mentions"]) == (1, 0) and "last_mention" not in after
    assert "mentions_me" not in item(e, said["id"])
    # a mention in the message as sent counts; editing it away removes the count and the alert
    pinged = await msg(e, zed, "ping @Maya")
    assert e.snapshot()["rooms"][0]["mentions"] == 1
    assert item(e, pinged["id"])["mentions_me"] is True
    await e._on_event(edit_ev(zed, pinged["id"], "ping nobody"), "relay")
    snap = e.snapshot()["rooms"][0]
    assert snap["mentions"] == 0 and "last_mention" not in snap
    assert "mentions_me" not in item(e, pinged["id"])
    # an edit that keeps the mention shows the new words in the alert, with the same id
    kept = await msg(e, zed, "@Maya first words")
    await e._on_event(edit_ev(zed, kept["id"], "@Maya second words"), "relay")
    lm = e.snapshot()["rooms"][0]["last_mention"]
    assert lm["id"] == kept["id"] and lm["text"] == "@Maya second words"
    await settle(e)


async def test_a_delete_takes_the_message_out_of_unread_and_mention_counts(bare):
    e, _ = bare()
    zed = Key("zed")
    pinged = await msg(e, zed, "hey @Maya")
    await msg(e, zed, "and another")
    assert e.snapshot()["rooms"][0]["mentions"] == 1 and e.snapshot()["rooms"][0]["unread"] == 2
    await e._on_event(delete_ev(zed, pinged["id"]), "relay")
    snap = e.snapshot()["rooms"][0]
    assert (snap["unread"], snap["mentions"]) == (1, 0) and "last_mention" not in snap
    await settle(e)


async def test_agent_transcripts_read_the_edited_text_and_drop_deleted_messages(bare):
    e, _ = bare()
    zed = Key("zed")
    now = int(time.time())
    a = await msg(e, zed, "first version", created_at=now - 30)
    b = await msg(e, zed, "to be taken back", created_at=now - 20)
    c = await msg(e, zed, "untouched", created_at=now - 10)
    await e._on_event(edit_ev(zed, a["id"], "second version"), "relay")
    await e._on_event(delete_ev(zed, b["id"]), "relay")
    texts = [ln.text for ln in e._transcript(ROOM)]
    assert texts == ["second version", "untouched"]
    assert e._line(ROOM, a).text == "second version"
    assert c
    await settle(e)


async def test_search_finds_the_new_words_never_the_old_and_never_a_deleted_message(bare):
    e, _ = bare()
    zed = Key("zed")
    now = int(time.time())
    a = await msg(e, zed, "alpha original", created_at=now - 30)
    b = await msg(e, zed, "bravo secret", created_at=now - 20)
    c = await msg(e, zed, "charlie stays", created_at=now - 10)
    await e._on_event(edit_ev(zed, a["id"], "alpha rewritten"), "relay")
    await e._on_event(delete_ev(zed, b["id"]), "relay")
    assert [h["id"] for h in e.search(ROOM, "rewritten")] == [a["id"]]
    assert e.search(ROOM, "original") == []
    assert e.search(ROOM, "secret") == [] and e.search(ROOM, "bravo") == []
    assert e.search(ROOM, "alpha")[0]["text"] == "alpha rewritten"
    ctx = [m["id"] for m in e.search_context(ROOM, c["id"])]
    assert ctx == [a["id"], c["id"]]                                       # the deleted one is no neighbour
    assert e.search_context(ROOM, b["id"]) == []
    await settle(e)


async def test_a_quote_follows_an_edit_and_says_deleted_for_a_deleted_message(bare):
    e, _ = bare()
    zed, fan = Key("zed"), Key("fan")
    said = await msg(e, zed, "the first wording")
    reply = await msg(e, fan, "re", name="Fan", tags=[["e", said["id"], "", "reply"]])
    await e._on_event(edit_ev(zed, said["id"], "the better wording"), "relay")
    assert item(e, reply["id"])["quote"]["text"] == "the better wording"
    await e._on_event(delete_ev(zed, said["id"]), "relay")
    assert item(e, reply["id"])["quote"] == {"deleted": True}              # never the words, never "missing"
    assert has(e, reply["id"])                                             # the reply itself stays
    # a deleted reply keeps nothing of what it answered
    await e._on_event(delete_ev(fan, reply["id"], "Fan"), "relay")
    gone = item(e, reply["id"])
    assert gone["deleted"] is True and "quote" not in gone and gone["reply_to"] is None
    await settle(e)


async def test_reactions_to_a_deleted_message_stay_with_it(bare):
    e, _ = bare()
    first = await e.post(ROOM, "react to me")
    fan = Key("fan")
    await e._on_event(fan.person({"t": "react", "target": first["id"], "emoji": THUMB, "on": True, "name": "Fan"}), "relay")
    await e.delete(ROOM, first["id"])
    m = item(e, first["id"])
    assert m["deleted"] is True and m["reactions"][0]["count"] == 1
    await settle(e)
    json.dumps(e.snapshot(ROOM))


async def test_an_edit_over_the_wire_reaches_the_other_client_and_a_delete_too(world):
    _, engines, _ = world
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    first = await run(maya, maya.post, room, "hello wrld")
    assert await wait_for(lambda: any(m["id"] == first["id"] for m in read(sam, sam.messages, room)))
    await run(maya, maya.edit, room, first["id"], "hello world")
    assert await wait_for(lambda: any(m["id"] == first["id"] and m.get("edited") and m["text"] == "hello world"
                                      for m in read(sam, sam.messages, room)))
    await run(maya, maya.delete, room, first["id"])
    assert await wait_for(lambda: any(m["id"] == first["id"] and m.get("deleted") for m in read(sam, sam.messages, room)))
    await quiet(maya, sam)


# ---- the UI half ------------------------------------------------------------------------------------------

def test_edit_and_delete_are_wired_into_the_bar_and_the_message():
    message = fn(ROOM_JS, "Message")
    assert "'/edit'" in message and "'/delete'" in message
    assert "MessageEditor" in message and "DeleteConfirm" in message and "MessageBody" in message
    assert "!agent && !m.deleted" in message                          # your own person messages only
    assert "Delete for everyone using Ninsei?" in fn(ROOM_JS, "DeleteConfirm")
    assert "Nostr can't take back what was published" in fn(ROOM_JS, "DeleteConfirm")
    for sel in (".h-edit", ".h-deleted-t", ".h-edited"):
        assert sel in STYLE, sel


@needs_node
def test_a_deleted_message_reads_message_deleted_and_an_edited_one_is_marked():
    js = fn(ROOM_JS, "MessageBody") + """
const fmtFull = ts => 'F' + ts
const gone = mount(MessageBody, { m: { id: 'a', text: '', deleted: true }, book: {} })
const edited = mount(MessageBody, { m: { id: 'b', text: 'new words', edited: true, edited_at: 7 }, book: {} })
const plain = mount(MessageBody, { m: { id: 'c', text: 'as sent' }, book: {} })
const body = (r, t) => find(r.tree, n => n.type === RichText && n.props.text === t)
function RichText() {}
const mark = find(edited.tree, n => n.props && n.props.className === 'h-edited')
out({ gone: text(gone.tree), hasEditedBody: !!body(edited, 'new words'), mark: mark && text(mark), title: mark && mark.props.title,
      plainMark: !!find(plain.tree, n => n.props && n.props.className === 'h-edited'), hasPlainBody: !!body(plain, 'as sent') })
"""
    r = run_js(js)
    assert r["gone"] == "Message deleted"
    assert r["hasEditedBody"] and "(edited)" in r["mark"] and "F7" in r["title"]
    assert r["plainMark"] is False and r["hasPlainBody"]


@needs_node
def test_the_editor_saves_with_enter_cancels_with_escape_and_the_delete_dialog_warns_first():
    js = fn(ROOM_JS, "MessageEditor") + fn(ROOM_JS, "DeleteConfirm") + """
function Modal() {}
const useLayoutEffect = useEffect
const posts = []; let cancelled = 0
const key = (k, shift) => ({ key: k, shiftKey: !!shift, nativeEvent: { isComposing: false }, preventDefault() {}, stopPropagation() {} })
const same = mount(MessageEditor, { text: 'old', onSave: async t => { posts.push('SAME:' + t) }, onCancel: () => { cancelled += 10 } })
find(same.tree, n => n.type === 'textarea').props.onKeyDown(key('Enter')); await settle()   // unchanged: just closes
const ed = mount(MessageEditor, { text: 'old', onSave: async t => { posts.push(t) }, onCancel: () => { cancelled++ } })
const area = () => find(ed.tree, n => n.type === 'textarea')
area().props.onChange({ target: { value: 'new text' } }); await settle()
area().props.onKeyDown(key('Enter', true)); await settle()        // shift+enter is a newline: nothing saved
const afterShift = posts.length
area().props.onKeyDown(key('Enter')); await settle()
area().props.onKeyDown(key('Escape')); await settle()
const dc = DeleteConfirm({ open: true, onConfirm() {}, onClose() {} })
out({ afterShift, posts, cancelled, title: dc.props.title, desc: dc.props.description, buttons: dc.props.footer.length })
"""
    r = run_js(js)
    assert r["afterShift"] == 0 and r["posts"] == ["new text"] and r["cancelled"] == 11   # Escape cancels; unchanged closes
    assert r["title"] == "Delete for everyone using Ninsei?"
    assert "Nostr can't take back what was published" in r["desc"] and r["buttons"] == 2
