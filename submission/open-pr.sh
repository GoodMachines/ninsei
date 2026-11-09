#!/usr/bin/env bash
# Opens the catalog PR once the demo video is on X:  submission/open-pr.sh https://x.com/<you>/status/<id> [--dry-run]
# Fills the video link into catalog-pr.md, requires check_submission.py to say "ready" and Hermes's catalog
# validator to pass, commits and pushes that, then adds plugin-catalog/ninsei.yaml on a branch of your fork of
# NousResearch/hermes-agent (through the API, no clone) and opens the PR. --dry-run checks everything on a copy
# and changes nothing, here or on GitHub.
set -euo pipefail
cd "$(dirname "$0")/.."
URL="${1:-}"; DRY="${2:-}"
UPSTREAM=NousResearch/hermes-agent
BRANCH=add-ninsei
TITLE="feat(plugin-catalog): add ninsei plugin"
VALIDATOR="$HOME/.hermes/hermes-agent/scripts/validate_plugin_catalog.py"
VPY="$HOME/.hermes/hermes-agent/.venv/bin/python"

[[ "$URL" =~ ^https://(x|twitter)\.com/[A-Za-z0-9_]{1,15}/status/[0-9]{5,25}$ ]] || { echo "usage: $0 https://x.com/<you>/status/<id> [--dry-run]"; exit 2; }
[[ -z "$DRY" || "$DRY" == "--dry-run" ]] || { echo "unknown option: $DRY"; exit 2; }
grep -q '<link>' submission/catalog-pr.md || { echo "catalog-pr.md has no <link> left: already filled?"; exit 1; }
[[ -z "$(git status --porcelain -- submission plugin.yaml)" ]] || { echo "commit or discard changes under submission/ first"; exit 1; }

WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
sed "s|<link>|$URL|" submission/catalog-pr.md > "$WORK/catalog-pr.md"

# the same checks as scripts/check_submission.py, on the filled-in copy
.venv/bin/python - "$WORK/catalog-pr.md" <<'EOF'
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
import check_submission as cs
found = cs.problems(Path("submission/ninsei.yaml").read_text(), Path(sys.argv[1]).read_text())
print("\n".join("NOT READY: " + p for p in found) or "ready")
sys.exit(1 if found else 0)
EOF
"$VPY" -I "$VALIDATOR" submission/ninsei.yaml
SHA=$(sed -n 's/^sha: "\([0-9a-f]\{40\}\)".*/\1/p' submission/ninsei.yaml)
git merge-base --is-ancestor "$SHA" origin/main || { echo "pinned sha $SHA is not on origin/main"; exit 1; }
ME=$(gh api user --jq .login)
cp "$WORK/catalog-pr.md" "$WORK/body.md"   # the PR text exactly as catalog-pr.md has it, no tool credit

if [[ "$DRY" == "--dry-run" ]]; then
  echo "dry run OK: would commit the link, fork $UPSTREAM as $ME, put plugin-catalog/ninsei.yaml on $ME:$BRANCH, open \"$TITLE\""
  exit 0
fi

cp "$WORK/catalog-pr.md" submission/catalog-pr.md
git add submission/catalog-pr.md
git commit -q -m "Catalog PR text: the demo video link

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push -q origin main

gh repo view "$ME/hermes-agent" >/dev/null 2>&1 || gh repo fork "$UPSTREAM" --clone=false --default-branch-only
for i in $(seq 1 30); do gh api "repos/$ME/hermes-agent" >/dev/null 2>&1 && break; sleep 2; done
BASE=$(gh api "repos/$UPSTREAM/git/ref/heads/main" --jq .object.sha)
gh api -X POST "repos/$ME/hermes-agent/git/refs" -f ref="refs/heads/$BRANCH" -f sha="$BASE" >/dev/null 2>&1 \
  || gh api -X PATCH "repos/$ME/hermes-agent/git/refs/heads/$BRANCH" -f sha="$BASE" -F force=true >/dev/null
gh api -X PUT "repos/$ME/hermes-agent/contents/plugin-catalog/ninsei.yaml" -f branch="$BRANCH" \
  -f message="feat(plugin-catalog): add ninsei plugin" -f content="$(base64 < submission/ninsei.yaml | tr -d '\n')" >/dev/null
PR=$(gh pr create -R "$UPSTREAM" --head "$ME:$BRANCH" --base main --title "$TITLE" --body-file "$WORK/body.md")
echo "PR: $PR"
echo "X:  $URL"
echo "Form: https://form.typeform.com/to/FwJLvOln  (paste both links)"
