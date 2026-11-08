// ---------------------------------------------------------------------------------------------
// people: the avatar a person builds from layers (skin, face shape, hair style and colour, eyes, brows,
// mouth, facial hair, build, top and its colour, things worn). This file is the data model only: the
// options, cleaning and Randomize. It travels in the face event and in settings exactly as cleaned here.
// How it is drawn lives in ui/15_person_art.js, which can be replaced without touching the model, the
// editor or the wire. Every option is open to everyone. It's never made up from a key: until someone
// builds one, they show their initial.
// ---------------------------------------------------------------------------------------------

// The options. Each list starts with its default and matches ninsei_engine/engine.py (a test compares them).
const AV_SKIN = 10   // tones 0 (lightest) to 9 (darkest)
const AV_FACES = ['oval', 'round', 'square', 'long']
const AV_HAIR = ['short', 'curly', 'long', 'buzz', 'bun', 'locs', 'bob', 'wavy', 'afro', 'ponytail', 'bald', 'swept']
const AV_HAIR_COLOURS = ['darkbrown', 'black', 'brown', 'auburn', 'ginger', 'blonde', 'platinum', 'grey', 'ice']
const AV_EYES = ['open', 'smile', 'almond', 'dot', 'sleepy']
const AV_BROWS = ['soft', 'straight', 'arched']
const AV_MOUTHS = ['smile', 'grin', 'laugh', 'flat', 'smirk']
const AV_FACIAL = ['none', 'stubble', 'moustache', 'short', 'full']
const AV_BUILDS = ['narrow', 'broad']
const AV_TOPS = ['coat', 'hoodie', 'turtleneck', 'jacket', 'tee', 'scarf']
const AV_TOP_COLOURS = ['navy', 'steel', 'slate', 'charcoal', 'glacier', 'teal']
const AV_ACCS = ['round-glasses', 'square-glasses', 'earrings', 'beanie', 'headphones', 'headscarf']
// Only one of each group can be worn; the first in the list wins.
const AV_ACC_GROUPS = [['round-glasses', 'square-glasses'], ['beanie', 'headscarf']]
const AV_DEFAULT = { v: 1, sk: 3, fs: 'oval', hs: 'short', hc: 'darkbrown', ey: 'open', br: 'soft', mo: 'smile', fh: 'none', bd: 'narrow', tp: 'coat', tc: 'navy', ac: [] }

// A person's avatar from settings or the wire, reduced to known options (same rules as clean_avatar in the
// engine). null when it isn't one: not an object, or a version this client doesn't know.
function cleanAvatar(v) {
  if (!v || typeof v !== 'object' || Array.isArray(v) || v.v !== 1) return null
  const pick = (key, opts) => opts.includes(v[key]) ? v[key] : AV_DEFAULT[key]
  const sk = Number.isInteger(v.sk) && v.sk >= 0 && v.sk < AV_SKIN ? v.sk : AV_DEFAULT.sk
  const want = Array.isArray(v.ac) ? v.ac.slice(0, 16) : []
  const ac = AV_ACCS.filter(a => want.includes(a)).filter((a, _, all) =>
    !AV_ACC_GROUPS.some(grp => grp.includes(a) && grp.find(x => all.includes(x)) !== a))
  return { v: 1, sk, fs: pick('fs', AV_FACES), hs: pick('hs', AV_HAIR), hc: pick('hc', AV_HAIR_COLOURS), ey: pick('ey', AV_EYES),
    br: pick('br', AV_BROWS), mo: pick('mo', AV_MOUTHS), fh: pick('fh', AV_FACIAL), bd: pick('bd', AV_BUILDS),
    tp: pick('tp', AV_TOPS), tc: pick('tc', AV_TOP_COLOURS), ac }
}

// A random avatar for the editor's Randomize button (never for a real person who didn't press it).
function randomAvatar(rand) {
  const r = rand || Math.random
  const pick = a => a[Math.floor(r() * a.length) % a.length]
  const ac = []
  if (r() < 0.3) ac.push(pick(['round-glasses', 'square-glasses']))
  if (r() < 0.25) ac.push('earrings')
  const head = r()
  if (head < 0.12) ac.push('beanie'); else if (head < 0.2) ac.push('headscarf'); else if (head < 0.28) ac.push('headphones')
  return cleanAvatar({ v: 1, sk: Math.floor(r() * AV_SKIN) % AV_SKIN, fs: pick(AV_FACES), hs: pick(AV_HAIR), hc: pick(AV_HAIR_COLOURS),
    ey: pick(AV_EYES), br: pick(AV_BROWS), mo: pick(AV_MOUTHS), fh: r() < 0.6 ? 'none' : pick(AV_FACIAL), bd: pick(AV_BUILDS),
    tp: pick(AV_TOPS), tc: pick(AV_TOP_COLOURS), ac })
}
