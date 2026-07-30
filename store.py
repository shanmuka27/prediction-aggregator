import sqlite3
import json
from datetime import datetime, timezone

from fetch import fetch_all_markets, get_volume_24hr

DB_PATH = "markets.db"


def init_db(conn):
    """Create tables if they don't exist yet. Safe to run every time."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS markets (
            id          TEXT PRIMARY KEY,
            question    TEXT NOT NULL,
            slug        TEXT,
            outcomes    TEXT
        );

        CREATE TABLE IF NOT EXISTS snapshots (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id    TEXT NOT NULL,
            captured_at  TEXT NOT NULL,
            price        REAL,
            volume_24hr  REAL,
            FOREIGN KEY (market_id) REFERENCES markets(id)
        );

        CREATE INDEX IF NOT EXISTS idx_snapshots_market_time
            ON snapshots(market_id, captured_at);
    """)
    conn.commit()


def save_market(conn, m):
    """Upsert the market's static info."""
    conn.execute(
        """INSERT OR REPLACE INTO markets (id, question, slug, outcomes)
           VALUES (?, ?, ?, ?)""",
        (m["id"], m["question"], m.get("slug"), m.get("outcomes")),
    )


def save_snapshot(conn, m, captured_at):
    """Append one price observation for this market."""
    prices = json.loads(m["outcomePrices"])
    price = float(prices[0]) if prices else None

    conn.execute(
        """INSERT INTO snapshots (market_id, captured_at, price, volume_24hr)
           VALUES (?, ?, ?, ?)""",
        (m["id"], captured_at, price, get_volume_24hr(m)),
    )


def collect():
    captured_at = datetime.now(timezone.utc).isoformat()
    markets = fetch_all_markets()
    print(f"\nFetched {len(markets)} markets")

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    saved = 0
    for m in markets:
        try:
            save_market(conn, m)
            save_snapshot(conn, m, captured_at)
            saved += 1
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            print(f"  skipped {m.get('id')}: {e}")

    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    runs = conn.execute(
        "SELECT COUNT(DISTINCT captured_at) FROM snapshots"
    ).fetchone()[0]
    conn.close()

    print(f"Saved {saved} snapshots at {captured_at}")
    print(f"Database now holds {total} snapshots across {runs} runs")


if __name__ == "__main__":
    collect()