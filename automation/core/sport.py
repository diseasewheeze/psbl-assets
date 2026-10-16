"""The league's baseball rules in one place: lineup, roster sizes, scoring, limits.

Every automation that needs a rule reads it from here, and the Constitution is
built from the same values (tools/constitution_source.py), so the two can never
disagree. Stat keys are the MLB Stats API's own field names.
"""

from __future__ import annotations

from typing import Mapping

# --- Lineup and roster (Constitution Article VI) -------------------------------

# Active lineup slots, in Fantrax order.
LINEUP: dict[str, int] = {
    "C": 1, "1B": 1, "2B": 1, "3B": 1, "SS": 1, "OF": 3, "UTIL": 2,
    "SP": 5, "RP": 3,
}
BENCH = 8
INJURED_LIST = 4
MINORS = 15

# MLB positions each lineup slot accepts.
SLOT_ACCEPTS: dict[str, frozenset[str]] = {
    "C": frozenset({"C"}),
    "1B": frozenset({"1B"}),
    "2B": frozenset({"2B"}),
    "3B": frozenset({"3B"}),
    "SS": frozenset({"SS"}),
    "OF": frozenset({"OF", "LF", "CF", "RF"}),
    "UTIL": frozenset({"C", "1B", "2B", "3B", "SS", "OF", "LF", "CF", "RF", "DH", "UT", "UTIL"}),
    "SP": frozenset({"SP"}),
    "RP": frozenset({"RP"}),
}
HITTER_SLOTS = ("C", "1B", "2B", "3B", "SS", "OF", "UTIL")
PITCHER_SLOTS = ("SP", "RP")

# --- Limits (Constitution Articles IX and X) -----------------------------------

# Most games started by pitchers that count for a franchise in one calendar
# week; a longer scoring period gets this times its length in weeks, rounded.
PITCHER_STARTS_PER_WEEK = 7
# Most player acquisitions per normal fantasy week.
ACQUISITIONS_PER_WEEK = 5

# --- Minor-league eligibility (Constitution Article VII) -----------------------

# A player is minor-eligible while his career MLB regular-season totals stay at
# or under both limits. At-bats come from his hitting stats only (pitching
# stats also carry an at-bats-faced figure, which does not count).
MINORS_MAX_AB = 130
MINORS_MAX_OUTS = 150  # 50 innings pitched

# --- Scoring (Constitution Article VIII) ----------------------------------------

# Points per stat, by MLB Stats API field name, entered in Fantrax the same way.
# Every event is priced at its run value from FanGraphs' linear weights for the
# 2021-2026 seasons, at 10 points per run: an out is -1, a single nets +4.6
# (at-bat -1, hit +5.6), a double +7.6, a triple +10.3 and a home run +14.0, and
# the pitcher pays the mirror price. Hits allowed count at half weight, because
# a pitcher only partly controls whether a ball in play falls in. The two values
# that are not run values, the inning (+6, so +2 per out) and saves and holds,
# were set against every MLB pitcher's 2021-2026 seasons so that a league's
# starters carry their share of the lineup and no reliever outscores the aces
# (research/scoring/). Intentional walks count as walks. "outs" are outs
# recorded while pitching (3 per inning).
HITTING: dict[str, float] = {
    "atBats": -1,
    "hits": 5.6,
    "doubles": 3.0,
    "triples": 5.7,
    "homeRuns": 9.4,
    "baseOnBalls": 3.1,
    "hitByPitch": 3.3,
    "stolenBases": 2.0,
    "caughtStealing": -4.1,
}

PITCHING: dict[str, float] = {
    "outs": 2.0,
    "strikeOuts": 2.0,
    "hits": -2.6,
    "homeRuns": -11.4,
    "baseOnBalls": -3.1,
    "hitBatsmen": -3.3,
    "saves": 6,
    "holds": 4,
}

# Display labels for each scored stat, in the order the Constitution lists them.
HITTING_LABELS: dict[str, str] = {
    "atBats": "At-Bat (AB)", "hits": "Hit (H)", "doubles": "Double (2B), added",
    "triples": "Triple (3B), added", "homeRuns": "Home Run (HR), added",
    "baseOnBalls": "Walk (BB)", "hitByPitch": "Hit by Pitch (HBP)",
    "stolenBases": "Stolen Base (SB)", "caughtStealing": "Caught Stealing (CS)",
}
PITCHING_LABELS: dict[str, str] = {
    "outs": "Inning Pitched (IP)", "strikeOuts": "Strikeout (K)",
    "hits": "Hit Allowed (H)", "homeRuns": "HR Allowed, added",
    "baseOnBalls": "Walk Issued (BB)", "hitBatsmen": "Hit Batter (HB)",
    "saves": "Save (SV)", "holds": "Hold (HLD)",
}

# What each hit is worth in all, for explainers: (hit + bonus) - the at-bat.
NET_HIT = {
    "single": round(HITTING["hits"] + HITTING["atBats"], 2),
    "double": round(HITTING["hits"] + HITTING["doubles"] + HITTING["atBats"], 2),
    "triple": round(HITTING["hits"] + HITTING["triples"] + HITTING["atBats"], 2),
    "home run": round(HITTING["hits"] + HITTING["homeRuns"] + HITTING["atBats"], 2),
}


def _num(stats: Mapping[str, object], key: str) -> float:
    value = stats.get(key)
    if value in (None, ""):
        return 0.0
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def singles(stats: Mapping[str, object]) -> float:
    if "singles" in stats:
        return _num(stats, "singles")
    return _num(stats, "hits") - _num(stats, "doubles") - _num(stats, "triples") - _num(stats, "homeRuns")


def hitting_points(stats: Mapping[str, object]) -> float:
    """Fantasy points for one hitting line (season, game or any span)."""
    total = 0.0
    for key, value in HITTING.items():
        total += value * (singles(stats) if key == "singles" else _num(stats, key))
    return round(total, 2)


def outs_recorded(stats: Mapping[str, object]) -> float:
    """Outs recorded, from "outs" or else from inningsPitched written as 6.2 (6 2/3)."""
    if stats.get("outs") not in (None, ""):
        return _num(stats, "outs")
    ip = str(stats.get("inningsPitched") or "0")
    whole, _, part = ip.partition(".")
    try:
        return int(whole or 0) * 3 + int(part or 0)
    except ValueError:
        return 0.0


def pitching_points(stats: Mapping[str, object]) -> float:
    """Fantasy points for one pitching line (season, game or any span)."""
    total = 0.0
    for key, value in PITCHING.items():
        total += value * (outs_recorded(stats) if key == "outs" else _num(stats, key))
    return round(total, 2)


def minor_eligible(career_at_bats: float, career_outs: float) -> bool:
    """True while a player's career MLB totals stay within both rookie limits."""
    return career_at_bats <= MINORS_MAX_AB and career_outs <= MINORS_MAX_OUTS


def slot_fits(slot: str, positions: set[str] | frozenset[str]) -> bool:
    """True when a player with these MLB/Fantrax positions may fill the slot."""
    return bool(SLOT_ACCEPTS.get(slot, frozenset()) & {p.upper() for p in positions})
