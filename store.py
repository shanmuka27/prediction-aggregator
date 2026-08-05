import os
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

from polymarket_fetch import fetch_normalized as fetch_polymarket
from kalshi_fetch import fetch_normalized as fetch_kalshi

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    game_id     TEXT PRIMARY KEY,
    platform    TEXT NOT NULL,
    game_date   DATE,
    team_a      TEXT,
    team_b      TEXT,
    league      TEXT,
    title       TEXT
);

CREATE TABLE IF NOT EXISTS markets (
    id          TEXT PRIMARY KEY,
    platform    TEXT NOT NULL,
    game_id     TEXT REFERENCES games(game_id),
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
CREATE INDEX IF NOT EXISTS idx_markets_game ON markets(game_id);
CREATE INDEX IF NOT EXISTS idx_games_date ON games(game_date);
"""


def init_db(conn):
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    conn.commit()


def gather():
    """Pull (records, games) from each platform. One failing source is isolated."""
    all_records = []
    all_games = []

    for name, fetcher in [("polymarket", fetch_polymarket), ("kalshi", fetch_kalshi)]:
        try:
            records, games = fetcher()
            print(f"{name}: {len(records)} markets, {len(games)} games")
            all_records.extend(records)
            all_games.extend(games)
        except Exception as e:
            print(f"{name} FAILED: {e}")

    return all_records, all_games


def to_rows(records, games, captured_at):
    game_rows = {}
    for g in games:
        game_rows[g["game_id"]] = (
            g["game_id"], g["platform"], g["game_date"],
            g["team_a"], g["team_b"], g["league"], g["title"],
        )

    market_rows = {}
    snapshot_rows = {}
    for r in records:
        market_rows[r["id"]] = (
            r["id"], r["platform"], r["game_id"],
            r["question"], r["slug"], r["outcomes"],
        )
        snapshot_rows[r["id"]] = (
            r["id"], captured_at, r["price"], r["volume_24hr"],
        )

    return list(game_rows.values()), list(market_rows.values()), list(snapshot_rows.values())


def collect():
    captured_at = datetime.now(timezone.utc)
    records, games = gather()

    if not records:
        print("nothing fetched, skipping write")
        return

    game_rows, market_rows, snapshot_rows = to_rows(records, games, captured_at)

    conn = psycopg2.connect(DATABASE_URL)
    try:
        init_db(conn)
        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO games (game_id, platform, game_date, team_a, team_b, league, title)
                VALUES %s
                ON CONFLICT (game_id) DO UPDATE SET
                    game_date = EXCLUDED.game_date,
                    team_a = EXCLUDED.team_a,
                    team_b = EXCLUDED.team_b,
                    league = EXCLUDED.league,
                    title = EXCLUDED.title
            """, game_rows)

            execute_values(cur, """
                INSERT INTO markets (id, platform, game_id, question, slug, outcomes)
                VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    game_id = EXCLUDED.game_id,
                    question = EXCLUDED.question,
                    slug = EXCLUDED.slug,
                    outcomes = EXCLUDED.outcomes
            """, market_rows)

            execute_values(cur, """
                INSERT INTO snapshots (market_id, captured_at, price, volume_24hr)
                VALUES %s
            """, snapshot_rows)
        conn.commit()
    finally:
        conn.close()

    print(f"\nSaved {len(game_rows)} games, {len(snapshot_rows)} snapshots at {captured_at.isoformat()}")


if __name__ == "__main__":
    collect()