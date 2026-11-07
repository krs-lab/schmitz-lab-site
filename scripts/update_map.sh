#!/usr/bin/env bash
# Guided update of the collaborator map after adding a paper.
# Usage: ./scripts/update_map.sh
set -uo pipefail
cd "$(dirname "$0")/.."
PY=python3

confirm() { read -r -p "$1 [y/N] " a; [[ "$a" =~ ^[Yy]$ ]]; }

echo "Before you start: have you added the paper to content/publications/_index.md"
echo "with its PubMed link (pubmed.ncbi.nlm.nih.gov/<PMID>) and saved the file?"
confirm "Yes, continue" || { echo "Add the paper first, then re-run."; exit 0; }

echo; echo "=== STEP 1: dry run (nothing is saved) ==="
$PY scripts/update_collaborators.py || { echo "Script failed. Fix the error above."; exit 1; }
echo
echo "Check the '+' lines: right person, right institution, sensible coordinates."
echo "If something is unresolved or wrong, add it to scripts/inst_overrides.json"
echo "(valid JSON: no trailing comma after the last entry), then re-run this script."
confirm "Everything looks right. Save to people.json?" || { echo "Nothing saved."; exit 0; }

echo; echo "=== STEP 2: write (a backup goes to scripts/backups/) ==="
$PY scripts/update_collaborators.py --write || { echo "Write failed."; exit 1; }

echo; echo "=== STEP 3: check against PubMed ==="
echo "(Some NAME_NOT_FOUND / NO_AFFIL_DATA rows are normal for older entries.)"
$PY scripts/verify_people.py || true
echo; $PY scripts/audit_people.py

echo; echo "=== STEP 4: look at the map ==="
echo "Run 'hugo server' in another terminal and open /publications/ and /collaborations/."
confirm "Map looks right?" || {
  latest=$(ls -t scripts/backups/people-*.json 2>/dev/null | head -1)
  echo "To undo: cp \"$latest\" static/data/people.json"
  exit 0
}

echo; echo "=== STEP 5: commit ==="
files=(content/publications/_index.md static/data/people.json scripts/geocode_cache.json \
       scripts/inst_overrides.json scripts/exclude.json scripts/README.md)
for f in "${files[@]}"; do [ -e "$f" ] && git add "$f"; done
git status --short
read -r -p "Commit message [Add paper and update collaborator map]: " msg
git commit -m "${msg:-Add paper and update collaborator map}"
confirm "Push now?" && git push
echo "Done."
