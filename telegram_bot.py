import re
import json
import requests
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ─────────────────────────────────────────
#  SETTINGS — paste your token here
# ─────────────────────────────────────────
BOT_TOKEN = "8574503831:AAH7OFxMcNWzAoKA9iDztROHIykAUvjjN1w"

logging.basicConfig(level=logging.INFO)

# ─────────────────────────────────────────
#  HEADERS
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
    name = name.strip().upper()
    if name == "1": return "1"
    elif name in ("X", "DRAW"): return "X"
    elif name == "2": return "2"
    return name

# ─────────────────────────────────────────
#  SCRAPERS
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

            if "1X2" not in market_name.upper() or "2UP" in market_name.upper():
                continue

            selections.append({
                "match": match_name,
                "outcome": outcome_label(outcome),
                "betpawa_odds": odds,
                "key": normalize(match_name)
            })
    return selections

def fetch_fortebet():
    url = "https://mobile.fortebet.ug/api/web/v1/offer/full-prematch-en"
    response = requests.get(url, headers=GENERIC_HEADERS)
    data = response.json()

    events = data.get("data", {}).get("event", {})
    markets = data.get("data", {}).get("markets", {})
    competitors = data.get("data", {}).get("competitors", {})

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
            results[key] = {"home": home, "draw": draw, "away": away}
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
            results[key] = {"home": float(home), "draw": float(draw), "away": float(away)}
    return results

def fetch_betika():
    results = {}
    page_num = 1
    headers = {**GENERIC_HEADERS, "Referer": "https://www.betika.com/"}
    while True:
        url = f"https://api-ug.betika.com/v1/uo/matches?sport_id=3&limit=100&page={page_num}"
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
                results[key] = {"home": float(home), "draw": float(draw), "away": float(away)}
        page_num += 1
    return results

# ─────────────────────────────────────────
#  TRANSLATE LOGIC
# ─────────────────────────────────────────
def translate_code(code):
    selections = fetch_betpawa_code(code)
    if not selections:
        return "❌ No valid 1X2 selections found in this code."

    fortebet = fetch_fortebet()
    premierbet = fetch_premierbet()
    betika = fetch_betika()

    all_books = {
        "Fortebet": fortebet,
        "Premierbet": premierbet,
        "Betika": betika
    }

    lines = [f"🎯 *Betpawa Code: {code}*\n"]

    for sel in selections:
        key = sel["key"]
        outcome = sel["outcome"]
        lines.append(f"📌 *{sel['match']}* → Pick: `{outcome}` (Betpawa: `{sel['betpawa_odds']}`)")

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

                diff = round(odds - sel["betpawa_odds"], 2)
                diff_str = f"+{diff}" if diff >= 0 else str(diff)
                better = " ✅ BETTER" if odds > sel["betpawa_odds"] else ""
                lines.append(f"   {book_name}: `{odds}` ({diff_str}){better}")
                found_any = True

        if not found_any:
            lines.append("   ❌ Not found on other bookmakers")
        lines.append("")

    return "\n".join(lines)

# ─────────────────────────────────────────
#  BOT HANDLERS
# ─────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to *Arby Bot*!\n\n"
        "Send me a *Betpawa booking code* and I'll find the same matches on other bookmakers and compare odds.\n\n"
        "Example: `HWGLLJY`\n\n"
        "Commands:\n"
        "/start - Show this message\n"
        "/help - How to use",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *How to use Arby Bot:*\n\n"
        "1. Go to Betpawa and build a betslip\n"
        "2. Click *Book Bet* to get a booking code\n"
        "3. Send the code to me (e.g. `HWGLLJY`)\n"
        "4. I'll show you the same odds on Fortebet, Premierbet and Betika\n\n"
        "✅ Odds marked BETTER are higher than Betpawa's",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()

    # Check if it looks like a booking code (letters/numbers, 5-10 chars)
    if not re.match(r'^[A-Z0-9]{4,12}$', text):
        await update.message.reply_text(
            "❓ That doesn't look like a booking code. Send a Betpawa booking code like `HWGLLJY`",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(f"🔍 Looking up code `{text}`...", parse_mode="Markdown")

    try:
        result = translate_code(text)
        await update.message.reply_text(result, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

# ─────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot is running... Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()