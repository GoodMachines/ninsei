// ---------------------------------------------------------------------------------------------
// small shared parts: form rows, segmented picker, interest chips, face picker, avatars
// ---------------------------------------------------------------------------------------------

function Field(props) {
  return jsxs('div', { className: 'h-field', children: [
    props.label && jsx('label', { htmlFor: props.id, children: props.label }),
    props.children,
    props.hint && jsx('div', { className: 'h-hint', children: props.hint })
  ] })
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

function FacePicker(props) {
  const face = faceFor(props.value, props.pk)
  const set = patch => props.onChange(Object.assign({}, face, patch))
  return jsxs('div', { className: 'h-row', style: { alignItems: 'flex-start', gap: 16 }, children: [
    jsx(Face, { face, pk: props.pk, state: props.previewState || 'activity: idle', size: 64, name: props.name }),
    jsxs('div', { className: 'h-col h-grow', children: [
      jsx('div', { className: 'h-shapes', role: 'radiogroup', 'aria-label': 'Face shape', children: SHAPES.map(s =>
        jsx('button', { type: 'button', className: 'h-shape', role: 'radio', 'aria-checked': face.shape === s, 'aria-label': s,
          'data-on': face.shape === s, onClick: () => set({ shape: s }),
          children: jsx(Face, { face: { hue: face.hue, shape: s }, pk: props.pk, state: 'activity: idle', size: 30 }) }, s)) }),
      jsx('input', { type: 'range', className: 'h-hue', min: 0, max: 359, value: face.hue, 'aria-label': 'Face colour',
        onChange: e => set({ hue: Number(e.target.value) }) })
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

// A toy someone shared: never loaded until the viewer presses Run, and then only inside an
// opaque-origin sandbox (scripts on, no same-origin, no popups, no top navigation).
function ToyFrame(props) {
  return jsx('div', { className: 'h-frame', 'data-tall': !!props.tall, children: jsx(K.Toy, { html: props.html, title: props.title || 'Shared toy' }) })
}

// A modal with the kit's own dialog. `footer` sits at the bottom right.
function Modal(props) {
  return jsx(K.Dialog, { open: props.open, onClose: props.onClose, title: props.title, description: props.description,
    wide: props.wide, footer: props.footer, children: props.children })
}
