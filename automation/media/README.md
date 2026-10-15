# PSBL Morning Recap

Code: `morning.py` · Workflow: `.github/workflows/league-morning-recap.yml` ·
Channel: `📸│media` (webhook secret `LEAGUE_WEBHOOK_MEDIA`, the same one the
Wire's podcast posts use) · Settings: `morning_recap` in `automation/league.yaml`

Every morning at about **8:30 AM ET**, after a day with MLB regular-season or
postseason games, the channel gets:

1. **LAST NIGHT IN MLB**: one line per final game, winner in bold, with
   extra innings, games called early and doubleheader games marked, the
   pitchers of record (W, L, S) and **Recap** and **Condensed** links to
   MLB.com (a missing link is left out), e.g.
   `**CHC 2**, STL 1 (game 2, 10 inn.) · W: Smith · L: Jones · [Recap](…) · [Condensed](…)`.
   Postponed games close the list with their makeup date. A very long day
   splits into a second embed.
2. **THE PSBL HOME RUN REEL**: only when a player on a PSBL roster homered. One
   field per franchise, e.g. `Hale (NYY) — 2 HR [▶](clip) [▶](clip)`. ▶ opens
   the home run on MLB.com. Nobody is mentioned.

Days without MLB games post nothing. It runs all year, so the MLB postseason
is covered after the PSBL season ends.

**Links only.** Nothing is downloaded or re-uploaded; Discord builds the
previews from MLB.com.

## Data

- MLB schedule for the day with `hydrate=linescore,decisions,scoringplays`
  (`automation/core/mlb.py`): finals, innings, pitchers of record and every
  home run (a home run is always a scoring play). One request.
- MLB game content for each final game (`/api/v1/game/{gamePk}/content`): the
  recap story (`editorial.recap.mlb`), the condensed game (the "Extended
  Highlights" group) and per-play clips (`highlights.highlights.items`; a
  home-run clip names its batter by MLB id, and a clip that names two batters,
  such as back-to-back homers, is not used). Content that cannot be read only
  drops that game's links.
- Fantrax `getTeamRosters` + `getPlayerIds` for PSBL ownership, matched with
  the Wire's roster matching (`automation/wire/roster.py`): name, narrowed by
  MLB club. A name two players share on different clubs is told apart by club;
  anything still ambiguous is skipped, because wrong credit is worse than none.
  While every PSBL roster is empty, the reel is skipped and the player
  directory is not read.

The test fixtures (`automation/tests/fixtures/mlb_schedule_2027-04_synthetic.json`,
`mlb_content_2027-04-13_synthetic.json`, and the MLB-shaped Fantrax variants)
are hand-built in the shapes checked live, not captures.

## Posting once

State (`state/morning_recap.json`, saved on the `automation-state` branch) is
keyed by MLB date and records each message as it goes out. A re-run never
repeats a message. If a post fails or Fantrax cannot be read, the run fails and
the scheduler retries it (up to 3 times); the retry posts only what is missing.
A Fantrax outage still lets the scores go out; the reel follows on the retry
that can read the rosters. (Empty PSBL rosters are not an outage: that day has
no reel.)

## Trying it

Actions → **PSBL Morning Recap** → Run workflow:

- `preview` prints every message in the log; nothing is posted or recorded.
- `test` posts `[TEST]` copies to 📸│media; nothing is recorded.
- `live` posts the day once (the scheduler uses this).
- `date` (optional, `YYYY-MM-DD`) picks another MLB date, for example a
  recent one to preview.

Locally: `python automation/media/morning.py --mode preview --date 2026-09-26`.
Tests: `python automation/media/test_morning.py`.
