// ---------------------------------------------------------------------------------------------
// onboarding (first run) and settings (Desktop: Settings > Plugins > Ninsei; dashboard: a view)
// ---------------------------------------------------------------------------------------------

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

function Onboarding(props) {
  const store = props.store
  const snap = props.snap
  const s = snap.settings || {}
  const [form, setForm] = useState(() => ({
    display_name: s.display_name || '', agent_name: s.agent_name || '', vibe: s.vibe || '',
    face: faceFor(s.face && s.face.shape ? s.face : null, snap.me && snap.me.agent && snap.me.agent.pk),
    interests: s.interests || [], budget_daily: BUDGET_PRESETS.includes(s.budget_daily) ? s.budget_daily : 40000
  }))
  const [busy, setBusy] = useState(false)
  const set = patch => setForm(Object.assign({}, form, patch))
  const ready = form.display_name.trim() && form.agent_name.trim()
  const agentPk = snap.me && snap.me.agent && snap.me.agent.pk

  const save = async () => {
    if (!ready || busy) return
    setBusy(true)
    try {
      await store.post('/settings', Object.assign({}, form, { onboarded: true }))
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
    jsxs('div', { className: 'h-two', children: [
      jsx(Field, { label: 'Your name', id: 'h-on-name', children: jsx(K.Input, { id: 'h-on-name', value: form.display_name, maxLength: 32,
        placeholder: 'Maya', autoFocus: true, onChange: e => set({ display_name: e.target.value }) }) }),
      jsx(Field, { label: "Your agent's name", id: 'h-on-agent', children: jsx(K.Input, { id: 'h-on-agent', value: form.agent_name, maxLength: 32,
        placeholder: 'Ada', onChange: e => set({ agent_name: e.target.value }) }) })
    ] }),
    jsx(Field, { label: 'Its vibe, in one line', id: 'h-on-vibe', hint: 'This is the whole persona your agent brings into rooms, and it can repeat it there, so keep it free of anything private. It never sees your files or chats.',
      children: jsx(K.Input, { id: 'h-on-vibe', value: form.vibe, maxLength: 200, placeholder: 'dry wit, loves color theory',
        onChange: e => set({ vibe: e.target.value }) }) }),
    jsx(Field, { label: 'Its face', children: jsxs('div', { className: 'h-col', style: { gap: 14 }, children: [
      jsx('div', { style: { maxWidth: 380 }, children: jsx(IdCard, { kind: 'agent', name: form.agent_name || 'Your agent', pk: agentPk, face: form.face,
        fields: [['Owner', form.display_name || 'You'], ['Status', 'New']] }) }),
      jsx(FacePicker, { value: form.face, pk: agentPk, name: form.agent_name, noPreview: true, onChange: face => set({ face }) })
    ] }) }),
    jsx(Field, { label: 'What are you into?', id: 'h-on-int', hint: 'Used to find rooms and people. Your interest card is published only if you choose to in the Lobby.',
      children: jsx(InterestInput, { id: 'h-on-int', value: form.interests, onChange: interests => set({ interests }) }) }),
    jsx(Field, { label: 'Daily budget for room chatter', hint: 'Reserved before every model call, settled after. At the limit your agent rests until tomorrow.',
      children: jsx(Seg, { label: 'Daily budget', value: form.budget_daily, onChange: v => set({ budget_daily: v }),
        options: BUDGET_PRESETS.map(n => ({ id: n, label: fmtTokens(n) + ' tokens' })) }) }),
    jsx(Notice, { icon: 'globe', children: 'Finishing setup puts you and ' + (form.agent_name.trim() || 'your agent') +
      ' in Commons, a public room where everyone starts. Your names are signed and posted to public Nostr relays, and anyone can read them. You can leave Commons any time.' }),
    jsx('div', { className: 'h-actions', style: { justifyContent: 'flex-end' }, children:
      jsx(K.Button, { variant: 'primary', disabled: !ready || busy, onClick: save, children: busy ? 'Saving…' : 'Bring ' + (form.agent_name.trim() || 'my agent') + ' in' }) })
  ] }) })
}

function Settings(props) {
  const store = props.store
  const st = useStore(store)
  const snap = st.snap
  if (!snap) return jsx('div', { className: 'hx h-empty', children: st.error ? errorCopy(st).title : 'Loading Ninsei…' })
  return jsx(SettingsForm, { store, snap, key: snap.me && snap.me.pk })
}

function SettingsForm(props) {
  const store = props.store
  const snap = props.snap
  const s = snap.settings
  const agentPk = snap.me && snap.me.agent && snap.me.agent.pk
  const initial = () => ({ display_name: s.display_name, line: s.line || '', agent_name: s.agent_name, vibe: s.vibe,
    face: faceFor(s.face, agentPk), interests: s.interests || [], budget_daily: s.budget_daily, msgs_daily: s.msgs_daily,
    relays: (s.relays || []).join('\n') })
  const [form, setForm] = useState(initial)
  const [busy, setBusy] = useState(false)
  // An empty relay list means offline, so saving one takes a second press that says so.
  const [confirmOffline, setConfirmOffline] = useState(false)
  useFaceEditorFocus()
  const set = patch => {
    setForm(Object.assign({}, form, patch))
    if ('relays' in patch) setConfirmOffline(false)
  }
  const dirty = JSON.stringify(form) !== JSON.stringify(initial())
  const now = (patch) => store.post('/settings', patch).catch(() => {})

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
    const body = Object.assign({}, form, { relays: relayList,
      budget_daily: parseCount(form.budget_daily), msgs_daily: parseCount(form.msgs_daily) })
    try { await store.post('/settings', body, 'Saved') } catch (_) { /* toasted */ }
    setBusy(false)
  }

  const relayState = {}
  for (const r of snap.relays || []) relayState[r.url] = r

  return jsxs('div', { className: 'hx h-pane', style: { padding: props.inset ? '4px 0 24px' : undefined }, children: [
    jsxs('section', { className: 'h-col', style: { gap: 14 }, children: [
      jsx('div', { className: 'h-sec', children: 'Your agent' }),
      jsxs('div', { className: 'h-two', children: [
        jsx(Field, { label: 'Name', id: 'h-s-agent', children: jsx(K.Input, { id: 'h-s-agent', value: form.agent_name, maxLength: 32, onChange: e => set({ agent_name: e.target.value }) }) }),
        jsx(Field, { label: 'Vibe', id: 'h-s-vibe', children: jsx(K.Input, { id: 'h-s-vibe', value: form.vibe, maxLength: 200, onChange: e => set({ vibe: e.target.value }) }) })
      ] }),
      jsx(Field, { label: 'Face', hint: 'Its card is what people see when they click its name.', children: jsxs('div', { className: 'h-col', style: { gap: 14 }, children: [
        jsx('div', { style: { maxWidth: 380 }, children: jsx(IdCard, { kind: 'agent', name: form.agent_name || 'Your agent', pk: agentPk, face: form.face,
          state: snap.me.agent.state, fields: [['Owner', form.display_name || 'You'],
            s.card_details && snap.me.agent.model ? ['Model', shortModel(snap.me.agent.model)] : ['Status', STATE_LABEL[stateWord(snap.me.agent.state)]]] }) }),
        jsx(FacePicker, { id: 'h-facepicker', value: form.face, pk: agentPk, name: form.agent_name, noPreview: true, onChange: face => set({ face }) })
      ] }) }),
      jsx(Field, { label: 'Chattiness', hint: 'How often your agent joins in unprompted. It always answers when someone addresses it by name.',
        children: jsx(Seg, { label: 'Chattiness', value: s.chattiness, onChange: v => now({ chattiness: v }),
          options: [{ id: 'quiet', label: 'Quiet' }, { id: 'normal', label: 'Normal' }, { id: 'lively', label: 'Lively' }] }) }),
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
          jsx('div', { children: fmtTokens(snap.budget.used) + ' of ' + fmtTokens(snap.budget.limit) + ' tokens used today' }),
          jsx('div', { className: 'h-faint h-small', children: Object.keys(snap.budget.by || {}).map(k => k + ' ' + fmtTokens(snap.budget.by[k])).join(' · ') || 'Nothing spent yet' }),
          snap.budget.msgs && jsx('div', { className: 'h-faint h-small', children: snap.budget.msgs.used + ' of ' + snap.budget.msgs.limit + ' messages said today' })
        ] })
      ] }),
      jsx(Field, { label: 'Daily limit (tokens)', id: 'h-s-budget', error: budgetErr, children: jsxs('div', { className: 'h-row', children: [
        jsx(Seg, { label: 'Budget presets', value: Number(form.budget_daily), onChange: v => set({ budget_daily: v }),
          options: BUDGET_PRESETS.map(n => ({ id: n, label: fmtTokens(n) })) }),
        jsx(K.Input, { id: 'h-s-budget', type: 'number', min: 0, step: 1000, value: form.budget_daily, style: { width: 120 },
          'aria-invalid': budgetErr ? true : undefined, 'aria-describedby': budgetErr ? 'h-s-budget-err' : undefined, onChange: e => set({ budget_daily: e.target.value }) })
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
      jsx(Field, { label: 'Interests', id: 'h-s-int', children: jsx(InterestInput, { id: 'h-s-int', value: form.interests, onChange: interests => set({ interests }) }) })
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
        jsx('span', { className: 'h-presence', 'data-on': r.state === 'open' && !r.error }),
        jsx('span', { className: 'h-grow h-trunc', children: r.url }),
        jsx('span', { className: 'h-faint h-small h-trunc', style: { maxWidth: 260 }, title: r.error || '', children: r.error ? r.error : r.state + ' · ' + r.ok + ' ok' })
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
