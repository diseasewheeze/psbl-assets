"""Fantasy points a player has produced since a trade, scored the DBL way from MLB game logs.

Scoring is the league's own, from automation/core/sport.py (Constitution
Article VIII): every game's hitting line with sport.hitting_points and its
pitching line with sport.pitching_points, added together, so a two-way player
gets both.

Data (read-only, MLB Stats API, through core/mlb_people.py):

  GET /people/{id}/stats?stats=gameLog&group=hitting,pitching&season=YYYY&gameType=R
      one request per player and season, both groups at once. Each game line
      has date, game.gamePk, team, opponent and the stats the scoring reads
      (checked against live responses on 2026-10-15).

Only MLB regular-season games count (Fantrax scores no postseason games), and
every game counts no matter which DBL team rosters the player afterwards.
Players are matched to MLB ids by name, narrowed by MLB team and by pitcher or
hitter (mlb_people.find_person); an ambiguous name is left unmatched rather
than guessed.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

AUTOMATION = Path(__file__).resolve().parents[1]
if str(AUTOMATION) not in sys.path:
    sys.path.insert(0, str(AUTOMATION))

from core import mlb_people as mp  # noqa: E402
from core import sport  # noqa: E402

OUT_OF_TIME = "not read in time"
hitting_points = sport.hitting_points
pitching_points = sport.pitching_points


def line_points(line: mp.GameLine) -> float:
    """DBL fantasy points for one game line (hitting or pitching)."""
    return pitching_points(line.stat) if line.group == "pitching" else hitting_points(line.stat)


def seasons_between(first: date, last: date) -> list[int]:
    """MLB seasons are calendar years."""
    return list(range(first.year, last.year + 1))


@dataclass
class Production:
    """One player's DBL points from MLB games after the trade."""
    mlb_id: int | None
    points: float = 0.0
    games: int = 0
    pitcher: bool = False         # pitched in at least one of those games
    error: str = ""               # set when the MLB data couldn't be read at all
    by_game: list[tuple[str, float]] = field(default_factory=list)


class MlbStats:
    """MLB reads with one shared client (tests pass a fake fetch).

    ``stop_at`` (a ``clock`` reading) is the run's time budget for MLB reads:
    once it passes, no further request is made and the player in progress gets
    the OUT_OF_TIME error, so a slow API can't run a job past its timeout.
    """

    def __init__(self, api: mp.MlbApi | None = None) -> None:
        self.api = api or mp.MlbApi()
        self.stop_at: float | None = None
        self.clock: Callable[[], float] = time.monotonic

    def out_of_time(self) -> bool:
        return self.stop_at is not None and self.clock() >= self.stop_at

    def find_id(self, name: str, team: str = "", position: str = "") -> int | None:
        """MLB person id for a Fantrax player ("Last, First", MLB team, positions), or None if unsure."""
        found = mp.find_person(self.api, name, team, position)
        return found.person.id if found.person else None

    def production(self, mlb_id: int | None, after: date, through: date) -> Production:
        """Points from MLB regular-season games played after ``after`` (the trade date) through ``through``."""
        out = Production(mlb_id)
        if mlb_id is None:
            out.error = "not matched to an MLB player"
            return out
        lines: list[mp.GameLine] = []
        for season in seasons_between(after, through):
            if self.out_of_time():
                out.error = OUT_OF_TIME
                return out
            try:
                lines += self.api.game_log(mlb_id, season)
            except Exception as exc:  # noqa: BLE001 - reported per player
                out.error = f"MLB game log unavailable ({exc.__class__.__name__})"
                return out
        games: dict[tuple[date, int], float] = {}
        for line in lines:
            if not (after < line.date <= through):
                continue
            key = (line.date, line.game_pk)
            games[key] = games.get(key, 0.0) + line_points(line)
            out.pitcher = out.pitcher or line.group == "pitching"
        for (day, _), pts in sorted(games.items()):
            out.by_game.append((day.isoformat(), round(pts, 2)))
        out.games = len(games)
        out.points = round(sum(games.values()), 2)
        return out
