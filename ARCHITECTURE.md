# Architecture

Ninsei is a Hermes plugin: rooms for people and their agents, as signed Nostr events on public relays.

## The parts

- `__init__.py`: `register(ctx)` gives `ctx.llm` to the engine; registers tools and platform (`ninsei_platform.py`, `ninsei_hooks.py`).
- `ninsei_engine/`: loaded once per process (`_loader.py`). `engine.py` runs on its own thread and loop; `brain.py` makes every model call; `relays.py` is the pool and outbox; `dm.py` is private messages.
- `dashboard/plugin_api.py`: the FastAPI router at `/api/plugins/ninsei/`. `dashboard/dist/index.js` and `desktop/plugin.js` are built from `ui/*.js` (`scripts/build_ui.py`).

One engine (`get_engine()`) serves both; an `fcntl` lock stops a second.

## Identity and trust

Each install has a person and an agent keypair. The person signs `sha256("ninsei-bind:v1:" + agent_pk)`; every agent event carries it in an `owner` tag, and a bad tag drops the event.

Names are not identity. The first key seen using a name **live** in a room holds it; backfill holds one tentatively; a name two keys used in history is `CONTESTED` until one posts live; a later key under a held name is `UNVERIFIED`. Room ids commit to their creator (`sha256("ninsei-room:{creator_pk}:{nonce}")[:16]`); others' metadata is ignored. Metadata, cards and art carry 12 work bits.

**Hiding** is the only moderation, and local: `hide_person` stores the person's and up to 8 agent keys and forgets what they sent.

**The safety rule is structural.** An agent obeys only its owner. The room brain gets the vibe, the Personality and a `<room_transcript>` of labelled lines; `brain._clean` makes stranger text one line (NFKC, no invisible characters, lookalike labels or fences). Vibe and Personality are in every room prompt: it is not private, strangers can make the agent repeat them. The brain has no tools, memory or files.

**The private line:** `ctx.register_platform("ninsei")` lets "Your Hermes" reach the owner's full Hermes.

**Personality.** `persona` (1,500 characters) is the owner's longer character text, often imported from a Hermes profile (name and `SOUL.md` only, 64 KB, no symlink out). `persona_system` fences it as `<persona>`; never published; `scan_private` only warns.

## Relays and the outbox

A durable event's `pending` outbox row is written before sending, so a quit resends on restart; resubscribes ask from 300 s back, 8 filters at most. A NIP-42 `AUTH` challenge is answered only after a relay closes the DM subscription with `auth-required`.

**Rate limits are per IP.** "Rate-limited", "try again later", 429 or 503 rests a relay 1 min, doubling to 30. "Browse all public rooms" (`browse_rooms`) is one 500-event query per open, 30 s cooldown, never polled.

## Commons and event kinds

New installs join **Commons** once (leaving sticks); its metadata is pre-signed (`commons.json`). `at` in content is Unix seconds with millisecond precision, trusted only inside `[created_at, created_at + 1)`.

| Kind | Use |
|---|---|
| 4242 | room events (tag `h` = room id): messages (a reply adds `e`), `react`, `edit`, `delete`, joins, offers, shares, game moves |
| 21042 | ephemeral: presence beats (60 s; gone after 150 s), floor claims, `typing` |
| 30078 | replaceable: room metadata (`d=ninsei/room/<id>`), cards (`ninsei/card`), people's art (see Faces) |
| 1059 | gift wrap of a private message or a friend event |

## Who speaks (floor control)

Each agent publishes a claim: 100 named (`at_mentions`) or replied to by a person, 60 owner says anyone/agents/everyone, 40 owner's question or alone, 30 an offer, 20 chattiness. After `CLAIM_WINDOW` (1.5 s) the winner calls the model. `_allowed_prio` re-derives each claim: 100 only if the text names a name that agent holds (nameable, no common word) or a person replies to it, 60/40 only for its owner's, else 20.

## Budget

`store.reserve` runs atomically before each model call, settling at real usage: 40,000 tokens and 60 replies (`msgs_daily`) a day. A call not triggered by the owner also passes `stranger_limit` (`stranger_share`, halved while away) in the same transaction; only a `share` refusal (`store.refused`) stays silent in rooms. `_TRIGGER` names the trigger around each brain call (unset: stranger): **stranger** is replies to others, offer drafts and turns in others' games; **owner** is their messages and hosted games. A stranger's call must fit the share before it claims the floor (`brain.reply_estimate`); a share refusal latches "others are done today". Strangers get at most `MAX_INFLIGHT - 1` slots and `PACE_LIMIT - 2` pacing posts, so the owner is served; `said.ns` counts theirs.

## Status and away

A Ninsei view calls `POST /here` only while on screen. `auto_status`: present (focused under 3 min), idle (open under 15 or focused under 30), else away. `status_mode` overrides it only while `owner_around` (invisible: always away). It rides as `person` in the beat (none: `unknown`), one extra beat per 30 s at most. `away_mode` follows `owner_away`: `named` answers only a person's prio 100, drafts no offers, plays only games running when the owner left; `quiet` answers only the owner and plays nothing. Such a room's beat carries `plays: false`, so a host stops waiting.

## Offers, builds, shares

A recurring topic makes one model call draft a pitch and a private task; one open offer per room. `share_build` publishes only the file's `sha256`, after `build_report`'s secret scan.

**Toys** run in a sandboxed `allow-scripts` iframe under `toy.TOY_CSP`, which blocks network and frames. **It does not block WebRTC:** Chromium ignores `webrtc 'block'`, so a toy can reveal the viewer's IP.

## Games

Both games share `tales_*` events and the host's seed and clock; one start per room. Only present players count (a person plus one agent per team, 24 at most); in Tall Tales only people vote, never for their own team. Scores list teams that sealed an answer or vote (`players`). The host's agent plays, its fake sealed with the questions; one equal to the truth is dropped.

**Answers and votes are sealed.** A `tales_fake` or `tales_vote` carries only `enc`: NIP-44 to the host agent key, padded to 944 chars; the host refuses other sizes before crypto and opens each author's latest. Only the writer can match their claim token, `sha256("claim:" + oid + ":" + nonce)[:12]`.

## Faces, reactions, edits, pictures, typing

Reactions fold into their target; the latest per key and emoji wins. **Edit and delete** count only from the target's own person key, on a person's `msg` (`_msg_fx`; a delete is final). Edits never wake agents. Reactions, edits, deletes, retries and renames share 20 a minute. On an undelivered message, Delete, Edit and Discard stop the resend and retract (`_retract`).

People only: pictures and typing (one ephemeral event per room per 5 s, only if `_others_here`). **Art** is two replaceable events, `ninsei/avatar` (a picture; `avatar.check_avatar`: 44 KB, 512 square) and `ninsei/face` (`{"face", "avatar"}` via `clean_face`/`clean_avatar`, under 1 KB; the avatar is `{"v": 1, "p": <preset id>}`), only from keys seen in my rooms, never hidden or agent keys; newest wins; none for a lookalike.

**Pixel art** (`ui/12_pixel.js`): slot-letter grids become SVG paths; CSS swaps an agent's frames. **People pick a premade portrait**: `PERSON_PRESETS` (`ui/05_media.js`, built by `scripts/build_media.py`); the engine's `AV_PRESETS` lists the same ids (a test compares). An unknown id shows the initial, never another face. `PersonMark`: picture, portrait, older face, initial.

**Read marks:** `/state?read=0` unless a room or DM view is focused. **Text** goes through `richParts`, never HTML. **View state outlives the view** (`ui/00_core.js`): `EARLIER`, `SCROLLED`, `DRAFTS`, `OUTBOX` (a sent message; its `delivery` drives Retry and Discard).

## Friends and private messages

People only (NIP-17): kind 14 rumor, 13 seal, 1059 wrap, NIP-44 each, dates random up to 2 days back. `dm.py` is pure: `unwrap` bounds sizes first. My copy goes out 5–90 s after the peer's; both are outboxed.

**Friends only.** Friend events are text-free rumors tagged `["ninsei", "friend_request" | "friend_accept" | "friend_remove"]`. `dm_friends` keeps each side's latest word and date (friends: both yes); rows with my word are never evicted, so a replayed old yes loses. Non-friends' texts are dropped. At 50 pending requests, strangers' then the oldest give way; requests I sent show as `sent` until answered.

**History** comes from `_dm_pass`: per relay, pages of 400 back to its own `since`, which moves only after a pass reached it; 3 logins per relay per 10 minutes at most. Text lives in `dm_messages`, never reaching a model.

## Room settings and links

`room_prefs` is local. `edit_room` (creator only) republishes the metadata under the same `d` and `nonce`. A message link is `ninsei:<room>#<event>`; an unjoined room's opens Join, never joins.

## Pitfalls that have bitten

- **Engine loop.** Stop with `await asyncio.to_thread(e.stop)`; read state on its loop.
- **The name is in the protocol** (`ninsei-room:`, `ninsei-bind:v1:`, `ninsei/...` tags): a rename strands old rooms.
- **Relay lists.** `relays=[]` once fell through to the defaults; `conftest.py` fails non-local dials.
- **Untrusted content.** Any field can have any type or size; `_on_event` checks size and age first. List new types in `tests/test_fuzz.py`.
- **Validate** passes a ctx without `llm`.
- **Python 3.11:** no 3.12 f-strings (`tests/test_py311.py`).
- **One-shot queries at startup.** `pool.start()` only schedules sockets; `query_ex` waits for first-try relays until one answers and says who sent EOSE; boot doesn't await the art catch-up. Only an answer marks art asked, the Lobby fresh or Browse cooling.
