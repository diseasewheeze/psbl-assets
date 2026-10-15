"""Schedule edge for the Monday matchup preview: projected games per franchise.

For every MLB game day in a Fantrax week, each franchise's lineup is filled
from its rostered players whose MLB club plays that day:

  - hitter slots: the league lineup (automation/core/sport.py: LINEUP and
    HITTER_SLOTS, 1 C, 1 1B, 1 2B, 1 3B, 1 SS, 3 OF, 2 UTIL), each taking a
    player whose positions it accepts (sport.SLOT_ACCEPTS);
  - who counts: players on the ACTIVE or RESERVE part of the roster. MINORS
    and IR players are left out;
  - positions: the player's Fantrax positions (getPlayerIds, comma-separated
    when he has more than one) plus his roster slot;
  - hitter slots are filled as fully as possible, and a club's doubleheader
    counts twice, so players with two games that day are placed first (a
    maximum matching; placing the most games first gives the most games);
  - starting pitchers: a start counts when MLB has announced the pitcher as
    his club's probable starter that day (matched by name and club; usually
    known only a few days ahead), at most the SP slots a day, and the week's
    total is capped at the credited starts: sport.PITCHER_STARTS_PER_WEEK per
    calendar week, so 14 for the two-week Championship (Article IX);
  - relief pitchers are left out: their appearances cannot be known ahead.

Projected games = hitter games + probable starts. Light-day games = the same
count on light days only (days when few MLB clubs play, as in the MLB games
grid). This is the most a manager could start with the current roster; it
says nothing about how good the players are.

A player whose MLB club is missing or unknown adds nothing. All inputs are
read-only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from core import mlb, sport

LINEUP = ("ACTIVE", "RESERVE")
SP_SLOTS = sport.LINEUP.get("SP", 0)
# Fantrax may write the utility slot "UT" or "Util"; the rules call it UTIL.
SLOT_NAMES = {"UT": "UTIL", "UTIL": "UTIL", "UTILITY": "UTIL"}


def positions_of(*values: Any) -> frozenset[str]:
    """Every position named in Fantrax position strings ("1B,OF", "SS/2B")."""
    found: set[str] = set()
    for value in values:
        for part in re.split(r"[,/ ]+", str(value or "").upper()):
            if part:
                found.add(SLOT_NAMES.get(part, part))
    return frozenset(found)


@dataclass(frozen=True)
class RosterPlayer:
    player_id: str
    name: str            # mlb.name_key form
    team: str            # MLB club (mlb.team_code)
    positions: frozenset[str]

    @property
    def starter(self) -> bool:
        return "SP" in self.positions

    def hitter_slots(self) -> set[str]:
        return {slot for slot in sport.HITTER_SLOTS if sport.slot_fits(slot, self.positions)}


def lineup_players(rosters: Any, players: Any) -> dict[str, list[RosterPlayer]] | None:
    """teamId -> players who can be in a lineup this week; None when every roster is empty."""
    block = rosters.get("rosters") if isinstance(rosters, dict) else None
    if not isinstance(block, dict) or not block:
        return None
    directory: dict[str, dict[str, Any]] = {}
    for key, raw in (players or {}).items() if isinstance(players, dict) else []:
        if isinstance(raw, dict):
            directory[str(key)] = raw
            if raw.get("fantraxId"):
                directory[str(raw["fantraxId"])] = raw
    teams: dict[str, list[RosterPlayer]] = {}
    any_items = False
    for team_id, team in block.items():
        if not isinstance(team, dict):
            continue
        squad: list[RosterPlayer] = []
        for item in team.get("rosterItems") or []:
            if not isinstance(item, dict):
                continue
            any_items = True
            if str(item.get("status") or "").upper() not in LINEUP:
                continue
            player_id = str(item.get("id") or "")
            info = directory.get(player_id) or {}
            positions = positions_of(info.get("position"), item.get("position"))
            club = mlb.team_code(info.get("team"))
            if positions and club:
                squad.append(RosterPlayer(player_id, mlb.name_key(info.get("name")), club, positions))
        teams[str(team_id)] = squad
    return teams if any_items else None


def max_hitter_games(eligible: list[tuple[set[str], int]]) -> int:
    """Most hitter games one day's lineup can hold.

    ``eligible`` lists, per player, the hitter slots he may fill and his games
    that day (2 in a doubleheader). Players are placed most games first, each
    by an augmenting path that may move an already-placed player to another of
    his slots; that order gives the most games, not just the most players.
    """
    seats = [slot for slot in sport.HITTER_SLOTS for _ in range(sport.LINEUP.get(slot, 0))]
    holder = [-1] * len(seats)

    def place(player: int, tried: set[int]) -> bool:
        for seat, slot in enumerate(seats):
            if seat in tried or slot not in eligible[player][0]:
                continue
            tried.add(seat)
            if holder[seat] == -1 or place(holder[seat], tried):
                holder[seat] = player
                return True
        return False

    order = sorted(range(len(eligible)), key=lambda i: (-eligible[i][1], len(eligible[i][0])))
    return sum(eligible[i][1] for i in order if eligible[i][0] and place(i, set()))


def days_in_period(games: list[mlb.Game], start: datetime, end: datetime,
                   tz: ZoneInfo) -> dict[date, dict[str, list[mlb.Game]]]:
    """Day -> club -> its regular-season games that day, for the period."""
    days: dict[date, dict[str, list[mlb.Game]]] = {}
    for game in mlb.regular_season(games):
        if game.played and mlb.in_period(game, start, end, tz):
            for team in game.teams:
                days.setdefault(game.day, {}).setdefault(team, []).append(game)
    return dict(sorted(days.items()))


@dataclass(frozen=True)
class Projection:
    games: int
    light_games: int
    hitter_games: int
    starts: int


def starts_on(pitcher: RosterPlayer, games: list[mlb.Game]) -> int:
    """His announced starts among one day's games for his club."""
    return sum(1 for g in games if (p := g.probable(pitcher.team)) is not None and mlb.name_key(p.name) == pitcher.name)


def project(
    squad: list[RosterPlayer],
    days: dict[date, dict[str, list[mlb.Game]]],
    light_days: set[date],
    start_cap: int,
) -> Projection:
    hitters = [p for p in squad if p.hitter_slots()]
    pitchers = [p for p in squad if p.starter]
    hitter_games = starts = light_hitters = light_starts = 0
    for day, playing in days.items():
        filled = max_hitter_games([(p.hitter_slots(), len(playing[p.team])) for p in hitters if p.team in playing])
        started = min(SP_SLOTS, sum(starts_on(p, playing[p.team]) for p in pitchers if p.team in playing))
        hitter_games += filled
        starts += started
        if day in light_days:
            light_hitters += filled
            light_starts += started
    credited = min(starts, start_cap)
    return Projection(
        games=hitter_games + credited,
        light_games=light_hitters + min(light_starts, start_cap),
        hitter_games=hitter_games,
        starts=credited,
    )


def projections(
    teams: dict[str, list[RosterPlayer]],
    games: list[mlb.Game],
    start: datetime,
    end: datetime,
    tz: ZoneInfo,
    *,
    start_cap: int,
    light_max: int = mlb.LIGHT_DAY_MAX_TEAMS,
) -> dict[str, Projection]:
    """teamId -> Projection for the period start..end (empty when no MLB games)."""
    days = days_in_period(games, start, end, tz)
    if not days:
        return {}
    light = {day for day, playing in days.items() if len(playing) <= light_max}
    return {team_id: project(squad, days, light, start_cap) for team_id, squad in teams.items()}
