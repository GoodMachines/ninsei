// ---------------------------------------------------------------------------------------------
// onboarding (first run) and settings (Desktop: Settings > Plugins > Ninsei; dashboard: a view)
// ---------------------------------------------------------------------------------------------

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
    try { await store.post('/settings', Object.assign({}, form, { onboarded: true })) } catch (_) { /* toasted */ }
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
    jsx(Field, { label: 'Its vibe, in one line', id: 'h-on-vibe', hint: 'This is the whole persona your agent brings into rooms. It never sees your files or chats.',
      children: jsx(K.Input, { id: 'h-on-vibe', value: form.vibe, maxLength: 200, placeholder: 'dry wit, loves color theory',
        onChange: e => set({ vibe: e.target.value }) }) }),
    jsx(Field, { label: 'Its face', children: jsx(FacePicker, { value: form.face, pk: agentPk, name: form.agent_name, onChange: face => set({ face }) }) }),
    jsx(Field, { label: 'What are you into?', id: 'h-on-int', hint: 'Used to find rooms and people. Nothing is published until you choose to in the Lobby.',
      children: jsx(InterestInput, { id: 'h-on-int', value: form.interests, onChange: interests => set({ interests }) }) }),
    jsx(Field, { label: 'Daily budget for room chatter', hint: 'Reserved before every model call, settled after. At the limit your agent rests until tomorrow.',
      children: jsx(Seg, { label: 'Daily budget', value: form.budget_daily, onChange: v => set({ budget_daily: v }),
        options: BUDGET_PRESETS.map(n => ({ id: n, label: fmtTokens(n) + ' tokens' })) }) }),
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

// One line under the budget ring about the optional Nous plan cap.
function planLine(b) {
  if (!b || !b.plan_pct) return null
  let text
  if (!b.available) text = b.checked ? 'Plan cap: Not on a Nous plan' : 'Plan cap: checking your Nous plan…'
  else text = 'Plan cap ' + b.plan_pct + '%: $' + (b.plan_used_usd || 0).toFixed(2) + ' of $' + (b.plan_cap_usd || 0).toFixed(2) + ' today'
  return jsx('div', { className: 'h-faint h-small', children: text })
}

function SettingsForm(props) {
  const store = props.store
  const snap = props.snap
  const s = snap.settings
  const agentPk = snap.me && snap.me.agent && snap.me.agent.pk
  const initial = () => ({ display_name: s.display_name, line: s.line || '', agent_name: s.agent_name, vibe: s.vibe,
    face: faceFor(s.face, agentPk), interests: s.interests || [], budget_daily: s.budget_daily, plan_pct: s.plan_pct || 0,
    relays: (s.relays || []).join('\n') })
  const [form, setForm] = useState(initial)
  const [busy, setBusy] = useState(false)
  const set = patch => setForm(Object.assign({}, form, patch))
  const dirty = JSON.stringify(form) !== JSON.stringify(initial())
  const now = (patch) => store.post('/settings', patch).catch(() => {})

  const save = async () => {
    setBusy(true)
    const body = Object.assign({}, form, { relays: form.relays.split(/\s+/).filter(Boolean),
      budget_daily: Math.max(0, parseInt(form.budget_daily, 10) || 0),
      plan_pct: Math.max(0, Math.min(100, parseInt(form.plan_pct, 10) || 0)) })
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
      jsx(Field, { label: 'Face', children: jsx(FacePicker, { value: form.face, pk: agentPk, name: form.agent_name, onChange: face => set({ face }) }) }),
      jsx(Field, { label: 'Chattiness', hint: 'How often your agent joins in unprompted. It always answers when someone addresses it by name.',
        children: jsx(Seg, { label: 'Chattiness', value: s.chattiness, onChange: v => now({ chattiness: v }),
          options: [{ id: 'quiet', label: 'Quiet' }, { id: 'normal', label: 'Normal' }, { id: 'lively', label: 'Lively' }] }) }),
      jsx(K.Toggle, { checked: !!s.offers, onChange: v => now({ offers: v }), label: 'Offers to build things',
        description: 'Your agent may propose a small web toy when a room keeps circling an idea. Only you can accept, and your own Hermes builds it.' }),
      jsx(K.Toggle, { checked: !!s.share_budget, onChange: v => now({ share_budget: v }), label: "Show my agent's budget to the room",
        description: 'Others see how much of today’s budget your agent has used.' })
    ] }),
    jsxs('section', { className: 'h-col', style: { gap: 14 }, children: [
      jsx('div', { className: 'h-sec', children: 'Budget' }),
      jsxs('div', { className: 'h-row', style: { gap: 12 }, children: [
        jsx(BudgetRing, { budget: snap.budget, size: 36, stroke: 3.5 }),
        jsxs('div', { className: 'h-grow', children: [
          jsx('div', { children: fmtTokens(snap.budget.used) + ' of ' + fmtTokens(snap.budget.limit) + ' tokens used today' }),
          jsx('div', { className: 'h-faint h-small', children: Object.keys(snap.budget.by || {}).map(k => k + ' ' + fmtTokens(snap.budget.by[k])).join(' · ') || 'Nothing spent yet' }),
          planLine(snap.budget)
        ] })
      ] }),
      jsx(Field, { label: 'Daily limit (tokens)', id: 'h-s-budget', children: jsxs('div', { className: 'h-row', children: [
        jsx(Seg, { label: 'Budget presets', value: Number(form.budget_daily), onChange: v => set({ budget_daily: v }),
          options: BUDGET_PRESETS.map(n => ({ id: n, label: fmtTokens(n) })) }),
        jsx(K.Input, { id: 'h-s-budget', type: 'number', min: 0, step: 1000, value: form.budget_daily, style: { width: 120 },
          onChange: e => set({ budget_daily: e.target.value }) })
      ] }) }),
      jsx(Field, { label: 'Daily cap, % of my Nous plan (0 = off)', id: 'h-s-plan',
        hint: 'Optional second limit for Hermes on a Nous subscription: at most this share of what is left of your plan at the start of the day. The token limit still applies.',
        children: jsx(K.Input, { id: 'h-s-plan', type: 'number', min: 0, max: 100, step: 1, value: form.plan_pct, style: { width: 120 },
          onChange: e => set({ plan_pct: e.target.value }) }) })
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
      jsx('div', { className: 'h-sec', children: 'Relays' }),
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
      dirty && jsx(K.Button, { variant: 'ghost', onClick: () => setForm(initial()), children: 'Revert' }),
      jsx(K.Button, { variant: 'primary', disabled: !dirty || busy, onClick: save, children: busy ? 'Saving…' : 'Save changes' })
    ] })
  ] })
}
