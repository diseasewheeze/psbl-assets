#!/usr/bin/env python3
"""Offline tests for the DBL League Bot's league commands.

Everything runs from the Fantrax samples in automation/tests/fixtures and
fake MLB, Fantrax and League Ledger sources; nothing touches the network.
"""

from __future__ import annotations

import copy
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from league_bot import constitution, deadlines, embeds, minor, pickem, rules, team, trade  # noqa: E402
from league_bot.config import load  # noqa: E402
from league_bot.league_data import Clearance, LeagueData, MlbLookup, TTLCache  # noqa: E402
from league_bot.shared import FIXTURES, build_constitution  # noqa: E402
from league_bot.store import Store  # noqa: E402

from core import mlb_people as mp  # noqa: E402
from core import season  # noqa: E402
from core import sport  # noqa: E402
from core.fantrax import normalize_scores  # noqa: E402

UTC = timezone.utc
NY = ZoneInfo("America/New_York")

# Fantrax team IDs in the test league (draft_picks_test.json order).
TEST = "gb4or3npmumb3mgv"      # "Test": a full lineup, 8 reserve, 10 minors (baseball_rosters)
TEST3 = "2tml63mumumuxoqh"     # "Test 3": a full lineup, 18 reserve (over the limit)
TEST4 = "8j6llh6gmumuxose"
TEST6 = "gobvt8opmumuxoxm"
TEST7 = "qqpqauuamumuxp03"
DURING_WEEK_2 = datetime(2026, 10, 6, 18, tzinfo=UTC)


def fixture(name: str):
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data["response"] if isinstance(data, dict) and "response" in data else data


INFO = fixture("league_info_2026_test.json")
PICKS = fixture("draft_picks_test.json")
LINEUP_SLOTS = [slot for slot, count in sport.LINEUP.items() for _ in range(count)]
FANTRAX_SLOT = {"UTIL": "UT"}   # assumed: the name Fantrax gives the utility slot
RESERVE_POSITIONS = ("OF", "1B", "SP", "RP", "2B", "3B")


def baseball_rosters() -> dict:
    """The live Fantrax roster sample with baseball slots: each team's ACTIVE players fill the lineup
    (sport.LINEUP) in order, the rest of them become RESERVE, and reserves and minors get baseball positions."""
    raw = copy.deepcopy(fixture("team_rosters_sample_test.json"))
    for roster in raw["rosters"].values():
        active = reserve = 0
        for item in roster["rosterItems"]:
            if item["status"] == "ACTIVE" and active < len(LINEUP_SLOTS):
                item["position"] = FANTRAX_SLOT.get(LINEUP_SLOTS[active], LINEUP_SLOTS[active])
                active += 1
            elif item["status"] in ("ACTIVE", "RESERVE"):
                item["status"] = "RESERVE"
                item["position"] = RESERVE_POSITIONS[reserve % len(RESERVE_POSITIONS)]
                reserve += 1
            else:
                item["position"] = "SS"
    return raw


ROSTERS = baseball_rosters()
FULL = len(LINEUP_SLOTS)
SCORES_2 = normalize_scores(fixture("matchup_scores_period2_test.json"))


def named_players() -> dict:
    """getPlayerIds-style names and positions for the sample rosters (SYNTHETIC; the live sample has no names)."""
    out = {}
    for roster in ROSTERS["rosters"].values():
        for i, item in enumerate(roster["rosterItems"]):
            out[item["id"]] = {"fantraxId": item["id"], "name": f"Player{i}, {roster['teamName'].replace(' ', '')}",
                               "position": item["position"], "team": "KC"}

    def name(pid, full, position, team):
        out[pid].update(name=full, position=position, team=team)

    name("04lcs", "Smith, Will", "C", "LAD")              # Test, ACTIVE in the C slot (its only catcher)
    name("03v70", "Witt Jr., Bobby", "SS", "KC")           # Test, ACTIVE at SS
    name("04xec", "Garcia Jr., Luis", "2B,SS", "WSH")      # Test, ACTIVE in a UTIL slot; can move to SS
    name("05ogy", "Griffin, Konnor", "SS", "PIT")          # Test, MINORS
    name("061a2", "Smith, Dominic", "1B", "ATL")           # Test 3, RESERVE
    name("061im", "Smith, Cam", "OF", "HOU")               # Test 3, RESERVE
    name("01mzc", "Raleigh, Cal", "C", "SEA")              # Test 3, ACTIVE at C
    name("03e1n", "Alonso, Pete", "1B", "NYM")             # Test 3, ACTIVE at 1B
    name("0045j", "Soto, Juan", "OF", "NYM")               # Test 3, ACTIVE in the OF
    return out


EVENTS = {
    "settings": {"timezone": "America/New_York", "default_channel": "league-calendar"},
    "events": [
        {"id": "dues-deadline", "enabled": True, "title": "DBL Dues Deadline", "starts_at": "2027-06-30T23:59:00",
         "channel": "league-calendar", "description": "League dues must be paid by this deadline."},
        {"id": "opening-night", "enabled": True, "title": "DBL Opening Night", "starts_at": "2027-10-07T19:00:00"},
        {"id": "trade-deadline", "enabled": True, "title": "DBL Trade Deadline", "starts_at": "2027-02-21T23:59:59"},
        {"id": "playoffs-begin", "enabled": True, "title": "DBL Playoffs Begin", "starts_at": "2027-03-08T19:00:00"},
        {"id": "past", "enabled": True, "title": "Already happened", "starts_at": "2026-01-01T12:00:00"},
        {"id": "off", "enabled": False, "title": "Disabled", "starts_at": "2026-12-01T12:00:00"},
        {"id": "undated", "enabled": True, "title": "No date", "starts_at": None},
        {"id": "private", "enabled": True, "title": "Commissioner only", "starts_at": "2026-11-01T12:00:00",
         "channel": "commissioner-desk"},
        {"id": "commissioner-trading-reopens", "enabled": False, "title": "Renew the league",
         "starts_at": "2027-06-25T09:00:00", "channel": "commissioner-desk"},
    ],
}


class FakeData:
    """LeagueData stand-in serving the fixtures; any source can be made to fail."""

    league_id = "w02cjakmmumb3lur"

    def __init__(self, fail: set[str] | None = None, picks=None, clearance: Clearance | None = None,
                 events=None, player_ids=None) -> None:
        self.fail = fail or set()
        self._picks = picks if picks is not None else PICKS
        self._clearance = clearance or Clearance("ok", {TEST: {"franchise": "Test", "paid_through": 2027},
                                                         TEST3: {"franchise": "Test 3", "paid_through": 2029}})
        self._events = events if events is not None else EVENTS
        self._players = player_ids if player_ids is not None else named_players()

    def _serve(self, name, value):
        if name in self.fail:
            raise RuntimeError(f"{name} unavailable")
        return value

    def league_info(self):
        return self._serve("league_info", INFO)

    def rosters(self):
        return self._serve("rosters", ROSTERS)

    def draft_picks(self):
        return self._serve("draft_picks", self._picks)

    def player_ids(self):
        return self._serve("player_ids", self._players)

    def matchup_scores(self, period):
        return self._serve("matchup_scores", SCORES_2 if period == 2 else [])

    def clearance(self):
        return self._serve("clearance", self._clearance)

    def events(self):
        return self._serve("events", self._events)


def traded_picks():
    """Test 4's 2028 1st now owned by Test; Test's 2029 2nd now owned by Test 7."""
    raw = copy.deepcopy(PICKS)
    for p in raw["futureDraftPicks"]:
        if (p["year"], p["round"], p["originalOwnerTeamId"]) == (2028, 1, TEST4):
            p["currentOwnerTeamId"] = TEST
        if (p["year"], p["round"], p["originalOwnerTeamId"]) == (2029, 2, TEST):
            p["currentOwnerTeamId"] = TEST7
    return raw


# --------------------------------------------------------------------- /rule
class RuleTests(unittest.TestCase):
    def source_text(self, article: int, n: int) -> str:
        blocks = build_constitution().S.ARTICLES[article - 1]["blocks"]
        return [b[1] for b in blocks if b[0] == "p"][n - 1]

    def test_12_4_and_15_5_resolve_to_the_right_text(self) -> None:
        s = constitution.section("12.4")
        self.assertTrue(s.text.startswith("The required payment must be received and confirmed by the Commissioner"))
        self.assertEqual(s.text, self.source_text(12, 4))
        s = constitution.section("15.5")
        self.assertTrue(s.text.startswith("**Draft-order ties.**"))
        self.assertEqual(s.text, self.source_text(15, 5))

    def test_tables_are_not_numbered(self) -> None:
        # The allocation table follows 3.5 without a number of its own, so 3.6 is the next paragraph.
        self.assertTrue(constitution.section("3.5").text.endswith("is:"))
        self.assertEqual(constitution.section("3.6").text, self.source_text(3, 6))
        self.assertTrue(constitution.section("3.6").text.startswith("The League Services Allocation is"))
        self.assertEqual(constitution.section("5.9").text, "The key dates and how each is set:")
        self.assertIsNone(constitution.section("5.10"))
        self.assertEqual(constitution.articles()[19].sections[-1].ref, "20.8")  # history table not numbered

    def test_scoring_tables_are_shown_but_not_numbered(self) -> None:
        build = build_constitution()
        scoring = constitution.articles()[7]
        self.assertEqual(scoring.title, "Scoring")
        paragraphs = [b for b in build.S.ARTICLES[7]["blocks"] if b[0] == "p"]
        self.assertEqual(len(scoring.sections), len(paragraphs))
        tables = [line for line in scoring.lines if "Home Run (HR)" in line]
        self.assertEqual(len(tables), 1)
        self.assertIsNone(constitution.SECTION_LINE.match(tables[0]))
        self.assertIn("Home Run (HR)", constitution.article_embeds(scoring)[0]["description"])

    def test_numbering_mirrors_the_published_build(self) -> None:
        build = build_constitution()
        published = []
        for art in build.S.ARTICLES:
            for line in build.article_lines(art, "md"):
                if line.startswith("**") and constitution.SECTION_LINE.match(line):
                    m = constitution.SECTION_LINE.match(line)
                    published.append((f"{m.group(1)}.{m.group(2)}", m.group(3)))
        ours = [(s.ref, s.text) for a in constitution.articles() for s in a.sections]
        self.assertEqual(ours, published)
        self.assertEqual(len(constitution.articles()), 20)

    def test_section_query_forms(self) -> None:
        for q in ("12.4", "Section 12.4", "§12.4", " 12 . 4 "):
            a = constitution.answer(q)
            self.assertEqual(a.embeds[0]["title"], "SECTION 12.4", q)
        self.assertIn("12.1 to 12.7", constitution.answer("12.9").message)
        self.assertIn("no Section 25.1", constitution.answer("25.1").message)

    def test_article_query_forms(self) -> None:
        for q in ("XII", "Article XII", "article 12", "art. xii", "12"):
            a = constitution.answer(q)
            self.assertTrue(a.embeds[0]["title"].startswith("ARTICLE XII —"), q)
            self.assertIn("**12.4**", a.embeds[0]["description"])
        self.assertIn("no Article XXI", constitution.answer("XXI").message)

    def test_keyword_search_top_three(self) -> None:
        found = constitution.search("prepayment")
        self.assertEqual(len(found), 3)
        self.assertTrue(all(s.article == 12 for s in found))
        self.assertEqual(constitution.search("trade deadline")[0].ref, "11.6")
        self.assertEqual(constitution.search("minor at-bats")[0].ref, "7.2")
        embed = constitution.answer("prepayment").embeds[0]
        self.assertEqual(len(embed["fields"]), 3)

    def test_word_that_looks_roman_is_a_keyword(self) -> None:
        self.assertIn("No section mentions", constitution.answer("civil").message)
        self.assertTrue(constitution.answer("mix").message)

    def test_every_answer_fits_discord(self) -> None:
        queries = [a.numeral for a in constitution.articles()] + ["prepayment", "dues", "pitcher", "the draft order"]
        for q in queries:
            a = constitution.answer(q)
            if a.embeds:
                self.assertTrue(embeds.fits(a.embeds), q)
                self.assertNotIn("Version", json.dumps(a.embeds))
                self.assertNotIn("image", a.embeds[0] if len(a.embeds) > 1 else {})

    def test_long_article_is_split_and_capped(self) -> None:
        art = constitution.articles()[18]
        long = constitution.Article(art.number, art.numeral, art.title, art.lines * 3, art.sections)
        out = constitution.article_embeds(long)
        self.assertTrue(embeds.fits(out))
        self.assertIn("too long to show here", out[-1]["description"])


# ---------------------------------------------------------------- /deadlines
class DeadlineTests(unittest.TestCase):
    NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)

    def test_next_three_enabled_dated_public_events(self) -> None:
        found = deadlines.upcoming(EVENTS, self.NOW, 3)
        self.assertEqual([d.id for d in found], ["trade-deadline", "playoffs-begin", "dues-deadline"])

    def test_naive_times_are_new_york_wall_clock(self) -> None:
        d = deadlines.upcoming(EVENTS, self.NOW, 1)[0]
        self.assertEqual(d.at.utcoffset(), timedelta(hours=-5))  # February: EST
        self.assertEqual((d.at.hour, d.at.minute), (23, 59))

    def test_embed_uses_discord_timestamps(self) -> None:
        found = deadlines.upcoming(EVENTS, self.NOW, 3)
        e = deadlines.embed(found)
        unix = int(found[0].at.timestamp())
        self.assertIn(f"<t:{unix}:F>", e["fields"][0]["value"])
        self.assertIn(f"<t:{unix}:R>", e["fields"][0]["value"])
        self.assertTrue(embeds.fits([e]))

    def test_nothing_published(self) -> None:
        e = deadlines.embed(deadlines.upcoming({"events": []}, self.NOW))
        self.assertIn("hasn't been published yet", e["description"])

    def test_shipped_events_file_has_no_public_dates_yet(self) -> None:
        shipped = deadlines.load()
        self.assertEqual(deadlines.upcoming(shipped, self.NOW), [])  # the only enabled event is private

    def test_event_time_ignores_enabled_flag(self) -> None:
        reopens = deadlines.event_time(EVENTS, "commissioner-trading-reopens")
        self.assertEqual(reopens, datetime(2027, 6, 25, 9, tzinfo=NY))
        self.assertIsNone(deadlines.event_time(EVENTS, "missing"))


# -------------------------------------------------------------------- /minor
AB, OUTS = sport.MINORS_MAX_AB, sport.MINORS_MAX_OUTS


def mlb_person(pid, name, pos, team, at_bats=None, outs=None, pitching_ab=0, active=True, debut="2025-04-01"):
    """A /people entry with career stats, in MLB's shape (automation/tests/fixtures/mlb_people_careers.json)."""
    stats = []
    if at_bats is not None:
        stats.append({"group": {"displayName": "hitting"}, "type": {"displayName": "career"},
                      "splits": [{"stat": {"atBats": at_bats}, "sport": {"id": 1}, "gameType": "R"}]})
    if outs is not None:
        stats.append({"group": {"displayName": "pitching"}, "type": {"displayName": "career"},
                      "splits": [{"stat": {"outs": outs, "atBats": pitching_ab}, "sport": {"id": 1}, "gameType": "R"}]})
    row = {"id": pid, "fullName": name, "active": active, "birthDate": "2004-05-06",
           "primaryPosition": {"abbreviation": pos}, "currentTeam": team}
    if debut:
        row["mlbDebutDate"] = debut
    if stats:
        row["stats"] = stats
    return row


PEOPLE = [
    mlb_person(804606, "Konnor Griffin", "SS", {"id": 134, "name": "Pittsburgh Pirates"}, at_bats=312),
    mlb_person(822298, "Logan Reddemann", "P", {"id": 1994, "name": "ACL Rockies", "parentOrgId": 115}, debut=None),
    mlb_person(669257, "Will Smith", "C", {"id": 119, "name": "Los Angeles Dodgers"}, at_bats=2300),
    mlb_person(519293, "Will Smith", "P", {"id": 118, "name": "Kansas City Royals"}, outs=1500, active=False),
    mlb_person(700001, "Prospect Pitcher", "P", {"id": 147, "name": "New York Yankees"}, outs=OUTS - 3, pitching_ab=AB + 10),
    mlb_person(700002, "Near Hitter", "2B", {"id": 147, "name": "New York Yankees"}, at_bats=AB - 5),
    mlb_person(700003, "Luis Garcia", "P", {"id": 119, "name": "Los Angeles Dodgers"}, outs=900),
    mlb_person(700004, "Luis Garcia", "P", {"id": 135, "name": "San Diego Padres"}, outs=600),
]


class FakeMlbFetch:
    """MLB player search and /people in the API's shape; counts requests."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, url, params):
        self.calls.append(url)
        if url.endswith("/people/search"):
            q = mp.norm_name(params["names"])
            return {"people": [p for p in PEOPLE if q in mp.norm_name(p["fullName"])]}
        if url.endswith("/people"):
            ids = {int(x) for x in params["personIds"].split(",")}
            return {"people": [p for p in PEOPLE if p["id"] in ids]}
        raise AssertionError(url)


def lookup_client() -> tuple[MlbLookup, FakeMlbFetch]:
    fetch = FakeMlbFetch()
    return MlbLookup(mp.MlbApi(fetch)), fetch


class MinorRuleTests(unittest.TestCase):
    def test_limits_come_from_the_rules_module(self) -> None:
        self.assertTrue(minor.verdict(AB, OUTS).eligible)
        self.assertFalse(minor.verdict(AB + 1, 0).eligible)
        self.assertFalse(minor.verdict(0, OUTS + 1).eligible)
        v = minor.verdict(AB + 1, OUTS + 1)
        self.assertEqual(v.reasons, (f"{AB + 1} career MLB at-bats (limit {AB})",
                                     f"{mp.innings_text(OUTS + 1)} career MLB innings (limit {OUTS // 3})"))


class MinorLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mlb, self.fetch = lookup_client()

    def test_candidates_tiers(self) -> None:
        def ids(query, team=None):
            return [p.id for p in minor.candidates(self.mlb.search(minor.query_name(query)), query, team)]
        self.assertEqual(ids("Konnor Griffin"), [804606])
        self.assertEqual(ids("griffin"), [804606])
        self.assertEqual(ids("Griffin, Konnor"), [804606])
        self.assertEqual(ids("Will Smith"), [669257])                 # the only active Will Smith
        self.assertEqual(len(ids("Luis Garcia")), 2)
        self.assertEqual(ids("Luis Garcia", "sd"), [700004])
        self.assertEqual(ids("Nobody"), [])

    def test_prospect_without_mlb_time_is_eligible(self) -> None:
        e, msg = minor.lookup(self.mlb, "Logan Reddemann", None)
        self.assertIsNone(msg)
        self.assertIn("**DBL minor-eligible: YES**", e["description"])
        self.assertIn("COL, ACL Rockies", e["description"])
        self.assertIn("no MLB debut yet", e["description"])
        text = json.dumps(e)
        self.assertIn(f"**0** of {AB}", text)
        self.assertIn("The Commissioner's determination is final (7.3).", text)
        self.assertTrue(embeds.fits([e]))

    def test_over_the_at_bat_limit(self) -> None:
        e, _ = minor.lookup(self.mlb, "Konnor Griffin", None)
        self.assertIn("**DBL minor-eligible: NO**", e["description"])
        self.assertIn(f"312 career MLB at-bats (limit {AB})", json.dumps(e))
        self.assertIn("WHY NOT", json.dumps(e))

    def test_at_bats_faced_as_a_pitcher_do_not_count(self) -> None:
        e, _ = minor.lookup(self.mlb, "Prospect Pitcher", None)
        text = json.dumps(e)
        self.assertIn("**DBL minor-eligible: YES**", e["description"])
        self.assertIn(f"**0** of {AB}", text)
        self.assertIn(f"Within {mp.innings_text(3)} innings of a limit", text)

    def test_near_the_at_bat_limit(self) -> None:
        e, _ = minor.lookup(self.mlb, "Near Hitter", None)
        self.assertIn("Within 5 at-bats of a limit", json.dumps(e))

    def test_lookup_unknown_and_ambiguous(self) -> None:
        e, msg = minor.lookup(self.mlb, "Wayne Nobody", None)
        self.assertIsNone(e)
        self.assertIn("No player matches", msg)
        e, msg = minor.lookup(self.mlb, "Garcia", None)
        self.assertIsNone(e)
        self.assertIn("More than one player", msg)
        self.assertIn("team: LAD", msg)
        e, _ = minor.lookup(self.mlb, "Luis Garcia", "LAD")
        self.assertIn("**DBL minor-eligible: NO**", e["description"])


# ------------------------------------------------------------------- /myteam
class TeamTests(unittest.TestCase):
    def test_limits_come_from_the_rules_module(self) -> None:
        self.assertEqual(team.LIMITS, {"active": sum(sport.LINEUP.values()), "reserve": sport.BENCH,
                                       "minors": sport.MINORS, "ir": sport.INJURED_LIST})
        self.assertEqual(list(team.SLOTS), LINEUP_SLOTS)
        self.assertEqual(team.LABELS["ir"], "IL")

    def test_roster_counts_against_limits(self) -> None:
        self.assertEqual(team.roster_counts(ROSTERS, TEST), {"active": FULL, "reserve": 8, "minors": 10, "ir": 0})
        over = team.roster_counts(ROSTERS, TEST3)
        self.assertEqual(team.over_limits(over), {"reserve": 18 - sport.BENCH})
        self.assertIn(f"**Reserve 18/{sport.BENCH} (over by {18 - sport.BENCH})**", team.roster_text(over))
        self.assertIsNone(team.roster_counts(ROSTERS, "nobody"))

    def test_ir_status_counts(self) -> None:
        raw = copy.deepcopy(ROSTERS)
        raw["rosters"][TEST]["rosterItems"][0]["status"] = "IR"
        self.assertEqual(team.roster_counts(raw, TEST)["ir"], 1)

    def test_picks_owned_acquired_and_traded_away(self) -> None:
        names = team.team_names(INFO)
        owned, away = team.picks_of(traded_picks(), TEST)
        self.assertEqual(len(owned), 15)
        owned_text, away_text = team.picks_text(owned, away, TEST, names)
        self.assertIn("**2028:** 1st, 1st (from Test 4), 2nd", owned_text)
        self.assertIn("**2029:** 1st, 3rd", owned_text)
        self.assertEqual(away_text, "2029 2nd to Test 7")
        _, away4 = team.picks_of(traded_picks(), TEST4)
        self.assertEqual(team.picks_text([], away4, TEST4, names)[1], "2028 1st to Test")

    def test_this_week_opponent_and_score(self) -> None:
        period, started = team.week_for(INFO, DURING_WEEK_2, NY)
        self.assertEqual((period.number, started), (2, True))
        text = team.week_text(INFO, period, started, TEST, SCORES_2)
        self.assertIn("Week 2 vs **Test 3**", text)
        self.assertIn("**11.10** to 0.00 (leading)", text)
        text = team.week_text(INFO, period, started, TEST4, SCORES_2)
        self.assertIn("vs **Test 6**", text)
        self.assertIn("(tied)", text)

    def test_preseason_and_offseason(self) -> None:
        period, started = team.week_for(INFO, datetime(2026, 9, 1, tzinfo=UTC), NY)
        self.assertEqual((period.number, started), (1, False))
        self.assertIn("vs **Test 4** • starts <t:", team.week_text(INFO, period, started, "vs89xezfmumuxp44", None))
        self.assertEqual(team.week_for(INFO, datetime(2027, 6, 1, tzinfo=UTC), NY), (None, False))
        self.assertIn("Offseason", team.week_text(INFO, None, False, TEST, None))

    def test_monday_morning_shows_the_new_week(self) -> None:
        monday = datetime(2026, 10, 12, 9, tzinfo=NY)  # Week 2 final at 6 AM; Week 3 starts 1 PM
        period, started = team.week_for(INFO, monday, NY)
        self.assertEqual((period.number, started), (3, False))

    def test_paid_through_states(self) -> None:
        table = {TEST: {"paid_through": 2028}, TEST3: {"paid_through": None}}
        self.assertEqual(team.paid_text(Clearance("ok", table), TEST), "Season 2028")
        self.assertEqual(team.paid_text(Clearance("ok", table), TEST3), "No Season confirmed yet")
        self.assertIn("Pick Clearance tab", team.paid_text(Clearance("ok", table), TEST4))
        self.assertIn("LEAGUE_LEDGER_CLEARANCE_CSV", team.paid_text(Clearance("unset"), TEST))
        self.assertIn("Couldn't read", team.paid_text(Clearance("error"), TEST))

    def test_build(self) -> None:
        e = team.build(FakeData(picks=traded_picks()), "Franchise 2", TEST, DURING_WEEK_2, NY)
        text = json.dumps(e)
        self.assertEqual(e["title"], "FRANCHISE 2")
        self.assertIn("Fantrax team: **Test**", e["description"])
        for expected in (f"Active {FULL}/{FULL}", f"Reserve 8/{sport.BENCH}", f"Minors 10/{sport.MINORS}",
                         f"IL 0/{sport.INJURED_LIST}", "FAAB: check Fantrax",
                         "Paid through: Season 2027", "DBL Trade Deadline", "2029 2nd to Test 7", "Week 2 vs"):
            self.assertIn(expected, text)
        self.assertEqual(e["fields"][-1]["value"].count("<t:"), 4)  # next 2 deadlines, F and R each
        self.assertTrue(embeds.fits([e]))

    def test_build_survives_partial_outages(self) -> None:
        with self.assertLogs("league.bot", level="WARNING"):
            e = team.build(FakeData(fail={"rosters", "draft_picks", "events", "clearance"}), "F", TEST, DURING_WEEK_2, NY)
        text = json.dumps(e)
        self.assertIn("Couldn't read rosters", text)
        self.assertIn("Couldn't read draft picks", text)
        self.assertIn("Couldn't read the League Calendar", text)
        self.assertIn("Week 2 vs", text)

    def test_unknown_team_id(self) -> None:
        e = team.build(FakeData(), "F", "nope", DURING_WEEK_2, NY)
        self.assertIn("no roster for team ID nope", json.dumps(e))


# --------------------------------------------------------------- /tradecheck
class TradeTests(unittest.TestCase):
    def side(self, franchise, team_id, players="", picks=""):
        return trade.Side(franchise, team_id, players, picks)

    def run_check(self, a, b, to_minors="", clearance=None, picks=None, window=("open", "Open.")):
        return trade.check(a=a, b=b, rosters=ROSTERS, player_ids=named_players(),
                           picks_raw=picks if picks is not None else PICKS,
                           clearance=clearance or Clearance("ok", {TEST: {"paid_through": 2027},
                                                                   TEST3: {"paid_through": 2029}}),
                           to_minors=to_minors, window=window)

    def test_parse_picks(self) -> None:
        picks, unread = trade.parse_picks("2029 1st, 2028 3rd; 2030 round 2 and 2027 R5, 2028 second, 2nd 2029, junk")
        self.assertEqual(picks, [(2029, 1), (2028, 3), (2030, 2), (2027, 5), (2028, 2), (2029, 2)])
        self.assertEqual(unread, ["junk"])
        self.assertEqual(trade.parse_picks(""), ([], []))

    def test_match_players(self) -> None:
        players = trade.roster_players(ROSTERS, TEST3, named_players())
        found, missing, ambiguous = trade.match_players("Dominic Smith, Alonso, Bobby Witt, smith", players)
        self.assertEqual([p["id"] for p in found], ["061a2", "03e1n"])
        self.assertEqual(missing, ["Bobby Witt"])
        self.assertEqual(len(ambiguous), 1)
        self.assertIn("Dominic Smith or Cam Smith", ambiguous[0])

    def test_prepayment_paid_unpaid_and_round_three(self) -> None:
        c = self.run_check(self.side("Test", TEST, picks="2028 1st, 2027 2nd, 2028 3rd"),
                           self.side("Test 3", TEST3, picks="2029 1st"))
        a_status = [s for s, _ in c.a.prepay]
        self.assertEqual(a_status, ["paid", "unpaid"])          # 2027 paid; 2028 needs a prepayment
        self.assertIn("**NOT PAID:**", c.a.prepay[1][1])
        self.assertIn("Season 2027", c.a.prepay[1][1])
        self.assertEqual([s for s, _ in c.b.prepay], ["paid"])  # Test 3 is paid through 2029
        self.assertIn("Test: prepayment", c.problems())

    def test_prepayment_without_ledger_is_a_manual_check(self) -> None:
        c = self.run_check(self.side("Test", TEST, picks="2029 2nd"), self.side("Test 3", TEST3, picks="2028 4th"),
                           clearance=Clearance("unset"))
        self.assertEqual([s for s, _ in c.a.prepay], ["unknown"])
        self.assertIn("isn't set up", c.a.prepay[0][1])
        self.assertEqual(c.b.prepay, [])  # rounds 3 to 5 need no prepayment (12.7)
        self.assertEqual(c.problems(), [f"Test 3: Reserve over by {18 - sport.BENCH}"])  # already over before the trade
        self.assertIn("already over a limit before this trade", json.dumps(trade.embed(c)))
        c.b.after = {key: 0 for key in team.LIMITS}
        self.assertEqual(c.problems(), [])
        self.assertIn("need a manual check", trade.embed(c)["description"])

    def test_pick_ownership(self) -> None:
        c = self.run_check(self.side("Test", TEST, picks="2028 1st, 2031 1st"), self.side("Test 3", TEST3, picks="2029 3rd"),
                           picks=traded_picks())
        self.assertEqual(c.a.pick_problems, ["2031 1st isn't tradeable in Fantrax (picks for 2027 to 2029 are, the "
                                             "next three Annual Drafts, 12.1)"])
        c = self.run_check(self.side("Test", TEST, picks="2029 2nd"), self.side("Test 3", TEST3, picks="2029 3rd"),
                           picks=traded_picks())
        self.assertEqual(c.a.pick_problems, ["doesn't own a 2029 2nd in Fantrax"])
        c = self.run_check(self.side("Test", TEST, picks="2028 1st, 2028 1st"), self.side("Test 3", TEST3, picks="2029 3rd"),
                           picks=traded_picks())
        self.assertEqual(c.a.pick_problems, [])  # owns its own and Test 4's 2028 1st

    def test_roster_limits_after_trade(self) -> None:
        # Test sends its only catcher for a first baseman and Soto (to minors).
        c = self.run_check(self.side("Test", TEST, players="Will Smith"),
                           self.side("Test 3", TEST3, players="Dominic Smith, Juan Soto"),
                           to_minors="Soto, Babe Ruth")
        # The open slot is C and no first baseman can fill it, so Dominic Smith goes to reserve.
        self.assertEqual(c.a.placed, {"061a2": "reserve", "0045j": "minors"})
        self.assertEqual(c.a.after, {"active": FULL - 1, "reserve": 9, "minors": 11, "ir": 0})
        self.assertEqual(c.a.empty_slots, ["C"])
        self.assertEqual(c.to_minors_unmatched, ["Babe Ruth"])
        # Test 3 already has a catcher and nobody else who can play the outfield spot Soto leaves.
        self.assertEqual(c.b.placed, {"04lcs": "reserve"})
        self.assertEqual(c.b.after, {"active": FULL - 1, "reserve": 18, "minors": 0, "ir": 0})
        problems = c.problems()
        self.assertIn(f"Test: Reserve over by {9 - sport.BENCH}", problems)
        self.assertFalse([p for p in problems if "Minors" in p])   # 11 is within the minors limit
        self.assertIn(f"Test 3: Reserve over by {18 - sport.BENCH}", problems)
        self.assertIn("**Test:** nobody left who can play C (6.2).", json.dumps(trade.embed(c), ensure_ascii=False))

    def test_a_teammate_shifts_so_an_incoming_player_starts(self) -> None:
        # Test sends its shortstop for an outfielder. Luis Garcia Jr. (2B/SS, in a UTIL slot) moves to SS and
        # Soto starts at UTIL: Test stays at a full lineup and 8 reserves, all legal (6.1, 6.2).
        c = self.run_check(self.side("Test", TEST, players="Bobby Witt Jr."),
                           self.side("Test 3", TEST3, players="Juan Soto"))
        self.assertEqual(c.a.placed, {"0045j": "active"})
        self.assertEqual((c.a.after["active"], c.a.after["reserve"]), (FULL, 8))
        self.assertEqual(c.a.empty_slots, [])
        self.assertFalse([p for p in c.problems() if p.startswith("Test:")])
        # Test 3 has nobody else for the outfield, so Witt (SS) can't start there.
        self.assertEqual(c.b.placed, {"03v70": "reserve"})

    def test_lineup_math(self) -> None:
        hitters = [team.positions("C"), team.positions("SS"), team.positions("2B,SS"), team.positions("UT")]
        self.assertEqual(team.lineup_size(hitters), 4)
        self.assertEqual(team.lineup_size([team.positions("C")] * 3), 3)   # C, then both UTIL slots
        self.assertEqual(team.lineup_size([team.positions("SP")] * 7), sport.LINEUP["SP"])
        self.assertIn("C", team.empty_slots([team.positions("SS")]))

    def test_trade_deadline_from_fantrax(self) -> None:
        deadline = trade.trade_deadline(INFO, NY)
        self.assertEqual(deadline.astimezone(NY), datetime(2027, 2, 21, 23, 59, 59, tzinfo=NY))
        self.assertIsNone(trade.trade_deadline(None, NY))

    def test_trade_window(self) -> None:
        deadline = datetime(2027, 2, 22, 4, 59, 59, tzinfo=UTC)
        reopens = datetime(2027, 6, 25, 13, tzinfo=UTC)
        self.assertEqual(trade.trade_window(deadline - timedelta(days=1), deadline, None)[0], "open")
        status, text = trade.trade_window(deadline + timedelta(days=1), deadline, reopens)
        self.assertEqual(status, "closed")
        self.assertIn(f"<t:{int(reopens.timestamp())}:F>", text)
        self.assertEqual(trade.trade_window(reopens + timedelta(hours=1), deadline, reopens)[0], "open")
        self.assertEqual(trade.trade_window(deadline + timedelta(days=1), deadline, None)[0], "closed")
        self.assertEqual(trade.trade_window(deadline + timedelta(days=60), deadline, None, season_over=True)[0], "unknown")
        self.assertEqual(trade.trade_window(deadline, None, None)[0], "unknown")
        stale = datetime(2026, 6, 20, tzinfo=UTC)  # last year's reopening date is ignored
        self.assertEqual(trade.trade_window(deadline + timedelta(days=1), deadline, stale)[0], "closed")

    def test_embed_never_grades_value(self) -> None:
        c = self.run_check(self.side("Test", TEST, players="Will Smith", picks="2027 1st"),
                           self.side("Test 3", TEST3, picks="2029 1st"))
        e = trade.embed(c)
        text = json.dumps(e).lower()
        self.assertIn("never grades value", text)
        for word in ("fair", "overpay", "winner", "lopsided", "rating"):
            self.assertNotIn(word, text)
        self.assertIn("conditional draft picks are prohibited (11.5)", text)
        self.assertIn("side deals", text)
        self.assertIn("(11.3)", text)
        self.assertTrue(embeds.fits([e]))

    def test_build_end_to_end(self) -> None:
        a = self.side("Test", TEST, players="Will Smith", picks="2028 2nd")
        b = self.side("Test 3", TEST3, players="Dominic Smith")
        e = trade.build(FakeData(), a, b, "", datetime(2026, 11, 1, tzinfo=UTC), NY)
        text = json.dumps(e)
        self.assertIn("NOT PAID", text)
        self.assertIn("Open. Trade deadline: <t:", text)
        late = trade.build(FakeData(), self.side("Test", TEST, picks="2028 4th"), self.side("Test 3", TEST3, picks="2028 5th"),
                           "", datetime(2027, 3, 1, tzinfo=UTC), NY)
        self.assertIn("**Closed**", json.dumps(late))
        self.assertIn("Trading reopens <t:", json.dumps(late))

    def test_build_with_fantrax_down(self) -> None:
        a = self.side("Test", TEST, players="Will Smith")
        b = self.side("Test 3", TEST3, picks="2029 1st")
        with self.assertLogs("league.bot", level="WARNING"):
            e = trade.build(FakeData(fail={"league_info", "rosters", "draft_picks"}), a, b, "", DURING_WEEK_2, NY)
        text = json.dumps(e)
        self.assertIn("Couldn't read Test's roster", text)
        self.assertIn("Couldn't read draft picks", text)
        # The deadline falls back to the League Calendar's trade-deadline event.
        self.assertIn("Open. Trade deadline", text)


# ------------------------------------------------------------------ Pick'em
class PickemTests(unittest.TestCase):
    def test_matchups_and_season_key(self) -> None:
        ms = pickem.matchups(INFO, 1)
        self.assertEqual(len(ms), 6)
        self.assertEqual((ms[0].away, ms[0].home), ("Test 8", "Test 4"))
        self.assertEqual(pickem.matchups(INFO, 23), [])  # playoff seeds, no teams
        self.assertEqual(pickem.season_key("w02c", INFO), "w02c:2026")
        self.assertEqual(pickem.season_label("w02c:2026"), "Season 2026")

    def test_post_when_previous_week_is_final(self) -> None:
        week1 = season.period(INFO, 1)
        self.assertEqual(pickem.post_at(INFO, 2, NY), season.final_at(week1, NY))
        self.assertEqual(pickem.post_at(INFO, 1, NY), week1.start - pickem.FIRST_WEEK_LEAD)

    def test_plan_timeline(self) -> None:
        week1, week2 = season.period(INFO, 1), season.period(INFO, 2)
        self.assertEqual(pickem.plan(INFO, week1.start - timedelta(days=4), NY, {}), [])
        self.assertEqual(pickem.plan(INFO, week1.start - timedelta(days=2), NY, {}), [("post", 1)])
        self.assertEqual(pickem.plan(INFO, week1.start + timedelta(minutes=1), NY, {1: "open"}), [("lock", 1)])
        self.assertEqual(pickem.plan(INFO, week1.start + timedelta(days=1), NY, {1: "locked"}), [])
        final1 = season.final_at(week1, NY)
        self.assertEqual(pickem.plan(INFO, final1, NY, {1: "locked"}), [("score", 1), ("post", 2)])
        self.assertEqual(pickem.plan(INFO, final1, NY, {1: "scored", 2: "open"}), [])
        # A Week that started before the bot could post is skipped, never posted late.
        self.assertEqual(pickem.plan(INFO, week2.start + timedelta(hours=1), NY, {1: "scored"}), [])

    def test_no_playoff_weeks(self) -> None:
        week23 = season.period(INFO, 23)
        stored = {n: "scored" for n in range(1, 23)}
        self.assertEqual(pickem.plan(INFO, week23.start - timedelta(hours=2), NY, stored), [])

    def test_winners_ties_and_missing(self) -> None:
        ms = pickem.matchups(INFO, 2)
        won = pickem.winners(ms, SCORES_2)
        test_vs_test3 = next(m for m in ms if {m.away, m.home} == {"Test 3", "Test"})
        self.assertEqual(won[test_vs_test3.key], TEST)  # 11.1 to 0
        self.assertIsNone(won[ms[0].key])  # 0 to 0: exact tie
        self.assertEqual(len(won), 6)
        partial = pickem.winners(ms, SCORES_2[:3])
        self.assertEqual(len(partial), 3)
        final = datetime(2026, 10, 12, 10, tzinfo=UTC)
        self.assertFalse(pickem.ready_to_score(ms, partial, final, final))
        self.assertTrue(pickem.ready_to_score(ms, partial, final + pickem.SCORE_GRACE, final))
        self.assertTrue(pickem.ready_to_score(ms, won, final, final))

    def test_scoring_one_point_per_correct_pick_tie_scores_nobody(self) -> None:
        won = {"a@b": "a", "c@d": None, "e@f": "f"}
        picks = [(1, "a@b", "a"), (1, "c@d", "c"), (1, "e@f", "f"), (2, "a@b", "b"), (2, "c@d", "d"), (3, "x@y", "x")]
        self.assertEqual(pickem.weekly(picks, won), {1: 2, 2: 0, 3: 0})

    def test_leaderboard_and_ties(self) -> None:
        board = pickem.leaderboard([{1: 4, 2: 5}, {1: 3, 2: 2, 3: 6}])
        self.assertEqual(board, [(1, 7, 2), (2, 7, 2), (3, 6, 1)])
        self.assertEqual([r[0] for r in pickem.ranked(board)], ["T1", "T1", "3"])

    def test_pages_respect_five_action_rows(self) -> None:
        ms = pickem.matchups(INFO, 1)
        self.assertEqual([len(p) for p in pickem.pages(ms)], [4, 2])
        self.assertLessEqual(pickem.PER_PAGE, 4)  # the fifth row holds the page buttons

    def test_embeds_fit(self) -> None:
        ms = pickem.matchups(INFO, 2)
        locks = season.period(INFO, 2).start
        post = pickem.post_embed(2, ms, locks)
        self.assertIn(f"<t:{int(locks.timestamp())}:F>", post["description"])
        won = pickem.winners(ms, SCORES_2)
        board = pickem.leaderboard([{u: u % 7 for u in range(40)}])
        result = pickem.results_embed(2, ms, won, {u: u % 7 for u in range(40)}, board, "Season 2026")
        self.assertIn("tied exactly (no points)", json.dumps(result))
        self.assertIn("**Test** beat Test 3", json.dumps(result))
        for e in (post, result, pickem.leaderboard_embed(board, "Season 2026", 1), pickem.leaderboard_embed([], "S", 0)):
            self.assertTrue(embeds.fits([e]))
        content = pickem.picks_content(2, ms, {ms[0].key: ms[0].away_id}, locks, 0, 2)
        self.assertIn("1 of 6 picked", content)
        self.assertIn("page 1 of 2", content)


class PickemStoreTests(unittest.TestCase):
    def test_week_and_picks_lifecycle(self) -> None:
        s = Store(":memory:")
        now = datetime(2026, 10, 5, 10, tzinfo=UTC)
        ms = pickem.matchups(INFO, 2)
        s.add_pickem_week("L:2026", 2, [m.as_dict() for m in ms], locks_at=season.period(INFO, 2).start, now=now)
        s.set_pickem_message("L:2026", 2, 10, 20)
        self.assertEqual(s.pickem_statuses("L:2026"), {2: "open"})
        self.assertEqual(s.pickem_week_by_message(20)["period"], 2)
        s.pick("L:2026", 2, 7, ms[0].key, ms[0].away_id, now=now)
        s.pick("L:2026", 2, 7, ms[0].key, ms[0].home_id, now=now)  # change of mind replaces the pick
        s.pick("L:2026", 2, 8, ms[0].key, ms[0].away_id, now=now)
        self.assertEqual(s.user_picks("L:2026", 2, 7), {ms[0].key: ms[0].home_id})
        self.assertEqual(len(s.week_picks("L:2026", 2)), 2)
        s.set_pickem_status("L:2026", 2, "scored", winners={ms[0].key: ms[0].home_id}, now=now)
        self.assertEqual(s.scored_weeks("L:2026"), [(2, {ms[0].key: ms[0].home_id})])
        self.assertEqual(s.latest_pickem_season(), "L:2026")
        rebuilt = pickem.leaderboard(pickem.weekly(s.week_picks("L:2026", p), w) for p, w in s.scored_weeks("L:2026"))
        self.assertEqual(rebuilt, [(7, 1, 1), (8, 0, 1)])

    def test_existing_database_gains_the_new_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.db"
            db = sqlite3.connect(path)
            db.executescript("CREATE TABLE proposals (id INTEGER PRIMARY KEY, title TEXT);"
                             "INSERT INTO proposals (title) VALUES ('kept');")
            db.commit()
            db.close()
            s = Store(path)
            self.assertEqual(s.pickem_statuses("x"), {})
            self.assertEqual(s.db.execute("SELECT title FROM proposals").fetchone()[0], "kept")
            s.db.close()
            Store(path).db.close()  # opening again is harmless


# ----------------------------------------------------------- config & roles
class ConfigAndRoleTests(unittest.TestCase):
    def test_shipped_config_has_test_league_ids_in_draft_order(self) -> None:
        cfg = load(HERE.parent / "config.yaml")
        order = list(dict.fromkeys(p["originalOwnerTeamId"] for p in PICKS["futureDraftPicks"]))
        self.assertEqual([f.fantrax_team_id for f in cfg.franchises], order)
        self.assertEqual(cfg.pickem_players, ("owner", "co_owner"))
        self.assertEqual(cfg.settings.amendment_votes_from.date(), date(2027, 9, 27))
        self.assertFalse(rules.fantrax_id_problems(cfg.franchises, team.team_names(INFO)))
        self.assertTrue(any("pickem_channel_id" in p for p in cfg.problems))

    def test_validation_messages(self) -> None:
        text = """
discord: {guild_id: "12x", co_owner_role_id: "55", franchise_owner_role_id: "44", pickem_channel_id: "9",
          scheduled_for_vote_tag_id: "3"}
franchises:
  - {name: A, role_id: "1", fantrax_team_id: "t1", commissioner: true}
  - {name: B, role_id: "2", fantrax_team_id: "t1"}
  - {name: C, role_id: "3"}
pickem: {players: [owner, fans]}
"""
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(text)
        try:
            cfg = load(f.name)
        finally:
            os.unlink(f.name)
        problems = "\n".join(cfg.problems)
        self.assertIn("discord.guild_id must be a Discord ID", problems)
        self.assertIn("Two franchises share a fantrax_team_id.", problems)
        self.assertIn("C has no fantrax_team_id yet", problems)
        self.assertIn("pickem.players has 'fans'", problems)
        self.assertIn("scheduled_for_vote_tag_id needs discord.suggestions_forum_id", problems)
        self.assertEqual(cfg.member_role_ids, {44, 55})
        self.assertEqual(cfg.pickem_role_ids, {44})
        self.assertNotIn("pickem_channel_id is not set", problems)
        self.assertEqual(rules.fantrax_id_problems(cfg.franchises, {"t1": "Team"}), [])
        self.assertEqual(len(rules.fantrax_id_problems(cfg.franchises, {"t9": "Team"})), 2)

    def test_team_member(self) -> None:
        fs = [rules.Franchise("A", 1, fantrax_team_id="t1"), rules.Franchise("B", 2)]
        self.assertEqual(rules.team_member({1, 44}, {44, 55}, fs)[0].name, "A")
        self.assertEqual(rules.team_member({1, 55}, {44, 55}, fs)[0].name, "A")  # Co-Owner
        self.assertIn("Franchise Owner or Co-Owner", rules.team_member({1}, {44, 55}, fs)[1])
        self.assertIn("franchise role", rules.team_member({44}, {44, 55}, fs)[1])
        self.assertIn("more than one", rules.team_member({1, 2, 44}, {44, 55}, fs)[1])
        self.assertIn("fantrax_team_id", rules.team_member({2, 44}, {44}, fs, needs_fantrax=True)[1])
        self.assertIn("aren't set up", rules.team_member({1}, set(), fs)[1])


# ------------------------------------------------------------------ caching
class FakeClient:
    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    def _hit(self, name, value):
        self.calls[name] = self.calls.get(name, 0) + 1
        return value

    def league_info(self):
        return self._hit("info", INFO)

    def rosters(self):
        return self._hit("rosters", ROSTERS)

    def draft_picks(self):
        return self._hit("picks", PICKS)

    def player_ids(self):
        return self._hit("players", {})

    def matchup_scores(self, period):
        return self._hit(f"scores{period}", SCORES_2)


class CacheTests(unittest.TestCase):
    def test_ttl_cache_expires(self) -> None:
        clock = [0.0]
        cache = TTLCache(lambda: clock[0])
        loads = []
        self.assertEqual(cache.get("k", 10, lambda: loads.append(1) or "v"), "v")
        cache.get("k", 10, lambda: loads.append(1) or "v")
        clock[0] = 11
        cache.get("k", 10, lambda: loads.append(1) or "v")
        self.assertEqual(len(loads), 2)

    def test_league_data_fills_in_a_set_drafts_picks(self) -> None:
        # Fantrax's currentDraftPicks rows: holder, round and pick number only.
        class Client:
            reads = 0

            def draft_picks(self):
                return {"futureDraftPicks": [], "currentDraftPicks": [
                    {"teamId": "b", "round": 1, "pick": 1}, {"teamId": "b", "round": 1, "pick": 2},
                    {"teamId": "c", "round": 1, "pick": 3}]}

            def draft_results(self):
                Client.reads += 1
                return {"draftDate": "2028-07-20T20:00:00.0-0400", "draftState": "scheduled",
                        "draftOrder": ["a", "b", "c"], "draftPicks": []}
        data = LeagueData(Client(), league_id="L", league_loader=lambda: {"timezone": "America/New_York"})
        owned, away = team.picks_of(data.draft_picks(), "b")
        self.assertEqual([(p["year"], p["round"], p["original"]) for p in owned], [(2028, 1, "b"), (2028, 1, "a")])
        _, away = team.picks_of(data.draft_picks(), "a")
        self.assertEqual([(p["year"], p["owner"]) for p in away], [(2028, "b")])
        self.assertEqual(Client.reads, 1)

    def test_league_data_reuses_reads(self) -> None:
        clock = [0.0]
        client = FakeClient()
        data = LeagueData(client, league_id="L", clock=lambda: clock[0], events_loader=lambda: EVENTS)
        for _ in range(3):
            data.league_info(), data.rosters(), data.matchup_scores(2), data.events()
        data.matchup_scores(3)
        self.assertEqual(client.calls, {"info": 1, "rosters": 1, "scores2": 1, "scores3": 1})
        clock[0] = 6 * 60
        data.rosters()
        data.league_info()
        self.assertEqual(client.calls["rosters"], 2)
        self.assertEqual(client.calls["info"], 1)

    def test_clearance_states(self) -> None:
        with patch.dict(os.environ, {"LEAGUE_LEDGER_CLEARANCE_CSV": ""}):
            self.assertEqual(LeagueData(FakeClient(), league_id="L").clearance().status, "unset")
        csv_text = "Fantrax Team ID,Franchise,Paid Through\nt1,Test,2028\n"
        from league_bot.shared import picktrades
        ok = LeagueData(FakeClient(), league_id="L", clearance_loader=lambda: picktrades().parse_clearance(csv_text))
        self.assertEqual(ok.clearance(), Clearance("ok", {"t1": {"franchise": "Test", "paid_through": 2028}}))
        bad = LeagueData(FakeClient(), league_id="L", clearance_loader=lambda: None)
        self.assertEqual(bad.clearance().status, "error")


class MlbLookupTests(unittest.TestCase):
    def test_search_and_career_are_cached(self) -> None:
        mlb, fetch = lookup_client()
        mlb.search("Konnor Griffin")
        mlb.search("konnor  griffin")
        mlb.career(804606)
        mlb.career(804606)
        self.assertIsNone(mlb.career(1))   # MLB has no record
        self.assertEqual(len(fetch.calls), 3)
        e, _ = minor.lookup(mlb, "Konnor Griffin", None)
        self.assertIn("NO", e["description"])
        self.assertEqual(len(fetch.calls), 3)


class EmbedHelperTests(unittest.TestCase):
    def test_finish_keeps_footer_and_divider_on_the_last_embed_only(self) -> None:
        cards = [embeds.card("A", "a", [], "F"), embeds.card("B", "b", [], "F")]
        out = embeds.finish(cards)
        self.assertNotIn("footer", out[0])
        self.assertNotIn("image", out[0])
        self.assertEqual(out[1]["footer"]["text"], "F")

    def test_card_clips_to_limits(self) -> None:
        e = embeds.card("T" * 300, "D" * 5000, [("N", "V" * 2000), ("Empty", "")], "F")
        self.assertTrue(embeds.fits([e]))
        self.assertTrue(e["description"].endswith("…"))
        self.assertFalse(embeds.fits([e] * 2))  # over 6,000 characters together


if __name__ == "__main__":
    unittest.main()
