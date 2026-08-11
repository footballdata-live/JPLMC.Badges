#!/usr/bin/env python3
# =============================================================================
#  JPL Fantasy Manager - bouw_players_v3.3.2.py
# =============================================================================
#  Vervangt bouw_players_v2.py. Schrijft players.json: het LIVE bestand dat de
#  ploegbouwer en de Worker lezen. Draait twee keer per dag via GitHub Actions.
#
#  WAT ER MISGING OP 7 AUGUSTUS
#  De koppeling viel van 484 naar 386 spelers. Beide bronnen waren intact -
#  BSD groeide zelfs van 606 naar 692 records - maar de matcher liep vast.
#
#  Twee oorzaken:
#  (1) GREEDY. De regels liepen speler per speler: voor elke Pro League-speler
#      werden alle vijf de regels doorlopen voor de volgende aan de beurt kwam.
#      Een zachte match kon daardoor een BSD-record inpikken dat een latere
#      EXACTE match nodig had. Met meer BSD-records erbij gebeurde dat vaker.
#      Christian Burgess en Louis Patris vielen zo weg terwijl ze identiek
#      gespeld in beide bronnen staan.
#  (2) De Pro League levert namen nu zonder accenten (Felix Lemarechal in
#      plaats van Félix Lemaréchal). De matcher heft accenten al op, dus dat
#      alleen brak niets, maar het maakte meer namen onderling gelijkend en
#      versterkte daardoor probleem (1).
#
#  v3.1 TWEEDE FOUT, ernstiger dan de matcher. Het BSD-endpoint
#  /api/players/ doet er soms tien seconden over per club. Achttien clubs is
#  dan drie minuten, en tijdens die stilte toonde het script niets - het leek
#  vastgelopen terwijl het gewoon stond te wachten. Erger: als een call na drie
#  pogingen faalde, sloeg het script die club over met een LEGE lijst in plaats
#  van te stoppen. Alle spelers van die club vielen dan stil uit de koppeling.
#  Nu: voortgang per club met de duur erbij, meer pogingen met oplopende
#  wachttijd, en een harde stop zodra een club minder spelers geeft dan
#  redelijk is.
#
#  v3.2 DE ECHTE OORZAAK, gevonden op 7 augustus.
#  BSD's spelersrecords lopen achter op de transferrealiteit. Christian Burgess
#  staat daar bij Union terwijl hij deze zomer naar Gent ging - de Pro League
#  publiceerde die transfer zelf. Datzelfde bij Forbs, Sommer, Diakhon,
#  Paskotsi en Kadri. Zowel /api/players/?team= als het veld current_team is
#  daardoor onbruikbaar om te bepalen wie waar speelt.
#
#  Gevolg: koppelen per club werkte niet meer. Burgess stond bij de Pro League
#  onder Gent en bij BSD onder Union, dus vond de matcher hem niet - terwijl
#  beide bronnen hem gewoon kenden.
#
#  DE OPLOSSING: koppelen op PRO LEAGUE-ID.
#  fm_basis_v2.json bewaart per speler zowel het BSD-ID als het Pro League-ID.
#  Die koppeling is op 27 juli geverifieerd en verandert nooit meer. Waar BSD
#  zijn speler ook onderbrengt, het ID blijft hetzelfde en de statistieken
#  blijven eraan hangen - dat is bevestigd: Burgess staat in de wedstrijddata
#  met ID 3746 en club KAA Gent, ook al zegt zijn spelersrecord Union.
#
#  Alleen voor spelers die NIET in de basis staan is er nog naamkoppeling
#  nodig, en dan over alle BSD-clubs heen in plaats van binnen een club -
#  want de club van BSD zegt niets meer.
#
#  v3.3.2 De zoektocht probeert nu MEERDERE naamdelen. Eerst het laatste -
#  meestal de achternaam en het meest onderscheidend - en levert dat niets op,
#  dan de overige delen van lang naar kort.
#
#  Een enkel naamdeel volstond niet. Michael Frey viel weg omdat "Michael"
#  honderd treffers geeft, wat het maximum van de API is: de echte Frey stond
#  daar niet tussen omdat de lijst werd afgekapt. Zoeken op "Frey" vindt hem
#  meteen.
#
#  v3.3.1 De zoektocht was accentgevoelig. BSD's ?search= negeert accenten
#  NIET: zoeken op "Herve Koffi" geeft nul treffers, op "Hervé Koffi" een.
#  De Pro League levert namen zonder accent, dus elke speler met een accent
#  in zijn naam viel weg zodra hij uit de clubselecties verdween.
#
#  Herve Koffi is daar het voorbeeld van: hij ging op 1 augustus op huurbasis
#  van Lens naar Union, stond eerst nog in de BSD-selectie van Union en werd
#  toen via de naamlaag gevonden. Zodra BSD hem naar RC Lens verplaatste, moest
#  de zoektocht het overnemen - en die faalde op het accent.
#
#  De fix: zoeken op het LANGSTE naamdeel, en daarna zelf filteren met plat(),
#  dat accenten wel opheft. "Koffi" geeft 36 treffers, waarvan er precies een
#  overeenkomt.
#
#  v3.3 BREDE ZOEKTOCHT VOOR WIE NIET KOPPELT.
#  Na v3.2 bleven er 34 Pro League-spelers over zonder BSD-record. Michael
#  Frey stond daarbij, en die scoorde twee keer op speeldag 1 - hij bestond
#  dus wel degelijk bij BSD, alleen niet in de clubselectie die wij ophaalden.
#
#  Een gerichte zoektocht op naam vond er 21 van de 34 terug. De reden dat ze
#  in de clubselecties ontbraken verschilt per geval:
#    - BSD zet ze nog bij hun vorige club (Mailula bij Toronto, Nielsen bij
#      Club Brugge terwijl hij naar Standard ging)
#    - BSD zet ze op "No team"
#    - of ze staan wel bij de juiste club maar de naam wijkt af
#
#  Die zoektocht is veilig omdat we enkel namen zoeken die de Pro League al
#  bevestigd heeft. Club en positie komen altijd van de Pro League, nooit van
#  BSD - anders zou Mailula als Toronto-speler in de lijst komen.
#
#  UITZONDERING: een handmatige uitsluitingslijst. Gyrano Kerk en Bjorn Engels
#  staan nog in de Pro League-selectie van Antwerp, maar hun contract liep af
#  op 30 juni 2026 en Transfermarkt zet beiden zonder club. De Pro League
#  loopt achter bij VERTREKKERS - bij binnenkomende transfers klopt hij wel
#  (Burgess stond daar meteen goed bij Gent). Zulke gevallen zijn niet
#  automatisch te herkennen, dus die staan hieronder met naam.
#
#  DE FIX VAN v3.1: laagsgewijs koppelen. Eerst ALLE exacte matches over de hele club,
#  dan pas laag twee over wat overblijft, enzovoort. Een zachte regel kan zo
#  nooit meer een record wegnemen dat een hardere regel nodig had.
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
import urllib.parse

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

# ----------------------------------------------------------------------------
#  HANDMATIGE UITSLUITINGEN
#  Spelers die nog in een Pro League-selectie staan maar aantoonbaar niet meer
#  in de competitie spelen. De Pro League werkt vertrekkers traag bij: een
#  speler wiens contract afliep blijft in de squad-pagina staan.
#
#  Alleen opnemen bij ZEKERHEID, met bron en datum. Bij twijfel niet
#  uitsluiten: een speler die niet speelt levert nul punten op en is dus een
#  slechte aankoop, maar een speler die wel speelt en niet koopbaar is, is een
#  echt gemis.
# ----------------------------------------------------------------------------
UITGESLOTEN = {
    # naam (genormaliseerd) : reden
    'gyrano kerk':  'contract Antwerp afgelopen 30/06/2026, zonder club (Transfermarkt, 10/08/2026)',
    'bjorn engels': 'contract Antwerp afgelopen, zonder club (10/08/2026)',
}


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


def zoekBijBSD(naam):
    """Zoekt een speler op naam over ALLE BSD-records heen, dus zonder
    clubfilter. Enkel gebruiken voor namen die de Pro League al bevestigd
    heeft - dan is de zoektocht veilig.

    BSD's ?search= is ACCENTGEVOELIG: "Herve Koffi" geeft nul treffers,
    "Hervé Koffi" een. De Pro League levert namen zonder accent. We zoeken
    daarom op het langste naamdeel - dat is doorgaans de achternaam en
    zelden geaccentueerd - en filteren daarna zelf met plat(), dat accenten
    wel opheft.

    Retour: het BSD-record bij precies EEN treffer, anders None. Bij meerdere
    treffers met dezelfde naam wordt er niet gekoppeld: dat zou gokken zijn.
    """
    delen = [d for d in re.split(r'[\s\-]+', naam or '') if len(d) > 1]
    if not delen:
        return None

    # Het LAATSTE naamdeel eerst: dat is meestal de achternaam en het meest
    # onderscheidend. Daarna de overige delen van lang naar kort.
    #
    # Een enkele zoekterm volstaat niet. Een gangbare voornaam als "Michael"
    # geeft honderd treffers - het maximum van de API - en dan valt de juiste
    # speler buiten de lijst. "Frey" vindt hem meteen.
    volgorde = [delen[-1]] + sorted(delen[:-1], key=len, reverse=True)

    for zoekterm in volgorde:
        d = bsd('/api/players/?search=' + urllib.parse.quote(zoekterm),
                pogingen=3, stil=True)
        res = (d or {}).get('results') or []
        treffers = [p for p in res if plat(p.get('name') or '') == plat(naam)]
        if len(treffers) == 1:
            p = treffers[0]
            return {
                'id':   str(p['id']),
                'naam': p.get('name') or '',
                'pos':  p.get('position'),
                'mv':   p.get('market_value'),
                'av':   p.get('availability') or 'available',
                'bsd_club': (p.get('current_team') or {}).get('name') or 'geen club',
            }
        # Meerdere treffers met dezelfde naam: niet koppelen, dat is gokken.
        if len(treffers) > 1:
            return None
        time.sleep(0.2)

    return None


def bsd(pad, pogingen=5, stil=False):
    """BSD-call met oplopende wachttijd. Het endpoint /api/players/ is traag
    (soms tien seconden per club), dus de timeout staat ruim en er wordt vaker
    opnieuw geprobeerd voor we opgeven."""
    for n in range(pogingen):
        try:
            t0 = time.time()
            rq = urllib.request.Request(BSD_BASE + pad, headers={'Authorization': 'Token ' + KEY})
            d = json.load(urllib.request.urlopen(rq, timeout=60))
            if not stil:
                duur = time.time() - t0
                if duur > 5:
                    print('     (%.1fs)' % duur, end='', flush=True)
            return d
        except Exception as e:
            if n == pogingen - 1:
                print('\n  FAAL na %d pogingen: %s -> %s' % (pogingen, pad, e))
                return None
            wacht = 3 * (n + 1)
            print('\n  poging %d mislukt (%s), %ds wachten...' % (n + 1, e, wacht), flush=True)
            time.sleep(wacht)


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
    """NIET MEER IN GEBRUIK sinds v3.2.

    Deze functie koppelde per club, en dat werkt niet meer nu BSD's
    clubtoewijzing achterloopt op de transfers. Bewaard omdat de laagsgewijze
    opbouw nog van pas kan komen als er ooit opnieuw op naam gekoppeld moet
    worden binnen een afgebakende groep.

    Koppelt de Pro League-selectie van een club aan de BSD-spelers van
    diezelfde club.

    LAAGSGEWIJS, niet speler per speler. Elke regel wordt eerst over de
    VOLLEDIGE club toegepast voor de volgende regel aan de beurt komt. Zo kan
    een zachte match nooit een BSD-record inpikken dat een hardere match nodig
    had - de fout die op 7 augustus 98 spelers kostte.

    Retour: (koppels, niet_gekoppeld) met koppels als lijst van
    (pl_speler, bsd_speler, methode).
    """
    vrij = list(bsd_kandidaten)
    koppels = []
    open_pl = list(pl_spelers)

    def pak(p, b, methode):
        koppels.append((p, b, methode))
        vrij.remove(b)

    # --- Laag 1: identieke tokenverzameling ---------------------------------
    rest = []
    for p in open_pl:
        tp = set(tokens(p['naam']))
        hit = next((b for b in vrij if set(tokens(b['naam'])) == tp), None)
        if hit:
            pak(p, hit, 'exact')
        else:
            rest.append(p)
    open_pl = rest

    # --- Laag 2: kern-deelverzameling --------------------------------------
    # "Mathias Delorge" tegenover "Mathias Delorge Knieper". Enkel wanneer er
    # precies EEN kandidaat overblijft; bij twijfel schuift de speler door.
    rest = []
    for p in open_pl:
        kp = kern_tokens(p['naam'])
        if len(kp) < 2:
            rest.append(p)
            continue
        tr = [b for b in vrij
              if len(kern_tokens(b['naam'])) >= 2
              and (kp <= kern_tokens(b['naam']) or kern_tokens(b['naam']) <= kp)]
        if len(tr) == 1:
            pak(p, tr[0], 'deelverzameling')
        else:
            rest.append(p)
    open_pl = rest

    # --- Laag 3: uniek lang token ------------------------------------------
    # "Sixtus" tegenover "Sixtus Ogbuehi", "Bi Goore" tegenover
    # "Hyllarion Goore". Enkel bij precies een kandidaat.
    rest = []
    for p in open_pl:
        lang = set(t for t in kern_tokens(p['naam']) if len(t) >= 4)
        if not lang:
            rest.append(p)
            continue
        tr = [b for b in vrij
              if lang & set(t for t in kern_tokens(b['naam']) if len(t) >= 4)]
        if len(tr) == 1:
            pak(p, tr[0], 'token')
        else:
            rest.append(p)
    open_pl = rest

    # --- Laag 4: tekstgelijkenis, BESTE EERST ------------------------------
    # Alle overblijvende paren scoren, dan de hoogste scores eerst toewijzen.
    # Zo krijgt de sterkste gelijkenis voorrang in plaats van wie toevallig
    # eerst in de lijst stond.
    paren = []
    for p in open_pl:
        pp = plat(p['naam'])
        for b in vrij:
            r = difflib.SequenceMatcher(None, pp, plat(b['naam'])).ratio()
            if r >= 0.70:
                paren.append((r, p, b))
    paren.sort(key=lambda x: -x[0])

    pl_gedaan, bsd_gedaan = set(), set()
    for r, p, b in paren:
        if id(p) in pl_gedaan or id(b) in bsd_gedaan:
            continue
        if r >= 0.82:
            methode = 'gelijkenis'
        else:
            # Onder 0,82 enkel als er geen andere serieuze kandidaat is
            concurrent = [x for x in paren
                          if x[1] is p and x[2] is not b
                          and id(x[2]) not in bsd_gedaan and x[0] >= r - 0.08]
            if concurrent:
                continue
            methode = 'zwak'
        pak(p, b, methode)
        pl_gedaan.add(id(p))
        bsd_gedaan.add(id(b))

    open_pl = [p for p in open_pl if id(p) not in pl_gedaan]
    return koppels, open_pl


# ----------------------------------------------------------------------------
# 1. BASIS INLEZEN
# ----------------------------------------------------------------------------

if not os.path.exists(BASIS_BESTAND):
    print('FOUT: %s niet gevonden. Draai eerst bouw_basis_v2.py.' % BASIS_BESTAND)
    sys.exit(1)

basis   = json.load(open(BASIS_BESTAND))
prijzen = basis['prijzen']

# Aantal spelers in de vorige publicatie, als vangnet tegen een plotse val
vorig_aantal = None
if os.path.exists(UIT_BESTAND):
    try:
        vorig_aantal = len(json.load(open(UIT_BESTAND)).get('players') or {})
    except Exception:
        vorig_aantal = None
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
    print('  [%2d/%d] %-30s %3d' % (clubs.index(c) + 1, len(clubs),
                                    CLUBMAP[c['slug']][:30], len(sp)), flush=True)

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

# BSD levert een platte index over ALLE clubs heen. De clubtoewijzing van
# BSD is onbetrouwbaar (zie kop), dus die gebruiken we niet - we halen alle
# records op en zoeken er later in op ID en op naam.
bsd_alle = {}          # bsd_id -> record
bsd_op_naam = collections.defaultdict(list)
MIN_PER_CLUB = 15

for n, (tid, tnaam) in enumerate(sorted(teams.items(), key=lambda x: x[1]), 1):
    print('  [%2d/%d] %-30s ' % (n, len(teams), tnaam[:30]), end='', flush=True)
    d = bsd('/api/players/?team=%d' % tid)
    if d is None:
        print('\nFOUT: BSD-selectie van %s niet op te halen. Afgebroken zonder te schrijven.' % tnaam)
        sys.exit(1)

    lijst = d.get('results') or []
    if len(lijst) < MIN_PER_CLUB:
        print('\nFOUT: %s gaf slechts %d spelers (minimum %d). Onvolledige ophaling.'
              % (tnaam, len(lijst), MIN_PER_CLUB))
        sys.exit(1)

    for p in lijst:
        pid = str(p['id'])
        if pid in bsd_alle:
            continue
        rec = {
            'id':   pid,
            'naam': p.get('name') or '',
            'pos':  p.get('position'),
            'mv':   p.get('market_value'),
            'av':   p.get('availability') or 'available',
            'bsd_club': tnaam,        # enkel ter info, NIET om op te koppelen
        }
        bsd_alle[pid] = rec
        bsd_op_naam[plat(rec['naam'])].append(rec)
    print(' %3d' % len(lijst), flush=True)
    time.sleep(0.2)

print('  totaal BSD: %d unieke spelers over %d clubs' % (len(bsd_alle), len(teams)))


# ----------------------------------------------------------------------------
# 4. KOPPELEN EN PRIJZEN
# ----------------------------------------------------------------------------

print('\nKoppelen...')

# Vaste koppeling Pro League-ID -> BSD-ID uit de bevroren basis. Die is op
# 27 juli geverifieerd en verandert nooit meer, ongeacht wat BSD met zijn
# clubtoewijzing doet.
pl_naar_bsd = {}
for bsd_id, v in prijzen.items():
    if v.get('pl_id'):
        pl_naar_bsd[str(v['pl_id'])] = bsd_id

print('  vaste koppelingen uit de basis: %d' % len(pl_naar_bsd))

spelers    = {}
via_plid   = 0
via_naam   = 0
via_zoek   = 0
uitgesloten = []
gevonden_via_zoek = []
nieuw_lijst = []
verplaatst = []
geen_bsd   = []
zonder_pos = 0
gebruikt_bsd = set()

for club in sorted(pl_squads):
    for s in pl_squads[club]:
        if s['pos'] not in GELDIGE_POS:
            zonder_pos += 1
            continue

        # Handmatig uitgesloten: staat nog in de Pro League-selectie maar
        # speelt aantoonbaar niet meer in de competitie.
        if plat(s['naam']) in UITGESLOTEN:
            uitgesloten.append((club, s['naam'], UITGESLOTEN[plat(s['naam'])]))
            continue

        b = None
        methode = None

        # 1. Vaste koppeling op Pro League-ID. Dit is de hoofdweg.
        bsd_id = pl_naar_bsd.get(str(s['pl_id']))
        if bsd_id and bsd_id not in gebruikt_bsd:
            b = bsd_alle.get(bsd_id)
            if b is None:
                # BSD kent dit ID nu niet in een JPL-selectie, maar de
                # koppeling blijft geldig: de statistieken hangen aan het ID.
                b = {'id': bsd_id, 'naam': prijzen[bsd_id]['naam'],
                     'pos': prijzen[bsd_id]['pos'],
                     'mv': prijzen[bsd_id].get('mv'), 'av': 'available'}
            methode = 'pl_id'
            via_plid += 1

        # 2. Onbekend bij de basis: op naam zoeken over ALLE BSD-records.
        #    De club van BSD zegt niets meer, dus die filtert niet.
        if b is None:
            kand = [x for x in bsd_op_naam.get(plat(s['naam']), [])
                    if x['id'] not in gebruikt_bsd]
            if len(kand) == 1:
                b = kand[0]
                methode = 'naam'
                via_naam += 1

        # 3. Brede zoektocht over ALLE BSD-records. Nodig omdat BSD een
        #    speler soms bij zijn vorige club of op "No team" zet, of een
        #    licht afwijkende naam voert. Veilig, want de Pro League heeft
        #    hem al bevestigd. Club en positie komen hieronder van de Pro
        #    League, dus BSD's clubtoewijzing verandert niets.
        if b is None:
            b = zoekBijBSD(s['naam'])
            if b is not None:
                methode = 'zoek'
                via_zoek += 1
                gevonden_via_zoek.append((club, s['naam'], b['id'], b.get('bsd_club')))
            time.sleep(0.25)

        if b is None:
            geen_bsd.append((club, s['naam'], s['pos'], s.get('nummer')))
            continue

        gebruikt_bsd.add(b['id'])
        bekend = prijzen.get(b['id'])

        if bekend and bekend['pos'] == s['pos']:
            fm, soort = bekend['fm'], 'bevroren'
        elif bekend:
            fm = prijs_uit_verdeling(s['pos'], b.get('mv'))
            soort = 'positie_gewijzigd'
            verplaatst.append((club, b['naam'], bekend['pos'], s['pos'], bekend['fm'], fm))
        else:
            fm = prijs_uit_verdeling(s['pos'], b.get('mv'))
            soort = 'nieuw'
            nieuw_lijst.append((club, s['naam'], s['pos'], fm, b.get('mv'), methode))

        spelers[b['id']] = {
            'naam':        b['naam'] or s['naam'],
            'club':        club,          # Pro League is de waarheid
            'pos':         s['pos'],      # Pro League is de waarheid
            'fm':          fm,
            'soort':       soort,
            'nummer':      s.get('nummer'),
            'pl_id':       str(s['pl_id']),
            'beschikbaar': b.get('av') or 'available',
        }

print('  via Pro League-ID : %d' % via_plid)
print('  via naam          : %d' % via_naam)
print('  via zoektocht     : %d' % via_zoek)
print('  in de databank    : %d' % len(spelers))
print('  geen BSD-record   : %d (vallen weg)' % len(geen_bsd))
if zonder_pos:
    print('  zonder bruikbare positie: %d' % zonder_pos)

# Clubwijzigingen zichtbaar maken: nuttig om te zien of de Pro League een
# transfer heeft verwerkt die BSD nog niet kent.
clubwijziging = []
for bsd_id, v in spelers.items():
    oud = prijzen.get(bsd_id)
    if oud and oud.get('club') and oud['club'] != v['club']:
        clubwijziging.append((oud['club'], v['club'], v['naam']))
if clubwijziging:
    print('\nVAN CLUB GEWISSELD (%d) - volgens de Pro League:' % len(clubwijziging))
    for van, naar, naam in sorted(clubwijziging):
        print('  %-28s %-26s -> %s' % (naam[:28], van[:26], naar))

if nieuw_lijst:
    print('\nNIEUWE SPELERS (%d):' % len(nieuw_lijst))
    for club, naam, pos, fm, mv, methode in sorted(nieuw_lijst, key=lambda x: -x[3]):
        mvs = ('%.1f mln' % (mv / 1e6)) if mv else 'geen waarde'
        print('  %-26s %-28s %s  %5.1f   (mv %s, via %s)'
              % (club[:26], naam[:28], pos, fm, mvs, methode))

if verplaatst:
    print('\nPOSITIE GEWIJZIGD (%d):' % len(verplaatst))
    for club, naam, oud, nw, oudfm, nwfm in verplaatst:
        print('  %-26s %-28s %s->%s  %.1f -> %.1f' % (club[:26], naam[:28], oud, nw, oudfm, nwfm))

if uitgesloten:
    print('\nHANDMATIG UITGESLOTEN (%d):' % len(uitgesloten))
    for club, naam, reden in sorted(uitgesloten):
        print('  %-26s %-28s %s' % (club[:26], naam[:28], reden))

if gevonden_via_zoek:
    print('\nGEVONDEN VIA DE BREDE ZOEKTOCHT (%d):' % len(gevonden_via_zoek))
    print('  De club komt van de Pro League; wat BSD zegt staat er enkel ter info.')
    for club, naam, bid, bsdclub in sorted(gevonden_via_zoek):
        vlag = '' if (bsdclub or '') == club else '   <- BSD zegt: %s' % (bsdclub or '?')
        print('  %-26s %-28s id=%-8s%s' % (club[:26], naam[:28], bid, vlag))

if geen_bsd:
    print('\nGEEN BSD-RECORD (%d) - niet koopbaar:' % len(geen_bsd))
    for club, naam, pos, nr in sorted(geen_bsd):
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

# Vangnet: een plotse val in het aantal gekoppelde spelers wijst op een
# probleem met een van de bronnen of met de koppeling zelf. Beter niets
# publiceren dan een halve lijst - dat kostte op 7 augustus 127 spelers.
if len(spelers) < 350:
    print('FOUT: slechts %d spelers. Wijst op een onvolledige ophaling. Afgebroken.'
          % len(spelers))
    sys.exit(1)

if vorig_aantal and len(spelers) < vorig_aantal * 0.85:
    print('FOUT: %d spelers, tegenover %d in de vorige versie (%.0f%%).'
          % (len(spelers), vorig_aantal, 100.0 * len(spelers) / vorig_aantal))
    print('      Een daling van meer dan 15%% wijst op een probleem, niet op')
    print('      gewone transferbewegingen. Afgebroken zonder te schrijven.')
    print('      Controleer de lijst "geregistreerd maar niet in BSD" hierboven.')
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
    'bron_detail':    'koppeling op Pro League-ID; BSD-clubtoewijzing genegeerd',
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
