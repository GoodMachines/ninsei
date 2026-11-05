// ---------------------------------------------------------------------------------------------
// the page: left rail (Lobby, rooms), centre (room, Lobby or settings), right rail (people)
// ---------------------------------------------------------------------------------------------

function errorCopy(st) {
  if (st.status === 409) return { title: 'Xenia is open in another Hermes process', body: st.error + ' Close the other one (a second `hermes dashboard` or Desktop gateway on this profile), then retry.' }
  if (st.status === 404) return { title: "Xenia's backend isn't loaded", body: 'Enable the xenia plugin for this profile (plugins.enabled in config.yaml) and restart Hermes so its routes mount.' }
  return { title: 'Xenia could not load', body: st.error || 'The backend did not answer.' }
}

function App(props) {
  const store = props.store
  const st = useStore(store)
  useEffect(() => store.view(), [store])
  const [view, setView] = useState(() => P.prefs.get('view', 'room'))
  const [people, setPeople] = useState(false)
  const go = v => { setView(v); P.prefs.set('view', v) }
  const snap = st.snap

  let inner
  if (!snap) {
    inner = st.error
      ? jsx(ErrorPanel, { st, store })
      : jsx('div', { className: 'h-empty', children: [jsx(Face, { pk: 'a1b2c3', state: 'activity: working', size: 48 }, 'f'), jsx('div', { children: 'Lighting the xenia…' }, 't')] })
  } else if (!snap.settings.onboarded) {
    inner = jsx(Onboarding, { store, snap })
  } else {
    const roomId = store.room()
    const room = snap.room && snap.room.id === roomId ? snap.room : null
    const showRoom = view === 'room' && roomId
    let center
    if (view === 'hermes') center = jsx(LineView, { store, snap })
    else if (view === 'settings') center = jsx('div', { className: 'h-scroll', children: jsxs('div', { className: 'h-pane', children: [jsx('h1', { children: 'Settings' }, 'h'), jsx(SettingsForm, { store, snap, inset: true }, 's')] }) })
    else if (showRoom && room) center = jsx(RoomView, { store, snap, room, onPeople: () => setPeople(!people) })
    else if (showRoom) center = jsx('div', { className: 'h-empty', children: 'Opening the room…' })
    else if (view === 'lobby' || !(snap.rooms || []).length) center = jsx(Lobby, { store, snap })
    else center = jsx(Welcome, { snap, onLobby: () => go('lobby') })

    inner = jsxs('div', { className: 'h-grid', 'data-people': people ? 'open' : 'closed', children: [
      jsx('nav', { className: 'h-left', 'aria-label': 'Xenia rooms', children: jsx(Rail, { store, snap, view, go, roomId }) }),
      jsxs('main', { className: 'h-center', children: [
        st.error && jsx('div', { style: { padding: '8px 18px 0' }, children: jsx(Notice, { icon: 'warning', role: 'alert', children: errorCopy(st).title + '. Showing the last state we had.' }) }),
        center
      ] }),
      jsx('aside', { className: 'h-right', 'aria-label': 'People', children: view === 'hermes' ? jsx(LineAbout, { snap }) : room && showRoom ? jsx(People, { room, snap }) : jsx(MyAgentCard, { snap }) })
    ] })
  }
  return jsxs('div', { className: 'hx h-page', 'data-platform': P.kind, children: [
    P.inlineStyle && jsx('style', { children: CSS }),
    inner
  ] })
}

function ErrorPanel(props) {
  const c = errorCopy(props.st)
  return jsxs('div', { className: 'h-empty', role: 'alert', children: [
    jsx(Face, { pk: 'a1b2c3', state: 'system: error', size: 48 }),
    jsx('b', { children: c.title }),
    jsx('div', { style: { maxWidth: 440 }, children: c.body }),
    jsx(K.Button, { variant: 'secondary', onClick: () => props.store.refresh(), children: 'Try again' })
  ] })
}

function Welcome(props) {
  const a = props.snap.me.agent
  return jsxs('div', { className: 'h-empty', children: [
    jsx(Face, { face: a.face, pk: a.pk, state: a.state, size: 64, name: a.name }),
    jsx('b', { children: (a.name || 'Your agent') + ' is ready' }),
    jsx('div', { children: 'Pick a room on the left, or find people in the Lobby.' }),
    jsx(K.Button, { variant: 'secondary', onClick: props.onLobby, children: 'Open the Lobby' })
  ] })
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
        jsx('b', { children: 'Xenia' }),
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
          jsx('span', { className: 'h-count', title: r.online + ' online', children: r.online || '' })
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
    try { const meta = await props.store.post('/rooms/join', { room: code.trim() }); props.onDone(meta.id) } catch (_) { setBusy(false) }
  }
  return jsx(Modal, { open: true, onClose: props.onClose, title: 'Join by code', description: 'Paste a code like xenia:203f22bcfd1b4b2f.',
    footer: [
      jsx(K.Button, { variant: 'ghost', onClick: props.onClose, children: 'Cancel' }, 'c'),
      jsx(K.Button, { variant: 'primary', disabled: busy || !code.trim(), onClick: join, children: busy ? 'Joining…' : 'Join' }, 'j')
    ],
    children: jsx(K.Input, { value: code, autoFocus: true, placeholder: 'xenia:…', 'aria-label': 'Room code', onChange: e => setCode(e.target.value),
      onKeyDown: e => { if (e.key === 'Enter') join() } }) })
}

// ---- Desktop status bar chip ------------------------------------------------------------------

function StatusChip(props) {
  const st = useStore(props.store)
  const snap = st.snap
  if (!snap || !snap.settings || !snap.settings.onboarded) {
    return jsx(K.Tip, { label: st.error ? 'Xenia: ' + errorCopy(st).title : 'Open Xenia', children: jsxs('button', { type: 'button', className: 'hx h-statuschip', onClick: props.onOpen, children: [
      jsx(K.Icon, { name: 'home', size: 12 }), 'Xenia'] }) })
  }
  const a = snap.me.agent
  const w = stateWord(a.state)
  const waiting = (snap.offers || []).some(o => o.status === 'open' || o.status === 'ready') || (snap.drafts || []).length > 0
  const label = (a.name || 'Your agent') + ' · ' + STATE_LABEL[w] + (a.note ? ' (' + a.note + ')' : '') + ' · ' +
    fmtTokens(snap.budget.used) + ' of ' + fmtTokens(snap.budget.limit) + ' tokens today' + (waiting ? ' · waiting on you' : '')
  return jsx(K.Tip, { label, children: jsxs('button', { type: 'button', className: 'hx h-statuschip', 'aria-label': 'Open Xenia: ' + label, onClick: props.onOpen, children: [
    jsx(Face, { face: a.face, pk: a.pk, state: waiting ? 'system: waiting' : a.state, size: 15, name: a.name }),
    jsx('span', { children: STATE_LABEL[w] }),
    jsx(BudgetRing, { budget: snap.budget, size: 11, stroke: 1.8 })
  ] }) })
}
