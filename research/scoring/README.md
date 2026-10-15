# Scoring research

The league's point values (automation/core/sport.py, Constitution Article VIII)
were set against every MLB regular-season player line of 2024, 2025 and 2026.

- `data/hitting_YYYY.csv`, `data/pitching_YYYY.csv`: one row per player per season
  from the MLB Stats API season totals (2,258 hitter rows including pitchers who
  batted, 2,596 pitcher rows). Player sums match the 30 team totals in
  `data/team_*.csv` within 0.3% on every stat; the few remaining differences are
  single cells, too small to move any result below.
- `analyze.py`: scores every player under a set of values, fills a 12-team
  league's lineup (C, 1B, 2B, 3B, SS, 3 OF, 2 UTIL, 5 SP, 3 RP) with the best
  players, and reports how points and value above replacement split between
  hitters, starters and relievers, and how well each player's points repeat
  from one season to the next.

Pitchers count as starters when at least half their games (and 3 or more) were
starts. Value above replacement is a starter's points minus the best unrostered
player who could fill the same slot.

## Results (averages of the three seasons)

| Values | Hitters: share of value | Starters | Relievers | Starter points per slot | Starter repeatability | Reliever repeatability |
| --- | --- | --- | --- | --- | --- | --- |
| Share of lineup slots | 55.6% | 27.8% | 16.7% | | | |
| Typical redraft (W 7, L -5, SV 7, K 0.5, ER -1, no holds) | 58.8% | 25.3% | 15.9% | 368 | 0.448 | 0.663 |
| League values (K 1.25, ER -2, W 2, L -1, SV 6, HLD 4) | 59.6% | 28.5% | 11.9% | 406 | 0.543 | 0.604 |

Hitting values are the same in both rows: single 1, double 2, triple 3, home
run 4, run 1, RBI 1, walk 1, hit by pitch 1, stolen base 2, caught stealing -1,
strikeout -0.5. Hitters' points per lineup slot average 424 a season.

Under the typical redraft values, 4 to 6 relievers ranked in the 25 most
valuable players each season; under the league values, 0 to 3. Wins and losses
fall from about 8% of pitcher points to about 2%.

Run it: `python3 research/scoring/analyze.py` is a library; see the functions
`run()` and `season_report()`.
