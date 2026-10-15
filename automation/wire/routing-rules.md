# The Wire: Routing Rules

## General principles
1. One story goes to one channel.
2. Higher-priority routes win.
3. Posts are a headline, a link and the source; articles are never republished.
4. Rumors, opinion, predictions, betting picks, game threads, lineups, start times and feed-navigation items never reach a specialty channel; most are filtered out entirely.
5. `🔄│mlb-transactions` has one source, MLB's official transaction log. Other outlets' transaction headlines are recorded, not posted.
6. Community feeds (r/baseball) are discovery only and count only when a post names its reporter (`[Passan] ...`).

## Route priority
`breaking-news` → `injury-report` → `mlb-transactions` → `prospect-wire` → `mlb-news`

## 🚨│breaking-news
Needs a source with `breaking_allowed: true` (MLB.com) and a high-impact headline:
- out for the season / season-ending / rest of the season
- out for months, or a torn ACL, Achilles or UCL
- Tommy John surgery
- suspended indefinitely or for the season
- retirement
- fired / dismissed
- a trade the headline calls a blockbuster

## 🏥│injury-report
- official injured-list placements, activations and transfers, and rehab assignments (MLB's log)
- headlines with injury words: injured list, IL forms such as "10-day IL" or "off the IL", strain, sprain, oblique, hamstring, surgery, setback, MRI, day-to-day, scratched, ruled out
- a concrete absence: "out for the Twins' next two games", "will miss his next start"

## 🔄│mlb-transactions
MLB's official log: recalls, options, contract selections, designations for assignment, outrights, trades, releases, waiver claims and signings. A minor-league contract or a plain draft-pick signing posts only for a player on a PSBL roster.

Other outlets' headlines with transaction actions (traded, signs, designated for assignment, optioned, recalled, called up, claimed, released, opts out, exercises an option, extension) are routed here and then recorded without posting. Analysis keeps a headline in MLB News: questions, "why/how/what/should" openers, trade targets, values and rumors, "interested in", "pursued", grading a trade.

## 🌱│prospect-wire
Prospect feeds (FanGraphs Prospects, Prospects Live) always post here. Other headlines come here when they mention prospects, rookies, the minor leagues (Triple-A, Double-A, High-A, Single-A), the Arizona Fall League, the Futures Game, the MLB Draft, farm systems, top-100 lists or an MLB debut.

## 📰│mlb-news
Everything relevant that matches no specialty channel: team and league news, interviews, awards, front-office moves, meaningful analysis.

## Duplicate suppression
- the same source id, canonical URL or headline is never posted twice in 30 days
- near-identical headlines in one channel within 48 hours
- the same story from two outlets in MLB News or Breaking News within 6 hours
- an outlet's injury story about a player MLB's log put on the injured list within 12 hours, unless it reports something worse

Official transaction records are told apart only by their own ids, because two real moves can read almost the same ("recalled RHP X from ...").
