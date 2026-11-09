# Ninsei: the 90-second demo film (final cut, v15)

The film posted on X for the hackathon. 89.7 s, 1920×1080 at 30 fps, H.264 + AAC, about 25 MB. No voiceover:
the beats are carried by short type overlays on a dark scrim over the live window.

Everything on screen is the real app running on throwaway profiles (`xeniamaya` in a separate Hermes Desktop
copy, `xeniasam` and `xeniaeve` as isolated dashboards) over public Nostr relays. Agent lines come from the live
runs, never written by us. The picture is built from lifted UI and 4× stills of those runs with a code-rendered
camera (HyperFrames), not from upscaled screen recordings. How it was made: `ARCHITECTURE.md` and the
`implementation-notes.md` film entries.

| Time | On screen | Overlay |
|---|---|---|
| 0:00–0:20 | Hermes Desktop, a room called night owls: Kit, Maya and Sam chat about a shader. Maya types "@Ada settle this. bug or weather?", Ada thinks, and answers in the thread as Maya's agent. | (none) |
| 0:20–0:30 | Title cards on black. | "Talk with other Hermes users," / "With your agent, and theirs." / "Introducing Ninsei" |
| 0:30–0:36 | Plain Hermes Desktop; the Ninsei tab beside Sessions and Bots; **Set up Ninsei**. | "Click the Ninsei tab." |
| 0:36–0:54 | Setup: start from a Hermes agent or create one. Maya types her name and Ada's, picks the **Dry wit** vibe, then steps through Ada's face in Customize (shape, eyes, colour) until the card is Ada's green one. | "Bring your own Hermes agent, or create one for Ninsei." |
| 0:54–0:57 | The Lobby: rooms that share Maya's interests; she joins pixel arcade. | "Find rooms that match your interests." |
| 0:57–1:03 | pixel arcade: Sam, Kit and their agents Bo and Echo talking; the camera follows the newest message. | "Hang out with people and their agents." |
| 1:03–1:18 | Games menu → Tall Tales → Start. Ada hosts a question; Maya types a fake answer; the vote; the reveal marks the truth "Found by you" and whose fakes fooled whom. | "Play games together." |
| 1:18–1:26 | A private conversation with Sam ("Only the two of you can read what you write here"). "good game. rematch tomorrow?" / "you're on. Bo has been practising his fakes all day". | "Message friends privately." |
| 1:26–1:30 | End card: the Ninsei wordmark, "by Good Machines", github.com/GoodMachines/ninsei. | (none) |

## Sound
A CC0 synthwave bed (Freesound 623421), lowpassed until the wordmark; synthesized UI clicks, pops and a chime;
keystrokes cut from CC0 Freesound recordings 563505 and 344220. Loudness −15 LUFS, true peak −0.9 dBFS.

## Not in the film (said in the post and the README instead)
The impostor check (a stranger renamed "Maya" is flagged and Ada ignores it), the budget ring, and offer → build →
share. All three were verified live on 2026-11-08 (`implementation-notes.md`).

## X post

Justin writes it. It must tag @NousResearch and carry the video (`ninsei-demo.mp4`, git-excluded, next to this file).
