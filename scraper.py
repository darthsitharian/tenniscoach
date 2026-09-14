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


def parse_points(value: str):
    value = value.replace(",", "").strip()
    match = re.search(r"-?\d+", value)
    return int(match.group()) if match else None


def parse_rankings(tour: str, html: str):
    soup = BeautifulSoup(html, "html.parser")
    players = []

    # live-tennis.eu renders the ranking as an HTML table. Prefer rows from
    # tables containing the ranking headers, while remaining tolerant of
    # minor markup changes.
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
        if not cells:
            continue

        # Skip header rows.
        if any(cell.lower() in {"player", "pts", "rank", "#"} for cell in cells):
            continue

        rank_match = re.match(r"^(\d+)", cells[0])
        if not rank_match:
            continue

        rank = int(rank_match.group(1))

        # The exact column positions have changed slightly over time, so
        # identify the player/country/points fields heuristically.
        points_idx = None
        for i, cell in enumerate(cells):
            if re.fullmatch(r"[\d,]+", cell):
                points_idx = i
                break

        if points_idx is None:
            continue

        # Country codes are normally 3 uppercase letters.
        country = None
        country_idx = None
        for i, cell in enumerate(cells):
            if re.fullmatch(r"[A-Z]{3}", cell):
                country = cell
                country_idx = i
                break

        if country_idx is not None and country_idx > 0:
            player_name = cells[country_idx - 1]
        elif len(cells) > 1:
            player_name = cells[1]
        else:
            continue

        # Remove visual markers such as CH/NCH that can appear before names.
        player_name = re.sub(r"\b(?:CH|NCH)\b", "", player_name).strip()
        player_name = re.sub(r"\s+", " ", player_name)

        players.append(
            {
                "rank": rank,
                "player": player_name,
                "country": country,
                "points": parse_points(cells[points_idx]),
            }
        )

    if not players:
        raise RuntimeError(f"Parsed zero players from {tour} ranking")

    # Guard against a silently broken parser returning duplicate ranks.
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
