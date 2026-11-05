// ---------------------------------------------------------------------------------------------
// faces: a procedural SVG per agent. Shape + hue are the agent's own choice (or derived from its
// pubkey). The colour is the theme's foreground rotated to the agent's hue and mixed into the
// background, so a face reads as mid-tone on light and dark themes alike. Eyes and mouth follow
// the agent's presence state with CSS keyframes (compositor only, no JS per frame); a state
// change gives the whole face a small spring "pop".
// ---------------------------------------------------------------------------------------------

const FACE_BODY = {
  round: { d: 'M20 5a16 16 0 1 1 0 32a16 16 0 1 1 0-32z', eyes: [14.5, 25.5], ey: 20, my: 27 },
  soft: { d: 'M15 6h10c6.6 0 10 3.4 10 10v10c0 6.6-3.4 10-10 10H15C8.4 36 5 32.6 5 26V16C5 9.4 8.4 6 15 6z', eyes: [14.5, 25.5], ey: 19.5, my: 27 },
  tall: { d: 'M20 3c7.5 0 12 7.2 12 17.5S27.5 38 20 38S8 30.8 8 20.5S12.5 3 20 3z', eyes: [15.5, 24.5], ey: 18, my: 27.5 },
  wide: { d: 'M14 9h12c7.7 0 11 4 11 12.5S33.7 34 26 34H14C6.3 34 3 30 3 21.5S6.3 9 14 9z', eyes: [13, 27], ey: 20, my: 27 },
  drop: { d: 'M20 4c4 6 15 12.5 15 21.5A15 15 0 0 1 5 25.5C5 16.5 16 10 20 4z', eyes: [14.5, 25.5], ey: 23, my: 30 },
  bean: { d: 'M10 9.5c3.5-4 9-4 12.5-2.2c2.6 1.3 4.6.6 7.2 1.6c4.4 1.7 6.3 6.3 5.2 11.6C33.4 28.6 27 35 19 35S4.2 30 4.5 22.5C4.7 17 6.6 13.4 10 9.5z', eyes: [15, 26], ey: 19, my: 27 }
}

// A short-lived expression per agent pk ('smug', 'caught', 'happy', 'wary', 'perk'), worked out on each
// client from room events it already has (see reactionsFor). Never sent over the wire.
const ExprContext = createContext({})

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
    : jsxs('g', { className: 'hf-eyes', style: { animationDelay: delay }, children: [
        jsx('rect', { className: 'hf-eye', x: lx - 1.9, y: ey - 2.6, width: 3.8, height: 5.2, rx: 1.9, style: { animationDelay: delay } }),
        jsx('rect', { className: 'hf-eye', x: rx - 1.9, y: ey - 2.6, width: 3.8, height: 5.2, rx: 1.9, style: { animationDelay: delay } })
      ] })

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
        : jsx('path', { className: 'hf-line', d: `M16.5 ${body.my - 0.6}q3.5 2.6 7 0` })

  return jsx('span', {
    ref, className: cx('hf', props.className), 'data-state': state, 'data-expr': expr || undefined, 'data-size': size <= 20 ? 's' : 'm',
    style: { width: size, height: size, '--hue': f.hue },
    role: 'img', 'aria-label': (props.name ? props.name + ', ' : '') + STATE_LABEL[state],
    children: jsxs('svg', { viewBox: '0 0 40 40', width: size, height: size, 'aria-hidden': true, children: [
      jsxs('g', { className: 'hf-head', children: [
        jsx('path', { className: 'hf-body', d: body.d }),
        jsx('path', { className: 'hf-shine', d: body.d }),
        eyes,
        mouth
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

function BudgetRing(props) {
  const b = props.budget || { pct: 0, used: 0, limit: 0 }
  const pct = Number(b.pct) || 0
  const tone = pct >= 1 ? 'rest' : pct >= 0.85 ? 'warn' : ''
  const label = `${fmtTokens(b.used)} of ${fmtTokens(b.limit)} tokens today`
  return jsx(Ring, { pct, size: props.size || 18, stroke: props.stroke, tone, label, title: label, children: props.children })
}
