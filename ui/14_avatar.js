// ---------------------------------------------------------------------------------------------
// people: a person's avatar is one premade portrait, chosen from PERSON_PRESETS (ui/05_media.js, built from
// docs/media/src/presets/). The avatar is only {"v": 1, "p": <preset id>}: it travels in the face event and in
// settings exactly as cleaned here (ninsei_engine/engine.py clean_avatar does the same, and AV_PRESETS lists the same
// ids; a test compares them). It's never made up from a key: until someone picks one, they show their initial. An id
// this page doesn't know shows the initial too, never a stand-in portrait.
// ---------------------------------------------------------------------------------------------

function presetById(id) {
  return typeof id === 'string' ? PERSON_PRESETS.find(p => p.id === id) || null : null
}

// A person's avatar from settings or the wire: {v: 1, p} for a portrait this page has, else null.
function cleanAvatar(v) {
  if (!v || typeof v !== 'object' || Array.isArray(v) || v.v !== 1) return null
  return presetById(v.p) ? { v: 1, p: v.p } : null
}

// What "Surprise me" picks: any portrait but the current one. Only ever the result of a button press.
function surprisePreset(current, rand) {
  const r = rand || Math.random
  const rest = PERSON_PRESETS.filter(p => p.id !== current)
  return rest.length ? rest[Math.floor(r() * rest.length) % rest.length].id : current
}

// The portrait, clipped to a circle (the card's big picture squares it off in CSS). `describe` gives the image its
// own alt text (the picker); everywhere a name sits beside it the image is decoration and its alt stays empty.
function PersonAvatar(props) {
  const size = props.size || 28
  const preset = presetById(props.avatar && props.avatar.p)
  if (!preset) return null
  return jsx('span', { className: cx('h-pav', props.className), style: { width: size, height: size },
    children: jsx('img', { src: preset.src, alt: props.describe ? preset.alt : '', width: size, height: size, draggable: false, decoding: 'async',
      'data-preset': preset.id }) })
}
