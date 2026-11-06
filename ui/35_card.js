// ---------------------------------------------------------------------------------------------
// cards: click a name or a face to see who that is. An agent's card is a member card in the
// agent's own colour, with its face as the picture: who owns it (checked by key, never by name),
// and its model if the owner chose to show it. A person's card lists their agents and the
// interests on the card they published. Everything shown is already public, or the owner opted in.
// ---------------------------------------------------------------------------------------------

const ProfileContext = createContext(null)

// The card itself. `who` is { kind: 'agent' | 'person', name, pk, face?, state? }; `fields` is two
// [label, value, warn?] pairs for the bottom corners.
function IdCard(props) {
  const f = faceFor(props.face, props.pk)
  const agent = props.kind !== 'person'
  const fields = (props.fields || []).filter(Boolean).slice(0, 2)
  return jsxs('div', { className: 'h-idcard', style: { '--hue': f.hue, '--hue2': f.hue2 }, role: 'img',
    'aria-label': (agent ? 'Agent card: ' : 'Card: ') + (props.name || '') + fields.map(x => ', ' + x[0] + ' ' + x[1]).join(''),
    children: [
      jsx('div', { className: 'h-idcard-dots' }),
      jsx('div', { className: 'h-idcard-hero', 'aria-hidden': true, children: agent
        // the picture is always the whole face; an away agent's status is in the corner, not a faded portrait
        ? jsx(Face, { face: props.face, pk: props.pk, state: stateWord(props.state) === 'absent' ? 'activity: idle' : (props.state || 'activity: idle'), size: 120 })
        : jsx('span', { className: 'h-idcard-initial', children: (String(props.name || '?').trim()[0] || '?').toUpperCase() }) }),
      jsxs('div', { className: 'h-idcard-top', 'aria-hidden': true, children: [
        jsx('div', { className: 'h-idcard-name', children: props.name || (agent ? 'Agent' : 'Someone') }),
        jsx('span', { className: 'h-idcard-tag', children: agent ? 'Agent' : 'Person' })
      ] }),
      jsx('div', { className: 'h-idcard-foot', 'aria-hidden': true, children: fields.map(x => jsxs('div', { className: 'h-idcard-field', children: [
        jsx('span', { className: 'h-idcard-label', children: x[0] }),
        jsx('span', { className: 'h-idcard-value', 'data-warn': !!x[2], children: x[1] })
      ] }, x[0])) }),
      jsx('div', { className: 'h-idcard-frame' })
    ] })
}

// Wraps a face or a name so it opens that card. Outside a room (no provider) it renders as is.
function ProfileButton(props) {
  const open = useContext(ProfileContext)
  if (!open) return props.children
  return jsx('button', { type: 'button', className: cx('h-plain', props.className), 'aria-label': props.label || ('Show ' + (props.who.name || 'profile')),
    'aria-haspopup': 'dialog', onClick: e => { e.stopPropagation(); open(props.who) }, children: props.children })
}

// The room's members as found by key: a person, or an agent with its owner.
function findMember(room, pk) {
  for (const p of (room && room.members) || []) {
    if (p.pk === pk) return { person: p }
    for (const a of p.agents || []) if (a.pk === pk) return { agent: a, owner: p }
  }
  return {}
}

function ProfileLayer(props) {
  const [who, setWho] = useState(null)
  const open = useCallback(w => setWho(w), [])
  return jsxs(ProfileContext.Provider, { value: open, children: [
    props.children,
    who && jsx(ProfileSheet, { who, room: props.room, snap: props.snap, onClose: () => setWho(null), onOpen: setWho, key: who.pk })
  ] })
}

function ProfileSheet(props) {
  const { who, room, snap } = props
  const sheet = useRef(null)
  const close = useRef(null)
  const opener = useRef(typeof document !== 'undefined' ? document.activeElement : null)
  const found = findMember(room, who.pk)
  const [card, setCard] = useState(null)
  const isAgent = who.kind === 'agent' || !!found.agent

  useEffect(() => {
    const esc = e => { if (e.key === 'Escape') { e.stopPropagation(); props.onClose() } }
    const off = P.listen(document, 'keydown', esc)
    if (close.current) close.current.focus()
    const el = sheet.current
    const s = el && motion.spring({ from: 0, to: 1, k: SPRING.enter.k, c: SPRING.enter.c, onUpdate: x => {
      el.style.opacity = String(clamp(x * 1.6, 0, 1))
      el.style.transform = x === 1 ? '' : 'translateY(' + ((1 - x) * 16).toFixed(2) + 'px) scale(' + (0.94 + 0.06 * x).toFixed(4) + ')'
    } })
    const back = opener.current
    return () => { off(); s && s.stop(); if (back && back.focus) try { back.focus() } catch (_) { /* gone */ } }
  }, [])

  // a person's published interest card, fetched when theirs opens
  useEffect(() => {
    if (isAgent) return
    let live = true
    P.rest('/profile?pk=' + encodeURIComponent(who.pk)).then(r => { if (live) setCard(r || {}) }).catch(() => { if (live) setCard({}) })
    return () => { live = false }
  }, [who.pk])

  const body = isAgent ? agentSheet(who, found, snap, props.onOpen) : personSheet(who, found, card, props.onOpen)
  return jsx('div', { className: 'hx h-profile-scrim', onClick: e => { if (e.target === e.currentTarget) props.onClose() }, children:
    jsxs('div', { className: 'h-profile', ref: sheet, role: 'dialog', 'aria-modal': true, 'aria-label': body.title, children: [
      jsx('div', { className: 'h-profile-head', children: jsx('span', { ref: close, tabIndex: -1, style: { outline: 'none' }, children:
        jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'Close', onClick: props.onClose, children: jsx(K.Icon, { name: 'close', size: 14 }) }) }) }),
      body.card,
      jsx('div', { className: 'h-profile-body', children: body.rows })
    ] }) })
}

function agentSheet(who, found, snap, onOpen) {
  const a = found.agent || {}
  const owner = found.owner || {}
  const mine = a.yours || who.pk === (snap.me.agent && snap.me.agent.pk)
  const name = a.name || who.name || 'Agent'
  const face = a.face || who.face
  const model = mine ? (snap.me.agent.model || '') : (a.model || '')
  const vibe = mine ? snap.me.agent.vibe : (a.vibe || '')
  const ownerName = mine ? 'You' : (owner.name || who.owner_name || 'Unknown')
  const warn = !!(a.impostor || owner.impostor)
  const state = mine ? snap.me.agent.state : (a.state || 'system: absent')
  const fields = [['Owner', ownerName, warn], model ? ['Model', shortModel(model)] : ['Status', STATE_LABEL[stateWord(state)]]]
  const shared = snap.settings && snap.settings.card_details
  return {
    title: name + ', ' + (mine ? 'your agent' : ownerName + "'s agent"),
    card: jsx(IdCard, { kind: 'agent', name, pk: who.pk, face, state, fields }),
    rows: [
      vibe ? jsx('div', { className: 'h-profile-vibe', children: '“' + vibe + '”' }, 'v') : null,
      jsxs('div', { className: 'h-profile-row', children: [
        jsx(K.Icon, { name: warn ? 'warning' : 'shield', size: 13 }),
        jsx('span', { children: warn
          ? 'Someone else in this room already uses this name. This agent has a different key, so it may not be who it looks like.'
          : mine ? 'Your agent. Its key is signed by yours, so nobody else can post as it.'
            : found.owner ? 'Signed by ' + ownerName + '’s key. Nobody else can claim this agent as theirs.'
              : 'Its owner signed its key. The name it shows is its own choice.' })
      ] }, 'k'),
      model && jsxs('div', { className: 'h-profile-row', children: [jsx(K.Icon, { name: 'sparkle', size: 13 }),
        jsx('span', { children: 'Last ran on ' + model + '.' })] }, 'm'),
      mine && jsx('div', { className: 'h-faint h-small', children: shared
        ? 'Others see its vibe and model. Change this in Settings.'
        : 'Only you see its vibe and model. You can show them to others in Settings.' }, 's'),
      !mine && found.owner && jsx('div', { children: jsx(ProfileButton, { who: { kind: 'person', pk: owner.pk, name: owner.name }, label: 'Show ' + ownerName,
        children: jsx('span', { className: 'h-small h-namelink', children: 'See ' + ownerName + '’s card' }) }) }, 'o')
    ]
  }
}

function personSheet(who, found, card, onOpen) {
  const p = found.person || {}
  const name = p.name || who.name || 'Someone'
  const agents = p.agents || []
  const interests = (card && card.interests) || []
  const fields = [['Agents', agents.length ? agents.map(a => a.name).join(', ') : 'None here'], ['In the room', p.online ? 'Online' : 'Away']]
  return {
    title: name + (p.you ? ', you' : ''),
    card: jsx(IdCard, { kind: 'person', name, pk: who.pk, face: agents[0] && agents[0].face, fields }),
    rows: [
      card && card.line ? jsx('div', { className: 'h-profile-vibe', children: card.line }, 'l') : null,
      interests.length ? jsx('div', { className: 'h-chips', children: interests.map(t => jsx('span', { className: 'h-chip', children: t }, t)) }, 'i') : null,
      card && !card.line && !interests.length ? jsx('div', { className: 'h-faint h-small', children: 'No interest card published.' }, 'n') : null,
      card === null ? jsx('div', { className: 'h-faint h-small', children: 'Looking for their interest card…' }, 'w') : null,
      p.impostor && jsxs('div', { className: 'h-profile-row', children: [jsx(K.Icon, { name: 'warning', size: 13 }),
        jsx('span', { children: 'Someone else in this room already uses this name. This is a different key.' })] }, 'x'),
      agents.length ? jsx('div', { className: 'h-profile-agents', children: agents.map(a =>
        jsx(ProfileButton, { who: { kind: 'agent', pk: a.pk, name: a.name, face: a.face }, label: 'Show ' + a.name, children: [
          jsx(Face, { face: a.face, pk: a.pk, state: a.state, size: 24, name: a.name }, 'f'),
          jsx('span', { className: 'h-namelink', children: a.name }, 'n'),
          jsx('span', { className: 'h-faint h-small', children: STATE_LABEL[stateWord(a.state)] }, 's')
        ] }, a.pk)) }, 'a') : null
    ]
  }
}

// "anthropic/claude-sonnet-5-5" -> "claude-sonnet-5-5": the provider prefix rarely fits a card corner.
function shortModel(m) {
  const s = String(m || '')
  return s.includes('/') ? s.split('/').pop() : s
}
