"""An agent's "X's agent" caption carries its owner's "not verified" flag.

Found filming the demo (2026-11-08): a seat renamed itself "Maya". Its own row in the member list said "not verified",
but its agent's caption under it read "Maya's agent", plain. Every caption now goes through ownerLabel() in
ui/00_core.js, and the source check below fails if a new one is built by hand."""
import re
from pathlib import Path

from test_audit_ui import CORE, ROOM, fn, needs_node, run

ROOT = Path(__file__).resolve().parents[1]
HELPER = fn(CORE, "ownerLabel")


def test_no_ui_file_builds_an_owner_caption_by_hand():
    found = []
    for f in sorted((ROOT / "ui").glob("*.js")):
        if f.name == "05_media.js":
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("//", 1)[0] if not line.lstrip().startswith("//") else ""
            if re.search(r"""['’]s agent['"]""", code) and "function ownerLabel" not in code and "curly ?" not in code:
                found.append(f"{f.name}:{i}: {line.strip()[:120]}")
    assert not found, "build \"X's agent\" with ownerLabel(name, flagged) so a lookalike owner stays flagged:\n" + "\n".join(found)


@needs_node
def test_owner_label_flags_a_lookalike_owner():
    r = run(HELPER + """
out([ownerLabel('Maya', false), ownerLabel('Maya', true), ownerLabel('Maya', true, true), ownerLabel('', false)])""")
    assert r == ["Maya's agent", "Maya (not verified)'s agent", "Maya (not verified)’s agent", "someone's agent"]


@needs_node
def test_the_mention_picker_flags_the_agent_of_a_lookalike():
    r = run(HELPER + "const isHere = p => !!p.here\n" + fn(ROOM, "mentionCandidates") + """
const room = { members: [
  { pk: 'p1', name: 'Maya', you: true, agents: [{ pk: 'a1', name: 'Ada', yours: true }] },
  { pk: 'p2', name: 'Maya', impostor: true, agents: [{ pk: 'a2', name: 'Echo' }] },
  { pk: 'p3', name: 'Sam', agents: [{ pk: 'a3', name: 'Bo' }] }
] }
out(mentionCandidates(room).map(c => c.name + ' / ' + c.sub))""")
    assert "Echo / Maya (not verified)’s agent" in r
    assert "Bo / Sam’s agent" in r
    assert "Ada / your agent" in r


def test_the_member_list_and_timeline_pass_the_flag():
    room = (ROOT / "ui/50_room.js").read_text(encoding="utf-8")
    assert "ownerLabel(p.name, !!p.impostor)" in fn(room, "Person")
    assert "ownerLabel(m.owner_name, !!(imp && imp.owner))" in room
