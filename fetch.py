import requests
import json

BASE = "https://gamma-api.polymarket.com"


def fetch_all_markets(page_size=100, max_pages=20):
    """Page through Gamma until we run out of markets or hit the cap."""
    all_markets = []
    offset = 0

    for _ in range(max_pages):
        resp = requests.get(
            f"{BASE}/markets",
            params={
                "limit": page_size,
                "offset": offset,
                "active": "true",
                "closed": "false",
            },
            timeout=10,
        )
        resp.raise_for_status()
        page = resp.json()

        if not page:
            break

        all_markets.extend(page)
        print(f"  fetched {len(all_markets)} so far...")

        offset += page_size

        if len(page) < page_size:
            break

    return all_markets


def get_volume(m):
    """Lifetime volume as a float. Some markets return None."""
    return float(m.get("volume") or 0)


def get_volume_24hr(m):
    """Volume in the last 24 hours. This is the one that shows real activity."""
    return float(m.get("volume24hr") or 0)


def top_markets(markets, n=10):
    """The n most active markets in the last 24 hours."""
    ranked = sorted(markets, key=get_volume_24hr, reverse=True)
    return ranked[:n]


def print_market(m):
    # Gamma returns these two as JSON-encoded strings, not real lists.
    outcomes = json.loads(m["outcomes"])
    prices = json.loads(m["outcomePrices"])

    print(m["question"])
    print(f"   24h vol: ${get_volume_24hr(m):,.0f}   lifetime: ${get_volume(m):,.0f}")

    for name, price in zip(outcomes, prices):
        print(f"   {name}: {float(price) * 100:.1f}%")
    print()


def main():
    print("Fetching markets...")
    markets = fetch_all_markets()
    print(f"\nTotal: {len(markets)} active markets\n")

    for m in top_markets(markets):
        print_market(m)


if __name__ == "__main__":
    main()