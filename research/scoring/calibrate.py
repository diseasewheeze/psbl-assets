"""Score every 2021-2026 MLB player under the PSBL run-value system and calibrate the pitching dials.

Fill a 12-team league's lineup (C, 1B, 2B, 3B, SS, 3 OF, 2 UTIL, 5 SP, 3 RP) with the best players by points,
then measure how value above replacement splits between hitters, starters and relievers."""
import csv, statistics as st
from collections import defaultdict
from pathlib import Path
D = Path(__file__).parent / "data"
SEASONS = range(2021, 2027)
TEAMS = 12
SLOTS = {"C": 1, "1B": 1, "2B": 1, "3B": 1, "SS": 1, "OF": 3, "UTIL": 2, "SP": 5, "RP": 3}
OF = {"LF", "CF", "RF", "OF"}
TARGET = {"Hitters": 10 / 18, "SP": 5 / 18, "RP": 3 / 18}

# hitting: net points per event; every at-bat without a hit is -1
HIT = {"1B": 4.6, "2B": 7.6, "3B": 10.3, "HR": 14.0, "BB": 3.1, "HBP": 3.3, "SB": 2.0, "CS": -4.1}
# pitching run values (balls in play regressed halfway; strikeouts at FanGraphs' FIP value of 2);
# the inning value and SV/HLD are the dials, set by calibration
PIT = {"K": 2.0, "H": -2.6, "HRX": -11.4, "BB": -3.1, "HBP": -3.3}

def f(r, k):
    try: return float(r[k])
    except (KeyError, ValueError): return 0.0

def load(season):
    hitters = []
    for r in csv.DictReader(open(D / f"hitting_{season}.csv")):
        if r["pos"] == "P" or f(r, "plateAppearances") <= 0:
            continue
        h = {k: f(r, k) for k in r if k not in ("id", "name", "pos", "team")}
        h["1B"] = h["hits"] - h["doubles"] - h["triples"] - h["homeRuns"]
        pos = r["pos"]
        h.update(id=r["id"], name=r["name"], pos="OF" if pos in OF else ("DH" if pos == "TWP" else pos))
        hitters.append(h)
    pitchers = []
    for r in csv.DictReader(open(D / f"pitching_{season}.csv")):
        p = {k: f(r, k) for k in r if k not in ("id", "name", "pos", "team")}
        if p["gamesPlayed"] <= 0:
            continue
        p.update(id=r["id"], name=r["name"])
        p["role"] = "SP" if p["gamesStarted"] >= 0.5 * p["gamesPlayed"] and p["gamesStarted"] >= 3 else "RP"
        pitchers.append(p)
    return hitters, pitchers

DATA = {s: load(s) for s in SEASONS}

def hit_pts(h):
    return (-(h["atBats"] - h["hits"]) + HIT["1B"] * h["1B"] + HIT["2B"] * h["doubles"] + HIT["3B"] * h["triples"]
            + HIT["HR"] * h["homeRuns"] + HIT["BB"] * h["baseOnBalls"] + HIT["HBP"] * h["hitByPitch"]
            + HIT["SB"] * h["stolenBases"] + HIT["CS"] * h["caughtStealing"])

def pit_pts(p, ip, sv, hld, bs, k=None):
    k = PIT["K"] if k is None else k
    return (ip / 3 * p["outs"] + k * p["strikeOuts"] + PIT["H"] * p["hits"] + PIT["HRX"] * p["homeRuns"]
            + PIT["BB"] * p["baseOnBalls"] + PIT["HBP"] * p["hitBatsmen"]
            + sv * p["saves"] + hld * p["holds"] - bs * p["blownSaves"])

def fill(hitters, pitchers):
    used, starters = set(), defaultdict(list)
    ranked = sorted(hitters, key=lambda x: -x["pts"])
    for slot in ("C", "SS", "2B", "3B", "1B", "OF"):
        for h in ranked:
            if len(starters[slot]) >= SLOTS[slot] * TEAMS: break
            if h["id"] not in used and h["pos"] == slot:
                starters[slot].append(h); used.add(h["id"])
    for h in ranked:
        if len(starters["UTIL"]) >= SLOTS["UTIL"] * TEAMS: break
        if h["id"] not in used:
            starters["UTIL"].append(h); used.add(h["id"])
    repl = {}
    for slot in ("C", "SS", "2B", "3B", "1B", "OF"):
        rest = [h["pts"] for h in ranked if h["id"] not in used and h["pos"] == slot]
        repl[slot] = rest[0] if rest else 0.0
    repl["UTIL"] = next((h["pts"] for h in ranked if h["id"] not in used), 0.0)
    for role in ("SP", "RP"):
        pool = sorted((p for p in pitchers if p["role"] == role), key=lambda x: -x["pts"])
        n = SLOTS[role] * TEAMS
        starters[role] = pool[:n]; repl[role] = pool[n]["pts"]
    return starters, repl

GROUPS = {"Hitters": ("C", "1B", "2B", "3B", "SS", "OF", "UTIL"), "SP": ("SP",), "RP": ("RP",)}

def season(s, ip, sv, hld, bs, k=None):
    hitters, pitchers = DATA[s]
    for h in hitters: h["pts"] = hit_pts(h)
    for p in pitchers: p["pts"] = pit_pts(p, ip, sv, hld, bs, k)
    starters, repl = fill(hitters, pitchers)
    par = {g: sum(max(0, x["pts"] - repl[sl]) for sl in sls for x in starters[sl]) for g, sls in GROUPS.items()}
    pts = {g: sum(x["pts"] for sl in sls for x in starters[sl]) for g, sls in GROUPS.items()}
    tot_par, tot_pts = sum(par.values()), sum(pts.values())
    out = {"par": {g: par[g] / tot_par for g in GROUPS}, "pts": {g: pts[g] / tot_pts for g in GROUPS},
           "per_slot": {g: pts[g] / (sum(SLOTS[sl] for sl in sls) * TEAMS) for g, sls in GROUPS.items()},
           "starters": starters, "repl": repl}
    allp = [(x["pts"] - repl[sl], x["pts"], x["name"], sl) for sl in starters for x in starters[sl]]
    out["top25"] = sorted(allp, reverse=True)[:25]
    return out

def shares(ip, sv, hld, bs, k=None):
    rs = [season(s, ip, sv, hld, bs, k) for s in SEASONS]
    return {g: st.mean(r["par"][g] for r in rs) for g in GROUPS}, rs
