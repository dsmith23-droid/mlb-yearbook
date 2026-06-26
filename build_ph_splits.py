#!/usr/bin/env python3
"""
Build season-long pinch-hit appearance counts vs LHP/RHP for every batter.
Reads YEARplays.csv + YEARbatting.csv and outputs data/ph_splits/YEAR.json
keyed by Retrosheet player id: {"id": {"L":N, "R":N}}  (N = PH appearance count)

Usage:
    python build_ph_splits.py           # all seasons
    python build_ph_splits.py 2011      # single season
    python build_ph_splits.py 2009 2010 2011
"""

import csv, json, os, sys
from collections import defaultdict

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR    = r"D:\baseball stuff"
SEASONS_DIR = BASE_DIR  # year folders (1940\, 1941\, ...) live directly under BASE_DIR
OUT_DIR     = os.path.join(os.path.dirname(__file__), "data", "ph_splits")
FIRST_YEAR, LAST_YEAR = 1915, 2025
# ─────────────────────────────────────────────────────────────────────────────

def build_year(year):
    y = str(year)
    data_dir = os.path.join(SEASONS_DIR, y)
    plays_path   = os.path.join(data_dir, f'{y}plays.csv')
    batting_path = os.path.join(data_dir, f'{y}batting.csv')

    if not (os.path.exists(plays_path) and os.path.exists(batting_path)):
        return False

    # Step 1: find every (gid, batter id) that was a pinch-hit appearance
    ph_keys = set()
    with open(batting_path, encoding='utf-8', errors='replace') as f:
        for r in csv.DictReader(f):
            if r.get('ph') == '1':
                ph_keys.add((r['gid'], r['id']))

    if not ph_keys:
        return False

    # Step 2: walk plays.csv, count PH appearances vs L/R pitcher handedness
    # (count the plate appearance once, using the pitcher's hand at that PA)
    counts = defaultdict(lambda: {'L': 0, 'R': 0})
    seen = set()  # (gid, batter) already counted, to avoid double counting multi-event PAs
    with open(plays_path, encoding='utf-8', errors='replace') as f:
        for p in csv.DictReader(f):
            if p.get('pa') != '1':
                continue
            key = (p['gid'], p['batter'])
            if key not in ph_keys or key in seen:
                continue
            hand = p.get('pithand', '')
            if hand not in ('L', 'R'):
                continue
            counts[p['batter']][hand] += 1
            seen.add(key)

    if not counts:
        return False

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{y}.json")
    clean = {pid: c for pid, c in counts.items() if c['L'] or c['R']}
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(clean, f, separators=(',', ':'))

    print(f"  OK  {year}: {len(clean)} players with PH appearances → {os.path.getsize(out_path)/1024:.0f} KB")
    return True

def main():
    args = sys.argv[1:]
    years = [int(a) for a in args if a.isdigit()] if args else range(FIRST_YEAR, LAST_YEAR+1)

    print(f"Building PH splits...")
    ok = skipped = 0
    for y in years:
        if build_year(y):
            ok += 1
        else:
            skipped += 1
    print(f"\nDone: {ok} OK, {skipped} skipped (no data)")
    print(f"Output: {OUT_DIR}")

if __name__ == '__main__':
    main()
