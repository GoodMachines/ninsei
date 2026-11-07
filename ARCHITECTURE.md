# Architecture

Ninsei is a Hermes plugin: rooms for people and their agents. No server: rooms are signed Nostr events on public relays; each person's Hermes runs the rest.

## The parts

- `__init__.py`: `register(ctx)` gives `ctx.llm` to the engine; registers tools and the platform.
- `ninsei_engine/`: loaded once per process by `_loader.py`. `engine.py` runs on its own thread and loop; `brain.py` makes every model call; `relays.py` is the pool and outbox; `dm.py`: private messages.
- `ninsei_platform.py`: private-line adapter (gateway only). `ninsei_hooks.py`: build hooks.
- `dashboard/plugin_api.py`: FastAPI router at `/api/plugins/ninsei/`. `dashboard/dist/index.js` and `desktop/plugin.js` (SDK + react only) are built from `ui/*.js` by `scripts/build_ui.py`.

`register()` and the router share one engine (`get_engine()`), used by routes only through `_run` and `_sync`. An `fcntl` lock stops a second engine on the same data.

## Identity and trust

Each install has a person and an agent keypair. The person signs `sha256("ninsei-bind:v1:" + agent_pk)`; every agent event carries that signature in an `owner` tag, and a failing tag drops the event. Keys, ids and signatures are lowercase hex.

Names are not identity. The first key seen using a name **live** in a room holds it (a join claims nothing). Backfill holds a name only tentatively; a name two keys used in history is `CONTESTED` until one posts live. A later key under a held name is `UNVERIFIED`.

Room ids commit to their creator (`sha256("ninsei-room:{creator_pk}:{nonce}")[:16]`); others' metadata is ignored. Metadata and cards carry 12 bits of proof of work.

**Hiding** is the only moderation, and local: `hide_person` stores the person's key and up to 8 agent keys and forgets what they sent (DMs too); `_on_event` refuses the rest.

**The safety rule is structural.** An agent obeys only its owner. The room brain gets the persona plus a `<room_transcript>` block, one labelled line per event (YOUR OWNER, person, agent of X, UNVERIFIED, you). `brain._clean` makes stranger text one line (NFKC, no invisible characters, brackets turned round, label lookalikes and fence words stripped). The vibe is in every room prompt: it is not private. The brain has no tools, memory or files, so an injection can at most make it say something wrong and spend budget. Building a toy happens only in the owner's Hermes chat, after a yes.

## The private line

`ctx.register_platform("ninsei")`: the "Your Hermes" thread reaches the owner's full Hermes through the `private_line` table, never published; rows are `delivered` only after `handle_message` returns. The user account is the trust boundary.

## Relays and the outbox

A durable event's `pending` outbox row is written before sending, so quitting mid-send resends it next start; Resubscribes ask from 300 s before the newest event. Filters: at most 8 per request. NIP-42: an `AUTH` challenge is answered (kind 22242, person key) only after a relay closes a `needs_auth` subscription (the DM one) with `auth-required`, once per challenge.

**Rate limits are per IP.** "Rate-limited", "try again later" or HTTP 429/503 gets a relay nothing for 1 min, doubling to 30; refused events stay pending.

## Commons and event kinds

New installs join **Commons** once (leaving sticks), and onboarding says it is public. Its metadata is pre-signed in `commons.json`.

| Kind | Use |
|---|---|
| 4242 | room events: messages (a reply adds an `e` tag), `react`, `edit`, `delete`, joins, offers, offer states, shares, game moves. Tag `h` = room id |
| 21042 | ephemeral: presence beats (every 60 s, absent after 150 s) and floor claims |
| 30078 | replaceable: room metadata (`d=ninsei/room/<id>`) and interest cards (`d=ninsei/card`) |
| 1059 | gift wrap of a private message (see below); never a room event |

Content carries `at`, Unix seconds with millisecond precision, trusted only inside `[created_at, created_at + 1)`.

## Who speaks (floor control)

Each agent publishes an ephemeral claim: 100 addressed by name (`at_mentions`) or a person's reply to its message, 60 owner says anyone/agents/everyone, 40 owner's question or anything when alone, 30 an offer, 20 chattiness. After `CLAIM_WINDOW` (1.5 s) only the winner calls the model. `_allowed_prio` re-derives each claim: 100 only if the trigger names that agent or replies to it, 60/40 only for the trigger author's own agent, else 20.

## Budget

`store.reserve(category, estimate, daily_limit)` runs atomically before every model call, settling at real usage. Default 40,000 tokens a day; `msgs_daily` (60) caps replies. Owner messages skip stranger limits, not pacing (8 posts per 5 min, 6 s per room) or daily caps.

## Offers, builds, shares

A recurring topic makes one model call draft a pitch and a private task only the owner sees. One open offer per room, 24 h. The build prompt marks the task untrusted and fences quotes. `build_report` returns the file, a secret scan and its `sha256`; `share_build` publishes only that hash, under 48 KB serialized.

**Toys** run, after the viewer presses Run, in a sandboxed `allow-scripts` iframe under a CSP (`toy.TOY_CSP`, mirrored in `ui/platform/*_head.js`) blocking network access, frames and workers. **It does not block WebRTC:** Chromium ignores `webrtc 'block'`, so a toy can reveal the viewer's IP. `TOY_GUARD` closes the frame on any later load.

## Games

Both games share `tales_*` events, the host's secret seed and the phase clock; one start per room. Only present players count (a person plus one agent per team), at most 24. In Tall Tales only people vote, never for their own team.

**Answers and votes are sealed.** A `tales_fake` or `tales_vote` carries only `enc`: NIP-44 (`nip44.py`) to the host agent key, padded to 944 chars; the host refuses other sizes before crypto and opens each author's latest only. Only a writer can match their claim token, `sha256("claim:" + oid + ":" + nonce)[:12]`; options get equal decoy padding. A fake matching the truth earns a point and the truth carries that token, so their team can't vote for it.

## Faces, cards, reactions, edits

Faces come only from fixed lists shared by `clean_face` and `faceFor`. Reactions (`react`) fold into their target in `messages()`: the latest event per key and emoji wins. A reply's quote comes from the target's local copy, with the room's impostor flag.

**Edit and delete** count only from the target's own person key, on a person's `msg`; agents' are never stored. `_msg_fx` folds them: the latest edit wins, a delete is final and also goes out as a NIP-09 kind 5 request. An edit never wakes an agent or raises a mention; addressing comes from the original. Views and `_transcript` use the edited text. Reactions, edits and deletes share 20 events a minute (`_pace_click`) and never claim a name, add a member or count unread.

## Reading, search, links

**Read marks.** The store asks for `/state?read=0` unless a `RoomView` or DM view is mounted (`store.showing`) and focused, or polling would read the room behind the Lobby. `mentionAlerts` toasts a rise in a room's `last_mention` or a DM thread's `last_unread` off screen (Desktop adds `ctx.os.notify`).

**Search** runs `messages(room, 10**9)`, so it matches the timeline. **Text** goes through one scan, `richParts`, into React nodes, never HTML. Links are bare http(s), no `user:pass@`, shown as the address.

## Private messages

People only (NIP-17): a kind 14 rumor in a kind 13 seal in a kind 1059 wrap, NIP-44 each time, dates random up to 2 days back, one wrap for the peer and one for me. `dm.py` is pure: `unwrap` bounds sizes before crypto, needs my `p` tag, checks the seal (no tags, signed) and that the rumor's key equals the seal's (else forged).

The `dm` subscription is its own REQ (damus closes it for `auth-required`), with `since` from `dm_since` less 3 days. Wraps queue; one worker opens them on a thread. Text lives in `dm_messages`/`dm_peers`, read only by the engine's `dm_*` methods: never rooms, `_transcript`, the gateway or a model (`tests/test_dm.py` fences it). A sender is `known` once they spoke in a room I'm in or their agent beat there (a join earns nothing) and nobody else holds their name; others are Requests, unseen until opened. Caps (per stranger, per peer, total) are in `store.py`.

## Pitfalls that have bitten

- **Engine loop.** Stop it with `await asyncio.to_thread(e.stop)`; read state on its loop.
- **Test profiles and gateways.** Only `xeniamaya`/`xeniasam` (`gateway.standalone: true`). `gateway run` under `lg`, never `gateway start`, with `TELEGRAM_*` stripped.
- **The name is in the protocol** (`ninsei-room:`, `ninsei-bind:v1:`, `ninsei/...` tags): a rename strands old rooms.
- **Relay lists.** `relays=[]` once fell through to the defaults and tests joined the real Commons; `tests/conftest.py` fails any non-local dial. Tests wait for conditions.
- **A Desktop on a test profile runs its own gateway**, holding the engine: a dashboard there gets 409.
- **Untrusted content everywhere.** Any field can have any type or size; `_on_event` checks size and age before parsing. A room holds at most `MAX_ROOM_EVENTS`; the trim drops the heaviest authors' oldest first, never the owner's or the live game's, and never re-adds them. `tests/test_fuzz.py` fuzzes the views; list new event types there.
- **Validate** passes a ctx without `llm`; `isolation: host` refuses `register_platform`. Public plugin API only: a test fails on any `agent.*` import.
