// ---------------------------------------------------------------------------------------------
// Desktop platform: the thin layer between the shared UI and the Desktop SDK.
// ---------------------------------------------------------------------------------------------

const BUTTON_VARIANT = { primary: 'default', secondary: 'secondary', ghost: 'ghost', outline: 'outline', danger: 'destructive' }
const BUTTON_SIZE = { sm: 'xs', md: 'sm', icon: 'icon-xs' }

const K = {
  Button(props) {
    const p = Object.assign({}, props, { variant: BUTTON_VARIANT[props.variant] || 'secondary', size: BUTTON_SIZE[props.size] || 'sm' })
    return jsx(sdk.Button, p)
  },
  Input: sdk.Input,
  // The SDK's spinner isn't known to honour reduced motion, so it isn't asked to spin when that's on.
  Icon(props) {
    return jsx(sdk.Codicon, { name: props.name, size: props.size || 14, spinning: !!props.spinning && !motion.reduced(), 'aria-hidden': true })
  },
  Tip(props) {
    return sdk.Tip ? jsx(sdk.Tip, { label: props.label, children: props.children }) : props.children
  },
  Dialog(props) {
    return jsx(sdk.Dialog, { open: !!props.open, onOpenChange: v => { if (!v) props.onClose() }, children:
      jsx(sdk.DialogContent, { style: props.wide ? { maxWidth: 680, width: 'calc(100vw - 32px)' } : { maxWidth: 460, width: 'calc(100vw - 32px)' },
        children: jsxs('div', { className: 'hx h-col', style: { gap: 14 }, children: [
          jsxs(sdk.DialogHeader, { children: [
            jsx(sdk.DialogTitle, { children: props.title }),
            props.description ? jsx(sdk.DialogDescription, { children: props.description }) : null
          ] }),
          props.children,
          props.footer ? jsx(sdk.DialogFooter, { children: props.footer }) : null
        ] }) }) })
  },
  Toggle(props) {
    if (sdk.ToggleRow) {
      return jsx(sdk.ToggleRow, { checked: !!props.checked, onChange: props.onChange, label: props.label, description: props.description })
    }
    return jsxs('label', { className: 'h-row', style: { justifyContent: 'space-between', gap: 16 }, children: [
      jsxs('span', { className: 'h-col', style: { gap: 2 }, children: [
        jsx('span', { children: props.label }), jsx('span', { className: 'h-faint h-small', children: props.description })
      ] }),
      jsx(sdk.Switch, { checked: !!props.checked, onCheckedChange: props.onChange })
    ] })
  },
  // a shared toy: the SDK's sandboxed frame (opaque origin, scripts only) on a data: URL
  Toy(props) {
    return jsx(sdk.SandboxedFrame, { src: 'data:text/html;base64,' + b64(withCsp(props.html)), title: props.title, onLoad: props.onLoad, ref: props.frameRef,
      style: { width: '100%', height: '100%', border: 0 } })
  }
}

function makePlatform(ctx) {
  return {
    kind: 'desktop',
    inlineStyle: false,
    // the profile Desktop's gateway is routed to, for "Ninsei is off for the X profile"
    profileName() { try { return host.state && host.state.profile ? String(host.state.profile.get() || '') : '' } catch (_) { return '' } },
    openPlugins: typeof host.navigate === 'function' ? () => host.navigate('/capabilities?tab=plugins') : null,
    rest: (path, opts) => ctx.rest(path, opts),
    toast(kind, message) { host.notify({ kind: kind === 'error' ? 'error' : 'info', message }) },
    // Links go to the system browser through the host's own door (ctx.os.openExternal, http(s) only as
    // far as this UI ever asks); null on an older Desktop, where the link's own target="_blank" is all there is.
    openExternal: ctx.os && typeof ctx.os.openExternal === 'function' ? url => Promise.resolve(ctx.os.openExternal(url)).catch(() => false) : null,
    // The OS notification for a mention. The host raises it only while you are away from Hermes, only if
    // Settings > Notifications > Plugin notifications is on, and throttles it per plugin.
    osNotify(o) {
      try {
        if (ctx.os && typeof ctx.os.notify === 'function') ctx.os.notify({ title: o.title, body: o.body, activate: '/ninsei', onActivate: o.onActivate })
      } catch (_) { /* no native notifications here */ }
    },
    copy: text => Promise.resolve(ctx.os && ctx.os.writeClipboard ? ctx.os.writeClipboard(text) : false).catch(() => false),
    // Desktop's SDK has no binary save (ctx.files writes text into granted folders, ctx.os.pickSavePath
    // returns a path on the backend), but the shell turns a page download into a Save dialog, so the link works.
    saveFile: (blob, filename) => anchorSave(blob, filename),
    loop(draw, idle) {
      if (sdk.createBudgetedLoop) {
        const l = sdk.createBudgetedLoop(draw, { fps: 60, idleWhen: idle })
        ctx.onDispose(() => l.dispose())
        return l
      }
      let frame = 0
      const tick = now => { frame = 0; draw(now); if (!idle()) frame = window.requestAnimationFrame(tick) }
      ctx.onDispose(() => frame && window.cancelAnimationFrame(frame))
      return { wake() { if (!frame) frame = window.requestAnimationFrame(tick) }, dispose() { frame && window.cancelAnimationFrame(frame); frame = 0 } }
    },
    setTimeout: (fn, ms) => ctx.setTimeout(fn, ms),
    setInterval: (fn, ms) => ctx.setInterval(fn, ms),
    listen: (target, type, fn) => ctx.addEventListener(target, type, fn),
    prefs: {
      get: (k, d) => { try { return ctx.storage.get(k, d) } catch (_) { return d } },
      set: (k, v) => { try { ctx.storage.set(k, v) } catch (_) { /* storage unavailable */ } }
    },
    // Accepting an offer: open a fresh chat and put the task in its composer. The owner reads it and
    // presses Enter; nothing is sent for them. Older Desktops: copy it and say so.
    async openBuild(prompt) {
      const composer = host.composer
      if (typeof host.newChat === 'function' && composer && typeof composer.setDraft === 'function') {
        host.newChat()
        for (let i = 0; i < 12; i++) {
          // the new draft's composer mounts a moment after newChat()
          await new Promise(resolve => ctx.setTimeout(resolve, 150))
          let ok = false
          try { ok = await composer.setDraft('new', prompt) } catch (_) { ok = false }
          if (ok) {
            host.notify({ kind: 'info', message: 'The build task is in a new chat. Read it, then press Enter to start.' })
            return true
          }
        }
      }
      const copied = await this.copy(prompt)
      host.notify({ kind: 'info', message: copied ? 'Build prompt copied. Paste it into a new Hermes chat and press Enter.' : 'Copy the build prompt from the dialog into a new Hermes chat.' })
      return false
    },
    openSettings() {
      host.navigate(sdk.pluginSettingsHref ? sdk.pluginSettingsHref('ninsei') : '/settings?tab=plugins&plugin=ninsei')
    }
  }
}

// Your agent waiting on you (an idea to answer, a build ready to share) gets one line in the pet's
// speech bubble, once per offer and state.
function watchForPet(ctx, store) {
  if (!ctx.pet || typeof ctx.pet.say !== 'function') return
  const said = new Set()
  ctx.onDispose(store.subscribe(st => {
    const snap = st.snap
    if (!snap || !snap.settings || !snap.settings.onboarded) return
    const agent = (snap.me.agent && snap.me.agent.name) || 'Your agent'
    for (const o of snap.offers || []) {
      const key = o.id + ':' + o.status
      if (said.has(key) || (o.status !== 'open' && o.status !== 'ready')) continue
      said.add(key)
      const room = ((snap.rooms || []).find(r => r.id === o.room) || {}).name || 'a room'
      const line = o.status === 'open' ? agent + ' has an idea in ' + room + ': ' + o.title + '. Review it in Ninsei.'
        : 'Your build “' + o.title + '” is ready to share in ' + room + '.'
      ctx.pet.say(line, { id: 'offer', tone: 'wait', ttlMs: 15000 })
    }
    // Your agent's reactions in the open room (named, impersonated, spotted, passed as a person).
    const room = snap.room
    const me = snap.me.agent
    if (!room || !me || !me.pk) return
    const book = nameBook(room, snap.me)
    const why = {}
    reactionsFor(room, room.game, book, Date.now() / 1000, why)
    const cause = why[me.pk]
    const key = cause && 'react:' + cause.expr + ':' + cause.key
    if (!cause || said.has(key)) return
    said.add(key)
    const line = petLine(cause, book, agent, room.name || 'a room')
    if (line) ctx.pet.say(line, { id: 'react', tone: 'info', ttlMs: 8000 })
  }))
}

// The "Ninsei" theme: warm paper by day, dim lamplight by night. The hue is Ninsei's own default
// agent colour (28, amber) pulled down to a calm, low-chroma family. Every text pair is
// at least WCAG AA (4.5:1): checked with the SDK's contrastRatio formula, lowest pair 5.0:1 light
// (primary on card) and 7.1:1 dark.
const NINSEI_THEME = {
  name: 'ninsei',
  label: 'Ninsei',
  description: 'Warm, calm and low-contrast: paper and lamplight',
  colors: {
    background: '#f6efe4', foreground: '#3a2f27', card: '#efe6d8', cardForeground: '#3a2f27',
    muted: '#e9dfcf', mutedForeground: '#66564a', popover: '#f1e9dc', popoverForeground: '#3a2f27',
    primary: '#9a4a1f', primaryForeground: '#ffffff', secondary: '#e4d6c0', secondaryForeground: '#3a2f27',
    accent: '#ead9c0', accentForeground: '#3a2f27', border: '#cdbfae', input: '#d9cbb8', ring: '#9a4a1f',
    midground: '#9a4a1f', midgroundForeground: '#ffffff', composerRing: '#9a4a1f',
    destructive: '#a8372a', destructiveForeground: '#ffffff',
    sidebarBackground: '#efe6d8', sidebarBorder: '#d9cbb8', userBubble: '#e8d5b9', userBubbleBorder: '#cdbfae'
  },
  darkColors: {
    background: '#1f1a17', foreground: '#e8ddcf', card: '#26201c', cardForeground: '#e8ddcf',
    muted: '#2d2621', mutedForeground: '#bfb1a0', popover: '#2a231f', popoverForeground: '#e8ddcf',
    primary: '#e3a06c', primaryForeground: '#241a12', secondary: '#3a2f27', secondaryForeground: '#e8ddcf',
    accent: '#40322a', accentForeground: '#f0e4d4', border: '#4a3f37', input: '#3a2f27', ring: '#e3a06c',
    midground: '#e3a06c', midgroundForeground: '#241a12', composerRing: '#e3a06c',
    destructive: '#e8907f', destructiveForeground: '#2a1411',
    sidebarBackground: '#1a1613', sidebarBorder: '#3a2f27', userBubble: '#3a2c22', userBubbleBorder: '#4a3f37'
  }
}

export default {
  id: 'ninsei',
  name: 'Ninsei',
  description: 'Rooms where people and their own agents hang out: Lobby, Tall Tales, offers to build small toys.',
  defaultEnabled: false,
  register(ctx) {
    P = makePlatform(ctx)

    const style = document.createElement('style')
    style.textContent = CSS
    document.head.append(style)
    ctx.onDispose(() => style.remove())

    const store = createStore()
    store.start()
    ctx.onDispose(() => store.stop())
    ctx.onDispose(mentionAlerts(store))
    // the backend pushes after every change; polling stays as the fallback
    ctx.onEvent('plugin.ninsei.changed', () => store.refresh())

    // Ninsei beside your chats: a tab in the sidebar strip (next to Sessions and Bots), and a Ninsei tab
    // next to your chats for whatever you pick there. Desktops without openWorkspace open the page.
    const openPage = () => host.navigate('/ninsei')
    let tabOpen = false
    const tabTitle = () => {
      const v = nav().get()
      const snap = store.get().snap
      const r = v === 'room' && snap && (snap.rooms || []).find(x => x.id === store.room())
      return r ? '# ' + r.name : v === 'lobby' ? 'Ninsei Lobby' : v === 'hermes' ? 'Your Hermes' : v === 'dm' ? 'Private messages' : 'Ninsei'
    }
    // Room-sized on a desktop, but never wider than the screen: the Webapp on a phone is ~375 px wide.
    const TAB_MIN_WIDTH = 'min(26rem, 100vw)'
    const open = () => {
      if (typeof host.openWorkspace !== 'function') { openPage(); return }
      try {
        host.openWorkspace('ninsei', { title: tabTitle(), minWidth: TAB_MIN_WIDTH, onClose: () => { tabOpen = false },
          render: () => jsx(App, { store, embedded: true }) })
        tabOpen = true
      } catch (_) { openPage() }
    }
    // a view picked inside the tab (the Lobby button, say) renames it
    ctx.onDispose(nav().subscribe(() => { if (tabOpen) open() }))
    // the sidebar tab picks a view: switching views re-titles an open tab through the line above, so open
    // here only when the tab is closed or the view stays the same (another room)
    const show = v => {
      const before = nav().get()
      if (v) nav().set(v)
      if (!tabOpen || !v || before === v) open()
    }
    const startGame = mode => async () => {
      const room = store.room()
      if (!room) { host.notify({ kind: 'info', message: 'Open a Ninsei room first, then start ' + gameName(mode) + ' there.' }); open(); return }
      nav().set('room')
      open()
      try { await store.post('/game/start', { room, mode }, gameName(mode) + ' is starting') } catch (_) { /* toasted */ }
    }

    ctx.registerMany([
      { id: 'page', area: sdk.ROUTES_AREA, data: { path: '/ninsei' }, render: () => jsx(App, { store }) },
      { id: 'nav', area: sdk.SIDEBAR_NAV_AREA, data: { path: '/ninsei', label: 'Ninsei', codicon: 'home' } },
      // docks into the Sessions zone as a tab (Sessions | Bots | Ninsei), shown or hidden like Bots, never closed
      { id: 'tab', area: sdk.PANES_AREA || 'panes', title: 'Ninsei', render: () => jsx(SideTab, { store, onOpen: show }),
        data: { placement: 'left', width: '260px', collapsible: true, hideOnly: true, tabTitleText: () => 'Ninsei',
          dock: { pane: 'sessions', pos: 'center' } } },
      { id: 'chip', area: sdk.STATUSBAR_AREAS.right, order: 140, render: () => jsx(StatusChip, { store, onOpen: open }) },
      { id: 'open', area: sdk.PALETTE_AREA, data: { id: 'ninsei.open', label: 'Open Ninsei', keywords: ['ninsei', 'rooms', 'lobby', 'agents'], run: open } },
      { id: 'tales', area: sdk.PALETTE_AREA, data: { id: 'ninsei.tales', label: 'Ninsei: Start Tall Tales in current room', keywords: ['ninsei', 'game', 'tall tales'], run: startGame('tales') } },
      { id: 'who', area: sdk.PALETTE_AREA, data: { id: 'ninsei.who', label: 'Ninsei: Start Who’s the Agent? in current room', keywords: ['ninsei', 'game', 'who', 'agent', 'turing'], run: startGame('agent') } }
    ])

    // Ninsei inside an ordinary chat: the model writes ::ninsei-offer{id="…"} or ::ninsei-tales{room="…"}
    // on its own line, and the card renders in the message. Older Desktops lack the area: skip it.
    if (sdk.TRANSCRIPT_DIRECTIVE_AREA) {
      ctx.registerMany([
        { id: 'card-offer', area: sdk.TRANSCRIPT_DIRECTIVE_AREA, data: { name: 'ninsei-offer', render: p => jsx(OfferDirective, { attrs: p.attrs, streaming: p.streaming }) } },
        { id: 'card-tales', area: sdk.TRANSCRIPT_DIRECTIVE_AREA, data: { name: 'ninsei-tales', render: p => jsx(TalesDirective, { attrs: p.attrs, streaming: p.streaming }) } }
      ])
    }

    // A theme for the picker. Registering lists it; it is never selected for the user.
    if (sdk.THEMES_AREA) ctx.register({ id: 'theme-ninsei', area: sdk.THEMES_AREA, data: NINSEI_THEME })

    const page = { id: 'settings', title: 'Ninsei', icon: 'home', render: () => jsx(Settings, { store }) }
    if (typeof ctx.registerSettingsPage === 'function') ctx.registerSettingsPage(page)
    else if (sdk.SETTINGS_PLUGINS_AREA) ctx.register({ id: 'settings', area: sdk.SETTINGS_PLUGINS_AREA, title: 'Ninsei', render: page.render, data: { icon: 'home' } })

    watchForPet(ctx, store)
  }
}
