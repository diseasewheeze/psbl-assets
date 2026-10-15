#!/usr/bin/env python3
"""Offline checks for the prospect board (MLB draft prospects)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import prospects  # noqa: E402
from core import mlb_people as mp  # noqa: E402
from core.league import load_league  # noqa: E402

FIXTURES = HERE.parent / "tests" / "fixtures"
TODAY = date(2027, 3, 3)


def expected_mentions() -> dict:
    """Alerts mention only the Commissioner set in league.yaml, or nobody when it is blank."""
    ping = str((load_league().get("commissioner_desk") or {}).get("ping_user_id") or "").strip()
    return {"users": [ping]} if ping else {"parse": []}


def prospect(i, rank=None, drafted=False):
    """One /draft/prospects entry in MLB's shape (the 2026 list, checked live 2026-10-15). SYNTHETIC players."""
    row = {"bisPlayerId": 1000 + i, "pickRound": "1" if drafted else None, "pickNumber": i if drafted else None,
           "isDrafted": drafted, "isPass": False, "year": "2027",
           "person": {"id": 900000 + i, "fullName": f"Prospect Number{i}", "birthDate": "2008-03-09",
                      "primaryPosition": {"abbreviation": "SS" if i % 2 else "P"}},
           "school": {"name": "Some Long High School Name", "schoolClass": "HS SR", "state": "TX", "country": "USA"},
           "draftType": {"code": "JR"}}
    if rank is not None:
        row["rank"] = rank
    if drafted:
        row["team"] = {"id": 134, "name": "Pittsburgh Pirates"}
    return row


def class_list(shift=0, unranked=20):
    """Ranked prospects 1 to 59 (number 7 shifted by ``shift`` places) plus unranked ones."""
    ranked = [prospect(i, rank=i + (shift if i == 7 else 0)) for i in range(1, 60)]
    return ranked + [prospect(100 + i) for i in range(unranked)]


class FakeFetch:
    def __init__(self, lists: dict[int, list]):
        self.lists = lists
        self.urls = []

    def __call__(self, url, params):
        self.urls.append(url)
        year = int(url.rstrip("/").rsplit("/", 1)[1])
        return {"copyright": "", "totalSize": 0, "prospects": self.lists.get(year, [])}


def api(lists):
    return mp.MlbApi(FakeFetch(lists))


class BoardTests(unittest.TestCase):
    def test_board_fits_one_discord_message_and_has_no_bullets(self):
        board = {"year": 2027, "prospects": class_list()}
        task = prospects.build_task(board, 30, TODAY)
        text = "\n\n".join(task["items"])
        self.assertLess(len(text), 3800)
        self.assertNotIn("•", text)
        self.assertIn("**Top 30**", text)
        self.assertIn("1. Prospect Number1: SS, Some Long High School Name (HS SR), age 18", text)
        self.assertIn("2027 MLB Draft", text)

    def test_unranked_players_are_skipped(self):
        self.assertEqual(len(prospects.ranked(class_list())), 59)
        self.assertEqual(prospects.ranked([prospect(1), prospect(2, rank=0)]), [])

    def test_drafted_players_show_the_pick(self):
        line = prospects.describe(prospect(3, rank=3, drafted=True), TODAY)
        self.assertIn("Pittsburgh Pirates, pick 3", line)

    def test_big_moves_are_reported(self):
        old = prospects.snapshot({"year": 2027, "prospects": class_list()})
        moves = prospects.movers(old, {"year": 2027, "prospects": class_list(shift=9)}, 30)
        self.assertEqual(moves, ["Prospect Number7 moved down from 7 to 16."])

    def test_small_moves_are_ignored(self):
        old = prospects.snapshot({"year": 2027, "prospects": class_list()})
        self.assertEqual(prospects.movers(old, {"year": 2027, "prospects": class_list(shift=3)}, 30), [])

    def test_config_and_draft_year(self):
        self.assertEqual(prospects.load_config(), {"top": 30, "year": None})
        self.assertEqual(prospects.draft_year(date(2026, 10, 15)), 2027)
        self.assertEqual(prospects.draft_year(date(2027, 3, 3)), 2027)
        self.assertEqual(prospects.draft_year(date(2027, 7, 31)), 2027)
        self.assertEqual(prospects.draft_year(date(2027, 8, 1)), 2028)
        self.assertEqual(prospects.draft_year(date(2027, 3, 3), 2029), 2029)


class RunTests(unittest.TestCase):
    def _run(self, lists, saved=None, mode="live", ok=True, today=TODAY):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state = Path(tmp.name) / "prospects.json"
        if saved is not None:
            state.write_text(json.dumps(saved))
        posts = []

        def fake_post(secret, payload):
            posts.append(payload)
            return ok, "delivered" if ok else "boom"

        with patch.object(prospects, "STATE_PATH", state), patch.object(prospects, "post_discord_webhook", fake_post), \
                patch("builtins.print"):
            c1 = prospects.run(mode, api(lists), today)
            c2 = prospects.run(mode, api(lists), today)
        return c1, c2, posts, state

    def test_first_run_posts_board_once(self):
        c1, c2, posts, state = self._run({2027: class_list()})
        self.assertEqual((c1, c2, len(posts)), (0, 0, 1))
        self.assertEqual(posts[0]["allowed_mentions"], expected_mentions())
        self.assertIn("hash", json.loads(state.read_text()))

    def test_changed_rankings_post_again(self):
        saved = prospects.snapshot({"year": 2027, "prospects": class_list()})
        _, _, posts, _ = self._run({2027: class_list(shift=9)}, saved)
        self.assertEqual(len(posts), 1)
        self.assertIn("Biggest moves", posts[0]["embeds"][0]["description"])

    def test_failed_delivery_retries_without_saving(self):
        c1, _, posts, state = self._run({2027: class_list()}, ok=False)
        self.assertEqual((c1, len(posts)), (1, 2))
        self.assertFalse(state.exists())

    def test_preview_posts_nothing(self):
        _, _, posts, state = self._run({2027: class_list()}, mode="preview")
        self.assertEqual(posts, [])
        self.assertFalse(state.exists())

    def test_empty_list_posts_and_saves_nothing(self):
        # MLB's real answer for 2027 on October 14-15, 2026.
        empty = json.loads((FIXTURES / "mlb_draft_prospects_2027.json").read_text(encoding="utf-8"))["prospects"]
        c1, c2, posts, state = self._run({2027: empty}, today=date(2026, 10, 15))
        self.assertEqual((c1, c2, posts), (0, 0, []))
        self.assertFalse(state.exists())

    def test_a_list_without_ranks_is_treated_as_not_published(self):
        _, _, posts, state = self._run({2027: [prospect(i) for i in range(1, 50)]})
        self.assertEqual(posts, [])
        self.assertFalse(state.exists())

    def test_test_post_waits_for_a_ranked_list(self):
        with patch.object(prospects, "post_discord_webhook") as post, patch("builtins.print"):
            self.assertEqual(prospects.test_post(api({2027: []}), date(2026, 10, 15)), 0)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
