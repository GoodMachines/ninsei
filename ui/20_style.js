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
.h-page{container-type:inline-size;height:100%;min-height:0}
.h-grid{display:grid;grid-template-columns:220px minmax(0,1fr) 240px;height:100%;min-height:0}
.h-left,.h-right{min-height:0;overflow-y:auto;padding:14px 10px}
.h-left{border-right:1px solid var(--h-line)}
.h-right{border-left:1px solid var(--h-line)}
.h-center{display:flex;flex-direction:column;min-height:0;min-width:0}
.h-grid[data-embedded]{grid-template-columns:minmax(0,1fr) 240px}
.h-tab{height:100%;min-height:0;overflow-y:auto;padding:10px 8px}
@container (max-width: 980px){.h-grid{grid-template-columns:200px minmax(0,1fr)}.h-grid[data-embedded]{grid-template-columns:minmax(0,1fr)}.h-right{display:none}.h-grid[data-people=open] .h-right{display:block;position:absolute;right:0;top:0;bottom:0;width:260px;z-index:5;background:var(--h-bg);box-shadow:-12px 0 24px -16px var(--h-shadow)}}
@container (max-width: 680px){.h-grid{grid-template-columns:minmax(0,1fr);grid-template-rows:auto minmax(0,1fr)}.h-grid[data-embedded]{grid-template-rows:minmax(0,1fr)}
.h-left{border-right:0;border-bottom:1px solid var(--h-line);padding:6px 10px;display:flex;align-items:center;gap:4px;overflow-x:auto;overflow-y:hidden}
.h-left .h-brand{padding:0 6px 0 0;flex:none}.h-left .h-brand>div{display:none}
.h-left .h-nav{flex-direction:row;margin:0;flex:none}.h-left .h-navrow{width:auto;white-space:nowrap}
.h-left .h-navhead{padding:0;flex:none;order:9}.h-left .h-navhead .h-sec{display:none}
.h-head{padding:10px 12px;flex-wrap:wrap}.h-timeline,.h-composer{padding-left:12px;padding-right:12px}}
.h-grid{position:relative}

/* the People toggle only shows when the right rail is folded away */
.h-peoplebtn{display:none!important}
@container (max-width: 980px){.h-peoplebtn{display:inline-flex!important}}

/* left rail */
.h-brand{display:flex;align-items:center;gap:8px;padding:0 6px 12px}
.h-brand b{font-size:14px;letter-spacing:.01em}
.h-nav{display:flex;flex-direction:column;gap:1px;margin-bottom:14px}
.h-navrow{display:flex;align-items:center;gap:8px;width:100%;padding:5px 8px;border-radius:6px;border:0;background:transparent;color:var(--h-fg2);cursor:pointer;text-align:left;min-width:0}
.h-navrow:hover{background:var(--h-hover);color:var(--h-fg)}
.h-navrow[data-on=true]{background:var(--h-raise);color:var(--h-fg)}
.h-navrow .h-dot{width:6px;height:6px;border-radius:50%;background:var(--h-accent);flex:none}
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
.h-scroll{flex:1;min-height:96px;overflow-y:auto;overscroll-behavior:contain}
.h-timeline{display:flex;flex-direction:column;padding:14px 18px 8px;gap:2px;max-width:860px;width:100%;margin:0 auto}
.h-msg{display:grid;grid-template-columns:32px minmax(0,1fr);gap:0 10px;padding:3px 0}
.h-msg[data-first=true]{margin-top:10px}
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
.h-menu button{display:flex;align-items:flex-start;gap:8px;width:100%;text-align:left;padding:7px 9px;border-radius:7px;border:0;background:transparent;color:var(--h-fg);cursor:pointer}
.h-menu button:hover{background:var(--h-hover)}
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
.h-typing i{width:5px;height:5px;border-radius:50%;background:var(--h-fg3);animation:h-breathe 1.1s cubic-bezier(.45,.05,.4,1) infinite alternate}
@keyframes h-breathe{0%{transform:translateY(1px);opacity:.35}100%{transform:translateY(-2px);opacity:1}}
@media (prefers-reduced-motion: reduce){.h-typing i{animation:none}}
.h-thinking{display:flex;align-items:center;gap:8px;padding:6px 2px 2px;animation:h-fadein .3s ease-out}
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
.h-agentrow{display:flex;align-items:center;gap:8px;margin-left:14px;padding:3px 6px 3px 8px;border-left:1px solid var(--h-line);min-width:0}
.h-statepill{font-size:10.5px;color:var(--h-fg3)}
.h-mine{border:1px solid var(--h-line);border-radius:12px;padding:12px;display:flex;flex-direction:column;gap:10px;margin-top:14px}

/* Tall Tales */
.h-tales{border:1px solid color-mix(in oklch,var(--h-accent) 40%,var(--h-line2));border-radius:14px;padding:12px 14px;margin-bottom:8px;background:var(--h-card);display:flex;flex-direction:column;gap:10px}
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
.h-notice{display:flex;gap:10px;align-items:flex-start;padding:10px 12px;border-radius:10px;background:var(--h-raise);color:var(--h-fg2);font-size:12px}
.h-hero{display:flex;flex-direction:column;align-items:center;text-align:center;gap:10px;padding:28px 10px 8px}
.h-savebar{justify-content:flex-end;position:sticky;bottom:0;padding:10px 0;background:var(--h-bg);border-top:1px solid var(--h-line)}
.h-relay{display:flex;align-items:center;gap:8px;font-size:12px;padding:3px 0}
.h-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:48px 20px;text-align:center;color:var(--h-fg2);flex:1}

/* status bar chip (Desktop) */
.h-statuschip{display:inline-flex;align-items:center;gap:5px;height:100%;padding:0 6px;border:0;background:transparent;color:var(--h-fg3);font-size:11px;cursor:pointer}
.h-statuschip:hover{color:var(--h-fg);background:var(--h-hover)}

/* faces */
.hf{display:inline-grid;place-items:center;flex:none;transform-origin:50% 60%}
.hf svg{overflow:visible}
.hf-body{fill:var(--h-accent);fill:color-mix(in oklch,oklch(from var(--h-fg) l 0.15 var(--hue)) 64%,var(--h-bg))}
.hf-shine{fill:none;stroke:color-mix(in oklch,var(--h-fg) 22%,transparent);stroke-width:1}
.hf-eye{fill:var(--h-bg);transform-box:fill-box;transform-origin:center}
.hf-xeyes path,.hf-line{fill:none;stroke:var(--h-bg);stroke-width:1.8;stroke-linecap:round}
.hf-mouth{fill:var(--h-bg);transform-box:fill-box;transform-origin:center}
.hf-clock circle{fill:var(--h-card);stroke:var(--h-fg2);stroke-width:1.2}
.hf-clock path{stroke:var(--h-fg2);stroke-width:1.2;stroke-linecap:round}
.hf-hand{transform-origin:33px 7px}
.hf-head{transform-origin:20px 22px;transition:transform .5s cubic-bezier(.34,1.45,.5,1),opacity .4s linear,filter .4s linear}
.hf[data-state=idle] .hf-eye{animation:hf-blink 4.7s infinite}
.hf[data-state=working] .hf-eyes{animation:hf-scan 1.6s cubic-bezier(.45,.05,.4,1) infinite alternate}
.hf[data-state=working] .hf-eye{animation:hf-blink 4.7s infinite}
.hf[data-state=speaking] .hf-talk{animation:hf-talk .34s cubic-bezier(.3,.7,.4,1) infinite alternate}
.hf[data-state=waiting] .hf-eye{transform:scaleY(.42)}
.hf[data-state=waiting] .hf-hand{animation:hf-tick 6s steps(12) infinite}
.hf[data-state=error] .hf-head{transform:rotate(-9deg)}
.hf[data-state=absent] .hf-head{opacity:.42;filter:saturate(.2)}
.hf[data-state=absent] .hf-eye{transform:scaleY(.14)}
.hf[data-size=s] .hf-shine{display:none}
/* idle life: a slow breath and an occasional glance, offset per face by the same delay as the blink */
.hf[data-state=idle]:not([data-expr]) .hf-head{animation:hf-breathe 4.2s cubic-bezier(.45,.05,.55,.95) infinite alternate}
.hf[data-state=idle]:not([data-expr]) .hf-eyes{animation:hf-glance 9.4s cubic-bezier(.3,.7,.4,1) infinite}
/* reactions (data-expr): eyes and head pose; the mouth shape comes from the component */
.hf[data-expr] .hf-eye{animation:none}
.hf[data-expr=smug] .hf-eye{transform:scaleY(.48) translateY(.7px)}
.hf[data-expr=smug] .hf-head{transform:rotate(8deg)}
.hf[data-expr=caught] .hf-eye{transform:scale(1.25)}
.hf[data-expr=caught] .hf-head{animation:hf-shake .5s cubic-bezier(.36,.07,.19,.97) 1}
.hf[data-expr=happy] .hf-eye{transform:scaleY(.42) translateY(-.4px)}
.hf[data-expr=happy] .hf-head{animation:hf-hop .62s cubic-bezier(.3,.7,.4,1) 2}
.hf[data-expr=wary] .hf-eye{transform:scaleY(.36) translateX(-1.2px)}
.hf[data-expr=wary] .hf-head{transform:rotate(-6deg)}
.hf[data-expr=perk] .hf-eye{transform:scale(1.12)}
.hf[data-expr=perk] .hf-head{animation:hf-hop .5s cubic-bezier(.3,.7,.4,1) 1}
@keyframes hf-breathe{0%{transform:scale(1)}100%{transform:scale(1.022,.985) translateY(.25px)}}
@keyframes hf-glance{0%,78%,100%{transform:translateX(0)}82%,90%{transform:translateX(1.5px)}94%{transform:translateX(-.4px)}}
@keyframes hf-shake{0%,100%{transform:translateX(0)}20%{transform:translateX(-1.6px) rotate(-4deg)}45%{transform:translateX(1.4px) rotate(3deg)}70%{transform:translateX(-.8px)}}
@keyframes hf-hop{0%,100%{transform:translateY(0)}35%{transform:translateY(-2.6px) scale(1.03,.97)}60%{transform:translateY(0) scale(.98,1.02)}}
@keyframes hf-blink{0%,93%,100%{transform:scaleY(1)}95.5%{transform:scaleY(.1)}}
@keyframes hf-scan{0%{transform:translateX(-1.6px)}100%{transform:translateX(1.6px)}}
@keyframes hf-talk{0%{transform:scaleY(.35) scaleX(1.1)}100%{transform:scaleY(1.15) scaleX(.9)}}
@keyframes hf-tick{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion: reduce){.hf *{animation:none!important;transition:none!important}}
`
