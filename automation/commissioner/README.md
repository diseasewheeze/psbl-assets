# PSBL Commissioner Desk

Private reminders for the manual work that keeps the league on track, posted
to a commissioner-only Discord channel. It is the automated companion to the
Commissioner Season Checklists.

## What it sends

Two kinds of reminder share one channel:

**Fantrax-timed (this folder, `tasks.yaml`).** Each task fires once when an
anchor from the Fantrax season calendar plus an offset arrives. Dates move by
themselves when the real 2027-28 calendar is created.

| When | Reminder |
| --- | --- |
| 7 days and 1 day before Week 1 | Before Season essentials |
| Monday after the trade-deadline week | Confirm Fantrax blocks trades |
| Monday after Week 22 | Seed the playoffs, enter consolation round 1, record draft-order inputs |
| 3 hours after Week 22 is final | Data report from the final standings: playoff field and round 1, Presidents' Trophy, consolation bracket, ties to check, draft-order teams. Waits until Fantrax has counted every week. Potential Points is not in Fantrax's data feed, so copy it from Fantrax by hand. |
| 6 hours before each playoff round | Consolation entry, reseeding, championship rules, third place |
| After the Championship | Close-out list, then countdowns at day 14, 25 and 29 for prizes and the Season Ledger |

**Date-based (`../league-office/events.yaml`, channel `commissioner-desk`).**
Things Fantrax cannot know: League Calendar due date, draft announcement,
dues notice, dues deadline and 7-day escalation, last day to open an amendment
vote, trading reopening, scheduler token renewal and Fantrax Premium payment.
They are disabled templates until you give each a `starts_at` and set
`enabled: true`.

Public deadline reminders for owners stay in League Office as before. This
channel is only for you.

## Pick-trade alert

`picktrades.py` (workflow PSBL Pick Trades, every 15 minutes) compares Fantrax's
future-pick ownership with the last saved copy and posts one message to this
channel whenever a pick changes owner. Fantrax processes trades without your
approval and shows a pick only after the trade has gone through, so a 1st- or
2nd-round pick traded before the seller's prepayment is confirmed is reversed
(Art. 12.2 to 12.5). Rounds 3 to 5 are listed for your records only.

**Automatic ledger check (optional, recommended).** The alert can read the
League Ledger's **Pick Clearance** tab, which lists each franchise's Fantrax
team ID and the Season it is paid through. Each 1st- or 2nd-round move then
says **PAID** (no action) or **NOT PAID** (reverse the whole trade). To turn it
on:

1. In the ledger, fill in each franchise's Fantrax team ID on the Settings tab.
   Run this workflow in `preview` mode to print every team's ID and name.
2. In Google Sheets: File > Share > Publish to web. Under "Link", pick the
   **Pick Clearance** tab (not "Entire document") and **Comma-separated values
   (.csv)**, then Publish and copy the link. Only that tab is published: team
   IDs, franchise names and paid-through Seasons, no amounts.
3. In GitHub: Settings > Secrets and variables > Actions > New repository
   secret named `LEAGUE_LEDGER_CLEARANCE_CSV`, value = that link.

Google refreshes a published tab within about five minutes of an edit, so
confirm a payment in the ledger a few minutes before the trade. If the link is
missing or can't be read, the alert falls back to asking you to check the
ledger by hand. When you reverse a trade, the picks moving back are recognized
(for 14 days) and reported as a reversal instead of a new trade.

The first run only saves a baseline. Use mode `test` for a sample alert and
`preview` to see what would post.

## Minor-eligibility watch

`minors.py` (workflow PSBL Minor Eligibility, once a day at 7 AM) matches every
rostered player to an MLB player by name, MLB team and position and reads his
career MLB regular-season totals from the MLB Stats API
(`automation/core/mlb_people.py`). It posts here when a rostered player crosses
an Article VII limit since the last run: more than 130 career at-bats or more
than 50 career innings pitched (the numbers come from `automation/core/sport.py`).
At-bats count from his hitting stats only; the at-bats a pitcher faced never
count. There is no age limit. The message says whether Fantrax shows the player
in a minor slot right now; if he is, his franchise has three calendar days after
notice (7.4). Players who were already ineligible are never repeated. The first
run only saves a baseline. `preview` mode also prints any players it could not
match to an MLB player (a name shared by two players on no clear team, or an
amateur MLB has no record of yet).

## Prospect board

`prospects.py` (workflow PSBL Prospect Board) posts MLB's ranked prospects for
the next MLB Draft here: the top 30 (`prospects.yaml`), with position, school,
age and, after the draft, the club and pick. It posts again only when the
rankings change (a new class, or a player moving five or more places). The
source is MLB's draft prospect list
(`https://statsapi.mlb.com/api/v1/draft/prospects/{year}`); until July the
board shows that year's class, from August the next year's.

MLB had not published the 2027 list on 2026-10-15 (the answer was an empty
list). Until it does, a run says so and posts nothing, and the scheduled job is
switched off: in `automation/scheduler/schedule.yaml` and
`automation/health/health_config.yaml` the `prospect-board` lines are commented
out. Remove the `#` from both once a `preview` run shows a ranked list.

## One-time setup

1. In Discord create a private channel visible only to you, for example
   `commissioner-desk`.
2. Channel settings > Integrations > Webhooks > New Webhook. Name it
   `PSBL Commissioner Desk` and copy the URL.
3. In GitHub: repository Settings > Secrets and variables > Actions > New
   repository secret named `LEAGUE_WEBHOOK_COMMISSIONER_DESK`.
4. Optional: put your Discord user ID (in quotes) in `ping_user_id` under
   `commissioner_desk` in `automation/league.yaml` to be @mentioned.
5. Actions > PSBL Commissioner Desk > Run workflow > mode `test`. You should
   see one `[TEST]` message.

## Checking it

- `preview` mode prints every task with its trigger time and whether it is
  early, due, overdue, already sent or expired. Add `at` (for example
  `2027-03-08T08:00`) to see what would post at that moment.
- The PSBL Scheduler starts the workflow hourly, so each reminder arrives
  within an hour of its trigger. Nothing is ever posted twice.
- **Late reminders are never silently dropped.** If GitHub or the scheduler
  was down, a reminder more than 36 hours late is still posted, titled
  `OVERDUE:` with "Was due" and the original time, for 7 days (30 for the
  close-out list, and until the due date for the prize countdowns). A
  countdown such as "Playoffs start in 6 hours" is dropped once that event
  has started, because it would only add noise.
- The first live run records anything already long past as handled, so
  turning this on mid-season does not flood the channel. Reminders that are
  on time at that moment still post.
- Automation Health reports a stale or failing Commissioner Desk run.

## Season rollover

Anchors are remembered in the saved state, so the 30-day prize countdown keeps
running even if you roll Fantrax into the next season before it finishes.
Nothing needs editing each year except dating the events in `events.yaml`.
