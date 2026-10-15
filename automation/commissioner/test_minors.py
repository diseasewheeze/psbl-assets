#!/usr/bin/env python3
"""Offline checks for the minor-eligibility watch (MLB career at-bats and innings, Article VII)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import minors  # noqa: E402
from core import mlb_people as mp  # noqa: E402
from core import sport  # noqa: E402

AB, OUTS = sport.MINORS_MAX_AB, sport.MINORS_MAX_OUTS


def person(pid, name, pos, team_id, at_bats=None, outs=None, pitching_ab=0):
    """A /people entry hydrated with career stats, in MLB's shape (see fixtures/mlb_people_careers.json)."""
    stats = []
    if at_bats is not None:
        stats.append({"group": {"displayName": "hitting"}, "type": {"displayName": "career"},
                      "splits": [{"stat": {"atBats": at_bats, "gamesPlayed": 10}, "sport": {"id": 1}, "gameType": "R"}]})
    if outs is not None:
        stats.append({"group": {"displayName": "pitching"}, "type": {"displayName": "career"},
                      "splits": [{"stat": {"outs": outs, "inningsPitched": mp.innings_text(outs), "atBats": pitching_ab},
                                  "sport": {"id": 1}, "gameType": "R"}]})
    row = {"id": pid, "fullName": name, "active": True, "primaryPosition": {"abbreviation": pos},
           "currentTeam": {"id": team_id}}
    if stats:
        row["stats"] = stats
    return row


class FakeMlb:
    """Serves MLB search and career totals; ``people`` can be changed between runs."""

    def __init__(self):
        self.people = {
            1: person(1, "Veteran Slugger", "1B", 118, at_bats=4000),
            2: person(2, "Young Hitter", "SS", 118, at_bats=AB - 10),
            # A reliever: 120 at-bats faced as a pitcher must not count as at-bats.
            3: person(3, "Relief Arm", "P", 118, outs=OUTS - 1, pitching_ab=120),
            4: person(4, "Never Called Up", "SS", 118),
        }
        self.searches = []

    def fetch(self, url, params):
        if url.endswith("/people/search"):
            self.searches.append(params["names"])
            q = mp.norm_name(params["names"])
            return {"people": [p for p in self.people.values() if mp.norm_name(p["fullName"]) == q]}
        if url.endswith("/people"):
            ids = [int(x) for x in params["personIds"].split(",")]
            return {"people": [self.people[i] for i in ids if i in self.people]}
        raise AssertionError(url)

    def api(self):
        return mp.MlbApi(self.fetch)


def rostered():
    return [
        {"fantraxId": "f1", "name": "Slugger, Veteran", "position": "1B", "mlb_team": "KC", "franchise": "Test 1", "slot": "ACTIVE"},
        {"fantraxId": "f2", "name": "Hitter, Young", "position": "SS", "mlb_team": "KC", "franchise": "Test 2", "slot": "MINORS"},
        {"fantraxId": "f3", "name": "Arm, Relief", "position": "RP", "mlb_team": "KC", "franchise": "Test 2", "slot": "MINORS"},
        {"fantraxId": "f4", "name": "Called Up, Never", "position": "SS", "mlb_team": "KC", "franchise": "Test 3", "slot": "MINORS"},
        {"fantraxId": "f9", "name": "Known, Nobody", "position": "C", "mlb_team": "KC", "franchise": "Test 3", "slot": "RESERVE"},
    ]


class RuleTests(unittest.TestCase):
    def test_limits_come_from_the_rules_module(self):
        self.assertTrue(minors.eligible(AB, OUTS))
        self.assertFalse(minors.eligible(AB + 1, 0))
        self.assertFalse(minors.eligible(0, OUTS + 1))
        self.assertEqual(minors.reasons(AB + 1, OUTS + 2),
                         [f"{AB + 1} career MLB at-bats (limit {AB})",
                          f"{mp.innings_text(OUTS + 2)} career MLB innings (limit {OUTS // 3})"])

    def test_name_handling(self):
        self.assertEqual(minors.fantrax_name("Witt Jr., Bobby"), ("Bobby", "Witt Jr."))
        self.assertEqual(minors.norm("José Ramírez Jr."), "joseramirez")


class EvaluateTests(unittest.TestCase):
    def test_evaluate_and_crossing(self):
        mlb = FakeMlb()
        cache = {}
        cur, unmatched = minors.evaluate(rostered(), mlb.api(), cache)
        self.assertEqual([u.split(" (")[0] for u in unmatched], ["Known, Nobody"])
        self.assertFalse(cur["f1"]["eligible"])
        self.assertTrue(cur["f2"]["eligible"])
        self.assertTrue(cur["f3"]["eligible"])           # pitching at-bats faced don't count
        self.assertEqual(cur["f3"]["at_bats"], 0)
        self.assertTrue(cur["f4"]["eligible"])           # no MLB stats at all
        self.assertEqual(cache["f2"], {"id": 2, "name": "Hitter, Young"})

        prev = {k: v["eligible"] for k, v in cur.items()}
        mlb.people[3] = person(3, "Relief Arm", "P", 118, outs=OUTS + 1)
        mlb.people[2] = person(2, "Young Hitter", "SS", 118, at_bats=AB + 5)
        searches = len(mlb.searches)
        cur2, _ = minors.evaluate(rostered(), mlb.api(), cache)
        # Matched ids are reused; only the unmatched player is searched again (full name, then last name).
        self.assertEqual(mlb.searches[searches:], ["Nobody Known", "Known"])
        found = minors.crossed(prev, cur2)
        self.assertEqual([p["name"] for p in found], ["Arm, Relief", "Hitter, Young"])
        self.assertIn(f"{AB + 5} career MLB at-bats (limit {AB})", minors.reason(found[1]))
        self.assertIn(f"{mp.innings_text(OUTS + 1)} career MLB innings", minors.reason(found[0]))

    def test_ineligible_before_is_never_realerted(self):
        cur = {"f1": {"eligible": False, "franchise": "x", "name": "a"}}
        self.assertEqual(minors.crossed({"f1": False}, cur), [])
        self.assertEqual(minors.crossed({}, cur), [])

    def test_alert_text(self):
        task = minors.build_task([{"name": "Hitter, Young", "mlbTeam": "KC", "franchise": "Test 2", "slot": "MINORS",
                                   "at_bats": AB + 5, "outs": 0}])
        self.assertEqual(task["title"], "Minor eligibility: 1 player is now ineligible")
        self.assertIn(f"Young Hitter (KC) on Test 2, in a minor slot now: {AB + 5} career MLB at-bats", task["items"][1])
        self.assertIn("(7.4)", task["items"][0])


class RunTests(unittest.TestCase):
    def _run(self, mlb, saved=None, mode="live", ok=True):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state = Path(tmp.name) / "minors.json"
        if saved is not None:
            state.write_text(json.dumps(saved))
        posts = []

        class FakeFantrax:
            def __init__(self, *a, **k):
                pass

        def fake_post(secret, payload):
            posts.append(payload)
            return ok, "delivered" if ok else "boom"

        with patch.object(minors, "STATE_PATH", state), patch.object(minors, "Fantrax", FakeFantrax), \
                patch.object(minors, "load_rostered", lambda fx: rostered()), \
                patch.object(minors, "post_discord_webhook", fake_post), patch("builtins.print"):
            code = minors.run(mode, mlb.api())
            code2 = minors.run(mode, mlb.api())
        return code, code2, posts, state

    def test_first_run_is_baseline_only(self):
        code, _, posts, state = self._run(FakeMlb())
        self.assertEqual((code, posts), (0, []))
        saved = json.loads(state.read_text())
        self.assertEqual(saved["sport"], "mlb")
        self.assertIn("eligible", saved)

    def test_state_from_before_baseball_is_not_a_baseline(self):
        mlb = FakeMlb()
        mlb.people[2] = person(2, "Young Hitter", "SS", 118, at_bats=AB + 5)
        # A state file saved before the move to baseball ("nhl" was its old cache key) has no "sport": "mlb".
        code, _, posts, state = self._run(mlb, {"eligible": {"f2": True}, "nhl": {}})
        self.assertEqual((code, posts), (0, []))
        self.assertEqual(json.loads(state.read_text())["eligible"]["f2"], False)

    def test_crossing_posts_one_alert_then_stays_quiet(self):
        mlb = FakeMlb()
        mlb.people[3] = person(3, "Relief Arm", "P", 118, outs=OUTS + 3)
        saved = {"sport": "mlb", "eligible": {"f1": False, "f2": True, "f3": True, "f4": True}}
        code, code2, posts, _ = self._run(mlb, saved)
        self.assertEqual((code, code2, len(posts)), (0, 0, 1))
        text = posts[0]["embeds"][0]["description"]
        self.assertIn("Relief Arm (KC) on Test 2, in a minor slot now", text)
        self.assertNotIn("•", text)

    def test_failed_delivery_is_retried_and_not_saved(self):
        mlb = FakeMlb()
        mlb.people[3] = person(3, "Relief Arm", "P", 118, outs=OUTS + 3)
        saved = {"sport": "mlb", "eligible": {"f1": False, "f2": True, "f3": True, "f4": True}}
        code, _, posts, state = self._run(mlb, saved, ok=False)
        self.assertEqual((code, len(posts)), (1, 2))
        self.assertEqual(json.loads(state.read_text())["eligible"], saved["eligible"])

    def test_preview_saves_nothing(self):
        _, _, posts, state = self._run(FakeMlb(), mode="preview")
        self.assertEqual(posts, [])
        self.assertFalse(state.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
