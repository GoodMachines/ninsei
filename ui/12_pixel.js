// ---------------------------------------------------------------------------------------------
// pixel art: every face (an agent's) and avatar (a person's) is drawn on one 64 x 64 grid from parts.
//
// A part paints cells of the grid with palette slots (one letter each); later parts paint over earlier
// ones. The grid becomes SVG: one <path> per colour, built from merged runs of cells (never a <rect>
// per cell). Everything here is plain arithmetic on whole cells (no trig, no randomness), so the same
// settings give the same pixels on every install. Nothing is fetched and no image is generated.
// ---------------------------------------------------------------------------------------------

const PX = 64
const PX_MID = 31.5   // the grid's centre line: symmetric parts mirror across it

// A grid: one byte per cell, 0 for empty, else a slot letter's char code.
function pxGrid() { return new Uint8Array(PX * PX) }
const pxCode = s => s.charCodeAt(0)

// A mask of the cells for which test(x, y) holds (x, y are whole cell coordinates).
function pxMask(test) {
  const m = new Uint8Array(PX * PX)
  for (let y = 0; y < PX; y++) for (let x = 0; x < PX; x++) if (test(x, y)) m[y * PX + x] = 1
  return m
}
const pxAt = (m, x, y) => x >= 0 && y >= 0 && x < PX && y < PX ? m[y * PX + x] : 0
function pxOr(a, b) { const m = new Uint8Array(PX * PX); for (let i = 0; i < m.length; i++) m[i] = a[i] || b[i] ? 1 : 0; return m }
function pxCut(a, b) { const m = new Uint8Array(PX * PX); for (let i = 0; i < m.length; i++) m[i] = a[i] && !b[i] ? 1 : 0; return m }
function pxAnd(a, b) { const m = new Uint8Array(PX * PX); for (let i = 0; i < m.length; i++) m[i] = a[i] && b[i] ? 1 : 0; return m }

// Shapes as tests. Centres may sit between cells (31.5 is the grid's middle).
const pxEllipse = (cx, cy, rx, ry) => (x, y) => { const u = (x - cx) / rx, v = (y - cy) / ry; return u * u + v * v <= 1 }
const pxRing = (cx, cy, rx, ry, t) => {
  const o = pxEllipse(cx, cy, rx, ry), i = pxEllipse(cx, cy, rx - t, ry - t)
  return (x, y) => o(x, y) && !i(x, y)
}
// a superellipse with exponent 4: a soft square
const pxSquircle = (cx, cy, rx, ry) => (x, y) => { const u = (x - cx) / rx, v = (y - cy) / ry; return u * u * u * u + v * v * v * v <= 1 }
const pxRect = (x0, y0, x1, y1) => (x, y) => x >= x0 && x <= x1 && y >= y0 && y <= y1
// a filled triangle (any winding)
const pxTri = (ax, ay, bx, by, cx, cy) => (x, y) => {
  const s1 = (bx - ax) * (y - ay) - (by - ay) * (x - ax)
  const s2 = (cx - bx) * (y - by) - (cy - by) * (x - bx)
  const s3 = (ax - cx) * (y - cy) - (ay - cy) * (x - cx)
  return (s1 >= 0 && s2 >= 0 && s3 >= 0) || (s1 <= 0 && s2 <= 0 && s3 <= 0)
}
// a thick line segment
const pxLine = (ax, ay, bx, by, w) => (x, y) => {
  const dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy
  let t = L ? ((x - ax) * dx + (y - ay) * dy) / L : 0
  t = t < 0 ? 0 : t > 1 ? 1 : t
  const ex = ax + t * dx - x, ey = ay + t * dy - y
  return ex * ex + ey * ey <= w * w / 4
}
const pxAny = (...tests) => (x, y) => tests.some(t => t(x, y))

// Paint every cell of a mask with a slot (only where `where` allows, when given).
function pxPaint(g, m, slot, where) {
  const c = pxCode(slot)
  for (let i = 0; i < m.length; i++) if (m[i] && (!where || where[i])) g[i] = c
}

// The cells just outside a mask (4-neighbours): its 1-cell outline.
function pxEdge(m) {
  return pxMask((x, y) => !m[y * PX + x] && (pxAt(m, x - 1, y) || pxAt(m, x + 1, y) || pxAt(m, x, y - 1) || pxAt(m, x, y + 1)))
}

// City-block distance from each cell of a mask to the nearest cell outside it (1 = on its edge).
function pxDepth(m) {
  const d = new Int16Array(PX * PX)
  const big = 999
  for (let y = 0; y < PX; y++) for (let x = 0; x < PX; x++) {
    const i = y * PX + x
    if (!m[i]) { d[i] = 0; continue }
    const up = y > 0 ? d[i - PX] : 0, left = x > 0 ? d[i - 1] : 0
    d[i] = Math.min(big, up + 1, left + 1)
  }
  for (let y = PX - 1; y >= 0; y--) for (let x = PX - 1; x >= 0; x--) {
    const i = y * PX + x
    if (!m[i]) continue
    const dn = y < PX - 1 ? d[i + PX] : 0, rt = x < PX - 1 ? d[i + 1] : 0
    d[i] = Math.min(d[i], dn + 1, rt + 1)
  }
  return d
}

// Rows of letters ('.' is nothing) placed with their top-left at (x, y); `flip` mirrors them.
function pxMap(g, rows, x, y, flip) {
  for (let r = 0; r < rows.length; r++) {
    const row = rows[r]
    for (let i = 0; i < row.length; i++) {
      const ch = row[i]
      if (ch === '.' || ch === ' ') continue
      const gx = flip ? x + row.length - 1 - i : x + i, gy = y + r
      if (gx >= 0 && gy >= 0 && gx < PX && gy < PX) g[gy * PX + gx] = pxCode(ch)
    }
  }
}

// A grid -> { slot letter: path data }. Each run of equal cells in a row is a rectangle; a rectangle
// that repeats exactly on the next row grows downwards instead of starting again.
function pxPaths(g) {
  const out = {}
  let open = new Map()   // "x0,x1,code" -> [y0, h] for runs still growing
  const flush = (key, r) => {
    const [x0, x1, code] = key.split(',').map(Number)
    const k = String.fromCharCode(code)
    out[k] = (out[k] || '') + 'M' + x0 + ' ' + r[0] + 'h' + (x1 - x0) + 'v' + r[1] + 'h' + (x0 - x1) + 'z'
  }
  for (let y = 0; y <= PX; y++) {
    const next = new Map()
    if (y < PX) {
      let x = 0
      while (x < PX) {
        const c = g[y * PX + x]
        let e = x + 1
        while (e < PX && g[y * PX + e] === c) e++
        if (c) {
          const key = x + ',' + e + ',' + c
          const r = open.get(key)
          if (r) { r[1] += 1; next.set(key, r); open.delete(key) } else next.set(key, [y, 1])
        }
        x = e
      }
    }
    open.forEach((r, key) => flush(key, r))
    open = next
  }
  return out
}

// A layer as SVG paths: one per slot, coloured from `colours` (slot -> hex); unknown slots are skipped.
function pxPathEls(paths, colours, prefix) {
  return Object.keys(paths).sort().map(k => colours[k]
    ? jsx('path', { d: paths[k], fill: colours[k], 'data-px': k }, (prefix || '') + k)
    : null)
}

// Cells a grid uses, as a mask (for an underlay that hides seams when the art is smoothed down).
function pxUsed(...grids) {
  const m = new Uint8Array(PX * PX)
  for (const g of grids) for (let i = 0; i < m.length; i++) if (g[i]) m[i] = 1
  return m
}

// Small cache: grids are cheap, but a room re-renders dozens of faces on every snapshot.
function pxCache(limit) {
  const map = new Map()
  return (key, make) => {
    if (map.has(key)) { const v = map.get(key); map.delete(key); map.set(key, v); return v }
    const v = make()
    map.set(key, v)
    if (map.size > limit) map.delete(map.keys().next().value)
    return v
  }
}

// Whether the art lands on whole device pixels at this size: then crisp edges; otherwise the browser
// smooths the downscale, which reads better than dropping rows at 24 or 40 px.
function pxCrisp(size, grid) {
  const n = grid || PX
  let dpr = 1
  try { dpr = window.devicePixelRatio || 1 } catch (_) { /* not in a browser */ }
  const dev = size * dpr
  return Math.abs(dev / n - Math.round(dev / n)) < 0.001 && dev >= n
}

// ---------------------------------------------------------------------------------------------
// agents: a glowing blob in its owner's hue. The body's outline, rim, light, shade, highlight and
// scanlines all follow from its silhouette, so every shape is lit the same way.
// ---------------------------------------------------------------------------------------------

// The six silhouettes. ex/ey: the left eye's centre (the right one mirrors across the middle);
// my: the mouth line; c: the centre the highlight is measured from.
const PXF_BODY = {
  round: { test: pxEllipse(PX_MID, 38, 22.6, 22), ex: 23, ey: 36, my: 46, c: [31.5, 38] },
  soft: { test: pxSquircle(PX_MID, 39, 23.2, 20.6), ex: 22, ey: 37, my: 47, c: [31.5, 39] },
  tall: { test: (x, y) => { const k = y < 36 ? 1 - (36 - y) * 0.0062 : 1; const u = (x - PX_MID) / (16.6 * k), v = (y - 37) / 24.6; return u * u + v * v <= 1 },
    ex: 25, ey: 34, my: 46, c: [31.5, 37] },
  wide: { test: pxSquircle(PX_MID, 41, 26.6, 16.6), ex: 21, ey: 39, my: 48, c: [31.5, 41] },
  drop: { test: (x, y) => {
    const cy = 42, r = 19.6, tip = 13
    if (y >= cy) { const u = (x - PX_MID) / r, v = (y - cy) / r; return u * u + v * v <= 1 }
    if (y < tip) return false
    const s = (y - tip) / (cy - tip), hw = r * s * Math.sqrt(1 - (1 - s) * (1 - s))
    return Math.abs(x - PX_MID) <= hw
  }, ex: 24, ey: 42, my: 51, c: [31.5, 42] },
  bean: { test: (x, y) => {
    const main = pxEllipse(32.5, 40, 26.4, 17.2)(x, y) || pxEllipse(20, 36, 14, 15.4)(x, y)
    const dent = pxEllipse(34, 20.2, 8.5, 4.6)(x, y)
    return main && !dent
  }, ex: 22, ey: 37, my: 47, c: [29, 38] }
}

// Hue -> the face's colours, as hex (computed here, so a saved card picture needs no page CSS).
// A hologram on a screen: a bright neon edge, a lit rim inside it, a body a little darker and softer
// toward the bottom right; features are the body's own hue, very dark.
function pxAgentColours(hue, hue2) {
  const h = ((Number(hue) % 360) + 360) % 360, h2 = ((Number(hue2) % 360) + 360) % 360
  const o = (l, c, hh) => oklchToHex(l, c, hh)
  return {
    o: o(0.91, 0.1, h), r: o(0.79, 0.13, h), l: o(0.73, 0.14, h), b: o(0.66, 0.15, h), s: o(0.57, 0.15, h),
    w: o(0.95, 0.05, h), f: o(0.22, 0.07, h), t: o(0.4, 0.12, h + 25), p: o(0.7, 0.13, h + 330), g: o(0.93, 0.1, h),
    a: o(0.78, 0.14, h2), A: o(0.6, 0.15, h2), k: o(0.93, 0.07, h2), c: o(0.74, 0.15, h2), d: o(0.42, 0.1, h2), q: o(0.25, 0.06, h2),
    glow: o(0.8, 0.15, h)
  }
}

// The body: silhouette, neon outline, a two-cell rim, light top-left, shade bottom-right, a small
// highlight that follows the contour, scanlines on alternate rows (drawn as a separate layer).
function pxAgentBody(shape) {
  const b = PXF_BODY[shape] || PXF_BODY.round
  const m = pxMask(b.test)
  const d = pxDepth(m)
  const g = pxGrid()
  pxPaint(g, pxEdge(m), 'o')
  const [cx, cy] = b.c
  for (let y = 0; y < PX; y++) for (let x = 0; x < PX; x++) {
    const i = y * PX + x
    if (!m[i]) continue
    const dx = x - cx, dy = y - cy
    let s = 'b'
    if (d[i] <= 2) s = 'r'
    else if (!pxAt(m, x + 4, y + 5)) s = 's'
    else if (!pxAt(m, x - 5, y - 6)) s = 'l'
    // the highlight: a short band four cells in, on the upper left (between about 30 and 60 degrees up)
    if (d[i] === 4 && dx < 0 && dy < 0 && -dy > -dx * 0.58 && -dy < -dx * 1.73) s = 'w'
    g[i] = pxCode(s)
  }
  const scan = pxMask((x, y) => m[y * PX + x] && y % 2 === 1 && d[y * PX + x] > 2)
  return { g, m, d, scan, b }
}

// The top of the body at column x (first filled row), and its sides at row y.
function pxTop(m, x) { for (let y = 0; y < PX; y++) if (m[y * PX + x]) return y; return PX }
function pxSides(m, y) {
  let l = -1, r = -1
  for (let x = 0; x < PX; x++) if (m[y * PX + x]) { if (l < 0) l = x; r = x }
  return [l, r]
}

// Features are small drawings, centred where the shape says (rows of slot letters).
const PXF_EYE = {
  dot: ['.ffff.', 'fwwfff', 'fwwfff', 'ffffff', 'ffffff', 'ffffff', 'ffffff', '.ffff.'],
  round: ['..fffff..', '.fffffff.', 'fwwffffff', 'fwwffffff', 'fffffffff', 'fffffffff', 'ffffffwff', '.fffffff.', '..fffff..'],
  wide: ['..ffff..', '.ffffff.', 'ffwwffff', 'fwwwffff', 'fwwwffff', 'ffwfffff', 'ffffffff', 'ffffffff', 'fffffwff', 'ffffffff', '.ffffff.', '..ffff..'],
  big: ['...ffff...', '.ffffffff.', 'ffwwwfffff', 'fwwwwfffff', 'fwwwffffff', 'ffffffffff', 'ffffffffff', 'ffffffffff', 'fffffffwff', 'ffffffffff', '.ffffffff.', '...ffff...'],
  closed: ['ffffffff', '.ffffff.'],
  content: ['ff......ff', '.ff....ff.', '..ffffff..'],
  happy: ['..ffffff..', '.ffffffff.', 'ff......ff', 'f........f'],
  x: ['ff....ff', 'fff..fff', '.ffffff.', '..ffff..', '..ffff..', '.ffffff.', 'fff..fff', 'ff....ff']
}
const PXF_MOUTH = {
  smile: ['ff..........ff', 'fff........fff', '.ffff....ffff.', '...ffffffff...'],
  flat: ['ffffffffff', 'ffffffffff'],
  grin: ['ffffffffffffffff', 'fttttttttttttttf', 'fttttttttttttttf', '.fttttttttttttf.', '.fttppppppppttf.', '..ftppppppppft..', '...ffppppppff...', '.....ffffff.....'],
  cat: ['ff....ff....ff', '.ff..ffff..ff.', '..ffff..ffff..'],
  o: ['..ffff..', '.ffffff.', 'ffttttff', 'fttttttf', 'fttppttf', 'ffppppff', '.ffffff.', '..ffff..'],
  talk: ['..ffffff..', '.fttttttf.', 'fttttttttf', 'ftttpptttf', 'fttppppttf', '.fppppppf.', '..ffffff..'],
  smirk: ['..........ff', '........fff.', 'ff....ffff..', '.ffffff.....'],
  frown: ['....ffff....', '..ffffffff..', '.ff......ff.', 'ff........ff']
}
// a drawing centred on (cx, cy): odd widths on a cell, even widths between two cells
function pxCentre(g, rows, cx, cy) { pxMap(g, rows, Math.round(cx - (rows[0].length - 1) / 2), Math.round(cy - (rows.length - 1) / 2)) }

// Eyes: each kind and frame drawn for the left eye centred on (ex, ey) and the right one on (63 - ex, ey),
// the same way round (both glints on the same side, like one light). Frames: open, closed (a blink,
// asleep), half (waiting, smug), happy, x (error), big (caught, perk), wary (half, glancing aside).
function pxEyes(kind, frame, b) {
  const g = pxGrid()
  const ex = b.ex, ey = b.ey, rx = PX - 1 - ex
  const both = (rows, dx, dy) => { pxCentre(g, rows, ex + (dx || 0), ey + (dy || 0)); pxCentre(g, rows, rx + (dx || 0), ey + (dy || 0)) }
  const paint = (test, slot) => pxPaint(g, pxMask(test), slot)
  if (kind === 'visor') {
    const top = ey - 5, bot = ey + 4, L = ex - 9, R = rx + 9
    paint((x, y) => y >= top && y <= bot && x >= L && x <= R && !((y === top || y === bot) && (x === L || x === R)), 'f')
    paint((x, y) => (y === top + 1) && x > L + 1 && x < R - 1, 'q')
    const lit = rows => { const r2 = rows.map(r => r.replace(/f/g, 'g')); both(r2, frame === 'wary' ? -2 : 0, 0) }
    if (frame === 'closed' || frame === 'half' || frame === 'wary') lit(['ffffffff'])
    else if (frame === 'happy') lit(['..ffff..', '.ff..ff.', 'ff....ff'])
    else if (frame === 'x') lit(['ff...ff', '.ff.ff.', '..fff..', '.ff.ff.', 'ff...ff'])
    else if (frame === 'big') lit(['ffffffff', 'ffffffff', 'ffffffff', 'ffffffff'])
    else lit(['.ffffff.', 'ffffffff', '.ffffff.'])
    return g
  }
  if (frame === 'closed') { both(kind === 'sleepy' ? PXF_EYE.content : PXF_EYE.closed, 0, 1); return g }
  if (frame === 'happy') { both(PXF_EYE.happy, 0, -1); return g }
  if (frame === 'x') { both(PXF_EYE.x); return g }
  if (kind === 'sleepy' && frame !== 'big') { both(PXF_EYE.content, frame === 'wary' ? -2 : 0, 1); return g }
  const k = frame === 'big' ? 'big' : (PXF_EYE[kind] ? kind : 'dot')
  both(PXF_EYE[k], frame === 'wary' ? -2 : 0, 0)
  if (frame === 'half' || frame === 'wary') {
    // a lid: everything above the eye line goes, and the line itself is the lid
    for (let y = 0; y < ey - 1; y++) for (let x = 0; x < PX; x++) g[y * PX + x] = 0
    for (let x = 0; x < PX; x++) if (g[(ey - 1) * PX + x] || g[ey * PX + x]) g[(ey - 1) * PX + x] = pxCode('f')
    for (let i = 0; i < g.length; i++) if (g[i] === pxCode('w')) g[i] = pxCode('f')
  }
  return g
}

// Mouths, centred on the middle line, their top on row my.
function pxMouth(kind, b) {
  const g = pxGrid()
  const rows = PXF_MOUTH[kind] || PXF_MOUTH.smile
  pxMap(g, rows, Math.round(PX_MID - (rows[0].length - 1) / 2), b.my - 1)
  return g
}

// Cheeks, in the second colour, kept inside the body (never on its rim).
function pxPattern(kind, body, g) {
  const b = body.b
  const inside = pxMask((x, y) => body.d[y * PX + x] > 3)
  const paint = (test, slot) => pxPaint(g, pxMask(test), slot, inside)
  const L = b.ex, R = PX - 1 - b.ex, y = b.ey + 6
  if (kind === 'blush') paint(pxAny(pxEllipse(L - 3, y, 4.6, 2.3), pxEllipse(R + 3, y, 4.6, 2.3)), 'c')
  else if (kind === 'freckles') {
    for (const [dx, dy] of [[-6, 0], [-3, 2], [0, 0], [-3, -2]]) {
      paint(pxRect(L + dx - 1, y + dy, L + dx, y + dy), 'd')
      paint(pxRect(R - dx, y + dy, R - dx + 1, y + dy), 'd')
    }
  } else if (kind === 'spots') {
    const [cx, cy] = b.c
    paint(pxAny(pxEllipse(cx - 12, cy - 10, 3.8, 3.4), pxEllipse(cx + 13, cy - 6, 2.8, 2.6), pxEllipse(cx + 10, cy + 10, 2.4, 2.2)), 'c')
  }
}

// What the agent wears, in the second colour, with its own dark outline. Drawn over everything.
function pxAccessory(kind, body) {
  const g = pxGrid()
  const m = body.m, b = body.b
  const top = pxTop(m, 31)
  const [sl, sr] = pxSides(m, b.ey)
  const shapes = []   // [mask, slot] pairs; the outline goes round their union
  const add = (test, slot) => shapes.push([pxMask(test), slot])
  // tall bodies leave little room above: tall things on top come down so they stay whole, outline and all
  const lift = Math.max(0, 16 - top)
  if (kind === 'antenna') {
    const ay = top - 11 + lift
    add(pxRect(31, ay + 3, 32, top + 1), 'A')
    add(pxEllipse(PX_MID, ay, 3.6, 3.6), 'a')
    add(pxRect(30, ay - 2, 30, ay - 1), 'k')
  } else if (kind === 'glasses') {
    const L = b.ex, R = PX - 1 - b.ex
    add(pxAny(pxRing(L, b.ey, 7.4, 6.6, 1.8), pxRing(R, b.ey, 7.4, 6.6, 1.8), pxRect(L + 7, b.ey - 2, R - 7, b.ey - 1)), 'a')
  } else if (kind === 'headphones') {
    // the cups hug the sides, but never closer than a cup and its outline to the edge
    const cl = Math.max(sl - 0.5, 5), cr = Math.min(sr + 0.5, PX - 6)
    const w = (cr - cl) / 2 + 1.7, cy = b.ey + 1
    add((x, y) => y <= cy - 6 && pxRing(PX_MID, cy, w, cy - top + 6, 3)(x, y), 'a')
    add(pxAny(pxSquircle(cl, cy, 3.6, 7.4), pxSquircle(cr, cy, 3.6, 7.4)), 'A')
    add(pxAny(pxRect(cl - 1.5, cy - 4, cl - 1.5, cy + 2), pxRect(cr + 0.5, cy - 4, cr + 0.5, cy + 2)), 'k')
  } else if (kind === 'halo') {
    add(pxRing(PX_MID, top - 7, 13.6, 4.2, 2.2), 'k')
  } else if (kind === 'sprout') {
    const sy = top + lift
    add(pxAny(pxLine(31.5, top + 1, 31.5, sy - 6, 2), pxLine(31.5, sy - 6, 33, sy - 8, 2)), 'A')
    add(pxAny(pxEllipse(26, sy - 9, 5.4, 2.8), pxEllipse(37.5, sy - 11, 4.6, 2.6)), 'a')
    add(pxAny(pxRect(23, sy - 10, 25, sy - 10), pxRect(36, sy - 12, 38, sy - 12)), 'k')
  } else if (kind === 'horns') {
    for (const s of [-1, 1]) {
      const bx = PX_MID + s * 11, by = pxTop(m, Math.round(bx)) + 3
      add(pxTri(bx - s * 4.5, by, bx + s * 4.5, by, bx + s * 5.5, by - 11), 'a')
      add(pxLine(bx + s * 2.5, by - 1, bx + s * 4.6, by - 8, 1.2), 'k')
    }
  } else if (kind === 'bow') {
    const x = 44, y = pxTop(m, 44) + 1
    add(pxAny(pxTri(x, y, x - 8, y - 5, x - 8, y + 5), pxTri(x, y, x + 8, y - 5, x + 8, y + 5)), 'a')
    add(pxEllipse(x, y, 2.4, 2.4), 'A')
    add(pxAny(pxRect(x - 7, y - 3, x - 6, y - 3), pxRect(x + 5, y - 3, x + 6, y - 3)), 'k')
  }
  if (!shapes.length) return g
  let all = new Uint8Array(PX * PX)
  shapes.forEach(([mk]) => { all = pxOr(all, mk) })
  pxPaint(g, pxEdge(all), 'o')
  shapes.forEach(([mk, slot]) => pxPaint(g, mk, slot))
  return g
}

// Which eyes and mouth a state or a reaction shows.
function pxAgentFrames(state, expr) {
  if (expr === 'smug') return { eyes: 'half', mouth: 'smirk' }
  if (expr === 'caught') return { eyes: 'big', mouth: 'o' }
  if (expr === 'happy') return { eyes: 'happy', mouth: 'grin' }
  if (expr === 'wary') return { eyes: 'wary', mouth: 'flat' }
  if (expr === 'perk') return { eyes: 'big', mouth: null }
  if (state === 'waiting') return { eyes: 'half', mouth: 'flat' }
  if (state === 'error') return { eyes: 'x', mouth: 'frown' }
  if (state === 'absent') return { eyes: 'closed', mouth: 'flat' }
  return { eyes: 'open', mouth: null }
}

const PXF_CACHE = pxCache(240)

// Everything needed to draw one agent face in one state: grids per layer, and colours.
function pxAgent(f, eyesFrame, mouthKind) {
  const key = [f.shape, f.eyes, f.mouth, f.acc, f.pattern, f.hue, f.hue2, eyesFrame, mouthKind].join('|')
  return PXF_CACHE(key, () => {
    const body = pxAgentBody(f.shape)
    const base = body.g.slice()
    pxPattern(f.pattern, body, base)
    const eyes = pxEyes(f.eyes, eyesFrame, body.b)
    const blink = eyesFrame === 'open' ? pxEyes(f.eyes, 'closed', body.b) : null
    const mouth = pxMouth(mouthKind || f.mouth, body.b)
    const talk = pxMouth('talk', body.b)
    const acc = pxAccessory(f.acc, body)
    const colours = pxAgentColours(f.hue, f.hue2)
    return {
      base: pxPaths(base), scan: pxPaths(body.scan.map(v => v ? pxCode('n') : 0)),
      eyes: pxPaths(eyes), blink: blink && pxPaths(blink), mouth: pxPaths(mouth), talk: pxPaths(talk), acc: pxPaths(acc),
      under: pxPaths(pxUsed(base, acc).map(v => v ? pxCode('o') : 0)),
      colours, grids: { base, eyes, mouth, acc }
    }
  })
}
