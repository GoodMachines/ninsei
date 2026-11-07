// ---------------------------------------------------------------------------------------------
// Tall Tales: the host agent asks an obscure question with a real answer; everyone (people and
// agents) writes a convincing fake; people vote for the truth. A team is a person + their agent.
// Pinned above the composer while a game runs.
// ---------------------------------------------------------------------------------------------

const LETTERS = 'ABCDEFGHIJKL'

// Who's the Agent? runs on the same rounds and panel: everyone answers a prompt about their own life,
// agents included and trying to pass as people; people flag the answers they think an agent wrote.
const GAME_NAME = { tales: 'Tall Tales', agent: 'Who’s the Agent?' }
function gameName(mode) { return GAME_NAME[mode] || GAME_NAME.tales }

// "How to play": what each phase does, its length, the points. The numbers come from the engine's own
// constants (game.rules), so the copy can't drift from the clock. Plain sentences, one thought each.
function howToLines(mode, rules) {
  const r = rules || {}
  const rounds = r.rounds || 3
  const secs = n => (n || 0) + ' seconds'
  const rows = []
  if (mode === 'agent') {
    rows.push(['Answer', 'Each round has a prompt about everyday life. You have ' + secs(r.fake) + ' to answer. Agents answer too, and they try to sound like people.'])
    rows.push(['Guess', 'Then you have ' + secs(r.vote) + ' to tap the answers you think an agent wrote. Anything you skip counts as a person.'])
    rows.push(['Reveal', 'Everyone sees who wrote what for ' + secs(r.reveal) + ', then the next round starts. ' + rounds + ' rounds in all.'])
    rows.push(['Points', 'For each answer from another team: a right call is 1 point for you. A wrong call is 1 point for the answer’s team, so an agent that passes as a person scores.'])
    rows.push(['Teams', 'You and your agent are one team. You can’t call your own team’s answers, and only people guess. The host’s agent plays too.'])
  } else {
    rows.push(['Write', 'Each round, the host’s agent asks a question that has a real answer. You have ' + secs(r.fake) + ' to write a fake answer that sounds true. Agents write fakes too, the host’s agent included.'])
    rows.push(['Vote', 'Then the real answer is mixed in with the fakes and you have ' + secs(r.vote) + ' to pick the one you think is true. Only people vote.'])
    rows.push(['Reveal', 'The truth and who wrote each fake show for ' + secs(r.reveal) + ', then the next round starts. ' + rounds + ' rounds in all.'])
    rows.push(['Points', 'Finding the truth is 2 points. Each person your fake fools is 1 point for you. If your fake happens to match the real answer, that is 1 lucky point.'])
    rows.push(['Teams', 'You and your agent are one team. You can’t vote for your team’s answers.'])
  }
  rows.push(['Sealed', 'Answers and votes are sealed until the reveal. Only the host can read them. A phase ends early once everyone is in.'])
  return rows
}

function HowToPlay(props) {
  const { game, onClose } = props
  return jsxs('section', { className: 'h-howto', 'aria-label': 'How to play ' + gameName(game.mode), children: [
    jsxs('div', { className: 'h-row', children: [
      jsx('div', { className: 'h-grow h-kicker h-sec', children: 'How to play' }),
      jsx(K.Button, { variant: 'secondary', size: 'sm', onClick: onClose, children: 'Got it' })
    ] }),
    jsx('dl', { className: 'h-howto-list', children: howToLines(game.mode, game.rules).map(r =>
      jsxs(Fragment, { children: [jsx('dt', { children: r[0] }), jsx('dd', { children: r[1] })] }, r[0])) })
  ] })
}

// One chip per agent playing the round: writing, answered, or couldn't answer. It says nothing about
// what an answer is or which option is whose.
const AGENT_STATUS = { writing: 'writing…', answered: 'answered', gave_up: 'couldn’t answer', none: 'no answer' }
function AgentStatus(props) {
  const agents = props.game.agents || []
  if (!agents.length) return null
  return jsx('ul', { className: 'h-agents-in', 'aria-label': 'Agents in this round', children: agents.map(a =>
    jsxs('li', { 'data-status': a.status, children: [
      jsx('span', { className: 'h-trunc', children: a.yours ? a.name + ' (yours)' : a.name }),
      jsx('span', { className: 'h-faint', children: AGENT_STATUS[a.status] || '' })
    ] }, a.pk)) })
}

function TallTales(props) {
  const { store, room, game, book } = props
  const [hidden, setHidden] = useState(false)
  // Shown on its own the first time this install sees each game; after that, behind the "How to play" button.
  const howKey = 'howto.' + (game.mode === 'agent' ? 'agent' : 'tales')
  const [how, setHow] = useState(() => !P.prefs.get(howKey, false))
  const closeHow = () => { setHow(false); P.prefs.set(howKey, true) }
  const running = game.phase !== 'end'
  const now = useNow(250, running && game.ends_at > 0)
  // A new phase that wants something from you (an answer, a vote) brings a hidden panel back, and so does
  // the end, once: a game hidden while it ran shows its final scores, with Close, instead of vanishing.
  const phaseKey = game.gid + ':' + game.n + ':' + game.phase
  const seen = useRef(phaseKey)
  useEffect(() => {
    if (seen.current === phaseKey) return
    seen.current = phaseKey
    if (game.phase === 'fakes' || game.phase === 'vote' || game.phase === 'end') setHidden(false)
  }, [phaseKey])
  if (hidden && !running) return null
  if (hidden) {
    const left = game.ends_at > 0 ? Math.max(0, Math.ceil(game.ends_at - now)) : 0
    return jsxs('section', { className: 'h-tales h-tales-bar', 'aria-label': gameName(game.mode) + ' (hidden)', children: [
      jsx(K.Icon, { name: 'game', size: 14 }),
      jsx('span', { className: 'h-grow h-small h-trunc', children: gameName(game.mode) + ' is running' + (game.n ? ' · round ' + game.n + ' of ' + game.rounds : '') + (left ? ' · ' + left + ' s left' : '') }),
      jsx(K.Button, { variant: 'secondary', size: 'sm', onClick: () => setHidden(false), children: 'Show game' })
    ] })
  }

  const hostLabel = game.you_host ? 'Your agent is hosting' : 'Hosted by ' + (game.host_name || 'an agent')
  const round = game.n ? 'Round ' + game.n + ' of ' + game.rounds : 'Getting ready'

  let body = null
  const who = game.mode === 'agent'
  if (game.phase === 'starting') body = jsx('div', { className: 'h-muted', children: (game.host_name || 'The host') + (who ? ' is picking prompts…' : ' is writing questions…') })
  else if (game.phase === 'fakes') body = jsx(FakePhase, { store, room, game, quiet: props.quiet })
  else if (game.phase === 'vote') body = who ? jsx(FlagPhase, { store, room, game }) : jsx(VotePhase, { store, room, game })
  else if (game.phase === 'reveal') body = who ? jsx(WhoRevealPhase, { game, book }) : jsx(RevealPhase, { game, book })
  else if (game.phase === 'end') body = jsx('div', { className: 'h-muted', children: game.stale ? 'The host went quiet, so the game is over.' : game.aborted ? 'The game stopped early.' : 'That’s the game. Final scores:' })

  return jsxs('section', { className: 'h-tales', 'aria-label': gameName(game.mode), children: [
    jsxs('div', { className: 'h-row', children: [
      jsx(K.Icon, { name: 'game', size: 16 }),
      jsxs('div', { className: 'h-grow', children: [
        jsx('div', { className: 'h-kicker h-sec', children: gameName(game.mode) + ' · ' + round }),
        jsx('div', { className: 'h-faint h-small', children: hostLabel })
      ] }),
      running && game.ends_at > 0 && jsx(Countdown, { game, now }),
      jsx(K.Button, { variant: 'ghost', size: 'sm', 'aria-expanded': how, onClick: () => (how ? closeHow() : setHow(true)), children: 'How to play' }),
      // Always closable: a host that vanished mid-game must never pin a panel over the room.
      jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: () => setHidden(true), children: running ? 'Hide' : 'Close' })
    ] }),
    how && jsx(HowToPlay, { game, onClose: closeHow }),
    game.q && game.phase !== 'end' && jsx('div', { className: 'h-tales-q', children: game.q }),
    body,
    game.phase === 'fakes' && jsx(AgentStatus, { game }),
    jsx(Scoreboard, { game, room })
  ] })
}

// The ring empties as the phase runs out. Its full length is the phase duration the host sent
// (game.secs); older hosts don't send it, so fall back to the longest remaining time seen.
function Countdown(props) {
  const { game, now } = props
  const total = useRef({ key: '', max: 1 })
  const key = game.gid + ':' + game.n + ':' + game.phase
  const left = Math.max(0, game.ends_at - now)
  if (total.current.key !== key) total.current = { key, max: Math.max(1, left) }
  else total.current.max = Math.max(total.current.max, left)
  if (game.secs > 0) total.current.max = Math.max(game.secs, left, 1)
  const secs = Math.ceil(left)
  return jsx(Ring, { pct: left / total.current.max, from: 1, size: 34, stroke: 3, spring: SPRING.tick, tone: secs <= 5 ? 'warn' : '',
    label: secs + ' seconds left', children: secs })
}

// True when moving focus to the game's answer box would take it from nothing, or from inside the game panel.
function wantsFocus(active, box) {
  if (!active || active === document.body || active === document.documentElement) return true
  const panel = box && box.closest ? box.closest('.h-tales') : null
  return !!(panel && panel.contains(active))
}

function FakePhase(props) {
  const { store, room, game } = props
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const who = game.mode === 'agent'
  const box = useRef(null)
  // Take focus when a round opens only if nobody is typing elsewhere (the chat composer): a late
  // keystroke must never land in an answer that can be sent only once.
  useEffect(() => {
    if (props.quiet || game.my_fake) return
    const input = box.current && box.current.querySelector('input')
    if (input && wantsFocus(document.activeElement, box.current)) input.focus()
  }, [])
  if (game.my_fake) {
    return jsxs('div', { className: 'h-col', style: { gap: 4 }, children: [
      jsxs('div', { children: [who ? 'Your answer is in: ' : 'Your fake is in: ', jsx('b', { children: '“' + game.my_fake + '”' })] }),
      jsx('div', { className: 'h-faint h-small', children: game.fakes_in + ' answer' + (game.fakes_in === 1 ? '' : 's') + ' in so far. ' +
        (who ? 'Your agent is answering too, and it’s trying to pass as a person.' : 'Your agent writes one too.') })
    ] })
  }
  const submit = async () => {
    const t = text.trim()
    if (!t || busy) return
    setBusy(true)
    try { await store.post('/game/fake', { room: room.id, gid: game.gid, n: game.n, text: t }) } catch (_) { /* toasted */ }
    setBusy(false)
  }
  return jsxs('div', { className: 'h-col', style: { gap: 6 }, children: [
    jsx('div', { className: 'h-faint h-small', children: who
      ? 'Answer as yourself. Agents answer too, and they’re trying to sound human. Or sound like a bot and fool the room.'
      : 'Write a believable fake answer. You score for everyone it fools.' }),
    jsxs('div', { className: 'h-row', children: [
      jsx('div', { className: 'h-grow', ref: box, children: jsx(K.Input, { value: text, maxLength: 80,
        placeholder: who ? 'Your answer' : 'Your fake answer', 'aria-label': who ? 'Your answer' : 'Your fake answer',
        onChange: e => setText(e.target.value), onKeyDown: e => { if (e.key === 'Enter') { e.preventDefault(); submit() } } }) }),
      jsx(K.Button, { variant: 'primary', disabled: !text.trim() || busy, onClick: submit, children: 'Submit' })
    ] })
  ] })
}

function VotePhase(props) {
  const { store, room, game } = props
  const [busy, setBusy] = useState('')
  const blocked = new Set(game.blocked || [])
  const vote = async id => {
    if (game.my_vote || busy) return
    setBusy(id)
    try { await store.post('/game/vote', { room: room.id, gid: game.gid, n: game.n, option: id }) } catch (_) { /* toasted */ }
    setBusy('')
  }
  return jsxs('div', { className: 'h-col', style: { gap: 6 }, children: [
    jsx('div', { className: 'h-faint h-small', children: game.my_vote ? 'Vote in. ' + game.votes_in + ' voted so far.' : 'Which one is true? You can’t pick your own team’s answers.' }),
    jsx('div', { className: 'h-opts', role: 'radiogroup', 'aria-label': 'Answers', children: (game.options || []).map((o, i) =>
      jsxs('button', { type: 'button', className: 'h-opt', role: 'radio', 'aria-checked': game.my_vote === o.id,
        'data-picked': game.my_vote === o.id || busy === o.id, disabled: blocked.has(o.id) || (!!game.my_vote && game.my_vote !== o.id),
        onClick: () => vote(o.id), children: [
          jsx('span', { className: 'h-letter', children: LETTERS[i] }),
          jsx('span', { className: 'h-grow', children: o.text }),
          blocked.has(o.id) && jsx('span', { className: 'h-faint h-tiny', children: 'your team' })
        ] }, o.id)) })
  ] })
}

// Who's the Agent?: tap every answer you think an agent wrote, then lock in. Unflagged means "a person".
function FlagPhase(props) {
  const { store, room, game } = props
  const [picked, setPicked] = useState(() => new Set())
  const [busy, setBusy] = useState(false)
  const blocked = new Set(game.blocked || [])
  const locked = !!game.my_vote
  const mine = new Set(game.my_picks || [])
  const toggle = id => {
    if (locked || blocked.has(id)) return
    const next = new Set(picked)
    next.has(id) ? next.delete(id) : next.add(id)
    setPicked(next)
  }
  const lock = async () => {
    if (locked || busy) return
    setBusy(true)
    try { await store.post('/game/vote', { room: room.id, gid: game.gid, n: game.n, agents: Array.from(picked) }) } catch (_) { /* toasted */ }
    setBusy(false)
  }
  const flagged = locked ? mine : picked
  return jsxs('div', { className: 'h-col', style: { gap: 6 }, children: [
    jsx('div', { className: 'h-faint h-small', children: locked
      ? 'Locked in. ' + game.votes_in + ' voted so far.'
      : 'Which ones did an agent write? Tap each one you suspect. Anything you skip counts as a person.' }),
    jsx('div', { className: 'h-opts', role: 'group', 'aria-label': 'Answers', children: (game.options || []).map((o, i) =>
      jsxs('button', { type: 'button', className: 'h-opt', 'aria-pressed': flagged.has(o.id), 'data-picked': flagged.has(o.id),
        disabled: blocked.has(o.id) || locked, onClick: () => toggle(o.id), children: [
          jsx('span', { className: 'h-letter', children: LETTERS[i] }),
          jsx('span', { className: 'h-grow', children: o.text }),
          blocked.has(o.id) ? jsx('span', { className: 'h-faint h-tiny', children: 'your team' })
            : jsx('span', { className: 'h-whotag', 'data-on': flagged.has(o.id), children: flagged.has(o.id) ? 'agent' : 'person' })
        ] }, o.id)) }),
    !locked && jsx('div', { className: 'h-actions', children: jsx(K.Button, { variant: 'primary', size: 'sm', disabled: busy, onClick: lock,
      children: busy ? 'Locking in…' : picked.size ? 'Lock in · ' + picked.size + ' agent' + (picked.size === 1 ? '' : 's') : 'Lock in · all people' }) })
  ] })
}

function WhoRevealPhase(props) {
  const { game } = props
  const rv = game.reveal || {}
  const book = Object.assign({}, props.book)
  Object.keys(rv.names || {}).forEach(pk => { if (!book[pk]) book[pk] = { name: String(rv.names[pk]) } })
  const authors = rv.authors || {}
  const kinds = rv.kinds || {}
  const flags = rv.picks || {}
  const voters = rv.voters || []
  const points = rv.points || {}
  const team = pk => (book[pk] && book[pk].agent && book[pk].owner) || pk
  return jsxs('div', { className: 'h-col', style: { gap: 6 }, children: [
    jsx('div', { className: 'h-opts', children: (game.options || []).map((o, i) => {
      const author = authors[o.id] || ''
      const agent = kinds[o.id] === 'agent'
      const flaggedBy = flags[o.id] || []
      // everyone who voted and could call this one (not the author's own team) but didn't flag it
      const missed = voters.filter(v => !flaggedBy.includes(v) && team(v) !== team(author))
      const right = agent ? flaggedBy : missed
      const wrong = agent ? missed : flaggedBy
      const verdict = []
      if (right.length) verdict.push((agent ? 'spotted by ' : 'read right by ') + joinNames(right.map(pk => whoLabel(book, pk))))
      if (wrong.length) verdict.push('fooled ' + joinNames(wrong.map(pk => whoLabel(book, pk))))
      return jsxs('div', { className: 'h-opt', 'data-agent': agent, children: [
        jsx('span', { className: 'h-letter', children: LETTERS[i] }),
        jsxs('span', { className: 'h-grow h-col', style: { gap: 1 }, children: [
          jsx('span', { children: o.text }),
          jsx('span', { className: 'h-faint h-small', children: whoLabel(book, author) + (agent ? ' · an agent' : ' · a person') + (verdict.length ? ' · ' + verdict.join(' · ') : '') })
        ] }),
        jsx('span', { className: 'h-whotag', 'data-on': agent, children: agent ? 'agent' : 'person' })
      ] }, o.id)
    }) }),
    Object.keys(points).length > 0 && jsx('div', { className: 'h-small', children: 'This round: ' + Object.keys(points).map(t => teamName(game, book, t) + ' +' + points[t]).join(' · ') })
  ] })
}

function RevealPhase(props) {
  const { game } = props
  const rv = game.reveal || {}
  // Names the host sent fill gaps for players who have left the room since.
  const book = Object.assign({}, props.book)
  Object.keys(rv.names || {}).forEach(pk => { if (!book[pk]) book[pk] = { name: String(rv.names[pk]) } })
  const authors = rv.authors || {}
  const picks = rv.picks || {}
  const points = rv.points || {}
  const lucky = rv.lucky || []
  const opts = game.options || []
  return jsxs('div', { className: 'h-col', style: { gap: 6 }, children: [
    jsx('div', { className: 'h-opts', children: opts.map((o, i) => {
      const truth = o.id === rv.truth
      const by = String(authors[o.id] || '').split(',').filter(Boolean).map(pk => whoLabel(book, pk))
      const fooled = (picks[o.id] || []).map(pk => whoLabel(book, pk))
      return jsxs('div', { className: 'h-opt', 'data-truth': truth, children: [
        jsx('span', { className: 'h-letter', children: truth ? '✓' : LETTERS[i] }),
        jsxs('span', { className: 'h-grow h-col', style: { gap: 1 }, children: [
          jsx('span', { children: o.text }),
          jsx('span', { className: 'h-faint h-small', children: truth
            ? (fooled.length ? 'The truth. Found by ' + joinNames(fooled) : 'The truth. Nobody found it')
            : 'Fake by ' + (by.length ? joinNames(by) : 'someone') + (fooled.length ? ' · fooled ' + joinNames(fooled) : '') })
        ] })
      ] }, o.id)
    }) }),
    lucky.length > 0 && jsx('div', { className: 'h-faint h-small', children: joinNames(lucky.map(pk => whoLabel(book, pk))) + ' guessed the real answer while writing a fake. Lucky.' }),
    Object.keys(points).length > 0 && jsx('div', { className: 'h-small', children: 'This round: ' + Object.keys(points).map(t => teamName(game, book, t) + ' +' + points[t]).join(' · ') })
  ] })
}

function teamName(game, book, pk) {
  const person = (game.team_names && game.team_names[pk]) || (book[pk] && book[pk].name) || 'Someone'
  const agent = Object.values(book).find(b => b.agent && b.owner === pk)
  return agent ? person + ' + ' + agent.name : person
}

function Scoreboard(props) {
  const { game, room } = props
  const book = nameBook(room, null)
  const scores = game.scores || {}
  const teams = Object.keys(Object.assign({}, game.team_names || {}, scores))
  if (!teams.length) return null
  teams.sort((a, b) => (scores[b] || 0) - (scores[a] || 0))
  const you = (room.members || []).find(p => p.you)
  return jsx('div', { className: 'h-score', 'aria-label': 'Scores', children: teams.map(t =>
    jsxs('span', { className: 'h-team', 'data-you': !!(you && you.pk === t), children: [
      jsx('span', { children: teamName(game, book, t) }), jsx('b', { children: scores[t] || 0 })
    ] }, t)) })
}
