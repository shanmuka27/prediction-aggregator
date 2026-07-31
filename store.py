import os
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

from fetch import fetch_normalized as fetch_polymarket
from kalshi_fetch import fetch_normalized as fetch_kalshi

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

CREATE INDEX IF NOT EXISTS idx_markets_platform
    ON markets(platform);
"""


def init_db(conn):
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    conn.commit()


def gather():
    """Pull from every platform. One source failing shouldn't kill the run."""
    records = []

    for name, fetcher in [("polymarket", fetch_polymarket), ("kalshi", fetch_kalshi)]:
        try:
            got = fetcher()
            print(f"{name}: {len(got)} records")
            records.extend(got)
        except Exception as e:
            print(f"{name} FAILED: {e}")

    return records


def to_rows(records, captured_at):
    """Dedupe by id, split into market rows and snapshot rows."""
    markets = {}
    snapshots = {}

    for r in records:
        markets[r["id"]] = (
            r["id"], r["platform"], r["question"], r["slug"], r["outcomes"],
        )
        snapshots[r["id"]] = (
            r["id"], captured_at, r["price"], r["volume_24hr"],
        )

    return list(markets.values()), list(snapshots.values())


def collect():
    captured_at = datetime.now(timezone.utc)
    records = gather()

    if not records:
        print("nothing fetched, skipping write")
        return

    market_rows, snapshot_rows = to_rows(records, captured_at)

    conn = psycopg2.connect(DATABASE_URL)
    try:
        init_db(conn)

        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO markets (id, platform, question, slug, outcomes)
                VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    platform = EXCLUDED.platform,
                    question = EXCLUDED.question,
                    slug     = EXCLUDED.slug,
                    outcomes = EXCLUDED.outcomes
            """, market_rows)

            execute_values(cur, """
                INSERT INTO snapshots (market_id, captured_at, price, volume_24hr)
                VALUES %s
            """, snapshot_rows)

            cur.execute("""
                SELECT m.platform, COUNT(*)
                FROM snapshots s JOIN markets m ON m.id = s.market_id
                GROUP BY m.platform
            """)
            by_platform = cur.fetchall()

        conn.commit()
    finally:
        conn.close()

    print(f"\nSaved {len(snapshot_rows)} snapshots at {captured_at.isoformat()}")
    for platform, count in by_platform:
        print(f"  {platform}: {count} total snapshots")


if __name__ == "__main__":
    collect()