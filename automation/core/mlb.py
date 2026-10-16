"""MLB Stats API reader (read-only): schedule, probable pitchers, final scores, game content.

Every MLB fact the automations use comes through here: which teams play on a
day (doubleheaders, postponements), who is the probable starter, final scores
with their linescore, decisions and scoring plays, and the video links for a
game (recap, condensed game, per-play clips).

Endpoints (no key needed):

  schedule  GET https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=D&endDate=D
            [&hydrate=probablePitcher | linescore,decisions,scoringplays]
  content   GET https://statsapi.mlb.com/api/v1/game/{gamePk}/content

CHECKED LIVE (October 2026, against 2026 regular-season and postseason games):

- schedule: top level ``dates`` (empty list on a day without games), each
  ``{date, games, ...}``. A game has ``gamePk`` (int), ``gameType`` ("R"
  regular season, "S" spring, "F"/"D"/"L"/"W" postseason), ``gameDate`` (UTC,
  e.g. 2026-09-27T01:40:00Z), ``officialDate``, ``status`` {abstractGameState
  Preview/Live/Final, codedGameState, detailedState, statusCode, startTimeTBD,
  reason}, ``teams.away/home`` {team{id, name}, score, isWinner,
  probablePitcher{id, fullName}}, ``doubleHeader`` ("N"; "Y" traditional; "S"
  split), ``gameNumber``, ``scheduledInnings``. A late West Coast game is listed
  under its local date even though its gameDate is the next day in UTC.
- A postponed game keeps its gamePk. It is listed on the original date with
  codedGameState "D" ("Postponed", reason e.g. "Inclement Weather"),
  ``rescheduleGameDate`` and an ``officialDate`` that already shows the makeup
  date, and listed again on the makeup date (usually as a split doubleheader,
  ``rescheduledFromDate``). So a game here is one listing: (gamePk, the date it
  is listed under), and the listing's own day comes from its ``dates`` block.
- A game called early is final with codedGameState "F" and detailedState
  "Completed Early" (reason "Rain"); its linescore has fewer innings.
- hydrate=linescore,decisions,scoringplays adds ``linescore`` {currentInning,
  scheduledInnings, innings[], teams{away, home}{runs, hits, errors}},
  ``decisions`` {winner, loser, save: {id, fullName}} (save missing when there
  was none) and ``scoringPlays`` [{result{event "Home Run", rbi, ...},
  about{halfInning "top"/"bottom", inning}, matchup{batter{id, fullName},
  pitcher}}]. Every home run is a scoring play.
- content: ``editorial.recap.mlb`` {headline, slug} (an MLB.com story; the page
  is https://www.mlb.com/news/{slug}); ``media.epgAlternate`` groups, the
  "Extended Highlights" group holding the condensed game {slug
  "condensed-game-...", playbacks[{name "mp4Avc", url}]} (page
  https://www.mlb.com/video/{slug}); ``highlights.highlights.items``, one
  video per play, each with ``keywordsAll`` entries {type, value} of type
  "taxonomy" (e.g. "home-run", "condensed-game", "game-recap"), "player_id"
  and "team_id". A home-run clip names its batter by player_id.
- The full content of a finished game is larger than the inspection tool could
  show, so the highlights items were checked in the same shape through the
  schedule's content hydration and on a game before first pitch.

NOT CHECKED LIVE: suspended games (codedGameState "T"/"U") and how their
resumption is listed, and the content of games in the first hours after they
end. The parsers are tolerant: anything missing is skipped, never guessed.

Tests use the hand-built fixtures automation/tests/fixtures/mlb_*_synthetic.json,
written in the shapes above.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

BASE = "https://statsapi.mlb.com/api/v1"
SCHEDULE_URL = BASE + "/schedule"
CONTENT_URL = BASE + "/game/{game_pk}/content"
MLB_SITE = "https://www.mlb.com"
USER_AGENT = "PSBL-Automation/2.0 (+https://github.com/diseasewheeze/psbl-assets)"

# Schedule hydrations.
PROBABLES = "probablePitcher"
SCORES = "linescore,decisions,scoringplays"

REGULAR_SEASON = "R"
POSTSEASON = frozenset({"F", "D", "L", "W"})

# Weekly grid defaults (league.yaml competition.light_day_max_teams /
# heavy_day_min_teams): about 15 games a day means 30 teams on a full slate.
LIGHT_DAY_MAX_TEAMS = 20
HEAVY_DAY_MIN_TEAMS = 30

# The 30 clubs: MLB team id -> (abbreviation, name). Checked live against
# /api/v1/teams?sportId=1&season=2026.
TEAMS: dict[int, tuple[str, str]] = {
    108: ("LAA", "Los Angeles Angels"), 109: ("AZ", "Arizona Diamondbacks"),
    110: ("BAL", "Baltimore Orioles"), 111: ("BOS", "Boston Red Sox"),
    112: ("CHC", "Chicago Cubs"), 113: ("CIN", "Cincinnati Reds"),
    114: ("CLE", "Cleveland Guardians"), 115: ("COL", "Colorado Rockies"),
    116: ("DET", "Detroit Tigers"), 117: ("HOU", "Houston Astros"),
    118: ("KC", "Kansas City Royals"), 119: ("LAD", "Los Angeles Dodgers"),
    120: ("WSH", "Washington Nationals"), 121: ("NYM", "New York Mets"),
    133: ("ATH", "Athletics"), 134: ("PIT", "Pittsburgh Pirates"),
    135: ("SD", "San Diego Padres"), 136: ("SEA", "Seattle Mariners"),
    137: ("SF", "San Francisco Giants"), 138: ("STL", "St. Louis Cardinals"),
    139: ("TB", "Tampa Bay Rays"), 140: ("TEX", "Texas Rangers"),
    141: ("TOR", "Toronto Blue Jays"), 142: ("MIN", "Minnesota Twins"),
    143: ("PHI", "Philadelphia Phillies"), 144: ("ATL", "Atlanta Braves"),
    145: ("CWS", "Chicago White Sox"), 146: ("MIA", "Miami Marlins"),
    147: ("NYY", "New York Yankees"), 158: ("MIL", "Milwaukee Brewers"),
}
CODES = frozenset(code for code, _ in TEAMS.values())
_BY_NAME = {name.lower(): code for code, name in TEAMS.values()}
# Other spellings of the same clubs: MLB's own teamCode/fileCode values (checked
# live) and common fantasy-site codes. All 30 of Fantrax's MLB team codes
# (getPlayerIds, October 2026) are MLB codes or listed here (CHW, ARI).
ALIASES = {
    "ARI": "AZ", "ANA": "LAA", "CHW": "CWS", "CHA": "CWS", "CHN": "CHC", "KCA": "KC", "KCR": "KC",
    "LA": "LAD", "LAN": "LAD", "NYA": "NYY", "NYN": "NYM", "OAK": "ATH", "SAC": "ATH", "SDN": "SD",
    "SDP": "SD", "SFN": "SF", "SFG": "SF", "SLN": "STL", "TBA": "TB", "TBR": "TB", "WAS": "WSH",
    "WSN": "WSH",
}


def team_code(value: Any) -> str:
    """The club's abbreviation (as MLB writes it) from any known spelling, else ""."""
    text = str(value or "").strip()
    upper = text.upper()
    if upper in CODES:
        return upper
    if upper in ALIASES:
        return ALIASES[upper]
    return _BY_NAME.get(text.lower(), "")


def normalize_directory(players: Any) -> dict[str, Any]:
    """A copy of Fantrax's getPlayerIds with each player's club written as MLB
    writes it ("" when unknown), so matching a player by name and club works
    whichever spelling Fantrax uses."""
    out: dict[str, Any] = {}
    for key, raw in (players or {}).items() if isinstance(players, dict) else []:
        if isinstance(raw, dict):
            out[key] = {**raw, "team": team_code(raw.get("team"))}
    return out


def _team(raw: Any) -> tuple[str, str]:
    """(code, name) of a schedule team object; code "" when the club is unknown."""
    team = raw.get("team") if isinstance(raw, dict) else None
    team = team if isinstance(team, dict) else {}
    try:
        code, name = TEAMS[int(team.get("id"))]
        return code, name
    except (TypeError, ValueError, KeyError):
        name = str(team.get("name") or "")
        return team_code(name), name


# --- Parsed shapes ------------------------------------------------------------

@dataclass(frozen=True)
class Person:
    player_id: int
    name: str  # "First Last"


@dataclass(frozen=True)
class Play:
    event: str     # "Home Run", "Single", ...
    batter: Person
    team: str      # the batter's club
    inning: int
    half: str      # "top" / "bottom"


@dataclass(frozen=True)
class Game:
    game_pk: int
    day: date                 # the date MLB lists this game under (local to the ballpark)
    start: datetime | None    # first pitch, UTC; None when MLB lists the time as TBD
    away: str
    home: str
    game_type: str = REGULAR_SEASON
    state: str = "S"          # codedGameState
    abstract: str = "Preview"  # abstractGameState: Preview, Live, Final
    detailed: str = "Scheduled"
    reason: str = ""
    double_header: str = "N"
    game_number: int = 1
    scheduled_innings: int = 9
    away_name: str = ""
    home_name: str = ""
    away_probable: Person | None = None
    home_probable: Person | None = None
    away_score: int | None = None
    home_score: int | None = None
    innings: int = 0
    winner: Person | None = None
    loser: Person | None = None
    save: Person | None = None
    plays: tuple[Play, ...] = ()
    makeup_of: date | None = None   # a makeup game: the date it was postponed from
    moved_to: date | None = None    # a postponed listing: the makeup date, when known

    @property
    def teams(self) -> tuple[str, str]:
        return self.away, self.home

    @property
    def key(self) -> tuple[int, str]:
        return self.game_pk, self.day.isoformat()

    @property
    def postponed(self) -> bool:
        return self.state == "D"

    @property
    def cancelled(self) -> bool:
        return self.state == "C"

    @property
    def played(self) -> bool:
        """Played (or still to be played) on this day: not postponed or cancelled."""
        return not (self.postponed or self.cancelled)

    @property
    def suspended(self) -> bool:
        return self.state in ("T", "U")

    @property
    def final(self) -> bool:
        return self.abstract == "Final" and self.state in ("F", "O")

    @property
    def live(self) -> bool:
        """In progress right now (a suspended game waits for another day, so it is not)."""
        return self.abstract == "Live" and not self.suspended

    @property
    def extra_innings(self) -> bool:
        return self.final and self.innings > self.scheduled_innings

    @property
    def shortened(self) -> bool:
        return self.final and 0 < self.innings < self.scheduled_innings

    def probable(self, team: str) -> Person | None:
        return self.away_probable if team == self.away else self.home_probable if team == self.home else None

    def opponent(self, team: str) -> str:
        return self.home if team == self.away else self.away

    @property
    def label(self) -> str:
        text = f"{self.away} at {self.home}"
        return text + (f" (Game {self.game_number})" if self.double_header in ("Y", "S") else "")


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _when(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _person(raw: Any) -> Person | None:
    if not isinstance(raw, dict):
        return None
    player_id, name = _int(raw.get("id")), str(raw.get("fullName") or "").strip()
    return Person(player_id, name) if player_id and name else None


def _score(side: Any) -> int | None:
    value = side.get("score") if isinstance(side, dict) else None
    return None if value is None else _int(value)


def _plays(raw: Any, away: str, home: str) -> tuple[Play, ...]:
    plays: list[Play] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        about = item.get("about") if isinstance(item.get("about"), dict) else {}
        matchup = item.get("matchup") if isinstance(item.get("matchup"), dict) else {}
        batter = _person(matchup.get("batter"))
        half = str(about.get("halfInning") or "").lower()
        if batter is None or half not in ("top", "bottom"):
            continue
        plays.append(Play(str(result.get("event") or ""), batter, away if half == "top" else home,
                          _int(about.get("inning")), half))
    return tuple(plays)


def parse_game(item: dict[str, Any], day: date) -> Game | None:
    teams = item.get("teams") if isinstance(item.get("teams"), dict) else {}
    away_raw, home_raw = teams.get("away") or {}, teams.get("home") or {}
    (away, away_name), (home, home_name) = _team(away_raw), _team(home_raw)
    game_pk = _int(item.get("gamePk"))
    if not (game_pk and away and home):
        return None
    status = item.get("status") if isinstance(item.get("status"), dict) else {}
    linescore = item.get("linescore") if isinstance(item.get("linescore"), dict) else {}
    decisions = item.get("decisions") if isinstance(item.get("decisions"), dict) else {}
    scheduled = _int(item.get("scheduledInnings") or linescore.get("scheduledInnings"), 9) or 9
    innings = max(_int(linescore.get("currentInning")), len(linescore.get("innings") or []))
    tbd = bool(status.get("startTimeTBD"))
    return Game(
        game_pk=game_pk,
        day=day,
        start=None if tbd else _when(item.get("gameDate")),
        away=away,
        home=home,
        game_type=str(item.get("gameType") or ""),
        state=str(status.get("codedGameState") or ""),
        abstract=str(status.get("abstractGameState") or ""),
        detailed=str(status.get("detailedState") or ""),
        reason=str(status.get("reason") or ""),
        double_header=str(item.get("doubleHeader") or "N"),
        game_number=_int(item.get("gameNumber"), 1) or 1,
        scheduled_innings=scheduled,
        away_name=away_name,
        home_name=home_name,
        away_probable=_person(away_raw.get("probablePitcher")),
        home_probable=_person(home_raw.get("probablePitcher")),
        away_score=_score(away_raw),
        home_score=_score(home_raw),
        innings=innings,
        winner=_person(decisions.get("winner")),
        loser=_person(decisions.get("loser")),
        save=_person(decisions.get("save")),
        plays=_plays(item.get("scoringPlays"), away, home),
        makeup_of=_date(item.get("rescheduledFromDate")),
        moved_to=_date(item.get("rescheduleGameDate")) if status.get("codedGameState") == "D" else None,
    )


def _order(game: Game) -> tuple:
    return (game.day, game.start or datetime.max.replace(tzinfo=timezone.utc), game.game_number, game.away)


def parse_schedule(raw: Any) -> list[Game]:
    """Every game listing in a schedule response, in date and start order.

    Raises ValueError when the response has no ``dates`` list (an error body or
    an API change), so it is never mistaken for a day without games.
    """
    days = raw.get("dates") if isinstance(raw, dict) else None
    if not isinstance(days, list):
        raise ValueError("MLB schedule response has no dates list (API changed?)")
    games: dict[tuple[int, str], Game] = {}
    for block in days:
        if not isinstance(block, dict):
            continue
        day = _date(block.get("date"))
        for item in block.get("games") or []:
            game = parse_game(item, day) if isinstance(item, dict) and day else None
            if game is not None:
                games[game.key] = game
    return sorted(games.values(), key=_order)


def schedule_url(first: date, last: date, hydrate: str = "") -> str:
    query = {"sportId": 1, "startDate": first.isoformat(), "endDate": last.isoformat()}
    if hydrate:
        query["hydrate"] = hydrate
    return f"{SCHEDULE_URL}?{urlencode(query, safe=',()')}"


def http_get_json(url: str) -> Any:
    import requests

    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    return response.json()


def fetch_schedule(
    first: date,
    last: date,
    get: Callable[[str], Any] | None = None,
    *,
    hydrate: str = PROBABLES,
) -> list[Game]:
    """Every MLB game listed from ``first`` through ``last`` (one request), any type."""
    return parse_schedule((get or http_get_json)(schedule_url(first, last, hydrate)))


def regular_season(games: Iterable[Game]) -> list[Game]:
    return [g for g in games if g.game_type == REGULAR_SEASON]


def in_period(game: Game, start: datetime, end: datetime, tz: ZoneInfo) -> bool:
    """Whether a game belongs to the Fantrax period running start..end (UTC).

    The game's own day decides. A period that starts or ends partway through a
    day (as the Fantrax test league's periods do, at the first game of a
    Monday) splits that day by first-pitch time. A game without a known time,
    or one that starts after midnight local time (a late West Coast game),
    goes by its day.

    Fantrax's MLB period boundaries are NOT checked yet: whole-day periods and
    periods that change at a day's first game both work here.
    """
    first, last = start.astimezone(tz).date(), end.astimezone(tz).date()
    if not first <= game.day <= last:
        return False
    if game.start is None or game.start.astimezone(tz).date() != game.day:
        return True
    if game.day == first and game.start < start:
        return False
    if game.day == last and game.start > end:
        return False
    return True


def games_on(games: Iterable[Game], day: date) -> dict[str, list[Game]]:
    """Regular-season games actually played on one day, by club, first pitch first."""
    playing: dict[str, list[Game]] = defaultdict(list)
    for game in regular_season(games):
        if game.day == day and game.played:
            for team in game.teams:
                playing[team].append(game)
    return {team: sorted(found, key=_order) for team, found in playing.items()}


def probable_starts(games: Iterable[Game]) -> dict[int, tuple[str, Person, list[Game]]]:
    """Pitcher id -> (club, pitcher, his announced starts), played games only."""
    found: dict[int, tuple[str, Person, list[Game]]] = {}
    for game in games:
        if not game.played:
            continue
        for team in game.teams:
            pitcher = game.probable(team)
            if pitcher is not None:
                found.setdefault(pitcher.player_id, (team, pitcher, []))[2].append(game)
    return found


# --- Weekly games grid --------------------------------------------------------

@dataclass
class WeekGrid:
    games_by_team: dict[str, int]
    days: list[tuple[date, int, int]]               # (day, clubs playing, games), game days in the period
    off_days: list[tuple[date, list[str]]]          # (day, clubs with no game that day)
    doubleheaders: list[tuple[date, Game]]          # the first game of each doubleheader
    postponed: list[Game]
    two_start: list[tuple[str, Person, list[date]]]  # (club, pitcher, start days)
    light_max: int = LIGHT_DAY_MAX_TEAMS
    heavy_min: int = HEAVY_DAY_MIN_TEAMS
    total_games: int = 0

    def by_count(self) -> list[tuple[int, list[str]]]:
        groups: dict[int, list[str]] = defaultdict(list)
        for team, count in self.games_by_team.items():
            groups[count].append(team)
        return [(count, sorted(groups[count])) for count in sorted(groups, reverse=True)]

    @property
    def light_days(self) -> list[tuple[date, int, int]]:
        return [d for d in self.days if d[1] <= self.light_max]

    @property
    def heavy_days(self) -> list[tuple[date, int, int]]:
        return [d for d in self.days if d[1] >= self.heavy_min]


def week_grid(
    games: list[Game],
    start: datetime,
    end: datetime,
    tz: ZoneInfo,
    *,
    light_max: int = LIGHT_DAY_MAX_TEAMS,
    heavy_min: int = HEAVY_DAY_MIN_TEAMS,
) -> WeekGrid:
    """Games per club, doubleheaders, off days, light/heavy days and two-start
    pitchers (announced probables only) for one Fantrax period.

    Every club is listed, with 0 games if it has none. Postponed and cancelled
    listings count for nothing; a makeup game counts on the day it is played.
    """
    week = [g for g in regular_season(games) if in_period(g, start, end, tz)]
    played = [g for g in week if g.played]
    counts: dict[str, int] = {team: 0 for team in CODES}
    by_day: dict[date, set[str]] = defaultdict(set)
    games_per_day: dict[date, int] = defaultdict(int)
    per_team_day: dict[tuple[str, date], list[Game]] = defaultdict(list)
    for game in played:
        games_per_day[game.day] += 1
        for team in game.teams:
            counts[team] = counts.get(team, 0) + 1
            by_day[game.day].add(team)
            per_team_day[(team, game.day)].append(game)

    first_day = start.astimezone(tz).date()
    last_day = max([g.day for g in week] + [first_day])
    days = [first_day + timedelta(days=i) for i in range((last_day - first_day).days + 1)]
    off = [(day, sorted(CODES - by_day.get(day, set()))) for day in days]
    seen: set[tuple[date, frozenset[str]]] = set()
    doubleheaders: list[tuple[date, Game]] = []
    for (team, day), found in sorted(per_team_day.items(), key=lambda x: (x[0][1], x[0][0])):
        pair = (day, frozenset(found[0].teams))
        if len(found) > 1 and pair not in seen:
            seen.add(pair)
            doubleheaders.append((day, sorted(found, key=_order)[0]))
    doubleheaders.sort(key=lambda x: (x[0], x[1].away))
    two_start = [(team, pitcher, sorted(g.day for g in starts))
                 for team, pitcher, starts in probable_starts(played).values() if len(starts) >= 2]
    two_start.sort(key=lambda x: (x[0], x[1].name))
    return WeekGrid(
        games_by_team=counts,
        days=[(day, len(by_day[day]), games_per_day[day]) for day in days if day in by_day],
        off_days=[(day, teams) for day, teams in off if teams and len(teams) < len(CODES)],
        doubleheaders=doubleheaders,
        postponed=[g for g in week if not g.played],
        two_start=two_start,
        light_max=light_max,
        heavy_min=heavy_min,
        total_games=len(played),
    )


# --- Home runs (scoring plays) -----------------------------------------------

@dataclass(frozen=True)
class MultiHomer:
    game: Game
    batter: Person
    team: str
    homers: int   # his home runs in the game
    order: int    # position among the game's scoring plays of his threshold-th homer


def home_runs(game: Game) -> dict[int, list[Play]]:
    """Batter id -> his home runs in the game, in order."""
    found: dict[int, list[Play]] = defaultdict(list)
    for play in game.plays:
        if play.event == "Home Run":
            found[play.batter.player_id].append(play)
    return dict(found)


def multi_homer_games(game: Game, threshold: int = 2) -> list[MultiHomer]:
    """Batters with at least ``threshold`` home runs in one game, earliest first."""
    counts: dict[int, int] = defaultdict(int)
    reached: dict[int, tuple[int, Play]] = {}
    for index, play in enumerate(game.plays):
        if play.event != "Home Run":
            continue
        counts[play.batter.player_id] += 1
        if counts[play.batter.player_id] == threshold:
            reached[play.batter.player_id] = (index, play)
    return [MultiHomer(game, play.batter, play.team, counts[pid], index)
            for pid, (index, play) in sorted(reached.items(), key=lambda x: x[1][0])]


# --- Game content (video links) -----------------------------------------------

@dataclass(frozen=True)
class Clip:
    url: str
    headline: str
    published: str
    player_ids: frozenset[int]
    taxonomy: frozenset[str]


@dataclass
class GameMedia:
    recap: str = ""       # MLB.com story (or recap video) for the game
    condensed: str = ""   # condensed game video
    clips: list[Clip] = field(default_factory=list)

    def home_run_clips(self, player_id: int) -> list[str]:
        """Links to one batter's home-run clips, oldest first.

        Only clips about him alone count (a "back-to-back homers" clip names
        two batters), so the first N are his N in-game home runs.
        """
        mine = [c for c in self.clips if "home-run" in c.taxonomy and c.player_ids == frozenset({player_id})]
        return [c.url for c in sorted(mine, key=lambda c: c.published)]


def video_url(slug: Any) -> str:
    text = str(slug or "").strip().strip("/")
    return f"{MLB_SITE}/video/{text}" if text and "/" not in text else ""


def news_url(slug: Any) -> str:
    text = str(slug or "").strip().strip("/")
    return f"{MLB_SITE}/news/{text}" if text and "/" not in text else ""


def _keywords(item: dict[str, Any], kind: str) -> list[str]:
    return [str(k.get("value") or "") for k in item.get("keywordsAll") or []
            if isinstance(k, dict) and k.get("type") == kind]


def _mp4(item: dict[str, Any]) -> str:
    for playback in item.get("playbacks") or []:
        if isinstance(playback, dict) and playback.get("name") == "mp4Avc":
            url = str(playback.get("url") or "")
            return url if url.startswith("https://") else ""
    return ""


def _item_url(item: dict[str, Any]) -> str:
    return video_url(item.get("slug") or item.get("id")) or _mp4(item)


def _items(*groups: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for group in groups:
        for item in group if isinstance(group, list) else []:
            if isinstance(item, dict):
                found.append(item)
    return found


def parse_content(raw: Any) -> GameMedia:
    """Recap, condensed game and per-play clips from /game/{gamePk}/content."""
    media = GameMedia()
    if not isinstance(raw, dict):
        return media
    editorial = raw.get("editorial") if isinstance(raw.get("editorial"), dict) else {}
    recap = ((editorial.get("recap") or {}) if isinstance(editorial.get("recap"), dict) else {}).get("mlb")
    if isinstance(recap, dict):
        media.recap = news_url(recap.get("slug"))

    epg = (raw.get("media") or {}).get("epgAlternate") if isinstance(raw.get("media"), dict) else None
    groups = [g for g in epg or [] if isinstance(g, dict)]
    extended = _items(*(g.get("items") for g in groups if str(g.get("title") or "") == "Extended Highlights"))
    others = _items(*(g.get("items") for g in groups))
    block = raw.get("highlights") if isinstance(raw.get("highlights"), dict) else {}
    inner = block.get("highlights") if isinstance(block.get("highlights"), dict) else {}
    plays = _items(inner.get("items"))

    for item in extended + others + plays:
        taxonomy = set(_keywords(item, "taxonomy"))
        slug = str(item.get("slug") or item.get("id") or "")
        if not media.condensed and ("condensed-game" in taxonomy or slug.startswith("condensed-game")):
            media.condensed = _item_url(item)
        elif not media.recap and "game-recap" in taxonomy:
            media.recap = _item_url(item)

    for item in plays:
        url = _item_url(item)
        if not url:
            continue
        ids = frozenset(_int(v) for v in _keywords(item, "player_id") if _int(v))
        media.clips.append(Clip(url, str(item.get("headline") or item.get("title") or ""),
                                str(item.get("date") or ""), ids, frozenset(_keywords(item, "taxonomy"))))
    return media


def fetch_content(game_pk: int, get: Callable[[str], Any] | None = None) -> GameMedia:
    return parse_content((get or http_get_json)(CONTENT_URL.format(game_pk=game_pk)))


# --- Display helpers ----------------------------------------------------------

_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}


def last_name(name: str) -> str:
    """'Daniel Lynch IV' -> 'Lynch'; 'Elly De La Cruz' -> 'De La Cruz'."""
    words = [w for w in str(name or "").split() if w]
    while len(words) > 1 and words[-1].lower() in _SUFFIXES:
        words.pop()
    if len(words) <= 1:
        return words[0] if words else ""
    particles = {"de", "la", "del", "van", "von", "da", "di", "le", "st.", "mc"}
    cut = len(words) - 1
    while cut > 1 and words[cut - 1].lower() in particles:
        cut -= 1
    return " ".join(words[cut:])


def name_key(name: Any) -> str:
    """A player's name for matching: "Last, First" or "First Last", accents,
    case, punctuation and Jr./Sr./II-IV suffixes ignored ("Julio Rodríguez" and
    "Rodriguez, Julio" match)."""
    text = str(name or "").strip()
    if text.count(",") == 1:
        last, first = (part.strip() for part in text.split(",", 1))
        if last and first:
            text = f"{first} {last}"
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower().replace("’", "'")
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\.?(?=\s|$)", "", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()
