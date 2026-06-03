#!/usr/bin/env python3
"""
Build STB (Season Ticket Baseball) ratings JSON files by parsing the PDF card files.
Reads Batters.pdf and Pitchers.pdf from each season folder and outputs data/stb/YEAR.json.

Usage:
    python build_stb_ratings.py           # all seasons
    python build_stb_ratings.py 2005      # single season
    python build_stb_ratings.py 2003 2004 2005

Config:
    STB_DIR  = path to your Season Ticket Baseball folder
    OUT_DIR  = where to write the JSON files
"""

import re, json, os, sys
from collections import defaultdict

try:
    import pdfplumber
except ImportError:
    print("ERROR: pdfplumber not installed. Run: pip install pdfplumber")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
STB_DIR = r"D:\baseball stuff\Baseball stuff\Season Ticket Baseball"
OUT_DIR = os.path.join(os.path.dirname(__file__), "data", "stb")
# ─────────────────────────────────────────────────────────────────────────────

def normalize_name(name):
    """Normalize ALL CAPS STB name to Title Case matching Retrosheet format."""
    import re as _re
    n = name.title()
    n = _re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), n)
    n = _re.sub(r"\bMac([a-z])", lambda m: "Mac" + m.group(1).upper(), n)
    n = _re.sub(r"\bO'([a-z])", lambda m: "O'" + m.group(1).upper(), n)
    # Collapse spaced initials: "J. J." -> "J.J."
    n = _re.sub(r'\b([A-Z])\. ([A-Z])\.', r'\1.\2.', n)
    return n

def safe_int(v, default=0):
    try: return int(v) if v and str(v).strip() not in ('-','') else default
    except: return default

def extract_column_texts(pdf_path):
    """Extract text per column from a multi-column PDF."""
    col_texts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False)
            if not words: continue
            col_w = page.width / 3
            cols = defaultdict(list)
            for w in words:
                col = int(w['x0'] / col_w)
                cols[col].append(w)
            for col_idx in sorted(cols.keys()):
                col_words = sorted(cols[col_idx], key=lambda w: w['top'])
                lines = defaultdict(list)
                for w in col_words:
                    line_y = round(w['top'] / 3) * 3
                    lines[line_y].append(w['text'])
                col_text = '\n'.join(' '.join(wds) for _, wds in sorted(lines.items()))
                if col_text.strip():
                    col_texts.append(col_text)
    return col_texts

# Regex to find player card boundaries
BATTER_CARD_RE = re.compile(
    r'^([A-Z][A-ZÀ-Ú\s\.\-\']+?)(?:\s+#(\d+))?\s+([\w/]+)\s*\n'
    r'([A-Z][A-Z\s\.]+?)\s*\((\d{4})\)\s+AGE\s+(\d+)\s+(RIGHTY|LEFTY|SWITCH)',
    re.MULTILINE
)
PITCHER_CARD_RE = re.compile(
    r'^([A-Z][A-ZÀ-Ú\s\.\-\']+?)(?:\s+#(\d+))?\s+(SP|RP|CL|SP/RP|RP/SP|CL/RP)\s*\n'
    r'([A-Z][A-Z\s\.]+?)\s*\((\d{4})\)\s+AGE\s+(\d+)\s+(RIGHTY|LEFTY|SWITCH)',
    re.MULTILINE
)
# Defense ratings: POS arm rng fld g
DEF_RE = re.compile(r'\b(P|C|1B|2B|3B|SS|LF|CF|RF)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d]+|-)(?:\s|$)')

def parse_batter_card(card_text, match):
    name = match.group(1).strip()
    pos  = match.group(3)
    team = match.group(4).strip()
    year = match.group(5)
    age  = safe_int(match.group(6))
    hand = match.group(7)

    bat = {}
    for r in ['Power','Contact','Eye','Speed','Steal','Bunt']:
        m = re.search(rf'\b{r}\s+(\d+)\b', card_text)
        if m: bat[r.lower()] = int(m.group(1))

    def_ratings = {}
    for dm in DEF_RE.finditer(card_text):
        dpos = dm.group(1)
        if dpos not in def_ratings:
            def_ratings[dpos] = {
                'arm': int(dm.group(2)), 'rng': int(dm.group(3)),
                'fld': int(dm.group(4)), 'g': dm.group(5)
            }
    ump_m = re.search(r'\bUmp\s+(\d)\b', card_text)   # single digit only
    pb_m  = re.search(r'\bPB\s+(\d)\b',  card_text)    # single digit only - avoids matching roll numbers like 'PB 529'
    if ump_m and 'C' in def_ratings: def_ratings['C']['ump'] = int(ump_m.group(1))
    if pb_m  and 'C' in def_ratings: def_ratings['C']['pb']  = int(pb_m.group(1))

    # All listed positions (from def dict)
    listed = list(def_ratings.keys())
    # Primary from pos field (first before /)
    primary = pos.split('/')[0].strip()

    return {
        'name': name, 'number': match.group(2) or '', 'pos': pos,
        'primary': primary, 'listed': listed,
        'team': team, 'year': year, 'age': age, 'hand': hand,
        'bat': bat, 'def': def_ratings, 'pitcher': False
    }

def parse_pitcher_card(card_text, match):
    name = match.group(1).strip()
    role = match.group(3)
    team = match.group(4).strip()
    year = match.group(5)
    age  = safe_int(match.group(6))
    hand = match.group(7)

    bat = {}
    for r in ['Power','Contact','Eye','Speed','Steal','Bunt']:
        m = re.search(rf'\b{r}\s+(\d+)\b', card_text)
        if m: bat[r.lower()] = int(m.group(1))

    pit = {}
    stamina_m = re.search(r'Stamina\s+([\d/]+)', card_text)
    stuff_m   = re.search(r'Stuff\s+vs\.\s+L/R\s+([\d/]+)', card_text)
    hold_m    = re.search(r'Hold\s+(\d+)', card_text)
    pickoff_m = re.search(r'Pickoff\s+(\d+)', card_text)
    arm_m     = re.search(r'Arm\s+(\d+)', card_text)
    fld_m     = re.search(r'Fielding\s+(\d+)', card_text)

    if stamina_m:  pit['stamina']  = stamina_m.group(1)
    if stuff_m:    pit['stuff']    = stuff_m.group(1)
    if hold_m:     pit['hold']     = int(hold_m.group(1))
    if pickoff_m:  pit['pickoff']  = int(pickoff_m.group(1))
    if arm_m:      pit['arm']      = int(arm_m.group(1))
    if fld_m:      pit['fld']      = int(fld_m.group(1))

    arm = pit.get('arm', 0)
    fld = pit.get('fld', 8)

    return {
        'name': name, 'number': match.group(2) or '', 'pos': 'P', 'role': role,
        'primary': 'P', 'listed': ['P'],
        'team': team, 'year': year, 'age': age, 'hand': hand,
        'bat': bat, 'pit': pit,
        'def': {'P': {'arm': arm, 'rng': 0, 'fld': fld, 'g': '-'}},
        'pitcher': True
    }

def parse_cards_from_col(col_text, is_pitcher=False, verbose=False):
    players = []
    pattern = PITCHER_CARD_RE if is_pitcher else BATTER_CARD_RE
    card_starts = [(m.start(), m) for m in pattern.finditer(col_text)]
    if verbose and not card_starts:
        # Suppress known non-card pages (pitcher batting card, rules pages)
        skip_phrases = ('PITCHER BATTING CARD', 'Ratings-Based Defense', 'Insert in Lineup')
        if not any(p in col_text[:100] for p in skip_phrases):
            print(f"    No cards found in column. First 200 chars: {repr(col_text[:200])}")
    for i, (start, match) in enumerate(card_starts):
        end = card_starts[i+1][0] if i+1 < len(card_starts) else len(col_text)
        card_text = col_text[start:end]
        try:
            if is_pitcher:
                players.append(parse_pitcher_card(card_text, match))
            else:
                players.append(parse_batter_card(card_text, match))
        except Exception as e:
            print(f"    Warning: error parsing {match.group(1)}: {e}")
    return players

def find_pdfs(year_dir):
    """Find all batter and pitcher PDFs in a year directory."""
    batter_pdfs, pitcher_pdfs = [], []
    year = os.path.basename(year_dir)

    def scan_dir(d):
        for fname in os.listdir(d):
            fpath = os.path.join(d, fname)
            if os.path.isdir(fpath):
                scan_dir(fpath)
            elif fname.lower().endswith('.pdf'):
                fl = fname.lower()
                if 'pitcher' in fl or 'pitching' in fl:
                    pitcher_pdfs.append(fpath)
                elif 'batter' in fl or 'batting' in fl or 'hitter' in fl:
                    batter_pdfs.append(fpath)

    if os.path.isdir(year_dir):
        scan_dir(year_dir)
    return batter_pdfs, pitcher_pdfs

def build_year(year):
    year_str = str(year)
    year_dir = os.path.join(STB_DIR, year_str)
    if not os.path.isdir(year_dir):
        print(f"  SKIP {year}: folder not found")
        return False

    batter_pdfs, pitcher_pdfs = find_pdfs(year_dir)
    if not batter_pdfs and not pitcher_pdfs:
        print(f"  SKIP {year}: no PDFs found")
        return False

    # Key: "NAME|TEAM"
    players = {}

    def add_player(p):
        # Normalize name to Title Case matching Retrosheet format
        p['name_upper'] = p['name']  # keep original ALL CAPS
        p['name'] = normalize_name(p['name'])
        key = f"{p['name']}|{p['team']}"
        if key in players:
            # Merge def ratings
            existing = players[key]
            for pos, d in p['def'].items():
                if pos not in existing['def']:
                    existing['def'][pos] = d
            if p.get('listed'):
                for lp in p['listed']:
                    if lp not in existing.get('listed',[]):
                        existing.setdefault('listed',[]).append(lp)
        else:
            players[key] = p

    total_pdfs = len(batter_pdfs) + len(pitcher_pdfs)
    parsed_players = 0

    for pdf_path in batter_pdfs:
        try:
            cols = extract_column_texts(pdf_path)
            found_in_pdf = 0
            for col_text in cols:
                for p in parse_cards_from_col(col_text, is_pitcher=False, verbose=True):
                    add_player(p)
                    parsed_players += 1
                    found_in_pdf += 1
            if found_in_pdf == 0:
                print(f"    Warning: 0 players parsed from {os.path.basename(pdf_path)}")
            else:
                print(f"    OK: {found_in_pdf} players from {os.path.basename(pdf_path)}")
        except Exception as e:
            print(f"    Warning: error reading {os.path.basename(pdf_path)}: {e}")

    for pdf_path in pitcher_pdfs:
        try:
            for col_text in extract_column_texts(pdf_path):
                for p in parse_cards_from_col(col_text, is_pitcher=True):
                    add_player(p)
                    parsed_players += 1
        except Exception as e:
            print(f"    Warning: error reading {os.path.basename(pdf_path)}: {e}")

    if not players:
        print(f"  SKIP {year}: no players parsed from {total_pdfs} PDFs")
        return False

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{year_str}.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(players, f, separators=(',',':'))

    size = os.path.getsize(out_path)
    multi = sum(1 for p in players.values() if len(p.get('def',{})) > 1)
    print(f"  OK  {year}: {len(players)} players ({multi} multi-pos) from {total_pdfs} PDFs → {size/1024:.0f} KB")
    return True

def main():
    args = sys.argv[1:]
    if args:
        years = [int(a) for a in args if a.isdigit()]
    else:
        years = []
        if os.path.isdir(STB_DIR):
            for d in sorted(os.listdir(STB_DIR)):
                if d.isdigit() and len(d) == 4:
                    years.append(int(d))
        if not years:
            print(f"No year folders found in {STB_DIR}")
            return

    print(f"Building STB ratings for {len(years)} seasons...")
    ok = skipped = 0
    for y in years:
        result = build_year(y)
        if result: ok += 1
        else: skipped += 1

    print(f"\nDone: {ok} OK, {skipped} skipped")
    print(f"Output: {OUT_DIR}")

if __name__ == '__main__':
    main()
