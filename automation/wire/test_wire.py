#!/usr/bin/env python3
"""Offline regression checks for DBL The Wire (no network; feedparser is not needed)."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import engine  # noqa: E402
import roster  # noqa: E402
import wire  # noqa: E402
from core import mlb_people as mp  # noqa: E402

FIXTURES = HERE.parent / "tests" / "fixtures"
TX_SOURCE = {"id": "mlb_transactions", "name": "MLB Transactions", "type": "mlb_transactions", "tier": 0}


def transactions() -> list[mp.Transaction]:
    raw = json.loads((FIXTURES / "mlb_transactions_2026-07-28.json").read_text(encoding="utf-8"))
    return mp.parse_transactions(raw)


def tx_entries() -> dict[str, dict]:
    """Wire entries from the transactions fixture, keyed by the first player's name."""
    return {e["player"]: e for e in wire.transaction_entries(transactions())}


class WireRoutingTests(unittest.TestCase):
    def route(self, title: str, breaking: bool = False) -> str:
        return wire.classify_title(title, breaking)

    def test_trade_analysis_and_questions_stay_news(self) -> None:
        self.assertEqual(self.route("Grading the trade that sent Logan O'Hoppe to the Rangers"), "mlb-news")
        self.assertEqual(self.route("Would the Cardinals trade Willson Contreras?"), "mlb-news")
        self.assertEqual(self.route("Twins Interested In Wade Miley"), "mlb-news")

    def test_actual_moves_route_transactions(self) -> None:
        for title in ("Angels trade Logan O'Hoppe to Rangers",
                      "Yankees sign Juan Soto to 15-year deal",
                      "Tigers designate Jake Rogers for assignment",
                      "Brewers outright Braden Shewmake to Triple-A",
                      "Phillies option Payton Henry to Triple-A",
                      "Pirates recall Jack Suwinski from Indianapolis",
                      "Cardinals select contract of Peter Strzelecki",
                      "Rays call up top prospect Carson Williams",
                      "Mets exercise Pete Alonso's option for 2027",
                      "Bo Bichette opts out of his contract with the Mets"):
            self.assertEqual(self.route(title), "mlb-transactions", title)

    def test_injury_has_priority_over_transaction_words(self) -> None:
        self.assertEqual(self.route("Twins place Byron Buxton on 10-day IL after trade rumors"), "injury-report")

    def test_injured_list_short_forms(self) -> None:
        for title in ("Pasquantino lands on 10-day IL with wrist soreness",
                      "Dodgers activate Edwin Diaz off the IL",
                      "Buxton out for Twins' next two games",
                      "Skubal will miss his next start with a blister"):
            self.assertEqual(self.route(title), "injury-report", title)

    def test_season_ending_injury_is_breaking(self) -> None:
        for title in ("Spencer Strider will miss rest of season with torn UCL",
                      "Astros' Yordan Alvarez out six to eight months after surgery",
                      "Braves ace to undergo Tommy John surgery"):
            self.assertEqual(self.route(title, True), "breaking-news", title)
            self.assertEqual(self.route(title, False), "injury-report", title)

    def test_short_absence_is_injury_not_breaking(self) -> None:
        self.assertEqual(self.route("Buxton out 2-3 weeks with hip impingement", True), "injury-report")
        self.assertEqual(self.route("Juan Soto out two weeks", True), "injury-report")

    def test_signing_opinion_piece_stays_news(self) -> None:
        for title in ("Why the Mets need to sign Pete Alonso to a long-term deal",
                      "How the Yankees could trade for a starting pitcher"):
            self.assertEqual(self.route(title), "mlb-news", title)

    def test_player_named_will_is_not_an_opinion_piece(self) -> None:
        for title in ("Will Smith signs 10-year extension with Dodgers",
                      "Will Benson traded to Reds from Guardians"):
            self.assertEqual(self.route(title), "mlb-transactions", title)

    def test_prospect_news(self) -> None:
        for title in ("Pirates top prospect Konnor Griffin promoted to Triple-A",
                      "Konnor Griffin makes MLB debut for Pirates",
                      "Arizona Fall League standouts from the first week"):
            self.assertEqual(self.route(title), "prospect-wire", title)

    def test_season_talk_without_absence_stays_news(self) -> None:
        for title in ("What to expect from the Yankees the rest of the season",
                      "These are the 2026 Gold Glove Award finalists"):
            self.assertEqual(self.route(title, True), "mlb-news", title)


class WireSourceTests(unittest.TestCase):
    def test_rss_link_recovers_alternate_href(self) -> None:
        entry = {
            "link": "",
            "links": [
                {"rel": "enclosure", "href": "https://cdn.example.test/audio.mp3"},
                {"rel": "alternate", "href": "https://www.mlb.com/news/example-story"},
            ],
            "id": "guid-123",
        }
        self.assertEqual(wire._rss_entry_link(entry), "https://www.mlb.com/news/example-story")

    def test_rss_link_can_use_http_guid(self) -> None:
        entry = {"link": "", "links": [], "guid": "https://www.mlb.com/news/guid-story"}
        self.assertEqual(wire._rss_entry_link(entry), "https://www.mlb.com/news/guid-story")

    def test_rss_link_does_not_invent_url_from_non_http_guid(self) -> None:
        self.assertEqual(wire._rss_entry_link({"link": "", "links": [], "guid": "mlb:story:12345"}), "")

    def test_feed_noise_is_ignored(self) -> None:
        # Real headlines seen in the MLB.com, CBS Sports and MLB Trade Rumors feeds on 2026-10-15.
        for title, source in (("LIVE: Brewers-Dodgers NLCS Game 3 on FS1/FOX One", "mlb_news"),
                              ("Updated Thursday start times: 1 ET (ALCS Game 3), 8 ET (NLCS Game 4)", "mlb_news"),
                              ("Use FanDuel promo code to get $350 bonus bets by targeting Guardians vs. Rays", "cbs_mlb"),
                              ("Guardians vs. Rays ALCS Game 2 picks: Tampa Bay hasn't lost consecutive games at home",
                               "cbs_mlb"),
                              ("Poll: Will Bo Bichette Opt Out?", "mlb_trade_rumors"),
                              ("East Notes: Mets, Wright, Colon, Jays, Red Sox, Sale", "mlb_trade_rumors"),
                              ("Brendan Gawlowski Prospects Chat 10-13-26", "fangraphs_prospects")):
            self.assertTrue(wire.should_ignore(title, source, "mlb-news"), title)

    def test_real_stories_are_kept(self) -> None:
        for title in ("Cardinals Open To Short-Term Addition At Third Base",
                      "These are the 2026 Gold Glove Award finalists",
                      "Arizona Fall League Pitcher Scouting Notebook"):
            self.assertFalse(wire.should_ignore(title, "mlb_trade_rumors", "mlb-news"), title)

    def test_community_posts_need_a_reporter(self) -> None:
        self.assertTrue(wire.should_ignore("Anyone else think the Mets look good?", "reddit_baseball", "mlb-news"))
        self.assertFalse(wire.should_ignore("[Passan] Juan Soto agrees to deal with Mets", "reddit_baseball",
                                            "mlb-transactions"))
        self.assertFalse(wire.should_ignore("[Rosenthal] Mets hire new pitching coach", "reddit_baseball", "mlb-news"))


class TransactionCollectorTests(unittest.TestCase):
    """MLB's transaction log, routed to injury-report and mlb-transactions (fixture in MLB's shape)."""

    def setUp(self) -> None:
        self.by_name = tx_entries()

    def test_injured_list_moves_and_rehab_go_to_the_injury_report(self) -> None:
        for name in ("Rob Refsnyder", "Beck Way", "Cole Sands", "Byron Buxton", "Danny Jansen", "Chris Bassitt"):
            self.assertEqual(self.by_name[name]["channel"], "injury-report", name)
        self.assertEqual(self.by_name["Byron Buxton"]["position"], "CF")
        self.assertEqual(self.by_name["Byron Buxton"]["team"], "MIN")
        self.assertEqual(self.by_name["Byron Buxton"]["source_detail"], "Injured list")
        self.assertEqual(self.by_name["Chris Bassitt"]["teams"], ["BAL"])   # Norfolk is an affiliate

    def test_roster_moves_go_to_mlb_transactions(self) -> None:
        for name in ("Jake Rogers", "Peter Strzelecki", "Johnathan Rodríguez", "Jose Franco", "Dennis Santana",
                     "Braden Shewmake", "Grant Hill", "Brandon Jaenke", "Sample Claim"):
            self.assertEqual(self.by_name[name]["channel"], "mlb-transactions", name)

    def test_other_status_changes_are_left_out(self) -> None:
        titles = [e["title"] for e in self.by_name.values()]
        self.assertNotIn("C Logan O'Hoppe roster status changed by Los Angeles Angels.", titles)
        self.assertNotIn("Cincinnati Reds activated RHP Jose Franco.", titles)
        self.assertEqual(self.by_name["Jose Franco"]["source_detail"], "Recalled")

    def test_a_trade_is_one_entry_with_every_player(self) -> None:
        trades = [e for e in self.by_name.values() if e["source_detail"] == "Trade"]
        self.assertEqual(len(trades), 1)
        trade = trades[0]
        self.assertEqual(sorted(p["player"] for p in trade["players"]), ["Angel Arredondo", "Chase Silseth", "Logan O'Hoppe"])
        self.assertEqual(sorted(trade["teams"]), ["LAA", "TEX"])
        self.assertTrue(trade["title"].startswith("Los Angeles Angels traded C Logan O'Hoppe"))

    def test_a_move_listed_twice_is_posted_once(self) -> None:
        entries = wire.transaction_entries(transactions())
        sanchez = [e for e in entries if e["player"] == "Jesús Sánchez"]
        self.assertEqual(len(sanchez), 1)
        again = wire.transaction_entries(transactions())
        self.assertEqual([e["external_id"] for e in entries], [e["external_id"] for e in again])

    def test_minor_league_deals_and_draft_pick_signings_need_a_dbl_roster(self) -> None:
        self.assertTrue(self.by_name["Brandon Jaenke"]["only_if_rostered"])   # minor league contract
        self.assertTrue(self.by_name["Grant Hill"]["only_if_rostered"])       # plain "signed" record
        self.assertFalse(self.by_name["Jake Rogers"]["only_if_rostered"])

    def test_entries_link_the_player_page_and_are_structured(self) -> None:
        e = self.by_name["Byron Buxton"]
        self.assertEqual(e["link"], "https://www.mlb.com/player/621439")
        self.assertTrue(e["structured"])
        self.assertEqual(e["published"], "")

    def test_collector_reads_today_and_the_lookback(self) -> None:
        calls = []

        def fetch(url, params):
            calls.append(params)
            return json.loads((FIXTURES / "mlb_transactions_2026-07-28.json").read_text(encoding="utf-8"))

        entries = wire.fetch_mlb_transactions({"lookback_days": 1}, today=date(2026, 7, 29), api=mp.MlbApi(fetch))
        self.assertEqual(calls, [{"sportId": 1, "startDate": "2026-07-28", "endDate": "2026-07-29"}])
        self.assertTrue(entries)


class WireFormattingTests(unittest.TestCase):
    def test_rfc_feed_timestamp_parses(self) -> None:
        parsed = engine.published_timestamp("Wed, 14 Oct 2026 19:05:00 GMT")
        self.assertTrue(str(parsed).endswith("+00:00"))

    def test_player_name_normalization(self) -> None:
        self.assertEqual(roster.normalize_player_name("Jesús Sánchez Jr."), roster.normalize_player_name("Jesus Sanchez"))
        self.assertEqual(roster.normalize_player_name("Witt Jr., Bobby"), roster.normalize_player_name("Bobby Witt Jr."))

    def test_channels_secrets_and_colors(self) -> None:
        self.assertEqual(engine.WEBHOOK_ENV["mlb-news"], "LEAGUE_WEBHOOK_MLB_NEWS")
        self.assertEqual(engine.WEBHOOK_ENV["mlb-transactions"], "LEAGUE_WEBHOOK_MLB_TRANSACTIONS")
        self.assertEqual(engine.CHANNEL_COLORS["mlb-news"], 0xBD3039)
        self.assertEqual(engine.discord_payload(_candidate(1, "mlb-news"))["embeds"][0]["color"], 0xBD3039)
        self.assertEqual(engine.discord_payload(_candidate(1, "unknown"))["embeds"][0]["color"], 0xBD3039)
        self.assertNotIn(0xFFB81C, engine.CHANNEL_COLORS.values())


# Fantrax getPlayerIds-style rows (SYNTHETIC: the MLB league's real directory isn't available yet).
PLAYERS = {
    "a1": {"fantraxId": "a1", "name": "Smith, Will", "position": "C", "team": "LAD"},
    "a2": {"fantraxId": "a2", "name": "Smith, Will", "position": "RP", "team": "KC"},
    "a3": {"fantraxId": "a3", "name": "Garcia, Luis", "position": "RP", "team": "LAD"},
    "a4": {"fantraxId": "a4", "name": "Garcia, Luis", "position": "RP", "team": "SD"},
    "a5": {"fantraxId": "a5", "name": "Garcia Jr., Luis", "position": "2B", "team": "WSH"},
    "a6": {"fantraxId": "a6", "name": "Witt Jr., Bobby", "position": "SS", "team": "KC"},
    "a7": {"fantraxId": "a7", "name": "Buxton, Byron", "position": "OF", "team": "MIN"},
    "a8": {"fantraxId": "a8", "name": "O'Hoppe, Logan", "position": "C", "team": "LAA"},
    "a9": {"fantraxId": "a9", "name": "Arredondo, Angel", "position": "SS", "team": "TEX"},
}


class RosterTagTests(unittest.TestCase):
    """Players who share a name are told apart by MLB team and pitcher or hitter."""

    @classmethod
    def setUpClass(cls) -> None:
        rosters = {"period": 1, "rosters": {
            "team-a": {"teamName": "Alpha", "rosterItems": [{"id": "a1"}, {"id": "a6"}]},    # Will Smith (LAD C), Witt
            "team-b": {"teamName": "Bravo", "rosterItems": [{"id": "a5"}, {"id": "a7"}]},    # Luis Garcia Jr. (WSH 2B), Buxton
            "team-c": {"teamName": "Charlie", "rosterItems": [{"id": "a8"}]},                # O'Hoppe
        }}
        cls.index = roster.build_index(rosters, PLAYERS)

    def test_same_name_different_team(self) -> None:
        self.assertEqual(self.index.match("Will Smith", "LAD", "C").owner_name, "Alpha")
        self.assertIsNone(self.index.match("Will Smith", "KC", "RP"))   # the other Will Smith is a free agent

    def test_same_name_told_apart_by_pitcher_or_hitter(self) -> None:
        self.assertEqual(self.index.match("Luis Garcia", "", "2B").owner_name, "Bravo")
        self.assertIsNone(self.index.match("Luis Garcia", "", "RHP"))    # two pitchers, neither rostered

    def test_ambiguous_without_team_is_not_tagged(self) -> None:
        self.assertIsNone(self.index.match("Will Smith"))

    def test_team_aliases(self) -> None:
        self.assertEqual(self.index.match("Will Smith", "LAN", "").owner_name, "Alpha")
        self.assertEqual(roster.normalize_team("ARI"), "AZ")
        self.assertEqual(roster.position_group("SP,RP"), "P")
        self.assertEqual(roster.position_group("2B,SS"), "H")
        self.assertEqual(roster.position_group("TWP"), "")

    def test_headline_scan_tags_unique_names_only(self) -> None:
        found = self.index.scan("Bobby Witt Jr. and Byron Buxton named players of the week")
        self.assertEqual(sorted(p.owner_name for p in found), ["Alpha", "Bravo"])
        self.assertEqual(self.index.scan("Will Smith homers twice as Dodgers win"), [])

    def test_tagging_transactions_and_news(self) -> None:
        entries = tx_entries()
        injury = engine.build_candidate(TX_SOURCE, entries["Byron Buxton"])
        trade = engine.build_candidate(TX_SOURCE, next(e for e in entries.values() if e["source_detail"] == "Trade"))
        news = _candidate(2, "mlb-news", title="Bobby Witt Jr. extends hitting streak to 20 games")
        self.assertEqual(roster.tag_candidates([injury, trade, news], self.index), 3)
        self.assertEqual(injury["fantasy_owner"], "Bravo")
        self.assertEqual(trade["fantasy_owner"], "Charlie (Logan O'Hoppe)")   # Arredondo and Silseth aren't rostered
        self.assertEqual(news["fantasy_owner"], "Alpha (Bobby Witt Jr.)")

    def test_owner_pings_are_opt_in_and_injury_only(self) -> None:
        injury = _candidate(1, "injury-report")
        injury["owners"] = [{"team_id": "team-b", "team_name": "Bravo", "player": "Byron Buxton"}]
        league = {"owners": {"Bravo": "123456789012345678"}, "wire_pings": {"injuries": True}}
        self.assertEqual(roster.owner_mentions(injury, league), ["123456789012345678"])
        self.assertEqual(roster.owner_mentions(injury, {"owners": {}, "wire_pings": {"injuries": True}}), [])
        self.assertEqual(roster.owner_mentions(dict(injury, channel="mlb-news"), league), [])

    def test_ping_payload_only_allows_listed_users(self) -> None:
        item = _candidate(1, "injury-report")
        item["mentions"] = ["123456789012345678"]
        payload = engine.discord_payload(item)
        self.assertEqual(payload["content"], "<@123456789012345678>")
        self.assertEqual(payload["allowed_mentions"], {"parse": [], "users": ["123456789012345678"]})

    def test_no_ping_by_default(self) -> None:
        payload = engine.discord_payload(_candidate(1, "injury-report"))
        self.assertNotIn("content", payload)
        self.assertEqual(payload["allowed_mentions"], {"parse": []})


_TEAMS = ("Yankees", "Dodgers", "Mets", "Braves", "Astros", "Phillies", "Padres",
          "Mariners", "Orioles", "Guardians", "Twins", "Brewers", "Royals")
_EVENTS = ("lands on injured list", "returns to lineup", "named opening day starter",
           "sent to minors", "signs extension", "homers twice in win", "suspended two games",
           "claimed off waivers", "scratched from lineup", "called up from Triple-A",
           "fined for comments", "out with illness", "sets franchise record")


def _candidate(n: int, channel: str = "injury-report", title: str | None = None) -> dict:
    default_title = f"{_TEAMS[n % len(_TEAMS)]} {channel.split('-')[0]} note: {_EVENTS[(n * 5) % len(_EVENTS)]}"
    return {
        "key": f"key-{channel}-{n}",
        "title": title or default_title,
        "link": f"https://example.test/story/{channel}/{n}",
        "published": "",
        "source_id": "test_source",
        "source_name": "Test Source",
        "source_detail": "",
        "tier": 1,
        "channel": channel,
        "discovery_only": False,
        "dedupe_by_url": True,
        "player": "",
        "team": "",
        "status": "",
        "fantasy_owner": "",
    }


class WireRoundupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sent: list[dict] = []
        self.roundups: list[tuple[str, dict]] = []
        self._deliver = engine.deliver
        self._post = engine.post_payload
        engine.deliver = lambda candidate: self.sent.append(candidate) or True
        engine.post_payload = lambda channel, payload: self.roundups.append((channel, payload)) or True

    def tearDown(self) -> None:
        engine.deliver = self._deliver
        engine.post_payload = self._post

    def run_quietly(self, batch, state, mode="live"):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            return engine.process_candidates(batch, state, mode)

    def test_overflow_becomes_one_roundup_not_dropped(self) -> None:
        state = engine.empty_state()
        counts = self.run_quietly([_candidate(i) for i in range(7)], state)
        self.assertEqual(len(self.sent), engine.MAX_LIVE_POSTS_PER_CHANNEL)
        self.assertEqual(len(self.roundups), 1)
        channel, payload = self.roundups[0]
        self.assertEqual(channel, "injury-report")
        self.assertIn("4 more updates", payload["embeds"][0]["title"])
        self.assertEqual(counts["digested"], 4)
        self.assertEqual(counts["suppressed"], 0)
        self.assertEqual(len(state["seen"]), 7)

    def test_failed_roundup_is_retried_next_run(self) -> None:
        engine.post_payload = lambda channel, payload: False
        state = engine.empty_state()
        self.run_quietly([_candidate(i) for i in range(5)], state)
        self.assertEqual(len(state["seen"]), 3)
        engine.post_payload = lambda channel, payload: self.roundups.append((channel, payload)) or True
        self.sent.clear()
        self.run_quietly([_candidate(i) for i in range(5)], state)
        self.assertEqual([c["key"] for c in self.sent], ["key-injury-report-3", "key-injury-report-4"])
        self.assertEqual(self.roundups, [])
        self.assertEqual(len(state["seen"]), 5)

    def test_duplicates_inside_overflow_are_caught(self) -> None:
        state = engine.empty_state()
        batch = [_candidate(i) for i in range(3)]
        batch.append(_candidate(10, title="Star outfielder out week-to-week with hamstring strain"))
        batch.append(_candidate(11, title="Star outfielder out week to week with hamstring strain"))
        self.run_quietly(batch, state)
        self.assertIn("1 more update", self.roundups[0][1]["embeds"][0]["title"])

    def official(self, name: str) -> dict:
        return engine.build_candidate(TX_SOURCE, tx_entries()[name])

    def test_similar_official_moves_both_post(self) -> None:
        # "... activated X from the 10-day injured list." twice, for two players: both are real moves.
        state = engine.empty_state()
        a, b = self.official("Rob Refsnyder"), self.official("Byron Buxton")
        b["title"] = a["title"].replace("Rob Refsnyder", "Rob Refsnyders")
        self.run_quietly([a, b], state)
        self.assertEqual(len(self.sent), 2)
        self.sent.clear()
        self.run_quietly([self.official("Rob Refsnyder")], state)
        self.assertEqual(self.sent, [])                                       # the same record next run

    def test_same_player_injury_from_a_news_outlet_is_skipped(self) -> None:
        state = engine.empty_state()
        self.run_quietly([self.official("Byron Buxton")], state)
        repeat = _candidate(21, title="Twins' Byron Buxton lands on IL with hip impingement")
        repeat["source_id"] = "mlb_news"
        self.assertTrue(engine.duplicate_reason(repeat, state).startswith("same-player:"))
        role = _candidate(22, title="Twins place CF Buxton on injured list")
        role["source_id"] = "mlb_trade_rumors"
        self.assertTrue(engine.duplicate_reason(role, state).startswith("same-player:"))

    def test_worse_news_and_other_players_still_post(self) -> None:
        state = engine.empty_state()
        self.run_quietly([self.official("Byron Buxton")], state)
        worse = _candidate(31, title="Byron Buxton to miss six weeks after hip surgery")
        worse["source_id"] = "mlb_news"
        self.assertIsNone(engine.duplicate_reason(worse, state))
        other = _candidate(32, title="Twins' Royce Lewis day-to-day with hamstring tightness")
        other["source_id"] = "mlb_news"
        self.assertIsNone(engine.duplicate_reason(other, state))
        breaking = _candidate(33, channel="breaking-news", title="Byron Buxton out for the season with torn ACL")
        breaking["source_id"] = "mlb_news"
        self.assertIsNone(engine.duplicate_reason(breaking, state))

    def test_transaction_headlines_from_news_outlets_are_recorded_not_posted(self) -> None:
        state = engine.empty_state()
        headline = _candidate(40, channel="mlb-transactions", title="Rangers acquire Logan O'Hoppe from Angels")
        headline["source_id"] = "mlb_trade_rumors"
        counts = self.run_quietly([headline, self.official("Jake Rogers")], state)
        self.assertEqual([c["source_id"] for c in self.sent], ["mlb_transactions"])
        self.assertEqual(counts["primary_skipped"], 1)
        self.assertEqual(len(state["seen"]), 2)

    def test_minor_league_deals_post_only_for_dbl_players(self) -> None:
        state = engine.empty_state()
        nobody, ours = self.official("Brandon Jaenke"), self.official("Grant Hill")
        ours["owners"] = [{"team_id": "t", "team_name": "Alpha", "player": "Grant Hill"}]
        counts = self.run_quietly([nobody, ours], state)
        self.assertEqual([c["player"] for c in self.sent], ["Grant Hill"])
        self.assertEqual(counts["unrostered_skipped"], 1)
        self.assertEqual(len(state["seen"]), 2)

    def _seen(self, state, title, source, channel="mlb-news", n=0):
        c = _candidate(100 + n, channel=channel, title=title)
        c["source_id"] = source
        engine.remember(c, state)

    def _check(self, state, title, source, channel="mlb-news", n=50):
        c = _candidate(200 + n, channel=channel, title=title)
        c["source_id"] = source
        return engine.duplicate_reason(c, state)

    def test_same_story_from_two_outlets_is_skipped(self) -> None:
        state = engine.empty_state()
        self._seen(state, "Brewers' Jackson Chourio homers on first pitch of NLCS Game 3", "mlb_news")
        self.assertEqual(self._check(state, "Chourio homers on first pitch as Brewers win NLCS Game 3",
                                     "mlb_trade_rumors"), "same-story")
        self.assertIsNone(self._check(state, "Dodgers announce rotation for the rest of the NLCS",
                                      "mlb_trade_rumors", n=51))

    def test_breaking_news_upgrade_still_posts(self) -> None:
        state = engine.empty_state()
        self._seen(state, "Strider likely to miss time after elbow injury in Braves loss", "mlb_trade_rumors")
        self.assertIsNone(self._check(state, "Strider likely to miss rest of season after elbow injury in Braves loss",
                                      "mlb_news", channel="breaking-news"))

    def test_run_wide_cap_spills_other_channels_into_roundups(self) -> None:
        state = engine.empty_state()
        batch = [_candidate(i, "injury-report") for i in range(3)]
        batch += [_candidate(i, "mlb-news") for i in range(3)]
        batch += [_candidate(i, "prospect-wire") for i in range(2)]
        self.run_quietly(batch, state)
        self.assertEqual(len(self.sent), engine.MAX_LIVE_POSTS_PER_RUN)
        self.assertEqual([c for c, _ in self.roundups], ["prospect-wire"])

    def test_rostered_players_get_individual_posts_first(self) -> None:
        state = engine.empty_state()
        batch = [_candidate(i) for i in range(5)]
        batch[4]["owners"] = [{"team_id": "t", "team_name": "Alpha", "player": "X"}]
        self.run_quietly(batch, state)
        self.assertEqual(self.sent[0]["key"], batch[4]["key"])

    def test_roundup_fits_discord_limit_and_counts_hidden(self) -> None:
        items = [_candidate(i, title=("Very long headline " * 12) + str(i)) for i in range(60)]
        payload, shown = engine.digest_payload("mlb-news", items)
        description = payload["embeds"][0]["description"]
        self.assertLessEqual(len(description), 4096)
        self.assertLess(shown, 60)
        self.assertIn(f"+{60 - shown} more not shown", description)

    def test_roundup_link_text_is_safe(self) -> None:
        item = _candidate(1, title="[Report] Player (OF) out")
        item["link"] = "https://example.test/a_(b)"
        payload, _ = engine.digest_payload("injury-report", [item])
        self.assertIn("[(Report) Player (OF) out](https://example.test/a_(b%29)", payload["embeds"][0]["description"])

    def test_roundup_keeps_dbl_roster_tag(self) -> None:
        item = _candidate(1)
        item["fantasy_owner"] = "Team Example"
        payload, _ = engine.digest_payload("injury-report", [item])
        self.assertIn("DBL roster:** Team Example", payload["embeds"][0]["description"])


class WireSourceConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import yaml
        cls.cfg = yaml.safe_load((HERE / "sources.yaml").read_text(encoding="utf-8"))

    def cand(self, source_id: str, key: str) -> dict:
        return {"key": key, "title": f"Episode {key} of a baseball podcast", "link": f"https://example.com/{key}",
                "channel": "media", "source_id": source_id, "tier": 2, "discovery_only": False}

    def test_new_baseline_first_source_posts_nothing_on_first_run(self) -> None:
        cfg = {"sources": [{"id": "pod_a", "baseline_first": True, "force_channel": "media"},
                           {"id": "news", "force_channel": "mlb-news"}]}
        state = {"initialized": True, "seen": []}
        first = engine.baseline_new_sources([self.cand("pod_a", "1"), self.cand("news", "2")], cfg, state)
        self.assertEqual([c["source_id"] for c in first], ["news"])
        self.assertEqual(state["known_sources"], ["pod_a"])
        later = engine.baseline_new_sources([self.cand("pod_a", "3")], cfg, state)
        self.assertEqual([c["key"] for c in later], ["3"])

    def test_every_live_source_starts_with_a_baseline(self) -> None:
        live = [s for s in self.cfg["sources"] if s.get("enabled") and not s.get("discovery_only")]
        self.assertTrue(live)
        for s in live:
            self.assertTrue(s.get("baseline_first"), s["id"])
            self.assertIn(s["type"], ("rss", "mlb_transactions"), s["id"])

    def test_podcasts_route_to_media(self) -> None:
        pods = [s for s in self.cfg["sources"] if s.get("role") == "podcast-episodes"]
        self.assertGreaterEqual(len(pods), 4)
        for s in pods:
            self.assertEqual(wire.route("Anything at all", s), "media")
        self.assertIn("media", engine.WEBHOOK_ENV)

    def test_the_official_log_is_the_transactions_source(self) -> None:
        ids = [s["id"] for s in self.cfg["sources"] if s.get("type") == "mlb_transactions" and s.get("enabled")]
        self.assertEqual(ids, [engine.STRUCTURED_SOURCE])
        self.assertEqual(engine.COLLECTOR_PRIMARY["mlb-transactions"], engine.STRUCTURED_SOURCE)
        for s in self.cfg["sources"]:
            self.assertIn(s.get("force_channel", "mlb-news"), engine.WEBHOOK_ENV, s["id"])


if __name__ == "__main__":
    unittest.main()
