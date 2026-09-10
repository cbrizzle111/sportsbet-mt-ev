import os
import json
import base64
import requests
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
ODDS_API_KEY = "3f0f2a1c262ac23d9b31145bd1f3b3ed"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") # Automatically grabbed by GitHub Actions
REPO_NAME = "cbrizzle111/sportsbet-mt-ev"
# ---------------------


def get_sharp_odds():
    """Fetches Pinnacle lines directly via The Odds API."""
    url = f"https://the-odds-api.com{ODDS_API_KEY}"
    response = requests.get(url)
    if response.status_code != 200:
        print("Error pulling sharp lines.")
        return []
    return response.json()

def scrape_sportsbet_mt():
    """Uses Playwright to simulate a browser session and read SportsBet MT."""
    scraped_games = []
    with sync_playwright() as p:
        # Launch browser invisibly
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Navigate directly to the SportsBet MT dynamic betting grid
        page.goto("https://www.sportsbetmontana.com/", wait_until="networkidle")
        
        # Wait for the JavaScript cards containing odds tables to render on screen
        page.wait_for_selector(".sport-event-row, .event-card, .odds-button", timeout=15000)
        
        # Target the sports cards using general structural elements
        cards = page.query_selector_all(".sport-event-row, .event-card")
        
        for card in cards:
            try:
                # Target team strings and match odds values out of buttons
                teams = card.query_selector_all(".team-name, .participant-name")
                odds_buttons = card.query_selector_all(".odds-button, .price-value")
                
                if len(teams) >= 2 and len(odds_buttons) >= 2:
                    away_team = teams[0].inner_text().strip()
                    home_team = teams[1].inner_text().strip()
                    
                    # Safe numerical conversions for soft lines
                    away_odds = int(odds_buttons[0].inner_text().replace("+", "").strip())
                    home_odds = int(odds_buttons[1].inner_text().replace("+", "").strip())
                    
                    scraped_games.append({
                        "away_team": away_team,
                        "home_team": home_team,
                        "away_odds": away_odds,
                        "home_odds": home_odds
                    })
            except Exception as e:
                continue # Skip corrupt entries or layout outliers smoothly
                
        browser.close()
    return scraped_games

def de_vig_sharp(sharp_away, sharp_home):
    """Calculates true probabilities by draining house edge."""
    def to_implied(o):
        return 100 / (o + 100) if o > 0 else abs(o) / (abs(o) + 100)
    p_a = to_implied(sharp_away)
    p_h = to_implied(sharp_home)
    total = p_a + p_h
    return p_a / total, p_h / total

def process_ev_opportunities(sharp_data, soft_data):
    """Correlates matchups and logs +EV lines via the math rules."""
    opportunities = []
    for soft in soft_data:
        for sharp in sharp_data:
            # String matching logic to verify matches despite naming differences
            if soft['away_team'].lower() in sharp['away_team'].lower() or sharp['away_team'].lower() in soft['away_team'].lower():
                try:
                    # Isolate Pinnacle lines from the API response structure
                    bookie = [b for b in sharp['bookmakers'] if b['key'] == 'pinnacle'][0]
                    market = bookie['markets'][0]['outcomes']
                    
                    sh_away = [o['price'] for o in market if o['name'] == sharp['away_team']][0]
                    sh_home = [o['price'] for o in market if o['name'] == sharp['home_team']][0]
                    
                    # Process clean probabilities
                    p_away, p_home = de_vig_sharp(sh_away, sh_home)
                    
                    # Test Away Edge
                    b_away = (soft['away_odds'] / 100) if soft['away_odds'] > 0 else (100 / abs(soft['away_odds']))
                    ev_away = (p_away * b_away) - (1 - p_away)
                    if ev_away > 0:
                        opportunities.append({
                            "team": soft['away_team'], "opponent": soft['home_team'],
                            "ev": round(ev_away * 100, 2), "soft_odds": soft['away_odds'], "sharp_odds": sh_away
                        })
                except:
                    continue
    return sorted(opportunities, key=lambda x: x['ev'], reverse=True)

def push_results_to_github(data_payload):
    """Pushes processed odds data straight to GitHub Pages so your phone gets it instantly."""
    file_path = "live_odds.json"
    url = f"https://github.com{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    # Get file sha to handle overwriting cleanly
    res = requests.get(url, headers=headers)
    sha = res.json().get("sha", None)
    
    json_bytes = json.dumps(data_payload, indent=2).encode("utf-8")
    encoded_content = base64.b64encode(json_bytes).decode("utf-8")
    
    payload = {"message": "Automated system update: Fresh lines loaded", "content": encoded_content}
    if sha:
        payload["sha"] = sha
        
    requests.put(url, headers=headers, json=payload)
    print("Dashboard payload successfully synced to GitHub Pages UI!")

if __name__ == "__main__":
    print("Step 1: Gathering Sharp Feeds...")
    sharps = get_sharp_odds()
    print("Step 2: Accessing SportsBet Montana Matrix...")
    softs = scrape_sportsbet_mt()
    print("Step 3: Crunching Math Model Engine...")
    final_ev_bets = process_ev_opportunities(sharps, softs)
    print("Step 4: Broadcasting Live App Feed updates...")
    push_results_to_github(final_ev_bets)
