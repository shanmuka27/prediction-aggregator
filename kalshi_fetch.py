import json
import time
import requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"


def _f(value):
    """Kalshi returns numbers as strings. Convert safely."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def fetch_all_markets(days_ahead=30, page_size=200, max_pages=40):
    """
    Open markets closing within `days_ahead`.

    Kalshi rate limits bursts, so we pace requests and back off on 429.
    """
    cutoff = int(time.time()) + days_ahead * 86400
    all_markets = []
    cursor = None

    for _ in range(max_pages):
        params = {"limit": page_size, "status": "open", "max_close_ts": cutoff}
        if cursor:
            params["cursor"] = cursor

        payload = None
        for attempt in range(5):
            resp = requests.get(f"{BASE}/markets", params=params, timeout=15)

            if resp.status_code == 429:
                wait = 2 ** attempt
                print(f"  kalshi: rate limited, waiting {wait}s")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            payload = resp.json()
            break

        if payload is None:
            print("  kalshi: giving up after repeated rate limits")
            break

        page = payload.get("markets", [])
        if not page:
            break

        all_markets.extend(page)
        print(f"  kalshi: {len(all_markets)} so far...")

        cursor = payload.get("cursor")
        if not cursor:
            break

        time.sleep(0.3)

    return all_markets


def implied_probability(m):
    """Midpoint of the yes bid/ask. Falls back to last traded price."""
    bid = _f(m.get("yes_bid_dollars"))
    ask = _f(m.get("yes_ask_dollars"))

    if bid > 0 and ask > 0:
        return (bid + ask) / 2

    last = _f(m.get("last_price_dollars"))
    return last if last > 0 else None


def build_question(m):
    title = m.get("title") or m["ticker"]
    sub = m.get("yes_sub_title")
    if sub and sub.lower() not in title.lower():
        return f"{title} ({sub})"
    return title


def normalize(m):
    """Convert a Kalshi market into our common shape."""
    return {
        "id": m["ticker"],
        "platform": "kalshi",
        "question": build_question(m),
        "slug": m.get("event_ticker"),
        "outcomes": json.dumps(["Yes", "No"]),
        "price": implied_probability(m),
        "volume_24hr": _f(m.get("volume_24h_fp")),
    }


def fetch_normalized(min_volume=1.0):
    """Live markets only, in our common shape."""
    raw = fetch_all_markets()
    records = [normalize(m) for m in raw]
    return [
        r for r in records
        if r["price"] is not None and r["volume_24hr"] >= min_volume
    ]


def main():
    records = fetch_normalized()
    records.sort(key=lambda r: r["volume_24hr"], reverse=True)

    print(f"\n{len(records)} live Kalshi markets\n")
    for r in records[:15]:
        print(r["question"][:75])
        print(f"   {r['price'] * 100:.1f}%   24h vol: {r['volume_24hr']:,.0f}")
        print()


if __name__ == "__main__":
    main()