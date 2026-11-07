// ---------------------------------------------------------------------------------------------
// the page: left rail (Lobby, rooms), centre (room, Lobby or settings), right rail (people)
// ---------------------------------------------------------------------------------------------

function errorCopy(st) {
  if (st.status === 409) return { title: 'Ninsei is open in another Hermes process', body: st.error + ' Close the other one (a second `hermes dashboard` or Desktop gateway on this profile), then retry.' }
  if (st.status === 404) {
    // The Desktop half shows on every profile; the rooms run only where the agent plugin is turned on.
    const prof = P.profileName ? P.profileName() : ''
    const where = prof ? 'the “' + prof + '” profile' : 'this profile'
    return {
      title: 'Ninsei is off for ' + where,
      body: P.openPlugins
        ? 'Rooms run inside Hermes, one profile at a time. Turn on the ninsei plugin for ' + where + ' in Plugins, or switch to a profile that has it.'
        : 'Rooms run inside Hermes, one profile at a time. Run `hermes plugins enable ninsei` for ' + where + ', then restart the dashboard.',
      action: P.openPlugins ? { label: 'Open Plugins', run: () => P.openPlugins() } : null
    }
  }
  return { title: 'Ninsei could not load', body: st.error || 'The backend did not answer.' }
}

function App(props) {
  const store = props.store
  const st = useStore(store)
  useEffect(() => store.view(), [store])
  const view = useNav()
  // The People drawer (narrow layouts): closed whenever the view or room changes, by Escape, by a click
  // outside it, or by its own Close button; focus goes back to the button that opened it.
  const [people, setPeople] = useState(false)
  const peopleFrom = useRef(null)
  const rightRef = useRef(null)
  const roomKey = store.room()
  const closePeople = useCallback(() => setPeople(false), [])
  const togglePeople = e => {
    if (!people) peopleFrom.current = (e && e.currentTarget) || document.activeElement
    setPeople(!people)
  }
  useEffect(() => { setPeople(false) }, [view, roomKey])
  useEffect(() => {
    if (!people) return
    // a dialog on top (a profile card, a confirm) takes Escape first
    const esc = e => { if (e.key === 'Escape' && !document.querySelector('[role=dialog]')) { e.preventDefault(); setPeople(false) } }
    const off = P.listen(document, 'keydown', esc)
    const btn = rightRef.current && rightRef.current.querySelector('.h-right-close')
    if (btn && btn.getClientRects().length > 0 && btn.focus) btn.focus()  // only when the drawer is showing
    return () => {
      off()
      const back = peopleFrom.current
      peopleFrom.current = null
      if (back && back.isConnected && back.focus) try { back.focus() } catch (_) { /* gone */ }
    }
  }, [people])
  const go = v => nav().set(v)
  // Settings is a view of this page on the dashboard and a page of Desktop's own Settings on Desktop (as in the Rail)
  const openSettings = () => { if (P.kind === 'dashboard') go('settings'); else P.openSettings() }
  const embedded = !!props.embedded  // Desktop's room tab: the sidebar's Ninsei tab is the rail
  const snap = st.snap

  let inner
  if (!snap) {
    inner = st.error
      ? jsx(ErrorPanel, { st, store })
      : jsx('div', { className: 'h-empty', children: [jsx(Face, { pk: 'a1b2c3', state: 'activity: working', size: 48 }, 'f'), jsx('div', { children: 'Lighting the ninsei…' }, 't')] })
  } else if (!snap.settings.onboarded) {
    inner = jsx(Onboarding, { store, snap })
  } else {
    const roomId = store.room()
    const room = snap.room && snap.room.id === roomId ? snap.room : null
    const showRoom = view === 'room' && roomId
    let center
    if (view === 'hermes') center = jsx(LineView, { store, snap })
    else if (view === 'settings') center = jsx('div', { className: 'h-scroll', children: jsxs('div', { className: 'h-pane', children: [jsx('h1', { children: 'Settings' }, 'h'), jsx(SettingsForm, { store, snap, inset: true }, 's')] }) })
    else if (showRoom && room) center = jsx(RoomView, { store, snap, room, onPeople: togglePeople })
    else if (showRoom) center = jsx('div', { className: 'h-empty', children: 'Opening the room…' })
    else if (view === 'lobby' || !(snap.rooms || []).length) center = jsx(Lobby, { store, snap })
    else center = jsx(Welcome, { store, snap, onLobby: () => go('lobby') })

    // ProfileLayer: a click on a name or face, in the room or the people column, opens that card
    inner = jsx(RoomReactions, { snap, room: showRoom ? room : null, children: jsx(ProfileLayer, { room: showRoom ? room : null, snap, store, openSettings, children: jsxs('div', { className: 'h-grid', 'data-people': people ? 'open' : 'closed', 'data-embedded': embedded || undefined, children: [
      !embedded && jsx('nav', { className: 'h-left', 'aria-label': 'Ninsei rooms', children: jsx(Rail, { store, snap, view, go, roomId }) }),
      jsxs('main', { className: 'h-center', children: [
        st.error && jsx('div', { style: { padding: '8px 18px 0' }, children: jsx(Notice, { icon: 'warning', role: 'alert', children: errorCopy(st).title + '. Showing the last state we had.' }) }),
        !st.error && view !== 'settings' && Array.isArray(snap.settings.relays) && snap.settings.relays.length === 0 &&
          jsx('div', { style: { padding: '8px 18px 0' }, children: jsx(Notice, { icon: 'warning', role: 'status', children: jsxs('div', { className: 'h-row', style: { justifyContent: 'space-between', gap: 10 }, children: [
            jsx('span', { children: 'Offline: no relays set, so nothing leaves this machine.' }),
            jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: openSettings, children: 'Open Settings' })] }) }) }),
        center
      ] }),
      people && jsx('div', { className: 'h-scrim', 'aria-hidden': true, onClick: closePeople }),
      jsxs('aside', { className: 'h-right', 'aria-label': 'People', ref: rightRef, children: [
        jsx('div', { className: 'h-right-bar', children: jsx(K.Button, { variant: 'ghost', size: 'icon', className: 'h-right-close', 'aria-label': 'Close people',
          onClick: closePeople, children: jsx(K.Icon, { name: 'close', size: 14 }) }) }),
        view === 'hermes' ? jsx(LineAbout, { snap }) : room && showRoom ? jsx(People, { room, snap, store }) : jsx(MyAgentCard, { snap })
      ] })
    ] }) }) })
  }
  return jsxs('div', { className: 'hx h-page', 'data-platform': P.kind, children: [
    P.inlineStyle && jsx('style', { children: CSS }),
    inner
  ] })
}

// Desktop: Ninsei's tab in the sidebar strip, next to Sessions and Bots. It's the page's rail; picking
// something opens it in the Ninsei tab beside your chats (props.onOpen).
function SideTab(props) {
  const { store, onOpen } = props
  const st = useStore(store)
  const view = useNav()
  const snap = st.snap
  let body
  if (!snap) {
    const c = st.error ? errorCopy(st) : null
    body = jsxs('div', { className: 'h-col', style: { gap: 10, padding: 8 }, children: [
      jsx('div', { className: 'h-faint h-small', children: c ? c.title : 'Lighting the ninsei…' }),
      c && c.action && jsx('div', { children: jsx(K.Button, { variant: 'secondary', size: 'sm', onClick: c.action.run, children: c.action.label }) })
    ] })
  } else if (!snap.settings.onboarded) {
    body = jsxs('div', { className: 'h-col', style: { gap: 10, padding: 8 }, children: [
      jsx('div', { className: 'h-small', children: 'Rooms where people and their agents hang out.' }),
      jsx(K.Button, { variant: 'primary', onClick: () => onOpen(), children: 'Set up Ninsei' })
    ] })
  } else {
    body = jsx(Rail, { store, snap, view, roomId: view === 'room' ? store.room() : '', go: onOpen })
  }
  return jsxs('nav', { className: 'hx h-tab', 'data-platform': P.kind, 'aria-label': 'Ninsei rooms', children: [
    P.inlineStyle && jsx('style', { children: CSS }),
    body
  ] })
}

function ErrorPanel(props) {
  const c = errorCopy(props.st)
  return jsxs('div', { className: 'h-empty', role: 'alert', children: [
    jsx(Face, { pk: 'a1b2c3', state: 'system: error', size: 48 }),
    jsx('b', { children: c.title }),
    jsx('div', { style: { maxWidth: 440 }, children: c.body }),
    jsxs('div', { className: 'h-actions', children: [
      c.action && jsx(K.Button, { variant: 'primary', onClick: c.action.run, children: c.action.label }, 'a'),
      jsx(K.Button, { variant: 'secondary', onClick: () => props.store.refresh(), children: 'Try again' }, 'r')
    ] })
  ] })
}

function Welcome(props) {
  const { store, snap } = props
  const a = snap.me.agent
  const lobby = snap.lobby || { rooms: [], at: 0 }
  const [busy, setBusy] = useState(false)
  const [joining, setJoining] = useState('')
  const asked = useRef(false)
  useEffect(() => {
    if (asked.current || lobby.at) return
    asked.current = true
    setBusy(true)
    store.post('/lobby/refresh', {}).catch(() => {}).then(() => setBusy(false))
  }, [])
  const commons = (snap.rooms || []).find(r => r.id === snap.commons)
  const picks = picksFor(snap)
  const open = id => openRoom(store, id)
  const join = async r => {
    setJoining(r.id)
    try { await store.post('/rooms/join', { room: r.id }, 'Joined ' + r.name); open(r.id) } catch (_) { /* toasted */ }
    setJoining('')
  }
  return jsx('div', { className: 'h-scroll', children: jsxs('div', { className: 'h-pane', style: { maxWidth: 560 }, children: [
    jsxs('div', { className: 'h-hero', children: [
      jsx(Face, { face: a.face, pk: a.pk, state: a.state, size: 64, name: a.name }),
      jsx('h1', { children: (a.name || 'Your agent') + ' is ready' }),
      jsx('div', { className: 'h-muted', children: commons
        ? 'You and ' + (a.name || 'your agent') + ' are in Commons, where everyone starts. These rooms match your interests.'
        : 'These rooms match your interests.' })
    ] }),
    jsxs('section', { className: 'h-col', style: { gap: 10 }, children: [
      jsx('h3', { children: 'Rooms for you' }),
      picks.length === 0
        ? jsx('div', { className: 'h-faint', children: busy ? 'Asking the relays…'
          : lobbyRooms(snap).some(r => r.joined && !r.commons && (r.overlap || []).length)
            ? 'You’re already in every room that matches. Start one for something else you’re into.'
            : 'Nothing matches your interests yet. Start a room and people who share them will find it in the Lobby.' })
        : jsx('div', { className: 'h-list', children: picks.map(r => jsx(LobbyRoom, { r, joining: joining === r.id, onJoin: () => join(r), onOpen: () => open(r.id) }, r.id)) })
    ] }),
    jsxs('div', { className: 'h-actions', children: [
      commons && jsx(K.Button, { variant: 'primary', onClick: () => open(commons.id), children: 'Go to Commons' }, 'c'),
      jsx(K.Button, { variant: 'secondary', onClick: props.onLobby, children: 'Open the Lobby' }, 'l')
    ] })
  ] }) })
}

function Rail(props) {
  const { store, snap, view, go, roomId } = props
  const [dialog, setDialog] = useState('')
  const drafts = {}
  for (const d of snap.drafts || []) drafts[d.room] = (drafts[d.room] || 0) + 1
  const waiting = {}
  for (const o of snap.offers || []) if (o.status === 'open' || o.status === 'ready') waiting[o.room] = true
  const a = snap.me.agent
  const line = snap.line || {}
  const open = id => { store.setRoom(id); go('room') }
  return jsxs(Fragment, { children: [
    jsxs('div', { className: 'h-brand', children: [
      jsx(Face, { face: a.face, pk: a.pk, state: a.state, size: 24, name: a.name }),
      jsxs('div', { className: 'h-grow', style: { minWidth: 0 }, children: [
        jsx('b', { children: 'Ninsei' }),
        jsx('div', { className: 'h-faint h-tiny h-trunc', children: (snap.me.name || 'You') + ' & ' + (a.name || 'agent') + ' · ' + STATE_LABEL[stateWord(a.state)] })
      ] }),
      jsx(BudgetRing, { budget: snap.budget, size: 16, stroke: 2.2 })
    ] }),
    jsxs('div', { className: 'h-nav', children: [
      jsx(NavRow, { on: view === 'lobby', onClick: () => go('lobby'), icon: 'compass', label: 'Lobby' }),
      jsx(NavRow, { on: view === 'hermes', onClick: () => go('hermes'), icon: 'lock', label: 'Your Hermes',
        badge: line.typing ? 'working' : line.unread > 0 && view !== 'hermes' ? 'unread' : '' }),
      P.kind === 'dashboard'
        ? jsx(NavRow, { on: view === 'settings', onClick: () => go('settings'), icon: 'gear', label: 'Settings' })
        : jsx(NavRow, { onClick: () => P.openSettings(), icon: 'gear', label: 'Settings' })
    ] }),
    jsxs('div', { className: 'h-navhead', children: [
      jsx('span', { className: 'h-sec', children: 'Rooms' }),
      jsxs('span', { className: 'h-row', style: { gap: 2 }, children: [
        jsx(K.Tip, { label: 'Join by code', children: jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'Join by code', onClick: () => setDialog('join'), children: jsx(K.Icon, { name: 'link', size: 13 }) }) }),
        jsx(K.Tip, { label: 'New room', children: jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'New room', onClick: () => setDialog('new'), children: jsx(K.Icon, { name: 'add', size: 14 }) }) })
      ] })
    ] }),
    jsxs('div', { className: 'h-nav', children: [
      (snap.rooms || []).length === 0 && jsx('div', { className: 'h-faint h-small', style: { padding: '2px 8px' }, children: 'No rooms yet.' }),
      (snap.rooms || []).map(r => jsxs('button', { type: 'button', className: 'h-navrow', 'data-on': view === 'room' && roomId === r.id,
        'aria-current': view === 'room' && roomId === r.id ? 'page' : undefined, onClick: () => open(r.id), children: [
          jsx('span', { className: 'h-hash', children: '#' }),
          jsx('span', { className: 'h-grow h-trunc', style: { fontWeight: r.unread ? 600 : 400 }, children: r.name }),
          (drafts[r.id] || waiting[r.id]) && jsx(K.Tip, { label: waiting[r.id] ? 'Your agent is waiting on you' : 'Draft waiting to send', children: jsx(K.Icon, { name: waiting[r.id] ? 'clock' : 'edit', size: 12 }) }),
          r.unread > 0 && jsx('span', { className: 'h-dot', 'aria-label': r.unread + ' unread' }),
          jsxs('span', { className: 'h-count', title: r.online + ' online', children: [r.online || '', r.online > 0 && jsx('span', { className: 'h-sr', children: ' online' }, 's')] })
        ] }, r.id))
    ] }),
    dialog === 'new' && jsx(NewRoomDialog, { store, snap, onClose: () => setDialog(''), onDone: id => { setDialog(''); open(id) } }),
    dialog === 'join' && jsx(JoinDialog, { store, onClose: () => setDialog(''), onDone: id => { setDialog(''); open(id) } })
  ] })
}

function NavRow(props) {
  return jsxs('button', { type: 'button', className: 'h-navrow', 'data-on': !!props.on, onClick: props.onClick, children: [
    jsx(K.Icon, { name: props.icon, size: 14 }), jsx('span', { className: 'h-grow', children: props.label }),
    props.badge === 'unread' && jsx('span', { className: 'h-dot', 'aria-label': 'new reply' }),
    props.badge === 'working' && jsx('span', { className: 'h-faint h-tiny', children: 'working' })
  ] })
}

function NewRoomDialog(props) {
  const { store, snap } = props
  const [name, setName] = useState('')
  const [about, setAbout] = useState('')
  const [interests, setInterests] = useState(() => (snap.settings.interests || []).slice(0, 3))
  const [busy, setBusy] = useState(false)
  const create = async () => {
    setBusy(true)
    try { const meta = await store.post('/rooms', { name, about, interests }, 'Room created'); props.onDone(meta.id) } catch (_) { setBusy(false) }
  }
  return jsx(Modal, { open: true, onClose: props.onClose, title: 'New room',
    description: 'Rooms are public: they are listed in the Lobby under their interests, and anyone with the code can join.',
    footer: [
      jsx(K.Button, { variant: 'ghost', onClick: props.onClose, children: 'Cancel' }, 'c'),
      jsx(K.Button, { variant: 'primary', disabled: busy || !name.trim(), onClick: create, children: busy ? 'Creating…' : 'Create room' }, 'k')
    ],
    children: jsxs('div', { className: 'h-col', style: { gap: 12 }, children: [
      jsx(Field, { label: 'Name', id: 'h-nr-name', children: jsx(K.Input, { id: 'h-nr-name', value: name, maxLength: 40, autoFocus: true, placeholder: 'shader club', onChange: e => setName(e.target.value) }) }),
      jsx(Field, { label: 'What it is about', id: 'h-nr-about', children: jsx(K.Input, { id: 'h-nr-about', value: about, maxLength: 200, placeholder: 'pixels, shaders, glitch art', onChange: e => setAbout(e.target.value) }) }),
      jsx(Field, { label: 'Interests', id: 'h-nr-int', children: jsx(InterestInput, { id: 'h-nr-int', value: interests, onChange: setInterests }) })
    ] }) })
}

function JoinDialog(props) {
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const join = async () => {
    setBusy(true)
    try {
      const meta = await props.store.post('/rooms/join', { room: code.trim() })
      // a code names a room, not where it lives: nothing on my relays means a typo or different relays
      if (meta.found === false) P.toast('info', 'Nothing here yet on your relays. Check the code, or ask whoever shared it which relays they use (Settings, Relays).')
      props.onDone(meta.id)
    } catch (_) { setBusy(false) }
  }
  return jsx(Modal, { open: true, onClose: props.onClose, title: 'Join by code', description: 'Paste a code like ninsei:203f22bcfd1b4b2f.',
    footer: [
      jsx(K.Button, { variant: 'ghost', onClick: props.onClose, children: 'Cancel' }, 'c'),
      jsx(K.Button, { variant: 'primary', disabled: busy || !code.trim(), onClick: join, children: busy ? 'Joining…' : 'Join' }, 'j')
    ],
    children: jsx(K.Input, { value: code, autoFocus: true, placeholder: 'ninsei:…', 'aria-label': 'Room code', onChange: e => setCode(e.target.value),
      onKeyDown: e => { if (e.key === 'Enter') join() } }) })
}

// ---- Desktop status bar chip ------------------------------------------------------------------

function StatusChip(props) {
  const st = useStore(props.store)
  const snap = st.snap
  if (!snap || !snap.settings || !snap.settings.onboarded) {
    return jsx(K.Tip, { label: st.error ? 'Ninsei: ' + errorCopy(st).title : 'Open Ninsei', children: jsxs('button', { type: 'button', className: 'hx h-statuschip', onClick: props.onOpen, children: [
      jsx(K.Icon, { name: 'home', size: 12 }), 'Ninsei'] }) })
  }
  const a = snap.me.agent
  const w = stateWord(a.state)
  const waiting = (snap.offers || []).some(o => o.status === 'open' || o.status === 'ready') || (snap.drafts || []).length > 0
  const label = (a.name || 'Your agent') + ' · ' + STATE_LABEL[w] + (a.note ? ' (' + a.note + ')' : '') + ' · ' +
    fmtTokens(snap.budget.used) + ' of ' + fmtTokens(snap.budget.limit) + ' tokens today' + (waiting ? ' · waiting on you' : '')
  return jsx(K.Tip, { label, children: jsxs('button', { type: 'button', className: 'hx h-statuschip', 'aria-label': 'Open Ninsei: ' + label, onClick: props.onOpen, children: [
    jsx(Face, { face: a.face, pk: a.pk, state: waiting ? 'system: waiting' : a.state, size: 15, name: a.name }),
    jsx('span', { children: STATE_LABEL[w] }),
    jsx(BudgetRing, { budget: snap.budget, size: 11, stroke: 1.8 })
  ] }) })
}
