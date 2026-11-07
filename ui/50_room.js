// ---------------------------------------------------------------------------------------------
// a room: header, timeline, offer and share cards, the drafts tray, the composer
// ---------------------------------------------------------------------------------------------

// Reactions: which agents pull a face right now, worked out from events every client already has, so
// nothing is published and nobody can send a fake reaction. Returns { agentPk: expr }.
const REACT_SECS = 6
const EXPR_RANK = { perk: 1, happy: 2, wary: 3, smug: 4, caught: 4 }
// `why`, when given, collects what caused each agent's expression (the pet's speech bubble uses it).
function reactionsFor(room, game, book, now, why) {
  const out = {}
  const put = (pk, expr, cause) => {
    if (!pk || (EXPR_RANK[expr] || 0) < (EXPR_RANK[out[pk]] || 0)) return
    out[pk] = expr
    if (why) why[pk] = Object.assign({ expr }, cause)
  }
  const agents = Object.keys(book).filter(pk => book[pk].agent)
  const agentOf = person => agents.find(pk => book[pk].owner === person)
  const offerAgent = {}
  for (const m of room.messages || []) {
    if (m.t === 'offer') offerAgent[m.id] = m.pk
    if (now - m.ts > REACT_SECS || m.ts - now > 30) continue
    if (m.t === 'msg') {
      if (m.impostor && m.impostor.agent) {  // someone wearing my owner's name: the agent narrows its eyes
        agents.filter(pk => book[pk].name === m.impostor.agent).forEach(pk => put(pk, 'wary', { key: m.id, claimed: m.impostor.claimed }))
        continue
      }
      for (const pk of agents) {  // named in a message: perks up
        if (pk === m.pk) continue
        const re = new RegExp('(^|[^\\p{L}\\p{N}])' + book[pk].name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '($|[^\\p{L}\\p{N}])', 'iu')
        if (book[pk].name.length > 1 && re.test(m.text || '')) put(pk, 'perk', { key: m.id, by: m.pk, unverified: !!m.impostor })
      }
    } else if (m.t === 'offer_state' && m.state === 'building') put(offerAgent[m.offer], 'happy')
    else if (m.t === 'share') put(agentOf(m.pk), 'happy')
  }
  const rv = game && game.phase === 'reveal' && game.reveal
  if (rv) {
    const authors = rv.authors || {}
    const picks = rv.picks || {}
    const team = pk => (book[pk] && book[pk].agent && book[pk].owner) || pk
    for (const oid of Object.keys(authors)) {
      for (const pk of String(authors[oid]).split(',').filter(Boolean)) {
        if (!book[pk] || !book[pk].agent) continue
        if (game.mode === 'agent') {
          const judges = (rv.voters || []).filter(v => team(v) !== team(pk))
          const cause = { key: game.gid + ':' + game.n, mode: game.mode, by: (picks[oid] || [])[0] }
          if ((picks[oid] || []).length) put(pk, 'caught', cause)        // spotted
          else if (judges.length) put(pk, 'smug', cause)                  // passed as a person
        } else if ((picks[oid] || []).length) put(pk, 'smug', { key: game.gid + ':' + game.n, mode: game.mode, by: picks[oid][0] })  // its fake fooled someone
      }
    }
    if (game.mode !== 'agent' && rv.truth) (picks[rv.truth] || []).forEach(p => put(agentOf(p), 'happy'))
  }
  return out
}

// One line for the Hermes pet's speech bubble when your own agent reacts. The pet's sprite is the core
// app's to animate; a plugin can only talk through its bubble. Null when there's nothing worth a line.
function petLine(cause, book, agentName, roomName) {
  if (!cause) return null
  // a second key using a name someone else holds is never named as them
  const name = pk => !book[pk] ? 'Someone' : book[pk].impostor ? 'Someone calling themselves ' + book[pk].name : book[pk].name
  const mine = pk => !!(book[pk] && (book[pk].you || book[pk].yours))
  const game = cause.mode === 'agent' ? 'Who\u2019s the Agent?' : 'Tall Tales'
  if (cause.expr === 'perk') return mine(cause.by) && !cause.unverified ? null
    : (cause.unverified ? 'Someone calling themselves ' + ((book[cause.by] && book[cause.by].name) || 'someone') : name(cause.by)) + ' mentioned ' + agentName + ' in ' + roomName + '.'
  if (cause.expr === 'wary') return 'Someone in ' + roomName + ' is posing as ' + (cause.claimed || 'you') + '. ' + agentName + ' is ignoring them.'
  if (cause.expr === 'caught') return name(cause.by) + ' spotted ' + agentName + ' in ' + game
  if (cause.expr === 'smug') return cause.mode === 'agent' ? agentName + ' passed as a person in ' + game
    : agentName + '\u2019s fake fooled ' + name(cause.by) + ' in ' + game
  return null
}

// Wraps the whole page (room view and people column), so every face of an agent reacts together.
function RoomReactions(props) {
  const { snap, room } = props
  const book = useMemo(() => room ? nameBook(room, snap.me) : {}, [room, snap.me])
  const game = room && room.game
  const msgs = (room && room.messages) || []
  const last = msgs.length ? msgs[msgs.length - 1].ts : 0
  const live = !!room && ((Date.now() / 1000 - last < REACT_SECS + 1) || !!(game && game.phase === 'reveal'))
  const now = useNow(500, live)  // ticks only while a reaction could be showing, so it can expire
  const exprs = useMemo(() => !room || motion.reduced() ? {} : reactionsFor(room, game, book, Math.max(now, Date.now() / 1000)),
    [room, game, book, now])
  return jsx(ExprContext.Provider, { value: exprs, children: props.children })
}

function RoomView(props) {
  const { store, snap, room } = props
  const book = useMemo(() => nameBook(room, snap.me), [room, snap.me])
  const drafts = (snap.drafts || []).filter(d => d.room === room.id)
  const game = room.game
  // The message being answered: set from a message's Reply button, cleared by the composer (Escape, its cancel
  // button, a sent reply) or by leaving the room. It is a small copy, so it survives the message scrolling away.
  const [replyTo, setReplyTo] = useState(null)
  useEffect(() => { setReplyTo(null) }, [room.id])
  const onReply = useCallback(m => setReplyTo({ id: m.id, name: m.name, text: String(m.text || '').slice(0, 120) }), [])
  const onCancelReply = useCallback(() => setReplyTo(null), [])
  // This room is on screen: the engine may mark it read from now on (and mention alerts stay quiet for it).
  useEffect(() => (store.showing ? store.showing(room.id) : undefined), [room.id])
  // Where you had read up to when you opened the room, kept until you leave it: the "New messages" line
  // goes before the first message from someone else newer than this. 0 (never opened) draws no line.
  const readMark = useRef({ id: '', ts: 0 })
  if (readMark.current.id !== room.id) {
    const r = (snap.rooms || []).find(x => x.id === room.id)
    readMark.current = { id: room.id, ts: (r && r.last_read) || 0 }
  }
  // search: the panel under the header, and the timeline's jump (set by Timeline) for a result that is loaded
  const [searching, setSearching] = useState(false)
  const jumpRef = useRef(null)
  useEffect(() => { setSearching(false) }, [room.id])
  const closeSearch = useCallback(() => {
    setSearching(false)
    const b = typeof document !== 'undefined' && document.querySelector && document.querySelector('.h-head [data-search-btn]')
    if (b && b.focus) b.focus()
  }, [])
  return jsxs(Fragment, { children: [
    jsx(RoomHeader, { store, room, snap, onPeople: props.onPeople, searching, onSearch: () => (searching ? closeSearch() : setSearching(true)) }),
    searching && jsx(SearchPanel, { room, onClose: closeSearch, onPick: id => !!(jumpRef.current && jumpRef.current(id, true)) }, room.id),
    jsx(Timeline, { store, snap, room, book, onReply, newAfter: readMark.current.ts, jumpRef }),
    jsxs('div', { className: 'h-composer', children: [
      // pinned above the input: model notice, the running game, drafts. Scrolls on its own if tall.
      jsxs('div', { className: 'h-pinned', children: [
        !snap.model && jsx('div', { style: { marginBottom: 8 }, children: jsx(Notice, { icon: 'warning', children:
          "Your agent can't reach a model from this Hermes process, so it will stay quiet. Check your Hermes model setup." }) }),
        game && jsx(TallTales, { store, room, game, book, key: game.gid }),
        drafts.length > 0 && jsx(DraftTray, { store, drafts })
      ] }),
      jsx(TypingLine, { list: room.typing }),
      jsx(Composer, { store, room, snap, gameOn: !!(game && game.phase !== 'end'), reply: replyTo, onCancelReply })
    ] })
  ] })
}

function RoomHeader(props) {
  const { store, room, snap } = props
  const [confirm, setConfirm] = useState(false)
  const mine = new Set((snap.settings && snap.settings.interests) || [])
  const online = (room.members || []).filter(p => p.online).length
  const copyCode = async () => {
    const ok = await P.copy('ninsei:' + room.id)
    P.toast(ok ? 'info' : 'error', ok ? 'Room code copied. Anyone with it can join; rooms are public.' : 'Could not reach the clipboard. The code is ninsei:' + room.id)
  }
  return jsxs('div', { className: 'h-head', children: [
    jsxs('div', { className: 'h-grow h-col', style: { gap: 3 }, children: [
      jsxs('div', { className: 'h-row', children: [
        jsx('h2', { className: 'h-trunc', children: room.name }),
        jsx('span', { className: 'h-faint h-small', children: online + ' here' })
      ] }),
      (room.about || (room.interests || []).length > 0) && jsxs('div', { className: 'h-row', style: { gap: 8, flexWrap: 'wrap' }, children: [
        room.about && jsx('span', { className: 'h-muted h-small h-trunc', children: room.about }),
        jsx(Chips, { items: room.interests, hits: (room.interests || []).filter(i => mine.has(i)) })
      ] })
    ] }),
    jsx(K.Tip, { label: 'Search this room', children: jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'Search this room', 'aria-pressed': !!props.searching,
      'aria-expanded': !!props.searching, 'data-search-btn': true, onClick: props.onSearch, children: jsx(K.Icon, { name: 'search', size: 14 }) }) }),
    jsx(K.Tip, { label: 'Copy the code people use to join', children: jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: copyCode,
      children: jsxs(Fragment, { children: [jsx(K.Icon, { name: 'link', size: 13 }), 'Share code'] }) }) }),
    props.onPeople && jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'People', onClick: props.onPeople, className: 'h-peoplebtn',
      children: jsx(K.Icon, { name: 'organization', size: 14 }) }),
    jsx(K.Tip, { label: 'Leave room', children: jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'Leave room', onClick: () => setConfirm(true),
      children: jsx(K.Icon, { name: 'sign-out', size: 14 }) }) }),
    jsx(Modal, { open: confirm, onClose: () => setConfirm(false), title: 'Leave ' + room.name + '?',
      description: 'You and your agent stop listening to this room. You can rejoin with its code.',
      footer: [
        jsx(K.Button, { variant: 'ghost', onClick: () => setConfirm(false), children: 'Stay' }, 'c'),
        jsx(K.Button, { variant: 'danger', onClick: () => { setConfirm(false); store.post('/rooms/leave', { room: room.id }); store.setRoom('') }, children: 'Leave' }, 'l')
      ] })
  ] })
}

// ---- timeline -------------------------------------------------------------------------------

function Timeline(props) {
  const { store, snap, room, book, onReply } = props
  const scroller = useRef(null)
  const stick = useRef(true)
  const seen = useRef(null)
  const msgs = room.messages || []
  // The id of the newest message when you scrolled up more than a screen (null while you are near the
  // bottom): the "Jump to latest" pill counts what came after it.
  const [away, setAway] = useState(null)
  const lastId = useRef('')
  lastId.current = msgs.length ? msgs[msgs.length - 1].id : ''

  // anything present on first render is history and does not animate in
  if (seen.current === null) seen.current = new Set(msgs.map(m => m.id))
  const fresh = id => {
    if (seen.current.has(id)) return false
    seen.current.add(id)
    return true
  }

  const onScroll = () => {
    const el = scroller.current
    if (!el) return
    const gap = el.scrollHeight - el.scrollTop - el.clientHeight
    stick.current = gap < 80
    const far = gap > Math.max(el.clientHeight, 200)
    setAway(prev => (far ? (prev === null ? lastId.current : prev) : null))
  }
  useLayoutEffect(() => {
    const el = scroller.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [msgs.length, msgs.length && msgs[msgs.length - 1].id])

  // Scroll to a message and flash it, when it is among the messages loaded. A quote's click says so when it
  // isn't; a search result (`quiet`) just reports false and shows the message in its own panel instead.
  const jump = useCallback((id, quiet) => {
    const el = scroller.current
    const node = el && [].find.call(el.querySelectorAll('[data-mid]'), n => n.getAttribute('data-mid') === id)
    if (!node) { if (!quiet) P.toast('info', 'That message is further back than what is loaded.'); return false }
    springIntoView(node)
    flash(node)
    return true
  }, [])
  if (props.jumpRef) props.jumpRef.current = jump
  const toLatest = () => { const el = scroller.current; if (el) springScrollTo(el, el.scrollHeight - el.clientHeight) }

  const k = away === null ? -1 : msgs.findIndex(m => m.id === away)
  const since = away === null ? 0 : (k < 0 ? msgs : msgs.slice(k + 1)).filter(m => m.t === 'msg' && !m.system && !m.deleted).length
  const items = groupItems(msgs, props.newAfter)
  return jsxs('div', { className: 'h-tlwrap', children: [
    jsx('div', { className: 'h-scroll', ref: scroller, onScroll, children: jsxs('div', { className: 'h-timeline', role: 'log', 'aria-live': 'polite', children: [
      items.length === 0 && jsx('div', { className: 'h-empty', children: 'Quiet in here. Say hello, or start a game of Tall Tales.' }),
      items.map(it => jsx(TimelineItem, { it, store, snap, room, book, onReply, onJump: jump, animate: fresh(it.key) }, it.key)),
      jsx(Thinking, { room })
    ] }) }),
    away !== null && jsx(JumpPill, { count: since, onClick: toLatest })
  ] })
}

// "Jump to latest": a pill over the foot of the timeline once you have scrolled up more than a screen, with
// the count of messages that came in meanwhile. It rises in on a spring; a click springs to the bottom.
function JumpPill(props) {
  const ref = useEnter(true)
  const n = props.count
  const label = n > 0 ? 'Jump to latest, ' + n + (n === 1 ? ' new message' : ' new messages') : 'Jump to latest'
  return jsx('div', { className: 'h-jump', children: jsxs('button', { type: 'button', className: 'h-jump-btn', ref, 'aria-label': label, onClick: props.onClick, children: [
    jsx(K.Icon, { name: 'arrow-down', size: 13 }),
    jsx('span', { children: n > 0 ? (n > 99 ? '99+' : n) + (n === 1 ? ' new message' : ' new messages') : 'Jump to latest' })
  ] }) })
}

// Agents in the room that are working on something: a face and typing dots at the foot of the timeline.
// "building “Pixel Sorter” · step 4", or "waiting on Maya to approve a step": the owner's Hermes is
// building the toy this agent offered. Only a title the agent itself posted and a step count arrive.
function buildLabel(a, ownerName) {
  const b = a && a.build
  if (!b) return ''
  const title = '“' + (b.title || 'the toy') + '”'
  if (b.wait) return 'building ' + title + ' · waiting on ' + ownerName + ' to approve a step'
  return 'building ' + title + (b.step ? ' · step ' + b.step : '')
}

function Thinking(props) {
  const busy = []
  const owner = {}
  for (const p of props.room.members || []) {
    for (const a of p.agents || []) {
      if (stateWord(a.state) === 'working' || (a.build && !a.build.wait)) { busy.push(a); owner[a.pk] = p.you ? 'you' : p.name }
    }
  }
  if (!busy.length) return null
  const builders = busy.filter(a => a.build)
  const thinkers = busy.filter(a => !a.build)
  const parts = builders.map(a => a.name + ' is ' + buildLabel(a, owner[a.pk]))
  if (thinkers.length) parts.push(joinNames(thinkers.map(a => a.name)) + (thinkers.length > 1 ? ' are' : ' is') + ' thinking')
  const text = parts.join('. ')
  return jsxs('div', { className: 'h-thinking', role: 'status', 'aria-label': text, children: [
    jsx('div', { className: 'h-row', style: { gap: 2 }, children: busy.slice(0, 3).map(a => jsx(Face, { face: a.face, pk: a.pk, state: a.state, size: 22, name: a.name }, a.pk)) }),
    jsxs('div', { className: 'h-typing', children: [0, 1, 2].map(i => jsx('i', { style: { animationDelay: (i * 0.16) + 's' } }, i)) }),
    jsx('span', { className: 'h-faint h-small', children: text })
  ] })
}

// Fold runs of joins into one quiet line; mark the first message of each speaker's run.
function groupItems(msgs, newAfter) {
  const out = []
  let prev = null
  let marked = !newAfter
  for (const m of msgs) {
    // "New messages": before the first message from someone else that arrived after you last read the room
    if (!marked && m.t === 'msg' && !m.system && !m.mine && !m.deleted && m.ts > newAfter) {
      out.push({ kind: 'new', key: 'new-line' })
      marked = true
      prev = null
    }
    if (m.t === 'join' && m.impostor) {  // never folded: the flag has to stay visible
      out.push({ kind: 'join', key: m.id, m })
      prev = null
      continue
    }
    if (m.t === 'join') {
      const last = out[out.length - 1]
      if (last && last.kind === 'joins') { if (!last.names.includes(m.name)) last.names.push(m.name) }
      else out.push({ kind: 'joins', key: 'j-' + m.id, names: [m.name], ts: m.ts })
      prev = null
      continue
    }
    if (m.t === 'msg' && !m.system) {
      const first = !prev || prev.pk !== m.pk || m.ts - prev.ts > 300 || !!m.impostor
      out.push({ kind: 'msg', key: m.id, m, first })
      prev = m
      continue
    }
    out.push({ kind: m.t, key: m.id, m })
    prev = null
  }
  return out
}

function TimelineItem(props) {
  const { it, store, snap, room, book } = props
  const ref = useEnter(props.animate)
  const m = it.m
  let body = null
  if (it.kind === 'new') body = jsx('div', { className: 'h-newline', role: 'separator', 'aria-label': 'New messages', children: jsx('span', { children: 'New messages' }) })
  else if (it.kind === 'joins') body = jsx('div', { className: 'h-line', children: joinNames(it.names) + ' joined' })
  else if (it.kind === 'join') body = jsxs('div', { className: 'h-line', children: [m.name + ' joined ', jsx(ImpostorChip, { imp: m.impostor })] })
  else if (m.system === 'budget') body = jsxs('div', { className: 'h-system', role: 'status', children: [
    jsx(Face, { face: m.face, pk: m.pk, state: 'system: waiting', size: 20 }),
    jsx('span', { children: m.text || (m.name + ' is resting: out of budget for today') })
  ] })
  else if (it.kind === 'msg') body = jsx(Message, { m, first: it.first, book, store, roomId: room.id, onReply: props.onReply, onJump: props.onJump })
  else if (it.kind === 'offer') body = jsx(OfferCard, { m, store, snap, room })
  else if (it.kind === 'offer_state') body = jsxs('div', { className: 'h-line', children: [offerStateLine(m, room), m.impostor && ' ', m.impostor && jsx(ImpostorChip, { imp: m.impostor })] })
  else if (it.kind === 'share') body = jsx(ShareCard, { m, store, room })
  else if (it.kind === 'tales_reveal') body = jsx('div', { className: 'h-line', children: m.mode === 'agent'
    ? gameName(m.mode) + ' · round ' + (m.round || '?') + ' revealed'
    : 'Tall Tales · round ' + (m.round || '?') + ' · the truth was “' + (m.answer || '') + '”' })
  else if (it.kind === 'tales_start') body = jsx('div', { className: 'h-line', children: m.name + ' started a game of ' + gameName(m.mode) })
  else if (it.kind === 'tales_end') body = jsx('div', { className: 'h-line', children: gameName(m.mode) + ' is over' })
  if (!body) return null
  return jsx('div', { ref, children: body })
}

function offerStateLine(m, room) {
  const offer = (room.messages || []).find(x => x.id === m.offer)
  const title = offer && offer.title ? '“' + offer.title + '”' : 'the idea'
  if (m.state === 'building') return m.name + ' is building ' + title + ' in Hermes'
  if (m.state === 'declined') return m.name + ' passed on ' + title
  if (m.state === 'expired') return 'The offer of ' + title + ' expired without an answer'
  return m.name + ' · ' + title + ' · ' + m.state
}

// The eight reactions; the engine holds the same list and ignores anything else.
const REACTION_LIST = ['\u{1F44D}', '\u2764\uFE0F', '\u{1F602}', '\u{1F62E}', '\u{1F389}', '\u{1F440}', '\u{1F525}', '\u{1F64F}']

// A brief wash of the accent colour on a message the reader was sent to (a quote's click). The colour runs
// on a spring through a custom property; with reduced motion it is a plain marker for a moment.
function flash(node) {
  if (motion.reduced()) {
    node.setAttribute('data-flash', 'true')
    P.setTimeout(() => node.removeAttribute('data-flash'), 1200)
    return
  }
  motion.spring({ from: 1, to: 0, k: SPRING.calm.k, c: 9, onUpdate: x => { node.style.setProperty('--h-flash', String(Math.max(0, x).toFixed(3))) },
    onRest: () => node.style.removeProperty('--h-flash') })
}

function Message(props) {
  const m = props.m
  const agent = m.role === 'agent'
  const f = agent ? faceFor(m.face, m.pk) : null
  const imp = m.impostor
  const [picking, setPicking] = useState(false)
  // Edit and Delete: only on your own person messages, never your agent's (agents don't edit or delete)
  const [editing, setEditing] = useState(false)
  const [asking, setAsking] = useState(false)
  const editBtn = useRef(null)
  const own = !!(props.store && m.mine && !agent && !m.deleted)
  const who = { kind: agent ? 'agent' : 'person', pk: m.pk, name: m.name, face: m.face, owner_name: m.owner_name }
  const text = jsx(MessageBody, { m, book: props.book })
  const stopEdit = () => { setEditing(false); P.setTimeout(() => editBtn.current && editBtn.current.focus && editBtn.current.focus(), 0) }
  const saveEdit = async t => {
    try { await props.store.post('/edit', { room: props.roomId, target: m.id, text: t }); stopEdit() } catch (_) { /* toasted */ }
  }
  const doDelete = async () => {
    setAsking(false)
    try { await props.store.post('/delete', { room: props.roomId, target: m.id }, 'Message deleted') } catch (_) { /* toasted */ }
  }
  const extra = own ? [
    jsx(K.Tip, { label: 'Edit', children: jsx('button', { type: 'button', className: 'h-bar-btn', ref: editBtn, 'aria-label': 'Edit your message',
      onClick: () => setEditing(true), children: jsx(K.Icon, { name: 'edit', size: 14 }) }) }, 'edit'),
    jsx(K.Tip, { label: 'Delete', children: jsx('button', { type: 'button', className: 'h-bar-btn', 'aria-label': 'Delete your message',
      onClick: () => setAsking(true), children: jsx(K.Icon, { name: 'trash', size: 14 }) }) }, 'delete')
  ] : null
  const react = (emoji, on) => props.store.post('/react', { room: props.roomId, target: m.id, emoji, on }).catch(() => {})
  const mineSet = (m.reactions || []).filter(r => r.mine).map(r => r.emoji)
  return jsxs('div', { className: cx('h-msg', agent && 'h-agent'), 'data-role': m.role, 'data-first': props.first, 'data-mid': m.id, 'data-bar': picking,
    'data-impostor': !!imp, 'data-mentioned': !!m.mentions_me, style: agent ? { '--hue': f.hue } : undefined, children: [
      jsx('div', { className: 'h-gutter', children: props.first ? jsx(ProfileButton, { who, label: 'Show ' + m.name + '’s card',
        children: agent ? jsx(Face, { face: m.face, pk: m.pk, state: 'activity: idle', size: 28, name: m.name }) : jsx(PersonMark, { pk: m.pk, name: m.name, flagged: !!imp }) }) : null }),
      jsxs('div', { style: { minWidth: 0 }, children: [
        props.first && jsxs('div', { className: 'h-meta', children: [
          jsx(ProfileButton, { who, label: 'Show ' + m.name + '’s card', children: jsx('b', { children: m.name }) }),
          agent && jsx('span', { className: 'h-owner', children: m.mine ? 'your agent' : (m.owner_name ? m.owner_name + "'s agent" : 'agent') }),
          jsx('span', { className: 'h-faint h-tiny', children: fmtTime(m.ts) })
        ] }),
        m.quote && jsx(QuoteLine, { quote: m.quote, onJump: props.onJump }),
        editing ? jsx(MessageEditor, { text: m.text, onSave: saveEdit, onCancel: stopEdit })
          : agent ? jsx('div', { className: 'h-bubble', children: jsx('div', { className: 'h-text', children: text }) })
          : jsx('div', { className: 'h-text', children: text }),
        imp && jsx(ImpostorChip, { imp }),
        (m.reactions || []).length > 0 && jsx(ReactionChips, { reactions: m.reactions, onToggle: (emoji, on) => react(emoji, on) }),
        m.delivery && jsx('div', { className: 'h-faint h-tiny', role: m.delivery === 'failed' ? 'alert' : undefined,
          children: m.delivery === 'pending' ? 'Not delivered yet. Ninsei will resend it when a relay is back.'
            : 'Not delivered. The relays turned it down or it waited too long.' })
      ] }),
      props.store && !m.deleted && jsx(MessageBar, { m, picking, setPicking, mine: mineSet, onReply: props.onReply, extra,
        onPick: emoji => react(emoji, !mineSet.includes(emoji)) }),
      asking && jsx(DeleteConfirm, { open: true, onConfirm: doDelete, onClose: () => setAsking(false) })
    ] })
}

// A message's words: "Message deleted" for a deleted one, otherwise the formatted text, followed by a quiet
// "(edited)" whose hover text says when. An edit never changes who said it or when it was sent.
function MessageBody(props) {
  const m = props.m
  if (m.deleted) return jsx('span', { className: 'h-deleted-t', children: 'Message deleted' })
  return jsxs(Fragment, { children: [
    jsx(RichText, { text: m.text, book: props.book }),
    m.edited && jsx('span', { className: 'h-edited', title: 'Edited ' + fmtTime(m.edited_at || m.ts), children: ' (edited)' })
  ] })
}

// Edit in place: the textarea holds the old words; Enter saves, Shift+Enter is a new line, Escape cancels.
// Saving the same words, or nothing, just closes it (the engine refuses an empty message: delete it instead).
function MessageEditor(props) {
  const [val, setVal] = useState(props.text || '')
  const [busy, setBusy] = useState(false)
  const ta = useRef(null)
  useLayoutEffect(() => {
    const el = ta.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(220, el.scrollHeight) + 'px'
  }, [val])
  useEffect(() => {
    const el = ta.current
    if (el && el.focus) { el.focus(); if (el.setSelectionRange) el.setSelectionRange(el.value.length, el.value.length) }
  }, [])
  const save = async () => {
    const t = val.trim()
    if (busy) return
    if (!t || t === String(props.text || '').trim()) { props.onCancel(); return }
    setBusy(true)
    try { await props.onSave(t) } finally { setBusy(false) }
  }
  const onKeyDown = e => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); props.onCancel() }
    else if (e.key === 'Enter' && !e.shiftKey && !(e.nativeEvent && e.nativeEvent.isComposing)) { e.preventDefault(); save() }
  }
  return jsxs('div', { className: 'h-edit', children: [
    jsx('textarea', { ref: ta, rows: 1, value: val, maxLength: 1200, 'aria-label': 'Edit your message', onKeyDown, onChange: e => setVal(e.target.value) }),
    jsx('div', { className: 'h-faint h-tiny', children: 'Enter to save · Shift+Enter for a new line · Escape to cancel' })
  ] })
}

// Deleting asks once, and says plainly what it can and can't do.
function DeleteConfirm(props) {
  return jsx(Modal, { open: props.open, onClose: props.onClose, title: 'Delete for everyone using Ninsei?',
    description: "Relays and other apps may already have a copy; Nostr can't take back what was published.",
    footer: [
      jsx(K.Button, { variant: 'ghost', onClick: props.onClose, children: 'Keep it' }, 'c'),
      jsx(K.Button, { variant: 'danger', onClick: props.onConfirm, children: 'Delete' }, 'd')
    ] })
}

// What you can do to a message, shown on hover and whenever focus is inside the message. Buttons are real
// buttons, so the keyboard reaches them. Edit and Delete (your own messages) are added to `extra`.
function MessageBar(props) {
  const { m, picking, setPicking } = props
  const trigger = useRef(null)
  const close = () => { setPicking(false); trigger.current && trigger.current.focus && trigger.current.focus() }
  return jsxs('div', { className: 'h-bar', role: 'toolbar', 'aria-label': 'Message actions', children: [
    jsx(K.Tip, { label: 'Add a reaction', children: jsx('button', { type: 'button', className: 'h-bar-btn', ref: trigger, 'aria-label': 'Add a reaction',
      'aria-haspopup': 'menu', 'aria-expanded': picking, onClick: () => setPicking(!picking), children: jsx(K.Icon, { name: 'smiley', size: 14 }) }) }),
    props.onReply && jsx(K.Tip, { label: 'Reply', children: jsx('button', { type: 'button', className: 'h-bar-btn', 'aria-label': 'Reply to ' + m.name,
      onClick: () => props.onReply(m), children: jsx(K.Icon, { name: 'reply', size: 14 }) }) }),
    props.extra,
    picking && jsx(ReactionPicker, { mine: props.mine, onClose: close, onPick: emoji => { props.onPick(emoji); close() } })
  ] })
}

// The eight emoji in a row: arrows move, Enter or Space chooses, Escape closes. The ones you already
// gave read as selected, and choosing one again takes it back.
function ReactionPicker(props) {
  const ref = useEnter(true)
  const [idx, setIdx] = useState(0)
  const items = useRef([])
  useEffect(() => {
    const el = items.current[idx]
    if (el && el.focus) el.focus()
  }, [idx])
  useEffect(() => {
    const away = e => { if (ref.current && !ref.current.contains(e.target)) props.onClose() }
    const off = P.listen(document, 'pointerdown', away)
    return () => off()
  }, [])
  const onKeyDown = e => {
    const n = REACTION_LIST.length
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); setIdx((idx + 1) % n) }
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); setIdx((idx + n - 1) % n) }
    else if (e.key === 'Home') { e.preventDefault(); setIdx(0) }
    else if (e.key === 'End') { e.preventDefault(); setIdx(n - 1) }
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); props.onPick(REACTION_LIST[idx]) }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); props.onClose() }
  }
  return jsx('div', { className: 'h-picker', ref, role: 'menu', 'aria-label': 'Add a reaction', onKeyDown,
    children: REACTION_LIST.map((emoji, i) => jsx('div', { role: 'menuitemradio', 'aria-checked': props.mine.includes(emoji), tabIndex: i === idx ? 0 : -1,
      className: 'h-pick', 'aria-label': emoji, ref: el => { items.current[i] = el }, onClick: () => props.onPick(emoji), onMouseEnter: () => setIdx(i),
      children: emoji }, emoji)) })
}

// Chips under a message. A chip you pressed is filled; pressing it again takes your reaction back. The count
// settles on a spring when it changes, and the names (up to eight, from the room's own name book) are its label.
function ReactionChips(props) {
  return jsx('div', { className: 'h-reacts', role: 'group', 'aria-label': 'Reactions', children: props.reactions.map(r =>
    jsx(ReactionChip, { r, onToggle: props.onToggle }, r.emoji)) })
}

function ReactionChip(props) {
  const { r } = props
  const ref = useRef(null)
  const first = useRef(true)
  useEffect(() => {
    const el = ref.current
    if (first.current) { first.current = false; return }
    if (!el || motion.reduced()) return
    const s = motion.spring({ from: 1.22, to: 1, k: SPRING.pop.k, c: SPRING.pop.c, onUpdate: x => { el.style.transform = Math.abs(x - 1) < 0.002 ? '' : 'scale(' + x.toFixed(3) + ')' } })
    return () => s.stop()
  }, [r.count, r.mine])
  const more = r.count - (r.names || []).length
  const who = (r.names || []).join(', ') + (more > 0 ? ' and ' + more + ' more' : '')
  const label = r.emoji + ' ' + r.count + (who ? ': ' + who : '') + (r.mine ? '. Press to take yours back.' : '. Press to add yours.')
  return jsxs('button', { type: 'button', className: 'h-react', ref, 'data-mine': r.mine, 'aria-pressed': r.mine, 'aria-label': label, title: who,
    onClick: () => props.onToggle(r.emoji, !r.mine), children: [
      jsx('span', { className: 'h-react-e', 'aria-hidden': true, children: r.emoji }),
      jsx('span', { className: 'h-react-n', 'aria-hidden': true, children: r.count })
    ] })
}

// The line above a reply: who and the start of what it answers. A click goes to the original when it is loaded.
// A lookalike's message is quoted with the same flag the room shows on it, never under the real name.
function QuoteLine(props) {
  const q = props.quote
  if (q.deleted) return jsxs('div', { className: 'h-quote h-quote-gone', children: [jsx(K.Icon, { name: 'reply', size: 11 }), jsx('span', { children: 'Message deleted' })] })
  if (q.missing) return jsxs('div', { className: 'h-quote h-quote-gone', children: [jsx(K.Icon, { name: 'reply', size: 11 }), jsx('span', { children: 'Original message not available' })] })
  return jsxs('div', { className: 'h-quote-row', children: [
    jsxs('button', { type: 'button', className: 'h-quote', 'aria-label': 'Go to the message from ' + q.name + ': ' + q.text, onClick: () => props.onJump && props.onJump(q.id), children: [
      jsx(K.Icon, { name: 'reply', size: 11 }),
      jsx('b', { children: q.name }),
      jsx('span', { className: 'h-quote-t', children: q.text })
    ] }),
    q.impostor && jsx(ImpostorChip, { imp: q.impostor })
  ] })
}

// Message text: formatting, links and @mentions drawn by one renderer over richParts' single scan. It
// builds React nodes only (never HTML), so nothing a stranger types can become markup. Plain text with
// nothing in it comes back as the string itself.
function RichText(props) {
  const blocks = useMemo(() => richParts(props.text, mentionNames(props.book)), [props.text, props.book])
  if (blocks.length === 1 && blocks[0].kind === 'text' && blocks[0].tokens.every(t => t.t === 'text' && !t.b && !t.i)) return String(props.text == null ? '' : props.text)
  return jsx(Fragment, { children: blocks.map((bl, k) => bl.kind === 'pre'
    ? jsx('pre', { className: 'h-fence', children: jsx('code', { children: bl.text }) }, k)
    : jsx(Fragment, { children: bl.tokens.map((t, i) => richNode(t, i)) }, k)) })
}

function richNode(t, i) {
  if (t.t === 'code') return jsx('code', { className: 'h-code', children: t.text }, i)
  let node
  if (t.t === 'link') node = jsx(RichLink, { href: t.href, text: t.text })
  else if (t.t === 'mention') node = jsx('span', { className: 'h-at', 'data-me': t.me, children: t.text })
  else node = t.text
  if (t.i) node = jsx('em', { children: node })
  if (t.b) node = jsx('strong', { children: node })
  return jsx(Fragment, { children: node }, i)
}

// A link shows the address itself, never other words. Desktop hands it to the system browser through the host
// (the page can't open windows); the dashboard opens a new tab with no opener. If the host can't, the address is
// copied so it is not lost.
function RichLink(props) {
  const open = e => {
    if (!P.openExternal) return
    e.preventDefault()
    P.openExternal(props.href).then(ok => {
      if (ok) return
      P.copy(props.href)
      P.toast('error', 'Couldn’t open the link here. It is copied: paste it into your browser.')
    })
  }
  return jsx('a', { className: 'h-link', href: props.href, target: '_blank', rel: 'noopener noreferrer', onClick: open,
    title: props.href !== props.text ? props.href : undefined, children: props.text })
}

// The search panel under the room header: type, arrows move through results, Enter opens one (it scrolls to the
// message when it is loaded, else the panel shows it with the messages around it), Escape goes back, then closes.
function SearchPanel(props) {
  const { room } = props
  const [q, setQ] = useState('')
  const [results, setResults] = useState(null)
  const [error, setError] = useState('')
  const [active, setActive] = useState(0)
  const [ctx, setCtx] = useState(null)   // { id, messages } while a result is shown in context
  const input = useRef(null)
  const ticket = useRef(0)
  useEffect(() => { if (input.current && input.current.focus) input.current.focus() }, [])
  useEffect(() => {
    const term = q.trim()
    const mine = ++ticket.current
    if (!term) { setResults(null); setError(''); return }
    const off = P.setTimeout(() => {
      P.rest('/search?room=' + encodeURIComponent(room.id) + '&q=' + encodeURIComponent(term.slice(0, 100)) + '&limit=50').then(out => {
        if (mine !== ticket.current) return
        setResults(out.results || []); setError(''); setActive(0)
      }, e => { if (mine === ticket.current) { setResults(null); setError(errText(e)) } })
    }, 180)
    return off
  }, [q, room.id])
  const open = r => {
    if (!r) return
    if (props.onPick(r.id)) { props.onClose(); return }
    P.rest('/search/context?room=' + encodeURIComponent(room.id) + '&id=' + encodeURIComponent(r.id)).then(
      out => setCtx({ id: r.id, messages: out.messages || [] }), e => setError(errText(e)))
  }
  const onKeyDown = e => {
    if (e.nativeEvent && e.nativeEvent.isComposing) return
    const n = (results || []).length
    if (e.key === 'ArrowDown' && n) { e.preventDefault(); setActive((active + 1) % n) }
    else if (e.key === 'ArrowUp' && n) { e.preventDefault(); setActive((active + n - 1) % n) }
    else if (e.key === 'Enter') { e.preventDefault(); open((results || [])[active]) }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); if (ctx) setCtx(null); else props.onClose() }
  }
  useEffect(() => {
    const el = typeof document !== 'undefined' && document.getElementById && document.getElementById('h-sr-' + active)
    if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' })
  }, [active, results])
  const ref = useEnter(true)
  const term = q.trim()
  const list = results || []
  const status = error ? error : !term ? '' : results === null ? 'Searching…' : list.length === 0 ? 'Nothing found in this room.' : list.length + (list.length === 1 ? ' message' : ' messages') + (list.length >= 50 ? ' (the newest 50)' : '')
  return jsxs('div', { className: 'h-search', ref, role: 'search', children: [
    jsx('input', { className: 'h-search-in', ref: input, type: 'search', value: q, maxLength: 100, placeholder: 'Search this room', 'aria-label': 'Search this room',
      role: 'combobox', 'aria-expanded': list.length > 0, 'aria-controls': 'h-search-list', 'aria-autocomplete': 'list',
      'aria-activedescendant': list.length && !ctx ? 'h-sr-' + active : undefined,
      onChange: e => { setCtx(null); setQ(e.target.value) }, onKeyDown }),
    jsx('div', { className: 'h-faint h-small h-search-status', role: 'status', children: status }),
    ctx
      ? jsxs('div', { className: 'h-search-ctx', children: [
          jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: () => setCtx(null), children: 'Back to results' }),
          ctx.messages.map(m => jsx(SearchRow, { m, q: term, current: m.id === ctx.id }, m.id))
        ] })
      : list.length > 0 && jsx('div', { className: 'h-search-list', id: 'h-search-list', role: 'listbox', 'aria-label': 'Search results',
          children: list.map((r, i) => jsx(SearchRow, { m: r, q: term, option: true, active: i === active, id: 'h-sr-' + i, onClick: () => { setActive(i); open(r) } }, r.id)) })
  ] })
}

// One found message: who and when, and its text with the matches marked. Long text is cut around the first match.
function SearchRow(props) {
  const { m, q } = props
  const full = String(m.text || '')
  const hits = matchRanges(full, q, 20)
  let from = 0
  if (hits.length && hits[0].start > 70) from = hits[0].start - 50
  const text = full.slice(from, from + 260)
  const parts = []
  let at = 0
  for (const h of matchRanges(text, q, 20)) {
    if (h.start > at) parts.push(text.slice(at, h.start))
    parts.push(jsx('mark', { className: 'h-mark', children: text.slice(h.start, h.end) }, h.start))
    at = h.end
  }
  if (at < text.length) parts.push(text.slice(at))
  return jsxs('div', { className: 'h-sr', id: props.id, role: props.option ? 'option' : undefined, 'aria-selected': props.option ? !!props.active : undefined,
    'data-active': !!props.active, 'data-current': !!props.current, onClick: props.onClick, children: [
      jsxs('div', { className: 'h-sr-meta', children: [
        jsx('b', { children: m.name }),
        m.role === 'agent' && jsx('span', { className: 'h-faint h-tiny', children: 'agent' }),
        m.impostor && jsx(ImpostorChip, { imp: m.impostor }),
        jsx('span', { className: 'h-faint h-tiny', children: fmtWhen(m.ts) })
      ] }),
      jsx('div', { className: 'h-sr-t', children: [from > 0 && '…', parts, from + 260 < full.length && '…'] })
    ] })
}

// The safety moment: a display name is not an identity. Owners are recognised by key only.
function ImpostorChip(props) {
  const imp = props.imp
  const text = 'Not signed by ' + imp.claimed + "'s key" + (imp.agent ? ' — ' + imp.agent + ' ignores it' : '')
  return jsx(K.Tip, { label: 'Someone else is using the name “' + imp.claimed + '”. Agents only take direction from their owner’s signing key, never from a display name.',
    children: jsxs('span', { className: 'h-impostor', role: 'note', children: [jsx(K.Icon, { name: 'shield', size: 12 }), text] }) })
}

// ---- offers: idea -> owner reviews -> owner's Hermes builds -> owner shares ----------------

function OfferCard(props) {
  const { m, store, snap, room } = props
  const [review, setReview] = useState(false)
  const [share, setShare] = useState(false)
  const [prompt, setPrompt] = useState(null)
  const f = faceFor(m.face, m.pk)
  const local = (snap.offers || []).find(o => o.id === m.id)
  const state = (local && local.status) || m.state || 'open'
  const owner = m.owner_name || 'its owner'

  const decline = () => store.post('/offers/answer', { offer: m.id, accept: false })

  let status = null
  let actions = null
  if (m.yours) {
    if (state === 'open') actions = [
      jsx(K.Button, { variant: 'primary', size: 'sm', onClick: () => setReview(true), children: 'Review & build' }, 'r'),
      jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: decline, children: 'Not now' }, 'n')]
    else if (state === 'building') status = 'Your Hermes is building it. When the file is saved, you can preview and share it here.'
    else if (state === 'ready') actions = [
      jsx(K.Button, { variant: 'primary', size: 'sm', onClick: () => setShare(true), children: 'Preview & share' }, 's')]
    else if (state === 'shared') status = 'Shared with the room.'
    else if (state === 'declined') status = 'You passed on this one.'
    else if (state === 'expired') status = 'Expired: nobody answered it within a day.'
    else if (state === 'dropped') status = 'Dropped when you left the room.'
  } else {
    status = state === 'open' ? 'Waiting for ' + owner + ' to decide.'
      : state === 'building' || state === 'ready' ? owner + ' is building it.'
      : state === 'shared' ? owner + ' shared it below.'
      : state === 'declined' ? owner + ' passed.'
      : state === 'expired' ? 'Expired without an answer.' : null
  }

  return jsxs('div', { className: 'h-card h-agent', style: { '--hue': f.hue }, children: [
    jsxs('div', { className: 'h-row', children: [
      jsx(Face, { face: m.face, pk: m.pk, state: state === 'open' && m.yours ? 'system: waiting' : 'activity: idle', size: 28, name: m.name }),
      jsxs('div', { className: 'h-grow', children: [
        jsx('div', { className: 'h-kicker', children: m.name + ' has an idea' + (m.topic ? ' · ' + m.topic : '') }),
        jsx('h4', { children: m.title })
      ] })
    ] }),
    jsx('div', { className: 'h-text', children: m.pitch }),
    status && jsx('div', { className: 'h-faint h-small', children: status }),
    actions && jsx('div', { className: 'h-actions', children: actions }),
    review && jsx(ReviewDialog, { m, store, onClose: () => setReview(false), onPrompt: setPrompt }),
    prompt && jsx(PromptDialog, { prompt, onClose: () => setPrompt(null) }),
    share && jsx(ShareDialog, { m, store, room, onClose: () => setShare(false) })
  ] })
}

function ReviewDialog(props) {
  const { m, store } = props
  const [task, setTask] = useState(m.task || '')
  const [busy, setBusy] = useState(false)
  const go = async () => {
    setBusy(true)
    let out = null
    try { out = await store.post('/offers/answer', { offer: m.id, accept: true, task }) } catch (_) { setBusy(false); return }
    props.onClose()
    const opened = await P.openBuild(out.prompt)
    if (!opened) props.onPrompt(out.prompt)
  }
  return jsx(Modal, { open: true, onClose: props.onClose, wide: true, title: 'Build “' + m.title + '”?',
    description: 'This is the full task your own Hermes will work on. Your room agent drafted it from room chat, which anyone in the room can write, so read all of it. Edit anything you like.',
    footer: [
      jsx(K.Button, { variant: 'ghost', onClick: props.onClose, children: 'Cancel' }, 'c'),
      jsx(K.Button, { variant: 'primary', disabled: busy || !task.trim(), onClick: go, children: busy ? 'Opening…' : P.kind === 'desktop' ? 'Build in Hermes' : 'Accept & get prompt' }, 'b')
    ],
    children: jsxs('div', { className: 'h-col', style: { gap: 10 }, children: [
      jsx('textarea', { className: 'h-ta', rows: 7, value: task, maxLength: 2000, 'aria-label': 'Task', onChange: e => setTask(e.target.value) }),
      jsx(Notice, { icon: 'shield', children: P.kind === 'desktop'
        ? 'A new Hermes chat opens with this task in the composer. Room quotes go in labelled as untrusted. Nothing runs until you press Enter, and it runs under your normal approvals.'
        : 'You get the full prompt to paste into a Hermes chat. Room quotes go in labelled as untrusted, and it runs under your normal approvals.' })
    ] }) })
}

// Dashboard (or a Desktop without the composer API): hand the prompt over by copy.
function PromptDialog(props) {
  const copy = async () => {
    const ok = await P.copy(props.prompt)
    P.toast(ok ? 'info' : 'error', ok ? 'Prompt copied' : 'Could not reach the clipboard; select the text instead')
  }
  return jsx(Modal, { open: true, onClose: props.onClose, wide: true, title: 'Paste this into Hermes',
    description: 'Start a chat (hermes, or a new chat in Hermes Desktop), paste the prompt, read it, and press Enter. When Hermes saves the file, “Preview & share” appears on the card.',
    footer: [
      jsx(K.Button, { variant: 'ghost', onClick: props.onClose, children: 'Done' }, 'd'),
      jsx(K.Button, { variant: 'primary', onClick: copy, children: jsxs(Fragment, { children: [jsx(K.Icon, { name: 'copy', size: 13 }), 'Copy prompt'] }) }, 'c')
    ],
    children: jsx('pre', { className: 'h-pre', style: { maxHeight: 360 }, children: props.prompt }) })
}

// The dialog shows one reading of the build, and the file is shared only if it is still those bytes:
// the share request carries the build's sha256, and the engine refuses a different file.
function shareChanged(sent, fresh) {
  return !!(fresh && fresh.sha256 && fresh.sha256 !== sent)
}

function ShareDialog(props) {
  const { m, store } = props
  const [build, setBuild] = useState(null)
  const [err, setErr] = useState('')
  const [title, setTitle] = useState(m.title || '')
  const [busy, setBusy] = useState(false)
  const [sure, setSure] = useState(false)
  const [run, setRun] = useState(false)
  const [changed, setChanged] = useState(false)
  const fetchBuild = () => P.rest('/offers/build?offer=' + encodeURIComponent(m.id))
  useEffect(() => { fetchBuild().then(setBuild, e => setErr(errText(e))) }, [m.id])
  const found = (build && build.secrets) || []
  const fits = !build || build.fits !== false
  const share = async () => {
    if (!build) return
    if (found.length && !sure) { setSure(true); return }
    setBusy(true)
    setChanged(false)
    try {
      await store.post('/offers/share', { offer: m.id, title, confirm_secrets: sure, sha256: build.sha256 }, 'Shared with the room')
      if (props.onShared) props.onShared()
      props.onClose()
    } catch (_) {
      setBusy(false)
      // The engine may have refused because the file changed after this dialog read it: read it again.
      // A new file means new source, a new scan and a new preview, so nothing approved carries over.
      try {
        const fresh = await fetchBuild()
        if (shareChanged(build.sha256, fresh)) { setBuild(fresh); setSure(false); setRun(false); setChanged(true) }
      } catch (_) { /* the engine's own message was toasted */ }
    }
  }
  return jsx(Modal, { open: true, onClose: props.onClose, wide: true, title: 'Share with ' + props.room.name,
    footer: [
      jsx(K.Button, { variant: 'ghost', onClick: props.onClose, children: 'Not yet' }, 'c'),
      jsx(K.Button, { variant: 'primary', disabled: !build || busy || !fits, onClick: share, children: busy ? 'Sharing…' : sure ? 'Share anyway' : 'Share this file' }, 's')
    ],
    children: jsxs('div', { className: 'h-col', style: { gap: 10 }, children: [
      err ? jsx(Notice, { icon: 'warning', role: 'alert', children: err })
        : !build ? jsx('div', { className: 'h-faint', children: 'Reading the build…' })
        : jsxs(Fragment, { children: [
          changed && jsx(Notice, { icon: 'warning', role: 'alert', children: 'The toy changed since you reviewed it, so nothing was shared. The preview, source and checks below are for the new file. Look them over before you share.' }),
          run ? jsx(ToyFrame, { html: build.frame || '', title: title })
            : jsxs('div', { className: 'h-col', style: { gap: 8 }, children: [
              jsx('div', { className: 'h-faint h-small', children: 'The toy does not run until you press Run preview. It runs in a sandbox with no access to your Hermes or your files. It can’t fetch from the web, but it can still open a direct WebRTC connection or a web page, and either can see your IP address.' }),
              jsx('div', { children: jsx(K.Button, { variant: 'secondary', size: 'sm', onClick: () => setRun(true), children: jsxs(Fragment, { children: [jsx(K.Icon, { name: 'play', size: 13 }), 'Run preview'] }) }) })
            ] }),
          jsx(Field, { label: 'Title', id: 'h-share-title', children: jsx(K.Input, { id: 'h-share-title', value: title, maxLength: 80, onChange: e => setTitle(e.target.value) }) }),
          jsx(Notice, { icon: 'globe', children: jsxs('span', { children: [
            'This exact file (', jsx('b', { children: fmtBytes(build.bytes) }), ') is published publicly to the room’s relays. Everyone in the room can run it in a sandbox. Public relays keep messages effectively forever.'
          ] }) }),
          !fits && jsx(Notice, { icon: 'warning', role: 'alert', children: 'Too big to send: ' + fmtBytes(build.serialized_bytes) + ' once packed for the relays, and the limit is ' + fmtBytes(build.limit) + '. Ask Hermes to make it smaller.' }),
          found.length > 0 && jsx(Notice, { icon: 'warning', role: 'alert', children: jsxs('span', { children: [
            jsx('b', { children: 'This file looks like it contains ' + (found.length === 1 ? 'a secret' : 'secrets') + ': ' }), found.join('; '),
            '. Check the source before you share it. ', sure ? 'Press “Share anyway” to publish it regardless.' : 'You will be asked once more.'
          ] }) }),
          jsxs('details', { children: [
            jsx('summary', { className: 'h-faint h-small', style: { cursor: 'pointer' }, children: 'Source (' + fmtBytes(build.bytes) + ')' }),
            jsx('pre', { className: 'h-pre', style: { maxHeight: 240 }, children: build.html })
          ] })
        ] })
    ] }) })
}

function ShareCard(props) {
  const { m, room } = props
  const [html, setHtml] = useState(null)
  const [tall, setTall] = useState(false)
  const [busy, setBusy] = useState(false)
  const card = useRef(null)
  const run = async () => {
    setBusy(true)
    try { const out = await P.rest('/share?room=' + encodeURIComponent(room.id) + '&id=' + encodeURIComponent(m.id)); setHtml(out.html) }
    catch (e) { P.toast('error', errText(e)) }
    setBusy(false)
  }
  // bring the running toy fully into view
  useEffect(() => {
    if (html != null && card.current) springIntoView(card.current)
  }, [html != null, tall])
  return jsxs('div', { className: 'h-card', ref: card, children: [
    jsxs('div', { className: 'h-row', children: [
      jsx(K.Icon, { name: 'play', size: 16 }),
      jsxs('div', { className: 'h-grow', children: [
        jsx('div', { className: 'h-kicker', children: (m.mine ? 'You' : m.name) + ' shared a toy · ' + fmtBytes(m.size) }),
        jsx('h4', { children: m.title || 'Untitled toy' }),
        m.impostor && jsx(ImpostorChip, { imp: m.impostor })
      ] }),
      html ? jsxs(Fragment, { children: [
        jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: () => setTall(!tall), children: tall ? 'Smaller' : 'Bigger' }),
        jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: () => setHtml(null), children: 'Stop' })
      ] }) : jsx(K.Button, { variant: 'secondary', size: 'sm', disabled: busy, onClick: run, children: busy ? 'Loading…' : 'Run' })
    ] }),
    html != null ? jsx(ToyFrame, { html, title: m.title, tall }) : jsx('div', { className: 'h-faint h-small', children: 'Runs in a sandbox with no access to your Hermes or your files. It can’t fetch from the web, but it can still open a direct WebRTC connection or a web page, and either can see your IP address and what you do in the toy. Run toys from people you trust.' })
  ] })
}

// ---- drafts queued by the ninsei_say tool --------------------------------------------------

function DraftTray(props) {
  const { store, drafts } = props
  return jsx('div', { className: 'h-tray', children: drafts.map(d => jsx(Draft, { store, d }, d.id)) })
}

function Draft(props) {
  const { store, d } = props
  const [text, setText] = useState(d.text)
  const ref = useEnter(true)
  const ta = useRef(null)
  // grow to the whole draft, so nothing is sent without being read
  useLayoutEffect(() => {
    const el = ta.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = el.scrollHeight + 'px'
  }, [text])
  return jsxs('div', { className: 'h-draft', ref, children: [
    jsx(K.Icon, { name: 'edit', size: 14 }),
    jsxs('div', { className: 'h-grow h-col', style: { gap: 4 }, children: [
      jsx('div', { className: 'h-faint h-tiny', children: 'Draft from ' + (d.origin || 'Hermes') + ' · not sent yet' }),
      jsx('textarea', { ref: ta, className: 'h-ta', rows: 1, style: { overflow: 'hidden', resize: 'none' }, value: text, onChange: e => setText(e.target.value), 'aria-label': 'Draft text' })
    ] }),
    jsxs('div', { className: 'h-col', style: { gap: 4 }, children: [
      jsx(K.Button, { variant: 'primary', size: 'sm', disabled: !text.trim(), onClick: () => store.post('/drafts/send', { id: d.id, text }), children: 'Send' }),
      jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: () => store.post('/drafts/discard', { id: d.id }), children: 'Discard' })
    ] })
  ] })
}

// ---- composer --------------------------------------------------------------------------------

// "Maya is typing…": people only (agents show their own thinking dots), always in the page so the composer never jumps.
// The row eases in on a spring when someone starts; the text is a status, so screen readers hear it once per change.
function TypingLine(props) {
  const list = props.list || []
  const text = typingText(list)
  return jsx('div', { className: 'h-typingline', role: 'status', 'aria-live': 'polite', children: text ? jsx(TypingRow, { list, text }, 'on') : null })
}

function TypingRow(props) {
  const ref = useEnter(true)
  return jsxs('div', { className: 'h-typingrow', ref, children: [
    jsx('span', { className: 'h-row', style: { gap: 2 }, 'aria-hidden': true, children: props.list.slice(0, 3).map(t => jsx(PersonMark, { pk: t.pk, name: t.name, size: 16, flagged: !!t.impostor }, t.pk)) }),
    jsx('span', { className: 'h-typing h-typing-s', 'aria-hidden': true, children: [0, 1, 2].map(i => jsx('i', { style: { animationDelay: (i * 0.16) + 's' } }, i)) }),
    jsx('span', { className: 'h-trunc', children: props.text })
  ] })
}

// Everyone you can @ in this room: your agent first, then who's here, then the rest. Never you, never a lookalike.
function mentionCandidates(room) {
  const out = []
  for (const p of (room && room.members) || []) {
    if (!p.you && !p.impostor) out.push({ pk: p.pk, name: p.name, kind: 'person', sub: p.online ? 'here now' : 'person', online: !!p.online })
    for (const a of p.agents || []) if (!a.impostor) out.push({ pk: a.pk, name: a.name, kind: 'agent', face: a.face, yours: !!a.yours,
      sub: a.yours ? 'your agent' : p.name + '’s agent', online: !!(a.yours || p.online) })
  }
  return out.sort((a, b) => (!!b.yours - !!a.yours) || (!!b.online - !!a.online) || a.name.localeCompare(b.name))
}

function Composer(props) {
  const { store, room, gameOn, reply, onCancelReply } = props
  // dm: a private conversation ({ onSend, placeholder, max }): no @ list (your agent is not in it), no games, no replies
  const dm = props.dm
  const [text, setText] = useState('')
  const [menu, setMenu] = useState(false)
  const [busy, setBusy] = useState(false)
  const [caret, setCaret] = useState(0)
  const [pick, setPick] = useState(0)
  const [shut, setShut] = useState(-1)  // the '@' position the menu was dismissed at, with Escape
  const ta = useRef(null)
  const caretTo = useRef(null)
  const cands = useMemo(() => dm ? [] : mentionCandidates(room), [room.members, !!dm])
  const mq = mentionQuery(text, caret)
  const opts = mq && mq.at !== shut ? mentionMatches(cands, mq.q) : []
  const open = opts.length > 0
  const sel = Math.min(pick, opts.length - 1)
  const listId = 'h-at-' + room.id
  const track = e => setCaret(e.target.selectionStart || 0)
  const choose = c => {
    const before = text.slice(0, mq.at) + '@' + c.name + ' '
    setText(before + text.slice(caret).replace(/^\s+/, ''))
    caretTo.current = before.length
    setCaret(before.length)
    setPick(0)
  }
  const send = async () => {
    const t = text.trim()
    if (!t || busy) return
    setBusy(true)
    setText('')
    const body = reply ? { room: room.id, text: t, reply: reply.id } : { room: room.id, text: t }
    try {
      if (dm) await dm.onSend(t)
      else { await store.post('/post', body); if (reply && onCancelReply) onCancelReply() }
    } catch (_) { setText(t) }
    setBusy(false)
    ta.current && ta.current.focus()
  }
  useLayoutEffect(() => {
    const el = ta.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(160, el.scrollHeight) + 'px'
    if (caretTo.current != null) { el.focus(); el.setSelectionRange(caretTo.current, caretTo.current); caretTo.current = null }
  }, [text])
  const replyId = reply ? reply.id : ''
  useEffect(() => { if (replyId && ta.current && ta.current.focus) ta.current.focus() }, [replyId])  // Reply puts you in the box
  const onKey = e => {
    if (e.key === 'Escape' && reply && !open && onCancelReply) { e.preventDefault(); onCancelReply(); return }
    if (open && !e.nativeEvent.isComposing) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        setPick((sel + (e.key === 'ArrowDown' ? 1 : opts.length - 1)) % opts.length)
        return
      }
      if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); choose(opts[sel]); return }
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); setShut(mq.at); return }
    }
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() }
  }
  const startGame = async mode => {
    setMenu(false)
    try { await store.post('/game/start', { room: room.id, mode }, gameName(mode) + ' is starting') } catch (_) { /* toasted */ }
  }
  return jsxs('div', { className: 'h-compose-box', style: { position: 'relative' }, 'data-private': dm ? true : undefined, children: [
    reply && jsxs('div', { className: 'h-replying', children: [
      jsx(K.Icon, { name: 'reply', size: 12 }),
      jsx('span', { className: 'h-trunc', children: jsxs(Fragment, { children: ['Replying to ', jsx('b', { children: reply.name }), jsx('span', { className: 'h-faint', children: ' · ' + reply.text })] }) }),
      jsx('button', { type: 'button', className: 'h-bar-btn', 'aria-label': 'Cancel reply', onClick: onCancelReply, children: jsx(K.Icon, { name: 'close', size: 12 }) })
    ] }),
    dm && jsx(K.Icon, { name: 'lock', size: 13 }),
    open && jsx('div', { className: 'h-ac', id: listId, role: 'listbox', 'aria-label': 'Mention someone', children: opts.map((c, i) =>
      jsxs('div', { id: listId + '-' + i, role: 'option', className: 'h-ac-opt', 'aria-selected': i === sel,
        onMouseDown: e => { e.preventDefault(); choose(c) }, onMouseEnter: () => setPick(i), children: [
          c.kind === 'agent' ? jsx(Face, { face: c.face, pk: c.pk, state: 'activity: idle', size: 22, name: c.name }) : jsx(PersonMark, { pk: c.pk, name: c.name, size: 22 }),
          jsx('b', { className: 'h-trunc', children: c.name }),
          jsx('span', { className: 'h-ac-sub h-trunc', children: c.sub })
        ] }, c.pk)) }),
    jsx('textarea', { ref: ta, rows: 1, value: text, placeholder: dm ? dm.placeholder : 'Message ' + room.name + ' (type @ to mention someone)', 'aria-label': dm ? dm.placeholder : 'Message', maxLength: dm ? dm.max : undefined,
      role: dm ? undefined : 'combobox', 'aria-autocomplete': dm ? undefined : 'list', 'aria-expanded': dm ? undefined : open, 'aria-controls': open ? listId : undefined,
      'aria-activedescendant': open ? listId + '-' + sel : undefined,
      onChange: e => { setText(e.target.value); track(e); setPick(0); if (!mentionQuery(e.target.value, e.target.selectionStart)) setShut(-1)
        if (!dm && e.target.value.trim()) typingPing(room.id) }, onSelect: track, onClick: track, onKeyUp: e => { if (!open || !/Arrow(Up|Down)/.test(e.key)) track(e) },
      onKeyDown: onKey }),
    !dm && jsxs('div', { style: { position: 'relative' }, children: [
      jsx(K.Tip, { label: 'Games', children: jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'Games', 'aria-expanded': menu,
        onClick: () => setMenu(!menu), children: jsx(K.Icon, { name: 'game', size: 15 }) }) }),
      menu && jsx(GamesMenu, { onClose: () => setMenu(false), onStart: startGame, gameOn })
    ] }),
    jsx(K.Button, { variant: 'primary', size: 'icon', 'aria-label': 'Send', disabled: !text.trim() || busy, onClick: send,
      children: jsx(K.Icon, { name: 'send', size: 14 }) })
  ] })
}

function GamesMenu(props) {
  const ref = useRef(null)
  useEffect(() => {
    const away = e => { if (ref.current && !ref.current.contains(e.target)) props.onClose() }
    const esc = e => { if (e.key === 'Escape') props.onClose() }
    const off1 = P.listen(document, 'pointerdown', away)
    const off2 = P.listen(document, 'keydown', esc)
    return () => { off1(); off2() }
  }, [])
  const item = (mode, icon, blurb) => jsxs('button', { type: 'button', role: 'menuitem', disabled: props.gameOn, onClick: () => props.onStart(mode), children: [
    jsx(K.Icon, { name: icon, size: 15 }),
    jsxs('span', { children: [
      jsx('b', { children: gameName(mode) }), jsx('br', {}),
      jsx('span', { className: 'h-faint h-small', children: props.gameOn ? 'A game is already running' : blurb })
    ] })
  ] }, mode)
  return jsxs('div', { className: 'h-menu', ref, role: 'menu', style: { left: 'auto', right: 0 }, children: [
    item('tales', 'game', 'Your agent hosts. Everyone writes a fake answer; spot the truth.'),
    item('agent', 'organization', 'Everyone answers, agents too, and the agents sound human on purpose. Spot them.')
  ] })
}

// ---- people -----------------------------------------------------------------------------------

function People(props) {
  const { room, snap } = props
  return jsxs('div', { className: 'h-col', style: { gap: 2 }, children: [
    jsx('div', { className: 'h-sec', style: { padding: '0 4px 6px' }, children: 'In the room' }),
    (room.members || []).map(p => jsx(Person, { p, store: props.store, key: p.pk })),
    jsx(MyAgentCard, { snap })
  ] })
}

function Person(props) {
  const p = props.p
  const ref = useEnter(false)
  return jsxs('div', { className: 'h-person', ref, children: [
    jsxs('div', { className: 'h-person-row', children: [
      jsx('span', { className: 'h-presence', 'data-on': !!p.online, role: 'img', 'aria-label': p.online ? 'online' : 'away' }),
      jsx(ProfileButton, { who: { kind: 'person', pk: p.pk, name: p.name }, label: 'Show ' + p.name + '’s card',
        children: jsx(PersonMark, { pk: p.pk, name: p.name, size: 22, flagged: !!p.impostor }) }),
      jsx(ProfileButton, { who: { kind: 'person', pk: p.pk, name: p.name }, className: 'h-trunc', label: 'Show ' + p.name + '’s card',
        children: jsx('span', { className: 'h-trunc h-namelink', style: { fontWeight: 600 }, children: p.name }) }),
      p.you && jsx('span', { className: 'h-faint h-tiny', children: 'you' }),
      p.impostor && jsx(NotVerified, { name: p.name }),
      !p.you && props.store && jsx('span', { className: 'h-hide', children: jsx(K.Tip, { label: 'Hide ' + p.name + ' and their agent', children:
        jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'Hide ' + p.name,
          onClick: () => props.store.post('/people/hide', { pk: p.pk, name: p.name }, 'Hid ' + p.name + ' and their agent. Undo in Settings.').catch(() => {}),
          children: jsx(K.Icon, { name: 'eye-closed', size: 13 }) }) }) })
    ] }),
    (p.agents || []).map(a => jsxs('div', { className: 'h-agentrow', children: [
      jsx(ProfileButton, { who: { kind: 'agent', pk: a.pk, name: a.name, face: a.face }, label: 'Show ' + a.name + '’s card',
        children: jsx(Face, { face: a.face, pk: a.pk, state: a.state, size: 20, name: a.name }) }),
      jsxs('div', { className: 'h-grow', style: { minWidth: 0 }, children: [
        jsxs('div', { className: 'h-row', style: { gap: 6, minWidth: 0 }, children: [
          jsx(ProfileButton, { who: { kind: 'agent', pk: a.pk, name: a.name, face: a.face }, className: 'h-trunc', label: 'Show ' + a.name + '’s card',
            children: jsx('span', { className: 'h-trunc h-namelink', children: a.name }) }),
          a.impostor && jsx(NotVerified, { name: a.name })
        ] }),
        jsx('div', { className: 'h-statepill', children: buildLabel(a, p.you ? 'you' : p.name) || (STATE_LABEL[stateWord(a.state)] + ' · ' + (p.you ? 'your agent' : p.name + "'s agent")) })
      ] }),
      a.budget && a.budget.limit ? jsx(BudgetRing, { budget: a.budget, size: 14, stroke: 2 }) : null
    ] }, a.pk))
  ] })
}

// A member using a name someone else in the room already holds: same rule as the message badge.
function NotVerified(props) {
  return jsx(K.Tip, { label: 'Someone else in this room already uses the name “' + props.name + '”. This is a different key.',
    children: jsxs('span', { className: 'h-impostor h-tiny', role: 'note', children: [jsx(K.Icon, { name: 'shield', size: 11 }), 'not verified'] }) })
}

function MyAgentCard(props) {
  const snap = props.snap
  const a = snap.me.agent
  const w = stateWord(a.state)
  return jsxs('div', { className: 'h-mine', children: [
    jsxs('div', { className: 'h-row', children: [
      jsx(ProfileButton, { who: { kind: 'agent', pk: a.pk, name: a.name, face: a.face }, label: 'Show your agent’s card',
        children: jsx(Face, { face: a.face, pk: a.pk, state: a.state, size: 40, name: a.name }) }),
      jsxs('div', { className: 'h-grow', children: [
        jsx('div', { style: { fontWeight: 600 }, children: a.name || 'Your agent' }),
        jsx('div', { className: 'h-faint h-small', children: STATE_LABEL[w] + (a.note ? ' · ' + a.note : '') })
      ] })
    ] }),
    jsxs('div', { className: 'h-row', children: [
      jsx(BudgetRing, { budget: snap.budget, size: 30, stroke: 3, children: Math.round((snap.budget.pct || 0) * 100) }),
      jsxs('div', { className: 'h-grow h-small', children: [
        jsx('div', { children: fmtTokens(snap.budget.used) + ' / ' + fmtTokens(snap.budget.limit) }),
        jsx('div', { className: 'h-faint', children: snap.budget.pct >= 1 ? 'resting until tomorrow' : 'tokens today' })
      ] })
    ] })
  ] })
}
