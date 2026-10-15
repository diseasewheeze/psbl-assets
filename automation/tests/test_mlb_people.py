#!/usr/bin/env python3
"""Offline checks for the MLB player client (automation/core/mlb_people.py), against fixtures in MLB's shape."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

AUTOMATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AUTOMATION))

from core import mlb_people as mp  # noqa: E402
from core import sport  # noqa: E402

FIXTURES = AUTOMATION / "tests" / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeFetch:
    """Serves fixtures by path; records every request."""

    def __init__(self, routes: dict[str, object] | None = None) -> None:
        self.routes = routes or {}
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url: str, params: dict) -> object:
        self.calls.append((url, params))
        path = url.replace(mp.BASE, "")
        route = self.routes.get(path)
        return route(params) if callable(route) else route


class NameAndTeamTests(unittest.TestCase):
    def test_names_match_across_fantrax_and_mlb(self) -> None:
        self.assertEqual(mp.norm_name("Witt Jr., Bobby"), mp.norm_name("Bobby Witt Jr."))
        self.assertEqual(mp.norm_name("Rodríguez, Johnathan"), "johnathan rodriguez")
        self.assertEqual(mp.split_name("Witt Jr., Bobby"), ("Bobby", "Witt Jr."))
        self.assertEqual(mp.split_name("Bobby Witt Jr."), ("Bobby", "Witt Jr."))
        self.assertEqual(mp.display_name("Ohtani, Shohei"), "Shohei Ohtani")

    def test_team_codes(self) -> None:
        self.assertEqual(len(mp.TEAMS), 30)
        self.assertEqual(set(mp.TEAMS.values()), set(mp.TEAM_NAMES))
        for alias, code in (("ARI", "AZ"), ("OAK", "ATH"), ("CHW", "CWS"), ("KCR", "KC"), ("WSN", "WSH"), ("nyy", "NYY")):
            self.assertEqual(mp.team_code(alias), code)
        self.assertEqual(mp.team_code(147), "NYY")
        self.assertEqual(mp.team_of({"id": 1994, "name": "ACL Rockies", "parentOrgId": 115}), "COL")
        self.assertEqual(mp.team_of({"id": 568, "name": "Norfolk Tides"}), "")

    def test_pitcher_or_hitter(self) -> None:
        self.assertTrue(mp.is_pitcher("SP"))
        self.assertTrue(mp.is_pitcher("P"))
        self.assertFalse(mp.is_pitcher("SS,2B"))
        self.assertIsNone(mp.is_pitcher("TWP"))
        self.assertIsNone(mp.is_pitcher(""))

    def test_innings(self) -> None:
        self.assertEqual(mp.outs_of({"inningsPitched": "614.1"}), 1843)
        self.assertEqual(mp.outs_of({"outs": 18, "inningsPitched": "9.9"}), 18)
        self.assertEqual(mp.innings_text(152), "50.2")


class CareerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fetch = FakeFetch({"/people": fixture("mlb_people_careers.json")})
        self.api = mp.MlbApi(self.fetch)

    def test_career_at_bats_come_from_hitting_only(self) -> None:
        careers = self.api.careers([677951, 660271, 804606, 822298])
        person, ohtani = careers[660271]
        self.assertEqual((person.name, person.position, person.team), ("Shohei Ohtani", "TWP", "LAD"))
        # 4253 at-bats as a hitter; the pitching group's 2222 at-bats faced do not count.
        self.assertEqual((ohtani.at_bats, ohtani.outs, ohtani.innings), (4253, 1843, "614.1"))
        self.assertEqual(careers[677951][1].at_bats, 3049)
        self.assertEqual(careers[677951][1].outs, 0)

    def test_player_without_mlb_stats_has_zero_totals(self) -> None:
        person, career = self.api.careers([822298])[822298]
        self.assertEqual((career.at_bats, career.outs), (0, 0))
        self.assertEqual((person.team, person.level_team, person.debut), ("COL", "ACL Rockies", ""))

    def test_people_are_fetched_in_batches(self) -> None:
        ids = list(range(1, mp.PEOPLE_BATCH * 2 + 2))
        self.api.careers(ids)
        self.assertEqual(len(self.fetch.calls), 3)
        url, params = self.fetch.calls[0]
        self.assertEqual(url, f"{mp.BASE}/people")
        self.assertIn("type=[career]", params["hydrate"])
        self.assertEqual(len(params["personIds"].split(",")), mp.PEOPLE_BATCH)


class SeasonAndGameTests(unittest.TestCase):
    def test_traded_season_uses_the_combined_row(self) -> None:
        api = mp.MlbApi(FakeFetch({"/people": fixture("mlb_people_year_by_year.json")}))
        seasons = api.seasons([665742, 804606])
        soto = seasons[665742]
        self.assertEqual(sorted(soto), [2021, 2022])
        self.assertEqual(soto[2022]["hitting"]["atBats"], 524)       # 342 + 182, not 1048
        self.assertEqual(soto[2022]["hitting"]["homeRuns"], 27)
        self.assertNotIn("pitching", soto[2022])
        self.assertEqual(seasons[804606][2026]["hitting"]["gamesPlayed"], 80)

    def test_game_log_reads_both_groups_and_only_regular_season(self) -> None:
        fetch = FakeFetch({"/people/660271/stats": fixture("mlb_game_log_660271_2026.json")})
        lines = mp.MlbApi(fetch).game_log(660271, 2026)
        self.assertEqual(fetch.calls[0][1], {"stats": "gameLog", "group": "hitting,pitching", "season": 2026, "gameType": "R"})
        self.assertEqual(sorted((l.date.isoformat(), l.group) for l in lines),
                         [("2026-03-26", "hitting"), ("2026-03-31", "hitting"), ("2026-03-31", "pitching")])
        pitching = next(l for l in lines if l.group == "pitching")
        self.assertEqual((pitching.game_pk, pitching.team, pitching.opponent), (823969, "LAD", "SD"))
        self.assertEqual(sport.outs_recorded(pitching.stat), 18)


class RosterAndTransactionTests(unittest.TestCase):
    def test_40_man_roster_status_codes(self) -> None:
        roster = mp.MlbApi(FakeFetch({"/teams/118/roster": fixture("mlb_roster_40man_118.json")})).roster_40man(118)
        self.assertEqual([(r.name, r.status) for r in roster][:2], [("Alec Marsh", "D60"), ("Alex Lange", "A")])
        self.assertEqual({r.team for r in roster}, {"KC"})
        self.assertEqual({r.status for r in roster}, {"A", "D15", "D60", "RM"})

    def test_transactions(self) -> None:
        fetch = FakeFetch({"/transactions": fixture("mlb_transactions_2026-07-28.json")})
        moves = mp.MlbApi(fetch).transactions(date(2026, 7, 28), date(2026, 7, 29))
        self.assertEqual(fetch.calls[0][1], {"sportId": 1, "startDate": "2026-07-28", "endDate": "2026-07-29"})
        trade = [m for m in moves if m.type_code == "TR"]
        self.assertEqual(len(trade), 3)
        self.assertEqual({m.id for m in trade}, {933275})
        self.assertEqual(trade[0].mlb_teams, ["TEX", "LAA"])
        optioned = next(m for m in moves if m.type_code == "OPT")
        self.assertEqual(optioned.mlb_teams, ["PIT"])                 # Indianapolis is an affiliate
        twice = [m for m in moves if m.name == "Jesús Sánchez"]
        self.assertNotEqual(twice[0].id, twice[1].id)
        self.assertEqual(twice[0].key, twice[1].key)                   # the same move listed twice

    def test_a_changed_answer_is_an_error_not_a_quiet_day(self) -> None:
        api = mp.MlbApi(FakeFetch({"/transactions": {"message": "error"}}))
        with self.assertRaises(ValueError):
            api.transactions(date(2026, 7, 28), date(2026, 7, 28))

    def test_draft_prospects_empty_list(self) -> None:
        api = mp.MlbApi(FakeFetch({"/draft/prospects/2027": fixture("mlb_draft_prospects_2027.json")}))
        self.assertEqual(api.draft_prospects(2027), [])


class MatchTests(unittest.TestCase):
    def api(self, by_query: dict[str, list]) -> mp.MlbApi:
        return mp.MlbApi(FakeFetch({"/people/search": lambda params: {"people": by_query.get(params["names"], [])}}))

    def test_same_name_is_narrowed_by_team_and_position(self) -> None:
        people = fixture("mlb_people_search_will_smith.json")["people"]
        api = self.api({"Will Smith": people})
        self.assertEqual(mp.find_person(api, "Smith, Will", "LAD", "C").person.id, 669257)
        self.assertEqual(mp.find_person(api, "Smith, Will", "KC", "RP").person.id, 519293)
        # Without a team or position the only active Will Smith is the Dodgers catcher.
        self.assertEqual(mp.find_person(api, "Smith, Will").person.id, 669257)

    def test_ambiguous_names_are_not_guessed(self) -> None:
        twins = [{"id": 1, "fullName": "Luis Garcia", "active": True, "primaryPosition": {"abbreviation": "P"},
                  "currentTeam": {"id": 119}},
                 {"id": 2, "fullName": "Luis Garcia", "active": True, "primaryPosition": {"abbreviation": "P"},
                  "currentTeam": {"id": 135}}]
        api = self.api({"Luis Garcia": twins})
        match = mp.find_person(api, "Garcia, Luis", "", "RP")
        self.assertIsNone(match.person)
        self.assertEqual(len(match.candidates), 2)
        self.assertEqual(mp.find_person(api, "Garcia, Luis", "SD", "RP").person.id, 2)

    def test_nickname_needs_last_name_initial_and_team(self) -> None:
        zack = {"id": 7, "fullName": "Zack Gelof", "active": True, "primaryPosition": {"abbreviation": "2B"},
                "currentTeam": {"id": 133}}
        api = self.api({"Gelof": [zack]})
        self.assertEqual(mp.find_person(api, "Gelof, Zachary", "OAK", "2B").person.id, 7)
        self.assertIsNone(mp.find_person(api, "Gelof, Zachary", "", "2B").person)
        self.assertIsNone(mp.find_person(api, "Gelof, Michael", "ATH", "2B").person)


if __name__ == "__main__":
    unittest.main(verbosity=2)
