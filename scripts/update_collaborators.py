#!/usr/bin/env python3
"""Update static/data/people.json from PMIDs on the publications page.

One entry per person, placed at the institution of their most recent paper.
Dry run by default. --write saves, after making a timestamped backup.
"""
import argparse, json, re, shutil, time, unicodedata
import urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
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

SURNAME_FIX = {"marchand": "lemarchand"}           # "Le Marchand" == "LeMarchand"


def http(url, data=None):
    req = urllib.request.Request(url, data=data,
                                 headers={"User-Agent": f"schmitz-lab-site-map/1.0 ({CONTACT})"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


# ---------- person identity ----------
def ident(name):
    """-> (surname, first name), both normalised. Surname = last word."""
    toks = [t for t in (norm(x) for x in re.split(r"[\s.]+", name)) if t]
    if not toks:
        return "", ""
    return SURNAME_FIX.get(toks[-1], toks[-1]), toks[0]


def compatible(a, b):
    if len(a) <= 2 or len(b) <= 2:                  # "C.A." vs "Chrystal"
        return True
    return a[:3] == b[:3]                           # "Shiqing" != "Shuxiang"


class People:
    """Assigns one id per real person, merging name variants."""
    def __init__(self):
        self.groups, self.n = {}, 0

    def cid(self, name):
        sur, first = ident(name)
        lst = self.groups.setdefault((sur, first[:1]), [])
        for g in lst:
            if compatible(g[0], first):
                if len(first) > len(g[0]):
                    g[0] = first
                return g[1]
        self.n += 1
        lst.append([first, self.n])
        return self.n


def fix_initials(fore):
    return re.sub(r"\b([A-Z])\b(?!\.)", r"\1.", fore)   # "Daniel W" -> "Daniel W."


# ---------- PubMed ----------
def get_pmids():
    text = PUBS.read_text(encoding="utf-8")
    return list(dict.fromkeys(re.findall(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", text)))


def pub_year(art):
    y = art.findtext(".//ArticleDate/Year") or art.findtext(".//JournalIssue/PubDate/Year")
    if y and y.isdigit():
        return int(y)
    m = re.search(r"\d{4}", art.findtext(".//JournalIssue/PubDate/MedlineDate") or "")
    return int(m.group()) if m else 0


def fetch_authors(pmids):
    out = []
    for i in range(0, len(pmids), 100):
        data = urllib.parse.urlencode({
            "db": "pubmed", "id": ",".join(pmids[i:i + 100]), "retmode": "xml",
            "tool": "schmitz-lab-map", "email": CONTACT}).encode()
        root = ET.fromstring(http(EFETCH, data))
        for art in root.findall(".//PubmedArticle"):
            pmid = art.findtext(".//MedlineCitation/PMID")
            year = pub_year(art)
            for au in art.findall(".//AuthorList/Author"):
                last = au.findtext("LastName")
                fore = au.findtext("ForeName") or au.findtext("Initials")
                if not last or not fore:
                    continue
                affs = [a.findtext("Affiliation") or "" for a in au.findall("AffiliationInfo")]
                out.append((pmid, year, fore, last, affs))
        time.sleep(0.4)
    return out


# ---------- institutions ----------
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

    original = json.loads(PEOPLE.read_text(encoding="utf-8"))
    overrides = json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {}
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    excl = set(json.loads(EXCLUDE.read_text())) if EXCLUDE.exists() else set()
    for p in original:
        cache.setdefault(p["inst"], [p["lat"], p["lon"]])

    def excluded(name):
        sur, first = ident(name)
        return f"{sur},{first[:1]}" in excl

    # 1. collapse existing entries: one per person (newest year wins; no year -> later in file wins)
    reg, best = People(), {}
    for p in original:
        if excluded(p["name"]):
            continue
        cid = reg.cid(p["name"])
        e = dict(p)
        e["year"] = e.get("year", 0)
        cur = best.get(cid)
        if cur is None or e["year"] >= cur["year"]:
            if cur and len(cur["name"]) > len(e["name"]):
                e["name"] = cur["name"]
            best[cid] = e
    print(f"{len(original)} existing entries -> {len(best)} unique people")

    # 2. apply PubMed
    pmids = get_pmids()
    print(f"{len(pmids)} PMIDs found in {PUBS.name}")
    papers = defaultdict(set)
    obs, unresolved, no_aff, failed = [], {}, 0, set()

    for pmid, year, fore, last, affs in fetch_authors(pmids):
        name = f"{fix_initials(fore)} {last}"
        if excluded(name):
            continue
        cid = reg.cid(name)
        papers[cid].add(pmid)
        if not any(affs):
            no_aff += 1
            continue
        for aff in affs:                            # first resolvable affiliation only
            r = resolve(aff, cache, overrides, failed)
            if not r:
                unresolved.setdefault(aff, pmid)
                continue
            obs.append((cid, year, pmid, name) + r)
            break

    # existing entries have no year: trust them unless a strictly newer paper disagrees
    for cid, e in best.items():
        if e["year"]:
            continue
        mine = [o for o in obs if o[0] == cid]
        same = [o[1] for o in mine if o[4] == e["inst"]]
        e["year"] = max(same) if same else max((o[1] for o in mine), default=0)

    added, moved = [], []
    for cid, year, pmid, name, inst, lat, lon in sorted(obs, key=lambda o: o[1]):
        cur = best.get(cid)
        cand = {"name": name, "inst": inst, "lat": lat, "lon": lon, "year": year}
        if cur is None:
            best[cid] = cand
            added.append(name)
            print(f"  + {name}  |  {inst}  ({lat}, {lon})  {year}  PMID {pmid}")
        elif year > cur["year"]:
            if cur["inst"] != inst:
                moved.append(name)
                print(f"  ~ {cur['name']}: {cur['inst']} -> {inst}  ({year}, PMID {pmid})")
            cand["name"] = max(cur["name"], name, key=len)
            best[cid] = cand

    # 3. result
    result = []
    for cid, e in best.items():
        e["papers"] = len(papers[cid]) if cid in papers else e.get("papers", 0)
        result.append({k: e[k] for k in ("name", "inst", "lat", "lon", "year", "papers")})

    print(f"\n{len(added)} new people, {len(moved)} moved to a newer institution, "
          f"{no_aff} authors had no affiliation in PubMed")
    if unresolved:
        print(f"\n{len(unresolved)} affiliations could not be resolved (add to inst_overrides.json):")
        for aff, pmid in unresolved.items():
            print(f"  PMID {pmid}: {aff[:140]}")

    changed = result != original
    if args.write and changed:
        BACKUPS.mkdir(exist_ok=True)
        bak = BACKUPS / f"people-{datetime.now():%Y%m%d-%H%M%S}.json"
        shutil.copy(PEOPLE, bak)
        PEOPLE.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nBackup: {bak}\nWrote {len(result)} people to {PEOPLE}")
    elif changed:
        print("\nDry run only. Re-run with --write to save.")
    else:
        print("\nNo changes.")


if __name__ == "__main__":
    main()
