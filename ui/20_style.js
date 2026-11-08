// ---------------------------------------------------------------------------------------------
// styles. Every colour is a theme variable: each platform prelude maps the `--h-*` tokens below
// onto its own theme (`--ui-*` in Desktop, `--color-*` in the dashboard), so Ninsei reskins with
// every theme. Agent tints are the theme's own foreground rotated to the agent's hue.
// ---------------------------------------------------------------------------------------------

const CSS = TOKENS + `
.hx{color:var(--h-fg);font-size:13px;line-height:1.45;-webkit-font-smoothing:antialiased}
.hx *{box-sizing:border-box}
.hx button{font:inherit}
.hx .h-muted{color:var(--h-fg2)}
.hx .h-faint{color:var(--h-fg3)}
.hx .h-small{font-size:11.5px}
.hx .h-tiny{font-size:10.5px;letter-spacing:.01em}
.hx .h-row{display:flex;align-items:center;gap:8px;min-width:0}
.hx .h-col{display:flex;flex-direction:column;gap:8px;min-width:0}
.hx .h-grow{flex:1;min-width:0}
.hx .h-trunc{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hx .h-sec{font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--h-fg3);font-weight:600}
.hx .h-agent{--tint:var(--h-accent);--tint:oklch(from var(--h-fg) l 0.15 var(--hue,28))}

/* page grid: left rail, centre, right rail. Collapses by container width, not viewport. */
.h-page{container-type:inline-size;position:relative;height:100%;min-height:0}
.h-grid{display:grid;grid-template-columns:220px minmax(0,1fr) 240px;height:100%;min-height:0}
.h-left,.h-right{min-height:0;overflow-y:auto;padding:14px 10px}
.h-left{border-right:1px solid var(--h-line)}
.h-right{border-left:1px solid var(--h-line)}
.h-center{display:flex;flex-direction:column;min-height:0;min-width:0}
.h-grid[data-embedded]{grid-template-columns:minmax(0,1fr) 240px}
.h-navbar{display:none}
.h-tab{height:100%;min-height:0;overflow-y:auto;padding:10px 8px}
@container (max-width: 980px){.h-grid{grid-template-columns:200px minmax(0,1fr)}.h-grid[data-embedded]{grid-template-columns:minmax(0,1fr)}.h-right{display:none}.h-grid[data-people=open] .h-right{display:block;position:absolute;right:0;top:0;bottom:0;width:260px;z-index:5;background:var(--h-bg);box-shadow:-12px 0 24px -16px var(--h-shadow)}
.h-grid[data-people=open] .h-scrim{display:block;position:absolute;inset:0;z-index:4;background:color-mix(in srgb,var(--h-bg) 55%,transparent)}.h-grid[data-people=open] .h-right-bar{display:flex;justify-content:flex-end;margin:-6px -2px 4px}}
@container (max-width: 720px){.h-grid,.h-grid[data-embedded]{grid-template-columns:minmax(0,1fr)}
.h-left{display:none}
.h-grid[data-nav=open] .h-left{display:block;position:absolute;left:0;top:0;bottom:0;width:min(280px,86%);z-index:6;background:var(--h-bg);border-right:1px solid var(--h-line);box-shadow:12px 0 24px -16px var(--h-shadow)}
.h-grid[data-nav=open] .h-scrim-nav{display:block;position:absolute;inset:0;z-index:5;background:color-mix(in srgb,var(--h-bg) 55%,transparent)}
.h-navbar{display:flex;align-items:center;gap:6px;padding:6px 10px;border-bottom:1px solid var(--h-line);flex:none}
.h-head{padding:10px 12px;flex-wrap:wrap;row-gap:4px}.h-head>.h-grow{flex:1 1 100%;min-width:min(100%,16ch)}.h-head>.h-grow h2{min-width:16ch}.h-head>.h-grow .h-row{flex-wrap:wrap}.h-timeline,.h-composer{padding-left:12px;padding-right:12px}
.h-grid[data-people=open] .h-right{left:0;right:0;top:auto;width:auto;max-height:72%;border-left:0;border-top:1px solid var(--h-line2);border-radius:14px 14px 0 0;box-shadow:0 -12px 28px -16px var(--h-shadow)}
.h-composer{padding-bottom:max(14px,env(safe-area-inset-bottom))}}
.h-grid{position:relative}
.h-scrim,.h-right-bar{display:none}

/* the People toggle only shows when the right rail is folded away */
.h-peoplebtn{display:none!important}
@container (max-width: 980px){.h-peoplebtn{display:inline-flex!important}}

/* left rail */
.h-brand{display:flex;align-items:flex-start;gap:8px;padding:0 6px 12px}.h-brand>:first-child,.h-brand>:last-child{margin-top:4px}
.h-wordmark{display:block;margin:2px 0 4px;flex:none}
.h-nav{display:flex;flex-direction:column;gap:1px;margin-bottom:14px}
.h-navrow{display:flex;align-items:center;gap:8px;width:100%;padding:5px 8px;border-radius:6px;border:0;background:transparent;color:var(--h-fg2);cursor:pointer;text-align:left;min-width:0}
.h-navrow:hover{background:var(--h-hover);color:var(--h-fg)}
.h-navrow[data-on=true]{background:var(--h-raise);color:var(--h-fg)}
.h-navrow .h-dot{width:6px;height:6px;border-radius:50%;background:var(--h-accent);flex:none}
.h-navrow .h-dot-quiet{background:var(--h-fg3)}
.h-navrow .h-count{font-size:10.5px;color:var(--h-fg3);font-variant-numeric:tabular-nums}
.h-hash{color:var(--h-fg3);width:14px;text-align:center;flex:none}
.h-navhead{display:flex;align-items:center;justify-content:space-between;padding:0 8px 4px}

/* centre: header, timeline, composer */
.h-head{display:flex;align-items:center;gap:10px;padding:12px 18px;border-bottom:1px solid var(--h-line);min-height:56px}
.h-head h2{margin:0;font-size:15px;font-weight:600;letter-spacing:.005em}
.h-chips{display:flex;flex-wrap:wrap;gap:4px}
.h-chip{display:inline-flex;align-items:center;gap:4px;padding:1px 7px;border-radius:999px;font-size:11px;background:var(--h-raise);color:var(--h-fg2);border:1px solid transparent;white-space:nowrap}
.h-chip[data-hit=true]{color:var(--h-fg);border-color:color-mix(in oklch,var(--h-accent) 55%,transparent);background:color-mix(in oklch,var(--h-accent) 14%,transparent)}
.h-chip button{border:0;background:transparent;color:inherit;padding:0;cursor:pointer;line-height:1}
.h-vibes .h-chip{font:inherit;font-size:12px;padding:3px 10px;cursor:pointer}
.h-vibes .h-chip:hover{color:var(--h-fg);background:var(--h-hover)}
.h-vibes .h-chip:focus-visible{outline:2px solid var(--h-accent);outline-offset:1px}
.h-scroll{flex:1;min-height:96px;overflow-y:auto;overscroll-behavior:contain}
.h-timeline{display:flex;flex-direction:column;padding:14px 18px 8px;gap:2px;max-width:860px;width:100%;margin:0 auto}
.h-msg{display:grid;grid-template-columns:32px minmax(0,1fr);gap:0 10px;padding:3px 0}
.h-msg[data-first=true]{margin-top:10px}
.h-msg[data-quoted=true]:not([data-first=true]){padding-top:17px}
.h-msg .h-gutter{display:flex;justify-content:center;padding-top:1px}
.h-msg .h-meta{display:flex;align-items:baseline;gap:6px;margin-bottom:1px;min-width:0}
.h-msg .h-meta b{font-weight:600}
.h-msg .h-text{white-space:pre-wrap;overflow-wrap:anywhere;color:var(--h-fg)}
.h-initial{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;font-size:12px;font-weight:600;background:var(--h-raise);color:var(--h-fg2)}
.h-msg[data-role=agent] .h-bubble{background:color-mix(in oklch,var(--tint) 10%,transparent);border:1px solid color-mix(in oklch,var(--tint) 22%,transparent);border-radius:4px 12px 12px 12px;padding:7px 11px;display:inline-block;max-width:100%}
.h-msg[data-role=agent] .h-meta b{color:color-mix(in oklch,var(--tint) 70%,var(--h-fg))}
.h-owner{color:var(--h-fg3);font-size:11.5px}
.h-line{display:flex;align-items:center;justify-content:center;gap:8px;padding:6px 0;color:var(--h-fg3);font-size:11.5px;text-align:center}
.h-line::before,.h-line::after{content:"";flex:1;max-width:80px;height:1px;background:var(--h-line)}
.h-system{display:flex;align-items:center;gap:8px;padding:6px 10px;margin:6px 0 6px 42px;border-radius:8px;border:1px dashed var(--h-line2);color:var(--h-fg2);font-size:12px}
.h-impostor{display:inline-flex;align-items:center;gap:6px;margin-top:4px;padding:2px 9px 2px 7px;border-radius:999px;font-size:11.5px;color:var(--h-fg);background:color-mix(in oklch,var(--h-warn) 16%,transparent);border:1px solid color-mix(in oklch,var(--h-warn) 45%,transparent)}
.h-impostor svg,.h-impostor .codicon{color:var(--h-warn)}
.h-whotag{flex:none;font-size:11px;line-height:18px;padding:0 8px;border-radius:999px;color:var(--h-fg3);border:1px solid var(--h-line)}
.h-whotag[data-on=true]{color:var(--h-fg);background:color-mix(in oklch,var(--h-accent) 22%,transparent);border-color:color-mix(in oklch,var(--h-accent) 55%,transparent)}
.h-opt[data-agent=true]{border-color:color-mix(in oklch,var(--h-accent) 45%,transparent)}
.h-person-row .h-impostor,.h-agentrow .h-impostor{margin-top:0;padding:0 7px 0 5px;gap:4px;font-size:10.5px;line-height:18px;flex-shrink:0}
.h-msg[data-impostor=true] .h-text{color:var(--h-fg2)}
.h-at{color:color-mix(in oklch,var(--h-accent) 75%,var(--h-fg));background:color-mix(in oklch,var(--h-accent) 14%,transparent);border-radius:4px;padding:0 2px;font-weight:500}
.h-at[data-me=true]{color:var(--h-fg);background:color-mix(in oklch,var(--h-warn) 26%,transparent)}
.h-msg[data-mentioned=true]{background:color-mix(in oklch,var(--h-warn) 7%,transparent);box-shadow:inset 2px 0 0 var(--h-warn);border-radius:0 6px 6px 0}
.h-msg{position:relative}
.h-msg::after{content:"";position:absolute;inset:0;border-radius:6px;background:var(--h-accent);opacity:calc(var(--h-flash,0)*.22);pointer-events:none}
.h-msg[data-flash=true]{--h-flash:1}
.h-bar{position:absolute;top:-14px;right:4px;z-index:5;display:flex;align-items:center;gap:2px;padding:2px;border:1px solid var(--h-line2);border-radius:8px;background:var(--h-card);box-shadow:0 6px 18px -8px var(--h-shadow);opacity:0;pointer-events:none}
.h-msg:hover .h-bar,.h-msg:focus-within .h-bar,.h-msg[data-bar=true] .h-bar{opacity:1;pointer-events:auto}
.h-bar-btn{display:grid;place-items:center;width:26px;height:24px;padding:0;border:0;border-radius:6px;background:transparent;color:var(--h-fg2);cursor:pointer}
.h-bar-btn:hover,.h-bar-btn[aria-expanded=true]{background:var(--h-hover);color:var(--h-fg)}
.h-bar-btn:focus-visible,.h-pick:focus-visible,.h-react:focus-visible,.h-quote:focus-visible{outline:2px solid var(--h-accent);outline-offset:1px}
.h-picker{position:absolute;top:calc(100% + 4px);right:0;display:flex;gap:2px;padding:4px;border:1px solid var(--h-line2);border-radius:10px;background:var(--h-card);box-shadow:var(--h-shadow)}
.h-pick{display:grid;place-items:center;width:30px;height:30px;border-radius:7px;font-size:17px;line-height:1;cursor:pointer;user-select:none}
.h-pick:hover,.h-pick:focus-visible{background:var(--h-hover)}
.h-pick[aria-checked=true]{background:color-mix(in oklch,var(--h-accent) 22%,transparent)}
.h-reacts{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}
.h-react{display:inline-flex;align-items:center;gap:5px;height:22px;padding:0 8px;border-radius:999px;border:1px solid var(--h-line2);background:var(--h-raise);color:var(--h-fg2);font:inherit;font-size:12px;cursor:pointer}
.h-react:hover{border-color:var(--h-fg3)}
.h-react[data-mine=true]{color:var(--h-fg);border-color:color-mix(in oklch,var(--h-accent) 60%,transparent);background:color-mix(in oklch,var(--h-accent) 18%,transparent)}
.h-react-e{font-size:13px;line-height:1}
.h-react-n{font-variant-numeric:tabular-nums;font-weight:600}
.h-quote-row{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-bottom:2px}
.h-quote{display:inline-flex;align-items:center;gap:6px;max-width:100%;min-width:0;padding:1px 8px 1px 6px;border:0;border-left:2px solid var(--h-line2);border-radius:0 6px 6px 0;background:transparent;color:var(--h-fg3);font:inherit;font-size:12px;text-align:left;cursor:pointer}
.h-quote:hover{background:var(--h-hover);color:var(--h-fg2)}
.h-quote b{font-weight:600;color:var(--h-fg2);flex:none}
.h-quote-t{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.h-quote-gone{cursor:default;font-style:italic;margin-bottom:2px}
.h-deleted-t{font-style:italic;color:var(--h-fg3)}
.h-edited{color:var(--h-fg3);font-size:11px}
.h-edit{display:flex;flex-direction:column;gap:4px}
.h-edit textarea{width:100%;box-sizing:border-box;resize:none;font:inherit;color:var(--h-fg);background:var(--h-card);border:1px solid color-mix(in oklch,var(--h-accent) 60%,var(--h-line2));border-radius:8px;padding:6px 9px;outline:none}
.h-quote-gone:hover{background:transparent;color:var(--h-fg3)}
.h-tlwrap{position:relative;flex:1;min-height:96px;display:flex;flex-direction:column}
.h-tlwrap>.h-scroll{flex:1;min-height:0}
.h-newline{display:flex;align-items:center;gap:10px;margin:12px 0 4px;color:var(--h-bad);font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase}
.h-newline::before,.h-newline::after{content:"";flex:1;height:1px;background:color-mix(in oklch,var(--h-bad) 55%,transparent)}
.h-day{display:flex;align-items:center;gap:10px;margin:14px 0 4px;color:var(--h-fg3);font-size:11px;font-weight:600;letter-spacing:.03em}
.h-day::before,.h-day::after{content:"";flex:1;height:1px;background:var(--h-line)}
.h-earlier{display:flex;justify-content:center;padding:4px 0 8px}
.h-gtime{align-self:start;padding-top:3px;font-size:10px;line-height:1.45;color:var(--h-fg3);opacity:0;white-space:nowrap;font-variant-numeric:tabular-nums}
.h-msg:hover .h-gtime,.h-msg:focus-within .h-gtime{opacity:1}
.h-msg[data-faint=true]{opacity:.5}
.h-failrow{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px;margin-top:2px;color:var(--h-bad)}
.h-ac-emoji{width:22px;text-align:center;font-size:17px;line-height:1;flex:none}
.h-sr-day{padding:8px 10px 2px;font-size:10.5px;font-weight:600;letter-spacing:.03em;color:var(--h-fg3)}
.h-jump{position:absolute;left:0;right:0;bottom:10px;display:flex;justify-content:center;pointer-events:none;z-index:6}
.h-jump-btn{pointer-events:auto;display:inline-flex;align-items:center;gap:6px;height:30px;padding:0 13px 0 10px;border:1px solid var(--h-line2);border-radius:999px;background:var(--h-card);color:var(--h-fg);font:inherit;font-size:12.5px;font-weight:600;cursor:pointer;box-shadow:0 8px 22px -10px var(--h-shadow)}
.h-jump-btn:hover{background:var(--h-hover)}
.h-jump-btn:focus-visible,.h-link:focus-visible,.h-search-in:focus-visible{outline:2px solid var(--h-accent);outline-offset:1px}
.h-link{color:var(--h-accent);text-decoration:underline;text-underline-offset:2px;overflow-wrap:anywhere;word-break:break-all}
.h-link:hover{text-decoration-thickness:2px}
button.h-link{background:none;border:0;padding:0;font:inherit;cursor:pointer;text-align:left}
.h-code{font-family:var(--h-mono);font-size:.92em;padding:1px 5px;border-radius:5px;background:var(--h-raise);border:1px solid var(--h-line)}
.h-fence{margin:4px 0;padding:8px 10px;max-width:100%;overflow-x:auto;border-radius:8px;background:var(--h-raise);border:1px solid var(--h-line);font-family:var(--h-mono);font-size:12.5px;line-height:1.45;white-space:pre-wrap;overflow-wrap:anywhere}
.h-fence code{font-family:inherit}
.h-search{flex:none;max-height:min(46vh,420px);overflow-y:auto;overscroll-behavior:contain;padding:8px 18px 10px;border-bottom:1px solid var(--h-line);background:var(--h-bg)}
.h-search-in{width:100%;box-sizing:border-box;height:34px;padding:0 12px;border:1px solid var(--h-line2);border-radius:9px;background:var(--h-card);color:var(--h-fg);font:inherit}
.h-search-in:focus{border-color:color-mix(in oklch,var(--h-accent) 60%,var(--h-line2))}
.h-search-status{min-height:18px;padding:5px 2px 3px}
.h-sr{padding:6px 10px;border-radius:8px;cursor:pointer;border-left:2px solid transparent}
.h-sr:hover{background:var(--h-hover)}
.h-sr[data-active=true]{background:color-mix(in oklch,var(--h-accent) 14%,transparent);border-left-color:var(--h-accent)}
.h-search-ctx .h-sr{cursor:default}.h-search-ctx .h-sr:hover{background:transparent}
.h-sr[data-current=true]{background:color-mix(in oklch,var(--h-warn) 14%,transparent);border-left-color:var(--h-warn)}
.h-sr-meta{display:flex;align-items:baseline;gap:6px;min-width:0}.h-sr-meta b{font-weight:600}
.h-sr-t{white-space:pre-wrap;overflow-wrap:anywhere;color:var(--h-fg2);font-size:13px;margin-top:1px}
.h-mark{background:color-mix(in oklch,var(--h-warn) 38%,transparent);color:var(--h-fg);border-radius:3px;padding:0 1px}
.h-compose-box{flex-wrap:wrap}
.h-replying{flex:0 0 100%;display:flex;align-items:center;gap:6px;min-width:0;margin:-2px 0 2px -6px;padding:2px 4px 4px 6px;border-bottom:1px solid var(--h-line);color:var(--h-fg3);font-size:12px}
.h-replying .h-trunc{flex:1;min-width:0}
.h-replying b{color:var(--h-fg2);font-weight:600}
.h-navrow .h-mentions{flex:none;min-width:18px;height:16px;padding:0 5px;border-radius:999px;display:grid;place-items:center;font-size:10.5px;font-weight:700;line-height:1;color:var(--h-bg);background:var(--h-warn)}
.h-ac{position:absolute;left:0;right:0;bottom:calc(100% + 6px);z-index:30;max-height:240px;overflow:auto;padding:4px;border:1px solid var(--h-line2);border-radius:10px;background:var(--h-card);box-shadow:var(--h-shadow)}
.h-ac-opt{display:flex;align-items:center;gap:8px;min-width:0;padding:5px 8px;border-radius:7px;cursor:pointer}
.h-ac-opt[aria-selected=true]{background:color-mix(in oklch,var(--h-accent) 18%,transparent)}
.h-menuwrap{position:relative;display:inline-flex}
.h-menu-down{top:calc(100% + 6px);bottom:auto;left:auto;right:0;min-width:270px}
.h-menu-h{padding:6px 9px 2px}.h-menu-sep{height:1px;margin:4px 2px;background:var(--h-line)}
.h-menu-tick{display:inline-grid;place-items:center;width:14px;flex:none;margin-top:2px}
.h-menu>button[aria-checked=true] b{color:var(--h-accent)}.h-menu>button:focus-visible{outline:2px solid var(--h-accent);outline-offset:-2px}
.h-qs-scrim{position:absolute;inset:0;z-index:50;display:flex;justify-content:center;align-items:flex-start;padding:12vh 12px 0;background:color-mix(in srgb,var(--h-bg) 60%,transparent)}
.h-qs{width:min(520px,100%);max-height:min(60vh,440px);display:flex;flex-direction:column;border:1px solid var(--h-line2);border-radius:12px;background:var(--h-card);box-shadow:0 18px 48px -16px var(--h-shadow);overflow:hidden}
.h-qs-in{border:0;border-bottom:1px solid var(--h-line);outline:0;background:transparent;color:var(--h-fg);font:inherit;padding:12px 14px}
.h-qs-in::placeholder{color:var(--h-fg3)}
.h-qs-list{overflow-y:auto;overscroll-behavior:contain;padding:4px}.h-qs-none{padding:14px}
.h-qs-opt{display:flex;align-items:center;gap:9px;min-width:0;padding:7px 10px;border-radius:8px;cursor:pointer}
.h-qs-opt[aria-selected=true]{background:color-mix(in oklch,var(--h-accent) 18%,transparent)}
.h-empty-s{padding:14px 10px;gap:6px;flex:none}.h-empty-art{display:block;width:240px;max-width:72%;height:auto;border-radius:12px;margin-bottom:4px;user-select:none}
@media (pointer:coarse){.h-bar-btn{width:38px;height:36px}.h-bar{top:-20px}}
.h-ac-opt .h-initial{width:22px;height:22px;font-size:11px}
.h-ac-opt b{font-weight:600}
.h-ac-sub{color:var(--h-fg3);font-size:12px}

.h-card{border:1px solid var(--h-line2);border-radius:12px;padding:12px 14px;background:var(--h-card);margin:6px 0 6px 42px;display:flex;flex-direction:column;gap:8px}
.h-card.h-agent{border-color:color-mix(in oklch,var(--tint) 35%,var(--h-line2))}
.h-card h4{margin:0;font-size:13.5px;font-weight:600}
.h-card .h-kicker{font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--h-fg3);font-weight:600}
.h-chatcard{border:1px solid var(--h-line2);border-radius:12px;padding:12px 14px;background:var(--h-card);margin:8px 0;display:flex;flex-direction:column;gap:8px;max-width:560px}
.h-chatcard.h-agent{border-color:color-mix(in oklch,var(--tint) 35%,var(--h-line2))}
.h-chatcard h4{margin:0;font-size:13.5px;font-weight:600}
.h-chatcard .h-kicker{font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--h-fg3);font-weight:600}
.h-chatcard-wrap{margin:8px 0;max-width:560px}
.h-chatcard-wrap .h-tales{margin-bottom:0}
.h-cardchip{margin:4px 0}
.h-actions{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.h-frame{width:100%;height:340px;border:1px solid var(--h-line);border-radius:8px;background:var(--h-bg);display:block}
.h-frame[data-tall=true]{height:620px}
.h-frame iframe{width:100%;height:100%;border:0;border-radius:8px;display:block}
.h-frame[data-starting=true] iframe{visibility:hidden}
.h-frame{position:relative}
.h-frame-note{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:16px;text-align:center}

.h-composer{padding:10px 18px 14px;max-width:860px;width:100%;margin:0 auto;flex:none}
.h-pinned{max-height:min(44vh,520px);overflow-y:auto;overscroll-behavior:contain}
.h-page>.h-scroll{height:100%}
.h-compose-box{display:flex;align-items:flex-end;gap:6px;border:1px solid var(--h-line2);border-radius:12px;padding:6px 6px 6px 12px;background:var(--h-card)}
.h-compose-box:focus-within{border-color:color-mix(in oklch,var(--h-accent) 60%,var(--h-line2))}
.h-compose-box textarea{flex:1;border:0;outline:0;resize:none;background:transparent;color:var(--h-fg);font:inherit;padding:5px 0;max-height:160px;min-height:22px;line-height:1.45}
.h-compose-box textarea::placeholder{color:var(--h-fg3)}
.h-menu{position:absolute;bottom:calc(100% + 6px);left:0;min-width:220px;border:1px solid var(--h-line2);border-radius:10px;background:var(--h-card);box-shadow:0 12px 32px -12px var(--h-shadow);padding:4px;z-index:10}
.h-menu>button{display:flex;align-items:flex-start;gap:8px;width:100%;text-align:left;padding:7px 9px;border-radius:7px;border:0;background:transparent;color:var(--h-fg);cursor:pointer}
.h-menu>button:hover{background:var(--h-hover)}
.h-gm-menu{min-width:320px}
.h-gm{display:flex;align-items:flex-start;gap:8px;padding:7px 9px;border-radius:7px}
.h-gm .h-grow{display:flex;flex-direction:column;gap:1px;min-width:0}
.h-gm .h-gm-line{display:block}
.h-gm button{flex:none;width:auto}
.h-howto{border:1px solid var(--h-line2);border-radius:10px;padding:10px 12px;background:var(--h-raise);display:flex;flex-direction:column;gap:6px}
.h-howto-compact summary{cursor:pointer}
.h-howto-compact[open] summary{margin-bottom:6px}
.h-howto-list{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;margin:0;font-size:13px;line-height:1.4}
.h-howto-list dt{font-weight:600;color:var(--h-fg2)}
.h-howto-list dd{margin:0;color:var(--h-fg)}
.h-agents-in{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12px}
.h-agents-in li{display:flex;gap:6px;min-width:0}
.h-agents-in li[data-status=gave_up] .h-faint{color:var(--h-warn)}
.h-tray{display:flex;flex-direction:column;gap:6px;margin-bottom:8px}
.h-draft{border:1px dashed var(--h-line2);border-radius:10px;padding:8px 10px;display:flex;gap:10px;align-items:flex-start}

/* the private line */
.h-private{display:inline-flex;align-items:center;gap:4px;padding:1px 7px;border-radius:999px;font-size:10.5px;color:var(--h-fg2);background:var(--h-raise)}
.h-hmark{display:inline-grid;place-items:center;flex:none;border-radius:30%;font-weight:700;letter-spacing:-.02em;color:var(--h-bg);background:color-mix(in oklch,var(--h-fg) 78%,var(--h-bg))}
.h-lmsg[data-role=hermes] .h-bubble{background:var(--h-raise);border:1px solid var(--h-line);border-radius:4px 12px 12px 12px;padding:7px 11px;display:inline-block;max-width:100%}
.h-lactions{margin-top:2px;opacity:.72}
.h-lmsg:hover .h-lactions,.h-lactions:focus-within{opacity:1}
.h-lmsg [data-status=failed]{color:var(--h-bad)}
.h-typing{display:inline-flex;gap:4px;align-items:center;padding:9px 12px;border-radius:4px 12px 12px 12px;background:var(--h-raise);border:1px solid var(--h-line);width:max-content}
.h-typing i{width:5px;height:5px;border-radius:50%;background:var(--h-fg3);display:block}
.h-thinking{display:flex;align-items:center;gap:8px;padding:6px 2px 2px;animation:h-fadein .3s ease-out}
@media (prefers-reduced-motion: reduce){.h-thinking{animation:none}.hx .h-spin{animation:none!important}}
.h-thinking .h-typing{padding:6px 9px}
@keyframes h-fadein{from{opacity:0;transform:translateY(4px)}}
.h-compose-box[data-private=true]{align-items:center}
.h-compose-box[data-private=true]>svg,.h-compose-box[data-private=true]>.codicon{color:var(--h-fg3);flex:none}

/* right rail: people with their agents nested */
.h-person{display:flex;flex-direction:column;gap:2px;padding:6px 4px;border-radius:8px}
.h-person-row{display:flex;align-items:center;gap:8px;min-width:0}
.h-person-row .h-hide{margin-left:auto;opacity:0;transition:opacity .12s}
.h-person:hover .h-hide,.h-hide:focus-within{opacity:1}
@media (hover:none){.h-person-row .h-hide{opacity:1}}
.h-presence{width:7px;height:7px;border-radius:50%;flex:none;background:var(--h-fg4)}
.h-presence[data-on=true]{background:var(--h-good)}
.h-presence[data-s=idle]{background:var(--h-warn)}
.h-presence[data-s=dnd]{background:var(--h-bad)}
.h-statusbtn{display:flex;align-items:center;gap:6px;max-width:100%;min-width:0;padding:1px 4px;margin:0 -4px;border:0;border-radius:6px;background:transparent;color:inherit;font:inherit;cursor:pointer;text-align:left}
.h-statusbtn:hover{background:var(--h-hover)}.h-statusbtn:focus-visible{outline:2px solid var(--h-accent);outline-offset:1px}
.h-mystatus{display:block;min-width:0}
/* A popover: fixed, placed by usePopover next to its button, never narrower than 280px (the sidebar is) */
.h-pop{position:fixed;top:0;left:0;bottom:auto;right:auto;z-index:60;width:300px;min-width:280px;max-width:none;overflow:auto;box-shadow:var(--h-shadow)}
.h-pop .h-gm-line{display:block;white-space:normal}
.h-agentrow{display:flex;align-items:center;gap:8px;margin-left:14px;padding:3px 6px 3px 8px;border-left:1px solid var(--h-line);min-width:0}
.h-statepill{font-size:10.5px;color:var(--h-fg3)}
.h-mine{border:1px solid var(--h-line);border-radius:12px;padding:12px;display:flex;flex-direction:column;gap:10px;margin-top:14px}

/* Tall Tales */
.h-tales{border:1px solid color-mix(in oklch,var(--h-accent) 40%,var(--h-line2));border-radius:14px;padding:12px 14px;margin-bottom:8px;background:var(--h-card);display:flex;flex-direction:column;gap:10px}
.h-tales-bar{flex-direction:row;align-items:center;gap:8px;padding:6px 10px}
.h-tales-q{font-size:14.5px;font-weight:600;line-height:1.35}
.h-opts{display:grid;gap:6px}
.h-opt{display:flex;align-items:center;gap:10px;width:100%;text-align:left;padding:8px 11px;border-radius:9px;border:1px solid var(--h-line2);background:transparent;color:var(--h-fg);cursor:pointer;font:inherit}
.h-opt:hover:not(:disabled){background:var(--h-hover)}
.h-opt:disabled{cursor:default;opacity:.55}
.h-opt[data-picked=true]{border-color:var(--h-accent);background:color-mix(in oklch,var(--h-accent) 12%,transparent)}
.h-opt[data-truth=true]{border-color:color-mix(in oklch,var(--h-good) 70%,transparent);background:color-mix(in oklch,var(--h-good) 12%,transparent)}
.h-opt .h-letter{width:20px;height:20px;border-radius:50%;display:grid;place-items:center;font-size:11px;font-weight:600;background:var(--h-raise);flex:none}
.h-score{display:flex;flex-wrap:wrap;gap:6px}
.h-team{display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:999px;background:var(--h-raise);font-size:12px}
.h-team b{font-variant-numeric:tabular-nums}
.h-team[data-you=true]{outline:1px solid color-mix(in oklch,var(--h-accent) 60%,transparent)}

/* rings */
.h-ring{position:relative;display:inline-grid;place-items:center;flex:none}
.h-ring svg{position:absolute;inset:0}
.h-ring-track{fill:none;stroke:var(--h-line2)}
.h-ring-arc{fill:none;stroke:var(--h-accent);stroke-linecap:round}
.h-ring[data-tone=warn] .h-ring-arc{stroke:var(--h-warn)}
.h-ring[data-tone=rest] .h-ring-arc{stroke:var(--h-fg3)}
.h-ring-label{position:relative;font-size:10px;font-variant-numeric:tabular-nums;color:var(--h-fg2)}

/* lobby, onboarding, settings */
.h-pane{padding:20px 22px 40px;max-width:820px;width:100%;margin:0 auto;display:flex;flex-direction:column;gap:22px}
.h-pane h1{font-size:20px;margin:0;font-weight:600;letter-spacing:-.005em}
.h-pane h3{font-size:13px;margin:0;font-weight:600}
.h-list{display:flex;flex-direction:column;gap:8px}
.h-item{border:1px solid var(--h-line);border-radius:12px;padding:11px 13px;display:flex;gap:12px;align-items:flex-start}
.h-cardpreview{border:1px solid var(--h-line2);border-radius:14px;padding:14px;display:flex;gap:14px;align-items:flex-start;background:var(--h-card)}
.h-pre{font-family:var(--h-mono);font-size:11px;white-space:pre-wrap;overflow-wrap:anywhere;background:var(--h-raise);padding:10px;border-radius:8px;margin:0;color:var(--h-fg2);max-height:240px;overflow:auto}
.h-field{display:flex;flex-direction:column;gap:5px}
.h-field label,.h-field .h-label{font-size:12px;font-weight:600;color:var(--h-fg2)}
.h-field .h-hint{font-size:11.5px;color:var(--h-fg3)}
.h-field .h-err{color:var(--h-bad)}
.h-vh{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
.h-two{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@container (max-width: 560px){.h-two{grid-template-columns:1fr}}
.h-shapes{display:flex;flex-wrap:wrap;gap:6px}
.h-shape{border:1px solid var(--h-line);border-radius:12px;padding:6px;background:transparent;cursor:pointer;display:grid;place-items:center}
.h-shape[data-on=true]{border-color:var(--h-accent);background:color-mix(in oklch,var(--h-accent) 10%,transparent)}
.h-hue{width:100%;accent-color:var(--h-accent);height:18px}
.h-seg{display:inline-flex;border:1px solid var(--h-line2);border-radius:9px;padding:2px;gap:2px}
.h-seg button{border:0;background:transparent;color:var(--h-fg2);padding:4px 10px;border-radius:7px;cursor:pointer;font-size:12px}
.h-seg button[data-on=true]{background:var(--h-raise);color:var(--h-fg)}
.h-ta{width:100%;border:1px solid var(--h-line2);border-radius:8px;background:transparent;color:var(--h-fg);font:inherit;padding:8px 10px;resize:vertical;outline:0}
.h-ta:focus{border-color:color-mix(in oklch,var(--h-accent) 60%,var(--h-line2))}
.h-hermes-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:6px}
.h-hermes-item{display:flex;flex-direction:column;align-items:flex-start;gap:2px;min-width:0;text-align:left;font:inherit;padding:8px 10px;border-radius:10px;border:1px solid var(--h-line2);background:transparent;color:var(--h-fg);cursor:pointer;transition:transform .45s cubic-bezier(.34,1.45,.5,1),background .15s linear,border-color .15s linear}
.h-hermes-item:hover:not(:disabled){background:var(--h-hover);transform:translateY(-1px)}
.h-hermes-item:active:not(:disabled){transform:scale(.97)}
.h-hermes-item:focus-visible{outline:2px solid var(--h-accent);outline-offset:1px}
.h-hermes-item[data-busy=true]{opacity:.6}
.h-hermes-item[data-here=true]{border-color:color-mix(in oklch,var(--h-accent) 45%,var(--h-line2))}
.h-hermes-top{display:flex;align-items:center;gap:6px;max-width:100%;font-size:12.5px}
.h-hermes-top b{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.h-hermes-here{flex:none}
.h-hermes-sub{font-size:11.5px;color:var(--h-fg3);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
.h-persona{animation:h-persona-in .5s cubic-bezier(.34,1.45,.5,1) both;transform-origin:top left}
.h-persona .h-ta{min-height:9em}
.h-persona-warn{color:var(--h-fg2)}
.h-persona-flags{margin:0;padding:8px 10px 8px 26px;border-radius:8px;background:var(--h-raise);color:var(--h-fg2);font-size:12px;display:flex;flex-direction:column;gap:2px;overflow-wrap:anywhere}
.h-persona-foot{display:flex;flex-wrap:wrap;align-items:center;gap:4px 12px}
.h-persona-foot [data-over=true]{color:var(--h-fg)}
.h-persona-peek{font-size:12px;color:var(--h-fg2);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;white-space:pre-line;overflow-wrap:anywhere}
@keyframes h-persona-in{from{opacity:0;transform:translateY(-6px) scale(.985)}}
@media (prefers-reduced-motion: reduce){.h-persona{animation:none}.h-hermes-item{transition:none}}
.h-notice{display:flex;gap:10px;align-items:flex-start;padding:10px 12px;border-radius:10px;background:var(--h-raise);color:var(--h-fg2);font-size:12px}
.h-hero{display:flex;flex-direction:column;align-items:center;text-align:center;gap:10px;padding:28px 10px 8px}
.h-savebar{justify-content:flex-end;position:sticky;bottom:0;padding:10px 0;background:var(--h-bg);border-top:1px solid var(--h-line)}
.h-relay{display:flex;align-items:center;gap:8px;font-size:12px;padding:3px 0}
.h-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:48px 20px;text-align:center;color:var(--h-fg2);flex:1}

/* status bar chip (Desktop) */
.h-statuschip{display:inline-flex;align-items:center;gap:5px;height:100%;padding:0 6px;border:0;background:transparent;color:var(--h-fg3);font-size:11px;cursor:pointer}
.h-statuschip:hover{color:var(--h-fg);background:var(--h-hover)}

/* faces: pixel art (ui/12_pixel.js). Animation swaps or steps whole layers by whole cells (1px in the 64-cell
   viewBox is one cell); the state picks the frames. Frames that wait their turn (a blink, a talking mouth) are hidden by
   default, so with no animation (reduced motion, a still face) the face simply rests. */
.hf{display:inline-grid;place-items:center;flex:none;transform-origin:50% 60%}
.hf svg{overflow:visible;filter:drop-shadow(0 0 .7px rgba(3,8,16,.8)) drop-shadow(0 0 .7px rgba(3,8,16,.5)) drop-shadow(0 0 var(--gs,1px) var(--glow,transparent)) drop-shadow(0 0 calc(var(--gs,1px) * 3) var(--glow2,transparent))}
.hf[data-size=s] svg{filter:drop-shadow(0 0 .5px rgba(3,8,16,.5))}
.pf-scan{opacity:.2}
.hf[data-size=s] .pf-scan,.hf[data-size=m] .pf-scan{display:none}
.pf-ec,.pf-mt{opacity:0}
.hf-clock circle{fill:var(--h-card);stroke:var(--h-fg2);stroke-width:2.2}
.hf-clock path{stroke:var(--h-fg2);stroke-width:2.2;stroke-linecap:round}
.hf-hand{transform-origin:54px 10px}
.hf[data-state=idle] .pf-eo,.hf[data-state=working] .pf-eo{animation:pf-blink-o 4.7s step-end infinite}
.hf[data-state=idle] .pf-ec,.hf[data-state=working] .pf-ec{animation:pf-blink-c 4.7s step-end infinite}
.hf[data-state=working] .hf-eyes{animation:pf-scan 1.6s step-end infinite}
.hf[data-state=speaking] .pf-mr{animation:pf-talk-r .36s step-end infinite}
.hf[data-state=speaking] .pf-mt{animation:pf-talk-t .36s step-end infinite}
.hf[data-state=waiting] .hf-hand{animation:hf-tick 6s steps(12) infinite}
.hf[data-state=error] .hf-head{transform:translateY(2px)}
.hf[data-state=absent] .hf-head{opacity:.45;filter:saturate(.25)}
/* idle life: a one-cell breath and an occasional glance, offset per face by the same delay as the blink */
.hf[data-state=idle]:not([data-expr]) .hf-head{animation:pf-bob 4.2s step-end infinite}
.hf[data-state=idle]:not([data-expr]) .hf-eyes{animation:pf-glance 9.4s step-end infinite}
/* reactions (data-expr): the frames come from the component; the head moves in whole cells */
.hf[data-expr=caught] .hf-head{animation:pf-shake .5s step-end 1}
.hf[data-expr=happy] .hf-head{animation:pf-hop .62s step-end 2}
.hf[data-expr=perk] .hf-head{animation:pf-hop .5s step-end 1}
.hf[data-expr=smug] .hf-head{transform:translateX(1px)}
@keyframes pf-blink-o{0%{opacity:1}94%{opacity:0}97%{opacity:1}}
@keyframes pf-blink-c{0%{opacity:0}94%{opacity:1}97%{opacity:0}}
@keyframes pf-talk-r{0%{opacity:1}50%{opacity:0}}
@keyframes pf-talk-t{0%{opacity:0}50%{opacity:1}}
@keyframes pf-bob{0%{transform:none}50%{transform:translateY(1px)}}
@keyframes pf-glance{0%{transform:none}80%{transform:translateX(2px)}91%{transform:translateX(-1px)}94%{transform:none}}
@keyframes pf-scan{0%{transform:translateX(-2px)}25%{transform:translateX(0)}50%{transform:translateX(2px)}75%{transform:translateX(0)}}
@keyframes pf-shake{0%{transform:translateX(-2px)}20%{transform:translateX(2px)}40%{transform:translateX(-1px)}60%{transform:translateX(1px)}80%{transform:none}}
@keyframes pf-hop{0%{transform:translateY(-2px)}30%{transform:translateY(-4px)}55%{transform:translateY(-1px)}75%{transform:none}}
@keyframes hf-tick{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion: reduce){.hf *{animation:none!important;transition:none!important}}
.hf-still *{animation:none!important}
.h-facepick{align-items:flex-start;gap:16px}
.h-facepart{display:flex;flex-direction:column;gap:5px}
.h-facepart .h-shape{padding:4px;border-radius:10px}
.h-caps{text-transform:uppercase;letter-spacing:.08em;font-weight:600}
.hx .h-plain{background:none;border:0;padding:0;margin:0;color:inherit;cursor:pointer;text-align:inherit;border-radius:8px;display:inline-flex;align-items:center;min-width:0}
.hx .h-plain:focus-visible{outline:2px solid var(--h-accent);outline-offset:2px}
.hx .h-plain.h-trunc{display:block}
.hx .h-plain:hover .h-namelink,.hx .h-plain:hover>b{text-decoration:underline;text-decoration-color:var(--h-fg3);text-underline-offset:3px}
.h-idcard-stage{--tx:0;--ty:0;--glow:0;position:relative;border-radius:22px;perspective:1000px;-webkit-tap-highlight-color:transparent}
.h-idcard-stage[data-interactive=true]{cursor:pointer;-webkit-user-select:none;user-select:none}
.h-idcard-stage:focus-visible{outline:2px solid var(--h-accent);outline-offset:3px}
.h-idcard-tilt{transform:rotateX(calc(var(--ty) * -7deg)) rotateY(calc(var(--tx) * 7deg));transform-style:preserve-3d}
.h-idcard-turn{position:relative;transform-style:preserve-3d}
.h-idcard{--c1:oklch(0.6 0.19 var(--hue));--c2:oklch(0.4 0.2 var(--hue));--c3:oklch(0.2 0.12 var(--hue));position:relative;width:100%;aspect-ratio:1.6;border-radius:22px;overflow:hidden;color:#fff;isolation:isolate;container-type:inline-size;
  -webkit-backface-visibility:hidden;backface-visibility:hidden;
  background:radial-gradient(115% 105% at 74% 40%,var(--c1) 0%,var(--c2) 46%,var(--c3) 100%);
  box-shadow:0 22px 48px -22px oklch(0.3 0.2 var(--hue) / .8),inset 0 0 0 1px oklch(1 0 0 / .08)}
.h-idcard-dots{position:absolute;inset:0;z-index:0;background-image:radial-gradient(circle,oklch(1 0 0 / .34) 0.85px,transparent 1.25px);background-size:5px 5px;
  -webkit-mask-image:radial-gradient(56% 74% at 72% 52%,#000 0%,transparent 72%);mask-image:radial-gradient(56% 74% at 72% 52%,#000 0%,transparent 72%)}
.h-idcard-frame{--spin:calc(210deg + var(--tx) * 34deg - var(--ty) * 18deg);position:absolute;inset:9px;z-index:3;border-radius:15px;padding:1.5px;pointer-events:none;opacity:calc(.9 + var(--glow) * .1);
  background:conic-gradient(from var(--spin),oklch(0.96 0.07 200),oklch(0.93 0.1 320),oklch(0.98 0.05 95),oklch(0.92 0.11 160),oklch(0.96 0.07 200));
  -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude}
.h-idcard-shine{position:absolute;inset:0;z-index:5;pointer-events:none;opacity:var(--glow);mix-blend-mode:overlay;
  background:radial-gradient(60% 95% at calc(50% + var(--tx) * 55%) calc(50% + var(--ty) * 60%),oklch(1 0 0 / .62) 0%,oklch(1 0 0 / .2) 38%,transparent 72%)}
.h-idcard-back .h-idcard-shine{background:radial-gradient(60% 95% at calc(50% - var(--tx) * 55%) calc(50% + var(--ty) * 60%),oklch(1 0 0 / .4) 0%,oklch(1 0 0 / .12) 38%,transparent 72%)}
.h-idcard-hero{position:absolute;z-index:1;right:7%;top:46%;transform:translateY(-50%);width:35%;aspect-ratio:1;display:grid;place-items:center;filter:drop-shadow(0 0 20px oklch(0.85 0.14 var(--hue) / .55))}
.h-idcard-hero .hf{width:100%!important;height:100%!important}
.h-idcard-hero .hf svg{width:100%;height:100%}
.h-idcard-crew{position:relative;width:100%;height:100%}
.h-idcard-mate{position:absolute;aspect-ratio:1;filter:brightness(.86) saturate(.85)}
.h-idcard-mate[data-front=true]{filter:drop-shadow(0 4px 10px oklch(0.2 0.14 var(--hue) / .55))}
.h-idcard-initial{font-size:clamp(60px,30cqw,120px);font-weight:200;line-height:1;color:oklch(0.95 0.04 var(--hue));text-shadow:0 0 28px oklch(0.85 0.14 var(--hue) / .7)}
.h-idcard-top{position:absolute;z-index:4;left:8%;top:13%;right:46%;display:flex;flex-direction:column;align-items:flex-start;gap:9px}
.h-idcard-name{font-weight:300;font-size:clamp(16px,6.6cqw,26px);line-height:1.08;letter-spacing:.12em;text-transform:uppercase;font-stretch:condensed;overflow-wrap:anywhere;text-shadow:0 1px 14px oklch(0.2 0.12 var(--hue) / .55);
  display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;line-clamp:2;overflow:hidden;max-width:100%}
.h-idcard-name[data-size=m]{font-size:clamp(14px,5.3cqw,21px);letter-spacing:.1em}
.h-idcard-name[data-size=s]{font-size:clamp(12px,4.3cqw,17px);letter-spacing:.08em;line-height:1.12}
.h-idcard-tag{font-size:clamp(8.5px,2.7cqw,10.5px);font-weight:500;letter-spacing:.16em;text-transform:uppercase;padding:2px 7px 1px;color:oklch(0.32 0.17 var(--hue));background:oklch(0.98 0.02 var(--hue));box-shadow:inset 0 0 0 1.5px oklch(0.4 0.17 var(--hue)),0 0 0 1.5px oklch(0.98 0.02 var(--hue))}
.h-idcard-serial{position:absolute;z-index:4;top:7%;right:8.5%;font-family:var(--h-mono,ui-monospace),ui-monospace,monospace;font-size:clamp(7.5px,2.35cqw,9.5px);line-height:1;letter-spacing:.16em;opacity:.72;text-shadow:0 1px 6px oklch(0.2 0.12 var(--hue) / .6)}
.h-idcard-foot{position:absolute;z-index:4;left:8%;right:8%;bottom:12%;display:flex;justify-content:space-between;align-items:flex-end;gap:14px}
.h-idcard-field{display:flex;flex-direction:column;gap:3px;min-width:0;max-width:60%}
.h-idcard-field+.h-idcard-field{text-align:right;align-items:flex-end;max-width:45%}
.h-idcard-label{font-size:clamp(8px,2.5cqw,10px);letter-spacing:.2em;text-transform:uppercase;opacity:.74}
.h-idcard-value{font-size:clamp(11px,4.4cqw,17px);letter-spacing:.06em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%;text-shadow:0 1px 10px oklch(0.2 0.12 var(--hue) / .5)}
.h-idcard-value[data-warn=true]{color:oklch(0.9 0.12 70)}
.h-idcard[data-warn=true]{box-shadow:0 22px 48px -22px oklch(0.35 0.2 30 / .85),inset 0 0 0 1px oklch(0.8 0.16 50 / .35)}
.h-idcard[data-warn=true]::after{content:'';position:absolute;inset:0;z-index:2;pointer-events:none;background:radial-gradient(120% 130% at 50% 50%,transparent 46%,oklch(0.55 0.21 32 / .62) 100%)}
.h-idcard[data-warn=true] .h-idcard-frame{padding:2.5px;opacity:1;background:conic-gradient(from var(--spin),oklch(0.8 0.17 45),oklch(0.68 0.21 28),oklch(0.88 0.15 78),oklch(0.72 0.2 35),oklch(0.8 0.17 45))}
.h-idcard[data-warn=true] .h-idcard-tag{color:oklch(0.3 0.13 35);background:oklch(0.9 0.13 75);box-shadow:inset 0 0 0 1.5px oklch(0.5 0.18 35),0 0 0 1.5px oklch(0.9 0.13 75)}
.h-idcard-back{position:absolute;inset:0;transform:rotateY(180deg);
  background:radial-gradient(120% 110% at 28% 40%,oklch(0.34 0.16 var(--hue)) 0%,var(--c3) 60%,oklch(0.14 0.07 var(--hue)) 100%)}
.h-idcard-back .h-idcard-dots{opacity:.42;-webkit-mask-image:radial-gradient(70% 80% at 30% 45%,#000 0%,transparent 75%);mask-image:radial-gradient(70% 80% at 30% 45%,#000 0%,transparent 75%)}
.h-idcard-back .h-idcard-frame{opacity:.5}
.h-idcard-stripe{position:absolute;z-index:4;left:0;right:0;top:10%;height:13%;background:linear-gradient(180deg,oklch(0.12 0.03 var(--hue)),oklch(0.17 0.05 var(--hue)));box-shadow:0 1px 0 oklch(1 0 0 / .06)}
.h-idcard-keyblock{position:absolute;z-index:4;left:8%;right:8%;top:31%;display:flex;flex-direction:column;gap:5px}
.h-idcard-key{display:grid;grid-template-columns:repeat(2,max-content);gap:3px 1.4em;font-family:var(--h-mono,ui-monospace),ui-monospace,monospace;font-size:clamp(8px,2.85cqw,11px);line-height:1.35;letter-spacing:.1em;opacity:.92}
.h-idcard-about{position:absolute;z-index:4;left:8%;right:8%;top:55%;font-size:clamp(10px,3.3cqw,13px);line-height:1.35;opacity:.86;
  display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;line-clamp:2;overflow:hidden;overflow-wrap:anywhere}
.h-idcard-back .h-idcard-foot{gap:16px}
.h-idcard-back .h-idcard-field,.h-idcard-back .h-idcard-field+.h-idcard-field{flex:0 0 auto;max-width:none;text-align:left;align-items:flex-start}
.h-idcard-back .h-idcard-field:last-child:not(:first-child){flex:0 1 auto;text-align:right;align-items:flex-end}
.h-idcard-back .h-idcard-label{white-space:nowrap;letter-spacing:.16em}
.h-idcard-back .h-idcard-value{font-size:clamp(10px,3.6cqw,14px)}
.h-idcard-num{font-family:var(--h-mono,ui-monospace),ui-monospace,monospace;letter-spacing:.06em;color:var(--h-fg)}
.h-idcard-sr{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
.h-idcard[data-card=scanner]{--scan-ui:oklch(0.86 0.12 205);--scan-ink:oklch(0.97 0.04 205);--scan-glow:oklch(0.78 0.15 215);color:var(--scan-ink);
  background:oklch(0.1 0.035 262);box-shadow:0 22px 48px -22px oklch(0.12 0.04 250 / .9)}
.h-idcard[data-card=scanner][data-warn=true]{--scan-ui:oklch(0.7 0.21 27);--scan-glow:oklch(0.62 0.24 27);box-shadow:0 22px 48px -22px oklch(0.3 0.17 28 / .9)}
.h-idcard[data-card=scanner][data-warn=true]::after{display:none}
.h-idcard[data-card=scanner][data-led=green]{--led:oklch(0.86 0.21 145)}
.h-idcard[data-card=scanner][data-led=amber]{--led:oklch(0.83 0.16 75)}
.h-idcard[data-card=scanner][data-led=red]{--led:oklch(0.66 0.24 27)}
.h-scan-screen{position:absolute;inset:0;border-radius:inherit;overflow:hidden;isolation:isolate;background:oklch(0.1 0.035 262)}
.h-scan-nebula{position:absolute;inset:0;z-index:0}
.h-scan-nebula canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
.h-scan-px{image-rendering:crisp-edges;image-rendering:pixelated}
.h-scan-bloom{filter:blur(2.6cqw) saturate(1.25) brightness(1.4);mix-blend-mode:screen;opacity:1;transform:scale(1.05)}
.h-scan-cells{position:absolute;inset:0;z-index:1;mix-blend-mode:multiply;opacity:.5;
  background-image:linear-gradient(90deg,oklch(0.55 0 0) 1px,transparent 1px),linear-gradient(oklch(0.55 0 0) 1px,transparent 1px);background-size:calc(100% / 48) 100%,100% calc(100% / 30)}
.h-scan-band{position:absolute;left:0;right:0;height:10%;z-index:2;background-size:1.55cqw 1.55cqw;
  background-image:linear-gradient(90deg,color-mix(in oklch,var(--scan-ui) 34%,transparent) 1px,transparent 1px),linear-gradient(color-mix(in oklch,var(--scan-ui) 34%,transparent) 1px,transparent 1px)}
.h-scan-band[data-at=top]{top:0;border-bottom:1px solid color-mix(in oklch,var(--scan-ui) 70%,transparent)}
.h-scan-band[data-at=bottom]{bottom:0;border-top:1px solid color-mix(in oklch,var(--scan-ui) 70%,transparent);background-position:0 100%}
.h-scan-scrim{position:absolute;inset:0;z-index:3;pointer-events:none;
  background:linear-gradient(to top,oklch(0.08 0.04 255 / .72) 0,oklch(0.08 0.04 255 / .5) 18%,transparent 36%),radial-gradient(ellipse 40% 26% at 30% 32%,oklch(0.08 0.04 255 / .5),transparent)}
.h-scan-box{position:absolute;z-index:3;right:7.5%;top:17%;width:30%;aspect-ratio:1;box-shadow:inset 0 0 0 1px color-mix(in oklch,var(--scan-ui) 38%,transparent);
  background:radial-gradient(closest-side,oklch(0.1 0.04 255 / .55),transparent)}
.h-scan-box::before{content:'';position:absolute;inset:0;--a:12%;--w:2px;background-repeat:no-repeat;filter:drop-shadow(0 0 3px var(--scan-glow));
  background-image:linear-gradient(var(--scan-ui),var(--scan-ui)),linear-gradient(var(--scan-ui),var(--scan-ui)),linear-gradient(var(--scan-ui),var(--scan-ui)),linear-gradient(var(--scan-ui),var(--scan-ui)),
    linear-gradient(var(--scan-ui),var(--scan-ui)),linear-gradient(var(--scan-ui),var(--scan-ui)),linear-gradient(var(--scan-ui),var(--scan-ui)),linear-gradient(var(--scan-ui),var(--scan-ui));
  background-position:0 0,0 0,100% 0,100% 0,0 100%,0 100%,100% 100%,100% 100%;
  background-size:var(--a) var(--w),var(--w) var(--a),var(--a) var(--w),var(--w) var(--a),var(--a) var(--w),var(--w) var(--a),var(--a) var(--w),var(--w) var(--a)}
.h-idcard[data-warn=true] .h-scan-box::before{--w:3px}
.h-scan-box .h-idcard-hero{inset:12%;right:12%;top:12%;width:auto;transform:none;filter:drop-shadow(0 0 1.3cqw color-mix(in oklch,var(--scan-glow) 75%,transparent))}
.h-idcard[data-card=scanner] .h-idcard-mate{filter:brightness(.78)}
.h-idcard[data-card=scanner] .h-idcard-mate[data-front=true]{filter:drop-shadow(0 .6cqw 1cqw oklch(0.08 0.04 255 / .7))}
.h-idcard[data-card=scanner] .h-idcard-initial{font-family:var(--h-mono,ui-monospace),ui-monospace,monospace;font-size:20cqw;font-weight:400;color:var(--scan-ink);text-shadow:0 0 1.6cqw var(--scan-glow)}
.h-scan-top{position:absolute;z-index:4;left:7.5%;top:17%;right:40%;display:flex;flex-direction:column;align-items:flex-start;gap:1.3cqw}
.h-scan-name,.h-scan-tag,.h-scan-id,.h-scan-label,.h-scan-value,.h-scan-key,.h-scan-about{font-family:var(--h-mono,ui-monospace),ui-monospace,monospace;text-transform:uppercase}
.h-scan-name{font-size:5.9cqw;font-weight:500;line-height:1.14;letter-spacing:.06em;color:var(--scan-ink);overflow-wrap:anywhere;max-width:100%;
  text-shadow:0 0 .5cqw var(--scan-glow),0 0 2.2cqw color-mix(in oklch,var(--scan-glow) 60%,transparent);display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;line-clamp:2;overflow:hidden}
.h-scan-name[data-size=m]{font-size:4.8cqw}
.h-scan-name[data-size=s]{font-size:3.6cqw}
.h-scan-tag{font-size:max(8px,2.25cqw);font-weight:500;letter-spacing:.18em;line-height:1;padding:.6cqw .9cqw .5cqw;margin-left:1px;color:var(--scan-ink);text-shadow:0 0 .6cqw var(--scan-glow);background:oklch(0.1 0.04 255 / .6);
  box-shadow:inset 0 0 0 1px var(--scan-ui),0 0 1cqw color-mix(in oklch,var(--scan-glow) 40%,transparent)}
.h-idcard[data-card=scanner][data-warn=true] .h-scan-tag{background:var(--scan-ui);color:oklch(0.16 0.05 27);text-shadow:none;box-shadow:0 0 1.6cqw var(--scan-glow)}
.h-scan-id{position:absolute;z-index:4;right:7.5%;top:5%;transform:translateY(-50%);font-size:max(7.5px,1.9cqw);line-height:1;letter-spacing:.14em;color:var(--scan-ink);padding:.55cqw .9cqw .5cqw;border-radius:.6cqw;
  background:oklch(0.09 0.04 255 / .72);text-shadow:0 0 .6cqw var(--scan-glow)}
.h-idcard[data-card=scanner][data-warn=true] .h-scan-id{color:oklch(0.95 0.05 25)}
.h-scan-foot{position:absolute;z-index:4;left:7.5%;right:7.5%;bottom:13%;display:flex;justify-content:space-between;align-items:flex-end;gap:3cqw}
.h-scan-field{display:flex;flex-direction:column;gap:.7cqw;min-width:0;max-width:52%}
.h-scan-field+.h-scan-field{text-align:right;align-items:flex-end;max-width:45%}
.h-scan-label{font-size:max(7.5px,1.85cqw);line-height:1;letter-spacing:.2em;color:var(--scan-ui);text-shadow:0 0 .5cqw oklch(0.08 0.04 255 / .95),0 0 .6cqw var(--scan-glow)}
.h-scan-value{font-size:3.3cqw;line-height:1.05;letter-spacing:.04em;color:var(--scan-ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%;
  text-shadow:0 0 .5cqw var(--scan-glow),0 0 1.8cqw color-mix(in oklch,var(--scan-glow) 55%,transparent)}
.h-scan-value[data-warn=true]{color:oklch(0.86 0.14 70);text-shadow:0 0 .8cqw oklch(0.7 0.18 50)}
.h-scan-glass{position:absolute;inset:0;z-index:5;pointer-events:none;border-radius:inherit;
  background:repeating-linear-gradient(180deg,transparent 0 2px,oklch(0 0 0 / .22) 2px 3px),radial-gradient(130% 120% at 50% 50%,transparent 55%,oklch(0.05 0.02 260 / .72) 100%),
    radial-gradient(90% 70% at 14% -12%,oklch(1 0 0 / .11),transparent 62%);
  box-shadow:inset 0 0 0 1px oklch(1 0 0 / .16),inset 0 1px 0 oklch(1 0 0 / .1),inset 0 0 3cqw oklch(0 0 0 / .6)}
.h-idcard[data-card=scanner][data-warn=true] .h-scan-glass{box-shadow:inset 0 0 0 1px oklch(0.7 0.21 27 / .55),inset 0 0 3cqw oklch(0 0 0 / .6),inset 0 0 4.5cqw oklch(0.6 0.23 27 / .6)}
.h-idcard[data-card=scanner] .h-idcard-shine{mix-blend-mode:screen;opacity:calc(var(--glow) * .9);
  background:linear-gradient(105deg,transparent calc(26% + var(--tx) * 30%),oklch(1 0 0 / .15) calc(38% + var(--tx) * 30%),oklch(1 0 0 / .04) calc(46% + var(--tx) * 30%),transparent calc(52% + var(--tx) * 30%)),
    radial-gradient(50% 70% at calc(50% + var(--tx) * 50%) calc(40% + var(--ty) * 50%),oklch(1 0 0 / .1),transparent 70%)}
.h-idcard-back[data-card=scanner] .h-idcard-shine{background:linear-gradient(255deg,transparent calc(26% + var(--tx) * 30%),oklch(1 0 0 / .08) calc(38% + var(--tx) * 30%),transparent calc(52% + var(--tx) * 30%))}
.h-scan-read{display:flex;align-items:center;gap:1.2cqw;min-width:0;max-width:100%}
.h-scan-read .h-scan-value{min-width:0}
.h-scan-led{flex:none;width:max(5px,1.5cqw);height:max(5px,1.5cqw);border-radius:50%;background:var(--led);
  box-shadow:0 0 0 .2cqw oklch(0.08 0.04 255 / .7),0 0 .7cqw .1cqw var(--led),0 0 2.6cqw .4cqw color-mix(in oklch,var(--led) 50%,transparent)}
.h-idcard[data-card=scanner][data-warn=true] .h-scan-led{width:max(6px,1.8cqw);height:max(6px,1.8cqw)}
.h-scan-term{position:absolute;z-index:4;left:7.5%;right:7.5%;top:17%;display:flex;flex-direction:column;align-items:flex-start;gap:1cqw}
.h-scan-key{display:grid;grid-template-columns:repeat(2,max-content);gap:.4cqw 3cqw;font-size:max(8px,2.7cqw);line-height:1.3;letter-spacing:.08em;color:var(--scan-ink);text-shadow:0 0 .5cqw var(--scan-glow)}
.h-scan-about{margin-top:1.4cqw;font-size:max(8px,2.6cqw);line-height:1.4;text-transform:none;color:var(--scan-ink);opacity:.92;text-shadow:0 0 .5cqw var(--scan-glow);overflow-wrap:anywhere;
  display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;line-clamp:2;overflow:hidden}
.h-idcard-back .h-scan-foot{justify-content:flex-start;gap:4cqw}
.h-idcard-back .h-scan-field,.h-idcard-back .h-scan-field+.h-scan-field{flex:0 0 auto;max-width:none;text-align:left;align-items:flex-start}
.h-idcard-back .h-scan-field:last-child:not(:first-child){flex:0 1 auto;min-width:0;margin-left:auto;text-align:right;align-items:flex-end}
.h-idcard-back .h-scan-value{font-size:max(8px,2.8cqw)}
.h-scan-cursor{display:inline-block;width:.6em;height:.95em;margin-left:.35em;vertical-align:-.1em;background:var(--scan-ink);box-shadow:0 0 .6cqw var(--scan-glow);animation:h-scan-blink 1.1s steps(1) infinite}
@keyframes h-scan-blink{50%{opacity:0}}
@media (prefers-reduced-motion: reduce){.h-scan-cursor{animation:none}}
.h-cardpick{display:flex!important;align-items:center;gap:8px;padding:4px 10px 4px 4px!important;font-size:12px;color:var(--h-fg)}
.h-cardswatch{display:block;position:relative;width:40px;height:25px;border-radius:5px;overflow:hidden;flex:none}
.h-cardswatch[data-card=member]{background:radial-gradient(115% 105% at 74% 40%,oklch(0.6 0.19 var(--hue)) 0%,oklch(0.4 0.2 var(--hue)) 46%,oklch(0.2 0.12 var(--hue)) 100%);
  box-shadow:inset 0 0 0 2px oklch(0.4 0.2 var(--hue)),inset 0 0 0 2.8px oklch(0.95 0.07 200 / .8)}
.h-cardswatch[data-card=scanner]{background:oklch(0.1 0.035 262)}
.h-cardswatch-screen{position:absolute;inset:0;border-radius:inherit;box-shadow:inset 0 0 0 1px oklch(1 0 0 / .16),inset 0 0 4px oklch(0 0 0 / .6);
  background:linear-gradient(oklch(0.86 0.12 205 / .8),oklch(0.86 0.12 205 / .8)) 0 2px/100% 1px no-repeat,
    radial-gradient(circle at 68% 58%,oklch(0.95 0.06 75) 0 1.5px,oklch(0.7 0.16 var(--hue2)) 3px,oklch(0.5 0.19 var(--hue)) 6px,transparent 10px),
    radial-gradient(circle at 26% 66%,oklch(0.6 0.19 var(--hue)) 0 2px,oklch(0.36 0.15 var(--hue)) 5px,transparent 8px),oklch(0.1 0.035 262)}
.h-profile-scrim{position:fixed;inset:0;z-index:1000;display:grid;place-items:center;padding:16px;background:color-mix(in oklch,var(--h-bg) 58%,transparent);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px)}
.h-profile{width:min(400px,100%);max-height:calc(100vh - 32px);overflow:auto;display:flex;flex-direction:column;gap:14px;padding:12px 12px 16px;border-radius:30px;background:var(--h-card);border:1px solid var(--h-line);box-shadow:0 30px 80px -30px var(--h-shadow);transform-origin:50% 60%}
.h-profile-body{display:flex;flex-direction:column;gap:10px;padding:0 8px}
.h-profile-actions{display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:0 8px}
.h-profile-actions>*{max-width:100%}
.h-profile-head{display:flex;justify-content:flex-end;align-items:center;gap:2px;margin-bottom:-6px}
.h-profile-vibe{font-size:14px;line-height:1.45;color:var(--h-fg)}
.h-profile-row{display:flex;gap:8px;align-items:flex-start;font-size:12px;color:var(--h-fg2)}
.h-profile-keyrow>button{flex:0 0 auto;margin-top:-3px}
.h-profile-agents{display:flex;flex-direction:column;gap:4px}
.h-profile-agents .h-plain{gap:8px;padding:4px 6px;border-radius:10px}
.h-profile-agents .h-plain:hover{background:var(--h-hover)}
/* people's pictures and faces: a plain circle, no tint (an agent's face has its bubble and its label) */
/* the builders (agent face, person avatar): preview and actions beside layer tabs and option grids; stacks when narrow */
.h-bld-wrap{container-type:inline-size}
.h-bld{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start;outline:none}
.h-bld-side{flex:none;display:flex;flex-direction:column;align-items:center;gap:10px;width:148px}
.h-bld-preview{width:148px;height:148px;display:grid;place-items:center;border-radius:18px;background:#0b1117;box-shadow:inset 0 0 0 1px var(--h-line)}
.h-bld-preview .h-pav{border-radius:12px}
.h-bld-actions{justify-content:center}
.h-bld-main{flex:1 1 260px;min-width:0;display:flex;flex-direction:column;gap:10px}
.h-bld-tabs{display:flex;flex-wrap:wrap;gap:4px}
.h-bld-tabs button{flex:none;border:1px solid transparent;background:transparent;color:var(--h-fg2);border-radius:999px;padding:4px 10px;font-size:12px;cursor:pointer;white-space:nowrap}
.h-bld-tabs button:hover{background:var(--h-hover);color:var(--h-fg)}
.h-bld-tabs button[data-on=true]{background:var(--h-raise);color:var(--h-fg);border-color:var(--h-line2)}
.h-bld-tabs button:focus-visible,.h-bld-opt:focus-visible{outline:2px solid var(--h-accent);outline-offset:1px}
.h-bld-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(74px,1fr));gap:6px}
.h-bld-swatches{grid-template-columns:repeat(auto-fill,minmax(82px,1fr))}
.h-bld-opt{display:flex;flex-direction:column;align-items:center;gap:4px;padding:4px;border:1px solid var(--h-line);border-radius:12px;background:#0b1117;cursor:pointer;
  transition:transform .32s cubic-bezier(.3,1.5,.5,1),border-color .15s linear,box-shadow .15s linear}
.h-bld-swatches .h-bld-opt{background:var(--h-raise);padding:8px 4px 6px}
.h-bld-opt:hover{border-color:var(--h-line2)}
.h-bld-opt:active{transform:scale(.95)}
.h-bld-opt[data-on=true]{border-color:var(--h-accent);box-shadow:0 0 0 1px var(--h-accent)}
.h-bld-opt .h-pav{border-radius:8px}
.h-bld-swatch{width:28px;height:28px;border-radius:50%;box-shadow:inset 0 0 0 1px oklch(0 0 0 / .25)}
.h-bld-name{font-size:11px;color:var(--h-fg2);text-align:center;line-height:1.2}
@media (prefers-reduced-motion: reduce){.h-bld-opt{transition:none}.h-bld-opt:active{transform:none}}
@container (max-width: 440px){.h-bld-side{flex-direction:row;width:100%;align-items:flex-end}.h-bld-actions{flex-direction:column;align-items:flex-start}}
.h-pav{display:inline-grid;flex:none;border-radius:50%;overflow:hidden}
.h-pav svg{display:block}
.h-pface,.h-photo{display:inline-grid;place-items:center;flex:none;border-radius:50%;overflow:hidden;background:var(--h-raise);box-shadow:inset 0 0 0 1px var(--h-line)}
.h-photo img{width:100%;height:100%;object-fit:cover;display:block}
.h-idcard-hero .h-pface,.h-idcard-hero .h-photo,.h-idcard-hero .h-pav{width:100%!important;height:100%!important}
.h-idcard-hero .h-pav{border-radius:16%;box-shadow:0 0 0 1px oklch(1 0 0 / .18)}
.h-idcard-hero .h-pav svg{width:100%;height:100%}
.h-typingline{min-height:22px;padding:2px 6px 3px;font-size:12px;color:var(--h-fg3);display:flex;align-items:center}
.h-typingrow{display:flex;align-items:center;gap:7px;min-width:0}
.h-typing.h-typing-s{padding:3px 6px;gap:3px;border-radius:999px;flex:none}.h-typing-s i{width:4px;height:4px}
.h-crop{border:1px solid var(--h-line2);border-radius:12px;padding:12px;background:var(--h-card)}
.h-crop-row{gap:16px;align-items:flex-start;flex-wrap:wrap}
.h-crop-view{width:160px;height:160px;flex:none;border-radius:50%;overflow:hidden;cursor:grab;touch-action:none;background:var(--h-raise);outline:0}
.h-crop-view:active{cursor:grabbing}.h-crop-view:focus-visible{box-shadow:0 0 0 2px var(--h-accent)}
.h-crop-view canvas{width:100%;height:100%;display:block}
.h-look .h-hint{font-size:11.5px;color:var(--h-fg3)}
`
