import sys, statistics as st
sys.path.insert(0, ".")
import calibrate as T

def corr(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    sx = sum((x - mx) ** 2 for x in xs) ** .5; sy = sum((y - my) ** 2 for y in ys) ** .5
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)

def stability(score_h, score_p):
    res = {}
    specs = (("Hitters", 0, lambda h: h["plateAppearances"] >= 400, lambda h: score_h(h) / h["plateAppearances"]),
             ("SP", 1, lambda p: p["role"] == "SP" and p["outs"] >= 300, lambda p: score_p(p) / p["gamesStarted"]),
             ("RP", 1, lambda p: p["role"] == "RP" and p["gamesPlayed"] >= 40, lambda p: score_p(p) / p["gamesPlayed"]))
    for kind, i, ok, rate in specs:
        xs, ys = [], []
        for a in range(2021, 2026):
            A = {x["id"]: x for x in T.DATA[a][i]}; B = {x["id"]: x for x in T.DATA[a + 1][i]}
            for pid, pa in A.items():
                pb = B.get(pid)
                if pb and ok(pa) and ok(pb):
                    xs.append(rate(pa)); ys.append(rate(pb))
        res[kind] = (corr(xs, ys), len(xs))
    return res

# the league's current preliminary values, for comparison
def old_h(h):
    return (h["1B"] + 2 * h["doubles"] + 3 * h["triples"] + 4 * h["homeRuns"] + h["runs"] + h["rbi"] + h["baseOnBalls"]
            + h["hitByPitch"] + 2 * h["stolenBases"] - h["caughtStealing"] - 0.5 * h["strikeOuts"])
def old_p(p):
    return (p["outs"] + 1.25 * p["strikeOuts"] - p["hits"] - p["baseOnBalls"] - p["hitBatsmen"] - 2 * p["earnedRuns"]
            + 2 * p["wins"] - p["losses"] + 6 * p["saves"] + 4 * p["holds"])

def run_custom(score_h, score_p):
    """Same fill, arbitrary scoring functions."""
    out = []
    for s in T.SEASONS:
        hitters, pitchers = T.DATA[s]
        for h in hitters: h["pts"] = score_h(h)
        for p in pitchers: p["pts"] = score_p(p)
        starters, repl = T.fill(hitters, pitchers)
        par = {g: sum(max(0, x["pts"] - repl[sl]) for sl in sls for x in starters[sl]) for g, sls in T.GROUPS.items()}
        tot = sum(par.values())
        per_slot = {g: sum(x["pts"] for sl in sls for x in starters[sl]) / (sum(T.SLOTS[sl] for sl in sls) * T.TEAMS)
                    for g, sls in T.GROUPS.items()}
        allp = sorted(((x["pts"] - repl[sl], x["pts"], x["name"], sl) for sl in starters for x in starters[sl]), reverse=True)
        sp = starters["SP"]
        out.append({"par": {g: par[g] / tot for g in par}, "per_slot": per_slot,
                    "rp_top25": sum(1 for t in allp[:25] if t[3] == "RP"),
                    "pts_per_start": sum(p["pts"] for p in sp) / sum(p["gamesStarted"] for p in sp),
                    "hit_per_game": sum(x["pts"] for sl in T.GROUPS["Hitters"] for x in starters[sl])
                                    / sum(x["gamesPlayed"] for sl in T.GROUPS["Hitters"] for x in starters[sl]),
                    "top": allp[:10], "starters": starters, "repl": repl})
    return out

def summarize(name, rs, stab):
    m = lambda f: st.mean(f(r) for r in rs)
    print(f"\n=== {name} ===")
    print(f"share of value above replacement: hitters {m(lambda r: r['par']['Hitters'])*100:.1f}%  SP {m(lambda r: r['par']['SP'])*100:.1f}%  RP {m(lambda r: r['par']['RP'])*100:.1f}%")
    print(f"points per lineup slot per season: hitter {m(lambda r: r['per_slot']['Hitters']):.0f}  SP {m(lambda r: r['per_slot']['SP']):.0f}  RP {m(lambda r: r['per_slot']['RP']):.0f}")
    print(f"rostered SP points per start {m(lambda r: r['pts_per_start']):.1f} | rostered hitter points per game {m(lambda r: r['hit_per_game']):.2f}")
    print(f"relievers in the top 25 by season: {[r['rp_top25'] for r in rs]}")
    print("repeatability: " + "  ".join(f"{k} {v[0]:.3f} (n={v[1]})" for k, v in stab.items()))

if __name__ == "__main__":
    ip, sv, hld, bs = (float(x) for x in sys.argv[1:5])
    k = float(sys.argv[5]) if len(sys.argv) > 5 else None
    new_h = T.hit_pts
    new_p = lambda p: T.pit_pts(p, ip, sv, hld, bs, k)
    rs = run_custom(new_h, new_p)
    summarize(f"run values: IP {ip}, K bonus {k or T.PIT['K']}, SV {sv}, HLD {hld}, BS -{bs}", rs, stability(new_h, new_p))
    if "--old" in sys.argv or len(sys.argv) > 6:
        ro = run_custom(old_h, old_p)
        summarize("current preliminary values", ro, stability(old_h, old_p))
