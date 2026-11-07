// ---------------------------------------------------------------------------------------------
// private messages: person to person (NIP-17), between friends only. Your agent is not in this view and never
// sees it: the engine keeps these in their own tables, and no model call is ever made with their words.
// A friend request has no words at all: only who is asking. It waits under Requests until you accept or ignore it.
// ---------------------------------------------------------------------------------------------

const NO_MSGS = []  // a stable empty list, so a conversation that hasn't loaded doesn't look like a new snapshot each render
const DM_REQUESTS = 'requests'  // store.dm() value that opens the Requests list instead of one conversation
const DM_POLL_MS = 2000  // how often an open conversation re-asks while a message of mine is still on its way

// The sidebar's "Direct messages": your friends (and any old conversation), then Requests (if any) as one row.
function DmRail(props) {
  const { store, snap, view, go } = props
  const dms = snap.dms || { threads: [], unread: 0, requests: 0 }
  const cur = view === 'dm' ? store.dm() : ''
  const list = dms.threads || []
  const open = pk => { store.setDm(pk); go('dm') }
  return jsxs(Fragment, { children: [
    jsx('div', { className: 'h-navhead', children: jsx('span', { className: 'h-sec', children: 'Direct messages' }) }),
    jsxs('div', { className: 'h-nav', children: [
      list.length === 0 && !dms.requests && jsx('div', { className: 'h-faint h-small', style: { padding: '2px 8px' }, children: 'Open someone’s card and press Add friend. Once they accept, you can message each other.' }),
      list.map(t => jsxs('button', { type: 'button', className: 'h-navrow', 'data-on': cur === t.pk, 'aria-current': cur === t.pk ? 'page' : undefined,
        onClick: () => open(t.pk), children: [
          jsx(PersonMark, { pk: t.pk, name: t.name, size: 18, flagged: !!t.impostor }),
          jsx('span', { className: 'h-grow h-trunc', style: { fontWeight: t.unread ? 600 : 400, opacity: t.friend === false ? 0.6 : 1 }, children: t.name }),
          t.friend === false && jsx('span', { className: 'h-faint h-small', children: 'not friends' }),
          t.unread > 0 && jsx('span', { className: 'h-dot', 'aria-label': t.unread + (t.unread === 1 ? ' unread private message' : ' unread private messages') })
        ] }, t.pk)),
      dms.requests > 0 && jsxs('button', { type: 'button', className: 'h-navrow', 'data-on': cur === DM_REQUESTS, onClick: () => open(DM_REQUESTS), children: [
        jsx(K.Icon, { name: 'organization', size: 12 }),
        jsx('span', { className: 'h-grow h-trunc', children: 'Requests' }),
        jsx('span', { className: 'h-mentions', 'aria-label': dms.requests + (dms.requests === 1 ? ' friend request' : ' friend requests'), children: dms.requests > 9 ? '9+' : dms.requests })
      ] })
    ] })
  ] })
}

// One conversation, loaded from /dm. It reloads when the summary's `rev` moves (a message arrived or went), and
// when the window regains focus, so a conversation that came in while you were away is marked read when you look.
// A relay's OK doesn't move `rev`, so while a message of mine is still sending or pending it reloads every
// DM_POLL_MS, and stops once every one has settled (sent, or failed with Retry / Discard).
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
  const unsettled = !!(data && (data.messages || []).some(m => m.mine && (m.delivery === 'sending' || m.delivery === 'pending')))
  useEffect(() => {
    if (!unsettled) return undefined
    const t = setTimeout(load, DM_POLL_MS)
    return () => clearTimeout(t)
  }, [data, unsettled])
  return { data, err, load }
}

function DmView(props) {
  const { store, snap, pk } = props
  const { data, err, load } = useDmThread(store, pk, snap.dms ? snap.dms.rev : 0)
  const seen = useRef(null)
  const [asking, setAsking] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const key = 'dm-' + pk
  const fetchPage = useCallback(id => P.rest('/dm?pk=' + encodeURIComponent(pk) + '&read=0&before=' + encodeURIComponent(id)).then(d => ({ messages: d.messages, more: d.earlier })), [pk])
  const er = useEarlier(key, (data && data.messages) || NO_MSGS, data && data.earlier, fetchPage)
  // what you just sent shows at once, faint, until the conversation has it
  const sent = useOutbox(key)
  const have = useMemo(() => new Set(er.msgs.map(m => m.id)), [er.msgs])
  useEffect(() => { outboxSweep(key, have) }, [have, sent])
  const mine = sent.filter(e => !(e.state === 'posted' && e.id && have.has(e.id)))
  const msgs = mine.length ? er.msgs.concat(mine.map(e => outboxItem(e, snap.me))) : er.msgs
  const loadEarlier = useCallback(async () => { setLoadingMore(true); try { return await er.load() } finally { setLoadingMore(false) } }, [er.load])
  const keeper = useScrollKeeper(key, !!data, msgs, er.more, loadEarlier)
  const { scroller, stick } = keeper
  if (data && seen.current === null) seen.current = new Set(msgs.map(m => m.id))
  const fresh = id => {
    if (!seen.current) return false
    if (seen.current.has(id)) return false
    seen.current.add(id)
    return !er.olderIds.has(id)
  }
  if (seen.current) for (const e of sent) if (e.id) seen.current.add(e.id)
  const name = (data && data.name) || 'Someone'
  // Sending: the message appears at once; a send the engine refuses becomes Retry / Discard in place
  const send = text => {
    stick.current = true
    return outboxSend(key, text, null, t => store.post('/dm/send', { pk, text: t }).then(out => load().then(() => out)))
  }
  const retry = m => {
    if (m.local) {
      const e = (OUTBOX.get(key) || []).find(x => x.tmp === m.id)
      if (!e) return
      outboxSet(key, l => l.filter(x => x.tmp !== m.id))
      send(e.text)
    } else store.post('/dm/retry', { pk, id: m.id }).then(load, () => {})   // the very same sealed message
  }
  const discard = m => {
    if (m.local) outboxSet(key, l => l.filter(x => x.tmp !== m.id))
    else store.post('/dm/discard', { pk, id: m.id }).then(load, () => {})
  }
  const friendPost = async (path, okMsg) => { try { await store.post(path, { pk }, okMsg); await load() } catch (_) { /* toasted */ } }
  const addFriend = () => friendPost('/friend/request', 'Friend request sent to ' + name + '.')
  const accept = () => friendPost('/friend/accept', name + ' is now your friend.')
  const ignore = async () => { try { await store.post('/friend/ignore', { pk }); store.setDm(''); nav().set('lobby') } catch (_) { /* toasted */ } }
  const unfriend = async () => {
    setRemoving(false)
    await friendPost('/friend/remove', name + ' isn’t your friend any more.')
  }
  const hide = async () => {
    try {
      await store.post('/people/hide', { pk, name }, 'Hid ' + name + '. Their private messages and friend requests are gone, and new ones are dropped. Undo in Settings.')
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
      jsx(PersonMark, { pk, name, size: 32, flagged: !!(data && data.impostor) }),
      jsxs('div', { className: 'h-grow h-col', style: { gap: 2, minWidth: 0 }, children: [
        jsxs('div', { className: 'h-row', children: [
          jsx('h2', { className: 'h-trunc', children: name }),
          jsxs('span', { className: 'h-private', children: [jsx(K.Icon, { name: 'lock', size: 11 }), 'private'] }),
          data && data.impostor && jsx(NotVerified, { name })
        ] }),
        jsx('div', { className: 'h-faint h-small h-trunc', children: 'Only the two of you can read this. Your agent never sees it.' })
      ] }),
      data && data.friend && jsx(K.Tip, { label: 'Remove ' + name + ' from your friends', children: jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'Remove ' + name + ' from your friends',
        onClick: () => setRemoving(true), children: jsx(K.Icon, { name: 'close', size: 14 }) }) }),
      props.onPeople && jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'About private messages', onClick: props.onPeople, className: 'h-peoplebtn',
        children: jsx(K.Icon, { name: 'shield', size: 14 }) }),
      jsx(K.Tip, { label: 'Delete this conversation from this computer', children: jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'Delete this conversation',
        onClick: () => setAsking(true), children: jsx(K.Icon, { name: 'trash', size: 14 }) }) })
    ] }),
    data && !data.friend && jsx('div', { style: { padding: '8px 18px 0' }, children: jsx(Notice, { icon: 'shield', role: 'status', children: jsxs('div', { className: 'h-col', style: { gap: 8 }, children: [
      jsx('span', { children: data.rel === 'request' ? name + ' asked to be friends. Accept to message each other. Ignore tells them nothing.'
        : data.rel === 'sent' ? 'You asked ' + name + ' to be friends. You can message each other once they accept.'
        : 'You and ' + name + ' aren’t friends, so neither of you can send a private message. The conversation so far stays here until you delete it.' }),
      jsxs('div', { className: 'h-actions', children: [
        data.rel === 'request' && jsx(K.Button, { variant: 'primary', size: 'sm', onClick: accept, children: 'Accept' }, 'a'),
        data.rel === 'request' && jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: ignore, children: 'Ignore' }, 'i'),
        !data.rel && jsx(K.Button, { variant: 'primary', size: 'sm', onClick: addFriend, children: 'Add friend' }, 'f'),
        data.rel === 'sent' && jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: unfriend, children: 'Cancel request' }, 'c'),
        jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: hide, children: 'Hide ' + name }, 'h')
      ] })
    ] }) }) }),
    jsx('div', { className: 'h-scroll', ref: scroller, onScroll: keeper.onScroll, children: jsxs('div', { className: 'h-timeline', role: 'log', 'aria-live': 'polite', 'aria-label': 'Private messages with ' + name, children: [
      er.more && jsx(EarlierButton, { onClick: keeper.loadMore, busy: loadingMore }),
      err && jsx(Notice, { icon: 'warning', role: 'alert', children: err }),
      !data && !err && jsx('div', { className: 'h-empty', children: 'Opening the conversation…' }),
      data && data.friend && msgs.length === 0 && mine.length === 0 && jsx(EmptyState, { icon: 'lock', title: 'Say hello to ' + name,
        hint: 'Only the two of you can read what you write here. It is encrypted on its way, and your agent never sees it.' }),
      items.map(it => (it.kind === 'day' ? jsx(DmItem, { it, animate: false }, it.key) : it.kind === 'msg' && jsx(DmItem, { it, animate: fresh(it.key), onRetry: retry, onDiscard: discard }, it.key)))
    ] }) }),
    data && data.friend && jsx('div', { className: 'h-composer', children: jsx(Composer, { store, room: composeRoom, snap, dm: dmSend }) }),
    jsx(Modal, { open: removing, onClose: () => setRemoving(false), title: 'Remove ' + name + ' from your friends?',
      description: 'You will both stop being able to send private messages, and ' + name + ' is told. The conversation stays on this computer until you delete it. You can add each other again later.',
      footer: [
        jsx(K.Button, { variant: 'ghost', onClick: () => setRemoving(false), children: 'Keep ' + name }, 'c'),
        jsx(K.Button, { variant: 'danger', onClick: unfriend, children: 'Remove friend' }, 'd')
      ] }),
    jsx(Modal, { open: asking, onClose: () => setAsking(false), title: 'Delete this conversation?',
      description: 'It is removed from this computer only. ' + name + ' keeps their copy, and the friendship is not affected.',
      footer: [
        jsx(K.Button, { variant: 'ghost', onClick: () => setAsking(false), children: 'Keep it' }, 'c'),
        jsx(K.Button, { variant: 'danger', onClick: forget, children: 'Delete' }, 'd')
      ] })
  ] })
}

function DmItem(props) {
  const ref = useEnter(props.animate)
  if (props.it.kind === 'day') return jsx(DayLine, { ts: props.it.ts })
  return jsx('div', { ref, children: jsx(Message, { m: props.it.m, first: props.it.first, book: {}, onRetry: props.onRetry, onDiscard: props.onDiscard }) })
}

// Friend requests. There is nothing to read: a request has no message, only who is asking (by the name your rooms
// know them by, or a short key) and, for a lookalike, a warning.
function DmRequests(props) {
  const { store, snap } = props
  const reqs = (snap.dms && snap.dms.pending) || []
  const accept = async t => { try { await store.post('/friend/accept', { pk: t.pk }, t.name + ' is now your friend.') } catch (_) { /* toasted */ } }
  const ignore = async t => { try { await store.post('/friend/ignore', { pk: t.pk }, 'Ignored. ' + t.name + ' isn’t told.') } catch (_) { /* toasted */ } }
  const hide = async t => { try { await store.post('/people/hide', { pk: t.pk, name: t.name }, 'Hid ' + t.name + '. Undo in Settings.') } catch (_) { /* toasted */ } }
  return jsx('div', { className: 'h-scroll', children: jsxs('div', { className: 'h-pane', style: { maxWidth: 560 }, children: [
    jsx('h1', { children: 'Friend requests' }),
    jsx('div', { className: 'h-muted', children: 'People who asked to be friends. A request has no message, only who is asking. Accept to message each other. Ignore is private: they aren’t told, and if they ask again within 30 days you won’t see it. Hide drops them and everything they send later.' }),
    reqs.length === 0 && jsx('div', { className: 'h-faint', style: { marginTop: 14 }, children: 'No requests right now.' }),
    jsx('div', { className: 'h-list', children: reqs.map(t => jsxs('div', { className: 'h-row', style: { gap: 10, padding: '8px 0' }, children: [
      jsx(PersonMark, { pk: t.pk, name: t.name, size: 28, flagged: !!t.impostor }),
      jsxs('div', { className: 'h-grow h-col', style: { gap: 2, minWidth: 0 }, children: [
        jsx('b', { className: 'h-trunc', children: t.name }),
        jsxs('span', { className: 'h-faint h-small', children: [(t.impostor ? 'not verified · ' : '') + 'wants to be friends · ' + fmtAgo(t.ts)] })
      ] }),
      jsx(K.Button, { variant: 'primary', size: 'sm', 'aria-label': 'Accept ' + t.name, onClick: () => accept(t), children: 'Accept' }),
      jsx(K.Button, { variant: 'ghost', size: 'sm', 'aria-label': 'Ignore ' + t.name, onClick: () => ignore(t), children: 'Ignore' }),
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
    row('Encrypted in transit', 'Relays carry a sealed message they can’t read, and the sealed note doesn’t say who sent it.'),
    row('What a relay can see', 'Your key, because Ninsei asks it for the messages addressed to you, and when each one arrives. From that timing a relay, or someone watching it, may guess who is writing to whom. Your copy of what you send goes out a little later to make that harder, not impossible.'),
    row('Friends only', 'Only people you are friends with can message you. A friend request carries no words, only who is asking, and it is sealed the same way.'),
    row('Stored on this computer', 'Readable here, unencrypted, by anyone who can open your account, like your keys. Delete a conversation to remove it.'),
    row('Never your agent', 'Your agent can’t send, read or be shown a private message, and no model is ever asked about one.')
  ] })
}

function DmEmpty(props) {
  const has = props.snap && props.snap.dms && (props.snap.dms.threads || []).length > 0
  return jsx(EmptyState, { icon: 'lock', title: has ? 'Pick a friend to message' : 'No friends yet',
    hint: has ? 'Only the two of you can read what you write. It is encrypted on its way, and your agent never sees it.'
      : 'Open anyone’s card in a room and press Add friend. Once they accept, you can message each other. Only the two of you can read it, and your agent never sees it.' })
}
