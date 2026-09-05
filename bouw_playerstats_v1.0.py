#!/usr/bin/env python3
# =============================================================================
#  JPLMC Fanpages - bouw_playerstats_v1.0.py
# =============================================================================
#  Schrijft playerstats.json in de repo footballdata-live/JPLMC.Badges.
#  Dat bestand voedt de spelerkaarten op de clubfanpages: doelpunten,
#  assists, minuten, clean sheets en kaarten per speler per club.
#
#  WAAROM DIT BESTAAT EN NIET UIT DE KV KOMT
#  Het managerspel berekent deze cijfers al elke speeldag, maar bewaart in
#  fm:pts:{speeldag} PUNTEN, geen aantallen:
#
#      voeg('goals', (r.goals || 0) * GOAL_PTS[pos])   # G:10 D:6 M:5 F:5
#
#  Terugdelen door GOAL_PTS werkt alleen zolang de positie van een speler
#  niet verandert. De Pro League herclassificeerde dit seizoen achttien
#  spelers halverwege, waardoor historische punten met een andere
#  vermenigvuldiger berekend zijn dan de huidige positie zou opleveren.
#  Die deling faalt dan stil. Daarom leest dit script de ruwe aantallen
#  rechtstreeks bij BSD.
#
#  WAAROM NIET CLIENT-SIDE VANUIT DE FANPAGE
#  De JPLMC-api Worker heeft een rate limiter van 30 verzoeken per 60
#  seconden per IP. Tegen het seizoenseinde zijn er 34 wedstrijden per club,
#  dus een fanpage die zelf aggregeert loopt gegarandeerd tegen een 429.
#
#  INCREMENTEEL
#  Een afgelopen wedstrijd verandert nooit meer. Het script houdt in
#  events_verwerkt bij welke events al geteld zijn en raakt die niet meer
#  aan. Per speeldag zijn dat negen nieuwe wedstrijden, niet 34 keer alles
#  opnieuw. Zonder die lijst zou een herstart dubbeltellen.
#
#  CLEAN SHEETS - VERPLICHTE WERKWIJZE
#  goals_conceded uit player-stats mag NOOIT gebruikt worden voor
#  veldspelers: dat veld is bij hen ongeveer 11% gevuld. Toen het een keer
#  wel gebruikt werd, kregen verdedigers 3,38 clean-sheetpunten per 90 in
#  plaats van 1,04, zonder enige foutmelding. Tegendoelpunten worden hier
#  geteld binnen het tijdvenster waarin de speler op het veld stond, exact
#  zoals puntenVoorSpeler() in de manager-Worker het doet.
#
#  LET OP - GEDUPLICEERDE LOGICA
#  De venster- en clean-sheetberekening hieronder staat ook in de
#  manager-Worker (functies verwerkIncidents en puntenVoorSpeler). Die twee
#  implementaties moeten gelijk blijven. Wijzigt er een, wijzig dan de
#  andere mee.
#
#  GEBRUIK
#      BSD_KEY=...  python3 bouw_playerstats_v1.0.py
#      BSD_KEY=... DATA_REPO_TOKEN=...  python3 bouw_playerstats_v1.0.py --push
#
#  Vlaggen:
#      --uit BESTAND      standaard playerstats.json
#      --matches BESTAND  standaard matches.json (lokaal); ontbreekt die,
#                         dan wordt hij van GitHub Pages gehaald
#      --push             na het schrijven naar de repo pushen
#      --herbouw          events_verwerkt negeren en alles opnieuw tellen
# =============================================================================

import base64
import json
import os
import sys
import time
import urllib.request
import urllib.parse

# ----------------------------------------------------------------------------
# CONFIGURATIE
# ----------------------------------------------------------------------------

BSD_BASE       = 'https://sports.bzzoiro.com'
LEAGUE_ID      = 14
HUIDIG_SEIZOEN = 1327

BADGES_REPO    = 'footballdata-live/JPLMC.Badges'
MATCHES_URL    = 'https://footballdata-live.github.io/JPLMC.Badges/matches.json'

# Een wedstrijd waarvan de incidents na dit aantal uur nog steeds niet
# kloppen met de eindstand wordt alsnog geteld. Zonder deze noodrem zou zo
# een wedstrijd nooit in het bestand terechtkomen.
NOODREM_UREN = 24

# Statussen die BSD gebruikt voor een afgelopen wedstrijd.
DONE_STATUS = ('finished', 'ft', 'aet', 'pen')


def arg(vlag, standaard):
    if vlag in sys.argv:
        i = sys.argv.index(vlag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return standaard


UIT_BESTAND     = arg('--uit', 'playerstats.json')
MATCHES_BESTAND = arg('--matches', 'matches.json')
PUSHEN          = '--push' in sys.argv
HERBOUW         = '--herbouw' in sys.argv

KEY = os.environ.get('BSD_KEY') or os.environ.get('K')
if not KEY:
    print('FOUT: BSD_KEY ontbreekt in de omgeving.')
    sys.exit(1)

REPO_TOKEN = os.environ.get('DATA_REPO_TOKEN') or os.environ.get('BADGES_REPO_TOKEN')


# ----------------------------------------------------------------------------
# NETWERK
# ----------------------------------------------------------------------------

def bsd(pad, pogingen=5, stil=False):
    """BSD-call met oplopende wachttijd. Zelfde contract als in
    bouw_players_v3.3: None bij falen, nooit een uitzondering naar boven."""
    for n in range(pogingen):
        try:
            t0 = time.time()
            rq = urllib.request.Request(
                BSD_BASE + pad,
                headers={'Authorization': 'Token ' + KEY}
            )
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
            print('\n  poging %d mislukt (%s), %ds wachten...' % (n + 1, e, wacht),
                  flush=True)
            time.sleep(wacht)


def haal_json(url, pogingen=3):
    for n in range(pogingen):
        try:
            rq = urllib.request.Request(url, headers={
                'User-Agent': ('Mozilla/5.0 (X11; Linux x86_64) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) '
                               'Chrome/145.0.0.0 Safari/537.36')
            })
            return json.load(urllib.request.urlopen(rq, timeout=45))
        except Exception as e:
            if n == pogingen - 1:
                print('  FAAL %s -> %s' % (url, e))
                return None
            time.sleep(3)


# ----------------------------------------------------------------------------
# INCIDENTS
# Overgenomen uit verwerkIncidents() in de manager-Worker. Kaarten komen
# UITSLUITEND hieruit en nooit uit het veld yellow_card in player-stats,
# anders telt de eerste gele kaart dubbel.
# ----------------------------------------------------------------------------

def verwerk_incidents(lijst):
    subs_in, subs_uit, rood_min = {}, {}, {}
    goals = []
    geel, tweede_geel, rood, eigen = {}, {}, {}, {}

    for x in (lijst or []):
        t = x.get('type')

        if t == 'substitution':
            if x.get('player_in_id') is not None:
                subs_in[str(x['player_in_id'])] = x.get('minute') or 0
            if x.get('player_out_id') is not None:
                subs_uit[str(x['player_out_id'])] = x.get('minute') or 0

        elif t == 'card':
            pid = x.get('player_id')
            if pid is None:
                continue
            pid = str(pid)
            ct = x.get('card_type')
            if ct == 'yellow':
                geel[pid] = geel.get(pid, 0) + 1
            elif ct == 'yellowRed':
                # Tweede gele kaart. Bewust apart geteld en niet bij rood
                # opgeteld: de weergave beslist zelf of ze als rood telt.
                tweede_geel[pid] = tweede_geel.get(pid, 0) + 1
                rood_min[pid] = x.get('minute') or 999
            elif ct == 'red':
                rood[pid] = rood.get(pid, 0) + 1
                rood_min[pid] = x.get('minute') or 999

        elif t == 'goal':
            goals.append({
                'minuut': x.get('minute') or 0,
                'thuis': bool(x.get('is_home'))
            })
            if x.get('goal_type') == 'ownGoal' and x.get('player_id') is not None:
                pid = str(x['player_id'])
                eigen[pid] = eigen.get(pid, 0) + 1

    return {
        'subs_in': subs_in, 'subs_uit': subs_uit, 'rood_min': rood_min,
        'goals': goals, 'geel': geel, 'tweede_geel': tweede_geel,
        'rood': rood, 'eigen': eigen,
    }


def tegendoelpunten_in_venster(pid, inc, thuis):
    """Tegendoelpunten binnen het tijdvenster van de speler.
    Basisspeler start op minuut 0, invaller op zijn wisselminuut. Het
    venster eindigt bij zijn uitwissel, bij zijn rode kaart, of bij het
    einde van de wedstrijd. Identiek aan puntenVoorSpeler() in de Worker."""
    start = inc['subs_in'].get(pid, 0)
    uit   = inc['subs_uit'].get(pid, 999)
    rd    = inc['rood_min'].get(pid, 999)
    eind  = min(uit, rd)

    n = 0
    for g in inc['goals']:
        if g['thuis'] != thuis and start <= g['minuut'] <= eind:
            n += 1
    return n


# ----------------------------------------------------------------------------
# EEN WEDSTRIJD VERWERKEN
# ----------------------------------------------------------------------------

def leeg_blok():
    return {
        'wedstrijden': 0, 'basis': 0, 'invaller': 0, 'minuten': 0,
        'goals': 0, 'assists': 0, 'cleansheets': 0,
        'geel': 0, 'tweede_geel': 0, 'rood': 0, 'eigen': 0,
    }


def verwerk_event(event_id, spelers):
    """Telt een afgelopen wedstrijd op bij spelers[pid][team_id].
    Geeft terug: 'ok', 'wacht' (nog niet compleet) of 'fout'."""

    ev = bsd('/api/v2/events/%s/' % event_id)
    if ev is None:
        print('  event %s: detail niet opgehaald' % event_id)
        return 'fout'

    status = (ev.get('status') or '').lower()
    if status not in DONE_STATUS:
        return 'wacht'

    # player-stats zit op /api/player-stats/ en geeft 404 op /api/v2/.
    statsdata = bsd('/api/player-stats/?event=%s&limit=200' % event_id)
    records = (statsdata or {}).get('results') or []
    if not records:
        print('  event %s: geen player-stats' % event_id)
        return 'wacht'

    incdata = bsd('/api/v2/events/%s/incidents/' % event_id)
    if incdata is None:
        # Een null is met zekerheid een fout, geen lege wedstrijd. Zou dit
        # als lege lijst doorgaan, dan worden kaarten en wissels genegeerd
        # en krijgt bij 0-0 iedereen ten onrechte een clean sheet.
        print('  event %s: incidents niet opgehaald, volgende run opnieuw' % event_id)
        return 'wacht'

    ruwe = incdata.get('incidents') or []

    # COMPLEETHEIDSCONTROLE. BSD vult incidents soms gedeeltelijk: kaarten
    # en wissels eerst, doelpunten later. Wie dan telt, deelt clean sheets
    # uit bij een 2-2.
    aantal_goals = len([x for x in ruwe if x.get('type') == 'goal'])
    eindstand = (ev.get('home_score') or 0) + (ev.get('away_score') or 0)

    if aantal_goals != eindstand:
        aftrap = ev.get('event_date')
        te_oud = False
        if aftrap:
            try:
                t = time.mktime(time.strptime(aftrap[:19], '%Y-%m-%dT%H:%M:%S'))
                te_oud = (time.time() - t) > NOODREM_UREN * 3600
            except Exception:
                te_oud = False
        if not te_oud:
            print('  event %s: incidents nog niet compleet (%d doelpunten '
                  'tegenover eindstand %d), volgende run opnieuw'
                  % (event_id, aantal_goals, eindstand))
            return 'wacht'
        print('  NOODREM event %s: na %d uur nog %d/%d doelpunten. Toch geteld.'
              % (event_id, NOODREM_UREN, aantal_goals, eindstand))

    if not ruwe:
        print('  BLIND GETELD event %s: lege incidentlijst. Geen kaarten, '
              'wissels of eigen doelpunten. Handmatig nakijken.' % event_id)

    inc = verwerk_incidents(ruwe)

    home_team    = ev.get('home_team')
    home_team_id = ev.get('home_team_id')
    away_team_id = ev.get('away_team_id')
    if home_team_id is None or away_team_id is None:
        print('  event %s: team_id ontbreekt in het event' % event_id)
        return 'fout'

    thuis_gezien = 0
    uit_gezien = 0

    for r in records:
        p = r.get('player') or {}
        pid = p.get('id')
        if pid is None:
            continue
        pid = str(pid)

        # Thuis of uit bepalen via de teamnaam op het spelersrecord. Dit is
        # dezelfde methode die de manager-Worker in productie gebruikt.
        thuis = (p.get('team') == home_team)
        if thuis:
            thuis_gezien += 1
        else:
            uit_gezien += 1

        team_id = str(home_team_id if thuis else away_team_id)

        minuten = r.get('minutes_played') or 0
        if minuten == 0:
            # Wel op het wedstrijdblad, niet gespeeld. Niets om te tellen.
            continue

        blok = spelers.setdefault(pid, {}).setdefault(team_id, leeg_blok())

        blok['wedstrijden'] += 1
        blok['minuten']     += minuten
        blok['goals']       += r.get('goals') or 0
        blok['assists']     += r.get('goal_assist') or 0

        if pid in inc['subs_in']:
            blok['invaller'] += 1
        else:
            blok['basis'] += 1

        tegen = tegendoelpunten_in_venster(pid, inc, thuis)
        if tegen == 0 and minuten >= 60:
            blok['cleansheets'] += 1

        blok['geel']        += inc['geel'].get(pid, 0)
        blok['tweede_geel'] += inc['tweede_geel'].get(pid, 0)
        blok['rood']        += inc['rood'].get(pid, 0)
        blok['eigen']       += inc['eigen'].get(pid, 0)

    # Sanity-check op de thuis/uit-bepaling. Slaat die om, dan komen alle
    # spelers bij een ploeg terecht en zijn de clean sheets waardeloos.
    if thuis_gezien == 0 or uit_gezien == 0:
        print('  WAARSCHUWING event %s: thuis/uit-verdeling is %d/%d. '
              'De teamnaam op het spelersrecord matcht mogelijk niet met '
              'home_team (%r).' % (event_id, thuis_gezien, uit_gezien, home_team))

    return 'ok'


# ----------------------------------------------------------------------------
# NAAR DE REPO PUSHEN
# Zelfde patroon als push_matches_to_public_repo() in badges_bot.py.
# ----------------------------------------------------------------------------

def push_naar_repo(pad, inhoud_bytes):
    if not REPO_TOKEN:
        print('[REPO] DATA_REPO_TOKEN niet ingesteld, push overgeslagen')
        return False

    api_url = 'https://api.github.com/repos/%s/contents/%s' % (BADGES_REPO, pad)
    headers = {
        'Authorization': 'token ' + REPO_TOKEN,
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'jplmc-playerstats',
        'Content-Type': 'application/json',
    }

    sha = None
    try:
        rq = urllib.request.Request(api_url, headers=headers)
        huidig = json.load(urllib.request.urlopen(rq, timeout=30))
        sha = huidig.get('sha')
    except Exception:
        sha = None  # bestaat nog niet, dat is een create in plaats van update

    payload = {
        'message': 'chore: update playerstats.json [skip ci]',
        'content': base64.b64encode(inhoud_bytes).decode('utf-8'),
    }
    if sha:
        payload['sha'] = sha

    try:
        rq = urllib.request.Request(
            api_url, headers=headers,
            data=json.dumps(payload).encode('utf-8'), method='PUT'
        )
        urllib.request.urlopen(rq, timeout=30)
        print('[REPO] playerstats.json gepusht naar %s' % BADGES_REPO)
        return True
    except Exception as e:
        print('[REPO] Push mislukt: %s' % e)
        return False


# ----------------------------------------------------------------------------
# HOOFDLOGICA
# ----------------------------------------------------------------------------

def main():
    print('=' * 60)
    print('bouw_playerstats v1.0 - league %d, seizoen %d'
          % (LEAGUE_ID, HUIDIG_SEIZOEN))
    print('=' * 60)

    # --- Bestaand bestand inlezen -------------------------------------------
    vorig = None
    if os.path.exists(UIT_BESTAND):
        try:
            vorig = json.load(open(UIT_BESTAND, encoding='utf-8'))
        except Exception:
            vorig = None

    if vorig and not HERBOUW:
        spelers  = vorig.get('spelers') or {}
        verwerkt = set(str(x) for x in (vorig.get('events_verwerkt') or []))
        print('Bestaand bestand: %d spelers, %d events al verwerkt'
              % (len(spelers), len(verwerkt)))
    else:
        spelers, verwerkt = {}, set()
        if HERBOUW:
            print('--herbouw: alles opnieuw tellen')
        else:
            print('Geen bestaand bestand, we beginnen leeg')

    # --- Kalender ophalen ---------------------------------------------------
    matches = None
    if os.path.exists(MATCHES_BESTAND):
        try:
            matches = json.load(open(MATCHES_BESTAND, encoding='utf-8'))
            print('Kalender uit %s' % MATCHES_BESTAND)
        except Exception:
            matches = None
    if matches is None:
        matches = haal_json(MATCHES_URL)
        print('Kalender van GitHub Pages')
    if not matches:
        print('FOUT: kalender niet beschikbaar. Afgebroken zonder te schrijven.')
        sys.exit(1)

    # Alleen events waarvan de aftrap voorbij is en die nog niet geteld zijn.
    # Zo hoeven we voor 306 wedstrijden geen 306 statuscalls te doen.
    nu = time.time()
    kandidaten = []
    for eid, m in matches.items():
        if str(eid) in verwerkt:
            continue
        d = m.get('event_date')
        if not d:
            continue
        try:
            t = time.mktime(time.strptime(d[:19], '%Y-%m-%dT%H:%M:%S'))
        except Exception:
            continue
        if t < nu:
            kandidaten.append((t, str(eid)))

    kandidaten.sort()
    print('Kandidaten: %d wedstrijden met een aftrap in het verleden\n'
          % len(kandidaten))

    if not kandidaten:
        print('Niets nieuws te verwerken.')
        print('WIJZIGING=nee')
        return

    # --- Verwerken ----------------------------------------------------------
    nieuw, gewacht, mislukt = 0, 0, 0
    for i, (_, eid) in enumerate(kandidaten, 1):
        print('[%d/%d] event %s' % (i, len(kandidaten), eid), flush=True)
        uitkomst = verwerk_event(eid, spelers)
        if uitkomst == 'ok':
            verwerkt.add(eid)
            nieuw += 1
        elif uitkomst == 'wacht':
            gewacht += 1
        else:
            mislukt += 1

    print('\nVerwerkt: %d nieuw, %d wachten nog, %d mislukt'
          % (nieuw, gewacht, mislukt))

    if nieuw == 0:
        print('Geen enkele nieuwe wedstrijd geteld - bestand niet herschreven.')
        print('WIJZIGING=nee')
        return

    # --- Wegschrijven -------------------------------------------------------
    uit = {
        'season_id':       HUIDIG_SEIZOEN,
        'league_id':       LEAGUE_ID,
        'bron':            'BSD player-stats + incidents',
        'bron_detail':     ('aantallen, geen punten; clean sheets uit '
                            'doelpuntincidents binnen het tijdvenster van '
                            'de speler, nooit uit goals_conceded'),
        'events_verwerkt': sorted(verwerkt, key=lambda x: int(x)),
        'spelers':         dict(sorted(spelers.items(), key=lambda x: int(x[0]))),
    }

    if vorig and vorig.get('spelers') == uit['spelers'] \
            and vorig.get('events_verwerkt') == uit['events_verwerkt']:
        print('Geen inhoudelijke wijziging - bestand niet herschreven.')
        print('WIJZIGING=nee')
        return

    uit['gegenereerd'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    blob = json.dumps(uit, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    with open(UIT_BESTAND, 'wb') as f:
        f.write(blob)

    print('\n%s geschreven - %d spelers, %d events, %.1f kB'
          % (UIT_BESTAND, len(spelers), len(verwerkt), len(blob) / 1024.0))

    if PUSHEN:
        push_naar_repo(os.path.basename(UIT_BESTAND), blob)

    print('WIJZIGING=ja')


if __name__ == '__main__':
    main()
