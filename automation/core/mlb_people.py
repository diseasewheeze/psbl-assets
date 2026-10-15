"""MLB players, read-only, from the MLB Stats API (https://statsapi.mlb.com/api/v1).

Shared by the minor-eligibility watch and the League Bot's /minor (career
totals), the Wire's transaction collector (transactions), trade revisits (game
logs) and draft retrospectives (season totals). Nothing here writes anywhere.

Endpoints and the shapes this module reads (checked against live responses on
2026-10-15 unless marked otherwise):

  GET /people/search?names=bobby%20witt&hydrate=currentTeam
      {"people": [{id, fullName, firstName, lastName, useName, birthDate, active,
      primaryPosition{abbreviation}, mlbDebutDate?, currentTeam{id, name, parentOrgId?}}]}
      Without ``sportIds`` the search only finds players who have reached the
      majors; with sportIds=1,11,12,13,14,16 it also finds minor leaguers (a
      2026 draftee was found only that way). currentTeam is absent unless
      hydrated; for a player at an affiliate it is the affiliate, with
      ``parentOrgId`` naming the MLB club.
  GET /people?personIds=1,2&hydrate=stats(group=[hitting,pitching],type=[career])
      people[] each with stats[] (one entry per group the player has MLB stats
      in; no ``stats`` key at all for a player without MLB stats). Each entry has
      group.displayName and splits[0].stat (atBats, plateAppearances,
      gamesPlayed; pitching adds outs, inningsPitched like "614.1" and its own
      atBats, the at-bats it faced). Career splits are MLB regular season only.
  GET /people?personIds=...&hydrate=stats(group=[hitting,pitching],type=[yearByYear])
      the same with one split per season and team; a season with two teams also
      has a combined split without ``team`` and with ``numTeams``.
  GET /people/{id}/stats?stats=gameLog&group=hitting,pitching&season=2026&gameType=R
      stats[] one entry per group; splits[] each with date, gameType,
      game{gamePk}, team{id, name}, opponent{id, name} and stat (hitting: hits,
      doubles, triples, homeRuns, runs, rbi, baseOnBalls, hitByPitch,
      stolenBases, caughtStealing, strikeOuts, atBats...; pitching: outs,
      inningsPitched, hits, earnedRuns, baseOnBalls, hitBatsmen, strikeOuts,
      wins, losses, saves, holds...).
  GET /teams/{teamId}/roster?rosterType=40Man
      roster[] {person{id, fullName}, position{abbreviation}, status{code,
      description}, parentTeamId}. Codes seen: A Active, D10/D15/D60 Injured
      10/15/60-Day, RM Reassigned to Minors.
  GET /transactions?sportId=1&startDate=YYYY-MM-DD&endDate=YYYY-MM-DD
      transactions[] {id, person{id, fullName}, toTeam{id, name}, fromTeam?,
      date, effectiveDate, resolutionDate?, typeCode, typeDesc, description}.
      Teams carry no abbreviation. A trade is one record per player sharing one
      id. Injured-list moves are typeCode SC with the list named in the
      description.

UNVERIFIED (not checked live): how many ids one /people?personIds= request
accepts (PEOPLE_BATCH is kept small), and the search's matching rules beyond
full names and last names. The parser is tolerant: a missing number counts as
0 and a malformed row is skipped.

Fantrax writes names "Last, First" and its own team codes; norm_name and
team_code (core/mlb.py's club table and aliases) turn both sides into one form
before matching.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Iterable

from . import mlb as _clubs

BASE = "https://statsapi.mlb.com/api/v1"
MLB_SPORT = 1
ALL_LEVELS = "1,11,12,13,14,16"   # MLB, Triple-A, Double-A, High-A, Single-A, Rookie
REGULAR_SEASON = "R"
PEOPLE_BATCH = 40
USER_AGENT = "DBL-Automation/2.0"
MIN_GAP = 0.25  # seconds between requests

# The 30 clubs, their names and other spellings come from core/mlb.py, so every
# module writes a club the same way (MLB's abbreviation, e.g. AZ, ATH, CWS).
TEAMS: dict[int, str] = {team_id: code for team_id, (code, _) in _clubs.TEAMS.items()}
TEAM_NAMES: dict[str, str] = {code: name for code, name in _clubs.TEAMS.values()}
TEAM_ALIASES: dict[str, str] = _clubs.ALIASES
PITCHER_POSITIONS = frozenset({"P", "SP", "RP", "RHP", "LHP"})
TWO_WAY = "TWP"


# --------------------------------------------------------------------- names and teams
def norm_name(value: Any) -> str:
    """'Witt Jr., Bobby' and 'Bobby Witt Jr.' -> 'bobby witt': accents, suffixes and punctuation dropped."""
    raw = str(value or "").strip()
    if raw.count(",") == 1:
        last, first = (part.strip() for part in raw.split(",", 1))
        if last and first:
            raw = f"{first} {last}"
    text = unicodedata.normalize("NFKD", raw)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower().replace("’", "'")
    text = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def split_name(value: Any) -> tuple[str, str]:
    """('Bobby', 'Witt Jr.') from 'Witt Jr., Bobby' or 'Bobby Witt Jr.'."""
    raw = " ".join(str(value or "").split())
    if raw.count(",") == 1:
        last, first = (part.strip() for part in raw.split(",", 1))
        return first, last
    parts = raw.split(" ")
    if len(parts) > 2 and norm_name(parts[-1]) == "":   # "Bobby Witt Jr."
        return " ".join(parts[:-2]), " ".join(parts[-2:])
    return (" ".join(parts[:-1]), parts[-1]) if parts else ("", "")


def display_name(value: Any) -> str:
    """Fantrax's 'Last, First' as 'First Last'."""
    first, last = split_name(value)
    return f"{first} {last}".strip()


def team_code(value: Any) -> str:
    """A club as MLB writes it ('ARI' -> 'AZ', 'Kansas City Royals' -> 'KC', 147 -> 'NYY'); "" when unknown.

    Text goes through core/mlb.team_code; a number is a Stats API team id.
    """
    if isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit()):
        return TEAMS.get(int(value), "")
    return _clubs.team_code(value)


def team_of(raw: Any) -> str:
    """The MLB club of a team object ({id, parentOrgId?}): the club itself, or an affiliate's parent."""
    if not isinstance(raw, dict):
        return ""
    for key in ("id", "parentOrgId"):
        try:
            code = TEAMS.get(int(raw.get(key) or 0), "")
        except (TypeError, ValueError):
            code = ""
        if code:
            return code
    return ""


def is_pitcher(position: Any) -> bool | None:
    """True for pitchers, False for hitters, None for two-way players or an unknown position."""
    codes = {p.strip().upper() for p in re.split(r"[,/ ]+", str(position or "")) if p.strip()}
    if not codes or TWO_WAY in codes:
        return None
    if codes <= PITCHER_POSITIONS:
        return True
    if codes & PITCHER_POSITIONS:
        return None
    return False


# --------------------------------------------------------------------- numbers
def num(stat: Any, key: str) -> float:
    try:
        return float((stat or {}).get(key) or 0)
    except (TypeError, ValueError, AttributeError):
        return 0.0


def outs_of(stat: Any) -> int:
    """Outs recorded, from ``outs`` or else inningsPitched written as '614.1' (614 1/3)."""
    if isinstance(stat, dict) and stat.get("outs") not in (None, ""):
        return int(num(stat, "outs"))
    whole, _, part = str((stat or {}).get("inningsPitched") or "0").partition(".")
    try:
        return int(whole or 0) * 3 + int(part or 0)
    except ValueError:
        return 0


def innings_text(outs: int) -> str:
    """152 outs -> '50.2' (MLB's own way of writing 50 2/3 innings)."""
    return f"{outs // 3}.{outs % 3}"


def _add(total: dict[str, float], stat: dict[str, Any]) -> None:
    """Add a stat line's numbers (rates such as avg are text and are skipped)."""
    for key, value in stat.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total[key] = total.get(key, 0) + value
    if "outs" not in stat and stat.get("inningsPitched") not in (None, ""):
        total["outs"] = total.get("outs", 0) + outs_of({"inningsPitched": stat["inningsPitched"]})


def _mlb_regular(splits: Iterable[Any]) -> list[dict[str, Any]]:
    out = []
    for s in splits or []:
        if not isinstance(s, dict):
            continue
        sport = (s.get("sport") or {}).get("id")
        if sport not in (None, MLB_SPORT) or s.get("gameType") not in (None, REGULAR_SEASON):
            continue
        out.append(s)
    return out


def _combine(splits: list[dict[str, Any]]) -> dict[str, float]:
    """One season or career line: the combined row when MLB gives one (traded players), else the sum."""
    whole = [s for s in splits if "team" not in s and s.get("numTeams")]
    rows = whole[:1] if whole else splits
    total: dict[str, float] = {}
    for s in rows:
        _add(total, s.get("stat") or {})
    return total


def group_name(entry: Any) -> str:
    return str(((entry or {}).get("group") or {}).get("displayName") or "").lower()


# --------------------------------------------------------------------- records
@dataclass(frozen=True)
class Person:
    id: int
    name: str
    position: str = ""            # MLB primaryPosition abbreviation (SS, P, TWP...)
    team: str = ""                # MLB club (an affiliate's parent club), "" when unattached
    level_team: str = ""          # the team he plays for now, e.g. an affiliate's name
    birth_date: str = ""
    debut: str = ""
    active: bool = True


@dataclass(frozen=True)
class Career:
    """Career MLB regular-season totals. At-bats come from the hitting group only."""
    at_bats: int = 0
    outs: int = 0
    hitting_games: int = 0
    pitching_games: int = 0

    @property
    def innings(self) -> str:
        return innings_text(self.outs)


@dataclass(frozen=True)
class GameLine:
    date: date
    game_pk: int
    group: str                    # hitting or pitching
    team: str
    opponent: str
    stat: dict[str, Any]


@dataclass(frozen=True)
class RosterEntry:
    person_id: int
    name: str
    position: str
    status: str                   # A, D10, D15, D60, RM...
    status_text: str
    team: str


@dataclass(frozen=True)
class Transaction:
    id: int
    person_id: int
    name: str
    type_code: str
    type_text: str
    description: str
    date: str
    effective_date: str
    to_team_id: int | None
    to_team: str
    from_team_id: int | None
    from_team: str

    @property
    def mlb_teams(self) -> list[str]:
        """The MLB clubs involved, receiving club first (affiliates are left out)."""
        out = []
        for tid in (self.to_team_id, self.from_team_id):
            code = TEAMS.get(int(tid or 0), "")
            if code and code not in out:
                out.append(code)
        return out

    @property
    def key(self) -> str:
        """Stable identity: MLB sometimes lists the same move twice under different ids."""
        digest = hashlib.sha1(self.description.encode("utf-8")).hexdigest()[:10]
        return f"{self.person_id}|{self.type_code}|{self.date}|{digest}"


def parse_person(raw: Any) -> Person | None:
    if not isinstance(raw, dict) or not raw.get("id"):
        return None
    try:
        pid = int(raw["id"])
    except (TypeError, ValueError):
        return None
    team = raw.get("currentTeam") if isinstance(raw.get("currentTeam"), dict) else {}
    return Person(
        id=pid,
        name=str(raw.get("fullName") or " ".join(x for x in (raw.get("useName") or raw.get("firstName"), raw.get("lastName")) if x)),
        position=str(((raw.get("primaryPosition") or {}).get("abbreviation")) or ""),
        team=team_of(team),
        level_team=str(team.get("name") or ""),
        birth_date=str(raw.get("birthDate") or ""),
        debut=str(raw.get("mlbDebutDate") or ""),
        active=bool(raw.get("active", True)),
    )


def career_of(raw_person: Any) -> Career:
    """Career totals from a person hydrated with stats(group=[hitting,pitching],type=[career])."""
    ab = outs = hg = pg = 0
    for entry in (raw_person or {}).get("stats") or []:
        group = group_name(entry)
        line = _combine(_mlb_regular(entry.get("splits") or []))
        if group == "hitting":
            ab, hg = int(line.get("atBats", 0)), int(line.get("gamesPlayed", 0))
        elif group == "pitching":
            outs, pg = int(line.get("outs", 0)), int(line.get("gamesPlayed", 0))
    return Career(ab, outs, hg, pg)


def seasons_of(raw_person: Any) -> dict[int, dict[str, dict[str, float]]]:
    """Season -> {"hitting": totals, "pitching": totals}, from a yearByYear hydration (MLB regular season)."""
    out: dict[int, dict[str, dict[str, float]]] = {}
    for entry in (raw_person or {}).get("stats") or []:
        group = group_name(entry)
        if group not in ("hitting", "pitching"):
            continue
        by_year: dict[int, list[dict[str, Any]]] = {}
        for s in _mlb_regular(entry.get("splits") or []):
            try:
                by_year.setdefault(int(s.get("season")), []).append(s)
            except (TypeError, ValueError):
                continue
        for year, rows in by_year.items():
            out.setdefault(year, {})[group] = _combine(rows)
    return out


def parse_game_log(raw: Any) -> list[GameLine]:
    """Every regular-season game line in a gameLog answer, hitting and pitching."""
    out = []
    for entry in (raw.get("stats") or [] if isinstance(raw, dict) else []):
        group = group_name(entry)
        for s in _mlb_regular(entry.get("splits") or []):
            try:
                day = date.fromisoformat(str(s.get("date"))[:10])
                pk = int((s.get("game") or {}).get("gamePk") or 0)
            except (TypeError, ValueError):
                continue
            out.append(GameLine(day, pk, group, team_of(s.get("team")), team_of(s.get("opponent")),
                                dict(s.get("stat") or {})))
    return out


def parse_roster(raw: Any) -> list[RosterEntry]:
    out = []
    for row in (raw.get("roster") or [] if isinstance(raw, dict) else []):
        person = (row or {}).get("person") or {}
        try:
            pid = int(person.get("id"))
        except (TypeError, ValueError):
            continue
        status = row.get("status") or {}
        out.append(RosterEntry(pid, str(person.get("fullName") or ""),
                               str((row.get("position") or {}).get("abbreviation") or ""),
                               str(status.get("code") or ""), str(status.get("description") or ""),
                               TEAMS.get(int(row.get("parentTeamId") or 0), "")))
    return out


def parse_transactions(raw: Any) -> list[Transaction]:
    out = []
    for row in (raw.get("transactions") or [] if isinstance(raw, dict) else []):
        if not isinstance(row, dict):
            continue
        person = row.get("person") or {}
        to, frm = row.get("toTeam") or {}, row.get("fromTeam") or {}
        try:
            out.append(Transaction(
                id=int(row.get("id") or 0), person_id=int(person.get("id") or 0),
                name=str(person.get("fullName") or ""), type_code=str(row.get("typeCode") or ""),
                type_text=str(row.get("typeDesc") or ""), description=" ".join(str(row.get("description") or "").split()),
                date=str(row.get("date") or "")[:10], effective_date=str(row.get("effectiveDate") or "")[:10],
                to_team_id=int(to["id"]) if to.get("id") else None, to_team=str(to.get("name") or ""),
                from_team_id=int(frm["id"]) if frm.get("id") else None, from_team=str(frm.get("name") or ""),
            ))
        except (TypeError, ValueError):
            continue
    return out


# --------------------------------------------------------------------- the client
def _http_get(url: str, params: dict[str, Any]) -> Any:
    """One GET with retries on 429 and 5xx; None for 404."""
    import requests

    last: Exception | None = None
    for attempt in range(4):
        try:
            response = requests.get(url, params=params or None, headers={"User-Agent": USER_AGENT}, timeout=20)
            if response.status_code == 404:
                return None
            if response.status_code == 429 or response.status_code >= 500:
                last = RuntimeError(f"HTTP {response.status_code}")
                time.sleep(min(2 ** (attempt + 1), 20))
                continue
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 - retried, then reported
            last = exc
            time.sleep(1)
    raise RuntimeError(f"MLB request failed: {url} ({last})")


class MlbApi:
    """Read-only MLB Stats API client. ``fetch(url, params)`` returns parsed JSON; tests pass a fake."""

    def __init__(self, fetch: Callable[[str, dict[str, Any]], Any] | None = None, *, min_gap: float = MIN_GAP,
                 sleep: Callable[[float], Any] = time.sleep, clock: Callable[[], float] = time.monotonic) -> None:
        self.fetch = fetch or _http_get
        self.min_gap = min_gap if fetch is None else 0.0
        self.sleep, self.clock = sleep, clock
        self._last = 0.0
        self._lock = threading.Lock()
        self.calls = 0

    def get(self, path: str, **params: Any) -> Any:
        url = path if path.startswith("http") else f"{BASE}{path}"
        with self._lock:
            wait = self.min_gap - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
            self._last = self.clock()
            self.calls += 1
        return self.fetch(url, {k: v for k, v in params.items() if v is not None})

    # -- people ---------------------------------------------------------------
    def search_raw(self, name: str, *, all_levels: bool = True) -> list[dict[str, Any]]:
        raw = self.get("/people/search", names=name, sportIds=ALL_LEVELS if all_levels else None,
                       hydrate="currentTeam") or {}
        return [p for p in raw.get("people") or [] if isinstance(p, dict)]

    def search(self, name: str, *, all_levels: bool = True) -> list[Person]:
        return [p for p in (parse_person(r) for r in self.search_raw(name, all_levels=all_levels)) if p]

    def people_raw(self, ids: Iterable[int], hydrate: str) -> dict[int, dict[str, Any]]:
        """Person id -> raw person, fetched PEOPLE_BATCH at a time."""
        wanted = list(dict.fromkeys(int(i) for i in ids))
        out: dict[int, dict[str, Any]] = {}
        for start in range(0, len(wanted), PEOPLE_BATCH):
            chunk = wanted[start:start + PEOPLE_BATCH]
            raw = self.get("/people", personIds=",".join(map(str, chunk)), hydrate=hydrate) or {}
            for person in raw.get("people") or []:
                if isinstance(person, dict) and person.get("id"):
                    out[int(person["id"])] = person
        return out

    def careers(self, ids: Iterable[int]) -> dict[int, tuple[Person | None, Career]]:
        """Person id -> (person, career MLB regular-season totals). Ids MLB doesn't return are left out."""
        raw = self.people_raw(ids, "currentTeam,stats(group=[hitting,pitching],type=[career])")
        return {pid: (parse_person(p), career_of(p)) for pid, p in raw.items()}

    def seasons(self, ids: Iterable[int]) -> dict[int, dict[int, dict[str, dict[str, float]]]]:
        """Person id -> season -> {"hitting", "pitching"} MLB regular-season totals."""
        raw = self.people_raw(ids, "stats(group=[hitting,pitching],type=[yearByYear])")
        return {pid: seasons_of(p) for pid, p in raw.items()}

    def game_log(self, person_id: int, season: int) -> list[GameLine]:
        raw = self.get(f"/people/{int(person_id)}/stats", stats="gameLog", group="hitting,pitching",
                       season=int(season), gameType=REGULAR_SEASON)
        return parse_game_log(raw)

    # -- teams and moves ---------------------------------------------------------
    def roster_40man(self, team_id: int) -> list[RosterEntry]:
        return parse_roster(self.get(f"/teams/{int(team_id)}/roster", rosterType="40Man"))

    def transactions(self, start: date, end: date) -> list[Transaction]:
        raw = self.get("/transactions", sportId=MLB_SPORT, startDate=start.isoformat(), endDate=end.isoformat())
        if not isinstance(raw, dict) or not isinstance(raw.get("transactions"), list):
            raise ValueError("MLB transactions answer has no transactions list (API changed?)")
        return parse_transactions(raw)

    def draft_prospects(self, year: int) -> list[dict[str, Any]]:
        """GET /draft/prospects/{year}: the draft class list (empty until MLB publishes it)."""
        raw = self.get(f"/draft/prospects/{int(year)}")
        if raw is None:
            return []
        if not isinstance(raw, dict) or not isinstance(raw.get("prospects"), list):
            raise ValueError("MLB draft prospects answer has no prospects list (API changed?)")
        return [p for p in raw["prospects"] if isinstance(p, dict)]


# --------------------------------------------------------------------- matching
@dataclass
class Match:
    person: Person | None
    why: str = ""                       # set when no single player matched
    candidates: list[Person] = field(default_factory=list)


def _narrow(people: list[Person], team: str, position: str) -> list[Person]:
    code = team_code(team)
    if code and len(people) > 1:
        people = [p for p in people if p.team == code] or people
    pitcher = is_pitcher(position)
    if pitcher is not None and len(people) > 1:
        people = [p for p in people if is_pitcher(p.position) in (pitcher, None)] or people
    if len(people) > 1:
        active = [p for p in people if p.active]
        if len(active) == 1:
            people = active
    return people


def find_person(api: MlbApi, name: str, team: str = "", position: str = "") -> Match:
    """The one MLB player a Fantrax player is ("Last, First", club, positions), or why not.

    Exact names first (accents and Jr. ignored), narrowed by club, then by
    pitcher or hitter, then to the only active one. Failing that, a player with
    the same last name, the same first initial and the same club (Zach and
    Zachary). Anything still ambiguous is left unmatched rather than guessed.
    """
    wanted = norm_name(name)
    if not wanted:
        return Match(None, "no name")
    first, last = split_name(name)
    query = f"{first} {last}".strip()
    found = api.search(query)
    exact = [p for p in found if norm_name(p.name) == wanted]
    if exact:
        narrowed = _narrow(exact, team, position)
        return Match(narrowed[0]) if len(narrowed) == 1 else Match(None, "more than one player has this name", narrowed)
    last_norm, initial = norm_name(last), norm_name(first)[:1]
    pool = found if found else api.search(last)
    code = team_code(team)
    near = [p for p in pool if norm_name(split_name(p.name)[1]) == last_norm
            and norm_name(split_name(p.name)[0])[:1] == initial and code and p.team == code]
    if len(near) == 1:
        return Match(near[0])
    return Match(None, "no MLB player matches" if not near else "more than one player could be this one", near)
