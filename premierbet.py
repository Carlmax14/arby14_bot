import json
import re
import requests

def normalize_name(name):
    name = name.lower()
    name = re.sub(r'\s+(vs\.?|-)\s+', ' v ', name)
    name = re.sub(r'\(n\)', '', name)
    name = name.replace('/', ' ')
    name = re.sub(r'[^a-z0-9 ]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def test_betpawa():
    print("\n--- Testing BetPawa ---")
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36",
        "x-pawa-brand": "betpawa-uganda",
        "x-pawa-language": "en",
        "devicetype": "smart_phone",
    }
    params = {
        "q": json.dumps({
            "queries": [{"query": {"eventType": "UPCOMING", "categories": ["2"]},
                "sort": {"popularity": "DESC"}, "take": 10,
                "view": {"marketTypes": ["3743"]}}]
        })
    }
    r = requests.get("https://www.betpawa.ug/api/sportsbook/v4/events/lists/by-queries",
                     headers=headers, params=params, timeout=15)
    print(f"Status: {r.status_code}")
    events = r.json()["responses"][0]["responses"]
    print(f"Matches: {len(events)}")
    if events:
        e = events[0]
        print(f"Sample: {e['name']}")

def test_22bet():
    print("\n--- Testing 22bet ---")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    url = "https://22bet.ug/service-api/LineFeed/Get1x2_VZip?sports=1&count=50&lng=en_GB&tf=3000000&tz=3&mode=4&country=191&partner=151&getEmpty=true&gr=337"
    r = requests.get(url, headers=headers, timeout=15)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        events = data.get("Value", [])
        print(f"Matches: {len(events)}")
        if events:
            print(f"Sample: {events[0].get('O1')} vs {events[0].get('O2')}")

def test_fortebet():
    print("\n--- Testing Fortebet ---")
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    r = requests.get("https://mobile.fortebet.ug/api/web/v1/offer/full-prematch-en",
                     headers=headers, timeout=15)
    print(f"Status: {r.status_code}")

def test_betika():
    print("\n--- Testing Betika ---")
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.betika.com/"}
    r = requests.get("https://api-ug.betika.com/v1/uo/matches?sport_id=3&limit=10&page=1",
                     headers=headers, timeout=15)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        matches = r.json().get("data", [])
        print(f"Matches: {len(matches)}")
        if matches:
            print(f"Sample: {matches[0].get('home_team')} vs {matches[0].get('away_team')}")

def test_bet9ja():
    print("\n--- Testing Bet9ja ---")
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36",
        "Referer": "https://sports.bet9ja.com/mobile/events/soccer/fifaworldcup2026/1-2252278/S_1X2",
    }
    r = requests.get("https://sports.bet9ja.com/mobile/feapi/PalimpsestAjax/GetEventsInGroupV2",
                     headers=headers,
                     params={"GROUPID": 2252278, "DISP": 0, "GROUPMARKETID": 1,
                             "v_cache_version": "1.318.2.243"}, timeout=15)
    print(f"Status: {r.status_code}")
    events = r.json()["D"].get("E", [])
    print(f"Matches: {len(events)}")
    if events:
        print(f"Sample: {events[0].get('DS')} → {events[0].get('O', {}).get('S_1X2_1')}/{events[0].get('O', {}).get('S_1X2_X')}/{events[0].get('O', {}).get('S_1X2_2')}")

test_betpawa()
test_22bet()
test_fortebet()
test_betika()
test_bet9ja()