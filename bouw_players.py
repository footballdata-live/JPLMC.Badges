#!/usr/bin/env python3
# =============================================================================
#  JPL Fantasy Manager - bouw_players.py  v1.0
# =============================================================================
#  Schrijft players.json: het LIVE bestand dat de ploegbouwer en de Worker
#  lezen. Draait twee keer per dag via GitHub Actions.
#
#  Doet bewust GEEN prijsberekening. Prijzen liggen vast binnen een periode
#  (regelset 2.6) en komen uit fm_basis.json, dat 4x per seizoen door
#  bouw_basis.py wordt gemaakt. Zou dit script prijzen herberekenen, dan zou
#  elke nieuwe speler de percentielrangschikking verschuiven en dus ieders
#  prijs veranderen - precies wat de regelset verbiedt.
#
#  Wat het wel doet: de 18 clubselecties ophalen (regelset 10.5) en:
#    - speler bekend in fm_basis   -> bevroren prijs
#    - speler onbekend, wel positie -> mediaan van zijn positie (nieuwkomer)
#    - speler zonder bruikbare positie -> overslaan (regelset 2.7)
#
#  Kosten: 2 calls voor de kalender + 18 voor de selecties = 20 per run.
#
#  Gebruik:
#     BSD_KEY=... python3 bouw_players.py --basis fm_basis.json --uit players.json
# =============================================================================

import json
import os
import sys
import time
import collections
import urllib.request

BASE           = 'https://sports.bzzoiro.com'
LEAGUE_ID      = 14
HUIDIG_SEIZOEN = 1327
GELDIGE_POS    = ('G', 'D', 'M', 'F')

# ----------------------------------------------------------------------------
# Argumenten
# ----------------------------------------------------------------------------

def arg(vlag, standaard):
    if vlag in sys.argv:
        i = sys.argv.index(vlag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return standaard

BASIS_BESTAND = arg('--basis', 'fm_basis.json')
UIT_BESTAND   = arg('--uit', 'players.json')

KEY = os.environ.get('BSD_KEY') or os.environ.get('K')
if not KEY:
    print('FOUT: BSD_KEY ontbreekt in de omgeving.')
    sys.exit(1)


def api(pad, pogingen=3):
    for n in range(pogingen):
        try:
            rq = urllib.request.Request(BASE + pad, headers={'Authorization': 'Token ' + KEY})
            return json.load(urllib.request.urlopen(rq, timeout=45))
        except Exception as e:
            if n == pogingen - 1:
                print('  FAAL %s -> %s' % (pad, e))
                return None
            time.sleep(3)


# ----------------------------------------------------------------------------
# 1. Basis inlezen
# ----------------------------------------------------------------------------

if not os.path.exists(BASIS_BESTAND):
    print('FOUT: %s niet gevonden. Draai eerst bouw_basis.py.' % BASIS_BESTAND)
    sys.exit(1)

basis    = json.load(open(BASIS_BESTAND))
prijzen  = basis['prijzen']
medianen = basis['medianen']

print('fm_basis.json: periode %s, %d spelers, berekend %s'
      % (basis.get('periode'), len(prijzen), basis.get('berekend')))

for pos in GELDIGE_POS:
    if pos not in medianen:
        print('FOUT: geen mediaan voor positie %s in de basis.' % pos)
        sys.exit(1)


# ----------------------------------------------------------------------------
# 2. Clubs ophalen
# ----------------------------------------------------------------------------

print('\nClubs ophalen...')
teams = {}
for off in (0, 200, 400):
    d = api('/api/v2/events/?league_id=%d&season_id=%d&limit=200&offset=%d'
            % (LEAGUE_ID, HUIDIG_SEIZOEN, off))
    if d is None:
        print('FOUT: kalender niet op te halen. Afgebroken zonder te schrijven.')
        sys.exit(1)
    r = d.get('results') or []
    for e in r:
        teams[e['home_team_id']] = e['home_team']
        teams[e['away_team_id']] = e['away_team']
    if len(r) < 200:
        break
    time.sleep(0.2)

print('  %d clubs' % len(teams))
if len(teams) < 16:
    print('FOUT: minder dan 16 clubs gevonden. Dat klopt niet - afgebroken.')
    sys.exit(1)


# ----------------------------------------------------------------------------
# 3. Selecties ophalen en prijzen toekennen
# ----------------------------------------------------------------------------

spelers  = {}
telling  = collections.Counter()
nieuw    = []
geenpos  = []

print('\nSelecties ophalen...')
for tid, tnaam in sorted(teams.items(), key=lambda x: x[1]):
    d = api('/api/players/?team=%d' % tid)      # let op: limit= wordt genegeerd
    if d is None:
        print('FOUT: selectie van %s niet op te halen. Afgebroken zonder te schrijven.' % tnaam)
        sys.exit(1)

    lijst = d.get('results') or []
    opgenomen = 0

    for p in lijst:
        pid = str(p['id'])
        pos = p.get('position')

        # Regelset 2.7: geen bruikbare positie = geen prijs = niet in de databank
        if pos not in GELDIGE_POS:
            geenpos.append((pid, p.get('name'), tnaam))
            telling['overgeslagen'] += 1
            continue

        if pid in prijzen:
            fm    = prijzen[pid]['fm']
            soort = prijzen[pid]['soort']
        else:
            fm    = medianen[pos]
            soort = 'nieuwkomer'
            nieuw.append((pid, p.get('name'), tnaam, pos, fm))

        spelers[pid] = {
            'naam':        p.get('name'),
            'club':        tnaam,
            'club_id':     tid,
            'pos':         pos,
            'fm':          fm,
            'soort':       soort,
            'beschikbaar': p.get('availability') or 'available',
        }
        telling[soort] += 1
        opgenomen += 1

    print('  %-30s %3d van %3d' % (tnaam[:30], opgenomen, len(lijst)))
    time.sleep(0.2)


# ----------------------------------------------------------------------------
# 4. Controles voor we schrijven
# ----------------------------------------------------------------------------

print('\nVerdeling:', dict(telling))

per_pos = collections.Counter(v['pos'] for v in spelers.values())
print('Per positie:', dict(per_pos))

# Een ploeg moet samen te stellen zijn: 2 G, 5 D, 5 M, 3 F, max 2 per club
minimaal = {'G': 2, 'D': 5, 'M': 5, 'F': 3}
for pos, n in minimaal.items():
    if per_pos.get(pos, 0) < n:
        print('FOUT: slechts %d spelers op positie %s, er zijn er minstens %d nodig.'
              % (per_pos.get(pos, 0), pos, n))
        sys.exit(1)

if len(spelers) < 300:
    print('FOUT: slechts %d spelers. Dat wijst op een onvolledige ophaling - afgebroken.'
          % len(spelers))
    sys.exit(1)

if nieuw:
    print('\nNIEUWE SPELERS (%d) - prijs op de mediaan van hun positie:' % len(nieuw))
    for pid, naam, club, pos, fm in nieuw:
        print('  %-8s %-26s %-24s %s  %.1f mln' % (pid, (naam or '')[:26], club[:24], pos, fm))

if geenpos:
    print('\nZONDER BRUIKBARE POSITIE (%d) - niet opgenomen:' % len(geenpos))
    for pid, naam, club in geenpos:
        print('  %-8s %-26s %s' % (pid, (naam or '')[:26], club))


# ----------------------------------------------------------------------------
# 5. Wegschrijven, maar alleen bij een echte wijziging
# ----------------------------------------------------------------------------

uit = {
    'season_id': HUIDIG_SEIZOEN,
    'periode':   basis.get('periode'),
    'budget':    basis.get('budget', 110.0),
    'basis_berekend': basis.get('berekend'),
    'players':   dict(sorted(spelers.items(), key=lambda x: int(x[0]))),
}

vorig = None
if os.path.exists(UIT_BESTAND):
    try:
        vorig = json.load(open(UIT_BESTAND))
    except Exception:
        vorig = None

# 'generated' verandert elke run en zou dus altijd een commit uitlokken.
# Vergelijken doen we daarom op de inhoud die er werkelijk toe doet.
if vorig and vorig.get('players') == uit['players'] and vorig.get('periode') == uit['periode']:
    print('\nGeen wijziging in de spelerslijst - bestand niet herschreven.')
    print('WIJZIGING=nee')
    sys.exit(0)

uit['generated'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
json.dump(uit, open(UIT_BESTAND, 'w'), ensure_ascii=False, separators=(',', ':'))

grootte = os.path.getsize(UIT_BESTAND)
print('\n%s geschreven - %d spelers, %.1f kB' % (UIT_BESTAND, len(spelers), grootte / 1024.0))
print('WIJZIGING=ja')
