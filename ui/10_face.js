// ---------------------------------------------------------------------------------------------
// faces: a procedural SVG per agent. Shape + hue are the agent's own choice (or derived from its
// pubkey). The colour is the theme's foreground rotated to the agent's hue and mixed into the
// background, so a face reads as mid-tone on light and dark themes alike. Eyes and mouth follow
// the agent's presence state with CSS keyframes (compositor only, no JS per frame); a state
// change gives the whole face a small spring "pop".
// ---------------------------------------------------------------------------------------------

// eyes/ey/my: eye x's, eye line, mouth line. top: the head's top at x=20. sides: its edges at eye level.
const FACE_BODY = {
  round: { d: 'M20 5a16 16 0 1 1 0 32a16 16 0 1 1 0-32z', eyes: [14.5, 25.5], ey: 20, my: 27, top: 5, sides: [4.5, 35.5] },
  soft: { d: 'M15 6h10c6.6 0 10 3.4 10 10v10c0 6.6-3.4 10-10 10H15C8.4 36 5 32.6 5 26V16C5 9.4 8.4 6 15 6z', eyes: [14.5, 25.5], ey: 19.5, my: 27, top: 6, sides: [5, 35] },
  tall: { d: 'M20 3c7.5 0 12 7.2 12 17.5S27.5 38 20 38S8 30.8 8 20.5S12.5 3 20 3z', eyes: [15.5, 24.5], ey: 18, my: 27.5, top: 3, sides: [8.3, 31.7] },
  wide: { d: 'M14 9h12c7.7 0 11 4 11 12.5S33.7 34 26 34H14C6.3 34 3 30 3 21.5S6.3 9 14 9z', eyes: [13, 27], ey: 20, my: 27, top: 9, sides: [3.2, 36.8] },
  drop: { d: 'M20 4c4 6 15 12.5 15 21.5A15 15 0 0 1 5 25.5C5 16.5 16 10 20 4z', eyes: [14.5, 25.5], ey: 23, my: 30, top: 4, sides: [5.6, 34.4] },
  bean: { d: 'M10 9.5c3.5-4 9-4 12.5-2.2c2.6 1.3 4.6.6 7.2 1.6c4.4 1.7 6.3 6.3 5.2 11.6C33.4 28.6 27 35 19 35S4.2 30 4.5 22.5C4.7 17 6.6 13.4 10 9.5z', eyes: [15, 26], ey: 19, my: 27, top: 7, sides: [4.8, 35.3] }
}

// The chosen eyes, drawn as .hf-eye so blinking, scanning and the state squints still apply.
function faceEyes(kind, lx, rx, ey, delay) {
  const st = { animationDelay: delay }
  const pair = make => [make(lx, 'l'), make(rx, 'r')]
  if (kind === 'visor') {
    return [jsx('rect', { className: 'hf-eye', x: lx - 3.4, y: ey - 1.9, width: rx - lx + 6.8, height: 3.8, rx: 1.9, style: st }, 'v')]
  }
  if (kind === 'round') return pair((x, k) => jsx('circle', { className: 'hf-eye', cx: x, cy: ey, r: 2.5, style: st }, k))
  if (kind === 'sleepy') return pair((x, k) => jsx('rect', { className: 'hf-eye', x: x - 2.3, y: ey - 0.4, width: 4.6, height: 2.2, rx: 1.1, style: st }, k))
  if (kind === 'wide') {
    return pair((x, k) => jsxs('g', { children: [
      jsx('ellipse', { className: 'hf-eye', cx: x, cy: ey, rx: 2.5, ry: 3.3, style: st }),
      jsx('circle', { className: 'hf-glint', cx: x + 0.9, cy: ey - 1.2, r: 0.8 })
    ] }, k))
  }
  return pair((x, k) => jsx('rect', { className: 'hf-eye', x: x - 1.9, y: ey - 2.6, width: 3.8, height: 5.2, rx: 1.9, style: st }, k))
}

// The resting mouth (speaking, reactions, waiting and errors draw their own).
function faceMouth(kind, my) {
  if (kind === 'flat') return jsx('path', { className: 'hf-line', d: `M17.5 ${my}h5` })
  if (kind === 'grin') return jsx('path', { className: 'hf-mouth', d: `M15.8 ${my - 1.2}q4.2 5 8.4 0z` })
  if (kind === 'cat') return jsx('path', { className: 'hf-line', d: `M16.4 ${my - 0.8}q1.8 2.2 3.6 0q1.8 2.2 3.6 0` })
  if (kind === 'o') return jsx('ellipse', { className: 'hf-mouth', cx: 20, cy: my, rx: 1.5, ry: 1.7 })
  return jsx('path', { className: 'hf-line', d: `M16.5 ${my - 0.6}q3.5 2.6 7 0` })
}

// Cheek marks in the second colour, kept well inside every body shape.
function facePattern(kind, b) {
  const [lx, rx] = b.eyes
  const cy = (b.ey + b.my) / 2 + 0.6
  if (kind === 'blush') {
    return [jsx('ellipse', { className: 'hf-acc hf-blush', cx: lx - 1.6, cy, rx: 2.4, ry: 1.4 }, 'l'),
      jsx('ellipse', { className: 'hf-acc hf-blush', cx: rx + 1.6, cy, rx: 2.4, ry: 1.4 }, 'r')]
  }
  if (kind === 'freckles') {
    const dots = []
    for (const [x, s] of [[lx, -1], [rx, 1]]) {
      for (const [dx, dy] of [[-1.6, 0], [0.4, -0.9], [0.9, 1]]) dots.push(jsx('circle', { className: 'hf-acc', cx: x + s * dx, cy: cy + dy, r: 0.55 }, x + ':' + dx))
    }
    return dots
  }
  if (kind === 'spots') {
    return [jsx('circle', { className: 'hf-acc hf-spot', cx: lx - 2.6, cy: b.ey - 5.4, r: 1.9 }, 'a'),
      jsx('circle', { className: 'hf-acc hf-spot', cx: rx + 2.2, cy: b.ey - 4.2, r: 1.3 }, 'b'),
      jsx('circle', { className: 'hf-acc hf-spot', cx: rx + 0.6, cy: b.my + 3.2, r: 1.1 }, 'c')]
  }
  return null
}

// Something worn, in the second colour. Drawn after the body so it sits on top.
function faceAcc(kind, b) {
  const [lx, rx] = b.eyes
  const [sl, sr] = b.sides
  const t = b.top
  const ey = b.ey
  if (kind === 'antenna') {
    return [jsx('path', { className: 'hf-acc-line', d: `M20 ${t + 0.6}V${t - 4.4}` }, 's'), jsx('circle', { className: 'hf-acc', cx: 20, cy: t - 5.6, r: 1.9 }, 'b')]
  }
  if (kind === 'glasses') {
    return [jsx('circle', { className: 'hf-acc-line', cx: lx, cy: ey, r: 3.7 }, 'l'), jsx('circle', { className: 'hf-acc-line', cx: rx, cy: ey, r: 3.7 }, 'r'),
      jsx('path', { className: 'hf-acc-line', d: `M${lx + 3.7} ${ey}q${(rx - lx) / 2 - 3.7} -1.4 ${rx - lx - 7.4} 0` }, 'b')]
  }
  if (kind === 'headphones') {
    return [jsx('path', { className: 'hf-acc-line hf-thick', d: `M${sl + 0.6} ${ey}C${sl} ${t - 6} ${sr} ${t - 6} ${sr - 0.6} ${ey}` }, 'band'),
      jsx('rect', { className: 'hf-acc', x: sl - 2.2, y: ey - 3.4, width: 4.4, height: 6.8, rx: 1.8 }, 'l'),
      jsx('rect', { className: 'hf-acc', x: sr - 2.2, y: ey - 3.4, width: 4.4, height: 6.8, rx: 1.8 }, 'r')]
  }
  if (kind === 'halo') return jsx('ellipse', { className: 'hf-acc-line hf-thick', cx: 20, cy: t - 3.6, rx: 7.5, ry: 2.1 })
  if (kind === 'sprout') {
    return [jsx('path', { className: 'hf-acc-line', d: `M20 ${t + 0.8}q-.4 -2.6 0 -4.6` }, 's'),
      jsx('path', { className: 'hf-acc', d: `M20 ${t - 3.6}q-3 -3.6 -6.4 -1.2q3 3 6.4 1.2z` }, 'l'),
      jsx('path', { className: 'hf-acc', d: `M20 ${t - 3.8}q2.4 -3 5.2 -1q-2.4 2.6 -5.2 1z` }, 'r')]
  }
  if (kind === 'horns') {
    const y = t + 2.6
    return [jsx('path', { className: 'hf-acc', d: `M13 ${y + 0.8}l-1.6 -6.2l5 3.6z` }, 'l'), jsx('path', { className: 'hf-acc', d: `M27 ${y + 0.8}l1.6 -6.2l-5 3.6z` }, 'r')]
  }
  if (kind === 'bow') {
    const x = 27.5, y = t + 3.4
    return [jsx('path', { className: 'hf-acc', d: `M${x} ${y}l-4.6 -2.8v5.6z` }, 'l'), jsx('path', { className: 'hf-acc', d: `M${x} ${y}l4.6 -2.8v5.6z` }, 'r'),
      jsx('circle', { className: 'hf-acc hf-knot', cx: x, cy: y, r: 1.3 }, 'k')]
  }
  return null
}

// A short-lived expression per agent pk ('smug', 'caught', 'happy', 'wary', 'perk'), worked out on each
// client from room events it already has (see reactionsFor). Never sent over the wire.
const ExprContext = createContext({})

// What the engine says each person looks like, from the snapshot: { people: {pk: {face?, av?}}, show: bool }.
// `av` is a picture's version (the picture is fetched on its own); `show` is the "Show profile pictures" switch.
const PeopleContext = createContext({ people: {}, show: true })

// A person's built face: the same drawings as an agent's, but still (no blinking, no breathing, no state) and in a
// plain circle with no tint, so a person never reads as an agent. Agents also keep their bubble and "X's agent" label.
function PersonFace(props) {
  const size = props.size || 28
  return jsx('span', { className: cx('h-pface', props.className), 'aria-hidden': true, style: { width: size, height: size },
    children: jsx(Face, { face: props.face, pk: props.pk, state: 'activity: idle', size: Math.round(size * 0.86), className: 'hf-still' }) })
}

function Face(props) {
  const f = faceFor(props.face, props.pk)
  const body = FACE_BODY[f.shape] || FACE_BODY.round
  const state = stateWord(props.state)
  const exprs = useContext(ExprContext)
  const expr = (state !== 'absent' && state !== 'error' && exprs[props.pk]) || ''
  const size = props.size || 40
  const ref = useRef(null)
  const first = useRef(true)

  // a new state: the face gives a small spring "pop" (scale dips, then settles)
  useEffect(() => {
    if (first.current) { first.current = false; return }
    const el = ref.current
    if (!el || motion.reduced()) return
    const s = motion.spring({ from: 0.86, to: 1, k: SPRING.pop.k, c: SPRING.pop.c, onUpdate: x => {
      el.style.transform = x === 1 ? '' : 'scale(' + x.toFixed(4) + ')'
    } })
    return () => s.stop()
  }, [state, expr])

  // a stable per-agent offset so two faces in a list never blink in unison
  const seed = parseInt(String(props.pk || '7f').slice(-3), 16) || 0
  const delay = -((seed % 4700) / 1000).toFixed(2) + 's'
  const [lx, rx] = body.eyes
  const ey = body.ey

  const eyes = state === 'error'
    ? jsxs('g', { className: 'hf-xeyes', children: [
        jsx('path', { d: `M${lx - 2} ${ey - 2}l4 4m0-4l-4 4` }),
        jsx('path', { d: `M${rx - 2} ${ey - 2}l4 4m0-4l-4 4` })
      ] })
    : jsx('g', { className: 'hf-eyes', style: { animationDelay: delay }, children: faceEyes(f.eyes, lx, rx, ey, delay) })

  const my = body.my
  const mouth = state === 'speaking'
    ? jsx('ellipse', { className: 'hf-mouth hf-talk', cx: 20, cy: body.my, rx: 2.6, ry: 1.8 })
    : expr === 'smug' ? jsx('path', { className: 'hf-line', d: `M16.8 ${my}q3 1.6 6.6 -1.2` })
    : expr === 'caught' ? jsx('ellipse', { className: 'hf-mouth', cx: 20, cy: my, rx: 1.6, ry: 1.9 })
    : expr === 'happy' ? jsx('path', { className: 'hf-mouth', d: `M15.8 ${my - 1.2}q4.2 5 8.4 0z` })
    : expr === 'wary' ? jsx('path', { className: 'hf-line', d: `M17.2 ${my + 0.4}h5.6` })
    : state === 'error'
      ? jsx('path', { className: 'hf-line', d: `M16.5 ${body.my + 1}q3.5 -2.4 7 0` })
      : state === 'waiting' || state === 'absent'
        ? jsx('path', { className: 'hf-line', d: `M17.5 ${body.my}h5` })
        : faceMouth(f.mouth, my)

  return jsx('span', {
    ref, className: cx('hf', props.className), 'data-state': state, 'data-expr': expr || undefined, 'data-size': size <= 20 ? 's' : 'm',
    style: { width: size, height: size, '--hue': f.hue, '--hue2': f.hue2 },
    role: 'img', 'aria-label': (props.name ? props.name + ', ' : '') + STATE_LABEL[state],
    children: jsxs('svg', { viewBox: '0 0 40 40', width: size, height: size, 'aria-hidden': true, children: [
      jsxs('g', { className: 'hf-head', children: [
        jsx('path', { className: 'hf-body', d: body.d }),
        jsx('path', { className: 'hf-shine', d: body.d }),
        facePattern(f.pattern, body),
        eyes,
        mouth,
        faceAcc(f.acc, body)
      ] }),
      state === 'waiting' && jsxs('g', { className: 'hf-clock', children: [
        jsx('circle', { cx: 33, cy: 7, r: 5.2 }),
        jsx('path', { className: 'hf-hand', d: 'M33 7V4.2' }),
        jsx('path', { d: 'M33 7h2' })
      ] })
    ] })
  })
}

// ---------------------------------------------------------------------------------------------
// rings: the budget ring and the countdown ring share one springy arc
// ---------------------------------------------------------------------------------------------

function Ring(props) {
  const size = props.size || 18
  const stroke = props.stroke || 2.5
  const r = (size - stroke) / 2
  const C = 2 * Math.PI * r
  const arc = useRef(null)
  const pct = clamp(Number(props.pct) || 0, 0, 1)
  useSpring(pct, Object.assign({ from: props.from != null ? props.from : 0 }, props.spring || SPRING.ring), x => {
    if (arc.current) arc.current.style.strokeDashoffset = String(C * (1 - clamp(x, 0, 1)))
  })
  return jsxs('span', { className: cx('h-ring', props.className), 'data-tone': props.tone || '', style: { width: size, height: size },
    title: props.title, role: props.label ? 'img' : undefined, 'aria-label': props.label, children: [
      jsxs('svg', { width: size, height: size, viewBox: `0 0 ${size} ${size}`, 'aria-hidden': true, children: [
        jsx('circle', { className: 'h-ring-track', cx: size / 2, cy: size / 2, r, strokeWidth: stroke }),
        jsx('circle', { ref: arc, className: 'h-ring-arc', cx: size / 2, cy: size / 2, r, strokeWidth: stroke,
          strokeDasharray: C, strokeDashoffset: C, transform: `rotate(-90 ${size / 2} ${size / 2})` })
      ] }),
      props.children != null && jsx('span', { className: 'h-ring-label', children: props.children })
    ] })
}

// What other people's messages cost today, for the budget card, and the plain words when their share runs out.
const OTHERS_SPENT = 'Others used their share today; your agent still answers you.'
function othersLine(b) {
  const o = b && b.others
  return o && o.used > 0 ? fmtTokens(o.used) + ' of it by others' : ''
}

function BudgetRing(props) {
  const b = props.budget || { pct: 0, used: 0, limit: 0 }
  const pct = Number(b.pct) || 0
  const tone = pct >= 1 ? 'rest' : pct >= 0.85 ? 'warn' : ''
  const label = `${fmtTokens(b.used)} of ${fmtTokens(b.limit)} tokens today`
  return jsx(Ring, { pct, size: props.size || 18, stroke: props.stroke, tone, label, title: label, children: props.children })
}
