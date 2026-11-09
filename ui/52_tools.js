// ---------------------------------------------------------------------------------------------
// room options (mute, chattiness, rename), the quick switcher, the reconnecting banner, empty states and the
// narrow-width drawers. Everything here is local to this page except renaming a room you made.
// ---------------------------------------------------------------------------------------------

// Keys the page offers to whatever is on screen: the room view sets `search` while it is mounted.
const HOTKEYS = { search: null }
// How a `ninsei:` link in a message opens: (room, event) -> the app decides (open the room, or the Join dialog).
const LinkContext = createContext(null)

// A quiet "nothing here yet" with a hint and, optionally, the one thing to do about it. It settles in on a spring.
function EmptyState(props) {
  const ref = useEnter(true)
  return jsxs('div', { className: cx('h-empty', props.compact && 'h-empty-s'), ref, children: [
    // Art is decorative (alt ''), so the title still says it all to a screen reader.
    props.art ? jsx('img', { className: 'h-empty-art', src: props.art, alt: '', width: 240, height: 184, draggable: false })
      : props.icon && jsx(K.Icon, { name: props.icon, size: props.compact ? 16 : 22 }),
    jsx('b', { children: props.title }),
    props.hint && jsx('div', { style: { maxWidth: 420 }, children: props.hint }),
    props.action && jsx('div', { className: 'h-actions', children: props.action })
  ] })
}

// A panel that slides in from an edge on a spring, only when the page is narrow enough to have made it a drawer
// (its CSS position is absolute then). `from` is the starting offset in px.
function useSlide(ref, open, from) {
  const first = useRef(true)
  useEffect(() => {
    const el = ref.current
    if (first.current) { first.current = false; return }
    if (!open || !el || motion.reduced()) return
    const cs = typeof getComputedStyle === 'function' ? getComputedStyle(el) : null
    if (!cs || cs.position !== 'absolute') return
    const sp = motion.spring({ from: 0, to: 1, k: SPRING.enter.k, c: SPRING.enter.c, onUpdate: x => {
      el.style.opacity = String(clamp(x * 1.25, 0, 1))
      el.style.transform = x >= 0.999 && x <= 1.001 ? '' : 'translate(' + ((1 - x) * from.x).toFixed(1) + 'px,' + ((1 - x) * from.y).toFixed(1) + 'px)'
    }, onRest: () => { el.style.opacity = ''; el.style.transform = '' } })
    return () => { sp.stop(); el.style.opacity = ''; el.style.transform = '' }
  }, [open])
}

// ---- my status ----------------------------------------------------------------------------------

const STATUS_CHOICES = [
  { id: 'auto', label: 'Automatic', hint: 'Present while you use Ninsei, then idle, then away when you stop.' },
  { id: 'present', label: 'Present', hint: 'Show as present while you are here.' },
  { id: 'idle', label: 'Idle', hint: 'Show as idle while you are here.' },
  { id: 'dnd', label: 'Do not disturb', hint: 'People see it. This screen shows no pop-ups or notifications.' },
  { id: 'invisible', label: 'Invisible', hint: 'You show as away. Your agent still works.' }
]

// Where a popover goes, in px: under `anchor` (its rect), as wide as `want` (at least `min` when the room allows),
// kept inside `bounds` with `pad` to spare. It flips above the anchor when there is no room below, and
// shifts sideways instead of overflowing; a popover taller than either side gets the bigger side and scrolls.
function placePopover(anchor, size, bounds, opts) {
  const o = Object.assign({ want: 300, min: 280, pad: 8, gap: 6 }, opts)
  const room = bounds.right - bounds.left - o.pad * 2
  const width = Math.max(Math.min(room, o.min), Math.min(o.want, room))
  const left = clamp(anchor.left, bounds.left + o.pad, Math.max(bounds.left + o.pad, bounds.right - width - o.pad))
  const below = bounds.bottom - o.pad - (anchor.bottom + o.gap)
  const above = anchor.top - o.gap - (bounds.top + o.pad)
  const flip = size.height > below && above > below
  const space = Math.max(0, flip ? above : below)
  const height = Math.min(size.height, space)
  const top = flip ? anchor.top - o.gap - height : anchor.bottom + o.gap
  return { left, top, width, maxHeight: Math.floor(space), flipped: flip }
}

// Puts a popover (position: fixed) next to its anchor button. A fixed child is placed relative to its containing
// block, which is the viewport unless an ancestor has a transform, filter or container query, and which one that is
// differs between Desktop and the dashboard (the dashboard's own frame, not `.h-page`, put it under the Hermes nav,
// found live 2026-11-07). So it measures instead of assuming: park at 0,0, read where that landed, offset from there.
// The bounds it keeps inside are the viewport, cut to `.h-page` when there is one. Runs before paint and on resize.
function usePopover(ref, anchor) {
  useLayoutEffect(() => {
    const el = ref.current, a = anchor && anchor.current
    if (!el || !a || !a.getBoundingClientRect) return
    const put = () => {
      const page = a.closest && a.closest('.h-page')
      const box = page ? page.getBoundingClientRect() : null
      const vw = (document.documentElement && document.documentElement.clientWidth) || 1e5
      const vh = (document.documentElement && document.documentElement.clientHeight) || 1e5
      const view = box ? { left: Math.max(0, box.left), top: Math.max(0, box.top), right: Math.min(vw, box.right), bottom: Math.min(vh, box.bottom) }
        : { left: 0, top: 0, right: vw, bottom: vh }
      const r = a.getBoundingClientRect()
      el.style.maxHeight = ''
      el.style.left = '0px'
      el.style.top = '0px'
      const origin = el.getBoundingClientRect ? el.getBoundingClientRect() : { left: 0, top: 0 }   // 0,0 of the containing block, in viewport px
      const pos = placePopover(r, { width: el.offsetWidth, height: el.scrollHeight }, view)
      el.style.width = pos.width + 'px'
      el.style.maxHeight = pos.maxHeight + 'px'
      el.style.left = (pos.left - origin.left) + 'px'
      el.style.top = (pos.top - origin.top) + 'px'
    }
    put()
    return P.listen(window, 'resize', put)
  }, [])
}

// The sidebar header's line, "Maya & Ada · idle", is a button: it shows your status as a dot (the word is its label)
// and opens the picker. People in your rooms see this status; Invisible hides it.
function MyStatus(props) {
  const { store, snap } = props
  const [open, setOpen] = useState(false)
  const btn = useRef(null)
  const a = snap.me.agent
  const st = snap.status || { mode: 'auto', shown: 'away', auto: 'away' }
  const shown = STATUS_LABEL[st.shown] || 'Away'
  const text = (snap.me.name || 'You') + ' & ' + (a.name || 'agent') + ' · ' + STATE_LABEL[stateWord(a.state)]
  const close = back => { setOpen(false); if (back) P.setTimeout(() => btn.current && btn.current.focus && btn.current.focus(), 0) }
  return jsxs('div', { className: 'h-menuwrap h-mystatus', children: [
    jsxs('button', { type: 'button', className: 'h-statusbtn h-faint h-tiny', ref: btn, 'aria-haspopup': 'menu', 'aria-expanded': open,
      'aria-label': 'You show as ' + shown + '. ' + text + '. Change your status', title: 'You show as ' + shown, onClick: () => setOpen(!open), children: [
        jsx('span', { className: 'h-presence', 'data-s': st.shown, 'data-on': st.shown !== 'away', 'aria-hidden': true }),
        jsx('span', { className: 'h-trunc', children: text })
      ] }),
    open && jsx(StatusMenu, { store, st, anchor: btn, onClose: close })
  ] })
}

function StatusMenu(props) {
  const { store, st } = props
  const ref = useEnter(true)
  usePopover(ref, props.anchor)
  const items = useRef([])
  const [idx, setIdx] = useState(Math.max(0, STATUS_CHOICES.findIndex(c => c.id === st.mode)))
  useEffect(() => { const el = items.current[idx]; if (el && el.focus) el.focus() }, [idx])
  useEffect(() => {
    const away = e => { if (ref.current && !ref.current.contains(e.target) && !(props.anchor.current && props.anchor.current.contains(e.target))) props.onClose(false) }
    return P.listen(document, 'pointerdown', away)
  }, [])
  const pick = id => { props.onClose(true); if (id !== st.mode) store.post('/settings', { status_mode: id }).catch(() => {}) }
  const n = STATUS_CHOICES.length
  const onKeyDown = e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setIdx((idx + 1) % n) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setIdx((idx + n - 1) % n) }
    else if (e.key === 'Home') { e.preventDefault(); setIdx(0) }
    else if (e.key === 'End') { e.preventDefault(); setIdx(n - 1) }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); props.onClose(true) }
    else if (e.key === 'Tab') props.onClose(false)
  }
  return jsxs('div', { className: 'h-menu h-pop', ref, role: 'menu', 'aria-label': 'Your status', onKeyDown, children: [
    jsx('div', { className: 'h-menu-h h-sec', role: 'presentation', children: 'Your status' }),
    jsx('div', { className: 'h-menu-h h-faint h-small', role: 'presentation', children: 'People in your rooms see it. You show as ' + (STATUS_LABEL[st.shown] || 'Away') + ' now.' }),
    STATUS_CHOICES.map((c, i) => jsxs('button', { type: 'button', role: 'menuitemradio', 'aria-checked': c.id === st.mode, tabIndex: i === idx ? 0 : -1,
      ref: el => { items.current[i] = el }, onClick: () => pick(c.id), onMouseEnter: () => setIdx(i), children: [
        jsx('span', { className: 'h-menu-tick', 'aria-hidden': true, children: c.id === st.mode ? jsx(K.Icon, { name: 'check', size: 13 }) : null }),
        jsxs('span', { className: 'h-grow', children: [jsx('b', { children: c.label }), jsx('span', { className: 'h-faint h-small h-gm-line', children: c.hint })] })
      ] }, c.id))
  ] })
}

// ---- room options -------------------------------------------------------------------------------

const CHATTY_LABEL = { quiet: 'Quiet', normal: 'Normal', lively: 'Lively' }

// The menu under the header's "Room options" button: mute, how chatty your agent is here, and (only if you made
// the room) rename. Arrow keys move, Enter chooses, Escape closes and gives focus back to the button.
function RoomMenu(props) {
  const { store, room, rm, snap } = props
  const ref = useEnter(true)
  const items = useRef([])
  const [idx, setIdx] = useState(0)
  useEffect(() => { const el = items.current[idx]; if (el && el.focus) el.focus() }, [idx])
  useEffect(() => {
    const away = e => { if (ref.current && !ref.current.contains(e.target) && !(props.anchor.current && props.anchor.current.contains(e.target))) props.onClose(false) }
    const off = P.listen(document, 'pointerdown', away)
    return () => off()
  }, [])
  const global = (snap.settings && snap.settings.chattiness) || 'normal'
  const pref = body => { props.onClose(true); store.post('/rooms/prefs', Object.assign({ room: room.id }, body)).catch(() => {}) }
  const entries = [
    { key: 'mute', role: 'menuitem', icon: rm.muted ? 'bell' : 'bell-slash', label: rm.muted ? 'Unmute this room' : 'Mute this room',
      hint: rm.muted ? 'Alerts and the unread count come back.' : 'No alerts, no notifications, no count. A quiet dot only.',
      run: () => pref({ muted: !rm.muted }) },
    { key: 'h', header: 'Your agent here' },
    { key: 'c-', role: 'menuitemradio', checked: !rm.chattiness, label: 'Follow Settings (' + CHATTY_LABEL[global].toLowerCase() + ')', run: () => pref({ chattiness: '' }) }
  ].concat(['quiet', 'normal', 'lively'].map(k => ({ key: 'c-' + k, role: 'menuitemradio', checked: rm.chattiness === k, label: CHATTY_LABEL[k],
    hint: k === 'quiet' ? 'Answers only when named or asked by you.' : k === 'lively' ? 'Joins in more often.' : '',
    run: () => pref({ chattiness: k }) })))
  if (rm.mine) entries.push({ key: 'sep' }, { key: 'edit', role: 'menuitem', icon: 'edit', label: 'Rename or change the description', run: () => { props.onClose(false); props.onEdit() } })
  const focusable = entries.filter(e => e.role)
  const onKeyDown = e => {
    const n = focusable.length
    if (e.key === 'ArrowDown') { e.preventDefault(); setIdx((idx + 1) % n) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setIdx((idx + n - 1) % n) }
    else if (e.key === 'Home') { e.preventDefault(); setIdx(0) }
    else if (e.key === 'End') { e.preventDefault(); setIdx(n - 1) }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); props.onClose(true) }
    else if (e.key === 'Tab') props.onClose(false)
  }
  let at = -1
  return jsx('div', { className: 'h-menu h-menu-down', ref, role: 'menu', 'aria-label': 'Room options', onKeyDown, children: entries.map(e => {
    if (e.header) return jsx('div', { className: 'h-menu-h h-sec', role: 'presentation', children: e.header }, e.key)
    if (!e.role) return jsx('div', { className: 'h-menu-sep', role: 'separator' }, e.key)
    const i = ++at
    return jsxs('button', { type: 'button', role: e.role, 'aria-checked': e.role === 'menuitemradio' ? !!e.checked : undefined, tabIndex: i === idx ? 0 : -1,
      ref: el => { items.current[i] = el }, onClick: e.run, onMouseEnter: () => setIdx(i), children: [
        e.icon ? jsx(K.Icon, { name: e.icon, size: 14 }) : jsx('span', { className: 'h-menu-tick', 'aria-hidden': true, children: e.checked ? jsx(K.Icon, { name: 'check', size: 13 }) : null }),
        jsxs('span', { className: 'h-grow', children: [jsx('b', { children: e.label }), e.hint && jsx('span', { className: 'h-faint h-small h-gm-line', children: e.hint })] })
      ] }, e.key)
  }) })
}

// Rename a room or change its description. Only the person who made it sees this (the engine refuses anyone else).
function RoomEditDialog(props) {
  const { store, room } = props
  const [name, setName] = useState(room.name || '')
  const [about, setAbout] = useState(room.about || '')
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try { await store.post('/rooms/edit', { room: room.id, name: name.trim(), about: about.trim() }, 'Room updated'); props.onClose() } catch (_) { setBusy(false) }
  }
  return jsx(Modal, { open: true, onClose: props.onClose, title: 'Rename or describe this room',
    description: 'Everyone in the room sees the new words. They are public, and relays or other apps may keep the earlier ones.',
    footer: [
      jsx(K.Button, { variant: 'ghost', onClick: props.onClose, children: 'Cancel' }, 'c'),
      jsx(K.Button, { variant: 'primary', disabled: busy || !name.trim(), onClick: save, children: busy ? 'Saving…' : 'Save' }, 's')
    ],
    children: jsxs('div', { className: 'h-col', style: { gap: 12 }, children: [
      jsx(Field, { label: 'Name', id: 'h-re-name', children: jsx(K.Input, { id: 'h-re-name', value: name, maxLength: 32, autoFocus: true,
        onChange: e => setName(e.target.value), onKeyDown: e => { if (e.key === 'Enter' && name.trim() && !busy) save() } }) }),
      jsx(Field, { label: 'What it is about', id: 'h-re-about', children: jsx(K.Input, { id: 'h-re-about', value: about, maxLength: 200,
        onChange: e => setAbout(e.target.value), onKeyDown: e => { if (e.key === 'Enter' && name.trim() && !busy) save() } }) })
    ] }) })
}

// ---- quick switcher ------------------------------------------------------------------------------

// What the switcher can go to: the Lobby, your Hermes, Settings, your rooms, your friends (and old conversations),
// and Requests when there are some. Plain data; `pick` in App does the going.
function switcherItems(snap) {
  const out = [
    { key: 'lobby', kind: 'lobby', icon: 'compass', label: 'Lobby', sub: 'Find rooms' },
    { key: 'hermes', kind: 'hermes', icon: 'lock', label: 'Your Hermes', sub: 'Private line' },
    { key: 'settings', kind: 'settings', icon: 'gear', label: 'Settings', sub: '' }
  ]
  for (const r of snap.rooms || []) out.push({ key: 'r-' + r.id, kind: 'room', id: r.id, icon: 'hash', label: r.name || 'Room', sub: r.muted ? 'Room, muted' : 'Room' })
  const dms = snap.dms || {}
  for (const t of dms.threads || []) out.push({ key: 'd-' + t.pk, kind: 'dm', id: t.pk, icon: 'person', label: t.name || 'Someone', sub: t.friend === false ? 'Not friends' : 'Friend' })
  if ((dms.invites || []).length > 0) out.push({ key: 'invites', kind: 'invites', icon: 'link', label: 'Room invites', sub: dms.invites.length + ' waiting' })
  if (dms.requests > 0) out.push({ key: 'requests', kind: 'requests', icon: 'organization', label: 'Friend requests', sub: dms.requests + (dms.requests === 1 ? ' waiting' : ' waiting') })
  // Rooms you left, last, so you can come back: picking one opens the Join preview with its code
  for (const r of snap.left || []) out.push({ key: 'rj-' + r.id, kind: 'rejoin', code: r.code, icon: 'hash', label: 'Rejoin ' + (r.name || 'a room'), match: r.name || 'a room', sub: 'Left room' })
  return out
}

function filterSwitcher(items, q) {
  const term = String(q || '').trim()
  if (!term) return items
  return items.map(it => ({ it, s: fuzzyScore(term, it.match || it.label) })).filter(x => x.s >= 0).sort((a, b) => (a.it.kind === 'rejoin') - (b.it.kind === 'rejoin') || b.s - a.s).map(x => x.it)
}

// Cmd/Ctrl+K: type a few letters, arrows move, Enter goes, Escape closes. Opens on a spring.
function QuickSwitcher(props) {
  const [q, setQ] = useState('')
  const [sel, setSel] = useState(0)
  const ref = useEnter(true)
  const input = useRef(null)
  const from = useRef(typeof document !== 'undefined' ? document.activeElement : null)
  useEffect(() => {
    if (input.current && input.current.focus) input.current.focus()
    return () => { const b = from.current; if (b && b.isConnected && b.focus) try { b.focus() } catch (_) { /* gone */ } }
  }, [])
  const list = useMemo(() => filterSwitcher(switcherItems(props.snap), q), [props.snap, q])
  useEffect(() => { setSel(0) }, [q])
  useEffect(() => {
    const el = typeof document !== 'undefined' && document.getElementById && document.getElementById('h-qs-' + sel)
    if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' })
  }, [sel, list])
  const onKeyDown = e => {
    if (e.nativeEvent && e.nativeEvent.isComposing) return
    const n = list.length
    if (e.key === 'ArrowDown' && n) { e.preventDefault(); setSel((sel + 1) % n) }
    else if (e.key === 'ArrowUp' && n) { e.preventDefault(); setSel((sel + n - 1) % n) }
    else if (e.key === 'Enter') { e.preventDefault(); if (list[sel]) props.onPick(list[sel]) }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); props.onClose() }
    else if (e.key === 'Tab') e.preventDefault()
  }
  return jsx('div', { className: 'h-qs-scrim', onMouseDown: e => { if (e.target === e.currentTarget) props.onClose() }, children:
    jsxs('div', { className: 'h-qs', ref, role: 'dialog', 'aria-modal': true, 'aria-label': 'Quick switcher', children: [
      jsx('input', { className: 'h-qs-in', ref: input, value: q, maxLength: 60, placeholder: 'Go to a room, a friend, Lobby or Settings', 'aria-label': 'Go to',
        role: 'combobox', 'aria-expanded': list.length > 0, 'aria-controls': 'h-qs-list', 'aria-autocomplete': 'list',
        'aria-activedescendant': list.length ? 'h-qs-' + sel : undefined, onChange: e => setQ(e.target.value), onKeyDown }),
      list.length === 0
        ? jsx('div', { className: 'h-faint h-small h-qs-none', role: 'status', children: 'Nothing called that.' })
        : jsx('div', { className: 'h-qs-list', id: 'h-qs-list', role: 'listbox', 'aria-label': 'Places', children: list.map((it, i) =>
          jsxs('div', { id: 'h-qs-' + i, role: 'option', className: 'h-qs-opt', 'aria-selected': i === sel, onMouseEnter: () => setSel(i),
            onMouseDown: e => { e.preventDefault(); props.onPick(it) }, children: [
              it.kind === 'dm' ? jsx(PersonMark, { pk: it.id, name: it.label, size: 18 })
                : it.icon === 'hash' ? jsx('span', { className: 'h-hash', 'aria-hidden': true, children: '#' }) : jsx(K.Icon, { name: it.icon, size: 14 }),
              jsx('b', { className: 'h-grow h-trunc', children: it.label }),
              it.sub && jsx('span', { className: 'h-faint h-small', children: it.sub })
            ] }, it.key)) })
    ] }) })
}

// ---- reconnecting ---------------------------------------------------------------------------------

// Shown while every relay is down. It counts down to the next try and goes away by itself when one is back
// (the snapshot stops saying they are all down). Messages you send meanwhile wait and go out later.
function ReconnectBanner(props) {
  const at = useMemo(() => Date.now() / 1000, [props.snap])
  const now = useNow(1000, true)
  const left = Math.max(0, Math.ceil(at + props.retry - now))
  const ref = useEnter(true)
  return jsx('div', { style: { padding: '8px 18px 0' }, ref, children: jsx(Notice, { icon: 'warning', role: 'status',
    children: 'Reconnecting to relays… ' + (left > 0 ? 'next try in ' + left + ' s.' : 'trying now.') + ' What you send waits and goes out when one is back.' }) })
}

// The bar that holds the menu button on a narrow page (hidden by CSS otherwise): the sidebar is a drawer there.
function NavBar(props) {
  return jsxs('div', { className: 'h-navbar', children: [
    jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'Open the sidebar', 'aria-expanded': !!props.open, onClick: props.onToggle, children: jsx(K.Icon, { name: 'menu', size: 15 }) }),
    jsx('b', { className: 'h-grow h-trunc', children: 'Ninsei' }),
    jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'Go to…', onClick: props.onSwitch, children: jsx(K.Icon, { name: 'search', size: 14 }) })
  ] })
}
