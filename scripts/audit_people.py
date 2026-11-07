import json, re, unicodedata
from collections import defaultdict
from pathlib import Path

p = json.load(open(Path(__file__).resolve().parent.parent / "static/data/people.json"))

def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", s.lower()).strip()

# 1. same last name + first initial: possible duplicates or people who moved
g = defaultdict(list)
for e in p:
    parts = e["name"].replace(".", " ").split()
    g[(norm(parts[-1]), norm(parts[0])[:1])].append(e)
print("== Same last name + first initial (review for duplicates) ==")
for k, v in sorted(g.items()):
    if len(v) > 1:
        for e in v:
            print(f"  {e['name']:28} | {e['inst']:40} | {e['lat']}, {e['lon']}")
        print()

# 2. one institution with more than one coordinate pair: inconsistent geocoding
c = defaultdict(set)
for e in p:
    c[e["inst"]].add((round(e["lat"], 2), round(e["lon"], 2)))
print("== Institutions with inconsistent coordinates ==")
for inst, s in c.items():
    if len(s) > 1:
        print(f"  {inst}: {sorted(s)}")

# 3. impossible coordinates
print("== Bad coordinates ==")
for e in p:
    if not (-90 <= e["lat"] <= 90 and -180 <= e["lon"] <= 180) or (e["lat"], e["lon"]) == (0, 0):
        print("  ", e)
print(f"\n{len(p)} people, {len(c)} institutions")
