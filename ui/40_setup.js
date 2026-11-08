// ---------------------------------------------------------------------------------------------
// onboarding (first run) and settings (Desktop: Settings > Plugins > Ninsei; dashboard: a view)
// ---------------------------------------------------------------------------------------------

// A relay that said "slow down" gets nothing from us for a while; say so, and when it comes back.
function relayNote(r) {
  if (r.resting_s > 0) return 'Resting: it asked us to slow down. Back in ' + (r.resting_s < 90 ? r.resting_s + ' s' : Math.ceil(r.resting_s / 60) + ' min')
  return r.error ? r.error : r.state + ' · ' + r.ok + ' ok'
}

// A whole number typed into a limit field, or null when it is empty or not a number (never a silent 0).
function parseCount(v) {
  const t = String(v == null ? '' : v).trim()
  return /^\d{1,9}$/.test(t) ? parseInt(t, 10) : null
}
const BUDGET_MAX = 5000000   // the engine's own caps
const MSGS_MAX = 2000
function limitError(v, max, unit, example) {
  const n = parseCount(v)
  if (n === null) return 'Enter a whole number of ' + unit + ', like ' + example + '.'
  if (n > max) return 'The most is ' + max.toLocaleString('en-US') + ' ' + unit + '.'
  return ''
}

// A daily token amount in words people can judge: "About 40 replies a day", the tokens under it, smaller.
function capFirst(t) {
  return t ? t[0].toUpperCase() + t.slice(1) : t
}
// A preset in replies, never past the message limit (the typed one in Settings, else the saved one), like the ring.
function budgetOption(n, b, msgsCap) {
  const cap = msgsCap != null ? msgsCap : (b && b.msgs && b.msgs.limit != null ? Number(b.msgs.limit) : null)
  const byTokens = repliesFor(n, b)
  const capped = cap != null && cap < byTokens
  return { id: n, label: jsxs('span', { className: 'h-seg-two', children: [
    jsx('span', { children: capFirst(repliesWords(capped ? cap : byTokens)) }),
    jsx('span', { className: 'h-vh', children: ', ' }),
    jsx('span', { className: 'h-seg-sub', children: fmtTokens(n) + ' tokens' + (capped ? ', message limit' : '') })
  ] }) }
}

// What a missing field keeps the Create button waiting for, said next to the button (aria-describedby).
function setupNeeds(form) {
  const you = !form.display_name.trim(), agent = !form.agent_name.trim()
  if (you && agent) return 'Add your name and your agent’s name to continue.'
  if (you) return 'Add your name to continue.'
  if (agent) return 'Add your agent’s name to continue.'
  return ''
}

// A sticky Save bar sits over the bottom of the scroll area: whatever gets focus underneath it is scrolled up above
// it (keyboard users never type into a hidden field), whichever element is the scroller (ours or the host's).
function useKeepAboveBar(ref) {
  useEffect(() => {
    const root = ref.current
    if (!root || !root.addEventListener) return
    const onFocus = e => {
      const bar = root.querySelector('.h-savebar')
      const t = e.target
      if (!bar || !t || bar.contains(t) || !t.getBoundingClientRect) return
      const over = t.getBoundingClientRect().bottom - bar.getBoundingClientRect().top
      if (over <= 0) return
      let sc = root.parentElement
      while (sc && !(sc.scrollHeight > sc.clientHeight && /auto|scroll/.test(getComputedStyle(sc).overflowY))) sc = sc.parentElement
      if (sc) sc.scrollTop += over + 12
    }
    return P.listen(root, 'focusin', onFocus)
  }, [])
}

function Onboarding(props) {
  const store = props.store
  const snap = props.snap
  const s = snap.settings || {}
  const [form, setForm] = useState(() => ({
    display_name: s.display_name || '', agent_name: s.agent_name || '', vibe: s.vibe || '',
    persona: s.persona || '', persona_source: s.persona_source || '',
    face: faceFor(s.face && s.face.shape ? s.face : null, snap.me && snap.me.agent && snap.me.agent.pk),
    interests: s.interests || [], budget_daily: BUDGET_PRESETS.includes(s.budget_daily) ? s.budget_daily : 40000,
    // how you look: no portrait until you pick one (nobody is given a face; "Surprise me" is you picking), and a
    // picture that waits here until setup is finished
    person_face: s.person_face || null, person_avatar: cleanAvatar(s.person_avatar),
    avatar: ''
  }))
  const [busy, setBusy] = useState(false)
  const [pick, setPick] = useState({ flags: [], truncated: false, open: false })   // page-only: never posted
  const set = patch => setForm(Object.assign({}, form, patch))
  const ready = form.display_name.trim() && form.agent_name.trim()
  const needs = setupNeeds(form)
  const agentPk = snap.me && snap.me.agent && snap.me.agent.pk

  const save = async () => {
    if (!ready || busy) return
    setBusy(true)
    try {
      const { avatar, person_face, person_avatar, ...rest } = form
      await store.post('/settings', Object.assign({}, rest, { person_face: person_face || {}, person_avatar: person_avatar || {}, onboarded: true }))
      // the picture is published only now: until setup is finished nothing about you has been sent anywhere
      if (avatar) { try { await store.post('/avatar', { img: avatar }) } catch (_) { /* toasted; it can be added in Settings */ } }
      nav().set('welcome')  // land on "Rooms for you", not an empty room view
    } catch (_) { /* toasted */ }
    setBusy(false)
  }

  return jsx('div', { className: 'h-scroll', children: jsxs('div', { className: 'h-pane', style: { maxWidth: 560 }, children: [
    jsxs('div', { className: 'h-hero', children: [
      jsx(Face, { face: form.face, pk: agentPk, state: busy ? 'activity: working' : 'activity: idle', size: 72 }),
      jsx('h1', { children: 'Welcome to Ninsei' }),
      jsx('div', { className: 'h-muted', style: { maxWidth: 420 }, children:
        'Rooms where people and their own agents hang out. Your agent comes with you, speaks politely, and only spends the budget you give it.' })
    ] }),
    jsx(HermesPicker, { onPick: p => applyProposal(p, set, setPick) }),
    jsxs('div', { className: 'h-two', children: [
      jsx(Field, { label: 'Your name', id: 'h-on-name', children: jsx(K.Input, { id: 'h-on-name', value: form.display_name, maxLength: 32,
        placeholder: 'Rowan', autoFocus: true, onChange: e => set({ display_name: e.target.value }) }) }),
      jsx(Field, { label: "Your agent's name", id: 'h-on-agent', children: jsx(K.Input, { id: 'h-on-agent', value: form.agent_name, maxLength: 32,
        placeholder: 'Pixel', onChange: e => set({ agent_name: e.target.value }) }) })
    ] }),
    jsx(Field, { label: 'Its vibe, in one line', id: 'h-on-vibe', hint: 'This short line is public: your agent brings it into rooms and can repeat it there, so keep it free of anything private. It never sees your files or chats.',
      children: jsxs('div', { className: 'h-col', style: { gap: 8 }, children: [
        jsx(K.Input, { id: 'h-on-vibe', value: form.vibe, maxLength: 200, placeholder: 'dry wit, loves color theory',
          onChange: e => set({ vibe: e.target.value }) }),
        jsx(VibePresets, { value: form.vibe, onPick: vibe => set({ vibe }) })
      ] }) }),
    jsx(PersonaField, { id: 'h-on-persona', value: form.persona, source: form.persona_source, pick, setPick, onChange: set }),
    // the card updates as you type; changing faces and pictures is optional, so it waits behind "Customize"
    jsx(Field, { label: 'Your agent’s card', children: jsx('div', { style: { maxWidth: 380 }, children: jsx(IdCard, { kind: 'agent', name: form.agent_name || 'Your agent', pk: agentPk, face: form.face,
      fields: [['Owner', form.display_name || 'You'], ['Status', 'New']] }) }) }),
    jsxs('details', { className: 'h-custom', children: [
      jsxs('summary', { children: [jsx('span', { children: 'Customize' }), jsx('span', { className: 'h-faint h-small', children: 'its face, your portrait or photo (optional)' })] }),
      jsxs('div', { className: 'h-col', style: { gap: 18, paddingTop: 12 }, children: [
        jsx(Field, { label: 'Its face', children: jsx(FacePicker, { value: form.face, pk: agentPk, name: form.agent_name, onChange: face => set({ face }) }) }),
        jsx(Field, { label: 'How you look', children: jsx(PersonLook, { id: 'h-on-look', pk: snap.me && snap.me.pk, name: form.display_name, stage: true,
          avatar: form.person_avatar, onAvatar: person_avatar => set({ person_avatar }),
          face: form.person_face, onFace: person_face => set({ person_face }), staged: form.avatar, hasPicture: !!form.avatar,
          art: { avatar: form.person_avatar || undefined, face: form.person_face || undefined },
          onPicture: avatar => set({ avatar }) }) })
      ] })
    ] }),
    jsx(Field, { label: 'What are you into?', id: 'h-on-int', hint: 'Used to find rooms and people. Your interest card is published only if you choose to in the Lobby.',
      children: jsx(InterestInput, { id: 'h-on-int', value: form.interests, onChange: interests => set({ interests }) }) }),
    jsx(Field, { label: 'Daily budget for room chatter', hint: 'Reserved before every model call, settled after. At the limit your agent rests until tomorrow.',
      children: jsx(Seg, { label: 'Daily budget', value: form.budget_daily, onChange: v => set({ budget_daily: v }),
        options: BUDGET_PRESETS.map(n => budgetOption(n, snap.budget)) }) }),
    jsx(Notice, { icon: 'globe', children: 'Finishing setup puts you and ' + (form.agent_name.trim() || 'your agent') +
      ' in Commons, a public room where everyone starts. Your names are signed and posted to public Nostr relays, and anyone can read them. You can leave Commons any time.' }),
    jsxs('div', { className: 'h-actions', style: { justifyContent: 'flex-end' }, children: [
      needs && jsx('span', { id: 'h-on-need', className: 'h-faint h-small', children: needs }),
      jsx(K.Button, { variant: 'primary', disabled: !ready || busy, onClick: save, 'aria-describedby': needs ? 'h-on-need' : undefined,
        children: busy ? 'Saving…' : 'Bring ' + (form.agent_name.trim() || 'my agent') + ' in' })
    ] })
  ] }) })
}

function Settings(props) {
  const store = props.store
  const st = useStore(store)
  const snap = st.snap
  if (!snap) return jsx('div', { className: 'hx h-empty', children: st.error ? errorCopy(st).title : 'Loading Ninsei…' })
  return jsx(SettingsForm, { store, snap, key: snap.me && snap.me.pk })
}

const AWAY_CHOICES = [
  { id: 'named', label: 'Answers only when named', hint: 'Replies to someone who names it or replies to it. It starts no chatter and drafts no offers.' },
  { id: 'quiet', label: 'Stays quiet', hint: 'Answers only you. No offers, no games.' },
  { id: 'chat', label: 'Chats as usual', hint: 'Behaves as it does when you are here.' }
]

function SettingsForm(props) {
  const store = props.store
  const snap = props.snap
  const s = snap.settings
  const agentPk = snap.me && snap.me.agent && snap.me.agent.pk
  const initial = () => ({ display_name: s.display_name, line: s.line || '', agent_name: s.agent_name, vibe: s.vibe,
    persona: s.persona || '', persona_source: s.persona_source || '',
    face: faceFor(s.face, agentPk), interests: s.interests || [], budget_daily: s.budget_daily, msgs_daily: s.msgs_daily,
    person_face: s.person_face || null, person_avatar: cleanAvatar(s.person_avatar), relays: (s.relays || []).join('\n') })
  const [form, setForm] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [pick, setPick] = useState({ flags: [], truncated: false, open: false })   // page-only: never posted
  // An empty relay list means offline, so saving one takes a second press that says so.
  const [confirmOffline, setConfirmOffline] = useState(false)
  useFaceEditorFocus()
  const root = useRef(null)
  useKeepAboveBar(root)
  const set = patch => {
    setForm(Object.assign({}, form, patch))
    if ('relays' in patch) setConfirmOffline(false)
  }
  const dirty = JSON.stringify(form) !== JSON.stringify(initial())
  const now = (patch) => store.post('/settings', patch).catch(() => {})
  // your picture is published the moment you choose it (or take it away), apart from the Save button
  const [picBusy, setPicBusy] = useState(false)
  const mePk = snap.me && snap.me.pk
  const myArt = (snap.people && snap.people[mePk]) || null
  const setPicture = async img => {
    setPicBusy(true)
    try { await store.post('/avatar', { img }, img ? 'Picture published' : 'Picture removed') } catch (_) { /* toasted */ }
    setPicBusy(false)
  }

  const budgetErr = limitError(form.budget_daily, BUDGET_MAX, 'tokens', '40000')
  const msgsErr = limitError(form.msgs_daily, MSGS_MAX, 'messages', '60')
  const relayList = form.relays.split(/\s+/).filter(Boolean)
  const offlineNow = (s.relays || []).length === 0
  const goingOffline = relayList.length === 0 && !offlineNow
  const save = async () => {
    if (budgetErr || msgsErr) return
    if (goingOffline && !confirmOffline) { setConfirmOffline(true); return }
    setConfirmOffline(false)
    setBusy(true)
    const body = Object.assign({}, form, { relays: relayList, person_face: form.person_face || {}, person_avatar: form.person_avatar || {},
      budget_daily: parseCount(form.budget_daily), msgs_daily: parseCount(form.msgs_daily) })
    try {
      const out = await store.post('/settings', body, 'Saved')
      // the engine looks the saved text over once more: what it finds (also anything typed since the import) shows now
      if (out && out.flags) setPick(prev => Object.assign({}, prev, { flags: out.flags }))
    } catch (_) { /* toasted */ }
    setBusy(false)
  }

  const relayState = {}
  for (const r of snap.relays || []) relayState[r.url] = r

  // what the typed limit buys, in replies: at the agent's recent average reply, and never past the message limit
  const limitTokens = parseCount(form.budget_daily)
  const perReply = (snap.budget && snap.budget.reply_tokens) || REPLY_TOKENS_GUESS
  const limitReplies = limitTokens == null ? null : repliesFor(limitTokens, snap.budget)
  const msgsCap = parseCount(form.msgs_daily)
  // a preset already says its replies; a typed number gets them here
  const per = 'at ' + fmtTokens(perReply) + ' tokens a reply (' + (snap.budget && snap.budget.reply_tokens ? 'your agent’s recent average' : 'a typical reply') + ')'
  const budgetHint = limitReplies == null ? undefined
    : (BUDGET_PRESETS.includes(limitTokens) ? capFirst(per) : capFirst(repliesWords(limitReplies)) + ', ' + per) +
      (msgsCap != null && msgsCap < limitReplies ? '. The message limit below stops it at ' + msgsCap + ' replies first.' : '.')

  return jsxs('div', { className: 'hx h-pane h-settings', ref: root, style: { padding: props.inset ? '4px 0 24px' : undefined }, children: [
    jsxs('section', { className: 'h-col', style: { gap: 14 }, children: [
      jsx('div', { className: 'h-sec', children: 'Your agent' }),
      jsx(HermesPicker, { collapsible: true, onPick: p => applyProposal(p, set, setPick) }),
      jsxs('div', { className: 'h-two', children: [
        jsx(Field, { label: 'Name', id: 'h-s-agent', children: jsx(K.Input, { id: 'h-s-agent', value: form.agent_name, maxLength: 32, onChange: e => set({ agent_name: e.target.value }) }) }),
        jsx(Field, { label: 'Vibe', id: 'h-s-vibe', children: jsx(K.Input, { id: 'h-s-vibe', value: form.vibe, maxLength: 200, onChange: e => set({ vibe: e.target.value }) }) })
      ] }),
      jsx(VibePresets, { value: form.vibe || '', onPick: vibe => set({ vibe }) }),
      jsx(PersonaField, { id: 'h-s-persona', value: form.persona, source: form.persona_source, pick, setPick, onChange: set }),
      jsx(Field, { label: 'Face', hint: 'Its card is what people see when they click its name.', children: jsxs('div', { className: 'h-col', style: { gap: 14 }, children: [
        jsx('div', { style: { maxWidth: 380 }, children: jsx(IdCard, { kind: 'agent', name: form.agent_name || 'Your agent', pk: agentPk, face: form.face,
          state: snap.me.agent.state, fields: [['Owner', form.display_name || 'You'],
            s.card_details && snap.me.agent.model ? ['Model', shortModel(snap.me.agent.model)] : ['Status', STATE_LABEL[stateWord(snap.me.agent.state)]]] }) }),
        jsx(FacePicker, { id: 'h-facepicker', value: form.face, pk: agentPk, name: form.agent_name, onChange: face => set({ face }) })
      ] }) }),
      jsx(Field, { label: 'Chattiness', hint: 'How often your agent joins in unprompted. It always answers when someone addresses it by name.',
        children: jsx(Seg, { label: 'Chattiness', value: s.chattiness, onChange: v => now({ chattiness: v }),
          options: [{ id: 'quiet', label: 'Quiet' }, { id: 'normal', label: 'Normal' }, { id: 'lively', label: 'Lively' }] }) }),
      jsx(Field, { label: 'When I’m away, my agent…', hint: 'Away means Ninsei has not been open on your screen for 15 minutes, whatever status you show. It always answers you.',
        children: jsxs('div', { className: 'h-col', style: { gap: 8 }, children: [
          jsx(Seg, { label: 'When I am away', value: s.away_mode || 'named', onChange: v => now({ away_mode: v }),
            options: AWAY_CHOICES.map(c => ({ id: c.id, label: c.label })) }),
          jsx('div', { className: 'h-col', style: { gap: 2 }, children: AWAY_CHOICES.map(c => jsxs('div', { className: 'h-small', 'data-on': (s.away_mode || 'named') === c.id,
            style: { opacity: (s.away_mode || 'named') === c.id ? 1 : 0.6 }, children: [jsx('b', { children: c.label }), ' ' + c.hint] }, c.id)) })
        ] }) }),
      jsx(K.Toggle, { checked: !!s.offers, onChange: v => now({ offers: v }), label: 'Offers to build things',
        description: 'Your agent may propose a small web toy when a room keeps circling an idea. Only you can accept, and your own Hermes builds it.' }),
      jsx(K.Toggle, { checked: !!s.share_budget, onChange: v => now({ share_budget: v }), label: "Show my agent's budget to the room",
        description: 'Others see how much of today’s budget your agent has used.' }),
      jsx(K.Toggle, { checked: !!s.card_details, onChange: v => now({ card_details: v }), label: "Show my agent's vibe and model on its card",
        description: 'People in your rooms see the vibe you wrote and the model your agent last ran on, on its card. Off unless you turn it on. Your agent can still repeat its vibe in a room either way.' })
    ] }),
    jsxs('section', { className: 'h-col', style: { gap: 14 }, children: [
      jsx('div', { className: 'h-sec', children: 'Budget' }),
      jsxs('div', { className: 'h-row', style: { gap: 12 }, children: [
        jsx(BudgetRing, { budget: snap.budget, size: 36, stroke: 3.5 }),
        jsxs('div', { className: 'h-grow', children: [
          jsx('div', { children: fmtTokens(snap.budget.used) + ' of ' + fmtTokens(snap.budget.limit) + ' tokens used today' +
            (repliesLeftWords(snap.budget) ? ' · ' + repliesLeftWords(snap.budget) : '') }),
          jsx('div', { className: 'h-faint h-small', children: Object.keys(snap.budget.by || {}).map(k => k + ' ' + fmtTokens(snap.budget.by[k])).join(' · ') || 'Nothing spent yet' }),
          othersLine(snap.budget) && jsx('div', { className: 'h-faint h-small', children: othersLine(snap.budget) }),
          snap.budget.msgs && jsx('div', { className: 'h-faint h-small', children: snap.budget.msgs.used + ' of ' + snap.budget.msgs.limit + ' messages said today' })
        ] })
      ] }),
      snap.budget.others && snap.budget.others.spent && jsx(Notice, { icon: 'clock', role: 'status', children: OTHERS_SPENT }),
      jsx(Field, { label: 'Others can use', hint: 'The most of the daily budget, and of the message limit, that people other than you can use by talking to your agent. It halves while you are away, and you always keep the rest.',
        children: jsx(Seg, { label: 'Others can use', value: s.stranger_share == null ? 0.5 : s.stranger_share, onChange: v => now({ stranger_share: v }),
          options: [{ id: 0.25, label: 'A quarter' }, { id: 0.5, label: 'Half' }, { id: 0.75, label: 'Three quarters' }] }) }),
      jsx(Field, { label: 'Daily limit', id: 'h-s-budget', error: budgetErr, hint: budgetErr ? undefined : budgetHint, hintId: 'h-s-budget-hint',
        children: jsxs('div', { className: 'h-row', style: { flexWrap: 'wrap' }, children: [
        jsx(Seg, { label: 'Budget presets', value: Number(form.budget_daily), onChange: v => set({ budget_daily: v }),
          options: BUDGET_PRESETS.map(n => budgetOption(n, snap.budget, msgsCap)) }),
        jsxs('span', { className: 'h-row', style: { gap: 6 }, children: [
          jsx(K.Input, { id: 'h-s-budget', type: 'number', min: 0, step: 1000, value: form.budget_daily, style: { width: 120 }, 'aria-label': 'Daily limit in tokens',
            'aria-invalid': budgetErr ? true : undefined, 'aria-describedby': budgetErr ? 'h-s-budget-err' : 'h-s-budget-hint', onChange: e => set({ budget_daily: e.target.value }) }),
          jsx('span', { className: 'h-faint h-small', 'aria-hidden': true, children: 'tokens' })
        ] })
      ] }) }),
      jsx(Field, { label: 'Daily limit (messages)', id: 'h-s-msgs', error: msgsErr,
        hint: 'How many messages your agent may say in rooms each day, across all rooms. At the limit it rests until tomorrow, even with tokens left.',
        children: jsx(K.Input, { id: 'h-s-msgs', type: 'number', min: 0, max: 2000, step: 10, value: form.msgs_daily, style: { width: 120 },
          'aria-invalid': msgsErr ? true : undefined, 'aria-describedby': msgsErr ? 'h-s-msgs-err' : undefined, onChange: e => set({ msgs_daily: e.target.value }) }) })
    ] }),
    jsxs('section', { className: 'h-col', style: { gap: 14 }, children: [
      jsx('div', { className: 'h-sec', children: 'You' }),
      jsxs('div', { className: 'h-two', children: [
        jsx(Field, { label: 'Display name', id: 'h-s-name', children: jsx(K.Input, { id: 'h-s-name', value: form.display_name, maxLength: 32, onChange: e => set({ display_name: e.target.value }) }) }),
        jsx(Field, { label: 'One line about you', id: 'h-s-line', children: jsx(K.Input, { id: 'h-s-line', value: form.line, maxLength: 200, onChange: e => set({ line: e.target.value }) }) })
      ] }),
      jsx(Field, { label: 'Interests', id: 'h-s-int', children: jsx(InterestInput, { id: 'h-s-int', value: form.interests, onChange: interests => set({ interests }) }) }),
      jsx(Field, { label: 'How you look', children: jsx(PersonLook, { id: 'h-s-look', pk: mePk, name: form.display_name,
        avatar: form.person_avatar, onAvatar: person_avatar => set({ person_avatar }),
        face: form.person_face, onFace: person_face => set({ person_face }),
        art: Object.assign({}, myArt || {}, { avatar: form.person_avatar || undefined, face: form.person_face || undefined }),
        hasPicture: !!(myArt && myArt.av), busy: picBusy, onPicture: setPicture }) }),
      jsx(Field, { label: 'Show profile pictures', hint: 'Pictures are other people’s files, shown to you as small images. Nobody keeps only faces and initials on your screen, and Ninsei stops keeping their pictures. Your own is not affected.',
        children: jsx(Seg, { label: 'Show profile pictures', value: s.show_avatars || 'everyone', onChange: v => now({ show_avatars: v }),
          options: [{ id: 'everyone', label: 'Everyone in my rooms' }, { id: 'nobody', label: 'Nobody' }] }) })
    ] }),
    jsxs('section', { className: 'h-col', style: { gap: 10 }, children: [
      jsx('div', { className: 'h-sec', children: 'Hidden people' }),
      jsx('div', { className: 'h-faint h-small', children: 'Only on your screen: their messages and their agents disappear, and your agent stops answering them. Nobody is told.' }),
      (snap.hidden || []).length === 0
        ? jsx('div', { className: 'h-faint h-small', children: 'Nobody hidden. Use the hide button next to a name in a room.' })
        : jsx('div', { className: 'h-col', style: { gap: 0 }, children: snap.hidden.map(h => jsxs('div', { className: 'h-relay', children: [
          jsx('span', { className: 'h-grow h-trunc', children: h.name }),
          jsx('span', { className: 'h-faint h-small', children: fmtAgo(h.at) }),
          jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: () => store.post('/people/unhide', { pk: h.pk }, 'Showing ' + h.name + ' again').catch(() => {}), children: 'Unhide' })
        ] }, h.pk)) })
    ] }),
    jsxs('section', { className: 'h-col', style: { gap: 10 }, children: [
      jsx('div', { className: 'h-sec', children: 'Relays' }),
      offlineNow && jsx(Notice, { icon: 'warning', role: 'status', children: 'Offline: no relays set. Nothing you or your agent say leaves this machine, and messages wait as not delivered. Add a relay below to go back online.' }),
      jsx('div', { className: 'h-col', style: { gap: 0 }, children: (snap.relays || []).map(r => jsxs('div', { className: 'h-relay', children: [
        jsx('span', { className: 'h-presence', 'data-on': r.state === 'open' && !r.error && !r.resting_s }),
        jsx('span', { className: 'h-grow h-trunc', children: r.url }),
        jsx('span', { className: 'h-faint h-small h-trunc', style: { maxWidth: 260 }, title: r.error || '', children: relayNote(r) })
      ] }, r.url)) }),
      jsx(Field, { label: 'Relay list, one per line', id: 'h-s-relays', hint: 'Public Nostr relays. Ninsei writes to all of them and reads from all of them. Messages on public relays are public and effectively permanent.',
        children: jsx('textarea', { id: 'h-s-relays', className: 'h-ta', rows: 5, value: form.relays, spellCheck: false, onChange: e => set({ relays: e.target.value }) }) }),
      jsx('div', { children: jsx(K.Button, { variant: 'secondary', size: 'sm', onClick: () => store.post('/relays/reconnect', {}, 'Reconnecting to relays'), children: 'Reconnect' }) })
    ] }),
    jsxs('div', { className: 'h-actions h-savebar', children: [
      confirmOffline && goingOffline && jsx('div', { className: 'h-grow h-small', role: 'alert', children: 'The relay list is empty. Saving takes your agent offline: nothing leaves this machine until you add a relay.' }),
      dirty && jsx(K.Button, { variant: 'ghost', onClick: () => { setForm(initial()); setConfirmOffline(false) }, children: 'Revert' }),
      jsx(K.Button, { variant: 'primary', disabled: !dirty || busy || !!budgetErr || !!msgsErr, onClick: save,
        children: busy ? 'Saving…' : confirmOffline && goingOffline ? 'Save and go offline' : 'Save changes' })
    ] })
  ] })
}
