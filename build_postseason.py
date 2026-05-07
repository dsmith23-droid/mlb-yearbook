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

def _rob(r1, r2, r3):
    return ('1' if r1 else '-')+('2' if r2 else '-')+('3' if r3 else '-')

_FPOS = {'1':'P','2':'C','3':'1B','4':'2B','5':'3B','6':'SS','7':'LF','8':'CF','9':'RF'}
_LOC_ZONE = {
    '7S':'Short LF','7M':'LF','7D':'Deep LF','7LD':'LF Line','7LS':'LF Line',
    '8S':'Short CF','8M':'CF','8D':'Deep CF','8LS':'LF-CF','8RS':'CF-RF',
    '9S':'Short RF','9M':'RF','9D':'Deep RF','9LD':'RF Line','9LS':'RF Line',
    '5S':'3B','5M':'3B','5D':'Deep 3B','5F':'3B Foul',
    '3S':'1B','3M':'1B','3D':'Deep 1B','3F':'1B Foul',
    '4S':'2B','4M':'2B','4D':'2B','6S':'SS','6M':'SS','6D':'SS',
    '2':'C','23':'C-1B','13':'P-1B','78':'LF-CF Gap','89':'CF-RF Gap',
    '34':'1B-2B','56':'SS-3B','46':'2B-SS','15':'3B-1B',
}

def _fseq_str(fseq):
    if not fseq: return ''
    parts = [_FPOS.get(c,c) for c in fseq if c.isdigit()]
    return '-'.join(parts) if parts else ''

def _loc_str(loc):
    loc = loc.rstrip('+-') if loc else ''
    if not loc: return ''
    for l in [loc, loc[:3], loc[:2], loc[:1]]:
        if l in _LOC_ZONE: return 'to ' + _LOC_ZONE[l]
    return ''

def _ev_loc(ev):
    """Extract hit location from event string (e.g. S7->LF, D8->CF, HR/F9->RF)."""
    if not ev: return ''
    base = ev.split('/')[0].split('.')[0]
    mod  = ev.split('/')[1].split('.')[0] if '/' in ev else ''
    # Hits with fielder in base: S7, D9, T8
    for prefix in ['T','D','S']:
        if base.startswith(prefix):
            rest = base[len(prefix):]
            if rest and rest[0].isdigit():
                return _FPOS.get(rest[0], '')
            return ''
    # HR - location in modifier: F9D, F7, etc.
    if base in ('HR','H'):
        m = mod.lstrip('FLGPBfbglp')
        if m and m[0].isdigit():
            return _FPOS.get(m[0], '')
        return ''
    return ''

def _ev_hittype(ev):
    """Get descriptive hit type from event modifier."""
    if '/' not in ev: return ''
    mod = ev.split('/')[1].split('.')[0]
    if mod[:2] in ('BG','BP','BF'): return 'Bunt'
    c = mod[0] if mod else ''
    return {'G':'Ground Ball','F':'Fly Ball','L':'Line Drive','P':'Pop Up'}.get(c,'')

def _abbr(name):
    parts = name.strip().split()
    if len(parts) >= 2:
        return parts[0][0] + '. ' + ' '.join(parts[1:])
    return name

def _decode_play(r):
    sb = []
    if r.get('sb2')=='1': sb.append('SB 2B')
    if r.get('sb3')=='1': sb.append('SB 3B')
    if r.get('sbh')=='1': sb.append('SB Home')
    if r.get('cs2')=='1': sb.append('CS 2B')
    if r.get('cs3')=='1': sb.append('CS 3B')
    if r.get('csh')=='1': sb.append('CS Home')
    if r.get('wp')=='1': sb.append('Wild Pitch')
    if r.get('pb')=='1': sb.append('Passed Ball')
    if r.get('bk')=='1': sb.append('Balk')
    if r.get('pa')!='1' and sb:
        return '; '.join(sb)
    ev   = r.get('event','')
    ht   = r.get('hittype','')
    loc  = r.get('loc','')
    fseq = r.get('fseq','')
    runs = si(r.get('runs',0))
    # Location: prefer loc field (detailed), fall back to event string
    zone = _loc_str(loc)
    if not zone:
        ev_f = _ev_loc(ev)
        if ev_f: zone = 'to ' + ev_f
    fs = _fseq_str(fseq)
    # Hit type: prefer hittype field, fall back to event modifier
    ht_mod = _ev_hittype(ev) if not ht else ''
    ht_desc = {'G':'Ground Ball','F':'Fly Ball','L':'Line Drive','P':'Pop Up'}.get(ht, ht_mod)
    # Bracket hit type if we have it and it adds info
    ht_sfx = f' ({ht_desc})' if ht_desc and ht_desc != 'Bunt' else ''
    if r.get('hr')=='1':
        on = sum(1 for k in ['br1_pre','br2_pre','br3_pre'] if r.get(k))
        desc = ['Solo HR','2-Run HR','3-Run HR','Grand Slam'][min(on,3)]
        if zone: desc += ' ' + zone
    elif r.get('triple')=='1':
        desc = f"Triple{' '+zone if zone else ''}{ht_sfx}"
    elif r.get('double')=='1':
        desc = f"Double{' '+zone if zone else ''}{ht_sfx}"
    elif r.get('single')=='1':
        desc = f"Single{' '+zone if zone else ''}{ht_sfx}"
    elif r.get('walk')=='1':
        desc = 'Intentional Walk' if r.get('iw')=='1' else 'Walk'
    elif r.get('hbp')=='1': desc = 'Hit by Pitch'
    elif r.get('k')=='1':   desc = 'Strikeout'
    elif r.get('roe')=='1': desc = f"Reached on Error{' ('+fs+')' if fs else ''}"
    elif r.get('fc')=='1':  desc = f"Fielder's Choice{' ('+fs+')' if fs else ''}"
    elif r.get('ground')=='1': desc = f"Groundout{': '+fs if fs else ''}"
    elif r.get('fly')=='1':
        desc = f"Flyball{': '+fs if fs else ''}{' '+zone if zone else ''}"
    elif r.get('line')=='1':
        desc = f"Lineout{': '+fs if fs else ''}{' '+zone if zone else ''}"
    elif r.get('bunt')=='1': desc = f"Bunt{' ('+fs+')' if fs else ''}"
    else: desc = f"Out{' ('+fs+')' if fs else ''}"
    if sb: desc += '; ' + '; '.join(sb)
    if runs > 0: desc += f' ({runs}R)'
    return desc

def _runner_advances(r, bio):
    def nm(pid):
        if not pid: return ''
        b = bio.get(pid, {}) if bio else {}
        name = b.get('name', pid)
        return _abbr(name) if ' ' in name else name
    pre = {1: r.get('br1_pre',''), 2: r.get('br2_pre',''), 3: r.get('br3_pre','')}
    post_pids = {r.get(f'br{b}_post',''): b for b in [1,2,3] if r.get(f'br{b}_post','')}
    advances = []
    for base in [1,2,3]:
        pid = pre[base]
        if not pid: continue
        name = nm(pid)
        if r.get(f'run{base}') == '1':
            advances.append(f'{name} Scores')
        elif pid in post_pids:
            dest = post_pids[pid]
            if dest != base:
                advances.append(f'{name} to {dest}B')
    return '; '.join(advances) if advances else ''

def _build_pbp(plays, bio=None):
    result = []
    for r in plays:
        has_base_event = any(r.get(k)=='1' for k in ['sb2','sb3','sbh','cs2','cs3','csh','wp','pb','bk'])
        if r.get('pa')!='1' and not has_base_event:
            continue
        def nm(pid):
            if not pid: return ''
            b = bio.get(pid, {}) if bio else {}
            return b.get('name', pid)
        adv = _runner_advances(r, bio)
        desc = _decode_play(r)
        full_desc = desc + ('; ' + adv if adv else '')
        result.append({
            'i':r.get('inning',''),'tb':r.get('top_bot','0'),
            'o':r.get('outs_pre','0'),'o2':r.get('outs_post','0'),
            'sv':si(r.get('score_v',0)),'sh':si(r.get('score_h',0)),
            'rob':_rob(bool(r.get('br1_pre')),bool(r.get('br2_pre')),bool(r.get('br3_pre'))),
            'bat':nm(r.get('batter','')), 'pit':nm(r.get('pitcher','')),
            'np':r.get('nump','') or '',
            'cnt':f"{r.get('balls','')}-{r.get('strikes','')}",
            'runs':si(r.get('runs',0)),
            'desc':full_desc,
        })
    return result

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

        _pbp = _build_pbp(plays_by_gid.get(gid,[]), _BIO)
        box_scores[gid] = {
            'gid': gid, 'd': g['date'], 'v': vis, 'h': hom,
            'gt': g['gametype'],
            'vb': make_team_box(vis, 'v', vts),
            'hb': make_team_box(hom, 'h', hts),
            'pbp': _pbp,
            'st': g.get('starttime','').strip(),
            'dn': g.get('daynight','').strip(),
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
