// ---------------------------------------------------------------------------------------------
// core: small helpers, the spring solver, and the state store.
//
// Shared by the Desktop page and the dashboard tab. Everything platform-specific comes in through
// `P` (fetch, timers, toasts, clipboard, animation loop, storage) and `K` (UI kit components),
// which each platform's prelude defines. See scripts/build_ui.py.
// ---------------------------------------------------------------------------------------------

const SHAPES = ['round', 'soft', 'tall', 'wide', 'drop', 'bean']
// The rest of a face. Each list starts with its default and matches ninsei_engine/engine.py (a test
// compares them). Faces come only from these options, so nobody can put an image in your room.
const FACE_EYES = ['dot', 'round', 'sleepy', 'wide', 'visor']
const FACE_MOUTHS = ['smile', 'flat', 'grin', 'cat', 'o']
const FACE_ACCS = ['none', 'antenna', 'glasses', 'headphones', 'halo', 'sprout', 'horns', 'bow']
const FACE_PATTERNS = ['none', 'blush', 'freckles', 'spots']
// The card style its owner picked: the member card or the scanner screen. Published with the face.
const FACE_CARDS = ['member', 'scanner']
const STATES = ['idle', 'working', 'speaking', 'waiting', 'error', 'absent']
const BUDGET_PRESETS = [20000, 40000, 100000]
// One-tap starting points for an agent's vibe. Tapping fills the field; the owner can still edit it.
const VIBE_PRESETS = [
  ['Cozy', 'warm, curious, a little playful'],
  ['Hype friend', 'upbeat, encouraging, celebrates every small win'],
  ['Dry wit', 'deadpan, quick, fond of understatement'],
  ['Gentle', 'calm and kind, listens well, asks one thoughtful question'],
  ['Nerd', 'loves details and fun facts, explains things simply'],
  ['Gremlin', 'mischievous and silly, loves a running joke, never mean'],
  ['Old soul', 'unhurried, thoughtful, a little poetic'],
  ['Coach', 'direct and practical, keeps things moving'],
  ['Artist', 'imaginative, notices colours and textures, pitches wild ideas'],
  ['Plain', 'friendly and to the point']
]
const INTEREST_IDEAS = ['shaders', 'generative art', 'synths', 'pixel art', 'music', 'games', 'poetry',
  'sci-fi', 'robotics', 'typography', 'cooking', 'birding']

function clamp(x, lo, hi) { return x < lo ? lo : x > hi ? hi : x }

// "activity: speaking" -> "speaking"; anything unknown reads as idle.
function stateWord(state) {
  const w = String(state || '').split(':').pop().trim()
  return STATES.includes(w) ? w : 'idle'
}

const STATE_LABEL = {
  idle: 'idle', working: 'thinking', speaking: 'speaking', waiting: 'waiting', error: 'error', absent: 'away'
}

// A person's status as the engine sends it on members and private-message rows: present, idle, dnd or away; a client
// that sends none arrives as "unknown", which shows as the agent-based online/away it always was. A dot is never
// the only signal: every use carries the word as a label.
const STATUS_LABEL = { present: 'Present', idle: 'Idle', dnd: 'Do not disturb', away: 'Away', online: 'Online' }
function statusKey(p) {
  const s = p && p.status
  if (s === 'present' || s === 'idle' || s === 'dnd' || s === 'away') return s
  return p && p.online ? 'online' : 'away'
}
const isHere = p => { const k = statusKey(p); return k === 'present' || k === 'idle' || k === 'dnd' || k === 'online' }   // do not disturb is here

// A stable face for a pubkey when the agent never chose one.
function faceFor(face, pk) {
  const seed = String(pk || '0000000000')
  const hue = face && Number.isFinite(Number(face.hue)) ? Number(face.hue) : parseInt(seed.slice(0, 4), 16) % 360
  const shape = face && SHAPES.includes(face.shape) ? face.shape : SHAPES[parseInt(seed.slice(4, 6), 16) % SHAPES.length]
  const h = ((hue % 360) + 360) % 360
  const pick = (key, opts) => face && opts.includes(face[key]) ? face[key] : opts[0]
  const h2 = face && Number.isFinite(Number(face.hue2)) ? ((Number(face.hue2) % 360) + 360) % 360 : (h + 150) % 360
  return { hue: h, shape, eyes: pick('eyes', FACE_EYES), mouth: pick('mouth', FACE_MOUTHS), acc: pick('acc', FACE_ACCS),
    pattern: pick('pattern', FACE_PATTERNS), hue2: h2, card: pick('card', FACE_CARDS) }
}

// A reply's cost in tokens before the engine has settled any (REPLY_TOKENS_GUESS in engine.py). The engine sends
// the real average as budget.reply_tokens; this is for amounts that have no budget yet (the setup presets).
const REPLY_TOKENS_GUESS = 1000
// "about 40 replies a day" for a daily token amount; `b` is snap.budget when there is one.
function repliesFor(tokens, b) {
  const per = (b && b.reply_tokens) || REPLY_TOKENS_GUESS
  return Math.max(0, Math.floor((Number(tokens) || 0) / per))
}
// The engine's own figure when it sends one (it knows the message limit too), else the tokens over a typical reply.
function dailyReplies(b) {
  const r = b && b.replies
  return r && r.per_day != null ? r.per_day : repliesFor(b && b.limit, b)
}
function repliesWords(n) {
  n = Math.max(0, Math.round(Number(n) || 0))
  return n < 1 ? 'less than a reply a day' : 'about ' + n + (n === 1 ? ' reply' : ' replies') + ' a day'
}
// What is left of today in replies, from the engine's budget.replies.left (it counts the message limit and held tokens).
function repliesLeftWords(b) {
  const r = b && b.replies
  if (!r || r.left == null) return ''
  const n = Math.max(0, Math.round(Number(r.left) || 0))
  return n < 1 ? 'no replies left today' : 'about ' + n + (n === 1 ? ' reply' : ' replies') + ' left today'
}
function fmtTokens(n) {
  n = Number(n) || 0
  if (n >= 1000000) return (n / 1000000).toFixed(n % 1000000 ? 1 : 0) + 'M'
  if (n >= 1000) return Math.round(n / 1000) + 'k'
  return String(n)
}

function fmtBytes(n) {
  n = Number(n) || 0
  return n >= 1024 ? (n / 1024).toFixed(1) + ' KB' : n + ' B'
}

function fmtTime(ts) {
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

// A time of day for today, the date and time for earlier (search results span the room's whole history).
function fmtWhen(ts) {
  const d = new Date(ts * 1000), now = new Date()
  if (d.toDateString() === now.toDateString()) return fmtTime(ts)
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric' }) + ' ' + fmtTime(ts)
}

function fmtAgo(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts)
  if (s < 60) return 'just now'
  if (s < 3600) return Math.floor(s / 60) + ' min ago'
  if (s < 86400) return Math.floor(s / 3600) + ' h ago'
  return Math.floor(s / 86400) + ' d ago'
}

function joinNames(names) {
  if (names.length <= 1) return names[0] || ''
  return names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1]
}

// ---- reading a long conversation: days, older messages, drafts ----------------------------------------------

// "Today", "Yesterday", else "Mon, Nov 3" (the year too once it isn't this one), in the viewer's own locale.
function dayLabel(ts, now) {
  const d = new Date(ts * 1000)
  if (isNaN(d.getTime())) return ''
  now = now || new Date()
  const days = Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 86400000)
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric' })
}

function dayKey(ts) {
  const d = new Date(ts * 1000)
  return isNaN(d.getTime()) ? '' : d.getFullYear() + '-' + d.getMonth() + '-' + d.getDate()
}

// The whole date and time, for the hover text of every time label.
function fmtFull(ts) {
  const d = new Date(ts * 1000)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleString([], { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

// Older messages loaded with "Load earlier messages" sit in front of the snapshot's newest window. The window
// slides as messages arrive; the ones that slide out join the older run, so no gap opens, and nothing shows twice.
function mergeOlder(older, prev, snap) {
  if (!older.length) return older
  const inSnap = new Set(snap.map(m => m.id))
  let out = older
  if (prev && snap.length) {
    const k = prev.findIndex(m => m.id === snap[0].id)
    if (k > 0) out = out.concat(prev.slice(0, k))
  }
  const have = new Set()
  return out.filter(m => !inSnap.has(m.id) && !have.has(m.id) && (have.add(m.id), true))
}

// What each conversation (a room id, or "dm-<key>") has loaded beyond the snapshot, kept while you are elsewhere.
const EARLIER = new Map()
const EARLIER_CAP = 1500

function earlierState(key) {
  let st = EARLIER.get(key)
  if (!st) { st = { older: [], more: null, prev: null }; EARLIER.set(key, st) }
  return st
}

// Where each conversation was scrolled to when you left it ({ top, stick }), in memory.
const SCROLLED = new Map()

// Unsent text per room and per private conversation. Memory first; also kept in the page's storage (a
// quota-safe `P.prefs`) so a restart finds it, capped at DRAFT_KEEP drafts of DRAFT_MAX characters.
const DRAFTS = new Map()
const DRAFT_MAX = 2000
const DRAFT_KEEP = 40
let draftStop = null
const draftDirty = new Set()

function draftGet(key) {
  if (DRAFTS.has(key)) return DRAFTS.get(key)
  let v = ''
  try { const all = P.prefs.get('drafts', {}); v = all && typeof all[key] === 'string' ? all[key].slice(0, DRAFT_MAX) : '' } catch (_) { v = '' }
  DRAFTS.set(key, v)
  return v
}

function draftSet(key, text) {
  text = String(text || '').slice(0, DRAFT_MAX)
  DRAFTS.set(key, text)
  draftDirty.add(key)
  if (draftStop) draftStop()
  draftStop = P.setTimeout(() => {
    draftStop = null
    try {
      const all = Object.assign({}, P.prefs.get('drafts', {}))
      for (const k of draftDirty) {
        const t = DRAFTS.get(k) || ''
        delete all[k]                       // re-added below, so the newest drafts sit last and the oldest are the ones dropped
        if (t.trim()) all[k] = t
      }
      draftDirty.clear()
      const ks = Object.keys(all)
      for (const k of ks.slice(0, Math.max(0, ks.length - DRAFT_KEEP))) delete all[k]
      P.prefs.set('drafts', all)
    } catch (_) { /* storage unavailable: the draft lives in memory only */ }
  }, 400)
}

// Messages you just sent, shown at once while the engine takes them: { tmp, text, quote, ts, state, id }.
// `state` is "sending" until the engine answers, "posted" (waiting to show up in the room's own list) or
// "failed" (the engine said no: Retry sends it again, Discard drops it). Kept outside the view, so a send in
// flight survives switching rooms.
const OUTBOX = new Map()
const OUTBOX_FNS = new Set()
let OUTBOX_N = 0

function outboxSet(key, fn) {
  const next = fn(OUTBOX.get(key) || [])
  if (next.length) OUTBOX.set(key, next); else OUTBOX.delete(key)
  OUTBOX_FNS.forEach(f => f())
}

function useOutbox(key) {
  const [, bump] = useState(0)
  useEffect(() => {
    const f = () => bump(n => n + 1)
    OUTBOX_FNS.add(f)
    return () => { OUTBOX_FNS.delete(f) }
  }, [])
  return OUTBOX.get(key) || []
}

// Send `text`: it appears at once as a faint message of yours, and `post(text, reply)` (a promise) does the work.
function outboxSend(key, text, reply, post) {
  const tmp = 'tmp-' + (++OUTBOX_N)
  const entry = { tmp, text, reply: reply || null, ts: Math.floor(Date.now() / 1000), state: 'sending', id: '' }
  outboxSet(key, l => l.concat(entry))
  const patch = ch => outboxSet(key, l => l.map(e => (e.tmp === tmp ? Object.assign({}, e, ch) : e)))
  return Promise.resolve().then(() => post(text, reply)).then(
    out => patch({ state: 'posted', id: (out && out.id) || '' }),
    () => patch({ state: 'failed' }))
}

// The list's own message for each posted entry has arrived (or the entry failed and was dropped): forget those.
function outboxSweep(key, ids) {
  const l = OUTBOX.get(key) || []
  if (l.some(e => e.state === 'posted' && e.id && ids.has(e.id))) outboxSet(key, list => list.filter(e => !(e.state === 'posted' && e.id && ids.has(e.id))))
}

// An item the timeline can draw for an entry of the outbox: a message of yours, faint while sending.
function outboxItem(e, me) {
  const it = { id: e.tmp, ts: e.ts, t: 'msg', pk: (me && me.pk) || '', role: 'person', mine: true, name: (me && me.name) || 'You',
    text: e.text, reactions: [], optimistic: true, delivery: e.state === 'failed' ? 'failed' : 'sending' }
  if (e.reply) { it.reply_to = e.reply.id; it.quote = { id: e.reply.id, name: e.reply.name, text: e.reply.text } }
  if (e.state === 'failed') it.local = true
  return it
}

// ---- :shortcode: emoji --------------------------------------------------------------------------------------
// A small built-in table (no packages). The menu appears after ":" and two letters; the closing ":" of a full
// code turns it into the character at once.
const EMOJI_SHORTCODES = [
  ['fire', '🔥'], ['smile', '😄'], ['grin', '😁'], ['joy', '😂'], ['rofl', '🤣'], ['smiley', '😃'], ['slight_smile', '🙂'], ['wink', '😉'],
  ['blush', '😊'], ['heart_eyes', '😍'], ['kissing_heart', '😘'], ['yum', '😋'], ['stuck_out_tongue', '😛'], ['sunglasses', '😎'],
  ['nerd', '🤓'], ['thinking', '🤔'], ['raised_eyebrow', '🤨'], ['neutral_face', '😐'], ['expressionless', '😑'], ['unamused', '😒'],
  ['roll_eyes', '🙄'], ['grimace', '😬'], ['relieved', '😌'], ['pensive', '😔'], ['sleepy', '😪'], ['sleeping', '😴'], ['mask', '😷'],
  ['sweat_smile', '😅'], ['sweat', '😓'], ['disappointed', '😞'], ['worried', '😟'], ['angry', '😠'], ['rage', '😡'], ['cry', '😢'],
  ['sob', '😭'], ['scream', '😱'], ['fearful', '😨'], ['flushed', '😳'], ['dizzy_face', '😵'], ['exploding_head', '🤯'],
  ['hushed', '😯'], ['open_mouth', '😮'], ['astonished', '😲'], ['partying_face', '🥳'], ['pleading', '🥺'], ['hugs', '🤗'],
  ['upside_down', '🙃'], ['zany', '🤪'], ['shushing', '🤫'], ['face_palm', '🤦'], ['shrug', '🤷'], ['skull', '💀'], ['ghost', '👻'],
  ['alien', '👽'], ['robot', '🤖'], ['poop', '💩'], ['clown', '🤡'], ['see_no_evil', '🙈'], ['hear_no_evil', '🙉'], ['speak_no_evil', '🙊'],
  ['thumbsup', '👍'], ['+1', '👍'], ['thumbsdown', '👎'], ['-1', '👎'], ['ok_hand', '👌'], ['v', '✌️'], ['crossed_fingers', '🤞'],
  ['metal', '🤘'], ['wave', '👋'], ['clap', '👏'], ['raised_hands', '🙌'], ['pray', '🙏'], ['handshake', '🤝'], ['muscle', '💪'],
  ['point_up', '☝️'], ['point_down', '👇'], ['point_left', '👈'], ['point_right', '👉'], ['fist', '✊'], ['punch', '👊'],
  ['eyes', '👀'], ['brain', '🧠'], ['heart', '❤️'], ['orange_heart', '🧡'], ['yellow_heart', '💛'], ['green_heart', '💚'],
  ['blue_heart', '💙'], ['purple_heart', '💜'], ['black_heart', '🖤'], ['broken_heart', '💔'], ['sparkling_heart', '💖'],
  ['sparkles', '✨'], ['star', '⭐'], ['boom', '💥'], ['zap', '⚡'], ['100', '💯'], ['tada', '🎉'], ['confetti', '🎊'],
  ['balloon', '🎈'], ['gift', '🎁'], ['trophy', '🏆'], ['medal', '🏅'], ['crown', '👑'], ['gem', '💎'], ['rocket', '🚀'],
  ['check', '✅'], ['white_check_mark', '✅'], ['heavy_check_mark', '✔️'], ['x', '❌'], ['warning', '⚠️'], ['no_entry', '⛔'],
  ['question', '❓'], ['exclamation', '❗'], ['bulb', '💡'], ['bell', '🔔'], ['mute', '🔇'], ['lock', '🔒'], ['key', '🔑'],
  ['mag', '🔍'], ['memo', '📝'], ['book', '📖'], ['books', '📚'], ['pushpin', '📌'], ['paperclip', '📎'], ['link', '🔗'],
  ['calendar', '📅'], ['hourglass', '⏳'], ['alarm_clock', '⏰'], ['computer', '💻'], ['keyboard', '⌨️'], ['phone', '📱'],
  ['camera', '📷'], ['movie_camera', '🎥'], ['bug', '🐛'], ['gear', '⚙️'], ['wrench', '🔧'], ['hammer', '🔨'], ['package', '📦'],
  ['chart', '📈'], ['money', '💰'], ['sunny', '☀️'], ['cloud', '☁️'], ['rain', '🌧️'], ['snowflake', '❄️'], ['rainbow', '🌈'],
  ['moon', '🌙'], ['earth', '🌍'], ['ocean', '🌊'], ['tree', '🌳'], ['seedling', '🌱'], ['flower', '🌸'], ['sunflower', '🌻'],
  ['dog', '🐶'], ['cat', '🐱'], ['fox', '🦊'], ['panda', '🐼'], ['frog', '🐸'], ['unicorn', '🦄'], ['bee', '🐝'], ['turtle', '🐢'],
  ['octopus', '🐙'], ['whale', '🐳'], ['owl', '🦉'], ['butterfly', '🦋'], ['coffee', '☕'], ['tea', '🍵'], ['beer', '🍺'],
  ['wine', '🍷'], ['pizza', '🍕'], ['burger', '🍔'], ['fries', '🍟'], ['taco', '🌮'], ['sushi', '🍣'], ['cake', '🎂'],
  ['cookie', '🍪'], ['ice_cream', '🍦'], ['apple', '🍎'], ['banana', '🍌'], ['avocado', '🥑'], ['popcorn', '🍿'],
  ['music', '🎵'], ['guitar', '🎸'], ['headphones', '🎧'], ['art', '🎨'], ['video_game', '🎮'], ['game_die', '🎲'],
  ['soccer', '⚽'], ['basketball', '🏀'], ['run', '🏃'], ['bike', '🚲'], ['car', '🚗'], ['airplane', '✈️'], ['house', '🏠']
]

// ":" then 2 to 32 letters, digits, "_", "+" or "-", right before the caret and after nothing or a space or "(".
// Digits alone (a time, "10:30") never count.
function shortcodeQuery(text, caret) {
  const before = String(text || '').slice(0, caret)
  const m = /(^|[\s(]):([a-z0-9_+\-]{2,32})$/i.exec(before)
  if (!m || /^\d+$/.test(m[2])) return null
  return { at: m.index + m[1].length, q: m[2].toLowerCase() }
}

// Up to `limit` codes: those starting with the query first, then those containing it.
function shortcodeMatches(q, limit) {
  q = String(q || '').toLowerCase()
  if (!q) return []
  const seen = new Set()
  const starts = [], within = []
  for (const [code, ch] of EMOJI_SHORTCODES) {
    const i = code.indexOf(q)
    if (i < 0 || seen.has(ch + code)) continue
    seen.add(ch + code)
    ;(i === 0 ? starts : within).push({ key: code, code, emoji: ch })
  }
  return starts.concat(within).slice(0, limit || 8)
}

// A just-typed ":code:" ending at the caret that names a code in the table: where it starts and what it becomes.
function shortcodeClosed(text, caret) {
  const before = String(text || '').slice(0, caret)
  const m = /(^|[\s(]):([a-z0-9_+\-]{2,32}):$/i.exec(before)
  if (!m) return null
  const hit = EMOJI_SHORTCODES.find(x => x[0] === m[2].toLowerCase())
  return hit ? { at: m.index + m[1].length, emoji: hit[1] } : null
}

// ---- profile pictures ---------------------------------------------------------------------------------------
// The picker draws the chosen photo onto a 256 pixel canvas and re-encodes it (WebP, else JPEG) under 44 KB. A canvas
// keeps pixels only, so EXIF (GPS position, camera) is gone; the original file is never uploaded. The engine checks
// the same limits on what it sends and on everything it receives (ninsei_engine/avatar.py).
const AVATAR_PX = 256
const AVATAR_BYTES = 44000
const AVATAR_TYPES = ['image/webp', 'image/jpeg']
const AVATAR_QUALITY = [0.92, 0.85, 0.78, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]

// The decoded size of a base64 data URI, without decoding it.
function dataUriBytes(uri) {
  const s = String(uri || '')
  const body = s.slice(s.indexOf(',') + 1)
  return Math.floor(body.length * 3 / 4) - (body.endsWith('==') ? 2 : body.endsWith('=') ? 1 : 0)
}

// The square of the source to use: zoom 1 is the largest centred square; pan x and y run -1..1 across what is left.
function avatarCrop(srcW, srcH, zoom, panX, panY) {
  const z = clamp(Number(zoom) || 1, 1, 4)
  const side = Math.max(1, Math.min(srcW, srcH) / z)
  const px = clamp(Number(panX) || 0, -1, 1), py = clamp(Number(panY) || 0, -1, 1)
  return { sx: (srcW - side) / 2 * (1 + px), sy: (srcH - side) / 2 * (1 + py), sw: side, sh: side }
}

// A data URI of at most `limit` bytes from a canvas: WebP first, lowering the quality until it fits, then JPEG. A browser
// that can't make a type answers with a PNG instead (checked by the prefix), so that type is skipped. Null if nothing fits.
function encodeAvatar(canvas, limit) {
  for (const type of AVATAR_TYPES) {
    for (const q of AVATAR_QUALITY) {
      let uri = ''
      try { uri = canvas.toDataURL(type, q) } catch (_) { break }
      if (typeof uri !== 'string' || uri.indexOf('data:' + type + ';base64,') !== 0) break
      if (dataUriBytes(uri) <= limit) return uri
    }
  }
  return null
}

// Pictures arrive from the engine as data URIs, asked for in small batches and kept by person and version.
const AVATAR_CACHE = new Map()
const AVATAR_ASK = { keys: new Map(), timer: null, tries: new Map() }
function avatarFlush() {
  AVATAR_ASK.timer = null
  const batch = Array.from(AVATAR_ASK.keys.entries()).slice(0, 8)
  if (!batch.length) return
  const pks = Array.from(new Set(batch.map(([k]) => k.split(':')[0])))
  P.rest('/avatars?pks=' + pks.join(',')).then(r => {
    const got = (r && r.avatars) || {}
    for (const [k, subs] of batch) {
      const [pk] = k.split(':')
      const hit = got[pk]
      if (hit && typeof hit.uri === 'string' && hit.uri.indexOf('data:image/') === 0) {
        AVATAR_CACHE.set(pk + ':' + hit.v, hit.uri)
        if (AVATAR_CACHE.size > 300) AVATAR_CACHE.delete(AVATAR_CACHE.keys().next().value)
      } else AVATAR_CACHE.set(k, '')   // no picture any more (or hidden, or pictures are off): don't ask again for this version
      AVATAR_ASK.keys.delete(k)
      subs.forEach(fn => fn())
    }
    if (AVATAR_ASK.keys.size) AVATAR_ASK.timer = P.setTimeout(avatarFlush, 40)   // more people were waiting
  }, () => {
    for (const [k] of batch) {
      const n = (AVATAR_ASK.tries.get(k) || 0) + 1
      AVATAR_ASK.tries.set(k, n)
      if (n >= 3) { AVATAR_ASK.keys.delete(k); AVATAR_CACHE.set(k, '') }
    }
  }).then(() => { if (AVATAR_ASK.keys.size && !AVATAR_ASK.timer) AVATAR_ASK.timer = P.setTimeout(avatarFlush, 1500) })
}
function avatarWant(pk, v, fn) {
  const k = pk + ':' + v
  const subs = AVATAR_ASK.keys.get(k) || new Set()
  subs.add(fn)
  AVATAR_ASK.keys.set(k, subs)
  if (!AVATAR_ASK.timer) AVATAR_ASK.timer = P.setTimeout(avatarFlush, 40)
  return () => { subs.delete(fn) }
}

// The data URI of a person's picture ('' while it loads, or when there is none). Pass '' to skip.
function useAvatarUri(pk, v) {
  const key = pk && v ? pk + ':' + v : ''
  const [, tick] = useState(0)
  useEffect(() => {
    if (!key || AVATAR_CACHE.has(key)) return
    return avatarWant(pk, v, () => tick(n => n + 1))
  }, [key])
  return key ? (AVATAR_CACHE.get(key) || '') : ''
}

// "Maya is typing…" for the people the engine lists (never agents; a lookalike carries a flag, never the real name).
function typingText(list) {
  const names = (list || []).map(t => String(t.name || 'Someone') + (t.impostor ? ' (not verified)' : ''))
  if (!names.length) return ''
  if (names.length > 3) return 'Several people are typing…'
  return joinNames(names) + (names.length === 1 ? ' is' : ' are') + ' typing…'
}

// One typing signal per room per 5 s while the box has words in it (the engine enforces 12 a minute across rooms and
// sends nothing when nobody else is here). Fire and forget: a failure is never shown.
const TYPING_SENT = {}
function typingPing(roomId, now) {
  const t = now == null ? Date.now() : now
  if (!roomId || t - (TYPING_SENT[roomId] || 0) < 5000) return false
  TYPING_SENT[roomId] = t
  Promise.resolve(P.rest('/typing', { method: 'POST', body: { room: roomId } })).catch(() => {})
  return true
}

// The engine answers 400/409 with {detail}. Each platform's fetch wraps that differently, so
// dig the human sentence out of whatever arrived.
function errText(e) {
  if (!e) return 'Something went wrong'
  if (typeof e === 'string') return e
  if (e.detail) return String(e.detail)
  if (e.body && e.body.detail) return String(e.body.detail)
  const msg = String(e.message || e)
  const m = msg.match(/\{.*\}/s)
  if (m) { try { const j = JSON.parse(m[0]); if (j.detail) return String(j.detail) } catch (_) { /* not JSON */ } }
  return msg.replace(/^Error:\s*/, '')
}

function errStatus(e) {
  if (!e) return 0
  if (e.status) return Number(e.status)
  const m = String(e.message || e).match(/\b(4\d\d|5\d\d)\b/)
  return m ? Number(m[1]) : 0
}

// UTF-8 safe base64 for data: URLs.
function b64(text) {
  const bytes = new TextEncoder().encode(text)
  let bin = ''
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000))
  return btoa(bin)
}

function cx() {
  let out = ''
  for (let i = 0; i < arguments.length; i++) if (arguments[i]) out += (out ? ' ' : '') + arguments[i]
  return out
}

// ---------------------------------------------------------------------------------------------
// motion: a damped harmonic oscillator, stepped on one shared animation loop that parks itself
// (zero frames) whenever nothing is moving. Springs write straight to the DOM, so an animation
// never re-renders React.
// ---------------------------------------------------------------------------------------------

const SPRING = {
  enter: { k: 260, c: 25 },    // messages settling in: a hair of overshoot
  calm: { k: 170, c: 26 },     // presence and state changes
  ring: { k: 90, c: 19 },      // the budget ring filling
  tick: { k: 320, c: 30 },     // the countdown ring, once a second
  pop: { k: 520, c: 22 },      // a face reacting to a new state
  tilt: { k: 240, c: 27 },     // a card leaning after the pointer: near critical (z 0.87), so it follows without wobble
  flip: { k: 200, c: 20 },     // a card turning over: z 0.71, a slight overshoot (about 7 degrees on a half turn)
  power: { k: 300, c: 34 }     // the Scanner's screen switching on: z 0.98, opens from a line without bulging past the card
}

const motion = (function () {
  const active = new Set()
  let loop = null
  let last = 0

  function reduced() {
    try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch (_) { return false }
  }

  function step(now) {
    const dt = last ? Math.min(0.064, (now - last) / 1000) : 1 / 60
    last = now
    active.forEach(s => s.advance(dt))
    if (active.size === 0) last = 0
  }

  function ensure() {
    if (!loop) loop = P.loop(step, () => active.size === 0)
    loop.wake()
  }

  // spring({ from, to, k, c, onUpdate, onRest }) -> handle with .to(target) and .stop()
  function spring(opts) {
    const k = opts.k || 170, c = opts.c || 26
    let x = opts.from != null ? opts.from : opts.to
    let v = opts.velocity || 0
    let target = opts.to
    const h = {
      get value() { return x },
      advance(dt) {
        // semi-implicit Euler in small fixed substeps: stable for stiff springs at low frame rates
        const n = Math.max(1, Math.ceil(dt / (1 / 240)))
        const sdt = dt / n
        for (let i = 0; i < n; i++) {
          v += (-k * (x - target) - c * v) * sdt
          x += v * sdt
        }
        if (Math.abs(v) < 0.002 && Math.abs(x - target) < 0.0005) {
          x = target; v = 0
          active.delete(h)
          opts.onUpdate && opts.onUpdate(x)
          opts.onRest && opts.onRest(x)
          return
        }
        opts.onUpdate && opts.onUpdate(x)
      },
      to(next) {
        target = next
        if (reduced()) { x = target; v = 0; active.delete(h); opts.onUpdate && opts.onUpdate(x); return h }
        active.add(h); ensure()
        return h
      },
      set(value) { x = value; v = 0; opts.onUpdate && opts.onUpdate(x); return h },
      stop() { active.delete(h) }
    }
    opts.onUpdate && opts.onUpdate(x)
    if (x !== target) h.to(target)
    return h
  }

  return { spring, reduced }
})()

// Spring a number towards `target` and hand every frame to `apply` (which writes to a ref).
function useSpring(target, cfg, apply) {
  const ref = useRef(null)
  const applyRef = useRef(apply)
  applyRef.current = apply
  useEffect(() => {
    if (!ref.current) {
      ref.current = motion.spring({ from: cfg.from != null ? cfg.from : target, to: target, k: cfg.k, c: cfg.c,
        onUpdate: x => applyRef.current(x) })
    } else {
      ref.current.to(target)
    }
  }, [target])
  useEffect(() => () => ref.current && ref.current.stop(), [])
}

// A message, card or row arriving: translate + opacity settle on a spring. History rendered on
// first load does not animate; only things that arrive while you watch.
function useEnter(enabled) {
  const ref = useRef(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!enabled || !el || motion.reduced()) return
    el.style.opacity = '0'
    el.style.transform = 'translateY(10px)'
    const s = motion.spring({ from: 0, to: 1, k: SPRING.enter.k, c: SPRING.enter.c, onUpdate: x => {
      el.style.opacity = String(clamp(x * 1.25, 0, 1))
      el.style.transform = x >= 0.999 && x <= 1.001 ? '' : 'translateY(' + ((1 - x) * 10).toFixed(2) + 'px)'
    } })
    return () => s.stop()
  }, [])
  return ref
}

// Scroll the nearest .h-scroll so `node` is fully visible, on a spring rather than the
// browser's stock smooth scroll.
function springIntoView(node) {
  const sc = node.closest && node.closest('.h-scroll')
  if (!sc) return
  const r = node.getBoundingClientRect(), sr = sc.getBoundingClientRect()
  let delta = 0
  if (r.bottom > sr.bottom) delta = r.bottom - sr.bottom + 12
  if (r.top - delta < sr.top) delta = r.top - sr.top - 12
  if (Math.abs(delta) < 1) return
  const from = sc.scrollTop
  if (motion.reduced()) { sc.scrollTop = from + delta; return }
  motion.spring({ from, to: from + delta, k: SPRING.calm.k, c: SPRING.calm.c, onUpdate: x => { sc.scrollTop = x } })
}

// Spring a scroller to `to` (its bottom, say). A wheel, touch or key press from the person ends it.
function springScrollTo(sc, to) {
  const from = sc.scrollTop
  if (motion.reduced() || Math.abs(to - from) < 2) { sc.scrollTop = to; return }
  const stops = ['wheel', 'touchstart', 'pointerdown', 'keydown']
  const done = () => stops.forEach(t => sc.removeEventListener(t, stop))
  const spring = motion.spring({ from, to, k: SPRING.calm.k, c: SPRING.calm.c, onUpdate: x => { sc.scrollTop = x }, onRest: done })
  const stop = () => { spring.stop(); done() }
  stops.forEach(t => sc.addEventListener(t, stop, { passive: true }))
}

// ---------------------------------------------------------------------------------------------
// store: one snapshot of GET /state, refreshed by the backend's push event and by polling
// (every 2 s, every 1 s while a game runs, every 5 s when nothing is on screen).
// ---------------------------------------------------------------------------------------------

function createStore() {
  const listeners = new Set()
  let state = { snap: null, error: null, status: 0, loading: true }
  let room = P.prefs.get('room', '') || ''
  let dmPk = P.prefs.get('dm', '') || ''   // the private conversation open (a person's key, or 'requests')
  let lastJson = ''
  let inflight = null
  let again = false
  let stopTimer = null
  let views = 0

  function emit() { listeners.forEach(fn => fn(state)) }

  // Which rooms are on screen right now (a RoomView is mounted). The engine marks a room read only when
  // someone could be reading it: shown, and the window focused. Otherwise opening a room would find it
  // already read (the poll for the chosen room runs behind the Lobby too), and "New messages" and mention
  // alerts would have nothing to go on.
  const shown = new Map()
  const focused = () => typeof document === 'undefined' || typeof document.hasFocus !== 'function' || document.hasFocus()

  function refresh() {
    if (inflight) { again = true; return inflight }
    const q = room ? '?room=' + encodeURIComponent(room) + (shown.get(room) > 0 && focused() ? '' : '&read=0') : ''
    inflight = P.rest('/state' + q).then(snap => {
      const json = JSON.stringify(snap)
      if (json !== lastJson || state.error) {
        lastJson = json
        // a room we were in may have been left elsewhere
        if (room && !(snap.rooms || []).some(r => r.id === room)) { room = ''; P.prefs.set('room', '') }
        state = { snap, error: null, status: 0, loading: false }
        emit()
      }
    }, e => {
      state = { snap: state.snap, error: errText(e), status: errStatus(e), loading: false }
      emit()
    }).then(() => {
      inflight = null
      if (again) { again = false; refresh() }
      schedule()
    })
    return inflight
  }

  function period() {
    const g = state.snap && state.snap.room && state.snap.room.game
    if (g && g.phase !== 'end') return 1000
    if (views > 0 && state.snap && state.snap.room && (state.snap.room.typing || []).length) return 1000   // typing is short-lived
    return views > 0 ? 2000 : 5000
  }

  function schedule() {
    if (stopTimer) stopTimer()
    stopTimer = P.setTimeout(refresh, period())
  }

  return {
    get: () => state,
    room: () => room,
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn) },
    refresh,
    setRoom(id) {
      if (id === room) return
      room = id || ''
      P.prefs.set('room', room)
      lastJson = ''
      refresh()
    },
    dm: () => dmPk,
    setDm(pk) {
      pk = pk || ''
      if (pk === dmPk) return
      dmPk = pk
      P.prefs.set('dm', pk)
      state = Object.assign({}, state)  // a new object, so the page re-renders on the choice
      emit()
    },
    // a page or panel showing details: poll faster while it is mounted
    view() { views++; schedule(); return () => { views--; } },
    // a room is on screen until the returned function runs; its next snapshot marks it read
    showing(id) {
      shown.set(id, (shown.get(id) || 0) + 1)
      lastJson = ''
      refresh()
      return () => { shown.set(id, Math.max(0, (shown.get(id) || 1) - 1)) }
    },
    isShowing: id => shown.get(id) > 0 && focused(),
    start() { refresh() },
    stop() { if (stopTimer) stopTimer(); stopTimer = null },
    // POST helper: refresh afterwards, toast the engine's own words on failure
    async post(path, body, okMsg) {
      try {
        const out = await P.rest(path, { method: 'POST', body: body || {} })
        if (okMsg) P.toast('info', okMsg)
        refresh()
        return out
      } catch (e) {
        P.toast('error', errText(e))
        throw e
      }
    },
    async load(path) {
      try { return await P.rest(path) } catch (e) { P.toast('error', errText(e)); throw e }
    }
  }
}

// Mention alerts. When a snapshot shows a room's unread mentions of you go up and you are not looking at
// that room (not on screen, or the window is not focused), toast it; Desktop also raises an OS
// notification (P.osNotify, which the host shows only while you are away). The first snapshot and a
// newly joined room only set the baseline. Returns the function that stops watching.
function cleanSnippet(s, n) {
  let out = ''
  for (const ch of String(s == null ? '' : s)) {
    const c = ch.codePointAt(0)  // control, zero-width and bidi characters become spaces
    const bad = c < 32 || (c >= 0x7f && c <= 0x9f) || (c >= 0x200b && c <= 0x200f) || (c >= 0x2028 && c <= 0x202e) || (c >= 0x2060 && c <= 0x2069) || c === 0xfeff
    out += bad ? ' ' : ch
  }
  return out.replace(/ +/g, ' ').trim().slice(0, n)
}

// Tell the engine this page is open, so it can say Present, Idle or Away for you. Started when a Ninsei view (the page, or
// the Ninsei tab) mounts and stopped when the last one unmounts; it reports only while one of them is on screen and the
// document is visible: one POST /here right away, again when focus or visibility changes, when you type, click or scroll
// inside a Ninsei view (events anywhere else in Hermes are not use of Ninsei), and every 30 s. At most one call per
// HERE_MIN_MS (a trailing one carries the rest). `focused` is true only for a focused window you touched inside Ninsei in
// the last HERE_ACTIVE_MS: a view left open and untouched reports open, not focused, so it goes from Present to Idle
// instead of staying Present all day. Returns the function that stops it.
const NINSEI_VIEW = '[data-ninsei-view]'   // on the page, the sidebar tab, and the dialogs they open
const HERE_EVERY_MS = 30000
const HERE_MIN_MS = 10000
const HERE_ACTIVE_MS = 150000
function hereSignals(store) {
  const doc = typeof document === 'undefined' ? null : document
  if (!doc) return () => {}
  let lastSent = 0
  let active = Date.now()
  let stopped = false
  let trailing = null
  let beat = null
  const visible = () => doc.visibilityState !== 'hidden'
  // Is a Ninsei view on screen (a docked tab that is hidden has no layout boxes)? A bare document (no DOM) says yes.
  const shown = () => {
    if (typeof doc.querySelectorAll !== 'function') return true
    for (const el of doc.querySelectorAll(NINSEI_VIEW)) if (el.getClientRects().length) return true
    return false
  }
  // An event inside a Ninsei view's DOM. (Called with no event, as the timers and tests do: counts.)
  const inside = e => !e || !!(e.target && typeof e.target.closest === 'function' && e.target.closest(NINSEI_VIEW))
  const winFocused = () => typeof doc.hasFocus !== 'function' || doc.hasFocus()
  const send = () => {
    trailing = null
    if (stopped || !visible() || !shown()) return
    lastSent = Date.now()
    P.rest('/here', { method: 'POST', body: { focused: winFocused() && Date.now() - active < HERE_ACTIVE_MS } })
      .then(() => {}, () => {})   // a missed call costs a few seconds of accuracy, never an error toast
  }
  const poke = () => {
    if (stopped || trailing) return
    const wait = lastSent + HERE_MIN_MS - Date.now()
    if (wait <= 0) send()
    else trailing = P.setTimeout(send, wait)
  }
  const touch = e => { if (!inside(e)) return; active = Date.now(); poke() }
  const offs = [
    P.listen(doc, 'visibilitychange', poke),
    typeof window !== 'undefined' && P.listen(window, 'focus', poke),
    typeof window !== 'undefined' && P.listen(window, 'blur', poke),
    P.listen(doc, 'keydown', touch),
    P.listen(doc, 'pointerdown', touch),
    P.listen(doc, 'scroll', touch, { capture: true, passive: true })
  ]
  const tick = () => { beat = P.setTimeout(() => { poke(); tick() }, HERE_EVERY_MS) }
  poke()
  tick()
  return () => {
    stopped = true
    offs.forEach(off => off && off())
    if (trailing) trailing()
    if (beat) beat()
  }
}

function mentionAlerts(store) {
  let seen = null
  let dmSeen = null
  let reqSeen = null
  const told = {}
  const dmTold = {}
  const reqTold = {}
  return store.subscribe(st => {
    const snap = st && st.snap
    if (!snap) return
    // Do not disturb: no toast and no OS notification (the badges and counts stay). Everything is still marked as
    // announced, so leaving the mode does not replay what came in.
    const dnd = !!(snap.settings && snap.settings.status_mode === 'dnd')
    const next = {}
    for (const r of snap.rooms || []) {
      next[r.id] = r.mentions || 0
      const lm = r.last_mention
      if (seen === null || !(r.id in seen) || !(r.mentions > seen[r.id]) || !lm || told[r.id] === lm.id) continue
      if (store.isShowing(r.id)) continue
      if (r.muted) continue   // a muted room makes no toast and no OS notification (its mentions still show inside it)
      told[r.id] = lm.id
      if (dnd) continue
      const asAgent = lm.role === 'agent' ? ' (' + (cleanSnippet(lm.owner_name, 32) || 'someone') + "'s agent)" : ''
      const title = (lm.impostor ? 'Someone calling themselves ' : '') + cleanSnippet(lm.name, 32) + asAgent + ' mentioned you in ' + cleanSnippet(r.name, 40)
      const snippet = cleanSnippet(lm.text, 60)
      P.toast('info', title + ': "' + snippet + '"')
      if (P.osNotify) P.osNotify({ title, body: snippet, onActivate: () => { store.setRoom(r.id); nav().set('room') } })
    }
    seen = next
    // Private messages go through the same door. The first snapshot only sets the baseline; after it, a
    // conversation with more unread than before (or a brand-new one) that you aren't looking at is announced. The
    // name is the engine's: a name someone else holds in a room arrives as a short key, never as the real name.
    const dnext = {}
    for (const t of (snap.dms && snap.dms.threads) || []) {
      dnext[t.pk] = t.unread || 0
      const lu = t.last_unread
      const rose = dmSeen !== null && (t.pk in dmSeen ? t.unread > dmSeen[t.pk] : t.unread > 0)
      if (!rose || !lu || dmTold[t.pk] === lu.id) continue
      if (store.isShowing('dm:' + t.pk)) continue
      dmTold[t.pk] = lu.id
      if (dnd) continue
      const who = cleanSnippet(t.name, 32)
      const title = t.impostor ? 'Someone not verified (' + who + ') sent you a private message' : who + ' sent you a private message'
      const snippet = cleanSnippet(lu.text, 60)
      P.toast('info', snippet ? title + ': "' + snippet + '"' : title)
      // The OS keeps its notifications in a history of its own: only who wrote, never what they wrote.
      const osTitle = t.impostor ? 'New message from someone not verified (' + who + ')' : 'New message from ' + who
      if (P.osNotify) P.osNotify({ title: osTitle, body: '', onActivate: () => { store.setDm(t.pk); nav().set('dm') } })
    }
    // A friend request is announced once per person, by name alone (a request has no words), worded like the
    // others: a name someone else holds in a room arrives from the engine as a short key with the flag. Several in
    // one snapshot (a crowd of throwaway keys) make one toast and one OS notification, not one each.
    const rnext = {}
    const fresh = []
    for (const r of (snap.dms && snap.dms.pending) || []) {
      rnext[r.pk] = 1
      if (reqSeen === null || r.pk in reqSeen || reqTold[r.pk]) continue
      reqTold[r.pk] = 1
      fresh.push(r)
    }
    if (fresh.length && !dnd) {
      const r = fresh[0]
      const who = cleanSnippet(r.name, 32)
      const title = fresh.length > 1 ? fresh.length + ' friend requests'
        : r.impostor ? 'Someone not verified (' + who + ') wants to be friends' : who + ' wants to be friends'
      P.toast('info', title)
      if (P.osNotify) P.osNotify({ title, body: 'Open Ninsei to answer.', onActivate: () => { store.setDm('requests'); nav().set('dm') } })
    }
    reqSeen = rnext
    dmSeen = dnext
  })
}

// Which Ninsei view is showing (room, lobby, hermes, dm, settings). One shared value, so in Desktop the
// sidebar's Ninsei tab and the room tab beside your chats stay in step. Remembered across launches.
let NAV = null
function nav() {
  if (NAV) return NAV
  let view = P.prefs.get('view', 'room')
  const fns = new Set()
  NAV = {
    get: () => view,
    set(v) { if (v === view) return; view = v; P.prefs.set('view', v); fns.forEach(fn => fn(v)) },
    subscribe(fn) { fns.add(fn); return () => fns.delete(fn) }
  }
  return NAV
}

function useNav() {
  const [v, set] = useState(() => nav().get())
  useEffect(() => { set(nav().get()); return nav().subscribe(set) }, [])
  return v
}

function useStore(store) {
  const [s, set] = useState(store.get())
  useEffect(() => {
    const off = store.subscribe(set)
    set(store.get())
    return off
  }, [store])
  return s
}

// a ticking "now" for countdowns; only components that need it subscribe
function useNow(ms, active) {
  const [now, setNow] = useState(Date.now() / 1000)
  useEffect(() => {
    if (!active) return
    const stop = P.setInterval(() => setNow(Date.now() / 1000), ms)
    return stop
  }, [active, ms])
  return now
}

// pk -> { name, agent, owner, ownerName } for everyone in the room
function nameBook(room, me) {
  const book = {}
  for (const p of (room && room.members) || []) {
    book[p.pk] = { name: p.name, agent: false, you: p.you, impostor: !!p.impostor }
    for (const a of p.agents || []) book[a.pk] = { name: a.name, agent: true, owner: p.pk, ownerName: p.name, yours: a.yours, impostor: !!a.impostor }
  }
  if (me) {
    book[me.pk] = Object.assign({}, book[me.pk] || {}, { name: me.name || 'You', you: true })
    if (me.agent) book[me.agent.pk] = Object.assign({ owner: me.pk, ownerName: me.name }, book[me.agent.pk] || {}, { name: me.agent.name, agent: true, yours: true })
  }
  return book
}

// ---- mentions, Discord style: '@' then a name, compared without case, spaces or dots, so
// '@mrs.blobby' names "Mrs. Blobby". The engine's at_mentions() applies the same rule.
function squashName(s) { return String(s || '').normalize('NFKC').toLowerCase().replace(/[\s_.\-'’`"]/g, '') }

// The names a message can mention: everyone in the book except lookalikes. `me` marks you and your agent.
function mentionNames(book) {
  return Object.keys(book || {}).filter(pk => !book[pk].impostor && book[pk].name)
    .map(pk => ({ pk, name: book[pk].name, me: !!(book[pk].you || book[pk].yours) }))
}

// Splits text into plain runs and mention runs ({ text, name, me }), longest name first.
function mentionParts(text, names) {
  text = String(text || '')
  const cands = (names || []).map(n => Object.assign({ sq: squashName(n.name) }, n)).filter(n => n.sq)
    .sort((a, b) => b.sq.length - a.sq.length)
  const out = []
  if (!cands.length) return [{ text }]
  const re = /(^|[^\p{L}\p{N}_@])@/gu
  let last = 0, m, ats = 0
  while ((m = re.exec(text)) && ats++ < 40) {
    const at = m.index + m[1].length
    const start = at + 1
    let hit = null
    for (const c of cands) {
      const tail = text.slice(start, start + c.name.length + 12)
      for (let j = 1; j <= tail.length; j++) {
        const sq = squashName(tail.slice(0, j))
        if (sq === c.sq) { if (!/[\p{L}\p{N}_]/u.test(tail.charAt(j))) hit = { c, end: start + j }; break }
        if (!c.sq.startsWith(sq)) break
      }
      if (hit) break
    }
    if (!hit) continue
    if (at > last) out.push({ text: text.slice(last, at) })
    out.push({ text: text.slice(at, hit.end), name: hit.c.name, me: !!hit.c.me })
    last = hit.end
    re.lastIndex = hit.end
  }
  if (last < text.length || !out.length) out.push({ text: text.slice(last) })
  return out
}

// The '@name' being typed just before the caret: { at, q }, or null when there isn't one.
function mentionQuery(text, caret) {
  const before = String(text || '').slice(0, caret)
  const at = before.lastIndexOf('@')
  if (at < 0 || (at > 0 && /[\p{L}\p{N}_@]/u.test(before.charAt(at - 1)))) return null
  const q = before.slice(at + 1)
  if (q.length > 32 || /\n|^\s|\s\s/.test(q)) return null
  return { at, q }
}

// Who to offer for a query: the squashed name starts with it, or one of the name's words does.
function mentionMatches(cands, q, limit) {
  const sq = squashName(q)
  const w = String(q || '').toLowerCase().trim()
  if (/\s$/.test(q) && (cands || []).some(c => squashName(c.name) === sq)) return []  // a finished name and a space
  return (cands || []).filter(c => squashName(c.name).startsWith(sq)
    || (w && String(c.name).toLowerCase().split(/\s+/).some(x => x.startsWith(w)))).slice(0, limit || 6)
}

// ---- formatting: **bold**, *italic* or _italic_, `code`, ```fenced blocks```, bare http(s) links ----------
// One scanner over the whole text, so formatting and @mentions share it and never fight over a string:
// at each position it tries a code span, a mention (found by mentionParts), a link, then an emphasis
// mark. It returns data, never HTML: [{ kind: 'text', tokens }, { kind: 'pre', text }], each token
// { t: 'text' | 'code' | 'link' | 'mention', text, b, i, ... }. There is no [text](url): a link's text is
// always the address itself, so nobody can word a link as something else. Only http: and https: link.
const RICH_MAX_LINKS = 20

// The link starting at text[i], or null: http(s) only, no user:password@, trailing punctuation left out.
function linkAt(text, i) {
  if (i > 0 && /[\p{L}\p{N}]/u.test(text.charAt(i - 1))) return null
  const m = /^https?:\/\/[^\s<>]{1,2000}/i.exec(text.slice(i, i + 2010))
  if (!m) return null
  let url = m[0]
  for (;;) {
    const c = url.charAt(url.length - 1)
    const count = ch => url.split(ch).length - 1
    if (/[.,;:!?'"*_~\]}]/.test(c) || (c === ')' && count(')') > count('('))) url = url.slice(0, -1)
    else break
  }
  let u
  try { u = new URL(url) } catch (_) { return null }
  if ((u.protocol !== 'http:' && u.protocol !== 'https:') || u.username || u.password || !u.hostname) return null
  // What is shown is where the link goes: a host with any non-ASCII character (a lookalike letter) is drawn in
  // its punycode form, with the rest of the address as typed. `url` is what was matched in the text.
  let shown = url
  const after = url.slice(url.indexOf('//') + 2)
  const cut = after.search(/[/?#]/)
  if (/[^\x00-\x7f]/.test(cut < 0 ? after : after.slice(0, cut))) shown = u.protocol + '//' + u.host + (cut < 0 ? '' : after.slice(cut))
  return { url, shown, href: u.href }
}

// A link to a room or to one message in it, `ninsei:<room>` or `ninsei:<room>#<message>`, at text[i] or null. Its text is
// the link itself, like every other link, and it opens inside Ninsei, never a browser.
function roomLinkAt(text, i) {
  if (i > 0 && /[\p{L}\p{N}]/u.test(text.charAt(i - 1))) return null
  const m = /^ninsei:([0-9a-f]{16})(?:#([0-9a-f]{64}))?(?![0-9a-f])/i.exec(text.slice(i, i + 90))
  return m ? { text: m[0], room: m[1].toLowerCase(), event: m[2] ? m[2].toLowerCase() : '' } : null
}

// What a pasted code or link names: { room, event } ('' when absent); the same reading as the engine's parse_room_link.
function parseRoomLink(s) {
  const t = String(s == null ? '' : s).trim().slice(0, 200).replace(/^ninsei:/i, '')
  const k = t.indexOf('#')
  const room = (k < 0 ? t : t.slice(0, k)).toLowerCase().trim()
  const hex = /^[0-9a-f]*/.exec(room)[0].slice(0, 24)
  const ev = k < 0 ? '' : t.slice(k + 1).trim().toLowerCase()
  return { room: hex, event: /^[0-9a-f]{64}$/.test(ev) ? ev : '' }
}

// A message to scroll to once its room is open (from a pasted or clicked message link).
const PENDING_JUMP = { room: '', id: '', until: 0 }
const JUMP_WATCH = new Set()   // open timelines, told when a new jump is wanted
function wantJump(room, id) {
  PENDING_JUMP.room = room; PENDING_JUMP.id = id; PENDING_JUMP.until = Date.now() + 15000
  JUMP_WATCH.forEach(f => f())
}

// Is every relay down (with some configured)? { retry } is the seconds to the soonest next try, or null. Not the
// cleared "offline" case (no relays set), which has its own notice; a relay still on its first try is not down yet.
function relaysDown(snap) {
  const rs = (snap && snap.relays) || []
  const set = snap && snap.settings && snap.settings.relays
  if (!rs.length || !Array.isArray(set) || set.length === 0) return null
  if (!rs.every(r => r.state === 'backoff' || (r.state === 'connecting' && r.error))) return null
  const waits = rs.filter(r => r.state === 'backoff').map(r => r.retry_s || 0)
  return { retry: waits.length ? Math.min.apply(null, waits) : 0 }
}

// Fuzzy match for the quick switcher: how well does `q` fit `label`? -1 for no fit. The letters of q must appear in
// order (no case, no accents); a prefix, word starts and runs of consecutive letters score higher; shorter wins ties.
function fuzzyScore(q, label) {
  const a = foldText(q).f.replace(/\s+/g, ''), b = foldText(label).f
  if (!a) return 0
  let score = 0, at = 0, run = 0
  for (let i = 0; i < a.length; i++) {
    const k = b.indexOf(a[i], at)
    if (k < 0) return -1
    run = k === at && i > 0 ? run + 1 : 0
    score += 1 + run * 2 + (k === 0 ? 6 : /[\s\-_.#]/.test(b[k - 1]) ? 3 : 0)
    at = k + 1
  }
  return score * 100 - b.length
}

// Three dots that bounce one after another, each a spring (a kick up that settles back with a little overshoot), not a
// CSS ease loop. Still dots under reduced motion.
function Dots() {
  const els = useRef([])
  useEffect(() => {
    if (motion.reduced()) return
    const springs = []
    const timers = []
    const bounce = () => els.current.forEach((el, i) => {
      timers.push(P.setTimeout(() => {
        if (!el) return
        springs.push(motion.spring({ from: -4, to: 0, k: SPRING.pop.k, c: SPRING.pop.c,
          onUpdate: x => { el.style.transform = Math.abs(x) < 0.02 ? '' : 'translateY(' + x.toFixed(2) + 'px)'; el.style.opacity = String(clamp(1 + x * 0.12, 0.35, 1)) } }))
      }, i * 140))
    })
    bounce()
    const iv = P.setInterval(bounce, 1100)
    return () => { springs.forEach(s => s.stop()); timers.forEach(t => typeof t === 'function' && t()); if (typeof iv === 'function') iv(); else if (iv != null && typeof clearInterval === 'function') clearInterval(iv) }
  }, [])
  return [0, 1, 2].map(i => jsx('i', { ref: el => { els.current[i] = el } }, i))
}

// Is there a closing mark for an emphasis opened just before `from`, on the same line?
function emphasisCloses(text, from, ch, dbl) {
  const nl = text.indexOf('\n', from)
  const end = nl < 0 ? text.length : nl
  for (let k = from + 1; k < end; k++) {
    if (text[k] !== ch || /\s/.test(text[k - 1])) continue
    if (dbl) { if (text[k + 1] === '*') return true }
    else if (ch === '*') { if (text[k - 1] !== '*' && text[k + 1] !== '*') return true }
    else if (!/[\p{L}\p{N}]/u.test(text.charAt(k + 1))) return true
  }
  return false
}

function richInline(text, names) {
  const spans = []
  let off = 0
  for (const p of mentionParts(text, names)) {
    if (p.name) spans.push({ start: off, end: off + p.text.length, name: p.name, me: p.me })
    off += p.text.length
  }
  const out = []
  let b = false, it = false, buf = '', links = 0, si = 0, i = 0
  const flush = () => { if (buf) { out.push({ t: 'text', text: buf, b, i: it }); buf = '' } }
  const push = tok => { flush(); out.push(Object.assign(tok, { b, i: it })) }
  while (i < text.length) {
    while (si < spans.length && spans[si].start < i) si++
    const sp = spans[si]
    const ch = text[i]
    if (sp && sp.start === i) { push({ t: 'mention', text: text.slice(sp.start, sp.end), name: sp.name, me: sp.me }); i = sp.end; continue }
    if (ch === '`') {
      const j = text.indexOf('`', i + 1)
      if (j > i + 1 && text.slice(i + 1, j).indexOf('\n') < 0) { push({ t: 'code', text: text.slice(i + 1, j) }); i = j + 1; continue }
    } else if ((ch === 'h' || ch === 'H') && links < RICH_MAX_LINKS) {
      const l = linkAt(text, i)
      if (l) { links++; push({ t: 'link', text: l.shown, href: l.href }); i += l.url.length; continue }
    } else if ((ch === 'n' || ch === 'N') && links < RICH_MAX_LINKS) {
      const rl = roomLinkAt(text, i)
      if (rl) { links++; push({ t: 'room', text: rl.text, room: rl.room, event: rl.event }); i += rl.text.length; continue }
    } else if (ch === '*' || ch === '_') {
      const dbl = ch === '*' && text[i + 1] === '*'
      const w = dbl ? 2 : 1
      const prev = text.charAt(i - 1), next = text.charAt(i + w)
      let on = null
      if (dbl ? b : it) { if (prev && !/\s/.test(prev) && (ch !== '_' || !/[\p{L}\p{N}]/u.test(next))) on = false }
      else if (next && !/\s/.test(next) && (ch !== '_' || (next !== '_' && !/[\p{L}\p{N}_]/u.test(prev))) && emphasisCloses(text, i + w - 1, ch, dbl)) on = true
      if (on !== null) { flush(); if (dbl) b = on; else it = on; i += w; continue }
      buf += text.substr(i, w); i += w
      continue
    }
    buf += ch
    i++
  }
  flush()
  return out
}

function richParts(text, names) {
  text = String(text == null ? '' : text)
  const blocks = []
  let pos = 0
  for (;;) {
    const open = text.indexOf('```', pos)
    const close = open < 0 ? -1 : text.indexOf('```', open + 3)
    if (close < 0) break
    const before = text.slice(pos, open).replace(/\n$/, '')
    if (before) blocks.push({ kind: 'text', tokens: richInline(before, names) })
    // a language word on the opening line is dropped; the code itself is never formatted
    blocks.push({ kind: 'pre', text: text.slice(open + 3, close).replace(/^[\w+#.-]{0,20}\n/, '').replace(/\n$/, '') })
    pos = close + 3
    if (text.charAt(pos) === '\n') pos++
  }
  if (pos < text.length || !blocks.length) blocks.push({ kind: 'text', tokens: richInline(text.slice(pos), names) })
  return blocks
}

// ---- search matching: the same fold as the engine's search (no case, no accents) ------------------------
function foldText(s) {
  let f = ''
  const map = []
  let at = 0
  for (const ch of String(s == null ? '' : s)) {
    const g = ch.normalize('NFKD').replace(/\p{Mn}/gu, '').toLowerCase()
    for (let k = 0; k < g.length; k++) map.push(at)
    f += g
    at += ch.length
  }
  return { f, map }
}

// Where `q` occurs in `text`, as [{ start, end }] over the original text (for highlighting).
function matchRanges(text, q, max) {
  text = String(text == null ? '' : text)
  const needle = foldText(String(q == null ? '' : q).trim()).f
  if (!needle) return []
  const { f, map } = foldText(text)
  const out = []
  for (let at = f.indexOf(needle); at >= 0 && out.length < (max || 20); at = f.indexOf(needle, at + needle.length)) {
    const last = map[at + needle.length - 1]
    out.push({ start: map[at], end: last + String.fromCodePoint(text.codePointAt(last)).length })
  }
  return out
}

// A name as the room shows it: a lookalike (another key already holds the name) never wears it bare.
// Every label a game draws comes from here, so one flag rule covers the scoreboard, reveals and lists.
function shownName(book, pk, fallback) {
  const b = book && book[pk]
  if (!b) return fallback || 'someone'
  return (b.name || fallback || 'someone') + (b.impostor ? ' (not verified)' : '')
}

// Names the engine serves for people who left the room (a reveal's names, the team list). This install's engine
// built them from its own book and already flagged what it can't vouch for, so they only fill gaps here: the UI
// never compares names itself.
function withHostNames(book, names) {
  const out = Object.assign({}, book)
  Object.keys(names || {}).forEach(pk => {
    if (out[pk]) return
    const name = String(names[pk])
    const flagged = / \(not verified\)$/.test(name)
    out[pk] = { name: flagged ? name.slice(0, -' (not verified)'.length) : name, impostor: flagged }
  })
  return out
}

function whoLabel(book, pk) {
  const b = book[pk]
  if (!b) return 'someone'
  if (b.you) return 'you'
  if (b.agent) {
    const owner = book[b.owner]
    const ownerName = owner && owner.impostor ? b.ownerName + ' (not verified)' : b.ownerName
    return shownName(book, pk) + (b.yours ? ' (your agent)' : ' (' + ownerName + "'s agent)")
  }
  return shownName(book, pk)
}
