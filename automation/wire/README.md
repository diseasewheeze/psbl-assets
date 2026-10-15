# The Wire

## Goal
A reliable, low-noise MLB news pipeline for the Pitch Slapped Baseball League Discord server.

## How it runs
The PSBL Scheduler starts the Wire every 15 minutes in **live** mode (`automation/scheduler/schedule.yaml`). Manual runs from the Actions tab default to **shadow** mode, which never posts.

Safeguards:
- persistent dedupe for 30 days (at most 5,000 remembered stories)
- fuzzy duplicate suppression, and one post per story when two outlets carry it
- a silent baseline on the first live run, and for every new source (`baseline_first: true`)
- per-run and per-channel flood guards, with the overflow combined into one roundup post per channel
- one failing source never stops the others; transient failures are retried once
- Discord retries on HTTP 429 and 5xx; `allowed_mentions` off except opted-in owner pings
- Automation Health watches for stale runs, persistent source failures and roundups that overflow in consecutive runs

## Discord channels
- `🚨│breaking-news`: only major, time-sensitive MLB developments.
- `📰│mlb-news`: national MLB news that fits no more specific channel.
- `🏥│injury-report`: injured-list placements, activations and transfers, rehab assignments, surgeries and availability news.
- `🔄│mlb-transactions`: recalls, options, contract selections, designations for assignment, outrights, trades, releases, waiver claims and signings, from MLB's official transaction log.
- `🌱│prospect-wire`: prospects, the minor leagues, the MLB Draft and debuts.
- `📸│media`: one post per new fantasy baseball podcast episode.
- `💬│news-desk`: people only; no automation.

## Sources
Live: MLB Transactions (MLB Stats API), MLB.com News, MLB Trade Rumors, FanGraphs Prospects, Prospects Live, and five podcasts (Fantasy Baseball Today, Prospects Live Podcast, Locked On Fantasy Baseball, Pitcher List Fantasy Baseball, In This League Fantasy Baseball).

Discovery only (manual runs with `include_discovery`): CBS Sports MLB.

Disabled until a shadow run shows they work: ESPN MLB (empty on 2026-10-15), r/baseball (not reachable from the 2026-10-15 check), MiLB.com News (stale since 2025).

Details and the check dates are in `sources.yaml` and `source-matrix.md`.

## Transactions come from MLB's own log
`wire.py` reads `https://statsapi.mlb.com/api/v1/transactions` (today and yesterday, league time) through `automation/core/mlb_people.py`. Injured-list moves and rehab assignments post to `🏥│injury-report`; roster moves post to `🔄│mlb-transactions`. A trade is one post naming every player in it. A minor-league contract, or a plain "signed" record (after the MLB Draft these are mostly draft picks), posts only when the player is on a PSBL roster. Status changes that aren't injured-list moves are left out.

Because the official log is the one source for `🔄│mlb-transactions`, other outlets' transaction headlines are recorded but not posted (`PRIMARY-SOURCE SKIP` in the log), so a move is announced once. An outlet's injury story about a player the log has just placed on the injured list is skipped too, unless it reports something worse (surgery, a longer absence).

## Routing priority
Each story posts to one channel:
1. Breaking News
2. Injury Report
3. MLB Transactions
4. Prospect Wire
5. MLB News

Transaction headlines are recognized by action words ("traded", "signs", "designated for assignment", "recalled"), not by broad nouns such as "trade" or "contract", so analysis and rumor pieces stay in MLB News. See `routing-rules.md`.

## Breaking-news standard
Hard to trigger on purpose: a season-ending or months-long injury (including Tommy John surgery), a major suspension, a retirement, a manager or GM firing, or a trade the headline itself calls a blockbuster, from an official or Tier 1 source. Routine signings, call-ups, short injuries, lineups, rumors, analysis and recaps never go there.

## PSBL roster tags
Stories about a player on a PSBL roster show which PSBL team owns him (`roster.py`):
- MLB transaction records carry the player's MLB club(s) and position, which separate players who share a name (two Will Smiths, several Luis Garcias). A traded player matches either club in the move.
- Headlines are scanned for full names of rostered players; a name any other MLB player shares is not tagged from a headline alone.
- Anything ambiguous is left untagged: a missing tag is better than a wrong one.
- Fantrax is read only when a run has new stories. If it can't be read, stories post without tags.

Owner pings are opt-in (`owners` and `wire_pings` in `automation/league.yaml`): only listed owners, only for their own players, only in `🏥│injury-report`.

## Security
Discord webhook URLs are credentials and live only in GitHub Actions Secrets:
- `LEAGUE_WEBHOOK_BREAKING_NEWS`
- `LEAGUE_WEBHOOK_MLB_NEWS`
- `LEAGUE_WEBHOOK_INJURY_REPORT`
- `LEAGUE_WEBHOOK_MLB_TRANSACTIONS`
- `LEAGUE_WEBHOOK_PROSPECT_WIRE`
- `LEAGUE_WEBHOOK_MEDIA`

## Maintenance
GitHub's built-in cron is best-effort, so the Wire is started by the PSBL Scheduler, driven by an external timer (`automation/scheduler/README.md`). Automation Health alerts if the Wire has not had a live run in 60 minutes. GitHub may disable scheduled workflows in a public repository after long inactivity, so check the Actions tab in the offseason.
