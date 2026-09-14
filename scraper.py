import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://live-tennis.eu/en"
RANKING_URLS = {
    "ATP": f"{BASE_URL}/official-atp-ranking",
    "WTA": f"{BASE_URL}/official-wta-ranking",
}
OUTPUT_DIR = Path("data")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    )
}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_number(value: str):
    value = value.replace(",", "").strip()
    match = re.search(r"-?\d+", value)
    return int(match.group()) if match else None


def parse_rankings(tour: str, html: str):
    soup = BeautifulSoup(html, "html.parser")
    players = []

    tables = soup.find_all("table")
    ranking_table = None
    for table in tables:
        header = clean_text(table.get_text(" ", strip=True)).lower()
        if "player" in header and "pts" in header:
            ranking_table = table
            break

    if ranking_table is None:
        raise RuntimeError(f"Could not find {tour} ranking table")

    for row in ranking_table.find_all("tr"):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
        if len(cells) < 5:
            continue

        rank_match = re.match(r"^(\d+)", cells[0])
        if not rank_match:
            continue
        rank = int(rank_match.group(1))

        country_idx = next(
            (i for i, cell in enumerate(cells) if re.fullmatch(r"[A-Z]{3}", cell)),
            None,
        )
        if country_idx is None or country_idx < 2 or country_idx + 1 >= len(cells):
            continue

        player_name = cells[country_idx - 1]
        player_name = re.sub(r"\b(?:CH|NCH)\b", "", player_name).strip()
        player_name = re.sub(r"\s+", " ", player_name)

        # In the official ranking table, Pts is immediately after Ctry.
        points = parse_number(cells[country_idx + 1])
        if points is None:
            continue

        change = None
        if country_idx + 2 < len(cells):
            change = parse_number(cells[country_idx + 2])

        players.append(
            {
                "rank": rank,
                "player": player_name,
                "country": cells[country_idx],
                "points": points,
                "change": change,
            }
        )

    if not players:
        raise RuntimeError(f"Parsed zero players from {tour} ranking")

    ranks = [p["rank"] for p in players]
    if len(ranks) != len(set(ranks)):
        raise RuntimeError(f"Duplicate ranks detected in {tour} ranking")

    players.sort(key=lambda p: p["rank"])
    return players


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
