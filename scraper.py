import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

RANKING_URLS = {
    "ATP": "https://live-tennis.eu/pl/oficjalny-ranking-atp",
    "WTA": "https://live-tennis.eu/pl/oficjalny-ranking-wta",
}
OUTPUT_DIR = Path("data")
MAX_RANK = 500

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def find_ranking_table(soup: BeautifulSoup, tour: str):
    candidates = []
    for table in soup.find_all("table"):
        text = clean_text(table.get_text(" ", strip=True)).lower()
        score = 0
        if "pkt" in text:
            score += 2
        if "kraj" in text:
            score += 2
        if "nazwisko" in text or "zawodniczka" in text or "zawodnik" in text:
            score += 2
        if "ranking" in text:
            score += 1
        if score >= 4:
            candidates.append((score, table))

    if not candidates:
        raise RuntimeError(f"Could not find {tour} ranking table")

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def parse_rankings(tour: str, html: str):
    soup = BeautifulSoup(html, "html.parser")
    table = find_ranking_table(soup, tour)
    players = []

    for row in table.find_all("tr"):
        cells = [clean_text(c.get_text(" ", strip=True)) for c in row.find_all("td")]
        if len(cells) < 2:
            continue

        # The first cell is the ranking position.
        rank_match = re.fullmatch(r"(\d+)", cells[0].replace(".", "").strip())
        if not rank_match:
            continue
        rank = int(rank_match.group(1))

        if rank > MAX_RANK:
            continue

        # The player name is the cell immediately after the rank.
        # Do not use country/points columns: they caused the player field
        # to contain the player's age (e.g. "29") in the previous parser.
        player_name = cells[1]
        if not player_name:
            continue

        # The ranking page may contain repeated responsive rows. Keep the
        # first valid occurrence for each rank.
        if any(player["rank"] == rank for player in players):
            continue

        players.append({
            "rank": rank,
            "player": player_name,
        })

    if not players:
        raise RuntimeError(f"Parsed zero players from {tour} ranking")

    players.sort(key=lambda player: player["rank"])

    if len(players) < MAX_RANK:
        missing = sorted(set(range(1, MAX_RANK + 1)) - {p["rank"] for p in players})
        preview = ", ".join(map(str, missing[:10]))
        raise RuntimeError(
            f"Incomplete {tour} ranking: parsed {len(players)}/{MAX_RANK} players; "
            f"missing ranks include {preview}"
        )

    return players[:MAX_RANK]


def fetch_ranking(tour: str, url: str):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return parse_rankings(tour, response.text)


def save_ranking(tour: str, players):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tour": tour,
        "source": RANKING_URLS[tour],
        "ranking": players,
    }
    path = OUTPUT_DIR / f"{tour.lower()}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(players)} {tour} players to {path}")


def main():
    for tour, url in RANKING_URLS.items():
        players = fetch_ranking(tour, url)
        save_ranking(tour, players)


if __name__ == "__main__":
    main()
