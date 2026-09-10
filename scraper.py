import os
import json
import base64
import requests
from playwright.sync_api import sync_playwright

# --- CONFIGURATION (Handled safely via GitHub Cloud settings) ---
ODDS_API_KEY = os.environ.get("ODDS_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = "YOUR_GITHUB_USERNAME/sportsbet-mt-ev"  # <-- Change this to your exact profile name
# ------------------------------------------------------------------

def get_sharp_odds():
    url = f"https://the-odds-api.com{ODDS_API_KEY}"
    response = requests.get(url)
    return response.json() if response.status_code == 200 else []

def scrape_sportsbet_mt():
    scraped_games = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://sportsbetmontana.com", wait_until="networkidle")
        
        try:
            page.wait_for_selector(".sport-event-row, .event-card, .odds-button", timeout=15000)
            cards = page.query_selector_all(".sport-event-row, .event-card")
            
            for card in cards:
                teams = card.query_selector_all(".team-name, .participant-name")
                odds_buttons = card.query_selector_all(".odds-button, .price-value")
                
                if len(teams) >= 2 and len(odds_buttons) >= 2:
                    away_team = teams.inner_text().strip()
                    home_team = teams.inner_text().strip()
                    away_odds = int(odds_buttons[0].inner_text().replace("+", "").strip())
                    home_odds = int(odds_buttons[1].inner_text().replace("+", "").strip())
                    
                    scraped_games.append({
                        "away_team": away_team, "home_team": home_team,
                        "away_odds": away_odds, "home_odds": home_odds
                    })
        except Exception as e:
            print(f"Scraper notice: {e}")
            
        browser.close()
    return scraped_games

def de_vig_sharp(sharp_away, sharp_home):
    def to_implied(o): return 100 / (o + 100) if o > 0 else abs(o) / (abs(o) + 100)
    p_a, p_h = to_implied(sharp_away), to_implied(sharp_home)
    total = p_a + p_h
    return p_a / total, p_h / total

def process_ev_opportunities(sharp_data, soft_data):
    opportunities = []
    for soft in soft_data:
        for sharp in sharp_data:
            if soft['away_team'].lower() in sharp['away_team'].lower() or sharp['away_team'].lower() in soft['away_team'].lower():
                try:
                    bookie = [b for b in sharp['bookmakers'] if b['key'] == 'pinnacle']
                    market = bookie[0]['markets'][0]['outcomes']
                    
                    sh_away = [o['price'] for o in market if o['name'] == sharp['away_team']][0]
                    sh_home = [o['price'] for o in market if o['name'] == sharp['home_team']][0]
                    
                    p_away, _ = de_vig_sharp(sh_away, sh_home)
                    b_away = (soft['away_odds'] / 100) if soft['away_odds'] > 0 else (100 / abs(soft['away_odds']))
                    ev_away = (p_away * b_away) - (1 - p_away)
                    
                    if ev_away > 0:
                        opportunities.append({
                            "team": soft['away_team'], "opponent": soft['home_team'],
                            "ev": round(ev_away * 100, 2), "soft_odds": soft['away_odds'], "sharp_odds": sh_away
                        })
                except: continue
    return sorted(opportunities, key=lambda x: x['ev'], reverse=True)

def push_results_to_github(data_payload):
    file_path = "live_odds.json"
    url = f"https://github.com{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    res = requests.get(url, headers=headers)
    sha = res.json().get("sha", None)
    
    json_bytes = json.dumps(data_payload, indent=2).encode("utf-8")
    encoded_content = base64.b64encode(json_bytes).decode("utf-8")
    
    payload = {"message": "Automated update: Fresh odds logged", "content": encoded_content}
    if sha: payload["sha"] = sha
        
    requests.put(url, headers=headers, json=payload)

if __name__ == "__main__":
    sharps = get_sharp_odds()
    softs = scrape_sportsbet_mt()
    final_ev_bets = process_ev_opportunities(sharps, softs)
    push_results_to_github(final_ev_bets)
    print("Execution complete.")
