"""Event values (10 points per run) from FanGraphs' 2021-2026 seasonal constants and league totals."""
import csv, statistics as st
from pathlib import Path
D = Path(__file__).parent / "data"
# Season: lgwOBA, scale, wBB, wHBP, w1B, w2B, w3B, wHR, runCS  (FanGraphs Guts!)
GUTS = {2021: (.314, 1.209, .692, .722, .879, 1.242, 1.568, 2.007, -.419),
        2022: (.310, 1.259, .689, .720, .884, 1.261, 1.601, 2.072, -.397),
        2023: (.318, 1.204, .696, .726, .883, 1.244, 1.569, 2.004, -.422),
        2024: (.310, 1.242, .689, .720, .882, 1.254, 1.590, 2.050, -.405),
        2025: (.313, 1.232, .691, .722, .882, 1.252, 1.584, 2.037, -.410),
        2026: (.316, 1.238, .698, .729, .890, 1.261, 1.596, 2.049, -.412)}
SEASONS = tuple(GUTS)

def league(season):
    t = list(csv.DictReader(open(D / f"team_hitting_{season}.csv")))
    s = lambda k: sum(float(r[k]) for r in t)
    return {k: s(k) for k in ("atBats", "hits", "doubles", "triples", "homeRuns", "strikeOuts", "sacFlies")}

def season_values(season):
    w, sc, bb, hbp, b1, b2, b3, hr, cs = GUTS[season]
    aa = lambda x: (x - w) / sc                      # runs above an average PA
    v = {"BB": aa(bb), "HBP": aa(hbp), "1B": aa(b1), "2B": aa(b2), "3B": aa(b3), "HR": aa(hr), "out": -w / sc,
         "SB": 0.2, "CS": cs}
    L = league(season)
    singles = L["hits"] - L["doubles"] - L["triples"] - L["homeRuns"]
    bip_hits = L["hits"] - L["homeRuns"]
    v["bip_hit"] = (singles * v["1B"] + L["doubles"] * v["2B"] + L["triples"] * v["3B"]) / bip_hits
    bip = L["atBats"] - L["strikeOuts"] - L["homeRuns"] + L["sacFlies"]
    v["babip"] = bip_hits / bip
    v["avg_bip"] = v["babip"] * v["bip_hit"] + (1 - v["babip"]) * v["out"]
    return v

def averaged():
    per = [season_values(s) for s in SEASONS]
    return {k: st.mean(p[k] for p in per) for k in per[0]}, per

if __name__ == "__main__":
    avg, per = averaged()
    print("season  " + " ".join(f"{k:>7}" for k in per[0]))
    for s, p in zip(SEASONS, per):
        print(s, "  " + " ".join(f"{p[k]:7.3f}" for k in p))
    print("avg   " + "  " + " ".join(f"{avg[k]:7.3f}" for k in avg))
    v = avg
    print("\nHITTER points (net, x10): out -1 | " + " ".join(f"{k} {10*v[k]:.1f}" for k in ("1B","2B","3B","HR","BB","HBP","SB","CS")))
    # pitcher mirror with balls in play regressed halfway to the league average
    k_val   = -10 * v["out"]
    bip_out = -10 * (0.5 * v["out"] + 0.5 * v["avg_bip"])
    bip_hit = -10 * (0.5 * v["bip_hit"] + 0.5 * v["avg_bip"])
    print(f"PITCHER (above average, x10): K {k_val:.2f} | BIP out {bip_out:.2f} | BIP hit {bip_hit:.2f} | BB {-10*v['BB']:.2f} | HBP {-10*v['HBP']:.2f} | HR {-10*v['HR']:.2f}")
    print(f"  as Fantrax entries: per out {bip_out:.2f} (+shift) | K bonus {k_val-bip_out:.2f} | H {bip_hit:.2f} | HR extra {-10*v['HR']-bip_hit:.2f} | BB {-10*v['BB']:.2f} | HBP {-10*v['HBP']:.2f}")
