import json
import re
import time
import requests

BASE = "https://gamma-api.polymarket.com"

DATE_SLUG = re.compile(r"^(.+?)-(\d{4}-\d{2}-\d{2})$")

# Tag labels that match sports keywords but aren't sports
EXCLUDE_LABELS = {"nflx", "influenza", "macro inflation", "maritime transport",
                  "inflation", "netflix", "world series of poker"}

KEYWORDS = ("sport", "nfl", "nba", "mlb", "nhl", "soccer", "football",
            "basketball", "baseball", "hockey", "tennis", "golf", "ufc",
            "mma", "boxing", "cricket", "league", "epl", "champions",
            "f1", "racing", "olympic", "cup", "liga", "serie", "bundesliga",
            "wnba", "ncaa", "esports", "valorant", "dota", "cs2")


def fetch_sports_tag_ids():
    """All tag IDs whose label/slug looks sports-related."""
    all_tags = []
    offset = 0
    for _ in range(25):
        r = requests.get(f"{BASE}/tags", params={"limit": 100, "offset": offset}, timeout=15)
        r.raise_for_status()
        page = r.json()
        if not page:
            break
        all_tags.extend(page)
        offset += 100
        if len(page) < 100:
            break

    ids = []
    for t in all_tags:
        label = (t.get("label") or "").lower()
        slug = (t.get("slug") or "").lower()
        if label in EXCLUDE_LABELS:
            continue
        if any(k in label or k in slug for k in KEYWORDS):
            ids.append(t["id"])
    print(f"  polymarket: {len(ids)} sports tags")
    return ids


def fetch_sports_events():
    """Active events under any sports tag, deduped by event id."""
    tag_ids = fetch_sports_tag_ids()
    events = {}

    for tag_id in tag_ids:
        try:
            r = requests.get(
                f"{BASE}/events",
                params={"limit": 100, "active": "true", "closed": "false",
                        "tag_id": tag_id},
                timeout=15,
            )
            if not r.ok:
                continue
            for e in r.json():
                events[e["id"]] = e
        except requests.RequestException:
            continue
        time.sleep(0.1)

    print(f"  polymarket: {len(events)} sports events")
    return list(events.values())


def parse_teams(title):
    """'Manhattan Jaspers vs. Siena Saints (W)' -> team names."""
    head = title.split(":")[0]
    head = re.sub(r"\s*\((W|M)\)\s*$", "", head)
    parts = re.split(r"\s+vs\.?\s+", head, flags=re.IGNORECASE)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None, None


def parse_game(e):
    """Game metadata from an event, or None if it isn't a dated game."""
    slug = e.get("slug") or ""
    m = DATE_SLUG.match(slug)
    if not m:
        return None
    team_a, team_b = parse_teams(e.get("title", ""))
    league = m.group(1).split("-")[0]
    return {
        "game_id": f"pm-{e['id']}",
        "platform": "polymarket",
        "game_date": m.group(2),
        "team_a": team_a,
        "team_b": team_b,
        "league": league,
        "title": e.get("title", ""),
    }


def normalize_market(m, game_id):
    """One Polymarket market in our common shape, or None if unusable."""
    try:
        prices = json.loads(m["outcomePrices"])
        price = float(prices[0]) if prices else None
    except (KeyError, ValueError, json.JSONDecodeError):
        return None
    if price is None:
        return None

    vol = float(m.get("volume24hr") or 0)
    return {
        "id": m["id"],
        "platform": "polymarket",
        "game_id": game_id,
        "question": m.get("question", ""),
        "slug": m.get("slug"),
        "outcomes": m.get("outcomes"),
        "price": price,
        "volume_24hr": vol,
    }


def fetch_normalized(min_volume=1.0):
    """
    Sports markets + games in common shape. Returns (records, games).

    Events embed their markets in the Gamma /events response.
    """
    events = fetch_sports_events()

    games = []
    records = []

    for e in events:
        game = parse_game(e)
        if game is None:
            continue

        game_records = []
        for m in e.get("markets") or []:
            rec = normalize_market(m, game["game_id"])
            if rec and rec["volume_24hr"] >= min_volume:
                game_records.append(rec)

        if game_records:
            games.append(game)
            records.extend(game_records)

    print(f"  polymarket: {len(records)} live markets across {len(games)} games")
    return records, games


if __name__ == "__main__":
    records, games_list = fetch_normalized()

    with_teams = [g for g in games_list if g["team_a"]]
    print(f"\n{len(with_teams)} games with parsed team names:\n")

    for g in sorted(with_teams, key=lambda x: x["game_date"])[:15]:
        print(f"{g['game_date']}  {g['team_a']} vs {g['team_b']}  [{g['league']}]")