"""
import_logos.py  -  copy team logos into the yearbook site and build logos/manifest.json

Your source layout:   <SRC>\\1953\\Boston_Red_Sox_1924.png   (number = first year that logo was used)
What this produces:   <SITE>\\logos\\Boston_Red_Sox_1924.png  (each image copied once)
                      <SITE>\\logos\\manifest.json            {"1953": {"BOS": "Boston_Red_Sox_1924.png", ...}, ...}

Run it any time you add or change logos:   python import_logos.py
"""
import os, re, json, shutil

SRC  = r"D:\baseball stuff\baseball logos by year"
SITE = r"D:\baseball stuff\yearbook_site"
DEST = os.path.join(SITE, "logos")
IMG_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}

# Normalized team name -> candidate team codes (first one that exists in that season's data wins).
# Names are lower-case, underscores -> spaces, periods removed, year ranges and trailing NL/AL dropped.
NAME_TO_CODES = {
    # American League
    'boston red sox': ['BOS'], 'boston americans': ['BOS'],
    'new york yankees': ['NYA'], 'new york highlanders': ['NYA'],
    'baltimore orioles': ['BAL'],
    'st louis browns': ['SLA'],
    'detroit tigers': ['DET'],
    'cleveland indians': ['CLE'], 'cleveland guardians': ['CLE'], 'cleveland naps': ['CLE'],
    'cleveland blues': ['CLE'], 'cleveland bronchos': ['CLE'],
    'chicago white sox': ['CHA'],
    'philadelphia athletics': ['PHA'],
    'washington senators': ['WS1', 'WS2', 'WSA'],
    'kansas city athletics': ['KC1'], 'kansas city royals': ['KCA'],
    'oakland athletics': ['OAK', 'ATH'], 'athletics': ['ATH', 'OAK'],
    'sacramento athletics': ['ATH'], 'las vegas athletics': ['ATH'],
    'seattle pilots': ['SE1', 'SEP'], 'seattle mariners': ['SEA'],
    'milwaukee brewers': ['MIL'], 'minnesota twins': ['MIN'], 'texas rangers': ['TEX'],
    'california angels': ['CAL', 'LAA', 'ANA'], 'anaheim angels': ['ANA', 'CAL', 'LAA'],
    'los angeles angels': ['LAA', 'ANA', 'CAL'], 'los angeles angels of anaheim': ['LAA', 'ANA', 'CAL'],
    'toronto blue jays': ['TOR'],
    'tampa bay devil rays': ['TBA'], 'tampa bay rays': ['TBA'],
    # National League
    'boston braves': ['BSN'], 'boston bees': ['BSN'], 'boston beaneaters': ['BSN'],
    'boston doves': ['BSN'], 'boston rustlers': ['BSN'],
    'milwaukee braves': ['MLN'], 'atlanta braves': ['ATL'],
    'brooklyn dodgers': ['BRO'], 'brooklyn robins': ['BRO'], 'brooklyn superbas': ['BRO'],
    'brooklyn trolley dodgers': ['BRO'], 'los angeles dodgers': ['LAN'],
    'new york giants': ['NY1'], 'san francisco giants': ['SFN'],
    'chicago cubs': ['CHN'],
    'cincinnati reds': ['CIN'], 'cincinnati redlegs': ['CIN'],
    'pittsburgh pirates': ['PIT'],
    'st louis cardinals': ['SLN'],
    'philadelphia phillies': ['PHI'], 'philadelphia blue jays': ['PHI'],
    'new york mets': ['NYN'],
    'houston astros': ['HOU'], 'houston colt 45s': ['HOU'],
    'montreal expos': ['MON'], 'washington nationals': ['WAS', 'WSN'],
    'san diego padres': ['SDN'], 'colorado rockies': ['COL'],
    'florida marlins': ['FLO', 'MIA'], 'miami marlins': ['MIA', 'FLO'],
    'arizona diamondbacks': ['ARI'],
}


def parse_name(stem):
    """'Washington_Senators_1901-1960_1953' -> ('washington senators', 1953)"""
    start = 0
    m = re.search(r'_(\d{4})$', stem)
    if m:
        start = int(m.group(1))
        stem = stem[:m.start()]
    stem = re.sub(r'_\d{4}-\d{4}$', '', stem)
    name = stem.replace('_', ' ').replace('.', '').lower().strip()
    name = re.sub(r'\s+(nl|al)$', '', name)
    return name, start


def season_codes(year):
    """Team codes present in that season's data file, if we can find it (used to pick between candidates)."""
    for d in ('data', 'data_v2'):
        p = os.path.join(SITE, d, f'{year}.json')
        if os.path.exists(p):
            try:
                with open(p, encoding='utf-8') as f:
                    return set(json.load(f).get('teams', {}).keys())
            except Exception:
                pass
    return None


def main():
    if not os.path.isdir(SRC):
        print(f"Source folder not found: {SRC}")
        return
    os.makedirs(DEST, exist_ok=True)

    manifest = {}
    unknown, skipped = {}, []
    copied = 0

    year_dirs = sorted(d for d in os.listdir(SRC)
                       if d.isdigit() and os.path.isdir(os.path.join(SRC, d)))
    for yd in year_dirs:
        year = int(yd)
        avail = season_codes(year)
        chosen = {}  # code -> (start_year, filename)
        for fn in sorted(os.listdir(os.path.join(SRC, yd))):
            stem, ext = os.path.splitext(fn)
            if ext.lower() not in IMG_EXT:
                continue
            name, start = parse_name(stem)
            cands = NAME_TO_CODES.get(name)
            if not cands:
                unknown.setdefault(name, []).append(yd)
                continue
            code = next((c for c in cands if avail is None or c in avail), None)
            if code is None:
                skipped.append(f"{yd}: {fn} (none of {cands} are in that season's data)")
                continue
            prev = chosen.get(code)
            if prev is None or start > prev[0]:
                chosen[code] = (start, fn)

        manifest[yd] = {}
        for code, (_, fn) in chosen.items():
            manifest[yd][code] = fn
            src = os.path.join(SRC, yd, fn)
            dst = os.path.join(DEST, fn)
            if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
                shutil.copy2(src, dst)
                copied += 1

    with open(os.path.join(DEST, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, separators=(',', ':'), sort_keys=True)

    total = sum(len(v) for v in manifest.values())
    print(f"{len(year_dirs)} year folders, {total} team-season logos, {copied} files copied to {DEST}")
    if unknown:
        print("\nNames I didn't recognize (add them to NAME_TO_CODES at the top of this script):")
        for n, yrs in sorted(unknown.items()):
            print(f"  '{n}'  (seen in {', '.join(yrs[:5])}{'...' if len(yrs) > 5 else ''})")
    if skipped:
        print("\nSkipped (team not in that season's data):")
        for s in skipped[:30]:
            print("  " + s)


if __name__ == '__main__':
    main()
