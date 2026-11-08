// ---------------------------------------------------------------------------------------------
// people, drawn: the person renderer. It takes a clean avatar (ui/14_avatar.js) and draws a still bust.
// The rest of the UI uses only this interface, so the part source and the grid can change here alone:
//   PersonAvatar({ avatar, size, className, label, view })   the drawing (an <svg> in a span)
//   AV_ART.grid                                              the grid size the art and views are in
//   AV_ART.views.face                                        the editor's close-up crop on the face
//   avSwatch(key, id)                                        a colour for the editor's swatches (sk, hc, tc)
// Today: a 64 x 64 grid on the agents' renderer (ui/12_pixel.js). Hair is drawn from run-length rows
// (converted from image drafts on one fixed template); everything else is built from shapes in code.
// This art is a working placeholder: a later pass draws generated layers on a 96 x 96 base instead.
// ---------------------------------------------------------------------------------------------

// ---- colours: [light, base, shade, outline] per material -------------------------------------------
const AV_SKIN_TONES = [
  ['#fbe7da', '#f2d3c0', '#d9ae9c', '#6b4a45'], ['#f5d9c2', '#e9bf9f', '#c99a85', '#634238'],
  ['#ecc7a4', '#ddac85', '#b88671', '#5b3a2e'], ['#e3b48c', '#cf9a6f', '#a9765f', '#523325'],
  ['#d6a27a', '#bf8559', '#98654f', '#4a2c1f'], ['#c38d63', '#a96f45', '#85563f', '#3f2519'],
  ['#a97650', '#8f5a36', '#6d4433', '#341d13'], ['#8c5f3f', '#744628', '#573427', '#2a170f'],
  ['#6f4a32', '#5a361f', '#432820', '#20120b'], ['#5a3b29', '#452817', '#331e19', '#170c07']
]
const AV_HAIR_TONES = {
  black: ['#3b3f4c', '#22242c', '#14151b', '#07080b'], darkbrown: ['#5a4235', '#3e2b22', '#2a1c17', '#110b09'],
  brown: ['#8a6141', '#6a462d', '#4b3020', '#1f130c'], auburn: ['#a2503a', '#7f3a28', '#5a271d', '#26100b'],
  ginger: ['#e39352', '#c56e33', '#94502a', '#3e1f0f'], blonde: ['#f1d996', '#d9b465', '#ad8a4c', '#4a3a1c'],
  platinum: ['#f6f3ea', '#ddd8cb', '#b2ada3', '#4f4c47'], grey: ['#c3c7cc', '#989da4', '#70757d', '#2d3035'],
  ice: ['#c8ecfa', '#8fc6de', '#5e93b0', '#1d3a4a']
}
const AV_TOP_TONES = {
  navy: ['#3d5577', '#26384f', '#18243a', '#080d16'], steel: ['#5f7d92', '#40596b', '#2b3d49', '#0e161c'],
  slate: ['#6c7180', '#4c5160', '#353845', '#121319'], charcoal: ['#474b52', '#2f3237', '#1f2125', '#0a0b0d'],
  glacier: ['#b2d0de', '#7fa6ba', '#5b8196', '#1d3340'], teal: ['#3f7c86', '#275a63', '#183e45', '#07181b']
}
const AV_INK = { e: '#e8eef1', i: '#1b1d24', o: '#101218', w: '#ffffff', m: '#3a1820', l: '#b45e5e', p: '#d97b84',
  G: '#15171c', g: '#cfe6f1', q: '#e6b955', Q: '#9c742a', B: '#121b23', b: '#182531', c: '#39434f', C: '#8fb3c7' }

function avColours(a) {
  const sk = AV_SKIN_TONES[a.sk] || AV_SKIN_TONES[3]
  const hr = AV_HAIR_TONES[a.hc] || AV_HAIR_TONES.darkbrown
  const tp = AV_TOP_TONES[a.tc] || AV_TOP_TONES.navy
  const alt = AV_TOP_TONES[AV_TOP_COLOURS[(AV_TOP_COLOURS.indexOf(a.tc) + 4) % AV_TOP_COLOURS.length]]
  const c = Object.assign({}, AV_INK)
  ;['j', 'k', 'K', 'u'].forEach((s, i) => { c[s] = sk[i] })
  ;['y', 'h', 'H', 'Y'].forEach((s, i) => { c[s] = hr[i] })
  ;['v', 't', 'T', 'V'].forEach((s, i) => { c[s] = tp[i] })
  ;['r', 'n', 'N', 'R'].forEach((s, i) => { c[s] = alt[i] })
  c.l = sk[2]
  // the night's rim light: each material's own light tone, turned towards ice
  c.z = avMix(hr[0], AV_ICE, 0.45)
  c.x = avMix(tp[0], AV_ICE, 0.5)
  c.Z = avMix(alt[0], AV_ICE, 0.5)
  return c
}
const AV_ICE = '#9fc3d6'
// a + (b - a) * t, per channel, on #rrggbb colours
function avMix(a, b, t) {
  const ch = (h, i) => parseInt(h.slice(1 + i * 2, 3 + i * 2), 16)
  return '#' + [0, 1, 2].map(i => Math.round(ch(a, i) + (ch(b, i) - ch(a, i)) * t).toString(16).padStart(2, '0')).join('')
}


// ---- the template: one cranium for everyone, four jaws, all on fixed lines ------------------------------
// Every part is drawn against these: hair against the cranium, glasses against the eye line, and so on.
const AV = { cy: 25, rx: 15.5, ry: 18.6, jaw: 27, eye: 30, ex: 24.5, brow: 25, nose: 34, mouth: 40, neck: [24, 39, 40], torso: 51 }
const AV_CRANIUM = pxEllipse(PX_MID, AV.cy, AV.rx, AV.ry)
const AV_JAW = {
  oval: { chin: 46, hw: t => 15.5 * Math.sqrt(1 - t * t * 0.9) },
  round: { chin: 45, hw: t => 16 * Math.sqrt(1 - t * t * t * t * 0.8) },
  square: { chin: 46, hw: t => t < 0.58 ? 15.4 : 15.4 - (t - 0.58) * 15.5 },
  long: { chin: 48, hw: t => 14.6 * Math.sqrt(1 - t * t * 0.94) }
}
function avHead(fs) {
  const j = AV_JAW[fs] || AV_JAW.oval
  return pxMask((x, y) => {
    if (y <= AV.jaw) return AV_CRANIUM(x, y)
    if (y > j.chin) return false
    return Math.abs(x - PX_MID) <= j.hw((y - AV.jaw) / (j.chin - AV.jaw))
  })
}
const AV_EARS = pxMask(pxAny(pxEllipse(15.6, 31, 2.6, 4.6), pxEllipse(47.4, 31, 2.6, 4.6)))

// Paint a material: its own darkest tone on its edge, base inside.
function avFill(g, m, base, line) {
  const d = pxDepth(m)
  for (let i = 0; i < m.length; i++) if (m[i]) g[i] = pxCode(d[i] <= 1 ? line : base)
  return d
}
// Shade on the side away from the light (right and below), light on the near side.
function avLight(g, m, d, shade, light, k) {
  for (let y = 0; y < PX; y++) for (let x = 0; x < PX; x++) {
    const i = y * PX + x
    if (!m[i] || d[i] <= 1) continue
    if (!pxAt(m, x + k, y + 1) || !pxAt(m, x + 1, y + k)) g[i] = pxCode(shade)
    else if (light && !pxAt(m, x - k, y - k)) g[i] = pxCode(light)
  }
}
// A cool rim of night light inside the top right edge of a material.
function avRim(g, m, d, slot, fromX) {
  for (let y = 0; y < PX; y++) for (let x = fromX; x < PX; x++) {
    const i = y * PX + x
    if (m[i] && d[i] === 2 && !pxAt(m, x + 2, y - 2)) g[i] = pxCode(slot)
  }
}

// Skin: the head lit as a rounded form from the upper left, the far cheek and the jaw's underside in shade.
function avSkin(g, head, chin) {
  const skin = pxOr(head, AV_EARS)
  const d = avFill(g, skin, 'k', 'u')
  for (let y = 0; y < PX; y++) for (let x = 0; x < PX; x++) {
    const i = y * PX + x
    if (!skin[i] || d[i] <= 1) continue
    if (!pxAt(head, x + 5, y) || !pxAt(head, x + 2, y + 3) || y >= chin - 1) g[i] = pxCode('K')
    else if (!pxAt(head, x - 4, y - 3) && y < AV.eye) g[i] = pxCode('j')
  }
  // a lit forehead and cheekbone, inner ears
  pxPaint(g, pxMask(pxAny(pxEllipse(25, 15, 5, 3.2), pxEllipse(22.5, 35, 3, 1.4))), 'j', pxMask((x, y) => g[y * PX + x] === pxCode('k')))
  pxPaint(g, pxMask(pxAny(pxRect(15, 29, 15, 33), pxRect(48, 29, 48, 33))), 'K')
  return skin
}

// ---- hair ------------------------------------------------------------------------------------------------
// Drawn parts, as run-length text: "row:" then per row runs of <count><letter> ('.' is nothing), rows split by
// '/'. Letters: y light, h base, H shade, Y line. A style is one layer, drawn over the head and shoulders; it
// never covers the face below the brows, so it sits right on every jaw. Drafted against one fixed template head,
// then cleaned on the grid.
function pxRle(text) {
  const g = pxGrid()
  if (!text) return g
  const cut = text.indexOf(':')
  let y = Number(text.slice(0, cut))
  for (const row of text.slice(cut + 1).split('/')) {
    let x = 0
    row.replace(/(\d*)(\D)/g, (_, n, ch) => {
      const k = n ? Number(n) : 1
      if (ch !== '.') for (let i = 0; i < k && x + i < PX; i++) if (y < PX) g[y * PX + x + i] = pxCode(ch)
      x += k
      return ''
    })
    y++
  }
  return g
}
const AV_HAIR_ART = {
  short: '4:28.9Y/24.5Y6yh5Y/22.3Y6y8hH2Y/20.2Y7y8h4HY/20.Y3y9h8H3Y/18.3Y3y2h2y3h4H5h3H2Y/18.Y3y2h3y3h4H7h3H2Y/17.2Y7y3h2H8h6HY/17.Y2y2h3y12h8H2Y/16.2Yy2h2y8h2H3h4H3Y3HY/16.Y4hy4h6H3h4H6YH2Y/16.YhHhy4hH4YH3h3H4Y6HY/16.2Y2h2H2h3Y2.Y3h2H3Y.Y7HY/16.2Y2hHYh2Y3.Y2h4Y4.5Y3HY/16.2Yh2Y.2Y4.4Y10.3YH2Y/17.4Y21.6Y/17.Y2HY22.Y2HY/17.Y2HY22.Y2HY/17.YhY24.YHY/17.YhY24.YHY/17.YHY24.YHY/17.3Y24.3Y',
  curly: '2:31.4Y/30.Y3yhY/25.2Y2.Y2y2HhY/22.3Y2y2Y2y3H8Y/21.Y7yH2hY4yhY2H2Y/17.3Y.Y2yh4H3hYy2Y3h2YHY/16.Y3y3YHh2yHYH2hH3YH2hYH5Y/15.Y2y2H6yH2yYH2hH2Y2hH3Y2H2hY/15.Yy2Yh10yH4Y3h8YhY/15.YhHY2y2H2h3y2HY2y2h5Y3h5Y/16.YHYy5H2y2HY2y3hH4YH3h3Y/14.3YyHhH4Y2hHY2yH2YHhY3H2Y3hYH4Y/13.Y4yhHY2yh2Y2HYyh4YHY3HhYH2hY4HY/12.Y2y4HYy3hH4Y2hH4YH2YHhYHh3Y2HY/12.Yh2H3yhHhH2YH2hHY2H7YH6YH4Y/12.Y2HYyHY3h2Y2y2hH4YH4YH7Y2hHYHY/13.2Y2h3YH3Y2h6Y2h2Y2.YHY.4YHYhYH2Y/12.3Y2hYH3Y2.YHY2.2Y2h3Y3.2Y2.5Yh4Y/12.4Y2hH2Y3.3Y2.YhH3Y4.2Y2.2YH7Y/11.Yy2h6Y8.YhHY9.Y4H5Y/11.Y2H2Y2H2Y10.2YHY8.Y4H2YHY/11.YH2YhH3Y12.2Y9.YHY4HY/12.YHYhH3Y12.2Y10.3Y2H3Y/12.YHY2H2Y26.5YHY/12.5Y30.4Y/12.3Y32.4Y/13.2Y34.2Y/13.2Y34.2Y/13.2Y',
  long: '4:26.5Y2.5Y/24.2Y5y2Y5h3Y/21.3Y4y5h5H2h3Y/20.Y3y13h3H3hY/19.Y3y4h3y9h4HhY/18.Y2y4h4y12h4HY/17.Y2y3h3y10h3H3h4HY/17.Y2yh4y5h4Y4h2H3h3HY/16.Y2yh4y4h2Y4.2Y3h2H3h3HY/16.Yy2h4y3hY8.Y3h2H3h2HY/15.Yy2h4y3hY10.Y3h2H2h3HY/15.Y2h3y5hY10.Y3h3H2h2HY/15.Y2h2y5hY12.Y2h4H2hHY/14.Y2h3y4hY14.Yh4H2h2HY/14.Y2h2y5hY14.Y2h4Hh2HY/14.Y2h2y4hY16.Y2h3Hh2HY/14.Y2hy4hY18.Y2h2HY2HY/13.Y2h2y4hY18.Y3hHY3HY/13.Y2hy4hY20.Y3hY3HY/13.Y2hy4hY20.Y3h2Y2HY/13.Yhy4h2Y21.Y3hY2HY/13.Yhyh4Y22.5Y2HY/12.Y2hyY30.2Y2HY/12.Y3hY30.2Y2HY/12.Y3hY30.2Y2HY/12.Y3hY30.3YHY/12.YhHhY30.YhYHY/12.YhHhY30.YhYHY/12.YhHhY30.YhYHY/12.YhHhY30.YhYHY/12.YhHhY30.YhYHY/12.YhHh2Y28.2Yh2HY/12.YhHh2Y28.2Yh2HY/12.YhHh3Y26.3Yh2HY/12.YhHh3Y26.YHYh2HY/12.YhHh2YHY24.Y2HYh2HY/12.YhH2Y2HY24.Y2HYhYHY/12.YhH2Y3HY22.Y2Hh3YHY/11.Y2hH2Y3H2Y20.Y3Hh3YHY/11.Y2hH2Y3H3Y18.Y4Hh3YHY/11.Y2hH2Yh2HY2HY16.Y2H2hH2h2Y2HY/11.Y2hHYHh2HY2HY16.Y2H2hH2h2Y2HY/11.Y2hHY2h5HY16.Y2H2hH2h2Y2HY/11.YhYHY2h2HhYHY16.Y2H2hH2h2Y2HY/11.YhYHY2h2HhYHY16.2YH2hH2h2Y2HY/11.YhYHY2h2Hh3Y16.2YH2hH2h2Y2HY/10.YhHYHY2h2Hh3Y16.2YH2hH2h2YH2Y/10.YhHYHY2h2Hh3Y16.2YH2hH2h2YHYHY/10.YhHYHY3hHh3Y16.2YH2hH2h2YHYHY/10.YH2YHY3hHh2Y18.YH2hH2h2YHYHY/10.2Y.YhY3hHh2Y18.Yh3H2hYH2YHY/13.YhY3hHh2Y18.Yh3H2hYHY.2Y/13.YhY3hH2hY18.Yh3H2hYHY/13.YhY3hH3hY16.Y2h3Hh2YhY/13.YhY3hH3hY16.Y2h3Hh2YhY/13.3Y3hH3hY16.Y2h3Hh4Y/15.Y3h2H2hY16.Y2h3Hh2Y/15.Y3h2H2hY16.Yh4Hh2Y/15.2Y2h3HhY16.Yh4Hh2Y/16.8Y16.8Y',
  bun: '0:30.4Y/30.4Y/28.2Yy3h2Y/27.Y4y3hHY/26.Y4y3h3HY/25.Y7h3H2Y/25.Y3h6H3Y/25.2YH10Y/26.2Yy2Hyh2H2Y/24.3Y2yH2y2hH2h3Y/23.2YH2yH2y3hH3hH2Y/22.Y2yH2yHy4hH3hH2hY/21.Y3y2Hy2H3h2H2h2H3hY/20.YH4y2Hy2H2hYHh2H3h2HY/19.Yy3H2yhHh4HY4H2h4HY/19.Y2y5H10Y3HYHhHY/18.Y2h2y2H2Y10.3YH2h2HY/17.Y2H2h3Y15.2Y3H2Y/17.YhH2Y20.2Y2HY/17.YHhY21.Y2H2Y/16.YhH2Y22.2YHY/16.Yh2HY22.Y2HY/16.YH2Y24.3Y/16.YHY25.3Y/16.YHY26.2Y/17.2Y26.2Y',
  locs: '1:31.2Y/25.3Y2.YyhY.3Y/24.Y2yh4Y2h2Y2h2Y/21.3Y3y4hHYhHYHhHh3Y/19.2Yh2y6Y2h2YH5YHyHY/18.8Y3h2Y2H2Y3h2HY3H2Y/17.Y2y3hY2y4hHYHY2h4H6Y/15.2Y2yh2HY2yh3YHhHYhH6Y3hH3Y/15.YyhH4Yyh5Y2HYH2Y3h2YH6hY/14.YyhH2Y2h3Y2hH3YH3Y2hH2h6YHhyY/14.YhHY2h2H2Y2hH2Y2.2Y.4YH2hY2h3Y2HY/14.YHYy2hH2YyhHY10.2YH2hY2hH2Y2HY/13.4Yyh3YyhHY12.2Y2h2YH2h2YHY/12.Y2hYyhH3YyHY14.Y2h3YH2h3Y/11.YHh2YyH3YyhY15.2Y2h2YHhH4Y/11.YhHYyhH3Y2hY16.Y2h4Y2hYHY/10.YhH2YhH4Y2hY16.YHh4Y2hYhyY/10.YH3YhH3YhHY18.YH4YH2hYHY/11.2YhYh4YhHY18.YHhH3Y2HYH2Y/10.YyhH5Y2hHY18.YH2hY2H3YHhY/9.Yy2h3YHY2hHY19.YHhHY2H3YHh2Y/9.YyhH2Y2HYHhHY20.YhH2Y2h3YHhY/9.YhH2YHhHY2H2Y20.Y2h3Y2h2YHhY/9.YhHY3hY2h2Y21.YHhH2YHhy2YHY/9.Yh2Y2h6Y21.7YH2hYHY/8.YyHYhH3Y30.3YHhYHY/8.YHYyh4Y32.Y2H2Y/8.YHYyhY2.Y33.YHhY/9.2YhHY2.Y33.YHhY/9.YyhY3.Y33.2YhY/9.YyhY38.YHhY/8.Yyh2Y38.YHhY/8.Yyh2Y38.2YHY/8.Yyh2Y38.2YHY/8.Yh2YHY2.2Y28.2Y.2YhYHY/7.Yyh2YhH2YHY28.4Y2hYHhY/7.YhHY2hH2YhHY26.2YH2Y2hY2HY/7.Yh2YhH3YyhY26.YHh2YHh2YHY/8.2Y2hHYHY2hY26.Y2h2YHhHYHY/9.Y2hY2HYHhHY24.2Y2h3YHh2Y/8.Yyh2Y2H2Y2h2Y22.2Y2h2YHYHhY/8.Yyh2YhH3YhHY21.2YHhHY2HYHhY/8.YhHY2hH3YH4Y18.3YHhHY2H2Y2hY/7.2Yh2YhHY2H4YHY17.4YhH3Y2HYHhY/7.Yyh2YhHY2H4Y2HY16.YHY2hH3YHhYHhY/7.YyH2YhHY2H4Y2hY16.YHY2hHYHYHh2Y2hY/7.YhH2YhHY2h3Y2hHY16.YHY2h2YhYHh2YHhY/7.YhHYyh2Y2h2YHh2HY16.Y2HhHYHhYHh2YHhY/7.YhHYyh2YyhHYHhH2Y16.2YhH2YHh2Y2hY2HhY/6.Y2h2Yyh2Y3hY2H3Y16.2Y2h3Y2hY2h2YHhY/6.Y2h2YyhYHYyhY2H3Y16.2YhH3Y2hYHhHYHhY/6.YhH2YhHYHYyh2Y2h2Y16.2YhH3YHh2Y2hYHhY/6.Y2HYyh2YHYyH2Y2hY18.YhH3YHh2YHh2YHY/6.Y2HYyh4Yy3Y2hY18.YhH3YHh2YHh2YHY/7.3Y2hY.Yyh3YH2Y17.Y2hHYHYHy3Yh3Y/9.YhHY.Yyh5Y18.YhHY.2YHyY.YhY/9.YhHY.YhHY22.YhY2.2Y2yY.YHY/9.YhY2.YhY23.YHY2.2Yh2Y2.2Y/10.2Y2.YhY23.3Y2.2YhY/14.3Y28.2YHY/47.2Y',
  bob: '6:27.10Y/24.3Y4y5hH2Y/21.3Y5y8h2H3Y/20.YH5y12h3HY/19.Y6y14h3HY/18.Y3yh2y11hH4h3HY/17.Y2y2h3y4hy7h2H3h3HY/17.Yy2h3y3h2y9h2H2h3HY/15.2Yy3h3yh4y9h3Hh4HY/15.Yy3h8y4hH6h4Hh2HY/15.Yy3h3y2h3y4hH6h4Hh3HY/15.Y4h2y2h3yH3h2H3hH2h4H2h2HY/15.Yhyh2y3h2yhH3h2H3hH3h4H2hHY/14.YhyhY2yhHhyh2H2h3HY2h2H3h3H2h2HY/14.YhyhYy2hYhyh2H2h3HY2h2H3hYh2Hh2HY/14.YhyhYy2hY3hYH2hY2HY2hHY3hYh2H2hHY/13.Yh2yhY3hY3hYH2hY2HY2hHY3hYh2H2h2H2Y/13.Yhy2hY3hY3hYH2hY2HY2h2Y2h2Yh3H2h2HY/12.Yh2yh2H3Y.3Y.3Y.2Y.2Y.3Y2.2Y2H2h2HY/12.Yh2yH3Y24.3Yh2H2Y/12.Yh2yY30.Y2H2Y/12.Y2yHY30.Y2H2Y/12.Y2yHY30.Y2H2Y/12.Y2yHY30.Y2H2Y/12.Yy2HY30.2YH2Y/12.Yy2HY30.2YH2Y/12.YhHhY30.2YH2Y/12.Y2HhY30.2Y2HY/12.2Y2hY30.Y2H2Y/12.2Y2hHY28.Y4HY/12.2Y2hHY28.Y3HY/13.Y2hH2Y26.2Y3HY/13.Y2hH2Y26.2Y3HY/13.Yh2HYhY24.YhY3HY/13.Yh2HYhY24.YhY2HY/14.Y2H2YhY22.YH2Y2HY/14.Y3HY2hY20.YhH3YHY/15.YhHY2h2Y18.2Yh5Y/16.7Y18.7Y',
  wavy: '3:28.7Y/24.4Y5y2h2Y/23.Y5y7hHY/21.2Y3y5h3H3hH4Y/19.2Y4y8h3H2hYH2h2Y/18.Y6y5h2y3h2HhY2H2h2Y/17.Yh4y4h4y5h2HYH4h2Y/16.Y5y2h5y4h2YhH2Y3H3h2Y/16.Y2y4h5y4h4YHY3h4H2Y/15.Y2y4h5y4h6YH4h5HY/15.Yy4h4y6hY5.3Y3h4HY/15.Yy2h3y2hy5hY8.YH3h3HY/14.2Y8hy5hY8.YH3h4HY/13.Y4y5h2y5hY9.Y6h2HY/12.Y4y5h2y5hY10.2Y8hY/11.Y2y7h3y4hY11.2Y3H5hY/11.Yy6h4y4hY13.Yh6H2hY/11.Yy3h5y4h2Y14.Y4h4HhY/11.Y2h2y7h2Y16.YH5h3HY/10.Yh4y4h3Y19.2Y5h2HY/10.Y4y4h2Y22.2Y5hHY/9.Y2y2h4HY24.4Y4hHY/9.Y2y3H2h2Y26.4Y3hY/9.Yy3H2hY30.3Y3hY/9.Yy2H3hY30.4Y2hY/10.YH3h2Y31.3YHhY/10.YH2h2Y33.Y2HhY/10.Y2h2Y34.Y2HhY/9.Y2yh2Y34.Y2HY/9.Y2yH2Y34.Y2HY/8.Y2y3HY34.YHY/8.Y2y2Hh2Y32.Y2HY/8.Yy2H2hH2Y30.Y2H2Y/8.Yh2Hhy2h2Y28.Y3H3Y/8.Yh2Hh2y2h2Y26.2Y3H2YHY/9.Y3H3y2hY26.2Y2HhHY2HY/10.2Y2H3yhY25.4YH2hHY2HY/11.Y3H2y2hY24.4YH4hYHY/11.Y4Hy2h2Y22.YH4YH3hYHY/10.2Yh3Hy2h3Y20.Y4H3Y4h2Y/9.2Y2h2H3hH4Y18.2Y5H3Y3hY/9.Yyh2H3hH6Y16.4Y4H3Y3hY/8.Y2y2H3h4Y2H2Y16.5Y3H3Y2hHY/8.Yy2H3h4Y3H2Y16.5Y3H2Y2hHY/8.Yh2H3h3Y3H3Y16.4Y3H2Y2h2Y/8.Y3H3h2Y3H4Y16.3Y4HY2h2Y/9.Y2H3h2Y2H5Y16.2Y4H2Y2h2Y/9.YHY3h2Y3H4Y16.2Y3H3Y2hY/10.2YH3h3YH4Y16.2Y2H4Y2hY/11.2YH4h3Y2HY16.2Y2H5Y2hY/12.3Y3h5Y19.3Y.6Y/15.3Y',
  afro: '0:26.5Y2.6Y/19.4Y.3Y3yh2Y5h8Y/18.2Y3yYH4y3hY7h2Y3h2Y/17.Y4y25hY/16.Yh3y11h4y3h2H7hY/14.3Yhy11h6y4h8H3Y/13.Y2y6h3y4h3y9h6H4hY/11.3Y3y2h7y3hy11h3H8h3Y/9.2Y12y17h4H10hY/8.2Y12y14h7H7h2H2hY/8.Y2y3h7y17h8H4h2H2h3Y/7.2Yy3h4y2hy11hH7h9H2h2H3h3Y/6.Y3y2h4y13h5H5h9H2h4H3h2Y/6.Y2y2h3y9h4H3h3YH4h17H2h2Y/6.Yy3hy10h4H4Y3.YHh19H2h3Y/5.Y2y3hy8h4H2Y8.5YH2Y13H4hY/4.Y3y13hH2Y14.3Y14H4hY/2.2Y5y10hH2Y19.Y2HY7H8hY/2.2Y2y9h4HY22.3Y5H10hY/2.2Yy6h3yh3HY25.Y9H3h2H2hY/3.YH4h4y3hHY26.3Y8H2h3HhY/2.2Y5h2y6hY28.Y13H2Y/.2YH5hy6hHY28.Y14HY/.Y7hy5hH2Y28.Y15HY/.Y5h2H5h2HY30.Y4H3Y7HY/Y5h3H4h3HY30.Y3H4Y3H2Y3HY/Y4h3H5h3HY30.13Y3HY/YH2h4H2h5H2Y32.10Y4HY/.2Yh2H3h5HY35.5Y7HY/2.Y4H2h4HY36.4Y8HY/2.2Y8H2Y36.2Y9HY/2.Y8H2Y37.2Y9HY/2.Y7H4Y36.2Y2HY5HY/2.2Y6H4Y36.5Y4H2Y/2.2Y2H2Y5HY36.5Y4HY/4.5Y5HY34.5Y3H3Y/5.5Y3H5Y28.6Y5H2Y/5.6YH7Y26.7Y6HY/5.14Y26.4Y5HY2HY/6.14Y24.6Y3H4Y/9.5YH5Y24.11Y/9.4Y3H5Y22.11Y/9.4Y5H4Y20.4Y2H6Y/11.3Y3H6Y18.4Y3H5Y/13.Y2H8Y16.5Y3H2Y/14.10Y16.9Y/18.6Y16.4Y/18.6Y16.4Y/20.3Y18.2Y',
  ponytail: '4:30.6Y/27.3Y4yh4Y4.6Y/25.2Y4y8hY2.Y4h3Y/24.Y5y5h5H2YH2h5Y/22.2Y3yhH4hHYH6h3Y5h2Y/21.Y3yhyHhy2h2H4h5H2Y6hY/20.Y3yhyhH3h2H3h3H4hHY4H2hHY/19.Y2y4h2H3hH3h2H7hHY4H2hY/19.Y2yhH2h2H2h2H3hH4h3H2h3Y3HhY/18.Y3yh2Hh2H2h2H2hH3h8H2Y3H2hY/18.Yy3h2H2hH7Y2h2H7h3Y3HhY/17.Y2yhH2h4Y7.4Y4H3h3Y3HhY/17.Yy3h2Y15.2Y5H3Y4HY/17.Y3hY19.2Y3H3YHh2H2Y/16.YH2hY22.YH4YHh2HhY/16.YhHY24.Y2H2Y2Hh2HY/16.Y2hY24.Y2H2Y2Hh2HY/16.YHY26.YH2Y3HhHY/16.YHY26.YH2Y3HhHY/16.YHY26.YH3Y2H2hY/16.2Y28.4Y3HhY/16.2Y28.4Y3HhyY/49.Y3H2hY/49.2Y2H2hY/51.Y2HhY/51.Y2HhY/51.Y2HhY/51.Y2HhY/51.Y2H2hY/51.Y2H2hY/51.YhH2hY/50.YHh2HhY/48.3YHh2HhY/47.Y2HYHh2HhHY/47.Yh2Yy2h3HY/47.YhYHy2h2HhY/46.Y2hY2y2h2HhY/45.YHh2Hy2h4HY/45.Yh2H2y2h4HY/45.Y2H2y3hHY2HY/44.Y3H2y3hHY2HY/44.Y2H2y3h2HY2HY/44.YHhy4h2HYHY/44.YHy5h2HYHY/43.YH2y4h2HY2HY/43.Y2y4h3HY2HY/43.Yy4h4HYHY/42.Y6h3H2YHY/42.Y5hHY2HYHY/41.YH2hHh4H4Y/41.Y2hH2h4H2Y/41.Yh2Hh2HYH2Y/41.Yh2HhH2YHY/41.YHY2h4Y/41.YHY2hY.2Y/42.3YHY/44.3Y/45.2Y',
  swept: '1:42.3Y/32.7Y2.2YhY/32.Y4y2h3Y2hY/26.6Y3y3h3Y3hY/23.4Y6y11hY/22.2Y4y10hH4hH3Y/21.Y4y10h2H4h2HYHY/19.2Y4y2h3y2h5H4h2H2YHY/18.2Y2y3h3y5H6h3H2Y2HY/18.2Yy3h2y5H7h4H2Y2HY/18.Y2y2h2y3H5h4Y4H2Y2H2Y/17.YhHy2hy3H3h5Y3H4Y3HY/17.Y2hHYh3H2h4Y4H4Y4H2Y/16.2Y3hYh6Y5H4Y4H5Y/16.Y2h2H3Y4.8Y3H6YHY/16.Yh3HY11.9Y4HY/16.2YHhY20.2Y3HY/16.2Y2HY22.Y2HY/16.2YHY23.2YHY/17.YHY24.YHY/17.YHY24.YHY/17.2Y25.YHY/17.2Y25.YHY/17.2Y26.2Y'
}

// Copy a drawn part onto the grid where `keep` allows (a hat covers what is under it).
function avStamp(g, part, keep) {
  for (let i = 0; i < part.length; i++) if (part[i] && (!keep || keep[i])) g[i] = part[i]
}

// ---- face features ---------------------------------------------------------------------------------------
// Left-side drawings (mirrored for the right). o: line, e: white, i: iris, w: glint, Y: brow (the hair's line
// colour), m: mouth, p: tongue, l: lip.
const AV_EYE = {
  open: ['.oooooo.', 'oeeiiwo.', '.eeiiie.'],
  smile: ['..oooo..', '.oo..oo.', 'o......o'],
  almond: ['...ooooo', '.ooeiiwo', 'o.eeiie.'],
  dot: ['.ii.', 'iwii', 'iiii', '.ii.'],
  sleepy: ['.oooooo.', 'ooeiiwo.', '..eiie..']
}
const AV_BROW = {
  soft: ['..YYYYY.', '.Y.....Y'],
  straight: ['YYYYYYYY', '.YYYYYYY'],
  arched: ['...YYYY.', '.YY....Y', 'Y.......']
}
const AV_MOUTH = {
  smile: ['o.........o', '.oo.....oo.', '...ooooo...'],
  grin: ['oooooooooo', 'oeeeeeeeeo', '.oeeeeeeo.', '..oooooo..'],
  laugh: ['oooooooooooo', 'oeeeeeeeeeeo', 'ommmmmmmmmmo', '.ommmppppmmo.', '..ommppmmo..', '...oooooo...'],
  flat: ['oooooooo'],
  smirk: ['.........oo', 'o......oo..', '.oooooo....']
}

function avFace(g, a) {
  const mirror = (rows, cxL, y) => {
    const w = rows[0].length
    const x = Math.round(cxL - (w - 1) / 2)
    pxMap(g, rows, x, y)
    pxMap(g, rows, PX - x - w, y, true)
  }
  const eye = AV_EYE[a.ey] || AV_EYE.open
  mirror(eye, AV.ex, AV.eye - 1)
  const brow = AV_BROW[a.br] || AV_BROW.soft
  mirror(brow, AV.ex, AV.brow - (brow.length - 2))
  // nose: a shadow down the far side, a lit tip, nostrils
  pxMap(g, ['..K', '..K', '..K', '.jK', 'K.K'], 30, AV.nose)
  const mouth = AV_MOUTH[a.mo] || AV_MOUTH.smile
  pxMap(g, mouth, Math.round(PX_MID - (mouth[0].length - 1) / 2), AV.mouth)
  // a lower lip under closed mouths, and the shadow under it
  if (a.mo === 'smile' || a.mo === 'flat' || a.mo === 'smirk') pxMap(g, ['lllll'], 30, AV.mouth + mouth.length)
  pxMap(g, ['KKK'], 31, AV.mouth + mouth.length + 1)
}

function avFacial(g, a, head, chin) {
  if (a.fh === 'none') return
  const d = pxDepth(head)
  const deep = a.fh === 'full' ? 9 : 3
  const jaw = (x, y) => y >= AV.nose + 3 && (d[y * PX + x] <= deep || y >= chin - deep)
  const side = (x, y) => y >= AV.eye && d[y * PX + x] <= 2
  const lip = (x, y) => y >= AV.mouth - 2 && y <= AV.mouth - 1 && Math.abs(x - PX_MID) <= 6.5
  const open = a.mo === 'grin' || a.mo === 'laugh'
  const hole = (x, y) => y >= AV.mouth && y <= AV.mouth + (open ? 5 : 2) && Math.abs(x - PX_MID) <= (open ? 6 : 4.5)
  const m = pxMask((x, y) => {
    if (!head[y * PX + x]) return false
    if (a.fh === 'moustache') return lip(x, y) || (y === AV.mouth && Math.abs(x - PX_MID) >= 5 && Math.abs(x - PX_MID) <= 7)
    return (jaw(x, y) || lip(x, y) || side(x, y)) && !hole(x, y)
  })
  const keepInk = c => c === pxCode('e') || c === pxCode('m') || c === pxCode('p') || c === pxCode('o')
  for (let i = 0; i < m.length; i++) {
    if (!m[i] || keepInk(g[i])) continue
    const x = i % PX, y = (i - x) / PX
    if (a.fh === 'stubble') { if ((x + y) % 2 === 0) g[i] = pxCode('K') }
    else g[i] = pxCode(d[i] <= 1 ? 'Y' : ((x * 5 + y * 3) % 7 === 0 ? 'y' : x > PX_MID + 5 ? 'H' : 'h'))
  }
}

// ---- body and tops ---------------------------------------------------------------------------------------
function avTorso(bd) {
  const W = bd === 'broad' ? 31.5 : 26
  return pxMask((x, y) => {
    if (y < AV.torso) return false
    const t = y >= 60 ? 1 : Math.sqrt(1 - ((60 - y) / 9) * ((60 - y) / 9))
    return Math.abs(x - PX_MID) <= 8 + (W - 8) * t
  })
}

function avTop(g, a, torso) {
  const d = avFill(g, torso, 't', 'V')
  avLight(g, torso, d, 'T', 'v', 3)
  avRim(g, torso, d, 'x', 40)
  const P = (test, slot, where) => pxPaint(g, pxMask(test), slot, where)
  const tp = a.tp
  const y0 = AV.torso
  if (tp === 'tee') {
    P(pxEllipse(PX_MID, y0, 9.4, 5.4), 'T', torso)
    P(pxEllipse(PX_MID, y0, 7.6, 4), 'k')
    P(pxEllipse(PX_MID, y0, 7.6, 4), 'K', pxMask((x, y) => y <= y0 + 1 || x > 34))
  } else if (tp === 'turtleneck') {
    const neck = pxRect(23, 44, 40, y0 + 2)
    P(neck, 't'); P((x, y) => neck(x, y) && (x === 23 || x === 40 || y === 44), 'V')
    P((x, y) => neck(x, y) && x > 23 && x < 40 && y > 44 && x % 2 === 0, 'T')
    P((x, y) => torso[y * PX + x] && x % 3 === 0 && y > y0 + 2, 'T', torso)
    P(pxRect(23, y0 + 1, 40, y0 + 2), 'T')
  } else if (tp === 'hoodie') {
    P(pxRing(PX_MID, y0 + 1, 16, 6.6, 3.4), 'v', torso)
    P(pxRing(PX_MID, y0 + 1, 16, 6.6, 1), 'V', torso)
    P(pxEllipse(PX_MID, y0 + 1, 12.6, 3.4), 'T', torso)
    P(pxAny(pxRect(27, y0 + 5, 27, 62), pxRect(36, y0 + 5, 36, 62)), 'x', torso)
  } else if (tp === 'jacket') {
    P(pxTri(PX_MID, 66, 23, y0 - 1, 40, y0 - 1), 'o', torso)
    P(pxTri(PX_MID, 64, 25, y0, 38, y0), 'N', torso)
    P(pxAny(pxTri(22, y0 - 2, 30, 61, 15, y0 + 6), pxTri(41, y0 - 2, 33, 61, 48, y0 + 6)), 'v', torso)
    P(pxAny(pxLine(22.5, y0 - 1, 30, 61, 1), pxLine(40.5, y0 - 1, 33, 61, 1)), 'V', torso)
  } else if (tp === 'coat' || tp === 'scarf') {
    // a turned-up collar behind the neck, wide lapels, a dark layer underneath
    P(pxTri(PX_MID, 68, 22, y0 - 1, 41, y0 - 1), 'o', torso)
    P(pxTri(PX_MID, 66, 24, y0, 39, y0), 'i', torso)
    P(pxAny(pxTri(21, y0 - 3, 31, 66, 12, y0 + 7), pxTri(42, y0 - 3, 32, 66, 51, y0 + 7)), 'v', torso)
    P(pxAny(pxLine(21.5, y0 - 2, 30.5, 64, 1), pxLine(41.5, y0 - 2, 32.5, 64, 1)), 'V', torso)
    P(pxAny(pxRect(19, y0 - 7, 22, y0), pxRect(41, y0 - 7, 44, y0)), 'v')
    P(pxAny(pxRect(18, y0 - 7, 18, y0), pxRect(45, y0 - 7, 45, y0), pxRect(18, y0 - 8, 22, y0 - 8), pxRect(41, y0 - 8, 45, y0 - 8)), 'V')
    if (tp === 'scarf') {
      // a chunky knit scarf, wrapped round the neck and hanging down the left
      const sm = pxMask(pxAny(pxEllipse(PX_MID, y0 - 1, 15, 6), pxRect(20, y0, 29, 63)))
      const sd = avFill(g, sm, 'n', 'R')
      avLight(g, sm, sd, 'N', 'r', 2)
      for (let i = 0; i < sm.length; i++) {
        const x = i % PX, y = (i - x) / PX
        if (sm[i] && sd[i] > 1 && (x + (y % 2)) % 3 === 0) g[i] = pxCode('N')
      }
      P(pxAny(pxRect(20, y0 + 5, 29, y0 + 5), pxRect(20, 61, 29, 61)), 'R')
    }
  }
}

// ---- accessories -------------------------------------------------------------------------------------------
function avGlasses(g, kind) {
  const ey = AV.eye, L = AV.ex, R = PX - 1 - AV.ex
  const frame = kind === 'round-glasses'
    ? pxAny(pxRing(L, ey, 6, 5.2, 1.3), pxRing(R, ey, 6, 5.2, 1.3))
    : pxAny((x, y) => pxRect(L - 6, ey - 4, L + 6, ey + 3)(x, y) && !pxRect(L - 5, ey - 3, L + 5, ey + 2)(x, y),
      (x, y) => pxRect(R - 6, ey - 4, R + 6, ey + 3)(x, y) && !pxRect(R - 5, ey - 3, R + 5, ey + 2)(x, y))
  pxPaint(g, pxMask(pxAny(frame, pxRect(L + 6, ey - 2, R - 6, ey - 2), pxRect(13, ey - 2, L - 6, ey - 2), pxRect(R + 6, ey - 2, 50, ey - 2))), 'G')
  pxPaint(g, pxMask(pxAny(pxLine(L - 3, ey + 1, L - 1, ey - 2, 1), pxLine(R - 3, ey + 1, R - 1, ey - 2, 1))), 'g')
}

function avEarrings(g) {
  for (const x of [14.5, 48.5]) pxPaint(g, pxMask(pxRing(x, 38, 2.4, 2.6, 1.1)), 'q')
  pxPaint(g, pxMask(pxAny(pxRect(13, 39, 13, 40), pxRect(50, 39, 50, 40))), 'Q')
}

const AV_BEANIE = (x, y) => y <= 22 && (pxEllipse(PX_MID, 22, 18, 17.6)(x, y) || pxRect(13.5, 16, 49.5, 22)(x, y))
function avBeanie(g) {
  const m = pxMask(AV_BEANIE)
  const d = avFill(g, m, 't', 'V')
  avLight(g, m, d, 'T', 'v', 3)
  avRim(g, m, d, 'x', 36)
  for (let i = 0; i < m.length; i++) {
    const x = i % PX, y = (i - x) / PX
    if (!m[i] || d[i] <= 1) continue
    if (y >= 16) g[i] = pxCode(y === 16 ? 'V' : x % 2 ? 'T' : 't')
    else if (x % 3 === 0 && g[i] !== pxCode('x')) g[i] = pxCode('T')
  }
}
const AV_SCARF_HEAD = (x, y) => (pxEllipse(PX_MID, 26, 19.6, 22)(x, y) && y < 50) || (y >= 42 && Math.abs(x - PX_MID) <= 20 - (y - 42) * 0.2)
const AV_SCARF_FACE = (x, y) => pxEllipse(PX_MID, 33, 13.6, 16.4)(x, y) && y > 19
function avHeadscarf(g) {
  const m = pxMask((x, y) => AV_SCARF_HEAD(x, y) && !AV_SCARF_FACE(x, y))
  const d = avFill(g, m, 'n', 'R')
  avLight(g, m, d, 'N', 'r', 3)
  avRim(g, m, d, 'Z', 38)
  for (let i = 0; i < m.length; i++) {
    const x = i % PX, y = (i - x) / PX
    if (m[i] && d[i] > 2 && (x * 2 - y + 64) % 11 === 0 && y > 22) g[i] = pxCode('N')
  }
}
function avHeadphones(g, top) {
  const band = pxMask((x, y) => y <= 28 && pxRing(PX_MID, 29, 19.4, 29 - top + 1, 2.6)(x, y))
  const cups = pxMask(pxAny(pxSquircle(12.5, 31, 3.8, 7), pxSquircle(50.5, 31, 3.8, 7)))
  pxPaint(g, pxEdge(pxOr(band, cups)), 'o')
  pxPaint(g, band, 'c')
  pxPaint(g, pxMask((x, y) => band[y * PX + x] && !pxAt(band, x, y - 1)), 'C')
  pxPaint(g, cups, 'c')
  pxPaint(g, pxMask(pxAny(pxRect(10, 27, 10, 35), pxRect(53, 27, 53, 35))), 'C')
  pxPaint(g, pxMask(pxAny(pxRect(13, 26, 15, 36), pxRect(48, 26, 50, 36))), 'G', cups)
}

// ---- the whole bust ----------------------------------------------------------------------------------------
const AV_CACHE = pxCache(160)
const AV_HAIR_GRIDS = pxCache(40)
function avHairPart(hs) { return AV_HAIR_GRIDS(hs, () => hs === 'buzz' ? avBuzz() : pxRle(AV_HAIR_ART[hs] || '')) }
// A buzz cut follows the skull exactly, so it is drawn from the cranium: a short stipple down to the hairline.
function avBuzz() {
  const g = pxGrid()
  const m = pxMask((x, y) => { const u = (x - PX_MID) / 13; return pxEllipse(PX_MID, AV.cy, AV.rx + 0.6, AV.ry + 0.6)(x, y) && y < 16 + 10 * u * u * u * u })
  const d = avFill(g, m, 'h', 'Y')
  for (let i = 0; i < m.length; i++) {
    const x = i % PX, y = (i - x) / PX
    if (m[i] && d[i] > 1) g[i] = pxCode((x + y) % 2 ? 'H' : x < 28 && y < 14 ? 'y' : 'h')
  }
  return g
}

function avGrid(a) {
  const g = pxGrid()
  const has = k => a.ac.includes(k)
  const hat = has('beanie') ? 'beanie' : has('headscarf') ? 'headscarf' : ''
  const head = avHead(a.fs)
  const chin = (AV_JAW[a.fs] || AV_JAW.oval).chin
  const hair = avHairPart(a.hs)
  // what a beanie leaves showing: hair below its brim
  const below = hat === 'beanie' ? pxMask((x, y) => !AV_BEANIE(x, y) && y > 20) : null
  // neck and shoulders
  const neck = pxMask(pxRect(AV.neck[0], AV.neck[2], AV.neck[1], 56))
  avFill(g, neck, 'k', 'u')
  pxPaint(g, pxMask((x, y) => neck[y * PX + x] && (y <= chin + 3 || x >= 35) && x > AV.neck[0] && x < AV.neck[1]), 'K')
  avTop(g, a, avTorso(a.bd))
  // the head and face
  avSkin(g, head, chin)
  avFace(g, a)
  avFacial(g, a, head, chin)
  if (has('earrings') && hat !== 'headscarf') avEarrings(g)
  // the front of the hair, and the shadow it casts on the forehead
  if (hat !== 'headscarf') {
    avStamp(g, hair, below)
    const hm = below ? pxAnd(hair, below) : hair
    avRim(g, hm, pxDepth(hm), 'z', 36)
    const shade = pxMask((x, y) => !hm[y * PX + x] && pxAt(hm, x, y - 1) && head[y * PX + x] &&
      (g[y * PX + x] === pxCode('k') || g[y * PX + x] === pxCode('j')))
    pxPaint(g, shade, 'K')
  }
  if (a.hs === 'bald' && !hat) pxPaint(g, pxMask(pxEllipse(25, 12, 3.4, 1.6)), 'j')
  if (hat === 'beanie') avBeanie(g)
  if (hat === 'headscarf') avHeadscarf(g)
  const glasses = AV_ACC_GROUPS[0].find(k => has(k))
  if (glasses) avGlasses(g, glasses)
  if (has('headphones')) {
    let top = PX
    for (let y = 0; y < PX && top === PX; y++) for (let x = 24; x < 40; x++) if (g[y * PX + x]) { top = y; break }
    avHeadphones(g, Math.max(2, top - 1))
  }
  return g
}

// The avatar as SVG layers: { paths, under, colours }. Cached by its settings.
function avArt(a) {
  const key = JSON.stringify(a)
  return AV_CACHE(key, () => {
    const g = avGrid(a)
    return { paths: pxPaths(g), under: pxPaths(pxUsed(g).map(v => v ? pxCode('o') : 0)), colours: avColours(a) }
  })
}

// ---- the interface -----------------------------------------------------------------------------
const AV_ART = { grid: PX, views: { small: '7 4 50 50', face: '14 16 36 36' } }
const AV_SWATCH = { sk: k => AV_SKIN_TONES[k], hc: k => AV_HAIR_TONES[k], tc: k => AV_TOP_TONES[k] }
function avSwatch(key, id) {
  const ramp = AV_SWATCH[key] && AV_SWATCH[key](id)
  return ramp ? ramp[1] : '#808080'
}

// A person's avatar, still, on a night backdrop. `view` crops it (the builder's close-ups of the face).
function PersonAvatar(props) {
  const size = props.size || 28
  const a = cleanAvatar(props.avatar) || AV_DEFAULT
  const art = avArt(a)
  const n = AV_ART.grid
  return jsx('span', { className: cx('h-pav', props.className), 'aria-hidden': props.label ? undefined : true, role: props.label ? 'img' : undefined,
    'aria-label': props.label, style: { width: size, height: size },
    // small marks come in closer on the head, so the face still reads at 24 px
    children: jsxs('svg', { viewBox: props.view || (size < 48 ? AV_ART.views.small : '0 0 ' + n + ' ' + n), width: size, height: size,
      shapeRendering: !props.view && size >= 48 && pxCrisp(size, n) ? 'crispEdges' : 'auto', children: [
      jsx('rect', { width: n, height: n, fill: AV_INK.B }),
      jsx('rect', { width: n, height: n * 0.375, fill: AV_INK.b }),
      jsx('g', { children: pxPathEls(art.under, { o: art.colours.u }, 'u') }),
      jsx('g', { children: pxPathEls(art.paths, art.colours, 'p') })
    ] }) })
}
