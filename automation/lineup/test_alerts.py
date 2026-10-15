#!/usr/bin/env python3
"""Offline checks for Lineup Alerts.

Rosters and players: the MLB-shaped Fantrax variants in tests/mlb_fixtures.py
(daily lineup for Thu Apr 15, 2027). MLB games: the synthetic Week 3 schedule.
Thursday is a light day: BAL-CLE (1:10 PM ET), DET-MIN (2:10 PM), TB-TOR
(3:07 PM, Toronto's starter not announced) and a NYY-BOS doubleheader (1:05
and 6:10 PM). Checked at 3:00 PM ET.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "tests"))

import alerts  # noqa: E402
import mlb_fixtures as fx  # noqa: E402
from core import mlb  # noqa: E402

ET = ZoneInfo("America/New_York")
OWNER = "123456789012345678"
NOW = fx.et(2027, 4, 15, 15, 0)


class FakeFantrax:
    def __init__(self) -> None:
        self.calls = 0

    def league_info(self) -> dict:
        return {"leagueName": "PSBL Test League"}

    def rosters(self) -> dict:
        self.calls += 1
        return fx.rosters()

    def player_ids(self) -> dict:
        return fx.player_ids()


class NoFantrax:
    def __getattr__(self, name: str):
        raise AssertionError("Fantrax should not be read")


def league(owners: dict | None = None) -> dict:
    return {
        "league_id": "test", "timezone": "America/New_York", "season_label": "2027 TEST",
        "color": 0xBD3039, "owners": owners or {}, "lineup_alerts": {"webhook": "TEST_LINEUP_HOOK"},
    }


def playing(day=fx.THU) -> dict:
    return alerts.todays_games(mlb.fetch_schedule(day, day, fx.schedule_get), day)


def today_alerts(now: datetime = NOW) -> list[alerts.TeamAlert]:
    return alerts.find_alerts(fx.rosters(), fx.player_ids(), playing(), now)


class EligibilityTests(unittest.TestCase):
    def test_slots_follow_the_league_rules(self) -> None:
        self.assertTrue(alerts.can_fill("1B", {"1B", "OF"}))
        self.assertTrue(alerts.can_fill("OF", {"CF"}))
        self.assertTrue(alerts.can_fill("UT", {"SS"}))      # Fantrax "UT" is the UTIL slot
        self.assertTrue(alerts.can_fill("UTIL", {"C"}))
        self.assertFalse(alerts.can_fill("UT", {"SP"}))
        self.assertFalse(alerts.can_fill("2B", {"SS"}))
        self.assertTrue(alerts.can_fill("SP", {"SP"}))
        self.assertFalse(alerts.can_fill("SP", {"RP"}))

    def test_positions_combine_roster_and_directory(self) -> None:
        self.assertEqual(alerts.positions_of("1B", "1B,OF"), {"1B", "OF"})
        self.assertEqual(alerts.positions_of("UT", None), {"UTIL"})
        self.assertTrue(alerts.is_hitter_slot("UT") and not alerts.is_hitter_slot("SP"))

    def test_names(self) -> None:
        self.assertEqual(alerts.display_name("Hale, Marcus"), "Marcus Hale")


class FindAlertTests(unittest.TestCase):
    def test_only_the_affected_franchise(self) -> None:
        self.assertEqual([a.team_id for a in today_alerts()], ["t1"])

    def test_idle_hitters_and_bench_options(self) -> None:
        alert = today_alerts()[0]
        self.assertEqual([(e.player_id, e.slot) for e in alert.idle],
                         [("h_holt", "1B"), ("h_mori", "OF"), ("h_carrow", "UT")])
        # Archer (TOR, 3:07 PM) fits 1B, OF and UT; Ortiz (TB, 3:07 PM) only UT. Lane's and
        # Ruiz's clubs started at 1:10 and 1:05 (Ruiz's doubleheader locks him at game 1).
        self.assertEqual([e.player_id for e in alert.bench], ["b_archer", "b_ortiz"])
        # Ford (2B) is idle too, but no bench player can play 2B.
        self.assertNotIn("h_ford", [e.player_id for e in alert.idle])

    def test_starting_pitchers(self) -> None:
        alert = today_alerts()[0]
        # Finch's club is off; Pollard's club named someone else; Lowe starts; Toronto
        # has not named Thursday's starter, so its SP is never flagged.
        self.assertEqual([(e.player_id, why) for e, why in alert.resting],
                         [("p_finch", "no game today"), ("p_det", "Yuri Carver starts")])
        self.assertEqual([e.player_id for e in alert.starters], ["b_kerr"])

    def test_both_doubleheader_starters_named(self) -> None:
        # Test 2's Garrett Cole is not starting either NYY game; its only bench SP
        # (Cleveland's starter) already pitched at 1:10, so Test 2 gets no alert.
        cole = alerts.Entry("p_cole", "Garrett Cole", "SP", {"SP"}, "NYY", playing()["NYY"])
        self.assertEqual(alerts.starter_status(cole), "Alex Dorsey and Hank Ellery start")
        early = fx.et(2027, 4, 15, 12, 0)
        t2 = next(a for a in today_alerts(early) if a.team_id == "t2")
        self.assertEqual([e.player_id for e in t2.starters], ["b_hart"])
        self.assertEqual([e.player_id for e, _ in t2.resting], ["p_off", "p_cole"])

    def test_no_alert_once_bench_games_have_started(self) -> None:
        self.assertEqual(today_alerts(fx.et(2027, 4, 15, 19, 30)), [])

    def test_unknown_clubs_never_guess(self) -> None:
        alert = today_alerts()[0]
        everyone = [e.player_id for e in alert.idle + alert.bench + alert.starters] + [e.player_id for e, _ in alert.resting]
        self.assertNotIn("b_fa", everyone)
        self.assertNotIn("m_kid", everyone)   # MINORS
        self.assertNotIn("i_hurt", everyone)  # IR

    def test_postponed_game_means_no_game(self) -> None:
        wednesday = alerts.todays_games(mlb.fetch_schedule(fx.WED, fx.WED, fx.schedule_get), fx.WED)
        self.assertNotIn("NYY", wednesday)
        self.assertEqual(len(wednesday), 28)

    def test_no_games_today_means_no_alerts(self) -> None:
        self.assertEqual(alerts.find_alerts(fx.rosters(), fx.player_ids(), {}, NOW), [])


class OwnerTests(unittest.TestCase):
    def test_opt_in_by_team_name_or_id(self) -> None:
        alert = alerts.TeamAlert("t1", "Test 1")
        self.assertEqual(alerts.owner_for(alert, alerts.owner_ids(league({"test 1": OWNER}))), OWNER)
        self.assertEqual(alerts.owner_for(alert, alerts.owner_ids(league({"t1": OWNER}))), OWNER)
        self.assertEqual(alerts.owner_for(alert, alerts.owner_ids(league({"Test 2": OWNER}))), "")

    def test_invalid_ids_ignored(self) -> None:
        self.assertEqual(alerts.owner_ids(league({"Test 1": "@someone", "Test 2": ""})), {})


class RunTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state_path = Path(tmp.name) / "lineup_alerts.json"
        patcher = patch.object(alerts, "STATE_PATH", self.state_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.sent: list[tuple[str, dict]] = []

    def fake_send(self, secret: str, payload: dict):
        self.sent.append((secret, payload))
        return True, "delivered", "1"

    def run_alerts(self, mode: str, owners: dict | None, *, all_teams: bool = False,
                   now: datetime = NOW, fx_client=None, get=fx.schedule_get) -> tuple[int, str]:
        out = io.StringIO()
        with patch.object(alerts, "send_discord_webhook", self.fake_send), redirect_stdout(out):
            code = alerts.run(mode, all_teams, now=now, league=league(owners), fx=fx_client or FakeFantrax(),
                              mlb_get=get)
        return code, out.getvalue()

    def test_nobody_opted_in_reads_nothing(self) -> None:
        code, out = self.run_alerts("live", {}, fx_client=NoFantrax())
        self.assertEqual(code, 0)
        self.assertIn("no owners have opted in", out)
        self.assertEqual(self.sent, [])

    def test_one_request_for_today(self) -> None:
        get, calls = fx.recording(fx.schedule_get)
        self.run_alerts("preview", {"Test 1": OWNER}, get=get)
        self.assertEqual(calls, ["https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2027-04-15"
                                 "&endDate=2027-04-15&hydrate=probablePitcher"])

    def test_live_alert_mentions_only_the_owner(self) -> None:
        code, _ = self.run_alerts("live", {"Test 1": OWNER})
        self.assertEqual(code, 0)
        self.assertEqual(len(self.sent), 1)
        secret, payload = self.sent[0]
        self.assertEqual(secret, "TEST_LINEUP_HOOK")
        self.assertEqual(payload["content"], f"<@{OWNER}>")
        self.assertEqual(payload["allowed_mentions"], {"parse": [], "users": [OWNER]})
        embed = payload["embeds"][0]
        self.assertEqual(embed["title"], "Lineup Alert — Test 1")
        fields = {f["name"]: f["value"] for f in embed["fields"]}
        self.assertEqual(list(fields), ["In your lineup, no game today", "On your bench, playing today",
                                        "Your SP, not starting today", "Bench SP, starting today"])
        self.assertEqual(fields["In your lineup, no game today"],
                         "1B — Bryce Holt (PHI)\nOF — Kenji Mori (LAD)\nUT — Pete Carrow (NYM)")
        tor = int(datetime(2027, 4, 15, 19, 7, tzinfo=timezone.utc).timestamp())
        self.assertEqual(fields["On your bench, playing today"],
                         f"1B/OF — Tom Archer (TOR, <t:{tor}:t>)\nSS — Sam Ortiz (TB, <t:{tor}:t>)")
        self.assertEqual(fields["Your SP, not starting today"],
                         "SP — Arlo Finch (PHI): no game today\nSP — Reese Pollard (DET): Yuri Carver starts")
        self.assertEqual(fields["Bench SP, starting today"], f"SP — Vince Vance (TB, <t:{tor}:t>, at TOR)")
        self.assertEqual(payload["username"], "PSBL Competition Desk")
        self.assertEqual(embed["color"], 0xBD3039)
        self.assertEqual(embed["footer"]["text"], "LINEUP ALERT • FANTRAX + MLB SCHEDULE DATA")

    def test_same_alert_not_repeated_same_day(self) -> None:
        self.run_alerts("live", {"Test 1": OWNER})
        code, out = self.run_alerts("live", {"Test 1": OWNER}, now=NOW + timedelta(minutes=5))
        self.assertEqual((code, len(self.sent)), (0, 1))
        self.assertIn("already alerted today", out)
        state = json.loads(self.state_path.read_text())
        self.assertEqual(state["alerted"], ["t1"])
        self.assertEqual(alerts.alerted_today(state, fx.THU + timedelta(days=1)), set())

    def test_franchise_without_owner_is_not_alerted_live(self) -> None:
        code, out = self.run_alerts("live", {"Test 2": OWNER}, all_teams=True)
        self.assertEqual((code, self.sent), (0, []))
        self.assertIn("owner has not opted in", out)

    def test_test_mode_pings_nobody_and_saves_nothing(self) -> None:
        self.run_alerts("test", {"Test 1": OWNER})
        payload = self.sent[0][1]
        self.assertTrue(payload["embeds"][0]["title"].startswith("[TEST] "))
        self.assertEqual(payload["allowed_mentions"], {"parse": [], "users": []})
        self.assertFalse(self.state_path.exists())

    def test_preview_all_teams_without_owners(self) -> None:
        code, out = self.run_alerts("preview", {}, all_teams=True)
        self.assertEqual((code, self.sent), (0, []))
        self.assertIn("PREVIEW Test 1: 3 idle, 2 bench option(s), 2 SP not starting, 1 bench SP starting", out)
        self.assertNotIn('"content"', out)
        self.assertFalse(self.state_path.exists())

    def test_day_without_mlb_games(self) -> None:
        code, out = self.run_alerts("live", {"Test 1": OWNER}, get=lambda url: {"dates": []}, fx_client=NoFantrax())
        self.assertEqual((code, self.sent), (0, []))
        self.assertIn("no MLB regular-season games today", out)


if __name__ == "__main__":
    unittest.main()
