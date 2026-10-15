#!/usr/bin/env python3
"""Offline checks for the PSBL Morning Recap.

MLB data (tests/mlb_fixtures.py) is SYNTHETIC, hand-built in the shapes checked
live: Tuesday Apr 13, 2027 has 16 finals (a CHC-STL doubleheader with game 2 in
10 innings, KC-CWS called after 6 for rain, Marcus Hale and Kenji Mori with two
home runs each) and game content for four games; Wednesday has NYY-BOS
postponed. Fantrax: the MLB-shaped roster and player variants (Test 1 rosters
Hale, Theo Banks, Mori and Dante Ruiz; Test 2 rosters Luis Garcia).
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "tests"))

import mlb_fixtures as fx  # noqa: E402
import morning  # noqa: E402
from core import mlb  # noqa: E402

MORNING = fx.et(2027, 4, 14, 8, 35)   # covers Tuesday
LEAGUE = {"league_id": "test", "timezone": "America/New_York", "season_label": "2027 TEST", "color": 0xBD3039,
          "morning_recap": {"enabled": True, "post_time": "08:30", "include_home_run_reel": True}}
EMPTY_ROSTERS = {"period": 9, "rosters": {"t1": {"teamName": "Test 1", "rosterItems": []},
                                          "t2": {"teamName": "Test 2", "rosterItems": []}}}


class FakeFantrax:
    def __init__(self, rosters: dict | None = None, fail: bool = False, players: dict | Exception | None = None) -> None:
        self._rosters = fx.rosters() if rosters is None else rosters
        self.fail = fail
        self._players = fx.player_ids() if players is None else players
        self.player_reads = 0

    def league_info(self) -> dict:
        return {"leagueName": "PSBL Test League"}

    def rosters(self) -> dict:
        if self.fail:
            raise RuntimeError("Fantrax down")
        return self._rosters

    def player_ids(self) -> dict:
        self.player_reads += 1
        if isinstance(self._players, Exception):
            raise self._players
        return self._players


def quiet(fn, *args, **kwargs):
    out = io.StringIO()
    with redirect_stdout(out):
        result = fn(*args, **kwargs)
    return result, out.getvalue()


def night(day: date = fx.TUE) -> morning.Night:
    return morning.read_night(fx.schedule_get(mlb.schedule_url(day, day, mlb.SCORES)), day)


def media(games: list[mlb.Game]) -> dict[int, mlb.GameMedia]:
    return quiet(morning.read_media, games, fx.content_get)[0]


def index(rosters: dict | None = None):
    return morning.roster.build_index(rosters or fx.rosters(), mlb.normalize_directory(fx.player_ids()))


def by_label(games: list[mlb.Game]) -> dict[str, mlb.Game]:
    return {g.label: g for g in games}


def get(url: str):
    return fx.content_get(url) if url.endswith("/content") else fx.schedule_get(url)


class ParseTests(unittest.TestCase):
    def test_finals_in_start_order(self):
        tuesday = night()
        self.assertEqual(len(tuesday.finals), 16)
        self.assertEqual((tuesday.postponed, tuesday.unfinished), ([], 0))
        self.assertEqual(tuesday.finals[0].label, "CHC at STL (Game 1)")  # 2:15 PM
        wednesday = night(fx.WED)
        self.assertEqual((len(wednesday.finals), [g.label for g in wednesday.postponed]), (14, ["NYY at BOS"]))

    def test_other_day_or_changed_api(self):
        response = fx.schedule_get(mlb.schedule_url(fx.TUE, fx.TUE, mlb.SCORES))
        self.assertEqual(morning.read_night(response, fx.WED).finals, [])
        with self.assertRaises(ValueError):
            morning.read_night({"message": "error"}, fx.TUE)
        self.assertEqual(morning.read_night({"dates": []}, fx.TUE).finals, [])

    def test_unfinished_games_are_counted(self):
        def live(game: dict) -> None:
            if game["gamePk"] == fx.find_game(fx.TUE, "LAD", "SF")["gamePk"]:
                game["status"].update(abstractGameState="Live", codedGameState="I", detailedState="In Progress")
        playing = fx.edited_schedule(live)
        tuesday = morning.read_night(fx.schedule_response(mlb.schedule_url(fx.TUE, fx.TUE, mlb.SCORES), playing), fx.TUE)
        self.assertEqual((len(tuesday.finals), tuesday.unfinished), (15, 1))


class LineTests(unittest.TestCase):
    def setUp(self):
        self.games = by_label(night().finals)
        self.media = media(night().finals)

    def line(self, label: str) -> str:
        game = self.games[label]
        return morning.game_line(game, self.media[game.game_pk])

    def test_winner_pitchers_and_links(self):
        self.assertEqual(self.line("NYY at BOS"),
                         "**NYY 6**, BOS 4 · W: Cole · L: Mosley · S: Barlow"
                         " · [Recap](https://www.mlb.com/news/hale-homers-twice-as-yankees-top-red-sox)"
                         " · [Condensed](https://www.mlb.com/video/condensed-game-nyy-bos-4-13-27)")

    def test_doubleheader_extra_innings_and_called_games(self):
        self.assertEqual(self.line("CHC at STL (Game 2)"),
                         "**CHC 2**, STL 1 (game 2, 10 inn.) · W: Quill · L: Quill"
                         " · [Recap](https://www.mlb.com/video/cubs-walk-it-off-in-the-10th)"
                         " · [Condensed](https://www.mlb.com/video/condensed-game-chc-stl-game-2-4-13-27)")
        self.assertEqual(self.line("KC at CWS"), "**KC 3**, CWS 1 (6 inn., rain) · W: Irwin · L: Barlow")
        self.assertTrue(self.line("CHC at STL (Game 1)").startswith("**STL 5**, CHC 3 (game 1) · "))

    def test_postponed_lines(self):
        self.assertEqual(morning.postponed_line(night(fx.WED).postponed[0]),
                         "Postponed: NYY at BOS (rain), made up Thu Apr 15")

    def test_content_that_cannot_be_read_only_drops_links(self):
        def broken(url):
            raise RuntimeError("HTTP 503")
        found, out = quiet(morning.read_media, night().finals[:2], broken)
        self.assertTrue(all(m == mlb.GameMedia() for m in found.values()))
        self.assertIn("links unavailable", out)


class SummaryTests(unittest.TestCase):
    look = morning.Look("PSBL Test League", "2027 TEST", 0xBD3039)

    def test_one_message_for_a_full_night(self):
        tuesday = night()
        messages = morning.summary_messages(self.look, tuesday, media(tuesday.finals), fx.TUE, MORNING)
        self.assertEqual(len(messages), 1)
        body = messages[0]
        self.assertEqual(body["allowed_mentions"], {"parse": []})
        self.assertEqual(body["username"], "PSBL News Wire")
        embed = body["embeds"][0]
        self.assertEqual(embed["title"], "LAST NIGHT IN MLB — Tuesday, April 13")
        self.assertTrue(embed["description"].startswith("**PSBL Test League** • 2027 TEST\n*16 games final."))
        self.assertEqual(embed["footer"]["text"], "MORNING RECAP • MLB DATA")
        self.assertEqual(embed["color"], 0xBD3039)
        self.assertEqual(len(embed["description"].split("\n\n", 1)[1].splitlines()), 16)

    def test_postponed_games_close_the_list(self):
        wednesday = night(fx.WED)
        embed = morning.summary_messages(self.look, wednesday, {}, fx.WED, MORNING)[0]["embeds"][0]
        self.assertTrue(embed["description"].endswith("\nPostponed: NYY at BOS (rain), made up Thu Apr 15"))

    def test_long_nights_split_within_discord_limits(self):
        long_slug = "a-very-long-recap-slug-" * 6
        many = [mlb.Game(i + 1, fx.TUE, None, "NYY", "BOS", state="F", abstract="Final", away_score=1, home_score=4,
                         innings=10, winner=mlb.Person(1, "Some Pitcher"), loser=mlb.Person(2, "Other Pitcher"))
                for i in range(40)]
        links = {g.game_pk: mlb.GameMedia(recap=f"https://www.mlb.com/news/{long_slug}{g.game_pk}",
                                          condensed=f"https://www.mlb.com/video/c-{long_slug}{g.game_pk}") for g in many}
        messages = morning.summary_messages(self.look, morning.Night(many, [], 0), links, fx.TUE, MORNING)
        embeds = [e for m in messages for e in m["embeds"]]
        self.assertGreater(len(embeds), 1)
        for message in messages:
            self.assertLessEqual(sum(morning.embed_size(e) for e in message["embeds"]), morning.EMBED_TOTAL_LIMIT)
            self.assertLessEqual(len(message["embeds"]), morning.MAX_EMBEDS)
        for embed in embeds:
            self.assertLessEqual(len(embed["description"]), morning.DESCRIPTION_LIMIT)
        self.assertTrue(embeds[1]["title"].endswith("(continued)"))
        self.assertEqual([("footer" in e) for e in embeds], [False] * (len(embeds) - 1) + [True])
        text = "\n".join(e["description"] for e in embeds)
        for game in many:
            self.assertEqual(text.count(f"c-{long_slug}{game.game_pk})"), 1)

    def test_postseason_nights_say_so(self):
        game = mlb.Game(1, fx.TUE, None, "LAD", "NYY", game_type="W", state="F", abstract="Final",
                        away_score=2, home_score=3, innings=11)
        embed = morning.summary_messages(self.look, morning.Night([game], [], 0), {}, fx.TUE, MORNING)[0]["embeds"][0]
        self.assertIn("*1 postseason game final.", embed["description"])
        self.assertIn("**NYY 3**, LAD 2 (11 inn.)", embed["description"])


class ReelTests(unittest.TestCase):
    look = morning.Look("PSBL Test League", "2027 TEST", 0xBD3039)

    def reel(self):
        finals = night().finals
        return morning.build_reel(finals, media(finals), index())

    def test_grouped_by_franchise_with_clips(self):
        reel = self.reel()
        values = {f.name: morning.franchise_value(f) for f in reel.franchises.values()}
        self.assertEqual(sorted(values), ["Test 1", "Test 2"])
        # Most home runs first, then full name.
        self.assertEqual(values["Test 1"].split("\n"), [
            "Mori (LAD) — 2 HR [▶](https://www.mlb.com/video/kenji-mori-s-solo-homer-5)"
            " [▶](https://www.mlb.com/video/kenji-mori-s-three-run-homer-6)",
            "Hale (NYY) — 2 HR [▶](https://www.mlb.com/video/marcus-hale-s-solo-home-run-3)"
            " [▶](https://www.mlb.com/video/marcus-hale-s-two-run-home-run-4)",
            "Ruiz (BOS) — HR [▶](https://www.mlb.com/video/dante-ruiz-s-two-run-homer-2)",  # a MIA player shares the name
            "Banks (NYY) — HR [▶](https://www.mlb.com/video/theo-banks-s-solo-homer-1)",
        ])
        # WSN in Fantrax is WSH in MLB data; NYM-WSH has no clips, so no link.
        self.assertEqual(values["Test 2"], "Garcia (WSH) — HR")
        # Jonah Pike (STL, two homers) is not rostered.
        self.assertNotIn("Pike", json.dumps(values))

    def test_reel_message(self):
        messages = morning.reel_messages(self.look, self.reel(), MORNING)
        self.assertEqual(len(messages), 1)
        embed = messages[0]["embeds"][0]
        self.assertEqual(embed["title"], "THE PSBL HOME RUN REEL")
        self.assertEqual([f["name"] for f in embed["fields"]], ["Test 1", "Test 2"])  # most home runs first
        self.assertEqual(embed["footer"]["text"], "MORNING RECAP • MLB AND FANTRAX DATA")
        self.assertEqual(messages[0]["allowed_mentions"], {"parse": []})
        self.assertNotIn("<@", json.dumps(messages))

    def test_omitted_when_nobody_is_rostered(self):
        client = FakeFantrax(EMPTY_ROSTERS)
        idx, out = quiet(morning.load_index, client)
        self.assertIsNone(idx)
        self.assertIn("no players on PSBL rosters", out)
        self.assertEqual(client.player_reads, 0)
        reel = morning.build_reel(night().finals, {}, idx)
        self.assertTrue(reel.empty)
        self.assertEqual(morning.reel_messages(self.look, reel, MORNING), [])

    def test_fantrax_failure_is_not_empty_rosters(self):
        for client in (FakeFantrax(fail=True), FakeFantrax({}), FakeFantrax(players=RuntimeError("HTTP 502")),
                       FakeFantrax(players={})):
            with self.assertRaises(morning.RosterReadError):
                quiet(morning.load_index, client)

    def test_large_reels_split_within_discord_limits(self):
        reel = morning.Reel()
        for f in range(20):
            franchise = morning.Franchise(f"Franchise {f:02d}")
            for p in range(8):
                franchise.lines[f * 100 + p] = morning.ReelLine(f"Player{p}", f"First Player{p}", "NYY",
                                                                clips=["https://www.mlb.com/video/" + "x" * 80] * 2)
            reel.franchises[str(f)] = franchise
        messages = morning.reel_messages(self.look, reel, MORNING)
        self.assertGreater(len(messages), 1)
        names = []
        for message in messages:
            self.assertLessEqual(sum(morning.embed_size(e) for e in message["embeds"]), morning.EMBED_TOTAL_LIMIT)
            for embed in message["embeds"]:
                self.assertLessEqual(len(embed["fields"]), morning.MAX_FIELDS)
                for item in embed["fields"]:
                    self.assertLessEqual(len(item["value"]), morning.FIELD_LIMIT)
                    names.append(item["name"])
        self.assertEqual(len(names), 20)

    def test_first_name_variants_match_carefully(self):
        players = {"m1": {"fantraxId": "m1", "name": "Harris, Michael", "position": "OF", "team": "ATL"},
                   "g1": {"fantraxId": "g1", "name": "Garver, Mitchell", "position": "C", "team": "SEA"},
                   "s1": {"fantraxId": "s1", "name": "Smith, John", "position": "C", "team": "SEA"},
                   "h1": {"fantraxId": "h1", "name": "Garcia, Luis", "position": "2B", "team": "WSH"},
                   "h2": {"fantraxId": "h2", "name": "Garcia, Luisangel", "position": "SS", "team": "WSH"}}
        rosters = {"rosters": {"t": {"teamName": "Test 1", "rosterItems": [
            {"id": "m1"}, {"id": "g1"}, {"id": "s1"}, {"id": "h1"}]}}}
        matcher = morning.Matcher(morning.roster.build_index(rosters, players))
        self.assertEqual(matcher.match("Mitch Garver", "SEA").player_id, "g1")     # same club, "mit" = "mit"
        self.assertIsNone(matcher.match("Mitch Garver", "NYM"))                    # other club
        self.assertIsNone(matcher.match("Mike Harris", "ATL"))                     # "mik" is not "mic"
        self.assertEqual(matcher.match("Michael Harris II", "ATL").player_id, "m1")  # suffix ignored
        self.assertIsNone(matcher.match("Jack Smith", "SEA"))                       # different first name
        self.assertEqual(matcher.match("Luis Garcia", "WSH").player_id, "h1")     # exact
        self.assertIsNone(matcher.match("Lui Garcia", "WSH"))                      # could be either

    def test_clips_stop_at_the_home_runs_hit(self):
        game = by_label(night().finals)["NYY at BOS"]
        reel = morning.build_reel([game], media([game]), index())
        hale = reel.franchises["t1"].lines[900001]
        self.assertEqual(len(hale.clips), 2)  # the two-homer-game clip is not a third homer


class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "morning_recap.json"
        self.patch = patch.object(morning, "STATE_PATH", self.state)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def run_mode(self, mode="live", *, now=MORNING, league=LEAGUE, client=None, getter=get, fail_on=None,
                 day=None):
        """Run with fake MLB and Discord; returns (code, output, posted bodies)."""
        posted, fetched = [], []

        def fake_send(secret, body):
            self.assertEqual(secret, "LEAGUE_WEBHOOK_MEDIA")
            if fail_on is not None and fail_on(body, len(posted)):
                return False, "Discord returned 500", None
            posted.append(body)
            return True, "delivered", str(len(posted))

        def fetch(url):
            fetched.append(url)
            return getter(url)

        with patch.object(morning, "send_discord_webhook", fake_send):
            code, out = quiet(morning.run, mode, now=now, league=league, fx=client or FakeFantrax(), get=fetch,
                              night=day)
        self.fetched = fetched
        return code, out, posted

    @staticmethod
    def titles(posted):
        return [body["embeds"][0]["title"] for body in posted]

    def test_posts_everything_once(self):
        code, out, posted = self.run_mode()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.titles(posted), ["LAST NIGHT IN MLB — Tuesday, April 13", "THE PSBL HOME RUN REEL"])
        self.assertEqual(self.fetched[0], "https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2027-04-13"
                                          "&endDate=2027-04-13&hydrate=linescore,decisions,scoringplays")
        self.assertEqual(len(self.fetched), 1 + 16)  # the schedule, then each final's content
        saved = json.loads(self.state.read_text())["dates"]["2027-04-13"]
        self.assertEqual((saved["summary"], saved["reel"], saved["complete"]), (1, 1, True))

        later = fx.et(2027, 4, 14, 11, 0)
        code, out, posted = self.run_mode(now=later)
        self.assertEqual((code, posted), (0, []))
        self.assertIn("already posted", out)

    def test_failed_post_is_retried_without_repeats(self):
        fail_reel = lambda body, n: body["embeds"][0]["title"] == "THE PSBL HOME RUN REEL"  # noqa: E731
        code, out, posted = self.run_mode(fail_on=fail_reel)
        self.assertEqual(code, 1)
        self.assertIn("retried next run", out)
        self.assertEqual(len(posted), 1)
        saved = json.loads(self.state.read_text())["dates"]["2027-04-13"]
        self.assertEqual((saved["summary"], saved.get("reel"), saved.get("complete")), (1, None, None))

        code, _, posted = self.run_mode()
        self.assertEqual(code, 0)
        self.assertEqual(self.titles(posted), ["THE PSBL HOME RUN REEL"])

    def test_fantrax_outage_posts_the_scores_and_retries_the_reel(self):
        code, out, posted = self.run_mode(client=FakeFantrax(fail=True))
        self.assertEqual(code, 1)
        self.assertIn("the Home Run Reel will be retried next run", out)
        self.assertEqual(self.titles(posted), ["LAST NIGHT IN MLB — Tuesday, April 13"])
        # Still down on the first retry: nothing is reposted, still failing.
        code, _, posted = self.run_mode(client=FakeFantrax(fail=True))
        self.assertEqual((code, posted), (1, []))
        code, _, posted = self.run_mode()
        self.assertEqual(code, 0)
        self.assertEqual(self.titles(posted), ["THE PSBL HOME RUN REEL"])
        saved = json.loads(self.state.read_text())["dates"]["2027-04-13"]
        self.assertEqual((saved["reel"], saved["complete"]), (1, True))

    def test_content_outage_still_posts_without_links(self):
        def no_content(url):
            if url.endswith("/content"):
                raise RuntimeError("HTTP 503")
            return fx.schedule_get(url)
        code, out, posted = self.run_mode(getter=no_content)
        self.assertEqual(code, 0)
        self.assertNotIn("[Recap]", json.dumps(posted))
        self.assertNotIn("[▶]", json.dumps(posted, ensure_ascii=False))
        self.assertIn("Hale (NYY) — 2 HR", json.dumps(posted, ensure_ascii=False))

    def test_empty_rosters_post_no_reel(self):
        client = FakeFantrax(EMPTY_ROSTERS)
        code, _, posted = self.run_mode(client=client)
        self.assertEqual(code, 0)
        self.assertEqual(self.titles(posted), ["LAST NIGHT IN MLB — Tuesday, April 13"])
        self.assertEqual(client.player_reads, 0)

    def test_reel_can_be_turned_off(self):
        league = {**LEAGUE, "morning_recap": {**LEAGUE["morning_recap"], "include_home_run_reel": False}}
        client = FakeFantrax()
        code, _, posted = self.run_mode(league=league, client=client)
        self.assertEqual((code, len(posted)), (0, 1))
        self.assertEqual(client.player_reads, 0)

    def test_nothing_on_days_without_finals(self):
        for answer in ({"dates": []}, fx.schedule_response(mlb.schedule_url(fx.FRI, fx.FRI, mlb.SCORES))):
            code, out, posted = self.run_mode(getter=lambda url, a=answer: a)
            self.assertEqual((code, posted), (0, []))
            self.assertIn("no final MLB games", out)
            self.assertFalse(self.state.exists())

    def test_waits_for_post_time_and_respects_enabled(self):
        code, out, posted = self.run_mode(now=fx.et(2027, 4, 14, 7, 0))
        self.assertEqual((code, posted), (0, []))
        self.assertIn("before 08:30", out)
        off = {**LEAGUE, "morning_recap": {**LEAGUE["morning_recap"], "enabled": False}}
        code, out, posted = self.run_mode(league=off)
        self.assertEqual((code, posted), (0, []))
        self.assertIn("enabled is false", out)

    def test_live_never_covers_a_day_still_in_progress(self):
        code, out, posted = self.run_mode(day=date(2027, 4, 14))
        self.assertEqual((code, posted), (0, []))
        self.assertIn("not over yet", out)

    def test_postponed_game_on_the_morning_after(self):
        code, _, posted = self.run_mode(now=fx.et(2027, 4, 15, 8, 40))
        self.assertEqual(code, 0)
        self.assertIn("Postponed: NYY at BOS (rain), made up Thu Apr 15", posted[0]["embeds"][0]["description"])
        self.assertEqual(self.titles(posted), ["LAST NIGHT IN MLB — Wednesday, April 14"])  # nobody rostered homered

    def test_preview_and_test_modes_never_save_state(self):
        code, out, posted = self.run_mode("preview")
        self.assertEqual((code, posted), (0, []))
        self.assertIn('"LAST NIGHT IN MLB — Tuesday, April 13"', out)
        code, _, posted = self.run_mode("test")
        self.assertEqual(code, 0)
        self.assertEqual(len(posted), 2)
        self.assertTrue(all(t.startswith("[TEST] ") for t in self.titles(posted)))
        self.assertFalse(self.state.exists())

    def test_state_keeps_recent_dates_only(self):
        old = {f"2026-0{m}-{d:02d}": {"complete": True} for m in (7, 8) for d in range(1, 31)}
        self.state.write_text(json.dumps({"dates": old}))
        self.run_mode()
        dates = json.loads(self.state.read_text())["dates"]
        self.assertEqual(len(dates), morning.KEEP_DATES)
        self.assertIn("2027-04-13", dates)


class ConfigTests(unittest.TestCase):
    def test_league_yaml_section(self):
        cfg = yaml.safe_load((HERE.parent / "league.yaml").read_text(encoding="utf-8"))
        section = cfg["morning_recap"]
        self.assertTrue(set(section) >= {"enabled", "post_time", "include_home_run_reel"})
        self.assertEqual(section.get("webhook", morning.DEFAULT_WEBHOOK), "LEAGUE_WEBHOOK_MEDIA")
        morning._clock(section["post_time"], morning.DEFAULT_POST_TIME)

    def test_scheduled_and_monitored(self):
        repo = HERE.parents[1]
        schedule = yaml.safe_load((HERE.parent / "scheduler" / "schedule.yaml").read_text(encoding="utf-8"))
        job = next(j for j in schedule["jobs"] if j["id"] == "morning-recap")
        self.assertEqual((job["workflow"], job["daily_at"]), ("league-morning-recap.yml", ["08:30"]))
        self.assertNotIn("phases", job)  # all year: the MLB postseason runs past the PSBL season
        health = yaml.safe_load((HERE.parent / "health" / "health_config.yaml").read_text(encoding="utf-8"))
        self.assertIn("league-morning-recap.yml", [w["file"] for w in health["workflows"]])
        workflow = (repo / ".github" / "workflows" / "league-morning-recap.yml").read_text(encoding="utf-8")
        self.assertIn("LEAGUE_WEBHOOK_MEDIA: ${{ secrets.LEAGUE_WEBHOOK_MEDIA }}", workflow)
        self.assertIn("automation/media/state/morning_recap.json", workflow)
        self.assertIn("python automation/media/morning.py", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=1)
