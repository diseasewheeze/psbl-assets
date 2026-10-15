"""Discord payloads for DBL Competition Desk posts.

Layouts follow automation/DISCORD_AUTOMATION_STYLE.md and keep the approved
scoreboard / standings / recap / playoff race / preview formats: DBL
Competition Desk sender, gold accent, vertical fields, no emoji, short footer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from core import sport
from core.league import AVATAR, DEFAULT_LEAGUE_NAME
from core.season import Period, calendar_weeks
from weekly import luck_extremes


@dataclass
class Context:
    league_name: str
    season_label: str
    color: int
    test: bool = False


def _fmt_score(value: float) -> str:
    return f"{value:.2f}"


def _fmt_gp(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def _fmt_gb(value: float) -> str:
    if abs(value) < 0.0001:
        return "—"
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def window(p: Period | None) -> str:
    if not p:
        return ""
    return f"<t:{int(p.start.timestamp())}:D> – <t:{int(p.end.timestamp())}:D>"


def _header(ctx: Context, p: Period | None = None) -> str:
    text = f"**{ctx.league_name or DEFAULT_LEAGUE_NAME}**"
    if ctx.season_label:
        text += f" • {ctx.season_label}"
    if p:
        text += f"\n**Scoring Period:** {window(p)}"
    return text


FANTRAX_SOURCE = "FANTRAX READ-ONLY DATA"
MLB_SOURCE = "MLB SCHEDULE DATA"
FIELD_LIMIT = 1024


def _clip(text: str, limit: int = FIELD_LIMIT) -> str:
    """Keep a field value inside Discord's limit, cutting at a line break."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 2].rsplit("\n", 1)[0]
    return cut + "\n…"


def _payload(
    ctx: Context,
    title: str,
    description: str,
    fields: list[dict],
    footer: str,
    *,
    source: str = FANTRAX_SOURCE,
) -> dict[str, Any]:
    return {
        "username": "DBL Competition Desk",
        "avatar_url": AVATAR,
        "allowed_mentions": {"parse": []},
        "embeds": [{
            "title": ("[TEST] " + title) if ctx.test else title,
            "description": description,
            "fields": fields[:25],
            "color": ctx.color,
            "footer": {"text": f"{footer} • {source}"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }


# --- Scoreboard ---------------------------------------------------------------

# Fantrax's matchup category for games started by pitchers. The MLB short name
# is not checked yet (the Fantrax test league is a hockey league, where GS is
# goalie starts); check it with tools/fantrax_probe.py once the MLB league exists.
STARTS_CATEGORY = "GS"


def start_cap(p: Period) -> int:
    """Credited pitcher starts in a period: sport.PITCHER_STARTS_PER_WEEK per
    calendar week it spans (7, or 14 for the two-week Championship; 9.2, 9.3)."""
    return sport.PITCHER_STARTS_PER_WEEK * calendar_weeks(p)


def pitcher_starts(team: dict, cap: int | None) -> int | None:
    """Credited pitcher starts (Fantrax category GS), or None if not shown."""
    if not cap:
        return None
    categories = team.get("categories") or {}
    if STARTS_CATEGORY not in categories:
        return None
    return int(categories[STARTS_CATEGORY])


def scoreboard_fields(rows: list[dict], start_cap: int | None = None) -> list[dict]:
    def starts(team: dict) -> str:
        used = pitcher_starts(team, start_cap)
        return "" if used is None else f" • Pitcher starts: {used} of {start_cap}"

    fields = []
    for index, row in enumerate(rows, start=1):
        away, home = row["away"], row["home"]
        a, h = _fmt_score(away["score"]), _fmt_score(home["score"])
        if away["score"] > home["score"]:
            a_text, h_text = f"**{a} pts**", f"{h} pts"
        elif home["score"] > away["score"]:
            a_text, h_text = f"{a} pts", f"**{h} pts**"
        else:
            a_text, h_text = f"{a} pts", f"{h} pts"
        fields.append({
            "name": f"Matchup {index}",
            "value": (
                f"**{away['teamName']}** *(Away)* — {a_text} • `{_fmt_gp(away['gamesPlayed'])} GP`{starts(away)}\n"
                f"**{home['teamName']}** *(Home)* — {h_text} • `{_fmt_gp(home['gamesPlayed'])} GP`{starts(home)}"
            ),
            "inline": False,
        })
    return fields


def scoreboard(
    ctx: Context,
    p: Period,
    rows: list[dict],
    *,
    final: bool,
    playoffs: bool,
    start_cap: int | None = None,
) -> dict[str, Any]:
    label = "Playoffs " if playoffs else ""
    title = f"DBL {label}Week {p.number} {'Final ' if final else ''}Scoreboard"
    if final:
        note = "*Final scores for the week, from Fantrax. The winning score is bolded.*"
    else:
        note = (
            "*Live scoreboard from Fantrax. This post updates through the week; "
            "the leading score is bolded.*"
        )
    if start_cap:
        note += f"\n*Pitcher starts are credited up to {start_cap} this week (9.2, 9.3).*"
    return _payload(ctx, title, f"{_header(ctx, p)}\n\n{note}", scoreboard_fields(rows, start_cap), "SCOREBOARD")


# --- Weekly recap -------------------------------------------------------------

def recap_fields(rows: list[dict]) -> list[dict]:
    fields = []
    for index, row in enumerate(rows, start=1):
        away, home = row["away"], row["home"]
        a, h = _fmt_score(away["score"]), _fmt_score(home["score"])
        margin = abs(away["score"] - home["score"])
        if away["score"] > home["score"]:
            a_text, h_text = f"**{a} pts**", f"{h} pts"
            result = f"Result: **{away['teamName']}** wins by {margin:.2f} pts"
        elif home["score"] > away["score"]:
            a_text, h_text = f"{a} pts", f"**{h} pts**"
            result = f"Result: **{home['teamName']}** wins by {margin:.2f} pts"
        else:
            a_text, h_text = f"{a} pts", f"{h} pts"
            result = "Result: Tie"
        fields.append({
            "name": f"Matchup {index}",
            "value": (
                f"**{away['teamName']}** *(Away)* — {a_text} • `{_fmt_gp(away['gamesPlayed'])} GP`\n"
                f"**{home['teamName']}** *(Home)* — {h_text} • `{_fmt_gp(home['gamesPlayed'])} GP`\n"
                f"{result}"
            ),
            "inline": False,
        })
    return fields


def all_play_field(rows: list[dict], week: dict[str, Any], season: dict[str, Any]) -> dict | None:
    """One field: each team's all-play record this week and for the season.

    ``week`` and ``season`` map teamId -> weekly.Record.
    """
    if not week:
        return None
    names = {t["teamId"]: t["teamName"] for row in rows for t in (row["away"], row["home"])}
    order = sorted(
        week,
        key=lambda tid: (-week[tid].wins, -week[tid].ties, -(season[tid].wins if tid in season else 0),
                         names.get(tid, "").lower()),
    )
    lines = []
    for tid in order:
        line = f"**{names.get(tid, 'Unknown Team')}** — {week[tid].text()}"
        if tid in season:
            line += f" • Season {season[tid].text()}"
        lines.append(line)
    return {"name": "All-Play", "value": _clip("\n".join(lines)), "inline": False}


def recap(
    ctx: Context,
    p: Period,
    rows: list[dict],
    *,
    all_play_week: dict[str, Any] | None = None,
    all_play_season: dict[str, Any] | None = None,
) -> dict[str, Any]:
    note = "*Completed matchup results pulled directly from Fantrax.*"
    fields = recap_fields(rows)
    extra = all_play_field(rows, all_play_week or {}, all_play_season or {})
    if extra:
        others = len(all_play_week or {}) - 1
        note += f"\n*All-play: each team's record had it played all {others} other teams this week.*"
        fields.append(extra)
    return _payload(ctx, f"DBL Week {p.number} Recap", f"{_header(ctx, p)}\n\n{note}", fields, "WEEKLY RECAP")


# --- Weekly awards ------------------------------------------------------------

def _team_score(team: dict) -> str:
    return f"**{team['teamName']}** — {_fmt_score(team['score'])} pts"


def _game(result: Any) -> str:
    w, l = result.winner, result.loser
    return (
        f"**{w['teamName']}** {_fmt_score(w['score'])} – {l['teamName']} {_fmt_score(l['score'])} • "
        f"{result.margin:.2f}-point margin"
    )


def awards(ctx: Context, p: Period, result: Any) -> dict[str, Any] | None:
    """Weekly Awards post from weekly.weekly_awards(); None if nothing to award."""
    if result.empty:
        return None
    fields = [
        {"name": label, "value": _team_score(team), "inline": False}
        for label, team in zip(("First Star", "Second Star", "Third Star"), result.stars)
    ]
    if result.tough_luck:
        r = result.tough_luck
        fields.append({
            "name": "Tough Luck",
            "value": f"{_team_score(r.loser)} in a loss to {r.winner['teamName']} ({_fmt_score(r.winner['score'])})",
            "inline": False,
        })
    if result.lucky_win:
        r = result.lucky_win
        fields.append({
            "name": "Lucky Win",
            "value": f"{_team_score(r.winner)} in a win over {r.loser['teamName']} ({_fmt_score(r.loser['score'])})",
            "inline": False,
        })
    if result.closest:
        fields.append({"name": "Closest Game", "value": _game(result.closest), "inline": False})
    if result.blowout:
        fields.append({"name": "Biggest Blowout", "value": _game(result.blowout), "inline": False})
    note = (
        "*From this week's final Fantrax scores. Stars are the top three scores; Tough Luck is the "
        "highest score in a loss and Lucky Win the lowest score in a win.*"
    )
    return _payload(ctx, f"DBL Week {p.number} Awards", f"{_header(ctx, p)}\n\n{note}", fields, "WEEKLY AWARDS")


# --- Power rankings -----------------------------------------------------------

def _change(row: Any, has_previous: bool) -> str:
    if not has_previous:
        return "—"
    if row.change is None:
        return "New"
    if row.change > 0:
        return f"Up {row.change}"
    if row.change < 0:
        return f"Down {-row.change}"
    return "Same"


def fmt_luck(value: float) -> str:
    """Luck to one decimal with its sign: +1.4, -0.6, 0.0."""
    shown = round(value, 1)
    return "0.0" if shown == 0 else f"{shown:+.1f}"


def _names(rows: list[Any]) -> str:
    names = [r.team_name for r in rows]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def luck_line(rows: list[Any]) -> str:
    """One line naming the luckiest and unluckiest teams ("" when all equal)."""
    high, low = luck_extremes(rows)
    if not high or not low:
        return ""
    return (f"**Luckiest:** {_names(high)} ({fmt_luck(high[0].luck)}) • "
            f"**Unluckiest:** {_names(low)} ({fmt_luck(low[0].luck)})")


def power_rankings(ctx: Context, after_week: int, rows: list[Any], *, has_previous: bool) -> dict[str, Any] | None:
    """Power Rankings post from weekly.power_rankings(); None if no results yet."""
    if not rows:
        return None
    fields = [
        {
            "name": f"{row.rank}. {row.team_name}",
            "value": (
                f"**Change:** {_change(row, has_previous)} • "
                f"**Record:** {row.record.text()} • "
                f"**PF:** {row.points_for:.2f} • "
                f"**All-Play:** {row.all_play.text()} • "
                f"**Luck:** {fmt_luck(row.luck)} • "
                f"**Score:** {row.score:.3f}"
            ),
            "inline": False,
        }
        for row in rows
    ]
    note = (
        "*Results only. Score = 50% season points-for + 30% points-for over the last 3 weeks + "
        "20% season all-play win %. Both points-for figures are scaled 0 to 1 across the league "
        "(lowest team 0, highest 1). Change is against last week's rankings. Luck = actual wins minus "
        "expected wins, where expected wins add up each week's all-play win share (ties count half); "
        "it is not part of the score.*"
    )
    extremes = luck_line(rows)
    if extremes:
        note += f"\n{extremes}"
    return _payload(ctx, f"DBL Power Rankings — After Week {after_week}", f"{_header(ctx)}\n\n{note}",
                    fields, "POWER RANKINGS")


# --- Standings ----------------------------------------------------------------

def standings(ctx: Context, rows: list[dict], *, after_week: int, playoff_cut: int, final: bool) -> dict[str, Any]:
    fields = []
    for row in rows:
        title = f"{row['rank']}. {row['teamName']}"
        if row["rank"] == playoff_cut:
            title += " — Playoff Cut"
        fields.append({
            "name": title,
            "value": (
                f"**Record:** {row['record']} • "
                f"**PF:** {row['pointsFor']:.2f} • "
                f"**GB:** {_fmt_gb(row['gamesBack'])}"
            ),
            "inline": False,
        })
    if final:
        title = "DBL Final Regular-Season Standings"
        note = f"*Final regular-season standings from Fantrax. The top {playoff_cut} teams qualify for the playoffs.*"
    else:
        title = f"DBL League Standings — After Week {after_week}"
        note = f"*Standings pulled directly from Fantrax. The top {playoff_cut} teams currently occupy playoff positions.*"
    return _payload(ctx, title, f"{_header(ctx)}\n\n{note}", fields, "STANDINGS")


# --- Wooden Spoon -------------------------------------------------------------

def wooden_spoon(ctx: Context, row: dict, owner_id: str = "") -> dict[str, Any]:
    """The last-place franchise takes the Wooden Spoon (league tradition, no penalty)."""
    holder = f"<@{owner_id}>" if owner_id else "Its owner"
    fields = [
        {"name": "Final record", "value": f"{row['record']} • {row['pointsFor']:.2f} points for", "inline": False},
        {"name": "The tradition", "value": f"{holder} holds the Wooden Spoon role for the Offseason and writes the "
                                           "preview of next Season, posted before Week 1.", "inline": False},
        {"name": "No penalty", "value": "Draft order is unaffected: it comes from Potential Points (14.5).", "inline": False},
    ]
    note = f"**{row['teamName']}** finishes last in the regular season and takes home the Wooden Spoon."
    payload = _payload(ctx, "The Wooden Spoon", f"{_header(ctx)}\n\n{note}", fields, "WOODEN SPOON")
    if owner_id:
        payload["content"] = f"<@{owner_id}>"
        payload["allowed_mentions"] = {"parse": [], "users": [] if ctx.test else [owner_id]}
    return payload


# --- Playoff race -------------------------------------------------------------

def playoff_race(
    ctx: Context,
    rows: list[dict],
    *,
    after_week: int,
    weeks_left: int,
    playoff_cut: int,
    bubble_depth: int,
) -> dict[str, Any]:
    limit = min(len(rows), playoff_cut + bubble_depth)
    fields = []
    for row in rows[:limit]:
        title = f"{row['rank']}. {row['teamName']}"
        if row["rank"] == playoff_cut:
            title += " — Playoff Cut"
        fields.append({
            "name": title,
            "value": (
                f"**Record:** {row['record']} • "
                f"**PF:** {row['pointsFor']:.2f} • "
                f"**GB:** {_fmt_gb(row['gamesBack'])}"
            ),
            "inline": False,
        })
    left = f"{weeks_left} week{'s' if weeks_left != 1 else ''} left in the regular season"
    note = (
        f"*After Week {after_week} — {left}. The top {playoff_cut} teams currently "
        f"occupy playoff positions; the next {bubble_depth} are on the bubble.*"
    )
    return _payload(ctx, "DBL Playoff Race", f"{_header(ctx)}\n\n{note}", fields, "PLAYOFF RACE")


# --- Matchup preview ----------------------------------------------------------

def projected_line(away: Any, home: Any) -> str:
    """ "Projected games: 68 vs 61 • Probable starts: 6 vs 4 • Light-day games: 12 vs 9" (away first)."""
    return (f"Projected games: {away.games} vs {home.games} • "
            f"Probable starts: {away.starts} vs {home.starts} • "
            f"Light-day games: {away.light_games} vs {home.light_games}")


def preview(
    ctx: Context,
    p: Period,
    pairs: list[dict],
    records: dict[str, dict],
    *,
    ranks_shown: bool,
    projections: dict[str, Any] | None = None,
    start_cap: int | None = None,
    light_max: int | None = None,
) -> dict[str, Any]:
    """Matchup preview. ``projections`` (teamId -> edge.Projection) adds each
    matchup's schedule edge; matchups missing either team simply go without."""
    def line(team: dict) -> str:
        meta = records.get(team.get("teamId", ""), {})
        record = meta.get("record") or "0-0-0"
        if ranks_shown and meta.get("rank"):
            return f"**{team.get('teamName', 'TBD')}** — #{meta['rank']} • {record}"
        return f"**{team.get('teamName', 'TBD')}** — {record}"

    projections = projections or {}
    shown = False
    fields = []
    for i, m in enumerate(pairs, start=1):
        value = f"{line(m['away'])}\nvs\n{line(m['home'])}"
        away, home = projections.get(m["away"].get("teamId", "")), projections.get(m["home"].get("teamId", ""))
        if away is not None and home is not None:
            value += "\n" + projected_line(away, home)
            shown = True
        fields.append({"name": f"Matchup {i}", "value": value, "inline": False})
    standing_note = "current Fantrax standing and record" if ranks_shown else "record including last week"
    note = (
        f"*This week's matchups with each team's {standing_note}. "
        "The scoreboard will track scoring once the week is underway.*"
    )
    if shown:
        cap = f", capped at {start_cap}" if start_cap else ""
        light = f" ({light_max} or fewer MLB teams playing)" if light_max else ""
        note += (
            "\n*Projected games: hitter lineup slots each current roster can fill on this week's MLB days "
            "(a doubleheader counts twice; minors and IL left out), plus starts by its starting pitchers "
            f"where MLB has announced them{cap}. Light-day games: the same count on light days{light}.*"
        )
    return _payload(ctx, f"DBL Week {p.number} Matchup Preview", f"{_header(ctx, p)}\n\n{note}", fields, "SCOREBOARD")


# --- MLB games grid -----------------------------------------------------------

def _day(d: date) -> str:
    return f"{d:%a} {d:%b} {d.day}"


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _days(days: list[tuple[date, int, int]]) -> str:
    if not days:
        return "None this week."
    return "\n".join(f"{_day(day)} — {_count(games, 'game')}, {teams} teams" for day, teams, games in days)


def games_grid(ctx: Context, p: Period, grid: Any) -> dict[str, Any]:
    """MLB games grid for one Fantrax week (core.mlb.WeekGrid)."""
    fields = []
    for count, teams in grid.by_count():
        label = "No Games" if count == 0 else _count(count, "Game")
        fields.append({"name": label, "value": _clip(", ".join(teams)), "inline": False})
    doubles = [f"{_day(day)} — {game.away} at {game.home}" + (" (makeup)" if game.makeup_of else "")
               for day, game in grid.doubleheaders]
    fields.append({"name": "Doubleheaders", "value": _clip("\n".join(doubles) or "None this week."), "inline": False})
    off = [f"{_day(day)} — " + (f"{len(teams)} teams: " if len(teams) > 4 else "") + ", ".join(teams)
           for day, teams in grid.off_days]
    fields.append({"name": "Off Days", "value": _clip("\n".join(off) or "None this week."), "inline": False})
    fields.append({"name": f"Light Days ({grid.light_max} or fewer teams)", "value": _clip(_days(grid.light_days)),
                   "inline": False})
    fields.append({"name": f"Heavy Days ({grid.heavy_min} or more teams)", "value": _clip(_days(grid.heavy_days)),
                   "inline": False})
    two = [f"**{team}:** {pitcher.name} ({', '.join(_day(d) for d in days)})" for team, pitcher, days in grid.two_start]
    fields.append({"name": "Two-Start Pitchers", "value": _clip("\n".join(two) or "None announced yet."),
                   "inline": False})
    if grid.postponed:
        lines = []
        for game in grid.postponed:
            why = f" ({game.reason})" if game.reason else ""
            moved = f", made up {_day(game.moved_to)}" if game.moved_to else ""
            lines.append(f"{_day(game.day)} — {game.away} at {game.home}{why}{moved}")
        fields.append({"name": "Postponed", "value": _clip("\n".join(lines)), "inline": False})
    note = (
        f"*MLB regular-season games in this Fantrax week ({_count(grid.total_games, 'game')}), to help plan daily "
        "lineups. A doubleheader counts as two games; a postponed game counts when it is made up. Two-start "
        "pitchers are listed only where MLB has announced both starts. Lineups lock about one minute before "
        "each player's game (5.3).*"
    )
    return _payload(ctx, f"DBL Week {p.number} MLB Games Grid", f"{_header(ctx, p)}\n\n{note}", fields,
                    "MLB GAMES GRID", source=MLB_SOURCE)


# --- Monthly awards -------------------------------------------------------------

MONTHLY_ROLE = "📅 Manager of the Month"


def _week_span(weeks: list[int] | tuple[int, ...]) -> str:
    if not weeks:
        return "no weeks"
    if len(weeks) == 1:
        return f"Week {weeks[0]}"
    return f"Weeks {weeks[0]}–{weeks[-1]}"


def _winners(winners: list[Any], text: Any) -> str:
    return "\n".join(f"**{w.team_name}** — {text(w)}" for w in winners)


def _together(names: list[str]) -> str:
    bolded = [f"**{n}**" for n in names]
    return bolded[0] if len(bolded) == 1 else ", ".join(bolded[:-1]) + " and " + bolded[-1]


def monthly_awards(
    ctx: Context,
    group: Any,
    span: Period,
    result: Any,
    *,
    month_to_date: bool = False,
) -> dict[str, Any] | None:
    """Monthly Awards post (monthly.MonthGroup + monthly.MonthlyAwards); None if nothing was played."""
    if result.empty:
        return None
    fields = [
        {"name": "Manager of the Month",
         "value": _winners(result.manager, lambda w: f"{_fmt_score(w.value)} pts"), "inline": False},
    ]
    if result.record:
        fields.append({"name": "Best Record of the Month", "value": _winners(
            result.record, lambda w: f"{w.record.text()} • {_fmt_score(w.total)} pts"), "inline": False})
    if result.big_week:
        fields.append({"name": "Biggest Single Week", "value": _winners(
            result.big_week, lambda w: f"{_fmt_score(w.value)} pts in Week {w.week}"), "inline": False})
    if result.hard_luck:
        fields.append({"name": "Hard Luck", "value": _winners(
            result.hard_luck,
            lambda w: f"{_fmt_score(w.value)} pts in {w.losses} loss{'es' if w.losses != 1 else ''}"), "inline": False})

    holders = _together([w.team_name for w in result.manager])
    verb = "holds" if len(result.manager) == 1 else "share"
    until = "the first Monthly Awards of next Season" if group.final else "next month's award"
    if month_to_date:
        role = f"Month to date. The award is decided when the last week ending in {group.month} is final."
    else:
        role = f"{holders} {verb} the {MONTHLY_ROLE} role until {until}. The Commissioner assigns the role."
    fields.append({"name": "The Role", "value": role, "inline": False})

    weeks = _week_span(result.weeks)
    note = (
        f"*{weeks}: the fantasy weeks that ended in {group.month}, from final Fantrax matchup scores. "
        "Hard Luck is the most points scored in losses. Ties go to more total points for the month, "
        "then are shared.*"
    )
    title = f"DBL Monthly Awards — {group.label}" + (" (Month to Date)" if month_to_date else "")
    return _payload(ctx, title, f"{_header(ctx, span)}\n\n{note}", fields, "MONTHLY AWARDS")


# --- Bounties -------------------------------------------------------------------

def _claim_value(bounty: Any, claim: Any) -> str:
    names = _together([t.get("teamName") or "Unknown Team" for t in claim.teams])
    lines = [f"{names} — {claim.detail}"]
    if bounty.description:
        lines.append(bounty.description)
    shared = " (shared)" if len(claim.teams) > 1 else ""
    lines.append(f"**Reward:** {bounty.reward}{shared}. The Commissioner assigns it.")
    return "\n".join(lines)


def bounties(
    ctx: Context,
    claims: list[tuple[Any, Any]],
    still_open: list[tuple[Any, str]],
    *,
    mlb_data: bool = False,
) -> dict[str, Any] | None:
    """Bounty post: claims [(Bounty, Claim)] plus the bounties still open
    [(Bounty, progress text)]. Without claims it is the Bounty Board."""
    if not claims and not still_open:
        return None
    fields = [{"name": bounty.title, "value": _clip(_claim_value(bounty, claim)), "inline": False}
              for bounty, claim in claims]
    if still_open:
        lines = []
        for bounty, status in still_open:
            line = f"**{bounty.title}** — {bounty.description}" if bounty.description else f"**{bounty.title}**"
            lines.append(line + (f"\n{status}" if status else ""))
        fields.append({"name": "Still Open", "value": _clip("\n".join(lines)), "inline": False})
    if not claims:
        title = "DBL Bounty Board"
    elif len(claims) == 1:
        title = f"DBL Bounty Claimed — {claims[0][0].title}"
    else:
        title = "DBL Bounties Claimed"
    note = (
        "*Season bounties: each is claimed once, by the first franchise to get there. "
        "Rewards are recognition only.*"
    )
    source = f"{FANTRAX_SOURCE} • MLB SCORE DATA" if mlb_data else FANTRAX_SOURCE
    return _payload(ctx, title, f"{_header(ctx)}\n\n{note}", fields, "BOUNTIES", source=source)
