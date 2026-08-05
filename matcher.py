import os
import re
from collections import defaultdict

import psycopg2
from rapidfuzz import fuzz
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]

# Words that add noise to team-name comparison
NOISE = {"fc", "cf", "sc", "ec", "afc", "cd", "club", "the", "de",
         "city", "united", "utd"}


def normalize_team(name):
    """Lowercase, strip punctuation and common filler, for comparison."""
    if not name:
        return ""
    name = name.lower()
    name = re.sub(r"[^\w\s]", " ", name)
    tokens = [t for t in name.split() if t not in NOISE]
    return " ".join(tokens)


def game_key(team_a, team_b):
    """Order-independent team signature so home/away flips still match."""
    a, b = normalize_team(team_a), normalize_team(team_b)
    return tuple(sorted([a, b]))


def load_games():
    """Distinct games per platform, deduped by date + teams."""
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT platform, game_date, team_a, team_b
            FROM games
            WHERE team_a IS NOT NULL AND team_b IS NOT NULL
              AND game_date >= CURRENT_DATE
        """)
        rows = cur.fetchall()
    conn.close()

    by_platform = defaultdict(list)
    for platform, date, a, b in rows:
        by_platform[platform].append({
            "date": date, "team_a": a, "team_b": b,
            "key": game_key(a, b),
        })
    return by_platform


def match(threshold=80):
    games = load_games()
    poly = games["polymarket"]
    kalshi = games["kalshi"]

    # Index kalshi by date for a cheaper comparison
    kalshi_by_date = defaultdict(list)
    for g in kalshi:
        kalshi_by_date[g["date"]].append(g)

    pairs = []
    for pg in poly:
        for kg in kalshi_by_date.get(pg["date"], []):
            # Compare the combined team signatures
            score = fuzz.token_set_ratio(
                " ".join(pg["key"]), " ".join(kg["key"])
            )
            if score >= threshold:
                pairs.append((score, pg, kg))

    pairs.sort(key=lambda x: -x[0])
    return pairs


if __name__ == "__main__":
    pairs = match()
    print(f"found {len(pairs)} candidate pairs\n")

    seen = set()
    for score, pg, kg in pairs:
        # Show each polymarket game only once, best match
        sig = (pg["date"], pg["key"])
        if sig in seen:
            continue
        seen.add(sig)
        print(f"[{score:.0f}] {pg['date']}")
        print(f"    PM: {pg['team_a']} vs {pg['team_b']}")
        print(f"    K:  {kg['team_a']} vs {kg['team_b']}")
        print()