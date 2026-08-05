import re
import time
import requests
from collections import defaultdict

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA = "https://gamma-api.polymarket.com"

DATE_SLUG = re.compile(r"^(.+?)-(\d{4}-\d{2}-\d{2})$")

# Words that look sporty but aren't, learned from the last run
EXCLUDE = {"nflx", "influenza", "macro inflation", "maritime transport",
           "inflation", "netflix"}

KEYWORDS = ("sport", "nfl", "nba", "mlb", "nhl", "soccer", "football",
            "basketball", "baseball", "hockey", "tennis", "golf", "ufc",
            "mma", "boxing", "cricket", "league", "epl", "champions",
            "f1", "racing", "olympic", "cup", "liga", "serie", "bundesliga")


def sports_tag_ids():
    all_tags = []
    offset = 0
    for _ in range(25):
        r = requests.get(f"{GAMMA}/tags", params={"limit": 100, "offset": offset}, timeout=15)
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
        if label in EXCLUDE:
            continue
        slug = (t.get("slug") or "").lower()
        if any(k in label or k in slug for k in KEYWORDS):
            ids.append((t["id"], t.get("label")))
    return ids


def polymarket_games():
    """Query per sports tag, keep events whose slug ends in a date."""
    games = defaultdict(list)
    tags = sports_tag_ids()
    print(f"checking {len(tags)} sports tags...")

    for tag_id, label in tags:
        try:
            r = requests.get(
                f"{GAMMA}/events",
                params={"limit": 100, "active": "true", "closed": "false", "tag_id": tag_id},
                timeout=15,
            )
            if not r.ok:
                continue
            for e in r.json():
                m = DATE_SLUG.match(e.get("slug") or "")
                if m:
                    games[m.group(2)].append((m.group(1), e.get("title", ""), label))
        except Exception:
            continue
        time.sleep(0.1)

    return games


def kalshi_games():
    months = {m: i for i, m in enumerate(
        ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"], 1)}
    games = defaultdict(list)
    cursor = None

    for _ in range(30):
        params = {"limit": 200, "status": "open"}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(f"{KALSHI}/events", params=params, timeout=15)
        r.raise_for_status()
        payload = r.json()
        evs = payload.get("events", [])
        if not evs:
            break
        for e in evs:
            if e.get("category") != "Sports":
                continue
            m = re.search(r"^(.+?)-(\d{2})([A-Z]{3})(\d{2})(.*)$", e["event_ticker"])
            if not m:
                continue
            series, yy, mon, dd, tail = m.groups()
            if mon not in months:
                continue
            date = f"20{yy}-{months[mon]:02d}-{dd}"
            games[date].append((series, tail, e.get("title", "")))
        cursor = payload.get("cursor")
        if not cursor:
            break
        time.sleep(0.3)

    return games


p = polymarket_games()
k = kalshi_games()

print(f"\npolymarket: {sum(len(v) for v in p.values())} dated game events")
print(f"kalshi:     {sum(len(v) for v in k.values())} dated sports events")

shared = sorted(set(p) & set(k))
print(f"dates on both: {len(shared)}\n")

for d in shared[:5]:
    print(f"--- {d} ---")
    for slug_head, title, tag in p[d][:5]:
        print(f"  P [{tag[:18]:18}] {slug_head[:45]}")
    print()
    for series, tail, title in k[d][:5]:
        print(f"  K [{series[:18]:18}] {tail[:20]}  {title[:40]}")
    print()