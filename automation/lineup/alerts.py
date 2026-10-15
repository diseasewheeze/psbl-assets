#!/usr/bin/env python3
"""DBL Lineup Alerts: a daily nudge when a starter has no MLB game today.

Once a day (about 3:00 PM ET, regular season and playoffs) this checks each
opted-in owner's Fantrax lineup for today and sends one short message in
🔔│lineup-alerts that mentions them when:

  - hitters: a player in an ACTIVE hitter slot whose MLB club has no game
    today (an off day, or its only game postponed) while one of that
    franchise's RESERVE players who fits that slot plays today and his club's
    first game has not started; or
  - starting pitchers: a player in an ACTIVE SP slot who is not today's
    probable starter (his club is off, or MLB has announced someone else)
    while a RESERVE SP is today's announced probable starter and that game has
    not started. When his club has not announced today's starter, nothing is
    said about him: never guess.

Relief pitchers are not checked (their appearances cannot be known ahead).
Lineups are the manager's job (9.1); this is only a reminder. Players lock
about one minute before their own game (5.3); in a doubleheader that is the
first game.

Who gets alerts: only owners listed under ``owners`` in automation/league.yaml,
the same opt-in the Wire uses for injury pings. Nobody else is mentioned.

Slot eligibility is the league's own (automation/core/sport.py SLOT_ACCEPTS):
an OF slot takes any outfielder, UTIL any hitter, SP only a starting
pitcher. A player's positions are his Fantrax roster position plus the
position(s) in getPlayerIds (comma-separated when Fantrax lists more than
one).

Data (all read-only):
  - getTeamRosters without a period = today's daily lineup (ACTIVE, RESERVE,
    MINORS, IR). MINORS and IR players are ignored.
  - getPlayerIds = each player's name, position and MLB club.
  - MLB schedule for today with probable pitchers (automation/core/mlb.py).
  A player whose club is missing or not one of the 30 MLB clubs is skipped
  rather than guessed at. Probable starters are matched by name and club.

Each franchise gets at most one alert per day (state/lineup_alerts.json).

Modes:
  preview  print the alerts; no Discord, no state change
  test     post [TEST] alerts without notifying anyone; no state change
  live     post alerts for opted-in owners and record them
  --all-teams (preview/test only) also covers franchises with no opted-in
  owner, without a mention.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
AUTOMATION = ROOT.parent
for folder in (AUTOMATION, AUTOMATION / "competition"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import render  # noqa: E402  (competition/render.py)
from core import mlb, sport  # noqa: E402
from core.fantrax import Fantrax  # noqa: E402
from core.league import color_value, load_json, load_league, save_json, timezone_of  # noqa: E402
from discord_webhook import send_discord_webhook  # noqa: E402

STATE_PATH = ROOT / "state" / "lineup_alerts.json"
DEFAULT_WEBHOOK = "LEAGUE_WEBHOOK_LINEUP_ALERTS"
LINEUP = ("ACTIVE", "RESERVE")
# Fantrax may write the utility slot "UT" or "Util"; the rules call it UTIL.
SLOT_NAMES = {"UT": "UTIL", "UTIL": "UTIL", "UTILITY": "UTIL"}
ORDER = ["C", "1B", "2B", "3B", "SS", "OF", "LF", "CF", "RF", "DH", "UTIL", "SP", "RP"]


@dataclass
class Entry:
    player_id: str
    name: str             # "First Last"
    slot: str             # Fantrax roster position as written (the lineup slot when ACTIVE)
    positions: set[str]
    team: str             # MLB club
    games: list[mlb.Game] = field(default_factory=list)  # today's games for his club, first pitch first

    @property
    def rule_slot(self) -> str:
        return SLOT_NAMES.get(self.slot.upper(), self.slot.upper())

    @property
    def first_pitch(self) -> datetime | None:
        return self.games[0].start if self.games else None

    def not_started(self, now: datetime) -> bool:
        """His club's first game today is still to come (a TBD time counts as to come)."""
        return bool(self.games) and (self.first_pitch is None or self.first_pitch > now)

    def starts_in(self) -> list[mlb.Game]:
        """Today's games in which MLB has announced him as his club's starter."""
        key = mlb.name_key(self.name)
        return [g for g in self.games if (p := g.probable(self.team)) is not None and mlb.name_key(p.name) == key]


@dataclass
class TeamAlert:
    team_id: str
    team_name: str
    idle: list[Entry] = field(default_factory=list)                   # ACTIVE hitters, no game today
    bench: list[Entry] = field(default_factory=list)                  # RESERVE hitters who fit, playing
    resting: list[tuple[Entry, str]] = field(default_factory=list)    # ACTIVE SPs not starting, and why
    starters: list[Entry] = field(default_factory=list)               # RESERVE SPs starting today

    @property
    def summary(self) -> str:
        return (f"{len(self.idle)} idle, {len(self.bench)} bench option(s), "
                f"{len(self.resting)} SP not starting, {len(self.starters)} bench SP starting")


def positions_of(*values: Any) -> set[str]:
    found: set[str] = set()
    for value in values:
        for part in re.split(r"[,/ ]+", str(value or "").upper()):
            if part:
                found.add(SLOT_NAMES.get(part, part))
    return found


def can_fill(slot: str, positions: set[str]) -> bool:
    """Whether a reserve with these positions can take this lineup slot (core/sport.py rules)."""
    return sport.slot_fits(SLOT_NAMES.get(slot.upper(), slot.upper()), positions)


def is_hitter_slot(slot: str) -> bool:
    return SLOT_NAMES.get(slot.upper(), slot.upper()) in sport.HITTER_SLOTS


def display_name(name: str) -> str:
    """Fantrax lists names as "Last, First"; show "First Last"."""
    if name.count(",") == 1:
        last, first = (part.strip() for part in name.split(",", 1))
        return f"{first} {last}"
    return name


def player_directory(players: dict[str, Any]) -> dict[str, dict[str, Any]]:
    directory: dict[str, dict[str, Any]] = {}
    for key, raw in (players or {}).items():
        if isinstance(raw, dict):
            directory[str(key)] = raw
            if raw.get("fantraxId"):
                directory[str(raw["fantraxId"])] = raw
    return directory


def todays_games(games: list[mlb.Game], today: date) -> dict[str, list[mlb.Game]]:
    """MLB club -> its regular-season games actually played today, first pitch first."""
    return mlb.games_on(games, today)


def starter_status(entry: Entry) -> str | None:
    """Why an ACTIVE SP is not starting today, or None when he starts or nobody knows yet."""
    if not entry.games:
        return "no game today"
    if entry.starts_in():
        return None
    announced = [g.probable(entry.team) for g in entry.games]
    if any(p is None for p in announced):
        return None  # his club has not named today's starter: never guess
    names = " and ".join(p.name for p in announced)
    return f"{names} start{'s' if len(announced) == 1 else ''}"


def find_alerts(
    rosters: dict[str, Any],
    players: dict[str, Any],
    playing: dict[str, list[mlb.Game]],
    now: datetime,
) -> list[TeamAlert]:
    directory = player_directory(players)
    block = rosters.get("rosters") if isinstance(rosters, dict) else None
    alerts: list[TeamAlert] = []
    for team_id, team in (block or {}).items():
        if not isinstance(team, dict):
            continue
        idle: list[Entry] = []
        bench: list[Entry] = []
        resting: list[tuple[Entry, str]] = []
        starters: list[Entry] = []
        for item in team.get("rosterItems") or []:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").upper()
            if status not in LINEUP:
                continue
            player_id = str(item.get("id") or "")
            info = directory.get(player_id) or {}
            club = mlb.team_code(info.get("team"))
            if not club:
                continue  # no MLB club or an unknown code: never guess
            entry = Entry(
                player_id=player_id,
                name=display_name(str(info.get("name") or player_id)),
                slot=str(item.get("position") or "").upper(),
                positions=positions_of(item.get("position"), info.get("position")),
                team=club,
                games=list(playing.get(club, [])),
            )
            if status == "ACTIVE":
                if is_hitter_slot(entry.slot) and not entry.games:
                    idle.append(entry)
                elif entry.rule_slot == "SP":
                    why = starter_status(entry)
                    if why:
                        resting.append((entry, why))
            else:
                if any(g.start is None or g.start > now for g in entry.starts_in()) and "SP" in entry.positions:
                    starters.append(entry)
                elif entry.not_started(now):
                    bench.append(entry)
        options = [b for b in bench if any(can_fill(i.slot, b.positions) for i in idle)]
        stuck = [i for i in idle if any(can_fill(i.slot, b.positions) for b in options)]
        alert = TeamAlert(str(team_id), str(team.get("teamName") or team_id))
        if stuck and options:
            alert.idle, alert.bench = stuck, options
        if resting and starters:
            alert.resting, alert.starters = resting, starters
        if alert.idle or alert.resting:
            alerts.append(alert)
    return alerts


# --- Owners (opt-in) ----------------------------------------------------------

def owner_ids(league: dict[str, Any]) -> dict[str, str]:
    """league.yaml ``owners``: lowercased team name/ID -> Discord user ID."""
    owners: dict[str, str] = {}
    for key, value in (league.get("owners") or {}).items():
        user = str(value or "").strip()
        if re.fullmatch(r"\d{15,21}", user):
            owners[str(key).strip().lower()] = user
    return owners


def owner_for(alert: TeamAlert, owners: dict[str, str]) -> str:
    return owners.get(alert.team_id.lower()) or owners.get(alert.team_name.lower()) or ""


# --- Discord ------------------------------------------------------------------

def _slot_label(positions: set[str]) -> str:
    return "/".join(p for p in ORDER if p in positions) or "?"


def _when(game: mlb.Game | None) -> str:
    return f"<t:{int(game.start.timestamp())}:t>" if game and game.start else ""


def alert_payload(ctx: render.Context, alert: TeamAlert, user_id: str, *, notify: bool) -> dict[str, Any]:
    fields = []
    if alert.idle:
        idle = "\n".join(f"{e.slot} — {e.name} ({e.team})" for e in alert.idle)
        bench = "\n".join(
            f"{_slot_label(e.positions)} — {e.name} ({e.team}" + (f", {_when(e.games[0])}" if _when(e.games[0]) else "")
            + ")" for e in alert.bench)
        fields += [{"name": "In your lineup, no game today", "value": render._clip(idle), "inline": False},
                   {"name": "On your bench, playing today", "value": render._clip(bench), "inline": False}]
    if alert.resting:
        resting = "\n".join(f"{e.slot} — {e.name} ({e.team}): {why}" for e, why in alert.resting)
        lines = []
        for e in alert.starters:
            game = next((g for g in e.starts_in()), None)
            where = f"{'at' if game.home != e.team else 'vs'} {game.opponent(e.team)}" if game else ""
            detail = ", ".join(x for x in (_when(game), where) if x)
            lines.append(f"SP — {e.name} ({e.team}{', ' + detail if detail else ''})")
        fields += [{"name": "Your SP, not starting today", "value": render._clip(resting), "inline": False},
                   {"name": "Bench SP, starting today", "value": render._clip("\n".join(lines)), "inline": False}]
    note = (
        "*A starter has no MLB game today, or a starting pitcher in your lineup is not today's probable "
        "starter, while an eligible bench player plays. Players lock about one minute before their own game "
        "(5.3); in a doubleheader, at the first game.*"
    )
    payload = render._payload(ctx, f"Lineup Alert — {alert.team_name}", f"{render._header(ctx)}\n\n{note}", fields,
                              "LINEUP ALERT", source="FANTRAX + MLB SCHEDULE DATA")
    if user_id:
        payload["content"] = f"<@{user_id}>"
        payload["allowed_mentions"] = {"parse": [], "users": [user_id] if notify else []}
    return payload


# --- Run ----------------------------------------------------------------------

def alerted_today(state: dict[str, Any], today: date) -> set[str]:
    if state.get("date") != today.isoformat():
        return set()
    return {str(t) for t in state.get("alerted") or []}


def run(
    mode: str,
    all_teams: bool = False,
    *,
    now: datetime | None = None,
    league: dict[str, Any] | None = None,
    fx: Any = None,
    mlb_get: Any = None,
) -> int:
    cfg = league or load_league()
    tz: ZoneInfo = timezone_of(cfg)
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(tz).date()
    settings = cfg.get("lineup_alerts") or {}
    secret = str(settings.get("webhook") or DEFAULT_WEBHOOK)
    owners = owner_ids(cfg)
    include_all = all_teams and mode != "live"
    print(f"DBL LINEUP ALERTS mode={mode.upper()} date={today} opted_in_owners={len(owners)} all_teams={include_all}")

    if not owners and not include_all:
        print("RESULT: no owners have opted in (league.yaml owners); nothing to check")
        return 0

    games = mlb.fetch_schedule(today, today, mlb_get, hydrate=mlb.PROBABLES)
    playing = todays_games(games, today)
    print(f"MLB clubs playing today={len(playing)}")
    if not playing:
        print("NOTE    no MLB regular-season games today; nothing to check")
        return 0

    fx = fx or Fantrax(str(cfg["league_id"]), user_agent="DBL-Lineup-Alerts/2.0")
    rosters = fx.rosters()
    players = fx.player_ids()
    print(f"FANTRAX daily lineup period={rosters.get('period')}")

    ctx = render.Context(
        league_name=str(fx.league_info().get("leagueName") or ""),
        season_label=str(cfg.get("season_label") or ""),
        color=color_value(cfg.get("color")),
        test=(mode == "test"),
    )
    state = load_json(STATE_PATH, {}) if mode == "live" else {}
    done = alerted_today(state, today)

    errors = sent = 0
    for alert in find_alerts(rosters, players, playing, now):
        user = owner_for(alert, owners)
        label = f"{alert.team_name}: {alert.summary}"
        if not user and not include_all:
            print(f"SKIP    {label} (owner has not opted in)")
            continue
        if alert.team_id in done:
            print(f"SKIP    {label} (already alerted today)")
            continue
        payload = alert_payload(ctx, alert, user, notify=(mode == "live"))
        if mode == "preview":
            print(f"PREVIEW {label}:\n{json.dumps(payload, indent=2)}")
            continue
        ok, detail, _ = send_discord_webhook(secret, payload)
        if not ok:
            print(f"ERROR   {label}: {detail}")
            errors += 1
            continue
        sent += 1
        print(f"POSTED  {label}")
        if mode == "live":
            done.add(alert.team_id)
            save_json(STATE_PATH, {"date": today.isoformat(), "alerted": sorted(done), "updated_at": now.isoformat()})

    print(f"SUMMARY sent={sent} errors={errors}")
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("preview", "test", "live"), default="preview")
    parser.add_argument("--all-teams", action="store_true",
                        help="Preview/test: include franchises with no opted-in owner (never mentioned)")
    args = parser.parse_args()
    try:
        return run(args.mode, args.all_teams)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
