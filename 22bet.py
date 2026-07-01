from playwright.sync_api import sync_playwright
import json

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
    page = context.new_page()

    captured = []

    def handle_response(response):
        if "LineFeed/Get1x2_VZip" in response.url:
            try:
                captured.append(response.json())
            except:
                pass

    page.on("response", handle_response)
    page.goto("https://22bet.ug/line/football", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)

    if not captured:
        print("No data captured - try increasing timeout")
    else:
        data = captured[0]
        print("=" * 65)
        print(f"{'MATCH':<35} {'HOME':>7} {'DRAW':>7} {'AWAY':>7}")
        print("=" * 65)

        import re

        seen = set()  # ← add this BEFORE the loop

        for event in data.get("Value", []):
            team1 = event.get("O1", "?")
            team2 = event.get("O2", "?")

            player_pattern = re.compile(r'^[A-Z][a-z]+ [A-Z][a-z]+$')
            if player_pattern.match(team1) or player_pattern.match(team2):
                continue

            if "1st teams" in team1 or "2nd teams" in team2:
                continue

            name = f"{team1} vs {team2}"

            if name in seen:
                continue
            seen.add(name)

            home = draw = away = "-"
            for odd in event.get("E", []):
                t = odd.get("T")
                c = odd.get("C", "-")
                if t == 1:
                    home = c
                elif t == 2:
                    draw = c
                elif t == 3:
                    away = c

            if home != "-" and draw != "-" and away != "-":
                print(f"{name:<35} {str(home):>7} {str(draw):>7} {str(away):>7}")

    browser.close()