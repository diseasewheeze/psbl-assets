# The Wire: Discord Webhooks

## Webhook identity
Posts appear as **DBL News Wire** with the league's webhook avatar.

## Channel webhooks
Create one webhook in each automated channel:

- `🚨│breaking-news`
- `📰│mlb-news`
- `🏥│injury-report`
- `🔄│mlb-transactions`
- `🌱│prospect-wire`
- `📸│media` (podcast episodes; the same webhook the other media posts use)

Do not create an automation webhook in `💬│news-desk`.

## GitHub Actions secret names
**Repository → Settings → Secrets and variables → Actions → New repository secret**, with these exact names:

- `LEAGUE_WEBHOOK_BREAKING_NEWS`
- `LEAGUE_WEBHOOK_MLB_NEWS`
- `LEAGUE_WEBHOOK_INJURY_REPORT`
- `LEAGUE_WEBHOOK_MLB_TRANSACTIONS`
- `LEAGUE_WEBHOOK_PROSPECT_WIRE`
- `LEAGUE_WEBHOOK_MEDIA`

A missing secret skips that channel's posts with a log line; the run still succeeds. Never paste a webhook URL into a committed file, issue, README, screenshot or public chat.

## Post style
Each post has the headline (linked), the source, the DBL roster tag when a rostered player is involved, and the publication time when the feed gives one. Official transactions link the player's MLB.com page and name the kind of move ("Injured list", "Trade", "Recalled"). Article bodies are never copied.
