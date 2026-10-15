# The Wire: Source Matrix

Checked 2026-10-15: every feed was loaded and its newest items read.

## Trust tiers
- **Tier 0**: official MLB source; may post Breaking News when the headline itself supports it.
- **Tier 1**: established national or specialist baseball outlet.
- **Tier 2**: reputable analysis outlet; normal channels only.
- **Tier 3**: community source; discovery only, never authoritative.

## Active sources

| Source | Method | Tier | Use | Breaking? | Notes |
|---|---|---:|---|---|---|
| MLB Transactions | MLB Stats API `/transactions?sportId=1` | 0 | Injury Report, MLB Transactions | No | The one source for `🔄│mlb-transactions`. Structured: player, clubs, type, MLB's own description. |
| MLB.com News | RSS `https://www.mlb.com/feeds/news/rss.xml` | 0 | MLB News, Breaking News | Yes | Official. Game-day items (`LIVE:`, start times, lineups) are filtered. |
| MLB Trade Rumors | RSS `https://feeds.feedburner.com/MlbTradeRumors` | 1 | MLB News, injuries | No | The site's own `/feed` served a January 2018 copy; FeedBurner is current. Polls, "Notes:" roundups and its minor-transaction digest are filtered. |
| FanGraphs Prospects | RSS `https://blogs.fangraphs.com/category/prospects/feed/` | 2 | Prospect Wire | No | Chats are filtered. |
| Prospects Live | RSS `https://www.prospectslive.com/feed/` | 2 | Prospect Wire | No | Dynasty-focused prospect coverage. |
| CBS Sports MLB | RSS `https://www.cbssports.com/rss/headlines/mlb` | 1 | Discovery only | No | Betting promos and other sports mixed in. |

## Podcasts (`📸│media`)

| Podcast | Feed |
|---|---|
| Fantasy Baseball Today (CBS Sports) | `https://rss.amperwave.net/v2/feed/audacynetwork/d4bae8cf54f36afd204b93ed7355d137` |
| Prospects Live Podcast (dynasty) | `https://www.spreaker.com/show/3147987/episodes/feed` |
| Locked On Fantasy Baseball | `https://feeds.simplecast.com/4vzt_3en` |
| Pitcher List Fantasy Baseball | `https://feeds.simplecast.com/Rbrm7xIB` |
| In This League Fantasy Baseball | `https://www.spreaker.com/show/3691391/episodes/feed` |

## Not active

| Source | Why |
|---|---|
| ESPN MLB RSS | Empty response on 2026-10-15. Disabled. |
| r/baseball | Could not be reached from the 2026-10-15 check. Disabled; discovery only once a shadow run shows it loads. |
| MiLB.com News RSS | Loads, but the newest item was from August 2025. Disabled. |
| Baseball America | Its feed refused automated reads (robots rules). |
| Fantasy Baseball Life (podcast) | Last episode in 2020. |

## Channel plan

- `🚨│breaking-news`: MLB.com only, high-impact headlines only.
- `📰│mlb-news`: MLB.com and MLB Trade Rumors.
- `🏥│injury-report`: MLB Transactions first; MLB.com and MLB Trade Rumors injury headlines when they add something.
- `🔄│mlb-transactions`: MLB Transactions only.
- `🌱│prospect-wire`: FanGraphs Prospects, Prospects Live, and prospect headlines from the news feeds.
- `📸│media`: the five podcasts.
