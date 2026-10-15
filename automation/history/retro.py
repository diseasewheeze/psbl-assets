"""Draft retrospectives: how a past draft has turned out, from saved draft results and MLB stats.

Output is measured from MLB regular-season stats since the draft (the Season
that draft supplies onward), scored the league's way (Constitution Article
VIII, automation/core/sport.py): each season's hitting totals with
sport.hitting_points and its pitching totals with sport.pitching_points, added
together. MLB's season totals carry every scored category, so nothing is left
out. Players are matched to MLB players by name, MLB team and position the same
way as the minor-eligibility watch (core/mlb_people.find_person), and season
totals come from the MLB Stats API in batches (a traded player's season is
MLB's combined line).

  Biggest steal       a pick after round 1 whose output ranks furthest ahead of where he was taken
  Biggest miss        the round-1 pick with the least output (players never matched are left out)
  Best undrafted      a player added from the unowned pool after the draft who is still rostered,
  pickup              with the most output since the Season he was added
  Best development    the drafted player whose output rose most from the Season before the draft
                      to the latest Season

An Annual Draft held in a year supplies that year's Season (the 2028 Annual
Draft supplies Season 2028), and an MLB season is its calendar year.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core import mlb_people as mp
from core import sport
from core.league import AVATAR, color_value
from history.context import LeagueHistory, ordinal

FOOTER_DIVIDER = (
    "https://raw.githubusercontent.com/diseasewheeze/dbl-assets/main/"
    "discord/webhooks/shared/dbl-footer-divider-1600x90.png?v=8bit-1"
)
MEASURE = ("MLB regular-season stats since the draft, scored the DBL way (Article VIII): every hitting and "
           "pitching category, from MLB's season totals.")


def season_label(season: int) -> str:
    return str(int(season))


def season_value(totals: dict[str, dict[str, float]]) -> dict[str, float]:
    """{gp, value} for one season's {"hitting", "pitching"} totals."""
    hitting, pitching = totals.get("hitting") or {}, totals.get("pitching") or {}
    gp = max(float(hitting.get("gamesPlayed") or 0), float(pitching.get("gamesPlayed") or 0))
    value = (sport.hitting_points(hitting) if hitting else 0.0) + (sport.pitching_points(pitching) if pitching else 0.0)
    return {"gp": gp, "value": round(value, 2)}


def season_stats(seasons: dict[int, dict[str, dict[str, float]]]) -> dict[int, dict[str, float]]:
    """Season -> {gp, value}, from mlb_people's season totals."""
    return {int(year): season_value(totals) for year, totals in seasons.items()}


def fetch_stats(hist: LeagueHistory, player_ids: list[str], api: mp.MlbApi | None = None,
                ) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Fantrax player id -> {mlb_id, seasons}; plus the names that could not be matched to an MLB player."""
    api = api or mp.MlbApi()
    matched: dict[str, int] = {}
    unmatched: list[str] = []
    for pid in dict.fromkeys(player_ids):
        info = hist.players.get(pid) or {}
        name = str(info.get("name") or "")
        if not name:
            unmatched.append(pid)
            continue
        found = mp.find_person(api, name, str(info.get("team") or ""), str(info.get("position") or ""))
        if found.person is None:
            unmatched.append(name)
            continue
        matched[pid] = found.person.id
    seasons = api.seasons(matched.values()) if matched else {}
    stats = {pid: {"mlb_id": mid, "seasons": season_stats(seasons.get(mid) or {})} for pid, mid in matched.items()}
    return stats, unmatched


def _since(seasons: dict[Any, dict[str, float]], first: int) -> dict[str, float]:
    total = {"gp": 0.0, "value": 0.0}
    for season, row in seasons.items():
        if int(season) >= first:
            for k in total:
                total[k] += float(row.get(k) or 0)
    return total


def _event_season(event: dict[str, Any]) -> int:
    """The Season an archive event counts toward: its year, or the next one after September."""
    day = str(event.get("date") or event.get("at") or "")[:10]
    try:
        y, m = int(day[:4]), int(day[5:7])
    except ValueError:
        return 0
    return y if m <= 9 else y + 1


def candidates_for_pickup(hist: LeagueHistory, draft: dict[str, Any]) -> list[dict[str, Any]]:
    """Adds from the pool after the draft, not taken in it, still on a roster."""
    drafted = {str(p.get("player")) for p in draft.get("picks") or []}
    after = str(draft.get("end") or draft.get("date") or "")
    out: dict[str, dict[str, Any]] = {}
    for e in hist.events():
        if e.get("type") != "add" or str(e.get("at") or "") < after:
            continue
        pid = str(e.get("player"))
        if pid in drafted or pid in out or not hist.current_owner(pid):
            continue
        out[pid] = e
    return list(out.values())


def build_report(hist: LeagueHistory, draft: dict[str, Any], stats: dict[str, dict[str, Any]],
                 unmatched: list[str] | None = None, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    year = int(draft.get("year") or 0)
    first = year
    before = year - 1
    picks = []
    for p in draft.get("picks") or []:
        pid = str(p.get("player") or "")
        if not pid or pid not in stats:
            continue
        seasons = {int(k): v for k, v in (stats[pid].get("seasons") or {}).items()}
        since = _since(seasons, first)
        later = [s for s in seasons if s >= first]
        latest = max(later) if later else None
        picks.append({
            "player": pid, "name": hist.player(pid), "franchise": hist.name(hist.franchise(str(p.get("team") or ""))),
            "round": int(p["round"]), "in_round": int(p["in_round"]), "overall": int(p["overall"]),
            "value": round(since["value"], 1), "gp": int(since["gp"]),
            "before": round(float((seasons.get(before) or {}).get("value") or 0), 1),
            "latest": round(float((seasons.get(latest) or {}).get("value") or 0), 1) if latest else 0.0,
            "latest_season": latest,
        })
    ranked = sorted(picks, key=lambda r: (-r["value"], r["overall"]))
    for rank, row in enumerate(ranked, 1):
        row["rank"] = rank

    late = [r for r in picks if r["round"] >= 2 and r["value"] > 0]
    steal = max(late, key=lambda r: (r["overall"] - r["rank"], r["value"]), default=None)
    early = [r for r in picks if r["round"] == 1]
    miss = min(early, key=lambda r: (r["value"], r["overall"]), default=None)
    grown = [r for r in picks if r["latest_season"] and r["latest_season"] > before]
    development = max(grown, key=lambda r: (r["latest"] - r["before"], r["latest"]), default=None)
    if development and development["latest"] - development["before"] <= 0:
        development = None

    pickup = None
    for e in candidates_for_pickup(hist, draft):
        pid = str(e["player"])
        if pid not in stats:
            continue
        seasons = {int(k): v for k, v in (stats[pid].get("seasons") or {}).items()}
        since = _since(seasons, max(_event_season(e), first))
        row = {"player": pid, "name": hist.player(pid), "franchise": hist.name(hist.franchise(str(e.get("team") or ""))),
               "added": hist.event_date(e), "value": round(since["value"], 1), "gp": int(since["gp"])}
        if row["value"] > 0 and (pickup is None or row["value"] > pickup["value"]):
            pickup = row

    return {
        "year": year,
        "season": draft.get("season"),
        "kind": "Startup Draft" if max((r["round"] for r in picks), default=0) > 5 or len(draft.get("picks") or []) > 100 else "Annual Draft",
        "as_of": now.isoformat(),
        "since_season": season_label(first),
        "picks_rated": len(picks),
        "picks_total": len(draft.get("picks") or []),
        "unmatched": sorted(unmatched or []),
        "steal": steal, "miss": miss, "pickup": pickup, "development": development,
        "top": ranked[:10],
        "measure": MEASURE,
    }


def slot(row: dict[str, Any]) -> str:
    return f"{row['round']}.{row['in_round']:02d} ({ordinal(row['overall'])} overall)"


def output_text(row: dict[str, Any]) -> str:
    unit = "MLB game" if row["gp"] == 1 else "MLB games"
    return f"{row['value']:g} DBL points in {row['gp']} {unit}"


def highlight_lines(report: dict[str, Any]) -> list[tuple[str, str]]:
    out = []
    s, m, p, d = report.get("steal"), report.get("miss"), report.get("pickup"), report.get("development")
    out.append(("BIGGEST STEAL", f"**{s['name']}**, {slot(s)} by {s['franchise']}: {output_text(s)} since the draft, "
                f"{'the most' if s['rank'] == 1 else 'the ' + ordinal(s['rank']) + ' most'} productive pick of the class."
                if s else "Not enough MLB games yet."))
    out.append(("BIGGEST MISS", f"**{m['name']}**, {slot(m)} by {m['franchise']}: {output_text(m)} since the draft." if m
                else "Not enough MLB games yet."))
    out.append(("BEST UNDRAFTED PICKUP", f"**{p['name']}**, added by {p['franchise']} on {p['added']} and still rostered: "
                f"{output_text(p)}." if p else "No undrafted pickup has produced yet."))
    out.append(("BEST DEVELOPMENT", f"**{d['name']}**, {slot(d)} by {d['franchise']}: {d['before']:g} DBL points the season "
                f"before the draft, {d['latest']:g} in {season_label(d['latest_season'])}." if d
                else "No drafted player has a later MLB season to compare yet."))
    return out


def title(report: dict[str, Any]) -> str:
    return f"{report['year']} DBL {report['kind']}: Retrospective"


def render_text(report: dict[str, Any]) -> str:
    lines = [title(report), f"Rated {report['picks_rated']} of {report['picks_total']} picks; stats since {report['since_season']}."]
    for label, text in highlight_lines(report):
        lines.append(f"{label.title()}: {text.replace('**', '')}")
    if report.get("unmatched"):
        lines.append(f"Not matched to an MLB player ({len(report['unmatched'])}): " + "; ".join(report["unmatched"][:20]))
    lines.append("How it is measured: " + report["measure"])
    return "\n".join(lines)


def payload(report: dict[str, Any], league: dict[str, Any], *, test: bool = False) -> dict[str, Any]:
    fields = [{"name": label, "value": text[:1024], "inline": False} for label, text in highlight_lines(report)]
    fields.append({"name": "HOW IT IS MEASURED", "value": report["measure"][:1024], "inline": False})
    rated = f"Rated {report['picks_rated']} of {report['picks_total']} picks"
    if report.get("unmatched"):
        rated += f" ({len(report['unmatched'])} could not be matched to an MLB player)"
    embed = {
        "title": ("[TEST] " if test else "") + title(report),
        "description": f"How the {report['year']} draft has turned out so far. {rated}.",
        "color": color_value(league.get("color")),
        "fields": fields,
        "footer": {"text": "DBL DRAFT CENTER • FANTRAX AND MLB DATA"},
        "image": {"url": FOOTER_DIVIDER},
    }
    return {"username": "DBL Draft Center", "avatar_url": AVATAR, "allowed_mentions": {"parse": []}, "embeds": [embed]}
