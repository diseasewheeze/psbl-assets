#!/usr/bin/env python3
"""DBL prospect board: MLB's ranked draft prospects, for the Commissioner only.

Reads MLB's draft prospect list for the next MLB Draft
(GET https://statsapi.mlb.com/api/v1/draft/prospects/{year}, through
core/mlb_people.py) and posts the top of the ranking to the private
Commissioner Desk channel. It posts only when something changed since the last
post: a new draft class, new rankings, or a player moving up or down five or
more places. The first live run that finds a ranked list posts the whole board.

MLB publishes the list well before the July draft. On October 14 and 15, 2026
the 2027 list was still empty, so a run says so, posts nothing and saves
nothing. The scheduler job (id prospect-board in
automation/scheduler/schedule.yaml) and its Automation Health entry are
switched off until the list fills; turn both back on then. Manual runs work at
any time.

What the board reads (the 2026 list's shape, checked live 2026-10-15):
prospects[] with rank (only ranked prospects have one; the rest are left out),
person{id, fullName, birthDate, primaryPosition}, school{name, schoolClass,
state, country}, and after the draft isDrafted, pickRound, pickNumber and
team. Nothing here touches the owner-facing channels.

Modes:
  preview  print the board and what would be posted; no Discord, no state change
  test     post one [TEST] board; no state change
  live     post when the rankings changed and save them
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

from core import mlb_people as mp  # noqa: E402
from core.league import load_json, load_league, save_json, timezone_of  # noqa: E402
from discord_webhook import post_discord_webhook  # noqa: E402
import desk  # noqa: E402

STATE_PATH = ROOT / "state" / "prospects.json"
CONFIG_PATH = ROOT / "prospects.yaml"
MOVE_MIN = 5
DEFAULT_TOP = 30
NEXT_CLASS_FROM_MONTH = 8   # the MLB Draft is in July; from August the board shows next year's class


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    year = raw.get("year")
    return {"top": int(raw.get("top", DEFAULT_TOP) or 0), "year": int(year) if year else None}


def draft_year(today: date, configured: int | None = None) -> int:
    """The draft class to show: configured, else this year's until the end of July, then next year's."""
    if configured:
        return int(configured)
    return today.year + (1 if today.month >= NEXT_CLASS_FROM_MONTH else 0)


def rank_of(p: dict[str, Any]) -> int | None:
    try:
        rank = int(p.get("rank"))
    except (TypeError, ValueError):
        return None
    return rank if rank > 0 else None


def person_of(p: dict[str, Any]) -> dict[str, Any]:
    return p.get("person") if isinstance(p.get("person"), dict) else {}


def player_key(p: dict[str, Any]) -> str:
    person = person_of(p)
    return str(person.get("id") or f"{person.get('fullName', '')}|{person.get('birthDate', '')}")


def ranked(prospects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ranked prospects, best first (MLB's list includes unranked players, which are left out)."""
    return sorted((p for p in prospects if rank_of(p)), key=lambda p: (rank_of(p), player_key(p)))


def fetch_board(api: mp.MlbApi, year: int) -> dict[str, Any]:
    return {"year": year, "prospects": api.draft_prospects(year)}


def snapshot(board: dict[str, Any]) -> dict[str, Any]:
    ranks = {player_key(p): rank_of(p) for p in ranked(board["prospects"])}
    stamp = hashlib.sha256(json.dumps(sorted(ranks.items())).encode()).hexdigest()[:16]
    return {"year": board["year"], "ranks": ranks, "hash": stamp}


def movers(prev: dict[str, Any], board: dict[str, Any], top: int) -> list[str]:
    out = []
    for p in ranked(board["prospects"])[:top]:
        before = (prev.get("ranks") or {}).get(player_key(p))
        now = rank_of(p)
        if before and abs(before - now) >= MOVE_MIN:
            direction = "up" if now < before else "down"
            out.append(f"{person_of(p).get('fullName', 'Unknown')} moved {direction} from {before} to {now}.")
    return out


def _age(birth: Any, today: date) -> int | None:
    try:
        y, m, d = (int(x) for x in str(birth)[:10].split("-"))
    except ValueError:
        return None
    return today.year - y - ((today.month, today.day) < (m, d))


def describe(p: dict[str, Any], today: date) -> str:
    person = person_of(p)
    school = p.get("school") if isinstance(p.get("school"), dict) else {}
    where = school.get("name") or ""
    if where and school.get("schoolClass"):
        where += f" ({school['schoolClass']})"
    age = _age(person.get("birthDate"), today)
    position = (person.get("primaryPosition") or {}).get("abbreviation") or ""
    bits = [position, where, f"age {age}" if age is not None else ""]
    if p.get("isDrafted") and p.get("pickNumber"):
        team = (p.get("team") or {}).get("name") or "drafted"
        bits.append(f"{team}, pick {p['pickNumber']}")
    return f"{rank_of(p)}. {person.get('fullName', 'Unknown')}: " + ", ".join(b for b in bits if b)


def build_task(board: dict[str, Any], top: int, today: date, moved: list[str] | None = None) -> dict[str, Any]:
    players = ranked(board["prospects"])[:top]
    items = [
        f"MLB's ranked prospects for the {board['year']} MLB Draft. These are MLB's own rankings, not DBL "
        "rankings. Use them for scouting only.",
    ]
    if players:
        items.append(f"**Top {len(players)}**\n" + "\n".join(describe(p, today) for p in players))
    if moved:
        items.append("**Biggest moves since the last post**\n" + "\n".join(moved))
    return {"title": f"Prospect board: {board['year']} draft class", "section": "Scouting", "items": items}


def run(mode: str, api: mp.MlbApi | None = None, today: date | None = None) -> int:
    cfg = load_league()
    today = today or datetime.now(timezone.utc).astimezone(timezone_of(cfg)).date()
    conf = load_config()
    year = draft_year(today, conf["year"])
    board = fetch_board(api or mp.MlbApi(), year)
    listed = ranked(board["prospects"])
    print(f"DBL PROSPECTS mode={mode.upper()} year={year} listed={len(board['prospects'])} ranked={len(listed)}")
    if not listed or conf["top"] <= 0:
        why = "the board is hidden (top: 0 in prospects.yaml)" if conf["top"] <= 0 else \
            f"MLB has not published a ranked {year} draft prospect list yet"
        print(f"Nothing to post: {why}. Nothing saved.")
        return 0
    snap = snapshot(board)
    state = load_json(STATE_PATH, {})
    if state.get("hash") == snap["hash"]:
        print("Rankings have not changed since the last post.")
        return 0
    moved = movers(state, board, conf["top"]) if state.get("year") == year else []
    task = build_task(board, conf["top"], today, moved)
    for line in task["items"]:
        print(line)
    if mode == "preview":
        return 0
    ok, detail = post_discord_webhook(desk.secret_name(cfg), desk.build_payload(task, None, cfg, now=datetime.now(timezone.utc)))
    if not ok:
        print(f"DELIVERY ERROR: {detail} (not saved, will retry next run)")
        return 1
    print("POSTED")
    save_json(STATE_PATH, snap)
    return 0


def test_post(api: mp.MlbApi | None = None, today: date | None = None) -> int:
    cfg = load_league()
    today = today or date.today()
    year = draft_year(today, load_config()["year"])
    board = fetch_board(api or mp.MlbApi(), year)
    if not ranked(board["prospects"]):
        print(f"No [TEST] board posted: MLB has not published a ranked {year} draft prospect list yet.")
        return 0
    task = build_task(board, 5, today)
    task["items"].insert(0, "Sample only. Real posts use the full board.")
    ok, detail = post_discord_webhook(desk.secret_name(cfg), desk.build_payload(task, None, cfg, test=True))
    print(("PASS" if ok else "ERROR") + f" [prospects]: {detail}")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("preview", "test", "live"), default="preview")
    args = parser.parse_args()
    return test_post() if args.mode == "test" else run(args.mode)


if __name__ == "__main__":
    sys.exit(main())
