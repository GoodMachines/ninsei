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
  Icon(props) {
    return jsx(sdk.Codicon, { name: props.name, size: props.size || 14, spinning: props.spinning, 'aria-hidden': true })
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
    return jsx(sdk.SandboxedFrame, { src: 'data:text/html;base64,' + b64(withCsp(props.html)), title: props.title, style: { width: '100%', height: '100%', border: 0 } })
  }
}

function makePlatform(ctx) {
  return {
    kind: 'desktop',
    inlineStyle: false,
    rest: (path, opts) => ctx.rest(path, opts),
    toast(kind, message) { host.notify({ kind: kind === 'error' ? 'error' : 'info', message }) },
    copy: text => Promise.resolve(ctx.os && ctx.os.writeClipboard ? ctx.os.writeClipboard(text) : false).catch(() => false),
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
      host.navigate(sdk.pluginSettingsHref ? sdk.pluginSettingsHref('xenia') : '/settings?tab=plugins&plugin=xenia')
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
      const line = o.status === 'open' ? agent + ' has an idea in ' + room + ': ' + o.title + '. Review it in Xenia.'
        : 'Your build “' + o.title + '” is ready to share in ' + room + '.'
      ctx.pet.say(line, { id: 'offer', tone: 'wait', ttlMs: 15000 })
    }
  }))
}

// The "Xenia" theme: warm paper by day, dim lamplight by night. The hue is Xenia's own default
// agent colour (28, amber) pulled down to a calm, low-chroma family. Every text pair is
// at least WCAG AA (4.5:1): checked with the SDK's contrastRatio formula, lowest pair 5.0:1 light
// (primary on card) and 7.1:1 dark.
const XENIA_THEME = {
  name: 'xenia',
  label: 'Xenia',
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
  id: 'xenia',
  name: 'Xenia',
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
    // the backend pushes after every change; polling stays as the fallback
    ctx.onEvent('plugin.xenia.changed', () => store.refresh())

    const open = () => host.navigate('/xenia')
    const startTales = async () => {
      const room = store.room()
      if (!room) { host.notify({ kind: 'info', message: 'Open a Xenia room first, then start Tall Tales there.' }); open(); return }
      open()
      try { await store.post('/game/start', { room }, 'Tall Tales is starting') } catch (_) { /* toasted */ }
    }

    ctx.registerMany([
      { id: 'page', area: sdk.ROUTES_AREA, data: { path: '/xenia' }, render: () => jsx(App, { store }) },
      { id: 'nav', area: sdk.SIDEBAR_NAV_AREA, data: { path: '/xenia', label: 'Xenia', codicon: 'home' } },
      { id: 'chip', area: sdk.STATUSBAR_AREAS.right, order: 140, render: () => jsx(StatusChip, { store, onOpen: open }) },
      { id: 'open', area: sdk.PALETTE_AREA, data: { id: 'xenia.open', label: 'Open Xenia', keywords: ['xenia', 'rooms', 'lobby', 'agents'], run: open } },
      { id: 'tales', area: sdk.PALETTE_AREA, data: { id: 'xenia.tales', label: 'Xenia: Start Tall Tales in current room', keywords: ['xenia', 'game', 'tall tales'], run: startTales } }
    ])

    // Xenia inside an ordinary chat: the model writes ::xenia-offer{id="…"} or ::xenia-tales{room="…"}
    // on its own line, and the card renders in the message. Older Desktops lack the area: skip it.
    if (sdk.TRANSCRIPT_DIRECTIVE_AREA) {
      ctx.registerMany([
        { id: 'card-offer', area: sdk.TRANSCRIPT_DIRECTIVE_AREA, data: { name: 'xenia-offer', render: p => jsx(OfferDirective, { attrs: p.attrs, streaming: p.streaming }) } },
        { id: 'card-tales', area: sdk.TRANSCRIPT_DIRECTIVE_AREA, data: { name: 'xenia-tales', render: p => jsx(TalesDirective, { attrs: p.attrs, streaming: p.streaming }) } }
      ])
    }

    // A theme for the picker. Registering lists it; it is never selected for the user.
    if (sdk.THEMES_AREA) ctx.register({ id: 'theme-xenia', area: sdk.THEMES_AREA, data: XENIA_THEME })

    const page = { id: 'settings', title: 'Xenia', icon: 'home', render: () => jsx(Settings, { store }) }
    if (typeof ctx.registerSettingsPage === 'function') ctx.registerSettingsPage(page)
    else if (sdk.SETTINGS_PLUGINS_AREA) ctx.register({ id: 'settings', area: sdk.SETTINGS_PLUGINS_AREA, title: 'Xenia', render: page.render, data: { icon: 'home' } })

    watchForPet(ctx, store)
  }
}
