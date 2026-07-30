import os
import json
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

from fetch import fetch_all_markets, get_volume_24hr

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    id          TEXT PRIMARY KEY,
    platform    TEXT NOT NULL DEFAULT 'polymarket',
    question    TEXT NOT NULL,
    slug        TEXT,
    outcomes    TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    id           BIGSERIAL PRIMARY KEY,
    market_id    TEXT NOT NULL REFERENCES markets(id),
    captured_at  TIMESTAMPTZ NOT NULL,
    price        DOUBLE PRECISION,
    volume_24hr  DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_snapshots_market_time
    ON snapshots(market_id, captured_at);
"""


def init_db(conn):
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    conn.commit()


def extract_price(m):
    """First outcome's price. Yes side on binary markets."""
    prices = json.loads(m["outcomePrices"])
    return float(prices[0]) if prices else None


def build_rows(markets, captured_at, platform="polymarket"):
    """Turn API records into DB rows, deduped by market id."""
    market_rows = {}
    snapshot_rows = {}

    for m in markets:
        try:
            mid = m["id"]
            market_rows[mid] = (
                mid, platform, m["question"], m.get("slug"), m.get("outcomes"),
            )
            snapshot_rows[mid] = (
                mid, captured_at, extract_price(m), get_volume_24hr(m),
            )
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            print(f"  skipped {m.get('id')}: {e}")

    return list(market_rows.values()), list(snapshot_rows.values())


def collect():
    captured_at = datetime.now(timezone.utc)
    markets = fetch_all_markets()
    print(f"\nFetched {len(markets)} markets")

    market_rows, snapshot_rows = build_rows(markets, captured_at)

    conn = psycopg2.connect(DATABASE_URL)
    try:
        init_db(conn)

        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO markets (id, platform, question, slug, outcomes)
                VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    question = EXCLUDED.question,
                    slug     = EXCLUDED.slug,
                    outcomes = EXCLUDED.outcomes
            """, market_rows)

            execute_values(cur, """
                INSERT INTO snapshots (market_id, captured_at, price, volume_24hr)
                VALUES %s
            """, snapshot_rows)

            cur.execute(
                "SELECT COUNT(*), COUNT(DISTINCT captured_at) FROM snapshots"
            )
            total, runs = cur.fetchone()

        conn.commit()
    finally:
        conn.close()

    print(f"Saved {len(snapshot_rows)} snapshots at {captured_at.isoformat()}")
    print(f"Database now holds {total} snapshots across {runs} runs")


if __name__ == "__main__":
    collect()