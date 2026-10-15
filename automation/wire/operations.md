# The Wire: Operations

## Architecture

**GitHub Actions = brain**
**Discord webhooks = delivery**
**MLB's official transaction log = the one source for `🔄│mlb-transactions`**

## Files

- `wire.py`: source collectors (RSS feeds and MLB's transaction log) and the headline classifier.
- `engine.py`: source order, routing, persistent dedupe, shadow and live modes, flood guards and Discord delivery. The workflow's entry point.
- `roster.py`: PSBL roster tags (name, MLB team, pitcher or hitter) and opt-in owner pings.
- `sources.yaml`: the source registry.
- `state/shadow.json`, `state/live.json`: dedupe state, kept on the `automation-state` branch.
- `.github/workflows/league-wire-engine.yml`: started in live mode every 15 minutes by the PSBL Scheduler.
- MLB reads go through `automation/core/mlb_people.py`.

## Live sources by channel

### 🚨│breaking-news / 📰│mlb-news
- MLB.com News, Tier 0, may post Breaking News.
- MLB Trade Rumors (FeedBurner address), Tier 1. Its transaction headlines are recorded but not posted.

CBS Sports MLB stays discovery only: its feed mixes betting promos and other sports into MLB headlines.

### 🏥│injury-report
- MLB Transactions: injured-list placements, activations, transfers, and rehab assignments, each with the player's name, club and position.
- MLB.com and MLB Trade Rumors headlines with injury words.

### 🔄│mlb-transactions
- MLB Transactions only (`https://statsapi.mlb.com/api/v1/transactions?sportId=1`, today and yesterday). A trade is one post with every player in it. A minor-league contract or a plain draft-pick signing posts only when the player is on a PSBL roster (`unrostered_skipped` in the summary otherwise).

### 🌱│prospect-wire
- FanGraphs Prospects.
- Prospects Live.

### 📸│media
- Fantasy Baseball Today, Prospects Live Podcast, Locked On Fantasy Baseball, Pitcher List Fantasy Baseball, In This League Fantasy Baseball.

## Dedupe behavior

State is kept per mode for **30 days**. Exact repeats are suppressed for the whole window by source id, canonical URL and normalized headline. Near-duplicate headlines are suppressed for **48 hours** within one channel, and the same story from two outlets in MLB News or Breaking News for **6 hours**.

Official transaction records are compared only by their own ids: two real moves can read almost alike ("Reds recalled RHP X from Louisville Bats"). A move MLB lists twice under different ids is posted once. Within **12 hours** of an official injured-list record, another outlet's injury story about the same player is skipped unless it reports something worse (surgery, weeks or months out, the 60-day list).

Sources are processed by trust tier, official first.

## Flood guards

Individual posts per run are capped at **6 in total** and **3 per channel**. Stories over either limit are logged as `RATE-GUARD ROUNDUP` and combined into **one roundup post per channel** ("Injury Report — 7 more updates"), each line with its link, source and PSBL roster tag. Nothing is silently dropped:

- Roundup stories are remembered only after the roundup is delivered; a failed roundup (`ROUNDUP NOT POSTED`) is retried next run.
- If a roundup would exceed Discord's embed size, the rest is counted as "+N more not shown" and logged as `RATE-GUARD SUPPRESSED`. Automation Health alerts if that happens in consecutive runs.

Stories about rostered players get the individual posts first.

## Shadow mode

Manual runs default to `shadow` and offer two extra controls:

- `reset_state`: clears the chosen mode's dedupe state first (testing only).
- `include_discovery`: also reads the discovery sources for that run.

Shadow mode fetches, classifies and routes, prints what **would** be posted, never calls Discord, and records dedupe state so repeats disappear from later shadow runs.

## Live safety rail

The first `--mode live` run on an empty state records everything and posts nothing. After that, a source marked `baseline_first: true` gets the same treatment on its own first live run (`NEW SOURCE BASELINE` in the log), so adding a feed never replays its backlog. Every source in `sources.yaml` is marked that way, so the move from the old feeds starts quietly.

## Discord webhook secrets

One Discord webhook per automated channel, stored under
`GitHub → psbl-assets → Settings → Secrets and variables → Actions`:

- `LEAGUE_WEBHOOK_BREAKING_NEWS`
- `LEAGUE_WEBHOOK_MLB_NEWS`
- `LEAGUE_WEBHOOK_INJURY_REPORT`
- `LEAGUE_WEBHOOK_MLB_TRANSACTIONS`
- `LEAGUE_WEBHOOK_PROSPECT_WIRE`
- `LEAGUE_WEBHOOK_MEDIA`

Never commit webhook URLs.

## Production monitoring

A quiet scheduled run looks like:

`SUMMARY mode=live posted=0 ... duplicates=<many> ... primary_skipped=0 unrostered_skipped=<some> digested=0 digest_posts=0 suppressed=0`

Investigate:

- repeated `SOURCE ERROR` lines (a feed moved, or MLB's API answered with something unexpected),
- `DELIVERY ERROR` or `NOT POSTED`,
- unexpected `RATE-GUARD SUPPRESSED` counts,
- an unusual burst of posts in Discord.

A shadow run shows the current routing without posting anything.
