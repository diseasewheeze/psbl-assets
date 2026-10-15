#!/usr/bin/env python3
"""PSBL Probable Pitchers: one live message per game day in ⚾│game-day.

During the regular season and playoffs the scheduler runs this several times
a day (automation/scheduler/schedule.yaml). The first run of the day (from
``post_from``) posts a "Probable Pitchers" message listing every MLB game
today with both clubs' probable starters as MLB has announced them, or "Not
announced". Starters on a PSBL roster show their PSBL team. Later runs edit that
same message (edits are silent, nobody is notified) when something changes: a
late scratch, a doubleheader's second starter named, a postponement. After
the last game of the day starts, the message is left as it is.

Pitcher starts count against the weekly cap (9.2), so this helps with daily
lineups (9.1). It is information only: Fantrax decides what counts.

Data (all read-only):
  - MLB schedule for today with probable pitchers (automation/core/mlb.py).
  - Fantrax getTeamRosters + getPlayerIds, for the PSBL tags (wire/roster.py
    matching by name and club: a name is only tagged when it identifies one
    player). If Fantrax cannot be read, the message posts without tags.

Modes:
  preview  print the message; no Discord, no state change
  test     post a new [TEST] message; no state change
  live     post or edit today's message and record it
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
AUTOMATION = ROOT.parent
for folder in (AUTOMATION, AUTOMATION / "competition", AUTOMATION / "wire"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import render  # noqa: E402  (competition/render.py)
import roster  # noqa: E402  (wire/roster.py)
from core import mlb  # noqa: E402
from core.fantrax import Fantrax  # noqa: E402
from core.league import color_value, load_json, load_league, save_json, timezone_of  # noqa: E402
from discord_webhook import send_discord_webhook, upsert_discord_message  # noqa: E402

STATE_PATH = ROOT / "state" / "probable_pitchers.json"
DEFAULT_WEBHOOK = "LEAGUE_WEBHOOK_GAME_DAY"
DEFAULT_POST_FROM = "09:00"
PAGE_URL = "https://www.mlb.com/probable-pitchers/{day}"
SOURCE = "MLB DATA"
COUNTED_TYPES = {mlb.REGULAR_SEASON} | set(mlb.POSTSEASON)


def todays_games(games: list[mlb.Game], day: date) -> list[mlb.Game]:
    """Today's regular-season and postseason listings (postponed ones too), first pitch first."""
    found = [g for g in games if g.day == day and g.game_type in COUNTED_TYPES]
    return sorted(found, key=lambda g: (g.start or datetime.max.replace(tzinfo=timezone.utc), g.game_number, g.away))


# --- PSBL rosters ---------------------------------------------------------------

def load_index(fx: Any) -> roster.RosterIndex | None:
    try:
        rosters = fx.rosters()
        players = fx.player_ids()
    except Exception as exc:
        print(f"ROSTER TAGS WARNING: Fantrax read failed, posting without PSBL tags: {exc}")
        return None
    index = roster.build_index(rosters, mlb.normalize_directory(players))
    print(f"ROSTER TAGS: {len(index.rostered_names)} rostered players indexed")
    return index


def owners(games: list[mlb.Game], index: roster.RosterIndex | None) -> dict[int, str]:
    """MLB pitcher id -> PSBL team, for announced starters on a PSBL roster."""
    if index is None:
        return {}
    tags: dict[int, str] = {}
    for game in games:
        for team in game.teams:
            pitcher = game.probable(team)
            if pitcher is None:
                continue
            player = index.match(pitcher.name, team)
            if player is not None:
                tags[pitcher.player_id] = player.owner_name
    return tags


# --- Discord --------------------------------------------------------------------

def _day(d: date) -> str:
    return f"{d:%a} {d:%b} {d.day}"


def _line(game: mlb.Game, team: str, tags: dict[int, str]) -> str:
    pitcher = game.probable(team)
    text = f"**{team}** {pitcher.name if pitcher else 'Not announced'}"
    if pitcher is not None and pitcher.player_id in tags:
        text += f" • *{tags[pitcher.player_id]}*"
    return text


def game_value(game: mlb.Game, tags: dict[int, str], now: datetime) -> str:
    if not game.played:
        what = "Postponed" if game.postponed else "Cancelled"
        why = f" ({game.reason})" if game.reason else ""
        moved = f", made up {_day(game.moved_to)}" if game.moved_to else ""
        return f"{what}{why}{moved}"
    if game.start is not None:
        when = f"<t:{int(game.start.timestamp())}:t>"
        if game.start <= now:
            when += " • under way"
    else:
        when = "Time TBA" if game.game_number == 1 else "After game 1"
    return render._clip(f"{when}\n{_line(game, game.away, tags)}\n{_line(game, game.home, tags)}")


def announced(games: list[mlb.Game]) -> tuple[int, int]:
    """(announced starters, starters needed) over the games still being played."""
    played = [g for g in games if g.played]
    named = sum(g.probable(team) is not None for g in played for team in g.teams)
    return named, 2 * len(played)


def payload(ctx: render.Context, games: list[mlb.Game], day: date, tags: dict[int, str],
            now: datetime) -> dict[str, Any]:
    named, total = announced(games)
    fields = [{"name": game.label, "value": game_value(game, tags, now), "inline": False} for game in games]
    description = (
        f"{render._header(ctx)}\n\n"
        f"**{named} of {total} starters announced** • updated <t:{int(now.timestamp())}:R>\n"
        "*Probable starters as MLB has announced them. This message updates until the last game starts. "
        f"Pitchers on a PSBL roster show their PSBL team.* Source: [MLB.com]({PAGE_URL.format(day=day.isoformat())})"
    )
    title = f"Probable Pitchers — {day.strftime('%A, %B')} {day.day}"
    return render._payload(ctx, title, description, fields[:25], "PROBABLE PITCHERS", source=SOURCE)


def fingerprint(games: list[mlb.Game], tags: dict[int, str]) -> str:
    rows = []
    for g in games:
        sides = [(p.player_id, tags.get(p.player_id, "")) if (p := g.probable(t)) else None for t in g.teams]
        rows.append([g.label, g.start.isoformat() if g.start else "", g.state, sides])
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()[:16]


# --- Run ------------------------------------------------------------------------

def _post_from(settings: dict[str, Any]) -> time:
    text = str(settings.get("post_from") or DEFAULT_POST_FROM)
    hour, minute = (int(part) for part in text.split(":", 1))
    return time(hour, minute)


def run(
    mode: str,
    *,
    now: datetime | None = None,
    league: dict[str, Any] | None = None,
    fx: Any = None,
    get: Callable[[str], Any] | None = None,
) -> int:
    cfg = league or load_league()
    tz: ZoneInfo = timezone_of(cfg)
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(tz)
    day = local.date()
    settings = cfg.get("probable_pitchers") or {}
    secret = str(settings.get("webhook") or DEFAULT_WEBHOOK)
    print(f"PSBL PROBABLE PITCHERS mode={mode.upper()} date={day} local_time={local:%H:%M}")

    if mode == "live" and local.time() < _post_from(settings):
        print(f"RESULT: before {_post_from(settings):%H:%M}; nothing to post yet")
        return 0

    games = todays_games(mlb.fetch_schedule(day, day, get, hydrate=mlb.PROBABLES), day)
    if not games:
        print("RESULT: MLB lists no games today; nothing to post")
        return 0
    upcoming = [g for g in games if g.played and (g.start is None or g.start > now)]
    named, total = announced(games)
    print(f"MLB games={len(games)} not_started={len(upcoming)} announced={named}/{total}")

    state = load_json(STATE_PATH, {}) if mode == "live" else {}
    if state.get("date") != day.isoformat():
        state = {}
    if mode == "live" and not upcoming:
        print("RESULT: every game has started; today's message is final")
        return 0

    fx = fx or Fantrax(str(cfg["league_id"]), user_agent="PSBL-Probable-Pitchers/1.0")
    tags = owners(games, load_index(fx))
    print(f"PSBL TAGS starters_on_psbl_rosters={len(tags)}")
    try:
        league_name = str(fx.league_info().get("leagueName") or "")
    except Exception:
        league_name = ""
    ctx = render.Context(
        league_name=league_name,
        season_label=str(cfg.get("season_label") or ""),
        color=color_value(cfg.get("color")),
        test=(mode == "test"),
    )
    body = payload(ctx, games, day, tags, now)

    if mode == "preview":
        print(json.dumps(body, indent=2, ensure_ascii=False))
        return 0
    if mode == "test":
        ok, detail, _ = send_discord_webhook(secret, body)
        print(f"{'POSTED' if ok else 'ERROR'} test message: {detail}")
        return 0 if ok else 1

    fp = fingerprint(games, tags)
    if state.get("message_id") and fp == state.get("fingerprint"):
        print("UNCHANGED no new probable starters since the last update")
        return 0
    ok, detail, new_id, how = upsert_discord_message(secret, body, state.get("message_id"))
    if not ok:
        print(f"ERROR   {detail}")
        return 1
    save_json(STATE_PATH, {"date": day.isoformat(), "message_id": new_id, "fingerprint": fp,
                           "updated_at": now.isoformat()})
    print(f"{how.upper():8} probable pitchers for {day}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("preview", "test", "live"), default="preview")
    args = parser.parse_args()
    try:
        return run(args.mode)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
