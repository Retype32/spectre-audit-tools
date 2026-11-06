"""
tests/test_agent.py — the agent toolkit: tools, registry, privacy, End of Day
summary and command line. All names and figures are fictional; every file is
written to a temporary folder. Everyone works 8-hour shifts.
"""
import contextlib
import datetime
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import pandas as pd

import scoring
from agent import tools as T
from agent.__main__ import main as cli
from agent.privacy import Pseudonymiser
from agent.registry import TOOLS, run_tool, tool_definitions
from agent.summary import end_of_day_summary
from engine.bags import save_bag_day
from engine.targets import save_targets

TODAY = datetime.date(2026, 6, 20)


class _Data(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        p = lambda n: os.path.join(self.dir, n)  # noqa: E731
        hist = [
            ("18.06.2026", "Alice", "1001", 200, 500000, "VMS"),
            ("18.06.2026", "Bob", "1002", 100, 300000, "VMS"),
            ("18.06.2026", "Zed", "1009", 45, 1500000, "VMS"),     # 360
            ("19.06.2026", "Alice", "1001", 220, 550000, "VMS"),
            ("19.06.2026", "Bob", "1002", 120, 330000, "VMS"),
            ("19.06.2026", "Dan", "1004", 90, 100000, "ISA"),      # not VMS
            ("20.06.2026", "Alice", "1001", 160, 400000, "VMS"),
            ("20.06.2026", "Bob", "1002", 140, 350000, "VMS"),
        ]
        pd.DataFrame(hist, columns=["Date", "Name", "Operator_Id", "System Count",
                                    "Total Value", "Format"]).to_csv(p("hist.csv"), index=False)
        save_bag_day("19.06.2026", 80, 0, p("bags.csv"))
        save_bag_day("20.06.2026", 100, 5, p("bags.csv"))
        save_targets({"team_score": "80", "min_cashier_score": "70"}, p("targets.json"))
        pd.DataFrame([("19.06.2026", "Bob", "", "small_mistake", "3", "", "x")],
                     columns=["date", "cashier", "operator_id", "type", "severity_points",
                              "notes", "logged_at"]).to_csv(p("mistakes.csv"), index=False)
        pd.DataFrame([("20.06.2026|1002|S9|250.0", "Bob", "confirmed", "x")],
                     columns=["key", "cashier", "verdict", "reviewed_at"]).to_csv(p("verdicts.csv"), index=False)
        for target, attr, value in [
            (T, "HISTORY_FILE", p("hist.csv")), (T, "BAG_LOG_FILE", p("bags.csv")),
            (T, "TARGETS_PATH", p("targets.json")), (T, "VERDICTS_FILE", p("verdicts.csv")),
            (scoring, "MISTAKES_DB", p("mistakes.csv")),
            (scoring, "DUPLICATE_VERDICTS_DB", p("verdicts.csv")),
        ]:
            patcher = mock.patch.object(target, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)


class TestTools(_Data):
    def test_team_overview(self):
        o = T.team_overview("This Week", today=TODAY)
        self.assertEqual((o["working_days"], o["cashiers"], o["slips"]), (3, 2, 940))
        self.assertEqual(o["bags"], {"logged_days": 2, "cleared_days": 1, "bags_in": 180,
                                     "carried_over": 5})
        self.assertEqual(o["not_scored"], {"days_360": 1, "cashiers_360": ["Zed"],
                                           "other_format_days": 1})

    def test_bad_period(self):
        with self.assertRaises(T.ToolError):
            T.team_overview("Fortnight", today=TODAY)

    def test_targets_vs_actual(self):
        items = {i["target"]: i for i in T.targets_vs_actual("This Week", today=TODAY)["items"]}
        team, lowest = items["Team score"], items["Lowest acceptable cashier score"]
        self.assertEqual((team["actual"], team["target_value"], team["gap"], team["met"]),
                         (83, 80, 3, True))
        self.assertEqual((lowest["actual"], lowest["met"], lowest["who_misses_it"]), (71, True, []))
        rate = items["Slips per hour (VMS)"]
        self.assertEqual((rate["target_value"], rate["met"], rate["who_misses_it"]), (25, False, ["Bob"]))
        carry = items["Bags carried over per day"]
        self.assertEqual((carry["actual"], carry["met"], carry["who_misses_it"]), (2.5, False, ["20.06.2026"]))

    def test_ranking_lowest_first_with_reasons(self):
        r = T.cashier_ranking("This Week", lowest_first=True, today=TODAY)
        first = r["cashiers"][0]
        self.assertEqual((first["name"], first["rank"], r["team_size"]), ("Bob", 2, 2))
        self.assertEqual(first["why"][0]["factor"], "slips per hour")
        self.assertTrue(all(a["points_lost"] >= b["points_lost"]
                            for a, b in zip(first["why"], first["why"][1:])))

    def test_profile(self):
        p = T.cashier_profile("bob", "This Week", today=TODAY)
        self.assertTrue(p["found"])
        self.assertEqual([d["date"] for d in p["daily"]], ["18.06.2026", "19.06.2026", "20.06.2026"])
        self.assertEqual(sorted(m["type"] for m in p["mistake_list"]), ["Duplicate Slip", "Small Mistake"])
        self.assertEqual(p["penalty"], 23)
        self.assertIn("this_month_cash", p)

    def test_profile_not_found_or_ambiguous(self):
        self.assertEqual(T.cashier_profile("Zoe", "This Week", today=TODAY)["cashiers_in_period"],
                         ["Alice", "Bob"])
        self.assertTrue(T.cashier_profile("ali", "This Week", today=TODAY)["found"])

    def test_day_summary_cleared_day(self):
        d = T.day_summary("19.06.2026", today=TODAY)
        self.assertEqual(d["bags"]["cleared"], True)
        self.assertLess(d["slip_target_per_hour"], 25)                # team's own pace
        self.assertEqual((d["best"]["name"], d["lowest"]["name"]), ("Alice", "Bob"))
        self.assertLessEqual(d["best"]["score"], 90)                  # no consistency bonus
        self.assertEqual(d["other_format"], [{"name": "Dan", "format": "ISA", "slips": 90}])
        self.assertEqual(d["mistakes_logged"], [{"cashier": "Bob", "type": "Small Mistake", "points": 3}])

    def test_day_summary_duplicates_and_360(self):
        self.assertEqual(T.day_summary("20.06.2026", today=TODAY)["confirmed_duplicates"], ["Bob"])
        self.assertEqual(T.day_summary("18.06.2026", today=TODAY)["processing_360"],
                         [{"name": "Zed", "slips": 45, "cash": 1500000.0}])

    def test_monthly_cash_leaders(self):
        m = T.monthly_cash_leaders("2026-06", today=TODAY)
        # Alice: €1.45m over 24 h = €60k/hr; Bob: €0.98m over 24 h = €41k/hr
        self.assertEqual([x["name"] for x in m["leaders"]], ["Alice", "Bob"])
        self.assertEqual(m["leaders"][0]["cash_per_hour"], 60417.0)
        self.assertIn("mainly speed", m["leaders"][0]["why"])
        self.assertEqual(m["team"]["days_360"], 1)


class TestSummary(_Data):
    def test_end_of_day_text(self):
        text = end_of_day_summary("19.06.2026", today=TODAY)
        for expected in ("End of Day — Friday 19.06.2026", "80 in, 0 carried over — cleared",
                         "team's own pace", "Team score:", "Best: Alice",
                         "Needs most attention: Bob", "Not VMS (not scored): Dan — ISA",
                         "Mistakes logged: Bob — Small Mistake (−3).", "Last 7 days:"):
            self.assertIn(expected, text)

    def test_day_without_data(self):
        text = end_of_day_summary("01.06.2026", today=TODAY)
        self.assertIn("not logged", text)
        self.assertIn("No VMS cashier work recorded", text)


class TestRegistry(_Data):
    def test_definitions_match_tools(self):
        defs = {d["name"]: d for d in tool_definitions()}
        self.assertEqual(set(defs), set(TOOLS))
        self.assertEqual(defs["cashier_profile"]["input_schema"]["required"], ["name"])
        self.assertFalse(defs["team_overview"]["input_schema"]["additionalProperties"])

    def test_run_tool_and_log(self):
        logs = os.path.join(self.dir, "logs")
        ok = run_tool("monthly_cash_leaders", {"month": "2026-06"}, log_dir=logs)
        self.assertEqual(ok["month"], "2026-06")
        bad = [run_tool("nope", {}, log_dir=logs),
               run_tool("team_overview", {"period": "Fortnight"}, log_dir=logs),
               run_tool("team_overview", {"colour": "red"}, log_dir=logs),
               run_tool("cashier_profile", {}, log_dir=logs)]
        self.assertTrue(all("error" in b for b in bad))
        lines = open(os.path.join(logs, os.listdir(logs)[0]), encoding="utf-8").read().splitlines()
        self.assertEqual([json.loads(x)["ok"] for x in lines], [True, False, False, False, False])
        self.assertNotIn("Bob", lines[0])                             # results aren't logged

    def test_cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli(["tools"]), 0)
            self.assertEqual(cli(["run", "monthly_cash_leaders", '{"month": "2026-06"}']), 0)
            self.assertEqual(cli(["run", "team_overview", "not json"]), 2)
        self.assertIn("day_summary", out.getvalue())


class TestPrivacy(unittest.TestCase):
    def setUp(self):
        self.p = Pseudonymiser({"1001": "Anna Example", "1003": "Will Sample", "1004": "Ann Other"})

    def test_hide_and_reveal(self):
        hidden = self.p.hide({"q": "How is anna example doing?", "names": ["Will Sample"]})
        self.assertEqual(hidden, {"q": "How is Cashier 1001 doing?", "names": ["Cashier 1003"]})
        self.assertEqual(self.p.reveal("Cashier 1001 and Cashier 1003"),
                         "Anna Example and Will Sample")

    def test_first_names_only_when_capitalised(self):
        self.assertEqual(self.p.hide("Is Anna late? She will be."),
                         "Is Cashier 1001 late? She will be.")

    def test_similar_aliases_dont_collide(self):
        p = Pseudonymiser({"1": "Al Short", "10": "Bea Long"})
        self.assertEqual(p.reveal("Cashier 10 and Cashier 1"), "Bea Long and Al Short")

    def test_names_not_in_database(self):
        self.p.add_names(["Zed Unknown"])
        self.assertEqual(self.p.hide("Zed Unknown"), "Cashier X1")
        self.assertEqual(self.p.reveal("Cashier X1"), "Zed Unknown")


if __name__ == "__main__":
    unittest.main()
