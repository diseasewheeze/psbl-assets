#!/usr/bin/env python3
"""Reusable League Office / Trade Center message templates and Discohook bundles.

1. Writes the reusable templates (placeholders in `backticks`) into templates/.
2. Builds one Discohook bundle per purpose in discohook-backups/ (messages array).
3. Builds discohook.org links for every channel-intro message, constitution
   message and bundle, written to discohook-backups/LINKS.md and links.json.

Every template and link is one Discord message in the PSBL format from
discohook_format.py (footer text and divider on the final embed only). Bundles
are libraries of separate one-message templates: open one, keep the message you
need, send it.

Build order: build_channel_intros.py, normalize_discohook_templates.py,
build_news_templates.py, build_send_console.py.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import discohook_format as fmt  # noqa: E402
import posted_messages as posted  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
T = ROOT / "templates"
OUT = ROOT / "discohook-backups"

GOLD, ALERT, RECORD = 12398649, 10697266, 795456  # red #BD3039, dark red, navy #0C2340
LO = "PSBL LEAGUE OFFICE"


def tmpl(path: str, title: str, desc: str, footer: str, fields: list[tuple[str, str]], color: int = GOLD,
         banner: str | None = None, thread_name: str | None = None) -> None:
    """Write one template. thread_name pre-fills Discohook's forum thread name for a forum post."""
    data = {"embeds": fmt.apply([{
        "title": title, "description": desc, "color": color, "footer": {"text": footer},
        "fields": [{"name": n, "value": v, "inline": False} for n, v in fields],
    }], banner, path)}
    if thread_name:
        data["thread_name"] = thread_name
    data = posted.keep_posted(path, data)
    p = T / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- announcements
tmpl("league-office/24_season_closing.json", "PSBL SEASON COMPLETE", "`[SEASON, for example 2027]` is officially in the books.", "PSBL RECORDS DEPARTMENT",
     [("CHAMPION", "\U0001F3C6 `[FRANCHISE]`"), ("RUNNER-UP", "`[FRANCHISE]`"), ("THIRD PLACE", "`[FRANCHISE]`"),
      ("PRESIDENTS' TROPHY", "\U0001F947 `[FRANCHISE]`"), ("CONSOLATION CHAMPION", "`[FRANCHISE]` — earns the $50 FAAB bonus next season"),
      ("DYNASTY POT", "`[BALANCE]` • `[LEADING FRANCHISE AND CHAMPIONSHIP COUNT, OR NONE]`"),
      ("NEXT", "`[OFFSEASON / TRADING REOPENS / DRAFT / DUES DEADLINE]`")], RECORD)
tmpl("league-office/13_clerical_correction.json", "COMMISSIONER CORRECTION", "A clerical, Fantrax configuration or platform correction under Section 2.5 of the Constitution.", f"{LO} • OFFICIAL NOTICE",
     [("WHAT WAS WRONG", "`[THE ERROR OR PLATFORM ISSUE]`"), ("RULE BEING APPLIED", "`[ARTICLE AND SECTION OF THE EXISTING RULE]`"),
      ("CORRECTION", "`[WHAT WAS FIXED]`"), ("INTENT PRESERVED", "This correction applies an existing rule. It does not create a new one.")])

# --------------------------------------------------------------------- calendar
tmpl("league-office/32_calendar_published.json", "LEAGUE CALENDAR PUBLISHED", "The League Calendar for **Season `[YEAR]`** is live. Every date comes from the formulas in Article V of the Constitution.", "PSBL LEAGUE CALENDAR",
     [("MLB SCHEDULE RELEASED", "`[DATE]`"), ("DUES DEADLINE", "**`[TIMESTAMP]`** (before the draft)"),
      ("DRAFT", "`[TIMESTAMP]` • between January 20 and February 10"),
      ("TRADE DEADLINE", "`[TIMESTAMP]` • Sunday 11:59 PM ET, end of Week 20"),
      ("PLAYOFFS", "Quarterfinals `[DATE STAMP]` • Semifinals `[DATE STAMP]` • Championship `[DATE STAMP]` to `[DATE STAMP]`"),
      ("IF A DATE LOOKS WRONG", "The formula in the Constitution controls. Tell the Commissioner.")])
tmpl("league-office/33_calendar_date_change.json", "CALENDAR DATE CHANGE", "`[EVENT]` has been updated.", "PSBL LEAGUE CALENDAR",
     [("PREVIOUS DATE", "`[OLD TIMESTAMP]`"), ("NEW DATE", "**`[NEW TIMESTAMP]`**"),
      ("REASON", "`[MLB SCHEDULE CHANGE / PLATFORM LIMITATION / OTHER]`"),
      ("NOTICE", "Changes get at least 7 days' notice where possible. Deadlines may be extended but are not moved earlier unless the MLB schedule forces it.")], ALERT)

# The Sesh reminder steps are part of the calendar intro (build_channel_intros.py).

# ----------------------------------------------------------------------- ledger
tmpl("league-office/40_ledger_season_summary.json", "SEASON LEDGER", "`[SEASON]` • Published within 30 days after the PSBL Championship.", "PSBL LEAGUE LEDGER",
     [("DUES RECEIVED", "`$[AMOUNT]` from `[12 / X]` franchises"), ("PRIZES PAID", "`$[AMOUNT]`"),
      ("OPERATING RESERVE", "Spent `$[AMOUNT]` on `[FANTRAX PREMIUM / OTHER]` • Unused `$[AMOUNT]` added to the Dynasty Pot"),
      ("LEAGUE SERVICES", "`$[AMOUNT]`"), ("DYNASTY POT", "`$[BALANCE]`")], RECORD)
tmpl("league-office/41_ledger_dues_status.json", "FRANCHISE DUES STATUS", "`[SEASON / DATE]`", "PSBL LEAGUE LEDGER • NO PAYMENT CREDENTIALS POSTED",
     [("PAID AND CONFIRMED", "`[LIST FRANCHISES]`"), ("PREPAID FUTURE SEASONS", "`[FRANCHISE: THROUGH SEASON YYYY]` or none"),
      ("OUTSTANDING", "`[LIST FRANCHISES / NONE]`"), ("DEADLINE", "`[TIMESTAMP]`")], RECORD)
tmpl("league-office/42_ledger_prize_pool.json", "PSBL PRIZE POOL", "`[SEASON]` • 12 franchises × $150 = $1,800", "PSBL LEAGUE LEDGER",
     [("PSBL CHAMPION", "$650"), ("RUNNER-UP", "$350"), ("THIRD PLACE", "$150"), ("PRESIDENTS' TROPHY", "$200"),
      ("DYNASTY POT CONTRIBUTION", "$200"), ("FANTRAX / OPERATING RESERVE", "$150"), ("LEAGUE SERVICES ALLOCATION", "$100")], RECORD)
tmpl("league-office/43_ledger_payment_confirmed.json", "PAYMENT CONFIRMED", "`[FRANCHISE]` is confirmed paid through **Season `[YEAR]`**.", "PSBL LEAGUE LEDGER • NO PAYMENT CREDENTIALS POSTED",
     [("COVERS", "`[SEASON DUES / FUTURE-SEASON PREPAYMENT THROUGH YEAR]`"), ("CONFIRMED", "`[DATE]`"),
      ("PICK TRADES", "`[FRANCHISE]` may now trade its 1st- and 2nd-round picks for drafts through **`[YEAR]`**. A pick trade made before payment is confirmed is reversed (Article XII).")], RECORD)
tmpl("league-office/44_ledger_prize_payout.json", "PRIZE PAID", "`[PRIZE]` for **Season `[YEAR]`** has been paid to `[FRANCHISE]`.", "PSBL LEAGUE LEDGER",
     [("AMOUNT", "`$[AMOUNT]`"), ("PAID", "`[DATE]`"), ("REMAINING THIS SEASON", "`[PRIZES STILL UNPAID, OR NONE]`")], RECORD)
tmpl("league-office/45_ledger_dynasty_pot.json", "DYNASTY POT UPDATE", "The pot stands at **`$[BALANCE]`**.", "PSBL LEAGUE LEDGER",
     [("THIS SEASON ADDED", "`$[DUES CONTRIBUTION]` from dues"),
      ("CHAMPIONSHIPS THIS CYCLE", "`[FRANCHISE: COUNT]`"),
      ("CYCLE STARTED", "`[SEASON]`"), ("TO WIN", "Three PSBL Championships in the same active cycle (Article IV).")], RECORD)

# ----------------------------------------------------------------------- voting
tmpl("league-office/50_vote_proposal_open.json", "AMENDMENT PROPOSAL — DISCUSSION", "`[PROPOSAL TITLE]`", "PSBL LEAGUE VOTING • DISCUSSION ONLY",
     [("AFFECTED RULE", "`[ARTICLE AND SECTION]`"), ("REPLACEMENT LANGUAGE", "`[EXACT NEW TEXT]`"),
      ("INTENDED EFFECTIVE DATE", "`[SEASON / DATE]`"), ("PROPOSED BY", "`[FRANCHISE OR COMMISSIONER]`"),
      ("VOTING OPENS", "**`[TIMESTAMP]`** • at least 7 days after this post (Article XX)")])
tmpl("league-office/51_vote_open.json", "OFFICIAL PSBL VOTE", "`[PROPOSAL TITLE]`", "PSBL LEAGUE VOTING • OFFICIAL",
     [("QUESTION", "`[EXACT QUESTION]`"), ("OPTIONS", "**Yes** — adopt the amendment\n**No** — keep the current rule"),
      ("VOTING CLOSES", "**`[TIMESTAMP]`** • 7-day window"),
      ("PASSAGE REQUIREMENT", "At least **8 affirmative votes out of 12**. Non-votes and abstentions are not affirmative."),
      ("WHO VOTES", "One formal vote per franchise, cast by the **Franchise Owner**."),
      ("EFFECTIVE", "`[NEXT SEASON / LATER DATE]` • must pass before that Season's dues deadline")])
tmpl("league-office/52_vote_result.json", "VOTE RESULT", "`[PROPOSAL TITLE]`", "PSBL LEAGUE VOTING • FINAL RESULT",
     [("RESULT", "**`[PASSED / FAILED]`**"), ("VOTE TOTAL", "Yes `[X]` • No `[Y]` • Not voted `[Z]` (8 of 12 required)"),
      ("EFFECTIVE", "`[SEASON / DATE / N/A]`"), ("NEXT STEP", "`[CONSTITUTION UPDATED / NO CHANGE]`")], RECORD)

# ----------------------------------------------------- constitution and rulings
tmpl("league-office/10_constitution_new_version.json", "CONSTITUTION UPDATED", "An updated PSBL Constitution has been published.", f"{LO} • OFFICIAL NOTICE",
     [("EFFECTIVE", "`[SEASON / DATE]`"), ("WHAT CHANGED", "`[SUMMARIZE CHANGES WITH ARTICLE NUMBERS]`"),
      ("APPROVED BY VOTE", "`[X]` of 12 on `[DATE]`"), ("ACTION REQUIRED", "`[NONE / REVIEW ARTICLES]`"),
      ("WHERE", "The current version is in **constitution**. Earlier versions are archived.")])
tmpl("league-office/11_constitution_amendment.json", "CONSTITUTION AMENDMENT", "A formally adopted amendment has been added to the PSBL Constitution.", f"{LO} • OFFICIAL NOTICE",
     [("AMENDMENT", "`[TITLE]` • Article `[ROMAN]` Section `[N.N]`"), ("APPROVED", "`[X]` of 12 on `[DATE]`"),
      ("EFFECTIVE", "`[SEASON / DATE]`"), ("TEXT", "`[NEW LANGUAGE OR CONCISE SUMMARY]`"),
      ("STATUS", "Now part of the current Constitution")])
tmpl("league-office/12_rules_ruling.json", "OFFICIAL RULE INTERPRETATION", "`[SHORT ISSUE TITLE]`", f"{LO} • OFFICIAL RULING",
     [("QUESTION", "`[RULE QUESTION]`"), ("RULING", "`[OFFICIAL INTERPRETATION]`"),
      ("BASIS", "`[ARTICLE AND SECTION / FANTRAX SETTING / PRIOR RULING]`"), ("EFFECTIVE", "`[IMMEDIATELY / DATE]`"),
      ("REVIEW", "A directly affected franchise may request review within 48 hours by opening an Appeal ticket in **open-a-ticket** (Section 19.4).")])
tmpl("league-office/14_recusal_notice.json", "COMMISSIONER RECUSAL", "The Commissioner's franchise is involved in `[MATTER]`. A neutral party will decide it.", f"{LO} • OFFICIAL NOTICE",
     [("DECIDED BY", "`[NEUTRAL ASSISTANT COMMISSIONER / TEMPORARY NEUTRAL REVIEWER / UNAFFECTED FRANCHISES]`"),
      ("TIMELINE", "Decision expected by `[DATE STAMP]`"), ("RECORD", "The outcome will be posted in **rulings-log**.")])
tmpl("league-office/15_appeal_outcome.json", "APPEAL OUTCOME", "Review of `[RULING TITLE]`", f"{LO} • OFFICIAL RULING",
     [("REQUESTED BY", "`[FRANCHISE]`"), ("REVIEW PANEL", "`[THREE UNAFFECTED FRANCHISES]`"),
      ("DECISION", "**`[UPHELD / MODIFIED / REVERSED]`**"), ("DETAILS", "`[WHAT CHANGES, IF ANYTHING]`"),
      ("FINAL", "The panel's decision is final for this matter (Article XIX).")], RECORD)

# -------------------------------------------------------------------- ownership
tmpl("league-office/60_owner_welcome.json", "NEW OWNER", "Welcome to the PSBL, `[OWNER]`. They are taking over **`[FRANCHISE]`**.", f"{LO} • OFFICIAL NOTICE",
     [("FRANCHISE", "`[FRANCHISE NAME]`"), ("PAID THROUGH", "Season `[YEAR]` (prepaid dues stay with the franchise)"),
      ("START HERE", "Read **welcome** and **constitution**, then check **league-calendar**.")])
tmpl("league-office/61_franchise_orphaned.json", "FRANCHISE SEEKING AN OWNER", "**`[FRANCHISE]`** is open and the league is looking for a replacement owner.", f"{LO} • OFFICIAL NOTICE",
     [("WHAT HAPPENS NOW", "The Commissioner may lock the franchise from transactions while a replacement is arranged. The Commissioner keeps the roster legal (Article XVIII)."),
      ("PREPAID DUES", "Any prepaid future seasons stay with the franchise and transfer to the new owner."),
      ("INCENTIVE", "`[NONE / DISCLOSED INCENTIVE]`"),
      ("INTERESTED?", "Contact the Commissioner. Please send names of qualified candidates.")], ALERT)
tmpl("league-office/62_commissioner_transition.json", "COMMISSIONER TRANSITION", "`[INTERIM COMMISSIONER]` is now Interim Commissioner.", f"{LO} • OFFICIAL NOTICE",
     [("REASON", "`[RESIGNATION / UNAVAILABLE 14 DAYS]`"), ("HOW CHOSEN", "`[DESIGNATED SUCCESSOR / MAJORITY OF ACTIVE FRANCHISES]`"),
      ("HANDOFF", "Funds, records, Fantrax access and Discord/automation administration transfer within 14 days (Article XIX)."),
      ("NEXT", "A permanent Commissioner is chosen by majority vote of active franchises.")], ALERT)

# ----------------------------------------------------------------------- honors
tmpl("league-office/70_champion_crowned.json", "THE PSBL CHAMPION", "\U0001F3C6 **`[FRANCHISE]`** wins the **Season `[YEAR]`** PSBL Championship.", "PSBL RECORDS DEPARTMENT",
     [("FINAL", "`[FRANCHISE]` `[SCORE]` over `[FRANCHISE]` `[SCORE]` (two-week cumulative)"),
      ("PRIZE", "$650"), ("RUNNER-UP", "`[FRANCHISE]` • $350"), ("THIRD PLACE", "`[FRANCHISE]` • $150"),
      ("CHAMPIONSHIP COUNT", "`[FRANCHISE]` now has `[N]` in the current Dynasty Pot cycle.")], RECORD)
tmpl("league-office/71_presidents_trophy.json", "PRESIDENTS' TROPHY", "\U0001F947 **`[FRANCHISE]`** finishes with the best regular-season record.", "PSBL RECORDS DEPARTMENT",
     [("RECORD", "`[W-L-T]` • `[POINTS FOR]`"), ("PRIZE", "$200"),
      ("TIEBREAKER USED", "`[NONE / POINTS SCORED / HEAD-TO-HEAD / FANTRAX / RANDOM DRAW]`")], RECORD)
tmpl("league-office/72_dynasty_pot_won.json", "DYNASTY POT WON", "**`[FRANCHISE]`** wins its third PSBL Championship in the active cycle and takes the entire Dynasty Pot.", "PSBL RECORDS DEPARTMENT",
     [("PAYOUT", "**`$[AMOUNT]`**"), ("CHAMPIONSHIPS", "`[SEASONS WON]`"),
      ("CYCLE RESET", "The pot returns to zero and every franchise's counter resets. A new cycle starts with Season `[YEAR]`.")], RECORD)

# ------------------------------------------------------------------ trade center
tmpl("trade-center/90_trade_completed.json", "TRADE COMPLETED", "Processed in Fantrax on `[DATE]`.", "PSBL TRADE CENTER",
     [("`[FRANCHISE A]` RECEIVES", "`[PLAYERS / PICKS / FAAB]`"), ("`[FRANCHISE B]` RECEIVES", "`[PLAYERS / PICKS / FAAB]`"),
      ("PREPAYMENT", "`[NOT REQUIRED / CONFIRMED IN LEAGUE-LEDGER ON DATE]`")])

# Deadline day: the PSBL Deadline Day Trade Center. The live tracker in 📢│announcements and the
# report cards with polls in 💬│trade-discussion are automated (automation/trades/);
# these two are posted by the Commissioner before deadline day.
DEADLINE_RULE = ("A trade must be fully processed in Fantrax before the deadline; one processed after it is "
                 "reversed (11.6).")
tmpl("trade-center/91_deadline_day_trade_bait_board.json", "PSBL DEADLINE DAY TRADE CENTER: TRADE BAIT",
     "The deadline-day trade bait board. One reply per franchise: what you're moving and what you need.",
     "PSBL TRADE CENTER • DEADLINE DAY",
     [("HOW TO POST", "Reply once for your franchise and edit that reply as things change, so the thread stays one "
                      "post per team. Delete it once you're done dealing."),
      ("FORMAT", "**Available:** players and picks you'd move\n**Looking for:** positions, prospects or picks\n"
                 "**Reach me:** DM, or reply in **trade-discussion**"),
      ("DEADLINE", f"**`[TIMESTAMP]`** • 11:59 PM ET, end of Week 20. {DEADLINE_RULE}"),
      ("ALLOWED IN TRADES", "Rostered players, eligible draft picks and current-season FAAB. Cash, loans, rentals, "
                            "predetermined tradebacks and conditional picks are prohibited (Article XI). A future "
                            "1st- or 2nd-round pick needs the seller's prepayment confirmed in **league-ledger** "
                            "first (Article XII)."),
      ("FOLLOW ALONG", "From 9:00 AM ET the live tracker in **announcements** counts down and lists every trade. "
                       "Each trade also gets a report card and a just-for-fun poll in **trade-discussion**.")],
     thread_name="PSBL Deadline Day Trade Center: Trade Bait")
tmpl("trade-center/92_deadline_day_sesh_event.json", "PSBL DEADLINE DAY TRADE CENTER",
     "Trade deadline day, live from 9:00 AM ET until the deadline at 11:59 PM ET.",
     "PSBL LEAGUE CALENDAR",
     [("WHEN", "**`[TIMESTAMP]`** • the Sunday that ends Week 20"),
      ("WHERE", "Live tracker in **announcements**\nTrade bait in the **trade-block** forum\n"
                "Talk, report cards and polls in **trade-discussion**"),
      ("BEFORE YOU TRADE", f"{DEADLINE_RULE} A future 1st- or 2nd-round pick needs the seller's prepayment "
                           "confirmed in **league-ledger** first (Article XII)."),
      ("REMINDERS", "RSVP to this event in **league-calendar** and Sesh sends you a reminder by direct message.")])

# -------------------------------------------------------- community and traditions
tmpl("league-office/36_calendar_sync.json", "ADD THE LEAGUE CALENDAR TO YOUR PHONE", "Every PSBL date can live in the calendar you already use.", "PSBL LEAGUE CALENDAR",
     [("HOW", "Type `/link` in any channel. Sesh replies privately with a calendar feed link."),
      ("THEN", "Add that link to Google Calendar (Other calendars → From URL), Apple Calendar (File → New Calendar Subscription) or Outlook (Add calendar → From internet)."),
      ("WHAT YOU GET", "Draft night, deadlines and owners' meetings appear on your phone and update on their own when a date changes.")])
tmpl("league-office/35_winter_meetings.json", "PSBL WINTER MEETINGS", "The yearly owners' meeting, held in the Offseason before the amendment window opens.", "PSBL LEAGUE CALENDAR",
     [("WHEN", "**`[TIMESTAMP]`** • RSVP on the Sesh event in **league-calendar**"),
      ("WHERE", "`[VOICE CHANNEL]`"),
      ("AGENDA", "Season review • Ideas from **league-suggestions** that could become amendment proposals (Article XX) • Draft and calendar dates • Open floor"),
      ("CAN'T MAKE IT", "Notes are posted in **gm-lounge** afterward. Nothing is decided at the meeting itself: rule changes still go through a written proposal and a vote.")])
tmpl("league-office/26_awards_night.json", "PSBL AWARDS NIGHT", "Season `[YEAR]` ballots are open in **league-voting**. Owners choose the winners.", "PSBL RECORDS DEPARTMENT",
     [("THE AWARDS", "**GM of the Year** • **Trade of the Year** • **Waiver Steal of the Year** • **Comeback Franchise** • **Bust of the Year** (all in good fun)"),
      ("HOW TO VOTE", "Press **Fill out my ballot** on the League Bot's post in **league-voting**: a 1st, 2nd and 3rd choice for each award, worth 5, 3 and 1 points. One ballot per franchise, cast by the Franchise Owner. Change it any time until **`[TIMESTAMP]`**."),
      ("NO SELF-VOTES", "Your own franchise, your own pickups and trades you were part of aren't on your ballot. Bust of the Year is the exception."),
      ("RESULTS", "Most points wins; a tie goes to the most first-place votes, then the award is shared. Winners are announced in **hall-of-champions** and kept in the league records."),
      ("JUST FOR FUN", "Awards carry no money and change nothing in the standings or the draft.")], RECORD)
tmpl("league-office/27_award_winners.json", "PSBL AWARDS NIGHT: THE WINNERS", "Season `[YEAR]`, as voted by the owners: `[N]` of `[N]` franchises returned a ballot. 5 points for a first-place vote, 3 for second, 1 for third.", "PSBL RECORDS DEPARTMENT",
     [("GM OF THE YEAR", "**`[FRANCHISE]`** • `[POINTS]` points, `[N]` first-place votes"),
      ("TRADE OF THE YEAR", "**`[TRADE]`** • `[POINTS]` points, `[N]` first-place votes"),
      ("WAIVER STEAL OF THE YEAR", "**`[PLAYER, FRANCHISE]`** • `[POINTS]` points, `[N]` first-place votes"),
      ("COMEBACK FRANCHISE", "**`[FRANCHISE]`** • `[POINTS]` points, `[N]` first-place votes"),
      ("BUST OF THE YEAR", "**`[NOMINEE]`** • `[POINTS]` points, `[N]` first-place votes"),
      ("JUST FOR FUN", "Awards carry no money and change nothing in the standings or the draft.")], RECORD)
tmpl("league-office/28_wooden_spoon_proposal.json", "NEW TRADITION? THE WOODEN SPOON", "A just-for-fun tradition for the last-place team. Owners decide whether we do it.", f"{LO} • DISCUSSION",
     [("THE IDEA", "The franchise that finishes last in the regular season holds the **Wooden Spoon** role for the Offseason and writes a short preview of the next Season, posted before Week 1."),
      ("WHAT IT ISN'T", "No money and no rule change. Draft order still comes from Potential Points (14.5), so the Spoon can't be chased."),
      ("HAVE YOUR SAY", "React 👍🏻 or 👎🏻 by **`[TIMESTAMP]`**, or reply in **gm-lounge**. It starts only if owners want it.")])
tmpl("league-office/29_wooden_spoon_awarded.json", "THE WOODEN SPOON", "**`[FRANCHISE]`** finishes last in Season `[YEAR]` and takes home the Spoon.", "PSBL RECORDS DEPARTMENT",
     [("THE TRADITION", "`[OWNER]` holds the Wooden Spoon role for the Offseason and writes the Season `[NEXT YEAR]` preview, posted before Week 1."),
      ("NO PENALTY", "Draft order is unaffected: it comes from Potential Points (14.5).")], RECORD)
tmpl("league-office/63_league_bot_launch.json", "MEET THE PSBL LEAGUE BOT", "League tools, right in Discord. Every command reads Fantrax and the Constitution; nothing here changes Fantrax.", f"{LO} • OFFICIAL NOTICE",
     [("YOUR TEAM", "`/myteam` shows your roster counts, picks you own, how far your dues are paid and this Week's matchup. Only you see it."),
      ("RULES", "`/rule 12.4` or `/rule prepayment` shows the Constitution's text. `/deadlines` lists the next dates."),
      ("PLAYERS AND TRADES", "`/minor` checks a player's minors eligibility. `/tradecheck` checks a trade against the rules (picks, prepayment, roster limits, the deadline). It never grades a trade."),
      ("PICK'EM", "Each Week the bot posts the matchups in **game-day**. Make your picks before the Week starts; a season leaderboard keeps score."),
      ("VOTING", "Proposals and official votes run through the bot in **league-voting**, one vote per franchise (Article XX).")])

# ---------------------------------------------------------------- scoring explainer
# One-time reference post for owners: why each scoring value is what it is.
# The event values are FanGraphs' linear weights for 2021-2026 at 10 points per
# run; the inning, save and hold values and every figure below come from all MLB
# regular-season player lines of 2021-2026, scored for a 12-team league with this
# lineup (research/scoring/ has the data and the scripts).
D = fmt.divider_name
tmpl("league-office/16_scoring_explained.json", "HOW PSBL SCORING WORKS",
     "PSBL scoring prices every play at what it's worth in runs, using the linear weights FanGraphs publishes, at 10 points "
     "per run. A hitter earns the run value of what he does, and the pitcher pays the same price from the other side. The "
     "values match FanGraphs' figures for every season from 2021 to 2026, and the reasons are below.",
     "PSBL LEAGUE OFFICE",
     [("HITTERS", "Every At-Bat **−1**\nHit **+5.6**\nDouble **+3** more • Triple **+5.7** more\nHome Run **+9.4** more\n"
                  "Walk **+3.1** • Hit by Pitch **+3.3**\nStolen Base **+2** • Caught Stealing **−4.1**"),
      ("PITCHERS", "Inning Pitched **+6** (+2 per out)\nStrikeout **+2**\nHit Allowed **−2.6**\nHome Run Allowed **−11.4** more\n"
                   "Walk **−3.1** • Hit Batter **−3.3**\nSave **+6** • Hold **+4**"),
      (D("HITTING"),
       "**Priced in runs.** With the at-bat counted, a single nets **+4.6**, a double **+7.6**, a triple **+10.3** and a home run "
       "**+14**, and an out costs **1**. That's what each is worth in runs: a home run is about three singles, and a walk about "
       "two-thirds of one.\n\n"
       "**No runs or RBI.** They depend on where a hitter bats and who's on base, and the hits behind them already count. A "
       "strikeout is an out like any other; the difference in runs is a tenth of a point.\n\n"
       "**Steals:** a steal adds about 0.2 runs and getting caught costs about 0.4, so a runner has to succeed about twice for "
       "every time he's caught to come out ahead."),
      (D("PITCHING"),
       "**What a pitcher controls counts in full.** Strikeouts, walks and home runs are mostly his own doing. Whether a ball in "
       "play falls for a hit depends a lot on the defense, the park and luck, so a hit allowed costs half its run value. Tested on "
       "every starter from 2021 to 2026, that mix matched a season's runs allowed almost as well as charging hits in full, and it "
       "predicted the next season's runs allowed better than a pitcher's actual runs allowed did.\n\n"
       "**No wins, losses or earned runs.** The offense, the bullpen and the scorer decide too much of them."),
      (D("INNINGS AND RELIEVERS"),
       "**The inning (+6) is the one number that isn't a run value.** It sets what a start is worth, so the five SP slots carry "
       "their share of the lineup: about **28%** of the value above replacement, the same as their share of the 18 slots.\n\n"
       "**Saves (+6) and holds (+4)** pay relievers for pitching in the biggest spots. At these values the best closer in each "
       "season from 2021 to 2026 ranked between the 9th and 27th best starter: worth a roster spot, but not worth more than an ace."),
      ("WHAT A GAME CAN LOOK LIKE",
       "Homer and a single in 4 at-bats → **+16.6**\n2 singles and a walk in 4 at-bats → **+10.3**\n0 for 4 → **−4**\n"
       "7 IP, 4 H, 1 BB, 10 K → **+48.5**\n6 IP, 5 H (a homer), 2 BB, 7 K → **+19.4**\n3 IP, 8 H (2 homers), 2 BB, 2 K → **−27.8**\n"
       "Closer: 1 IP, 2 K, save → **+16**\nSetup man: 1 IP, 1 H, 1 K, hold → **+9.4**"),
      (D("WHAT ISN'T SCORED"),
       "**Runs and RBI:** the hits behind them already count.\n"
       "**Wins, losses and earned runs:** the offense, the bullpen and the defense decide too much of them.\n"
       "**Quality starts, complete games, shutouts and no-hitters:** innings, strikeouts and hits already reward them.\n"
       "**Blown saves:** the hits and walks behind them already cost the pitcher, and a closer's blown-save rate doesn't carry "
       "over from one season to the next."),
      (D("FOR YOUR ROSTER"),
       "From 2021 to 2026 a hitter in a league's lineup averaged about **5.5 points a game** and a starter about **20 points a "
       "start**. The best seasons ran about 1,300 to 1,570 for a hitter, 890 to 980 for a starter and 580 to 700 for a reliever. "
       "Hitters top the point totals because they play every day, so draft by value, not by raw points.")],
     banner=fmt.GENERIC_HEADER)

# ------------------------------------------------------------------- bundles
BUNDLES = {
    "01_Announcements": ["league-office/20_announcement_standard.json", "league-office/21_announcement_action_required.json",
                         "league-office/22_announcement_urgent_deadline.json", "league-office/23_season_opening.json",
                         "league-office/24_season_closing.json", "league-office/13_clerical_correction.json"],
    "02_Calendar": ["league-office/30_calendar_event.json", "league-office/31_calendar_deadline_reminder.json",
                    "league-office/32_calendar_published.json", "league-office/33_calendar_date_change.json",
                    "league-office/35_winter_meetings.json", "league-office/36_calendar_sync.json"],
    "03_Ledger": ["league-office/40_ledger_season_summary.json", "league-office/41_ledger_dues_status.json",
                  "league-office/42_ledger_prize_pool.json", "league-office/43_ledger_payment_confirmed.json",
                  "league-office/44_ledger_prize_payout.json", "league-office/45_ledger_dynasty_pot.json"],
    "04_Voting": ["league-office/50_vote_proposal_open.json", "league-office/51_vote_open.json", "league-office/52_vote_result.json"],
    "05_Constitution_and_Rulings": ["league-office/10_constitution_new_version.json", "league-office/11_constitution_amendment.json",
                                    "league-office/12_rules_ruling.json", "league-office/14_recusal_notice.json", "league-office/15_appeal_outcome.json"],
    "06_Honors_and_Records": ["league-office/70_champion_crowned.json", "league-office/71_presidents_trophy.json", "league-office/72_dynasty_pot_won.json"],
    "07_Ownership": ["league-office/60_owner_welcome.json", "league-office/61_franchise_orphaned.json", "league-office/62_commissioner_transition.json"],
    "08_Trades": ["trade-center/90_trade_completed.json"],
    "10_Deadline_Day_Trade_Center": ["trade-center/91_deadline_day_trade_bait_board.json",
                                     "trade-center/92_deadline_day_sesh_event.json"],
    "09_Community_and_Traditions": ["league-office/26_awards_night.json", "league-office/27_award_winners.json",
                                    "league-office/28_wooden_spoon_proposal.json", "league-office/29_wooden_spoon_awarded.json",
                                    "league-office/63_league_bot_launch.json"],
}

def message(path: Path) -> dict:
    """Load one template and confirm it is a single message in the PSBL format."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rel = path.relative_to(T).as_posix()
    errors = fmt.problems(data["embeds"], fmt.header_url(rel), rel)
    if errors:
        raise SystemExit(f"{rel}: {'; '.join(errors)} (run normalize_discohook_templates.py first)")
    return data


def link(messages: list[dict]) -> str:
    raw = json.dumps({"messages": [{"data": m} for m in messages]}, ensure_ascii=True, separators=(",", ":")).encode()
    return "https://discohook.org/?data=" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    links: dict[str, str] = {}
    for name, files in BUNDLES.items():
        msgs = [message(T / f) for f in files]
        (OUT / f"PSBL_Templates_{name}.json").write_text(
            json.dumps({"messages": [{"data": m} for m in msgs]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        links[f"bundle:{name}"] = link(msgs)
    for p in sorted(T.rglob("*_channel_intro.json")):
        links[f"intro:{p.relative_to(T).as_posix()}"] = link([message(p)])
    welcome = message(T / fmt.WELCOME)
    (OUT / "PSBL_Welcome_Single_Message.json").write_text(json.dumps(welcome, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    links["welcome"] = link([welcome])
    links["scoring"] = link([message(T / "league-office/16_scoring_explained.json")])
    for p in sorted((T / "constitution").glob("*.json")):
        links[f"constitution:{p.name}"] = link([message(p)])
    (OUT / "links.json").write_text(json.dumps(links, indent=2) + "\n", encoding="utf-8")
    biggest = max(len(v) for v in links.values())
    print(f"{len(BUNDLES)} bundles, {len(links)} links, longest link {biggest} chars")


if __name__ == "__main__":
    main()
