#!/usr/bin/env python3
# =============================================================================
#  JPL Fantasy Manager - bouw_players_v2.py
# =============================================================================
#  Vervangt bouw_players.py. Schrijft players.json: het LIVE bestand dat de
#  ploegbouwer en de Worker lezen. Draait twee keer per dag via GitHub Actions.
#
#  WAT ER VERANDERDE TEN OPZICHTE VAN v1
#  De selectie komt niet langer van BSD maar van proleague.be. BSD leverde
#  stilzwijgend verouderde selecties: gestopte spelers (Vertonghen), vertrokken
#  spelers en beloften stonden er nog in, en geen enkel veld in de BSD-data
#  kon ze onderscheiden - niet contract_until, niet market_value, niet
#  availability.
#
#  DE GEMENE DELER
#  Een speler komt enkel in players.json als hij in BEIDE bronnen staat.
#    - enkel Pro League : geen BSD-record, dus geen statistieken, dus geen
#                         punten te berekenen. Valt weg.
#    - enkel BSD        : niet geregistreerd voor de competitie. Valt weg.
#  Posities komen van de Pro League. Die is de officiele registratie.
#
#  PRIJZEN
#  Komen uit fm_basis_v2.json, dat 4x per seizoen bevroren wordt. Een speler
#  die tussentijds bijkomt, wordt geprijsd tegen de BEVROREN verdeling van
#  marktwaarden in zijn positiegroep. Zo verschuift geen enkele bestaande
#  prijs, wat regelset 2.6 vereist.
#
#  Kosten per run: 19 fetches op proleague.be + 20 calls op BSD.
#
#  Gebruik:
#     BSD_KEY=... python3 bouw_players_v2.py --basis fm_basis_v2.json --uit players.json
# =============================================================================

import json
import os
import re
import sys
import time
import difflib
import collections
import unicodedata
import urllib.request

# ----------------------------------------------------------------------------
# CONFIGURATIE
# ----------------------------------------------------------------------------

BUDGET = 100.0            # beslissing van de admins, 27/07/2026

PL_BASE        = 'https://www.proleague.be'
BSD_BASE       = 'https://sports.bzzoiro.com'
LEAGUE_ID      = 14
HUIDIG_SEIZOEN = 1327

UA = {'User-Agent': ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                     '(KHTML, like Gecko) Chrome/126 Safari/537.36')}

POSITIES_NL = {'Doelman': 'G', 'Verdediger': 'D', 'Middenvelder': 'M', 'Aanvaller': 'F'}
GELDIGE_POS = ('G', 'D', 'M', 'F')
QUOTA       = {'G': 2, 'D': 5, 'M': 5, 'F': 3}

CLUBMAP = {
    'cercle-brugge':               'Cercle Brugge',
    'club-brugge':                 'Club Brugge KV',
    'kaa-gent':                    'KAA Gent',
    'krc-genk':                    'KRC Genk',
    'kv-kortrijk':                 'KV Kortrijk',
    'kv-mechelen':                 'KV Mechelen',
    'kvc-westerlo':                'KVC Westerlo',
    'lommel-sk':                   'Lommel SK',
    'oh-leuven':                   'Oud-Heverlee Leuven',
    'raal-la-louviere':            'RAAL La Louvière',
    'royal-antwerp-fc':            'Royal Antwerp FC',
    'royale-union-saint-gilloise': 'Royale Union Saint-Gilloise',
    'rsc-anderlecht':              'RSC Anderlecht',
    'sk-beveren':                  'SK Beveren',
    'sporting-charleroi':          'RC Sporting Charleroi',
    'standard-de-liege':           'Standard Liège',
    'stvv':                        'Sint-Truidense VV',
    'sv-zulte-waregem':            'SV Zulte Waregem',
}

RUIS = {'van', 'de', 'der', 'den', 'el', 'al', 'da', 'do', 'du', 'le', 'la',
        'dos', 'des', 'ben', 'bin', 'ter', 'te', 'op'}


def arg(vlag, standaard):
    if vlag in sys.argv:
        i = sys.argv.index(vlag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return standaard


BASIS_BESTAND = arg('--basis', 'fm_basis_v2.json')
UIT_BESTAND   = arg('--uit',   'players.json')

KEY = os.environ.get('BSD_KEY') or os.environ.get('K')
if not KEY:
    print('FOUT: BSD_KEY ontbreekt in de omgeving.')
    sys.exit(1)


# ----------------------------------------------------------------------------
# NETWERK
# ----------------------------------------------------------------------------

def haal_html(url, pogingen=3):
    for n in range(pogingen):
        try:
            rq = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(rq, timeout=45).read().decode('utf-8', 'replace')
        except Exception as e:
            if n == pogingen - 1:
                print('  FAAL %s -> %s' % (url, e))
                return None
            time.sleep(3)


def bsd(pad, pogingen=3):
    for n in range(pogingen):
        try:
            rq = urllib.request.Request(BSD_BASE + pad, headers={'Authorization': 'Token ' + KEY})
            return json.load(urllib.request.urlopen(rq, timeout=45))
        except Exception as e:
            if n == pogingen - 1:
                print('  FAAL %s -> %s' % (pad, e))
                return None
            time.sleep(3)


# ----------------------------------------------------------------------------
# NAAMVERWERKING EN KOPPELING
# Identiek aan bouw_basis_v2.py. Bewust gedupliceerd in plaats van
# geimporteerd: dit script moet zelfstandig in een workflow kunnen draaien.
# ----------------------------------------------------------------------------

def ontdiakritiseer(s):
    s = unicodedata.normalize('NFKD', s or '')
    return ''.join(c for c in s if not unicodedata.combining(c))


def tokens(naam):
    s = ontdiakritiseer(naam).lower()
    s = s.replace('-', ' ').replace("'", ' ').replace('.', ' ')
    s = re.sub(r'[^a-z ]', ' ', s)
    return [t for t in s.split() if len(t) > 1]


def kern_tokens(naam):
    return set(t for t in tokens(naam) if t not in RUIS)


def plat(naam):
    return ' '.join(sorted(tokens(naam)))


def koppel(pl_spelers, bsd_kandidaten):
    vrij = list(bsd_kandidaten)
    koppels, open_pl = [], []

    rest = []
    for p in pl_spelers:
        tp = set(tokens(p['naam']))
        hit = next((b for b in vrij if set(tokens(b['naam'])) == tp), None)
        if hit:
            koppels.append((p, hit, 'exact')); vrij.remove(hit)
        else:
            rest.append(p)

    rest2 = []
    for p in rest:
        kp = kern_tokens(p['naam'])
        if len(kp) < 2:
            rest2.append(p); continue
        tr = [b for b in vrij
              if len(kern_tokens(b['naam'])) >= 2
              and (kp <= kern_tokens(b['naam']) or kern_tokens(b['naam']) <= kp)]
        if len(tr) == 1:
            koppels.append((p, tr[0], 'deelverzameling')); vrij.remove(tr[0])
        else:
            rest2.append(p)

    rest3 = []
    for p in rest2:
        lang = set(t for t in kern_tokens(p['naam']) if len(t) >= 4)
        if not lang:
            rest3.append(p); continue
        tr = [b for b in vrij if lang & set(t for t in kern_tokens(b['naam']) if len(t) >= 4)]
        if len(tr) == 1:
            koppels.append((p, tr[0], 'token')); vrij.remove(tr[0])
        else:
            rest3.append(p)

    for p in rest3:
        pp = plat(p['naam'])
        sc = sorted(((difflib.SequenceMatcher(None, pp, plat(b['naam'])).ratio(), b)
                     for b in vrij), key=lambda x: -x[0])
        if not sc:
            open_pl.append(p); continue
        beste = sc[0]
        tweede = sc[1][0] if len(sc) > 1 else 0.0
        if beste[0] >= 0.82:
            koppels.append((p, beste[1], 'gelijkenis')); vrij.remove(beste[1])
        elif beste[0] >= 0.70 and beste[0] - tweede >= 0.08:
            koppels.append((p, beste[1], 'zwak')); vrij.remove(beste[1])
        else:
            open_pl.append(p)

    return koppels, open_pl


# ----------------------------------------------------------------------------
# 1. BASIS INLEZEN
# ----------------------------------------------------------------------------

if not os.path.exists(BASIS_BESTAND):
    print('FOUT: %s niet gevonden. Draai eerst bouw_basis_v2.py.' % BASIS_BESTAND)
    sys.exit(1)

basis   = json.load(open(BASIS_BESTAND))
prijzen = basis['prijzen']
BEREIK  = {k: tuple(v) for k, v in basis['bereiken'].items()}
CURVE   = basis.get('curve', 1.8)

print('%s: periode %s, %d spelers, curve %.2f, berekend %s'
      % (BASIS_BESTAND, basis.get('periode'), len(prijzen), CURVE, basis.get('berekend')))

# Bevroren marktwaardeverdeling per positie. Nodig om een speler die
# tussentijds bijkomt te prijzen zonder de bestaande prijzen te verschuiven.
verdeling = {p: sorted(v['mv'] for v in prijzen.values()
                       if v['pos'] == p and v.get('mv')) for p in GELDIGE_POS}
for p in GELDIGE_POS:
    print('   %s: %d referentiewaarden' % (p, len(verdeling[p])))


def prijs_uit_verdeling(pos, mv):
    """Prijs voor een speler die niet in de bevroren tabel staat."""
    lo, hi = BEREIK[pos]
    ref = verdeling.get(pos) or []
    if not mv or not ref:
        return lo
    lager = sum(1 for x in ref if x < mv)
    pct = lager / float(max(1, len(ref) - 1))
    pct = min(1.0, max(0.0, pct))
    return round(lo + (hi - lo) * (pct ** CURVE), 1)


# ----------------------------------------------------------------------------
# 2. PRO LEAGUE-SELECTIES
# ----------------------------------------------------------------------------

print('\nPro League-selecties ophalen...')
html = haal_html(PL_BASE + '/jpl-clubs')
if not html:
    print('FOUT: clublijst niet op te halen. Afgebroken zonder te schrijven.')
    sys.exit(1)

clubs, gezien = [], set()
for m in re.finditer(r'href="(/teams/([a-z0-9\-]+?)-(\d+))"', html):
    pad, slug, cid = m.group(1), m.group(2), m.group(3)
    if cid in gezien:
        continue
    gezien.add(cid)
    clubs.append({'id': cid, 'slug': slug, 'pad': pad})

print('  %d clubs' % len(clubs))
if len(clubs) < 18:
    print('FOUT: minder dan 18 clubs gevonden. Afgebroken zonder te schrijven.')
    sys.exit(1)

onbekend = [c['slug'] for c in clubs if c['slug'] not in CLUBMAP]
if onbekend:
    print('FOUT: onbekende club-slug %s. CLUBMAP moet aangevuld worden.' % onbekend)
    sys.exit(1)

pl_squads = {}
for c in clubs:
    h = haal_html(PL_BASE + c['pad'] + '/squad')
    time.sleep(1.5)
    if not h:
        print('FOUT: selectie van %s niet op te halen. Afgebroken.' % c['slug'])
        sys.exit(1)

    sp = {}
    for m in re.finditer(r'<a[^>]+href="[^"]*?/spillere/([a-z0-9\-]+?)-(\d+)"[^>]*>(.*?)</a>',
                         h, re.S):
        slug, pid, inhoud = m.group(1), m.group(2), m.group(3)
        tekst = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', inhoud)).strip()
        pos = None
        for nl, code in POSITIES_NL.items():
            if nl in tekst:
                pos = code
                break
        nrs = re.findall(r'\b(\d{1,2})\b', tekst)
        sp[pid] = {'pl_id': pid, 'naam': slug.replace('-', ' ').title(),
                   'pos': pos, 'nummer': nrs[0] if nrs else None}

    if len(sp) < 15:
        print('FOUT: %s gaf slechts %d spelers. Pagina mogelijk gewijzigd. Afgebroken.'
              % (c['slug'], len(sp)))
        sys.exit(1)

    pl_squads[CLUBMAP[c['slug']]] = list(sp.values())
    print('  %-30s %3d' % (CLUBMAP[c['slug']][:30], len(sp)))

pl_totaal = sum(len(v) for v in pl_squads.values())
print('  totaal Pro League: %d' % pl_totaal)


# ----------------------------------------------------------------------------
# 3. BSD-SELECTIES
# ----------------------------------------------------------------------------

print('\nBSD-selecties ophalen...')
teams = {}
for off in (0, 200, 400):
    d = bsd('/api/v2/events/?league_id=%d&season_id=%d&limit=200&offset=%d'
            % (LEAGUE_ID, HUIDIG_SEIZOEN, off))
    if d is None:
        print('FOUT: BSD-kalender niet op te halen. Afgebroken.')
        sys.exit(1)
    r = d.get('results') or []
    for e in r:
        teams[e['home_team_id']] = e['home_team']
        teams[e['away_team_id']] = e['away_team']
    if len(r) < 200:
        break
    time.sleep(0.2)

bsd_per_club = collections.defaultdict(list)
for tid, tnaam in sorted(teams.items(), key=lambda x: x[1]):
    d = bsd('/api/players/?team=%d' % tid)
    if d is None:
        print('FOUT: BSD-selectie van %s niet op te halen. Afgebroken.' % tnaam)
        sys.exit(1)
    for p in (d.get('results') or []):
        bsd_per_club[tnaam].append({
            'id':   str(p['id']),
            'naam': p.get('name') or '',
            'pos':  p.get('position'),
            'mv':   p.get('market_value'),
            'av':   p.get('availability') or 'available',
        })
    time.sleep(0.2)

print('  %d clubs, %d spelers' % (len(bsd_per_club), sum(len(v) for v in bsd_per_club.values())))

ontbreekt = [c for c in pl_squads if c not in bsd_per_club]
if ontbreekt:
    print('FOUT: geen BSD-selectie voor %s. Afgebroken.' % ontbreekt)
    sys.exit(1)


# ----------------------------------------------------------------------------
# 4. KOPPELEN EN PRIJZEN
# ----------------------------------------------------------------------------

print('\nKoppelen...')
spelers   = {}
methoden  = collections.Counter()
nieuw     = []
verplaatst = []
pl_alleen = []
zonder_pos = 0

for club in sorted(pl_squads):
    pl_lijst = [p for p in pl_squads[club] if p['pos'] in GELDIGE_POS]
    zonder_pos += len(pl_squads[club]) - len(pl_lijst)

    koppels, open_pl = koppel(pl_lijst, bsd_per_club[club])
    for p, b, methode in koppels:
        methoden[methode] += 1
        bekend = prijzen.get(b['id'])

        if bekend and bekend['pos'] == p['pos']:
            fm, soort = bekend['fm'], 'bevroren'
        elif bekend:
            # Positie gewijzigd bij de Pro League: prijs herrekenen in de
            # nieuwe positiegroep, want de bereiken verschillen.
            fm = prijs_uit_verdeling(p['pos'], b['mv'])
            soort = 'positie_gewijzigd'
            verplaatst.append((club, b['naam'], bekend['pos'], p['pos'], bekend['fm'], fm))
        else:
            fm = prijs_uit_verdeling(p['pos'], b['mv'])
            soort = 'nieuw'
            nieuw.append((club, b['naam'], p['pos'], fm, b['mv']))

        spelers[b['id']] = {
            'naam':        b['naam'] or p['naam'],
            'club':        club,
            'pos':         p['pos'],
            'fm':          fm,
            'soort':       soort,
            'nummer':      p.get('nummer'),
            'beschikbaar': b['av'],
        }

    for p in open_pl:
        pl_alleen.append((club, p['naam'], p['pos'], p.get('nummer')))

print('  methoden: %s' % dict(methoden))
print('  in de databank        : %d' % len(spelers))
print('  Pro League zonder BSD : %d (vallen weg)' % len(pl_alleen))
if zonder_pos:
    print('  zonder bruikbare positie: %d' % zonder_pos)

if nieuw:
    print('\nNIEUWE SPELERS (%d) - geprijsd tegen de bevroren verdeling:' % len(nieuw))
    for club, naam, pos, fm, mv in sorted(nieuw, key=lambda x: -x[3]):
        mvs = ('%.1f mln' % (mv / 1e6)) if mv else 'geen waarde'
        print('  %-26s %-28s %s  %5.1f   (mv %s)' % (club[:26], naam[:28], pos, fm, mvs))

if verplaatst:
    print('\nPOSITIE GEWIJZIGD (%d):' % len(verplaatst))
    for club, naam, oud, nieuwp, oudfm, nieuwfm in verplaatst:
        print('  %-26s %-28s %s->%s  %.1f -> %.1f' % (club[:26], naam[:28], oud, nieuwp, oudfm, nieuwfm))

if pl_alleen:
    print('\nGEREGISTREERD MAAR NIET IN BSD (%d) - niet koopbaar:' % len(pl_alleen))
    for club, naam, pos, nr in sorted(pl_alleen):
        print('  %-26s %-30s %s #%s' % (club[:26], naam[:30], pos or '?', nr or '-'))


# ----------------------------------------------------------------------------
# 5. CONTROLES
# ----------------------------------------------------------------------------

per_pos = collections.Counter(v['pos'] for v in spelers.values())
print('\nPer positie: %s' % dict(per_pos))

for pos, n in QUOTA.items():
    if per_pos.get(pos, 0) < n:
        print('FOUT: %d spelers op positie %s, minstens %d nodig. Afgebroken.'
              % (per_pos.get(pos, 0), pos, n))
        sys.exit(1)

if len(spelers) < 350:
    print('FOUT: slechts %d spelers. Wijst op een onvolledige ophaling. Afgebroken.'
          % len(spelers))
    sys.exit(1)

# Is er met dit budget nog een geldige ploeg te bouwen?
goedkoopst = 0.0
for pos, n in QUOTA.items():
    pr = sorted(v['fm'] for v in spelers.values() if v['pos'] == pos)
    goedkoopst += sum(pr[:n])
print('Goedkoopst mogelijke ploeg: %.1f van %.1f budget' % (goedkoopst, BUDGET))
if goedkoopst > BUDGET:
    print('FOUT: geen geldige ploeg mogelijk binnen het budget. Afgebroken.')
    sys.exit(1)


# ----------------------------------------------------------------------------
# 6. WEGSCHRIJVEN, ENKEL BIJ EEN ECHTE WIJZIGING
# ----------------------------------------------------------------------------

uit = {
    'season_id':      HUIDIG_SEIZOEN,
    'periode':        basis.get('periode'),
    'budget':         BUDGET,
    'basis_berekend': basis.get('berekend'),
    'bron':           'proleague.be squads x BSD',
    'players':        dict(sorted(spelers.items(), key=lambda x: int(x[0]))),
}

vorig = None
if os.path.exists(UIT_BESTAND):
    try:
        vorig = json.load(open(UIT_BESTAND))
    except Exception:
        vorig = None

if (vorig and vorig.get('players') == uit['players']
        and vorig.get('periode') == uit['periode']
        and vorig.get('budget') == uit['budget']):
    print('\nGeen wijziging - bestand niet herschreven.')
    print('WIJZIGING=nee')
    sys.exit(0)

uit['generated'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
json.dump(uit, open(UIT_BESTAND, 'w'), ensure_ascii=False, separators=(',', ':'))

print('\n%s geschreven - %d spelers, %.1f kB'
      % (UIT_BESTAND, len(spelers), os.path.getsize(UIT_BESTAND) / 1024.0))
print('WIJZIGING=ja')
