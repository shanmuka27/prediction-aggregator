# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Pulls live sports-market data from Polymarket (Gamma API) and Kalshi (trade API), normalizes both into a
common shape, and stores snapshots in Postgres so odds can be compared/tracked over time across platforms.

## Setup

```
py -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Requires a `.env` file with `DATABASE_URL` (Postgres connection string) — loaded via `python-dotenv` in
`store.py` and `matcher.py`.

## Commands

- `python store.py` — run one collection pass (fetch both platforms, upsert games/markets, insert snapshots).
- `python batch_collect.py` — run 4 collection passes, 15 min apart, then exit (used for local backfilling).
- `python collector.py` — run collection forever, every 15 min, until Ctrl+C (long-running/overnight use).
- `python matcher.py` — fuzzy-match today-and-later games between Polymarket and Kalshi, print candidate pairs.
- `python polymarket_fetch.py` / `python kalshi_fetch.py` — run a single source's fetch standalone and print a
  sample of parsed games (useful for debugging tag filters or team-name parsing without touching the DB).
- `python explore_tags.py` — ad hoc script for investigating Polymarket sports tags vs Kalshi event tickers by
  shared date; not part of the regular pipeline.

There is no test suite, linter, or build step in this repo.

## Architecture

**Per-platform fetch → normalize → common shape.** `polymarket_fetch.py` and `kalshi_fetch.py` each expose a
`fetch_normalized()` that returns `(records, games)`:
- `records`: one dict per live market (`id`, `platform`, `game_id`, `question`, `slug`, `outcomes`, `price`,
  `volume_24hr`), filtered by `min_volume`.
- `games`: one dict per event that has at least one surviving market (`game_id`, `platform`, `game_date`,
  `team_a`, `team_b`, `league`, `title`).

Each fetcher is self-contained (its own tag/keyword filtering, team-name parsing from the event title, date
extraction) — there's no shared base class, just the same dict shape by convention. When adding a new
platform, match this `fetch_normalized() -> (records, games)` contract so `store.py` doesn't need to change.

**`store.py` is the write path.** `gather()` calls both fetchers and isolates failures per-source (one
platform failing doesn't block the other). `collect()` converts records/games to rows and upserts into three
tables: `games`, `markets` (both upserted on conflict), and `snapshots` (append-only, one row per market per
collection run — this is what builds the time series). Schema is created inline via `CREATE TABLE IF NOT
EXISTS` in `store.py`, not a migration tool.

**`matcher.py` links the same real-world game across platforms.** Since Polymarket and Kalshi assign unrelated
IDs to the same game, matching is done post-hoc by comparing normalized team-name pairs (order-independent,
noise words like "FC"/"United" stripped) on games sharing a date, scored with `rapidfuzz.fuzz.token_set_ratio`
against a threshold. This is read-only against the `games` table — it doesn't write match results back to the
DB yet.

**Two entry points for running collection**, both wrapping `store.collect()`: `collector.py` loops forever
(local/manual overnight runs), `batch_collect.py` runs a fixed number of passes then exits (used by the GitHub
Actions workflow at `.github/workflows/collect.yml`, which runs collection hourly at :07 via
`workflow_dispatch`/cron using `DATABASE_URL` from repo secrets).

## Notes

- `markets.db` (SQLite) and `README.md`'s `fetch.py` reference are leftover from an earlier iteration before
  the Postgres/multi-source design — the actual pipeline today is Postgres-only, driven by `store.py`.
- Kalshi's API string-encodes numeric fields; use `_f()` in `kalshi_fetch.py` for safe float coercion rather
  than casting directly.
- Both fetchers' sports-tag/category filtering is allowlist-plus-denylist (`KEYWORDS` + `EXCLUDE_LABELS`/
  `EXCLUDE`) tuned by trial and error against real API responses — if sports events go missing or junk events
  appear, check these lists first before changing the fetch logic.
