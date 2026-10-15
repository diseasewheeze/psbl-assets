"""Season bounties: one-time goals, each claimed by the first franchise to get there.

Configured in automation/league.yaml under competition.bounties. Each bounty:

  id           unique key, kept in the saved state (do not rename mid-season)
  title        short name shown in Discord
  description  one line on what it takes
  type         one of TYPES below
  threshold    the number to reach
  reward       recognition only (default: the 🎯 Bounty Hunter role for the
               Season). Anything that mentions FAAB, picks, the draft, dues or
               money is rejected: bounties never carry a competitive reward.

Types (regular-season weeks only; weeks where nobody scored are ignored):

  team_season_points  first franchise whose season points reach ``threshold``
                      (if several cross in the same week, the higher total)
  team_week_points    first single-week score of at least ``threshold``
                      (the highest that week if several; periods longer than
                      one calendar week do not count)
  team_win_streak     first franchise to win ``threshold`` head-to-head
                      matchups in a row (a tie ends a streak; if several get
                      there the same week, the higher score that week)
  player_multi_homer  first MLB regular-season game in which a player on a
                      DBL roster hits ``threshold`` home runs (2 = a
                      multi-homer game). Read from the MLB schedule's scoring
                      plays day by day, the morning after; the franchise that
                      rosters the player at that check gets the credit.
                      Skipped quietly when Fantrax or MLB cannot be read.

An exact tie on the deciding figure is shared. Claims are saved in the
Competition Desk state, so each bounty is announced once per Season (the
season rollover clears that state).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from core import mlb, season
from monthly import last_night
from weekly import latest_names, real_matchups, real_weeks, teams

TEAM_SEASON_POINTS = "team_season_points"
TEAM_WEEK_POINTS = "team_week_points"
TEAM_WIN_STREAK = "team_win_streak"
PLAYER_MULTI_HOMER = "player_multi_homer"
TYPES = (TEAM_SEASON_POINTS, TEAM_WEEK_POINTS, TEAM_WIN_STREAK, PLAYER_MULTI_HOMER)
TEAM_TYPES = (TEAM_SEASON_POINTS, TEAM_WEEK_POINTS, TEAM_WIN_STREAK)

DEFAULT_REWARD = "🎯 Bounty Hunter role for the Season"
NOT_COSMETIC = re.compile(r"faab|\$|\bpicks?\b|\bdraft|\bcash\b|\bmoney\b|\bdues\b|\bwaiver|\bbudget\b|\broster spot", re.I)
# MLB schedule requests per run at most (one per day). Each run normally has
# one new day to check; this only limits catching up after an outage.
MAX_NIGHTS_PER_RUN = 7
EPSILON = 1e-9


@dataclass(frozen=True)
class Bounty:
    id: str
    title: str
    description: str
    type: str
    threshold: float
    reward: str = DEFAULT_REWARD


def load_bounties(comp: dict[str, Any]) -> tuple[list[Bounty], list[str]]:
    """Valid bounties from competition.bounties, plus a message per rejected one."""
    raw = comp.get("bounties") or []
    if not isinstance(raw, list):
        return [], ["competition.bounties must be a list"]
    found: list[Bounty] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            errors.append(f"bounty {index}: not a mapping")
            continue
        bounty_id = str(item.get("id") or "").strip()
        label = bounty_id or f"bounty {index}"
        kind = str(item.get("type") or "").strip()
        reward = str(item.get("reward") or DEFAULT_REWARD).strip()
        try:
            threshold = float(item.get("threshold"))
        except (TypeError, ValueError):
            threshold = 0.0
        if not bounty_id or bounty_id in seen:
            errors.append(f"{label}: id missing or duplicated")
        elif kind not in TYPES:
            errors.append(f"{label}: unknown type {kind!r} (use one of {', '.join(TYPES)})")
        elif threshold <= 0:
            errors.append(f"{label}: threshold must be a positive number")
        elif not str(item.get("title") or "").strip():
            errors.append(f"{label}: title is required")
        elif NOT_COSMETIC.search(reward):
            errors.append(f"{label}: rewards are recognition only (no FAAB, picks, draft, dues or money)")
        else:
            seen.add(bounty_id)
            found.append(Bounty(bounty_id, str(item["title"]).strip(), str(item.get("description") or "").strip(),
                                kind, threshold, reward))
    return found, errors


@dataclass
class Claim:
    bounty_id: str
    teams: list[dict[str, str]]  # [{"teamId", "teamName"}]; more than one = shared
    detail: str
    week: int = 0
    night: str = ""              # player_multi_homer: the MLB game date (YYYY-MM-DD)
    claimed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Any) -> "Claim | None":
        if not isinstance(raw, dict) or not raw.get("bounty_id"):
            return None
        return cls(
            bounty_id=str(raw["bounty_id"]),
            teams=[t for t in raw.get("teams") or [] if isinstance(t, dict)],
            detail=str(raw.get("detail") or ""),
            week=int(raw.get("week") or 0),
            night=str(raw.get("night") or ""),
            claimed_at=str(raw.get("claimed_at") or ""),
        )


def fmt_number(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


def _top(scores: dict[str, float]) -> list[str]:
    """Team IDs with the highest figure (several when exactly tied)."""
    high = max(scores.values())
    return sorted(tid for tid, v in scores.items() if abs(v - high) < EPSILON)


def _claim(bounty: Bounty, team_ids: list[str], names: dict[str, str], detail: str, week: int) -> Claim:
    return Claim(bounty.id, [{"teamId": t, "teamName": names.get(t, "Unknown Team")} for t in team_ids],
                 detail, week)


# --- Team bounties (Fantrax matchup scores) ------------------------------------

def team_claims(
    bounties: list[Bounty],
    weeks: dict[int, list[dict]],
    long_weeks: set[int] | frozenset[int] = frozenset(),
) -> dict[str, Claim]:
    """The first claim of every team bounty in ``weeks`` (week number -> matchups)."""
    played = real_weeks(weeks)
    names = latest_names(played)
    claims: dict[str, Claim] = {}
    for bounty in bounties:
        if bounty.type == TEAM_SEASON_POINTS:
            claim = _season_points(bounty, played, names)
        elif bounty.type == TEAM_WEEK_POINTS:
            claim = _week_points(bounty, played, names, long_weeks)
        elif bounty.type == TEAM_WIN_STREAK:
            claim = _win_streak(bounty, played, names)
        else:
            continue
        if claim:
            claims[bounty.id] = claim
    return claims


def _season_points(bounty: Bounty, played: dict[int, list[dict]], names: dict[str, str]) -> Claim | None:
    total: dict[str, float] = {}
    for number, rows in played.items():
        for t in teams(rows):
            total[t["teamId"]] = total.get(t["teamId"], 0.0) + t["score"]
        crossed = {tid: v for tid, v in total.items() if v >= bounty.threshold - EPSILON}
        if crossed:
            winners = _top(crossed)
            return _claim(bounty, winners, names, f"{crossed[winners[0]]:.2f} season points after Week {number}", number)
    return None


def _week_points(bounty: Bounty, played: dict[int, list[dict]], names: dict[str, str],
                 long_weeks: set[int] | frozenset[int]) -> Claim | None:
    for number, rows in played.items():
        if number in long_weeks:
            continue
        crossed = {t["teamId"]: t["score"] for t in teams(rows) if t["score"] >= bounty.threshold - EPSILON}
        if crossed:
            winners = _top(crossed)
            return _claim(bounty, winners, names, f"{crossed[winners[0]]:.2f} points in Week {number}", number)
    return None


def _streaks(played: dict[int, list[dict]], until: int | None = None) -> tuple[dict[str, int], dict[str, float]]:
    """Each team's current win streak after each week, and that week's scores."""
    streak: dict[str, int] = {}
    scores: dict[str, float] = {}
    for number, rows in played.items():
        if until is not None and number > until:
            break
        scores = {}
        for row in real_matchups(rows):
            away, home = row["away"], row["home"]
            for me, them in ((away, home), (home, away)):
                scores[me["teamId"]] = me["score"]
                streak[me["teamId"]] = streak.get(me["teamId"], 0) + 1 if me["score"] > them["score"] else 0
    return streak, scores


def _win_streak(bounty: Bounty, played: dict[int, list[dict]], names: dict[str, str]) -> Claim | None:
    need = int(round(bounty.threshold))
    for number in played:
        streak, scores = _streaks(played, until=number)
        reached = {tid: scores.get(tid, 0.0) for tid, n in streak.items() if n >= need}
        if reached:
            winners = _top(reached)
            return _claim(bounty, winners, names, f"{need} straight wins through Week {number}", number)
    return None


def progress(bounty: Bounty, weeks: dict[int, list[dict]], long_weeks: set[int] | frozenset[int] = frozenset()) -> str:
    """Where an open team bounty stands ("" when there is nothing to show)."""
    played = real_weeks(weeks)
    if not played or bounty.type not in TEAM_TYPES:
        return ""
    names = latest_names(played)

    def who(ids: list[str]) -> str:
        return " and ".join(f"**{names.get(t, 'Unknown Team')}**" for t in ids)

    if bounty.type == TEAM_SEASON_POINTS:
        total: dict[str, float] = {}
        for rows in played.values():
            for t in teams(rows):
                total[t["teamId"]] = total.get(t["teamId"], 0.0) + t["score"]
        leaders = _top(total)
        return f"Leader: {who(leaders)} — {total[leaders[0]]:.2f} of {fmt_number(bounty.threshold)}"
    if bounty.type == TEAM_WEEK_POINTS:
        best: dict[str, tuple[float, int]] = {}
        for number, rows in played.items():
            if number in long_weeks:
                continue
            for t in teams(rows):
                if t["score"] > best.get(t["teamId"], (-1.0, 0))[0]:
                    best[t["teamId"]] = (t["score"], number)
        if not best:
            return ""
        leaders = _top({tid: v[0] for tid, v in best.items()})
        score, number = best[leaders[0]]
        return f"Best so far: {who(leaders)} — {score:.2f} in Week {number}"
    streak, _ = _streaks(played)
    longest = max(streak.values(), default=0)
    if longest <= 0:
        return "Longest active streak: none"
    leaders = sorted(t for t, n in streak.items() if n == longest)
    return f"Longest active streak: {who(leaders)} — {longest}"


# --- Multi-homer game (MLB scoring plays) ---------------------------------------------

def regular_season_nights(info: dict[str, Any], tz: ZoneInfo, last_regular: int) -> tuple[date, date] | None:
    """First and last MLB game day inside the DBL regular season (local dates).

    The last night is the final regular-season week's ``monthly.last_night``.
    """
    weeks = [p for p in season.periods(info) if p.number <= last_regular]
    if not weeks:
        return None
    return weeks[0].start.astimezone(tz).date(), last_night(weeks[-1], tz)


def nights_to_check(
    info: dict[str, Any],
    tz: ZoneInfo,
    now: datetime,
    last_regular: int,
    through: str | None,
    limit: int = MAX_NIGHTS_PER_RUN,
) -> list[date]:
    """Finished regular-season game days after ``through`` (YYYY-MM-DD), oldest first."""
    span = regular_season_nights(info, tz, last_regular)
    if not span:
        return []
    first, last = span
    start = first
    if through:
        try:
            start = max(first, date.fromisoformat(through) + timedelta(days=1))
        except ValueError:
            pass
    end = min(last, now.astimezone(tz).date() - timedelta(days=1))
    nights: list[date] = []
    day = start
    while day <= end and len(nights) < limit:
        nights.append(day)
        day += timedelta(days=1)
    return nights


def _day(d: date) -> str:
    return f"{d:%a} {d:%b} {d.day}"


@dataclass
class FeatCheck:
    claim: Claim | None = None
    checked_through: date | None = None   # last day fully checked
    notes: list[str] = field(default_factory=list)


def find_multi_homer(
    bounty: Bounty,
    nights: list[date],
    fetch: Callable[[date], Any],
    owner_of: Callable[[str, str], tuple[str, str] | None],
) -> FeatCheck:
    """Check days in order for the bounty's first multi-homer game.

    ``fetch(day)`` returns the raw MLB schedule for that day with its scoring
    plays (mlb.SCORES); ``owner_of(name, club)`` returns (teamId, teamName) of
    the DBL franchise that rosters that player, or None (not rostered or
    ambiguous). Stops at a day that cannot be read or still has a game in
    progress, so that day is checked again on the next run. A suspended game
    does not hold the check up: its home runs count once it is completed.
    """
    result = FeatCheck()
    need = int(round(bounty.threshold))
    for night in nights:
        try:
            games = mlb.parse_schedule(fetch(night))
        except Exception as exc:  # network, HTTP or shape problems: try again next run
            result.notes.append(f"MLB scores for {night.isoformat()} could not be read: {exc}")
            return result
        regular = [g for g in mlb.regular_season(games) if g.day == night]
        if any(g.live for g in regular):
            result.notes.append(f"MLB games on {night.isoformat()} are still in progress")
            return result
        found = []
        for game in regular:
            if not game.final:
                continue
            for multi in mlb.multi_homer_games(game, need):
                owner = owner_of(multi.batter.name, multi.team)
                if owner:
                    start = game.start.timestamp() if game.start else float("inf")
                    found.append((start, game.game_number, multi.order, multi, owner))
        result.checked_through = night
        if found:
            _, _, _, multi, (team_id, team_name) = min(found, key=lambda x: x[:3])
            runs = "home run" if multi.homers == 1 else "home runs"
            detail = (f"{multi.batter.name} ({multi.team}): {multi.homers} {runs} against "
                      f"{multi.game.opponent(multi.team)} on {_day(night)}")
            result.claim = Claim(bounty.id, [{"teamId": team_id, "teamName": team_name}], detail,
                                 night=night.isoformat())
            return result
    return result
