#!/usr/bin/env python3
"""
Build player_index.json using Retrosheet player IDs as primary keys.
Correctly disambiguates same-name players (e.g. two George Burns in 1921).

Usage: python build_player_index.py
"""
import json, os, glob, csv

SEASONS_DIR = r"D:\baseball stuff"
DATA_DIR    = "data"
BIO_FILE    = os.path.join(SEASONS_DIR, "biofile0.csv")

# Load biofile: pid -> birth year
bio_birth = {}
bio_name  = {}
if os.path.exists(BIO_FILE):
    with open(BIO_FILE, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            pid      = row["id"].strip()
            bd       = row["birthdate"].strip()
            usename  = row.get("usename","").strip()
            lastname = row.get("lastname","").strip()
            bio_birth[pid] = bd[:4] if bd else ""
            bio_name[pid]  = f"{usename} {lastname}".strip() if usename else lastname
    print(f"Loaded {len(bio_birth)} bio entries")

files = sorted(glob.glob(os.path.join(DATA_DIR, "*.json")))
files = [f for f in files if os.path.basename(f) != "player_index.json"]
print(f"Scanning {len(files)} season files...")

# pid -> {name, birth, seasons: {year: [teams]}}
by_pid = {}

for path in files:
    year = os.path.basename(path).replace(".json", "")
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        print(f"  SKIP {year}: {e}")
        continue

    # Scan box scores - each player entry now has 'id' field
    pid_teams = {}   # pid -> set of team codes
    pid_name  = {}   # pid -> display name

    for box in d.get("box_scores", {}).values():
        for side, ck in [("vb","v"), ("hb","h")]:
            tb   = box.get(side, {})
            code = box.get(ck, "")
            for section in ["l", "b", "bp", "p"]:
                for p in tb.get(section, []):
                    pid = p.get("id", "")
                    nm  = p.get("n", "")
                    if not pid or not nm:
                        continue
                    if pid not in pid_teams:
                        pid_teams[pid] = set()
                        pid_name[pid]  = nm
                    pid_teams[pid].add(code)

    for pid, teams in pid_teams.items():
        nm    = pid_name[pid]
        birth = bio_birth.get(pid, "")
        if pid not in by_pid:
            by_pid[pid] = {"name": nm, "birth": birth, "seasons": {}}
        by_pid[pid]["seasons"][year] = sorted(teams)

    print(f"  {year}: {len(pid_teams)} players with IDs")

# Build output sorted by name then birth
output = []
for pid, data in sorted(by_pid.items()):
    output.append({
        "pid": pid,
        "n":   data["name"],
        "b":   data["birth"],
        "s":   data["seasons"]   # {year: [teams]}
    })
output.sort(key=lambda x: (x["n"].lower(), x["b"]))

out_path = os.path.join(DATA_DIR, "player_index.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, separators=(",", ":"))

size  = os.path.getsize(out_path)
total = len(output)
names = len(set(e["n"] for e in output))
dups  = total - names
print(f"\nDone: {total:,} players ({dups} disambiguation entries for same names)")
print(f"Output: {out_path} ({size/1024:.0f} KB)")
