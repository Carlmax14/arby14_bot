import requests
import json

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
                    "categories": ["2"]  # 2=football, add more below
                },
                "sort": {"popularity": "DESC"},
                "take": 200,  # change 50 to 200
                "view": {
                    "marketTypes": ["3743"]
                }
            },
            {
                "query": {
                    "eventType": "UPCOMING",
                    "categories": ["3"]  # basketball
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

url = "https://www.betpawa.ug/api/sportsbook/v4/events/lists/by-queries"
response = requests.get(url, headers=headers, params=params)
data = response.json()

print("=" * 65)
print(f"{'MATCH':<35} {'HOME':>7} {'DRAW':>7} {'AWAY':>7}")
print("=" * 65)

try:
    events = data["responses"][0]["responses"]
    for event in events:
        name = event.get("name", "Unknown")
        markets = event.get("markets", [])

        home = draw = away = "-"
        for market in markets:
            market_id = market.get("marketType", {}).get("id", "")
            if market_id == "3743":
                rows = market.get("row", [])
                if rows:
                    prices = rows[0].get("prices", [])
                    for price in prices:
                        label = price.get("name", "")
                        odds = price.get("odds", "-")
                        if label == "1":
                            home = odds
                        elif label == "X":
                            draw = odds
                        elif label == "2":
                            away = odds

        print(f"{name:<35} {str(home):>7} {str(draw):>7} {str(away):>7}")

except Exception as e:
    print("Error:", e)
    print(json.dumps(data, indent=2)[:2000])