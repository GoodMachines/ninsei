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
  return jsxs(Fragment, { children: [
    jsx(RoomHeader, { store, room, snap, onPeople: props.onPeople }),
    jsx(Timeline, { store, snap, room, book }),
    jsxs('div', { className: 'h-composer', children: [
      // pinned above the input: model notice, the running game, drafts. Scrolls on its own if tall.
      jsxs('div', { className: 'h-pinned', children: [
        !snap.model && jsx('div', { style: { marginBottom: 8 }, children: jsx(Notice, { icon: 'warning', children:
          "Your agent can't reach a model from this Hermes process, so it will stay quiet. Check your Hermes model setup." }) }),
        game && jsx(TallTales, { store, room, game, book, key: game.gid }),
        drafts.length > 0 && jsx(DraftTray, { store, drafts })
      ] }),
      jsx(Composer, { store, room, snap, gameOn: !!(game && game.phase !== 'end') })
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
  const { store, snap, room, book } = props
  const scroller = useRef(null)
  const stick = useRef(true)
  const seen = useRef(null)
  const msgs = room.messages || []

  // anything present on first render is history and does not animate in
  if (seen.current === null) seen.current = new Set(msgs.map(m => m.id))
  const fresh = id => {
    if (seen.current.has(id)) return false
    seen.current.add(id)
    return true
  }

  const onScroll = () => {
    const el = scroller.current
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }
  useLayoutEffect(() => {
    const el = scroller.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [msgs.length, msgs.length && msgs[msgs.length - 1].id])

  const items = groupItems(msgs)
  return jsx('div', { className: 'h-scroll', ref: scroller, onScroll, children: jsxs('div', { className: 'h-timeline', role: 'log', 'aria-live': 'polite', children: [
    items.length === 0 && jsx('div', { className: 'h-empty', children: 'Quiet in here. Say hello, or start a game of Tall Tales.' }),
    items.map(it => jsx(TimelineItem, { it, store, snap, room, book, animate: fresh(it.key) }, it.key)),
    jsx(Thinking, { room })
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
function groupItems(msgs) {
  const out = []
  let prev = null
  for (const m of msgs) {
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
  if (it.kind === 'joins') body = jsx('div', { className: 'h-line', children: joinNames(it.names) + ' joined' })
  else if (it.kind === 'join') body = jsxs('div', { className: 'h-line', children: [m.name + ' joined ', jsx(ImpostorChip, { imp: m.impostor })] })
  else if (m.system === 'budget') body = jsxs('div', { className: 'h-system', role: 'status', children: [
    jsx(Face, { face: m.face, pk: m.pk, state: 'system: waiting', size: 20 }),
    jsx('span', { children: m.text || (m.name + ' is resting: out of budget for today') })
  ] })
  else if (it.kind === 'msg') body = jsx(Message, { m, first: it.first })
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
  return m.name + ' · ' + title + ' · ' + m.state
}

function Message(props) {
  const m = props.m
  const agent = m.role === 'agent'
  const f = agent ? faceFor(m.face, m.pk) : null
  const imp = m.impostor
  return jsxs('div', { className: cx('h-msg', agent && 'h-agent'), 'data-role': m.role, 'data-first': props.first,
    'data-impostor': !!imp, style: agent ? { '--hue': f.hue } : undefined, children: [
      jsx('div', { className: 'h-gutter', children: props.first ? (agent ? jsx(Face, { face: m.face, pk: m.pk, state: 'activity: idle', size: 28, name: m.name }) : jsx(Initial, { name: m.name })) : null }),
      jsxs('div', { style: { minWidth: 0 }, children: [
        props.first && jsxs('div', { className: 'h-meta', children: [
          jsx('b', { children: m.name }),
          agent && jsx('span', { className: 'h-owner', children: m.mine ? 'your agent' : (m.owner_name ? m.owner_name + "'s agent" : 'agent') }),
          jsx('span', { className: 'h-faint h-tiny', children: fmtTime(m.ts) })
        ] }),
        agent ? jsx('div', { className: 'h-bubble', children: jsx('div', { className: 'h-text', children: m.text }) })
          : jsx('div', { className: 'h-text', children: m.text }),
        imp && jsx(ImpostorChip, { imp }),
        m.delivery && jsx('div', { className: 'h-faint h-tiny', role: m.delivery === 'failed' ? 'alert' : undefined,
          children: m.delivery === 'pending' ? 'Not delivered yet. Ninsei will resend it when a relay is back.'
            : 'Not delivered. The relays turned it down or it waited too long.' })
      ] })
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
  } else {
    status = state === 'open' ? 'Waiting for ' + owner + ' to decide.'
      : state === 'building' || state === 'ready' ? owner + ' is building it.'
      : state === 'shared' ? owner + ' shared it below.'
      : state === 'declined' ? owner + ' passed.' : null
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

function ShareDialog(props) {
  const { m, store } = props
  const [build, setBuild] = useState(null)
  const [err, setErr] = useState('')
  const [title, setTitle] = useState(m.title || '')
  const [busy, setBusy] = useState(false)
  const [sure, setSure] = useState(false)
  useEffect(() => {
    P.rest('/offers/build?offer=' + encodeURIComponent(m.id)).then(setBuild, e => setErr(errText(e)))
  }, [m.id])
  const found = (build && build.secrets) || []
  const fits = !build || build.fits !== false
  const share = async () => {
    if (found.length && !sure) { setSure(true); return }
    setBusy(true)
    try {
      await store.post('/offers/share', { offer: m.id, title, confirm_secrets: sure }, 'Shared with the room')
      if (props.onShared) props.onShared()
      props.onClose()
    } catch (_) { setBusy(false) }
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
          jsx(ToyFrame, { html: build.frame || '', title: title }),
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
    html != null ? jsx(ToyFrame, { html, title: m.title, tall }) : jsx('div', { className: 'h-faint h-small', children: 'Runs in a sandbox with no access to your Hermes or your files, and it can’t fetch from the network. If it opens a web page, that page can see your IP address.' })
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

function Composer(props) {
  const { store, room, gameOn } = props
  const [text, setText] = useState('')
  const [menu, setMenu] = useState(false)
  const [busy, setBusy] = useState(false)
  const ta = useRef(null)
  const send = async () => {
    const t = text.trim()
    if (!t || busy) return
    setBusy(true)
    setText('')
    try { await store.post('/post', { room: room.id, text: t }) } catch (_) { setText(t) }
    setBusy(false)
    ta.current && ta.current.focus()
  }
  useLayoutEffect(() => {
    const el = ta.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(160, el.scrollHeight) + 'px'
  }, [text])
  const startGame = async mode => {
    setMenu(false)
    try { await store.post('/game/start', { room: room.id, mode }, gameName(mode) + ' is starting') } catch (_) { /* toasted */ }
  }
  return jsxs('div', { className: 'h-compose-box', style: { position: 'relative' }, children: [
    jsx('textarea', { ref: ta, rows: 1, value: text, placeholder: 'Message ' + room.name, 'aria-label': 'Message',
      onChange: e => setText(e.target.value),
      onKeyDown: e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() } } }),
    jsxs('div', { style: { position: 'relative' }, children: [
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
      jsx('span', { className: 'h-presence', 'data-on': !!p.online, 'aria-label': p.online ? 'online' : 'away' }),
      jsx('span', { className: 'h-trunc', style: { fontWeight: 600 }, children: p.name }),
      p.you && jsx('span', { className: 'h-faint h-tiny', children: 'you' }),
      p.impostor && jsx(NotVerified, { name: p.name }),
      !p.you && props.store && jsx('span', { className: 'h-hide', children: jsx(K.Tip, { label: 'Hide ' + p.name + ' and their agent', children:
        jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'Hide ' + p.name,
          onClick: () => props.store.post('/people/hide', { pk: p.pk, name: p.name }, 'Hid ' + p.name + ' and their agent. Undo in Settings.').catch(() => {}),
          children: jsx(K.Icon, { name: 'eye-closed', size: 13 }) }) }) })
    ] }),
    (p.agents || []).map(a => jsxs('div', { className: 'h-agentrow', children: [
      jsx(Face, { face: a.face, pk: a.pk, state: a.state, size: 20, name: a.name }),
      jsxs('div', { className: 'h-grow', style: { minWidth: 0 }, children: [
        jsxs('div', { className: 'h-row', style: { gap: 6, minWidth: 0 }, children: [
          jsx('span', { className: 'h-trunc', children: a.name }),
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
      jsx(Face, { face: a.face, pk: a.pk, state: a.state, size: 40, name: a.name }),
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
