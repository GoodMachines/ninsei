"""Walkthrough polish (2026-11-08): Settings keeps the import list behind a button and keeps focused fields above the
Save bar; budgets say what they buy in replies; onboarding is shorter (faces and pictures behind "Customize"), its
sample names are nobody real and the disabled button says why; dialogs keep Ninsei's type; the agent glow follows the
theme; the exported card keeps the on-screen card's rounded corners."""
import re

from test_audit_review import SETTINGS_JS
from test_audit_ui import APP, CORE, ROOT, SETUP, STYLE, PARTS, const, fn, needs_node, run, src
from test_import_profile_ui import ONBOARD_JS, PICKER_JS

FACE = src("10_face.js")
LOOK = src("32_look.js")
CARDIMG = src("36_cardimage.js")
SCANNER = src("34_scanner.js")


# --- 1: Settings layout -------------------------------------------------------------------------------------------

@needs_node
def test_settings_keeps_the_hermes_list_behind_a_reimport_button_and_onboarding_shows_it():
    r = run(PICKER_JS + """
setupRest(PROFILES, PROPOSAL)
const items = tree => { const out = []; (function walk(n) { if (!n || typeof n !== 'object') return; if (Array.isArray(n)) return n.forEach(walk)
  if (n.type === 'button') out.push(n); kids(n).forEach(walk) })(tree); return out }
const toggleOf = tree => find(tree, n => n.type === K.Button && n.props['aria-controls'] === 'h-hermes-pick')
const folded = mount(HermesPicker, { collapsible: true, onPick: () => {} })
await settle()
const t0 = toggleOf(folded.tree)
const before = { items: items(folded.tree).length, text: text(t0), expanded: t0.props['aria-expanded'],
  list: !!find(folded.tree, n => n.props && n.props.id === 'h-hermes-pick') }
t0.props.onClick()
await settle()
const t1 = toggleOf(folded.tree)
const group = find(folded.tree, n => n.props && n.props.id === 'h-hermes-pick')
const after = { items: items(folded.tree).length, text: text(t1), expanded: t1.props['aria-expanded'], group: group.props.role,
  label: group.props['aria-labelledby'] }
t1.props.onClick()
await settle()
const t2 = toggleOf(folded.tree)
const closed = { text: text(t2), expanded: t2.props['aria-expanded'], items: items(folded.tree).length }
const open = mount(HermesPicker, { onPick: () => {} })
await settle()
out({ before, after, closed, onboarding: items(open.tree).length, onboardingToggle: !!toggleOf(open.tree) })
""")
    assert r["before"] == {"items": 0, "text": "Re-import from a Hermes agent", "expanded": False, "list": False}
    assert r["after"] == {"items": 3, "text": "Close", "expanded": True, "group": "group", "label": "h-hermes-label"}
    assert r["closed"] == {"text": "Re-import from a Hermes agent", "expanded": False, "items": 0}
    assert r["onboarding"] == 3 and r["onboardingToggle"] is False
    # one toggle element in a fixed slot (React keeps it mounted, so focus stays on it when the list opens or closes)
    picker = fn(PARTS, "HermesPicker")
    assert picker.count("'aria-controls': 'h-hermes-pick'") == 1 and "'aria-expanded': open" in picker
    assert "jsx(HermesPicker, { collapsible: true," in fn(SETUP, "SettingsForm")
    assert "collapsible" not in fn(SETUP, "Onboarding")


@needs_node
def test_a_field_focused_under_the_save_bar_is_scrolled_above_it():
    r = run(fn(SETUP, "useKeepAboveBar") + """
const listeners = {}
globalThis.P = { listen: (t, type, f) => { listeners[type] = f; return () => {} } }
globalThis.getComputedStyle = el => ({ overflowY: el.overflow })
const scroller = { scrollHeight: 3000, clientHeight: 800, scrollTop: 100, overflow: 'auto', parentElement: null }
const pane = { scrollHeight: 3000, clientHeight: 3000, overflow: 'visible', parentElement: scroller }
const bar = { getBoundingClientRect: () => ({ top: 750, bottom: 800 }), contains: n => n === saveBtn }
const saveBtn = { getBoundingClientRect: () => ({ bottom: 790 }) }
const root = { parentElement: pane, addEventListener() {}, querySelector: s => s === '.h-savebar' ? bar : null }
function Host() { const ref = useRef(root); useKeepAboveBar(ref); return null }
mount(Host, {})
const under = { getBoundingClientRect: () => ({ bottom: 780 }) }
const above = { getBoundingClientRect: () => ({ bottom: 700 }) }
listeners.focusin({ target: above }); const a = scroller.scrollTop
listeners.focusin({ target: under }); const b = scroller.scrollTop
listeners.focusin({ target: saveBtn }); const c = scroller.scrollTop
out([a, b, c])
""")
    assert r == [100, 100 + 30 + 12, 142]       # above: nothing; under by 30 px: moved 30 + 12; the bar's own button: nothing
    form = fn(SETUP, "SettingsForm")
    assert "useKeepAboveBar(root)" in form and "ref: root" in form
    assert ".h-scroll:has(.h-savebar){scroll-padding-bottom:72px}" in STYLE
    assert ".h-settings{scroll-margin-bottom" not in STYLE and ".h-settings>section:last-of-type" not in STYLE  # no-op rules gone



@needs_node
def test_the_save_bar_sits_on_the_scrollers_edge_even_when_the_host_pads_its_bottom():
    # 2026-11-08, live in Desktop: its Settings panel pads the scroller's bottom, and a sticky bar stops above that
    # padding, so the bar floated 80 px up with the form showing under it.
    r = run(fn(SETUP, "useKeepAboveBar") + """
globalThis.P = { listen: () => () => {} }
globalThis.getComputedStyle = el => ({ overflowY: el.overflow, paddingBottom: el.pad })
const out_ = []
for (const pad of ['80px', '0px']) {
  const scroller = { overflow: 'auto', pad, parentElement: null }
  const pane = { overflow: 'visible', pad: '0px', parentElement: scroller }
  const bar = { style: {} }
  const root = { parentElement: pane, addEventListener() {}, querySelector: s => s === '.h-savebar' ? bar : null }
  function Host() { const ref = useRef(root); useKeepAboveBar(ref); return null }
  mount(Host, {})
  out_.push(bar.style.bottom)
}
out(out_)
""")
    assert r == ["-80px", ""]

# --- 2: budgets in replies ----------------------------------------------------------------------------------------

BUDGET_JS = (fn(SETUP, "capFirst") + fn(SETUP, "budgetOption") + fn(CORE, "repliesFor") + fn(CORE, "repliesWords")
             + fn(CORE, "dailyReplies") + const(CORE, "REPLY_TOKENS_GUESS") + fn(CORE, "fmtTokens"))


@needs_node
def test_budget_presets_say_how_many_replies_with_the_tokens_under_them():
    r = run(BUDGET_JS + fn(FACE, "BudgetRing") + """
function Ring() {}
const o = budgetOption(40000, { reply_tokens: 800 })
const guess = budgetOption(20000, undefined)
const ring = BudgetRing({ budget: { used: 12000, limit: 40000, pct: 0.3, replies: { per_day: 47 } } })
const [main, gap, sub] = o.label.props.children
out({ id: o.id, main: text(main), gap: [gap.props.className, text(gap)], sub: text(sub), guess: text(guess.label), ring: ring.props.label })
""")
    assert r["id"] == 40000 and r["main"] == "About 50 replies a day" and r["sub"] == "40k tokens"
    # the accessible name reads as two phrases ("…a day, 20k tokens"), the comma hidden on screen
    assert r["gap"] == ["h-vh", ", "]
    assert r["guess"] == "About 20 replies a day, 20k tokens"
    assert r["ring"] == "12k of 40k tokens today (about 47 replies a day)"
    assert "budgetOptions(snap.budget, null, form.budget_daily)" in fn(SETUP, "Onboarding")
    assert "budgetOptions(snap.budget, msgsCap, form.budget_daily)" in fn(SETUP, "SettingsForm")
    assert ".h-seg-sub{" in STYLE


@needs_node
def test_a_preset_never_promises_more_replies_than_the_message_limit_allows():
    # 2026-11-08, live: the 40k preset said "About 87 replies a day" beside "about 60 replies left today"
    r = run(BUDGET_JS + """
const saved = budgetOption(40000, { reply_tokens: 456, msgs: { limit: 60 } })
const typed = budgetOption(40000, { reply_tokens: 456, msgs: { limit: 60 } }, 30)
const under = budgetOption(20000, { reply_tokens: 456, msgs: { limit: 60 } })
const words = o => o.label.props.children.map(text).join('')
out({ saved: words(saved), typed: words(typed), under: words(under) })
""")
    assert r["saved"] == "About 60 replies a day, 40k tokens, message limit"
    assert r["typed"] == "About 30 replies a day, 40k tokens, message limit"
    assert r["under"] == "About 43 replies a day, 20k tokens"



@needs_node
def test_presets_the_message_limit_caps_alike_show_once_unless_picked():
    # 2026-11-08, filming: with a settled reply of ~450 tokens both 40k and 100k said "About 60 replies a day"
    r = run(BUDGET_JS + const(CORE, "BUDGET_PRESETS") + fn(SETUP, "budgetOptions") + """
const b = { reply_tokens: 456, msgs: { limit: 60 } }
const ids = os => os.map(o => o.id)
out({ capped: ids(budgetOptions(b, null, 40000)), picked: ids(budgetOptions(b, null, 100000)),
      roomy: ids(budgetOptions(b, 500, 40000)), fresh: ids(budgetOptions(undefined, null, 40000)),
      typed: ids(budgetOptions(b, 30, '40000')) })
""")
    assert r["capped"] == [20000, 40000]             # 100k buys the same 60 replies as 40k: one button
    assert r["picked"] == [20000, 40000, 100000]     # a saved 100k still shows as picked
    assert r["roomy"] == [20000, 40000, 100000]      # a higher message limit brings it back
    assert r["fresh"] == [20000, 40000, 100000]      # before any reply settles: 20, 40, 100 at the guess
    assert r["typed"] == [20000, 40000]              # 20k is 43 replies, capped at 30 like 40k; 40k stays as picked


def test_welcome_promises_only_what_the_code_enforces():
    on = fn(SETUP, "Onboarding")
    assert "speaks politely" not in on               # nothing enforces manners
    assert "takes instructions only from you" in on  # the owner-signature check does

@needs_node
def test_settings_daily_limit_says_what_a_typed_number_buys_and_when_messages_stop_it_first():
    r = run(SETTINGS_JS() + """
const root = mount(SettingsForm, { store: { post: async () => ({}) }, snap: snapWith(['wss://relay.example']) })
const hint = () => find(root.tree, n => n.type === Field && n.props.id === 'h-s-budget').props.hint
const preset = hint()
find(root.tree, n => n.type === K.Input && n.props.id === 'h-s-budget').props.onChange({ target: { value: '55000' } })
await settle()
const typed = hint()
find(root.tree, n => n.type === K.Input && n.props.id === 'h-s-msgs').props.onChange({ target: { value: '30' } })
await settle()
const capped = hint()
const input = find(root.tree, n => n.type === K.Input && n.props.id === 'h-s-budget').props
out({ preset, typed, capped, label: input['aria-label'], describedby: input['aria-describedby'] })
""")
    assert r["preset"] == "At 1000 tokens a reply (a typical reply)."          # the preset already says its replies
    assert r["typed"] == "About 55 replies a day, at 1000 tokens a reply (a typical reply)."
    assert r["capped"].endswith("The message limit below stops it at 30 replies first.")
    assert r["label"] == "Daily limit in tokens" and r["describedby"] == "h-s-budget-hint"
    assert "id: props.hintId" in fn(PARTS, "Field")


# --- 3: onboarding ------------------------------------------------------------------------------------------------

@needs_node
def test_onboarding_keeps_the_card_preview_and_puts_faces_and_pictures_behind_customize():
    r = run(ONBOARD_JS() + """
setupRest(PROFILES, PROPOSAL)
const root = mount(Onboarding, { store: { post: async () => ({}) }, snap: snap() })
const details = find(root.tree, n => n.type === 'details')
const inside = t => !!find(details, n => n.type === t)
out({ cls: details.props.className, summary: text(find(details, n => n.type === 'summary')), face: inside(FacePicker), look: inside(PersonLook),
  cardInside: inside(IdCard), card: !!find(root.tree, n => n.type === IdCard), open: !!details.props.open })
""")
    assert r == {"cls": "h-custom", "summary": "Customizeits face, your portrait or photo (optional)", "face": True, "look": True,
                 "cardInside": False, "card": True, "open": False}


@needs_node
def test_the_disabled_bring_in_button_says_what_it_waits_for():
    r = run(ONBOARD_JS() + """
setupRest(PROFILES, PROPOSAL)
const s = snap(); s.settings.display_name = ''
const root = mount(Onboarding, { store: { post: async () => ({}) }, snap: s })
const state = () => { const b = button(root.tree, 'Bring'); const h = find(root.tree, n => n.props && n.props.id === 'h-on-need')
  return { disabled: !!b.props.disabled, by: b.props['aria-describedby'] || null, hint: h ? text(h) : null } }
const both = state()
find(root.tree, n => n.type === K.Input && n.props.id === 'h-on-name').props.onChange({ target: { value: 'Rowan' } })
await settle()
const agent = state()
find(root.tree, n => n.type === K.Input && n.props.id === 'h-on-agent').props.onChange({ target: { value: 'Pixel' } })
await settle()
out({ both, agent, done: state(), only: setupNeeds({ display_name: '', agent_name: 'Pixel' }) })
""")
    assert r["both"] == {"disabled": True, "by": "h-on-need", "hint": "Add your name and your agent’s name to continue."}
    assert r["agent"] == {"disabled": True, "by": "h-on-need", "hint": "Add your agent’s name to continue."}
    assert r["done"] == {"disabled": False, "by": None, "hint": None}
    assert r["only"] == "Add your name to continue."


def test_sample_names_are_nobody_from_the_test_rooms():
    holders = re.findall(r"placeholder: '([^']*)'", SETUP)
    assert holders and "Rowan" in holders and "Pixel" in holders
    for real in ("Maya", "Sam", "Ada", "Bo", "Justin", "Beca"):
        assert real not in holders, real


def test_the_picture_note_is_short_with_the_detail_behind_more():
    look = fn(LOOK, "PersonLook")
    short = look.split("h-look-public")[1].split("details")[0]
    assert "Public and permanent" in short and "keep old pictures forever" in short     # the two facts stay up front
    assert "EXIF" not in short
    more = look.split("className: 'h-more'")[1]
    assert "EXIF" in more and "original file is never uploaded" in more
    # the summary stays when open (it keeps focus and closes it again), saying Less
    assert "jsx('summary', { children: more ? 'Less' : 'More' })" in more and "onToggle: e => setMore(e.currentTarget.open)" in look
    assert ".h-more>summary{" in STYLE and ".h-more[open]>summary{display:none}" not in STYLE


@needs_node
def test_new_room_says_why_create_waits():
    r = run(fn(APP, "NewRoomDialog") + """
function Modal() {}; function Field() {}; function InterestInput() {}
const snap = { settings: { interests: [] } }
const root = mount(NewRoomDialog, { store: {}, snap, onClose() {}, onDone() {} })
const st = () => { const b = button(root.tree, 'Create room'); const h = find(root.tree, n => n.props && n.props.id === 'h-nr-need')
  return [!!b.props.disabled, b.props['aria-describedby'] || null, h ? text(h) : null] }
const empty = st()
find(root.tree, n => n.type === K.Input && n.props.id === 'h-nr-name').props.onChange({ target: { value: 'shader club' } })
await settle()
out([empty, st()])
""")
    assert r == [[True, "h-nr-need", "Name the room to create it."], [False, None, None]]


@needs_node
def test_join_says_why_it_waits_and_enter_does_nothing_without_a_code():
    r = run(fn(APP, "JoinDialog") + """
function Modal() {}
let posts = 0
const store = { post: async () => { posts++; return { id: 'r' } } }
const root = mount(JoinDialog, { store, onClose() {}, onDone() {} })
const st = () => { const b = button(root.tree, 'Join'); const h = find(root.tree, n => n.props && n.props.id === 'h-jn-need')
  return [!!b.props.disabled, b.props['aria-describedby'] || null, h ? text(h) : null] }
find(root.tree, n => n.type === K.Input).props.onKeyDown({ key: 'Enter' })
await settle()
const empty = st()
find(root.tree, n => n.type === K.Input).props.onChange({ target: { value: 'ninsei:abc' } })
await settle()
out([empty, st(), posts])
""")
    assert r == [[True, "h-jn-need", "Paste a code to join."], [False, None, None], 0]


@needs_node
def test_settings_budget_summary_says_how_many_replies_are_left():
    r = run(fn(CORE, "repliesLeftWords") + """
out([repliesLeftWords({ replies: { per_day: 47, left: 28 } }), repliesLeftWords({ replies: { left: 1 } }),
     repliesLeftWords({ replies: { left: 0 } }), repliesLeftWords({}), repliesLeftWords(undefined)])
""")
    assert r == ["about 28 replies left today", "about 1 reply left today", "no replies left today", "", ""]
    assert "' · ' + repliesLeftWords(snap.budget)" in fn(SETUP, "SettingsForm")


def test_dialog_titles_and_descriptions_use_ninsei_type():
    # the dashboard's DialogDescription is `font-mondwest` (a serif) and its title `font-expanded uppercase`; inline styles
    # put the page's type back without a selector on the host's markup (the catalog's desktop-surface rule)
    tail = (ROOT / "ui" / "platform" / "dashboard_tail.js").read_text()
    dialog = tail.split("function Dialog(props) {", 1)[1].split("\n  }\n", 1)[0]
    assert "jsx(C.DialogTitle, { style: DIALOG_TITLE," in dialog and "jsx(C.DialogDescription, { style: DIALOG_DESC," in dialog
    assert "const DIALOG_TITLE = { fontFamily: 'inherit', textTransform: 'none', letterSpacing: 'normal'" in tail
    assert "const DIALOG_DESC = { fontFamily: 'inherit'" in tail
    assert "data-slot" not in STYLE
    # the theme's header carries a bottom rule (border-b): space under the text keeps it off the description
    assert "jsxs(C.DialogHeader, { style: { padding: '0 0 12px' }," in dialog


# --- 4: light themes ----------------------------------------------------------------------------------------------

def test_the_agent_glow_fades_with_a_light_theme_but_not_on_cards():
    assert "'--gh': f.hue" in fn(FACE, "Face")
    rule = STYLE.split("@supports (color:oklch(from red l c h)){.hf svg{", 1)[1].split("}}", 1)[0]
    assert "var(--h-glowbase,var(--h-fg,#fff))" in rule and "var(--gh,200)" in rule and "clamp(0, (l - 0.5)" in rule
    assert "rgba(3,8,16,.8)" in rule                                            # the hairline stays on every theme
    assert ".h-idcard{--h-glowbase:#fff}" in STYLE                              # cards are dark whatever the theme
    # the glow's colour is the same oklch the pixel colours use for it
    assert "glow: o(0.8, 0.15, h)" in src("12_pixel.js") and "0.8 0.15 var(--gh,200)" in rule


# --- 5: exported cards --------------------------------------------------------------------------------------------

def test_exported_cards_have_the_on_screen_cards_rounded_corners():
    # on screen: 22px corners on a card about 380px wide; the 1200px export clips to rx 70 (22 / 380 * 1200 = 69.5)
    assert "aspect-ratio:1.6;border-radius:22px" in STYLE
    member = fn(CARDIMG, "cardSvg")
    assert "<clipPath id=\"ncclip\"><rect width=\"' + W + '\" height=\"' + H + '\" rx=\"70\"/></clipPath>" in member
    assert "out.push('<g clip-path=\"url(#ncclip)\">')" in member
    scanner = fn(SCANNER, "scannerSvg")
    assert "const R = 70" in scanner and "clip-path=\"url(#nscard)\"" in scanner


# --- the Hermes picker is one sideways row --------------------------------------------------------------------------

def test_hermes_picker_is_one_scrolling_row_with_the_current_profile_first():
    rule = STYLE.split(".h-hermes-list{", 1)[1].split("}", 1)[0]
    assert "display:flex" in rule and "flex-flow:row nowrap" in rule and "grid" not in rule
    assert "overflow-x:auto" in rule and "overflow-y:hidden" in rule and "scroll-snap-type:x proximity" in rule
    assert "scroll-padding:0 40px" in rule   # wider than the 36px edge fade, so a focused card's ring is never faded
    item = STYLE.split(".h-hermes-item{", 1)[1].split("}", 1)[0]
    assert "flex:0 0 190px" in item and "scroll-snap-align:start" in item
    assert ".h-hermes-list[data-edge=end]{" in STYLE and "mask-image" in STYLE
    assert "scroll-behavior:smooth" in STYLE and "prefers-reduced-motion: no-preference" in STYLE
    picker = fn(PARTS, "HermesPicker")
    assert "list.filter(p => p.current).concat(list.filter(p => !p.current))" in picker
    assert "ordered.map(" in picker and "aria-label" in picker and "onWheel" not in picker
