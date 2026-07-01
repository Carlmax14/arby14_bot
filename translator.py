import requests
import json
import re

# ─────────────────────────────────────────
#  SETTINGS
# ─────────────────────────────────────────
BETPAWA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://www.betpawa.ug/",
    "x-pawa-brand": "betpawa-uganda",
    "x-pawa-language": "en"
}

GENERIC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}

# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────
def normalize(name):
    name = name.lower()
    name = re.sub(r'\s+(vs\.?|-)\s+', ' v ', name)
    name = re.sub(r'\(n\)', '', name)
    name = name.replace('/', ' ')
    name = re.sub(r'[^a-z0-9 ]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def outcome_label(name):
    """Convert outcome name to 1/X/2."""
    name = name.strip().upper()
    if name == "1":
        return "1"
    elif name in ("X", "DRAW"):
        return "X"
    elif name == "2":
        return "2"
    return name

# ─────────────────────────────────────────
#  STEP 1: FETCH BETPAWA BOOKING CODE
# ─────────────────────────────────────────
def fetch_betpawa_code(code):
    url = f"https://www.betpawa.ug/api/sportsbook/v3/booking-number/{code}"
    response = requests.get(url, headers=BETPAWA_HEADERS)
    data = response.json()

    selections = []
    for item in data.get("items", []):
        event = item.get("eventInfo", {})
        participants = event.get("participants", [])
        if len(participants) < 2:
            continue

        home = participants[0].get("name", "")
        away = participants[1].get("name", "")
        match_name = f"{home} vs {away}"

        for sel in item.get("selections", []):
            market_name = sel.get("market", {}).get("name", "")
            outcome = sel.get("selectionInfo", {}).get("name", "")
            odds = item.get("odds", {}).get("price")

            # Only handle standard 1X2 markets
            if "1X2" not in market_name.upper() or "2UP" in market_name.upper():
                print(f"  ⚠️  Skipping non-standard market: {market_name} for {match_name}")
                continue

            selections.append({
                "match": match_name,
                "home": home,
                "away": away,
                "outcome": outcome_label(outcome),
                "betpawa_odds": odds,
                "key": normalize(match_name)
            })

    return selections

# ─────────────────────────────────────────
#  STEP 2: FETCH ODDS FROM OTHER BOOKMAKERS
# ─────────────────────────────────────────
def fetch_fortebet():
    url = "https://mobile.fortebet.ug/api/web/v1/offer/full-prematch-en"
    response = requests.get(url, headers=GENERIC_HEADERS)
    data = response.json()

    events = data.get("data", {}).get("event", {})
    markets = data.get("data", {}).get("markets", {})
    competitors = data.get("data", {}).get("competitors", {})

    # Build event_id -> market_1 lookup
    event_main_market = {}
    for _, market_data in markets.items():
        if market_data.get("marketId") == 1:
            eid = market_data.get("eventId")
            event_main_market[eid] = market_data

    results = {}
    for event_id, event in events.items():
        comp_ids = event.get("competitors", [])
        if len(comp_ids) != 2:
            continue
        team1 = competitors.get(str(comp_ids[0]), {}).get("name", "")
        team2 = competitors.get(str(comp_ids[1]), {}).get("name", "")
        if not team1 or not team2:
            continue

        market_data = event_main_market.get(event_id)
        if not market_data:
            continue

        home = draw = away = None
        for _, odd_data in market_data.get("odds", {}).items():
            oid = odd_data.get("outcomeId")
            price = odd_data.get("odds")
            if oid == 1: home = price
            elif oid == 2: draw = price
            elif oid == 3: away = price

        if home and draw and away:
            key = normalize(f"{team1} vs {team2}")
            results[key] = {"home": home, "draw": draw, "away": away,
                           "match": f"{team1} vs {team2}", "bookmaker": "Fortebet"}
    return results

def fetch_premierbet():
    url = "https://pmbet.dualsoft.bet/restapi/offer/en/sport/S/mob?locale=en"
    response = requests.get(url, headers=GENERIC_HEADERS)
    data = response.json()

    results = {}
    for match in data.get("esMatches", []):
        team1 = match.get("home", "")
        team2 = match.get("away", "")
        odds = match.get("odds", {})
        home = odds.get("1")
        draw = odds.get("2")
        away = odds.get("3")
        if home and draw and away and team1 and team2:
            key = normalize(f"{team1} vs {team2}")
            results[key] = {"home": float(home), "draw": float(draw), "away": float(away),
                           "match": f"{team1} vs {team2}", "bookmaker": "Premierbet"}
    return results

def fetch_betika():
    results = {}
    page_num = 1
    while True:
        url = f"https://api-ug.betika.com/v1/uo/matches?sport_id=3&limit=100&page={page_num}"
        headers = {**GENERIC_HEADERS, "Referer": "https://www.betika.com/"}
        response = requests.get(url, headers=headers)
        data = response.json()
        matches = data.get("data", [])
        if not matches:
            break
        for match in matches:
            team1 = match.get("home_team", "")
            team2 = match.get("away_team", "")
            home = match.get("home_odd")
            draw = match.get("neutral_odd")
            away = match.get("away_odd")
            if home and draw and away and team1 and team2:
                key = normalize(f"{team1} vs {team2}")
                results[key] = {"home": float(home), "draw": float(draw), "away": float(away),
                               "match": f"{team1} vs {team2}", "bookmaker": "Betika"}
        page_num += 1
    return results

# ─────────────────────────────────────────
#  STEP 3: TRANSLATE
# ─────────────────────────────────────────
def translate(code):
    print(f"\n🔍 Fetching Betpawa code: {code}")
    selections = fetch_betpawa_code(code)

    if not selections:
        print("❌ No valid 1X2 selections found in this code.")
        return

    print(f"✅ Found {len(selections)} selection(s)\n")

    print("📡 Fetching odds from other bookmakers...")
    fortebet = fetch_fortebet()
    premierbet = fetch_premierbet()
    betika = fetch_betika()

    all_books = {
        "Fortebet": fortebet,
        "Premierbet": premierbet,
        "Betika": betika
    }

    print(f"\n{'='*70}")
    print(f"  BOOKING CODE TRANSLATOR  |  Betpawa code: {code}")
    print(f"{'='*70}")

    for sel in selections:
        key = sel["key"]
        outcome = sel["outcome"]
        print(f"\n📌 {sel['match']}  →  Pick: {outcome}  (Betpawa odds: {sel['betpawa_odds']})")

        found_any = False
        for book_name, book_data in all_books.items():
            match_data = book_data.get(key)
            if match_data:
                if outcome == "1":
                    odds = match_data["home"]
                elif outcome == "X":
                    odds = match_data["draw"]
                else:
                    odds = match_data["away"]

                diff = odds - sel["betpawa_odds"]
                diff_str = f"+{diff:.2f}" if diff >= 0 else f"{diff:.2f}"
                better = "✅ BETTER" if odds > sel["betpawa_odds"] else ""
                print(f"   {book_name:<12} odds: {odds:<6} ({diff_str})  {better}")
                found_any = True

        if not found_any:
            print("   ❌ Match not found on any other bookmaker")

    print(f"\n{'='*70}\n")

# ─────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────
if __name__ == "__main__":
    code = input("Enter Betpawa booking code: ").strip().upper()
    translate(code)