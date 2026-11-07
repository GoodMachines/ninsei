// ---------------------------------------------------------------------------------------------
// Chat cards (Desktop): `::ninsei-offer{id="…"}` and `::ninsei-tales{room="…"}` rendered inside a
// normal Hermes conversation. The model writes the attributes, so they are untrusted: each is
// checked for shape, then looked up in what the backend returns, and a miss is a small quiet chip.
// Text is only ever rendered as text. Buttons call the same backend routes as the Ninsei page.
// ---------------------------------------------------------------------------------------------

const OFFER_ID_RE = /^[0-9a-f]{64}$/
const ROOM_ID_RE = /^[0-9a-f]{8,64}$/

// A hidden turn that tells the agent what the owner just did. `window.hermes.send` is the SDK's
// documented, rate-limited way for a widget to talk back; where the host does not provide it to a
// plugin component (it is a preview-frame API), nothing is sent and the route call is the whole
// effect. Limits per the SDK: 500 characters, one per second. Never a visible fallback.
let lastTell = 0
function tellAgent(text) {
  const bridge = typeof window !== 'undefined' ? window.hermes : null
  if (!bridge || typeof bridge.send !== 'function') return Promise.resolve({ ok: false, error: 'unavailable' })
  const now = Date.now()
  if (now - lastTell < 1100) return Promise.resolve({ ok: false, error: 'throttled' })
  lastTell = now
  try { return Promise.resolve(bridge.send(String(text).slice(0, 500))).catch(() => ({ ok: false, error: 'undelivered' })) } catch (_) { return Promise.resolve({ ok: false, error: 'undelivered' }) }
}

// Poll `load` while mounted (and enabled); keeps the last good value across a failed poll.
function usePolled(load, key, ms, enabled) {
  const [s, setS] = useState({ ready: false, data: null, status: 0 })
  const loadRef = useRef(load)
  loadRef.current = load
  const [kick, setKick] = useState(0)
  useEffect(() => {
    if (!enabled) return
    let dead = false
    let busy = false
    const run = async () => {
      if (busy || dead) return
      busy = true
      try { const data = await loadRef.current(); if (!dead) setS({ ready: true, data, status: 0 }) }
      catch (e) { if (!dead) setS(prev => ({ ready: true, data: prev.data, status: errStatus(e) || 500 })) }
      busy = false
    }
    run()
    const stop = P.setInterval(() => { if (!document.hidden) run() }, ms)
    return () => { dead = true; if (stop) stop() }
  }, [key, enabled, kick])
  return [s, () => setKick(k => k + 1)]
}

// POST helper for a card: toast the engine's own words on failure, then re-poll.
function cardPost(refresh) {
  return {
    async post(path, body, okMsg) {
      try {
        const out = await P.rest(path, { method: 'POST', body: body || {} })
        if (okMsg) P.toast('info', okMsg)
        refresh()
        return out
      } catch (e) { P.toast('error', errText(e)); throw e }
    }
  }
}

function CardChip(props) {
  return jsxs('span', { className: 'hx h-chip h-cardchip', role: 'note', children: [jsx(K.Icon, { name: 'radio-tower', size: 12 }), props.children || 'Ninsei: not found'] })
}

// ---- offer ------------------------------------------------------------------------------------

// The offer's message lives in its room's transcript (title, pitch, owner); the local list only
// holds offers still waiting, building or ready. Fetching a room's state marks it read, so the
// room is only fetched when we have nothing cached or the offer changed state.
function useOffer(id, enabled) {
  const cache = useRef({ id: '', m: null, room: null })
  const load = async () => {
    const snap = await P.rest('/state')
    const rooms = snap.rooms || []
    const pend = (snap.offers || []).find(o => o.id === id)
    const c = cache.current.id === id ? cache.current : { id, m: null, room: null }
    const final = c.m && (c.m.state === 'shared' || c.m.state === 'declined')
    if (!c.m || (pend ? pend.status !== c.m.state : !final)) {
      const order = pend ? rooms.filter(r => r.id === pend.room) : rooms.slice(0, 8)
      c.m = null
      for (const r of order) {
        const s = await P.rest('/state?room=' + encodeURIComponent(r.id))
        const m = ((s.room && s.room.messages) || []).find(x => x.t === 'offer' && x.id === id)
        if (m) { c.m = m; c.room = { id: r.id, name: r.name }; break }
      }
    }
    cache.current = c
    if (!c.m) return null
    return { m: c.m, room: c.room, state: pend ? pend.status : c.m.state }
  }
  return usePolled(load, id, 2500, enabled)
}

function OfferDirective(props) {
  const id = String((props.attrs && props.attrs.id) || '').toLowerCase()
  const valid = OFFER_ID_RE.test(id)
  const [res, refresh] = useOffer(id, valid && !props.streaming)
  if (!valid) return jsx(CardChip, {})
  if (!res.ready) return jsx(CardChip, { children: 'Ninsei…' })
  if (res.status === 404) return jsx(CardChip, { children: 'Ninsei: not available' })
  if (!res.data) return jsx(CardChip, {})
  return jsx(OfferChatCard, { d: res.data, refresh })
}

function OfferChatCard(props) {
  const { m, room, state } = props.d
  const [busy, setBusy] = useState('')
  const [sure, setSure] = useState(false)
  const [review, setReview] = useState(false)
  const [prompt, setPrompt] = useState(null)
  const enter = useEnter(true)
  const cs = cardPost(props.refresh)
  const f = faceFor(m.face, m.pk)
  const owner = m.owner_name || 'its owner'

  const run = async (name, fn) => {
    if (busy) return
    setBusy(name)
    try { await fn() } catch (_) { /* toasted */ }
    setBusy('')
  }
  // Accept never hands anything over unseen: it opens the same review as the Ninsei page, with the
  // full task in an editable box. The hand-off (a fresh chat with the task in its composer) happens there.
  const decline = () => run('decline', async () => {
    await cs.post('/offers/answer', { offer: m.id, accept: false })
    tellAgent('Ninsei: I passed on offer ' + m.id.slice(0, 12) + '. No action needed.')
  })
  // Sharing goes through the same dialog as the Ninsei page: preview, size, secret scan and source.
  const shared = () => tellAgent('Ninsei: I shared the build for offer ' + m.id.slice(0, 12) + ' with the room.')

  let status = null
  let actions = null
  if (m.yours) {
    if (state === 'open') actions = [
      jsx(K.Button, { variant: 'primary', size: 'sm', disabled: !!busy, onClick: () => setReview(true), children: 'Review & build' }, 'a'),
      jsx(K.Button, { variant: 'ghost', size: 'sm', disabled: !!busy, onClick: decline, children: 'Not now' }, 'n')]
    else if (state === 'building') status = 'Your Hermes is building it. When the file is saved, you can share it here.'
    else if (state === 'ready') actions = [
      jsx(K.Button, { variant: 'primary', size: 'sm', onClick: () => setSure(true), children: 'Preview & share' }, 's')]
    else if (state === 'shared') status = 'Shared with #' + room.name + '.'
    else if (state === 'declined') status = 'You passed on this one.'
  } else {
    status = state === 'open' ? 'Waiting for ' + owner + ' to decide.'
      : state === 'building' || state === 'ready' ? owner + ' is building it.'
      : state === 'shared' ? owner + ' shared it.' : state === 'declined' ? owner + ' passed.' : null
  }

  return jsxs('div', { ref: enter, className: 'hx h-chatcard h-agent', style: { '--hue': f.hue }, 'data-state': state, children: [
    jsxs('div', { className: 'h-row', children: [
      jsx(Face, { face: m.face, pk: m.pk, state: state === 'open' && m.yours ? 'system: waiting' : state === 'building' ? 'activity: working' : 'activity: idle', size: 28, name: m.name }),
      jsxs('div', { className: 'h-grow', style: { minWidth: 0 }, children: [
        jsx('div', { className: 'h-kicker', children: 'Ninsei · ' + room.name + ' · ' + state }),
        jsx('h4', { children: m.title })
      ] })
    ] }),
    jsx('div', { className: 'h-text', children: m.pitch }),
    status && jsx('div', { className: 'h-faint h-small', children: status }),
    actions && jsx('div', { className: 'h-actions', children: actions }),
    review && jsx(ReviewDialog, { m, store: cs, onClose: () => { setReview(false); props.refresh() }, onPrompt: setPrompt }),
    sure && jsx(ShareDialog, { m, store: cs, room, onShared: shared, onClose: () => { setSure(false); props.refresh() } }),
    prompt && jsx(PromptDialog, { prompt, onClose: () => setPrompt(null) })
  ] })
}

// ---- Tall Tales -------------------------------------------------------------------------------

function TalesDirective(props) {
  const room = String((props.attrs && props.attrs.room) || '').toLowerCase()
  const valid = ROOM_ID_RE.test(room)
  const load = async () => {
    const snap = await P.rest('/state?room=' + encodeURIComponent(room))
    if (!(snap.rooms || []).some(r => r.id === room) || !snap.room || snap.room.id !== room) return null
    return { room: snap.room, me: snap.me }
  }
  // the same one-second rhythm as the Ninsei page while a game runs
  const [res, refresh] = usePolled(load, room, 1000, valid && !props.streaming)
  if (!valid) return jsx(CardChip, {})
  if (!res.ready) return jsx(CardChip, { children: 'Ninsei…' })
  if (res.status === 404) return jsx(CardChip, { children: 'Ninsei: not available' })
  if (!res.data) return jsx(CardChip, {})
  return jsx(TalesChatCard, { room: res.data.room, me: res.data.me, game: res.data.room.game, refresh })
}

function TalesChatCard(props) {
  const { room, me, game } = props
  const enter = useEnter(true)
  const store = cardPost(props.refresh)
  const book = nameBook(room, me)
  return jsx('div', { ref: enter, className: 'hx h-chatcard-wrap', children:
    game
      ? jsx(TallTales, { store, room, game, book, quiet: true }, game.gid)
      : jsxs('div', { className: 'h-chatcard', children: [
          jsx('div', { className: 'h-kicker', children: 'Ninsei · ' + room.name }),
          jsx('div', { className: 'h-muted', children: 'No Tall Tales game is running in this room.' })
        ] }) })
}
