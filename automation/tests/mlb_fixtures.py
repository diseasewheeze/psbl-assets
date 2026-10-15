"""Shared offline MLB and MLB-shaped Fantrax test data (not a test module).

- SCHEDULE: mlb_schedule_2027-04_synthetic.json, Week 3 of a made-up 2027 season
  (see its _note). ``schedule_get`` answers a schedule URL from it like the MLB
  Stats API would: only the dates asked for, and only the hydrations asked for.
- CONTENT: mlb_content_2027-04-13_synthetic.json; ``content_get`` answers
  /game/{gamePk}/content (an empty content object for games it does not list).
- MLB_INFO, ROSTERS, PLAYERS, SCORES: MLB-shaped variants of the live Fantrax
  captures from the hockey test league. Fantrax's real MLB shapes must be
  checked with tools/fantrax_probe.py once the MLB league exists.
"""

from __future__ import annotations

import copy
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ET = ZoneInfo("America/New_York")


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


SCHEDULE = _load("mlb_schedule_2027-04_synthetic.json")
CONTENT = _load("mlb_content_2027-04-13_synthetic.json")["responses"]
MLB_INFO = _load("fantrax_league_info_mlb_synthetic.json")
ROSTERS = _load("fantrax_rosters_mlb_synthetic.json")["response"]
PLAYERS = _load("fantrax_player_ids_mlb_synthetic.json")["players"]
SCORES = _load("fantrax_matchup_scores_mlb_synthetic.json")["response"]

MON, TUE, WED, THU, FRI, SAT, SUN = (date(2027, 4, 12 + i) for i in range(7))
EMPTY_CONTENT = {"copyright": SCHEDULE["copyright"], "editorial": {}, "media": {}}


def et(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET).astimezone(timezone.utc)


def _strip(game: dict, hydrate: str) -> dict:
    asked = {part.strip().lower() for part in hydrate.split(",") if part.strip()}
    game = copy.deepcopy(game)
    if "probablepitcher" not in asked:
        for side in game.get("teams", {}).values():
            side.pop("probablePitcher", None)
    for key, name in (("linescore", "linescore"), ("decisions", "decisions"), ("scoringPlays", "scoringplays")):
        if name not in asked:
            game.pop(key, None)
    return game


def schedule_response(url: str, master: dict | None = None) -> dict:
    """The schedule response for ``url`` (startDate/endDate or date; hydrate)."""
    parsed = urlparse(url)
    assert parsed.netloc == "statsapi.mlb.com" and parsed.path == "/api/v1/schedule", url
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert query.get("sportId") == "1", url
    first = query.get("startDate") or query["date"]
    last = query.get("endDate") or query["date"]
    hydrate = query.get("hydrate", "")
    blocks = []
    for block in (master or SCHEDULE)["dates"]:
        if first <= block["date"] <= last:
            blocks.append({**block, "games": [_strip(g, hydrate) for g in block["games"]]})
    total = sum(len(b["games"]) for b in blocks)
    return {"copyright": SCHEDULE["copyright"], "totalItems": total, "totalEvents": 0, "totalGames": total,
            "totalGamesInProgress": 0, "dates": blocks}


def schedule_get(url: str) -> dict:
    return schedule_response(url)


def content_get(url: str) -> dict:
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    assert parsed.netloc == "statsapi.mlb.com" and parts[:3] == ["api", "v1", "game"] and parts[4] == "content", url
    return copy.deepcopy(CONTENT.get(parts[3], EMPTY_CONTENT))


def recording(get: Callable[[str], Any]) -> tuple[Callable[[str], Any], list[str]]:
    """A getter that also records every URL it was asked for."""
    calls: list[str] = []

    def wrapped(url: str) -> Any:
        calls.append(url)
        return get(url)

    return wrapped, calls


def edited_schedule(change: Callable[[dict], None]) -> dict:
    """A copy of SCHEDULE with ``change(game)`` applied to every game."""
    master = copy.deepcopy(SCHEDULE)
    for block in master["dates"]:
        for game in block["games"]:
            change(game)
    return master


def find_game(day: date, away: str, home: str, number: int = 1, master: dict | None = None) -> dict:
    """The raw fixture game listed on ``day`` (team abbreviations as MLB writes them)."""
    from core.mlb import TEAMS

    names = {code: name for code, name in TEAMS.values()}
    for block in (master or SCHEDULE)["dates"]:
        if block["date"] != day.isoformat():
            continue
        for game in block["games"]:
            if (game["teams"]["away"]["team"]["name"], game["teams"]["home"]["team"]["name"], game["gameNumber"]) == \
                    (names[away], names[home], number):
                return game
    raise KeyError((day, away, home, number))


def player_ids() -> dict:
    return copy.deepcopy(PLAYERS)


def rosters() -> dict:
    return copy.deepcopy(ROSTERS)
