# Updating the collaborator map

Run after adding a paper to `content/publications/_index.md`:

    ./scripts/update_map.sh

It runs these steps, pausing for your OK between them:

1. Dry run: `python3 scripts/update_collaborators.py` (lists new people, saves nothing)
2. Write: `... --write` (backs up `people.json` to `scripts/backups/` first)
3. Check: `verify_people.py` (against PubMed) and `audit_people.py` (consistency)
4. Look at the map with `hugo server`
5. Commit and push

## Requirements
- The new paper needs a PubMed link in the page (`pubmed.ncbi.nlm.nih.gov/<PMID>`)
- Old papers often lack affiliations in PubMed; those authors are skipped

## Fixing problems
- Wrong or unresolved institution: add it to `scripts/inst_overrides.json`.
  The key is any text found in the affiliation; keep the JSON valid (no trailing comma).
- Person who should never appear: add `"lastname,firstinitial"` (lowercase) to `scripts/exclude.json`.
- Bad write: copy the newest file in `scripts/backups/` over `static/data/people.json`.

## Files
- `update_collaborators.py` adds new people  |  `verify_people.py` / `audit_people.py` checks
- `inst_overrides.json`, `exclude.json` manual fixes  |  `geocode_cache.json` saved lookups
