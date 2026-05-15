#!/usr/bin/env python3
"""
MLB Yearbook — Batch Season Builder
Builds data/YEAR.json for every season in one run.

Expected folder layout (edit BASE_DIR and subfolder paths below):
  D:/baseball stuff/
    1940/          <- season data (CSVs, ROS files, TEAM file)
    1941/
    ...
    2025/
    OD rosters/
      OpeningDay-1940.txt
      OpeningDay-1941.txt
      ...
    transactions/
      Transactions-1940.txt
      Transactions-1941.txt
      ...

Usage:
    python build_all_seasons.py

Output:  data/YEAR.json  for each season
"""

import csv, json, glob, os, sys, traceback
from collections import defaultdict
from datetime import datetime

# ── Configuration ───────────────────────────────────────────────────────────
BASE_DIR        = r"D:\baseball stuff"          # root folder
SEASONS_DIR     = BASE_DIR                       # where 1940\, 1941\, ... live
OD_DIR          = os.path.join(BASE_DIR, "OD rosters")
TXN_DIR         = os.path.join(BASE_DIR, "transactions")
OUT_DIR         = "data_v2"                      # output JSON folder (relative to this script)
BIO_FILE    = os.path.join(BASE_DIR, "biofile0.csv")  # Retrosheet biofile

# Load bio handedness once at startup
_BIO_HAND = {}
if os.path.exists(BIO_FILE):
    with open(BIO_FILE, encoding='utf-8', errors='replace') as _bf:
        for _row in csv.DictReader(_bf):
            _pid = _row['id'].strip()
            _first = (_row.get('usename') or _row.get('firstname','')).strip()
            _last  = _row.get('lastname','').strip()
            _BIO_HAND[_pid] = {'bt': _row.get('bats','').strip(),
                               'th': _row.get('throws','').strip(),
                               'born': _row.get('birthdate','').strip(),
                               'name': f"{_first} {_last}".strip() or _pid}

# Team code aliases: OD rosters/transactions sometimes differ from TEAM files
# Static aliases: OD/transaction code -> TEAM file code (year-independent)
TEAM_ALIAS = {
    # Historic franchise aliases
    'ML4':  'MIL',  # Milwaukee Brewers (AL era 1969-71)
    'ML1':  'MLN',  # Milwaukee Braves
    'SEP':  'SE1',  # Seattle Pilots 1969
    'WSA':  'WS2',  # Washington expansion Senators 1961-71
    # Modern aliases - OD files use these, TEAM files use Retrosheet codes
    'CHW':  'CHA',  # Chicago White Sox
    'CHC':  'CHN',  # Chicago Cubs
    'NYY':  'NYA',  # New York Yankees
    'NYG':  'NY1',  # New York Giants (pre-1958)
    'SLB':  'SLA',  # St. Louis Browns
    'SLC':  'SLN',  # St. Louis Cardinals (some years)
    'STL':  'SLN',  # St. Louis Cardinals (modern)
    'WSH':  'WS1',  # Washington Senators (original)
    'LAD':  'LAN',  # Los Angeles Dodgers
    'SDP':  'SDN',  # San Diego Padres
    'SFG':  'SFN',  # San Francisco Giants
    'TBR':  'TBA',  # Tampa Bay Rays
    'KCR':  'KCA',  # Kansas City Royals (modern OD code)
    'NYM':  'NYN',  # New York Mets (modern OD code)
    'WSN':  'WAS',  # Washington Nationals
}

# Year-dependent aliases (same OD code maps to different TEAM codes by era)
def get_alias(code, year):
    y = int(year)
    # KCA in OD = Athletics 1955-67; Royals use KCA in TEAM from 1969+
    if code == 'KCA' and y <= 1967:
        return 'KC1'
    # FLO IS the TEAM code 1993-2011; became MIA from 2012
    if code == 'FLO' and y >= 2012:
        return 'MIA'
    # LAA in OD = expansion Angels 1961-64 (TEAM also LAA, no alias needed)
    #           = modern Angels 2005+ (TEAM uses ANA)
    if code == 'LAA' and y >= 1997:
        return 'ANA'
    return TEAM_ALIAS.get(code, code)


FIRST_YEAR  = 1915
LAST_YEAR       = 2025

# ── Helpers ──────────────────────────────────────────────────────────────────
POS_NAMES = {1:'P',2:'C',3:'1B',4:'2B',5:'3B',6:'SS',7:'LF',8:'CF',9:'RF',
             10:'DH',11:'PH',12:'PR'}

import re as _re

def _load_bio(bio_file):
    """Load birthdate lookup from Retrosheet biofile."""
    bio_raw, bio_norm = {}, {}
    def _norm(name):
        suffix = '_jr' if _re.search(r'\bJr\.?\b', name) else ('_sr' if _re.search(r'\bSr\.?\b', name) else '')
        n = _re.sub(r'\b(Jr\.?|Sr\.?|II|III|IV|V)\b', '', name)
        n = _re.sub(r'\.', '', n); n = _re.sub(r'\s+', ' ', n).strip()
        parts = n.split(); result = []; i = 0
        while i < len(parts):
            if len(parts[i])==1 and i+1<len(parts) and len(parts[i+1])==1:
                result.append(parts[i]+parts[i+1]); i += 2
            else:
                result.append(parts[i]); i += 1
        return ' '.join(result) + suffix
    if not os.path.exists(bio_file):
        return bio_raw, bio_norm
    with open(bio_file, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            name = f"{row['usename'].strip()} {row['lastname'].strip()}"
            bd = row['birthdate'].strip()
            if bd and len(bd) == 8:
                bio_raw[name] = bd
                nn = _norm(name)
                if nn not in bio_norm: bio_norm[nn] = bd
    return bio_raw, bio_norm

_BIO_RAW, _BIO_NORM = None, None
def _get_birth(name):
    global _BIO_RAW, _BIO_NORM
    if _BIO_RAW is None: _BIO_RAW, _BIO_NORM = _load_bio(BIO_FILE)
    if name in _BIO_RAW: return _BIO_RAW[name]
    def _norm(name):
        suffix = '_jr' if _re.search(r'\bJr\.?\b', name) else ('_sr' if _re.search(r'\bSr\.?\b', name) else '')
        n = _re.sub(r'\b(Jr\.?|Sr\.?|II|III|IV|V)\b', '', name)
        n = _re.sub(r'\.', '', n); n = _re.sub(r'\s+', ' ', n).strip()
        parts = n.split(); result = []; i = 0
        while i < len(parts):
            if len(parts[i])==1 and i+1<len(parts) and len(parts[i+1])==1:
                result.append(parts[i]+parts[i+1]); i += 2
            else:
                result.append(parts[i]); i += 1
        return ' '.join(result) + suffix
    return _BIO_NORM.get(_norm(name))

def safe_int(v, default=0):
    try: return int(v) if v and str(v).strip() else default
    except: return default

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
    runs = safe_int(r.get('runs',0))
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
            'sv':safe_int(r.get('score_v',0)),'sh':safe_int(r.get('score_h',0)),
            'rob':_rob(bool(r.get('br1_pre')),bool(r.get('br2_pre')),bool(r.get('br3_pre'))),
            'bat':nm(r.get('batter','')), 'pit':nm(r.get('pitcher','')),
            'np':r.get('nump','') or '',
            'cnt':f"{r.get('balls','')}-{r.get('strikes','')}",
            'runs':safe_int(r.get('runs',0)),
            'desc':full_desc,
        })
    return result

# ── Core builder ─────────────────────────────────────────────────────────────
def build_season(year):
    y = str(year)
    data_dir  = os.path.join(SEASONS_DIR, y)
    od_file   = os.path.join(OD_DIR,  f"OpeningDay-{y}.txt")
    txn_file  = os.path.join(TXN_DIR, f"Transactions-{y}.txt")
    out_path  = os.path.join(OUT_DIR,  f"{y}.json")

    # ── validation ──
    missing = [p for p in [data_dir, od_file, txn_file] if not os.path.exists(p)]
    if missing:
        print(f"  SKIP {y}: missing {', '.join(missing)}")
        return False

    # ── rosters ──
    ros_pos, roster = {}, {}
    for rf in glob.glob(os.path.join(data_dir, '*.ROS')):
        with open(rf, encoding='utf-8', errors='replace') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) >= 7:
                    pid  = parts[0].strip()
                    name = f"{parts[2].strip()} {parts[1].strip()}"
                    pos  = parts[6].strip()
                    if name not in ros_pos: ros_pos[name] = pos
                    if pid  not in roster:  roster[pid]  = {'name': name, 'pos': pos}

    # ── teams ──
    teams = {}
    team_file = os.path.join(data_dir, f'TEAM{y}')
    with open(team_file, encoding='utf-8', errors='replace') as f:
        for line in f:
            parts = line.strip().split(',')
            if len(parts) >= 4:
                code, league_raw = parts[0].strip(), parts[1].strip()
                city, name       = parts[2].strip(), parts[3].strip()
                league = 'AL' if league_raw in ('A','AL') else \
                         ('NL' if league_raw in ('N','NL') else None)
                if league:
                    teams[code] = {'league': league, 'city': city,
                                   'name': name, 'full': f"{city} {name}"}
    # ── team name overrides for historical accuracy ──
    NAME_OVERRIDES = {
        ('HOU', 1962): ('Houston', 'Colt .45s'),
        ('HOU', 1963): ('Houston', 'Colt .45s'),
        ('HOU', 1964): ('Houston', 'Colt .45s'),
        ('WS2', 1961): ('Washington', 'Senators'),
        ('WS2', 1962): ('Washington', 'Senators'),
        ('WS2', 1963): ('Washington', 'Senators'),
        ('WS2', 1964): ('Washington', 'Senators'),
        ('WS2', 1965): ('Washington', 'Senators'),
        ('WS2', 1966): ('Washington', 'Senators'),
        ('WS2', 1967): ('Washington', 'Senators'),
        ('WS2', 1968): ('Washington', 'Senators'),
        ('WS2', 1969): ('Washington', 'Senators'),
        ('WS2', 1970): ('Washington', 'Senators'),
        ('WS2', 1971): ('Washington', 'Senators'),
    }
    for (code_ov, yr_ov), (city_ov, name_ov) in NAME_OVERRIDES.items():
        if code_ov in teams and int(y) == yr_ov:
            teams[code_ov]['city'] = city_ov
            teams[code_ov]['name'] = name_ov
            teams[code_ov]['full'] = f"{city_ov} {name_ov}"
    ML_TEAMS = set(teams.keys())
    if not ML_TEAMS:
        print(f"  SKIP {y}: no teams found in TEAM{y}")
        return False

    # ── opening day rosters ──
    opening_day = defaultdict(set)
    with open(od_file, encoding='utf-8', errors='replace') as f:
        next(f)
        for line in f:
            parts = [p.strip() for p in line.strip().split(',')]
            if len(parts) >= 4 and parts[0] == 'Opening Day':
                raw_t, player = parts[2].strip(), parts[3].strip()
                team = get_alias(raw_t, y)
                if team in ML_TEAMS:
                    opening_day[team].add(player)
    # ── transactions ──
    transactions, seen = [], set()
    with open(txn_file, encoding='utf-8', errors='replace') as f:
        next(f)
        for line in f:
            parts = [p.strip().strip('"') for p in line.strip().split(',')]
            if len(parts) < 5: continue
            try:   date = datetime.strptime(parts[0].strip(), '%m/%d/%Y')
            except: continue
            txn_type, player = parts[1].strip(), parts[2].strip()
            from_team = get_alias(parts[3].strip(), y)
            to_team   = get_alias(parts[4].strip(), y)
            key = (date, txn_type, player, from_team, to_team)
            if key not in seen:
                seen.add(key)
                transactions.append({'date': date, 'type': txn_type,
                                     'player': player, 'from': from_team, 'to': to_team})
    transactions.sort(key=lambda x: x['date'])

    # ── game dates ──
    gameinfo_path = os.path.join(data_dir, f'{y}gameinfo.csv')
    game_dates_raw = []
    with open(gameinfo_path, encoding='utf-8', errors='replace') as f:
        dates_seen = set()
        for row in csv.DictReader(f):
            if (row['gametype'] in ('regular','playoff')
                    and row['visteam'] in ML_TEAMS
                    and row['hometeam'] in ML_TEAMS):
                d = row['date']
                if d not in dates_seen:
                    dates_seen.add(d)
                    game_dates_raw.append(datetime.strptime(d, '%Y%m%d'))
    game_dates_raw.sort()

    # ── roster snapshots ──
    current_active = {t: set(p) for t, p in opening_day.items()}
    txn_idx = 0
    roster_by_date = {}
    for gdate in game_dates_raw:
        while txn_idx < len(transactions) and transactions[txn_idx]['date'] <= gdate:
            t = transactions[txn_idx]; txn_idx += 1
            if t['type'] == 'activate':
                if t['from'] in ML_TEAMS: current_active[t['from']].add(t['player'])
            elif t['type'] == 'deactivate':
                if t['from'] in ML_TEAMS: current_active[t['from']].discard(t['player'])
            elif t['type'] == 'trade':
                if t['from'] in ML_TEAMS: current_active[t['from']].discard(t['player'])
                if t['to']   in ML_TEAMS: current_active[t['to']].add(t['player'])
        # Build snapshot - also store under reverse aliases so game-data codes always match
        snap = {t: sorted(p) for t, p in current_active.items()}
        # Add entries for alias targets: if game uses 'SEP' but roster stored under 'SEA',
        # also store under 'SEP' so lookup works either way
        _REV = {}  # reverse: alias_target -> [alias_source, ...]
        for alias_src, alias_tgt in TEAM_ALIAS.items():
            _REV.setdefault(alias_tgt, []).append(alias_src)
        for tgt, srcs in _REV.items():
            if tgt in snap:
                for s in srcs:
                    if s not in snap:
                        snap[s] = snap[tgt]
        # Year-aware reverse aliases
        if int(y) <= 1967 and 'KC1' in snap and 'KCA' not in snap:
            snap['KCA'] = snap['KC1']
        if int(y) >= 2012 and 'MIA' in snap and 'FLO' not in snap:
            snap['FLO'] = snap['MIA']
        if int(y) >= 1997 and 'ANA' in snap and 'LAA' not in snap:
            snap['LAA'] = snap['ANA']
        roster_by_date[gdate.strftime('%Y%m%d')] = snap

    # ── load game data ──
    def load_csv(name):
        path = os.path.join(data_dir, f'{y}{name}.csv')
        rows = []
        with open(path, encoding='utf-8', errors='replace') as f:
            for row in csv.DictReader(f):
                rows.append(row)
        return rows

    teamstats = {}
    for row in load_csv('teamstats'):
        if row['stattype'] == 'value':
            teamstats[(row['gid'], row['team'])] = row

    batting_by_game = defaultdict(list)
    for row in load_csv('batting'):
        if row['stattype'] == 'value' and row.get('b_lp',''):
            batting_by_game[row['gid']].append(row)

    pitching_by_game = defaultdict(list)
    for row in load_csv('pitching'):
        if row['stattype'] == 'value':
            pitching_by_game[row['gid']].append(row)

    # Build per-game starter handedness lookup: gid -> {team: hand}
    gid_starter_hand = {}
    for gid_p, rows_p in pitching_by_game.items():
        for pr in rows_p:
            if pr.get('p_gs') == '1':
                team_p = pr.get('team','')
                hand_p = _BIO_HAND.get(pr.get('id',''), {}).get('th', '')
                if team_p and hand_p:
                    if gid_p not in gid_starter_hand:
                        gid_starter_hand[gid_p] = {}
                    gid_starter_hand[gid_p][team_p] = hand_p

    fielding_pos = {}
    for row in load_csv('fielding'):
        if row.get('d_seq') == '1' and row.get('d_pos',''):
            try: fielding_pos[(row['gid'], row['id'])] = POS_NAMES.get(int(row['d_pos']), '?')
            except: pass

    # ── substitution chains from plays.csv ──
    gid_subs = {}
    plays_path = os.path.join(data_dir, f'{y}plays.csv')
    if os.path.exists(plays_path):
        plays_by_game = defaultdict(list)
        pitch_counts = defaultdict(lambda: defaultdict(int))
        with open(plays_path, encoding='utf-8', errors='replace') as f:
            for row in csv.DictReader(f):
                if row.get('gametype') in ('regular','playoff'):
                    plays_by_game[row['gid']].append(row)
                    if row.get('pa')=='1' and row.get('nump','').isdigit():
                        pitch_counts[row['gid']][row['pitcher']] += int(row['nump'])
        for gid_p, prows in plays_by_game.items():
            subs_v, subs_h = {}, {}
            for side, subs_d in [('0', subs_v), ('1', subs_h)]:
                plays = [r for r in prows if r.get('top_bot') == side]
                prev = {}
                for r in plays:
                    inning = safe_int(r.get('inning', 0))
                    for slot in range(1, 10):
                        pid = r.get(f'l{slot}', '')
                        if not pid: continue
                        if slot not in prev:
                            subs_d[slot] = [(pid, 0)]
                            prev[slot] = pid
                        elif pid != prev[slot]:
                            subs_d[slot].append((pid, inning))
                            prev[slot] = pid
            v_out = {str(s): [{'id':p,'n':roster.get(p,{}).get('name',p),'i':i}
                               for p,i in chain[1:]]
                     for s, chain in subs_v.items() if len(chain) > 1}
            h_out = {str(s): [{'id':p,'n':roster.get(p,{}).get('name',p),'i':i}
                               for p,i in chain[1:]]
                     for s, chain in subs_h.items() if len(chain) > 1}
            if v_out or h_out:
                gid_subs[gid_p] = {'v': v_out, 'h': h_out}

    games_raw = []
    with open(gameinfo_path, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            if (row['gametype'] in ('regular','playoff')
                    and row['visteam'] in ML_TEAMS
                    and row['hometeam'] in ML_TEAMS):
                games_raw.append(row)

    # ── box score builder ──
    def get_pos(gid, pid): return fielding_pos.get((gid, pid), '?')

    def build_team_box(gid, team, date_str):
        bat_rows   = [r for r in batting_by_game[gid] if r['team'] == team]
        pitch_rows = sorted([r for r in pitching_by_game[gid] if r['team'] == team],
                            key=lambda x: safe_int(x['p_seq']))
        ts = teamstats.get((gid, team), {})

        starters, sub_bat = {}, {}
        for r in bat_rows:
            lp, seq = safe_int(r['b_lp']), safe_int(r['b_seq'])
            if not lp: continue
            if seq == 1: starters[lp] = r
            else:
                nm = roster.get(r['id'], {}).get('name', r['id'])
                if nm not in sub_bat: sub_bat[nm] = r

        lineup, lineup_names = [], set()
        for lp in sorted(starters.keys()):
            r   = starters[lp]
            pid = r['id']
            pos = get_pos(gid, pid)
            nm  = roster.get(pid, {}).get('name', pid)
            lineup_names.add(nm)
            is_p = (pos == 'P')
            entry = {'lp': lp, 'n': nm, 'id': r['id'], 'bt': _BIO_HAND.get(r['id'], {}).get('bt', ''), 'born': _BIO_HAND.get(r['id'], {}).get('born', ''), 'ph': gid_starter_hand.get(r['gid'], {}).get(r.get('opp',''), ''), 'pos': pos, 'p': is_p,
                     'ab': safe_int(r['b_ab']), 'h': safe_int(r['b_h']),
                     'bb': safe_int(r['b_w']),  'k': safe_int(r['b_k']),
                     'hr': safe_int(r['b_hr']), 'rbi': safe_int(r['b_rbi']),
                     'd': safe_int(r['b_d']),   't': safe_int(r['b_t']),
                     'sb': safe_int(r['b_sb']), 'cs': safe_int(r['b_cs']),
                     'bt': _BIO_HAND.get(r['id'], {}).get('bt', '')}
            lineup.append(entry)

        pitcher_names, pitchers = set(), []
        for r in pitch_rows:
            pid = r['id']
            nm  = roster.get(pid, {}).get('name', pid)
            pitcher_names.add(nm)
            outs = safe_int(r['p_ipouts'])
            ip   = f"{outs//3}.{outs%3}"
            dec  = ('W' if r['wp'] == '1' else
                    'L' if r['lp'] == '1' else
                    'S' if r['save'] == '1' else '')
            pitchers.append({'n': nm, 'id': r['id'], 'th': _BIO_HAND.get(r['id'], {}).get('th', ''), 'born': _BIO_HAND.get(r['id'], {}).get('born', ''), 'ip': ip, 'gs': r['p_gs'] == '1',
                             'h': safe_int(r['p_h']),  'r': safe_int(r['p_r']),
                             'er': safe_int(r['p_er']), 'bb': safe_int(r['p_w']),
                             'k':  safe_int(r['p_k']),  'dec': dec,
                             'np': pitch_counts.get(gid,{}).get(r['id'],0)})

        appeared_batters   = set(sub_bat.keys())
        starter_names      = {p['n'] for p in pitchers if p['gs']}
        appeared_relievers = {n for n in pitcher_names if n not in lineup_names and n not in starter_names}
        active_roster      = set(roster_by_date.get(date_str, {}).get(team, []))
        # Debug: if active_roster is empty and we expect players, check aliases
        if not active_roster:
            # Try all known codes for this team
            _aliases_for = [k for k,v in TEAM_ALIAS.items() if v==team or k==team]
            for _alt in _aliases_for:
                _try = set(roster_by_date.get(date_str, {}).get(_alt, []))
                if _try:
                    active_roster = _try
                    break

        bench = []
        for nm in sorted(active_roster):
            if nm in lineup_names: continue
            if ros_pos.get(nm, '?') == 'P': continue
            ap    = nm in appeared_batters
            pid_b = sub_bat[nm]['id'] if ap and nm in sub_bat else ''
            entry = {'n': nm, 'id': pid_b, 'born': _BIO_HAND.get(pid_b,{}).get('born',''), 'a': ap}
            if ap and nm in sub_bat:
                r = sub_bat[nm]
                entry.update({'ph': gid_starter_hand.get(r['gid'], {}).get(r.get('opp',''), ''), 'ab': safe_int(r['b_ab']), 'h': safe_int(r['b_h']),
                              'bb': safe_int(r['b_w']),  'k': safe_int(r['b_k']),
                              'hr': safe_int(r['b_hr']), 'rbi': safe_int(r['b_rbi']),
                              'd': safe_int(r['b_d']),   't': safe_int(r['b_t'])})
            bench.append(entry)

        bullpen = []
        for nm in sorted(active_roster):
            if nm in lineup_names: continue
            if ros_pos.get(nm, '?') != 'P': continue
            ap    = nm in appeared_relievers
            pe_bp = next((p for p in pitchers if p['n'] == nm and not p['gs']), None)
            pid_b = pe_bp['id'] if pe_bp else (next((p for p in pitchers if p['n']==nm),{'id':''}).get('id',''))
            entry = {'n': nm, 'id': pid_b, 'born': _BIO_HAND.get(pid_b,{}).get('born',''), 'a': ap}
            if ap:
                pe = pe_bp
                if pe:
                    entry.update({'ip': pe['ip'], 'h': pe['h'], 'r': pe['r'],
                                  'er': pe['er'], 'bb': pe['bb'], 'k': pe['k'],
                                  'dec': pe['dec']})
            bullpen.append(entry)

        innings = []
        for i in range(1, 16):
            v = ts.get(f'inn{i}', '')
            if v != '':
                innings.append(v)
            else:
                if any(ts.get(f'inn{j}','') != '' for j in range(i+1, 16)):
                    innings.append('')
                else:
                    break

        return {'l': lineup, 'b': bench, 'bp': bullpen, 'p': pitchers,
                'i': innings,
                'r': ts.get('b_r', '0'), 'h': ts.get('b_h', '0'), 'e': ts.get('d_e', '0')}

    # ── assemble output ──
    games_by_date, box_scores = defaultdict(list), {}
    records = defaultdict(lambda: {'w': 0, 'l': 0})

    for g in games_raw:
        date_str  = g['date']
        vis, home = g['visteam'], g['hometeam']
        gid       = g['gid']
        vis_ts    = teamstats.get((gid, vis), {})
        home_ts   = teamstats.get((gid, home), {})
        vis_r     = vis_ts.get('b_r', '?')
        home_r    = home_ts.get('b_r', '?')

        vsp_rows = sorted([r for r in pitching_by_game[gid]
                           if r['team'] == vis and r['p_gs'] == '1'],
                          key=lambda x: safe_int(x['p_seq']))
        hsp_rows = sorted([r for r in pitching_by_game[gid]
                           if r['team'] == home and r['p_gs'] == '1'],
                          key=lambda x: safe_int(x['p_seq']))
        vis_sp  = roster.get(vsp_rows[0]['id'], {}).get('name', '?') if vsp_rows else '?'
        home_sp = roster.get(hsp_rows[0]['id'], {}).get('name', '?') if hsp_rows else '?'

        wteam = g['wteam']
        if wteam == vis:  records[vis]['w']  += 1; records[home]['l'] += 1
        elif wteam == home: records[home]['w'] += 1; records[vis]['l']  += 1

        games_by_date[date_str].append({
            'gid': gid, 'v': vis, 'h': home,
            'vr': vis_r, 'hr': home_r,
            'vsp': vis_sp, 'hsp': home_sp,
            'w': wteam, 'att': g['attendance'],
            'n': g['number'] if g['number'] in ('1', '2') else '',
            'st': g.get('starttime','').strip(),
            'dn': g.get('daynight','').strip(),
            'tp': sum(pitch_counts.get(gid,{}).values())
        })
        _bx_vb = build_team_box(gid, vis,  date_str)
        _bx_hb = build_team_box(gid, home, date_str)
        if gid in gid_subs:
            _s = gid_subs[gid]
            if _s.get('v'): _bx_vb['subs'] = _s['v']
            if _s.get('h'): _bx_hb['subs'] = _s['h']
        _pbp = _build_pbp(plays_by_game.get(gid, []), _BIO_HAND) if plays_by_game.get(gid) else []
        box_scores[gid] = {
            'gid': gid, 'v': vis, 'h': home, 'd': date_str,
            'vb': _bx_vb,
            'hb': _bx_hb,
            'att': g['attendance'],
            'st': g.get('starttime','').strip(),
            'dn': g.get('daynight','').strip(),
            'pbp': _pbp,
        }


    # Build births lookup for all players in this season
    all_player_names = set()
    for bx in box_scores.values():
        for side_key in ['vb','hb']:
            tb = bx[side_key]
            for p in tb['l']+tb['b']+tb['bp']+tb['p']:
                all_player_names.add(p['n'])
    births = {n: _get_birth(n) for n in all_player_names if _get_birth(n)}

    # Pitchers list from ROS files
    pitchers_set = {name for name, pos in ros_pos.items() if pos == 'P'}

    # Write per-game box files: data_v2/boxes/YEAR/GID.json (no PBP)
    boxes_dir = os.path.join(os.path.dirname(out_path), 'boxes', str(y))
    pbp_dir   = os.path.join(os.path.dirname(out_path), 'pbp',   str(y))
    os.makedirs(boxes_dir, exist_ok=True)
    os.makedirs(pbp_dir,   exist_ok=True)
    for gid, box in box_scores.items():
        # Box file — no PBP, stripped zeros
        _tp = sum(pitch_counts.get(gid,{}).values())
        clean_box = {
            'gid': gid, 'd': box['d'], 'v': box['v'], 'h': box['h'],
            'att': box.get('att', ''),
            'st': box.get('st',''),
            'dn': box.get('dn',''),
            'tp': _tp if _tp else 0,
            'vb': _strip(box['vb']),
            'hb': _strip(box['hb']),
        }
        with open(os.path.join(boxes_dir, f'{gid}.json'), 'w', encoding='utf-8') as f:
            json.dump(clean_box, f, separators=(',', ':'))
        # PBP file — array format, optional
        pbp_raw = box.get('pbp', [])
        if pbp_raw:
            pbp_arrays = []
            for p in _clean_pbp(pbp_raw):
                arr = [p.get('i',''), p.get('tb','') or None, p.get('o','0'),
                       p.get('sv',0) or None, p.get('sh',0) or None,
                       p.get('rob','---'), p.get('bat',''), p.get('pit',''),
                       p.get('cnt',''), p.get('runs',0) or None, p.get('desc','')]
                while arr and arr[-1] is None: arr.pop()
                pbp_arrays.append(arr)
            with open(os.path.join(pbp_dir, f'{gid}.json'), 'w', encoding='utf-8') as f:
                json.dump(pbp_arrays, f, separators=(',', ':'))

    # Season file — no box_scores, just schedule/standings/metadata
    output = {
        'season':       y,
        'teams':        teams,
        'dates':        sorted(games_by_date.keys()),
        'games_by_date': dict(games_by_date),
        'records':      dict(records),
        'pitchers':     sorted(pitchers_set),
        'births':       births,
    }
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, separators=(',', ':'))

    size = os.path.getsize(out_path)
    print(f"  OK  {y}: {len(games_raw):>4} games, {len(sorted(games_by_date.keys())):>3} dates "
          f"→ {size/1024/1024:.1f} MB")
    return True


def _strip(obj):
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items()
                if v not in (0, 0.0, '', False, None, [])}
    if isinstance(obj, list):
        return [_strip(i) for i in obj]
    return obj

def _clean_pbp(pbp):
    result = []
    for p in pbp:
        e = {k: v for k, v in p.items()
             if k not in ('np', 'o2') and v not in (0, '', None)}
        if e.get('tb') == '0': del e['tb']
        result.append(e)
    return result

# ── Module-level worker (must be at top level for Windows multiprocessing) ────
def _build_one(y):
    try:
        r = build_season(y)
        return (y, 'ok' if r else 'skip', None)
    except Exception as e:
        import traceback as _tb
        return (y, 'fail', _tb.format_exc())


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    os.makedirs(OUT_DIR, exist_ok=True)

    years = list(range(FIRST_YEAR, LAST_YEAR + 1))

    # Allow running a single year:  python build_all_seasons.py 1987
    if len(sys.argv) > 1:
        years = [int(a) for a in sys.argv[1:]]

    print(f"Building {len(years)} season(s) into {os.path.abspath(OUT_DIR)}/\n")
    ok, skipped, failed = 0, 0, 0

    for year in years:
        try:
            result = build_season(year)
            if result: ok += 1
            else:       skipped += 1
        except Exception as e:
            print(f"  FAIL {year}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\nDone: {ok} built, {skipped} skipped, {failed} failed")
    if ok:
        print(f"JSON files are in: {os.path.abspath(OUT_DIR)}/")
        print("\nNext step — add each season to SEASONS_AVAILABLE in index.html:")
        print("  {year:'YYYY', file:'YYYY.json', champs:{AL:'...', NL:'...'}},")
