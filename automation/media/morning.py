#!/usr/bin/env python3
"""DBL Morning Recap: last night's MLB games in 📸│media, every morning.

The scheduler starts this once a day (08:30 ET, all year). For the previous
day's MLB games it posts, once:

  1. LAST NIGHT IN MLB: one line per final game (winner in bold; extra innings,
     games called early and doubleheader games marked) with the winning,
     losing and saving pitchers and links to the MLB.com recap and condensed
     game; postponed games are listed at the end.
  2. THE DBL HOME RUN REEL (only when a player on a DBL roster homered): one
     field per DBL franchise listing its players' home runs, each with a link
     to the MLB.com clip when MLB's game content has one.

Days without a final regular-season or postseason game post nothing. Links
only: nothing is downloaded or re-uploaded.

Data (all read-only):
  - MLB schedule for the day with linescore, decisions and scoring plays
    (automation/core/mlb.py): finals, innings, pitchers of record, and every
    home run (a home run is always a scoring play).
  - MLB game content for each final game (/api/v1/game/{gamePk}/content): the
    recap story, the condensed game and per-play clips; a home-run clip names
    its batter by MLB id. Content that cannot be read only drops that game's
    links.
  - Fantrax getTeamRosters + getPlayerIds for DBL ownership, matched with the
    Wire's roster matching (wire/roster.py): name, narrowed by MLB club; a
    name that could be two players is skipped.

State (state/morning_recap.json, kept on the automation-state branch) is keyed
by MLB date and records each part as it is posted, so a re-run never posts a
part twice and a failed part is retried on the next run. If Fantrax cannot be
read, the scores still go out, the day stays open and the run fails, so the
scheduler's retry posts the Home Run Reel.

Modes:
  preview  print the messages; no Discord, no state change
  test     post [TEST] copies; no state change
  live     post the day's messages once and record them
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
AUTOMATION = ROOT.parent
for folder in (AUTOMATION, AUTOMATION / "wire"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import roster  # noqa: E402  (wire/roster.py)
from core import mlb  # noqa: E402
from core.fantrax import Fantrax  # noqa: E402
from core.league import AVATAR, DEFAULT_LEAGUE_NAME, color_value, load_json, load_league, save_json, timezone_of  # noqa: E402
from discord_webhook import send_discord_webhook  # noqa: E402

STATE_PATH = ROOT / "state" / "morning_recap.json"
DEFAULT_WEBHOOK = "LEAGUE_WEBHOOK_MEDIA"
DEFAULT_POST_TIME = "08:30"
KEEP_DATES = 60

# The 📸│media channel's existing identity (the Wire's podcast posts).
USERNAME = "DBL News Wire"
FOOTER = "MORNING RECAP"
SCORE_SOURCE = "MLB DATA"
REEL_SOURCE = "MLB AND FANTRAX DATA"
COUNTED_TYPES = {mlb.REGULAR_SEASON} | set(mlb.POSTSEASON)

# Discord limits, with a little headroom.
DESCRIPTION_LIMIT = 4096
DESCRIPTION_BUDGET = 4000
EMBED_TOTAL_LIMIT = 6000
MESSAGE_BUDGET = 5800
FIELD_LIMIT = 1024
MAX_FIELDS = 25
MAX_EMBEDS = 10


# --- MLB data -------------------------------------------------------------------

@dataclass
class Night:
    finals: list[mlb.Game]
    postponed: list[mlb.Game]
    unfinished: int          # games still live or not yet played (suspended games excepted)


def read_night(raw: Any, day: date) -> Night:
    """Last night's counted games from a schedule response (with mlb.SCORES).

    Raises ValueError when the response has no dates list (mlb.parse_schedule),
    so an API change is noticed instead of looking like a day without games.
    """
    games = [g for g in mlb.parse_schedule(raw) if g.day == day and g.game_type in COUNTED_TYPES]
    finals = [g for g in games if g.final]
    return Night(
        finals=finals,
        postponed=[g for g in games if not g.played],
        unfinished=sum(1 for g in games if g.played and not g.final and not g.suspended),
    )


def read_media(games: list[mlb.Game], get: Callable[[str], Any]) -> dict[int, mlb.GameMedia]:
    """gamePk -> its video links; a game whose content cannot be read gets none."""
    media: dict[int, mlb.GameMedia] = {}
    for game in games:
        try:
            media[game.game_pk] = mlb.fetch_content(game.game_pk, get)
        except Exception as exc:
            print(f"CONTENT WARNING: {game.label} ({game.game_pk}) links unavailable: {exc}")
            media[game.game_pk] = mlb.GameMedia()
    return media


# --- DBL rosters and the Home Run Reel -------------------------------------------

@dataclass
class ReelLine:
    name: str      # last name
    full: str
    team: str
    clips: list[str] = field(default_factory=list)  # one entry per home run ("" = no clip)

    @property
    def homers(self) -> int:
        return len(self.clips)


@dataclass
class Franchise:
    name: str
    lines: dict[int, ReelLine] = field(default_factory=dict)

    @property
    def homers(self) -> int:
        return sum(line.homers for line in self.lines.values())


@dataclass
class Reel:
    franchises: dict[str, Franchise] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.franchises


class RosterReadError(RuntimeError):
    """Fantrax could not be read, so the Home Run Reel is unknown (not empty)."""


def load_index(fx: Any) -> roster.RosterIndex | None:
    """DBL roster index, or None when nobody is rostered.

    Raises RosterReadError when Fantrax cannot be read, so a failed read is
    never mistaken for empty rosters and the reel can be retried.
    """
    try:
        rosters = fx.rosters()
    except Exception as exc:
        raise RosterReadError(f"Fantrax roster read failed: {exc}") from exc
    block = rosters.get("rosters") if isinstance(rosters, dict) else None
    if not isinstance(block, dict):
        raise RosterReadError("Fantrax roster response has no rosters")
    if not any((team or {}).get("rosterItems") for team in block.values() if isinstance(team, dict)):
        print("HOME RUN REEL: no players on DBL rosters yet; reel skipped")
        return None
    try:
        players = fx.player_ids()
    except Exception as exc:
        raise RosterReadError(f"Fantrax player directory read failed: {exc}") from exc
    if not players:
        raise RosterReadError("Fantrax player directory came back empty")
    index = roster.build_index(rosters, mlb.normalize_directory(players))
    if index.empty:
        print("HOME RUN REEL: no rostered players found in the Fantrax player directory; reel skipped")
        return None
    print(f"HOME RUN REEL: {len(index.rostered_names)} rostered players indexed")
    return index


def _name_parts(name: str) -> tuple[str, str]:
    """(first, last), normalized, from Fantrax's "Last, First" or "First Last"."""
    if name.count(",") == 1:
        last, first = (part.strip() for part in name.split(",", 1))
    else:
        last = mlb.last_name(name)
        first = name[: len(name) - len(last)].strip() if name.endswith(last) else ""
    return roster.normalize_player_name(first), roster.normalize_player_name(last)


class Matcher:
    """The Wire's roster matching, plus one careful fallback for short names.

    MLB and Fantrax sometimes spell a first name differently ("Mike" /
    "Michael"). Only when no Fantrax player has MLB's exact name, a player is
    accepted if he is the only one on that club with the same last name and a
    first name starting with the same three letters.
    """

    def __init__(self, index: roster.RosterIndex) -> None:
        self.index = index
        self.by_team_last: dict[tuple[str, str], list[tuple[str, roster.Player]]] = {}
        for players in index.by_name.values():
            for player in players:
                first, last = _name_parts(player.name)
                self.by_team_last.setdefault((player.team, last), []).append((first, player))

    def match(self, name: str, team: str) -> roster.Player | None:
        player = self.index.match(name, team)
        if player is not None or self.index.by_name.get(roster.normalize_player_name(name)):
            return player
        first, last = _name_parts(name)
        key = (roster.normalize_team(team), last)
        if len(first) < 3 or not key[0]:
            return None
        found = [p for f, p in self.by_team_last.get(key, []) if f[:3] == first[:3]]
        return found[0] if len(found) == 1 and found[0].owner_id else None


def build_reel(games: list[mlb.Game], media: dict[int, mlb.GameMedia], index: roster.RosterIndex | None) -> Reel:
    reel = Reel()
    if index is None:
        return reel
    matcher = Matcher(index)
    for game in games:
        links = media.get(game.game_pk) or mlb.GameMedia()
        for batter_id, plays in mlb.home_runs(game).items():
            batter, team = plays[0].batter, plays[0].team
            player = matcher.match(batter.name, team)
            if player is None:
                continue
            clips = links.home_run_clips(batter_id)[: len(plays)]
            clips += [""] * (len(plays) - len(clips))
            franchise = reel.franchises.setdefault(player.owner_id, Franchise(player.owner_name))
            line = franchise.lines.setdefault(batter_id, ReelLine(mlb.last_name(batter.name), batter.name, team))
            line.clips.extend(clips)
    return reel


def _escape(text: str) -> str:
    """Keep names from turning into Discord formatting."""
    return re.sub(r"([*_`~|\\])", r"\\\1", text)


def _link(url: str) -> str:
    return url.replace(")", "%29").replace(" ", "%20")


def reel_line(line: ReelLine, *, full_name: bool = False) -> str:
    label = "HR" if line.homers == 1 else f"{line.homers} HR"
    links = " ".join(f"[▶]({_link(c)})" for c in line.clips if c)
    who = _escape(line.full if full_name else line.name)
    return f"{who} ({line.team}) — {label} {links}".rstrip()


def franchise_value(franchise: Franchise) -> str:
    lines = sorted(franchise.lines.values(), key=lambda l: (-l.homers, -sum(1 for c in l.clips if c), l.full))
    last_names = [(l.name, l.team) for l in lines]
    rows = [reel_line(l, full_name=last_names.count((l.name, l.team)) > 1) for l in lines]
    return clip_text("\n".join(rows), FIELD_LIMIT)


# --- Discord payloads -----------------------------------------------------------

def clip_text(text: str, limit: int) -> str:
    """Fit ``text`` in ``limit`` characters, cutting at a line break."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 2].rsplit("\n", 1)[0]
    return cut + "\n…"


def embed_size(embed: dict[str, Any]) -> int:
    size = len(embed.get("title") or "") + len(embed.get("description") or "")
    size += len((embed.get("footer") or {}).get("text") or "")
    size += len((embed.get("author") or {}).get("name") or "")
    for item in embed.get("fields") or []:
        size += len(item.get("name") or "") + len(item.get("value") or "")
    return size


def _message(embeds: list[dict[str, Any]]) -> dict[str, Any]:
    return {"username": USERNAME, "avatar_url": AVATAR, "allowed_mentions": {"parse": []}, "embeds": embeds}


def pack(embeds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group embeds into as few messages as Discord's per-message limits allow."""
    messages: list[list[dict[str, Any]]] = []
    for embed in embeds:
        if messages and len(messages[-1]) < MAX_EMBEDS and \
                sum(embed_size(e) for e in messages[-1]) + embed_size(embed) <= MESSAGE_BUDGET:
            messages[-1].append(embed)
        else:
            messages.append([embed])
    return [_message(group) for group in messages]


def _finish(embeds: list[dict[str, Any]], footer: str, now: datetime) -> list[dict[str, Any]]:
    """Footer and timestamp on the last embed only; '(continued)' titles after the first."""
    for i, embed in enumerate(embeds):
        if i:
            embed["title"] = embed["title"] + " (continued)"
    embeds[-1]["footer"] = {"text": footer}
    embeds[-1]["timestamp"] = now.isoformat()
    return embeds


@dataclass
class Look:
    league_name: str
    season_label: str
    color: int
    test: bool = False

    def title(self, text: str) -> str:
        return ("[TEST] " + text) if self.test else text

    @property
    def header(self) -> str:
        text = f"**{_escape(self.league_name or DEFAULT_LEAGUE_NAME)}**"
        return text + (f" • {self.season_label}" if self.season_label else "")


def _day(d: date) -> str:
    return f"{d:%a} {d:%b} {d.day}"


def game_line(game: mlb.Game, media: mlb.GameMedia | None = None) -> str:
    away, home = game.away_score or 0, game.home_score or 0
    if away >= home:
        winner, loser = (game.away, away), (game.home, home)
    else:
        winner, loser = (game.home, home), (game.away, away)
    text = f"**{winner[0]} {winner[1]}**, {loser[0]} {loser[1]}"
    notes = []
    if game.double_header in ("Y", "S"):
        notes.append(f"game {game.game_number}")
    if game.extra_innings:
        notes.append(f"{game.innings} inn.")
    elif game.shortened:
        notes.append(f"{game.innings} inn." + (f", {game.reason.lower()}" if game.reason else ""))
    if notes:
        text += f" ({', '.join(notes)})"
    decisions = [f"{label}: {_escape(mlb.last_name(p.name))}"
                 for label, p in (("W", game.winner), ("L", game.loser), ("S", game.save)) if p]
    media = media or mlb.GameMedia()
    links = [f"[{label}]({_link(url)})" for label, url in (("Recap", media.recap), ("Condensed", media.condensed)) if url]
    return " · ".join([text, *decisions, *links])


def postponed_line(game: mlb.Game) -> str:
    what = "Postponed" if game.postponed else "Cancelled"
    why = f" ({game.reason.lower()})" if game.reason else ""
    moved = f", made up {_day(game.moved_to)}" if game.moved_to else ""
    return f"{what}: {game.away} at {game.home}{why}{moved}"


def night_title(day: date) -> str:
    return f"LAST NIGHT IN MLB — {day.strftime('%A, %B')} {day.day}"


def summary_messages(look: Look, night: Night, media: dict[int, mlb.GameMedia], day: date,
                     now: datetime) -> list[dict[str, Any]]:
    games = night.finals
    postseason = all(g.game_type in mlb.POSTSEASON for g in games)
    noun = "postseason game" if postseason else "game"
    count = len(games)
    note = (f"*{count} {noun}{'' if count == 1 else 's'} final. "
            "Recap and Condensed open on MLB.com. W, L and S are the pitchers of record.*")
    title = look.title(night_title(day))
    chunks: list[list[str]] = [[]]
    used = len(look.header) + len(note) + 2
    lines = [game_line(g, media.get(g.game_pk)) for g in games] + [postponed_line(g) for g in night.postponed]
    for line in lines:
        if chunks[-1] and used + len(line) + 1 > DESCRIPTION_BUDGET:
            chunks.append([])
            used = 0
        chunks[-1].append(line)
        used += len(line) + 1
    embeds = []
    for i, block in enumerate(chunks):
        body = "\n".join(block)
        description = f"{look.header}\n{note}\n\n{body}" if i == 0 else body
        embeds.append({"title": title, "description": description[:DESCRIPTION_LIMIT], "color": look.color})
    return pack(_finish(embeds, f"{FOOTER} • {SCORE_SOURCE}", now))


def reel_messages(look: Look, reel: Reel, now: datetime) -> list[dict[str, Any]]:
    if reel.empty:
        return []
    ordered = sorted(reel.franchises.values(), key=lambda f: (-f.homers, f.name.lower()))
    fields = [{"name": clip_text(_escape(f.name), 256), "value": franchise_value(f), "inline": False}
              for f in ordered]
    title = look.title("THE DBL HOME RUN REEL")
    description = (f"{look.header}\n*Home runs last night by players on DBL rosters. "
                   "▶ opens the clip on MLB.com.*")
    footer = f"{FOOTER} • {REEL_SOURCE}"
    reserve = len(title) + len(" (continued)") + len(footer)
    embeds: list[dict[str, Any]] = []
    current: dict[str, Any] = {"title": title, "description": description, "color": look.color, "fields": []}
    for item in fields:
        size = len(item["name"]) + len(item["value"])
        if current["fields"] and (len(current["fields"]) >= MAX_FIELDS
                                  or embed_size(current) + size + reserve > MESSAGE_BUDGET):
            embeds.append(current)
            current = {"title": title, "color": look.color, "fields": []}
        current["fields"].append(item)
    embeds.append(current)
    return pack(_finish(embeds, footer, now))


# --- Run ------------------------------------------------------------------------

def _clock(text: Any, default: str) -> time:
    hour, minute = (int(part) for part in str(text or default).split(":", 1))
    return time(hour, minute)


def _prune(dates: dict[str, Any]) -> dict[str, Any]:
    return {key: dates[key] for key in sorted(dates)[-KEEP_DATES:]}


def run(
    mode: str,
    *,
    now: datetime | None = None,
    league: dict[str, Any] | None = None,
    fx: Any = None,
    get: Callable[[str], Any] | None = None,
    night: date | None = None,
) -> int:
    cfg = league or load_league()
    settings = cfg.get("morning_recap") or {}
    tz: ZoneInfo = timezone_of(cfg)
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(tz)
    day = night or (local.date() - timedelta(days=1))
    secret = str(settings.get("webhook") or DEFAULT_WEBHOOK)
    get = get or mlb.http_get_json
    print(f"DBL MORNING RECAP mode={mode.upper()} mlb_date={day} local_time={local:%Y-%m-%d %H:%M}")

    if mode == "live":
        if not settings.get("enabled", True):
            print("RESULT: morning_recap.enabled is false in league.yaml; nothing posted")
            return 0
        if day >= local.date():
            print(f"RESULT: {day} is not over yet; the Morning Recap covers finished days only")
            return 0
        post_time = _clock(settings.get("post_time"), DEFAULT_POST_TIME)
        if night is None and local.time() < post_time:
            print(f"RESULT: before {post_time:%H:%M}; nothing to post yet")
            return 0

    state = load_json(STATE_PATH, {}) if mode == "live" else {}
    dates = state.get("dates") if isinstance(state.get("dates"), dict) else {}
    record = dict(dates.get(day.isoformat()) or {})
    if mode == "live" and record.get("complete"):
        print(f"RESULT: the Morning Recap for {day} was already posted")
        return 0

    games = read_night(get(mlb.schedule_url(day, day, mlb.SCORES)), day)
    print(f"MLB final_games={len(games.finals)} postponed={len(games.postponed)} not_final={games.unfinished}")
    if not games.finals:
        print(f"RESULT: no final MLB games on {day}; nothing to post")
        return 0
    media = read_media(games.finals, get)
    print(f"MLB CONTENT recaps={sum(1 for m in media.values() if m.recap)} "
          f"condensed={sum(1 for m in media.values() if m.condensed)} clips={sum(len(m.clips) for m in media.values())}")

    fx = fx or Fantrax(str(cfg["league_id"]), user_agent="DBL-Morning-Recap/1.0", timeout=20)
    index = None
    reel_error = ""  # Fantrax could not be read: the reel is retried, not skipped
    if settings.get("include_home_run_reel", True):
        try:
            index = load_index(fx)
        except RosterReadError as exc:
            reel_error = str(exc)
            print(f"HOME RUN REEL WARNING: {reel_error}; no reel this run")
    reel = build_reel(games.finals, media, index)
    print(f"HOME RUN REEL franchises={len(reel.franchises)} homers={sum(f.homers for f in reel.franchises.values())}")
    try:
        league_name = str(fx.league_info().get("leagueName") or "")
    except Exception:
        league_name = ""

    look = Look(league_name, str(cfg.get("season_label") or ""), color_value(cfg.get("color")), test=(mode == "test"))
    summary = summary_messages(look, games, media, day, now)
    reel_posts = reel_messages(look, reel, now)

    if mode == "preview":
        for body in summary + reel_posts:
            print(json.dumps(body, indent=2, ensure_ascii=False))
        print(f"RESULT: preview only ({len(summary)} summary, {len(reel_posts)} home run reel messages)")
        return 0

    if mode == "test":
        failed = 0
        for body in summary + reel_posts:
            ok, detail, _ = send_discord_webhook(secret, body)
            print(f"{'POSTED' if ok else 'ERROR'} test message: {detail}")
            failed += 0 if ok else 1
        return 1 if failed else 0

    # live: post each part once, saving progress after every message.
    def save() -> None:
        dates[day.isoformat()] = record
        state["dates"] = _prune(dates)
        state["updated_at"] = now.isoformat()
        save_json(STATE_PATH, state)

    for part, bodies in (("summary", summary), ("reel", reel_posts)):
        done = int(record.get(part) or 0)
        for i, body in enumerate(bodies):
            if i < done:
                continue
            ok, detail, _ = send_discord_webhook(secret, body)
            if not ok:
                save()
                print(f"ERROR   {part} message {i + 1} of {len(bodies)} not posted: {detail}; retried next run")
                return 1
            record[part] = i + 1
            save()
            print(f"POSTED  {part} message {i + 1} of {len(bodies)}")

    if reel_error:
        # Not complete: the next run posts only what is still missing.
        save()
        print(f"ERROR   {reel_error}; the Home Run Reel will be retried next run")
        return 1

    record.update({"complete": True, "games": len(games.finals), "posted_at": now.isoformat()})
    save()
    print(f"RESULT: Morning Recap for {day} posted")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("preview", "test", "live"), default="preview")
    parser.add_argument("--date", default="", help="MLB date YYYY-MM-DD (default: yesterday)")
    args = parser.parse_args()
    night = None
    if args.date.strip():
        try:
            night = date.fromisoformat(args.date.strip())
        except ValueError:
            print(f"ERROR: --date must be YYYY-MM-DD, got {args.date!r}")
            return 1
    try:
        return run(args.mode, night=night)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
