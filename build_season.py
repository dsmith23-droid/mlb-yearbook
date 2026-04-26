#!/usr/bin/env python3
"""
MLB Yearbook Season Builder
Usage: python build_season.py YEAR /path/to/season/dir opening_day.txt transactions.txt

Outputs: data/YEAR.json
"""
import csv, json, glob, os, sys
from collections import defaultdict
from datetime import datetime

POS_NAMES = {1:'P',2:'C',3:'1B',4:'2B',5:'3B',6:'SS',7:'LF',8:'CF',9:'RF',10:'DH',11:'PH',12:'PR'}


# Load bio handedness
_BIO_HAND = {}
_bio_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'biofile0.csv')
if not os.path.exists(_bio_file):
    _bio_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'biofile0.csv')
if os.path.exists(_bio_file):
    with open(_bio_file, encoding='utf-8', errors='replace') as _bf:
        for _row in csv.DictReader(_bf):
            _pid = _row['id'].strip()
            _first = (_row.get('usename') or _row.get('firstname','')).strip()
            _last  = _row.get('lastname','').strip()
            _BIO_HAND[_pid] = {'bt': _row.get('bats','').strip(),
                               'th': _row.get('throws','').strip(),
                               'born': _row.get('birthdate','').strip(),
                               'name': f"{_first} {_last}".strip() or _pid}

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


import re as _re, csv as _csv

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


def _get_birth(name, bio_file):
    if not hasattr(_get_birth, "_cache"):
        _get_birth._cache = {}
        if os.path.exists(bio_file):
            def _norm(n):
                suf = '_jr' if _re.search(r'\bJr\.?\b', n) else ('_sr' if _re.search(r'\bSr\.?\b', n) else '')
                n = _re.sub(r'\b(Jr\.?|Sr\.?|II|III|IV|V)\b', '', n)
                n = _re.sub(r'\.', '', n); n = _re.sub(r'\s+', ' ', n).strip()
                p = n.split(); r2 = []; i = 0
                while i < len(p):
                    if len(p[i])==1 and i+1<len(p) and len(p[i+1])==1: r2.append(p[i]+p[i+1]); i+=2
                    else: r2.append(p[i]); i+=1
                return ' '.join(r2) + suf
            with open(bio_file, encoding='utf-8', errors='replace') as f2:
                raw = {}; norm = {}
                for row in _csv.DictReader(f2):
                    nm = f"{row['usename'].strip()} {row['lastname'].strip()}"
                    bd = row['birthdate'].strip()
                    if bd and len(bd)==8:
                        raw[nm] = bd
                        nn = _norm(nm)
                        if nn not in norm: norm[nn] = bd
            _get_birth._cache = (raw, norm, _norm)
    cache = _get_birth._cache
    if not isinstance(cache, tuple): return None
    raw, norm, _norm = cache
    return raw.get(name) or norm.get(_norm(name))

def build_season(year, data_dir, opening_day_file, transactions_file):
    year = str(year)
    print(f"Building {year}...")

    ros_pos, roster = {}, {}
    for rf in glob.glob(os.path.join(data_dir, '*.ROS')):
        with open(rf) as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) >= 7:
                    pid = parts[0].strip()
                    name = f"{parts[2].strip()} {parts[1].strip()}"
                    pos = parts[6].strip()
                    if name not in ros_pos: ros_pos[name] = pos
                    if pid not in roster: roster[pid] = {'name': name, 'pos': pos}

    teams = {}
    with open(os.path.join(data_dir, f'TEAM{year}')) as f:
        for line in f:
            parts = line.strip().split(',')
            if len(parts) >= 4:
                code, league_raw = parts[0].strip(), parts[1].strip()
                city, name = parts[2].strip(), parts[3].strip()
                league = 'AL' if league_raw in ('A','AL') else ('NL' if league_raw in ('N','NL') else None)
                if league:
                    teams[code] = {'league': league, 'city': city, 'name': name, 'full': f"{city} {name}"}
    # ── team name overrides for historical accuracy ──
    NAME_OVERRIDES = {
        ('HOU', 1962): ('Houston', 'Colt .45s'),
        ('HOU', 1963): ('Houston', 'Colt .45s'),
        ('HOU', 1964): ('Houston', 'Colt .45s'),
    }
    for (code_ov, yr_ov), (city_ov, name_ov) in NAME_OVERRIDES.items():
        if code_ov in teams and int(year) == yr_ov:
            teams[code_ov].update({'city': city_ov, 'name': name_ov, 'full': f"{city_ov} {name_ov}"})
    ML_TEAMS = set(teams.keys())
    print(f"  {len(ML_TEAMS)} teams")

    opening_day = defaultdict(set)
    with open(opening_day_file) as f:
        next(f)
        for line in f:
            parts = [p.strip() for p in line.strip().split(',')]
            if len(parts) >= 4 and parts[0] == 'Opening Day':
                raw_t, player = parts[2].strip(), parts[3].strip()
                team = get_alias(raw_t, y)
                if team in ML_TEAMS: opening_day[team].add(player)
    transactions = []
    seen = set()
    with open(transactions_file) as f:
        next(f)
        for line in f:
            parts = [p.strip().strip('"') for p in line.strip().split(',')]
            if len(parts) < 5: continue
            try: date = datetime.strptime(parts[0].strip(), '%m/%d/%Y')
            except: continue
            txn_type, player = parts[1].strip(), parts[2].strip()
            from_team = get_alias(parts[3].strip(), y)
            to_team   = get_alias(parts[4].strip(), y)
            key = (date, txn_type, player, from_team, to_team)
            seen.add(key)
            transactions.append({'date': date, 'type': txn_type, 'player': player, 'from': from_team, 'to': to_team})
    transactions.sort(key=lambda x: x['date'])

    game_dates_raw = []
    with open(os.path.join(data_dir, f'{year}gameinfo.csv')) as f:
        dates_seen = set()
        for row in csv.DictReader(f):
            if row['gametype'] in ('regular','playoff') and row['visteam'] in ML_TEAMS and row['hometeam'] in ML_TEAMS:
                d = row['date']
                if d not in dates_seen:
                    dates_seen.add(d)
                    game_dates_raw.append(datetime.strptime(d, '%Y%m%d'))
    game_dates_raw.sort()

    current_active = {team: set(players) for team, players in opening_day.items()}
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
                if t['to'] in ML_TEAMS: current_active[t['to']].add(t['player'])
        snap = {t: set(p) for t, p in current_active.items()}
        _REV = {}
        for alias_src, alias_tgt in TEAM_ALIAS.items():
            _REV.setdefault(alias_tgt, []).append(alias_src)
        # Add year-aware aliases to reverse map
        if int(y) <= 1967:
            _REV.setdefault('KC1', []).append('KCA')
        if int(y) >= 2012:
            _REV.setdefault('MIA', []).append('FLO')
        for tgt, srcs in _REV.items():
            if tgt in snap:
                for s in srcs:
                    if s not in snap: snap[s] = snap[tgt]
        # Year-aware reverse aliases
        if int(year) <= 1967 and 'KC1' in snap and 'KCA' not in snap:
            snap['KCA'] = snap['KC1']
        if int(year) >= 2012 and 'MIA' in snap and 'FLO' not in snap:
            snap['FLO'] = snap['MIA']
        if int(year) >= 1997 and 'ANA' in snap and 'LAA' not in snap:
            snap['LAA'] = snap['ANA']
        roster_by_date[gdate.strftime('%Y%m%d')] = snap

    teamstats = {}
    with open(os.path.join(data_dir, f'{year}teamstats.csv')) as f:
        for row in csv.DictReader(f):
            if row['stattype'] == 'value':
                teamstats[(row['gid'], row['team'])] = row

    batting_by_game = defaultdict(list)
    with open(os.path.join(data_dir, f'{year}batting.csv')) as f:
        for row in csv.DictReader(f):
            if row['stattype'] == 'value' and row['b_lp']:
                batting_by_game[row['gid']].append(row)

    pitching_by_game = defaultdict(list)
    with open(os.path.join(data_dir, f'{year}pitching.csv')) as f:
        for row in csv.DictReader(f):
            if row['stattype'] == 'value':
                pitching_by_game[row['gid']].append(row)

    # Build per-game starter handedness: gid -> {team: hand}
    gid_starter_hand = {}
    for gid_p, rows_p in pitching_by_game.items():
        for pr in rows_p:
            if pr.get('p_gs') == '1':
                hand_p = _BIO_HAND.get(pr.get('id',''), {}).get('th', '')
                team_p = pr.get('team','')
                if team_p and hand_p:
                    gid_starter_hand.setdefault(gid_p, {})[team_p] = hand_p

    # ── substitution chains from plays.csv ──
    gid_subs = {}
    plays_path = os.path.join(data_dir, f'{year}plays.csv')
    if os.path.exists(plays_path):
        plays_by_gm = defaultdict(list)
        with open(plays_path, encoding='utf-8', errors='replace') as f:
            for row in csv.DictReader(f):
                if row.get('gametype') in ('regular','playoff'):
                    plays_by_gm[row['gid']].append(row)
        for gid_p, prows in plays_by_gm.items():
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

    fielding_pos = {}
    with open(os.path.join(data_dir, f'{year}fielding.csv')) as f:
        for row in csv.DictReader(f):
            if row['d_seq'] == '1' and row['d_pos']:
                try: fielding_pos[(row['gid'], row['id'])] = POS_NAMES.get(int(row['d_pos']), '?')
                except: pass

    games_raw = []
    with open(os.path.join(data_dir, f'{year}gameinfo.csv')) as f:
        for row in csv.DictReader(f):
            if row['gametype'] in ('regular','playoff') and row['visteam'] in ML_TEAMS and row['hometeam'] in ML_TEAMS:
                games_raw.append(row)

    def get_pos(gid, pid): return fielding_pos.get((gid, pid), '?')

    def build_team_box(gid, team, date_str):
        bat_rows = [r for r in batting_by_game[gid] if r['team'] == team]
        pitch_rows = sorted([r for r in pitching_by_game[gid] if r['team'] == team], key=lambda x: safe_int(x['p_seq']))
        ts = teamstats.get((gid, team), {})
        starters, sub_bat_by_name = {}, {}
        for r in bat_rows:
            lp, seq = safe_int(r['b_lp']), safe_int(r['b_seq'])
            if not lp: continue
            if seq == 1: starters[lp] = r
            else:
                name = roster.get(r['id'], {}).get('name', r['id'])
                if name not in sub_bat_by_name: sub_bat_by_name[name] = r
        lineup, lineup_names = [], set()
        for lp in sorted(starters.keys()):
            r = starters[lp]; pid = r['id']
            pos = get_pos(gid, pid); name = roster.get(pid, {}).get('name', pid)
            lineup_names.add(name); is_p = (pos == 'P')
            lineup_names.add(name); is_p = (pos == 'P')
            entry = {'lp': lp, 'n': name, 'id': pid, 'bt': _BIO_HAND.get(pid,{}).get('bt',''), 'born': _BIO_HAND.get(pid,{}).get('born',''), 'ph': gid_starter_hand.get(r['gid'],{}).get(r.get('opp',''),''), 'pos': pos, 'p': is_p,
                     'hr': safe_int(r['b_hr']), 'rbi': safe_int(r['b_rbi']),
                     'd': safe_int(r['b_d']),   't': safe_int(r['b_t']),
                     'sb': safe_int(r['b_sb']), 'cs': safe_int(r['b_cs'])}
        pitcher_names_all = set(); pitchers = []
        for r in pitch_rows:
            pid = r['id']; name = roster.get(pid, {}).get('name', pid)
            pitcher_names_all.add(name)
            outs = safe_int(r['p_ipouts']); ip = f"{outs//3}.{outs%3}"
            dec = 'W' if r['wp']=='1' else ('L' if r['lp']=='1' else ('S' if r['save']=='1' else ''))
            pitchers.append({'n': name, 'id': pid, 'th': _BIO_HAND.get(pid,{}).get('th',''), 'born': _BIO_HAND.get(pid,{}).get('born',''), 'ip': ip, 'gs': r['p_gs']=='1',
                             'h': safe_int(r['p_h']), 'r': safe_int(r['p_r']),
                             'er': safe_int(r['p_er']), 'bb': safe_int(r['p_w']),
                             'k': safe_int(r['p_k']), 'dec': dec})
        # Players who appeared as pinch hitters/runners
        appeared_batters = set(sub_bat_by_name.keys())
        starter_names = {p['n'] for p in pitchers if p['gs']}
        appeared_relievers = {n for n in pitcher_names_all if n not in lineup_names and n not in starter_names}
        # Full active roster from transaction system
        active_roster = roster_by_date.get(date_str, {}).get(team, set())
        if not active_roster:
            for _alt in [k for k,v in TEAM_ALIAS.items() if v==team or k==team]:
                _try = roster_by_date.get(date_str, {}).get(_alt, set())
                if _try:
                    active_roster = _try
                    break
        bench = []
        for name in sorted(active_roster):
            if name in lineup_names: continue
            if ros_pos.get(name, '?') == 'P': continue
            appeared = name in appeared_batters
            pid_bs = sub_bat_by_name[name]['id'] if appeared and name in sub_bat_by_name else ''
            entry = {'n': name, 'id': pid_bs, 'born': _BIO_HAND.get(pid_bs,{}).get('born',''), 'a': appeared}
            if appeared and name in sub_bat_by_name:
                r = sub_bat_by_name[name]
                entry.update({'ph': gid_starter_hand.get(r['gid'], {}).get(r.get('opp',''), ''), 'ab': safe_int(r['b_ab']), 'h': safe_int(r['b_h']),
                              'bb': safe_int(r['b_w']), 'k': safe_int(r['b_k']),
                              'hr': safe_int(r['b_hr']), 'rbi': safe_int(r['b_rbi']),
                              'd': safe_int(r['b_d']),   't': safe_int(r['b_t'])})
            bench.append(entry)
        bullpen = []
        for name in sorted(active_roster):
            if name in lineup_names: continue
            if ros_pos.get(name, '?') != 'P': continue
            appeared = name in appeared_relievers
            pid_bs = sub_bat_by_name[name]['id'] if appeared and name in sub_bat_by_name else ''
            entry = {'n': name, 'id': pid_bs, 'born': _BIO_HAND.get(pid_bs,{}).get('born',''), 'a': appeared}
            if appeared:
                p_entry = next((p for p in pitchers if p['n']==name and not p['gs']), None)
                if p_entry:
                    entry.update({'ip': p_entry['ip'], 'h': p_entry['h'], 'r': p_entry['r'],
                                  'er': p_entry['er'], 'bb': p_entry['bb'], 'k': p_entry['k'],
                                  'dec': p_entry['dec']})
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
                'i': innings, 'r': ts.get('b_r','0'), 'h': ts.get('b_h','0'), 'e': ts.get('d_e','0')}

    games_by_date, box_scores = defaultdict(list), {}
    records = defaultdict(lambda: {'w':0,'l':0})
    for g in games_raw:
        date_str, vis, home, gid = g['date'], g['visteam'], g['hometeam'], g['gid']
        vis_ts = teamstats.get((gid,vis),{}); home_ts = teamstats.get((gid,home),{})
        vis_r, home_r = vis_ts.get('b_r','?'), home_ts.get('b_r','?')
        vsp_rows = sorted([r for r in pitching_by_game[gid] if r['team']==vis and r['p_gs']=='1'], key=lambda x: safe_int(x['p_seq']))
        hsp_rows = sorted([r for r in pitching_by_game[gid] if r['team']==home and r['p_gs']=='1'], key=lambda x: safe_int(x['p_seq']))
        vis_sp = roster.get(vsp_rows[0]['id'],{}).get('name','?') if vsp_rows else '?'
        home_sp = roster.get(hsp_rows[0]['id'],{}).get('name','?') if hsp_rows else '?'
        wteam = g['wteam']
        if wteam==vis: records[vis]['w']+=1; records[home]['l']+=1
        elif wteam==home: records[home]['w']+=1; records[vis]['l']+=1
        games_by_date[date_str].append({'gid':gid,'v':vis,'h':home,'vr':vis_r,'hr':home_r,
            'vsp':vis_sp,'hsp':home_sp,'w':wteam,'att':g['attendance'],
            'n':g['number'] if g['number'] in ('1','2') else ''})
        _bx = {'gid':gid,'v':vis,'h':home,'d':date_str,
            'vb':build_team_box(gid,vis,date_str),'hb':build_team_box(gid,home,date_str),'att':g['attendance']}
        if gid in gid_subs:
            s = gid_subs[gid]
            if s.get('v'): _bx['vb']['subs'] = s['v']
            if s.get('h'): _bx['hb']['subs'] = s['h']
        _bx['pbp'] = _build_pbp(plays_by_gm.get(gid, []), _BIO_HAND)
        box_scores[gid] = _bx

    # Collect all player names for births lookup
    _all = set()
    for bx in box_scores.values():
        for sk in ['vb','hb']:
            tb = bx[sk]
            for p in tb['l']+tb['b']+tb['bp']+tb['p']: _all.add(p['n'])
    _bio_f = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                          os.path.join('..', 'biofile0.csv'))
    births = {n: _get_birth(n,_bio_f) for n in _all if _get_birth(n,_bio_f)}
    pitchers_set = {nm for nm,pos in ros_pos.items() if pos=='P'}
    output = {'season':year,'teams':teams,'dates':sorted(games_by_date.keys()),
              'games_by_date':dict(games_by_date),'box_scores':box_scores,
              'records':dict(records),'pitchers':sorted(pitchers_set),'births':births}
    os.makedirs('data', exist_ok=True)
    out_path = f'data/{year}.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, separators=(',',':'))
    size = os.path.getsize(out_path)
    print(f"  Done → {out_path} ({size/1024/1024:.1f} MB, {len(games_raw)} games)")

if __name__ == '__main__':
    if len(sys.argv) < 5:
        print("Usage: python build_season.py YEAR /path/to/season/dir opening_day.txt transactions.txt")
        sys.exit(1)
    build_season(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
