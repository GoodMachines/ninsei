// ---------------------------------------------------------------------------------------------
// the builders: one editor shape for an agent's face and a person's avatar. A big live preview,
// layer tabs, and each option as a small live render of the whole thing with that option applied
// (colours as named swatches). Arrow keys move between tabs and within a layer; every option has a
// label; Randomize (and, for a person, Reset).
// ---------------------------------------------------------------------------------------------

// Layer tabs (the ARIA tabs pattern: arrows move and select, Home/End jump).
function LayerTabs(props) {
  const refs = useRef([])
  const i = Math.max(0, props.layers.findIndex(l => l.key === props.value))
  const go = j => {
    const n = props.layers.length
    const k = (j + n) % n
    props.onChange(props.layers[k].key)
    const el = refs.current[k]
    if (el) { el.focus(); try { el.scrollIntoView({ block: 'nearest', inline: 'nearest' }) } catch (_) { /* old engine */ } }
  }
  const onKey = e => {
    if (e.key === 'ArrowRight') go(i + 1)
    else if (e.key === 'ArrowLeft') go(i - 1)
    else if (e.key === 'Home') go(0)
    else if (e.key === 'End') go(props.layers.length - 1)
    else return
    e.preventDefault()
  }
  return jsx('div', { className: 'h-bld-tabs', role: 'tablist', 'aria-label': props.label, onKeyDown: onKey, children: props.layers.map((l, k) =>
    jsx('button', { type: 'button', role: 'tab', id: props.id + '-tab-' + l.key, 'aria-controls': props.id + '-panel',
      'aria-selected': k === i, tabIndex: k === i ? 0 : -1, 'data-on': k === i, ref: el => { refs.current[k] = el },
      onClick: () => props.onChange(l.key), children: l.label }, l.key)) })
}

// One choice per layer: a radio group whose arrow keys move the choice (and the focus) through the options.
function OptionGrid(props) {
  const refs = useRef([])
  const opts = props.options
  // the chosen option; none (a hue picked on the slider) leaves every swatch unchecked, the first one focusable
  const sel = opts.findIndex(o => o.id === props.value)
  const i = Math.max(0, sel)
  const pick = j => {
    const k = (j + opts.length) % opts.length
    props.onChange(opts[k].id)
    const el = refs.current[k]
    if (el) el.focus()
  }
  // how many options sit on a row, so up and down move by a row
  const perRow = () => {
    const a = refs.current[0], b = refs.current.find((el, k) => k > 0 && el && a && el.offsetTop > a.offsetTop + 2)
    return b ? refs.current.indexOf(b) : opts.length
  }
  const onKey = e => {
    if (e.key === 'ArrowRight') pick(sel + 1)
    else if (e.key === 'ArrowLeft') pick((sel < 0 ? 0 : sel) - 1)
    else if (e.key === 'ArrowDown') pick(Math.min(opts.length - 1, i + perRow()))
    else if (e.key === 'ArrowUp') pick(Math.max(0, i - perRow()))
    else if (e.key === 'Home') pick(0)
    else if (e.key === 'End') pick(opts.length - 1)
    else return
    e.preventDefault()
  }
  return jsx('div', { className: cx('h-bld-grid', props.swatch && 'h-bld-swatches'), role: 'radiogroup', 'aria-label': props.label, onKeyDown: onKey,
    children: opts.map((o, k) => jsxs('button', { type: 'button', role: 'radio', className: 'h-bld-opt', 'aria-checked': k === sel, 'data-on': k === sel,
      tabIndex: k === i ? 0 : -1, 'aria-label': o.label, title: o.label, ref: el => { refs.current[k] = el }, onClick: () => props.onChange(o.id),
      children: [o.render(), props.swatch && jsx('span', { className: 'h-bld-name', 'aria-hidden': true, children: o.label })] }, o.id)) })
}

// Things worn: any number, each a toggle button. Arrow keys move the focus; Space or Enter puts it on or off.
function ToggleGrid(props) {
  const refs = useRef([])
  const [at, setAt] = useState(0)
  const move = j => { const k = (j + props.options.length) % props.options.length; setAt(k); const el = refs.current[k]; if (el) el.focus() }
  const onKey = e => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') move(at + 1)
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') move(at - 1)
    else if (e.key === 'Home') move(0)
    else if (e.key === 'End') move(props.options.length - 1)
    else return
    e.preventDefault()
  }
  return jsx('div', { className: 'h-bld-grid', role: 'group', 'aria-label': props.label, onKeyDown: onKey, children: props.options.map((o, k) =>
    jsx('button', { type: 'button', className: 'h-bld-opt', 'aria-pressed': props.value.includes(o.id), 'data-on': props.value.includes(o.id),
      tabIndex: k === at ? 0 : -1, 'aria-label': o.label, title: o.label, ref: el => { refs.current[k] = el }, onFocus: () => setAt(k),
      onClick: () => props.onToggle(o.id), children: o.render() }, o.id)) })
}

// The preview pops on a spring when anything changes (nothing with reduced motion).
function usePreviewPop(dep) {
  const ref = useRef(null)
  const first = useRef(true)
  useEffect(() => {
    if (first.current) { first.current = false; return }
    const el = ref.current
    if (!el || motion.reduced()) return
    const s = motion.spring({ from: 0.94, to: 1, k: SPRING.pop.k, c: SPRING.pop.c, onUpdate: x => {
      el.style.transform = x === 1 ? '' : 'scale(' + x.toFixed(4) + ')'
    } })
    return () => s.stop()
  }, [dep])
  return ref
}

function BuilderShell(props) {
  const pop = usePreviewPop(props.version)
  // the wrapper is the size container: on a narrow column the preview and its buttons sit side by side
  return jsx('div', { className: 'h-bld-wrap', children: jsxs('div', { className: 'h-bld', id: props.id, tabIndex: props.id ? -1 : undefined, role: 'group', 'aria-label': props.label, children: [
    jsxs('div', { className: 'h-bld-side', children: [
      jsx('div', { className: 'h-bld-preview', ref: pop, children: props.preview }),
      jsxs('div', { className: 'h-actions h-bld-actions', children: props.actions })
    ] }),
    jsxs('div', { className: 'h-bld-main', children: [
      jsx(LayerTabs, { id: props.uid, label: props.label + ' layers', layers: props.layers, value: props.tab, onChange: props.setTab }),
      jsx('div', { className: 'h-bld-panel', role: 'tabpanel', id: props.uid + '-panel', 'aria-labelledby': props.uid + '-tab-' + props.tab, children: props.panel })
    ] })
  ] }) })
}

// ---- a person's avatar ------------------------------------------------------------------------------
const AV_LABEL = {
  oval: 'Oval', round: 'Round', square: 'Square', long: 'Long',
  short: 'Short', curly: 'Curly', long_hair: 'Long', buzz: 'Buzz cut', bun: 'Bun', locs: 'Locs', bob: 'Bob', wavy: 'Wavy',
  afro: 'Afro', ponytail: 'Ponytail', bald: 'Bald', swept: 'Swept',
  darkbrown: 'Dark brown', black: 'Black', brown: 'Brown', auburn: 'Auburn', ginger: 'Ginger', blonde: 'Blonde',
  platinum: 'Platinum', grey: 'Grey', ice: 'Ice blue',
  open: 'Open', smile: 'Smiling', almond: 'Almond', dot: 'Dots', sleepy: 'Sleepy',
  soft: 'Soft', straight: 'Straight', arched: 'Arched',
  grin: 'Grin', laugh: 'Laugh', flat: 'Straight', smirk: 'Smirk',
  none: 'None', stubble: 'Stubble', moustache: 'Moustache', short_beard: 'Short beard', full: 'Full beard',
  narrow: 'Narrow', broad: 'Broad',
  coat: 'Coat', hoodie: 'Hoodie', turtleneck: 'Turtleneck', jacket: 'Jacket', tee: 'T-shirt', scarf: 'Coat and scarf',
  navy: 'Navy', steel: 'Steel', slate: 'Slate', charcoal: 'Charcoal', glacier: 'Glacier', teal: 'Teal',
  'round-glasses': 'Round glasses', 'square-glasses': 'Square glasses', earrings: 'Earrings', beanie: 'Beanie',
  headphones: 'Headphones', headscarf: 'Headscarf'
}
function avOptLabel(key, id) {
  if (key === 'sk') return 'Skin ' + (id + 1) + (id === 0 ? ', lightest' : id === AV_SKIN - 1 ? ', darkest' : '')
  if (key === 'hs' && id === 'long') return 'Long'
  if (key === 'fh' && id === 'short') return 'Short beard'
  if (key === 'mo' && id === 'smile') return 'Smile'
  return AV_LABEL[id] || id
}
// the layers that are about the face show close-ups (the renderer says where the face is)
const AV_FACE_VIEW = AV_ART.views.face
const AV_LAYERS = [
  { key: 'sk', label: 'Skin', opts: Array.from({ length: AV_SKIN }, (_, i) => i), swatch: k => avSwatch('sk', k) },
  { key: 'fs', label: 'Face', opts: AV_FACES, view: AV_FACE_VIEW },
  { key: 'hs', label: 'Hair', opts: AV_HAIR },
  { key: 'hc', label: 'Hair colour', opts: AV_HAIR_COLOURS, swatch: k => avSwatch('hc', k) },
  { key: 'ey', label: 'Eyes', opts: AV_EYES, view: AV_FACE_VIEW },
  { key: 'br', label: 'Brows', opts: AV_BROWS, view: AV_FACE_VIEW },
  { key: 'mo', label: 'Mouth', opts: AV_MOUTHS, view: AV_FACE_VIEW },
  { key: 'fh', label: 'Facial hair', opts: AV_FACIAL, view: AV_FACE_VIEW },
  { key: 'bd', label: 'Build', opts: AV_BUILDS },
  { key: 'tp', label: 'Top', opts: AV_TOPS },
  { key: 'tc', label: 'Top colour', opts: AV_TOP_COLOURS, swatch: k => avSwatch('tc', k) },
  { key: 'ac', label: 'Extras', opts: AV_ACCS }
]

// props: value (a clean avatar), onChange(avatar), id, name
function AvatarEditor(props) {
  const a = cleanAvatar(props.value) || AV_DEFAULT
  const [tab, setTab] = useState('hs')
  const uid = (props.id || 'h-av') + '-b'
  const set = patch => props.onChange(cleanAvatar(Object.assign({}, a, patch)))
  const layer = AV_LAYERS.find(l => l.key === tab) || AV_LAYERS[0]
  const thumb = patch => jsx(PersonAvatar, { avatar: Object.assign({}, a, patch), size: 64, view: layer.view, className: 'h-bld-thumb' })
  const panel = layer.key === 'ac'
    ? jsx(ToggleGrid, { label: 'Extras', value: a.ac, options: layer.opts.map(o => ({ id: o, label: avOptLabel('ac', o),
        render: () => thumb({ ac: a.ac.includes(o) ? a.ac : a.ac.concat([o]) }) })),
      onToggle: o => set({ ac: a.ac.includes(o) ? a.ac.filter(x => x !== o)
        : a.ac.filter(x => !AV_ACC_GROUPS.some(g => g.includes(o) && g.includes(x))).concat([o]) }) })
    : jsx(OptionGrid, { label: layer.label, value: a[layer.key], swatch: !!layer.swatch, onChange: v => set({ [layer.key]: v }),
        options: layer.opts.map(o => ({ id: o, label: avOptLabel(layer.key, o),
          render: () => layer.swatch ? jsx('span', { className: 'h-bld-swatch', style: { background: layer.swatch(o) } }) : thumb({ [layer.key]: o }) })) })
  return jsx(BuilderShell, { id: props.id, uid, label: 'Avatar builder', version: JSON.stringify(a), tab, setTab,
    layers: AV_LAYERS, panel,
    preview: jsx(PersonAvatar, { avatar: a, size: 128, label: (props.name ? props.name + '’s' : 'Your') + ' avatar' }),
    actions: [
      jsx(K.Button, { variant: 'secondary', size: 'sm', onClick: () => props.onChange(randomAvatar()), children: 'Randomize' }, 'r'),
      jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: () => props.onChange(cleanAvatar(AV_DEFAULT)), children: 'Reset' }, 's')
    ] })
}

// ---- an agent's face --------------------------------------------------------------------------------
const FACE_LAYERS = [
  { key: 'shape', label: 'Shape', opts: SHAPES },
  { key: 'eyes', label: 'Eyes', opts: FACE_EYES },
  { key: 'mouth', label: 'Mouth', opts: FACE_MOUTHS },
  { key: 'acc', label: 'Extra', opts: FACE_ACCS },
  { key: 'pattern', label: 'Cheeks', opts: FACE_PATTERNS },
  { key: 'colour', label: 'Colour' }
]
// a few named hues for the colour swatches; the sliders reach every other one
const FACE_HUES = [['Ice', 215], ['Glacier', 235], ['Violet', 285], ['Rose', 340], ['Ember', 30], ['Amber', 75], ['Moss', 130], ['Teal', 180]]

function randomFace(face, rand) {
  const r = rand || Math.random
  const pick = a => a[Math.floor(r() * a.length) % a.length]
  return Object.assign({}, face, { hue: Math.floor(r() * 360), hue2: Math.floor(r() * 360), shape: pick(SHAPES), eyes: pick(FACE_EYES),
    mouth: pick(FACE_MOUTHS), acc: pick(FACE_ACCS), pattern: pick(FACE_PATTERNS) })
}

function FaceColours(props) {
  const face = props.face
  const swatch = (key, label) => jsx(OptionGrid, { label, swatch: true, value: FACE_HUES.find(h => h[1] === face[key]) ? face[key] : null,
    onChange: v => props.set({ [key]: v }),
    options: FACE_HUES.map(([name, h]) => ({ id: h, label: name, render: () => jsx('span', { className: 'h-bld-swatch',
      style: { background: oklchToHex(0.72, 0.14, h) } }) })) })
  return jsxs('div', { className: 'h-col', style: { gap: 10 }, children: [
    jsx('div', { className: 'h-faint h-tiny h-caps', children: 'Colour' }),
    swatch('hue', 'Face colour'),
    jsx('input', { type: 'range', className: 'h-hue', min: 0, max: 359, value: face.hue, 'aria-label': 'Face colour, any hue',
      onChange: e => props.set({ hue: Number(e.target.value) }) }),
    jsx('div', { className: 'h-faint h-tiny h-caps', children: 'Accent (extras and cheeks)' }),
    swatch('hue2', 'Accent colour'),
    jsx('input', { type: 'range', className: 'h-hue', min: 0, max: 359, value: face.hue2, 'aria-label': 'Accent colour, any hue',
      onChange: e => props.set({ hue2: Number(e.target.value) }) })
  ] })
}
