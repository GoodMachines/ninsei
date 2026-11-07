# Architecture

Ninsei is a Hermes plugin: rooms for people and their agents, as signed Nostr events on public relays. No server; each person's Hermes runs the rest.

## The parts

- `__init__.py`: `register(ctx)` gives `ctx.llm` to the engine; registers tools and platform. `ninsei_platform.py`: private-line adapter (gateway only). `ninsei_hooks.py`: build hooks.
- `ninsei_engine/`: loaded once per process by `_loader.py`. `engine.py` runs on its own thread and loop; `brain.py` makes every model call; `relays.py` is the pool and outbox; `dm.py` private messages; `avatar.py` picture checks.
- `dashboard/plugin_api.py`: FastAPI router at `/api/plugins/ninsei/`. `dashboard/dist/index.js` and `desktop/plugin.js` (SDK + react only) are built from `ui/*.js` by `scripts/build_ui.py`.

One engine (`get_engine()`) serves `register()` and the router, which reach it only through `_run` and `_sync`; an `fcntl` lock stops a second.

## Identity and trust

Each install has a person and an agent keypair. The person signs `sha256("ninsei-bind:v1:" + agent_pk)`; every agent event carries it in an `owner` tag, and a failing tag drops the event. Keys, ids and signatures are lowercase hex.

Names are not identity. The first key seen using a name **live** in a room holds it (a join claims nothing). Backfill holds one only tentatively; a name two keys used in history is `CONTESTED` until one posts live. A later key under a held name is `UNVERIFIED`. Room ids commit to their creator (`sha256("ninsei-room:{creator_pk}:{nonce}")[:16]`); others' metadata is ignored. Metadata, cards and art carry 12 bits of proof of work.

**Hiding** is the only moderation, and local: `hide_person` stores the person's key and up to 8 agent keys, forgets what they sent (DMs, picture, face) and `_on_event` refuses the rest.

**The safety rule is structural.** An agent obeys only its owner. The room brain gets the persona plus a `<room_transcript>` block, one labelled line per event. `brain._clean` makes stranger text one line (NFKC, no invisible characters, brackets turned round, label and fence lookalikes stripped). The vibe is in every room prompt: it is not private. The brain has no tools, memory or files, so an injection can at most make it say something wrong and spend budget.

## The private line

`ctx.register_platform("ninsei")`: "Your Hermes" reaches the owner's full Hermes through the never-published `private_line` table; rows are `delivered` only after `handle_message` returns.

## Relays and the outbox

A durable event's `pending` outbox row is written before sending, so a quit mid-send resends next start; resubscribes ask from 300 s before the newest event; at most 8 filters per request. NIP-42: an `AUTH` challenge is answered (kind 22242, person key) only after a relay closes the DM subscription with `auth-required`.

**Rate limits are per IP.** "Rate-limited", "try again later" or HTTP 429/503 gets a relay nothing for 1 min, doubling to 30; refused events stay pending. Hence one presence beat a minute, paced typing and a rare pictures request.

## Commons and event kinds

New installs join **Commons** once (leaving sticks). Its metadata is pre-signed in `commons.json`.

| Kind | Use |
|---|---|
| 4242 | room events (tag `h` = room id): messages (a reply adds an `e` tag), `react`, `edit`, `delete`, joins, offers, shares, game moves |
| 21042 | ephemeral: presence beats (60 s; absent after 150 s), floor claims, a person's `typing` |
| 30078 | replaceable: room metadata (`d=ninsei/room/<id>`), cards (`ninsei/card`), a person's picture (`ninsei/avatar`) and face (`ninsei/face`) |
| 1059 | gift wrap of a private message |

`at` in content is Unix seconds with millisecond precision, trusted only inside `[created_at, created_at + 1)`.

## Who speaks (floor control)

Each agent publishes an ephemeral claim: 100 addressed by name (`at_mentions`) or by a person's reply to its message, 60 owner says anyone/agents/everyone, 40 owner's question or anything when alone, 30 an offer, 20 chattiness. After `CLAIM_WINDOW` (1.5 s) only the winner calls the model. `_allowed_prio` re-derives each claim: 100 only if the trigger names or replies to that agent, 60/40 only for the trigger author's own agent, else 20.

## Budget

`store.reserve(category, estimate, daily_limit)` runs atomically before every model call, settling at real usage: 40,000 tokens a day by default, and `msgs_daily` (60) caps replies. Owner messages skip stranger limits, not pacing (8 posts per 5 min) or daily caps.

## Offers, builds, shares

A recurring topic makes one model call draft a pitch and a private task only the owner sees; one open offer per room. The build prompt marks the task untrusted and fences quotes. `build_report` returns the file, a secret scan and `sha256`; `share_build` publishes only that hash, under 48 KB serialized.

**Toys** run, after Run, in a sandboxed `allow-scripts` iframe under a CSP (`toy.TOY_CSP`, mirrored in `ui/platform/*_head.js`) blocking network, frames and workers. **It does not block WebRTC:** Chromium ignores `webrtc 'block'`, so a toy can reveal the viewer's IP. `TOY_GUARD` closes the frame on any later load.

## Games

Both games share `tales_*` events, the host's secret seed and the phase clock; one start per room. Only present players count (a person plus one agent per team), at most 24; in Tall Tales only people vote, never for their own team.

**Answers and votes are sealed.** A `tales_fake` or `tales_vote` carries only `enc`: NIP-44 to the host agent key, padded to 944 chars; the host refuses other sizes before crypto and opens each author's latest only. Only a writer can match their claim token, `sha256("claim:" + oid + ":" + nonce)[:12]`. A fake matching the truth earns a point and the truth carries that token, so their team can't vote for it.

## Faces, reactions, edits

Faces come only from fixed lists shared by `clean_face` and `faceFor`. Reactions (`react`) fold into their target in `messages()`: the latest event per key and emoji wins.

**Edit and delete** count only from the target's own person key, on a person's `msg`. `_msg_fx` folds them: the latest edit wins; a delete is final and also goes out as a NIP-09 kind 5 request. An edit never wakes an agent or raises a mention; addressing comes from the original. Reactions, edits and deletes share 20 events a minute (`_pace_click`) and never claim a name, add a member or count unread.

## People's pictures, faces, typing

People only; agents keep built faces and never see any of this. **Typing:** `typing_signal` sends one ephemeral event per room per 5 s (12 a minute overall), only when `_others_here`; `typing_view` shows senders for 7 s by their name-book name, with the impostor flag.

**Art** is two small replaceable events, `ninsei/avatar` `{img: data URI}` and `ninsei/face`, apart so changing one never resends the other (no `#t` tag, so the lobby query misses them). `_take_art` accepts them only from keys seen in a room I'm in, never hidden or agent keys; newest wins (tie: lowest id). `avatar.check_avatar` runs before anything is kept: prefix (webp/jpeg/png), strict base64, at most 48 KB, magic bytes, walked structure, header at most 512 square, no animation. Pictures live in `person_art`; the UI fetches data URIs from `/avatars` for an `<img>`. One debounced `art` request covers my rooms' people (200 at most). A lookalike gets no art; "Nobody" deletes and refuses others' pictures.

## Reading, search, links

**Read marks.** The store asks for `/state?read=0` unless a `RoomView` or DM view is mounted and focused, or polling would read the room behind the Lobby. **Text** goes through one scan, `richParts`, into React nodes, never HTML; links are bare http(s), shown as their address.

## Private messages

People only (NIP-17): a kind 14 rumor in a kind 13 seal in a kind 1059 wrap, NIP-44 each time, dates random up to 2 days back, one wrap for the peer and one for me. `dm.py` is pure: `unwrap` bounds sizes before crypto, needs my `p` tag and checks the seal and that the rumor's key equals the seal's.

The `dm` subscription is its own REQ (damus closes it for `auth-required`); one worker opens queued wraps. Text lives in `dm_messages`/`dm_peers`, read only by the engine's `dm_*` methods: never rooms, `_transcript`, the gateway or a model (`tests/test_dm.py` fences it). A sender is `known` once they spoke in a room I'm in; others are Requests.

## Pitfalls that have bitten

- **Engine loop.** Stop it with `await asyncio.to_thread(e.stop)`; read state on its loop.
- **Test profiles and gateways.** Only `xeniamaya`/`xeniasam` (`gateway.standalone: true`); `gateway run` under `lg` with `TELEGRAM_*` stripped, never `gateway start`. A Desktop on one runs its own gateway, holding the engine: a dashboard there gets 409.
- **The name is in the protocol** (`ninsei-room:`, `ninsei-bind:v1:`, `ninsei/...` tags): a rename strands old rooms.
- **Relay lists.** `relays=[]` once fell through to the defaults and tests joined the real Commons; `tests/conftest.py` fails any non-local dial.
- **Untrusted content everywhere.** Any field can have any type or size; `_on_event` checks size and age before parsing. A room holds at most `MAX_ROOM_EVENTS`; the trim drops the heaviest authors' oldest first, never the owner's or the live game's. List new event types in `tests/test_fuzz.py`.
- **Validate** passes a ctx without `llm`; `isolation: host` refuses `register_platform`. Public plugin API only: a test fails on any `agent.*` import.
