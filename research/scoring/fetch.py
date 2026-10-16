"""Pull MLB regular-season player and team totals for 2021-2026 from the MLB Stats API."""
import csv, json, sys, time, urllib.request
from pathlib import Path
OUT = Path(__file__).parent / "data"
API = "https://statsapi.mlb.com/api/v1"
HIT = ["gamesPlayed","plateAppearances","atBats","hits","doubles","triples","homeRuns","runs","rbi","baseOnBalls",
       "intentionalWalks","hitByPitch","stolenBases","caughtStealing","strikeOuts","sacFlies","sacBunts","groundIntoDoublePlay"]
PIT = ["gamesPlayed","gamesStarted","gamesFinished","outs","battersFaced","hits","doubles","triples","homeRuns","earnedRuns","runs",
       "baseOnBalls","intentionalWalks","hitBatsmen","strikeOuts","sacFlies","wins","losses","saves","holds","blownSaves",
       "saveOpportunities","inheritedRunners","inheritedRunnersScored","groundIntoDoublePlay"]

def get(url):
    for i in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            print("retry", url, e, file=sys.stderr); time.sleep(2 + 3 * i)
    raise SystemExit("failed " + url)

def players(season, group, fields):
    rows, offset = [], 0
    while True:
        d = get(f"{API}/stats?stats=season&group={group}&season={season}&sportId=1&gameType=R&playerPool=ALL&limit=1000&offset={offset}")
        s = d["stats"][0]; sp = s["splits"]
        for x in sp:
            st = x["stat"]
            rows.append([x["player"]["id"], x["player"]["fullName"], x.get("position", {}).get("abbreviation", ""),
                         x.get("numTeams", 1), x.get("team", {}).get("id", "")] + [st.get(f, 0) for f in fields])
        offset += len(sp)
        if not sp or offset >= s.get("totalSplits", 0):
            break
    with open(OUT / f"{group}_{season}.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["id", "name", "pos", "numTeams", "team"] + fields); w.writerows(rows)
    return len(rows)

def teams(season, group, fields):
    d = get(f"{API}/teams/stats?stats=season&group={group}&season={season}&sportIds=1&gameType=R")
    rows = [[x["team"]["id"], x["team"]["name"]] + [x["stat"].get(f, 0) for f in fields] for x in d["stats"][0]["splits"]]
    with open(OUT / f"team_{group}_{season}.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["id", "name"] + fields); w.writerows(rows)
    return len(rows)

for season in range(2021, 2027):
    print(season, "hitting", players(season, "hitting", HIT), "pitching", players(season, "pitching", PIT),
          "teams", teams(season, "hitting", HIT), teams(season, "pitching", PIT), flush=True)
