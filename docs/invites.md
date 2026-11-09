# Invites and the small social fixes (spec, 2026-11-09)

Scope picked by Justin on 2026-11-09: in-app invites to friends, codes that carry their relays, a Join preview,
a web invite page on goodmachines.ai, and three small fixes. Private (encrypted) rooms are out of scope: see
`docs/private-rooms.md`.

Ninsei's rules hold throughout: nothing a stranger sends carries free text into an invite; agents never see,
send or answer an invite; every new incoming shape is size-checked first and listed in `tests/test_fuzz.py`;
no route awaits a model call.

## 1. Codes carry relays

Today a code names the room, not where it lives, so a code from someone on other relays finds nothing.

- **Format.** `ninsei:<room>` stays valid. A code may add up to 3 relay hosts: `ninsei:<room>@nos.lol,relay.damus.io`.
  A message link becomes `ninsei:<room>@hosts#<event>`. Hosts are written without `wss://`; `wss://` is implied.
  Each host: lowercase, `[a-z0-9.-]` labels with an optional `:port`, at most 253 characters, at least one dot,
  no IP literals and no `localhost` (a code is pasted from anywhere; it must not aim your install at your own
  network). Anything that fails is dropped silently; a code with only bad hosts still joins by id.
- `parse_room_link` returns `(room, event, relays)`, relays as `wss://` URLs. Every caller is updated;
  `join_room` keeps ignoring what it doesn't need.
- **Share code** (room header, and the empty-room note) copies the code with up to 3 of my relays: the ones the
  room's metadata or recent history came from when known, else the first 3 of my relay list. Copy link to
  message carries the same hosts.
- **Adding a relay is never silent.** Connecting to a relay shows it your IP address. A code's hosts that I
  don't already use are shown in the Join preview (section 2) as "Also on: host, host" with a button **Add and
  look again**, which adds them to my relay list (the same setting as Settings, Relays) and repeats the preview.
  Nothing connects to a code's relays before that press.

## 2. Join preview

The Join dialog (Join by code, a pasted or clicked link to an unjoined room, an invite's Join) first shows what
the room is, then a Join button.

- Engine: `room_preview(code)` queries my relays (no join, no subscription, no publish) for the room's metadata
  (creator-signed, the same check as `_room_meta_from`) and its activity (`_room_activity`). Returns
  `{id, found, name, about, interests, msgs, talkers, last, joined, unknown_relays}`. `unknown_relays` lists the
  code's hosts not in my relay list. Cooldown: one query per room per 5 s; a repeat inside it returns the last
  answer.
- Route: `GET /rooms/preview?code=...`. Must return inside Desktop's 30 s bridge limit (query timeouts 4-6 s).
- UI: the dialog shows name, about, interest chips, and one activity line ("4 people talked today · last message
  12 min ago", or "Quiet lately"). No names of people: names in an unjoined room's history aren't checked yet.
  `found: false` says "Nothing on your relays for this code" plus the "Also on" row when the code has hosts.
  Already joined: the button reads **Open**.

## 3. Invite a friend

- **Protocol.** An invite is a NIP-17 rumor like a friend event: kind 14, EMPTY content, tags
  `["p", friend]`, `["ninsei", "room_invite"]`, `["h", <room id>]` and up to 3 `["relay", "wss://host"]`.
  `dm.py` adds `ROOM_INVITE` (not part of `FRIEND_TYPES`, so the friend-state machine never sees it) and
  `unwrap` returns `type = ROOM_INVITE` with `room` and `relays` validated there: room id 16-24 lowercase hex,
  relays by the section 1 host rules. Anything else in the tags is ignored; anything malformed is GARBAGE.
- **Who can invite.** Friends only, both ways yes, at arrival (live) or, read from history, dated after the
  friendship began (the same rules `_dm_process` applies to a text). From anyone else it is dropped and
  recorded handled. Hidden people's are dropped. An agent key's is dropped. My own copy from another install
  is recorded as "sent" there.
- **Sending.** `room_invite(room, friends)`: room must be one I'm in; 1-10 friends a call; each friend is two
  wraps (theirs and my copy, the existing `_dm_publish`), and each counts against `DM_SEND_PER_MIN`. Route
  `POST /rooms/invite {room, friends: [pk]}` returns `{sent: n}`.
- **Storing.** A small `invites` table (or kv): `(from_pk, room, relays, at, status)` with status
  `new | joined | ignored`. Latest per (from, room) wins. At most 50 kept; at the cap the oldest non-new go
  first, then the oldest. Ignore is local and silent. Joining the room (any way) marks its invites `joined`.
  Unfriending someone drops their `new` invites. Hiding drops all of theirs.
- **Room name.** An invite carries no name. The receiver looks the name up from the room's creator-signed
  metadata on its own relays (the cached Lobby, else a query) and shows "a room" until it is found. Lookups are
  limited to 3 a minute in all, whoever the invites are from; the rooms waiting go in one query, and a room whose
  invite is gone is not asked about. When the inviter made the room, the name shown is their own words: what they
  typed as the room's name, cut to 32 characters with invisible characters removed. Nothing else they chose is
  shown, only who they are; a room made by someone I hid shows "a room".
- **UI.**
  - Room header: **Invite** next to Share code. A dialog lists my friends (checkboxes, a filter box past 8),
    and below it **Copy invite link** (section 4). Friends already in the room show "in this room" and no box.
  - Receiving: a toast "Kit invited you to demoscene" (one per 30 s per sender; several at once make
    "3 room invites"), a desktop notification under the same rules as friend requests, an **Invites** group in
    the sidebar's Direct messages section (like Requests) with **Join** (opens the Join preview) and **Ignore**,
    and a system line in the conversation with that friend: "Kit invited you to demoscene. Join".
  - Sender side: a system line in the conversation, "You invited Kit to demoscene".
- **Small fixes that share this plumbing:** **Invite to a room** on a friend's card and in a conversation's
  header (pick one of my rooms; same route).

## 4. Web invite link

- `https://goodmachines.ai/ninsei/join#<room>@<hosts>` (the part after `#` never reaches the server).
- A static page in the Good Machines site repo (`~/Developer/brand/good-machines/site/ninsei/join.html`) styled
  as the Ninsei brand (Black Ice). It reads the hash, validates it with the same rules (room 16-24 hex, hosts),
  and shows: "You've been invited to a room on Ninsei", the code with **Copy code**, the install command, and
  "Already have Ninsei? Open it, press Join by code, and paste." No relay connection from the page in this
  round (it would show visitors' IPs to relays they never chose), so it shows no room name. Bad or empty hash:
  a plain "This invite link is incomplete" with the install steps.
- **Copy invite link** builds it from the same code Share code makes.
- Deploying that site is outward-facing: it is built and checked locally, and deployed only after Justin's go.

## 5. Other small fixes

- **Someone joined your room.** In a room I created, a person's live `join` (not history, not an agent, not me,
  not a hidden person) shows a toast "Sam joined shader sketchbook"; several inside 30 s make "3 people joined
  shader sketchbook". Off when the room is muted. Never a desktop notification.
- **Rejoin a room you left.** `leave_room` remembers the last 5 left rooms locally (id, name, relays as a code).
  Cmd+K lists them as "Rejoin <name>" after the live matches; picking one opens the Join preview. Joining it
  again removes it from the list. "Forget" is not needed (the list is 5 long and local).

## Tests and docs

- Engine and dm tests for every rule above, including: a stranger's invite dropped; a pre-friendship invite read
  from history dropped; an agent key's dropped; a hidden person's dropped and their stored invites deleted;
  oversized/malformed tags (bad room id, 4 relays, IP literal, localhost, `ws://`) never stored; the 50 cap;
  rate limit shared with DMs; a code with hosts parses, a bad host is dropped; preview never publishes or
  subscribes; Add and look again changes the relay setting only on that call.
- `tests/test_fuzz.py` lists the new rumor shape. UI tests in the style of `tests/test_dm_ui.py`.
- README "How it works" (Rooms, Friends) and "What leaves your machine" (an invite is a private message to that
  friend, encrypted like one, carrying the room's id and up to 3 relay hosts). ARCHITECTURE "Friends and private
  messages" and "Room settings and links". `implementation-notes.md` gets a section.
