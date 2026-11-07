"""Batch A, second half: the "New messages" line and Jump to latest, links and formatting, mention alerts,
and search in a room. Engine halves run on a bare engine and the API through TestClient; the UI halves run the
real functions under node (the harness in test_audit_ui)."""
import importlib.util
import inspect
import sys
import time
from pathlib import Path

import pytest

from ninsei_engine import engine as eng
from ninsei_engine.engine import SEARCH_CONTEXT
from test_audit_ui import APP, CORE, ROOM as ROOM_JS, STYLE, fn, needs_node, run as run_js
from test_engine import read, run, setup_room, wait_for, world  # noqa: F401  (fixture)
from test_hostile import Key, ROOM, bare, settle  # noqa: F401  (fixture)
from test_replies_reactions import msg


async def fill(e, n, who="zed", prefix="line", start=None):
    """n messages from one stranger, one second apart and oldest first."""
    key = Key(who)
    start = start or int(time.time()) - n - 5
    for i in range(n):
        await msg(e, key, f"{prefix} {i}", created_at=start + i)
    return key


# ---- snapshot: last_read and the newest unread mention ----------------------------------------------------

async def test_the_room_list_carries_last_read_and_the_newest_unread_mention(world):
    _, engines, _ = world
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    await run(sam, sam.post, room, "@maya first")
    await run(sam, sam.post, room, "@maya " + "x" * 200)
    assert await wait_for(lambda: sum(1 for m in read(maya, maya.messages, room) if m["text"].startswith("@maya")) >= 2)
    r = next(x for x in read(maya, maya.snapshot)["rooms"] if x["id"] == room)
    lm = r["last_mention"]
    assert r["mentions"] == 2 and lm["text"] == "@maya " + "x" * (eng.MENTION_SNIPPET - 6)   # the newest, cut to 60
    assert lm["name"] == "Sam" and isinstance(lm["id"], str) and isinstance(lm["ts"], int)
    assert isinstance(r["last_read"], int)
    read(maya, maya.snapshot, room)                                    # opening the room reads it
    r = next(x for x in read(maya, maya.snapshot)["rooms"] if x["id"] == room)
    assert r["mentions"] == 0 and "last_mention" not in r and r["last_read"] >= lm["ts"]


async def test_a_room_not_on_screen_is_loaded_without_being_marked_read(world):
    _, engines, _ = world
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    await run(sam, sam.post, room, "@maya look")
    assert await wait_for(lambda: any(m["text"] == "@maya look" for m in read(maya, maya.messages, room)))
    snap = read(maya, maya.snapshot, room, False)                      # mark=False: loaded, not read
    assert snap["room"]["id"] == room
    assert next(x for x in snap["rooms"] if x["id"] == room)["mentions"] == 1
    assert next(x for x in read(maya, maya.snapshot)["rooms"] if x["id"] == room)["mentions"] == 1
    read(maya, maya.snapshot, room)
    assert next(x for x in read(maya, maya.snapshot)["rooms"] if x["id"] == room)["mentions"] == 0


async def test_a_mention_from_a_lookalike_is_flagged_in_the_alert(bare):
    e, _ = bare()
    await msg(e, Key("real"), "hi all", name="Sam")                     # the first live key holds "Sam"
    await msg(e, Key("fake"), "@maya it's me", name="Sam")              # a second key under the same name
    lm = next(x for x in e.snapshot()["rooms"] if x["id"] == ROOM)["last_mention"]
    assert lm["name"] == "Sam" and lm["impostor"] is True
    await msg(e, Key("real"), "@maya the real one", name="Sam", created_at=int(time.time()) + 1)  # strictly newer
    lm = next(x for x in e.snapshot()["rooms"] if x["id"] == ROOM)["last_mention"]
    assert lm["text"] == "@maya the real one" and lm["impostor"] is False
    await settle(e)


async def test_a_mention_from_a_hostile_name_stays_a_short_clean_string(bare):
    e, _ = bare()
    zed = Key("zed")
    await msg(e, zed, "@maya hi", name="Z" * 500)
    r = next(x for x in e.snapshot()["rooms"] if x["id"] == ROOM)
    assert r["last_mention"]["name"] == "Z" * 32
    await settle(e)


# ---- search ---------------------------------------------------------------------------------------------

async def test_search_covers_every_stored_message_not_just_the_last_120(bare):
    e, _ = bare()
    await fill(e, 150)
    assert len(e.messages(ROOM)) == 120
    hits = e.search(ROOM, "line 3")
    assert [h["text"] for h in hits][:2] == ["line 39", "line 38"] or hits[0]["ts"] >= hits[-1]["ts"]
    assert {"id", "ts", "name", "role", "text"} <= set(hits[0]) and hits[0]["role"] == "person"
    assert [h["text"] for h in e.search(ROOM, "line 0")][-1] == "line 0"     # beyond the loaded 120
    assert len(e.search(ROOM, "line", limit=7)) == 7 and len(e.search(ROOM, "line")) == 50
    assert [h["ts"] for h in hits] == sorted((h["ts"] for h in hits), reverse=True)
    await settle(e)


async def test_search_ignores_case_and_accents_and_empty_or_odd_queries_return_nothing(bare):
    e, _ = bare()
    zed = Key("zed")
    await msg(e, zed, "Meet at the Café, ÉCOLE after", created_at=int(time.time()) - 5)
    assert len(e.search(ROOM, "cafe")) == 1 and len(e.search(ROOM, "CAFÉ")) == 1 and len(e.search(ROOM, "ecole")) == 1
    assert e.search(ROOM, "") == [] and e.search(ROOM, "   ") == [] and e.search("nope", "cafe") == []
    for odd in (None, 5, ["x"], {"a": 1}, "z" * 5000):
        assert e.search(ROOM, odd) == []
    for limit in (None, "x", -3, 10 ** 9, 0):
        assert len(e.search(ROOM, "cafe", limit)) == 1
    await settle(e)


async def test_search_never_returns_a_hidden_person_and_flags_lookalikes(bare):
    e, _ = bare()
    zed, gone = Key("zed"), Key("gone")
    await msg(e, zed, "needle one", name="Real", created_at=int(time.time()) - 30)
    await msg(e, gone, "needle two", name="Gone", created_at=int(time.time()) - 20)
    fake = Key("fake")
    await msg(e, fake, "needle three", name="Real", created_at=int(time.time()) - 10)   # wears Real's name
    got = {h["text"]: h for h in e.search(ROOM, "needle")}
    assert set(got) == {"needle one", "needle two", "needle three"}
    assert "impostor" in got["needle three"] and "impostor" not in got["needle one"]
    await e.hide_person(gone.ppk, "Gone")
    assert {h["text"] for h in e.search(ROOM, "needle")} == {"needle one", "needle three"}
    await settle(e)


async def test_search_context_returns_the_message_with_its_neighbours(bare):
    e, _ = bare()
    await fill(e, 20)
    target = next(h for h in e.search(ROOM, "line 10"))
    ctx = e.search_context(ROOM, target["id"])
    assert [m["text"] for m in ctx] == [f"line {i}" for i in range(10 - SEARCH_CONTEXT, 10 + SEARCH_CONTEXT + 1)]
    first = e.search_context(ROOM, e.search(ROOM, "line 0")[0]["id"])
    assert first[0]["text"] == "line 0" and len(first) == SEARCH_CONTEXT + 1
    for bad in ("nope", None, 5, {"a": 1}, ""):
        assert e.search_context(ROOM, bad) == []
    assert e.search_context("nope", target["id"]) == []
    await settle(e)


def test_the_search_routes_and_the_read_flag_are_declared_with_bounds():
    import ast
    src = (Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py").read_text()
    tree = ast.parse(src)
    fns = {n.name: n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)}
    def route(name):
        return next(d for d in fns[name].decorator_list if isinstance(d, ast.Call))
    assert ast.literal_eval(route("search").args[0]) == "/search" and route("search").func.attr == "get"
    assert ast.literal_eval(route("search_context").args[0]) == "/search/context" and route("search_context").func.attr == "get"
    assert "max_length=200" in src and "ge=1, le=100" in src
    assert "read: bool = True" in src and "eng.snapshot, room or None, read" in src


def _api(e):
    """The route module with its engine swapped for ours. (httpx isn't installed, so no TestClient: the route
    functions are awaited directly, and the query bounds are read off their signatures.)"""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    spec = importlib.util.spec_from_file_location("ninsei_plugin_api_a2", Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py")
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)

    async def engine():
        return e
    api._engine = engine
    return api


async def test_the_api_routes_search_bound_the_query_and_pass_read_through(world):
    pytest.importorskip("fastapi")
    _, engines, _ = world
    room = await setup_room(engines)
    maya, sam = engines["Maya"], engines["Sam"]
    await run(sam, sam.post, room, "@maya the marmalade plan")
    assert await wait_for(lambda: any("marmalade" in m["text"] for m in read(maya, maya.messages, room)))
    api = _api(maya)
    out = await api.search(room, "MARMALADE", 50)
    assert [x["text"] for x in out["results"]] == ["@maya the marmalade plan"]
    ctx = await api.search_context(room, out["results"][0]["id"])
    assert len(ctx["messages"]) >= 1
    params = {r.path: r for r in api.router.routes}
    q = inspect.signature(api.search).parameters
    assert any(getattr(m, "max_length", None) == 200 for m in q["q"].default.metadata)     # bounded
    assert any(getattr(m, "ge", None) == 1 for m in q["limit"].default.metadata) and any(getattr(m, "le", None) == 100 for m in q["limit"].default.metadata)
    assert "/search" in params and "/search/context" in params and params["/search"].methods == {"GET"}
    await api.state(room, False)                                          # read=0: loaded, still unread
    assert next(x for x in (await api.state("", True))["rooms"] if x["id"] == room)["mentions"] == 1
    await api.state(room, True)
    assert next(x for x in (await api.state("", True))["rooms"] if x["id"] == room)["mentions"] == 0


# ---- formatting and links (UI, node) ---------------------------------------------------------------------

RICH_FNS = ("squashName", "mentionNames", "mentionParts", "linkAt", "roomLinkAt", "emphasisCloses", "richInline", "richParts")


def rich_js():
    return "".join(fn(CORE, n) for n in RICH_FNS) + "const RICH_MAX_LINKS = 20\n"


@needs_node
def test_formatting_marks_compose_with_mentions_and_code_inside_one_scan():
    js = rich_js() + """
const names = [{ name: 'Maya', me: true }, { name: 'snake_bot', me: false }]
const toks = t => richParts(t, names)[0].tokens.map(x => [x.t, x.text, x.b ? 'b' : '', x.i ? 'i' : ''].join('|'))
out({
  basic: toks('**bold** and *it* and _it2_ `c*d*` x'),
  mixed: toks('hi @maya **look @snake_bot now** https://a.com/x_y_z. ok'),
  literal: toks('__init__ 2 * 3 * 4 snake_case_word **unclosed *it'),
  inCode: toks('`@maya **no**`'),
})
"""
    r = run_js(js)
    assert r["basic"] == ["text|bold|b|", "text| and ||", "text|it||i", "text| and ||", "text|it2||i", "text| ||", "code|c*d*||", "text| x||"]
    assert r["mixed"] == ["text|hi ||", "mention|@maya||", "text| ||", "text|look |b|", "mention|@snake_bot|b|", "text| now|b|",
                          "text| ||", "link|https://a.com/x_y_z||", "text|. ok||"]
    assert r["literal"] == ["text|__init__ 2 * 3 * 4 snake_case_word **unclosed *it||"]
    assert r["inCode"] == ["code|@maya **no**||"]


@needs_node
def test_only_plain_http_links_are_links_and_their_text_is_always_the_address():
    js = rich_js() + """
const links = t => richParts(t, []).flatMap(b => b.tokens || []).filter(x => x.t === 'link').map(x => x.text)
out({
  masked: links('[click here](https://evil.example/login)'),
  trailing: links('see https://a.com/x, or (https://b.com/y). Also https://c.com/p?q=1!'),
  wiki: links('(https://en.wikipedia.org/wiki/A_(b))'),
  bold: links('**https://a.com/x**'),
  userinfo: links('https://google.com@evil.example/ and https://user:pw@evil.example'),
  schemes: links('javascript:alert(1) data:text/html,x ftp://x.org file:///etc/passwd //evil.example www.evil.example mailto:a@b.c'),
  midword: links('xhttps://a.com'),
  bareHost: links('https:// and https://. and http://'),
  many: links(Array.from({ length: 30 }, (_, i) => 'https://a.com/' + i).join(' ')).length,
  long: links('https://a.com/' + 'a'.repeat(3000)).map(s => s.length),
})
"""
    r = run_js(js)
    assert r["masked"] == ["https://evil.example/login"]            # the words "click here" are not the link
    assert r["trailing"] == ["https://a.com/x", "https://b.com/y", "https://c.com/p?q=1"]
    assert r["wiki"] == ["https://en.wikipedia.org/wiki/A_(b)"] and r["bold"] == ["https://a.com/x"]
    assert r["userinfo"] == [] and r["schemes"] == [] and r["midword"] == [] and r["bareHost"] == []
    assert r["many"] == 20
    assert r["long"] == [2008]                                      # cut at 2000 characters after the scheme, not refused


@needs_node
def test_fenced_blocks_are_literal_and_unclosed_ones_stay_text():
    js = rich_js() + """
out({
  fenced: richParts('before\\n```js\\nlet a = **x** https://a.com @maya\\n```\\nafter', [{ name: 'Maya', me: true }]),
  unclosed: richParts('```never closed **b**', []),
  two: richParts('```a```mid```b```', []).map(b => b.kind),
  empty: richParts('', []), junk: richParts(null, null).length,
})
"""
    r = run_js(js)
    kinds = [b["kind"] for b in r["fenced"]]
    assert kinds == ["text", "pre", "text"]
    assert r["fenced"][1]["text"] == "let a = **x** https://a.com @maya"        # nothing inside is formatted or linked
    assert r["unclosed"][0]["kind"] == "text" and r["unclosed"][0]["tokens"][0]["text"].startswith("```never closed ")
    assert r["two"] == ["pre", "text", "pre"] and r["junk"] == 1


@needs_node
def test_rich_text_builds_nodes_never_markup_and_links_open_through_the_host():
    js = rich_js() + fn(ROOM_JS, "RichText") + fn(ROOM_JS, "richNode") + fn(ROOM_JS, "RichLink") + """
function useMemo(f) { return f() }
const opened = [], toasts = [], copied = []
globalThis.P = { openExternal: async url => { opened.push(url); return url.includes('fail') ? false : true },
                 toast: (k, m) => toasts.push([k, m]), copy: async t => copied.push(t) }
const book = { me: { name: 'Maya', you: true } }
const plain = RichText({ text: 'just words', book })
const html = RichText({ text: '<img src=x onerror=alert(1)> **b** <script>x</script>', book })
const root = mount(RichText, { text: 'go https://a.com/x and **bold @maya**, `code`\\n```\\nblock\\n```', book })
const tags = []
const walk = n => { if (!n || typeof n !== 'object') return; if (Array.isArray(n)) return n.forEach(walk); if (typeof n.type === 'string') tags.push(n.type); kids(n).forEach(walk) }
walk(root.tree)
const linkNode = find(root.tree, n => n.type === RichLink)
const lroot = mount(RichLink, linkNode.props)
const a = find(lroot.tree, n => n.type === 'a')
let prevented = 0
a.props.onClick({ preventDefault() { prevented++ } })
const bad = mount(RichLink, { href: 'https://fail.example/', text: 'https://fail.example/' })
find(bad.tree, n => n.type === 'a').props.onClick({ preventDefault() {} })
await settle()
delete globalThis.P.openExternal                      // the dashboard: a plain anchor opens its own tab
const dash = mount(RichLink, { href: 'https://a.com/', text: 'https://a.com/' })
let dashPrevented = 0
find(dash.tree, n => n.type === 'a').props.onClick({ preventDefault() { dashPrevented++ } })
out({ plain, htmlIsText: JSON.stringify(html).includes('<img src=x onerror=alert(1)>'), tags: [...new Set(tags)].sort(),
      a: { href: a.props.href, rel: a.props.rel, target: a.props.target, text: a.props.children }, opened, prevented, copied, toasts, dashPrevented })
"""
    r = run_js(js)
    assert r["plain"] == "just words"
    assert r["htmlIsText"] is True and "script" not in r["tags"] and "img" not in r["tags"]
    assert r["tags"] == ["code", "pre", "span", "strong"]      # links are RichLink elements, checked below
    assert r["a"] == {"href": "https://a.com/x", "rel": "noopener noreferrer", "target": "_blank", "text": "https://a.com/x"}
    assert r["opened"] == ["https://a.com/x", "https://fail.example/"] and r["prevented"] == 1
    assert r["copied"] == ["https://fail.example/"] and r["toasts"][0][0] == "error"      # a failed open copies the address
    assert r["dashPrevented"] == 0


def test_messages_use_the_one_renderer_and_offer_pitches_stay_plain():
    assert "jsx(RichText, { text: m.text, book: props.book })" in fn(ROOM_JS, "MessageBody") and "MessageBody" in fn(ROOM_JS, "Message")
    assert "MentionText" not in ROOM_JS
    for name in ("OfferCard", "ShareCard"):
        assert "RichText" not in fn(ROOM_JS, name)
    for sel in (".h-link{", ".h-code{", ".h-fence{", ".h-link:focus-visible"):
        assert sel in STYLE, sel


# ---- "New messages" and Jump to latest ----------------------------------------------------------------------

@needs_node
def test_the_new_line_goes_before_the_first_message_from_someone_else_after_last_read():
    js = fn(ROOM_JS, "groupItems") + fn(CORE, "dayKey") + """
const m = (id, ts, extra) => Object.assign({ id, ts, t: 'msg', pk: 'p' + id, text: id }, extra)
const line = (msgs, after) => groupItems(msgs, after).filter(i => i.kind !== 'day').map(i => i.kind === 'new' ? '--NEW--' : i.m ? i.m.id : i.kind)
const msgs = [m('a', 10), m('b', 20, { mine: true }), m('c', 30), m('d', 40)]
const first = groupItems(msgs, 15).find(i => i.m && i.m.id === 'c')
out({
  after15: line(msgs, 15),                   // b is mine and newer, so the line waits for c
  after40: line(msgs, 40), never: line(msgs, 0), undef: line(msgs, undefined),
  allNew: line([m('x', 50)], 5),
  joinsDontCount: line([{ id: 'j', ts: 50, t: 'join', name: 'Z' }, m('y', 60)], 5),
  firstHasHeader: first.first,
})
"""
    r = run_js(js)
    assert r["after15"] == ["a", "b", "--NEW--", "c", "d"]
    assert "--NEW--" not in r["after40"] and "--NEW--" not in r["never"] and "--NEW--" not in r["undef"]
    assert r["allNew"] == ["--NEW--", "x"] and r["joinsDontCount"] == ["joins", "--NEW--", "y"]
    assert r["firstHasHeader"] is True


TIMELINE_HOOKS = "".join(fn(ROOM_JS, n) for n in ("useEarlier", "useScrollKeeper", "EarlierButton")) + "".join(
    fn(CORE, n) for n in ("dayKey", "dayLabel", "fmtFull", "mergeOlder", "earlierState", "outboxSet", "useOutbox", "outboxSweep", "outboxItem", "errText", "errStatus")) + """
const EARLIER = new Map(), SCROLLED = new Map(), OUTBOX = new Map(), OUTBOX_FNS = new Set(), EARLIER_CAP = 1500
"""

TIMELINE_PRELUDE = """
function useMemo(f) { return f() }
const useLayoutEffect = useEffect
const useEnter = () => ({ current: null })
const PENDING_JUMP = { room: '', id: '', until: 0 }, JUMP_WATCH = new Set()
function EmptyState() {}
function TimelineItem() {}; function Thinking() {}
const springIntoView = () => {}; const flash = () => {}
const scrolled = []
function springScrollTo(el, to) { scrolled.push(to) }
globalThis.P = { toast() {} }
K.Icon = function Icon() {}
"""


@needs_node
def test_jump_to_latest_appears_after_a_screen_of_scroll_counts_new_messages_and_springs_down():
    js = fn(ROOM_JS, "groupItems") + fn(ROOM_JS, "Timeline") + fn(ROOM_JS, "JumpPill") + TIMELINE_PRELUDE + TIMELINE_HOOKS + """
const m = (id, ts, extra) => Object.assign({ id, ts, t: 'msg', pk: 'p', name: 'Zed', text: id }, extra)
const room = { id: 'r', messages: [m('a', 1), m('b', 2), m('c', 3)], members: [] }
const props = (r, after) => ({ store: {}, snap: {}, room: r, book: {}, newAfter: after })
const root = mount(Timeline, props(room, 0))
const scroll = () => find(root.tree, n => n.props && n.props.className === 'h-scroll')
const pill = () => find(root.tree, n => n.type === JumpPill)
const el = { scrollHeight: 3000, scrollTop: 2500, clientHeight: 500 }
scroll().props.ref.current = el
const atBottom = !pill()
el.scrollTop = 2400; scroll().props.onScroll(); await settle()          // 100 up: less than a screen
const nearBottom = !pill()
el.scrollTop = 1000; scroll().props.onScroll(); await settle()          // 1500 up: more than a screen
const shownEmpty = pill() && pill().props.count
root.update(props({ id: 'r', messages: [...room.messages, m('d', 4), m('e', 5, { t: 'join' }), m('f', 6)], members: [] }, 0))
await settle()
const counted = pill() && pill().props.count                            // d and f; a join is not a message
const pr = mount(JumpPill, pill().props)
const label = find(pr.tree, n => n.type === 'button').props['aria-label']
find(pr.tree, n => n.type === 'button').props.onClick()
root.update(root.props)
el.scrollTop = 2500; scroll().props.onScroll(); await settle()          // back near the bottom
out({ atBottom, nearBottom, shownEmpty, counted, label, scrolled, gone: !pill() })
"""
    r = run_js(js)
    assert r["atBottom"] and r["nearBottom"] and r["shownEmpty"] == 0
    assert r["counted"] == 2 and r["label"] == "Jump to latest, 2 new messages"
    assert r["scrolled"] == [2500] and r["gone"] is True                   # scrollHeight - clientHeight


def test_new_line_and_pill_styles_exist_and_the_room_remembers_last_read_until_it_is_left():
    for sel in (".h-newline{", ".h-jump{", ".h-jump-btn{", ".h-tlwrap{"):
        assert sel in STYLE, sel
    room_view = fn(ROOM_JS, "RoomView")
    assert "readMark" in room_view and "last_read" in room_view and "store.showing" in room_view
    assert "newAfter: readMark.current.ts" in room_view


@needs_node
def test_the_store_marks_a_room_read_only_while_it_is_shown_and_the_window_is_focused():
    js = fn(CORE, "createStore") + """
const paths = []
let focus = true
globalThis.document = { hasFocus: () => focus }
globalThis.P = { prefs: { get: (k, d) => (k === 'room' ? 'r1' : d), set() {} }, setTimeout: () => () => {}, rest: async p => { paths.push(p); return { rooms: [{ id: 'r1' }] } } }
const store = createStore()
await store.refresh()                                  // not shown yet: loaded, not read
const off = store.showing('r1'); await settle()        // shown: read
focus = false
await store.refresh()                                  // window in the background: not read
focus = true
const shownFocused = store.isShowing('r1')
off()
await store.refresh()                                  // left: not read
out({ paths, shownFocused, after: store.isShowing('r1') })
"""
    r = run_js(js)
    assert r["paths"] == ["/state?room=r1&read=0", "/state?room=r1", "/state?room=r1&read=0", "/state?room=r1&read=0"]
    assert r["shownFocused"] is True and r["after"] is False


# ---- mention alerts ---------------------------------------------------------------------------------------

@needs_node
def test_mention_alerts_fire_for_a_rise_in_a_room_you_are_not_looking_at_and_never_on_first_load():
    js = fn(CORE, "cleanSnippet") + fn(CORE, "mentionAlerts") + """
const toasts = [], os = []
globalThis.P = { toast: (k, m) => toasts.push([k, m]), osNotify: o => os.push(o) }
function nav() { return { set() {} } }
let listener = null, showing = false
const store = { subscribe: fn => { listener = fn; return () => { listener = null } }, isShowing: () => showing, setRoom() {} }
const off = mentionAlerts(store)
const snap = (mentions, lm, rooms) => ({ snap: { rooms: rooms || [{ id: 'r1', name: 'Shader club', mentions, last_mention: lm }] } })
const lm = (id, text) => ({ id, name: 'Sam', text, ts: 1 })
listener(snap(3, lm('e1', 'old @maya')))                      // first load: baseline only
const firstLoad = toasts.length
listener(snap(3, lm('e1', 'old @maya')))                      // no change
listener(snap(4, lm('e2', '@maya look\\n\\u202e at this ' + 'x'.repeat(100))))   // a rise, room not shown
const afterRise = toasts.slice()
listener(snap(4, lm('e2', 'again')))                          // same mention, not announced twice
showing = true
listener(snap(5, lm('e3', 'while looking')))                  // the room is on screen and focused: quiet
showing = false
listener(snap(0, undefined))                                  // read elsewhere: baseline drops
listener(snap(1, lm('e4', 'after a read')))
listener(snap(1, lm('e5', 'a new room'), [{ id: 'r1', name: 'Shader club', mentions: 1 }, { id: 'r2', name: 'Fresh', mentions: 2, last_mention: lm('e9', 'x') }]))
off()
out({ firstLoad, afterRise, total: toasts.length, os: os.map(o => [o.title, o.body.length, typeof o.onActivate]), stopped: listener === null })
"""
    r = run_js(js)
    assert r["firstLoad"] == 0 and r["stopped"] is True
    kind, text = r["afterRise"][0]
    assert kind == "info" and r["afterRise"] and len(r["afterRise"]) == 1
    assert text.startswith('Sam mentioned you in Shader club: "@maya look ') and text.endswith('"')
    assert "\n" not in text and "\u202e" not in text
    assert r["total"] == 2                                       # the rise, then the one after a read; a joined room is only a baseline
    assert r["os"][0][0] == "Sam mentioned you in Shader club" and r["os"][0][1] <= 60 and r["os"][0][2] == "function"


def test_alerts_are_installed_on_both_platforms_and_desktop_uses_the_hosts_notification_door():
    tail = (importlib_path("ui/platform/desktop_tail.js"))
    assert "mentionAlerts(store)" in tail and "ctx.os.notify" in tail and "ctx.os.openExternal" in tail
    assert "mentionAlerts(store)" in importlib_path("ui/platform/dashboard_tail.js")


def importlib_path(rel):
    return (Path(__file__).resolve().parents[1] / rel).read_text()


# ---- search UI ---------------------------------------------------------------------------------------------

@needs_node
def test_search_matches_without_case_or_accents_and_maps_back_to_the_original_text():
    js = fn(CORE, "foldText") + fn(CORE, "matchRanges") + """
out({ a: matchRanges('Café au lait CAFE', 'cafe'), b: matchRanges('naïve Naive', 'NAIVE', 5), c: matchRanges('x', ''), d: matchRanges('aaaa', 'aa'),
      e: matchRanges('😀 hi 😀', 'hi'), f: matchRanges(null, 'a'), g: matchRanges('abc', null) })
"""
    r = run_js(js)
    assert r["a"] == [{"start": 0, "end": 4}, {"start": 13, "end": 17}]
    assert r["b"] == [{"start": 0, "end": 5}, {"start": 6, "end": 11}]
    assert r["c"] == [] and r["d"] == [{"start": 0, "end": 2}, {"start": 2, "end": 4}]
    assert r["e"] == [{"start": 3, "end": 5}] and r["f"] == [] and r["g"] == []


@needs_node
def test_the_search_panel_queries_moves_with_arrows_opens_loaded_results_and_shows_others_in_context():
    js = fn(CORE, "foldText") + fn(CORE, "matchRanges") + fn(CORE, "errText") + fn(CORE, "errStatus") + fn(CORE, "dayKey") + fn(CORE, "dayLabel") + fn(CORE, "fmtFull") + fn(ROOM_JS, "SearchPanel") + fn(ROOM_JS, "SearchRow") + """
function useMemo(f) { return f() }
const useEnter = () => ({ current: null })
function ImpostorChip() {}; const fmtWhen = () => 'now'
K.Button = function Button() {}
const asked = [], picked = []
globalThis.document = { getElementById: () => null }
const result = (id, text) => ({ id, ts: 1, name: 'Zed', role: 'person', text })
globalThis.P = { setTimeout: (f, ms) => { const t = setTimeout(f, 0); return () => clearTimeout(t) },
  rest: async p => { asked.push(p); if (p.startsWith('/search/context')) return { messages: [result('x0', 'before'), result('x1', 'the needle here'), result('x2', 'after')] }
    return { results: [result('x1', 'the needle here'), result('y1', 'Another NEEDLE')] } } }
let closed = 0
const loaded = new Set(['x1'])
const root = mount(SearchPanel, { room: { id: 'r1' }, onClose: () => { closed++ }, onPick: id => { picked.push(id); return loaded.has(id) } })
const input = () => find(root.tree, n => n.type === 'input')
const key = k => ({ key: k, nativeEvent: { isComposing: false }, preventDefault() {}, stopPropagation() {} })
input().props.onChange({ target: { value: 'needle' } }); await settle()
const rows = () => [].concat((find(root.tree, n => n.props && n.props.role === 'listbox') || { props: { children: [] } }).props.children).filter(r => r && r.type === SearchRow)
const marks = find(mount(SearchRow, rows()[0].props).tree, n => n.type === 'mark')
root.update(root.props)          // mount() points the harness's setters at the newest root: point them back
const nResults = rows().length
const active0 = input().props['aria-activedescendant']
input().props.onKeyDown(key('ArrowDown')); await settle()
const active1 = input().props['aria-activedescendant']
input().props.onKeyDown(key('Enter')); await settle()                 // y1 is not loaded: shown in context
const ctxRows = () => [].concat((find(root.tree, n => n.props && n.props.className === 'h-search-ctx') || { props: { children: [] } }).props.children).flat().filter(r => r && r.type === SearchRow)
const inContext = ctxRows().length
input().props.onKeyDown(key('Escape')); await settle()                // back to the results
const afterEsc = [closed, !!find(root.tree, n => n.props && n.props.role === 'listbox')]
input().props.onKeyDown(key('ArrowUp')); await settle(); input().props.onKeyDown(key('Enter')); await settle()   // x1 is loaded: closes
input().props.onKeyDown(key('Escape')); await settle()
out({ asked, picked, nResults, active0, active1, marked: marks && marks.props.children, inContext, afterEsc, closed })
"""
    r = run_js(js)
    assert r["asked"][0] == "/search?room=r1&q=needle&limit=50"
    assert r["asked"][1].startswith("/search/context?room=r1&id=y1")
    assert r["nResults"] == 2 and r["active0"] == "h-sr-0" and r["active1"] == "h-sr-1"
    assert r["marked"] == "needle"
    assert r["picked"] == ["y1", "x1"] and r["inContext"] == 3          # the 3 messages around it
    assert r["afterEsc"] == [0, True]                                    # Escape left the context view, not the panel
    assert r["closed"] == 2                                              # the loaded pick, then Escape


def test_search_is_wired_into_the_header_with_a_labelled_button_and_styles():
    header = fn(ROOM_JS, "RoomHeader")
    assert "'aria-label': 'Search this room'" in header and "name: 'search'" in header
    assert "SearchPanel" in fn(ROOM_JS, "RoomView") and "jumpRef" in fn(ROOM_JS, "RoomView")
    dash = importlib_path("ui/platform/dashboard_tail.js")
    assert "    search: '" in dash and "    'arrow-down': '" in dash
    for sel in (".h-search{", ".h-search-in{", ".h-sr{", ".h-mark{"):
        assert sel in STYLE, sel
