"""Desktop: Ninsei's tab in the sidebar strip (next to Sessions and Bots) and the Ninsei tab beside your chats.

Loads the real built desktop/plugin.js under node with a stub SDK and React (hooks as plain values,
jsx as plain objects), registers it, then clicks through the sidebar tab the way a person would."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

HARNESS = r"""
globalThis.document = { createElement: () => ({ remove() {} }), head: { append() {} } }
const regs = [], opened = [], navs = []
const snap = { settings: { onboarded: true }, me: { name: 'Maya', pk: 'm', agent: { name: 'Ada', pk: 'a', state: 'activity: idle' } },
  budget: { pct: 0.1, used: 1, limit: 10 }, rooms: [{ id: 'r1', name: 'shader club', unread: 0, online: 2 }], offers: [], drafts: [], line: {} }
globalThis.__SDK__ = {
  host: { navigate: p => navs.push(p), notify() {}, openWorkspace: (id, o) => { opened.push({ id, title: o.title, el: o.render() }); return () => {} } },
  ROUTES_AREA: 'routes', SIDEBAR_NAV_AREA: 'sidebar.nav', PALETTE_AREA: 'palette', STATUSBAR_AREAS: { right: 'statusBar.right' }
}
const el = (type, props) => ({ type, props: props || {} })
globalThis.__REACT__ = { Fragment: 'F', createContext: () => ({ Provider: 'P' }), useContext: () => ({}), useCallback: f => f,
  useEffect() {}, useLayoutEffect() {}, useMemo: f => f(), useRef: v => ({ current: v }), useState: v => [typeof v === 'function' ? v() : v, () => {}] }
globalThis.__JSX__ = { jsx: el, jsxs: el }
const store = {}
const ctx = {
  register(c) { regs.push(c); return () => {} }, registerMany(cs) { cs.forEach(c => regs.push(c)) },
  onDispose() {}, onEvent() {}, setTimeout: () => () => {}, setInterval: () => () => {}, addEventListener() {},
  storage: { get: (k, d) => store[k] ?? d, set: (k, v) => { store[k] = v } },
  rest: async () => snap
}
const mod = await import(process.argv[2])
mod.default.register(ctx)
await new Promise(r => setTimeout(r, 20))   // the first /state lands
const tab = regs.find(c => c.id === 'tab')
const side = tab.render()
const rendered = side.type(side.props)                     // SideTab
const rail = rendered.props.children.find(c => c && c.type && c.type.name === 'Rail')
const lobbyRow = () => rail.type(rail.props)               // Rail's tree
const find = (node, pred) => {
  if (!node || typeof node !== 'object') return null
  if (Array.isArray(node)) { for (const c of node) { const f = find(c, pred); if (f) return f } return null }
  if (pred(node)) return node
  for (const c of [].concat(node.props && node.props.children || [])) { const f = find(c, pred); if (f) return f }
  return null
}
const tree = lobbyRow()
find(tree, n => n.props && n.props.label === 'Lobby').props.onClick()
find(tree, n => n.type === 'button' && n.props.className === 'h-navrow' && JSON.stringify(n.props.children).includes('shader club')).props.onClick()
console.log(JSON.stringify({
  tab: { area: tab.area, title: tab.title, data: { ...tab.data, tabTitleText: tab.data.tabTitleText() } },
  opened: opened.map(o => ({ id: o.id, title: o.title, embedded: o.el.props.embedded, app: o.el.type.name })),
  navs, view: store.view, room: store.room
}))
"""


def test_sidebar_tab_docks_beside_sessions_and_opens_rooms_beside_chats(tmp_path):
    src = (ROOT / "desktop" / "plugin.js").read_text()
    src = (src.replace("import * as sdk from '@hermes/plugin-sdk'", "const sdk = globalThis.__SDK__")
              .replace("import { jsx, jsxs } from 'react/jsx-runtime'", "const { jsx, jsxs } = globalThis.__JSX__"))
    src, n = re.subn(r"^import (\{[^}]*\}) from 'react'$", r"const \1 = globalThis.__REACT__", src, count=1, flags=re.M)
    assert n == 1
    plugin = tmp_path / "plugin.mjs"
    plugin.write_text(src)
    harness = tmp_path / "harness.mjs"
    harness.write_text(HARNESS)
    out = subprocess.run([NODE, str(harness), plugin.as_uri()], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr[-2000:]
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got["tab"]["area"] == "panes" and got["tab"]["title"] == "Ninsei"
    data = got["tab"]["data"]
    assert data["dock"] == {"pane": "sessions", "pos": "center"} and data["placement"] == "left" and data["hideOnly"] is True
    assert data["tabTitleText"] == "Ninsei"
    # Lobby, then a room: each opens (or re-fronts) the one Ninsei tab beside your chats, named for what it shows
    assert got["opened"] == [{"id": "ninsei", "title": "Ninsei Lobby", "embedded": True, "app": "App"},
                             {"id": "ninsei", "title": "# shader club", "embedded": True, "app": "App"}]
    assert got["navs"] == [] and got["view"] == "room" and got["room"] == "r1"



# setup: the same harness up to registering, with a first run's /state, then "Open Ninsei" from the palette
SETUP_HARNESS = (HARNESS.split("const tab = regs.find")[0]
                 .replace("settings: { onboarded: true }", "settings: { onboarded: false }")
                 .replace("onDispose() {}, onEvent() {},", "onDispose() {}, onEvent(n, f) { events[n] = f },")
                 .replace("const store = {}", "const store = {}, events = {}")) + """
regs.find(c => c.id === 'open').data.run()
const titles = [opened[opened.length - 1].title]
snap.settings.onboarded = true                      // the save lands; the backend pushes a change
events['plugin.ninsei.changed']()
await new Promise(r => setTimeout(r, 20))
titles.push(opened[opened.length - 1].title)
console.log(JSON.stringify({ titles, opens: opened.length }))
"""


def test_tab_says_set_up_during_setup_and_renames_when_it_finishes(tmp_path):
    # 2026-11-08, filming: setup ran under a tab still called "# shader club", the last room's name
    src = (ROOT / "desktop" / "plugin.js").read_text()
    src = (src.replace("import * as sdk from '@hermes/plugin-sdk'", "const sdk = globalThis.__SDK__")
              .replace("import { jsx, jsxs } from 'react/jsx-runtime'", "const { jsx, jsxs } = globalThis.__JSX__"))
    src, n = re.subn(r"^import (\{[^}]*\}) from 'react'$", r"const \1 = globalThis.__REACT__", src, count=1, flags=re.M)
    assert n == 1
    plugin = tmp_path / "plugin.mjs"
    plugin.write_text(src)
    harness = tmp_path / "harness.mjs"
    harness.write_text(SETUP_HARNESS)
    out = subprocess.run([NODE, str(harness), plugin.as_uri()], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr[-2000:]
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got["titles"] == ["Set up Ninsei", "Ninsei"] and got["opens"] == 2
