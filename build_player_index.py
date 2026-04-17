#!/usr/bin/env python3
"""
Build player_index.json - run this after build_all_seasons.py
Scans all data/YEAR.json files AND the season ROS files to create
data/player_index.json with disambiguation for same-named players.

Usage: python build_player_index.py

Requires: biofile0.csv in the same folder as build_all_seasons.py
          (i.e., in D:\baseball stuff\ or wherever BASE_DIR points)
"""
import json, os, glob, csv

# ── Edit these paths ──────────────────────────────────────────────────────────
SEASONS_DIR = r"D:\baseball stuff"   # same as in build_all_seasons.py
DATA_DIR    = "data"
BIO_FILE    = os.path.join(SEASONS_DIR, "biofile0.csv")
# ─────────────────────────────────────────────────────────────────────────────

# Load biofile: id -> birth_year
bio_birth = {}
if os.path.exists(BIO_FILE):
    with open(BIO_FILE, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            pid = row["id"].strip()
            bd  = row["birthdate"].strip()
            bio_birth[pid] = bd[:4] if bd and len(bd) >= 4 else ""
    print(f"Loaded {len(bio_birth)} bio entries")
else:
    print(f"WARNING: biofile not found at {BIO_FILE} — no birth year disambiguation")

# Build name+birth_year -> set of seasons
# Key: (name, birth_year) or just name if no birth data
player_index = {}   # (name, birth_year) -> sorted list of seasons
player_names = {}   # (name, birth_year) -> display name

files = sorted(glob.glob(os.path.join(DATA_DIR, "*.json")))
files = [f for f in files if os.path.basename(f) != "player_index.json"]
print(f"Scanning {len(files)} season files...")

for path in files:
    year = os.path.basename(path).replace(".json", "")

    # Load ROS files for this season to get player ID -> birth year mapping
    ros_dir = os.path.join(SEASONS_DIR, year)
    pid_to_birth = {}
    pid_to_name  = {}
    if os.path.isdir(ros_dir):
        for rf in glob.glob(os.path.join(ros_dir, "*.ROS")):
            with open(rf, encoding="utf-8", errors="replace") as f:
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) >= 3:
                        pid  = parts[0].strip()
                        name = f"{parts[2].strip()} {parts[1].strip()}"
                        birth_yr = bio_birth.get(pid, "")
                        pid_to_birth[name] = birth_yr  # last write wins if dup name, OK
                        pid_to_name[pid]   = name

    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        print(f"  SKIP {year}: {e}")
        continue

    names_this_season = set()
    for box in d.get("box_scores", {}).values():
        for side in ["vb", "hb"]:
            tb = box.get(side, {})
            for section in ["l", "b", "bp", "p"]:
                for p in tb.get(section, []):
                    nm = p.get("n")
                    if nm:
                        names_this_season.add(nm)

    for nm in names_this_season:
        birth_yr = pid_to_birth.get(nm, "")
        key = (nm, birth_yr)
        if key not in player_index:
            player_index[key] = []
        if year not in player_index[key]:
            player_index[key].append(year)

    print(f"  {year}: {len(names_this_season)} players")

# Sort seasons and convert to output format
# Output: list of {name, birth, seasons} sorted by name then birth
output = []
for (name, birth), seasons in player_index.items():
    output.append({
        "n": name,
        "b": birth,
        "s": sorted(seasons)
    })
output.sort(key=lambda x: (x["n"].lower(), x["b"]))

out_path = os.path.join(DATA_DIR, "player_index.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, separators=(",", ":"))

size = os.path.getsize(out_path)
total = len(output)
multi = sum(1 for e in output if len(e["s"]) > 1)
dups  = len(output) - len(set(e["n"] for e in output))
print(f"\nDone: {total:,} player-entries, {multi:,} multi-season, {dups} disambiguation entries")
print(f"Output: {out_path} ({size/1024:.0f} KB)")
