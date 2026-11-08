// ---------------------------------------------------------------------------------------------
// the Scanner card style: the card is an old monitor's screen, edge to edge, with no bezel around it. It
// shows a pixel nebula grown from the agent's key (so each agent's is its own and never changes), in the
// agent's colours, drifting very slowly. Cyan grid bands, brackets and glowing readouts sit on the glass;
// every readout is the same data the Member card shows. A small status light sits by the Status (or "In
// the room") readout: green when online, amber when away, red when the key check failed.
//
// The field is a small grid of numbers (nebulaField, pure, runs in node for the tests), coloured through a
// lookup table and put on a canvas a few cells wide that CSS scales up with hard pixel edges. A blurred
// copy of the bright cells, blended on top, is the bloom. The drift redraws about 15 times a second, only
// while the card is on screen and the page is visible, and never with reduced motion.
// ---------------------------------------------------------------------------------------------

// The field's size in cells: the card's own 1.6:1 (the screen is the whole card), so cells stay square.
const SCAN_W = 48
const SCAN_H = 30
// Layout in % of the card, kept in step with the .h-scan rules in 20_style.js (the export reads these):
// the side inset of the readouts, the grid bands' height, and the hero's bracket box (right edge and width in
// % of the card's width, top in % of its height; it is square).
const SCAN_PAD = 7.5
const SCAN_BAND = 10
const SCAN_BOX = { right: 7.5, top: 17, size: 30 }
// The status light's colours, shared by the card (CSS --led) and the export.
const SCAN_LEDS = { green: [0.86, 0.21, 145], amber: [0.83, 0.16, 75], red: [0.66, 0.24, 27] }

// ---- the field ---------------------------------------------------------------------------------

// FNV-1a over the key: the nebula's seed. Any value gives a number; the same key always the same one.
function scanSeed(pk) {
  const s = typeof pk === 'string' ? pk : String(pk == null ? '' : pk)
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) }
  return h >>> 0
}

// A lattice point's value in [0, 1), from integer coordinates and a seed.
function scanHash(x, y, s) {
  let h = Math.imul(x | 0, 0x27d4eb2d) ^ Math.imul(y | 0, 0x165667b1) ^ (s | 0)
  h = Math.imul(h ^ (h >>> 15), 0x85ebca6b)
  h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35)
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296
}

// Value noise: the four corners of the cell, eased.
function scanNoise(x, y, s) {
  const xi = Math.floor(x)
  const yi = Math.floor(y)
  const fx = x - xi
  const fy = y - yi
  const u = fx * fx * (3 - 2 * fx)
  const v = fy * fy * (3 - 2 * fy)
  const a = scanHash(xi, yi, s)
  const b = scanHash(xi + 1, yi, s)
  const c = scanHash(xi, yi + 1, s)
  const d = scanHash(xi + 1, yi + 1, s)
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v
}

// A few octaves (four unless said), each turned about 37 degrees so the lattice never lines up.
function scanFbm(x, y, s, oct) {
  let sum = 0
  let amp = 0.5
  let total = 0
  const n = oct || 4
  for (let o = 0; o < n; o++) {
    sum += amp * scanNoise(x, y, s + o * 1013)
    total += amp
    const nx = 1.6 * x - 1.2 * y + 17.3
    y = 1.2 * x + 1.6 * y - 9.1
    x = nx
    amp *= 0.5
  }
  return sum / total
}

function scanStep(a, b, x) {
  const t = clamp((x - a) / (b - a), 0, 1)
  return t * t * (3 - 2 * t)
}

// The nebula for a key at time t (seconds), as w x h cells: d is brightness and m is heat (where the
// colour turns from the agent's hue to the hot second colour), both in [0, 1]. Two clouds, placed by the
// seed, give it a composition; warped noise gives the filaments. The top-left stays darker, since the name
// sits there. Pure: the same key, size and time always give the same numbers.
function nebulaField(pk, w, h, t) {
  w = clamp(Math.floor(Number(w)) || SCAN_W, 1, 256)
  h = clamp(Math.floor(Number(h)) || SCAN_H, 1, 256)
  t = Number.isFinite(Number(t)) ? Number(t) : 0
  const s = scanSeed(pk)
  const r = i => scanHash(i, 7919, s)
  const lobes = [
    { x: 0.22 + (r(1) - 0.5) * 0.12, y: 0.58 + (r(2) - 0.5) * 0.14, rad: 0.25 + r(3) * 0.07, ph: r(10) * 6.28 },
    { x: 0.68 + (r(4) - 0.5) * 0.1, y: 0.56 + (r(5) - 0.5) * 0.16, rad: 0.27 + r(6) * 0.08, ph: r(11) * 6.28 }
  ]
  const ox = r(8) * 64
  const oy = r(9) * 64
  const aspect = w / h
  const d = new Float32Array(w * h)
  const m = new Float32Array(w * h)
  const s1 = s ^ 0x1b873593
  const s2 = s ^ 0x2c1b3c6d
  const s3 = s ^ 0x297a2d39
  const s4 = s ^ 0x6b6b2b13
  // fbm sits between about 0.24 and 0.76; stretch it to 0..1
  const norm = x => clamp((x - 0.26) / 0.48, 0, 1)
  for (let j = 0; j < h; j++) {
    for (let i = 0; i < w; i++) {
      const u = (i + 0.5) / w
      const v = (j + 0.5) / h
      const x = u * aspect * 2.7 + ox
      const y = v * 2.7 + oy
      // domain warp: the noise is read through two other noises, which drift at different speeds
      const qx = scanFbm(x + t * 0.05, y, s1, 3)
      const qy = scanFbm(x + 5.2, y + 1.3 - t * 0.037, s2, 3)
      const n = norm(scanFbm(x + 3.6 * qx + t * 0.02, y + 3.6 * qy, s3))
      const k = norm(scanFbm(0.8 * x + 2.2 * qy + 8.7, 0.8 * y + 2.2 * qx - t * 0.016, s4, 3))
      let glow = 0
      for (const L of lobes) {
        // the clouds are warped by the same noise, so their edges tear into flames instead of discs
        const dx = (u + 0.42 * (qx - 0.5) - L.x - 0.012 * Math.sin(t * 0.05 + L.ph)) * aspect
        const dy = v + 0.42 * (qy - 0.5) - L.y - 0.012 * Math.cos(t * 0.04 + L.ph)
        glow += Math.exp(-(dx * dx + dy * dy) / (L.rad * L.rad))
      }
      glow = Math.min(1.2, glow)
      // bright clouds where the lobes are, thin wisps of the same noise everywhere, dark lanes between
      const cloud = glow * (0.08 + 1.2 * Math.pow(n, 1.35))
      const wisp = scanStep(0.58, 1, n) * (0.25 + 0.25 * k)
      let val = Math.max(cloud, wisp) * scanStep(0.16, 0.48, n)
      const tl = Math.exp(-(((u - 0.17) / 0.25) ** 2 + ((v - 0.28) / 0.25) ** 2))
      val *= 1 - 0.5 * tl
      // and the bottom corners a little, under the two fields
      val *= 1 - 0.3 * Math.exp(-(((u - 0.14) / 0.2) ** 2 + ((v - 0.8) / 0.1) ** 2)) - 0.3 * Math.exp(-(((u - 0.86) / 0.2) ** 2 + ((v - 0.8) / 0.1) ** 2))
      // a little grain per cell, like a mosaic of phosphor tiles
      const grain = scanHash(i, j, s)
      val *= 0.84 + 0.32 * grain
      const at = j * w + i
      d[at] = clamp(1 - Math.exp(-1.8 * val), 0, 1) // soft clip: cores taper instead of flattening to white
      m[at] = clamp(0.55 * k + 0.95 * glow * n - 0.22 + 0.12 * (grain - 0.5), 0, 1)
    }
  }
  return { w, h, d, m }
}

// ---- colour ------------------------------------------------------------------------------------

function scanLab(L, C, hue) {
  const r = hue * Math.PI / 180
  return [L, C * Math.cos(r), C * Math.sin(r)]
}

// Hue a, turned k of the short way towards hue b.
function scanMixHue(a, b, k) {
  const dd = ((b - a + 540) % 360) - 180
  return (a + dd * k + 360) % 360
}

function scanRamp(stops, x) {
  let i = 0
  while (i < stops.length - 2 && x > stops[i + 1][0]) i++
  const [x0, c0] = stops[i]
  const [x1, c1] = stops[i + 1]
  const k = clamp((x - x0) / (x1 - x0), 0, 1)
  return [c0[0] + (c1[0] - c0[0]) * k, c0[1] + (c1[1] - c0[1]) * k, c0[2] + (c1[2] - c0[2]) * k]
}

// 64 brightness steps x 16 heat steps of [r, g, b]. Deep navy under everything, the agent's hue as the
// cool body, a violet turn of it on the way up, and the second colour going orange-white in the hot cores.
function scannerLut(hue, hue2) {
  const h1 = cardHue(hue)
  const h2 = cardHue(hue2 == null ? h1 + 150 : hue2)
  const base = scanMixHue(262, h1, 0.3)
  const mid = (h1 + 38) % 360
  const cool = [[0, scanLab(0.1, 0.035, base)], [0.2, scanLab(0.2, 0.09, scanMixHue(base, h1, 0.35))], [0.4, scanLab(0.42, 0.16, scanMixHue(base, h1, 0.7))],
    [0.58, scanLab(0.6, 0.19, h1)], [0.76, scanLab(0.76, 0.13, mid)], [1, scanLab(0.97, 0.03, mid)]]
  const hot = [[0, scanLab(0.1, 0.035, base)], [0.2, scanLab(0.24, 0.09, mid)], [0.4, scanLab(0.52, 0.15, h2)],
    [0.58, scanLab(0.72, 0.17, scanMixHue(h2, 62, 0.2))], [0.76, scanLab(0.88, 0.11, scanMixHue(h2, 70, 0.55))], [1, scanLab(0.99, 0.025, 80)]]
  const lut = new Uint8ClampedArray(64 * 16 * 3)
  for (let di = 0; di < 64; di++) {
    const dv = di / 63
    const c = scanRamp(cool, dv)
    const hc = scanRamp(hot, dv)
    for (let mi = 0; mi < 16; mi++) {
      const heat = scanStep(0.3, 0.8, mi / 15) * scanStep(0.3, 0.6, dv)
      const rgb = oklabToRgb(c[0] + (hc[0] - c[0]) * heat, c[1] + (hc[1] - c[1]) * heat, c[2] + (hc[2] - c[2]) * heat)
      const o = (di * 16 + mi) * 3
      lut[o] = rgb[0]; lut[o + 1] = rgb[1]; lut[o + 2] = rgb[2]
    }
  }
  return lut
}

// Field + lookup table -> RGBA pixels for the screen and for its bloom (only the bright cells). dim < 1 for
// the card's back.
function scanPaint(f, lut, px, bloom, dim) {
  const k = dim == null ? 1 : dim
  for (let i = 0; i < f.d.length; i++) {
    const dv = f.d[i]
    const o = ((Math.min(63, (dv * 64) | 0)) * 16 + Math.min(15, (f.m[i] * 16) | 0)) * 3
    const p = i * 4
    const r = lut[o] * k
    const g = lut[o + 1] * k
    const b = lut[o + 2] * k
    px[p] = r; px[p + 1] = g; px[p + 2] = b; px[p + 3] = 255
    if (bloom) {
      const e = scanStep(0.42, 0.9, dv)
      bloom[p] = r * e; bloom[p + 1] = g * e; bloom[p + 2] = b * e; bloom[p + 3] = 255
    }
  }
}

// The last time each screen canvas was drawn at, so a saved image shows the same moment.
const SCAN_T = typeof WeakMap === 'function' ? new WeakMap() : null

// One loop for every nebula on the page, as `motion` does for springs: a Set of live ones, a single P.loop
// made the first time one needs it. (A loop per card mount would leave one more dispose handler behind on
// Desktop each time a sheet opened, each holding that mount's canvases.) A nebula moves only while it is
// on screen and facing the viewer: a card turned to its back keeps its front canvas "intersecting", so the
// flip is tracked on its own.
const NEBULAS = new Set()
let nebulaLoop = null
const nebulaMoves = e => e.shown && !e.flipped
const nebulaIdle = () => {
  if (document.hidden) return true
  for (const e of NEBULAS) if (nebulaMoves(e)) return false
  return true
}
function nebulaFrame(now) {
  NEBULAS.forEach(e => {
    if (!nebulaMoves(e)) return
    if (!e.start) e.start = now - 1
    if (now - e.last < 66) return // about 15 frames a second: the drift is slow and the cells are big
    e.last = now
    e.paint(e.phase + (now - e.start) / 1000)
  })
}
function nebulaWake() {
  if (!nebulaLoop) nebulaLoop = P.loop(nebulaFrame, nebulaIdle)
  if (!nebulaIdle()) nebulaLoop.wake()
}

// Draws the nebula on two canvases and keeps it drifting. Static (one frame) with reduced motion or
// `still`; parked while the page is hidden, the card is off screen or turned to its back; leaves the shared
// loop on unmount.
function useNebula(pxRef, bloomRef, pk, hue, hue2, still, dim, flipped) {
  const entry = useRef(null)
  useEffect(() => {
    const a = pxRef.current
    const b = bloomRef.current
    const ca = a && a.getContext && a.getContext('2d')
    const cb = b && b.getContext && b.getContext('2d')
    if (!ca || !cb) return
    const lut = scannerLut(hue, hue2)
    const ia = ca.createImageData(SCAN_W, SCAN_H)
    const ib = cb.createImageData(SCAN_W, SCAN_H)
    // each key starts somewhere else along its drift, so two cards side by side never move in step
    const phase = scanHash(3, 5, scanSeed(pk)) * 400
    const paint = t => {
      scanPaint(nebulaField(pk, SCAN_W, SCAN_H, t), lut, ia.data, ib.data, dim)
      ca.putImageData(ia, 0, 0)
      cb.putImageData(ib, 0, 0)
      if (SCAN_T) SCAN_T.set(a, t)
    }
    paint(phase)
    if (still || motion.reduced()) return
    const e = { paint, phase, shown: true, flipped: !!flipped, start: 0, last: 0 }
    entry.current = e
    NEBULAS.add(e)
    const offVis = P.listen(document, 'visibilitychange', nebulaWake)
    let io = null
    if (typeof IntersectionObserver === 'function') {
      io = new IntersectionObserver(es => { e.shown = es.some(x => x.isIntersecting); nebulaWake() })
      io.observe(a)
    }
    nebulaWake()
    return () => {
      NEBULAS.delete(e)
      entry.current = null
      offVis()
      if (io) io.disconnect()
    }
  }, [pk, hue, hue2, still, dim])
  // turning the card over parks this nebula; turning it back wakes it
  useEffect(() => {
    const e = entry.current
    if (!e) return
    e.flipped = !!flipped
    if (!e.flipped) nebulaWake()
  }, [flipped])
}

function ScanScreen(props) {
  const px = useRef(null)
  const bloom = useRef(null)
  useNebula(px, bloom, props.pk, props.hue, props.hue2, !!props.still, props.dim == null ? 1 : props.dim, !!props.flipped)
  return jsxs('div', { className: 'h-scan-nebula', children: [
    jsx('canvas', { className: 'h-scan-px', ref: px, width: SCAN_W, height: SCAN_H }),
    jsx('canvas', { className: 'h-scan-bloom', ref: bloom, width: SCAN_W, height: SCAN_H })
  ] })
}

// ---- the card ------------------------------------------------------------------------------------

// Which colour the LED shows: red on a failed key check, else green when online or active, amber when away.
function scanLed(props) {
  if (props.warn) return 'red'
  if (props.kind === 'person') return props.online ? 'green' : 'amber'
  return stateWord(props.state) === 'absent' ? 'amber' : 'green'
}

// Which readout the status light sits by: the Status field (agents) or In the room (people). -1 when the card
// shows neither (an agent card showing its model instead), and the light then sits by the tag.
function scanLightAt(fields) {
  return (fields || []).findIndex(x => x && (x[0] === 'Status' || x[0] === 'In the room'))
}

function scanLight() {
  return jsx('span', { className: 'h-scan-led' }, 'led')
}

function scanBands() {
  return [jsx('div', { className: 'h-scan-band', 'data-at': 'top' }, 'bt'), jsx('div', { className: 'h-scan-band', 'data-at': 'bottom' }, 'bb')]
}

// The front: the picture in its bracket box, the readouts in the corners.
function scannerFront(model, props, hero) {
  const { f, warn, fields, name, serial } = model
  const at = scanLightAt(fields)
  return jsxs('div', { className: 'h-idcard h-idcard-front', ref: props.cardRef, 'data-card': 'scanner', 'data-warn': warn, 'data-led': model.led,
    style: { '--hue': f.hue, '--hue2': f.hue2 }, role: props.interactive ? undefined : 'img', 'aria-label': props.interactive ? undefined : props.label,
    children: [
      jsxs('div', { className: 'h-scan-screen', 'aria-hidden': true, children: [
        jsx(ScanScreen, { pk: props.pk, hue: f.hue, hue2: f.hue2, flipped: props.flipped }),
        jsx('div', { className: 'h-scan-cells' }),
        ...scanBands(),
        jsx('div', { className: 'h-scan-scrim' }),
        jsx('div', { className: 'h-scan-box', 'data-hero': true, children: jsx('div', { className: 'h-idcard-hero', children: hero }) }),
        jsxs('div', { className: 'h-scan-top', children: [
          jsx('div', { className: 'h-scan-name', 'data-size': nameSize(name), children: name }),
          jsxs('div', { className: 'h-scan-read', children: [jsx('span', { className: 'h-scan-tag', children: model.tag }, 'tag'), at < 0 ? scanLight() : null] })
        ] }),
        serial ? jsx('div', { className: 'h-scan-id', children: 'ID ' + serial }) : null,
        jsx('div', { className: 'h-scan-foot', children: fields.map((x, i) => jsxs('div', { className: 'h-scan-field', children: [
          jsx('span', { className: 'h-scan-label', children: x[0] }),
          jsxs('div', { className: 'h-scan-read', children: [i === at ? scanLight() : null, jsx('span', { className: 'h-scan-value', 'data-warn': !!x[2], children: x[1] }, 'v')] })
        ] }, x[0])) }),
        jsx('div', { className: 'h-scan-glass' })
      ] }),
      jsx('div', { className: 'h-idcard-shine' })
    ] })
}

// The back: the same screen, dimmed and still, the key and the rest as terminal lines.
function scannerBack(model, props, back) {
  const { f, warn } = model
  return jsxs('div', { className: 'h-idcard h-idcard-back', 'aria-hidden': true, 'data-card': 'scanner', 'data-warn': warn, 'data-led': model.led,
    style: { '--hue': f.hue, '--hue2': f.hue2 }, children: [
      jsxs('div', { className: 'h-scan-screen', children: [
        jsx(ScanScreen, { pk: props.pk, hue: f.hue, hue2: f.hue2, still: true, dim: 0.34 }),
        jsx('div', { className: 'h-scan-cells' }),
        ...scanBands(),
        jsxs('div', { className: 'h-scan-term', children: [
          jsx('div', { className: 'h-scan-label', children: '> Key' }),
          back.groups.length
            ? jsx('div', { className: 'h-scan-key', children: back.groups.map((g, i) => jsx('span', { children: g }, i)) })
            : jsx('div', { className: 'h-scan-value', children: 'Unknown' }),
          back.about ? jsx('div', { className: 'h-scan-about', children: back.about }) : null
        ] }),
        jsx('div', { className: 'h-scan-foot', 'data-n': back.fields.length, children: back.fields.map((x, i) => jsxs('div', { className: 'h-scan-field', children: [
          jsx('span', { className: 'h-scan-label', children: x[0] }),
          jsxs('span', { className: 'h-scan-value', children: [x[1], i === back.fields.length - 1 ? jsx('span', { className: 'h-scan-cursor' }, 'c') : null] })
        ] }, x[0])) }),
        jsx('div', { className: 'h-scan-glass' })
      ] }),
      jsx('div', { className: 'h-idcard-shine' })
    ] })
}

// A small picture of each style for the face editor's Card row.
function CardSwatch(props) {
  return jsx('span', { className: 'h-cardswatch', 'data-card': props.card, style: { '--hue': props.hue, '--hue2': props.hue2 }, 'aria-hidden': true,
    children: props.card === 'scanner' ? jsx('span', { className: 'h-cardswatch-screen' }) : null })
}

// ---- the saved image -------------------------------------------------------------------------------

// The nebula as a PNG data URL the size of the image's screen: hard-edged cells plus a soft bloom, drawn
// with the page's own canvas (nothing is fetched). '' when there is no canvas.
function scanNebulaPng(pk, hue, hue2, t, width, height) {
  try {
    const small = document.createElement('canvas')
    small.width = SCAN_W
    small.height = SCAN_H
    const glow = document.createElement('canvas')
    glow.width = SCAN_W
    glow.height = SCAN_H
    const sc = small.getContext('2d')
    const gc = glow.getContext('2d')
    const ia = sc.createImageData(SCAN_W, SCAN_H)
    const ib = gc.createImageData(SCAN_W, SCAN_H)
    scanPaint(nebulaField(pk, SCAN_W, SCAN_H, t), scannerLut(hue, hue2), ia.data, ib.data, 1)
    sc.putImageData(ia, 0, 0)
    gc.putImageData(ib, 0, 0)
    const out = document.createElement('canvas')
    out.width = Math.round(width)
    out.height = Math.round(height)
    const oc = out.getContext('2d')
    oc.imageSmoothingEnabled = false
    oc.drawImage(small, 0, 0, out.width, out.height)
    // the seams between cells, as on screen (.h-scan-cells)
    oc.globalCompositeOperation = 'multiply'
    oc.fillStyle = 'rgba(140, 140, 140, 0.5)'
    for (let i = 1; i < SCAN_W; i++) oc.fillRect(Math.round(i * out.width / SCAN_W), 0, 2, out.height)
    for (let j = 1; j < SCAN_H; j++) oc.fillRect(0, Math.round(j * out.height / SCAN_H), out.width, 2)
    // the bloom: the bright cells at half and quarter size, scaled back up smoothly, which blurs them
    // (works where canvas filters don't)
    oc.globalCompositeOperation = 'screen'
    oc.imageSmoothingEnabled = true
    for (const [div, alpha] of [[1, 0.5], [2, 0.75], [4, 1]]) {
      const c = document.createElement('canvas')
      c.width = Math.ceil(SCAN_W / div)
      c.height = Math.ceil(SCAN_H / div)
      const cc = c.getContext('2d')
      cc.imageSmoothingEnabled = true
      cc.drawImage(glow, 0, 0, c.width, c.height)
      oc.globalAlpha = alpha
      oc.drawImage(c, 0, 0, out.width, out.height)
    }
    return out.toDataURL('image/png')
  } catch (_) { return '' }
}

function scanMeasure(text, px, spacing) {
  try {
    if (!measureCtx) measureCtx = document.createElement('canvas').getContext('2d')
    measureCtx.font = '500 ' + px + 'px ' + CARD_MONO
    return measureCtx.measureText(text).width + Array.from(text).length * (spacing || 0)
  } catch (_) { return guessWidth(text, px, spacing) }
}

// Only a PNG we made ourselves may go in: a base64 data URL and nothing else.
function scanPngOk(s) {
  return typeof s === 'string' && s.length < 8000000 && /^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(s)
}

// The Scanner front as a standalone SVG string, 1200 x 750, like cardSvg (same options, plus `led` and
// `nebula`, a PNG data URL from scanNebulaPng, the size of the whole card). Text is escaped the same way; faces go through faceMarkup.
function scannerSvg(o) {
  o = o || {}
  const W = CARD_W
  const H = CARD_H
  const U = W / 100 // one cqw
  const warn = !!o.warn
  const hue = cardHue(o.hue)
  const hx = oklchToHex
  const measure = typeof o.measure === 'function' ? o.measure : guessWidth
  const width = (text, px, ls) => {
    const w = Number(measure(text, px, ls))
    return Number.isFinite(w) ? w : guessWidth(text, px, ls)
  }
  const up = s => Array.from(xmlClean(s).replace(/\s+/g, ' ').trim()).slice(0, 120).join('').toUpperCase()
  const num = n => String(Math.round(n * 100) / 100)
  const ui = warn ? hx(0.7, 0.21, 27) : hx(0.86, 0.12, 205)
  const ink = hx(0.97, 0.04, 205)
  const text = (x, y, str, a) => '<text x="' + num(x) + '" y="' + num(y) + '" font-family="' + (a.sans ? CARD_FONT : CARD_MONO) + '" font-size="' + num(a.size) +
    '" font-weight="' + (a.weight || 500) + '" fill="' + (a.fill || ink) + '"' + (a.ls ? ' letter-spacing="' + num(a.ls) + '"' : '') +
    (a.anchor ? ' text-anchor="' + a.anchor + '"' : '') + (a.opacity != null ? ' fill-opacity="' + a.opacity + '"' : '') +
    (a.glow === false ? '' : ' filter="url(#nsglow)"') + '>' + xmlEsc(str) + '</text>'

  // the screen is the whole card
  const R = 70 // the card's corner radius at this size (the Member export's too)
  const px = (x, y) => [x / 100 * W, y / 100 * H]

  const defs = []
  const out = []
  defs.push(HERO_CLIP)
  defs.push('<clipPath id="nscard"><rect width="' + W + '" height="' + H + '" rx="' + R + '"/></clipPath>')
  defs.push('<pattern id="nsscan" width="8" height="5" patternUnits="userSpaceOnUse"><rect y="3" width="8" height="2" fill="#000" fill-opacity="0.26"/></pattern>')
  const cell = 1.55 * U
  defs.push('<pattern id="nsgrid" width="' + num(cell) + '" height="' + num(cell) + '" patternUnits="userSpaceOnUse">' +
    '<path d="M0 0.75H' + num(cell) + 'M0.75 0V' + num(cell) + '" stroke="' + ui + '" stroke-width="1.5" stroke-opacity="0.34" fill="none"/></pattern>')
  defs.push('<radialGradient id="nsvig" cx="0.5" cy="0.5" r="0.75"><stop offset="0.55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.72"/></radialGradient>')
  defs.push('<linearGradient id="nsglare" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0.13"/><stop offset="0.36" stop-color="#fff" stop-opacity="0.03"/>' +
    '<stop offset="0.37" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')
  defs.push('<radialGradient id="nsdark" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="' + hx(0.1, 0.04, 255) + '" stop-opacity="0.55"/><stop offset="1" stop-color="' + hx(0.1, 0.04, 255) + '" stop-opacity="0"/></radialGradient>')
  const shade = hx(0.08, 0.04, 255)
  defs.push('<linearGradient id="nsscrim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="' + shade + '" stop-opacity="0"/><stop offset="0.5" stop-color="' + shade +
    '" stop-opacity="0.5"/><stop offset="1" stop-color="' + shade + '" stop-opacity="0.72"/></linearGradient>')
  defs.push('<radialGradient id="nsscrimn" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="' + shade + '" stop-opacity="0.5"/><stop offset="1" stop-color="' + shade + '" stop-opacity="0"/></radialGradient>')
  defs.push('<filter id="nsglow" x="-20%" y="-60%" width="140%" height="220%" color-interpolation-filters="sRGB"><feGaussianBlur in="SourceGraphic" stdDeviation="5" result="b"/>' +
    '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
  defs.push('<filter id="nsface" x="-40%" y="-40%" width="180%" height="180%" color-interpolation-filters="sRGB"><feDropShadow dx="0" dy="0" stdDeviation="14" flood-color="' +
    (warn ? hx(0.65, 0.22, 27) : hx(0.8, 0.14, 215)) + '" flood-opacity="0.75"/></filter>')
  defs.push('<filter id="nsdim" x="-40%" y="-40%" width="180%" height="180%" color-interpolation-filters="sRGB">' +
    '<feComponentTransfer><feFuncR type="linear" slope="0.7"/><feFuncG type="linear" slope="0.7"/><feFuncB type="linear" slope="0.7"/></feComponentTransfer></filter>')
  // the status light: red whenever the key check failed, whatever was asked for
  const led = SCAN_LEDS[warn ? 'red' : Object.prototype.hasOwnProperty.call(SCAN_LEDS, o.led) ? o.led : 'green']
  const ledHex = hx(led[0], led[1], led[2])
  defs.push('<radialGradient id="nsled" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="' + ledHex + '" stop-opacity="0.75"/>' +
    '<stop offset="1" stop-color="' + ledHex + '" stop-opacity="0"/></radialGradient>')
  // the glass edge: a soft dark falloff just inside the rim
  defs.push('<filter id="nsedge" x="-5%" y="-8%" width="110%" height="116%"><feGaussianBlur stdDeviation="14"/></filter>')

  out.push('<g clip-path="url(#nscard)">')
  out.push('<rect width="' + W + '" height="' + H + '" fill="' + hx(0.1, 0.035, 262) + '"/>')
  if (scanPngOk(o.nebula)) {
    out.push('<image width="' + W + '" height="' + H + '" preserveAspectRatio="none" href="' + o.nebula + '"/>')
  }
  const band = H * SCAN_BAND / 100
  out.push('<rect width="' + W + '" height="' + num(band) + '" fill="url(#nsgrid)"/>')
  out.push('<rect y="' + num(H - band) + '" width="' + W + '" height="' + num(band) + '" fill="url(#nsgrid)"/>')
  out.push('<path d="M0 ' + num(band) + 'H' + W + 'M0 ' + num(H - band) + 'H' + W + '" stroke="' + ui + '" stroke-width="2" stroke-opacity="0.7" fill="none"/>')

  // a soft dark scrim under the name block and the two fields, so a bright core never washes the text out
  // (the .h-scan-scrim layer: the same stops)
  out.push('<rect y="' + num(H * 0.64) + '" width="' + W + '" height="' + num(H * 0.36) + '" fill="url(#nsscrim)"/>')
  out.push('<ellipse cx="' + num(W * 0.3) + '" cy="' + num(H * 0.32) + '" rx="' + num(W * 0.4) + '" ry="' + num(H * 0.26) + '" fill="url(#nsscrimn)"/>')

  // the hero's bracket box, the picture inside it
  const bs = SCAN_BOX.size / 100 * W
  const bx = W * (1 - SCAN_BOX.right / 100) - bs
  const by = SCAN_BOX.top / 100 * H
  out.push('<rect x="' + num(bx) + '" y="' + num(by) + '" width="' + num(bs) + '" height="' + num(bs) + '" fill="url(#nsdark)"/>')
  out.push('<rect x="' + num(bx + 1) + '" y="' + num(by + 1) + '" width="' + num(bs - 2) + '" height="' + num(bs - 2) + '" fill="none" stroke="' + ui + '" stroke-width="2" stroke-opacity="0.38"/>')
  const arm = bs * 0.12
  const corner = (x, y, dx, dy) => 'M' + num(x + dx * arm) + ' ' + num(y) + 'H' + num(x) + 'V' + num(y + dy * arm)
  out.push('<path d="' + corner(bx, by, 1, 1) + corner(bx + bs, by, -1, 1) + corner(bx, by + bs, 1, -1) + corner(bx + bs, by + bs, -1, -1) +
    '" stroke="' + ui + '" stroke-width="' + (warn ? 6 : 4.5) + '" fill="none" filter="url(#nsglow)"/>')
  const hpad = bs * 0.12
  const hs = bs - 2 * hpad
  const faces = heroParts(o.faces, bx + hpad, by + hpad, hs, 'nsdim')
  out.push('<g filter="url(#nsface)">')
  if (faces.length) {
    faces.forEach(s => out.push(s))
  } else if (o.initial) {
    out.push(text(bx + bs / 2, by + bs / 2 + 26 * U * 0.36, Array.from(xmlClean(o.initial))[0] || '?', { size: 26 * U, weight: 300, anchor: 'middle', glow: false }))
  }
  out.push('</g>')

  // the status light: a lit dot and its halo, centred on (x, y)
  const lr = (warn ? 0.9 : 0.75) * U
  const light = (x, y) => {
    out.push('<circle cx="' + num(x) + '" cy="' + num(y) + '" r="' + num(3.2 * lr) + '" fill="url(#nsled)"/>')
    out.push('<circle cx="' + num(x) + '" cy="' + num(y) + '" r="' + num(lr) + '" fill="' + ledHex + '"/>')
  }
  const lightGap = 1.2 * U
  const fields = (Array.isArray(o.fields) ? o.fields : []).filter(Boolean).slice(0, 2)
  const at = scanLightAt(fields)

  // the name (two lines at most) and the tag under it
  const size = nameSize(o.name)
  const npx = { l: 5.9, m: 4.8, s: 3.6 }[size] * U
  const nls = npx * 0.06
  const lh = npx * 1.14
  const [nx, ny] = px(SCAN_PAD, 17)
  const lines = wrapLines(up(o.name), W * (1 - SCAN_PAD / 100 - 0.4), 2, s => width(s, npx, nls))
  lines.forEach((ln, i) => out.push(text(nx, ny + i * lh + npx * 0.86, ln, { size: npx, ls: nls })))
  const tagPx = 2.25 * U
  const tagLs = tagPx * 0.18
  const tagText = up(o.tag || '')
  const ty = ny + lines.length * lh + 1.3 * U
  const th = tagPx * 1.75
  let tagEnd = nx
  if (tagText) {
    const tw = width(tagText, tagPx, tagLs) + 1.8 * U
    out.push('<rect x="' + num(nx + 1) + '" y="' + num(ty) + '" width="' + num(tw) + '" height="' + num(th) + '" fill="' + (warn ? ui : hx(0.1, 0.04, 255)) + '" fill-opacity="' + (warn ? 0.92 : 0.6) +
      '" stroke="' + ui + '" stroke-width="2.4"/>')
    out.push(text(nx + 1 + 0.9 * U + tagLs / 2, ty + th / 2 + tagPx * 0.36, tagText, { size: tagPx, ls: tagLs, fill: warn ? '#1a0606' : ink, glow: !warn }))
    tagEnd = nx + 1 + tw + lightGap
  }
  if (at < 0) light(tagEnd + lr, ty + th / 2)

  // the card number, top right, in the grid band
  if (o.serial) {
    const [ix, iy] = px(100 - SCAN_PAD, SCAN_BAND / 2)
    const idPx = 1.9 * U
    const idLs = idPx * 0.14
    const idText = 'ID ' + o.serial
    const idW = width(idText, idPx, idLs)
    const padX = 0.9 * U
    const padY = 0.55 * U
    out.push('<rect x="' + num(ix - idW - padX) + '" y="' + num(iy - idPx / 2 - padY) + '" width="' + num(idW + 2 * padX) + '" height="' + num(idPx + 2 * padY) + '" rx="' + num(0.6 * U) +
      '" fill="' + hx(0.09, 0.04, 255) + '" fill-opacity="0.72"/>')
    out.push(text(ix, iy + idPx * 0.36, idText, { size: idPx, ls: idLs, anchor: 'end', fill: warn ? hx(0.95, 0.05, 25) : ink }))
  }

  // the two fields, bottom corners; the light (when it is here) takes room before its value
  const vpx = 3.3 * U
  const vls = vpx * 0.04
  const lpx = 1.85 * U
  const lls = lpx * 0.2
  const base = H * (1 - 0.13)
  const rowW = W * (1 - 2 * SCAN_PAD / 100)
  const lightW = 2 * lr + lightGap
  const shown = fields.map(() => '')
  for (const i of fields.map((_, n) => n).reverse()) {
    const own = i === at ? lightW : 0
    const room = (i === 1 ? rowW * 0.45 : Math.min(rowW * 0.52, shown[1] ? rowW - width(shown[1], vpx, vls) - (at === 1 ? lightW : 0) - 3 * U : rowW)) - own
    shown[i] = fitText(up(fields[i][1]), room, s => width(s, vpx, vls))
  }
  fields.forEach((fl, i) => {
    const right = W * (1 - SCAN_PAD / 100)
    const x = i === 0 ? nx : right
    const anchor = i === 0 ? 'start' : 'end'
    out.push(text(x, base - vpx * 1.02, up(fl[0]), { size: lpx, ls: lls, anchor, fill: ui }))
    let vx = x
    if (i === at) {
      const cy = base - vpx * 0.36
      if (i === 0) { light(x + lr, cy); vx = x + lightW } else light(x - width(shown[i], vpx, vls) - lightGap - lr, cy)
    }
    out.push(text(vx, base, shown[i], { size: vpx, ls: vls, anchor, fill: fl[2] ? hx(0.86, 0.14, 70) : ink }))
  })

  // the glass: scanlines, vignette, glare, a red inner glow when the key check failed, then the edge: a soft
  // dark falloff and a thin light rim (glass catching the light, not a frame)
  out.push('<rect width="' + W + '" height="' + H + '" fill="url(#nsscan)"/>')
  out.push('<rect width="' + W + '" height="' + H + '" fill="url(#nsvig)"/>')
  if (warn) {
    out.push('<rect x="6" y="6" width="' + (W - 12) + '" height="' + (H - 12) + '" rx="' + (R - 6) + '" fill="none" stroke="' + ui +
      '" stroke-width="12" stroke-opacity="0.35" filter="url(#nsglow)"/>')
  }
  out.push('<rect width="' + W + '" height="' + H + '" fill="url(#nsglare)"/>')
  out.push('<rect width="' + W + '" height="' + H + '" rx="' + R + '" fill="none" stroke="#000" stroke-opacity="0.6" stroke-width="40" filter="url(#nsedge)"/>')
  out.push('</g>')
  out.push('<rect x="1.5" y="1.5" width="' + (W - 3) + '" height="' + (H - 3) + '" rx="' + (R - 1.5) + '" fill="none" stroke="#fff" stroke-opacity="' + (warn ? 0 : 0.16) + '" stroke-width="3"/>')
  if (warn) out.push('<rect x="1.5" y="1.5" width="' + (W - 3) + '" height="' + (H - 3) + '" rx="' + (R - 1.5) + '" fill="none" stroke="' + ui + '" stroke-opacity="0.5" stroke-width="3"/>')

  return '<svg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '"><defs>' + defs.join('') + '</defs>' + out.join('') + '</svg>'
}
