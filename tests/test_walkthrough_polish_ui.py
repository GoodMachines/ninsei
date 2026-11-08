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
const folded = mount(HermesPicker, { collapsible: true, onPick: () => {} })
await settle()
const before = { items: items(folded.tree).length, button: !!button(folded.tree, 'Re-import from a Hermes agent'),
  expanded: button(folded.tree, 'Re-import from a Hermes agent').props['aria-expanded'] }
button(folded.tree, 'Re-import from a Hermes agent').props.onClick()
await settle()
const after = { items: items(folded.tree).length, close: !!button(folded.tree, 'Close') }
const open = mount(HermesPicker, { onPick: () => {} })
await settle()
out({ before, after, onboarding: items(open.tree).length, onboardingButton: !!button(open.tree, 'Re-import') })
""")
    assert r["before"] == {"items": 0, "button": True, "expanded": False}
    assert r["after"] == {"items": 3, "close": True}
    assert r["onboarding"] == 3 and r["onboardingButton"] is False
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
out({ id: o.id, main: text(o.label.props.children[0]), sub: text(o.label.props.children[1]), guess: text(guess.label), ring: ring.props.label })
""")
    assert r["id"] == 40000 and r["main"] == "About 50 replies a day" and r["sub"] == "40k tokens"
    assert r["guess"] == "About 20 replies a day20k tokens"
    assert r["ring"] == "12k of 40k tokens today (about 47 replies a day)"
    assert "BUDGET_PRESETS.map(n => budgetOption(n, snap.budget))" in fn(SETUP, "Onboarding")
    assert "BUDGET_PRESETS.map(n => budgetOption(n, snap.budget))" in fn(SETUP, "SettingsForm")
    assert ".h-seg-sub{" in STYLE


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
    assert "jsx('summary', { children: 'More' })" in more and "EXIF" in more and "original file is never uploaded" in more
    assert ".h-more>summary{" in STYLE and ".h-more[open]>summary{display:none}" in STYLE


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


def test_dialog_titles_and_descriptions_use_ninsei_type():
    # the dashboard's DialogDescription is `font-mondwest` (a serif) and its title `font-expanded uppercase`; inline styles
    # put the page's type back without a selector on the host's markup (the catalog's desktop-surface rule)
    tail = (ROOT / "ui" / "platform" / "dashboard_tail.js").read_text()
    dialog = tail.split("function Dialog(props) {", 1)[1].split("\n  }\n", 1)[0]
    assert "jsx(C.DialogTitle, { style: DIALOG_TITLE," in dialog and "jsx(C.DialogDescription, { style: DIALOG_DESC," in dialog
    assert "const DIALOG_TITLE = { fontFamily: 'inherit', textTransform: 'none', letterSpacing: 'normal'" in tail
    assert "const DIALOG_DESC = { fontFamily: 'inherit'" in tail
    assert "data-slot" not in STYLE


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
