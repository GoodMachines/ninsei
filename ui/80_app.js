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
  useEffect(() => (P.viewMounted ? P.viewMounted(store) : undefined), [store])   // Desktop: presence reports while a view is up
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
  // The sidebar is a drawer on a narrow page; going anywhere closes it
  const [drawer, setDrawer] = useState(false)
  const leftRef = useRef(null)
  const go = v => { nav().set(v); setDrawer(false) }
  const dmKey = store.dm()
  useEffect(() => { setDrawer(false) }, [view, roomKey, dmKey])
  useSlide(leftRef, drawer, { x: -28, y: 0 })
  useSlide(rightRef, people, { x: 0, y: 40 })
  useEffect(() => {
    if (!drawer) return
    const esc = e => { if (e.key === 'Escape' && !e.defaultPrevented && !document.querySelector('[role=dialog]')) { e.preventDefault(); setDrawer(false) } }
    const off = P.listen(document, 'keydown', esc)
    const btn = leftRef.current && leftRef.current.querySelector('button')
    if (btn && btn.getClientRects().length > 0 && btn.focus) btn.focus()
    return off
  }, [drawer])
  // Quick switcher and a Join dialog opened by a message link
  const [switching, setSwitching] = useState(false)
  const switchingRef = useRef(false)
  switchingRef.current = switching
  const [joinFor, setJoinFor] = useState('')
  const [joinFrom, setJoinFrom] = useState(null)   // { name, room }: the Join dialog was opened by this friend's invite
  const [inviteFor, setInviteFor] = useState(null)   // { pk, name }: pick a room to invite this friend to
  const rootRef = useRef(null)
  const live = useRef(false)
  // Cmd/Ctrl+K and Cmd/Ctrl+F belong to Ninsei only while focus (or your last click) is inside it, so the host's own
  // shortcuts keep working everywhere else. F does nothing unless a room is open (then the host's find still runs).
  useEffect(() => {
    const mark = e => { const r = rootRef.current; live.current = !!(r && e.target && r.contains && r.contains(e.target)) }
    const key = e => {
      if (!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey || e.isComposing) return
      const k = String(e.key || '').toLowerCase()
      if (k !== 'k' && k !== 'f') return
      const r = rootRef.current
      const a = document.activeElement
      const idle = !a || a === document.body
      if (!r || !(idle ? live.current : r.contains(a))) return
      if (k === 'k') { e.preventDefault(); e.stopPropagation(); setSwitching(!switchingRef.current) }
      else if (HOTKEYS.search && !switchingRef.current) { e.preventDefault(); e.stopPropagation(); HOTKEYS.search() }
    }
    const offs = [P.listen(document, 'pointerdown', mark, true), P.listen(document, 'focusin', mark), P.listen(window, 'keydown', key, { capture: true })]
    return () => offs.forEach(f => f())
  }, [])
  // Settings is a view of this page on the dashboard and a page of Desktop's own Settings on Desktop (as in the Rail)
  const openSettings = () => { if (P.kind === 'dashboard') go('settings'); else P.openSettings() }
  // "Message" on a person's card: their private conversation, in the centre
  const openDm = pk => { store.setDm(pk); go('dm') }
  // a `ninsei:` link in a message: a room you are in opens (at the message, if it names one); any other opens the Join dialog
  // `code` is the link as written (it may name relays: the Join preview lists the ones you don't use yet)
  const openLink = (room, event, code, from, roomName) => {
    const joined = ((store.get().snap || {}).rooms || []).some(r => r.id === room)
    if (!joined) { setJoinFrom(from ? { name: from, room: roomName || '' } : null); setJoinFor(code || room + (event ? '#' + event : '')); return }
    if (event) wantJump(room, event)
    store.setRoom(room); go('room')
  }
  const pick = it => {
    setSwitching(false)
    if (it.kind === 'room') { store.setRoom(it.id); go('room') }
    else if (it.kind === 'dm') { store.setDm(it.id); go('dm') }
    else if (it.kind === 'requests') { store.setDm(DM_REQUESTS); go('dm') }
    else if (it.kind === 'invites') { store.setDm(DM_INVITES); go('dm') }
    else if (it.kind === 'rejoin') { setJoinFrom(null); setJoinFor(it.code) }
    else if (it.kind === 'settings') openSettings()
    else go(it.kind)
  }
  const embedded = !!props.embedded  // Desktop's room tab: the sidebar's Ninsei tab is the rail
  const snap = st.snap
  // what each person looks like, for every PersonMark below (pictures only while "Show profile pictures" is on)
  const looks = useMemo(() => ({ people: (snap && snap.people) || {}, show: !(snap && snap.settings && snap.settings.show_avatars === 'nobody'),
    me: [snap && snap.me && snap.me.pk, snap && snap.me && snap.me.agent && snap.me.agent.pk].filter(Boolean) }),
    [snap && snap.people, snap && snap.me, snap && snap.settings && snap.settings.show_avatars])

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
    const dmPk = store.dm()
    if (view === 'hermes') center = jsx(LineView, { store, snap })
    else if (view === 'dm') center = dmPk === DM_REQUESTS ? jsx(DmRequests, { store, snap }) : dmPk === DM_INVITES ? jsx(DmInvites, { store, snap, onJoin: (code, room, from, name) => openLink(room, '', code, from, name) })
      : dmPk ? jsx(DmView, { store, snap, pk: dmPk, onPeople: togglePeople, onInvite: (pk, name) => setInviteFor({ pk, name }), onJoin: (code, room, from, name) => openLink(room, '', code, from, name) }, dmPk) : jsx(DmEmpty, { snap })
    else if (view === 'settings') center = jsx('div', { className: 'h-scroll', children: jsxs('div', { className: 'h-pane', children: [jsx('h1', { children: 'Settings' }, 'h'), jsx(SettingsForm, { store, snap, inset: true }, 's')] }) })
    else if (showRoom && room) center = jsx(RoomView, { store, snap, room, onPeople: togglePeople }, room.id)
    else if (showRoom) center = jsx('div', { className: 'h-empty', children: 'Opening the room…' })
    else if (view === 'lobby' || !(snap.rooms || []).length) center = jsx(Lobby, { store, snap })
    else center = jsx(Welcome, { store, snap, onLobby: () => go('lobby') })

    // ProfileLayer: a click on a name or face, in the room or the people column, opens that card
    const down = !st.error ? relaysDown(snap) : null
    inner = jsx(LinkContext.Provider, { value: openLink, children: jsx(PeopleContext.Provider, { value: looks, children: jsx(RoomReactions, { snap, room: showRoom ? room : null, children: jsx(ProfileLayer, { room: showRoom ? room : null, snap, store, openSettings, openDm, openInvite: (pk, name) => setInviteFor({ pk, name }), children: jsxs('div', { className: 'h-grid', 'data-people': people ? 'open' : 'closed', 'data-nav': drawer ? 'open' : 'closed', 'data-embedded': embedded || undefined, children: [
      !embedded && jsx('nav', { className: 'h-left', ref: leftRef, 'aria-label': 'Ninsei rooms', children: jsx(Rail, { store, snap, view, go, roomId }) }),
      drawer && jsx('div', { className: 'h-scrim h-scrim-nav', 'aria-hidden': true, onClick: () => setDrawer(false) }),
      jsxs('main', { className: 'h-center', children: [
        !embedded && jsx(NavBar, { open: drawer, onToggle: () => setDrawer(!drawer), onSwitch: () => setSwitching(true) }),
        down && jsx(ReconnectBanner, { snap, retry: down.retry }),
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
        view === 'hermes' ? jsx(LineAbout, { snap }) : view === 'dm' ? jsx(DmAbout, {}) : room && showRoom ? jsx(People, { room, snap, store }) : jsx(MyAgentCard, { snap })
      ] })
    ] }) }) }) }) })
  }
  return jsxs('div', { className: 'hx h-page', ref: rootRef, 'data-platform': P.kind, 'data-ninsei-view': '', children: [
    P.inlineStyle && jsx('style', { children: CSS }),
    inner,
    snap && snap.settings.onboarded && switching && jsx(QuickSwitcher, { snap, onPick: pick, onClose: () => setSwitching(false) }),
    snap && snap.settings.onboarded && inviteFor && jsx(InviteToRoomDialog, { store, snap, pk: inviteFor.pk, name: inviteFor.name, onClose: () => setInviteFor(null) }),
    snap && snap.settings.onboarded && joinFor && jsx(JoinDialog, { store, initial: joinFor, from: joinFrom, onClose: () => setJoinFor(''), onDone: id => { setJoinFor(''); store.setRoom(id); go('room') } })
  ] })
}

// Desktop: Ninsei's tab in the sidebar strip, next to Sessions and Bots. It's the page's rail; picking
// something opens it in the Ninsei tab beside your chats (props.onOpen).
function SideTab(props) {
  const { store, onOpen } = props
  const st = useStore(store)
  useEffect(() => (P.viewMounted ? P.viewMounted(store) : undefined), [store])
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
  return jsxs('nav', { className: 'hx h-tab', 'data-platform': P.kind, 'data-ninsei-view': '', 'aria-label': 'Ninsei rooms', children: [
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
        jsx(Wordmark, { height: 13 }),
        jsx(MyStatus, { store, snap })
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
          jsx('span', { className: 'h-grow h-trunc', style: { fontWeight: r.unread && !r.muted ? 600 : 400, opacity: r.muted ? 0.65 : 1 }, children: r.name }),
          r.muted && jsx(K.Tip, { label: 'Muted', children: jsx('span', { className: 'h-faint', role: 'img', 'aria-label': 'Muted', children: jsx(K.Icon, { name: 'bell-slash', size: 12 }) }) }),
          (drafts[r.id] || waiting[r.id]) && jsx(K.Tip, { label: waiting[r.id] ? 'Your agent is waiting on you' : 'Draft waiting to send', children: jsx(K.Icon, { name: waiting[r.id] ? 'clock' : 'edit', size: 12 }) }),
          r.muted ? (r.unread > 0 && jsx('span', { className: 'h-dot h-dot-quiet', 'aria-label': 'unread, muted' }))
          : r.mentions > 0 ? jsx('span', { className: 'h-mentions', 'aria-label': r.mentions + (r.mentions === 1 ? ' mention' : ' mentions') + ' of you', children: '@' + (r.mentions > 9 ? '9+' : r.mentions) })
            : r.unread > 0 && jsx('span', { className: 'h-dot', 'aria-label': r.unread + ' unread' }),
          jsxs('span', { className: 'h-count', title: r.online + ' here', children: [r.online || '', r.online > 0 && jsx('span', { className: 'h-vh', children: ' here' }, 's')] })
        ] }, r.id))
    ] }),
    jsx(DmRail, { store, snap, view, go }),
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
      // the footer says why Create waits, next to it (and tied to it for screen readers)
      !name.trim() && jsx('span', { id: 'h-nr-need', className: 'h-faint h-small', children: 'Name the room to create it.' }, 'n'),
      jsx(K.Button, { variant: 'ghost', onClick: props.onClose, children: 'Cancel' }, 'c'),
      jsx(K.Button, { variant: 'primary', disabled: busy || !name.trim(), onClick: create, 'aria-describedby': name.trim() ? undefined : 'h-nr-need',
        children: busy ? 'Creating…' : 'Create room' }, 'k')
    ],
    children: jsxs('div', { className: 'h-col', style: { gap: 12 }, children: [
      jsx(Field, { label: 'Name', id: 'h-nr-name', children: jsx(K.Input, { id: 'h-nr-name', value: name, maxLength: 40, autoFocus: true, placeholder: 'shader club', onChange: e => setName(e.target.value) }) }),
      jsx(Field, { label: 'What it is about', id: 'h-nr-about', children: jsx(K.Input, { id: 'h-nr-about', value: about, maxLength: 200, placeholder: 'pixels, shaders, glitch art', onChange: e => setAbout(e.target.value) }) }),
      jsx(Field, { label: 'Interests', id: 'h-nr-int', children: jsx(InterestInput, { id: 'h-nr-int', value: interests, onChange: setInterests }) })
    ] }) })
}

// Join by code, a pasted or clicked link to a room you haven't joined, or an invite's Join. It first shows what the room is
// (the engine asks your relays; nothing joins, subscribes or publishes), then the Join button. Hosts a code names that you
// don't use yet are listed ("Also on: ...") with a button; nothing connects to them until you press it. The preview is
// advice: Join works without it (a code names a room, and the engine joins by its id).
function JoinDialog(props) {
  const [code, setCode] = useState(props.initial || '')
  const [busy, setBusy] = useState(false)
  const [pv, setPv] = useState(null)   // { code, state: 'loading' | 'done' | 'error', data }
  const [adding, setAdding] = useState(false)
  const ticket = useRef(0)
  const link = parseRoomLink(code)
  const looks = link.room.length >= 16   // a code that could name a room (the engine says what is not one)
  const look = async text => {
    const mine = ++ticket.current
    setPv({ code: text, state: 'loading', data: null })
    try {
      const data = await P.rest('/rooms/preview?code=' + encodeURIComponent(text.trim()))
      if (ticket.current === mine) setPv({ code: text, state: 'done', data })
    } catch (e) { if (ticket.current === mine) setPv({ code: text, state: 'error', data: null }) }
  }
  useEffect(() => {
    if (!looks) { ticket.current++; setPv(null); return undefined }
    return P.setTimeout(() => look(code), pv ? 450 : 0)   // the first look is at once (a link or an invite); typing waits for a pause
  }, [code])
  const shown = pv && pv.code === code ? pv : null
  const d = shown && shown.data
  const joined = !!(d && d.joined)
  const join = async () => {
    if (joined) { props.onDone(d.id); return }
    setBusy(true)
    try {
      const meta = await props.store.post('/rooms/join', { room: code.trim() })
      if (link.event) wantJump(meta.id, link.event)
      // a code names a room, not where it lives: nothing on my relays means a typo or different relays
      if (meta.found === false) P.toast('info', 'Nothing here yet on your relays. Check the code, or ask whoever shared it which relays they use (Settings, Relays).')
      props.onDone(meta.id)
    } catch (_) { setBusy(false) }
  }
  const addAndLook = async () => {
    setAdding(true)
    try {
      const out = await props.store.post('/relays/add', { code: code.trim() })
      P.toast('info', out.added.length === 1 ? 'Added ' + relayHost(out.added[0]) + ' to your relays.' : 'Added ' + out.added.length + ' relays.')
      await look(code)
    } catch (_) { /* toasted */ }
    setAdding(false)
  }
  const also = d && (d.unknown_relays || []).length > 0 ? d.unknown_relays : []
  let body = null
  if (shown && shown.state === 'loading') body = jsx('div', { className: 'h-faint h-small', role: 'status', children: 'Looking on your relays…' })
  else if (shown && shown.state === 'error') body = jsx('div', { className: 'h-faint h-small', role: 'status', children: 'Couldn’t look the room up. You can still join.' })
  else if (d && d.found) body = jsxs('div', { className: 'h-col', style: { gap: 6 }, role: 'status', 'data-preview': 'found', children: [
    jsx('b', { children: cleanSnippet(d.name, 60) }),
    d.about && jsx('div', { className: 'h-muted h-small', children: cleanSnippet(d.about, 200) }),
    (d.interests || []).length > 0 && jsx(Chips, { items: d.interests.map(t => cleanSnippet(t, 24)) }),
    jsx('div', { className: 'h-faint h-small', children: previewActivity(d) }),
    joined && jsx('div', { className: 'h-faint h-small', children: 'You are already in this room.' })
  ] })
  else if (d) body = jsx('div', { className: 'h-faint h-small', role: 'status', 'data-preview': 'none', children: d.reached === false
    ? 'Couldn’t reach your relays. Check your connection, then try again.' : 'Nothing on your relays for this code.' })
  // opened by a friend's invite (and the code not changed since): say whose
  const from = props.from && code === props.initial ? props.from : null
  return jsx(Modal, { open: true, onClose: props.onClose,
    title: from ? cleanSnippet(from.name, 32) + ' invited you to ' + (cleanSnippet(from.room, 40) || 'a room') : 'Join by code',
    description: from ? 'This is what the room looks like on your relays. Nothing joins until you press Join.' : 'Paste a code like ninsei:203f22bcfd1b4b2f, or a link to a message in a room.',
    footer: [
      !code.trim() && jsx('span', { id: 'h-jn-need', className: 'h-faint h-small', children: 'Paste a code to join.' }, 'n'),
      jsx(K.Button, { variant: 'ghost', onClick: props.onClose, children: 'Cancel' }, 'c'),
      jsx(K.Button, { variant: 'primary', disabled: busy || !code.trim(), onClick: join, 'aria-describedby': code.trim() ? undefined : 'h-jn-need',
        children: busy ? 'Joining…' : joined ? 'Open' : 'Join' }, 'j')
    ],
    children: jsxs('div', { className: 'h-col', style: { gap: 12 }, children: [
      jsx(K.Input, { value: code, autoFocus: true, placeholder: 'ninsei:…', 'aria-label': 'Room code', onChange: e => setCode(e.target.value),
        onKeyDown: e => { if (e.key === 'Enter' && code.trim() && !busy) join() } }),
      body,
      also.length > 0 && jsxs('div', { className: 'h-row', style: { gap: 8, justifyContent: 'space-between', flexWrap: 'wrap' }, 'data-also': true, children: [
        jsx('span', { className: 'h-small', children: 'Also on: ' + also.map(relayHost).join(', ') }),
        jsx(K.Button, { variant: 'secondary', size: 'sm', disabled: adding, onClick: addAndLook, children: adding ? 'Adding…' : 'Add and look again' })
      ] }),
      also.length > 0 && jsx('div', { className: 'h-faint h-small', children: 'Connecting to a relay shows it your IP address. Nothing connects to these until you press the button.' })
    ] }) })
}

// Pick one of your rooms to invite one friend to (a friend's card, or the header of your conversation with them). The
// same private invite as the room's Invite button: the room's id and where it lives, nothing you type.
function InviteToRoomDialog(props) {
  const { store, snap, pk, name } = props
  const [busy, setBusy] = useState('')
  const rooms = snap.rooms || []
  const send = async r => {
    setBusy(r.id)
    try {
      await store.post('/rooms/invite', { room: r.id, friends: [pk] }, 'Invited ' + name + ' to ' + r.name + '.')
      props.onClose()
    } catch (_) { setBusy('') }
  }
  return jsx(Modal, { open: true, onClose: props.onClose, title: 'Invite ' + cleanSnippet(name, 32) + ' to a room',
    description: 'They get a private invite with the room’s code. It carries no message, and your agent never sees it.',
    footer: [jsx(K.Button, { variant: 'ghost', onClick: props.onClose, children: 'Cancel' }, 'c')],
    children: jsx('div', { className: 'h-list', role: 'group', 'aria-label': 'Your rooms', style: { maxHeight: 280, overflowY: 'auto' }, children: rooms.length === 0
      ? jsx('div', { className: 'h-faint h-small', children: 'You aren’t in any rooms yet.' })
      : rooms.map(r => jsxs('button', { type: 'button', className: 'h-navrow', disabled: !!busy, onClick: () => send(r), children: [
        jsx('span', { className: 'h-hash', children: '#' }),
        jsx('span', { className: 'h-grow h-trunc', children: r.name }),
        busy === r.id && jsx('span', { className: 'h-faint h-small', children: 'Sending…' })
      ] }, r.id)) }) })
}

// ---- Desktop status bar chip ------------------------------------------------------------------

function StatusChip(props) {
  const st = useStore(props.store)
  const snap = st.snap
  if (!snap || !snap.settings || !snap.settings.onboarded) {
    return jsx(K.Tip, { label: st.error ? 'Ninsei: ' + errorCopy(st).title : 'Open Ninsei', children: jsxs('button', { type: 'button', className: 'hx h-statuschip', onClick: props.onOpen, children: [
      jsx(K.Icon, { name: 'radio-tower', size: 12 }), 'Ninsei'] }) })
  }
  const a = snap.me.agent
  const w = stateWord(a.state)
  const waiting = (snap.offers || []).some(o => o.status === 'open' || o.status === 'ready') || (snap.drafts || []).length > 0
  const label = (a.name || 'Your agent') + ' · ' + STATE_LABEL[w] + (a.note ? ' (' + a.note + ')' : '') + ' · ' +
    fmtTokens(snap.budget.used) + ' of ' + fmtTokens(snap.budget.limit) + ' tokens used today (' +
    repliesWords(dailyReplies(snap.budget)) + ')' + (waiting ? ' · waiting on you' : '')
  return jsx(K.Tip, { label, children: jsxs('button', { type: 'button', className: 'hx h-statuschip', 'aria-label': 'Open Ninsei: ' + label, onClick: props.onOpen, children: [
    jsx(Face, { face: a.face, pk: a.pk, state: waiting ? 'system: waiting' : a.state, size: 15, name: a.name }),
    jsx('span', { children: STATE_LABEL[w] }),
    jsx(BudgetRing, { budget: snap.budget, size: 11, stroke: 1.8 })
  ] }) })
}
