# Private rooms: design

Status: proposed 2026-11-11, not built. Target version 0.3.0.

## What a private room is

Justin's definition: no one can enter the room or read from it without being invited, and the room shows up only
for the people in it.

A private room is a room whose events are encrypted with a key that only its members hold. It lives on the same
public relays as every other room, so nobody hosts anything.

## What it protects, and what it does not

| | Public room today | Private room |
|---|---|---|
| Message text, names, reactions, edits, shares, game moves | Anyone can read | Members only |
| Room name and description | In the Lobby and "Browse all" | Members only; never listed |
| Posting into the room | Anyone with the id | Members only: an event that does not decrypt is dropped |
| Joining | Anyone with the code | Invited people only |

Still visible to someone watching the relays:

- that events exist under one opaque room tag, and their sizes and times;
- which keys sign them. A person's key links to their public card, so a watcher can learn that two people share a
  private room and when they are active in it, but nothing they say;
- which agent belongs to which person (the `owner` tag, public today).

Limits of a shared key:

- A member can pass the key on. Invite rules are enforced by honest clients only.
- No removal in version one. Someone who should no longer read the room keeps the key; the fix is a new room.
- A new member can read the history still on the relays (3 days is what Ninsei fetches).
- If the key leaks, everything still on the relays can be read.

Members cannot forge each other: every event is still signed by its author's own key.

## How it works

**Key.** `create_room(private=True)` makes 32 random bytes. The room id is made as today
(`room_id_for(creator, nonce)`), so members can still check that a rename comes from the creator. The key is kept
in the room's local row in `ninsei.db`, next to the messages, which are plain text there already.

**Events.** Kinds, tags and signatures do not change. Only `content` does: the JSON that `_publish_room` builds is
encrypted with NIP-44 (`nip44.encrypt`, already used for private messages) under a key derived from the room key
and the room id. Every room event already goes out through `_publish_room` and comes in through `_on_event`, so the
change sits in those two places:

- out: encrypt when the room has a key;
- in: decrypt when the room has a key; drop the event if that fails. Plain text posted under a private room's tag
  never shows.

Presence beats, typing and floor claims (kind 21042) are encrypted the same way. Size limits that apply to
`content` today apply to the decrypted text, after a cap on the ciphertext. The largest event, a 48 KB share,
encrypts to about 87 KB, under the 128 KB message limit of the strictest default relay.

**Metadata.** The room's kind-30078 event keeps `d=ninsei/room/<id>` and has encrypted content and no `t` tags.
The Lobby and "Browse all" query by `t`, so they never receive it. A client without the key, or an older client,
fails the creator check on it and shows nothing.

**Invites.** A private invite is the existing room invite (a gift-wrapped rumor to a friend, with the room id and
up to 3 relay hosts) plus a `key` tag, under a new mark, `private_invite`. Older clients reject an unknown mark, so
an invite to someone on 0.2.x is dropped on their side and never opens a room they cannot read. Invites still
carry no words: the invited person's client uses the key to read the room's name from its metadata.

- Friends only, as today.
- Any member can invite, as in public rooms.
- My own copy of the invite carries the key, so my second install can join.

**No codes.** A private room has no shareable code. "Copy code" is hidden there, and pasting its id into Join
finds nothing.

**Agents.** Agents are in by default (Justin, 2026-11-11). An agent runs on its owner's install and uses the same
room key. Its replies are encrypted like any other event. What a member's agent reads goes to that member's model
provider, as in public rooms; the create and join screens say so in one line. The existing per-room agent controls
apply.

## Hosting

None is needed for privacy. A private room uses its creator's relays at the time of the invite, like a public one.

Delivery is a separate problem. On 2026-11-11 two of the five default relays were down and two more did not
acknowledge writes (see implementation-notes.md). Options, cheapest first:

1. Replace the dead defaults with relays that answer. No cost.
2. Let a creator name their own relay for a room. Invites already carry relay hosts.
3. Run a Good Machines relay. This has a monthly cost and needs Justin's yes on a number.

## Open decisions

1. **Removal.** Version one has none. Adding it later means the creator sends a new key to everyone who stays.
2. **Hiding who is in the room from relay watchers.** Possible by signing the outer event with a throwaway key and
   putting the real signature inside. It costs more code and breaks relay-side deletes. Not in version one unless
   Justin wants it.

## Build order

1. Engine: key, encrypt and decrypt, private metadata, private invite, tests (an outsider cannot read or post, an
   old client drops the invite, the Lobby never lists the room, limits hold on decrypted text).
2. UI: a Private switch on Create, a lock on the room, invite from the room, no code sharing.
3. README, ARCHITECTURE.md, then a live check on the test seats and across two networks.
