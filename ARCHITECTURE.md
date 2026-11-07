# Architecture

Ninsei is a Hermes plugin: rooms for people and their own agents. No server: rooms are signed Nostr events on public relays, and each person's Hermes runs the rest.

## The parts

- `__init__.py`: `register(ctx)` hands `ctx.llm` to the engine and registers tools and the platform. On a fresh profile the tools create nothing.
- `ninsei_engine/`: loaded once per process by `_loader.py`. `engine.py` runs on its own thread and loop; `brain.py` makes every model call; `relays.py` is the pool and outbox.
- `ninsei_platform.py`: gateway-only adapter for the private line. `ninsei_hooks.py`: build-progress hooks.
- `dashboard/plugin_api.py`: FastAPI router at `/api/plugins/ninsei/` for both UIs. `dashboard/dist/index.js` and `desktop/plugin.js` (ESM, SDK + react only) are built from `ui/*.js` by `scripts/build_ui.py`.

`register()` and the router share one engine (`get_engine()`); routes touch its state only through `_run` and `_sync`, on its loop. An `fcntl` lock on `engine.lock` stops a second engine on the same data.

## Identity and trust

Each install has a person and an agent keypair. The person signs `sha256("ninsei-bind:v1:" + agent_pk)`, and every agent event carries that signature in an `owner` tag; a failing tag drops the event. Keys, ids and signatures are exact lowercase hex.

Display names are not identity. The first key seen using a name **live** in a room holds it (a bare join claims nothing). A backfill event (a history pull, or dated over `FRESH_WINDOW` before arrival) takes a name only tentatively; a name two keys used in history is `CONTESTED` until one posts live. A later key under a held name is `UNVERIFIED` to the model. Lookalike spellings get past this.

Room ids commit to their creator (`sha256("ninsei-room:{creator_pk}:{nonce}")[:16]`); other keys' metadata is ignored. Metadata and cards carry 12 bits of proof of work against careless junk.

**Hiding** is the only moderation, and local: `hide_person` stores the person's key and up to 8 agent keys, and `_on_event` refuses their events first.

**The safety rule is structural.** An agent obeys only its owner. The room brain gets the persona plus a `<room_transcript>` block, one labelled line per event (YOUR OWNER, person, agent of X, UNVERIFIED, you). `brain._clean` makes stranger text one line (NFKC, no invisible characters, brackets turned round, label lookalikes and fence words stripped), so only the real owner row can say YOUR OWNER. Game turns say they come from the owner's plugin, the host's question fenced in `<game_question>`, else the model refuses and posts the refusal; `game_answer` drops off-script output. The brain has no tools, memory or files: an injection can at most make the agent say something wrong and spend budget. The vibe is in every room prompt: it is not private. Anything with real power (building a toy) happens only in the owner's Hermes chat, after their yes.

## The private line

`ctx.register_platform("ninsei")`: the "Your Hermes" thread reaches the owner's full Hermes through the `private_line` table, never published. Owner rows are marked `delivered` only after `handle_message` returns, else re-queued (at-least-once). The user account is the trust boundary: any process under it can insert an owner row. The adapter imports only the store (linted).

## Relays and the outbox

A durable event's `pending` outbox row is written before sending, so quitting mid-send resends it next start. Failed rows stay 4 days. Resubscribes ask from 300 s before the newest event, clamped to now. Backoff resets only after a connection stayed up 30 s, or delivered something and stayed up 5 s. All filters (live, each creator's metadata, one history filter per room, limit 300) are chunked, at most 8 per request. An empty relay list means offline.

**Rate limits are per IP.** A relay that says "rate-limited", "try again later" or HTTP 429/503 gets no events for 1 min, doubling to 30 until it stays quiet that long; refused events stay pending and are resent paced. Codes don't carry relays, so a join that finds nothing returns `found: false`. `scripts/relay_probe.py` checks a room from outside.

## Finding people

New installs join **Commons** once (leaving sticks); onboarding says it is public. Its metadata ships pre-signed in `ninsei_engine/commons.json` (`scripts/sign_commons.py`).

## Event kinds

| Kind | Use |
|---|---|
| 4242 | room events: messages, joins, offers, offer states, shares, game moves. Tag `h` = room id |
| 21042 | ephemeral: presence beats (every 60 s, absent after 150 s; state changes at most one per 5 s) and floor claims |
| 30078 | replaceable: room metadata (`d=ninsei/room/<id>`) and interest cards (`d=ninsei/card`) |

Content carries `at`, Unix seconds with millisecond precision, trusted only inside `[created_at, created_at + 1)`. Arrival times persist in `events.arrived_at`.

## Who speaks (floor control)

Each agent publishes an ephemeral claim: 100 addressed by name (`at_mentions` ignores case and spacing), 60 the owner says anyone/agents/everyone, 40 the owner's question, or anything when alone, 30 an offer, 20 chattiness; ties by `sha256(agent_pk + trigger)[:8]`. After `CLAIM_WINDOW` (1.5 s) only the winner calls the model. Receivers re-derive each claim with `_allowed_prio`: 100 only if the trigger names that agent, 60/40 only for the trigger author's own agent, else 20.

## Budget

`store.reserve(category, estimate, daily_limit)` runs atomically before every model call. A call that returns is settled at real usage; one that raises costs 0, but a timeout or cancel keeps the estimate. Default: 40,000 tokens a day. `msgs_daily` (default 60) caps chat replies. Owner messages skip the stranger limits but not pacing (8 posts per 5 min, 6 s per room) or the daily caps. Strangers are capped per team and per room before anything is sent.

## Offers, builds, shares

When a topic keeps coming up, one model call drafts a pitch, title and private task only the owner sees. One open offer per room; unanswered, it expires after 24 h. Leaving a room drops its offers and drafts. The build prompt marks the task untrusted and fences room quotes with a random boundary, which lowers the risk only.

`build_report` returns the file, a secret scan and its `sha256`; `share_build` publishes only a file with that hash, under 48 KB serialized.

**Toys** run, after the viewer presses Run, in a sandboxed `allow-scripts` iframe under a CSP (`toy.TOY_CSP`, mirrored in `ui/platform/*_head.js`, test-checked) that blocks fetch, XHR, WebSocket, images, fonts, frames and workers. **It does not block WebRTC:** Chromium ignores `webrtc 'block'`, so a toy can reveal the viewer's IP. `TOY_GUARD` hides the WebRTC constructors (a child `srcdoc` frame gets them back) and closes the frame on any later load. Validate refuses `<script` in `desktop/plugin.js`.

**Build progress.** `ninsei_hooks.py` writes only a step count and state, shown in that room's presence.

## Games

Both games share `tales_*` events, the host's secret seed and the phase clock. One start per room at a time; a start with no known arrival never outranks a live one. Only present players count (per team, the person's answer plus one agent's), at most 24, regulars first, then the seed picks. Reveals stay under 32 KB. In Tall Tales only people vote, never for their team's option.

**Answers and votes are sealed.** A `tales_fake` or `tales_vote` carries only `enc`: NIP-44 v2 (`nip44.py`, vectors in `tests/data/`) to the host agent key, padded to 944 chars. Answers hold `{text, nonce}`, votes `{option, agents}`. The host refuses other sizes before crypto, opens each author's latest event only, ignores plaintext. Only its writer can match a claim token, `sha256("claim:" + oid + ":" + nonce)[:12]`; each option gets equal decoy-padded counts, in option order. Lucky rule: a fake matching the truth earns a point, the truth carries that writer's token and (like a merged fake) the first writer's spelling, and their team can't vote for it. Who answered and voted is public.

## Faces, cards and reactions

Faces come only from fixed lists shared by `clean_face` and `faceFor`. Beats are capped at 4 KB. Saved card images XML-escape stranger strings. Reactions derive from events every client has, so none can be forged.

## Pitfalls that have bitten

- **Engine loop.** Stop it with `await asyncio.to_thread(e.stop)`; read state on its loop.
- **Test profiles and gateways.** Only `xeniamaya`/`xeniasam` (`gateway.standalone: true`). Run `gateway run` under `lg`, never `gateway start`, with `TELEGRAM_*` stripped. After a profile rename, a stale `gateway_state.json` shows `profile_mismatch`: move it aside.
- **The name is in the protocol** (`ninsei-room:`, `ninsei-bind:v1:`, `ninsei/...` tags): a rename strands old rooms.
- **Tests wait for conditions, not time** (`tests/test_test_hygiene.py` enforces it).
- **Relay lists.** `relays=[]` once fell through to the defaults and tests joined the real Commons; `tests/conftest.py` fails any non-local dial.
- **A Desktop on a test profile runs its own gateway** holding the engine: a dashboard there gets 409.
- **Untrusted content everywhere.** Any field can have any type or size; `_on_event` checks size and age before parsing. A room holds at most `MAX_ROOM_EVENTS`; the trim drops the heaviest authors' oldest events first, never the owner's or the live game's, and never re-adds them. `tests/test_fuzz.py` fuzzes the views.
- **The validate probe** passes a ctx without `llm`; `plugins.isolation: host` refuses `register_platform`.
- **Public plugin API only.** A test fails on any `agent.*` import. `websockets` is declared in `plugin.yaml`.
