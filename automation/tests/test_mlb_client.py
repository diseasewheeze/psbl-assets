#!/usr/bin/env python3
"""Offline checks for the MLB Stats API reader (automation/core/mlb.py).

MLB data: the synthetic Week 3 schedule and Tuesday content fixtures (see
tests/mlb_fixtures.py), built in the shapes checked live in October 2026.
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import mlb_fixtures as fx  # noqa: E402
from core import mlb, season  # noqa: E402

ET = ZoneInfo("America/New_York")
P3 = season.period(fx.MLB_INFO, 3)  # Mon Apr 12 18:40 -> Mon Apr 19 11:09:59


def games(hydrate: str = mlb.SCORES) -> list[mlb.Game]:
    return mlb.parse_schedule(fx.schedule_response(mlb.schedule_url(fx.MON, date(2027, 4, 19), hydrate)))


def one(day: date, away: str, home: str, number: int = 1, found: list[mlb.Game] | None = None) -> mlb.Game:
    return next(g for g in (found or games()) if (g.day, g.away, g.home, g.game_number) == (day, away, home, number))


class TeamTests(unittest.TestCase):
    def test_thirty_clubs(self) -> None:
        self.assertEqual(len(mlb.CODES), 30)
        self.assertEqual(mlb.TEAMS[133], ("ATH", "Athletics"))

    def test_codes_from_any_spelling(self) -> None:
        for raw, code in (("NYY", "NYY"), ("nyy", "NYY"), ("ARI", "AZ"), ("CHW", "CWS"), ("WSN", "WSH"),
                          ("WAS", "WSH"), ("OAK", "ATH"), ("SDP", "SD"), ("TBR", "TB"), ("KCR", "KC"),
                          ("Chicago White Sox", "CWS"), ("athletics", "ATH")):
            self.assertEqual(mlb.team_code(raw), code, raw)
        for raw in ("FA", "", None, "(N/A)", "XYZ"):
            self.assertEqual(mlb.team_code(raw), "", raw)


class ScheduleTests(unittest.TestCase):
    def test_one_request_with_the_hydration(self) -> None:
        get, calls = fx.recording(fx.schedule_get)
        found = mlb.fetch_schedule(fx.TUE, fx.WED, get)
        self.assertEqual(calls, ["https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2027-04-13"
                                 "&endDate=2027-04-14&hydrate=probablePitcher"])
        self.assertEqual(len(found), 31)
        self.assertTrue(all(g.plays == () and g.winner is None for g in found))  # not asked for
        self.assertIsNotNone(one(fx.TUE, "NYY", "BOS", found=found).away_probable)

    def test_listing_fields(self) -> None:
        nyy = one(fx.TUE, "NYY", "BOS")
        self.assertEqual((nyy.game_type, nyy.state, nyy.abstract, nyy.detailed), ("R", "F", "Final", "Final"))
        self.assertEqual(nyy.start, datetime(2027, 4, 13, 23, 5, tzinfo=timezone.utc))
        self.assertEqual((nyy.away_name, nyy.home_name), ("New York Yankees", "Boston Red Sox"))
        self.assertEqual((nyy.away_score, nyy.home_score, nyy.innings, nyy.scheduled_innings), (6, 4, 9, 9))
        self.assertEqual(nyy.save.name, "Vince Barlow")
        self.assertIsNone(one(fx.TUE, "ATL", "PHI").save)  # MLB leaves "save" out when there was none
        self.assertTrue(nyy.final and nyy.played and not nyy.live)
        self.assertEqual(one(fx.FRI, "TOR", "NYY").state, "S")
        self.assertIsNone(one(fx.FRI, "TOR", "NYY").away_score)

    def test_postponed_game_is_listed_twice(self) -> None:
        # Live behaviour: the postponed listing keeps its gamePk and its officialDate already
        # shows the makeup date, so the day comes from the dates block it is listed under.
        found = games()
        ppd = one(fx.WED, "NYY", "BOS", found=found)
        makeup = one(fx.THU, "NYY", "BOS", 1, found)
        self.assertEqual(ppd.game_pk, makeup.game_pk)
        self.assertNotEqual(ppd.key, makeup.key)
        self.assertTrue(ppd.postponed and not ppd.played)
        self.assertEqual((ppd.reason, ppd.moved_to, makeup.makeup_of), ("Rain", fx.THU, fx.WED))
        self.assertEqual((makeup.double_header, makeup.game_number), ("S", 1))
        self.assertEqual(fx.find_game(fx.WED, "NYY", "BOS")["officialDate"], "2027-04-15")

    def test_late_game_stays_on_its_day_and_tbd_times(self) -> None:
        late = one(fx.SAT, "SD", "LAD")
        self.assertEqual(late.start, datetime(2027, 4, 18, 2, 10, tzinfo=timezone.utc))  # Sunday in UTC
        second = one(fx.SAT, "TOR", "NYY", 2)
        self.assertEqual((second.double_header, second.start), ("Y", None))  # startTimeTBD
        self.assertEqual(second.label, "TOR at NYY (Game 2)")

    def test_extra_innings_and_called_games(self) -> None:
        extra = one(fx.TUE, "CHC", "STL", 2)
        self.assertTrue(extra.extra_innings and not extra.shortened)
        self.assertEqual(extra.innings, 10)
        called = one(fx.TUE, "KC", "CWS")
        self.assertTrue(called.shortened and called.final)
        self.assertEqual((called.detailed, called.reason, called.innings), ("Completed Early", "Rain", 6))

    def test_error_bodies_and_empty_days(self) -> None:
        self.assertEqual(mlb.parse_schedule({"totalGames": 0, "dates": []}), [])
        for broken in ({}, {"message": "Internal error"}, {"dates": None}, [], None):
            with self.assertRaises(ValueError):
                mlb.parse_schedule(broken)
        bad = {"dates": [{"date": "2027-04-13", "games": [{"gamePk": 1, "teams": {}}, "x", {"teams": None}]}]}
        self.assertEqual(mlb.parse_schedule(bad), [])

    def test_games_on_a_day(self) -> None:
        thursday = mlb.games_on(games(), fx.THU)
        self.assertEqual(sorted(thursday), ["BAL", "BOS", "CLE", "DET", "MIN", "NYY", "TB", "TOR"])
        self.assertEqual([g.game_number for g in thursday["NYY"]], [1, 2])
        self.assertNotIn("NYY", mlb.games_on(games(), fx.WED))  # postponed


class PeriodTests(unittest.TestCase):
    def test_mid_day_boundaries(self) -> None:
        found = games()
        self.assertFalse(mlb.in_period(one(fx.MON, "NYY", "BOS", found=found), P3.start, P3.end, ET))  # 13:10
        self.assertTrue(mlb.in_period(one(fx.MON, "ATL", "PHI", found=found), P3.start, P3.end, ET))   # 18:45
        apr19 = [g for g in found if g.day == date(2027, 4, 19)]
        self.assertEqual(len(apr19), 2)
        self.assertFalse(any(mlb.in_period(g, P3.start, P3.end, ET) for g in apr19))  # 11:10 starts Week 4
        p4 = season.period(fx.MLB_INFO, 4)
        self.assertTrue(all(mlb.in_period(g, p4.start, p4.end, ET) for g in apr19))

    def test_whole_day_periods_keep_late_games(self) -> None:
        start = datetime(2027, 4, 12, 0, 0, tzinfo=ET).astimezone(timezone.utc)
        end = datetime(2027, 4, 17, 23, 59, 59, tzinfo=ET).astimezone(timezone.utc)
        late = one(fx.SAT, "SD", "LAD")  # 10:10 PM ET Saturday
        self.assertTrue(mlb.in_period(late, start, end, ET))
        self.assertFalse(mlb.in_period(one(fx.SUN, "TOR", "NYY"), start, end, ET))
        self.assertTrue(mlb.in_period(one(fx.MON, "NYY", "BOS"), start, end, ET))


class GridTests(unittest.TestCase):
    def grid(self) -> mlb.WeekGrid:
        return mlb.week_grid(games(mlb.PROBABLES), P3.start, P3.end, ET)

    def test_games_per_club(self) -> None:
        grid = self.grid()
        self.assertEqual(grid.total_games, 85)
        groups = dict(grid.by_count())
        self.assertEqual(groups[7], ["NYY", "TOR"])
        self.assertEqual(len(groups[6]), 16)
        self.assertEqual(groups[5], ["ATH", "AZ", "COL", "CWS", "HOU", "KC", "LAA", "MIA", "PIT", "SD", "SEA", "TEX"])
        self.assertEqual(sum(len(t) for t in groups.values()), 30)

    def test_days_doubleheaders_and_postponements(self) -> None:
        grid = self.grid()
        self.assertEqual([(d.day, n, g) for d, n, g in grid.days], [(12, 8, 4), (13, 30, 16), (14, 28, 14),
                                                                      (15, 8, 5), (16, 30, 15), (17, 30, 16),
                                                                      (18, 30, 15)])
        self.assertEqual([d.day for d, _, _ in grid.light_days], [12, 15])
        self.assertEqual([d.day for d, _, _ in grid.heavy_days], [13, 16, 17, 18])
        self.assertEqual([(d.day, len(t)) for d, t in grid.off_days], [(12, 22), (14, 2), (15, 22)])
        self.assertEqual(dict(grid.off_days)[fx.WED], ["BOS", "NYY"])
        self.assertEqual([(d.day, g.away, g.home) for d, g in grid.doubleheaders],
                         [(13, "CHC", "STL"), (15, "NYY", "BOS"), (17, "TOR", "NYY")])
        self.assertEqual([(g.day.day, g.label, g.reason) for g in grid.postponed],
                         [(12, "CHC at STL", "Rain"), (14, "NYY at BOS", "Rain")])

    def test_two_start_pitchers_from_announced_probables(self) -> None:
        two = [(team, p.name, [d.day for d in days]) for team, p, days in self.grid().two_start]
        self.assertEqual(two, [("NYY", "Alex Dorsey", [15, 18]), ("NYY", "Garrett Cole", [13, 17]),
                               ("TOR", "Eli Dorsey", [14, 18]), ("TOR", "Xavier Coburn", [13, 17])])

    def test_clubs_without_games_are_listed(self) -> None:
        only = [g for g in games() if "SEA" not in g.teams]
        grid = mlb.week_grid(only, P3.start, P3.end, ET)
        self.assertEqual(dict(grid.by_count())[0], ["SEA"])


class HomeRunTests(unittest.TestCase):
    def test_multi_homer_games(self) -> None:
        nyy = one(fx.TUE, "NYY", "BOS")
        self.assertEqual({pid: len(p) for pid, p in mlb.home_runs(nyy).items()}, {900001: 2, 900002: 1, 900003: 1})
        multi = mlb.multi_homer_games(nyy)
        self.assertEqual([(m.batter.name, m.team, m.homers, m.order) for m in multi], [("Marcus Hale", "NYY", 2, 4)])
        self.assertEqual(mlb.multi_homer_games(nyy, 3), [])
        pike = mlb.multi_homer_games(one(fx.TUE, "CHC", "STL", 1))[0]
        self.assertEqual((pike.batter.name, pike.team, pike.game.opponent(pike.team)), ("Jonah Pike", "STL", "CHC"))


class ContentTests(unittest.TestCase):
    def media(self, away: str, home: str, number: int = 1) -> mlb.GameMedia:
        return mlb.fetch_content(one(fx.TUE, away, home, number).game_pk, fx.content_get)

    def test_recap_condensed_and_home_run_clips(self) -> None:
        media = self.media("NYY", "BOS")
        self.assertEqual(media.recap, "https://www.mlb.com/news/hale-homers-twice-as-yankees-top-red-sox")
        self.assertEqual(media.condensed, "https://www.mlb.com/video/condensed-game-nyy-bos-4-13-27")
        # His own clips, oldest first: the back-to-back clip names two batters and is skipped.
        self.assertEqual(media.home_run_clips(900001), [
            "https://www.mlb.com/video/marcus-hale-s-solo-home-run-3",
            "https://www.mlb.com/video/marcus-hale-s-two-run-home-run-4",
            "https://www.mlb.com/video/marcus-hale-s-two-homer-game"])
        self.assertEqual(media.home_run_clips(900002), ["https://www.mlb.com/video/theo-banks-s-solo-homer-1"])
        self.assertEqual(media.home_run_clips(123), [])

    def test_recap_video_when_there_is_no_story(self) -> None:
        media = self.media("CHC", "STL", 2)
        self.assertEqual(media.recap, "https://www.mlb.com/video/cubs-walk-it-off-in-the-10th")
        self.assertEqual(media.condensed, "https://www.mlb.com/video/condensed-game-chc-stl-game-2-4-13-27")

    def test_missing_content_and_odd_items(self) -> None:
        self.assertEqual(self.media("KC", "CWS"), mlb.GameMedia())
        self.assertEqual(mlb.parse_content(None), mlb.GameMedia())
        raw = {"highlights": {"highlights": {"items": [
            {"headline": "No slug", "keywordsAll": [{"type": "taxonomy", "value": "home-run"},
                                                     {"type": "player_id", "value": "5"}],
             "playbacks": [{"name": "mp4Avc", "url": "https://example.invalid/clip.mp4"}]},
            {"slug": "../evil", "keywordsAll": []}, "junk"]}}}
        media = mlb.parse_content(raw)
        self.assertEqual(media.home_run_clips(5), ["https://example.invalid/clip.mp4"])
        self.assertEqual(len(media.clips), 1)


class HelperTests(unittest.TestCase):
    def test_last_names(self) -> None:
        self.assertEqual(mlb.last_name("Daniel Lynch IV"), "Lynch")
        self.assertEqual(mlb.last_name("Elly De La Cruz"), "De La Cruz")
        self.assertEqual(mlb.last_name("Ichiro"), "Ichiro")
        self.assertEqual(mlb.last_name("Vladimir Guerrero Jr."), "Guerrero")

    def test_name_keys(self) -> None:
        self.assertEqual(mlb.name_key("Rodríguez, Julio"), mlb.name_key("Julio Rodriguez"))
        self.assertEqual(mlb.name_key("Vladimir Guerrero Jr."), "vladimir guerrero")
        self.assertEqual(mlb.name_key("Lynch IV, Daniel"), "daniel lynch")
        self.assertEqual(mlb.name_key(None), "")

    def test_cap_periods(self) -> None:
        self.assertEqual(season.calendar_weeks(season.period(fx.MLB_INFO, 1)), 2)   # Opening Night to Apr 5
        self.assertEqual(season.calendar_weeks(P3), 1)
        self.assertEqual(season.calendar_weeks(season.period(fx.MLB_INFO, 25)), 2)  # Championship
        self.assertEqual(P3.end - P3.start, timedelta(days=6, hours=16, minutes=29, seconds=59))


if __name__ == "__main__":
    unittest.main()
