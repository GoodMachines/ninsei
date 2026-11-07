"""Mentions, Discord style: '@' plus a name in any case or spacing, highlighted, counted per room, offered
by autocomplete. And an owner alone in a room gets an answer from their agent without having to ask."""
import pytest

from ninsei_engine import engine as eng
from ninsei_engine.engine import at_mentions
from test_audit_ui import APP, CORE, ROOM, STYLE, fn, needs_node, run as run_js
from test_engine import read, run, quiet, setup_room, wait_for, world  # noqa: F401  (fixture)


@pytest.mark.parametrize("text,name,hit", [
    ("@mrs.blobby hello", "Mrs. Blobby", True),       # the one that failed live: dots and no space
    ("@MrsBlobby hi", "Mrs. Blobby", True),
    ("@mrs. blobby are you there", "Mrs. Blobby", True),
    ("hey @Mrs. Blobby.", "Mrs. Blobby", True),
    ("@Adam hi", "Ada", False),                         # a longer name isn't a mention of a shorter one
    ("mail me at x@ada.com", "Ada", False),             # an '@' inside a word is not a mention
    ("Mrs. Blobby without the at", "Mrs. Blobby", False),
    ("@", "Ada", False),
    ("@ada", "", False),
])
def test_at_mentions_ignore_case_dots_and_spaces(text, name, hit):
    assert at_mentions(text, name) is hit


async def test_an_at_with_different_spelling_reaches_the_agent_and_flags_its_owner(world):
    _, engines, llms = world
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    maya.save_settings({"agent_name": "Mrs. Blobby"})
    await run(sam, sam.post, room, "@mrs.blobby what do you think?")
    assert await wait_for(lambda: "ninsei.reply" in llms["Maya"].calls)
    await quiet(maya, sam)
    assert "ninsei.reply" not in llms["Sam"].calls       # Bo wasn't named and chattiness is quiet
    mine = [m for m in read(maya, maya.messages, room) if m["text"].startswith("@mrs.blobby")]
    assert mine and mine[0]["mentions_me"] is True        # Maya sees it as aimed at her side
    theirs = [m for m in read(sam, sam.messages, room) if m["text"].startswith("@mrs.blobby")]
    assert theirs and "mentions_me" not in theirs[0]       # never your own message


async def test_room_list_counts_unread_mentions_of_you(world):
    _, engines, _ = world
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    await run(sam, sam.post, room, "@maya look at this")
    await run(sam, sam.post, room, "and something for everyone")
    assert await wait_for(lambda: sum(1 for m in read(maya, maya.messages, room) if m["pk"] == read(sam, sam._identity)["person_pk"]) >= 2)
    snap = read(maya, maya.snapshot)                        # no room open, so nothing gets marked read
    r = next(x for x in snap["rooms"] if x["id"] == room)
    assert r["mentions"] == 1 and r["unread"] >= 1  # unread compares whole seconds with the read mark
    read(maya, maya.snapshot, room)                         # opening the room reads it
    assert next(x for x in read(maya, maya.snapshot)["rooms"] if x["id"] == room)["mentions"] == 0


async def test_owner_alone_in_a_room_gets_an_answer_without_a_question(world):
    _, engines, llms = world
    maya = engines["Maya"]
    maya.save_settings({"chattiness": "normal"})
    meta = await run(maya, maya.create_room, "just me", "", [])
    await run(maya, maya.post, meta["id"], "Hello!")
    assert await wait_for(lambda: "ninsei.reply" in llms["Maya"].calls)


async def test_with_someone_else_here_a_plain_hello_is_left_to_chance(world, monkeypatch):
    _, engines, llms = world
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    maya.save_settings({"chattiness": "normal"})
    monkeypatch.setattr(eng.random, "random", lambda: 0.999)   # the chatty roll never fires
    sam_pk = read(sam, sam._identity)["person_pk"]
    assert await wait_for(lambda: read(maya, maya._others_here, room)), "Bo's beat never reached Maya"
    await run(maya, maya.post, room, "Hello!")
    await quiet(maya, sam)
    assert "ninsei.reply" not in llms["Maya"].calls
    assert sam_pk  # Sam is the someone else


# ---- the UI half, run under node ------------------------------------------------------------------

MENTION_JS = lambda: "".join(fn(CORE, n) for n in ("squashName", "mentionNames", "mentionParts", "mentionQuery", "mentionMatches"))


@needs_node
def test_parts_split_out_mentions_longest_name_first_and_mark_yours():
    js = MENTION_JS() + """
const names = [{ name: 'Ada', me: false }, { name: 'Ada Lovelace', me: false }, { name: 'Mrs. Blobby', me: true }]
out([
  mentionParts('@mrs.blobby hi @Ada Lovelace and @adam, x@ada.com', names),
  mentionParts('no mentions here', names),
  mentionParts('', names),
])
"""
    parts, none, empty = run_js(js)
    assert [p for p in parts if p.get("name")] == [
        {"text": "@mrs.blobby", "name": "Mrs. Blobby", "me": True},
        {"text": "@Ada Lovelace", "name": "Ada Lovelace", "me": False}]
    assert "".join(p["text"] for p in parts) == "@mrs.blobby hi @Ada Lovelace and @adam, x@ada.com"
    assert none == [{"text": "no mentions here"}] and empty == [{"text": ""}]


@needs_node
def test_query_finds_the_at_being_typed_and_matches_by_name_or_word():
    js = MENTION_JS() + """
const c = [{ name: 'Mrs. Blobby' }, { name: 'Maya' }, { name: 'Bo' }]
out([
  mentionQuery('hi @mr', 6), mentionQuery('hi @mrs. bl', 11), mentionQuery('mail x@y', 8), mentionQuery('@a\\nb', 4),
  mentionMatches(c, 'm').map(x => x.name), mentionMatches(c, 'mrs.b').map(x => x.name),
  mentionMatches(c, 'blob').map(x => x.name), mentionMatches(c, '').length,
])
"""
    q1, q2, q3, q4, m, mb, blob, everyone = run_js(js)
    assert q1 == {"at": 3, "q": "mr"} and q2 == {"at": 3, "q": "mrs. bl"}
    assert q3 is None and q4 is None
    assert m == ["Mrs. Blobby", "Maya"] and mb == ["Mrs. Blobby"] and blob == ["Mrs. Blobby"] and everyone == 3


@needs_node
def test_composer_offers_room_members_and_enter_inserts_the_full_name():
    js = MENTION_JS() + fn(ROOM, "mentionCandidates") + fn(ROOM, "Composer") + """
function useMemo(f) { return f() }
const useLayoutEffect = useEffect
function Face() {}; function Initial() {}; function GamesMenu() {}; function gameName(m) { return m }
const K2 = K; K2.Tip = function Tip() {}
const posts = []
const store = { post: async (p, b) => { posts.push(b) } }
const room = { id: 'r1', name: 'club', members: [
  { pk: 'me', name: 'Justin', you: true, online: true, agents: [{ pk: 'ag', name: 'Mrs. Blobby', yours: true, face: {} }] },
  { pk: 'w', name: 'Maya', online: true, agents: [{ pk: 'wa', name: 'Ada', face: {} }] },
  { pk: 'x', name: 'Maya', impostor: true, online: true, agents: [] }] }
const root = mount(Composer, { store, room, gameOn: false })
const area = () => find(root.tree, n => n.type === 'textarea')
const ev = (value, caret) => ({ target: { value, selectionStart: caret } })
const key = k => ({ key: k, shiftKey: false, nativeEvent: { isComposing: false }, preventDefault() {}, stopPropagation() {} })
area().props.onChange(ev('hey @', 5)); await settle()
const all = find(root.tree, n => n.props && n.props.role === 'listbox')
const listed = all ? kids(all).map(o => text(o)) : null
area().props.onChange(ev('hey @mrs', 8)); await settle()
area().props.onKeyDown(key('Enter')); await settle()
const after = area().props.value
area().props.onKeyDown(key('Enter')); await settle()
out({ listed, after, expanded: area().props['aria-expanded'], posts })
"""
    res = run_js(js)
    # your agent first, then who's here; never you, never the lookalike Maya
    assert res["listed"] == ["Mrs. Blobbyyour agent", "AdaMaya’s agent", "Mayahere now"]
    assert res["after"] == "hey @Mrs. Blobby "
    assert res["expanded"] is False
    assert res["posts"] == [{"room": "r1", "text": "hey @Mrs. Blobby"}]   # the next Enter sends


def test_mentions_are_drawn_highlighted_and_badged():
    assert "'data-mentioned': !!m.mentions_me" in fn(ROOM, "Message")
    assert "jsx(RichText, { text: m.text, book: props.book })" in fn(ROOM, "MessageBody") and "MessageBody" in fn(ROOM, "Message")
    assert "r.mentions > 0" in APP and "h-mentions" in APP
    for sel in (".h-at{", ".h-at[data-me=true]", ".h-msg[data-mentioned=true]", ".h-navrow .h-mentions", ".h-ac{", ".h-ac-opt[aria-selected=true]"):
        assert sel in STYLE, sel


def test_an_alert_from_a_lookalike_never_names_them_as_the_real_person():
    alerts = fn(CORE, "mentionAlerts")
    assert "(lm.impostor ? 'Someone calling themselves ' : '')" in alerts
