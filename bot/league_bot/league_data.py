"""Cached, read-only data for the bot's league commands.

Every method here blocks (Fantrax, the MLB Stats API, the League Ledger CSV,
the events file), so the Discord layer calls them with ``asyncio.to_thread``.
Results are cached for a few minutes (rosters, scores) up to half a day
(Fantrax's player list), so busy commands don't hammer Fantrax or MLB.
Nothing here writes to Fantrax.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from .shared import picktrades

from core import mlb_people as mp  # noqa: E402  (path set up by .shared)

USER_AGENT = "DBL-LeagueBot/1.0"
log = logging.getLogger("league.bot")

# Seconds each kind of data is reused before it is read again.
TTL = {
    "info": 30 * 60,        # league calendar and schedule rarely change
    "rosters": 5 * 60,
    "picks": 10 * 60,
    "players": 12 * 3600,   # getPlayerIds is large and changes slowly
    "scores": 3 * 60,
    "standings": 10 * 60,
    "clearance": 10 * 60,
    "clearance_error": 60,
    "events": 60,
    "mlb_search": 6 * 3600,
    "mlb_career": 3 * 3600,  # career totals change at most once a day
}


class TTLCache:
    """Thread-safe cache of loaded values, each kept for its own lifetime."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, max_entries: int = 500) -> None:
        self.clock = clock
        self.max_entries = max_entries
        self._data: dict[Any, tuple[float, float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Any, ttl: float, load: Callable[[], Any], max_age: float | None = None) -> Any:
        """The cached value, or a fresh ``load()``. ``max_age`` (seconds) asks for a fresher copy than the TTL."""
        with self._lock:
            hit = self._data.get(key)
            if hit:
                limit = hit[1] if max_age is None else min(hit[1], max_age)
                if self.clock() - hit[0] < limit:
                    return hit[2]
        value = load()  # outside the lock: a slow load doesn't block other keys
        self.put(key, ttl, value)
        return value

    def put(self, key: Any, ttl: float, value: Any) -> None:
        with self._lock:
            if len(self._data) >= self.max_entries:
                oldest = min(self._data, key=lambda k: self._data[k][0])
                self._data.pop(oldest, None)
            self._data[key] = (self.clock(), ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


@dataclass(frozen=True)
class Clearance:
    """The League Ledger's Pick Clearance tab: status is ok, unset or error."""
    status: str
    table: dict[str, dict[str, Any]] | None = None


class LeagueData:
    """Fantrax league data, the Pick Clearance CSV and the League Calendar, cached."""

    def __init__(self, client: Any = None, *, league_id: str | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 events_loader: Callable[[], dict[str, Any]] | None = None,
                 clearance_loader: Callable[[], Any] | None = None,
                 league_loader: Callable[[], dict[str, Any]] | None = None) -> None:
        self._client = client
        self._league_id = league_id
        self.cache = TTLCache(clock)
        self._events_loader = events_loader
        self._clearance_loader = clearance_loader
        self._league_loader = league_loader
        self._client_lock = threading.Lock()

    @property
    def league_id(self) -> str:
        if self._league_id is None:
            from core.league import load_league
            self._league_id = str(load_league()["league_id"])
        return self._league_id

    @property
    def client(self) -> Any:
        with self._client_lock:
            if self._client is None:
                from core.fantrax import Fantrax
                self._client = Fantrax(self.league_id, user_agent=USER_AGENT)
            return self._client

    def league_info(self) -> dict[str, Any]:
        return self.cache.get("info", TTL["info"], self.client.league_info)

    def rosters(self) -> dict[str, Any]:
        """getTeamRosters for today (each player's slot: ACTIVE, RESERVE, MINORS or INJURED_RESERVE)."""
        return self.cache.get("rosters", TTL["rosters"], self.client.rosters)

    def draft_picks(self) -> dict[str, Any]:
        """getDraftPicks. Once a draft's order is set, Fantrax moves that season's unmade picks to
        currentDraftPicks without their year or original team; those are filled in from the draft."""
        def load() -> dict[str, Any]:
            raw = self.client.draft_picks()
            current = raw.get("currentDraftPicks") if isinstance(raw, dict) else None
            if not any(isinstance(r, dict) and not (r.get("year") and r.get("originalOwnerTeamId"))
                       for r in current or []):
                return raw
            from core import draft as dr
            try:
                draft = dr.parse_results(self.client.draft_results())
            except Exception as exc:  # future picks still show
                log.warning("getDraftResults unreadable, current-draft picks left out: %s", exc)
                draft = None
            return dr.complete_current_picks(raw, draft, dr.draft_year(draft, self._timezone()))
        return self.cache.get("picks", TTL["picks"], load)

    def _timezone(self) -> Any:
        from zoneinfo import ZoneInfo
        try:
            from core.league import load_league, timezone_of
            return timezone_of(self._league_loader() if self._league_loader is not None else load_league())
        except Exception:  # the league runs on Eastern Time (5.8)
            return ZoneInfo("America/New_York")

    def player_ids(self) -> dict[str, Any]:
        return self.cache.get("players", TTL["players"], self.client.player_ids)

    def matchup_scores(self, period: int) -> list[dict[str, Any]]:
        return self.cache.get(("scores", period), TTL["scores"], lambda: self.client.matchup_scores(period))

    def standings(self) -> list[dict[str, Any]]:
        """getStandings, normalized (rank, teamId, record, points for); the Awards Ballot's Comeback and Bust."""
        return self.cache.get("standings", TTL["standings"], self.client.standings)

    def events(self) -> dict[str, Any]:
        def load() -> dict[str, Any]:
            if self._events_loader:
                return self._events_loader()
            from .deadlines import load as load_events
            return load_events()
        return self.cache.get("events", TTL["events"], load)

    def clearance(self) -> Clearance:
        """Paid-through Seasons from LEAGUE_LEDGER_CLEARANCE_CSV (picktrades.py's parser)."""
        pt = picktrades()
        if self._clearance_loader is None and not os.environ.get(pt.CLEARANCE_ENV, "").strip():
            return Clearance("unset")

        def load() -> Clearance:
            table = (self._clearance_loader or pt.load_clearance)()
            return Clearance("ok", table) if table is not None else Clearance("error")

        result = self.cache.get("clearance", TTL["clearance"], load)
        if result.status == "error":  # retry a failed read sooner
            self.cache.put("clearance", TTL["clearance_error"], result)
        return result


class MlbLookup:
    """MLB player search and career totals (core/mlb_people.py), cached.

    One client is shared by the command threads; its request pacing is locked.
    """

    def __init__(self, api: Any = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.api = api or mp.MlbApi()
        self.cache = TTLCache(clock)

    def search(self, query: str) -> list[Any]:
        """Players at every level whose name matches (mp.Person)."""
        return self.cache.get(("search", mp.norm_name(query)), TTL["mlb_search"], lambda: self.api.search(query))

    def career(self, person_id: int) -> tuple[Any, Any] | None:
        """(mp.Person, mp.Career) for one player, or None when MLB has no record."""
        pid = int(person_id)
        return self.cache.get(("career", pid), TTL["mlb_career"], lambda: self.api.careers([pid]).get(pid))
