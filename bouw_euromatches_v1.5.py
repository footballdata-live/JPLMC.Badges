#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bouw_euromatches v1.5
=====================

Bouwt euromatches.json voor de fanpages: alle Champions League-, Europa
League- en Conference League-wedstrijden van Belgische clubs.

Zusterscript van bouw_bekermatches_v1.1.py. Zelfde uitvoerstructuur, zelfde
seizoenscontrole, zelfde samenvoeglogica, zodat de fanpage beide bestanden
door dezelfde renderlogica kan halen.

WIJZIGING TEN OPZICHTE VAN v1.4
-------------------------------
v1.4 VERVING de score door extra_time_score. Dat was fout: dat veld bevat
alleen de doelpunten die IN de verlenging vielen, niet de totaalstand.

Vastgesteld op event 220448, Bodo/Glimt tegen Union:

    home_score        2          <- stand na 90 minuten
    away_score        2
    extra_time_score  {"home": 1, "away": 0}   <- alleen de verlenging
    period            "AET"
    current_minute    125

De eindstand was 3-2. Dus 2+1 en 2+0, niet vervangen. v1.4 zou er 1-0 van
gemaakt hebben.

De verlenging wordt nu herkend aan period == "AET", wat een expliciete
markering is, met de aanwezigheid van extra_time_score als vangnet.

LET OP VOOR ELDERS
------------------
getScoreBSD in de WK-widget vervangt de score wel:

    scoreH = m.extra_time_score.home;

Bij deze data zou dat 1-0 tonen in plaats van 3-2. Of dat bij de WK-brondata
anders lag is hier niet vast te stellen, maar het is het nakijken waard voor
de eerste WK-knockoutwedstrijd met verlenging.

WIJZIGING IN v1.4 TEN OPZICHTE VAN v1.3
---------------------------------------
De eindstand bij verlengingen werd niet opgepikt.

Bodo/Glimt tegen Union in de derde voorronde van de Champions League stond
in het bestand als 2-2, terwijl het 3-2 werd na verlenging. Over twee
wedstrijden 6-5 voor Bodo/Glimt, en dat is precies waarom Union naar de
Europa League zakte. Zonder dat doelpunt klopt het verhaal niet.

De oorzaak staat in de WK-widget gedocumenteerd, niet vermoed:

    BSD: home_score/away_score = stand na 90 min.
    Bij verlenging staat de eindstand in extra_time_score.

Dat veld was in de eerste steekproef altijd null, simpelweg omdat geen van
die wedstrijden verlengingen had gehad.

De volgorde uit getScoreBSD in de WK-widget wordt hier overgenomen:
extra_time_score bepaalt de score, penalty_shootout vervangt alleen de
achtervoegseltekst en NIET de score. Dat klopt met Gent tegen LNZ Cherkasy:
0-0 na verlenging, gewonnen met 4-2 na strafschoppen.

Anders dan de widget gebeurt dit hier bij het bouwen, niet bij het renderen.
De fanpage krijgt dus een correcte eindstand binnen en hoeft zelf geen
scorelogica te bevatten.

Nieuwe velden: verlenging (bool), home_score_90 en away_score_90. Die laatste
twee kosten niets en de stand na 90 minuten is echte informatie.

WIJZIGING IN v1.3 TEN OPZICHTE VAN v1.2
---------------------------------------
Het script was blind in een GitHub-runner. Een run bleef vier minuten hangen
zonder ook maar een regel uitvoer, waardoor niet vast te stellen was waar hij
stond: bij clubs.json, bij CL, bij EL of bij UECL.

Oorzaak: Python buffert zijn uitvoer als hij niet in een terminal draait. In
een runner verschijnt er dus niets tot het proces klaar is. Lokaal viel dat
nooit op.

Drie dingen daartegen:

  (1) Elke print doet flush=True, en de workflow draait python3 -u. Dubbelop,
      maar dan is het script ook bruikbaar als iemand die vlag vergeet.

  (2) Een voortgangsregel per pagina: welke competitie, welke offset, hoeveel
      items, hoeveel seconden. Zo is live te zien waar hij staat.

  (3) Een harde bovengrens op de totale duur. TIMEOUT geldt per
      socket-operatie, niet voor de hele run: een verbinding die traag
      doordruppelt loopt daar onderdoor en hangt tot de runner na zes uur
      afkapt. MAX_DUUR laat het script netjes falen met een verklaring.

De ophaallogica zelf is NIET gewijzigd. De paginering is met een aparte
diagnostic bevestigd: offset=0 gaf 200 items, offset=200 gaf er 166,
offset=400 gaf er nul, met telkens andere ids en in anderhalve seconde per
call. Er is dus geen lus en geen genegeerde parameter.

WIJZIGING IN v1.2 TEN OPZICHTE VAN v1.1
---------------------------------------
De push naar GitHub is eruit. Dit script schrijft alleen nog het bestand;
de commit gebeurt in de workflow met de ingebouwde GITHUB_TOKEN.

Reden: de workflow draait IN footballdata-live/JPLMC.Badges zelf, dus een
PAT is overbodig. Dat scheelt een vervaldatum, en de vorige tokens verliepen
op 1 september. Dit is hetzelfde patroon als playerstats.yml v2, dat om
precies deze reden al eerder omgebouwd is. De eerste echte run van v1.1
strandde hierop: het bestand werd gebouwd maar nooit gecommit.

Het bestaande bestand komt nu mee met de checkout in plaats van via GitHub
Pages opgehaald te worden. Dat maakt het samenvoegen betrouwbaarder: Pages
loopt achter op de repo omdat de site eerst moet bouwen, dus twee runs kort
na elkaar lazen daar een verouderde versie.

WIJZIGING IN v1.1 TEN OPZICHTE VAN v1.0
---------------------------------------
Rondenamen worden vertaald naar het Nederlands, en er komt een veld
competitie_naam bij met de volledige competitienaam.

Aanleiding: de eerste echte run leverde 52 wedstrijden op in plaats van de
verwachte 36, en dat bleek volledig terecht. De voorrondes zitten erin, en
daarmee ook de trajecten die doodliepen. Union speelde de derde voorronde
van de Champions League en zakte door naar de Europa League. Sint-Truiden
probeerde het via de Europa League en zakte door naar de Conference League.

Op de fanpage krijgen alle Europese wedstrijden dezelfde achtergrond,
ongeacht het niveau. De subtekst vertelt om welke competitie en ronde het
ging, en daarvoor moeten beide velden in het Nederlands leesbaar zijn
zonder dat de pagina zelf hoeft te vertalen.

Een wedstrijd staat onder de competitie waarin hij GESPEELD is, niet onder
de competitie waarin de club uiteindelijk uitkomt. Op de fanpage van Union
staan dus twee wedstrijden als Champions League en acht als Europa League.
Dat is feitelijk juist en zichtbaar via de subtekst.

BRON
----
BSD, rechtstreeks. Nooit via de JPLMC-Worker: die begrenst op 30 verzoeken
per 60 seconden per IP en heeft een Referer-check op voetbalbe.boards.net.
Een bouwscript hoort daar niet doorheen.

    GET /api/events/?league={id}&season_id={id}&date_from=&date_to=&limit=200
    Authorization: Token {BSD_KEY}

PAGINERING IS VERPLICHT
-----------------------
BSD kapt af op 200 resultaten per antwoord en negeert een hogere limit
zonder dat te melden. Dit seizoen passen CL (144), EL (144) en UECL (108)
daar nog binnen, maar daar mag het script niet op leunen: breidt een
competitie uit of komt de knockoutfase erbij, dan verdwijnen wedstrijden
stilzwijgend. Er wordt dus altijd doorgepagineerd tot de bron leeg is.

CLUBHERKENNING
--------------
Op team_id, niet op naam.

Dat is met een diagnostic vastgesteld: BSD gebruikt in CL, EL en UECL exact
dezelfde team_ids als in de JPL. Club Brugge is 123 in beide, Union 116,
Anderlecht 240, Gent 245, STVV 244. Er is dus geen aparte koppeltabel nodig
zoals bij de beker, waar de bron een andere identifier gebruikt.

Naammatching zou hier bovendien fout gaan: BSD schrijft "Standard Liège"
waar clubs.json "Standard de Liège" zegt, en "Royale Union Saint-Gilloise"
tegenover "Union Saint-Gilloise".

LET OP: de teamnaam staat bij BSD in home_team als STRING. Het object met de
id zit in home_team_obj. Dat onderscheid is de reden dat een eerder
diagnostisch script vijf valse "wijkt af"-meldingen gaf.

De clublijst komt uit clubs.json, niet uit een lijst in dit bestand. Wie
volgend seizoen Europees speelt hoeft dus niemand bij te werken: elke club
die in clubs.json staat en in een Europese competitie opduikt, wordt
opgepikt.

SEIZOEN
-------
Twee constanten per jaar bij te werken: SEASON_IDS en SEIZOEN_LABEL. Het
script controleert daarnaast of de teruggekregen events werkelijk het
verwachte seizoenslabel dragen, zodat een verouderd season_id niet stil
vorig jaar oplevert. Dat is dezelfde bescherming als HUIDIG_SEIZOEN in het
bekerscript, en om dezelfde reden: daar bleek de bron stilzwijgend op de
vorige editie te blijven staan.

GEBRUIK
-------
    export BSD_KEY='...'
    python3 bouw_euromatches_v1.5.py              # schrijft euromatches.json
    python3 bouw_euromatches_v1.5.py --toon       # print ook de lijst

Committen doet de workflow, niet dit script.
"""

import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# CONFIGURATIE
# ---------------------------------------------------------------------------

BSD_BASIS = 'https://sports.bzzoiro.com'
BSD_KEY = os.environ.get('BSD_KEY', '')

CLUBS_URL = ('https://raw.githubusercontent.com/footballdata-live/'
             'JPLMC.Badges/main/clubs.json')

UIT_BESTAND = 'euromatches.json'

# ---------------------------------------------------------------------------
# SEIZOEN - TWEE PLEKKEN PER JAAR BIJWERKEN
#
# De season_ids zijn met een diagnostic vastgesteld uit de events zelf, niet
# uit een seizoenlijst. Ze veranderen elk jaar.
#
# SEIZOEN_LABEL wordt vergeleken met season.name uit de bron, die luidt
# bijvoorbeeld "UEFA Champions League 26/27". Draagt een event een ander
# label, dan wordt het overgeslagen: dan wijst het season_id naar een ander
# seizoen dan we denken.
# ---------------------------------------------------------------------------

SEIZOEN_LABEL = '26/27'

LEAGUES = {
    7:  ('CL',   'Champions League',  1112),
    8:  ('EL',   'Europa League',     1269),
    83: ('UECL', 'Conference League', 1606),
}

# Ruim genomen. De competitiefase loopt van september tot eind januari, de
# knockoutfase tot in mei.
DATUM_VAN = '2026-07-01'
DATUM_TOT = '2027-06-30'

# ---------------------------------------------------------------------------
# RONDENAMEN
#
# BSD geeft Engels. We vertalen hier zodat de fanpage geen vertaallogica
# nodig heeft, net als in het bekerscript.
#
# Waargenomen in de eerste echte run: "Qualification Round 2",
# "Qualification Round 3", "Playoff round". De knockoutfase is nog niet
# gespeeld, dus die namen zijn NIET waargenomen maar op de gebruikelijke
# UEFA-terminologie gebaseerd. Klopt er een niet, dan valt hij terug op de
# originele Engelse naam en is dat zichtbaar op de pagina in plaats van
# stil fout.
# ---------------------------------------------------------------------------

RONDE_NL = {
    'playoff round':              'Play-offronde',
    'play-off round':             'Play-offronde',
    'knockout round play-offs':   'Tussenronde',
    'knockout phase play-off':    'Tussenronde',
    'round of 16':                'Achtste finale',
    'round of 32':                '1/16 finale',
    'quarter-finals':             'Kwartfinale',
    'quarter-final':              'Kwartfinale',
    'semi-finals':                'Halve finale',
    'semi-final':                 'Halve finale',
    'final':                      'Finale',
    'finale':                     'Finale',
    'league phase':               'Competitiefase',
}

# "Qualification Round 3" -> "Voorronde 3". Apart omdat het nummer varieert.
KWALIFICATIE_RE = re.compile(
    r'^qualifica\w*\s+round\s+(\d+)$', re.IGNORECASE)

# De volledige competitienaam, voor de subtekst op de fanpage. Dit zijn
# eigennamen en blijven dus onvertaald.
COMPETITIE_NAAM = {
    'CL':   'Champions League',
    'EL':   'Europa League',
    'UECL': 'Conference League',
}

PAGINA = 200          # BSD kapt hier hoe dan ook af
MAX_PAGINAS = 25      # veiligheidsrem tegen een oneindige lus
PAUZE = 0.7

# Per socket-operatie. Dit is GEEN grens op de totale duur: een verbinding
# die traag doordruppelt blijft hieronder en hangt door.
TIMEOUT = 30

# Harde bovengrens op de hele run. Ruim genomen: de gemeten werkelijkheid is
# twee calls per competitie in anderhalve seconde elk, dus een gezonde run
# duurt ongeveer tien seconden. Drie minuten is dus twintig keer de normale
# duur en betekent dat er iets structureel mis is.
MAX_DUUR = 180

UA = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')


# ---------------------------------------------------------------------------
# OPHALEN
# ---------------------------------------------------------------------------

START = time.monotonic()


def zeg(tekst=''):
    """print met flush. Zonder dit blijft de uitvoer in een GitHub-runner in
    de buffer staan tot het proces klaar is, en is er bij een hangende run
    niets te zien."""
    print(tekst, flush=True)


def verstreken():
    return time.monotonic() - START


def bewaak_tijd():
    if verstreken() > MAX_DUUR:
        raise RuntimeError(
            'MAX_DUUR van %ds overschreden (nu %.0fs). De run is gestopt in '
            'plaats van te blijven hangen.' % (MAX_DUUR, verstreken()))


def haal_json(url, headers=None):
    rq = urllib.request.Request(url, headers=headers or {'User-Agent': UA})
    with urllib.request.urlopen(rq, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode('utf-8', errors='replace'))


def haal_bsd(pad, params):
    url = BSD_BASIS + pad + '?' + urllib.parse.urlencode(params)
    return haal_json(url, {
        'Authorization': 'Token ' + BSD_KEY,
        'Accept': 'application/json',
        'User-Agent': UA,
    })


def lijst_van(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for s in ('results', 'data', 'events', 'items'):
            if isinstance(data.get(s), list):
                return data[s]
    return []


def haal_events(league_id, season_id, code):
    """Alle events van een competitie ophalen, met paginering.

    BSD kapt af op 200 en meldt dat niet. We blijven dus pagineren tot een
    pagina minder dan PAGINA items teruggeeft, of tot count bereikt is.

    Bevestigd met een aparte diagnostic op league 83: offset=0 gaf 200 items
    (ids 221473 tot 223416), offset=200 gaf er 166 (ids 223417 tot 601384),
    offset=400 gaf er nul. De ids verschillen per pagina, dus offset wordt
    werkelijk toegepast en niet stilzwijgend genegeerd.
    """
    alles = []
    offset = 0
    verwacht = None

    for _ in range(MAX_PAGINAS):
        bewaak_tijd()
        t0 = time.monotonic()
        data = haal_bsd('/api/events/', {
            'league': league_id,
            'season_id': season_id,
            'date_from': DATUM_VAN,
            'date_to': DATUM_TOT,
            'limit': PAGINA,
            'offset': offset,
        })
        if verwacht is None and isinstance(data, dict) and 'count' in data:
            verwacht = data.get('count')

        blok = lijst_van(data)
        alles.extend(blok)

        zeg('    %-5s offset=%-5d %3d items in %4.1fs  (count=%s, totaal nu %d)'
            % (code, offset, len(blok), time.monotonic() - t0,
               verwacht, len(alles)))

        if len(blok) < PAGINA:
            break
        offset += PAGINA
        if verwacht is not None and offset >= verwacht:
            break
        time.sleep(PAUZE)

    return alles, verwacht


# ---------------------------------------------------------------------------
# OMZETTEN
# ---------------------------------------------------------------------------

def team_uit(ev, kant):
    """(team_id, naam) uit een event halen.

    De naam staat in home_team / away_team als string, het object met de id
    in home_team_obj / away_team_obj.
    """
    obj = ev.get(kant + '_team_obj')
    if isinstance(obj, dict):
        return str(obj.get('id') or ''), (obj.get('name') or '')
    naam = ev.get(kant + '_team')
    return '', (naam if isinstance(naam, str) else '')


def seizoen_van(ev):
    s = ev.get('season')
    if isinstance(s, dict):
        return (s.get('name') or '').strip()
    return ''


def paar_uit(ev, veld):
    """(home, away) uit een scoreveld als penalty_shootout of
    extra_time_score. Bevestigd bij Gent tegen LNZ Cherkasy: de sleutels zijn
    home en away. De tweede vorm blijft staan als vangnet."""
    blok = ev.get(veld)
    if isinstance(blok, dict):
        for h, a in (('home', 'away'), ('home_score', 'away_score')):
            if isinstance(blok.get(h), int) and isinstance(blok.get(a), int):
                return blok[h], blok[a]
    return None, None


def score_uit(ev):
    """De eindstand bepalen, plus de stand na 90 minuten.

    extra_time_score bevat ALLEEN de doelpunten uit de verlenging, niet de
    totaalstand. Dat is vastgesteld op event 220448: home_score 2, away_score
    2, extra_time_score {"home": 1, "away": 0}, werkelijke eindstand 3-2.
    De verlengingsdoelpunten worden dus OPGETELD.

    penalty_shootout verandert de score niet, alleen wat je erachter toont.
    Gent tegen LNZ Cherkasy eindigde 0-0 en werd gewonnen met 4-2 na
    strafschoppen; de score blijft 0-0.

    Alleen toegepast bij een afgelopen wedstrijd. Dat is geen beperking op de
    livescore: dit bestand wordt eens per dag gebouwd en draagt sowieso nooit
    een lopende stand. Live komt van de Worker.
    """
    s90_h = ev.get('home_score')
    s90_a = ev.get('away_score')

    eind_h, eind_a = s90_h, s90_a
    verlenging = False

    klaar = (ev.get('status') or '').lower() in ('finished', 'ft', 'aet', 'pen')
    periode = (ev.get('period') or '').upper()

    if klaar:
        et_h, et_a = paar_uit(ev, 'extra_time_score')
        # period == "AET" is de expliciete markering. De aanwezigheid van
        # extra_time_score staat erbij als vangnet, voor het geval BSD de
        # periode ooit anders schrijft.
        if et_h is not None and (periode == 'AET' or et_h or et_a):
            if isinstance(s90_h, int) and isinstance(s90_a, int):
                eind_h = s90_h + et_h
                eind_a = s90_a + et_a
                verlenging = True
        elif periode == 'AET':
            # Verlengd maar zonder doelpunten erin: de score klopt al, de
            # markering hoort er wel bij zodat "nv" getoond kan worden.
            verlenging = True

    hp, ap = paar_uit(ev, 'penalty_shootout')

    return {
        'home_score': eind_h,
        'away_score': eind_a,
        'home_score_90': s90_h,
        'away_score_90': s90_a,
        'verlenging': verlenging,
        'home_pens': hp,
        'away_pens': ap,
    }


def vertaal_ronde(naam):
    """Engelse rondenaam naar het Nederlands. Onbekende namen komen
    onvertaald terug: dan staat er tijdelijk Engels op de pagina, en dat is
    altijd beter dan een leeg veld of een verkeerde gok."""
    if not naam:
        return ''
    schoon = naam.strip()

    m = KWALIFICATIE_RE.match(schoon)
    if m:
        return 'Voorronde %s' % m.group(1)

    return RONDE_NL.get(schoon.lower(), schoon)


def ronde_van(ev):
    naam = (ev.get('round_name') or '').strip()
    if naam:
        return vertaal_ronde(naam)
    # In de competitiefase is round_name leeg en draagt round_number de
    # speeldag. Dat is al Nederlands.
    nummer = ev.get('round_number')
    if isinstance(nummer, int) and nummer > 0:
        return 'Speeldag %d' % nummer
    return ''


def zet_om(ev, code, onze_clubs):
    """Een BSD-event omzetten naar ons formaat.

    Geeft None terug als er geen Belgische club bij betrokken is.
    """
    thuis_id, thuis_naam = team_uit(ev, 'home')
    uit_id, uit_naam = team_uit(ev, 'away')

    if thuis_id not in onze_clubs and uit_id not in onze_clubs:
        return None

    score = score_uit(ev)
    venue = ev.get('venue')
    venue_naam = venue.get('name') if isinstance(venue, dict) else ''

    datum = ev.get('event_date') or ''

    return {
        'competitie':   code,
        # Voluit, voor de subtekst op de fanpage. Alle Europese wedstrijden
        # krijgen dezelfde achtergrond, dus de tekst moet vertellen om welke
        # competitie en ronde het ging.
        'competitie_naam': COMPETITIE_NAAM.get(code, code),
        'seizoen':      seizoen_van(ev),
        'ronde':        ronde_van(ev),
        # Bij de beker splitsen date en kickoff omdat de bron dat doet. BSD
        # geeft een enkel ISO-tijdstip; date is daar de eerste tien tekens
        # van, zodat beide bestanden dezelfde velden dragen.
        'date':         datum[:10],
        'kickoff':      datum,
        'home_team':    thuis_naam,
        'away_team':    uit_naam,
        'home_team_id': thuis_id if thuis_id in onze_clubs else '',
        'away_team_id': uit_id if uit_id in onze_clubs else '',
        # De eindstand, dus inclusief verlengingen. De stand na 90 minuten
        # staat apart in home_score_90 en away_score_90.
        'home_score':    score['home_score'],
        'away_score':    score['away_score'],
        'home_score_90': score['home_score_90'],
        'away_score_90': score['away_score_90'],
        'verlenging':    score['verlenging'],
        'home_pens':     score['home_pens'],
        'away_pens':     score['away_pens'],
        # Rauw overgenomen zoals BSD hem geeft ("notstarted" en verder). De
        # vertaling naar pending, live en ended gebeurt aan de renderkant,
        # waar de sidebar-widget al dezelfde waarden verwerkt.
        'status':       ev.get('status') or '',
        'minuut':       ev.get('current_minute'),
        'stadion':      venue_naam or '',
        'bsd_id':       str(ev.get('id') or ''),
    }


# ---------------------------------------------------------------------------
# BESTAND INLEZEN EN SAMENVOEGEN
# ---------------------------------------------------------------------------

def lees_bestaand():
    if not os.path.exists(UIT_BESTAND):
        return None
    try:
        return json.load(io.open(UIT_BESTAND, encoding='utf-8'))
    except Exception:
        return None


def bewaarde_wedstrijden(oud):
    """Wedstrijden uit het bestaande bestand die we behouden: alleen die van
    het huidige seizoen. Anders sleept het bestand jaar na jaar oude edities
    mee.

    BSD levert de volledige competitiefase in een keer, dus anders dan bij
    de beker verwachten we hier geen verdwijnende wedstrijden. Het
    samenvoegen blijft toch staan: het kost niets en het beschermt tegen een
    bron die tijdelijk minder teruggeeft.
    """
    if not oud:
        return {}
    behouden = {}
    weg = 0
    for wid, w in (oud.get('wedstrijden') or {}).items():
        if isinstance(w, dict) and SEIZOEN_LABEL in (w.get('seizoen') or ''):
            behouden[wid] = w
        else:
            weg += 1
    if weg:
        zeg('Uit het bestaande bestand verwijderd (ander seizoen): %d' % weg)
    return behouden


def is_gewijzigd(oud, nieuwe):
    """Vergelijkt alleen de wedstrijden, niet het tijdstempel. Anders zou
    elke run een wijziging lijken en kregen we dagelijks een lege commit."""
    if not oud:
        return True
    return (oud.get('wedstrijden') or {}) != nieuwe


# ---------------------------------------------------------------------------
# HOOFDLOGICA
# ---------------------------------------------------------------------------

def main():
    toon = '--toon' in sys.argv

    zeg('=' * 66)
    zeg('bouw_euromatches v1.5 - CL, EL en Conference League')
    zeg('Verwacht seizoenslabel: %s' % SEIZOEN_LABEL)
    zeg('=' * 66)

    if not BSD_KEY:
        zeg('FOUT: BSD_KEY staat niet in de omgeving.')
        zeg('WIJZIGING=nee')
        return 1

    # --- clublijst ---------------------------------------------------------
    # Uit clubs.json, zodat niemand hoeft bij te werken wie Europees speelt.
    try:
        clubs = haal_json(CLUBS_URL)
        onze_clubs = set(str(k) for k in clubs)
    except Exception as e:
        # Zonder clublijst kunnen we niet filteren, en alles doorlaten zou
        # het bestand vullen met wedstrijden die er niet horen.
        zeg('FOUT: clubs.json niet op te halen (%s)' % e)
        zeg('WIJZIGING=nee')
        return 1
    zeg('clubs.json: %d clubs als filter' % len(onze_clubs))

    # --- events ophalen ----------------------------------------------------
    verse = {}
    mislukt = []

    for lid, (code, naam, sid) in LEAGUES.items():
        try:
            events, verwacht = haal_events(lid, sid, code)
        except Exception as e:
            zeg('  %-5s league %-3d FOUT: %s' % (code, lid, e))
            mislukt.append(code)
            continue

        # Seizoenscontrole. Een verouderd season_id levert stil vorig jaar op.
        labels = {}
        for ev in events:
            s = seizoen_van(ev) or '(geen)'
            labels[s] = labels.get(s, 0) + 1

        goed = [ev for ev in events if SEIZOEN_LABEL in seizoen_van(ev)]

        aantal = 0
        for ev in goed:
            omgezet = zet_om(ev, code, onze_clubs)
            if omgezet is not None:
                sleutel = str(ev.get('id') or '')
                if sleutel:
                    verse[sleutel] = omgezet
                    aantal += 1

        waarschuwing = ''
        if len(goed) != len(events):
            waarschuwing = '  LET OP: %d van %d events dragen een ander ' \
                           'seizoenslabel (%s)' % (
                               len(events) - len(goed), len(events),
                               ', '.join('%s x%d' % (k, v)
                                         for k, v in sorted(labels.items())))
        if verwacht is not None and len(events) != verwacht:
            waarschuwing += '  LET OP: count=%s maar %d opgehaald' % (
                verwacht, len(events))

        zeg('  %-5s league %-3d season %-5s -> %3d events, %2d Belgisch%s'
              % (code, lid, sid, len(events), aantal, waarschuwing))
        time.sleep(PAUZE)

    if mislukt:
        # Een competitie die faalt mag niet leiden tot een bestand waarin die
        # competitie ontbreekt: dat zou wedstrijden laten verdwijnen.
        zeg('Niet alle competities opgehaald (%s). Niets weggeschreven.'
              % ', '.join(mislukt))
        zeg('WIJZIGING=nee')
        return 1

    zeg('Belgische wedstrijden gevonden: %d  (ophalen duurde %.0fs)'
        % (len(verse), verstreken()))

    if not verse:
        zeg('Geen Europese wedstrijden met een Belgische club.')
        zeg('Klopt het seizoenslabel of season_id niet meer, pas dan')
        zeg('SEIZOEN_LABEL en SEASON_IDS aan.')
        zeg('WIJZIGING=nee')
        return 0

    # --- samenvoegen -------------------------------------------------------
    oud = lees_bestaand()
    wedstrijden = bewaarde_wedstrijden(oud)
    vooraf = len(wedstrijden)
    wedstrijden.update(verse)
    if vooraf:
        zeg('Uit het bestaande bestand behouden: %d, waarvan %d niet meer '
              'in de bron' % (vooraf, len(wedstrijden) - len(verse)))

    if toon:
        for wid, w in sorted(wedstrijden.items(),
                             key=lambda x: (x[1].get('date') or '')):
            score = ''
            if w.get('home_score') is not None and w.get('away_score') is not None:
                score = ' %s-%s' % (w['home_score'], w['away_score'])
                if w.get('home_pens') is not None:
                    score += ' (%s-%s ns)' % (w['home_pens'], w['away_pens'])
                elif w.get('verlenging'):
                    score += ' nv'
            zeg('  %-10s %-5s %-14s %-28s - %-28s%s  [%s]' % (
                w.get('date', ''), w.get('competitie', ''), w.get('ronde', ''),
                w.get('home_team', ''), w.get('away_team', ''), score,
                w.get('status') or '?'))

    # --- wegschrijven ------------------------------------------------------
    if not is_gewijzigd(oud, wedstrijden):
        zeg('Inhoud ongewijzigd. Niets weggeschreven.')
        zeg('WIJZIGING=nee')
        return 0

    uit = {
        'bijgewerkt': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'seizoen': SEIZOEN_LABEL,
        'wedstrijden': wedstrijden,
    }
    inhoud = json.dumps(uit, ensure_ascii=False, indent=1).encode('utf-8')
    io.open(UIT_BESTAND, 'wb').write(inhoud)
    zeg('%s geschreven - %d wedstrijden, %.1f kB'
          % (UIT_BESTAND, len(wedstrijden), len(inhoud) / 1024.0))

    zeg('WIJZIGING=ja')
    return 0


if __name__ == '__main__':
    sys.exit(main())
