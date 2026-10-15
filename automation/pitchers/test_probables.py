#!/usr/bin/env python3
"""Offline checks for Probable Pitchers.

MLB: the synthetic Week 3 schedule (tests/mlb_fixtures.py). Thursday Apr 15,
2027 has five games: a NYY-BOS split doubleheader (1:05 and 6:10 PM ET),
BAL-CLE, DET-MIN and TB-TOR (Toronto's starter not announced). Wednesday has
NYY-BOS postponed. Fantrax: the MLB-shaped roster and player variants, where
Test 1 rosters Corbin Lowe (BAL) and Vince Vance (TB) and Test 2 rosters Jake
Ashby (CLE).
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "tests"))

import mlb_fixtures as fx  # noqa: E402
import probables  # noqa: E402
from core import mlb  # noqa: E402

MORNING = fx.et(2027, 4, 15, 9, 30)
LEAGUE = {"league_id": "test", "timezone": "America/New_York", "season_label": "2027 TEST", "color": 0xBD3039,
          "probable_pitchers": {"webhook": "LEAGUE_WEBHOOK_GAME_DAY", "post_from": "09:00"}}


class FakeFantrax:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def league_info(self) -> dict:
        return {"leagueName": "PSBL Test League"}

    def rosters(self) -> dict:
        if self.fail:
            raise RuntimeError("Fantrax down")
        return fx.rosters()

    def player_ids(self) -> dict:
        return fx.player_ids()


def quiet(fn, *args, **kwargs):
    out = io.StringIO()
    with redirect_stdout(out):
        result = fn(*args, **kwargs)
    return result, out.getvalue()


def games(day=fx.THU, master: dict | None = None) -> list[mlb.Game]:
    return probables.todays_games(
        mlb.fetch_schedule(day, day, lambda url: fx.schedule_response(url, master)), day)


def tags(found: list[mlb.Game]) -> dict[int, str]:
    index, _ = quiet(probables.load_index, FakeFantrax())
    return probables.owners(found, index)


class ScheduleTests(unittest.TestCase):
    def test_todays_games_in_start_order(self):
        found = games()
        self.assertEqual([g.label for g in found], ["NYY at BOS (Game 1)", "BAL at CLE", "DET at MIN", "TB at TOR",
                                                    "NYY at BOS (Game 2)"])
        self.assertEqual(probables.announced(found), (9, 10))

    def test_postponed_games_are_listed_but_not_counted(self):
        wednesday = games(fx.WED)
        self.assertEqual(len(wednesday), 15)
        self.assertEqual(probables.announced(wednesday), (28, 28))
        ppd = next(g for g in wednesday if g.postponed)
        self.assertEqual(probables.game_value(ppd, {}, MORNING), "Postponed (Rain), made up Thu Apr 15")

    def test_spring_training_is_left_out(self):
        spring = fx.edited_schedule(lambda game: game.update(gameType="S"))
        self.assertEqual(games(master=spring), [])


class TagTests(unittest.TestCase):
    def test_rostered_starters_are_tagged(self):
        found = games()
        named = {p.name: team for g in found for t in g.teams if (p := g.probable(t)) and p.player_id in tags(found)
                 for team in [tags(found)[p.player_id]]}
        self.assertEqual(named, {"Corbin Lowe": "Test 1", "Jake Ashby": "Test 2", "Vince Vance": "Test 1"})

    def test_fantrax_failure_means_no_tags(self):
        index, out = quiet(probables.load_index, FakeFantrax(fail=True))
        self.assertIsNone(index)
        self.assertIn("posting without PSBL tags", out)
        self.assertEqual(probables.owners(games(), None), {})


class PayloadTests(unittest.TestCase):
    def test_message_layout(self):
        found = games()
        ctx = probables.render.Context("PSBL Test League", "2027 TEST", 0xBD3039)
        body = probables.payload(ctx, found, fx.THU, tags(found), MORNING)
        embed = body["embeds"][0]
        self.assertEqual(embed["title"], "Probable Pitchers — Thursday, April 15")
        self.assertIn("**9 of 10 starters announced**", embed["description"])
        self.assertIn("[MLB.com](https://www.mlb.com/probable-pitchers/2027-04-15)", embed["description"])
        fields = {f["name"]: f["value"] for f in embed["fields"]}
        self.assertEqual(len(fields), 5)
        bal = int(datetime(2027, 4, 15, 17, 10, tzinfo=timezone.utc).timestamp())
        self.assertEqual(fields["BAL at CLE"], f"<t:{bal}:t>\n**BAL** Corbin Lowe • *Test 1*\n**CLE** Jake Ashby • *Test 2*")
        self.assertTrue(fields["TB at TOR"].endswith("**TB** Vince Vance • *Test 1*\n**TOR** Not announced"))
        self.assertIn("**NYY** Hank Ellery", fields["NYY at BOS (Game 2)"])
        self.assertEqual(embed["footer"]["text"], "PROBABLE PITCHERS • MLB DATA")
        self.assertEqual(body["allowed_mentions"], {"parse": []})
        self.assertEqual(body["username"], "PSBL Competition Desk")
        self.assertLess(len(json.dumps(embed)), 6000)

    def test_full_slate_fits_one_message(self):
        found = games(fx.SAT)  # 16 games with the doubleheader
        body = probables.payload(probables.render.Context("L", "S", 1), found, fx.SAT, {}, fx.et(2027, 4, 17, 9))
        embed = body["embeds"][0]
        self.assertEqual(len(embed["fields"]), 16)
        self.assertIn("After game 1", next(f["value"] for f in embed["fields"] if f["name"] == "TOR at NYY (Game 2)"))
        self.assertLess(len(json.dumps(embed, ensure_ascii=False)), 6000)

    def test_started_games_are_marked(self):
        found = games()
        value = probables.game_value(found[0], {}, fx.et(2027, 4, 15, 13, 30))
        self.assertIn("• under way", value.splitlines()[0])


class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "probable_pitchers.json"
        self.patch = patch.object(probables, "STATE_PATH", self.state)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def live(self, now, upsert_result=None, master=None, fantrax=None):
        calls = []

        def fake_upsert(secret, body, message_id):
            calls.append((secret, message_id, body))
            return upsert_result or (True, "delivered", message_id or "111", "edited" if message_id else "posted")

        with patch.object(probables, "upsert_discord_message", fake_upsert):
            code, out = quiet(probables.run, "live", now=now, league=LEAGUE, fx=fantrax or FakeFantrax(),
                              get=lambda url: fx.schedule_response(url, master))
        return code, out, calls

    def test_too_early_does_nothing(self):
        code, out, calls = self.live(fx.et(2027, 4, 15, 8, 0))
        self.assertEqual((code, calls), (0, []))
        self.assertIn("before 09:00", out)

    def test_one_request_for_today(self):
        get, urls = fx.recording(fx.schedule_get)
        quiet(probables.run, "preview", now=MORNING, league=LEAGUE, fx=FakeFantrax(), get=get)
        self.assertEqual(urls, ["https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2027-04-15"
                                "&endDate=2027-04-15&hydrate=probablePitcher"])

    def test_posts_then_edits_only_on_change(self):
        code, _, calls = self.live(MORNING)
        self.assertEqual(code, 0)
        self.assertEqual([c[:2] for c in calls], [("LEAGUE_WEBHOOK_GAME_DAY", None)])
        saved = json.loads(self.state.read_text())
        self.assertEqual((saved["date"], saved["message_id"]), ("2027-04-15", "111"))

        later = fx.et(2027, 4, 15, 11, 45)
        code, out, calls = self.live(later)
        self.assertEqual((code, calls), (0, []))
        self.assertIn("UNCHANGED", out)

        tor = fx.find_game(fx.THU, "TB", "TOR")["gamePk"]

        def name_toronto(game: dict) -> None:
            if game["gamePk"] == tor:
                game["teams"]["home"]["probablePitcher"] = {"id": 701419, "fullName": "Late Arrival"}
        code, out, calls = self.live(later, master=fx.edited_schedule(name_toronto))
        self.assertEqual([c[1] for c in calls], ["111"])  # same message, edited
        self.assertIn("EDITED", out)
        self.assertIn("**10 of 10 starters announced**", calls[0][2]["embeds"][0]["description"])

    def test_new_day_posts_a_new_message(self):
        self.state.write_text(json.dumps({"date": "2027-04-14", "message_id": "999", "fingerprint": "x"}))
        _, _, calls = self.live(MORNING)
        self.assertEqual(calls[0][1], None)

    def test_after_the_last_first_pitch_the_message_is_final(self):
        self.live(MORNING)
        code, out, calls = self.live(fx.et(2027, 4, 15, 18, 30))
        self.assertEqual((code, calls), (0, []))
        self.assertIn("every game has started", out)

    def test_failed_post_keeps_state(self):
        code, _, _ = self.live(MORNING, upsert_result=(False, "HTTP 500", None, "failed"))
        self.assertEqual(code, 1)
        self.assertFalse(self.state.exists())

    def test_fantrax_failure_still_posts_without_tags(self):
        code, out, calls = self.live(MORNING, fantrax=FakeFantrax(fail=True))
        self.assertEqual(code, 0)
        self.assertIn("posting without PSBL tags", out)
        self.assertNotIn("Test 1", json.dumps(calls[0][2]))

    def test_preview_and_test_modes_never_save_state(self):
        code, out = quiet(probables.run, "preview", now=MORNING, league=LEAGUE, fx=FakeFantrax(), get=fx.schedule_get)
        self.assertEqual(code, 0)
        self.assertIn('"Probable Pitchers', out)
        sent = []
        with patch.object(probables, "send_discord_webhook", lambda s, b: (sent.append(b), (True, "delivered", "1"))[1]):
            code, _ = quiet(probables.run, "test", now=MORNING, league=LEAGUE, fx=FakeFantrax(), get=fx.schedule_get)
        self.assertEqual(code, 0)
        self.assertTrue(sent[0]["embeds"][0]["title"].startswith("[TEST] "))
        self.assertFalse(self.state.exists())

    def test_no_games_today(self):
        code, out = quiet(probables.run, "live", now=MORNING, league=LEAGUE, fx=FakeFantrax(),
                          get=lambda url: {"dates": []})
        self.assertEqual(code, 0)
        self.assertIn("no games today", out)


class ConfigTests(unittest.TestCase):
    def test_league_yaml_section(self):
        cfg = yaml.safe_load((HERE.parent / "league.yaml").read_text(encoding="utf-8"))
        section = cfg["probable_pitchers"]
        self.assertEqual(section.get("webhook", probables.DEFAULT_WEBHOOK), "LEAGUE_WEBHOOK_GAME_DAY")
        probables._post_from(section)

    def test_scheduled_and_monitored(self):
        repo = HERE.parents[1]
        schedule = yaml.safe_load((HERE.parent / "scheduler" / "schedule.yaml").read_text(encoding="utf-8"))
        job = next(j for j in schedule["jobs"] if j["id"] == "probable-pitchers")
        self.assertEqual((job["workflow"], job["phases"]), ("league-probable-pitchers.yml", ["regular", "playoffs"]))
        self.assertGreaterEqual(min(job["daily_at"]), LEAGUE["probable_pitchers"]["post_from"])
        health = yaml.safe_load((HERE.parent / "health" / "health_config.yaml").read_text(encoding="utf-8"))
        self.assertIn("league-probable-pitchers.yml", [w["file"] for w in health["workflows"]])
        workflow = (repo / ".github" / "workflows" / "league-probable-pitchers.yml").read_text(encoding="utf-8")
        self.assertIn("LEAGUE_WEBHOOK_GAME_DAY: ${{ secrets.LEAGUE_WEBHOOK_GAME_DAY }}", workflow)
        self.assertIn("automation/pitchers/state/probable_pitchers.json", workflow)
        self.assertIn("python automation/pitchers/probables.py", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=1)
