#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bouw_bekermatches v1.2
======================

Bouwt bekermatches.json voor de fanpages: alle Croky Cup-wedstrijden waar
minstens een JPL-club bij betrokken is.

WIJZIGING TEN OPZICHTE VAN v1.1
-------------------------------
De push naar GitHub is eruit. Dit script schrijft alleen nog het bestand;
de commit gebeurt in de workflow met de ingebouwde GITHUB_TOKEN.

Reden: de workflow draait IN footballdata-live/JPLMC.Badges zelf, dus een
PAT is overbodig. Dat scheelt een vervaldatum, en de vorige tokens verliepen
op 1 september. Dit is hetzelfde patroon als playerstats.yml v2, dat om
precies deze reden al eerder omgebouwd is.

Het bestaande bestand komt nu mee met de checkout in plaats van via GitHub
Pages opgehaald te worden. Dat maakt het samenvoegen betrouwbaarder: Pages
loopt achter op de repo omdat de site eerst moet bouwen, dus twee runs kort
na elkaar lazen daar een verouderde versie.

WIJZIGINGEN IN v1.1 TEN OPZICHTE VAN v1.0
-----------------------------------------
Alle drie komen voort uit wat de eerste echte run aan het licht bracht.

(1) SEIZOENSCONTROLE. v1.0 haalde dertig wedstrijden op en vond dat prima,
    maar het waren de dertig wedstrijden van seizoen 2025/2026. De
    kalenderpagina valt namelijk terug op de laatst gepubliceerde editie
    zolang het nieuwe seizoen er nog niet staat. Een lege kalender gedraagt
    zich dus niet als leeg, maar als vorig jaar. Zonder deze controle
    stonden er bij de lancering dertig wedstrijden van vorig seizoen op de
    fanpages, met uitslagen en al.

    HUIDIG_SEIZOEN wordt vergeleken met season.name uit de bron. Komt het
    niet overeen, dan gebeurt er niets. Een regel per jaar bijwerken.

(2) SAMENVOEGEN IN PLAATS VAN VERVANGEN. v1.0 bouwde de lijst elke run
    volledig opnieuw op. Dat verliest wedstrijden die uit de bron
    verdwijnen, en dat gebeurt aantoonbaar: zie punt 3.

(3) SPEELWEEKWAARSCHUWING. Een ronde kan meerdere gameweeks hebben. De
    halve finale heeft er twee, Leg 1 en Leg 2. Met ?roundId= geeft de
    server altijd de currentGameweek terug, en de heenwedstrijden zijn
    server-side niet op te vragen.

    Dat is met een diagnostic vastgesteld, niet vermoed. Zes varianten
    geprobeerd (gameweekId, gameweek, weekId, met en zonder roundId): alle
    zes gaven Leg 2. previousGameweek bestaat wel en kent Leg 1 bij naam,
    maar bevat alleen metadata (id, name, shortName, week, round) en geen
    matches. In de HTML staan zes links en die gaan alle zes over roundId.
    De speelweeknavigatie is client-side en loopt via de makerweb-API.

    Niet opgelost via die API, bewust. Het gaat om twee wedstrijden per
    seizoen, en dankzij (2) halen we ze alsnog binnen: in de dagen rond de
    heenwedstrijd is Leg 1 de currentGameweek, het script draait dagelijks,
    dus hij komt voorbij en blijft daarna bewaard.

BRON
----
proleague.be is een Next.js-site die server-side rendert. De volledige
wedstrijddata staat in het <script id="__NEXT_DATA__"> blok van de rauwe
HTML. Geen API-sleutel nodig, geen HTML-parser: fetchen met een browser
User-Agent en de JSON eruit lezen.

Zonder browser User-Agent geeft proleague.be 403. Bewezen in
bouw_players_v3.3.py en hier onverkort geldig.

De kalenderpagina honoreert ?roundId={uuid} bij het server-side renderen.
Bevestigd: status 200 en de gevraagde ronde komt terug. De _next/data-route
is bewust niet gebruikt, die hangt af van een buildId die bij elke
deployment verandert.

ZELFONTDEKKEND
--------------
data.rounds bevat alle rondes van de huidige editie met hun UUID's. Er
wordt niets gehardcodeerd behalve het pad van de kalenderpagina en het
seizoenslabel.

CLUBHERKENNING
--------------
Op slug, niet op naam en niet op de driecijferige code.

  - De naam wijkt af: de Pro League zegt "STVV", clubs.json zegt
    "Sint-Truidense VV". En "Royale Union Saint-Gilloise" tegenover
    "Union Saint-Gilloise".
  - De code wijkt bij twee clubs af: Union is STG bij de Pro League en USG
    bij ons, RAAL is LAL en RAAL. Matchen op code zou die twee clubs stil
    uit de bekerkalender laten vallen. Geen foutmelding, gewoon twee
    fanpages zonder bekerwedstrijden.

De slug bevat achteraan een numerieke Pro League-ID en is stabiel over
seizoenen heen.

Een tegenstander die niet in de tabel staat is een amateurclub. Die wordt
niet overgeslagen, de wedstrijd wel behouden: het team_id blijft leeg maar
de naam staat er, zodat "Club Brugge - Eendracht Aalst Lede" correct toont.

GEBRUIK
-------
    python3 bouw_bekermatches_v1.2.py              # schrijft bekermatches.json
    python3 bouw_bekermatches_v1.2.py --toon       # print ook de lijst

Committen doet de workflow, niet dit script.
"""

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

# Het pad is bevestigd via de console. De host proberen we in deze volgorde,
# de eerste die bruikbare HTML teruggeeft wint. In de praktijk werkt
# www.proleague.be; de tweede staat er voor het geval de Pro League dat ooit
# omzet.
HOSTS = [
    'https://www.proleague.be',
    'https://proleague.be',
]
KALENDER_PAD = '/kalender-croky-cup'

# ---------------------------------------------------------------------------
# SEIZOENSLABEL - EEN REGEL PER JAAR BIJWERKEN
#
# Exact zoals season.name het schrijft in de bron. Bij de eerste run van
# seizoen 2027/2028 moet hier 'Seizoen 2027/2028' komen te staan, anders
# blijft het script zwijgen en vult de kalender zich niet.
#
# Het script waarschuwt daar zelf voor: vindt hij uitsluitend wedstrijden
# van een ander seizoen, dan print hij welk seizoen de bron aanbiedt.
# ---------------------------------------------------------------------------

HUIDIG_SEIZOEN = 'Seizoen 2026/2027'

UIT_BESTAND = 'bekermatches.json'

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
# Geverifieerd tegen clubs.json: 18 op 18 gekoppeld, geen dubbele en geen
# ongebruikte team_id.
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
    """"Semi-finals | Leg 1" -> " heen". Heen en terug bestaat alleen in de
    halve finale, maar we detecteren het generiek."""
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

def seizoen_van(w):
    seizoen = w.get('season') or {}
    return (seizoen.get('name') or '').strip()


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

    De seizoenscontrole gebeurt NIET hier maar in main(), zodat we in de log
    kunnen melden welk seizoen de bron aanbiedt in plaats van stilzwijgend
    alles weg te gooien.
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
    # niet, dan blijkt dat op de eerste echte wedstrijd en passen we het aan
    # op een vastgestelde afwijking, niet op een verwachte.
    return {
        'competitie':   'BEKER',
        'seizoen':      seizoen_van(w),
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
    """De wedstrijden uit het bestaande bestand die we willen behouden.

    Alleen die van het huidige seizoen. Anders sleept het bestand jaar na
    jaar oude edities mee, en dat is precies het probleem dat de
    seizoenscontrole moet voorkomen.

    Een wedstrijd zonder seizoensveld komt uit een oudere scriptversie en
    wordt weggegooid: we weten niet van welk seizoen hij is, en gokken is
    hier erger dan opnieuw ophalen.
    """
    if not oud:
        return {}
    behouden = {}
    weg = 0
    for wid, w in (oud.get('wedstrijden') or {}).items():
        if isinstance(w, dict) and w.get('seizoen') == HUIDIG_SEIZOEN:
            behouden[wid] = w
        else:
            weg += 1
    if weg:
        print('Uit het bestaande bestand verwijderd (ander seizoen): %d' % weg)
    return behouden


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
    toon = '--toon' in sys.argv

    print('=' * 62)
    print('bouw_bekermatches v1.2 - Croky Cup')
    print('Verwacht seizoen: %s' % HUIDIG_SEIZOEN)
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
            rdata = (rmod or {}).get('data') or {}
            wedstrijden = rdata.get('matches') or []
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

        # --- Speelweekwaarschuwing -----------------------------------------
        # Heeft deze ronde meerdere gameweeks, dan krijgen we er maar een:
        # de currentGameweek. De andere is server-side niet op te vragen.
        # Dankzij het samenvoegen hieronder blijft een eerder opgehaalde leg
        # wel bewaard, dus dit is een melding en geen fout.
        alle_gw = ronde.get('gameweeks') or []
        huidige_gw = rdata.get('gameweek') or {}
        extra = ''
        if len(alle_gw) > 1:
            gemist = [g.get('name') for g in alle_gw
                      if g.get('id') != huidige_gw.get('id')]
            if gemist:
                extra = '  (LET OP: alleen %r, niet server-side: %s)' % (
                    huidige_gw.get('name') or '?', ', '.join(
                        n for n in gemist if n))

        print('  [%d/%d] %-16s %d wedstrijden%s'
              % (i, len(rondes), rnaam, nieuw, extra))

        if i < len(rondes):
            time.sleep(PAUZE)

    print('Ruwe wedstrijden opgehaald: %d' % len(ruwe))

    # --- Seizoenscontrole ---------------------------------------------------
    # De kalenderpagina valt terug op de laatst gepubliceerde editie zolang
    # het nieuwe seizoen er niet staat. Zonder deze controle vullen we de
    # fanpages met vorig seizoen.
    seizoenen = {}
    for w in ruwe.values():
        s = seizoen_van(w) or '(geen seizoensveld)'
        seizoenen[s] = seizoenen.get(s, 0) + 1

    if seizoenen:
        print('Seizoenen in de bron: %s' % ', '.join(
            '%s (%d)' % (s, n) for s, n in sorted(seizoenen.items())))

    van_dit_seizoen = {wid: w for wid, w in ruwe.items()
                       if seizoen_van(w) == HUIDIG_SEIZOEN}

    if not van_dit_seizoen:
        print('De bron staat nog op een andere editie dan %s.' % HUIDIG_SEIZOEN)
        print('Dat is normaal zolang de Pro League de nieuwe bekerkalender')
        print('niet gepubliceerd heeft. Bestaand bestand blijft ongemoeid.')
        print('Klopt het seizoenslabel niet meer, pas dan HUIDIG_SEIZOEN aan.')
        print('WIJZIGING=nee')
        return 0

    print('Van %s: %d' % (HUIDIG_SEIZOEN, len(van_dit_seizoen)))

    # --- Filteren en omzetten ----------------------------------------------
    verse = {}
    for wid, w in van_dit_seizoen.items():
        omgezet = zet_om(w)
        if omgezet is not None:
            verse[wid] = omgezet

    print('Met minstens een JPL-club: %d' % len(verse))

    # --- Samenvoegen met wat er al staat -----------------------------------
    # Verse gegevens winnen, maar een wedstrijd die uit de bron verdwenen is
    # blijft staan met wat we eerder ophaalden. Zo overleeft de heenwedstrijd
    # van de halve finale het moment waarop de site naar Leg 2 doorschakelt.
    oud = lees_bestaand()
    wedstrijden = bewaarde_wedstrijden(oud)
    behouden_vooraf = len(wedstrijden)
    wedstrijden.update(verse)
    bewaard_extra = len(wedstrijden) - len(verse)
    if behouden_vooraf:
        print('Uit het bestaande bestand behouden: %d, waarvan %d niet meer '
              'in de bron' % (behouden_vooraf, bewaard_extra))

    if toon:
        for wid, w in sorted(wedstrijden.items(),
                             key=lambda x: (x[1].get('date') or '')):
            score = ''
            if w.get('home_score') is not None and w.get('away_score') is not None:
                score = ' %s-%s' % (w['home_score'], w['away_score'])
                if w.get('home_pens') is not None and w.get('away_pens') is not None:
                    score += ' (%s-%s ns)' % (w['home_pens'], w['away_pens'])
            print('  %-10s %-18s %-30s - %-30s%s  [%s]' % (
                w.get('date', ''), w.get('ronde', ''), w.get('home_team', ''),
                w.get('away_team', ''), score, w.get('status') or 'gepland'))

    if not wedstrijden:
        # De amateurrondes lopen, onze clubs stappen pas later in. Geen fout.
        print('Nog geen wedstrijden met een JPL-club.')
        print('WIJZIGING=nee')
        return 0

    # --- Vergelijken en wegschrijven ---------------------------------------
    if not is_gewijzigd(oud, wedstrijden):
        print('Inhoud ongewijzigd. Niets weggeschreven.')
        print('WIJZIGING=nee')
        return 0

    uit = {
        'bijgewerkt': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'seizoen': HUIDIG_SEIZOEN,
        'editie': editie,
        'wedstrijden': wedstrijden,
    }
    inhoud = json.dumps(uit, ensure_ascii=False, indent=1).encode('utf-8')
    io.open(UIT_BESTAND, 'wb').write(inhoud)
    print('%s geschreven - %d wedstrijden, %.1f kB'
          % (UIT_BESTAND, len(wedstrijden), len(inhoud) / 1024.0))

    print('WIJZIGING=ja')
    return 0


if __name__ == '__main__':
    sys.exit(main())
