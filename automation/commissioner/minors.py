#!/usr/bin/env python3
"""DBL minor-eligibility watch: tells the commissioner when a rostered player stops being minor-eligible.

Constitution Article VII: a player is minor-eligible while his career MLB
regular-season totals stay within MLB's rookie limits, at most
sport.MINORS_MAX_AB at-bats and at most sport.MINORS_MAX_OUTS outs pitched
(50 innings), checked with sport.minor_eligible. At-bats come from his hitting
stats only: MLB's pitching stats also carry an at-bats-faced figure, which
never counts. There is no age limit. Once a minor-league player passes either
limit, his franchise has three calendar days after notice to remove him from
the minor slot (7.4).

Fantrax's feed has no career totals, so this matches every rostered player to
an MLB player by name, MLB team and position (core/mlb_people.py; matched ids
are remembered) and reads career totals from the MLB Stats API in batches. It
reports every rostered player who crossed a limit since the last run, and says
whether Fantrax shows him in a minor slot right now. The first live run only
saves a baseline.

Modes:
  preview  print what would be posted and every unmatched player; no Discord, no state change
  test     post one [TEST] sample alert; no state change
  live     post alerts and save eligibility
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

from core import mlb_people as mp  # noqa: E402
from core import sport  # noqa: E402
from core.fantrax import Fantrax, normalize_standings  # noqa: E402
from core.league import load_json, load_league, save_json  # noqa: E402
from discord_webhook import post_discord_webhook  # noqa: E402
import desk  # noqa: E402

STATE_PATH = ROOT / "state" / "minors.json"
STATE_SPORT = "mlb"   # state saved before the league moved to baseball is not a baseline
MINOR_SLOT = "MINORS"


def norm(text: str) -> str:
    """A name with spaces, accents, punctuation and Jr. removed, for comparing names ('witt bobby' style keys)."""
    return re.sub(r" ", "", mp.norm_name(text))


def fantrax_name(raw: str) -> tuple[str, str]:
    """'Witt Jr., Bobby' -> ('Bobby', 'Witt Jr.')."""
    return mp.split_name(raw)


def eligible(at_bats: float, outs: float) -> bool:
    """Article VII: within both career limits (sport.minor_eligible)."""
    return sport.minor_eligible(at_bats, outs)


def reasons(at_bats: int, outs: int) -> list[str]:
    out = []
    if at_bats > sport.MINORS_MAX_AB:
        out.append(f"{at_bats} career MLB at-bats (limit {sport.MINORS_MAX_AB})")
    if outs > sport.MINORS_MAX_OUTS:
        out.append(f"{mp.innings_text(outs)} career MLB innings (limit {sport.MINORS_MAX_OUTS // 3})")
    return out


def match_ids(rostered: list[dict[str, Any]], api: mp.MlbApi, cache: dict[str, Any]) -> tuple[dict[str, int], list[str]]:
    """Fantrax id -> MLB person id, reusing ids matched before; plus the players that couldn't be matched."""
    ids: dict[str, int] = {}
    unmatched: list[str] = []
    for r in rostered:
        saved = cache.get(r["fantraxId"])
        if isinstance(saved, dict) and saved.get("name") == r["name"] and saved.get("id"):
            ids[r["fantraxId"]] = int(saved["id"])
            continue
        found = mp.find_person(api, r["name"], r["mlb_team"], r["position"])
        if found.person is None:
            unmatched.append(f"{r['name']} ({found.why})")
            continue
        ids[r["fantraxId"]] = found.person.id
        cache[r["fantraxId"]] = {"id": found.person.id, "name": r["name"]}
    return ids, unmatched


def evaluate(rostered: list[dict[str, Any]], api: mp.MlbApi, cache: dict[str, Any],
             ) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """fantraxId -> {name, mlbTeam, franchise, slot, at_bats, outs, eligible}; plus unmatched names."""
    ids, unmatched = match_ids(rostered, api, cache)
    careers = api.careers(ids.values()) if ids else {}
    out: dict[str, dict[str, Any]] = {}
    for r in rostered:
        pid = ids.get(r["fantraxId"])
        if pid is None:
            continue
        if pid not in careers:
            unmatched.append(f"{r['name']} (MLB has no record for id {pid})")
            cache.pop(r["fantraxId"], None)
            continue
        career = careers[pid][1]
        out[r["fantraxId"]] = {
            "name": r["name"], "mlbTeam": r["mlb_team"], "franchise": r["franchise"], "slot": r.get("slot") or "",
            "at_bats": career.at_bats, "outs": career.outs, "eligible": eligible(career.at_bats, career.outs),
        }
    return out, unmatched


def crossed(prev: dict[str, bool], cur: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Players who were minor-eligible at the last run and are not now."""
    return sorted(
        ({**v, "id": k} for k, v in cur.items() if prev.get(k) is True and not v["eligible"]),
        key=lambda v: (v["franchise"], v["name"]),
    )


def reason(p: dict[str, Any]) -> str:
    return " and ".join(reasons(int(p["at_bats"]), int(p["outs"])))


def build_task(found: list[dict[str, Any]]) -> dict[str, Any]:
    title = "Minor eligibility: 1 player is now ineligible" if len(found) == 1 else f"Minor eligibility: {len(found)} players are now ineligible"
    lines = []
    for p in found:
        where = ", in a minor slot now" if p.get("slot") == MINOR_SLOT else ""
        team = f" ({p['mlbTeam']})" if p.get("mlbTeam") else ""
        lines.append(f"{mp.display_name(p['name'])}{team} on {p['franchise']}{where}: {reason(p)}.")
    items = [
        "If a player below is in a minor-league slot, his franchise has three calendar days after notice to promote, "
        "trade, drop or otherwise remove him (7.4). Career totals are MLB's own; the Commissioner's determination "
        "is final (7.3).",
        *lines,
    ]
    return {"title": title, "section": "Article VII", "items": items}


def load_rostered(fx: Fantrax) -> list[dict[str, Any]]:
    names = {r["teamId"]: r["teamName"] for r in normalize_standings(fx.standings())}
    ids = fx.player_ids()
    out = []
    for team_id, team in (fx.rosters().get("rosters") or {}).items():
        for item in team.get("rosterItems") or []:
            info = ids.get(item["id"]) or {}
            if not info.get("name"):
                continue
            out.append({
                "fantraxId": item["id"], "name": info["name"],
                "position": info.get("position") or item.get("position") or "",
                "mlb_team": mp.team_code(info.get("team")), "slot": str(item.get("status") or "").upper(),
                "franchise": team.get("teamName") or names.get(team_id, team_id),
            })
    return out


def run(mode: str, api: mp.MlbApi | None = None) -> int:
    cfg = load_league()
    now = datetime.now(timezone.utc)
    api = api or mp.MlbApi()
    fx = Fantrax(str(cfg["league_id"]), user_agent="DBL-Minors/2.0")
    rostered = load_rostered(fx)
    state = load_json(STATE_PATH, {})
    ours = state.get("sport") == STATE_SPORT
    cache = dict(state.get("mlb_ids") or {}) if ours else {}
    cur, unmatched = evaluate(rostered, api, cache)
    print(f"DBL MINORS mode={mode.upper()} rostered={len(rostered)} matched={len(cur)} unmatched={len(unmatched)} "
          f"ineligible={sum(not v['eligible'] for v in cur.values())}")
    if unmatched:
        print("Could not match to an MLB player: " + "; ".join(sorted(unmatched)[:40]))
    new_state = {"sport": STATE_SPORT, "mlb_ids": cache, "eligible": {k: v["eligible"] for k, v in cur.items()}}
    prev = state.get("eligible") if ours else None
    if not isinstance(prev, dict):
        print("No saved copy yet: recording eligibility as the baseline. No alert.")
        if mode == "live":
            save_json(STATE_PATH, {**new_state, "baselined": now.isoformat()})
        return 0
    if state.get("baselined"):
        new_state["baselined"] = state["baselined"]
    found = crossed(prev, cur)
    if not found:
        print("No rostered player has become minor-ineligible.")
        if mode == "live":
            save_json(STATE_PATH, new_state)
        return 0
    task = build_task(found)
    for line in task["items"]:
        print("  " + line)
    if mode == "preview":
        return 0
    ok, detail = post_discord_webhook(desk.secret_name(cfg), desk.build_payload(task, None, cfg, now=now))
    if not ok:
        print(f"DELIVERY ERROR: {detail} (not saved, will retry next run)")
        return 1
    print("POSTED")
    save_json(STATE_PATH, new_state)
    return 0


def test_post() -> int:
    cfg = load_league()
    sample = [{"name": "Player, Sample", "mlbTeam": "KC", "franchise": "Test 1", "slot": MINOR_SLOT,
               "at_bats": sport.MINORS_MAX_AB + 12, "outs": 0}]
    task = build_task(sample)
    task["items"].insert(0, "Sample only. No player has actually changed.")
    ok, detail = post_discord_webhook(desk.secret_name(cfg), desk.build_payload(task, None, cfg, test=True))
    print(("PASS" if ok else "ERROR") + f" [minors]: {detail}")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("preview", "test", "live"), default="preview")
    args = parser.parse_args()
    return test_post() if args.mode == "test" else run(args.mode)


if __name__ == "__main__":
    sys.exit(main())
