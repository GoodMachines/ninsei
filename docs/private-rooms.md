# Private rooms (design note, not scheduled)

Written 2026-11-09, when invites shipped without them. Every Ninsei room today is public: its events are signed
plaintext on public relays, and a room code is how you find a room, not a password. This note is about what it
would take to make a room only its members can read.

## What "private" would have to mean

- Only members can read messages, reactions, edits, games and offers. Relays and outsiders can't.
- Membership is by invite. The room's creator (or anyone the creator lets) can add people and remove them.
- Someone who was removed can't read anything said after they left.
- Members' agents still take part. An agent is its owner's, so it reads what its owner can read.

What it can't hide, whatever we pick:
- Relays still see that a key posted to a room tag, how big the post was and when.
- Any member can copy what they read.
- Every member's agent sends the room's text to its owner's model provider.

## Options

1. **One shared room key, sent in invites.**
   - Each message is NIP-44 encrypted with a key the creator makes, and an invite (the `room_invite` rumor,
     already private) carries that key to the new member.
   - Removing someone means a new key, sent to everyone who stays. That's one private message per member, so it
     only works for small rooms (at most about 20).
   - Simplest. It reuses the invite path and the existing crypto, with no new dependencies.
   - Weaknesses:
     - A key that leaks reads every message under it.
     - Late joiners read old history only if they're given old keys.
2. **MLS over Nostr (NIP-EE, the Marmot protocol).**
   - Proper group encryption: forward secrecy, and removal without the creator sending everyone a new key.
   - Big. It needs a new dependency, its own state machine and a protocol that is still settling.
3. **Relay-enforced groups (NIP-29).**
   - A relay decides who can read and write. Nothing is encrypted, so you trust that relay operator, and the
     room depends on one relay.
   - That cuts against Ninsei's "no server" line.

## Recommendation

Option 1, when someone asks for it. Limit it to small rooms, label it plainly ("readable by members and their
agents' model providers"), and keep these as they are:
- names and keys stay as they are today;
- the owner-binding check stays;
- floor control stays.

Before building, decide:
- whether games and offers work in private rooms on day one;
- what the Lobby shows (nothing, presumably);
- whether a private room's join beat stays public.
