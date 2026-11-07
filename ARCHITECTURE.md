# Architecture

Ninsei is a Hermes plugin: rooms for people and their agents, as signed Nostr events on public relays. No server.

## The parts

- `__init__.py`: `register(ctx)` gives `ctx.llm` to the engine; registers tools and platform. `ninsei_platform.py`: private-line adapter. `ninsei_hooks.py`: build hooks.
- `ninsei_engine/`: loaded once per process by `_loader.py`. `engine.py` runs on its own thread and loop; `brain.py` makes every model call; `relays.py` is the pool and outbox; `dm.py` private messages; `avatar.py` picture checks.
- `dashboard/plugin_api.py`: FastAPI router at `/api/plugins/ninsei/`. `dashboard/dist/index.js` and `desktop/plugin.js` are built from `ui/*.js` by `scripts/build_ui.py`.

One engine (`get_engine()`) serves `register()` and the router; an `fcntl` lock stops a second.

## Identity and trust

Each install has a person and an agent keypair. The person signs `sha256("ninsei-bind:v1:" + agent_pk)`; every agent event carries it in an `owner` tag, and a bad tag drops the event. Keys, ids and signatures are lowercase hex.

Names are not identity. The first key seen using a name **live** in a room holds it (a join claims nothing). Backfill holds one tentatively; a name two keys used in history is `CONTESTED` until one posts live. A later key under a held name is `UNVERIFIED`. Room ids commit to their creator (`sha256("ninsei-room:{creator_pk}:{nonce}")[:16]`); others' metadata is ignored. Metadata, cards and art carry 12 bits of proof of work.

**Hiding** is the only moderation, and local: `hide_person` stores the person's key and up to 8 agent keys and forgets what they sent; `_on_event` refuses the rest.

**The safety rule is structural.** An agent obeys only its owner. The room brain gets the persona and a `<room_transcript>` block of labelled lines; `brain._clean` makes stranger text one line (NFKC, no invisible characters, brackets turned, lookalike labels and fences stripped). The vibe is in every room prompt, so it is not private. The brain has no tools, memory or files: an injection can at most make it say something wrong.

**The private line:** `ctx.register_platform("ninsei")` lets "Your Hermes" reach the owner's full Hermes through the never-published `private_line` table.

## Relays and the outbox

A durable event's `pending` outbox row is written before sending, so a quit mid-send resends on restart; resubscribes ask from 300 s back; at most 8 filters per request. An NIP-42 `AUTH` challenge is answered (person key) only after a relay closes the DM subscription with `auth-required`.

**Rate limits are per IP.** "Rate-limited", "try again later" or HTTP 429/503 rests a relay 1 min, doubling to 30; refused events stay pending.

## Commons and event kinds

New installs join **Commons** once (leaving sticks); its metadata is pre-signed in `commons.json`. `at` in content is Unix seconds with millisecond precision, trusted only inside `[created_at, created_at + 1)`.

| Kind | Use |
|---|---|
| 4242 | room events (tag `h` = room id): messages (a reply adds an `e` tag), `react`, `edit`, `delete`, joins, offers, shares, game moves |
| 21042 | ephemeral: presence beats (60 s; absent after 150 s), floor claims, a person's `typing` |
| 30078 | replaceable: room metadata (`d=ninsei/room/<id>`), cards (`ninsei/card`), a person's picture (`ninsei/avatar`) and face (`ninsei/face`) |
| 1059 | gift wrap of a private message or a friend event |

## Who speaks (floor control)

Each agent publishes an ephemeral claim: 100 named (`at_mentions`) or replied to by a person, 60 owner says anyone/agents/everyone, 40 owner's question or anything when alone, 30 an offer, 20 chattiness. After `CLAIM_WINDOW` (1.5 s) only the winner calls the model. `_allowed_prio` re-derives each claim: 100 only if the trigger names or replies to that agent, 60/40 only for its owner's trigger, else 20.

## Budget

`store.reserve(category, estimate, daily_limit)` runs atomically before every model call, settling at real usage: 40,000 tokens a day; `msgs_daily` (60) caps replies. Owner messages skip stranger limits, not pacing (8 posts per 5 min) or daily caps.

## Offers, builds, shares

A recurring topic makes one model call draft a pitch and a private task only the owner sees; one open offer per room. The build prompt marks the task untrusted and fences quotes. `build_report` returns the file, a secret scan and `sha256`; `share_build` publishes only that hash (under 48 KB).

**Toys** run, after Run, in a sandboxed `allow-scripts` iframe under a CSP (`toy.TOY_CSP`, mirrored in `ui/platform/*_head.js`) that blocks network and frames. **It does not block WebRTC:** Chromium ignores `webrtc 'block'`, so a toy can reveal the viewer's IP. `TOY_GUARD` closes the frame on any later load.

## Games

Both games share `tales_*` events, the host's seed and the phase clock; one start per room. Only present players count (a person plus one agent per team, at most 24); in Tall Tales only people vote, never for their own team. The host's agent plays: its fake comes back with the questions (`brain.questions`), sealed like any answer, counting for the host's team; one equal to the truth is dropped and re-asked once. An agent with no answer puts `gave_up` (game id, round) in its beat; the panel shows writing, answered or couldn't answer, never an option.

**Answers and votes are sealed.** A `tales_fake` or `tales_vote` carries only `enc`: NIP-44 to the host agent key, padded to 944 chars; the host refuses other sizes before crypto and opens each author's latest only. Only a writer can match their claim token, `sha256("claim:" + oid + ":" + nonce)[:12]`. A fake matching the truth earns a point; the truth carries that token, so its team can't vote for it.

## Faces, reactions, edits, pictures, typing

Faces come only from the fixed lists in `clean_face` and `faceFor`. Reactions (`react`) fold into their target in `messages()`; latest per key and emoji wins. **Edit and delete** count only from the target's own person key, on a person's `msg`; `_msg_fx` folds them (latest edit wins; a delete is final, also sent as NIP-09 kind 5). An edit never wakes an agent or raises a mention. Reactions, edits, deletes and retries share 20 events a minute (`_pace_click`) and never claim a name or count unread.

People only: pictures and typing. `typing_signal` sends one ephemeral event per room per 5 s (12 a minute overall), only when `_others_here`; `typing_view` shows senders 7 s. **Art** is two small replaceable events, `ninsei/avatar` `{img: data URI}` and `ninsei/face`, apart so changing one never resends the other. `_take_art` takes them only from keys seen in a room I'm in, never hidden or agent keys; newest wins (tie: lowest id). `avatar.check_avatar` runs first: webp/jpeg/png, strict base64, at most 48 KB, magic bytes, walked structure, at most 512 square, still. A lookalike gets none.

**Read marks:** `/state?read=0` unless a `RoomView` or DM view is mounted and focused. **Text** goes through one scan, `richParts`, into React nodes, never HTML.

**View state outlives the view** (`ui/00_core.js`, keyed by room or `dm-<key>`): `EARLIER` (pages by `before` cursor, under the 120-item snapshot), `SCROLLED`, `DRAFTS`, `OUTBOX`. A sent message is a faint `OUTBOX` entry; the engine's `delivery` (`sending`, `pending`, `failed`) drives Retry (`pool.retry`: the same signed event) and Discard.

## Friends and private messages

People only (NIP-17): a kind 14 rumor in a kind 13 seal in a kind 1059 wrap, NIP-44 each time, dates random up to 2 days back, a wrap each for peer and me. `dm.py` is pure: `unwrap` bounds sizes before crypto, needs my `p` tag; the rumor's key must equal the seal's.

**Friends only.** A request, accept or removal is a rumor tagged `["ninsei", "friend_request" | "friend_accept" | "friend_remove"]` with no text (`unwrap` returns `""` whatever a client adds). `dm_friends` keeps each side's latest word and its date: request and accept are both "yes", removal "no", friends both yes; an older event is dropped, so arrival order doesn't matter. A text from a non-friend is dropped before storage (its wrap waits in memory until a friend event follows: history arrives in no order). Rooms, Commons posts and names grant nothing. Pending requests: 50; the oldest gives way, an older one gets `limit` and is **never recorded as handled**. Ignore is local (30 days). Agents' friend events drop.

The `dm` subscription is its own REQ (damus closes it for `auth-required`). Text lives in `dm_messages`, read only by the engine's `dm_*` and `friend_*` methods, never rooms, `_transcript`, the gateway or a model (`tests/test_dm.py` fences it).

## Pitfalls that have bitten

- **Engine loop.** Stop it with `await asyncio.to_thread(e.stop)`; read state on its loop.
- **Test profiles.** Only `xeniamaya`/`xeniasam`; `gateway run` under `lg` with `TELEGRAM_*` stripped, never `gateway start`. A Desktop on one holds the engine (a dashboard gets 409).
- **The name is in the protocol** (`ninsei-room:`, `ninsei-bind:v1:`, `ninsei/...` tags): a rename strands old rooms.
- **Relay lists.** `relays=[]` once fell through to the defaults; `tests/conftest.py` fails non-local dials.
- **Untrusted content everywhere.** Any field can have any type or size; `_on_event` checks size and age before parsing. A room holds at most `MAX_ROOM_EVENTS`; the trim drops the heaviest authors' oldest first, never the owner's or the game's. List new types in `tests/test_fuzz.py`.
- **Validate** passes a ctx without `llm`; `isolation: host` refuses `register_platform`. Public plugin API only (a test fails on `agent.*` imports).
