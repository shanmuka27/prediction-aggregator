import json
import re
import time
import requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"

MONTHS = {m: i for i, m in enumerate(
    ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"], 1)}


def _f(value):
    """Kalshi returns numbers as strings. Convert safely."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _get(url, params):
    """GET with backoff on 429."""
    for attempt in range(5):
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 429:
            wait = 2 ** attempt
            print(f"  kalshi: rate limited, waiting {wait}s")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    return None


def fetch_sports_events(with_markets=True):
    """All open sports events, with their markets embedded."""
    events = []
    cursor = None

    for _ in range(40):
        params = {"limit": 200, "status": "open"}
        if with_markets:
            params["with_nested_markets"] = "true"
        if cursor:
            params["cursor"] = cursor
        payload = _get(f"{BASE}/events", params)
        if payload is None:
            break
        page = payload.get("events", [])
        if not page:
            break
        events.extend(e for e in page if e.get("category") == "Sports")
        cursor = payload.get("cursor")
        if not cursor:
            break
        time.sleep(0.3)

    print(f"  kalshi: {len(events)} sports events")
    return events


def parse_game_date(event_ticker):
    """Extract YYYY-MM-DD from tickers like KXMLBGAME-26AUG03NYYCHC."""
    m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})", event_ticker)
    if not m:
        return None
    yy, mon, dd = m.groups()
    if mon not in MONTHS:
        return None
    return f"20{yy}-{MONTHS[mon]:02d}-{dd}"


def parse_teams(title):
    """'Vancouver vs Atlante: Total Goals' -> ('Vancouver', 'Atlante')."""
    head = title.split(":")[0]
    parts = re.split(r"\s+vs\.?\s+", head, flags=re.IGNORECASE)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None, None


def implied_probability(m):
    """Midpoint of yes bid/ask, falling back to last traded price."""
    bid = _f(m.get("yes_bid_dollars"))
    ask = _f(m.get("yes_ask_dollars"))
    if bid > 0 and ask > 0:
        return (bid + ask) / 2
    last = _f(m.get("last_price_dollars"))
    return last if last > 0 else None


def fetch_normalized(min_volume=1.0):
    """
    Sports markets + their parent games, both in common shape.

    Returns (records, games):
      records - one dict per live market, matching the shape store.py expects
      games   - one dict per game/event that has at least one live market
    """
    events = fetch_sports_events()

    games = {}
    records = []

    for e in events:
        t = e["event_ticker"]
        date = parse_game_date(t)
        if not date:
            continue

        home, away = parse_teams(e.get("title", ""))
        games[t] = {
            "game_id": t,
            "platform": "kalshi",
            "game_date": date,
            "team_a": home,
            "team_b": away,
            "league": e.get("series_ticker"),
            "title": e.get("title", ""),
        }

        for m in e.get("markets") or []:
            if m.get("status") not in (None, "active", "open"):
                continue
            price = implied_probability(m)
            vol = _f(m.get("volume_24h_fp"))
            if price is None or vol < min_volume:
                continue
            title = m.get("title") or m.get("ticker", "")
            sub = m.get("yes_sub_title")
            if sub and sub.lower() not in title.lower():
                title = f"{title} ({sub})"
            records.append({
                "id": m["ticker"],
                "platform": "kalshi",
                "game_id": t,
                "question": title,
                "slug": t,
                "outcomes": json.dumps(["Yes", "No"]),
                "price": price,
                "volume_24hr": vol,
            })

    live_ids = {r["game_id"] for r in records}
    live_games = [g for t, g in games.items() if t in live_ids]

    print(f"  kalshi: {len(records)} live markets across {len(live_games)} games")
    return records, live_games


if __name__ == "__main__":
    records, games_list = fetch_normalized()

    with_teams = [g for g in games_list if g["team_a"]]
    print(f"\n{len(with_teams)} games with parsed team names:\n")

    for g in sorted(with_teams, key=lambda x: x["game_date"])[:15]:
        print(f"{g['game_date']}  {g['team_a']} vs {g['team_b']}  [{g['league']}]")