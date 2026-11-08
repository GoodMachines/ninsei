// ---------------------------------------------------------------------------------------------
// small shared parts: form rows, segmented picker, interest chips, face picker, avatars
// ---------------------------------------------------------------------------------------------

function Field(props) {
  return jsxs('div', { className: 'h-field', children: [
    props.label && jsx('label', { htmlFor: props.id, children: props.label }),
    props.children,
    props.error && jsx('div', { className: 'h-hint h-err', id: props.id ? props.id + '-err' : undefined, role: 'alert', children: props.error }),
    props.hint && jsx('div', { className: 'h-hint', id: props.hintId, children: props.hint })
  ] })
}

// The wordmark: "Ninsei" in DotGothic16, as outlines (no font file to load, nothing fetched). The glyphs are
// taken from DotGothic16 (SIL Open Font License 1.1, see docs/fonts/DotGothic16-OFL.txt) by
// scripts/wordmark_path.py. It takes the text colour, so it follows the host theme.
const WORDMARK_PATH = 'M28 373H102V496H163V620H225V743H287V867H349V991H400V373H472V1188H400V1125H338V1001H276V878H214V754H153V631H102V1188H28ZM713 434H786V569H713ZM713 620H786V1188H713ZM1028 620H1102V682H1153V620H1349V682H1410V743H1472V1188H1400V754H1338V692H1163V754H1102V1188H1028ZM1528 991H1602V1114H1900V940H1591V878H1528V682H1591V620H1910V682H1972V816H1900V692H1602V867H1910V929H1972V1125H1910V1188H1591V1125H1528ZM2091 1063H2028V743H2091V682H2153V620H2349V682H2410V743H2472V940H2102V1053H2163V1114H2338V1053H2400V991H2472V1063H2410V1125H2349V1188H2153V1125H2091ZM2400 867V754H2338V692H2163V754H2102V867ZM2713 434H2786V569H2713ZM2713 620H2786V1188H2713Z'
function Wordmark(props) {
  const h = props.height || 14
  return jsx('svg', { className: 'h-wordmark', role: 'img', 'aria-label': 'Ninsei', viewBox: '0 360 2800 840', height: h, width: h * 2800 / 840,
    fill: 'currentColor', children: jsx('path', { d: WORDMARK_PATH }) })
}

// Vibe presets under the vibe field: each fills it in, and the one matching the field shows as picked.
function VibePresets(props) {
  return jsx('div', { className: 'h-chips h-vibes', role: 'group', 'aria-label': 'Vibe presets', children: VIBE_PRESETS.map(([label, vibe]) =>
    jsx('button', { type: 'button', className: 'h-chip', 'data-hit': props.value.trim() === vibe, 'aria-pressed': props.value.trim() === vibe,
      title: vibe, onClick: () => props.onPick(vibe), children: label }, label)) })
}

// ---- Start from one of your Hermes agents ------------------------------------------------------------
// The owner's local Hermes profiles, as a row of choices. Picking one reads its personality file once (a
// proposal: nothing is saved) and hands the name and text to the form; the owner reviews them and saves.
const PERSONA_MAX = 1500
const FLAG_LABEL = {
  email: 'Looks like an email', phone: 'Looks like a phone number', key: 'Looks like a key or token',
  home_path: 'Looks like a path on your computer', ip: 'Looks like an IP address',
  url_secret: 'Looks like a link with a secret in it', address: 'Looks like a street address',
  sensitive_line: 'Mentions a password or similar'
}

function flagLine(f) { return (FLAG_LABEL[f.kind] || 'Looks private') + ': ' + f.text }

// A flag stays while the text it found is still in the box, so deleting the line clears its warning.
function liveFlags(flags, text) {
  const t = String(text || '')
  return (flags || []).filter(f => t.includes(String(f.text || '').replace(/…$/, '')))
}

// A profile card's second line: its description, else whether it has a personality, else the profile's own name
// when the card shows a different display name. Never the title again.
function hermesSub(p) {
  if (p.description) return p.description
  if (!p.has_personality) return 'No personality set'
  return p.display_name && p.display_name !== p.name ? p.name : ''
}

// `collapsible` (Settings): the list waits behind a "Re-import from a Hermes agent" button, since picking one is a
// setup step; onboarding shows it open.
function HermesPicker(props) {
  const [list, setList] = useState(null)
  const [busy, setBusy] = useState('')
  const [open, setOpen] = useState(!props.collapsible)
  useEffect(() => {
    let live = true
    P.rest('/profiles/hermes').then(r => { if (live) setList((r && r.profiles) || []) }, () => { if (live) setList([]) })
    return () => { live = false }
  }, [])
  // one sideways row: which edges still have cards past them (drives the fade; only set while it overflows)
  const rowRef = useRef(null)
  const [edge, setEdge] = useState('')
  const measure = () => {
    const el = rowRef.current
    if (!el) return
    const more = el.scrollWidth - el.clientWidth > 2
    const next = !more ? '' : el.scrollLeft <= 2 ? 'end' : el.scrollLeft + el.clientWidth >= el.scrollWidth - 2 ? 'start' : 'both'
    setEdge(prev => prev === next ? prev : next)
  }
  useEffect(() => {
    measure()
    if (typeof window === 'undefined') return undefined
    // the panel can change width without the window resizing (a docked pane, Settings opening)
    const ro = typeof ResizeObserver === 'function' && rowRef.current ? new ResizeObserver(measure) : null
    if (ro) ro.observe(rowRef.current)
    window.addEventListener('resize', measure)
    return () => { window.removeEventListener('resize', measure); if (ro) ro.disconnect() }
  }, [list, open])
  if (!list || !list.length) return null
  // the profile in use first, so the likely choice shows without scrolling; the rest keep their order
  const ordered = list.filter(p => p.current).concat(list.filter(p => !p.current))
  const pick = async p => {
    if (busy) return
    setBusy(p.name)
    try { props.onPick(await P.rest('/profiles/hermes/import?name=' + encodeURIComponent(p.name))) }
    catch (e) { P.toast('error', errText(e)) }
    setBusy('')
  }
  // one toggle that stays mounted (focus stays on it), saying whether the list is open and which list it opens
  const toggle = props.collapsible && jsx(K.Button, { variant: 'ghost', size: 'sm', 'aria-expanded': open, 'aria-controls': 'h-hermes-pick',
    onClick: () => setOpen(!open), children: open ? 'Close' : 'Re-import from a Hermes agent' })
  return jsxs('div', { className: open ? 'h-field h-hermes' : 'h-hermes-add', children: [
    jsxs('div', { className: 'h-row', style: { justifyContent: open ? 'space-between' : 'flex-start' }, children: [
      open && jsx('div', { className: 'h-label', id: 'h-hermes-label', children: props.collapsible ? 'Re-import from one of your Hermes agents' : 'Start from one of your Hermes agents' }),
      toggle
    ] }),
    open && jsxs('div', { id: 'h-hermes-pick', className: 'h-col', role: 'group', 'aria-labelledby': 'h-hermes-label', style: { gap: 8 }, children: [
      jsx('div', { className: 'h-hermes-list', ref: rowRef, 'data-edge': edge, onScroll: measure, role: 'group', 'aria-label': 'Your Hermes agents, scroll sideways for more', children: ordered.map(p =>
        jsxs('button', { type: 'button', className: 'h-hermes-item', 'data-here': !!p.current, 'data-busy': busy === p.name, disabled: !!busy,
          title: p.description || p.name, onClick: () => pick(p), children: [
          jsxs('span', { className: 'h-hermes-top', children: [
            jsx('b', { children: p.display_name || p.name }),
            p.current && jsx('span', { className: 'h-chip h-hermes-here', children: 'this one' })
          ] }),
          hermesSub(p) && jsx('span', { className: 'h-hermes-sub', children: hermesSub(p) })
        ] }, p.name)) }),
      jsx('div', { className: 'h-hint', children: 'Reads that agent’s personality file (SOUL.md) and name once, and never changes it. Nothing is saved until you press Save.' })
    ] })
  ] })
}

// What a picked profile fills in. The form is the one holding the values; `pick` is page-only state (flags,
// whether the text was cut, whether the editor is open) that is never posted.
function applyProposal(p, set, setPick) {
  set(Object.assign({ agent_name: p.agent_name }, p.persona ? { persona: p.persona, persona_source: p.source } : {}))
  setPick({ flags: p.flags || [], truncated: !!p.truncated, open: !!p.persona })
  if (!p.persona) P.toast('info', 'That agent has no personality text, so only its name was filled in.')
}

// The Personality box: optional and closed until asked for or filled by a picked profile; once set, a quiet
// row with Edit and Remove. Everything it says about privacy is plain text, above the box.
function PersonaField(props) {
  const v = props.value || ''
  const pick = props.pick || {}
  const flags = liveFlags(pick.flags, v)
  const label = 'Personality' + (props.source ? ' · from ' + props.source : '')
  const setOpen = open => props.setPick(Object.assign({}, pick, { open }))
  if (!pick.open && !v) {
    return jsx('div', { className: 'h-persona-add', children: jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: () => setOpen(true), children: 'Add a personality (optional)' }) })
  }
  if (!pick.open) {
    return jsxs('div', { className: 'h-field h-persona-row', children: [
      jsx('div', { className: 'h-label', children: label }),
      jsx('div', { className: 'h-persona-peek', children: v }),
      jsxs('div', { className: 'h-actions', children: [
        jsx(K.Button, { variant: 'secondary', size: 'sm', onClick: () => setOpen(true), children: 'Edit' }),
        jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: () => { props.onChange({ persona: '', persona_source: '' }); props.setPick({ flags: [], truncated: false, open: false }) }, children: 'Remove' })
      ] })
    ] })
  }
  return jsxs('div', { className: 'h-field h-persona', children: [
    jsx('label', { htmlFor: props.id, children: label }),
    jsx('div', { className: 'h-hint h-persona-warn', children: 'Your agent uses this in every room it’s in, and people there could get it to repeat it. Remove anything private.' }),
    jsx('textarea', { id: props.id, className: 'h-ta', rows: 9, value: v, maxLength: PERSONA_MAX, spellCheck: false,
      placeholder: 'How your agent talks, what it likes, what it cares about', onChange: e => props.onChange({ persona: e.target.value }) }),
    flags.length > 0 && jsx('ul', { className: 'h-persona-flags', 'aria-label': 'Possibly private', children: flags.map((f, i) =>
      jsx('li', { children: flagLine(f) }, i)) }),
    jsxs('div', { className: 'h-persona-foot', children: [
      jsx('span', { className: 'h-hint', 'data-over': v.length >= PERSONA_MAX, children: v.length.toLocaleString('en-US') + ' / ' + PERSONA_MAX.toLocaleString('en-US') }),
      pick.truncated && jsx('span', { className: 'h-hint', children: 'Cut to 1,500 characters' }),
      jsx('span', { className: 'h-grow' }),
      jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: () => { props.onChange({ persona: '', persona_source: '' }); props.setPick({ flags: [], truncated: false, open: false }) }, children: 'Remove' }),
      v && jsx(K.Button, { variant: 'secondary', size: 'sm', onClick: () => setOpen(false), children: 'Done' })
    ] })
  ] })
}

function Seg(props) {
  return jsx('div', { className: 'h-seg', role: 'radiogroup', 'aria-label': props.label, children:
    props.options.map(o => jsx('button', { type: 'button', role: 'radio', 'aria-checked': props.value === o.id,
      'data-on': props.value === o.id, onClick: () => props.onChange(o.id), children: o.label }, o.id)) })
}

// A person's status dot. The word is its label (and its tooltip): colour alone never says it.
function StatusDot(props) {
  const k = statusKey(props.p)
  return jsx('span', { className: 'h-presence', 'data-s': k, 'data-on': k !== 'away', role: 'img', 'aria-label': STATUS_LABEL[k], title: STATUS_LABEL[k] })
}

function Chips(props) {
  const hits = new Set(props.hits || [])
  const list = props.items || []
  if (!list.length) return null
  return jsx('div', { className: 'h-chips', children: list.map(t =>
    jsxs('span', { className: 'h-chip', 'data-hit': hits.has(t), children: [
      t,
      props.onRemove && jsx('button', { type: 'button', 'aria-label': 'Remove ' + t, onClick: () => props.onRemove(t), children: '×' })
    ] }, t)) })
}

// Type an interest, press Enter or comma. Suggestions are one click away.
function InterestInput(props) {
  const [text, setText] = useState('')
  const value = props.value || []
  const add = raw => {
    const t = String(raw || '').toLowerCase().replace(/[^a-z0-9 +#-]/g, '').trim().slice(0, 24)
    if (!t || value.includes(t) || value.length >= 8) return
    props.onChange(value.concat([t]))
  }
  const ideas = INTEREST_IDEAS.filter(t => !value.includes(t)).slice(0, 8)
  return jsxs('div', { className: 'h-col', style: { gap: 6 }, children: [
    jsx(Chips, { items: value, onRemove: t => props.onChange(value.filter(x => x !== t)) }),
    jsx(K.Input, { id: props.id, value: text, placeholder: value.length >= 8 ? 'That is plenty' : 'Add an interest and press Enter',
      disabled: value.length >= 8,
      onChange: e => setText(e.target.value),
      onKeyDown: e => {
        if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(text); setText('') }
        else if (e.key === 'Backspace' && !text && value.length) props.onChange(value.slice(0, -1))
      } }),
    ideas.length > 0 && jsx('div', { className: 'h-chips', children: ideas.map(t =>
      jsx('button', { type: 'button', className: 'h-chip', style: { cursor: 'pointer' }, onClick: () => add(t), children: '+ ' + t }, t)) })
  ] })
}

// The face editor's labels, for every option a face can have.
const FACE_OPT_LABEL = { dot: 'Dots', round: 'Round', sleepy: 'Sleepy', wide: 'Wide', visor: 'Visor', smile: 'Smile',
  flat: 'Flat', grin: 'Grin', cat: 'Cat', o: 'Surprised', none: 'None', antenna: 'Antenna', glasses: 'Glasses',
  headphones: 'Headphones', halo: 'Halo', sprout: 'Sprout', horns: 'Horns', bow: 'Bow', blush: 'Blush', freckles: 'Freckles',
  spots: 'Spots', soft: 'Soft', tall: 'Tall', drop: 'Drop', bean: 'Bean' }

const CARD_STYLE_LABEL = { member: 'Member', scanner: 'Scanner' }

// "Edit face" on a card opens Settings and wants the face editor in view. The request is a one-shot flag
// that Settings picks up when it mounts (or at once if it is already open); it lapses after 15 s so an
// old one never steals focus later.
const FACE_FOCUS = { at: 0, fns: new Set() }
function wantFaceEditor() {
  FACE_FOCUS.at = Date.now()
  FACE_FOCUS.fns.forEach(fn => fn())
}

// Focus the face editor and scroll its card and controls to the top of whatever scrolls. A spring does
// the scrolling (an instant jump with reduced motion). False if the editor isn't on the page yet.
function showFaceEditor() {
  const picker = document.getElementById('h-facepicker')
  if (!picker) return false
  try { picker.focus({ preventScroll: true }) } catch (_) { /* not focusable here */ }
  const target = picker.parentElement || picker
  let box = target.parentElement
  while (box && !(box.scrollHeight > box.clientHeight + 1 && /(auto|scroll)/.test(getComputedStyle(box).overflowY))) box = box.parentElement
  if (!box) { target.scrollIntoView({ block: 'start' }); return true }
  const dy = target.getBoundingClientRect().top - box.getBoundingClientRect().top - 16
  const from = box.scrollTop
  const to = clamp(from + dy, 0, box.scrollHeight - box.clientHeight)
  if (motion.reduced() || Math.abs(to - from) < 2) { box.scrollTop = to; return true }
  // the person scrolling for themselves ends the animation
  const stops = ['wheel', 'touchstart', 'pointerdown', 'keydown']
  const done = () => stops.forEach(t => box.removeEventListener(t, stop))
  const spring = motion.spring({ from, to, k: SPRING.calm.k, c: SPRING.calm.c, onUpdate: x => { box.scrollTop = x }, onRest: done })
  const stop = () => { spring.stop(); done() }
  stops.forEach(t => box.addEventListener(t, stop, { passive: true }))
  return true
}

function useFaceEditorFocus() {
  useEffect(() => {
    let frame = 0
    let live = true
    const attempt = tries => {
      if (!live || !FACE_FOCUS.at) return
      if (Date.now() - FACE_FOCUS.at > 15000) { FACE_FOCUS.at = 0; return }
      if (showFaceEditor()) { FACE_FOCUS.at = 0; return }
      if (tries > 0) frame = window.requestAnimationFrame(() => attempt(tries - 1))
    }
    const kick = () => { window.cancelAnimationFrame(frame); frame = window.requestAnimationFrame(() => attempt(40)) }
    FACE_FOCUS.fns.add(kick)
    kick()
    return () => { live = false; window.cancelAnimationFrame(frame); FACE_FOCUS.fns.delete(kick) }
  }, [])
}

// An agent's face editor: a big live preview, a tab per part, each option a small live face (ui/33_builder.js).
// `noCard` leaves out the card style.
function FacePicker(props) {
  const face = faceFor(props.value, props.pk)
  const [tab, setTab] = useState('shape')
  const uid = (props.id || 'h-face') + '-b'
  const set = patch => props.onChange(Object.assign({}, face, patch))
  const layers = FACE_LAYERS.concat(!props.noCard ? [{ key: 'card', label: 'Card' }] : [])
  const layer = layers.find(l => l.key === tab) || layers[0]
  const thumb = patch => jsx(Face, { face: Object.assign({}, face, patch), pk: props.pk, state: 'activity: idle', size: 64, className: 'hf-still' })
  const panel = layer.key === 'colour' ? jsx(FaceColours, { face, set })
    : layer.key === 'card' ? jsx(OptionGrid, { label: 'Card style', value: face.card, swatch: true, onChange: v => set({ card: v }),
      options: FACE_CARDS.map(o => ({ id: o, label: CARD_STYLE_LABEL[o], render: () => jsx(CardSwatch, { card: o, hue: face.hue, hue2: face.hue2 }) })) })
    : jsx(OptionGrid, { label: 'Face ' + layer.label.toLowerCase(), value: face[layer.key], onChange: v => set({ [layer.key]: v }),
      options: layer.opts.map(o => ({ id: o, label: FACE_OPT_LABEL[o] || o, render: () => thumb({ [layer.key]: o }) })) })
  return jsx(BuilderShell, { id: props.id, uid, label: 'Face editor', version: JSON.stringify(face), tab, setTab, layers, panel,
    preview: jsx(Face, { face, pk: props.pk, state: props.previewState || 'activity: idle', size: 128, name: props.name }),
    actions: [jsx(K.Button, { variant: 'secondary', size: 'sm', onClick: () => props.onChange(randomFace(face)), children: 'Randomize' }, 'r')] })
}

function Initial(props) {
  const n = String(props.name || '?').trim()
  const size = props.size
  return jsx('span', { className: 'h-initial', 'aria-hidden': true, style: size ? { width: size, height: size, fontSize: Math.max(9, Math.round(size * 0.43)) } : undefined,
    children: (n[0] || '?').toUpperCase() })
}

// A picture someone chose, in a circle. `uri` is a data URI the engine rebuilt from bytes it checked; an <img> only,
// never inlined, and it never gets a name or a link of its own.
function PersonPhoto(props) {
  const size = props.size || 28
  return jsx('span', { className: cx('h-photo', props.className), 'aria-hidden': true, style: { width: size, height: size },
    children: jsx('img', { src: props.uri, alt: '', width: size, height: size, draggable: false, decoding: 'async', referrerPolicy: 'no-referrer' }) })
}

// How a person shows up anywhere: their picture (when they set one and pictures are on), else their pixel avatar, else
// the face they built before avatars existed, else the letter. A lookalike (`flagged`) gets the letter only, so a
// copied picture or avatar can't make it pass for the real person. Nothing is ever made up from the key.
// `art` overrides the snapshot's (Settings previews a picture before it is published).
function PersonMark(props) {
  const ctx = useContext(PeopleContext)
  const size = props.size || 28
  const art = props.flagged ? null : (props.art !== undefined ? props.art : ctx.people[props.pk])
  const pics = props.art !== undefined || ctx.show || (!!ctx.me && ctx.me.includes(props.pk))  // your own picture always shows: the engine serves it, others see it
  const uri = useAvatarUri(art && art.av && pics ? props.pk : '', art && art.av)
  const body = art && art.uri && pics ? art.uri : uri
  if (body) return jsx(PersonPhoto, { uri: body, size, className: props.className })
  if (art && art.avatar && cleanAvatar(art.avatar)) return jsx(PersonAvatar, { avatar: art.avatar, size, className: props.className })
  if (art && art.face) return jsx(PersonFace, { face: art.face, pk: props.pk, size, className: props.className })
  return jsx(Initial, { name: props.name, size: props.size })
}

function Notice(props) {
  return jsxs('div', { className: 'h-notice', role: props.role, children: [
    props.icon && jsx(K.Icon, { name: props.icon, size: 14 }),
    jsx('div', { className: 'h-grow', children: props.children })
  ] })
}

// A toy may show one page: its own. Every platform's frame reports each load inside it (Desktop's
// iframe, the Webapp's guest shell, the dashboard iframe). The frame stays hidden until its first
// load comes with the key from the guard script the backend puts at the top of every toy document
// (ninsei_engine/toy.py TOY_GUARD; the key itself never appears in the document). Any later load means the toy navigated (a link, location=,
// a refresh tag, a reload), and the frame is closed. A toy that navigates while its own page is still
// loading reports only the new page's load, without the key, so that page is never shown; after 10 s
// the viewer is told it hasn't started (a slow honest toy still appears when its key arrives).
// The request has already gone out either way, so that page may have seen the viewer's IP address.
// This stops links, redirects and scripted navigation; a toy written to beat it from inside its own
// page (document.open() wipes the guard's listeners) can still get one page shown. See toy.py.
function toyGuard(key, show, leave, later, stuck) {
  let loads = 0
  let proved = false
  let helloed = false
  return {
    // The key goes out once, in reply to the first hello: TOY_GUARD's, posted before any toy code
    // runs. It can't wait for "no load yet": Chrome delivers the frame's load to this page before
    // that earlier hello message, so an honest toy would never get its key.
    hello() { if (helloed) return null; helloed = true; return key },
    message(data) {
      if (proved || data !== 'ninsei-toy-loaded:' + key || loads > 1) return
      proved = true
      if (loads === 1) show()
    },
    load() {
      loads += 1
      if (loads > 1) return leave()
      if (proved) return show()
      later(() => { if (!proved) stuck() }, 10000)
    }
  }
}

function toyKey() {
  const a = new Uint8Array(16)
  crypto.getRandomValues(a)
  return Array.from(a, b => b.toString(16).padStart(2, '0')).join('')
}

// A toy someone shared: never loaded until the viewer presses Run, and then only inside an
// opaque-origin sandbox (scripts on, no same-origin, no popups, no top navigation).
function ToyFrame(props) {
  return jsx(GuardedToy, { key: props.html, html: props.html, title: props.title, tall: props.tall })
}

function GuardedToy(props) {
  const [state, setState] = useState('starting')
  const frame = useRef(null)
  const guard = useRef(null)
  const timers = useRef([])
  if (!guard.current) {
    guard.current = toyGuard(toyKey(), () => setState(s => s === 'closed' ? s : 'shown'), () => setState('closed'),
      (fn, ms) => timers.current.push(window.setTimeout(fn, ms)), () => setState(s => s === 'starting' ? 'stuck' : s))
  }
  useEffect(() => {
    const onMessage = e => {
      const win = frame.current && frame.current.contentWindow
      if (!win || e.source !== win) return
      if (e.data === 'ninsei-toy-hello') {
        const key = guard.current.hello()
        if (key) win.postMessage(key, '*')
      } else if (typeof e.data === 'string') guard.current.message(e.data)
    }
    window.addEventListener('message', onMessage)
    return () => { window.removeEventListener('message', onMessage); timers.current.forEach(t => window.clearTimeout(t)) }
  }, [])
  if (state === 'closed') {
    return jsx(Notice, { icon: 'warning', role: 'alert', children: 'This toy tried to open a web page, so Ninsei closed it. That page may have seen your IP address.' })
  }
  return jsxs('div', { className: 'h-frame', 'data-tall': !!props.tall, 'data-starting': state !== 'shown', children: [
    state === 'stuck' && jsx('div', { className: 'h-frame-note h-faint h-small', role: 'status',
      children: 'This toy hasn’t finished starting. If it tried to open a web page, Ninsei is keeping that page hidden.' }),
    jsx(K.Toy, { html: props.html, title: props.title || 'Shared toy', onLoad: () => guard.current.load(), frameRef: frame })
  ] })
}

// A modal with the kit's own dialog. `footer` sits at the bottom right.
function Modal(props) {
  return jsx(K.Dialog, { open: props.open, onClose: props.onClose, title: props.title, description: props.description,
    wide: props.wide, footer: props.footer, children: props.children })
}
