"""Audit the league values on one season: who leads, where relievers rank among starters, odd cases."""
import sys, statistics as st
sys.path.insert(0, ".")
import calibrate as T
T.PIT.update(K=2.0, H=-2.6, HRX=-11.4, BB=-3.1, HBP=-3.3)
IP, SV, HLD, BS = 6.0, 6, 4, 0
S = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
hitters, pitchers = T.DATA[S]
for h in hitters: h["pts"] = T.hit_pts(h)
for p in pitchers:
    p["pts"] = T.pit_pts(p, IP, SV, HLD, BS); p["ip"] = p["outs"] / 3
    p["lev"] = SV * p["saves"] + HLD * p["holds"]
starters, repl = T.fill(hitters, pitchers)
slot_of = {x["id"]: sl for sl in starters for x in starters[sl]}

def tag(x):
    return x.get("role") or x["pos"]

print("== A. Top 30 by raw points (all players)")
allp = sorted(hitters + pitchers, key=lambda x: -x["pts"])
for i, x in enumerate(allp[:30], 1):
    extra = f"{x['ip']:.0f} IP" if "ip" in x else f"{x['plateAppearances']:.0f} PA"
    print(f"{i:3}. {x['name'][:24]:24} {tag(x):4} {x['pts']:6.0f}  {extra}")
print("first pitcher at raw rank", next(i for i, x in enumerate(allp, 1) if "ip" in x),
      "| first reliever at raw rank", next(i for i, x in enumerate(allp, 1) if x.get("role") == "RP"))

print("\n== B. Top 30 by value above replacement")
par = sorted(((x["pts"] - repl[sl], x, sl) for sl in starters for x in starters[sl]), key=lambda t: -t[0])
for i, (v, x, sl) in enumerate(par[:30], 1):
    print(f"{i:3}. {x['name'][:24]:24} {sl:4} pts {x['pts']:6.0f}  above repl {v:5.0f}")
print("relievers in top 25/50/100 by value:", [sum(1 for t in par[:n] if t[2] == 'RP') for n in (25, 50, 100)])

print("\n== C. Each lineup slot: #1, #12, last rostered, replacement")
for sl in ("C", "1B", "2B", "3B", "SS", "OF", "UTIL", "SP", "RP"):
    xs = sorted(starters[sl], key=lambda x: -x["pts"])
    print(f"{sl:4} #1 {xs[0]['name'][:20]:20} {xs[0]['pts']:5.0f} | #12 {xs[11]['pts']:5.0f} | last ({len(xs)}) {xs[-1]['pts']:5.0f} | repl {repl[sl]:5.0f} | median {st.median(x['pts'] for x in xs):5.0f}")

print("\n== D. Relievers vs starters")
SPs = sorted(starters["SP"], key=lambda x: -x["pts"]); RPs = sorted(starters["RP"], key=lambda x: -x["pts"])
sp_pts = [p["pts"] for p in SPs]
for p in RPs[:12]:
    rank = sum(1 for v in sp_pts if v > p["pts"]) + 1
    print(f"  {p['name'][:22]:22} {p['pts']:5.0f} | SP rank {rank:3} | {p['ip']:5.1f} IP {p['strikeOuts']:3.0f} K SV {p['saves']:2.0f} HLD {p['holds']:2.0f} | from SV/HLD {p['lev']/p['pts']*100:4.0f}%")
sp_ip = sum(p["pts"] for p in SPs) / sum(p["ip"] for p in SPs); rp_ip = sum(p["pts"] for p in RPs) / sum(p["ip"] for p in RPs)
rp_ip_nolev = sum(p["pts"] - p["lev"] for p in RPs) / sum(p["ip"] for p in RPs)
print(f"  points per inning: rostered SP {sp_ip:.2f} | rostered RP {rp_ip:.2f} ({rp_ip_nolev:.2f} without SV/HLD)")
print(f"  per appearance: rostered SP per start {sum(p['pts'] for p in SPs)/sum(p['gamesStarted'] for p in SPs):.1f} | rostered RP per game {sum(p['pts'] for p in RPs)/sum(p['gamesPlayed'] for p in RPs):.1f}")
print(f"  per week (26): best SP {SPs[0]['pts']/26:.1f}, SP #30 {SPs[29]['pts']/26:.1f}, best RP {RPs[0]['pts']/26:.1f}, RP #12 {RPs[11]['pts']/26:.1f}, RP #36 {RPs[35]['pts']/26:.1f}")

print("\n== E. Relief-eligible pitchers with starter-like innings (GS>0 or 80+ IP), by points")
sw = sorted([p for p in pitchers if p["role"] == "RP" and (p["gamesStarted"] > 0 or p["ip"] >= 80)], key=lambda p: -p["pts"])[:10]
for p in sw:
    print(f"  {p['name'][:22]:22} {p['pts']:5.0f} | {p['ip']:5.1f} IP G {p['gamesPlayed']:3.0f} GS {p['gamesStarted']:2.0f} SV {p['saves']:2.0f} HLD {p['holds']:2.0f} | rostered as RP: {'yes' if slot_of.get(p['id'])=='RP' else 'no'}")
dual = sorted([p for p in pitchers if p["gamesStarted"] >= 5 and p["gamesPlayed"] - p["gamesStarted"] >= 5], key=lambda p: -p["pts"])[:8]
print("  likely dual SP/RP eligible (5+ starts and 5+ relief games):")
for p in dual:
    print(f"    {p['name'][:22]:22} {p['pts']:5.0f} | {p['ip']:5.1f} IP G {p['gamesPlayed']:3.0f} GS {p['gamesStarted']:2.0f} | counted as {p['role']}")

print("\n== F. Lowest regulars")
for h in sorted([h for h in hitters if h["plateAppearances"] >= 400], key=lambda h: h["pts"])[:5]:
    print(f"  hitter {h['name'][:22]:22} {h['pos']:3} {h['pts']:5.0f} pts in {h['plateAppearances']:.0f} PA")
for p in sorted([p for p in pitchers if p["ip"] >= 100], key=lambda p: p["pts"])[:5]:
    print(f"  pitcher {p['name'][:21]:21} {p['role']} {p['pts']:5.0f} pts in {p['ip']:.0f} IP (runs/9 {27*p['runs']/p['outs']:.2f})")
neg = [h for h in hitters if h["plateAppearances"] >= 300 and h["pts"] < 0]
print("  hitters with 300+ PA below zero:", len(neg), "| pitchers with 100+ IP below zero:", sum(1 for p in pitchers if p['ip'] >= 100 and p['pts'] < 0))

print("\n== G. Rate outliers (part-timers)")
for h in sorted([h for h in hitters if 150 <= h["plateAppearances"] < 400], key=lambda h: -h["pts"]/h["plateAppearances"])[:4]:
    print(f"  {h['name'][:22]:22} {h['pts']/h['plateAppearances']:.2f} pts/PA in {h['plateAppearances']:.0f} PA (rostered regulars avg {st.mean(x['pts']/x['plateAppearances'] for sl in T.GROUPS['Hitters'] for x in starters[sl]):.2f})")

print("\n== H. Speed: top base stealers")
for h in sorted(hitters, key=lambda h: -h["stolenBases"])[:6]:
    rk = sum(1 for x in hitters if x["pts"] > h["pts"]) + 1
    print(f"  {h['name'][:22]:22} SB {h['stolenBases']:2.0f} CS {h['caughtStealing']:2.0f} | steals net {2*h['stolenBases']-4.1*h['caughtStealing']:5.0f} of {h['pts']:5.0f} pts | hitter rank {rk}")

print("\n== I. Two-way and catchers")
for x in hitters + pitchers:
    if "Ohtani" in x["name"]:
        print(f"  {x['name']} {'pitching' if 'ip' in x else 'hitting'}: {x['pts']:.0f}")
Cs = sorted(starters["C"], key=lambda x: -x["pts"])
print(f"  catchers: #1 {Cs[0]['pts']:.0f}, #12 {Cs[11]['pts']:.0f}; per game rostered C {st.mean(x['pts']/x['gamesPlayed'] for x in Cs):.2f} vs other rostered hitters {st.mean(x['pts']/x['gamesPlayed'] for sl in ('1B','2B','3B','SS','OF') for x in starters[sl]):.2f}")
