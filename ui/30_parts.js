// ---------------------------------------------------------------------------------------------
// small shared parts: form rows, segmented picker, interest chips, face picker, avatars
// ---------------------------------------------------------------------------------------------

function Field(props) {
  return jsxs('div', { className: 'h-field', children: [
    props.label && jsx('label', { htmlFor: props.id, children: props.label }),
    props.children,
    props.error && jsx('div', { className: 'h-hint h-err', id: props.id ? props.id + '-err' : undefined, role: 'alert', children: props.error }),
    props.hint && jsx('div', { className: 'h-hint', children: props.hint })
  ] })
}

// Vibe presets under the vibe field: each fills it in, and the one matching the field shows as picked.
function VibePresets(props) {
  return jsx('div', { className: 'h-chips h-vibes', role: 'group', 'aria-label': 'Vibe presets', children: VIBE_PRESETS.map(([label, vibe]) =>
    jsx('button', { type: 'button', className: 'h-chip', 'data-hit': props.value.trim() === vibe, 'aria-pressed': props.value.trim() === vibe,
      title: vibe, onClick: () => props.onPick(vibe), children: label }, label)) })
}

function Seg(props) {
  return jsx('div', { className: 'h-seg', role: 'radiogroup', 'aria-label': props.label, children:
    props.options.map(o => jsx('button', { type: 'button', role: 'radio', 'aria-checked': props.value === o.id,
      'data-on': props.value === o.id, onClick: () => props.onChange(o.id), children: o.label }, o.id)) })
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

// The face editor: every part as a row of small faces, each showing the agent with that option.
const FACE_PARTS = [
  { key: 'shape', label: 'Shape', opts: SHAPES },
  { key: 'eyes', label: 'Eyes', opts: FACE_EYES },
  { key: 'mouth', label: 'Mouth', opts: FACE_MOUTHS },
  { key: 'acc', label: 'Extra', opts: FACE_ACCS },
  { key: 'pattern', label: 'Cheeks', opts: FACE_PATTERNS }
]
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

function FacePicker(props) {
  const face = faceFor(props.value, props.pk)
  const set = patch => props.onChange(Object.assign({}, face, patch))
  const accent = face.acc !== 'none' || face.pattern !== 'none'
  return jsxs('div', { className: 'h-row h-facepick', id: props.id, tabIndex: props.id ? -1 : undefined, role: props.id ? 'group' : undefined,
    'aria-label': props.id ? 'Face editor' : undefined, children: [
    !props.noPreview && jsx(Face, { face, pk: props.pk, state: props.previewState || 'activity: idle', size: 64, name: props.name }),
    jsxs('div', { className: 'h-col h-grow', style: { gap: 10, minWidth: 0 }, children: [
      jsxs('div', { className: 'h-facepart', children: [
        jsx('div', { className: 'h-faint h-tiny h-caps', children: 'Card' }),
        jsx('div', { className: 'h-shapes', role: 'radiogroup', 'aria-label': 'Card style', children: FACE_CARDS.map(o =>
          jsxs('button', { type: 'button', className: 'h-shape h-cardpick', role: 'radio', 'aria-checked': face.card === o, 'data-on': face.card === o,
            onClick: () => set({ card: o }), children: [
              jsx(CardSwatch, { card: o, hue: face.hue, hue2: face.hue2 }, 's'),
              jsx('span', { children: CARD_STYLE_LABEL[o] }, 'l')
            ] }, o)) })
      ] }),
      ...FACE_PARTS.map(part => jsxs('div', { className: 'h-facepart', children: [
        jsx('div', { className: 'h-faint h-tiny h-caps', children: part.label }),
        jsx('div', { className: 'h-shapes', role: 'radiogroup', 'aria-label': 'Face ' + part.label.toLowerCase(), children: part.opts.map(o =>
          jsx('button', { type: 'button', className: 'h-shape', role: 'radio', 'aria-checked': face[part.key] === o,
            'aria-label': FACE_OPT_LABEL[o] || o, title: FACE_OPT_LABEL[o] || o, 'data-on': face[part.key] === o,
            onClick: () => set({ [part.key]: o }),
            children: jsx(Face, { face: Object.assign({}, face, { [part.key]: o }), pk: props.pk, state: 'activity: idle', size: 30, className: 'hf-still' }) }, o)) })
      ] }, part.key)),
      jsxs('div', { className: 'h-facepart', children: [
        jsx('div', { className: 'h-faint h-tiny h-caps', children: 'Colour' }),
        jsx('input', { type: 'range', className: 'h-hue', min: 0, max: 359, value: face.hue, 'aria-label': 'Face colour',
          onChange: e => set({ hue: Number(e.target.value) }) })
      ] }),
      accent && jsxs('div', { className: 'h-facepart', children: [
        jsx('div', { className: 'h-faint h-tiny h-caps', children: 'Accent' }),
        jsx('input', { type: 'range', className: 'h-hue', min: 0, max: 359, value: face.hue2, 'aria-label': 'Accent colour',
          onChange: e => set({ hue2: Number(e.target.value) }) })
      ] })
    ] })
  ] })
}

function Initial(props) {
  const n = String(props.name || '?').trim()
  return jsx('span', { className: 'h-initial', 'aria-hidden': true, children: (n[0] || '?').toUpperCase() })
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
