import json
import re
import unicodedata
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

SPECIAL_CHAR_MAP = str.maketrans({
    "Ł": "L",
    "ł": "l",
    "Đ": "D",
    "đ": "d",
    "Ø": "O",
    "ø": "o",
    "Æ": "AE",
    "æ": "ae",
    "Œ": "OE",
    "œ": "oe",
    "ß": "ss",
})


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_player_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return value.translate(SPECIAL_CHAR_MAP)


def find_ranking_table(soup: BeautifulSoup, tour: str):
    candidates = []
    for table in soup.find_all("table"):
        text = clean_text(table.get_text(" ", strip=True)).lower()
        score = 0
        if "pkt" in text:
            score += 2
        if "kraj" in text:
            score += 2
        if "nazwisko" in text:
            score += 3
        if "wiek" in text:
            score += 2
        if re.search(r"\b1\s+[^\n]+\s+\d{1,3}\s+[A-Z]{3}\s+\d+", text, re.I):
            score += 2
        if score >= 5:
            candidates.append((score, len(table.find_all("tr")), table))

    if not candidates:
        raise RuntimeError(f"Could not find {tour} ranking table")

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def parse_rankings(tour: str, html: str):
    soup = BeautifulSoup(html, "html.parser")
    table = find_ranking_table(soup, tour)
    players_by_rank = {}

    # Parse the complete visible row text instead of relying on a specific
    # number/order of <td> elements. live-tennis.eu includes age, country,
    # points and tournament columns, and its markup can vary between runs.
    # The stable part is: rank + player name + age + country + points.
    row_pattern = re.compile(
        r"^(\d+)\s+(.+?)\s+\d{1,3}\s+[A-Z]{3}\s+\d+(?:\s|$)"
    )

    for row in table.find_all("tr"):
        row_text = clean_text(row.get_text(" ", strip=True))
        match = row_pattern.match(row_text)
        if not match:
            continue

        rank = int(match.group(1))
        if rank > MAX_RANK:
            continue

        player_name = normalize_player_name(match.group(2).strip())
        if not player_name:
            continue

        # Keep the first valid occurrence if the page contains duplicate
        # responsive/secondary markup for the same ranking position.
        players_by_rank.setdefault(
            rank,
            {
                "rank": rank,
                "player": player_name,
            },
        )

    players = [players_by_rank[rank] for rank in sorted(players_by_rank)]

    if not players:
        raise RuntimeError(f"Parsed zero players from {tour} ranking")

    if len(players) < MAX_RANK:
        missing = sorted(set(range(1, MAX_RANK + 1)) - set(players_by_rank))
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
