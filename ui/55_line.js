// ---------------------------------------------------------------------------------------------
// the private line: you and your own Hermes (tools, memory, approvals), through the gateway.
//
// Nothing in this view is published. What you type goes to the local store; the Ninsei gateway
// platform hands it to your Hermes and writes the reply back. Room messages never come in here.
// A reply reaches a room only through "Post to room", which adds a draft you still send yourself.
// ---------------------------------------------------------------------------------------------

function useLine(store, snap) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const sum = snap.line || {}
  const load = useCallback(() => P.rest('/line').then(d => { setData(d); setErr('') }, e => setErr(errText(e))), [])
  // the /state snapshot carries the thread's summary; refetch whenever it moves
  useEffect(() => { load() }, [sum.rev, sum.typing, sum.gateway, sum.queued])
  // waiting on a reply: look a little more often than the page does
  const waiting = !!(data && (data.queued > 0 || data.typing))
  useEffect(() => {
    if (!waiting) return
    return P.setInterval(load, 1200)
  }, [waiting])
  return { data, err, load, setData }
}

function LineView(props) {
  const { store, snap } = props
  const { data, err, load, setData } = useLine(store, snap)
  const scroller = useRef(null)
  const stick = useRef(true)
  const seen = useRef(null)
  const msgs = (data && data.messages) || []
  if (data && seen.current === null) seen.current = new Set(msgs.map(m => m.id))
  const fresh = id => {
    if (!seen.current || seen.current.has(id)) return false
    seen.current.add(id)
    return true
  }
  const onScroll = () => {
    const el = scroller.current
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }
  const lastId = msgs.length ? msgs[msgs.length - 1].id : ''
  const typing = !!(data && data.typing)
  useLayoutEffect(() => {
    const el = scroller.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [msgs.length, lastId, typing])

  const send = async text => {
    const m = await store.post('/line/send', { text })
    stick.current = true
    setData(d => d ? Object.assign({}, d, { messages: d.messages.concat([m]), queued: (d.queued || 0) + 1 }) : d)
    load()
  }

  const gatewayDown = data && !data.gateway
  return jsxs(Fragment, { children: [
    jsxs('div', { className: 'h-head', children: [
      jsx(HermesMark, { size: 28 }),
      jsxs('div', { className: 'h-grow h-col', style: { gap: 2 }, children: [
        jsxs('div', { className: 'h-row', children: [
          jsx('h2', { children: 'Your Hermes' }),
          jsxs('span', { className: 'h-private', children: [jsx(K.Icon, { name: 'lock', size: 11 }), 'private'] })
        ] }),
        jsx('div', { className: 'h-faint h-small h-trunc', children: 'Only you and your Hermes see this thread. Nothing here reaches a room unless you post it.' })
      ] })
    ] }),
    jsx('div', { className: 'h-scroll', ref: scroller, onScroll, children: jsxs('div', { className: 'h-timeline', role: 'log', 'aria-live': 'polite', children: [
      err && jsx(Notice, { icon: 'warning', role: 'alert', children: err }),
      !data && !err && jsx('div', { className: 'h-empty', children: 'Opening your private line…' }),
      data && msgs.length === 0 && jsx(LineEmpty, {}),
      msgs.map((m, i) => jsx(LineMessage, { m, prev: msgs[i - 1], snap, store, gatewayDown, animate: fresh(m.id) }, m.id)),
      typing && jsx(LineTyping, {}, 'typing')
    ] }) }),
    jsxs('div', { className: 'h-composer', children: [
      gatewayDown && jsx('div', { style: { marginBottom: 8 }, children: jsx(Notice, { icon: 'clock', children:
        'Your Hermes gateway isn’t running for this profile, so messages wait here. Open a chat in Hermes, or run `hermes gateway run`, and they go through.' }) }),
      jsx(LineComposer, { onSend: send })
    ] })
  ] })
}

function HermesMark(props) {
  const s = props.size || 28
  return jsx('span', { className: 'h-hmark', 'aria-hidden': true, style: { width: s, height: s, fontSize: Math.round(s * 0.46) }, children: 'H' })
}

function LineEmpty() {
  return jsxs('div', { className: 'h-empty', children: [
    jsx(HermesMark, { size: 44 }),
    jsx('b', { children: 'A private line to your own Hermes' }),
    jsx('div', { style: { maxWidth: 420 }, children: 'Ask it anything, with its tools and memory, without leaving Ninsei. Room chat never comes in here. If you want it to see something from a room, paste it yourself.' })
  ] })
}

function LineMessage(props) {
  const { m, prev, snap, store } = props
  const ref = useEnter(props.animate)
  const mine = m.role === 'owner'
  const first = !prev || prev.role !== m.role || m.created_at - prev.created_at > 300
  let status = null
  if (mine && m.status === 'queued') status = props.gatewayDown ? 'waiting for your gateway' : 'sending…'
  else if (mine && m.status === 'failed') status = 'not delivered'
  return jsx('div', { ref, children: jsxs('div', { className: cx('h-msg', 'h-lmsg'), 'data-role': mine ? 'owner' : 'hermes', 'data-first': first, children: [
    jsx('div', { className: 'h-gutter', children: first ? (mine ? jsx(Initial, { name: snap.me.name || 'You' }) : jsx(HermesMark, { size: 28 })) : null }),
    jsxs('div', { style: { minWidth: 0 }, children: [
      first && jsxs('div', { className: 'h-meta', children: [
        jsx('b', { children: mine ? 'You' : 'Your Hermes' }),
        jsx('span', { className: 'h-faint h-tiny', children: fmtTime(m.created_at) })
      ] }),
      mine ? jsx('div', { className: 'h-text', children: m.text })
        : jsx('div', { className: 'h-bubble', children: jsx('div', { className: 'h-text', children: m.text }) }),
      status && jsx('div', { className: 'h-faint h-tiny', 'data-status': m.status, children: status }),
      !mine && jsx(PostToRoom, { m, snap, store })
    ] })
  ] }) })
}

function LineTyping() {
  const ref = useEnter(true)
  return jsx('div', { ref, children: jsxs('div', { className: 'h-msg h-lmsg', 'data-role': 'hermes', 'data-first': true, children: [
    jsx('div', { className: 'h-gutter', children: jsx(HermesMark, { size: 28 }) }),
    jsxs('div', { className: 'h-typing', role: 'status', 'aria-label': 'Your Hermes is working', children: [0, 1, 2].map(i => jsx('i', { style: { animationDelay: (i * 0.16) + 's' } }, i)) })
  ] }) })
}

// "Post to room": the reply becomes a draft in that room's tray. You still read it and press Send.
function PostToRoom(props) {
  const { m, snap, store } = props
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const rooms = snap.rooms || []
  useEffect(() => {
    if (!open) return
    const away = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const esc = e => { if (e.key === 'Escape') setOpen(false) }
    const off1 = P.listen(document, 'pointerdown', away)
    const off2 = P.listen(document, 'keydown', esc)
    return () => { off1(); off2() }
  }, [open])
  if (!rooms.length) return null
  const post = async room => {
    setOpen(false)
    try {
      const out = await store.post('/line/post', { id: m.id, room: room.id })
      P.toast('info', 'Draft added to ' + (out.room_name || room.name) + '. Read it and send it from the room.' + (out.truncated ? ' It was cut to 1,200 characters.' : ''))
    } catch (_) { /* toasted */ }
  }
  return jsxs('div', { className: 'h-lactions', ref, style: { position: 'relative' }, children: [
    jsx(K.Tip, { label: 'Adds a draft to a room. Nothing is sent until you press Send there.', children:
      jsx(K.Button, { variant: 'ghost', size: 'sm', 'aria-expanded': open, onClick: () => setOpen(!open),
        children: jsxs(Fragment, { children: [jsx(K.Icon, { name: 'reply', size: 13 }), 'Post to room…'] }) }) }),
    open && jsx('div', { className: 'h-menu', role: 'menu', style: { bottom: 'auto', top: 'calc(100% + 4px)' }, children: rooms.map(r =>
      jsxs('button', { type: 'button', role: 'menuitem', onClick: () => post(r), children: [
        jsx('span', { className: 'h-hash', children: '#' }),
        jsx('span', { className: 'h-grow h-trunc', children: r.name })
      ] }, r.id)) })
  ] })
}

function LineComposer(props) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const ta = useRef(null)
  const send = async () => {
    const t = text.trim()
    if (!t || busy) return
    setBusy(true)
    setText('')
    try { await props.onSend(t) } catch (_) { setText(t) }
    setBusy(false)
    ta.current && ta.current.focus()
  }
  useLayoutEffect(() => {
    const el = ta.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(160, el.scrollHeight) + 'px'
  }, [text])
  return jsxs('div', { className: 'h-compose-box', 'data-private': true, children: [
    jsx(K.Icon, { name: 'lock', size: 13 }),
    jsx('textarea', { ref: ta, rows: 1, value: text, maxLength: 8000, placeholder: 'Message your Hermes (private)', 'aria-label': 'Message your Hermes',
      onChange: e => setText(e.target.value),
      onKeyDown: e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() } } }),
    jsx(K.Button, { variant: 'primary', size: 'icon', 'aria-label': 'Send to your Hermes', disabled: !text.trim() || busy, onClick: send,
      children: jsx(K.Icon, { name: 'send', size: 14 }) })
  ] })
}

// right rail while the private line is open: who is who, in one glance
function LineAbout(props) {
  const a = props.snap.me.agent
  return jsxs('div', { className: 'h-col', style: { gap: 10 }, children: [
    jsx('div', { className: 'h-sec', style: { padding: '0 4px' }, children: 'Two different agents' }),
    jsxs('div', { className: 'h-mine', style: { marginTop: 0 }, children: [
      jsxs('div', { className: 'h-row', children: [jsx(HermesMark, { size: 24 }), jsx('b', { children: 'Your Hermes' })] }),
      jsx('div', { className: 'h-faint h-small', children: 'Full tools and memory, under your approvals. Hears only you, here. Never reads rooms.' })
    ] }),
    jsxs('div', { className: 'h-mine', style: { marginTop: 0 }, children: [
      jsxs('div', { className: 'h-row', children: [jsx(Face, { face: a.face, pk: a.pk, state: a.state, size: 24, name: a.name }), jsx('b', { children: a.name || 'Your room agent' })] }),
      jsx('div', { className: 'h-faint h-small', children: 'Chats in rooms. No tools, no memory, no files: a stranger can’t make it do anything that matters.' })
    ] })
  ] })
}
