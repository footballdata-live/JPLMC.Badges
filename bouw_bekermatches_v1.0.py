#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bouw_bekermatches v1.0
======================

Bouwt bekermatches.json voor de fanpages: alle Croky Cup-wedstrijden waar
minstens een JPL-club bij betrokken is.

BRON
----
proleague.be is een Next.js-site die server-side rendert. De volledige
wedstrijddata staat in het <script id="__NEXT_DATA__"> blok van de rauwe
HTML. Er is dus geen API-sleutel nodig en geen HTML-parser: gewoon fetchen
met een browser User-Agent en de JSON eruit lezen.

Zonder browser User-Agent geeft proleague.be 403. Dat is bewezen in
bouw_players_v3.3.py en geldt hier onverkort.

De kalenderpagina honoreert ?roundId={uuid} bij het server-side renderen.
Dat is met een diagnostic bevestigd: status 200 en de gevraagde ronde komt
terug. De _next/data-route werkt NIET bruikbaar en is bewust niet gebruikt,
want die hangt bovendien af van een buildId die bij elke deployment van de
Pro League verandert.

ZELFONTDEKKEND
--------------
De module bevat data.rounds met alle rondes van de huidige editie, elk met
hun eigen UUID. Er wordt dus niets gehardcodeerd behalve het pad van de
kalenderpagina zelf. Bij een nieuw seizoen verandert de editie-UUID, maar
daar hoeft niemand iets voor te doen.

CLUBHERKENNING
--------------
Op slug, niet op naam en niet op de driecijferige code.

  - De naam wijkt af: de Pro League zegt "STVV", clubs.json zegt
    "Sint-Truidense VV". En "Royale Union Saint-Gilloise" tegenover
    "Union Saint-Gilloise".
  - De code wijkt bij twee clubs af: Union is STG bij de Pro League en USG
    bij ons, RAAL is LAL bij de Pro League en RAAL bij ons. Matchen op code
    zou die twee clubs stil uit de bekerkalender laten vallen. Geen
    foutmelding, gewoon twee fanpages zonder bekerwedstrijden.

De slug bevat achteraan een numerieke Pro League-ID en is stabiel over
seizoenen heen. Vandaar de bevroren tabel hieronder, geverifieerd tegen
clubs.json: 18 op 18, elke team_id precies een keer gebruikt.

Een tegenstander die niet in de tabel staat is een amateurclub. Die wordt
niet overgeslagen, de wedstrijd wel behouden: home_team_id blijft leeg maar
de naam staat er, zodat "Club Brugge - KVC Winkel Sport" gewoon correct
toont op de fanpage.

LEGE KALENDER IS GEEN FOUT
--------------------------
Bij de start van een seizoen bestaat de bekerkalender nog niet, en de
JPL-clubs stappen pas in vanaf Round of 32. Vindt het script geen rondes of
geen relevante wedstrijden, dan schrijft het niets weg, laat het een
bestaand bestand ongemoeid, meldt het WIJZIGING=nee en eindigt het met
exitcode 0. Zo kan de workflow vanaf nu al dagelijks draaien en vult het
bestand zich vanzelf zodra de Pro League publiceert.

NIET INCREMENTEEL
-----------------
Anders dan bouw_playerstats_v1.0.py bouwt dit script de volledige lijst elke
run opnieuw op uit de bron. Dat mag hier: het zijn hooguit vijf rondes en
een dertigtal wedstrijden. Er wordt alleen gepusht als de inhoud werkelijk
verschilt van wat er in de repo staat, zodat er geen commits ontstaan die
niets veranderen. Het veld "bijgewerkt" telt daarbij niet mee, anders zou
elke run een wijziging lijken.

GEBRUIK
-------
    python3 bouw_bekermatches_v1.0.py              # lokaal, schrijft alleen
    python3 bouw_bekermatches_v1.0.py --push       # pusht naar de repo
    python3 bouw_bekermatches_v1.0.py --toon       # print de gevonden lijst
"""

import base64
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# CONFIGURATIE
# ---------------------------------------------------------------------------

# Het pad is bevestigd via de console: location.pathname was
# /kalender-croky-cup. De host proberen we in deze volgorde, de eerste die
# bruikbare HTML teruggeeft wint. Zo hoeft niemand te gokken of er www voor
# moet en blijft het werken als de Pro League dat ooit omzet.
HOSTS = [
    'https://www.proleague.be',
    'https://proleague.be',
]
KALENDER_PAD = '/kalender-croky-cup'

UIT_BESTAND = 'bekermatches.json'
BADGES_REPO = 'footballdata-live/JPLMC.Badges'
REPO_TOKEN = os.environ.get('DATA_REPO_TOKEN', '')

# Pauze tussen twee rondefetches. Vijf rondes per run, dus dit kost hooguit
# een tiental seconden en het houdt ons ver van elke rate limit.
PAUZE = 2.0
TIMEOUT = 30

USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
              'AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/126.0.0.0 Safari/537.36')

# ---------------------------------------------------------------------------
# CLUBTABEL
# Slug van de Pro League -> team_id zoals in clubs.json en badges.json.
# Geverifieerd tegen clubs.json op 5 september 2026: 18 op 18 gekoppeld,
# geen dubbele en geen ongebruikte team_id.
# ---------------------------------------------------------------------------

SLUG_NAAR_TEAM = {
    'cercle-brugge-3':                '235',   # Cercle Brugge
    'club-brugge-4':                  '123',   # Club Brugge
    'kaa-gent-7':                     '245',   # KAA Gent
    'krc-genk-6':                     '146',   # KRC Genk
    'kv-kortrijk-24':                 '2763',  # KV Kortrijk
    'kv-mechelen-8':                  '237',   # KV Mechelen
    'kvc-westerlo-15':                '241',   # KVC Westerlo
    'lommel-sk-29':                   '1827',  # Lommel SK
    'oh-leuven-9':                    '242',   # OH Leuven
    'raal-la-louviere-10':            '238',   # RAAL La Louviere
    'rsc-anderlecht-1':               '240',   # RSC Anderlecht
    'royal-antwerp-fc-2':             '233',   # Royal Antwerp FC
    'sk-beveren-19':                  '2414',  # SK Beveren
    'sv-zulte-waregem-16':            '236',   # SV Zulte Waregem
    'stvv-11':                        '244',   # Sint-Truidense VV
    'sporting-charleroi-12':          '243',   # Sporting Charleroi
    'standard-de-liege-13':           '239',   # Standard de Liege
    'royale-union-saint-gilloise-14': '116',   # Union Saint-Gilloise
}

# ---------------------------------------------------------------------------
# RONDENAMEN
# De bron geeft Engels. We vertalen hier zodat de fanpage geen vertaallogica
# nodig heeft. Een onbekende ronde valt terug op de originele naam: dan staat
# er tijdelijk Engels op de pagina, wat altijd beter is dan een leeg veld.
# ---------------------------------------------------------------------------

RONDE_NL = {
    'finale':          'Finale',
    'final':           'Finale',
    'semi-finals':     'Halve finale',
    'semi-final':      'Halve finale',
    'quarter-finals':  'Kwartfinale',
    'quarter-final':   'Kwartfinale',
    'round of 16':     'Achtste finale',
    'round of 32':     '1/16 finale',
    'round of 64':     '1/32 finale',
    'round of 128':    '1/64 finale',
}


def vertaal_ronde(naam):
    if not naam:
        return ''
    return RONDE_NL.get(naam.strip().lower(), naam.strip())


def leg_achtervoegsel(gameweek_naam):
    """"Semi-finals | Leg 1" -> " heen". Heen- en terugwedstrijden bestaan
    alleen in de halve finale, maar we detecteren het generiek."""
    if not gameweek_naam:
        return ''
    laag = gameweek_naam.lower()
    if 'leg 1' in laag:
        return ' heen'
    if 'leg 2' in laag:
        return ' terug'
    return ''


# ---------------------------------------------------------------------------
# OPHALEN
# ---------------------------------------------------------------------------

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


def haal_html(url):
    rq = urllib.request.Request(url, headers={
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'nl-BE,nl;q=0.9',
    })
    with urllib.request.urlopen(rq, timeout=TIMEOUT) as r:
        rauw = r.read()
    return rauw.decode('utf-8', errors='replace')


def haal_next_data(url):
    """HTML ophalen en het __NEXT_DATA__ blok als dict teruggeven."""
    html = haal_html(url)
    m = NEXT_DATA_RE.search(html)
    if not m:
        raise ValueError('__NEXT_DATA__ niet gevonden in %s' % url)
    return json.loads(m.group(1))


def vind_module(node, diepte=0):
    """De football_list-module zoeken waar de wedstrijden in zitten.

    Bewust op type gezocht en niet op grids[0].areas[0].modules[0]. Zet de
    Pro League ooit een banner boven de kalender, dan schuift die index op
    en breekt een positionele verwijzing zonder foutmelding.
    """
    if node is None or diepte > 14:
        return None
    if isinstance(node, dict):
        if node.get('type') == 'football_list':
            data = node.get('data')
            if isinstance(data, dict) and 'matches' in data:
                return node
        for waarde in node.values():
            gevonden = vind_module(waarde, diepte + 1)
            if gevonden is not None:
                return gevonden
    elif isinstance(node, list):
        for waarde in node:
            gevonden = vind_module(waarde, diepte + 1)
            if gevonden is not None:
                return gevonden
    return None


def bepaal_basis():
    """De eerste host proberen die bruikbare HTML teruggeeft."""
    laatste_fout = None
    for host in HOSTS:
        url = host + KALENDER_PAD
        try:
            data = haal_next_data(url)
            mod = vind_module(data)
            if mod is not None:
                print('Bron: %s' % url)
                return host, mod
            laatste_fout = 'module niet gevonden'
        except Exception as e:
            laatste_fout = str(e)
        print('  %s werkte niet (%s)' % (url, laatste_fout))
    return None, None


# ---------------------------------------------------------------------------
# OMZETTEN
# ---------------------------------------------------------------------------

def team_id_van(team):
    if not isinstance(team, dict):
        return ''
    return SLUG_NAAR_TEAM.get(team.get('slug') or '', '')


def team_naam_van(team):
    if not isinstance(team, dict):
        return ''
    return team.get('name') or team.get('displayName') or ''


def zet_om(w):
    """Een wedstrijdobject van de Pro League omzetten naar ons formaat.

    Geeft None terug als er geen enkele JPL-club bij betrokken is. Zo vallen
    de amateurrondes vanzelf weg zonder dat we die clubs moeten kennen.
    """
    thuis = w.get('homeTeam') or {}
    uit = w.get('awayTeam') or {}

    thuis_id = team_id_van(thuis)
    uit_id = team_id_van(uit)
    if not thuis_id and not uit_id:
        return None

    gw = w.get('gameweek') or {}
    ronde_obj = gw.get('round') or {}
    ronde = vertaal_ronde(ronde_obj.get('name') or gw.get('name'))
    ronde += leg_achtervoegsel(gw.get('name'))

    periode = w.get('period') or {}

    # De bron zet een Z achter de tijd en beweert daarmee UTC. Dat nemen we
    # over zoals het er staat: niet compenseren op een vermoeden. Klopt het
    # niet, dan blijkt dat op de eerste echte wedstrijd en passen we het op
    # een vastgestelde afwijking aan, niet op een verwachte.
    return {
        'competitie':   'BEKER',
        'ronde':        ronde,
        'date':         w.get('date') or '',
        'kickoff':      w.get('time') or '',
        'home_team':    team_naam_van(thuis),
        'away_team':    team_naam_van(uit),
        'home_team_id': thuis_id,
        'away_team_id': uit_id,
        'home_score':   w.get('homeScore'),
        'away_score':   w.get('awayScore'),
        'home_pens':    w.get('homeShootOutScore'),
        'away_pens':    w.get('awayShootOutScore'),
        'status':       periode.get('shortName') or '',
        'status_type':  periode.get('type') or '',
        'slug':         w.get('slug') or '',
    }


# ---------------------------------------------------------------------------
# PUSHEN
# Zelfde patroon als push_naar_repo() in bouw_playerstats_v1.0.py.
# ---------------------------------------------------------------------------

def push_naar_repo(pad, inhoud_bytes):
    if not REPO_TOKEN:
        print('[REPO] DATA_REPO_TOKEN niet ingesteld, push overgeslagen')
        return False

    api_url = 'https://api.github.com/repos/%s/contents/%s' % (BADGES_REPO, pad)
    headers = {
        'Authorization': 'token ' + REPO_TOKEN,
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'jplmc-bekermatches',
        'Content-Type': 'application/json',
    }

    sha = None
    try:
        rq = urllib.request.Request(api_url, headers=headers)
        huidig = json.load(urllib.request.urlopen(rq, timeout=TIMEOUT))
        sha = huidig.get('sha')
    except Exception:
        sha = None  # bestaat nog niet, dat is een create in plaats van update

    payload = {
        'message': 'chore: update bekermatches.json [skip ci]',
        'content': base64.b64encode(inhoud_bytes).decode('utf-8'),
    }
    if sha:
        payload['sha'] = sha

    try:
        rq = urllib.request.Request(
            api_url, headers=headers,
            data=json.dumps(payload).encode('utf-8'), method='PUT')
        urllib.request.urlopen(rq, timeout=TIMEOUT)
        print('[REPO] bekermatches.json gepusht naar %s' % BADGES_REPO)
        return True
    except Exception as e:
        print('[REPO] Push mislukt: %s' % e)
        return False


def lees_bestaand():
    if not os.path.exists(UIT_BESTAND):
        return None
    try:
        return json.load(io.open(UIT_BESTAND, encoding='utf-8'))
    except Exception:
        return None


def is_gewijzigd(oud, nieuwe_wedstrijden):
    """Vergelijkt alleen de wedstrijden, niet het tijdstempel. Anders zou
    elke run een wijziging lijken en kregen we dagelijks een lege commit."""
    if not oud:
        return True
    return (oud.get('wedstrijden') or {}) != nieuwe_wedstrijden


# ---------------------------------------------------------------------------
# HOOFDLOGICA
# ---------------------------------------------------------------------------

def main():
    push = '--push' in sys.argv
    toon = '--toon' in sys.argv

    print('=' * 62)
    print('bouw_bekermatches v1.0 - Croky Cup')
    print('=' * 62)

    host, mod = bepaal_basis()
    if mod is None:
        # Geen bereikbare bron. Dat is iets anders dan een lege kalender, dus
        # dit meldt wel een fout, maar laat het bestaande bestand met rust.
        print('FOUT: kalenderpagina niet bereikbaar of module niet gevonden.')
        print('WIJZIGING=nee')
        return 1

    rondes = (mod.get('data') or {}).get('rounds') or []
    editie = (mod.get('data') or {}).get('editionId') or '(onbekend)'
    print('Editie: %s' % editie)
    print('Rondes gevonden: %d' % len(rondes))

    if not rondes:
        # Normaal bij de start van een seizoen. Geen fout.
        print('Nog geen rondes gepubliceerd. Niets te doen.')
        print('WIJZIGING=nee')
        return 0

    # --- Alle rondes aflopen ------------------------------------------------
    ruwe = {}
    for i, ronde in enumerate(rondes, 1):
        rid = ronde.get('id')
        rnaam = ronde.get('name') or '?'
        if not rid:
            continue

        url = '%s%s?roundId=%s' % (host, KALENDER_PAD, rid)
        try:
            data = haal_next_data(url)
            rmod = vind_module(data)
            wedstrijden = ((rmod or {}).get('data') or {}).get('matches') or []
        except Exception as e:
            # Een ronde die faalt mag de rest niet meeslepen.
            print('  [%d/%d] %-16s FOUT: %s' % (i, len(rondes), rnaam, e))
            continue

        nieuw = 0
        for w in wedstrijden:
            wid = w.get('id')
            if wid and wid not in ruwe:
                ruwe[wid] = w
                nieuw += 1
        print('  [%d/%d] %-16s %d wedstrijden' % (i, len(rondes), rnaam, nieuw))

        if i < len(rondes):
            time.sleep(PAUZE)

    print('Ruwe wedstrijden opgehaald: %d' % len(ruwe))

    # --- Filteren en omzetten ----------------------------------------------
    wedstrijden = {}
    for wid, w in ruwe.items():
        omgezet = zet_om(w)
        if omgezet is not None:
            wedstrijden[wid] = omgezet

    print('Met minstens een JPL-club: %d' % len(wedstrijden))

    if toon:
        for wid, w in sorted(wedstrijden.items(), key=lambda x: x[1]['date']):
            score = ''
            if w['home_score'] is not None and w['away_score'] is not None:
                score = ' %s-%s' % (w['home_score'], w['away_score'])
                if w['home_pens'] is not None and w['away_pens'] is not None:
                    score += ' (%s-%s ns)' % (w['home_pens'], w['away_pens'])
            print('  %-10s %-16s %-28s - %-28s%s  [%s]' % (
                w['date'], w['ronde'], w['home_team'], w['away_team'],
                score, w['status'] or 'gepland'))

    if not wedstrijden:
        # De amateurrondes lopen, onze clubs stappen pas later in. Geen fout.
        print('Nog geen wedstrijden met een JPL-club. Bestaand bestand blijft staan.')
        print('WIJZIGING=nee')
        return 0

    # --- Vergelijken en wegschrijven ---------------------------------------
    oud = lees_bestaand()
    if not is_gewijzigd(oud, wedstrijden):
        print('Inhoud ongewijzigd. Niets weggeschreven.')
        print('WIJZIGING=nee')
        return 0

    uit = {
        'bijgewerkt': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'editie': editie,
        'wedstrijden': wedstrijden,
    }
    inhoud = json.dumps(uit, ensure_ascii=False, indent=1).encode('utf-8')
    io.open(UIT_BESTAND, 'wb').write(inhoud)
    print('%s geschreven - %d wedstrijden, %.1f kB'
          % (UIT_BESTAND, len(wedstrijden), len(inhoud) / 1024.0))

    if push:
        push_naar_repo(UIT_BESTAND, inhoud)
    else:
        print('(geen --push meegegeven, alleen lokaal geschreven)')

    print('WIJZIGING=ja')
    return 0


if __name__ == '__main__':
    sys.exit(main())
