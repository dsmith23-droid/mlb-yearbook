#!/usr/bin/env python3
"""
check_aliases.py - Find teams with empty bench/bullpen due to alias mismatches.

Run this AFTER build_all_seasons.py to audit the built JSON files.
Prints any team+season combos where bench AND bullpen are both empty
across ALL games (which indicates a roster alias mismatch, not just
a team that happened to use everyone on a given day).

Usage: python check_aliases.py
"""

import json, os, glob

DATA_DIR = "data"
MIN_GAMES = 5  # only flag teams that played this many games with empty rosters

files = sorted(glob.glob(os.path.join(DATA_DIR, "*.json")))
files = [f for f in files if os.path.basename(f) != "player_index.json"]

print(f"Checking {len(files)} season files...\n")

all_issues = []

for path in files:
    year = os.path.basename(path).replace(".json", "")
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        print(f"  SKIP {year}: {e}")
        continue

    # Count games per team where bench AND bullpen are both empty
    team_empty = {}   # team -> count of games with empty bench+bp
    team_total = {}   # team -> total games

    for gid, box in d.get("box_scores", {}).items():
        for side, code_key in [("vb", "v"), ("hb", "h")]:
            code = box.get(code_key, "")
            tb = box.get(side, {})
            bench = tb.get("b", [])
            bullpen = tb.get("bp", [])

            team_total[code] = team_total.get(code, 0) + 1
            if len(bench) == 0 and len(bullpen) == 0:
                team_empty[code] = team_empty.get(code, 0) + 1

    # Report teams where ALL (or nearly all) games have empty bench+bp
    for team, empty_count in team_empty.items():
        total = team_total.get(team, 1)
        pct = empty_count / total
        if pct > 0.8 and total >= MIN_GAMES:  # >80% of games empty
            all_issues.append((year, team, empty_count, total,
                               d["teams"].get(team, {}).get("full", team)))

if not all_issues:
    print("✓ No alias mismatches detected! All teams have bench/bullpen data.")
else:
    print(f"Found {len(all_issues)} team-seasons with missing bench/bullpen:\n")
    print(f"  {'Year':<6} {'Code':<6} {'Empty/Total':<14} {'Team'}")
    print(f"  {'-'*5:<6} {'-'*5:<6} {'-'*13:<14} {'-'*30}")
    for year, team, empty, total, name in sorted(all_issues):
        print(f"  {year:<6} {team:<6} {empty}/{total:<12} {name}")

    print("\nThese team codes appear in game data but have no OD roster match.")
    print("For each one, check what code the OD/transaction files use and add")
    print("the mapping to TEAM_ALIAS in build_all_seasons.py, then rebuild.")

print(f"\nDone.")
