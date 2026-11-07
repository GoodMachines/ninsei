// ---------------------------------------------------------------------------------------------
// private messages: person to person (NIP-17). Your agent is not in this view and never sees it:
// the engine keeps these in their own tables, and no model call is ever made with their words.
// A sender you have never met in a room waits under Requests until you accept or hide them.
// ---------------------------------------------------------------------------------------------

const DM_REQUESTS = 'requests'  // store.dm() value that opens the Requests list instead of one conversation

// The sidebar's "Direct messages": the conversations you have, then Requests (if any) as one row.
function DmRail(props) {
  const { store, snap, view, go } = props
  const dms = snap.dms || { threads: [], unread: 0, requests: 0 }
  const cur = view === 'dm' ? store.dm() : ''
  const list = (dms.threads || []).filter(t => !t.request)
  const open = pk => { store.setDm(pk); go('dm') }
  return jsxs(Fragment, { children: [
    jsx('div', { className: 'h-navhead', children: jsx('span', { className: 'h-sec', children: 'Direct messages' }) }),
    jsxs('div', { className: 'h-nav', children: [
      list.length === 0 && !dms.requests && jsx('div', { className: 'h-faint h-small', style: { padding: '2px 8px' }, children: 'Open someone’s card and press Message.' }),
      list.map(t => jsxs('button', { type: 'button', className: 'h-navrow', 'data-on': cur === t.pk, 'aria-current': cur === t.pk ? 'page' : undefined,
        onClick: () => open(t.pk), children: [
          jsx(K.Icon, { name: 'lock', size: 12 }),
          jsx('span', { className: 'h-grow h-trunc', style: { fontWeight: t.unread ? 600 : 400 }, children: t.name }),
          t.unread > 0 && jsx('span', { className: 'h-dot', 'aria-label': t.unread + (t.unread === 1 ? ' unread private message' : ' unread private messages') })
        ] }, t.pk)),
      dms.requests > 0 && jsxs('button', { type: 'button', className: 'h-navrow', 'data-on': cur === DM_REQUESTS, onClick: () => open(DM_REQUESTS), children: [
        jsx(K.Icon, { name: 'shield', size: 12 }),
        jsx('span', { className: 'h-grow h-trunc', children: 'Requests' }),
        jsx('span', { className: 'h-mentions', 'aria-label': dms.requests + (dms.requests === 1 ? ' message request' : ' message requests'), children: dms.requests > 9 ? '9+' : dms.requests })
      ] })
    ] })
  ] })
}

// One conversation, loaded from /dm. It reloads when the summary's `rev` moves (a message arrived or went), and
// when the window regains focus, so a conversation that came in while you were away is marked read when you look.
function useDmThread(store, pk, rev) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => (store.showing ? store.showing('dm:' + pk) : undefined), [pk])
  const load = useCallback(() => {
    const read = store.isShowing ? store.isShowing('dm:' + pk) : true
    return P.rest('/dm?pk=' + encodeURIComponent(pk) + (read ? '' : '&read=0')).then(d => { setData(d); setErr('') }, e => setErr(errText(e)))
  }, [pk])
  useEffect(() => { load() }, [pk, rev])
  useEffect(() => P.listen(window, 'focus', load), [pk])
  return { data, err, load }
}

function DmView(props) {
  const { store, snap, pk } = props
  const { data, err, load } = useDmThread(store, pk, snap.dms ? snap.dms.rev : 0)
  const scroller = useRef(null)
  const stick = useRef(true)
  const seen = useRef(null)
  const [asking, setAsking] = useState(false)
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
  useLayoutEffect(() => {
    const el = scroller.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [msgs.length, lastId])
  const name = (data && data.name) || 'Someone'
  const send = async text => {
    await store.post('/dm/send', { pk, text })
    stick.current = true
    await load()
  }
  const accept = async () => { try { await store.post('/dm/accept', { pk }); load() } catch (_) { /* toasted */ } }
  const hide = async () => {
    try {
      await store.post('/people/hide', { pk, name }, 'Hid ' + name + '. Their private messages are gone and new ones are dropped. Undo in Settings.')
      store.setDm('')
      nav().set('lobby')
    } catch (_) { /* toasted */ }
  }
  const forget = async () => {
    setAsking(false)
    try { await store.post('/dm/forget', { pk }, 'Conversation deleted from this computer'); store.setDm(''); nav().set('lobby') } catch (_) { /* toasted */ }
  }
  const items = groupItems(msgs, 0)
  const composeRoom = useMemo(() => ({ id: 'dm-' + pk, name, members: [] }), [pk, name])
  const dmSend = useMemo(() => ({ onSend: send, placeholder: 'Message ' + name + ' (private)', max: 2000 }), [pk, name])
  return jsxs(Fragment, { children: [
    jsxs('div', { className: 'h-head', children: [
      jsx(Initial, { name }),
      jsxs('div', { className: 'h-grow h-col', style: { gap: 2, minWidth: 0 }, children: [
        jsxs('div', { className: 'h-row', children: [
          jsx('h2', { className: 'h-trunc', children: name }),
          jsxs('span', { className: 'h-private', children: [jsx(K.Icon, { name: 'lock', size: 11 }), 'private'] }),
          data && data.impostor && jsx(NotVerified, { name })
        ] }),
        jsx('div', { className: 'h-faint h-small h-trunc', children: 'Only the two of you can read this. Your agent never sees it.' })
      ] }),
      props.onPeople && jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'About private messages', onClick: props.onPeople, className: 'h-peoplebtn',
        children: jsx(K.Icon, { name: 'shield', size: 14 }) }),
      jsx(K.Tip, { label: 'Delete this conversation from this computer', children: jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'Delete this conversation',
        onClick: () => setAsking(true), children: jsx(K.Icon, { name: 'trash', size: 14 }) }) })
    ] }),
    data && data.request && jsx('div', { style: { padding: '8px 18px 0' }, children: jsx(Notice, { icon: 'shield', role: 'status', children: jsxs('div', { className: 'h-col', style: { gap: 8 }, children: [
      jsx('span', { children: name + ' isn’t someone you’ve met in a room. Reply or press Accept to move this conversation to your list. Hide drops it, and everything they send later.' }),
      jsxs('div', { className: 'h-actions', children: [
        jsx(K.Button, { variant: 'primary', size: 'sm', onClick: accept, children: 'Accept' }, 'a'),
        jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: hide, children: 'Hide ' + name }, 'h')
      ] })
    ] }) }) }),
    jsx('div', { className: 'h-scroll', ref: scroller, onScroll, children: jsxs('div', { className: 'h-timeline', role: 'log', 'aria-live': 'polite', 'aria-label': 'Private messages with ' + name, children: [
      err && jsx(Notice, { icon: 'warning', role: 'alert', children: err }),
      !data && !err && jsx('div', { className: 'h-empty', children: 'Opening the conversation…' }),
      data && msgs.length === 0 && jsxs('div', { className: 'h-empty', children: [
        jsx(K.Icon, { name: 'lock', size: 22 }),
        jsx('b', { children: 'Say hello to ' + name }),
        jsx('div', { style: { maxWidth: 420 }, children: 'Only the two of you can read what you write here. It is encrypted on its way, and your agent never sees it.' })
      ] }),
      items.map(it => it.kind === 'msg' && jsx(DmItem, { it, animate: fresh(it.key) }, it.key))
    ] }) }),
    jsx('div', { className: 'h-composer', children: jsx(Composer, { store, room: composeRoom, snap, dm: dmSend }) }),
    jsx(Modal, { open: asking, onClose: () => setAsking(false), title: 'Delete this conversation?',
      description: 'It is removed from this computer only. ' + name + ' keeps their copy, and a new message from them starts it again.',
      footer: [
        jsx(K.Button, { variant: 'ghost', onClick: () => setAsking(false), children: 'Keep it' }, 'c'),
        jsx(K.Button, { variant: 'danger', onClick: forget, children: 'Delete' }, 'd')
      ] })
  ] })
}

function DmItem(props) {
  const ref = useEnter(props.animate)
  return jsx('div', { ref, children: jsx(Message, { m: props.it.m, first: props.it.first, book: {} }) })
}

// Strangers' first messages. What they wrote stays unseen until you open the conversation.
function DmRequests(props) {
  const { store, snap } = props
  const reqs = ((snap.dms && snap.dms.threads) || []).filter(t => t.request)
  const open = pk => store.setDm(pk)
  const accept = async t => { try { await store.post('/dm/accept', { pk: t.pk }, t.name + ' accepted'); } catch (_) { /* toasted */ } }
  const hide = async t => { try { await store.post('/people/hide', { pk: t.pk, name: t.name }, 'Hid ' + t.name + '. Undo in Settings.') } catch (_) { /* toasted */ } }
  return jsx('div', { className: 'h-scroll', children: jsxs('div', { className: 'h-pane', style: { maxWidth: 560 }, children: [
    jsx('h1', { children: 'Message requests' }),
    jsx('div', { className: 'h-muted', children: 'People you haven’t met in a room. Their words stay hidden until you open the conversation. Accepting moves it to your list; hiding drops it and anything they send later.' }),
    reqs.length === 0 && jsx('div', { className: 'h-faint', style: { marginTop: 14 }, children: 'No requests right now.' }),
    jsx('div', { className: 'h-list', children: reqs.map(t => jsxs('div', { className: 'h-row', style: { gap: 10, padding: '8px 0' }, children: [
      jsx(Initial, { name: t.name }),
      jsxs('div', { className: 'h-grow h-col', style: { gap: 2, minWidth: 0 }, children: [
        jsx('b', { className: 'h-trunc', children: t.name }),
        jsx('span', { className: 'h-faint h-small', children: (t.unread || 1) + (t.unread === 1 ? ' message · ' : ' messages · ') + fmtAgo(t.ts) })
      ] }),
      jsx(K.Button, { variant: 'secondary', size: 'sm', onClick: () => open(t.pk), children: 'Open' }),
      jsx(K.Button, { variant: 'primary', size: 'sm', onClick: () => accept(t), children: 'Accept' }),
      jsx(K.Button, { variant: 'ghost', size: 'sm', 'aria-label': 'Hide ' + t.name, onClick: () => hide(t), children: 'Hide' })
    ] }, t.pk)) })
  ] }) })
}

// Right rail while private messages are open: exactly what is and isn't private.
function DmAbout() {
  const row = (title, body) => jsxs('div', { className: 'h-mine', style: { marginTop: 0 }, children: [
    jsx('b', { children: title }), jsx('div', { className: 'h-faint h-small', children: body })
  ] })
  return jsxs('div', { className: 'h-col', style: { gap: 10 }, children: [
    jsx('div', { className: 'h-sec', style: { padding: '0 4px' }, children: 'What is private' }),
    row('Encrypted in transit', 'Relays carry a sealed message. They can’t read it or tell who sent it, but they can see that some key received one.'),
    row('Stored on this computer', 'Readable here, unencrypted, by anyone who can open your account, like your keys. Delete a conversation to remove it.'),
    row('Never your agent', 'Your agent can’t send, read or be shown a private message, and no model is ever asked about one.')
  ] })
}

function DmEmpty() {
  return jsxs('div', { className: 'h-empty', children: [
    jsx(K.Icon, { name: 'lock', size: 22 }),
    jsx('b', { children: 'Private messages' }),
    jsx('div', { style: { maxWidth: 420 }, children: 'Open anyone’s card in a room and press Message. Only the two of you can read it, and your agent never sees it.' })
  ] })
}
