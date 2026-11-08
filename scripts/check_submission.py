"""Is the catalog submission ready to open? Run this before the catalog PR goes out.

    python scripts/check_submission.py [--yaml submission/ninsei.yaml] [--pr submission/catalog-pr.md]

Hermes's own catalog validator accepts the all-zeros placeholder sha and never looks inside image URLs, so
it says OK on a draft. This check fails until the entry is really pinned:
- `sha` is 40 lowercase hex, not a placeholder, a commit in this repo, and already on origin/main;
- every raw.githubusercontent.com link in both files uses that sha, and the file exists at that commit;
  the one exception is screenshots under `catalog/`, which live on the orphan `media` branch so they never ship
  in an install (the scanner counts the whole tree): those pin to a full commit on origin/media instead;
- no `<sha>`, `<link>`, `TODO` or draft header is left in either file.
Exit 0 when ready, 1 with one line per problem otherwise.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = re.compile(r"https://raw\.githubusercontent\.com/GoodMachines/ninsei/([^/\s]+)/([^\s)\"'>]+)")
LEFTOVERS = ("<sha>", "<link>", "TODO", "DRAFT", "NOT submitted")


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


def problems(yaml_text: str, pr_text: str) -> list[str]:
    out = []
    m = re.search(r"^sha:\s*[\"']?([^\"'\s#]*)", yaml_text, re.M)
    sha = m.group(1) if m else ""
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        out.append(f"sha {sha!r} is not 40 lowercase hex characters")
    elif set(sha) == {"0"}:
        out.append("sha is still the all-zeros placeholder")
    elif git("cat-file", "-e", f"{sha}^{{commit}}").returncode:
        out.append(f"sha {sha} is not a commit in this repo")
    elif git("merge-base", "--is-ancestor", sha, "origin/main").returncode:
        out.append(f"sha {sha} is not on origin/main (push it first)")
    sha_ok = not out
    for name, text in (("ninsei.yaml", yaml_text), ("catalog-pr.md", pr_text)):
        for word in LEFTOVERS:
            if word in text:
                out.append(f"{name} still contains {word!r}")
        for ref, path in RAW.findall(text):
            if path.startswith("catalog/"):
                if not re.fullmatch(r"[0-9a-f]{40}", ref):
                    out.append(f"{name}: {path} is pinned to {ref!r}, not a full media commit")
                elif git("merge-base", "--is-ancestor", ref, "origin/media").returncode:
                    out.append(f"{name}: {path} is pinned to {ref[:12]}, which is not on origin/media")
                elif git("cat-file", "-e", f"{ref}:{path}").returncode:
                    out.append(f"{name}: {path} does not exist at {ref[:12]}")
            elif ref != sha:
                out.append(f"{name}: {path} is pinned to {ref!r}, not the sha")
            elif sha_ok and git("cat-file", "-e", f"{sha}:{path}").returncode:
                out.append(f"{name}: {path} does not exist at {sha[:12]}")
    if sha and f"pinned at `{sha}`" not in pr_text:
        out.append("catalog-pr.md does not say it is pinned at the sha")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--yaml", default=str(ROOT / "submission/ninsei.yaml"))
    ap.add_argument("--pr", default=str(ROOT / "submission/catalog-pr.md"))
    a = ap.parse_args()
    found = problems(Path(a.yaml).read_text(), Path(a.pr).read_text())
    for p in found:
        print("NOT READY: " + p)
    if not found:
        print("ready: sha pinned, every link resolves at it, no placeholders left")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
