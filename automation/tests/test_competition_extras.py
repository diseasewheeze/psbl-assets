#!/usr/bin/env python3
"""Offline checks for the Luck Index, the schedule edge, Monthly Awards and bounties.

Fantrax samples: league_info_2026_test.json and standings_week0.json (live
captures from the 2026-27 test league, for the calendar and standings) and
the MLB-shaped variants in tests/mlb_fixtures.py (a 2027 calendar, rosters and
player directory). MLB: the synthetic Week 3 schedule with scoring plays, in
the shape checked live. Full rosters are built here.
"""

from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

AUTOMATION = Path(__file__).resolve().parents[1]
for sub in ("", "competition", "tests"):
    sys.path.insert(0, str(AUTOMATION / sub))

import bounties  # noqa: E402
import desk  # noqa: E402
import edge  # noqa: E402
import mlb_fixtures as fx  # noqa: E402
import monthly  # noqa: E402
import render  # noqa: E402
import weekly  # noqa: E402
from core import mlb, season  # noqa: E402
from core.fantrax import normalize_standings, schedule_for  # noqa: E402
from core.league import load_league  # noqa: E402

ET = ZoneInfo("America/New_York")
FIXTURES = Path(__file__).resolve().parent / "fixtures"
INFO = json.loads((FIXTURES / "league_info_2026_test.json").read_text())
RAW_STANDINGS = json.loads((FIXTURES / "standings_week0.json").read_text())
MLB_INFO = fx.MLB_INFO
CTX = render.Context("PSBL Test League", "2027 TEST", 0xBD3039)
COMP = {"report_time": "08:00", "playoff_race_start_week": 16, "bubble_depth": 3}


def et(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET).astimezone(timezone.utc)


def morning_of_end(week: int, hour: int = 8, info: dict = INFO) -> datetime:
    local = season.period(info, week).end.astimezone(ET)
    return datetime(local.year, local.month, local.day, hour, 0, tzinfo=ET).astimezone(timezone.utc)


def team(tid: str, score: float) -> dict:
    return {"teamId": tid, "teamName": f"Team {tid}", "score": score, "gamesPlayed": 0.0, "categories": {}}


def week(*games: tuple[str, float, str, float]) -> list[dict]:
    return [{"away": team(a, sa), "home": team(h, sh)} for a, sa, h, sh in games]


def items(plan: desk.ReportPlan) -> list[tuple[str, int]]:
    return [(p.item, p.week) for p in plan.posts]


# Same four-team season as test_competition_additions.py.
W1 = week(("A", 120, "B", 100), ("C", 90, "D", 90))
W2 = week(("A", 80, "C", 110), ("B", 130, "D", 70))
W3 = week(("A", 0, "D", 0), ("B", 0, "C", 0))  # placeholder week
SEASON = {1: W1, 2: W2, 3: W3}


# --- Luck Index -----------------------------------------------------------------

class LuckTests(unittest.TestCase):
    def test_expected_wins_by_hand(self) -> None:
        # Week 1 all-play share: A 3/3, B 2/3, C 0.5/3, D 0.5/3 (C and D tied).
        # Week 2: B 3/3, C 2/3, A 1/3, D 0. The placeholder week 3 is ignored.
        xw = weekly.expected_wins(SEASON)
        expected = {"A": 4 / 3, "B": 5 / 3, "C": 5 / 6, "D": 1 / 6}
        for tid, value in expected.items():
            self.assertAlmostEqual(xw[tid], value)

    def test_luck_is_wins_minus_expected_with_ties_half(self) -> None:
        # Actual: A 1 win, B 1, C 1 win + 1 tie = 1.5, D 1 tie = 0.5.
        luck = weekly.luck(SEASON)
        expected = {"A": 1 - 4 / 3, "B": 1 - 5 / 3, "C": 1.5 - 5 / 6, "D": 0.5 - 1 / 6}
        for tid, value in expected.items():
            self.assertAlmostEqual(luck[tid], value)
        self.assertAlmostEqual(sum(luck.values()), 0.0)

    def test_twelve_team_league_adds_up(self) -> None:
        # 6 matchups a week: expected wins add up to 6 per week, Luck to 0.
        rows = [synthetic_week(w) for w in (1, 2, 3)]
        weeks = dict(enumerate(rows, start=1))
        self.assertAlmostEqual(sum(weekly.expected_wins(weeks).values()), 18.0)
        self.assertAlmostEqual(sum(weekly.luck(weeks).values()), 0.0)

    def test_format(self) -> None:
        self.assertEqual(render.fmt_luck(1.44), "+1.4")
        self.assertEqual(render.fmt_luck(-0.66), "-0.7")
        self.assertEqual(render.fmt_luck(-0.04), "0.0")
        self.assertEqual(render.fmt_luck(0.0), "0.0")

    def test_power_rankings_show_luck(self) -> None:
        rows = weekly.power_rankings(SEASON)
        self.assertAlmostEqual(next(r for r in rows if r.team_id == "C").luck, 2 / 3)
        body = render.power_rankings(CTX, 2, rows, has_previous=False)
        embed = body["embeds"][0]
        values = {f["name"]: f["value"] for f in embed["fields"]}
        self.assertIn("**All-Play:** 5-1-0 • **Luck:** -0.7 • **Score:**", values["1. Team B"])
        self.assertIn("**Luck:** +0.7", values["3. Team C"])
        self.assertIn("**Luckiest:** Team C (+0.7) • **Unluckiest:** Team B (-0.7)", embed["description"])
        self.assertIn("Luck = actual wins minus expected wins", embed["description"])

    def test_shared_extremes_and_no_line_when_all_equal(self) -> None:
        even = {1: week(("A", 100, "B", 100), ("C", 100, "D", 100))}  # all ties: Luck 0 for everyone
        rows = weekly.power_rankings(even)
        self.assertEqual(weekly.luck_extremes(rows), ([], []))
        self.assertNotIn("Luckiest", render.power_rankings(CTX, 1, rows, has_previous=False)["embeds"][0]["description"])
        # A and C: 1 win against an all-play share of (2 + 0.5) / 3; B and D: 0 against 0.5 / 3.
        split = {1: week(("A", 100, "B", 90), ("C", 100, "D", 90))}
        line = render.luck_line(weekly.power_rankings(split))
        self.assertEqual(line, "**Luckiest:** Team A and Team C (+0.2) • **Unluckiest:** Team B and Team D (-0.2)")


def synthetic_week(w: int, info: dict = INFO) -> list[dict]:
    """Distinct, deterministic scores for the 12 test-league teams."""
    rows = []
    for index, pair in enumerate(schedule_for(info, w)):
        row = {}
        for side in ("away", "home"):
            t = pair[side]
            i = int(t["teamId"], 36) % 1000
            score = round(60 + (i * 37 + w * 53) % 97 + i * 0.001 + index * 0.0001, 4)
            row[side] = {"teamId": t["teamId"], "teamName": t["teamName"], "score": score,
                         "gamesPlayed": 10.0, "categories": {"GS": 2.0}}
        rows.append(row)
    return rows


# --- Schedule edge ----------------------------------------------------------------

def player(pid: str, team_code: str, *positions: str, name: str = "") -> edge.RosterPlayer:
    return edge.RosterPlayer(pid, mlb.name_key(name or pid), team_code, frozenset(positions))


def week3_games() -> list[mlb.Game]:
    p3 = season.period(MLB_INFO, 3)
    return mlb.fetch_schedule(p3.start.astimezone(ET).date(), p3.end.astimezone(ET).date(), fx.schedule_get)


class HitterFillTests(unittest.TestCase):
    def test_slot_limits(self) -> None:
        # Hitter slots: C, 1B, 2B, 3B, SS, 3 OF, 2 UTIL (core/sport.py).
        self.assertEqual(edge.max_hitter_games([({"OF", "UTIL"}, 1)] * 7), 5)   # 3 OF + 2 UTIL
        self.assertEqual(edge.max_hitter_games([({"C", "UTIL"}, 1)] * 4), 3)    # 1 C + 2 UTIL
        self.assertEqual(edge.max_hitter_games([(set(), 1)] * 3), 0)            # pitchers
        self.assertEqual(edge.max_hitter_games([]), 0)

    def test_multi_position_player_goes_where_he_helps(self) -> None:
        # Three SS-only players and one 2B/SS: the 2B/SS must play 2B so the
        # SS-only players can use SS and both UTIL slots: 4.
        eligible = [(player(f"s{i}", "NYY", "SS").hitter_slots(), 1) for i in range(3)]
        eligible.append((player("m", "NYY", "2B", "SS").hitter_slots(), 1))
        self.assertEqual(edge.max_hitter_games(eligible), 4)
        self.assertEqual(edge.max_hitter_games(list(reversed(eligible))), 4)

    def test_doubleheader_players_first(self) -> None:
        # Six outfielders for five seats: the two with a doubleheader play.
        self.assertEqual(edge.max_hitter_games([({"OF", "UTIL"}, 1)] * 4 + [({"OF", "UTIL"}, 2)] * 2), 7)

    def test_slots_from_positions(self) -> None:
        self.assertEqual(player("1", "NYY", "C").hitter_slots(), {"C", "UTIL"})
        self.assertEqual(player("2", "NYY", "1B", "OF").hitter_slots(), {"1B", "OF", "UTIL"})
        self.assertEqual(player("3", "NYY", "LF").hitter_slots(), {"OF", "UTIL"})
        self.assertEqual(player("4", "NYY", *edge.positions_of("UT")).hitter_slots(), {"UTIL"})
        self.assertEqual(player("5", "NYY", "SP").hitter_slots(), set())
        self.assertTrue(player("5", "NYY", "SP").starter)
        self.assertEqual(edge.positions_of("1B,OF", "UT"), frozenset({"1B", "OF", "UTIL"}))


class ProjectionTests(unittest.TestCase):
    def test_one_day_by_hand(self) -> None:
        # Thursday Apr 15: NYY plays a doubleheader, TOR one game, LAD is off.
        thursday = {fx.THU: edge.days_in_period(week3_games(), *self.p3())[fx.THU]}
        g1, g2 = thursday[fx.THU]["NYY"]
        squad = ([player("c", "NYY", "C"), player("1b", "NYY", "1B"), player("ss", "TOR", "SS")]
                 + [player(f"of{i}", "TOR", "OF") for i in range(4)] + [player("lad", "LAD", "OF")]
                 + [player("sp1", "NYY", "SP", name=g1.away_probable.name),
                    player("sp2", "NYY", "SP", name=g2.away_probable.name),
                    player("sp3", "NYY", "SP", name="Not Starting")])
        proj = edge.project(squad, thursday, {fx.THU}, start_cap=7)
        # C 2 + 1B 2 + SS 1 + three OF and one UTIL from TOR 4 = 9 hitter games; two announced starts.
        self.assertEqual((proj.hitter_games, proj.starts, proj.games, proj.light_games), (9, 2, 11, 11))

    def p3(self) -> tuple:
        p = season.period(MLB_INFO, 3)
        return p.start, p.end, ET

    def test_starts_capped_per_period_and_slots_per_day(self) -> None:
        ace = player("ace", "NYY", "SP", name="Ace One")
        days = {}
        for i in range(8):
            day = date(2027, 5, 1) + timedelta(days=i)
            days[day] = {"NYY": [mlb.Game(i + 1, day, None, "NYY", "BOS", away_probable=mlb.Person(1, "Ace One"))]}
        self.assertEqual(edge.project([ace], days, set(), start_cap=7).starts, 7)
        self.assertEqual(edge.project([ace], days, set(), start_cap=14).starts, 8)
        clubs = ["NYY", "TOR", "BOS", "TB", "BAL", "CLE"]
        day = date(2027, 5, 1)
        one_day = {day: {c: [mlb.Game(i + 1, day, None, c, "SEA", away_probable=mlb.Person(i + 1, f"Arm {c}"))]
                         for i, c in enumerate(clubs)}}
        six = [player(c, c, "SP", name=f"Arm {c}") for c in clubs]
        self.assertEqual(edge.project(six, one_day, set(), start_cap=7).starts, 5)  # five SP slots

    def test_light_days_counted_separately(self) -> None:
        mon, tue, wed = date(2027, 5, 3), date(2027, 5, 4), date(2027, 5, 5)
        squad = [player("a", "NYY", "SS"), player("b", "TOR", "SS"), player("c", "TOR", "C")]
        game = lambda d, a, h: mlb.Game(hash((d, a)) % 1000 + 1, d, None, a, h)  # noqa: E731
        days = {mon: {"NYY": [game(mon, "NYY", "BOS")]},
                tue: {"NYY": [game(tue, "NYY", "BOS")], "TOR": [game(tue, "TOR", "TB")]},
                wed: {"TOR": [game(wed, "TOR", "TB")]}}
        proj = edge.project(squad, days, {mon, wed}, start_cap=7)
        self.assertEqual((proj.games, proj.light_games), (1 + 3 + 2, 1 + 2))

    def test_lineup_players_skip_minors_ir_and_unknown_clubs(self) -> None:
        teams = edge.lineup_players(fx.rosters(), fx.player_ids())
        t1 = {p.player_id: p for p in teams["t1"]}
        self.assertNotIn("m_kid", t1)    # MINORS
        self.assertNotIn("i_hurt", t1)   # IR
        self.assertNotIn("b_fa", t1)     # no MLB club
        self.assertEqual(t1["b_archer"].positions, frozenset({"1B", "OF"}))
        self.assertEqual(t1["h_carrow"].positions, frozenset({"1B", "UTIL"}))  # roster slot UT
        self.assertEqual(t1["h_hale"].name, "marcus hale")
        t2 = {p.player_id: p for p in teams["t2"]}
        self.assertEqual((t2["h_garcia"].team, t2["h_pikeless"].team), ("WSH", "CWS"))  # Fantrax-style codes
        empty = {"rosters": {"t1": {"rosterItems": []}, "t2": {"rosterItems": []}}}
        self.assertIsNone(edge.lineup_players(empty, fx.player_ids()))

    def test_week_from_mlb_schedule(self) -> None:
        start, end, tz = self.p3()
        days = edge.days_in_period(week3_games(), start, end, tz)
        self.assertEqual(len(days), 7)
        self.assertEqual(sum(len(clubs) for clubs in days.values()), 164)
        self.assertEqual(sum(len(g) for clubs in days.values() for g in clubs.values()), 170)  # 85 games
        squad = [player("nyy", "NYY", "C"), player("kc", "KC", "C")]
        proj = edge.projections({"x": squad}, week3_games(), start, end, tz, start_cap=7)["x"]
        self.assertEqual((proj.games, proj.light_games), (7 + 5, 2))  # NYY 7 (two doubleheaders), KC 5


# --- Desk: schedule edge in the preview ---------------------------------------------

def rosters_for(info: dict, w: int, codes: list[str],
                starters: dict[str, list[str]] | None = None) -> tuple[dict, dict]:
    """Full 25-player rosters (plus a minor) for every team in week w, one MLB club each.

    ``starters`` names a club's starting pitchers (to match its probables).
    """
    rosters: dict = {"rosters": {}}
    players: dict = {}
    layout = ["C"] * 2 + ["1B"] * 2 + ["2B"] * 2 + ["3B"] * 2 + ["SS"] * 2 + ["OF"] * 5 + ["SP"] * 6 + ["RP"] * 4
    for n, pair in enumerate(t for row in schedule_for(info, w) for t in (row["away"], row["home"])):
        club = codes[n % len(codes)]
        names = list((starters or {}).get(club, []))
        items = []
        for k, pos in enumerate(layout + ["SS"]):
            pid = f"p{n}-{k}"
            name = f"Player, {pid}"
            if pos == "SP" and names:
                first, _, last = names.pop(0).partition(" ")
                name = f"{last}, {first}"
            players[pid] = {"fantraxId": pid, "name": name, "position": pos, "team": club}
            items.append({"id": pid, "position": pos, "status": "MINORS" if k == len(layout) else
                          ("ACTIVE" if k < 18 else "RESERVE")})
        rosters["rosters"][pair["teamId"]] = {"teamName": pair["teamName"], "rosterItems": items}
    return rosters, players


class FakeFantrax:
    def __init__(self, counted: int, weeks: dict[int, list[dict]] | None = None,
                 rosters: dict | None = None, players: dict | None = None, info: dict = INFO) -> None:
        raw = copy.deepcopy(RAW_STANDINGS)
        for i, row in enumerate(raw):
            wins = counted // 2 + (1 if i % 2 and counted % 2 else 0)
            row["points"] = f"{wins}-{counted - wins}-0"
        self.rows = normalize_standings(raw)
        self.weeks = weeks or {}
        self._rosters, self._players = rosters, players
        self.roster_calls = 0
        self.info = info

    def league_info(self) -> dict:
        return self.info

    def standings(self) -> list[dict]:
        return self.rows

    def matchup_scores(self, period: int) -> list[dict]:
        return copy.deepcopy(self.weeks.get(period) or synthetic_week(period, self.info))

    def rosters(self) -> dict:
        self.roster_calls += 1
        if self._rosters is None:
            raise RuntimeError("Fantrax is down")
        return self._rosters

    def player_ids(self) -> dict:
        if self._players is None:
            raise RuntimeError("Fantrax is down")
        return self._players


class DeskBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmp.name) / "competition.json"
        patcher = patch.object(desk, "STATE_PATH", self.state_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.cfg = load_league()
        self.mlb_calls: list[str] = []

    def getter(self, fail_scores: bool = False, fail_schedule: bool = False):
        def get(url: str) -> dict:
            self.mlb_calls.append(url)
            scores = "scoringplays" in url
            if (fail_scores and scores) or (fail_schedule and not scores):
                raise RuntimeError("MLB Stats API unreachable")
            return fx.schedule_get(url)
        return get

    def make(self, fantrax: FakeFantrax, saved: dict | None = None, **get_opts) -> desk.Desk:
        return desk.Desk(self.cfg, fx=fantrax, saved_state=saved or {}, mlb_get=self.getter(**get_opts))

    def live(self, d: desk.Desk, now: datetime, fail: tuple[str, ...] = ()) -> tuple[list[tuple[str, str]], str]:
        sent: list[tuple[str, str]] = []

        def fake_send(secret: str, payload: dict):
            title = payload["embeds"][0]["title"]
            if any(f in title for f in fail):
                return False, "HTTP 500", None
            sent.append((secret, title))
            return True, "delivered", "1"

        out = io.StringIO()
        with patch.object(desk, "send_discord_webhook", fake_send), redirect_stdout(out):
            desk.run("live", list(desk.ITEMS), None, False, desk=d, now=now)
        return sent, out.getvalue()

    def state(self) -> dict:
        return json.loads(self.state_path.read_text())


def nyy_starters() -> list[str]:
    return sorted({g.probable("NYY").name for g in week3_games() if "NYY" in g.teams and g.probable("NYY")})


class PreviewEdgeTests(DeskBase):
    MONDAY = fx.et(2027, 4, 12, 8)

    def test_preview_shows_projected_games(self) -> None:
        rosters, players = rosters_for(MLB_INFO, 3, ["NYY", "KC", "TOR", "SEA"], {"NYY": nyy_starters()})
        d = self.make(FakeFantrax(2, rosters=rosters, players=players, info=MLB_INFO))
        body = d.build("preview", 3, self.MONDAY)
        embed = body["embeds"][0]
        first = schedule_for(MLB_INFO, 3)[0]
        # First matchup: NYY players vs KC players. 15 hitters fill all 10 hitter slots every
        # game: NYY 7 games (two doubleheaders) = 70, KC 5 games = 50. NYY's five starters
        # cover all 7 announced NYY starts (cap 7). Light days: Thursday's NYY doubleheader.
        self.assertIn("Projected games: 77 vs 50 • Probable starts: 7 vs 0 • Light-day games: 22 vs 0",
                      embed["fields"][0]["value"])
        self.assertTrue(embed["fields"][0]["value"].startswith(f"**{first['away']['teamName']}** — #"))
        self.assertIn("where MLB has announced them, capped at 7", embed["description"])
        self.assertIn("20 or fewer MLB teams playing", embed["description"])
        self.assertEqual(len(embed["fields"]), 6)

    def test_empty_rosters_leave_the_preview_unchanged(self) -> None:
        empty = {"rosters": {pair["teamId"]: {"teamName": pair["teamName"], "rosterItems": []}
                             for row in schedule_for(MLB_INFO, 3) for pair in (row["away"], row["home"])}}
        d = self.make(FakeFantrax(2, rosters=empty, players={}, info=MLB_INFO))
        body = d.build("preview", 3, self.MONDAY)
        self.assertNotIn("Projected", json.dumps(body))
        self.assertTrue(body["embeds"][0]["description"].endswith(
            "\n\n*This week's matchups with each team's current Fantrax standing and record. "
            "The scoreboard will track scoring once the week is underway.*"))
        self.assertTrue(any("every PSBL roster is empty" in n for n in d.notes))
        self.assertEqual(self.mlb_calls, [])  # no MLB call needed

    def test_failures_never_break_the_preview(self) -> None:
        rosters, players = rosters_for(MLB_INFO, 3, ["NYY"])
        for d in (self.make(FakeFantrax(2, rosters=rosters, players=players, info=MLB_INFO), fail_schedule=True),
                  self.make(FakeFantrax(2, info=MLB_INFO))):  # Fantrax rosters down
            body = d.build("preview", 3, self.MONDAY)
            self.assertEqual(body["embeds"][0]["title"], "PSBL Week 3 Matchup Preview")
            self.assertNotIn("Projected", json.dumps(body))
            self.assertTrue(any("schedule edge left out" in n for n in d.notes))

    def test_live_monday_still_posts_preview_when_mlb_is_down(self) -> None:
        self.state_path.write_text(json.dumps({"recap_week": 1, "standings_week": 1, "preview_week": 2,
                                               "bounties_week": 1, "bounties": {"feat_through": "2027-04-11"}}))
        rosters, players = rosters_for(MLB_INFO, 3, ["NYY"])
        sent, out = self.live(self.make(FakeFantrax(2, rosters=rosters, players=players, info=MLB_INFO),
                                        fail_schedule=True), self.MONDAY)
        self.assertIn(("LEAGUE_WEBHOOK_SCOREBOARD", "PSBL Week 3 Matchup Preview"), sent)
        self.assertIn("NOTE    preview week 3: schedule edge left out", out)
        self.assertIn("ERROR   games week 3", out)  # the grid itself still reports the MLB failure

    def test_schedule_fetched_once_for_preview_and_grid(self) -> None:
        rosters, players = rosters_for(MLB_INFO, 3, ["NYY"])
        d = self.make(FakeFantrax(2, rosters=rosters, players=players, info=MLB_INFO))
        d.build("preview", 3, self.MONDAY)
        d.build("games", 3, self.MONDAY)
        self.assertEqual(len(self.mlb_calls), 1)  # one request covers the week


# --- Monthly awards ---------------------------------------------------------------

M1 = week(("A", 120, "B", 100), ("C", 90, "D", 90))
M2 = week(("A", 80, "C", 110), ("B", 130, "D", 70))
M3 = week(("A", 100, "D", 140), ("B", 95, "C", 105))
MONTH = {1: M1, 2: M2, 3: M3}


class MonthGroupTests(unittest.TestCase):
    groups = monthly.month_groups(INFO, ET, 22)

    def test_weeks_belong_to_the_month_of_their_last_night(self) -> None:
        got = [(g.key, g.weeks, g.report_week, g.final) for g in self.groups]
        self.assertEqual(got, [
            ("2026-10", (1, 2, 3, 4), 5, False),
            ("2026-11", (5, 6, 7, 8, 9), 10, False),
            ("2026-12", (10, 11, 12, 13), 14, False),
            ("2027-01", (14, 15, 16, 17, 18), 19, False),  # Week 18 ends Mon Feb 1: last night Sun Jan 31
            ("2027-02", (19, 20, 21), 22, False),          # Week 21 ends Mon Mar 1: last night Sun Feb 28
            ("2027-03", (22,), 22, True),   # the last month goes out with Week 22
        ])
        self.assertEqual(self.groups[0].label, "October 2026")

    def test_month_ending_on_a_sunday_keeps_its_last_week(self) -> None:
        # October 2027 ends on a Sunday. Fantrax ends the Oct 25-31 week on
        # Monday, November 1 at the first game; it is still an October week.
        info = {"scoringPeriods": [
            {"number": 1, "startDate": "2027-10-18T19:00:00.0-0400", "endDate": "2027-10-25T18:59:59.0-0400"},
            {"number": 2, "startDate": "2027-10-25T19:00:00.0-0400", "endDate": "2027-11-01T18:59:59.0-0400"},
            {"number": 3, "startDate": "2027-11-01T19:00:00.0-0400", "endDate": "2027-11-08T18:59:59.0-0500"},
        ]}
        self.assertEqual(monthly.last_night(season.period(info, 2), ET), date(2027, 10, 31))
        got = [(g.key, g.weeks, g.report_week, g.final) for g in monthly.month_groups(info, ET, 3)]
        self.assertEqual(got, [("2027-10", (1, 2), 3, False), ("2027-11", (3,), 3, True)])

    def test_due_and_baseline(self) -> None:
        self.assertEqual([g.key for g in monthly.due_groups(self.groups, 5, 0)], ["2026-10"])
        self.assertEqual(monthly.due_groups(self.groups, 5, 4), [])
        self.assertEqual(monthly.due_groups(self.groups, 4, 0), [])
        self.assertEqual(monthly.posted_baseline(self.groups, 5), 4)
        self.assertEqual(monthly.posted_baseline(self.groups, 4), 0)


class MonthlyAwardTests(unittest.TestCase):
    def test_awards_by_hand(self) -> None:
        # Totals A 300, B 325, C 305, D 300. Records A 1-2-0, B 1-2-0, C 2-0-1, D 1-1-1.
        # Best week D 140 (Week 3). Points in losses: A 80+100, B 100+95, D 70.
        a = monthly.monthly_awards(MONTH)
        self.assertEqual([(w.team_id, w.value) for w in a.manager], [("B", 325)])
        self.assertEqual([(w.team_id, w.record.text()) for w in a.record], [("C", "2-0-1")])
        self.assertEqual([(w.team_id, w.value, w.week) for w in a.big_week], [("D", 140, 3)])
        self.assertEqual([(w.team_id, w.value, w.losses) for w in a.hard_luck], [("B", 195, 2)])

    def test_ties_go_to_points_then_are_shared(self) -> None:
        shared = monthly.monthly_awards({1: week(("A", 100, "B", 90), ("C", 100, "D", 90))})
        self.assertEqual([w.team_id for w in shared.manager], ["A", "C"])
        self.assertEqual([w.team_id for w in shared.record], ["A", "C"])
        self.assertEqual([w.team_id for w in shared.hard_luck], ["B", "D"])
        decided = monthly.monthly_awards({1: week(("A", 100, "B", 90), ("C", 95, "D", 90))})
        self.assertEqual([w.team_id for w in decided.record], ["A"])  # same record, more points

    def test_two_week_period_is_not_a_single_week(self) -> None:
        a = monthly.monthly_awards(MONTH, long_weeks={3})
        self.assertEqual([(w.team_id, w.value, w.week) for w in a.big_week], [("B", 130, 2)])
        self.assertEqual(monthly.multi_week_periods(INFO, [18, 19, 20]), {19})

    def test_placeholder_month_has_no_post(self) -> None:
        group = monthly.month_groups(INFO, ET, 22)[0]
        span = season.period(INFO, 1)
        self.assertIsNone(render.monthly_awards(CTX, group, span, monthly.monthly_awards({3: W3})))

    def test_post(self) -> None:
        groups = monthly.month_groups(INFO, ET, 22)
        body = render.monthly_awards(CTX, groups[0], season.period(INFO, 1), monthly.monthly_awards(MONTH))
        embed = body["embeds"][0]
        fields = {f["name"]: f["value"] for f in embed["fields"]}
        self.assertEqual(embed["title"], "PSBL Monthly Awards — October 2026")
        self.assertEqual(list(fields), ["Manager of the Month", "Best Record of the Month", "Biggest Single Week",
                                        "Hard Luck", "The Role"])
        self.assertEqual(fields["Manager of the Month"], "**Team B** — 325.00 pts")
        self.assertEqual(fields["Best Record of the Month"], "**Team C** — 2-0-1 • 305.00 pts")
        self.assertEqual(fields["Biggest Single Week"], "**Team D** — 140.00 pts in Week 3")
        self.assertEqual(fields["Hard Luck"], "**Team B** — 195.00 pts in 2 losses")
        self.assertEqual(fields["The Role"], "**Team B** holds the 📅 Manager of the Month role until next "
                                             "month's award. The Commissioner assigns the role.")
        self.assertIn("Weeks 1–3: the fantasy weeks that ended in October", embed["description"])
        self.assertEqual(embed["footer"]["text"], "MONTHLY AWARDS • FANTRAX READ-ONLY DATA")
        self.assertEqual(body["username"], "PSBL Competition Desk")
        self.assertEqual(body["allowed_mentions"], {"parse": []})
        final = render.monthly_awards(CTX, groups[-1], season.period(INFO, 21), monthly.monthly_awards(
            {1: week(("A", 100, "B", 90), ("C", 100, "D", 90))}))
        role = final["embeds"][0]["fields"][-1]["value"]
        self.assertEqual(role, "**Team A** and **Team C** share the 📅 Manager of the Month role until the first "
                               "Monthly Awards of next Season. The Commissioner assigns the role.")


class MonthlyPlanTests(unittest.TestCase):
    comp = COMP | {"monthly_awards": True}

    def plan(self, now: datetime, counted: int, state: dict, comp: dict | None = None) -> desk.ReportPlan:
        raw = copy.deepcopy(RAW_STANDINGS)
        for i, row in enumerate(raw):
            wins = counted // 2 + (1 if i % 2 and counted % 2 else 0)
            row["points"] = f"{wins}-{counted - wins}-0"
        return desk.plan_report(INFO, normalize_standings(raw), state, now, ET, comp or self.comp)

    def test_first_week_of_new_month_brings_last_months_awards(self) -> None:
        state = {"recap_week": 4, "standings_week": 4, "preview_week": 5, "monthly_week": 0}
        self.assertEqual(items(self.plan(morning_of_end(5), 5, state)),
                         [("recap", 5), ("awards", 5), ("rankings", 5), ("monthly", 4), ("standings", 5),
                          ("preview", 6), ("games", 6)])

    def test_posted_once(self) -> None:
        state = {"recap_week": 5, "standings_week": 5, "preview_week": 6, "monthly_week": 4}
        self.assertEqual(items(self.plan(morning_of_end(5, 20), 5, state)), [])
        mid_month = {"recap_week": 5, "standings_week": 5, "preview_week": 6, "monthly_week": 4}
        self.assertNotIn("monthly", [i for i, _ in items(self.plan(morning_of_end(6), 6, mid_month))])

    def test_deploy_never_posts_an_old_month(self) -> None:
        # State saved before Monthly Awards existed (no monthly_week).
        state = {"recap_week": 5, "standings_week": 5, "preview_week": 6}
        self.assertNotIn("monthly", [i for i, _ in items(self.plan(morning_of_end(6), 6, state))])
        migrated = dict(state)
        desk.migrate_monthly(migrated, INFO, ET, self.comp)
        self.assertEqual(migrated["monthly_week"], 4)
        before = {"recap_week": 4, "standings_week": 4, "preview_week": 5}
        self.assertIn(("monthly", 4), items(self.plan(morning_of_end(5), 5, before)))

    def test_last_regular_week_posts_the_final_month(self) -> None:
        # Week 22 is the first March week, so February (Weeks 19-21) is due
        # too; March (Week 22 alone) is the final month and goes out with it.
        state = {k: 21 for k in ("recap_week", "standings_week", "race_week")} | {"preview_week": 22,
                                                                                   "monthly_week": 18}
        self.assertEqual(items(self.plan(morning_of_end(22), 22, state)),
                         [("recap", 22), ("awards", 22), ("rankings", 22), ("monthly", 21), ("monthly", 22),
                          ("standings", 22), ("spoon", 22)])

    def test_force_reposts_latest_month_only(self) -> None:
        self.assertEqual([i for i in items(self.plan(morning_of_end(15), 15, {})) if i[0] == "monthly"],
                         [("monthly", 13)])

    def test_off_unless_enabled(self) -> None:
        state = {"recap_week": 4, "standings_week": 4, "preview_week": 5}
        self.assertNotIn("monthly", [i for i, _ in items(self.plan(morning_of_end(5), 5, state, COMP))])


class MonthlyDeskTests(DeskBase):
    def test_live_post_and_retry_after_failure(self) -> None:
        self.state_path.write_text(json.dumps({"recap_week": 4, "standings_week": 4, "preview_week": 5,
                                               "bounties_week": 4, "bounties": {"feat_through": "2026-11-01"}}))
        sent, _ = self.live(self.make(FakeFantrax(5)), morning_of_end(5), fail=("Monthly",))
        self.assertNotIn("Monthly", " ".join(t for _, t in sent))
        state = self.state()
        self.assertEqual((state["recap_week"], state["monthly_week"]), (5, 0))
        sent, _ = self.live(self.make(FakeFantrax(5), state), morning_of_end(5, 20))
        self.assertEqual(sent, [("LEAGUE_WEBHOOK_WEEKLY_RECAP", "PSBL Monthly Awards — October 2026")])
        self.assertEqual(self.state()["monthly_week"], 4)
        sent, _ = self.live(self.make(FakeFantrax(5), self.state()), morning_of_end(6))
        self.assertNotIn("Monthly", " ".join(t for _, t in sent))

    def test_month_post_uses_that_months_weeks(self) -> None:
        d = self.make(FakeFantrax(5))
        body = d.build("monthly", 4, morning_of_end(5))
        embed = body["embeds"][0]
        expected = monthly.monthly_awards({w: synthetic_week(w) for w in (1, 2, 3, 4)})
        self.assertIn(f"**{expected.manager[0].team_name}** — {expected.manager[0].value:.2f} pts",
                      embed["fields"][0]["value"])
        self.assertIn("Weeks 1–4", embed["description"])
        self.assertEqual(d.webhook("monthly"), "LEAGUE_WEBHOOK_WEEKLY_RECAP")

    def test_preview_defaults_and_month_to_date(self) -> None:
        d = self.make(FakeFantrax(6))
        self.assertEqual(d.default_week("monthly", morning_of_end(6)), 4)   # October, complete
        self.assertEqual(d.default_week("monthly", morning_of_end(3)), 3)   # October to date
        title = d.build("monthly", 6, morning_of_end(7))["embeds"][0]["title"]
        self.assertEqual(title, "PSBL Monthly Awards — November 2026 (Month to Date)")
        self.assertIsNone(d.build("monthly", 23, morning_of_end(23)))  # playoffs: no monthly awards


# --- Bounties ---------------------------------------------------------------------

def bounty(kind: str, threshold: float, bid: str = "b") -> bounties.Bounty:
    return bounties.Bounty(bid, "Title", "What it takes.", kind, threshold)


class BountyConfigTests(unittest.TestCase):
    def test_defaults_in_league_yaml_are_valid(self) -> None:
        found, errors = bounties.load_bounties(load_league()["competition"])
        self.assertEqual(errors, [])
        self.assertEqual(sorted(b.type for b in found), sorted(bounties.TYPES))
        for b in found:
            self.assertIn("🎯 Bounty Hunter", b.reward)

    def test_rejects_bad_entries_and_competitive_rewards(self) -> None:
        raw = {"bounties": [
            {"id": "ok", "title": "OK", "type": "team_week_points", "threshold": 300},
            {"id": "ok", "title": "Dup", "type": "team_week_points", "threshold": 300},
            {"id": "faab", "title": "F", "type": "team_week_points", "threshold": 300, "reward": "$25 FAAB"},
            {"id": "pick", "title": "P", "type": "team_week_points", "threshold": 300, "reward": "A 5th-round pick"},
            {"id": "kind", "title": "K", "type": "most_goals", "threshold": 3},
            {"id": "zero", "title": "Z", "type": "team_win_streak", "threshold": 0},
        ]}
        found, errors = bounties.load_bounties(raw)
        self.assertEqual([b.id for b in found], ["ok"])
        self.assertEqual(found[0].reward, bounties.DEFAULT_REWARD)
        self.assertEqual(len(errors), 5)
        self.assertTrue(any("recognition only" in e for e in errors))


class TeamBountyTests(unittest.TestCase):
    weeks = {
        1: week(("A", 300, "B", 250), ("C", 345, "D", 200)),
        2: week(("A", 280, "C", 351), ("B", 352, "D", 260)),   # B 352 and C 351 cross 350 the same week
        3: week(("A", 400, "D", 100), ("B", 300, "C", 300)),   # B-C tie ends both streaks
        4: week(("A", 290, "B", 280), ("C", 250, "D", 260)),
    }

    def claims(self, *bs: bounties.Bounty, long_weeks: set[int] = frozenset()) -> dict:
        return bounties.team_claims(list(bs), self.weeks, long_weeks)

    def test_week_points_highest_that_week(self) -> None:
        claim = self.claims(bounty("team_week_points", 350))["b"]
        self.assertEqual((claim.teams, claim.week, claim.detail),
                         ([{"teamId": "B", "teamName": "Team B"}], 2, "352.00 points in Week 2"))
        later = self.claims(bounty("team_week_points", 350), long_weeks={2})["b"]
        self.assertEqual((later.teams[0]["teamId"], later.week), ("A", 3))  # two-week periods do not count

    def test_season_points(self) -> None:
        # After week 2: A 580, B 602, C 696, D 460. After week 3: A 980, B 902, C 996.
        claim = self.claims(bounty("team_season_points", 950))["b"]
        self.assertEqual((claim.teams[0]["teamId"], claim.week), ("C", 3))
        self.assertEqual(claim.detail, "996.00 season points after Week 3")
        self.assertNotIn("b", self.claims(bounty("team_season_points", 5000)))

    def test_win_streak_ties_break_it(self) -> None:
        # A: W, L, W, W -> 2 after week 4. B: L, W, T, L. C: W, W, T, L. D: L, L, L, W.
        self.assertNotIn("b", self.claims(bounty("team_win_streak", 3)))
        claim = self.claims(bounty("team_win_streak", 2))["b"]
        self.assertEqual((claim.teams[0]["teamId"], claim.week, claim.detail), ("C", 2, "2 straight wins through Week 2"))

    def test_exact_tie_is_shared(self) -> None:
        tied = {1: week(("A", 360, "B", 100), ("C", 360, "D", 100))}
        claim = bounties.team_claims([bounty("team_week_points", 350)], tied)["b"]
        self.assertEqual([t["teamId"] for t in claim.teams], ["A", "C"])
        self.assertIn("**Team A** and **Team C** — 360.00 points in Week 1",
                      render.bounties(CTX, [(bounty("team_week_points", 350), claim)], [])["embeds"][0]["fields"][0]["value"])

    def test_progress_for_open_bounties(self) -> None:
        self.assertEqual(bounties.progress(bounty("team_season_points", 6000), self.weeks),
                         "Leader: **Team A** — 1270.00 of 6,000")
        self.assertEqual(bounties.progress(bounty("team_week_points", 500), self.weeks),
                         "Best so far: **Team A** — 400.00 in Week 3")
        self.assertEqual(bounties.progress(bounty("team_win_streak", 5), self.weeks),
                         "Longest active streak: **Team A** — 2")
        self.assertEqual(bounties.progress(bounty("player_multi_homer", 2), self.weeks), "")
        self.assertEqual(bounties.progress(bounty("team_win_streak", 5), {}), "")


def day_scores(day: date) -> dict:
    return fx.schedule_response(mlb.schedule_url(day, day, mlb.SCORES))


class MultiHomerTests(unittest.TestCase):
    feat = bounty("player_multi_homer", 2, "first-multi-homer")

    def owner_of(self, skip: str = ""):
        sys.path.insert(0, str(AUTOMATION / "wire"))
        import roster
        index = roster.build_index(fx.rosters(), mlb.normalize_directory(fx.player_ids()))

        def owner(name: str, code: str):
            player = None if name == skip else index.match(name, code)
            return (player.owner_id, player.owner_name) if player else None
        return owner

    def test_earliest_rostered_multi_homer_wins(self) -> None:
        # Jonah Pike (STL) homered twice in the 2:15 PM game but is not rostered.
        check = bounties.find_multi_homer(self.feat, [fx.TUE], day_scores, self.owner_of())
        self.assertEqual(check.claim.teams, [{"teamId": "t1", "teamName": "Test 1"}])
        self.assertEqual(check.claim.detail, "Marcus Hale (NYY): 2 home runs against BOS on Tue Apr 13")
        self.assertEqual(check.claim.night, "2027-04-13")
        self.assertEqual(check.checked_through, fx.TUE)

    def test_unrostered_and_higher_thresholds_are_skipped(self) -> None:
        nobody = bounties.find_multi_homer(self.feat, [fx.TUE], day_scores, lambda name, code: None)
        self.assertIsNone(nobody.claim)
        self.assertEqual(nobody.checked_through, fx.TUE)
        claim = bounties.find_multi_homer(self.feat, [fx.TUE], day_scores, self.owner_of(skip="Marcus Hale")).claim
        self.assertEqual(claim.detail, "Kenji Mori (LAD): 2 home runs against SF on Tue Apr 13")
        three = bounties.find_multi_homer(bounty("player_multi_homer", 3), [fx.MON, fx.TUE, fx.WED], day_scores,
                                          self.owner_of())
        self.assertEqual((three.claim, three.checked_through), (None, fx.WED))

    def test_live_game_or_fetch_error_stops_without_advancing(self) -> None:
        def live(game: dict) -> None:
            if game["gamePk"] == fx.find_game(fx.TUE, "LAD", "SF")["gamePk"]:
                game["status"].update(abstractGameState="Live", codedGameState="I", detailedState="In Progress")
        playing = fx.edited_schedule(live)
        check = bounties.find_multi_homer(self.feat, [fx.TUE], lambda d: fx.schedule_response(
            mlb.schedule_url(d, d, mlb.SCORES), playing), self.owner_of())
        self.assertIsNone(check.checked_through)
        self.assertIn("still in progress", check.notes[0])

        def boom(d: date) -> dict:
            raise RuntimeError("timeout")
        failed = bounties.find_multi_homer(self.feat, [fx.MON], boom, self.owner_of())
        self.assertEqual((failed.claim, failed.checked_through), (None, None))
        self.assertIn("could not be read", failed.notes[0])

    def test_a_suspended_game_does_not_hold_the_check_up(self) -> None:
        def suspend(game: dict) -> None:
            if game["gamePk"] == fx.find_game(fx.TUE, "LAD", "SF")["gamePk"]:
                game["status"].update(abstractGameState="Live", codedGameState="U", detailedState="Suspended: Rain")
        held = fx.edited_schedule(suspend)
        check = bounties.find_multi_homer(self.feat, [fx.TUE], lambda d: fx.schedule_response(
            mlb.schedule_url(d, d, mlb.SCORES), held), self.owner_of(skip="Marcus Hale"))
        self.assertIsNone(check.claim)  # Mori's game is not final yet
        self.assertEqual(check.checked_through, fx.TUE)

    def test_error_body_is_retried_not_skipped(self) -> None:
        # MLB answers 200 with an error body on the multi-homer day: stop there,
        # so the next run checks it again instead of skipping it.
        bodies = {fx.MON: day_scores(fx.MON), fx.TUE: {"message": "Internal server error"}}
        failed = bounties.find_multi_homer(self.feat, [fx.MON, fx.TUE], lambda d: bodies[d], self.owner_of())
        self.assertIsNone(failed.claim)
        self.assertEqual(failed.checked_through, fx.MON)
        self.assertIn("MLB scores for 2027-04-13 could not be read", failed.notes[0])
        retry = bounties.find_multi_homer(self.feat, [fx.TUE], day_scores, self.owner_of())
        self.assertEqual((retry.claim.night, retry.checked_through), ("2027-04-13", fx.TUE))

    def test_nights_to_check(self) -> None:
        thu = fx.et(2027, 4, 15, 8)
        self.assertEqual(bounties.nights_to_check(MLB_INFO, ET, thu, 22, "2027-04-12"), [fx.TUE, fx.WED])
        first = bounties.nights_to_check(MLB_INFO, ET, thu, 22, None)
        self.assertEqual((first[0], len(first)), (date(2027, 3, 24), bounties.MAX_NIGHTS_PER_RUN))
        self.assertEqual(bounties.nights_to_check(MLB_INFO, ET, thu, 22, "2027-04-14"), [])
        # The last regular day is the Sunday before Week 22 ends (Mon Aug 30).
        self.assertEqual(bounties.regular_season_nights(MLB_INFO, ET, 22), (date(2027, 3, 24), date(2027, 8, 29)))
        self.assertEqual(bounties.nights_to_check(MLB_INFO, ET, fx.et(2027, 9, 5, 8), 22, "2027-08-29"), [])


def big_week(w: int, score: float = 460.0) -> list[dict]:
    rows = synthetic_week(w, MLB_INFO)
    rows[0]["away"]["score"] = score
    return rows


class BountyDeskTests(DeskBase):
    MON_WEEK2 = fx.et(2027, 4, 12, 8)

    def base_state(self, **extra) -> dict:
        state = {"recap_week": 1, "awards_week": 1, "rankings_week": 1, "standings_week": 1,
                 "preview_week": 2, "games_week": 2}
        state.update(extra)
        return state

    def fantrax(self, counted: int, weeks: dict | None = None, **kw) -> FakeFantrax:
        return FakeFantrax(counted, weeks, info=MLB_INFO, **kw)

    def test_team_bounty_announced_once(self) -> None:
        self.state_path.write_text(json.dumps(self.base_state()))
        weeks = {2: big_week(2), 3: big_week(3, 480.0)}
        sent, out = self.live(self.make(self.fantrax(2, weeks)), self.MON_WEEK2)
        self.assertIn(("LEAGUE_WEBHOOK_WEEKLY_RECAP", "PSBL Bounty Claimed — The 450 Club"), sent)
        titles = [t for _, t in sent]
        self.assertLess(titles.index("PSBL Power Rankings — After Week 2"),
                        titles.index("PSBL Bounty Claimed — The 450 Club"))
        state = self.state()
        claim = state["bounties"]["claimed"]["big-week-450"]
        self.assertEqual((claim["week"], claim["detail"]), (2, "460.00 points in Week 2"))
        self.assertEqual(state["bounties_week"], 2)
        # Week 3 has a bigger week: the bounty is already claimed, nothing new is announced.
        sent, _ = self.live(self.make(self.fantrax(3, weeks), state), fx.et(2027, 4, 19, 8))
        self.assertFalse(any("Bount" in t for _, t in sent))
        self.assertEqual(self.state()["bounties"]["claimed"]["big-week-450"]["week"], 2)

    def test_claim_post(self) -> None:
        self.state_path.write_text(json.dumps(self.base_state()))
        d = self.make(self.fantrax(2, {2: big_week(2)}))
        d.mode, d.live_state = "live", self.base_state()
        embed = d.build("bounties", 2, self.MON_WEEK2)["embeds"][0]
        name = synthetic_week(2, MLB_INFO)[0]["away"]["teamName"]
        self.assertEqual(embed["fields"][0]["name"], "The 450 Club")
        self.assertEqual(embed["fields"][0]["value"],
                         f"**{name}** — 460.00 points in Week 2\nFirst franchise to score 450 points in a single "
                         "week.\n**Reward:** 🎯 Bounty Hunter role for the Season. The Commissioner assigns it.")
        self.assertEqual(embed["fields"][-1]["name"], "Still Open")
        self.assertIn("**Eight Thousand** — First franchise to reach 8,000 season points.\nLeader: ",
                      embed["fields"][-1]["value"])
        self.assertEqual(embed["footer"]["text"], "BOUNTIES • FANTRAX READ-ONLY DATA")

    def test_multi_homer_claimed_the_morning_after(self) -> None:
        state = self.base_state(recap_week=2, awards_week=2, rankings_week=2, standings_week=2, preview_week=3,
                                games_week=3, bounties_week=2, bounties={"feat_through": "2027-04-12"})
        self.state_path.write_text(json.dumps(state))
        fantrax = self.fantrax(2, rosters=fx.rosters(), players=fx.player_ids())
        sent, _ = self.live(self.make(fantrax, state), fx.et(2027, 4, 15, 8))
        self.assertEqual(sent, [("LEAGUE_WEBHOOK_WEEKLY_RECAP", "PSBL Bounty Claimed — First Multi-Homer Game")])
        saved = self.state()["bounties"]
        self.assertEqual(saved["feat_through"], "2027-04-13")
        self.assertEqual(saved["claimed"]["first-multi-homer"]["teams"], [{"teamId": "t1", "teamName": "Test 1"}])
        self.assertEqual(self.mlb_calls, ["https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2027-04-13"
                                          "&endDate=2027-04-13&hydrate=linescore,decisions,scoringplays"])
        # Claimed: the evening run checks nothing.
        self.mlb_calls.clear()
        sent, _ = self.live(self.make(fantrax, self.state()), fx.et(2027, 4, 15, 20))
        self.assertEqual((sent, self.mlb_calls), ([], []))

    def test_old_saved_key_still_counts(self) -> None:
        self.assertEqual(desk.bounty_state({"bounties": {"hat_trick_through": "2027-04-12"}})["feat_through"],
                         "2027-04-12")

    def test_claim_post_footer(self) -> None:
        claim = bounties.Claim("first-multi-homer", [{"teamId": "t1", "teamName": "Test 1"}], "x", night="2027-04-13")
        body = render.bounties(CTX, [(bounty("player_multi_homer", 2), claim)], [], mlb_data=True)
        self.assertEqual(body["embeds"][0]["footer"]["text"], "BOUNTIES • FANTRAX READ-ONLY DATA • MLB SCORE DATA")

    def test_empty_rosters_advance_without_mlb_calls(self) -> None:
        state = self.base_state(bounties_week=1, bounties={"feat_through": "2027-04-05"})
        self.state_path.write_text(json.dumps(state))
        empty = {"rosters": {"t1": {"teamName": "Test", "rosterItems": []}}}
        sent, _ = self.live(self.make(self.fantrax(1, rosters=empty, players={}), state), fx.et(2027, 4, 9, 8))
        self.assertEqual(sent, [])
        self.assertEqual(self.state()["bounties"]["feat_through"], "2027-04-08")
        self.assertFalse(any("scoringplays" in u for u in self.mlb_calls))

    def test_outages_are_quiet_and_retried(self) -> None:
        state = self.base_state(bounties_week=1, bounties={"feat_through": "2027-04-12"})
        self.state_path.write_text(json.dumps(state))
        d = self.make(self.fantrax(2, rosters=fx.rosters(), players=fx.player_ids()), state, fail_scores=True)
        out = io.StringIO()
        with patch.object(desk, "send_discord_webhook", lambda s, p: (True, "delivered", "1")), redirect_stdout(out):
            self.assertEqual(desk.run("live", ["bounties"], None, False, desk=d, now=fx.et(2027, 4, 15, 8)), 0)
        self.assertIn("multi-homer check: MLB scores for 2027-04-13 could not be read", out.getvalue())
        self.assertEqual(self.state()["bounties"]["feat_through"], "2027-04-12")
        # Fantrax rosters down: same, nothing advances, no error.
        down = self.make(self.fantrax(2), self.state())
        with redirect_stdout(io.StringIO()):
            self.assertEqual(desk.run("live", ["bounties"], None, False, desk=down, now=fx.et(2027, 4, 15, 20)), 0)
        self.assertEqual(self.state()["bounties"]["feat_through"], "2027-04-12")

    def test_no_daily_fantrax_reread_for_team_bounties(self) -> None:
        state = self.base_state(recap_week=2, bounties_week=2, bounties={"feat_through": "2027-04-13"})
        d = self.make(self.fantrax(2, rosters={"rosters": {"t": {"rosterItems": []}}}, players={}), state)
        d.mode, d.live_state = "live", state
        with patch.object(d, "season_weeks", side_effect=AssertionError("re-read every week")) as reread:
            self.assertIsNone(d.build("bounties", 2, fx.et(2027, 4, 15, 8)))
            self.assertFalse(reread.called)

    def test_preview_board(self) -> None:
        d = self.make(self.fantrax(3))
        self.assertEqual(d.default_week("bounties", fx.et(2027, 4, 20, 8)), 3)
        body = d.build("bounties", 3, fx.et(2027, 4, 20, 8))
        embed = body["embeds"][0]
        self.assertEqual(embed["title"], "PSBL Bounty Board")
        board = embed["fields"][0]["value"]
        for title in ("First Multi-Homer Game", "The 450 Club", "Six Straight", "Eight Thousand"):
            self.assertIn(f"**{title}**", board)
        self.assertIn("Leader: **", board)
        self.assertFalse(self.state_path.exists())

    def test_plan(self) -> None:
        comp = COMP | {"bounties": load_league()["competition"]["bounties"]}
        rows = self.fantrax(2).rows
        base = self.base_state(recap_week=2, awards_week=2, rankings_week=2, standings_week=2, preview_week=3,
                               games_week=3)

        def plan(state: dict, now: datetime) -> list[tuple[str, int]]:
            return items(desk.plan_report(MLB_INFO, rows, state, now, ET, comp))

        self.assertEqual(plan(base, fx.et(2027, 4, 15, 8)), [("bounties", 2)])
        checked = base | {"bounties_week": 2, "bounties": {"feat_through": "2027-04-14"}}
        self.assertEqual(plan(checked, fx.et(2027, 4, 15, 8)), [])
        self.assertEqual(plan(checked, fx.et(2027, 4, 16, 8)), [("bounties", 2)])   # Thursday to check
        all_claimed = checked | {"bounties": {"claimed": {b["id"]: {} for b in comp["bounties"]}}}
        self.assertEqual(plan(all_claimed, fx.et(2027, 4, 19, 8)).count(("bounties", 3)), 0)
        # Before Week 1 is final only the multi-homer check can be due.
        self.assertEqual(plan({"preview_week": 1}, fx.et(2027, 3, 26, 8)), [("bounties", 0)])
        self.assertEqual(items(desk.plan_report(MLB_INFO, rows, base, fx.et(2027, 4, 15, 8), ET, COMP)), [])


class AllItemsTests(DeskBase):
    def test_every_item_previews_and_tests(self) -> None:
        rosters, players = rosters_for(MLB_INFO, 3, ["NYY", "KC"])
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(desk.run("preview", ["monthly", "bounties", "preview"], 3, False,
                                      desk=self.make(FakeFantrax(3, rosters=rosters, players=players,
                                                                 info=MLB_INFO))), 0)
        text = out.getvalue()
        for item in ("monthly", "bounties", "preview"):
            self.assertIn(f"PREVIEW {item} week 3", text)
        self.assertIn("Projected games: ", text)
        sent: list[str] = []
        with patch.object(desk, "send_discord_webhook",
                          lambda s, p: (sent.append(p["embeds"][0]["title"]) or (True, "delivered", "1"))), \
                redirect_stdout(io.StringIO()):
            d = self.make(FakeFantrax(3, info=MLB_INFO))
            d.ctx.test = True
            self.assertEqual(desk.run("test", ["monthly", "bounties"], 3, False, desk=d), 0)
        self.assertEqual(sent, ["[TEST] PSBL Monthly Awards — April 2027 (Month to Date)", "[TEST] PSBL Bounty Board"])
        self.assertFalse(self.state_path.exists())

    def test_workflow_offers_the_new_items(self) -> None:
        workflow = (AUTOMATION.parent / ".github" / "workflows" / "league-competition-desk.yml").read_text()
        for item in desk.ITEMS:
            self.assertIn(item, workflow.split("options: [all,", 1)[1].split("]", 1)[0])


if __name__ == "__main__":
    unittest.main()
