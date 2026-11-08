// ---------------------------------------------------------------------------------------------
// faces: a pixel-art head per agent (ui/12_pixel.js draws it). Shape, parts and hue are the agent's own
// choice (or derived from its pubkey); the head glows in its hue like a hologram, with a neon edge and a
// faint dark hairline (CSS) so it reads
// on light and dark themes alike. Eyes and mouth follow the agent's presence state: the state picks
// which frames are drawn, and CSS keyframes swap or step them (blinking, talking, scanning; no JS per
// frame). A state change gives the whole face a small spring "pop".
// ---------------------------------------------------------------------------------------------

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
  const fr = pxAgentFrames(state, expr)
  const art = pxAgent(f, fr.eyes, fr.mouth)
  const col = art.colours
  const g = (cls, paths, key, style) => jsx('g', { className: cls, style, children: pxPathEls(paths, col, key) }, key)

  return jsx('span', {
    ref, className: cx('hf', 'hf-px', props.className), 'data-state': state, 'data-expr': expr || undefined,
    'data-size': size <= 20 ? 's' : size < 48 ? 'm' : 'l',
    // --gh: the glow's hue, for the theme-aware glow in CSS (col.glow is oklch(0.8 0.15 hue))
    style: { width: size, height: size, '--glow': col.glow + 'a6', '--glow2': col.glow + '40', '--gh': f.hue, '--gs': Math.max(1, Math.round(size / 20)) + 'px' },
    role: 'img', 'aria-label': (props.name ? props.name + ', ' : '') + STATE_LABEL[state],
    children: jsxs('svg', { viewBox: '0 0 64 64', width: size, height: size, 'aria-hidden': true,
      shapeRendering: pxCrisp(size) ? 'crispEdges' : 'auto', children: [
      jsxs('g', { className: 'hf-head', children: [
        jsx('g', { className: 'pf-under', children: pxPathEls(art.under, col, 'u') }),
        g('pf-base', art.base, 'b'),
        jsx('g', { className: 'pf-scan', children: pxPathEls(art.scan, { n: '#02050a' }, 's') }),
        jsxs('g', { className: 'hf-eyes', style: { animationDelay: delay }, children: [
          g('pf-eo', art.eyes, 'eo', { animationDelay: delay }),
          art.blink && g('pf-ec', art.blink, 'ec', { animationDelay: delay })
        ] }),
        jsxs('g', { className: 'pf-mouth', children: [
          g('pf-mr', art.mouth, 'mr'),
          state === 'speaking' && !expr && g('pf-mt', art.talk, 'mt')
        ] }),
        g('pf-acc', art.acc, 'a')
      ] }),
      state === 'waiting' && jsxs('g', { className: 'hf-clock', children: [
        jsx('circle', { cx: 54, cy: 10, r: 8.5 }),
        jsx('path', { className: 'hf-hand', d: 'M54 10V4.5' }),
        jsx('path', { d: 'M54 10h4' })
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
  // what the tokens buy, in replies, next to the tokens themselves
  const label = `${fmtTokens(b.used)} of ${fmtTokens(b.limit)} tokens today (${repliesWords(dailyReplies(b))})`
  return jsx(Ring, { pct, size: props.size || 18, stroke: props.stroke, tone, label, title: label, children: props.children })
}
