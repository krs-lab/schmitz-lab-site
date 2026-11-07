#!/usr/bin/env python3
"""Automated sanity check of static/data/people.json against PubMed.

For every person it checks:
  1. NAME  - appears as an author on at least one PMID listed on the publications page
  2. INST  - one of their PubMed affiliations supports the institution on the map
and for every institution:
  3. GEO   - stored coordinates are within 75 km of a fresh geocode of the institution name

Usage: python3 scripts/verify_people.py [--no-geo]
Writes scripts/verify_report.csv. Exit code 1 if any problem is found.
"""
import argparse, csv, json, math, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_collaborators as u

GEO_CACHE = u.ROOT / "scripts/verify_geocache.json"
REPORT = u.ROOT / "scripts/verify_report.csv"
GEO_TOL_KM = 75


def km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def supports(inst, aff, overrides):
    n_inst = u.norm(inst)
    if n_inst and n_inst in u.norm(aff):
        return True
    low = aff.lower()
    return any(k.lower() in low and v["inst"] == inst for k, v in overrides.items())


def first_name_ok(a, b):
    # "karl" vs "k" / "kr" / "karl" -> compatible
    return a[:1] == b[:1] and (len(a) <= 2 or len(b) <= 2 or a.startswith(b) or b.startswith(a))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-geo", action="store_true", help="skip the coordinate check (faster)")
    args = ap.parse_args()

    people = json.loads(u.PEOPLE.read_text(encoding="utf-8"))
    overrides = json.loads(u.OVERRIDES.read_text()) if u.OVERRIDES.exists() else {}

    pmids = u.get_pmids()
    print(f"Fetching authors for {len(pmids)} PMIDs from PubMed...")
    idx = defaultdict(list)                      # norm(last) -> [(pmid, norm first, affs)]
    for pmid, fore, last, affs in u.fetch_authors(pmids):
        fn = (u.norm(fore).split() or [""])[0]
        idx[u.norm(last)].append((pmid, fn, affs))

    rows, problems = [], 0
    for p in people:
        n = u.norm(p["name"])
        first = n.split()[0] if n else ""
        hits = []
        for last, entries in idx.items():
            if n.endswith(" " + last):
                hits += [(pm, aff) for pm, fn, aff in entries if first_name_ok(first, fn)]
        if not hits:
            status, detail = "NAME_NOT_FOUND", ""
        else:
            pm_list = sorted({pm for pm, _ in hits})
            affs = [a for _, al in hits for a in al if a]
            if not affs:
                status, detail = "NO_AFFIL_DATA", "PMIDs " + ",".join(pm_list)
            elif any(supports(p["inst"], a, overrides) for a in affs):
                status, detail = "OK", "PMIDs " + ",".join(pm_list)
            else:
                status, detail = "INST_MISMATCH", "PubMed says: " + affs[0][:110]
        rows.append([p["name"], p["inst"], p["lat"], p["lon"], status, detail])

    # coordinate check, one geocode per institution
    geo_bad = []
    if not args.no_geo:
        cache = json.loads(GEO_CACHE.read_text()) if GEO_CACHE.exists() else {}
        insts = {}
        for p in people:
            insts.setdefault(p["inst"], (p["lat"], p["lon"]))
        print(f"Geocoding {len(insts)} institutions (about {int(len(insts) * 1.2)} s)...")
        for inst, (lat, lon) in insts.items():
            if inst not in cache:
                cache[inst] = u.geocode(inst)
            g = cache[inst]
            if g and km(lat, lon, g[0], g[1]) > GEO_TOL_KM:
                geo_bad.append((inst, (lat, lon), g, round(km(lat, lon, g[0], g[1]))))
        GEO_CACHE.write_text(json.dumps(cache, indent=1))

    with open(REPORT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "institution", "lat", "lon", "status", "detail"])
        w.writerows(rows)

    counts = defaultdict(int)
    for r in rows:
        counts[r[4]] += 1
    print(f"\n{len(people)} people checked")
    for k in ("OK", "NO_AFFIL_DATA", "NAME_NOT_FOUND", "INST_MISMATCH"):
        print(f"  {k:15} {counts[k]}")

    for label, key, note in (
        ("INST_MISMATCH", "INST_MISMATCH", "author found, but no PubMed affiliation supports this institution:"),
        ("NAME_NOT_FOUND", "NAME_NOT_FOUND", "not an author on any PMID on the publications page:"),
    ):
        bad = [r for r in rows if r[4] == key]
        if bad:
            print(f"\n{label}: {note}")
            for r in bad:
                print(f"  {r[0]} | {r[1]} {r[5]}")
    problems += counts["INST_MISMATCH"] + counts["NAME_NOT_FOUND"]

    if geo_bad:
        print(f"\nGEO: stored coordinates more than {GEO_TOL_KM} km from a fresh geocode:")
        for inst, stored, g, d in geo_bad:
            print(f"  {inst}: stored {stored}, geocoder says {tuple(g)} ({d} km apart)")
        problems += len(geo_bad)

    print(f"\nFull report: {REPORT}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
