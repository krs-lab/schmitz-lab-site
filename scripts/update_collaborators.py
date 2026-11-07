#!/usr/bin/env python3
"""Add new collaborators to static/data/people.json from PMIDs on the publications page.

Dry run by default. --write saves, after making a timestamped backup.
"""
import argparse, json, re, shutil, time, unicodedata
import urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBS = ROOT / "content/publications/_index.md"
PEOPLE = ROOT / "static/data/people.json"
CACHE = ROOT / "scripts/geocode_cache.json"
OVERRIDES = ROOT / "scripts/inst_overrides.json"   # manual institution fixes
EXCLUDE = ROOT / "scripts/exclude.json"            # people to skip, e.g. ["shi,y"]
BACKUPS = ROOT / "scripts/backups"
CONTACT = "schmitzk@udel.edu"

EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
NOMINATIM = "https://nominatim.openstreetmap.org/search"

STRONG = re.compile(r"universit|college|hospital|polytechnic|school of|medical school|max planck|academy", re.I)
WEAK = re.compile(r"institut|laborator|\bcenter\b|\bcentre\b|clinic|pharmaceutical|\binc\b|medical cent", re.I)
SUB_UNIT = re.compile(r"^(department|dept|division|section|program|graduate|laboratory|lab\b)", re.I)


def http(url, data=None):
    req = urllib.request.Request(url, data=data,
                                 headers={"User-Agent": f"schmitz-lab-site-map/1.0 ({CONTACT})"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


def person_key(name, lat, lon):
    # same person at the same place (within ~1 km) counts once, whatever the institution is called
    parts = name.replace(".", " ").split()
    return (norm(parts[-1]), norm(parts[0])[:1], round(lat, 2), round(lon, 2))


def fix_initials(fore):
    return re.sub(r"\b([A-Z])\b(?!\.)", r"\1.", fore)   # "Daniel W" -> "Daniel W."


def get_pmids():
    text = PUBS.read_text(encoding="utf-8")
    return list(dict.fromkeys(re.findall(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", text)))


def fetch_authors(pmids):
    out = []
    for i in range(0, len(pmids), 100):
        data = urllib.parse.urlencode({
            "db": "pubmed", "id": ",".join(pmids[i:i + 100]), "retmode": "xml",
            "tool": "schmitz-lab-map", "email": CONTACT}).encode()
        root = ET.fromstring(http(EFETCH, data))
        for art in root.findall(".//PubmedArticle"):
            pmid = art.findtext(".//MedlineCitation/PMID")
            for au in art.findall(".//AuthorList/Author"):
                last = au.findtext("LastName")
                fore = au.findtext("ForeName") or au.findtext("Initials")
                if not last or not fore:
                    continue
                affs = [a.findtext("Affiliation") or "" for a in au.findall("AffiliationInfo")]
                out.append((pmid, fore, last, affs))
        time.sleep(0.4)
    return out


def parse_aff(aff):
    aff = re.sub(r"\S+@\S+", "", aff)
    aff = re.sub(r"Electronic address:?", "", aff, flags=re.I).strip(" .;")
    aff = aff.split(";")[0]                         # first affiliation only
    segs = [s.strip() for s in aff.split(",") if s.strip()]
    for rx in (STRONG, WEAK):                       # prefer a real university over an "institute"
        for i, s in enumerate(segs):
            if rx.search(s) and not SUB_UNIT.match(s):
                tail = [t for t in segs[i + 1:] if not re.search(r"\d", t)]   # drop zip codes
                return s, tail
    return None


def geocode(query):
    time.sleep(1.1)                                 # Nominatim limit: 1 request/second
    url = NOMINATIM + "?" + urllib.parse.urlencode({"q": query, "format": "json", "limit": 1})
    res = json.loads(http(url))
    return [round(float(res[0]["lat"]), 5), round(float(res[0]["lon"]), 5)] if res else None


def resolve(aff, cache, overrides, failed):
    low = aff.lower()
    for k, v in overrides.items():
        if k.lower() in low:
            return v["inst"], v["lat"], v["lon"]
    parsed = parse_aff(aff)
    if not parsed:
        return None
    inst, tail = parsed
    if inst in failed:
        return None
    if inst not in cache:
        coords = geocode(", ".join([inst] + tail[-2:])) or geocode(inst)
        if not coords:
            failed.add(inst)
            return None
        cache[inst] = coords
    return inst, cache[inst][0], cache[inst][1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="modify people.json (default: dry run)")
    args = ap.parse_args()

    people = json.loads(PEOPLE.read_text(encoding="utf-8"))
    overrides = json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {}
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    excl = set(json.loads(EXCLUDE.read_text())) if EXCLUDE.exists() else set()
    for p in people:
        cache.setdefault(p["inst"], [p["lat"], p["lon"]])
    seen = {person_key(p["name"], p["lat"], p["lon"]) for p in people}

    pmids = get_pmids()
    print(f"{len(pmids)} PMIDs found in {PUBS.name}; {len(people)} people already on the map")
    new, unresolved, no_aff, failed = [], {}, 0, set()

    for pmid, fore, last, affs in fetch_authors(pmids):
        if f"{norm(last)},{norm(fore)[:1]}" in excl:
            continue
        name = f"{fix_initials(fore)} {last}"
        if not any(affs):
            no_aff += 1
            continue
        for aff in affs:
            r = resolve(aff, cache, overrides, failed)
            if not r:
                unresolved.setdefault(aff, pmid)
                continue
            inst, lat, lon = r
            key = person_key(name, lat, lon)
            if key not in seen:
                seen.add(key)
                new.append({"name": name, "inst": inst, "lat": lat, "lon": lon})
                print(f"  + {name}  |  {inst}  ({lat}, {lon})  PMID {pmid}")

    print(f"\n{len(new)} new entries; {no_aff} authors had no affiliation in PubMed")
    if unresolved:
        print(f"\n{len(unresolved)} affiliations could not be resolved (add to inst_overrides.json):")
        for aff, pmid in unresolved.items():
            print(f"  PMID {pmid}: {aff[:140]}")

    if args.write and new:
        BACKUPS.mkdir(exist_ok=True)
        bak = BACKUPS / f"people-{datetime.now():%Y%m%d-%H%M%S}.json"
        shutil.copy(PEOPLE, bak)
        people.extend(new)
        PEOPLE.write_text(json.dumps(people, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nBackup: {bak}\nWrote {len(new)} entries to {PEOPLE}")
    elif new:
        print("\nDry run only. Re-run with --write to save.")


if __name__ == "__main__":
    main()
