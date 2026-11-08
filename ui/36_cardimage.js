// ---------------------------------------------------------------------------------------------
// card images: the front of a card as a 1200x750 PNG, to save or copy. Built as a standalone SVG
// string (no library, no page CSS), then drawn onto a canvas. It shows exactly what the card front
// shows: IdCard's own cardModel() supplies the words, and the picture is the card's rendered face,
// read back from the DOM with its styles written onto each shape.
//
// Names, models and every label come from strangers, so each text value is XML-escaped and anything
// that is not a plain shape is refused: no scripts, event attributes, foreign objects, links or
// references outside the document.
// ---------------------------------------------------------------------------------------------

const CARD_W = 1200
const CARD_H = 750
const CARD_FONT = 'system-ui, -apple-system, sans-serif'
const CARD_MONO = 'ui-monospace, SFMono-Regular, Menlo, monospace'
// the only elements a face may be drawn with
const FACE_SHAPES = ['svg', 'g', 'path', 'circle', 'ellipse', 'rect', 'line', 'polyline', 'polygon']
const FACE_ATTRS = ['d', 'cx', 'cy', 'r', 'rx', 'ry', 'x', 'y', 'width', 'height', 'x1', 'y1', 'x2', 'y2', 'points', 'viewBox']

// ---- colour -----------------------------------------------------------------------------------

function clamp01(v) {
  return Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0
}

// OKLab -> [r, g, b] as 0-255 integers (linear sRGB, then gamma). Out-of-gamut values are clamped.
function oklabToRgb(L, a, b) {
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b
  const s_ = L - 0.0894841775 * a - 1.2914855480 * b
  const l3 = l_ * l_ * l_
  const m3 = m_ * m_ * m_
  const s3 = s_ * s_ * s_
  const lin = [4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3,
    -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3,
    -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3]
  return lin.map(v => {
    const g = v <= 0.0031308 ? 12.92 * v : 1.055 * Math.pow(v, 1 / 2.4) - 0.055
    return Math.round(clamp01(g) * 255)
  })
}

function rgbHex(rgb) {
  return '#' + rgb.map(n => ('0' + Math.min(255, Math.max(0, Math.round(n) || 0)).toString(16)).slice(-2)).join('')
}

// CSS oklch(l c h) -> '#rrggbb'. l is 0-1, c about 0-0.4, h in degrees. Anything odd gives a valid colour.
function oklchToHex(l, c, h) {
  const L = Number(l)
  const C = Number(c)
  const H = (Number(h) || 0) * Math.PI / 180
  const ok = Number.isFinite(L) && Number.isFinite(C) && Number.isFinite(H)
  return rgbHex(ok ? oklabToRgb(L, C * Math.cos(H), C * Math.sin(H)) : [0, 0, 0])
}

// A computed CSS colour string -> { hex, a }, or null when it isn't one we can read (or is 'none').
// Browsers hand back rgb(), color(srgb ...), oklch() or oklab() depending on what the stylesheet said.
function cssColor(str) {
  const s = String(str == null ? '' : str).trim().toLowerCase()
  if (!s || s === 'none') return null
  if (s === 'transparent') return { hex: '#000000', a: 0 }
  let m = /^#([0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})$/.exec(s)
  if (m) {
    let h = m[1]
    if (h.length <= 4) h = h.split('').map(ch => ch + ch).join('')
    return { hex: '#' + h.slice(0, 6), a: h.length === 8 ? parseInt(h.slice(6), 16) / 255 : 1 }
  }
  m = /^([a-z-]+)\(([^)]*)\)$/.exec(s)
  if (!m) return null
  const sides = m[2].split('/')
  const toks = sides[0].trim().split(/[\s,]+/).filter(Boolean)
  const val = (t, whole) => {
    if (t == null) return NaN
    if (t === 'none') return 0
    return t.endsWith('%') ? parseFloat(t) / 100 * whole : parseFloat(t)
  }
  let a = 1
  const aTok = sides[1] != null ? sides[1].trim() : (m[1] === 'rgba' && toks.length > 3 ? toks[3] : null)
  if (aTok != null) a = clamp01(val(aTok, 1))
  let rgb = null
  if (m[1] === 'rgb' || m[1] === 'rgba') rgb = [0, 1, 2].map(i => val(toks[i], 255))
  else if (m[1] === 'oklch') rgb = oklabToRgb(val(toks[0], 1), val(toks[1], 0.4) * Math.cos((val(toks[2], 360) || 0) * Math.PI / 180), val(toks[1], 0.4) * Math.sin((val(toks[2], 360) || 0) * Math.PI / 180))
  else if (m[1] === 'oklab') rgb = oklabToRgb(val(toks[0], 1), val(toks[1], 0.4), val(toks[2], 0.4))
  else if (m[1] === 'color' && toks[0] === 'srgb') rgb = [1, 2, 3].map(i => val(toks[i], 1) * 255)
  if (!rgb || rgb.some(n => !Number.isFinite(n))) return null
  return { hex: rgbHex(rgb), a }
}

// Whatever cssColor can't read (display-p3, color-mix, a named colour), asked of the browser itself.
function canvasColor(str) {
  try {
    const ctx = document.createElement('canvas').getContext('2d')
    ctx.fillStyle = '#000'
    ctx.fillStyle = String(str)
    ctx.clearRect(0, 0, 1, 1)
    ctx.fillRect(0, 0, 1, 1)
    const d = ctx.getImageData(0, 0, 1, 1).data
    return { hex: rgbHex([d[0], d[1], d[2]]), a: d[3] / 255 }
  } catch (_) { return null }
}

// ---- text ---------------------------------------------------------------------------------------

// Drop the characters XML cannot hold (controls, lone surrogates, U+FFFE and U+FFFF).
function xmlClean(s) {
  let out = ''
  for (const ch of String(s == null ? '' : s)) {
    const c = ch.codePointAt(0)
    if (c === 9 || c === 10 || c === 13 || (c >= 0x20 && c <= 0xD7FF) || (c >= 0xE000 && c <= 0xFFFD) || (c >= 0x10000 && c <= 0x10FFFF)) out += ch
  }
  return out
}

// Text as it goes between tags or inside an attribute: the five XML characters, escaped.
function xmlEsc(s) {
  return xmlClean(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&apos;')
}

// A rough text width when the page can't measure: 0.64 em a letter, plus the letter spacing.
function guessWidth(text, px, spacing) {
  return Array.from(String(text)).length * (px * 0.64 + (spacing || 0))
}

// One line of text cut with an ellipsis until it fits maxW.
function fitText(text, maxW, width) {
  const chars = Array.from(String(text))
  if (width(chars.join('')) <= maxW) return chars.join('')
  while (chars.length > 1 && width(chars.join('') + '…') > maxW) chars.pop()
  return chars.join('') + '…'
}

// Words wrapped to at most maxLines lines of maxW. A word wider than a line is broken, and whatever
// still doesn't fit ends the last line with an ellipsis. Always returns at least one line.
function wrapLines(text, maxW, maxLines, width) {
  const words = String(text).split(/\s+/).filter(Boolean)
  const lines = []
  let cur = ''
  for (let w of words) {
    while (Array.from(w).length > 1 && width(w) > maxW) {
      const chars = Array.from(w)
      let n = chars.length - 1
      while (n > 1 && width(chars.slice(0, n).join('')) > maxW) n--
      if (cur) { lines.push(cur); cur = '' }
      lines.push(chars.slice(0, n).join(''))
      w = chars.slice(n).join('')
    }
    const next = cur ? cur + ' ' + w : w
    if (cur && width(next) > maxW) { lines.push(cur); cur = w } else cur = next
  }
  if (cur) lines.push(cur)
  if (!lines.length) return ['']
  if (lines.length > maxLines) {
    const rest = lines.slice(maxLines - 1).join(' ')
    lines.length = maxLines - 1
    lines.push(rest)
  }
  lines[lines.length - 1] = fitText(lines[lines.length - 1], maxW, width)
  return lines
}

// "Ada Lovelace" -> "ninsei-ada-lovelace-card.png": lowercase letters, digits and hyphens only.
function cardFilename(name) {
  const slug = String(name == null ? '' : name).normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40).replace(/-+$/g, '')
  return 'ninsei-' + (slug || 'card') + '-card.png'
}

// ---- the picture --------------------------------------------------------------------------------

// A face's inner markup, or '' if it is anything but plain shapes with plain attributes. The elements
// come from a short list, so scripts, styles, foreign objects, images, links and animation all fail
// at once; the rest of the checks are belts over the braces.
function faceMarkup(markup) {
  if (typeof markup !== 'string') return ''
  const m = markup.replace(/\sxmlns(:\w+)?="[^"]*"/g, '')
  const tags = m.match(/<\/?[A-Za-z][\w:.-]*/g) || []
  if (!tags.length || m.length > 20000) return ''
  if (tags.some(t => !FACE_SHAPES.includes(t.replace(/^<\/?/, '')))) return ''
  if (/\son\w+\s*=/i.test(m) || /href\s*=/i.test(m) || /javascript:/i.test(m) || /\/\//.test(m) || /@import/i.test(m)) return ''
  if (/url\(\s*(?!['"]?#)/i.test(m)) return ''
  return m
}

// A face's own viewBox ("x y w h", plain numbers only), else the pixel grid's.
function faceBox(vb) {
  const n = String(vb == null ? '' : vb).trim().split(/\s+/).map(Number)
  return n.length === 4 && n.every(Number.isFinite) && n[2] > 0 && n[3] > 0 ? n.join(' ') : '0 0 64 64'
}

function cardHue(h) {
  const n = Number(h)
  return Number.isFinite(n) ? ((n % 360) + 360) % 360 : 0
}

// The card front as a standalone SVG string, 1200 x 750. Sizes are the card's own CSS percentages
// (cqw) scaled to this width, so it looks like the card on screen.
//   hue, hue2     the face's colours
//   name, tag, serial, fields [[label, value, warn?]], warn, initial   the words on the front
//   faces         [{ inner, left, top, size, front }]: face drawings from heroFaces(), placed in % of the
//                 picture's box; with none, `initial` is drawn big instead
//   measure       (text, fontPx, letterSpacingPx) -> width, from a canvas; a rough guess without it
function cardSvg(o) {
  o = o || {}
  const W = CARD_W
  const H = CARD_H
  const hue = cardHue(o.hue)
  const hue2 = cardHue(o.hue2 == null ? o.hue : o.hue2)
  const warn = !!o.warn
  const hx = oklchToHex
  const measure = typeof o.measure === 'function' ? o.measure : guessWidth
  const width = (text, px, ls) => {
    const w = Number(measure(text, px, ls))
    return Number.isFinite(w) ? w : guessWidth(text, px, ls)
  }
  const up = s => Array.from(xmlClean(s).replace(/\s+/g, ' ').trim()).slice(0, 120).join('').toUpperCase()
  const num = n => String(Math.round(n * 100) / 100)
  const text = (x, y, str, a) => '<text x="' + num(x) + '" y="' + num(y) + '" font-family="' + (a.mono ? CARD_MONO : CARD_FONT) + '" font-size="' + num(a.size) +
    '" font-weight="' + (a.weight || 400) + '" fill="' + (a.fill || '#fff') + '"' + (a.ls ? ' letter-spacing="' + num(a.ls) + '"' : '') +
    (a.anchor ? ' text-anchor="' + a.anchor + '"' : '') + (a.opacity != null ? ' fill-opacity="' + a.opacity + '"' : '') + '>' + xmlEsc(str) + '</text>'

  const out = []
  const defs = []
  defs.push('<radialGradient id="ncbg" gradientUnits="userSpaceOnUse" gradientTransform="translate(' + num(W * 0.74) + ' ' + num(H * 0.4) + ') scale(' + num(W * 1.15) + ' ' + num(H * 1.05) + ')" cx="0" cy="0" r="1">' +
    '<stop offset="0" stop-color="' + hx(0.6, 0.19, hue) + '"/><stop offset="0.46" stop-color="' + hx(0.4, 0.2, hue) + '"/><stop offset="1" stop-color="' + hx(0.2, 0.12, hue) + '"/></radialGradient>')
  defs.push('<pattern id="ncdots" width="16" height="16" patternUnits="userSpaceOnUse"><circle cx="8" cy="8" r="2.7" fill="#fff" fill-opacity="0.34"/></pattern>')
  defs.push('<radialGradient id="ncfade" gradientUnits="userSpaceOnUse" gradientTransform="translate(' + num(W * 0.72) + ' ' + num(H * 0.52) + ') scale(' + num(W * 0.56) + ' ' + num(H * 0.74) + ')" cx="0" cy="0" r="1">' +
    '<stop offset="0" stop-color="#fff"/><stop offset="0.72" stop-color="#fff" stop-opacity="0"/></radialGradient>')
  defs.push('<mask id="ncmask"><rect width="' + W + '" height="' + H + '" fill="url(#ncfade)"/></mask>')
  const ring = warn ? [[0.8, 0.17, 45], [0.68, 0.21, 28], [0.88, 0.15, 78], [0.72, 0.2, 35], [0.8, 0.17, 45]]
    : [[0.96, 0.07, 200], [0.93, 0.1, 320], [0.98, 0.05, 95], [0.92, 0.11, 160], [0.96, 0.07, 200]]
  defs.push('<linearGradient id="ncring" gradientUnits="userSpaceOnUse" x1="60" y1="40" x2="' + (W - 60) + '" y2="' + (H - 40) + '">' +
    ring.map((c, i) => '<stop offset="' + i / 4 + '" stop-color="' + hx(c[0], c[1], c[2]) + '"/>').join('') + '</linearGradient>')
  defs.push('<filter id="ncglow" filterUnits="userSpaceOnUse" x="' + num(W * 0.4) + '" y="0" width="' + num(W * 0.6) + '" height="' + H + '" color-interpolation-filters="sRGB">' +
    '<feDropShadow dx="0" dy="0" stdDeviation="32" flood-color="' + hx(0.85, 0.14, hue) + '" flood-opacity="0.55"/></filter>')
  defs.push('<filter id="ncdim" x="-40%" y="-40%" width="180%" height="180%" color-interpolation-filters="sRGB">' +
    '<feComponentTransfer><feFuncR type="linear" slope="0.86"/><feFuncG type="linear" slope="0.86"/><feFuncB type="linear" slope="0.86"/></feComponentTransfer>' +
    '<feColorMatrix type="saturate" values="0.85"/></filter>')
  if (warn) {
    defs.push('<radialGradient id="ncwarn" gradientUnits="userSpaceOnUse" gradientTransform="translate(' + W / 2 + ' ' + H / 2 + ') scale(' + num(W * 1.2) + ' ' + num(H * 1.3) + ')" cx="0" cy="0" r="1">' +
      '<stop offset="0.46" stop-color="' + hx(0.55, 0.21, 32) + '" stop-opacity="0"/><stop offset="1" stop-color="' + hx(0.55, 0.21, 32) + '" stop-opacity="0.62"/></radialGradient>')
  }
  defs.push('<clipPath id="ncclip"><rect width="' + W + '" height="' + H + '" rx="70"/></clipPath>')

  out.push('<g clip-path="url(#ncclip)">')
  out.push('<rect width="' + W + '" height="' + H + '" fill="url(#ncbg)"/>')
  out.push('<rect width="' + W + '" height="' + H + '" fill="url(#ncdots)" mask="url(#ncmask)"/>')
  if (warn) out.push('<rect width="' + W + '" height="' + H + '" fill="url(#ncwarn)"/>')

  // the picture: up to three faces, or the initial
  const bx = W * 0.58
  const by = H * 0.46 - W * 0.175
  const bs = W * 0.35
  const faces = (Array.isArray(o.faces) ? o.faces : []).map(f => ({ f, inner: faceMarkup(f && f.inner) })).filter(x => x.inner).slice(0, 3)
  out.push('<g filter="url(#ncglow)">')
  if (faces.length) {
    for (let i = faces.length - 1; i >= 0; i--) {
      const { f, inner } = faces[i]
      const left = Number(f.left) || 0
      const top = Number(f.top) || 0
      const size = Number(f.size) || 100
      out.push('<svg x="' + num(bx + left / 100 * bs) + '" y="' + num(by + top / 100 * bs) + '" width="' + num(size / 100 * bs) + '" height="' + num(size / 100 * bs) +
        '" viewBox="' + faceBox(f.vb) + '" overflow="visible"' + (f.front ? '' : ' filter="url(#ncdim)"') + '>' + inner + '</svg>')
    }
  } else if (o.initial) {
    out.push(text(bx + bs / 2, by + bs / 2 + W * 0.3 * 0.36, Array.from(xmlClean(o.initial))[0] || '?', { size: W * 0.3, weight: 200, fill: hx(0.95, 0.04, hue), anchor: 'middle' }))
  }
  out.push('</g>')

  // name (two lines at most), then the tag under it
  const size = nameSize(o.name)
  const px = { l: 6.6, m: 5.3, s: 4.3 }[size] * (W / 100)
  const ls = px * { l: 0.12, m: 0.1, s: 0.08 }[size]
  const lh = px * (size === 's' ? 1.12 : 1.08)
  const left = W * 0.08
  const top = H * 0.13
  const lines = wrapLines(up(o.name), W * 0.46, 2, s => width(s, px, ls))
  lines.forEach((ln, i) => out.push(text(left, top + i * lh + (lh - px) / 2 + px * 0.8, ln, { size: px, weight: 300, ls })))
  const tagPx = 2.7 * (W / 100)
  const tagLs = tagPx * 0.16
  const tagText = up(o.tag || '')
  const tagW = width(tagText, tagPx, tagLs) + 44
  const tagY = top + lines.length * lh + 29
  const tFill = warn ? hx(0.9, 0.13, 75) : hx(0.98, 0.02, hue)
  const tInk = warn ? hx(0.3, 0.13, 35) : hx(0.32, 0.17, hue)
  const tRing = warn ? hx(0.5, 0.18, 35) : hx(0.4, 0.17, hue)
  if (tagText) {
    out.push('<rect x="' + num(left) + '" y="' + num(tagY) + '" width="' + num(tagW) + '" height="46" fill="' + tFill + '"/>')
    out.push('<rect x="' + num(left + 2.4) + '" y="' + num(tagY + 2.4) + '" width="' + num(tagW - 4.8) + '" height="' + 41.2 + '" fill="none" stroke="' + tRing + '" stroke-width="4.8"/>')
    out.push(text(left + 22 + tagLs / 2, tagY + 6 + tagPx * 0.88, tagText, { size: tagPx, weight: 500, ls: tagLs, fill: tInk }))
  }

  // card number, top right
  if (o.serial) out.push(text(W * 0.915, H * 0.07 + 28, o.serial, { size: 2.35 * (W / 100), mono: true, ls: 2.35 * (W / 100) * 0.16, anchor: 'end', opacity: 0.72 }))

  // the two fields along the bottom
  const fields = (Array.isArray(o.fields) ? o.fields : []).filter(Boolean).slice(0, 2)
  const valuePx = 4.4 * (W / 100)
  const labelPx = 2.5 * (W / 100)
  const valueLs = valuePx * 0.06
  const labelLs = labelPx * 0.2
  const base = H * 0.88 - valuePx * 0.22
  // the right field is cut first (at 45% of the row), then the left gets what is left (at most 60%) minus a gap
  const rowW = W * 0.84
  const shown = fields.map(() => '')
  for (const i of fields.map((_, n) => n).reverse()) {
    const room = i === 1 ? rowW * 0.45 : Math.min(rowW * 0.6, shown[1] ? rowW - width(shown[1], valuePx, valueLs) - 42 : rowW)
    shown[i] = fitText(up(fields[i][1]), room, s => width(s, valuePx, valueLs))
  }
  fields.forEach((fl, i) => {
    const x = i === 0 ? left : W - left
    const anchor = i === 0 ? 'start' : 'end'
    out.push(text(x, base - valuePx * 0.72 - 11, up(fl[0]), { size: labelPx, ls: labelLs, anchor, opacity: 0.74 }))
    out.push(text(x, base, shown[i], { size: valuePx, ls: valueLs, anchor, fill: fl[2] ? hx(0.9, 0.12, 70) : '#fff' }))
  })

  // the frame
  out.push('<rect x="29" y="29" width="' + (W - 58) + '" height="' + (H - 58) + '" rx="48" fill="none" stroke="url(#ncring)" stroke-width="' + (warn ? 8 : 4.8) + '" stroke-opacity="' + (warn ? 1 : 0.9) + '"/>')
  out.push('</g>')
  out.push('<rect x="1.5" y="1.5" width="' + (W - 3) + '" height="' + (H - 3) + '" rx="69" fill="none" stroke="#fff" stroke-opacity="0.08" stroke-width="3"/>')

  return '<svg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '"><defs>' + defs.join('') + '</defs>' + out.join('') + '</svg>'
}

// ---- reading the rendered card ----------------------------------------------------------------

// One face's <svg> from the page, as markup that needs no page CSS: every shape gets the fill, stroke,
// opacity and transform it is drawn with right now, and nothing else survives (no classes, ids,
// styles or unknown attributes). The face holds still while it is read, so a blink never lands in
// the picture. Returns the markup inside the <svg>, or ''.
function inlineFace(svgEl) {
  const hf = svgEl.closest ? svgEl.closest('.hf') : null
  const had = !!(hf && hf.classList.contains('hf-still'))
  // no transition either: stopping the breathing would otherwise ease the head back to rest
  const heads = hf ? Array.from(hf.querySelectorAll('.hf-head')) : []
  heads.forEach(h => { h.style.transition = 'none' })
  if (hf) hf.classList.add('hf-still')
  try {
    const clone = svgEl.cloneNode(true)
    const src = Array.from(svgEl.querySelectorAll('*'))
    const dst = Array.from(clone.querySelectorAll('*'))
    src.forEach((el, i) => {
      const to = dst[i]
      const tag = el.tagName.toLowerCase()
      if (!to || !FACE_SHAPES.includes(tag)) { if (to) to.remove(); return }
      const cs = getComputedStyle(el)
      const style = []
      for (const key of ['fill', 'stroke']) {
        const v = cs.getPropertyValue(key)
        const c = cssColor(v) || (v && v !== 'none' ? canvasColor(v) : null)
        style.push(key + ':' + (c ? c.hex : 'none'))
        if (c && c.a < 1) style.push(key + '-opacity:' + (Math.round(c.a * 100) / 100))
      }
      for (const key of ['fill-opacity', 'stroke-opacity', 'opacity']) {
        const v = parseFloat(cs.getPropertyValue(key))
        if (Number.isFinite(v) && v !== 1) style.push(key + ':' + v)
      }
      // pixel art (ui/12_pixel.js marks its paths) stays hard-edged at the picture's size
      if (el.hasAttribute('data-px')) style.push('shape-rendering:crispEdges')
      const sw = parseFloat(cs.getPropertyValue('stroke-width'))
      if (Number.isFinite(sw)) style.push('stroke-width:' + sw)
      for (const key of ['stroke-linecap', 'stroke-linejoin']) {
        const v = cs.getPropertyValue(key)
        if (/^(butt|round|square|miter|bevel)$/.test(v)) style.push(key + ':' + v)
      }
      const tf = cs.getPropertyValue('transform')
      if (tf && tf !== 'none' && /^matrix(3d)?\([-0-9., e]+\)$/.test(tf)) {
        style.push('transform:' + tf)
        const origin = cs.getPropertyValue('transform-origin')
        if (/^[-0-9. a-z%]+$/.test(origin)) style.push('transform-origin:' + origin)
        const box = cs.getPropertyValue('transform-box')
        if (/^(fill-box|view-box|stroke-box)$/.test(box)) style.push('transform-box:' + box)
      }
      for (const a of Array.from(to.attributes)) if (!FACE_ATTRS.includes(a.name)) to.removeAttribute(a.name)
      to.setAttribute('style', style.join(';'))
    })
    const ser = new XMLSerializer()
    return Array.from(clone.children).map(c => ser.serializeToString(c)).join('').replace(/\sxmlns="[^"]*"/g, '')
  } finally {
    if (hf && !had) hf.classList.remove('hf-still')
    heads.forEach(h => { h.style.transition = '' })
  }
}

// The picture on a rendered card front: [{ inner, left, top, size, front }] in % of its box.
function heroFaces(front) {
  const out = []
  const mates = Array.from(front.querySelectorAll('.h-idcard-mate'))
  const place = (svg, left, top, size, isFront) => {
    const inner = svg ? inlineFace(svg) : ''
    if (inner) out.push({ inner, left, top, size, front: isFront, vb: svg.getAttribute('viewBox') })
  }
  if (mates.length) {
    mates.forEach(el => place(el.querySelector('svg'), parseFloat(el.style.left) || 0, parseFloat(el.style.top) || 0, parseFloat(el.style.width) || 100, el.getAttribute('data-front') === 'true'))
  } else {
    place(front.querySelector('.h-idcard-hero svg'), 0, 0, 100, true)
  }
  return out
}

let measureCtx = null
function canvasMeasure(text, px, spacing) {
  try {
    if (!measureCtx) measureCtx = document.createElement('canvas').getContext('2d')
    measureCtx.font = '300 ' + px + 'px ' + CARD_FONT
    return measureCtx.measureText(text).width + Array.from(text).length * (spacing || 0)
  } catch (_) { return guessWidth(text, px, spacing) }
}

function rasterizeSvg(svg) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = CARD_W
        canvas.height = CARD_H
        canvas.getContext('2d').drawImage(img, 0, 0, CARD_W, CARD_H)
        canvas.toBlob(b => (b ? resolve(b) : reject(new Error('The card did not turn into an image'))), 'image/png')
      } catch (e) { reject(e) }
    }
    img.onerror = () => reject(new Error('The card did not draw'))
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
  })
}

// The card front as a PNG: IdCard's props say what is on it, the rendered `front` element gives the face.
// The Scanner style has its own picture (scannerSvg in 34_scanner.js).
async function cardImage(props, front) {
  const m = cardModel(props)
  const faces = front ? heroFaces(front) : []
  const opts = { hue: m.f.hue, hue2: m.f.hue2, name: m.name, tag: m.tag, serial: m.serial, fields: m.fields, warn: m.warn,
    faces, initial: faces.length ? '' : m.initial, measure: canvasMeasure }
  let svg
  if (m.card === 'scanner') {
    // the nebula at the moment the card shows (its canvas remembers when that was)
    const canvas = front && front.querySelector('.h-scan-px')
    const t = canvas && SCAN_T && SCAN_T.has(canvas) ? SCAN_T.get(canvas) : scanHash(3, 5, scanSeed(props.pk)) * 400
    svg = scannerSvg(Object.assign(opts, { pk: props.pk, led: m.led, measure: scanMeasure, nebula: scanNebulaPng(props.pk, m.f.hue, m.f.hue2, t, CARD_W, CARD_H) }))
  } else {
    svg = cardSvg(opts)
  }
  return { blob: await rasterizeSvg(svg), filename: cardFilename(m.name) }
}

// Save a file through the page: a temporary link with a download name. Desktop's shell and every
// browser turn that into a save. Resolves false if the click could not be made.
function anchorSave(blob, filename) {
  try {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.rel = 'noopener'
    a.style.display = 'none'
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 15000)
    return Promise.resolve(true)
  } catch (_) { return Promise.resolve(false) }
}

// Copying a picture needs the browser's image clipboard. The blob may still be on its way, which
// the clipboard accepts as a promise (Safari wants it so the click still counts).
function canCopyImage() {
  return typeof ClipboardItem !== 'undefined' && typeof navigator !== 'undefined' && !!(navigator.clipboard && navigator.clipboard.write)
}

// canCopyImage, minus the places that say outright that the page may not write to the clipboard
// (Hermes Desktop's shell denies it to plugin pages). Browsers that can't be asked just get the button.
function useCanCopyImage() {
  const [ok, setOk] = useState(canCopyImage)
  useEffect(() => {
    let live = true
    try {
      if (navigator.permissions && navigator.permissions.query) {
        navigator.permissions.query({ name: 'clipboard-write' }).then(s => { if (live && s.state === 'denied') setOk(false) }, () => {})
      }
    } catch (_) { /* can't ask: leave the button */ }
    return () => { live = false }
  }, [])
  return ok
}
