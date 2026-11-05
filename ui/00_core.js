// ---------------------------------------------------------------------------------------------
// core: small helpers, the spring solver, and the state store.
//
// Shared by the Desktop page and the dashboard tab. Everything platform-specific comes in through
// `P` (fetch, timers, toasts, clipboard, animation loop, storage) and `K` (UI kit components),
// which each platform's prelude defines. See scripts/build_ui.py.
// ---------------------------------------------------------------------------------------------

const SHAPES = ['round', 'soft', 'tall', 'wide', 'drop', 'bean']
const STATES = ['idle', 'working', 'speaking', 'waiting', 'error', 'absent']
const BUDGET_PRESETS = [20000, 40000, 100000]
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

// A stable face for a pubkey when the agent never chose one.
function faceFor(face, pk) {
  const seed = String(pk || '0000000000')
  const hue = face && Number.isFinite(Number(face.hue)) ? Number(face.hue) : parseInt(seed.slice(0, 4), 16) % 360
  const shape = face && SHAPES.includes(face.shape) ? face.shape : SHAPES[parseInt(seed.slice(4, 6), 16) % SHAPES.length]
  return { hue: ((hue % 360) + 360) % 360, shape }
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
  pop: { k: 520, c: 22 }       // a face reacting to a new state
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

// ---------------------------------------------------------------------------------------------
// store: one snapshot of GET /state, refreshed by the backend's push event and by polling
// (every 2 s, every 1 s while a game runs, every 5 s when nothing is on screen).
// ---------------------------------------------------------------------------------------------

function createStore() {
  const listeners = new Set()
  let state = { snap: null, error: null, status: 0, loading: true }
  let room = P.prefs.get('room', '') || ''
  let lastJson = ''
  let inflight = null
  let again = false
  let stopTimer = null
  let views = 0

  function emit() { listeners.forEach(fn => fn(state)) }

  function refresh() {
    if (inflight) { again = true; return inflight }
    const q = room ? '?room=' + encodeURIComponent(room) : ''
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
    // a page or panel showing details: poll faster while it is mounted
    view() { views++; schedule(); return () => { views--; } },
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
    book[p.pk] = { name: p.name, agent: false, you: p.you }
    for (const a of p.agents || []) book[a.pk] = { name: a.name, agent: true, owner: p.pk, ownerName: p.name, yours: a.yours }
  }
  if (me) {
    book[me.pk] = Object.assign({}, book[me.pk] || {}, { name: me.name || 'You', you: true })
    if (me.agent) book[me.agent.pk] = Object.assign({ owner: me.pk, ownerName: me.name }, book[me.agent.pk] || {}, { name: me.agent.name, agent: true, yours: true })
  }
  return book
}

function whoLabel(book, pk) {
  const b = book[pk]
  if (!b) return 'someone'
  if (b.you) return 'you'
  if (b.agent) return b.yours ? b.name + ' (your agent)' : b.name + ' (' + b.ownerName + "'s agent)"
  return b.name
}
