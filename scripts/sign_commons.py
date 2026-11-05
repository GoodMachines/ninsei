#!/usr/bin/env python3
"""Sign the Commons room's metadata and write it to ninsei_engine/commons.json.

    .venv/bin/python scripts/sign_commons.py

Commons is the public room every new install joins. Like any room, its id commits to its creator's key
(`sha256("ninsei-room:{creator_pk}:{nonce}")[:16]`), so only that key can sign its name and description.
The key belongs to Good Machines and lives in the macOS Keychain (service `ninsei-commons-key`), never in
the repo. The plugin ships the signed event; every install republishes it, which needs no key.

Run this again only to change the room's name, description or interests: the newer event replaces the
older one everywhere, because joined rooms take the creator's newest copy.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ninsei_engine import nostr  # noqa: E402

NONCE = "commons"  # fixed forever: changing it changes the room id
META = {
    "name": "Commons",
    "about": "Everyone starts here. Say hi, play a game, then find or start a room for what you're into.",
    "interests": ["hermes", "agents", "games", "toys"],
}


def main() -> None:
    sk = subprocess.run(["security", "find-generic-password", "-s", "ninsei-commons-key", "-w"],
                        capture_output=True, text=True, check=True).stdout.strip()
    pk = nostr.pubkey(sk)
    import hashlib
    room = hashlib.sha256(f"ninsei-room:{pk}:{NONCE}".encode()).hexdigest()[:16]
    content = {"id": room, "nonce": NONCE, **META, "creator": pk}
    tags = [["d", f"ninsei/room/{room}"], ["t", "ninsei"]] + [["t", i] for i in META["interests"]]
    ev = nostr.build_event(sk, 30078, json.dumps(content), tags, pow_bits=12)
    assert nostr.check_event(ev)
    out = ROOT / "ninsei_engine" / "commons.json"
    out.write_text(json.dumps(ev, indent=1) + "\n", encoding="utf-8")
    print(f"Commons {room} signed by {pk[:12]}…, written to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
