from playwright.sync_api import sync_playwright
import json
import csv
import re
from datetime import datetime
from itertools import combinations

# ─────────────────────────────────────────
#  SETTINGS
# ─────────────────────────────────────────
BANKROLL = 100000          # Change this to your actual bankroll (UGX or USD)
MIN_PROFIT_PCT = 0.5    # Minimum profit % to flag as arbitrage (0.5 = 0.5%)
OUTPUT_CSV = "arb_opportunities.csv"

# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────
def normalize_name(name):
    """Lowercase and strip punctuation for fuzzy matching across bookmakers."""
    name = name.lower()
    # Normalize both " vs " and " - " to the same separator
    name = re.sub(r'\s+(vs\.?|-)\s+', ' v ', name)
    # Remove trailing tags like "(n)"
    name = re.sub(r'\(n\)', '', name)
    name = name.replace('/', ' ')
    name = re.sub(r'[^a-z0-9 ]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def is_player_special(team1, team2):
    """Detect player vs country specials (e.g. Kai Havertz vs Morocco)."""
    player_pattern = re.compile(r'^[A-Z][a-z]+ [A-Z][a-z]+$')
    return player_pattern.match(team1) or player_pattern.match(team2)

def calc_arb(home, draw, away):
    """Return implied margin. Below 1.0 = arbitrage opportunity."""
    try:
        return (1/home) + (1/draw) + (1/away)
    except ZeroDivisionError:
        return 99

def calc_stakes(home, draw, away, bankroll):
    """Calculate how much to bet on each outcome for guaranteed profit."""
    margin = calc_arb(home, draw, away)
    profit_pct = (1 - margin) * 100
    stake_home = (bankroll / home) / margin * home   # = bankroll / (margin * home) * home
    stake_home = bankroll * (1/home) / margin
    stake_draw = bankroll * (1/draw) / margin
    stake_away = bankroll * (1/away) / margin
    guaranteed_profit = bankroll / margin - bankroll
    return round(stake_home, 2), round(stake_draw, 2), round(stake_away, 2), round(guaranteed_profit, 2), round(profit_pct, 2)



def get_22bet_leagues(sport_id):
    """Fetch all league IDs for a given sport."""
    import requests
    url = (
        f"https://22bet.ug/service-api/LineFeed/Get1x2_VZip"
        f"?sports={sport_id}&count=50&lng=en_GB&tf=3000000&tz=3"
        f"&mode=4&country=191&partner=151&getEmpty=true&gr=337"
    )
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    response = requests.get(url, headers=headers)
    data = response.json()
    
    # Extract unique league IDs
    leagues = {}
    for event in data.get("Value", []):
        li = event.get("LI")
        ln = event.get("L", "Unknown")
        if li:
            leagues[li] = ln
    return leagues

def scrape_fortebet(page):
    print("🔄 Scraping Fortebet...")
    results = {}

    import requests

    try:
        url = "https://mobile.fortebet.ug/api/web/v1/offer/full-prematch-en"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://mobile.fortebet.ug/"
        }
        response = requests.get(url, headers=headers)
        data = response.json()

        events = data.get("data", {}).get("event", {})
        markets = data.get("data", {}).get("markets", {})
        competitors = data.get("data", {}).get("competitors", {})

        # Build a lookup: event_id -> market_1_data
        event_main_market = {}
        for market_key, market_data in markets.items():
            if market_data.get("marketId") == 1:
                eid = market_data.get("eventId")
                event_main_market[eid] = market_data

        for event_id, event in events.items():
            comp_ids = event.get("competitors", [])
            if len(comp_ids) != 2:
                continue

            team1 = competitors.get(str(comp_ids[0]), {}).get("name", "")
            team2 = competitors.get(str(comp_ids[1]), {}).get("name", "")
            if not team1 or not team2:
                continue

            match_name = f"{team1} vs {team2}"

            market_data = event_main_market.get(event_id)
            if not market_data:
                continue

            home = draw = away = None
            for odd_key, odd_data in market_data.get("odds", {}).items():
                outcome_id = odd_data.get("outcomeId")
                price = odd_data.get("odds")
                if outcome_id == 1:
                    home = price
                elif outcome_id == 2:
                    draw = price
                elif outcome_id == 3:
                    away = price

            if home and draw and away:
                key = normalize_name(match_name)
                results[key] = {
                    "match": match_name,
                    "bookmaker": "fortebet",
                    "home": float(home),
                    "draw": float(draw),
                    "away": float(away),
                    "league": "Unknown"
                }

    except Exception as e:
        print(f"  ❌ Fortebet error: {e}")

    print(f"  ✅ Fortebet: {len(results)} matches found")
    return results

def scrape_premierbet(page):
    print("🔄 Scraping Premierbet...")
    results = {}

    import requests

    try:
        url = "https://pmbet.dualsoft.bet/restapi/offer/en/sport/S/mob?locale=en"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers)
        data = response.json()

        for match in data.get("esMatches", []):
            team1 = match.get("home", "")
            team2 = match.get("away", "")
            if not team1 or not team2:
                continue

            odds = match.get("odds", {})
            home = odds.get("1")
            draw = odds.get("2")
            away = odds.get("3")

            if home and draw and away:
                match_name = f"{team1} vs {team2}"
                key = normalize_name(match_name)
                results[key] = {
                    "match": match_name,
                    "bookmaker": "premierbet",
                    "home": float(home),
                    "draw": float(draw),
                    "away": float(away),
                    "league": "Unknown"
                }

    except Exception as e:
        print(f"  ❌ Premierbet error: {e}")

    print(f"  ✅ Premierbet: {len(results)} matches found")
    return results

def scrape_betika(page):
    print("🔄 Scraping Betika...")
    results = {}

    import requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Referer": "https://www.betika.com/"
    }

    sports = [3, 6]  # 3=Soccer, 6=Basketball

    try:
        for sport_id in sports:
            page_num = 1
            while True:
                url = f"https://api-ug.betika.com/v1/uo/matches?sport_id={sport_id}&limit=100&page={page_num}"
                response = requests.get(url, headers=headers)
                data = response.json()

                matches = data.get("data", [])
                if not matches:
                    break

                for match in matches:
                    team1 = match.get("home_team", "")
                    team2 = match.get("away_team", "")
                    if not team1 or not team2:
                        continue

                    home = match.get("home_odd")
                    draw = match.get("neutral_odd")
                    away = match.get("away_odd")

                    if home and draw and away:
                        match_name = f"{team1} vs {team2}"
                        key = normalize_name(match_name)
                        results[key] = {
                            "match": match_name,
                            "bookmaker": "betika",
                            "home": float(home),
                            "draw": float(draw),
                            "away": float(away),
                            "league": match.get("competition_name", "Unknown")
                        }

                page_num += 1

    except Exception as e:
        print(f"  ❌ Betika error: {e}")

    print(f"  ✅ Betika: {len(results)} matches found")
    return results
# ─────────────────────────────────────────
#  SCRAPER: 22BET
# ─────────────────────────────────────────
def scrape_22bet(page):
    print("🔄 Scraping 22bet...")
    results = {}
    seen = set()
    player_pattern = re.compile(r'^[A-Z][a-z]+ [A-Z][a-z]+$')

    import requests

    # Sports: 1=football, 2=hockey, 3=basketball, 4=tennis, 5=baseball
    sports = [1, 2, 3, 4, 5]

    for sport_id in sports:
        try:
            url = (
                f"https://22bet.ug/service-api/LineFeed/Get1x2_VZip"
                f"?sports={sport_id}&count=50&lng=en_GB&tf=3000000&tz=3"
                f"&mode=4&country=191&partner=151&getEmpty=true&gr=337"
            )
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            }
            response = requests.get(url, headers=headers)
            data = response.json()

            events = data.get("Value", [])
            
                        # Get additional matches by league
            leagues = get_22bet_leagues(sport_id)
            for league_id, league_name in leagues.items():
                try:
                    league_url = (
                        f"https://22bet.ug/service-api/LineFeed/GamesByGlobalChamp"
                        f"?id=144&champ={league_id}&partner=151&gr=337&country=191&lng=en"
                    )
                    r = requests.get(league_url, headers=headers)
                    league_data = r.json()
                    
                    league_value = league_data.get("Value", [])
                    if isinstance(league_value, list):
                        events.extend(league_value)
                except:
                    pass
            print(f"  Sport {sport_id}: {len(events)} events")

            for event in events:
                team1 = event.get("O1", "")
                team2 = event.get("O2", "")

                if not team1 or not team2:
                    continue
                if player_pattern.match(team1) or player_pattern.match(team2):
                    continue
                if "1st teams" in team1 or "1st teams" in team2:
                    continue

                match_name = f"{team1} vs {team2}"
                if match_name in seen:
                    continue
                seen.add(match_name)

                home = draw = away = None
                for odd in event.get("E", []):
                    t = odd.get("T")
                    c = odd.get("C")
                    if t == 1:
                        home = c
                    elif t == 2:
                        draw = c
                    elif t == 3:
                        away = c

                if home and draw and away:
                    key = normalize_name(match_name)
                    results[key] = {
                        "match": match_name,
                        "bookmaker": "22bet",
                        "home": float(home),
                        "draw": float(draw),
                        "away": float(away),
                        "league": event.get("L", "Unknown"),
                        "sport": event.get("SE", "Unknown")
                    }


        except Exception as e:
            print(f"  ❌ 22bet sport {sport_id} error: {e}")

    print(f"  ✅ 22bet: {len(results)} matches found")
    return results

# ─────────────────────────────────────────
#  SCRAPER: BETPAWA
#  → Add your betpawa scraping logic here
#    Must return same dict format as above
# ─────────────────────────────────────────
def scrape_betpawa(page):
    print("🔄 Scraping Betpawa...")
    results = {}

    import requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "Referer": "https://www.betpawa.ug/",
        "x-pawa-brand": "betpawa-uganda",
        "x-pawa-language": "en",
        "devicetype": "smart_phone",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }

    params = {
    "q": json.dumps({
        "queries": [
            {
                "query": {
                    "eventType": "UPCOMING",
                    "categories": ["2"]
                },
                "sort": {"popularity": "DESC"},
                "take": 100,
                "view": {
                    "marketTypes": ["3743"]
                }
            }
        ]
    })
}

    try:
        url = "https://www.betpawa.ug/api/sportsbook/v4/events/lists/by-queries"
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        print(json.dumps(data, indent=2)[:2000])

        events = data["responses"][0]["responses"]
        for event in events:
            match_name = event.get("name", "")
            if not match_name:
                continue

            markets = event.get("markets", [])
            home = draw = away = None

            for market in markets:
                market_id = market.get("marketType", {}).get("id", "")
                if market_id == "3743":
                    rows = market.get("row", [])
                    if rows:
                        for price in rows[0].get("prices", []):
                            label = price.get("name", "")
                            odds = price.get("odds")
                            if label == "1":
                                home = odds
                            elif label == "X":
                                draw = odds
                            elif label == "2":
                                away = odds

            if home and draw and away:
                key = normalize_name(match_name)
                results[key] = {
                    "match": match_name,
                    "bookmaker": "betpawa",
                    "home": float(home),
                    "draw": float(draw),
                    "away": float(away),
                    "league": event.get("competition", {}).get("name", "Unknown")
                }

    except Exception as e:
        print(f"  ❌ Betpawa error: {e}")

    print(f"  ✅ Betpawa: {len(results)} matches found")
    return results

# ─────────────────────────────────────────
#  ADD MORE BOOKMAKERS HERE
#  Copy the scrape_betpawa() pattern above
#  and add to SCRAPERS list below
# ─────────────────────────────────────────
SCRAPERS = [scrape_22bet, scrape_betpawa, scrape_fortebet, scrape_premierbet, scrape_betika]

# ─────────────────────────────────────────
#  ARBITRAGE FINDER
# ─────────────────────────────────────────
def find_arbitrage(all_books_data):
    """
    Compare the same match across all bookmakers.
    Picks the best home/draw/away odds from ANY bookmaker combination.
    """
    # Merge all matches by normalized key
    all_matches = {}
    for book_data in all_books_data:
        for key, data in book_data.items():
            if key not in all_matches:
                all_matches[key] = []
            all_matches[key].append(data)

  # DEBUG
    all_keys = [set(d.keys()) for d in all_books_data]
    common = set.intersection(*all_keys) if all_keys else set()
    print(f"\n✅ Matched across ALL bookmakers: {len(common)}")
    for k in common:
        print(f"  {k}")

    # Show pairwise overlaps too
    for i in range(len(all_books_data)):
        for j in range(i+1, len(all_books_data)):
            pair_common = all_keys[i] & all_keys[j]
            print(f"\n  Bookmaker {i} & {j} overlap: {len(pair_common)}")
    

    opportunities = []

    for key, entries in all_matches.items():
        if len(entries) < 2:
            continue  # Need at least 2 bookmakers for arbitrage

        # Find best odds for each outcome across all bookmakers
        best_home = max(entries, key=lambda x: x["home"])
        best_draw = max(entries, key=lambda x: x["draw"])
        best_away = max(entries, key=lambda x: x["away"])

        home_odd = best_home["home"]
        draw_odd = best_draw["draw"]
        away_odd = best_away["away"]

        margin = calc_arb(home_odd, draw_odd, away_odd)
        profit_pct = (1 - margin) * 100

        if profit_pct >= MIN_PROFIT_PCT:
            s_home, s_draw, s_away, profit, pct = calc_stakes(
                home_odd, draw_odd, away_odd, BANKROLL
            )
            opportunities.append({
                "match": entries[0]["match"],
                "league": entries[0]["league"],
                "home_odd": home_odd,
                "home_book": best_home["bookmaker"],
                "draw_odd": draw_odd,
                "draw_book": best_draw["bookmaker"],
                "away_odd": away_odd,
                "away_book": best_away["bookmaker"],
                "stake_home": s_home,
                "stake_draw": s_draw,
                "stake_away": s_away,
                "guaranteed_profit": profit,
                "profit_pct": pct,
            })

    # Sort by best profit first
    opportunities.sort(key=lambda x: x["profit_pct"], reverse=True)
    return opportunities

# ─────────────────────────────────────────
#  OUTPUT
# ─────────────────────────────────────────
def print_results(opportunities):
    if not opportunities:
        print("\n❌ No arbitrage opportunities found.")
        return

        # Play sound alert
    import winsound
    import ctypes
    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        # Windows popup notification
    ctypes.windll.user32.MessageBoxW(
    0,
    f"🎯 {len(opportunities)} arbitrage opportunity found!\nCheck the terminal for details.",
    "Arby - Arbitrage Alert!",
    0x40  # Info icon
    )

    print(f"\n{'='*90}")
    print(f"  🎯 ARBITRAGE OPPORTUNITIES  |  Bankroll: {BANKROLL}  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*90}")

    for o in opportunities:
        print(f"\n📌 {o['match']}  ({o['league']})")
        print(f"   Profit: {o['profit_pct']}%  →  Guaranteed: +{o['guaranteed_profit']}")
        print(f"   HOME  {o['home_odd']}  @ {o['home_book']:10s}  → Stake: {o['stake_home']}")
        print(f"   DRAW  {o['draw_odd']}  @ {o['draw_book']:10s}  → Stake: {o['stake_draw']}")
        print(f"   AWAY  {o['away_odd']}  @ {o['away_book']:10s}  → Stake: {o['stake_away']}")

    print(f"\n{'='*90}")
    print(f"  Total opportunities: {len(opportunities)}")
    print(f"{'='*90}\n")

def save_csv(opportunities):
    if not opportunities:
        return
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=opportunities[0].keys())
        writer.writeheader()
        writer.writerows(opportunities)
    print(f"💾 Saved to {OUTPUT_CSV}")

# ─────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────
def main():
    print(f"\n🚀 Arbitrage Detector Starting | Bankroll: {BANKROLL} | Min profit: {MIN_PROFIT_PCT}%\n")

    all_books_data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )

        for scraper in SCRAPERS:
            page = context.new_page()
            try:
                data = scraper(page)
                if data:
                    all_books_data.append(data)
            except Exception as e:
                print(f"  ❌ Error in {scraper.__name__}: {e}")
            finally:
                page.close()

        browser.close()

    opportunities = find_arbitrage(all_books_data)
    print_results(opportunities)
    save_csv(opportunities)

if __name__ == "__main__":
    import time

    RUN_INTERVAL_SECONDS = 300  # 5 minutes

    print(f"⏰ Auto-scheduler started — running every {RUN_INTERVAL_SECONDS // 60} minutes. Press Ctrl+C to stop.\n")
    while True:
        try:
            main()
            print(f"\n⏳ Next scan in {RUN_INTERVAL_SECONDS // 60} minutes...\n")
            time.sleep(RUN_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\n🛑 Scheduler stopped.")
            break