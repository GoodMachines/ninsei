// ---------------------------------------------------------------------------------------------
// cards: click a name or a face to see who that is. An agent's card is a member card in the
// agent's own colour, with its face as the picture: who owns it (checked by key, never by name),
// and its model if the owner chose to show it. A person's card lists their agents and the
// interests on the card they published. Everything shown is already public, or the owner opted in.
// ---------------------------------------------------------------------------------------------

const ProfileContext = createContext(null)

// "3f2a9c1b77e0..." -> "3F2A·9C1B·77E0": the start of a key, printed on the card like a card number.
// Anything that isn't at least 12 hex characters gets no number.
function cardSerial(pk) {
  const s = typeof pk === 'string' ? pk : ''
  if (!/^[0-9a-fA-F]{12,}$/.test(s)) return ''
  const h = s.slice(0, 12).toUpperCase()
  return h.slice(0, 4) + '·' + h.slice(4, 8) + '·' + h.slice(8, 12)
}

// A whole 64-character key as four rows of 16, for the back of the card ([] for anything else).
function keyGroups(pk) {
  const s = typeof pk === 'string' ? pk : ''
  if (!/^[0-9a-fA-F]{64}$/.test(s)) return []
  const h = s.toUpperCase()
  return [h.slice(0, 16), h.slice(16, 32), h.slice(32, 48), h.slice(48, 64)]
}

// Three type sizes for the name, so a long one stays in two lines above the fields. Long words step
// down sooner than long names, since a word only breaks mid-letter.
function nameSize(name) {
  const s = String(name == null ? '' : name).trim()
  const len = Array.from(s).length
  const word = s.split(/\s+/).reduce((m, w) => Math.max(m, Array.from(w).length), 0)
  if (len > 20 || word > 12) return 's'
  if (len > 12 || word > 9) return 'm'
  return 'l'
}

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// unix seconds -> "Thu 6 Nov" (with the year when it isn't this one); '' for anything else.
function fmtDay(ts) {
  const n = typeof ts === 'number' ? ts : NaN
  if (!Number.isFinite(n) || n <= 0) return ''
  const d = new Date(n * 1000)
  if (isNaN(d.getTime())) return ''
  const out = DAY_NAMES[d.getDay()] + ' ' + d.getDate() + ' ' + MONTH_NAMES[d.getMonth()]
  return d.getFullYear() === new Date().getFullYear() ? out : out + ' ' + d.getFullYear()
}

// A message count the engine sent, or null.
function postCount(n) {
  return Number.isInteger(n) && n >= 0 ? n : null
}

// "First seen here Thu 6 Nov. 42 messages here." from whatever of the two is known.
function activityText(first, posts) {
  const day = fmtDay(first)
  const n = postCount(posts)
  const out = []
  if (day) out.push('First seen here ' + day + '.')
  if (n != null) out.push(n + (n === 1 ? ' message' : ' messages') + ' here.')
  return out.join(' ')
}

// Where a person's agents sit in their card's picture: [left, top, size] in % of the hero box.
// The first is largest and in front; the others peek out behind it.
const CREW_SPOTS = {
  1: [[0, 0, 100]],
  2: [[4, 16, 78], [52, -2, 50]],
  3: [[14, 21, 72], [57, -1, 45], [-6, 5, 41]]
}

// Pointer tilt: the card leans toward the pointer and a shine follows it. Three springs write
// --tx, --ty (-1..1) and --glow (0..1) on the stage; CSS turns them into the rotation, the shine and
// the frame's colour shift. No tilt for touch or with reduced motion.
function useCardTilt(ref, enabled) {
  useEffect(() => {
    const el = ref.current
    if (!el || !enabled) return
    const put = name => x => el.style.setProperty(name, x.toFixed(4))
    const sx = motion.spring({ from: 0, to: 0, k: SPRING.tilt.k, c: SPRING.tilt.c, onUpdate: put('--tx') })
    const sy = motion.spring({ from: 0, to: 0, k: SPRING.tilt.k, c: SPRING.tilt.c, onUpdate: put('--ty') })
    const glow = motion.spring({ from: 0, to: 0, k: SPRING.calm.k, c: SPRING.calm.c, onUpdate: put('--glow') })
    const move = e => {
      if (e.pointerType === 'touch' || motion.reduced()) return
      const r = el.getBoundingClientRect()
      if (!r.width || !r.height) return
      sx.to(clamp((e.clientX - r.left) / r.width * 2 - 1, -1, 1))
      sy.to(clamp((e.clientY - r.top) / r.height * 2 - 1, -1, 1))
      glow.to(1)
    }
    const rest = () => { sx.to(0); sy.to(0); glow.to(0) }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerleave', rest)
    el.addEventListener('pointercancel', rest)
    return () => {
      el.removeEventListener('pointermove', move)
      el.removeEventListener('pointerleave', rest)
      el.removeEventListener('pointercancel', rest)
      sx.stop(); sy.stop(); glow.stop()
    }
  }, [enabled])
}

// The half turn: rotateY on a spring with a little overshoot, lifting slightly mid-turn. Reduced
// motion swaps faces at once (the spring snaps).
function useCardFlip(ref, flipped) {
  const s = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const deg = flipped ? 180 : 0
    if (s.current) { s.current.to(deg); return }
    s.current = motion.spring({ from: deg, to: deg, k: SPRING.flip.k, c: SPRING.flip.c, onUpdate: x => {
      const lift = 1 + 0.04 * Math.max(0, Math.sin(x * Math.PI / 180))
      el.style.transform = x === 0 ? '' : 'rotateY(' + x.toFixed(2) + 'deg) scale(' + lift.toFixed(4) + ')'
    } })
  }, [flipped])
  useEffect(() => () => s.current && s.current.stop(), [])
}

// Picking the Scanner style while the card is on screen (the face editor) switches the monitor on: the
// picture opens from a bright line on a spring. Only on a change, never when a card first appears.
function useScreenPowerOn(ref, card) {
  const shown = useRef(card)
  useEffect(() => {
    if (shown.current === card) return
    shown.current = card
    const el = card === 'scanner' && ref.current && ref.current.querySelector('.h-idcard-front .h-scan-screen')
    if (!el || motion.reduced()) return
    const put = x => {
      const done = x >= 0.999
      el.style.transform = done ? '' : 'scaleY(' + (0.012 + 0.988 * clamp(x, 0, 1)).toFixed(4) + ')'
      el.style.filter = done ? '' : 'brightness(' + (1 + 2.4 * clamp(1 - x, 0, 1)).toFixed(3) + ')'
    }
    const s = motion.spring({ from: 0, to: 1, k: SPRING.power.k, c: SPRING.power.c, onUpdate: put })
    return () => { s.stop(); put(1) }
  }, [card])
}

// What the card's front says, from IdCard's props. The image export reads the same function, so the
// picture can never show something the card doesn't.
function cardModel(props) {
  const agent = props.kind !== 'person'
  const warn = !!props.warn
  return {
    f: faceFor(props.face, props.pk),
    agent,
    warn,
    name: props.name || (agent ? 'Agent' : 'Someone'),
    tag: warn ? 'Check key' : agent ? 'Agent' : 'Person',
    serial: cardSerial(props.pk),
    fields: (props.fields || []).filter(Boolean).slice(0, 2),
    initial: (String(props.name || '?').trim()[0] || '?').toUpperCase(),
    card: faceFor(props.face, props.pk).card,
    led: scanLed(props)
  }
}

// The card itself. Props:
//   kind 'agent' | 'person', name, pk, face, state   who it is (face picks the hue and the card style)
//   online      a person is in the room (the Scanner's LED)
//   fields      up to two [label, value, warn?] pairs for the front's bottom corners
//   warn        the key check failed: red frame and a "Check key" tag
//   agents      a person's agents [{ face, pk }], drawn as the picture (up to three)
//   about, model, first, posts   the back: vibe or line, model, first seen (unix s), messages here
//   interactive the sheet's card: click, Enter or Space turns it over (role=button, aria-pressed)
//   flipped, onFlip   control the turn from outside (the sheet's Flip button); else it keeps its own
//   tilt        false turns off the pointer tilt (on by default, preview included)
//   cardRef     ref to the front face element
function IdCard(props) {
  const model = cardModel(props)
  const { f, agent, warn, fields, name, serial } = model
  const interactive = !!props.interactive
  const [own, setOwn] = useState(false)
  const flipped = interactive && (props.flipped != null ? !!props.flipped : own)
  const stage = useRef(null)
  const turn = useRef(null)
  useCardTilt(stage, props.tilt !== false)
  useCardFlip(turn, flipped)
  useScreenPowerOn(turn, model.card)

  const label = (agent ? 'Agent card: ' : 'Card: ') + (props.name || '') + (warn ? ', check key' : '') +
    fields.map(x => ', ' + x[0] + ' ' + x[1]).join('') + (serial ? ', card number ' + serial : '')
  const flip = () => { if (props.onFlip) props.onFlip(!flipped); else setOwn(!flipped) }
  const crew = (props.agents || []).filter(a => a && a.pk).slice(0, 3)
  const idle = 'activity: idle'

  // a person who set a picture or a face is shown by it (never a lookalike: the sheet passes `art` only for the real key)
  const mark = !agent && !warn && props.art && (props.art.av || props.art.face) ? jsx(PersonHero, { pk: props.pk, art: props.art }) : null
  const hero = agent
    // the picture is always the whole face; an away agent's status is in the corner, not a faded portrait
    ? jsx(Face, { face: props.face, pk: props.pk, state: stateWord(props.state) === 'absent' ? idle : (props.state || idle), size: 120 })
    : mark ? mark
    : crew.length
      ? jsx('div', { className: 'h-idcard-crew', children: crew.map((a, i) => {
          const [left, top, size] = CREW_SPOTS[crew.length][i]
          return jsx('div', { className: 'h-idcard-mate', 'data-front': i === 0, style: { left: left + '%', top: top + '%', width: size + '%', zIndex: 3 - i },
            children: jsx(Face, { face: a.face, pk: a.pk, state: idle, size: 120 }) }, a.pk)
        }) })
      : jsx('span', { className: 'h-idcard-initial', children: model.initial })

  const scanner = model.card === 'scanner'
  const front = scanner ? scannerFront(model, Object.assign({}, props, { label, flipped }), hero) : jsxs('div', { className: 'h-idcard h-idcard-front', ref: props.cardRef, 'data-warn': warn,
    style: { '--hue': f.hue, '--hue2': f.hue2 }, role: interactive ? undefined : 'img', 'aria-label': interactive ? undefined : label,
    children: [
      jsx('div', { className: 'h-idcard-dots' }),
      jsx('div', { className: 'h-idcard-hero', 'aria-hidden': true, children: hero }),
      jsxs('div', { className: 'h-idcard-top', 'aria-hidden': true, children: [
        jsx('div', { className: 'h-idcard-name', 'data-size': nameSize(name), children: name }),
        jsx('span', { className: 'h-idcard-tag', children: model.tag })
      ] }),
      serial ? jsx('div', { className: 'h-idcard-serial', 'aria-hidden': true, children: serial }) : null,
      jsx('div', { className: 'h-idcard-foot', 'aria-hidden': true, children: fields.map(x => jsxs('div', { className: 'h-idcard-field', children: [
        jsx('span', { className: 'h-idcard-label', children: x[0] }),
        jsx('span', { className: 'h-idcard-value', 'data-warn': !!x[2], children: x[1] })
      ] }, x[0])) }),
      jsx('div', { className: 'h-idcard-frame' }),
      jsx('div', { className: 'h-idcard-shine' })
    ] })

  // Everything on the back is also in the sheet's rows, so screen readers skip it.
  const groups = keyGroups(props.pk)
  const day = fmtDay(props.first)
  const posts = postCount(props.posts)
  const backFields = [day && ['First seen here', day], posts != null && ['Messages here', String(posts)],
    props.model && ['Model', shortModel(props.model)]].filter(Boolean)
  const back = interactive && scanner ? scannerBack(model, props, { groups, about: props.about, fields: backFields })
    : interactive && jsxs('div', { className: 'h-idcard h-idcard-back', 'aria-hidden': true, 'data-warn': warn,
    style: { '--hue': f.hue, '--hue2': f.hue2 }, children: [
      jsx('div', { className: 'h-idcard-dots' }),
      jsx('div', { className: 'h-idcard-stripe' }),
      jsxs('div', { className: 'h-idcard-keyblock', children: [
        jsx('span', { className: 'h-idcard-label', children: 'Key' }),
        groups.length
          ? jsx('div', { className: 'h-idcard-key', children: groups.map((g, i) => jsx('span', { children: g }, i)) })
          : jsx('span', { className: 'h-idcard-value', children: 'Unknown' })
      ] }),
      props.about ? jsx('div', { className: 'h-idcard-about', children: props.about }) : null,
      jsx('div', { className: 'h-idcard-foot', 'data-n': backFields.length, children: backFields.map(x => jsxs('div', { className: 'h-idcard-field', children: [
        jsx('span', { className: 'h-idcard-label', children: x[0] }),
        jsx('span', { className: 'h-idcard-value', children: x[1] })
      ] }, x[0])) }),
      jsx('div', { className: 'h-idcard-frame' }),
      jsx('div', { className: 'h-idcard-shine' })
    ] })

  return jsx('div', { className: 'h-idcard-stage', ref: stage, 'data-interactive': interactive,
    role: interactive ? 'button' : undefined, tabIndex: interactive ? 0 : undefined,
    'aria-pressed': interactive ? flipped : undefined, 'aria-label': interactive ? label : undefined,
    onClick: interactive ? flip : undefined,
    onKeyDown: interactive ? e => {
      // a native button acts once per press; holding the key must not keep turning the card
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (!e.repeat) flip() }
    } : undefined,
    children: jsx('div', { className: 'h-idcard-tilt', children: jsxs('div', { className: 'h-idcard-turn', ref: turn, children: [front, back] }) }) })
}

// A person's picture or face as the card's big picture. The saved card image draws a face but not a picture
// (the picture is a stranger's file: it stays out of anything that gets exported).
function PersonHero(props) {
  const uri = useAvatarUri(props.art.av && props.pk ? props.pk : '', props.art.av)
  if (uri) return jsx(PersonPhoto, { uri, size: 120, className: 'h-idcard-photo' })
  if (props.art.face) return jsx(PersonFace, { face: props.art.face, pk: props.pk, size: 120 })
  return null
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

// The first thing focused when a card opens is where focus returns when the last card closes, even
// after name -> agent -> name chains that remove each sheet's own button.
function ProfileLayer(props) {
  const [who, setWho] = useState(null)
  const opener = useRef(null)
  const shown = useRef(false)
  const open = useCallback(w => {
    if (!shown.current) { shown.current = true; opener.current = typeof document !== 'undefined' ? document.activeElement : null }
    setWho(w)
  }, [])
  const close = useCallback(() => { shown.current = false; setWho(null) }, [])
  return jsxs(ProfileContext.Provider, { value: open, children: [
    props.children,
    who && jsx(ProfileSheet, { who, room: props.room, snap: props.snap, store: props.store, openSettings: props.openSettings, openDm: props.openDm,
      opener, onClose: close, onOpen: open, key: who.pk })
  ] })
}

// Tab and Shift+Tab stay inside a modal sheet: from `active`, which of `items` gets focus next, or
// null when the browser's own move stays inside. A focus that is outside the sheet comes back in.
function tabTarget(items, active, shift) {
  if (!items.length) return null
  const i = items.indexOf(active)
  if (i < 0) return shift ? items[items.length - 1] : items[0]
  if (shift && i === 0) return items[items.length - 1]
  if (!shift && i === items.length - 1) return items[0]
  return null
}

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'

// What the buttons under a card may do. Edit face: only on your own agent's card. Hide: only on someone
// else's card, and it hides their person (an agent's card hides its owner, as the People column does).
// Never on your own person or agent.
function cardActions(who, found, snap) {
  const myPk = snap && snap.me && snap.me.pk
  const myAgent = snap && snap.me && snap.me.agent && snap.me.agent.pk
  const hide = (pk, name) => (typeof pk === 'string' && pk && pk !== myPk && pk !== myAgent ? { pk, name: String(name || 'them') } : null)
  // Message: a private message goes person to person, so an agent's card offers its owner. Never to yourself.
  if (who.kind === 'agent' || found.agent) {
    const a = found.agent || {}
    const o = found.owner
    if (a.yours || (myAgent && who.pk === myAgent)) return { edit: true, hide: null, message: null }
    return { edit: false, hide: o && !o.you ? hide(o.pk, o.name) : null, message: o && !o.you ? hide(o.pk, o.name) : null }
  }
  const p = found.person || {}
  return { edit: false, hide: p.you ? null : hide(who.pk, p.name || who.name), message: p.you ? null : hide(who.pk, p.name || who.name) }
}

function ProfileSheet(props) {
  const { who, room, snap } = props
  const sheet = useRef(null)
  const close = useRef(null)
  const cardRef = useRef(null)
  const keepFocus = useRef(false)
  const [busy, setBusy] = useState('')
  const canCopy = useCanCopyImage()
  const found = findMember(room, who.pk)
  // what this person looks like: their picture (while pictures are on) and face, from the snapshot
  const looks = useContext(PeopleContext)
  const entry = looks.people[who.pk]
  const art = entry ? (looks.show ? entry : entry.face ? { face: entry.face } : undefined) : undefined
  const [card, setCard] = useState(null)
  const [flipped, setFlipped] = useState(false)
  const isAgent = who.kind === 'agent' || !!found.agent

  useEffect(() => {
    const esc = e => {
      if (e.key === 'Escape') { e.stopPropagation(); props.onClose(); return }
      if (e.key !== 'Tab' || !sheet.current) return
      const items = Array.from(sheet.current.querySelectorAll(FOCUSABLE)).filter(el => el.getClientRects().length > 0)
      const next = tabTarget(items, document.activeElement, e.shiftKey)
      if (next) { e.preventDefault(); next.focus() }
    }
    const off = P.listen(document, 'keydown', esc)
    const closeBtn = close.current && close.current.querySelector('button')
    if (closeBtn) closeBtn.focus()
    const el = sheet.current
    const s = el && motion.spring({ from: 0, to: 1, k: SPRING.enter.k, c: SPRING.enter.c, onUpdate: x => {
      el.style.opacity = String(clamp(x * 1.6, 0, 1))
      el.style.transform = x === 1 ? '' : 'translateY(' + ((1 - x) * 16).toFixed(2) + 'px) scale(' + (0.94 + 0.06 * x).toFixed(4) + ')'
    } })
    return () => {
      off(); s && s.stop()
      const back = props.opener && props.opener.current
      if (!keepFocus.current && back && back.isConnected && back.focus) try { back.focus() } catch (_) { /* gone */ }
    }
  }, [])

  // a person's published interest card, fetched when theirs opens
  useEffect(() => {
    if (isAgent) return
    let live = true
    P.rest('/profile?pk=' + encodeURIComponent(who.pk)).then(r => { if (live) setCard(r || {}) }).catch(() => { if (live) setCard({}) })
    return () => { live = false }
  }, [who.pk])

  // the sheet's card turns over (click, Enter/Space, or the Flip button) and tilts
  const flip = { interactive: true, flipped, onFlip: setFlipped, cardRef }
  const body = isAgent ? agentSheet(who, found, snap, props.onOpen, flip) : personSheet(who, found, card, props.onOpen, flip, art)

  // buttons under the card: save or copy it as an image, edit your own agent's face, hide someone else
  const act = cardActions(who, found, snap)
  const cardName = body.card.props.name
  const image = () => cardImage(body.card.props, cardRef.current)
  const save = async () => {
    setBusy('save')
    try {
      const { blob, filename } = await image()
      if (await P.saveFile(blob, filename)) P.toast('info', 'Saved ' + cardName + '’s card.')
      else P.toast('error', 'Couldn’t save the image here. Try Copy image.')
    } catch (_) { P.toast('error', 'Couldn’t save the image here. Try Copy image.') }
    setBusy('')
  }
  const copyImage = async () => {
    setBusy('copy')
    try {
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': image().then(r => r.blob) })])
      P.toast('info', 'Copied ' + cardName + '’s card.')
    } catch (_) { P.toast('error', 'Couldn’t copy the image here. Try Save image.') }
    setBusy('')
  }
  const editFace = () => {
    keepFocus.current = true
    wantFaceEditor()
    props.onClose()
    if (props.openSettings) props.openSettings()
  }
  const messageThem = () => {
    if (!act.message || !props.openDm) return
    keepFocus.current = true
    props.onClose()
    props.openDm(act.message.pk)
  }
  const hideThem = async () => {
    if (!act.hide || !props.store) return
    try {
      await props.store.post('/people/hide', { pk: act.hide.pk, name: act.hide.name }, 'Hid ' + act.hide.name + ' and their agent. Undo in Settings.')
      props.onClose()
    } catch (_) { /* toasted */ }
  }
  const saveBtn = jsx(K.Button, { variant: 'outline', size: 'sm', disabled: !!busy, onClick: save, children: [jsx(K.Icon, { name: 'save', size: 13 }, 'i'), 'Save image'] }, 'save')
  const copyBtn = canCopy ? jsx(K.Button, { variant: 'outline', size: 'sm', disabled: !!busy, onClick: copyImage, children: [jsx(K.Icon, { name: 'copy', size: 13 }, 'i'), 'Copy image'] }, 'copy') : null
  return jsx('div', { className: 'hx h-profile-scrim', onClick: e => { if (e.target === e.currentTarget) props.onClose() }, children:
    jsxs('div', { className: 'h-profile', ref: sheet, role: 'dialog', 'aria-modal': true, 'aria-label': body.title, children: [
      jsxs('div', { className: 'h-profile-head', children: [
        jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'Flip card', 'aria-pressed': flipped, onClick: () => setFlipped(v => !v),
          children: jsx(K.Icon, { name: 'refresh', size: 14 }) }),
        jsx('span', { ref: close, children:
          jsx(K.Button, { variant: 'ghost', size: 'icon', 'aria-label': 'Close', onClick: props.onClose, children: jsx(K.Icon, { name: 'close', size: 14 }) }) })
      ] }),
      body.card,
      jsxs('div', { className: 'h-profile-actions', children: [
        saveBtn, copyBtn,
        act.message && jsx(FriendAction, { rel: ((snap.dms || {}).rel || {})[act.message.pk] || '', name: act.message.name, pk: act.message.pk,
          store: props.store, onMessage: props.openDm ? messageThem : null }, 'friend'),
        act.edit && jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: editFace, children: [jsx(K.Icon, { name: 'edit', size: 13 }, 'i'), 'Edit face'] }, 'edit'),
        act.hide && props.store && jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: hideThem, children: [jsx(K.Icon, { name: 'eye-closed', size: 13 }, 'i'),
          jsx('span', { className: 'h-trunc', style: { maxWidth: 190 }, children: 'Hide ' + act.hide.name }, 't')] }, 'hide')
      ] }),
      jsx('div', { className: 'h-profile-body', children: body.rows })
    ] }) })
}

// The card's private-message button, by who you are to each other: friends get Message, someone you asked shows
// "Request sent", someone who asked you can be accepted here, anyone else gets Add friend. A friend request carries
// no text. (An agent's card reaches its owner, never the agent.)
function FriendAction(props) {
  const { rel, name, pk, store } = props
  const post = async (path, okMsg) => { try { await store.post(path, { pk }, okMsg) } catch (_) { /* toasted */ } }
  const label = text => jsx('span', { className: 'h-trunc', style: { maxWidth: 190 }, children: text }, 't')
  if (rel === 'friend') {
    return props.onMessage ? jsx(K.Button, { variant: 'secondary', size: 'sm', onClick: props.onMessage, children: [jsx(K.Icon, { name: 'send', size: 13 }, 'i'), label('Message ' + name)] }) : null
  }
  if (!store) return null
  if (rel === 'sent') {
    return jsx(K.Button, { variant: 'secondary', size: 'sm', disabled: true, 'aria-disabled': true, children: [jsx(K.Icon, { name: 'clock', size: 13 }, 'i'), 'Request sent'] })
  }
  if (rel === 'request') {
    return jsx(K.Button, { variant: 'primary', size: 'sm', onClick: () => post('/friend/accept', name + ' is now your friend.'), children: [jsx(K.Icon, { name: 'add', size: 13 }, 'i'), label('Accept ' + name)] })
  }
  return jsx(K.Button, { variant: 'secondary', size: 'sm', onClick: () => post('/friend/request', 'Friend request sent to ' + name + '.'), children: [jsx(K.Icon, { name: 'add', size: 13 }, 'i'), label('Add friend')] })
}

function agentSheet(who, found, snap, onOpen, flip) {
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
  const serial = cardSerial(who.pk)
  const activity = activityText(a.first, a.posts)
  return {
    title: name + ', ' + (mine ? 'your agent' : ownerName + "'s agent"),
    card: jsx(IdCard, Object.assign({ kind: 'agent', name, pk: who.pk, face, state, fields, warn, about: vibe, model,
      first: a.first, posts: a.posts }, flip)),
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
      serial ? cardNumberRow(serial, who.pk, mine ? 'your agent’s' : 'its') : null,
      model && jsxs('div', { className: 'h-profile-row', children: [jsx(K.Icon, { name: 'sparkle', size: 13 }),
        jsx('span', { children: 'Last ran on ' + model + '.' })] }, 'm'),
      activity ? activityRow(activity) : null,
      mine && jsx('div', { className: 'h-faint h-small', children: shared
        ? 'Others see its vibe and model. Change this in Settings.'
        : 'Its card hides its vibe and model. Your agent still acts on its vibe in rooms and can repeat it, so keep it free of anything private.' }, 's'),
      !mine && found.owner && jsx('div', { children: jsx(ProfileButton, { who: { kind: 'person', pk: owner.pk, name: owner.name }, label: 'Show ' + ownerName,
        children: jsx('span', { className: 'h-small h-namelink', children: 'See ' + ownerName + '’s card' }) }) }, 'o')
    ]
  }
}

function personSheet(who, found, card, onOpen, flip, art) {
  const p = found.person || {}
  const name = p.name || who.name || 'Someone'
  const agents = p.agents || []
  const interests = (card && card.interests) || []
  const fields = [['Agents', agents.length ? agents.map(a => a.name).join(', ') : 'None here'], ['Status', STATUS_LABEL[statusKey(p)]]]
  const serial = cardSerial(who.pk)
  const activity = activityText(p.first, p.posts)
  return {
    title: name + (p.you ? ', you' : ''),
    card: jsx(IdCard, Object.assign({ kind: 'person', name, pk: who.pk, face: agents[0] && agents[0].face, fields, warn: !!p.impostor, online: isHere(p),
      agents, about: card && card.line, first: p.first, posts: p.posts, art }, flip)),
    rows: [
      card && card.line ? jsx('div', { className: 'h-profile-vibe', children: card.line }, 'l') : null,
      interests.length ? jsx('div', { className: 'h-chips', children: interests.map(t => jsx('span', { className: 'h-chip', children: t }, t)) }, 'i') : null,
      card && !card.line && !interests.length ? jsx('div', { className: 'h-faint h-small', children: 'No interest card published.' }, 'n') : null,
      card === null ? jsx('div', { className: 'h-faint h-small', children: 'Looking for their interest card…' }, 'w') : null,
      p.impostor && jsxs('div', { className: 'h-profile-row', children: [jsx(K.Icon, { name: 'warning', size: 13 }),
        jsx('span', { children: 'Someone else in this room already uses this name. This is a different key.' })] }, 'x'),
      serial ? cardNumberRow(serial, who.pk, p.you ? 'your' : 'their') : null,
      activity ? activityRow(activity) : null,
      agents.length ? jsx('div', { className: 'h-profile-agents', children: agents.map(a =>
        jsx(ProfileButton, { who: { kind: 'agent', pk: a.pk, name: a.name, face: a.face }, label: 'Show ' + a.name, children: [
          jsx(Face, { face: a.face, pk: a.pk, state: a.state, size: 24, name: a.name }, 'f'),
          jsx('span', { className: 'h-namelink', children: a.name }, 'n'),
          jsx('span', { className: 'h-faint h-small', children: STATE_LABEL[stateWord(a.state)] }, 's')
        ] }, a.pk)) }, 'a') : null
    ]
  }
}

// What the card number is, in words. It is only a label: the first 12 characters of the key are cheap to
// imitate, so the copy sends people to the full key on the card's back, and a button copies that key
// (the back can't be selected, since the stage turns on click). The full key also rides along for screen readers.
function cardNumberRow(serial, pk, whose) {
  const groups = keyGroups(pk)
  const copyKey = async () => {
    const ok = await P.copy(groups.join('').toLowerCase())
    P.toast(ok ? 'info' : 'error', ok ? 'Key copied.' : 'Couldn’t reach the clipboard here. Flip the card to read the key.')
  }
  return jsxs('div', { className: 'h-profile-row h-profile-keyrow', children: [jsx(K.Icon, { name: 'lock', size: 13 }),
    jsxs('span', { className: 'h-grow', children: ['Card number ', jsx('span', { className: 'h-idcard-num', children: serial }, 'n'),
      ' is short for ' + whose + ' key. To be certain, compare the full key on the back of the card.',
      groups.length ? jsx('span', { className: 'h-idcard-sr', children: ' Full key: ' + groups.join(' ') + '.' }, 'k') : null] }),
    groups.length ? jsx(K.Button, { variant: 'outline', size: 'sm', onClick: copyKey, 'aria-label': 'Copy full key',
      children: [jsx(K.Icon, { name: 'copy', size: 13 }, 'i'), 'Copy key'] }, 'b') : null] }, 'c')
}

function activityRow(text) {
  return jsxs('div', { className: 'h-profile-row', children: [jsx(K.Icon, { name: 'clock', size: 13 }), jsx('span', { children: text })] }, 'act')
}

// "anthropic/claude-sonnet-5-5" -> "claude-sonnet-5-5": the provider prefix rarely fits a card corner.
function shortModel(m) {
  const s = String(m || '')
  return s.includes('/') ? s.split('/').pop() : s
}
