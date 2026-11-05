  // ---------------------------------------------------------------------------------------------
  // dashboard platform: fetch, timers, toasts, clipboard, storage, and the kit adapter. The
  // dashboard SDK has fewer components than Desktop, so a few are plain elements styled with the
  // dashboard's own theme variables.
  // ---------------------------------------------------------------------------------------------

  const toasts = { list: [], fns: new Set(), seq: 0 }
  function pushToast(kind, message) {
    const id = ++toasts.seq
    toasts.list = toasts.list.concat([{ id, kind, message }]).slice(-3)
    toasts.fns.forEach(fn => fn(toasts.list))
    window.setTimeout(() => {
      toasts.list = toasts.list.filter(t => t.id !== id)
      toasts.fns.forEach(fn => fn(toasts.list))
    }, kind === 'error' ? 7000 : 4000)
  }

  const P = {
    kind: 'dashboard',
    inlineStyle: true,
    rest(path, opts) {
      const o = opts || {}
      const init = o.method && o.method !== 'GET'
        ? { method: o.method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(o.body || {}) }
        : undefined
      return SDK.fetchJSON('/api/plugins/hearth' + path, init)
    },
    toast: pushToast,
    copy(text) {
      try { return navigator.clipboard.writeText(text).then(() => true, () => false) } catch (_) { return Promise.resolve(false) }
    },
    // the shared animation loop: one rAF chain, parked whenever idle() says nothing moves
    loop(draw, idle) {
      let frame = 0
      const tick = now => { frame = 0; draw(now); if (!idle()) frame = window.requestAnimationFrame(tick) }
      return {
        wake() { if (!frame) frame = window.requestAnimationFrame(tick) },
        dispose() { if (frame) window.cancelAnimationFrame(frame); frame = 0 }
      }
    },
    setTimeout(fn, ms) { const t = window.setTimeout(fn, ms); return () => window.clearTimeout(t) },
    setInterval(fn, ms) { const t = window.setInterval(fn, ms); return () => window.clearInterval(t) },
    listen(target, type, fn) { target.addEventListener(type, fn); return () => target.removeEventListener(type, fn) },
    prefs: {
      get(k, d) { try { const v = window.localStorage.getItem('hearth.' + k); return v == null ? d : JSON.parse(v) } catch (_) { return d } },
      set(k, v) { try { window.localStorage.setItem('hearth.' + k, JSON.stringify(v)) } catch (_) { /* private mode */ } }
    },
    // no composer to hand a prompt to from the browser: the caller shows it with a Copy button
    openBuild() { return Promise.resolve(false) },
    openSettings() {}
  }

  // a handful of line icons, drawn on a 16px grid with the current text colour
  const ICONS = {
    add: 'M8 3v10M3 8h10',
    link: 'M6.5 9.5l3-3M7 4.5l1-1a2.8 2.8 0 0 1 4 4l-1 1M9 11.5l-1 1a2.8 2.8 0 0 1-4-4l1-1',
    compass: 'M8 1.8a6.2 6.2 0 1 0 0 12.4A6.2 6.2 0 0 0 8 1.8zM10.6 5.4L9.2 9.2 5.4 10.6 6.8 6.8z',
    gear: 'M8 5.6a2.4 2.4 0 1 0 0 4.8 2.4 2.4 0 0 0 0-4.8zM8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M3.4 12.6l1.1-1.1M11.5 4.5l1.1-1.1',
    refresh: 'M13 4v3h-3M3 12V9h3M12.4 7A4.6 4.6 0 0 0 4 5.2M3.6 9a4.6 4.6 0 0 0 8.4 1.8',
    copy: 'M5.5 5.5h7v7h-7zM3.5 10.5v-7h7',
    play: 'M5 3.5l7 4.5-7 4.5z',
    send: 'M2.5 8L13.5 3 10 13.5 7.7 8.6zM7.7 8.6L13.5 3',
    game: 'M5 5.5h6a3 3 0 0 1 3 3v.5a2.5 2.5 0 0 1-4.4 1.6L9 10H7l-.6.6A2.5 2.5 0 0 1 2 9v-.5a3 3 0 0 1 3-3zM5 7.2v2M4 8.2h2M10.5 8h.01M11.8 9h.01',
    shield: 'M8 1.8l5 2v3.7c0 3-2.2 5.6-5 6.7-2.8-1.1-5-3.7-5-6.7V3.8z',
    warning: 'M8 2l6.2 11H1.8zM8 6.5v3M8 11.3h.01',
    globe: 'M8 1.8a6.2 6.2 0 1 0 0 12.4A6.2 6.2 0 0 0 8 1.8zM1.8 8h12.4M8 1.8c1.7 1.8 2.5 3.9 2.5 6.2S9.7 12.4 8 14.2C6.3 12.4 5.5 10.3 5.5 8S6.3 3.6 8 1.8z',
    edit: 'M10.5 2.5l3 3-8 8H2.5v-3zM9 4l3 3',
    organization: 'M5.5 6.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM2 13c0-2.2 1.6-4 3.5-4S9 10.8 9 13M11 7a1.7 1.7 0 1 0 0-3.4A1.7 1.7 0 0 0 11 7zM10.5 9c1.9 0 3.5 1.6 3.5 4',
    'sign-out': 'M6 2.5H3v11h3M10 5l3 3-3 3M13 8H6',
    clock: 'M8 1.8a6.2 6.2 0 1 0 0 12.4A6.2 6.2 0 0 0 8 1.8zM8 4.5V8l2.3 1.5',
    flame: 'M8 14c-2.6 0-4.5-1.8-4.5-4.3C3.5 6.5 6.5 5 7 1.8c2 1.4 5.5 4.3 5.5 7.9C12.5 12.2 10.6 14 8 14zM8 14c-1.2 0-2-.9-2-2 0-1.6 1.4-2.3 2-3.6.8.8 2 1.9 2 3.6 0 1.1-.8 2-2 2z',
    close: 'M4 4l8 8M12 4l-8 8',
    lock: 'M4.5 7.5h7v6h-7zM6 7.5V5.5a2 2 0 0 1 4 0v2',
    reply: 'M6.5 4L3 7.5 6.5 11M3 7.5h6.5a3.5 3.5 0 0 1 3.5 3.5v1'
  }

  function Icon(props) {
    const s = props.size || 14
    return jsx('svg', { width: s, height: s, viewBox: '0 0 16 16', fill: 'none', stroke: 'currentColor', strokeWidth: 1.4,
      strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true, className: props.spinning ? 'h-spin' : undefined,
      style: { flex: 'none' }, children: jsx('path', { d: ICONS[props.name] || ICONS.add }) })
  }

  // The dashboard's Button is the theme's own (mono, arc border). Icon buttons are plain and quiet.
  function Button(props) {
    const { variant, size, className, children } = props
    const rest = Object.assign({}, props)
    delete rest.variant; delete rest.size; delete rest.className; delete rest.children
    if (size === 'icon' || variant === 'ghost') {
      return jsx('button', Object.assign({ type: 'button', className: cx('h-dbtn', size === 'icon' && 'h-dbtn-icon', className) }, rest, { children }))
    }
    return jsx(C.Button, Object.assign({ className: cx(size === 'sm' && 'h-dbtn-sm', className), outlined: variant === 'secondary' || variant === 'outline',
      destructive: variant === 'danger' }, rest, { children }))
  }

  function Dialog(props) {
    return jsx(C.Dialog, { open: !!props.open, onOpenChange: v => { if (!v) props.onClose() }, children:
      jsx(C.DialogContent, { style: props.wide ? { maxWidth: 680, width: 'calc(100vw - 32px)' } : { width: 'calc(100vw - 32px)', maxWidth: 460 },
        children: jsxs('div', { className: 'hx h-col', style: { gap: 14, padding: 20 }, children: [
          jsxs(C.DialogHeader, { style: { padding: 0 }, children: [
            jsx(C.DialogTitle, { children: props.title }),
            props.description && jsx(C.DialogDescription, { children: props.description })
          ] }),
          props.children,
          props.footer && jsx('div', { className: 'h-actions', style: { justifyContent: 'flex-end' }, children: props.footer })
        ] }) }) })
  }

  function Toggle(props) {
    return jsxs('label', { className: 'h-row', style: { alignItems: 'flex-start', gap: 10, cursor: 'pointer' }, children: [
      jsx('input', { type: 'checkbox', checked: !!props.checked, onChange: e => props.onChange(e.target.checked),
        style: { marginTop: 3, accentColor: 'var(--h-accent)' } }),
      jsxs('span', { className: 'h-col', style: { gap: 2 }, children: [
        jsx('span', { style: { fontWeight: 600 }, children: props.label }),
        props.description && jsx('span', { className: 'h-faint h-small', children: props.description })
      ] })
    ] })
  }

  const K = {
    Button,
    Input: C.Input,
    Dialog,
    Icon,
    Toggle,
    Tip: props => jsx('span', { title: typeof props.label === 'string' ? props.label : undefined, style: { display: 'inline-flex' }, children: props.children }),
    // a shared toy: opaque origin (no allow-same-origin), scripts only
    Toy: props => jsx('iframe', { title: props.title, sandbox: 'allow-scripts', srcDoc: props.html, referrerPolicy: 'no-referrer' })
  }

  const DASH_CSS = `
.h-dbtn{display:inline-flex;align-items:center;justify-content:center;gap:6px;border:0;background:transparent;color:var(--h-fg2);border-radius:6px;padding:4px 8px;cursor:pointer;font-size:12px;white-space:nowrap}
.h-dbtn:hover:not(:disabled){background:var(--h-hover);color:var(--h-fg)}
.h-dbtn:disabled{opacity:.45;cursor:default}
.h-dbtn-icon{width:28px;height:28px;padding:0}
.h-dbtn-sm{font-size:11px!important;padding:4px 10px!important;height:auto!important}
.hx button svg:not(:only-child){margin-right:6px}
.h-spin{animation:h-spin 1s linear infinite}
@keyframes h-spin{to{transform:rotate(360deg)}}
.h-toasts{position:fixed;right:20px;bottom:20px;display:flex;flex-direction:column;gap:8px;z-index:60;max-width:360px}
.h-toast{border:1px solid var(--h-line2);background:var(--h-card);color:var(--h-fg);padding:10px 14px;border-radius:10px;font-size:12.5px;box-shadow:0 12px 32px -16px var(--h-shadow)}
.h-toast[data-kind=error]{border-color:color-mix(in srgb,var(--h-bad) 60%,transparent)}
`

  function Toasts() {
    const [list, setList] = useState(toasts.list)
    useEffect(() => { toasts.fns.add(setList); return () => toasts.fns.delete(setList) }, [])
    return jsx('div', { className: 'hx h-toasts', role: 'status', 'aria-live': 'polite', children: list.map(t =>
      jsx(ToastItem, { t }, t.id)) })
  }
  function ToastItem(props) {
    const ref = useEnter(true)
    return jsx('div', { ref, className: 'h-toast', 'data-kind': props.t.kind, children: props.t.message })
  }

  // The tab mounts inside the dashboard's scrolling <main>. Size the page to the space left
  // below its top edge so the room's header and composer stay put and only the timeline scrolls.
  function useFitHeight() {
    const ref = useRef(null)
    const [h, setH] = useState(0)
    useEffect(() => {
      const fit = () => {
        const el = ref.current
        if (!el) return
        const top = el.getBoundingClientRect().top
        setH(Math.max(480, Math.floor(window.innerHeight - Math.max(0, top) - 24)))
      }
      fit()
      const t = window.setTimeout(fit, 300)
      window.addEventListener('resize', fit)
      return () => { window.clearTimeout(t); window.removeEventListener('resize', fit) }
    }, [])
    return [ref, h]
  }

  let store = null
  function HearthTab() {
    if (!store) store = createStore()
    useEffect(() => { store.start(); return () => store.stop() }, [])
    const [ref, h] = useFitHeight()
    return jsxs('div', { ref, className: 'h-dashframe', style: h ? { height: h } : { height: '75vh' }, children: [
      jsx('style', { children: DASH_CSS }),
      jsx(App, { store }),
      jsx(Toasts, {})
    ] })
  }

  window.__HERMES_PLUGINS__.register('hearth', HearthTab)
})()
