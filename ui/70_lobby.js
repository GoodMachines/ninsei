// ---------------------------------------------------------------------------------------------
// Lobby: your interest card (previewed exactly before it is published), then public rooms and
// people sorted by how many interests you share.
// ---------------------------------------------------------------------------------------------

// The engine already sends rooms in this order; sorting again keeps an older engine's list sensible.
function byActivity(a, b) {
  return (b.live ? 1 : 0) - (a.live ? 1 : 0) || (b.overlap || []).length - (a.overlap || []).length ||
    (b.talkers || 0) - (a.talkers || 0) || (b.msgs || 0) - (a.msgs || 0) || (b.at || 0) - (a.at || 0)
}

// Open a room you're in: pick it and switch to the room view (the Lobby and Welcome stay up until the view changes).
function openRoom(store, id) {
  store.setRoom(id)
  nav().set('room')
}

// After setup and whenever no room is open: the rooms most worth joining for you right now.
function picksFor(snap) {
  return lobbyRooms(snap).filter(r => !r.joined && (r.live || (r.overlap || []).length)).slice(0, 3)
}

// The Lobby's rooms with "joined" taken from the rooms you're in now, not from when the Lobby was last fetched.
function lobbyRooms(snap) {
  const mine = new Set((snap.rooms || []).map(r => r.id))
  return ((snap.lobby || {}).rooms || []).map(r => Object.assign({}, r, { joined: mine.has(r.id) })).sort(byActivity)
}

function Lobby(props) {
  const { store, snap } = props
  const lobby = snap.lobby || { rooms: [], people: [], at: 0 }
  const [busy, setBusy] = useState(false)
  const [joining, setJoining] = useState('')
  const asked = useRef(false)

  const refresh = async () => {
    setBusy(true)
    try { await store.post('/lobby/refresh', {}) } catch (_) { /* toasted */ }
    setBusy(false)
  }
  // first visit with an empty lobby: look around once by ourselves
  useEffect(() => { if (!asked.current && !lobby.at) { asked.current = true; refresh() } }, [])

  const join = async r => {
    setJoining(r.id)
    try { await store.post('/rooms/join', { room: r.id }, 'Joined ' + r.name); openRoom(store, r.id) } catch (_) { /* toasted */ }
    setJoining('')
  }

  const byOverlap = (a, b) => (b.overlap || []).length - (a.overlap || []).length || (b.at || 0) - (a.at || 0)
  const rooms = lobbyRooms(snap)
  const people = (lobby.people || []).slice().sort(byOverlap)

  return jsx('div', { className: 'h-scroll', children: jsxs('div', { className: 'h-pane', children: [
    jsxs('div', { className: 'h-row', children: [
      jsxs('div', { className: 'h-grow', children: [
        jsx('h1', { children: 'Lobby' }),
        jsx('div', { className: 'h-muted', children: 'Public rooms and people on Ninsei. Rooms where people are talking come first, then the closest matches.' })
      ] }),
      jsx(K.Button, { variant: 'secondary', size: 'sm', disabled: busy, onClick: refresh, children: jsxs(Fragment, { children: [
        jsx(K.Icon, { name: 'refresh', size: 13, spinning: busy }), busy ? 'Looking…' : 'Refresh'] }) })
    ] }),
    jsx(CardSection, { store, snap }),
    jsxs('section', { className: 'h-col', style: { gap: 10 }, children: [
      jsxs('div', { className: 'h-row', children: [
        jsx('h3', { className: 'h-grow', children: 'Rooms' }),
        lobby.at ? jsx('span', { className: 'h-faint h-small', children: 'updated ' + fmtAgo(lobby.at) }) : null
      ] }),
      rooms.length === 0 ? jsx('div', { className: 'h-faint', children: busy ? 'Asking the relays…' : 'No public rooms found yet. Start one and it shows up here for others.' })
        : jsx('div', { className: 'h-list', children: rooms.map(r => jsx(LobbyRoom, { r, joining: joining === r.id, onJoin: () => join(r), onOpen: () => openRoom(store, r.id) }, r.id)) })
    ] }),
    jsxs('section', { className: 'h-col', style: { gap: 10 }, children: [
      jsx('h3', { children: 'People' }),
      people.length === 0 ? jsx('div', { className: 'h-faint', children: busy ? 'Asking the relays…' : 'Nobody has published a card that matches yet.' })
        : jsx('div', { className: 'h-list', children: people.map(p => jsx(LobbyPerson, { p }, p.pk)) })
    ] })
  ] }) })
}

function LobbyRoom(props) {
  const r = props.r
  const ref = useEnter(false)
  const n = (r.overlap || []).length
  return jsxs('div', { className: 'h-item', ref, children: [
    jsx('span', { className: 'h-hash', style: { fontSize: 18, lineHeight: '22px' }, children: '#' }),
    jsxs('div', { className: 'h-grow h-col', style: { gap: 4 }, children: [
      jsxs('div', { className: 'h-row', children: [
        jsx('b', { className: 'h-trunc', children: r.name }),
        n > 0 && jsx('span', { className: 'h-faint h-tiny', children: n + ' shared interest' + (n === 1 ? '' : 's') })
      ] }),
      r.about && jsx('div', { className: 'h-muted h-small', children: r.about }),
      jsx(RoomActivity, { r }),
      jsx(Chips, { items: r.interests, hits: r.overlap })
    ] }),
    r.joined ? jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: props.onOpen, children: 'Open' })
      : jsx(K.Button, { variant: 'secondary', size: 'sm', disabled: props.joining, onClick: props.onJoin, children: props.joining ? 'Joining…' : 'Join' })
  ] })
}

// How alive a room is, from the last day of messages: rooms where people are talking sort first.
function RoomActivity(props) {
  const r = props.r
  let text
  if (r.live) text = 'active now' + (r.talkers > 1 ? ' · ' + r.talkers + ' people talking today' : '')
  else if (r.msgs > 0) text = r.msgs + ' message' + (r.msgs === 1 ? '' : 's') + ' today, last ' + fmtAgo(r.last)
  else text = 'quiet today'
  return jsxs('div', { className: 'h-row h-small', style: { gap: 6 }, children: [
    jsx('span', { className: 'h-presence', 'data-on': !!r.live, 'aria-hidden': true }),
    jsx('span', { className: r.live ? '' : 'h-faint', children: text }),
    r.commons && jsx('span', { className: 'h-faint', children: '· everyone starts here' })
  ] })
}

function LobbyPerson(props) {
  const p = props.p
  return jsxs('div', { className: 'h-item', children: [
    jsx(Initial, { name: p.name }),
    jsxs('div', { className: 'h-grow h-col', style: { gap: 4 }, children: [
      jsxs('div', { className: 'h-row', children: [
        jsx('b', { className: 'h-trunc', children: p.name }),
        p.at ? jsx('span', { className: 'h-faint h-tiny', children: fmtAgo(p.at) }) : null
      ] }),
      p.line && jsx('div', { className: 'h-muted h-small', children: p.line }),
      jsx(Chips, { items: p.interests, hits: p.overlap })
    ] }),
    p.agent && jsxs('div', { className: 'h-row', style: { gap: 6 }, title: p.agent + ' is ' + p.name + "'s agent", children: [
      jsx(Face, { face: p.face, pk: p.pk, state: 'activity: idle', size: 24, name: p.agent }),
      jsx('span', { className: 'h-small h-muted', children: p.agent })
    ] })
  ] })
}

// What gets published, shown before it is: the rendered card and the exact JSON.
function CardSection(props) {
  const { store, snap } = props
  const [preview, setPreview] = useState(null)
  const [raw, setRaw] = useState(false)
  const [busy, setBusy] = useState(false)
  const s = snap.settings
  const key = JSON.stringify([s.display_name, s.line, s.interests, s.agent_name, s.face])
  useEffect(() => { P.rest('/card/preview').then(setPreview, () => setPreview(null)) }, [key])
  const publish = async () => {
    setBusy(true)
    try {
      const out = await store.post('/card/publish', {})
      P.toast('info', 'Card published to ' + out.accepted + ' of ' + out.relays + ' relays')
    } catch (_) { /* toasted */ }
    setBusy(false)
  }
  const published = s.card_published_at > 0
  const noInterests = !(s.interests || []).length
  const c = preview || { name: s.display_name, line: s.line, interests: s.interests, agent: { name: s.agent_name, face: s.face, pk: snap.me.agent.pk } }
  return jsxs('section', { className: 'h-col', style: { gap: 10 }, children: [
    jsxs('div', { className: 'h-row', children: [
      jsx('h3', { className: 'h-grow', children: 'Your interest card' }),
      jsx('span', { className: 'h-faint h-small', children: published ? 'Published ' + fmtAgo(s.card_published_at) : 'Not published' })
    ] }),
    jsxs('div', { className: 'h-cardpreview', children: [
      jsx(Face, { face: c.agent && c.agent.face, pk: c.agent && c.agent.pk, state: busy ? 'activity: working' : 'activity: idle', size: 44, name: c.agent && c.agent.name }),
      jsxs('div', { className: 'h-grow h-col', style: { gap: 4 }, children: [
        jsxs('div', { children: [jsx('b', { children: c.name || 'No name yet' }), c.agent && c.agent.name ? jsx('span', { className: 'h-faint', children: ' with ' + c.agent.name }) : null] }),
        c.line ? jsx('div', { className: 'h-muted h-small', children: c.line }) : jsx('div', { className: 'h-faint h-small', children: 'No line about you yet (Settings)' }),
        jsx(Chips, { items: c.interests || [] })
      ] })
    ] }),
    raw && jsx('pre', { className: 'h-pre', children: JSON.stringify(c, null, 2) }),
    jsx(Notice, { icon: 'globe', children: 'Publishing puts exactly this on public Nostr relays so others can find you. Anyone can read it. Publish again after you change it.' }),
    jsxs('div', { className: 'h-actions', children: [
      jsx(K.Button, { variant: 'primary', size: 'sm', disabled: busy || noInterests, 'aria-describedby': noInterests ? 'h-card-hint' : undefined, onClick: publish, children: busy ? 'Publishing…' : published ? 'Publish again' : 'Publish my card' }),
      jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: () => setRaw(!raw), children: raw ? 'Hide exact data' : 'Show exact data' })
    ] }),
    noInterests && jsxs('div', { className: 'h-faint h-small h-row', id: 'h-card-hint', style: { gap: 6, flexWrap: 'wrap' }, children: [
      'Add at least one interest to publish your card. People find you through them.',
      jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: () => { if (P.kind === 'dashboard') nav().set('settings'); else P.openSettings() }, children: 'Open Settings' })
    ] })
  ] })
}
