# Scoring research

The league's point values (automation/core/sport.py, Constitution Article VIII,
and the Fantrax scoring settings) price every play at its run value, the way
FanGraphs' linear weights do, at 10 points per run.

- **Event values** come from FanGraphs' seasonal constants (Guts!) for 2021-2026,
  averaged: each event's runs above an average plate appearance, times 10. An out
  is set at -1 rather than its above-average value (-2.6), so everyday hitters
  stay positive. `values.py` does the arithmetic. The six seasons agree to within
  a tenth of a point, and they match the 2011 FanGraphs Points values closely.
- **Pitching** is the mirror image. Strikeouts, walks, hit batters and home runs
  count in full. A ball in play is regressed halfway to the league average, so a
  hit allowed costs half its run value (-2.6). Strikeouts use FanGraphs' FIP value
  (+2): the strict half-regressed figure is +1.2, but +2 makes starters' points
  repeat noticeably better (0.51 against 0.45).
- **The two values that are not run values**, the inning (+6, so +2 per out) and
  saves and holds (+6 / +4), were set against every MLB player's 2021-2026
  regular seasons: the inning so a 12-team league's starting pitchers carry their
  share of the lineup (28% of value above replacement), and saves and holds so
  relievers matter without the best closer outscoring the aces.

## Files

- `data/hitting_YYYY.csv`, `data/pitching_YYYY.csv`: every MLB player's
  regular-season totals, 2021-2026, from the MLB Stats API (`fetch.py`). Player
  sums match the 30 team totals in `data/team_*.csv` exactly for every season.
- `values.py`: event values from the FanGraphs constants and league totals.
- `calibrate.py`: scores every player, fills a 12-team league's lineup (C, 1B,
  2B, 3B, SS, 3 OF, 2 UTIL, 5 SP, 3 RP) with the best players, and measures how
  value above replacement splits between hitters, starters and relievers.
- `report.py IP SV HLD BS K`: shares, points per slot, repeatability, and with
  `--old` the same figures for the earlier draft values. Example:
  `python3 report.py 6.0 6 4 0 2.0 --old`
- `audit.py [season]`: one season's leaders, each slot's range, relievers against
  starters, and odd cases (swingmen, speed-only hitters, two-way players).

Pitchers count as starters when at least half their games (and 3 or more) were
starts. Value above replacement is a player's points minus the best unrostered
player who could fill the same slot.

## Results, 2021-2026 (averages of the six seasons)

| | Hitters | Starters | Relievers |
| --- | --- | --- | --- |
| Share of lineup slots | 55.6% | 27.8% | 16.7% |
| Share of value above replacement | 64.2% | 28.2% | 7.6% |
| Points per lineup slot, per season | 784 | 594 | 461 |
| Season-to-season repeatability (r) | 0.47 | 0.51 | 0.46 |

A rostered starter averages about 20 points a start and a rostered hitter about
5.5 a game. No reliever ranked among the 25 most valuable players in any season.

**Hits allowed at half weight**, tested on starters with 100+ innings:

| Hit weight | Points per hit | Matches that season's runs allowed (r) | Predicts next season's runs allowed (r) |
| --- | --- | --- | --- |
| None (pure FIP) | 0 | 0.76 | 0.37 |
| Half | -2.6 | 0.87 | 0.41 |
| Full | -5.4 | 0.88 | 0.40 |

A pitcher's actual runs allowed predict his next season's at r = 0.31.

**Saves and holds:** at +6 / +4 the best reliever each season ranked between the
9th and 27th best starter (only Emmanuel Clase's 2024 passed the 12th). At
+8 / +5 the top three closers of 2026 ranked with the top 12 starters, which is
why the values were lowered. Blown saves are not scored: removing them left
relievers' share of value unchanged and made their points repeat better, and a
closer's blown-save rate does not carry over from one season to the next
(r = 0.02).

**Not scored, after testing:** sac flies, an extra hitter strikeout penalty and
double plays (none improved repeatability, and they depend on who is on base),
and earned runs (better at describing a season, worse at predicting the next).
