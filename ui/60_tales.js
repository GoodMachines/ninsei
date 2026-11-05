// ---------------------------------------------------------------------------------------------
// Tall Tales: the host agent asks an obscure question with a real answer; everyone (people and
// agents) writes a convincing fake; people vote for the truth. A team is a person + their agent.
// Pinned above the composer while a game runs.
// ---------------------------------------------------------------------------------------------

const LETTERS = 'ABCDEFGHIJKL'

function TallTales(props) {
  const { store, room, game, book } = props
  const [hidden, setHidden] = useState(false)
  const running = game.phase !== 'end'
  const now = useNow(250, running && game.ends_at > 0)
  if (hidden) return null

  const hostLabel = game.you_host ? 'Your agent is hosting' : 'Hosted by ' + (game.host_name || 'an agent')
  const round = game.n ? 'Round ' + game.n + ' of ' + game.rounds : 'Getting ready'

  let body = null
  if (game.phase === 'starting') body = jsx('div', { className: 'h-muted', children: (game.host_name || 'The host') + ' is writing questions…' })
  else if (game.phase === 'fakes') body = jsx(FakePhase, { store, room, game, quiet: props.quiet })
  else if (game.phase === 'vote') body = jsx(VotePhase, { store, room, game })
  else if (game.phase === 'reveal') body = jsx(RevealPhase, { game, book })
  else if (game.phase === 'end') body = jsx('div', { className: 'h-muted', children: game.aborted ? 'The game stopped early.' : 'That’s the game. Final scores:' })

  return jsxs('section', { className: 'h-tales', 'aria-label': 'Tall Tales', children: [
    jsxs('div', { className: 'h-row', children: [
      jsx(K.Icon, { name: 'game', size: 16 }),
      jsxs('div', { className: 'h-grow', children: [
        jsx('div', { className: 'h-kicker h-sec', children: 'Tall Tales · ' + round }),
        jsx('div', { className: 'h-faint h-small', children: hostLabel })
      ] }),
      running && game.ends_at > 0 && jsx(Countdown, { game, now }),
      !running && jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: () => setHidden(true), children: 'Close' })
    ] }),
    game.q && game.phase !== 'end' && jsx('div', { className: 'h-tales-q', children: game.q }),
    body,
    jsx(Scoreboard, { game, room })
  ] })
}

// The ring empties as the phase runs out. Its full length is the longest remaining time we have
// seen for this phase, so it works without knowing the host's timer settings.
function Countdown(props) {
  const { game, now } = props
  const total = useRef({ key: '', max: 1 })
  const key = game.gid + ':' + game.n + ':' + game.phase
  const left = Math.max(0, game.ends_at - now)
  if (total.current.key !== key) total.current = { key, max: Math.max(1, left) }
  else total.current.max = Math.max(total.current.max, left)
  const secs = Math.ceil(left)
  return jsx(Ring, { pct: left / total.current.max, from: 1, size: 34, stroke: 3, spring: SPRING.tick, tone: secs <= 5 ? 'warn' : '',
    label: secs + ' seconds left', children: secs })
}

function FakePhase(props) {
  const { store, room, game } = props
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  if (game.my_fake) {
    return jsxs('div', { className: 'h-col', style: { gap: 4 }, children: [
      jsxs('div', { children: ['Your fake is in: ', jsx('b', { children: '“' + game.my_fake + '”' })] }),
      jsx('div', { className: 'h-faint h-small', children: game.fakes_in + ' answer' + (game.fakes_in === 1 ? '' : 's') + ' in so far. Your agent writes one too.' })
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
    jsx('div', { className: 'h-faint h-small', children: 'Write a believable fake answer. You score for everyone it fools.' }),
    jsxs('div', { className: 'h-row', children: [
      jsx('div', { className: 'h-grow', children: jsx(K.Input, { value: text, maxLength: 80, autoFocus: !props.quiet, placeholder: 'Your fake answer', 'aria-label': 'Your fake answer',
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

function RevealPhase(props) {
  const { game, book } = props
  const rv = game.reveal || {}
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
