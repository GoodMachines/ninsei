// ---------------------------------------------------------------------------------------------
// the builders: the agent's face editor (a big live preview, layer tabs, each option a small live render, colours as
// named swatches; arrow keys move between tabs and within a layer; every option has a label; Randomize) and the
// person's PresetPicker (a preview and a grid of premade portraits).
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
  return jsx('div', { className: cx('h-bld-grid', props.swatch && 'h-bld-swatches', props.className), role: 'radiogroup', 'aria-label': props.label, onKeyDown: onKey,
    children: opts.map((o, k) => jsxs('button', { type: 'button', role: 'radio', className: 'h-bld-opt', 'aria-checked': k === sel, 'data-on': k === sel,
      tabIndex: k === i ? 0 : -1, 'aria-label': o.label, title: o.label, ref: el => { refs.current[k] = el }, onClick: () => props.onChange(o.id),
      children: [o.render(), props.swatch && jsx('span', { className: 'h-bld-name', 'aria-hidden': true, children: o.label })] }, o.id)) })
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

// ---- a person's portrait ----------------------------------------------------------------------------
// props: value (a clean avatar or null), onChange(avatar), id, name. Nothing is chosen for anyone: until they pick
// (or press Surprise me, which is them picking) the preview shows their initial and no portrait is set. The grid is
// one radio group over PERSON_PRESETS; each option is labelled from its portrait's alt text.
function PresetPicker(props) {
  const a = cleanAvatar(props.value)
  const preset = a && presetById(a.p)
  const pop = usePreviewPop(a ? a.p : '')
  const choose = id => props.onChange({ v: 1, p: id })
  const options = PERSON_PRESETS.map(p => ({ id: p.id, label: p.alt,
    render: () => jsx(PersonAvatar, { avatar: { v: 1, p: p.id }, size: 56, className: 'h-pp-thumb' }) }))
  return jsx('div', { className: 'h-bld-wrap', children: jsxs('div', { className: 'h-pp', id: props.id, tabIndex: props.id ? -1 : undefined, role: 'group', 'aria-label': 'Choose your portrait', children: [
    jsxs('div', { className: 'h-pp-side', children: [
      jsx('div', { className: 'h-pp-preview', ref: pop, children: preset
        ? jsx(PersonAvatar, { avatar: a, size: 128, describe: true })
        : jsx('span', { className: 'h-pp-none', children: jsx(Initial, { name: props.name, size: 128 }) }) }),
      jsx('div', { className: 'h-faint h-tiny h-pp-cap', 'aria-live': 'polite', children: preset ? preset.alt : 'No portrait chosen' }),
      jsx(K.Button, { variant: 'secondary', size: 'sm', onClick: () => choose(surprisePreset(a ? a.p : '')), children: 'Surprise me' })
    ] }),
    jsx(OptionGrid, { label: 'Portraits', className: 'h-pp-grid', value: a ? a.p : null, options, onChange: choose })
  ] }) })
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
