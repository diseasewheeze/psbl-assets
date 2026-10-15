# The Wire: Test Plan

## Automated checks
`python automation/wire/test_wire.py` runs offline in the regression workflow (and locally without feedparser): headline routing, feed-noise filters, MLB transaction routing against a fixture in MLB's shape (`automation/tests/fixtures/mlb_transactions_2026-07-28.json`), roster tags for players who share a name, dedupe across outlets, flood guards and roundups, and the source registry.

## Before enabling a new source
1. Load the feed by hand and confirm it has current items.
2. Add it to `sources.yaml` with `baseline_first: true`.
3. Run PSBL Wire Engine manually in `shadow` mode (add `include_discovery` for a discovery source) and read the routing in the log.
4. Enable it. Its first live run only records what is already there.

## Routing examples
- `Braves ace to undergo Tommy John surgery` → `breaking-news` from MLB.com; otherwise `injury-report`
- `Pasquantino lands on 10-day IL with wrist soreness` → `injury-report`
- `Rays call up top prospect Carson Williams` → `mlb-transactions` (recorded; MLB's log posts the move)
- `Konnor Griffin makes MLB debut for Pirates` → `prospect-wire`
- `Grading the trade that sent Logan O'Hoppe to the Rangers` → `mlb-news`

## Live check after a change
1. Run in `shadow` mode and read the `SHADOW` lines.
2. Let the next scheduled live run post; check formatting, links and roster tags in Discord.
3. Watch the `SUMMARY` line for `SOURCE ERROR`, `DELIVERY ERROR` and `RATE-GUARD SUPPRESSED`.

## Offseason check
Scheduled workflows in a public repository can be disabled after 60 days without repository activity. Check the Actions tab before each season.
