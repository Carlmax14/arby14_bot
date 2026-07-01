"""
Telegram Arbitrage Bot
=======================
Wraps your existing arbitrage-finder logic in a Telegram bot.

Setup:
1. Message @BotFather on Telegram, create a bot, copy the token.
2. Put the token in the TELEGRAM_BOT_TOKEN environment variable, or paste it
   into BOT_TOKEN below.
3. pip install -r requirements.txt
4. python telegram_arb_bot.py
5. On Telegram, find your bot and send /start to subscribe to alerts.

Commands:
  /start          - subscribe this chat to arbitrage alerts
  /stop           - unsubscribe
  /scan           - run a scan immediately and reply with results
  /status         - show current bankroll / min profit / interval
  /setbankroll N  - change bankroll used for stake sizing
  /setminprofit P - change minimum profit % to flag (e.g. 0.5)
  /setinterval M  - change auto-scan interval in minutes
"""

import os
import re
import csv
import json
import time
import threading
from datetime import datetime

import requests
import telebot

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8694626121:AAHVBHLGuYa5Sl_vg4GfWlskuy-LeN2mJn4")

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
SUBSCRIBERS_FILE = os.path.join(DATA_DIR, "subscribers.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
OUTPUT_CSV = os.path.join(DATA_DIR, "arb_opportunities.csv")

DEFAULT_CONFIG = {
    "bankroll": 100000,
    "min_profit_pct": 0.5,
    "interval_minutes": 5,
}

bot = telebot.TeleBot(BOT_TOKEN)  # plain text — team/league names can contain
# characters (*, _, [, ]) that break Telegram's Markdown parser and crash sends

_lock = threading.Lock()


# ─────────────────────────────────────────
#  PERSISTENCE (subscribers + settings survive restarts)
# ─────────────────────────────────────────
def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_subscribers():
    return set(load_json(SUBSCRIBERS_FILE, []))


def add_subscriber(chat_id):
    subs = load_subscribers()
    subs.add(chat_id)
    save_json(SUBSCRIBERS_FILE, list(subs))


def remove_subscriber(chat_id):
    subs = load_subscribers()
    subs.discard(chat_id)
    save_json(SUBSCRIBERS_FILE, list(subs))


def load_config():
    cfg = DEFAULT_CONFIG.copy()
    cfg.update(load_json(CONFIG_FILE, {}))
    return cfg


def save_config(cfg):
    save_json(CONFIG_FILE, cfg)


config = load_config()


# ─────────────────────────────────────────
#  HELPERS (from your original script, unchanged)
# ─────────────────────────────────────────
def normalize_name(name):
    """Lowercase and strip punctuation for fuzzy matching across bookmakers."""
    name = name.lower()
    name = re.sub(r'\s+(vs\.?|-)\s+', ' v ', name)
    name = re.sub(r'\(n\)', '', name)
    name = name.replace('/', ' ')
    name = re.sub(r'[^a-z0-9 ]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def calc_arb(home, draw, away):
    """Return implied margin. Below 1.0 = arbitrage opportunity."""
    try:
        return (1 / home) + (1 / draw) + (1 / away)
    except ZeroDivisionError:
        return 99


def calc_stakes(home, draw, away, bankroll):
    """Calculate how much to bet on each outcome for guaranteed profit."""
    margin = calc_arb(home, draw, away)
    stake_home = bankroll * (1 / home) / margin
    stake_draw = bankroll * (1 / draw) / margin
    stake_away = bankroll * (1 / away) / margin
    guaranteed_profit = bankroll / margin - bankroll
    profit_pct = (1 - margin) * 100
    return (
        round(stake_home, 2),
        round(stake_draw, 2),
        round(stake_away, 2),
        round(guaranteed_profit, 2),
        round(profit_pct, 2),
    )


# ─────────────────────────────────────────
#  SCRAPERS (unchanged from your original — all use `requests`,
#  none actually need a Playwright page, so that dependency is dropped)
# ─────────────────────────────────────────
def scrape_fortebet():
    print("Scraping Fortebet...")
    results = {}
    try:
        url = "https://mobile.fortebet.ug/api/web/v1/offer/full-prematch-en"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://mobile.fortebet.ug/",
        }
        response = requests.get(url, headers=headers, timeout=15)
        data = response.json()

        events = data.get("data", {}).get("event", {})
        markets = data.get("data", {}).get("markets", {})
        competitors = data.get("data", {}).get("competitors", {})

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
                    "league": "Unknown",
                }
    except Exception as e:
        print(f"  Fortebet error: {e}")

    print(f"  Fortebet: {len(results)} matches found")
    return results


def scrape_premierbet():
    print("Scraping Premierbet...")
    results = {}
    try:
        url = "https://pmbet.dualsoft.bet/restapi/offer/en/sport/S/mob?locale=en"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
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
                    "league": "Unknown",
                }
    except Exception as e:
        print(f"  Premierbet error: {e}")

    print(f"  Premierbet: {len(results)} matches found")
    return results


def scrape_betika():
    print("Scraping Betika...")
    results = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Referer": "https://www.betika.com/",
    }
    sports = [3, 6]  # 3=Soccer, 6=Basketball
    try:
        for sport_id in sports:
            page_num = 1
            while True:
                url = f"https://api-ug.betika.com/v1/uo/matches?sport_id={sport_id}&limit=100&page={page_num}"
                response = requests.get(url, headers=headers, timeout=15)
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
                            "league": match.get("competition_name", "Unknown"),
                        }
                page_num += 1
    except Exception as e:
        print(f"  Betika error: {e}")

    print(f"  Betika: {len(results)} matches found")
    return results


def get_22bet_leagues(sport_id):
    """Fetch all league IDs for a given sport."""
    url = (
        f"https://22bet.ug/service-api/LineFeed/Get1x2_VZip"
        f"?sports={sport_id}&count=50&lng=en_GB&tf=3000000&tz=3"
        f"&mode=4&country=191&partner=151&getEmpty=true&gr=337"
    )
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    response = requests.get(url, headers=headers, timeout=15)
    data = response.json()

    leagues = {}
    for event in data.get("Value", []):
        li = event.get("LI")
        ln = event.get("L", "Unknown")
        if li:
            leagues[li] = ln
    return leagues


def scrape_22bet():
    print("Scraping 22bet...")
    results = {}
    seen = set()
    player_pattern = re.compile(r'^[A-Z][a-z]+ [A-Z][a-z]+$')

    sports = [1, 2, 3, 4, 5]  # football, hockey, basketball, tennis, baseball
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    }

    for sport_id in sports:
        try:
            url = (
                f"https://22bet.ug/service-api/LineFeed/Get1x2_VZip"
                f"?sports={sport_id}&count=50&lng=en_GB&tf=3000000&tz=3"
                f"&mode=4&country=191&partner=151&getEmpty=true&gr=337"
            )
            response = requests.get(url, headers=headers, timeout=15)
            data = response.json()
            events = data.get("Value", [])

            leagues = get_22bet_leagues(sport_id)
            for league_id, league_name in leagues.items():
                try:
                    league_url = (
                        f"https://22bet.ug/service-api/LineFeed/GamesByGlobalChamp"
                        f"?id=144&champ={league_id}&partner=151&gr=337&country=191&lng=en"
                    )
                    r = requests.get(league_url, headers=headers, timeout=15)
                    league_data = r.json()
                    league_value = league_data.get("Value", [])
                    if isinstance(league_value, list):
                        events.extend(league_value)
                except Exception:
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
                        "sport": event.get("SE", "Unknown"),
                    }
        except Exception as e:
            print(f"  22bet sport {sport_id} error: {e}")

    print(f"  22bet: {len(results)} matches found")
    return results


def scrape_betpawa():
    print("Scraping Betpawa...")
    results = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36",
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
                    "query": {"eventType": "UPCOMING", "categories": ["2"]},
                    "sort": {"popularity": "DESC"},
                    "take": 100,
                    "view": {"marketTypes": ["3743"]},
                }
            ]
        })
    }

    try:
        url = "https://www.betpawa.ug/api/sportsbook/v4/events/lists/by-queries"
        response = requests.get(url, headers=headers, params=params, timeout=15)
        data = response.json()

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
                    "league": event.get("competition", {}).get("name", "Unknown"),
                }
    except Exception as e:
        print(f"  Betpawa error: {e}")

    print(f"  Betpawa: {len(results)} matches found")
    return results


SCRAPERS = [scrape_22bet, scrape_betpawa, scrape_fortebet, scrape_premierbet, scrape_betika]


# ─────────────────────────────────────────
#  ARBITRAGE FINDER
# ─────────────────────────────────────────
def find_arbitrage(all_books_data, bankroll, min_profit_pct):
    all_matches = {}
    for book_data in all_books_data:
        for key, data in book_data.items():
            all_matches.setdefault(key, []).append(data)

    opportunities = []
    for key, entries in all_matches.items():
        if len(entries) < 2:
            continue

        best_home = max(entries, key=lambda x: x["home"])
        best_draw = max(entries, key=lambda x: x["draw"])
        best_away = max(entries, key=lambda x: x["away"])

        home_odd = best_home["home"]
        draw_odd = best_draw["draw"]
        away_odd = best_away["away"]

        margin = calc_arb(home_odd, draw_odd, away_odd)
        profit_pct = (1 - margin) * 100

        if profit_pct >= min_profit_pct:
            s_home, s_draw, s_away, profit, pct = calc_stakes(home_odd, draw_odd, away_odd, bankroll)
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

    opportunities.sort(key=lambda x: x["profit_pct"], reverse=True)
    return opportunities


def save_csv(opportunities):
    if not opportunities:
        return
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=opportunities[0].keys())
        writer.writeheader()
        writer.writerows(opportunities)


def run_full_scan():
    """Run every scraper and return the list of arbitrage opportunities."""
    cfg = load_config()
    all_books_data = []
    for scraper in SCRAPERS:
        try:
            data = scraper()
            if data:
                all_books_data.append(data)
        except Exception as e:
            print(f"Error in {scraper.__name__}: {e}")

    opportunities = find_arbitrage(all_books_data, cfg["bankroll"], cfg["min_profit_pct"])
    save_csv(opportunities)
    return opportunities


# ─────────────────────────────────────────
#  TELEGRAM MESSAGE FORMATTING
# ─────────────────────────────────────────
def format_message(opportunities, cfg):
    lines = [
        f"🎯 {len(opportunities)} arbitrage opportunity(ies) found",
        f"Bankroll: {cfg['bankroll']} | {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]
    for o in opportunities[:15]:  # cap message length
        lines.append(f"📌 {o['match']} ({o['league']})")
        lines.append(f"Profit: {o['profit_pct']}% → guaranteed +{o['guaranteed_profit']}")
        lines.append(f"HOME {o['home_odd']} @ {o['home_book']} → stake {o['stake_home']}")
        lines.append(f"DRAW {o['draw_odd']} @ {o['draw_book']} → stake {o['stake_draw']}")
        lines.append(f"AWAY {o['away_odd']} @ {o['away_book']} → stake {o['stake_away']}")
        lines.append("")
    if len(opportunities) > 15:
        lines.append(f"...and {len(opportunities) - 15} more. Full list in {OUTPUT_CSV}")
    return "\n".join(lines)


def broadcast(opportunities):
    if not opportunities:
        return
    cfg = load_config()
    text = format_message(opportunities, cfg)
    for chat_id in load_subscribers():
        try:
            bot.send_message(chat_id, text)
        except Exception as e:
            print(f"Failed to send to {chat_id}: {e}")


# ─────────────────────────────────────────
#  BOT COMMANDS
# ─────────────────────────────────────────
@bot.message_handler(commands=["start"])
def cmd_start(message):
    add_subscriber(message.chat.id)
    bot.reply_to(
        message,
        "✅ Subscribed! You'll get arbitrage alerts here automatically.\n\n"
        "Commands\n"
        "/scan - run a scan right now\n"
        "/status - show current settings\n"
        "/setbankroll <amount> - e.g. /setbankroll 200000\n"
        "/setminprofit <pct> - e.g. /setminprofit 1.0\n"
        "/setinterval <minutes> - e.g. /setinterval 10\n"
        "/stop - unsubscribe",
    )


@bot.message_handler(commands=["stop"])
def cmd_stop(message):
    remove_subscriber(message.chat.id)
    bot.reply_to(message, "🛑 Unsubscribed. Send /start anytime to resume alerts.")


@bot.message_handler(commands=["status"])
def cmd_status(message):
    cfg = load_config()
    n_subs = len(load_subscribers())
    bot.reply_to(
        message,
        f"Current settings\n"
        f"Bankroll: {cfg['bankroll']}\n"
        f"Min profit: {cfg['min_profit_pct']}%\n"
        f"Scan interval: {cfg['interval_minutes']} min\n"
        f"Subscribers: {n_subs}",
    )


@bot.message_handler(commands=["scan"])
def cmd_scan(message):
    bot.reply_to(message, "🔄 Scanning all bookmakers, this can take 30-60s...")
    threading.Thread(target=_manual_scan, args=(message.chat.id,), daemon=True).start()


def _manual_scan(chat_id):
    try:
        opportunities = run_full_scan()
        cfg = load_config()
        if opportunities:
            bot.send_message(chat_id, format_message(opportunities, cfg))
        else:
            bot.send_message(chat_id, "❌ No arbitrage opportunities found right now.")
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Scan failed: {e}")


@bot.message_handler(commands=["setbankroll"])
def cmd_setbankroll(message):
    try:
        amount = float(message.text.split(maxsplit=1)[1])
        cfg = load_config()
        cfg["bankroll"] = amount
        save_config(cfg)
        bot.reply_to(message, f"✅ Bankroll set to {amount}")
    except (IndexError, ValueError):
        bot.reply_to(message, "Usage: /setbankroll 100000")


@bot.message_handler(commands=["setminprofit"])
def cmd_setminprofit(message):
    try:
        pct = float(message.text.split(maxsplit=1)[1])
        cfg = load_config()
        cfg["min_profit_pct"] = pct
        save_config(cfg)
        bot.reply_to(message, f"✅ Minimum profit threshold set to {pct}%")
    except (IndexError, ValueError):
        bot.reply_to(message, "Usage: /setminprofit 0.5")


@bot.message_handler(commands=["setinterval"])
def cmd_setinterval(message):
    try:
        minutes = int(message.text.split(maxsplit=1)[1])
        cfg = load_config()
        cfg["interval_minutes"] = minutes
        save_config(cfg)
        bot.reply_to(message, f"✅ Auto-scan interval set to {minutes} minutes")
    except (IndexError, ValueError):
        bot.reply_to(message, "Usage: /setinterval 5")


# ─────────────────────────────────────────
#  BACKGROUND AUTO-SCAN LOOP
# ─────────────────────────────────────────
def background_loop():
    while True:
        try:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running scheduled scan...")
            opportunities = run_full_scan()
            print(f"  Found {len(opportunities)} opportunities.")
            broadcast(opportunities)
        except Exception as e:
            print(f"Background scan error: {e}")

        cfg = load_config()
        time.sleep(cfg["interval_minutes"] * 60)


# ─────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────
if __name__ == "__main__":
    if BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        raise SystemExit(
            "Set your bot token first: either export TELEGRAM_BOT_TOKEN=xxx, "
            "or edit BOT_TOKEN in this file."
        )

    print("Starting background auto-scan thread...")
    t = threading.Thread(target=background_loop, daemon=True)
    t.start()

    print("Bot is polling for commands. Press Ctrl+C to stop.")
    bot.infinity_polling()