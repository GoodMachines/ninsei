"""The page side of starting the agent from a Hermes profile, run under node with the shared hooks harness: the
picker renders the list, picking fills the name and the personality, flags and the count render, and nothing is
posted to /settings before Save."""
from test_audit_ui import CORE, PARTS, SETUP, STYLE, block, const, fn, needs_node, run
from test_audit_review import SETTINGS_JS

PICKER_JS = (const(PARTS, "PERSONA_MAX") + block(PARTS, "FLAG_LABEL") + fn(PARTS, "flagLine") + fn(PARTS, "liveFlags")
             + fn(PARTS, "hermesSub") + fn(PARTS, "HermesPicker") + fn(PARTS, "applyProposal") + fn(PARTS, "PersonaField") + fn(CORE, "errText") + """
K.Input = function Input() {}
const toasts = []
const PROFILES = [
  { name: 'default', display_name: '', description: '', has_personality: true, current: false, is_default: true },
  { name: 'archivist', display_name: 'Archie the Keeper', description: 'Keeps an eye on things', has_personality: true, current: true, is_default: false },
  { name: 'notes-bot', display_name: '', description: '', has_personality: false, current: false, is_default: false }
]
const PROPOSAL = { source: 'archivist', agent_name: 'Archie the Keeper', persona: 'You are Archie. Mail a@b.co or see ~/vault.', truncated: true,
  flags: [{ kind: 'email', text: 'a@b.co' }, { kind: 'home_path', text: '~/vault.' }] }
function setupRest(list, proposal) {
  const calls = []
  globalThis.P = { rest: async (path, opts) => { calls.push([path, opts]); if (path === '/profiles/hermes') { if (list === null) throw new Error('no'); return { profiles: list } }
    if (path.startsWith('/profiles/hermes/import')) return proposal; throw new Error('unexpected ' + path) },
    toast: (kind, msg) => toasts.push([kind, msg]) }
  return calls
}
""")


@needs_node
def test_the_picker_lists_profiles_marks_this_one_and_hides_when_there_are_none():
    r = run(PICKER_JS + """
setupRest(PROFILES, PROPOSAL)
const root = mount(HermesPicker, { onPick: () => {} })
await settle()
const items = []
;(function walk(n) { if (!n || typeof n !== 'object') return; if (Array.isArray(n)) return n.forEach(walk); if (n.type === 'button') items.push(n); kids(n).forEach(walk) })(root.tree)
const empty = (setupRest([], null), mount(HermesPicker, { onPick: () => {} })); await settle()
const failed = (setupRest(null, null), mount(HermesPicker, { onPick: () => {} })); await settle()
out({ label: text(root.tree).includes('Start from one of your Hermes agents'), n: items.length, texts: items.map(text),
      here: items.filter(b => b.props['data-here']).map(text), titles: items.map(b => b.props.title), tree: empty.tree, failedTree: failed.tree,
      hint: text(root.tree).includes('Nothing is saved until you press Save') })
""")
    assert r["label"] and r["n"] == 3 and r["hint"]
    assert r["texts"][0] == "Archie the Watcherthis oneKeeps an eye on things"      # the profile in use leads the row
    assert r["texts"][1] == "default" and r["texts"][2] == "bookmark-botNo personality set"
    assert r["here"] == [r["texts"][0]]
    assert r["tree"] is None and r["failedTree"] is None          # no profiles, or the list failed: the row is simply not there


@needs_node
def test_picking_reads_the_proposal_once_and_posts_nothing():
    r = run(PICKER_JS + """
const calls = setupRest(PROFILES, PROPOSAL)
const picked = []
const root = mount(HermesPicker, { onPick: p => picked.push(p) })
await settle()
const archivist = find(root.tree, n => n.type === 'button' && text(n).includes('Archie'))
await archivist.props.onClick()
await settle()
out({ calls: calls.map(c => [c[0], (c[1] || {}).method || 'GET']), picked })
""")
    assert r["calls"] == [["/profiles/hermes", "GET"], ["/profiles/hermes/import?name=archivist", "GET"]]
    assert r["picked"][0]["agent_name"] == "Archie the Keeper"


@needs_node
def test_the_personality_box_warns_counts_lists_flags_and_says_when_it_was_cut():
    r = run(PICKER_JS + """
const changes = []
const pick = { flags: PROPOSAL.flags, truncated: true, open: true }
const root = mount(PersonaField, { id: 'p', value: PROPOSAL.persona, source: 'archivist', pick, setPick: () => {}, onChange: c => changes.push(c) })
const t = text(root.tree)
const ta = find(root.tree, n => n.type === 'textarea')
ta.props.onChange({ target: { value: 'new text' } })
const flagsAfter = text(mount(PersonaField, { id: 'p', value: 'You are Archie.', source: 'archivist', pick, setPick: () => {}, onChange: () => {} }).tree)
out({ t, max: ta.props.maxLength, changes, flagsAfter })
""")
    t = r["t"]
    assert "Personality · from archivist" in t
    assert "Your agent uses this in every room it’s in, and people there could get it to repeat it. Remove anything private." in t
    assert "Looks like an email: a@b.co" in t and "Looks like a path on your computer: ~/vault." in t
    assert "42 / 1,500" in t and "Cut to 1,500 characters" in t
    assert r["max"] == 1500 and r["changes"] == [{"persona": "new text"}]
    assert "Looks like" not in r["flagsAfter"]                   # the text was removed from the box, so its warning goes


@needs_node
def test_the_box_is_closed_and_optional_until_asked_for_and_a_saved_one_shows_edit_and_remove():
    r = run(PICKER_JS + """
const sets = [], changes = []
const none = mount(PersonaField, { id: 'p', value: '', source: '', pick: { open: false }, setPick: p => sets.push(p), onChange: c => changes.push(c) })
const closedText = text(none.tree), hasTa = !!find(none.tree, n => n.type === 'textarea')
button(none.tree, 'Add a personality').props.onClick()
const set = mount(PersonaField, { id: 'p', value: 'Likes owls.', source: 'archivist', pick: { open: false }, setPick: p => sets.push(p), onChange: c => changes.push(c) })
const setText = text(set.tree)
button(set.tree, 'Edit').props.onClick()
button(set.tree, 'Remove').props.onClick()
out({ closedText, hasTa, setText, sets, changes })
""")
    assert r["closedText"] == "Add a personality (optional)" and not r["hasTa"]
    assert "Personality · from archivist" in r["setText"] and "Likes owls." in r["setText"]
    assert r["sets"][0]["open"] is True and r["sets"][1]["open"] is True
    assert r["sets"][2] == {"flags": [], "truncated": False, "open": False}
    assert r["changes"] == [{"persona": "", "persona_source": ""}]


ONBOARD_JS = lambda: (PICKER_JS + fn(SETUP, "Onboarding") + fn(SETUP, "setupNeeds") + fn(SETUP, "capFirst") + fn(SETUP, "budgetOption") + fn(SETUP, "budgetOptions")
                      + fn(CORE, "repliesFor") + fn(CORE, "repliesWords") + fn(CORE, "repliesLeftWords") + const(CORE, "REPLY_TOKENS_GUESS") + """
function Field() {}; function Seg() {}; function VibePresets() {}; function IdCard() {}; function FacePicker() {}; function Face() {}; const AWAY_CHOICES = []; const OTHERS_SPENT = ''; function othersLine() { return '' }
function InterestInput() {}; function Notice() {}; function PersonLook() {}; const cleanAvatar = a => a || null
const faceFor = f => f || {}; const fmtTokens = n => String(n); const BUDGET_PRESETS = [40000]
const nav = () => ({ set() {} })
function snap() {
  return { me: { pk: 'p', agent: { pk: 'a' } }, settings: { display_name: 'Maya', agent_name: '', vibe: 'warm', face: {}, interests: [], budget_daily: 40000 } }
}
""")


@needs_node
def test_onboarding_picking_fills_the_name_and_personality_and_saves_only_on_continue():
    r = run(ONBOARD_JS() + """
setupRest(PROFILES, PROPOSAL)
const posts = []
const store = { post: async (path, body) => { posts.push([path, body]); return {} } }
const root = mount(Onboarding, { store, snap: snap() })
const picker = find(root.tree, n => n.type === HermesPicker)
picker.props.onPick(PROPOSAL)
await settle()
const nameField = find(root.tree, n => n.type === K.Input && n.props.id === 'h-on-agent')
const box = find(root.tree, n => n.type === PersonaField)
const before = posts.length
await button(root.tree, 'Bring').props.onClick()
await settle()
out({ name: nameField.props.value, persona: box.props.value, source: box.props.source, open: box.props.pick.open, flags: box.props.pick.flags.length,
      cut: box.props.pick.truncated, before, posts })
""")
    assert r["name"] == "Archie the Keeper" and r["persona"].startswith("You are Archie.") and r["source"] == "archivist"
    assert r["open"] is True and r["flags"] == 2 and r["cut"] is True
    assert r["before"] == 0, "picking a profile must not post anything"
    assert [p[0] for p in r["posts"]] == ["/settings"]
    body = r["posts"][0][1]
    assert body["persona"].startswith("You are Archie.") and body["persona_source"] == "archivist" and body["agent_name"] == "Archie the Keeper"
    assert "pick" not in body and "flags" not in body and body["onboarded"] is True


@needs_node
def test_onboarding_without_a_pick_has_a_closed_optional_box_and_the_vibe_still_works():
    r = run(ONBOARD_JS() + """
setupRest(PROFILES, PROPOSAL)
const posts = []
const store = { post: async (path, body) => { posts.push(body); return {} } }
const root = mount(Onboarding, { store, snap: snap() })
const box = find(root.tree, n => n.type === PersonaField)
const vibe = find(root.tree, n => n.type === VibePresets)
vibe.props.onPick('dry wit')
await settle()
find(root.tree, n => n.type === K.Input && n.props.id === 'h-on-agent').props.onChange({ target: { value: 'Ada' } })
await settle()
await button(root.tree, 'Bring').props.onClick()
await settle()
out({ open: box.props.pick.open, value: box.props.value, posted: posts })
""")
    assert r["open"] is False and r["value"] == ""
    assert r["posted"][0]["vibe"] == "dry wit" and r["posted"][0]["persona"] == "" and r["posted"][0]["agent_name"] == "Ada"


@needs_node
def test_picking_a_profile_without_a_personality_fills_only_the_name():
    r = run(ONBOARD_JS() + """
setupRest(PROFILES, PROPOSAL)
const store = { post: async () => ({}) }
const root = mount(Onboarding, { store, snap: snap() })
find(root.tree, n => n.type === HermesPicker).props.onPick({ source: 'notes-bot', agent_name: 'Notes Bot', persona: '', truncated: false, flags: [] })
await settle()
const box = find(root.tree, n => n.type === PersonaField)
out({ name: find(root.tree, n => n.type === K.Input && n.props.id === 'h-on-agent').props.value, open: box.props.pick.open, persona: box.props.value, toasts })
""")
    assert r["name"] == "Notes Bot" and r["open"] is False and r["persona"] == ""
    assert r["toasts"] and "only its name" in r["toasts"][0][1]


@needs_node
def test_settings_pick_changes_nothing_until_save_and_the_save_carries_the_text_and_shows_flags():
    r = run(SETTINGS_JS() + PICKER_JS + """
setupRest(PROFILES, PROPOSAL)
const posts = []
const store = { post: async (path, body) => { posts.push([path, body]); return { flags: [{ kind: 'email', text: 'a@b.co' }] } } }
const root = mount(SettingsForm, { store, snap: snapWith(['wss://relay.example']) })
find(root.tree, n => n.type === HermesPicker).props.onPick(PROPOSAL)
await settle()
const dirty = !!button(root.tree, 'Save changes') && !button(root.tree, 'Save changes').props.disabled
const before = posts.length
await button(root.tree, 'Save changes').props.onClick()
await settle()
const box = find(root.tree, n => n.type === PersonaField)
out({ before, dirty, posts, flags: box.props.pick.flags, value: box.props.value })
""")
    assert r["before"] == 0 and r["dirty"]
    assert len(r["posts"]) == 1 and r["posts"][0][0] == "/settings"
    b = r["posts"][0][1]
    assert b["persona"].startswith("You are Archie.") and b["persona_source"] == "archivist" and b["agent_name"] == "Archie the Keeper"
    assert r["flags"] == [{"kind": "email", "text": "a@b.co"}]


@needs_node
def test_settings_with_a_saved_personality_says_where_it_came_from_and_remove_posts_nothing_until_save():
    r = run(SETTINGS_JS() + PICKER_JS + """
setupRest([], null)
const posts = []
const store = { post: async (path, body) => { posts.push(body); return {} } }
const s = snapWith([]); s.settings.persona = 'Likes owls.'; s.settings.persona_source = 'archivist'
const root = mount(SettingsForm, { store, snap: s })
const box = find(root.tree, n => n.type === PersonaField)
const shownProps = box.props
box.props.onChange({ persona: '', persona_source: '' })
await settle()
const before = posts.length
await button(root.tree, 'Save changes').props.onClick()
await settle()
const shown = text(mount(PersonaField, shownProps).tree)
out({ shown, before, posted: posts.map(p => [p.persona, p.persona_source]) })
""")
    assert "Personality · from archivist" in r["shown"] and "Edit" in r["shown"] and "Remove" in r["shown"]
    assert r["before"] == 0 and r["posted"] == [["", ""]]


def test_the_page_styles_the_picker_and_box_and_respects_narrow_widths_and_reduced_motion():
    for sel in (".h-hermes-list{", ".h-hermes-item{", ".h-persona{", ".h-persona-flags{", "@keyframes h-persona-in"):
        assert sel in STYLE, sel
    assert "prefers-reduced-motion: reduce){.h-persona{animation:none}" in STYLE
    assert "cubic-bezier(.34,1.45,.5,1)" in STYLE.split(".h-hermes-item{", 1)[1].split("\n", 1)[0]
    assert SETUP.count("jsx(HermesPicker,") == 2 and SETUP.count("jsx(PersonaField,") == 2
