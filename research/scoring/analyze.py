"""Score every MLB player of 2024-2026 under candidate point systems and compare.

For each season: fill a 12-team league's lineup slots (C, 1B, 2B, 3B, SS, 3 OF,
2 UTIL, 5 SP, 3 RP) with the best players by points, then report how the
points split between hitters, starters and relievers, how far starters sit
above replacement, which stats carry the points, and how stable each player's
points are from one season to the next.
"""
from __future__ import annotations

import csv
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

RAW = Path(__file__).parent / "data"
SEASONS = (2024, 2025, 2026)
TEAMS = 12
SLOTS = {"C": 1, "1B": 1, "2B": 1, "3B": 1, "SS": 1, "OF": 3, "UTIL": 2, "SP": 5, "RP": 3}
OF = {"LF", "CF", "RF", "OF"}


def num(row, k):
    v = row.get(k, "")
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def load(season):
    def first_per_id(rows):
        seen, out = set(), []
        for r in rows:
            if r.get("id") and r["id"] not in seen:
                seen.add(r["id"]); out.append(r)
        return out
    hit = first_per_id(csv.DictReader(open(RAW / f"hitting_{season}.csv", encoding="utf-8")))
    pit = first_per_id(csv.DictReader(open(RAW / f"pitching_{season}.csv", encoding="utf-8")))
    hitters = []
    for r in hit:
        if r.get("pos") == "P":
            continue
        h = {k: num(r, k) for k in ("G", "PA", "AB", "H", "2B", "3B", "HR", "R", "RBI", "BB", "HBP", "SB", "CS", "K")}
        h["1B"] = h["H"] - h["2B"] - h["3B"] - h["HR"]
        pos = r.get("pos", "")
        h.update(id=r["id"], name=r["name"], pos="OF" if pos in OF else pos)
        hitters.append(h)
    pitchers = []
    for r in pit:
        p = {k: num(r, k) for k in ("G", "GS", "GF", "outs", "H", "ER", "BB", "HBP", "K", "W", "L", "SV", "HLD", "BS")}
        if p["G"] <= 0:
            continue
        p.update(id=r["id"], name=r["name"])
        p["role"] = "SP" if p["GS"] >= 0.5 * p["G"] and p["GS"] >= 3 else "RP"
        pitchers.append(p)
    return hitters, pitchers


def hit_points(h, w):
    return sum(w.get(k, 0) * h[k] for k in ("1B", "2B", "3B", "HR", "R", "RBI", "BB", "HBP", "SB", "CS", "K"))


def pit_points(p, w):
    return sum(w.get(k, 0) * p[k] for k in ("outs", "K", "H", "ER", "BB", "HBP", "W", "L", "SV", "HLD", "BS"))


def fill(hitters, pitchers, wh, wp):
    """Greedy league fill: scarce hitter slots first, then OF, then UTIL; SP and RP by role."""
    for h in hitters:
        h["pts"] = hit_points(h, wh)
    for p in pitchers:
        p["pts"] = pit_points(p, wp)
    used = set()
    starters = defaultdict(list)
    order = ["C", "SS", "2B", "3B", "1B", "OF"]
    ranked_h = sorted(hitters, key=lambda x: -x["pts"])
    for slot in order:
        need = SLOTS[slot] * TEAMS
        for h in ranked_h:
            if len(starters[slot]) >= need:
                break
            if h["id"] in used or h["pos"] != slot:
                continue
            starters[slot].append(h); used.add(h["id"])
    need = SLOTS["UTIL"] * TEAMS
    for h in ranked_h:
        if len(starters["UTIL"]) >= need:
            break
        if h["id"] not in used:
            starters["UTIL"].append(h); used.add(h["id"])
    for role in ("SP", "RP"):
        pool = sorted((p for p in pitchers if p["role"] == role), key=lambda x: -x["pts"])
        starters[role] = pool[: SLOTS[role] * TEAMS]
    # replacement level: best unused player who fits each slot
    repl = {}
    for slot in order:
        rest = [h["pts"] for h in ranked_h if h["id"] not in used and h["pos"] == slot]
        repl[slot] = rest[0] if rest else 0.0
    rest = [h["pts"] for h in ranked_h if h["id"] not in used]
    repl["UTIL"] = rest[0] if rest else 0.0
    for role in ("SP", "RP"):
        pool = sorted((p["pts"] for p in pitchers if p["role"] == role), reverse=True)
        k = SLOTS[role] * TEAMS
        repl[role] = pool[k] if len(pool) > k else 0.0
    return starters, repl


def season_report(season, wh, wp):
    hitters, pitchers = load(season)
    starters, repl = fill(hitters, pitchers, wh, wp)
    groups = {"Hitters": [s for s in ("C", "1B", "2B", "3B", "SS", "OF", "UTIL")], "SP": ["SP"], "RP": ["RP"]}
    out = {}
    total_pts = sum(p["pts"] for g in groups.values() for s in g for p in starters[s])
    total_par = sum(max(0, p["pts"] - repl[s]) for g in groups.values() for s in g for p in starters[s])
    for g, slots in groups.items():
        pts = [p["pts"] for s in slots for p in starters[s]]
        par = [max(0, p["pts"] - repl[s]) for s in slots for p in starters[s]]
        nslots = sum(SLOTS[s] for s in slots)
        out[g] = {
            "per_slot_avg": sum(pts) / (nslots * TEAMS),
            "share_pts": sum(pts) / total_pts,
            "share_par": sum(par) / total_par if total_par else 0,
            "slot_share": nslots / sum(SLOTS.values()),
            "top": max(pts), "median": st.median(pts),
        }
    out["repl"] = repl
    # top 15 overall by points above replacement
    allp = [(p["pts"] - repl[s], p["pts"], p["name"], s) for s in starters for p in starters[s]]
    out["top15"] = sorted(allp, reverse=True)[:15]
    # component shares among starters
    hs = [p for s in groups["Hitters"] for p in starters[s]]
    ps = [p for s in ("SP", "RP") for p in starters[s]]
    comp_h = {k: sum(wh.get(k, 0) * h[k] for h in hs) for k in wh}
    comp_p = {k: sum(wp.get(k, 0) * p[k] for p in ps) for k in wp}
    th, tp = sum(comp_h.values()), sum(abs(v) for v in comp_p.values())
    out["comp_h"] = {k: v / th for k, v in comp_h.items()}
    out["comp_p"] = {k: v / tp for k, v in comp_p.items()}
    out["players"] = {"h": {h["id"]: h for h in hitters}, "p": {p["id"]: p for p in pitchers}}
    return out


def stability(reports, wh, wp):
    """Season-to-season correlation of points for regulars (400+ PA, or 40+ IP as SP / 40+ G as RP)."""
    def corr(xs, ys):
        mx, my = st.mean(xs), st.mean(ys)
        sx = sum((x - mx) ** 2 for x in xs) ** .5; sy = sum((y - my) ** 2 for y in ys) ** .5
        return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)
    res = {}
    for kind, ok, rate in (("Hitters", lambda h: h["PA"] >= 400, lambda h: h["pts"] / h["PA"]),
                           ("SP", lambda p: p["role"] == "SP" and p["outs"] >= 300, lambda p: p["pts"] / p["GS"]),
                           ("RP", lambda p: p["role"] == "RP" and p["G"] >= 40, lambda p: p["pts"] / p["G"])):
        xs, ys = [], []
        key = "h" if kind == "Hitters" else "p"
        for a, b in ((2024, 2025), (2025, 2026)):
            A, B = reports[a]["players"][key], reports[b]["players"][key]
            for pid, pa in A.items():
                pb = B.get(pid)
                if pb and ok(pa) and ok(pb):
                    xs.append(rate(pa)); ys.append(rate(pb))
        res[kind] = (corr(xs, ys), len(xs))
    return res


def run(name, wh, wp, show=True):
    reports = {s: season_report(s, wh, wp) for s in SEASONS}
    stab = stability(reports, wh, wp)
    agg = {}
    for g in ("Hitters", "SP", "RP"):
        agg[g] = {k: st.mean(reports[s][g][k] for s in SEASONS) for k in ("per_slot_avg", "share_pts", "share_par", "slot_share", "top", "median")}
    if show:
        print(f"\n=== {name} ===")
        print(f"{'group':8} {'slots%':>7} {'pts%':>6} {'PAR%':>6} {'per-slot':>9} {'median':>7} {'top':>6} {'y2y r':>6}")
        for g in ("Hitters", "SP", "RP"):
            a = agg[g]
            print(f"{g:8} {a['slot_share']*100:7.1f} {a['share_pts']*100:6.1f} {a['share_par']*100:6.1f} {a['per_slot_avg']:9.1f} {a['median']:7.1f} {a['top']:6.1f} {stab[g][0]:6.3f} (n={stab[g][1]})")
    return reports, agg, stab


if __name__ == "__main__":
    pass
