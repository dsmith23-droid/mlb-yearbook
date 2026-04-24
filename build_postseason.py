#!/usr/bin/env python3
"""
MLB Yearbook — Postseason Builder
Reads D:/baseball stuff/postseason/ CSV files
Outputs data/postseason/YEAR.json for each year

Usage: python build_postseason.py [YEAR ...]
"""
import csv, json, os, sys
from collections import defaultdict

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR      = r"D:\baseball stuff"
POSTSEASON_DIR = os.path.join(BASE_DIR, "postseason")
OUT_DIR       = os.path.join(BASE_DIR, "yearbook_site", "data", "postseason")
BIO_FILE      = os.path.join(BASE_DIR, "biofile0.csv")

# ── League membership (for bracket AL/NL assignment) ─────────────────────────
AL = {'NYA','BOS','CLE','HOU','MIN','KCA','DET','TBA','TBD','TEX','OAK','SEA',
      'ANA','LAA','CHA','BAL','TOR','ML4','SEP','WS2','KC1','CAL','MIL'}
NL = {'LAN','CHN','WAS','ARI','COL','SFN','SDN','MIL','ATL','PHI','NYN','SLN',
      'PIT','CIN','FLO','MIA','MON','HOU','BRO','BSN','NY1','MLN','SF1'}

def league(team):
    if team in AL: return 'AL'
    if team in NL: return 'NL'
    return 'AL'  # fallback

# ── Bio file ──────────────────────────────────────────────────────────────────
_BIO = {}
if os.path.exists(BIO_FILE):
    with open(BIO_FILE, encoding='utf-8', errors='replace') as f:
        for r in csv.DictReader(f):
            pid = r['id'].strip()
            first = (r.get('usename') or r.get('firstname','')).strip()
            last  = r.get('lastname','').strip()
            _BIO[pid] = {
                'name': f"{first} {last}".strip() or pid,
                'bt':   r.get('bats','').strip(),
                'th':   r.get('throws','').strip(),
                'born': r.get('birthdate','').strip(),
            }

def si(v):
    try: return int(v) if v and str(v).strip() else 0
    except: return 0

POS = {1:'P',2:'C',3:'1B',4:'2B',5:'3B',6:'SS',7:'LF',8:'CF',9:'RF',10:'DH',11:'PH',12:'PR'}

ROUND_ORDER = ['wildcard','divisionseries','lcs','worldseries','championship']
ROUND_LABEL = {
    'wildcard': 'Wild Card',
    'divisionseries': 'Division Series',
    'lcs': 'League Championship',
    'worldseries': 'World Series',
    'championship': 'Championship Series',
}

def load_csv(path):
    if not os.path.exists(path): return []
    with open(path, encoding='utf-8', errors='replace') as f:
        return list(csv.DictReader(f))

def ip_str(ipouts):
    return f"{ipouts//3}.{ipouts%3}"

def build_year(year, gameinfo_rows, batting_rows, pitching_rows, teamstats_rows, plays_rows):
    yr = str(year)
    
    # Filter to this year
    games  = [r for r in gameinfo_rows  if yr in r['gid'][:7]]
    bats   = [r for r in batting_rows   if yr in r['gid'][:7] and r.get('stattype')=='value']
    pitches= [r for r in pitching_rows  if yr in r['gid'][:7] and r.get('stattype')=='value']
    ts     = {(r['gid'],r['team']): r for r in teamstats_rows if yr in r['gid'][:7] and r.get('stattype')=='value'}
    plays  = [r for r in plays_rows     if yr in r['gid'][:7]]
    
    if not games: return None

    # Build batting/pitching indexes by gid
    bat_by_gid = defaultdict(list)
    for r in bats: bat_by_gid[r['gid']].append(r)
    pit_by_gid = defaultdict(list)
    for r in pitches: pit_by_gid[r['gid']].append(r)
    plays_by_gid = defaultdict(list)
    for r in plays: plays_by_gid[r['gid']].append(r)

    # Starter handedness and positions from plays
    starter_hand = {}  # gid -> {team: hand}
    gid_pos = {}       # gid -> {pid: pos_str}
    for r in plays:
        gid = r['gid']
        if gid not in starter_hand: starter_hand[gid] = {}
        ph = r.get('pithand','')
        pt = r.get('pitteam','')
        if ph and pt and pt not in starter_hand[gid]:
            starter_hand[gid][pt] = ph
        # Extract starting lineup positions from first play per game
        if gid not in gid_pos and r.get('l1'):
            gid_pos[gid] = {}
            # Batting team positions (l1-l9 / lf1-lf9)
            for slot in range(1, 10):
                pid = r.get(f'l{slot}','')
                fld = r.get(f'lf{slot}','')
                if pid and fld:
                    gid_pos[gid][pid] = POS.get(int(fld), fld) if fld.isdigit() else fld
            # Fielding team positions (f2-f9 = C,1B,2B,3B,SS,LF,CF,RF)
            fpos = {2:'C',3:'1B',4:'2B',5:'3B',6:'SS',7:'LF',8:'CF',9:'RF'}
            for fnum, fname in fpos.items():
                pid = r.get(f'f{fnum}','')
                if pid and pid not in gid_pos[gid]:
                    gid_pos[gid][pid] = fname
            # Pitcher from pitteam
            pitcher = r.get('pitcher','')
            if pitcher and pitcher not in gid_pos[gid]:
                gid_pos[gid][pitcher] = 'P'

    # Build series: group games by round and matchup
    series_map = defaultdict(lambda: defaultdict(list))  # round -> frozenset(teams) -> [gids]
    for g in games:
        rnd = g['gametype']
        pair = frozenset([g['visteam'], g['hometeam']])
        series_map[rnd][pair].append(g['gid'])

    # Build box scores
    box_scores = {}
    for g in games:
        gid = g['gid']
        vis, hom = g['visteam'], g['hometeam']
        vts = ts.get((gid, vis), {})
        hts = ts.get((gid, hom), {})

        def make_team_box(team_code, side, team_ts):
            b_rows = [r for r in bat_by_gid.get(gid,[]) if r['team']==team_code]
            p_rows = [r for r in pit_by_gid.get(gid,[]) if r['team']==team_code]
            b_rows.sort(key=lambda r: (si(r.get('b_seq',99)), si(r.get('b_lp',99))))
            p_rows.sort(key=lambda r: si(r.get('p_seq',99)))

            lineup, bench, bullpen = [], [], []
            seen_lp = set()
            for r in b_rows:
                lp = si(r.get('b_lp',0)) or si(r.get('b_seq',0))
                pid = r.get('id','')
                nm = _BIO.get(pid, {}).get('name', pid)
                bio = _BIO.get(pid, {})
                entry = {
                    'lp': lp, 'n': nm, 'id': pid,
                    'bt': bio.get('bt',''), 'born': bio.get('born',''),
                    'ph': starter_hand.get(gid,{}).get(g['hometeam'] if side=='v' else g['visteam'],''),
                    'pos': gid_pos.get(gid,{}).get(pid, ''),
                    'p': gid_pos.get(gid,{}).get(pid,'') == 'P',
                    'ab': si(r['b_ab']), 'h': si(r['b_h']),
                    'd': si(r['b_d']), 't': si(r['b_t']),
                    'hr': si(r['b_hr']), 'rbi': si(r['b_rbi']),
                    'bb': si(r['b_w']), 'k': si(r['b_k']),
                    'sb': si(r['b_sb']), 'cs': si(r['b_cs']),
                }
                if not lp:
                    # No lineup position - skip (incomplete data)
                    continue
                if lp not in seen_lp:
                    seen_lp.add(lp)
                    lineup.append(entry)
                else:
                    entry['a'] = True
                    # Set pos for pinch hitters/runners
                    if r.get('ph') == 'Y': entry['pos'] = 'PH'
                    elif r.get('pr') == 'Y': entry['pos'] = 'PR'
                    bench.append(entry)

            for r in p_rows:
                bio = _BIO.get(r.get('id',''), {})
                bullpen.append({
                    'n': _BIO.get(r.get('id',''),{}).get('name', r.get('id','')), 'id': r.get('id',''),
                    'th': bio.get('th',''), 'born': bio.get('born',''),
                    'ip': ip_str(si(r['p_ipouts'])), 'ipouts': si(r['p_ipouts']),
                    'h': si(r['p_h']), 'r': si(r['p_r']), 'er': si(r['p_er']),
                    'bb': si(r['p_w']), 'k': si(r['p_k']),
                    'dec': 'W' if r.get('wp')=='1' else ('L' if r.get('lp')=='1' else ('S' if r.get('save')=='1' else '')),
                })

            innings = [team_ts.get(f'inn{i}','') for i in range(1,10)]
            extra   = [team_ts.get(f'inn{i}','') for i in range(10,29) if team_ts.get(f'inn{i}','')]
            return {
                'l': lineup, 'b': bench, 'p': bullpen,
                'i': innings + extra,
                'r': si(team_ts.get('b_r',0)),
                'h': si(team_ts.get('b_h',0)),
                'e': si(team_ts.get('d_e',0)),
            }

        box_scores[gid] = {
            'gid': gid, 'd': g['date'], 'v': vis, 'h': hom,
            'gt': g['gametype'],
            'vb': make_team_box(vis, 'v', vts),
            'hb': make_team_box(hom, 'h', hts),
        }

    # Build series summaries with wins per team
    series_list = []
    for rnd in ROUND_ORDER:
        if rnd not in series_map: continue
        for pair, gids in series_map[rnd].items():
            teams = list(pair)
            wins = defaultdict(int)
            game_entries = []
            for gid in sorted(gids, key=lambda g: box_scores.get(g,{}).get('d','')):
                box = box_scores.get(gid,{})
                vr = box.get('vb',{}).get('r',0)
                hr = box.get('hb',{}).get('r',0)
                winner = box['h'] if hr > vr else box['v']
                wins[winner] += 1
                game_entries.append({
                    'gid': gid,
                    'd': box.get('d',''),
                    'v': box.get('v',''), 'vr': vr,
                    'h': box.get('h',''), 'hr': hr,
                    'w': winner,
                })
            # Determine series winner (most wins, max 4)
            sw = max(wins, key=lambda t: wins[t]) if wins else teams[0]
            sl = [t for t in teams if t != sw][0] if len(teams) > 1 else ''
            lg = league(teams[0])
            series_list.append({
                'round': rnd,
                'label': ROUND_LABEL.get(rnd, rnd),
                'lg': lg,
                'teams': teams,
                'winner': sw,
                'loser': sl,
                'wins': {sw: wins[sw], sl: wins[sl]},
                'games': game_entries,
            })

    # Sort series by round order then by league
    series_list.sort(key=lambda s: (ROUND_ORDER.index(s['round']) if s['round'] in ROUND_ORDER else 99, s['lg']))

    # Find champion (WS winner)
    champion = ''
    for s in series_list:
        if s['round'] == 'worldseries':
            champion = s['winner']
            break

    return {
        'year': yr,
        'champion': champion,
        'series': series_list,
        'box_scores': box_scores,
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # Load all CSVs once
    print("Loading postseason data files...")
    gameinfo  = load_csv(os.path.join(POSTSEASON_DIR, 'gameinfo.csv'))
    batting   = load_csv(os.path.join(POSTSEASON_DIR, 'batting.csv'))
    pitching  = load_csv(os.path.join(POSTSEASON_DIR, 'pitching.csv'))
    teamstats = load_csv(os.path.join(POSTSEASON_DIR, 'teamstats.csv'))
    plays     = load_csv(os.path.join(POSTSEASON_DIR, 'plays.csv'))
    print(f"  {len(gameinfo)} games, {len(batting)} batting rows, {len(pitching)} pitching rows")

    # Get all years
    all_years = sorted(set(int(r['gid'][3:7]) for r in gameinfo if len(r.get('gid','')) >= 7))
    
    if len(sys.argv) > 1:
        all_years = [int(a) for a in sys.argv[1:]]

    print(f"\nBuilding {len(all_years)} postseason(s)...\n")
    ok = 0
    for year in all_years:
        try:
            data = build_year(year, gameinfo, batting, pitching, teamstats, plays)
            if not data:
                print(f"  SKIP {year}: no games found")
                continue
            out = os.path.join(OUT_DIR, f'{year}.json')
            with open(out, 'w') as f:
                json.dump(data, f, separators=(',',':'))
            ns = len(data['series'])
            nb = len(data['box_scores'])
            print(f"  OK   {year}: {ns} series, {nb} games → {os.path.getsize(out)/1024:.0f} KB")
            ok += 1
        except Exception as e:
            import traceback
            print(f"  FAIL {year}: {e}")
            traceback.print_exc()

    # Write manifest.json for fast home page loading
    manifest = {}
    for yr in sorted(os.listdir(OUT_DIR)):
        if not yr.endswith('.json') or yr == 'manifest.json': continue
        try:
            with open(os.path.join(OUT_DIR, yr)) as f:
                d = json.load(f)
            manifest[d['year']] = {'champion': d.get('champion','')}
        except: pass
    with open(os.path.join(OUT_DIR, 'manifest.json'), 'w') as f:
        json.dump(manifest, f, separators=(',',':'))
    print(f"  manifest.json: {len(manifest)} seasons")
    print(f"\nDone: {ok} seasons built → {os.path.abspath(OUT_DIR)}/")

if __name__ == '__main__':
    main()
