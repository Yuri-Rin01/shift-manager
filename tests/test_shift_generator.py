"""Run with: python -m unittest discover -s tests -v."""

import unittest
from collections import Counter
from copy import deepcopy
from unittest.mock import patch

from data.settings_defaults import DEFAULT_SETTINGS
from data.shift_symbols import symbol_to_key
from services.shift_generator import _Generator


def settings_for(mode="work_type", *, off_days=8, night_staff=1, day_staff=1):
    settings = deepcopy(DEFAULT_SETTINGS)
    settings.update(
        staffing_requirement_mode=mode,
        off_days_per_period=off_days,
        require_leader_on_night=False,
        min_staff_by_work_type={key: 0 for key in ("early", "day", "late", "night")},
        min_staff_by_floor={
            f"{floor}F": {
                "early": 0, "day": day_staff if floor == 1 else 0,
                "late": 0, "night": night_staff if floor == 1 else 0,
            }
            for floor in range(1, 5)
        },
        time_slot_staffing_rules=[
            {"label": "日勤帯", "start_time": "09:00", "end_time": "16:00", "min_staff": day_staff, "floor": "1F"},
            {"label": "夜勤帯", "start_time": "16:30", "end_time": "09:00", "min_staff": night_staff, "floor": "1F"},
        ],
    )
    return settings


def staff_member(sid, nights=None):
    return {
        "id": sid, "name": f"職員{sid}", "departments": ["1F"],
        "can_work_night": nights is not None,
        "fix_night_shift_count": nights is not None,
        "night_shift_count": nights,
        "staffing_basis": {"day": 60, "night": 40} if nights is not None else {"day": 100},
    }


def generate(staff, settings, existing=None, *, seed=1, year=2026, month=9):
    with patch("services.shift_generator.list_staff", return_value=staff):
        engine = _Generator(year, month, settings)
        engine._rng.seed(seed)
        result = engine.run(existing or {})
    return engine, result


def counts(engine, sid):
    return Counter(symbol_to_key(engine.grid.get((sid, day), ""), engine.settings) for day in engine.period_dates)


class ShiftGeneratorTests(unittest.TestCase):
    def test_fixed_nights_and_visible_off_counts_in_both_modes(self):
        for mode in ("work_type", "time_slot"):
            with self.subTest(mode=mode):
                staff = [staff_member(sid, n) for sid, n in enumerate([8, 6, 4, 4, 4, 4], 1)]
                engine, result = generate(staff, settings_for(mode))
                for member in staff:
                    actual = counts(engine, member["id"])
                    self.assertEqual(actual["night"], member["night_shift_count"])
                    self.assertEqual(actual["off"], 8)
                self.assertEqual(len(result["assignments"]), 6 * 30)
                for day in engine.period_dates:
                    self.assertGreaterEqual(engine._count_work_on_day(day, "night", floor="1F"), 1)
                    self.assertGreaterEqual(engine._count_work_on_day(day, "day", floor="1F"), 1)

    def test_zero_fixed_nights_are_never_used_to_fill_shortages(self):
        for mode in ("work_type", "time_slot"):
            with self.subTest(mode=mode):
                engine, result = generate([staff_member(1, 0), staff_member(2, 2)], settings_for(mode))
                self.assertEqual(counts(engine, 1)["night"], 0)
                self.assertEqual(counts(engine, 2)["night"], 2)
                self.assertTrue(any(w["code"] in {"understaffed", "time_slot_understaffed"} for w in result["warnings"]))

    def test_off_days_are_spread_across_the_calendar(self):
        staff = [staff_member(sid) for sid in range(1, 11)]
        engine, _ = generate(staff, settings_for(night_staff=0, day_staff=6))
        for member in staff:
            sid = member["id"]
            self.assertEqual(counts(engine, sid)["off"], 8)
            off_indices = [i for i, d in enumerate(engine.period_dates) if symbol_to_key(engine.grid[(sid, d)], engine.settings) == "off"]
            boundaries = [-1, *off_indices, 30]
            self.assertLessEqual(max(b - a - 1 for a, b in zip(boundaries, boundaries[1:])), 5)
        for day in engine.period_dates:
            self.assertGreaterEqual(engine._count_work_on_day(day, "day"), 6)

    def test_manual_and_requested_leave_survive_night_chains(self):
        existing = {
            (1, "2026-09-01"): {"symbol": "夜", "source": "manual"},
            (1, "2026-09-02"): {"symbol": "×", "source": "leave"},
            (1, "2026-09-10"): {"symbol": "有休", "source": "leave"},
            (1, "2026-09-20"): {"symbol": "○", "source": "manual"},
        }
        for rows in (existing, dict(reversed(list(existing.items())))):
            engine, result = generate([staff_member(1, 4)], settings_for(night_staff=0, day_staff=0), rows)
            assignments = {(sid, day): (symbol, source) for sid, day, symbol, source in result["assignments"]}
            for key, cell in existing.items():
                self.assertEqual(assignments[key], (cell["symbol"], cell["source"]))
            self.assertEqual(counts(engine, 1)["night"], 4)
            self.assertTrue(any(w["code"] == "night_chain_conflict" for w in result["warnings"]))

    def test_automatic_offs_remain_automatic_when_regenerating(self):
        staff = [staff_member(1), staff_member(2)]
        settings = settings_for(night_staff=0, day_staff=0)
        _, first = generate(staff, settings)
        self.assertTrue(all(source == "auto" for _, _, _, source in first["assignments"]))
        existing = {(sid, day): {"symbol": sym, "source": source} for sid, day, sym, source in first["assignments"]}
        settings["off_days_per_period"] = 6
        engine, _ = generate(staff, settings, existing)
        self.assertEqual(counts(engine, 1)["off"], 6)
        self.assertEqual(counts(engine, 2)["off"], 6)

    def test_custom_public_off_symbol_is_counted_and_generated(self):
        settings = settings_for(night_staff=0, day_staff=0)
        settings["shift_symbols"]["off"] = "休"
        engine, _ = generate([staff_member(1, 4)], settings)
        self.assertEqual(counts(engine, 1)["off"], 8)
        self.assertNotIn("×", engine.grid.values())

    def test_manual_work_does_not_reduce_monthly_work_or_night_targets(self):
        existing = {(1, f"2026-09-{day:02d}"): {"symbol": "○", "source": "manual"} for day in (1, 4, 7, 10, 13)}
        engine, _ = generate([staff_member(1, 5)], settings_for(night_staff=0, day_staff=0), existing)
        actual = counts(engine, 1)
        self.assertEqual(actual["night"], 5)
        self.assertEqual(actual["off"], 8)
        self.assertEqual(actual["day"] + actual["night"] + actual["morning_off"], 22)

    def test_night_assignment_checks_the_whole_recovery_chain(self):
        settings = settings_for()
        member = staff_member(1, 5)
        for offset, symbol, source in ((1, "×", "leave"), (1, "有休", "leave"), (1, "○", "manual"), (2, "○", "manual"), (2, "夜", "manual")):
            with self.subTest(offset=offset, symbol=symbol):
                with patch("services.shift_generator.list_staff", return_value=[member]):
                    engine = _Generator(2026, 9, settings)
                engine._phase_manual({(1, f"2026-09-{10 + offset:02d}"): {"symbol": symbol, "source": source}})
                self.assertFalse(engine._can_work(member, "night", "2026-09-10"))

    def test_consecutive_work_checks_both_sides_of_a_gap(self):
        member = staff_member(1)
        with patch("services.shift_generator.list_staff", return_value=[member]):
            engine = _Generator(2026, 9, settings_for())
        engine._phase_manual({(1, f"2026-09-{day:02d}"): {"symbol": "○", "source": "manual"} for day in (1, 2, 3, 5, 6)})
        self.assertFalse(engine._can_work(member, "day", "2026-09-04"))

    def test_infeasible_fixed_count_reports_original_target_after_generation(self):
        member = staff_member(1, 10)
        settings = settings_for(night_staff=0, day_staff=0)
        settings["max_night_per_week"] = 1
        engine, result = generate([member], settings)
        actual = counts(engine, 1)["night"]
        self.assertLess(actual, 10)
        warnings = [w for w in result["warnings"] if w["code"] == "night_count_shortfall"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("10", warnings[0]["message"])
        self.assertIn(str(actual), warnings[0]["message"])

    def test_manual_nights_above_fixed_count_are_preserved_and_reported(self):
        existing = {(1, f"2026-09-{day:02d}"): {"symbol": "夜", "source": "manual"} for day in (1, 8, 15)}
        engine, result = generate([staff_member(1, 2)], settings_for(night_staff=0, day_staff=0), existing)
        self.assertEqual(counts(engine, 1)["night"], 3)
        self.assertTrue(any(w["code"] == "night_count_excess" for w in result["warnings"]))

    def test_eight_fixed_nights_do_not_depend_on_random_placement_order(self):
        for seed in (3, 7):
            with self.subTest(seed=seed):
                engine, _ = generate([staff_member(1, 8)], settings_for(night_staff=0, day_staff=0), seed=seed)
                self.assertEqual(counts(engine, 1)["night"], 8)
                self.assertEqual(counts(engine, 1)["off"], 8)

    def test_recovery_from_manual_night_is_saved_as_automatic(self):
        existing = {(1, "2026-09-01"): {"symbol": "夜", "source": "manual"}}
        _, result = generate([staff_member(1, 4)], settings_for(night_staff=0, day_staff=0), existing)
        assignments = {(sid, day): (symbol, source) for sid, day, symbol, source in result["assignments"]}
        self.assertEqual(assignments[(1, "2026-09-03")], ("×", "auto"))
        self.assertEqual(result["stats"]["leave_locked"], 0)

    def test_semi_nights_share_the_fixed_quota(self):
        staff = staff_member(1, 4)
        staff["staffing_basis"] = {"day": 60, "semi_night": 40}
        existing = {(1, "2026-09-01"): {"symbol": "準夜", "source": "manual"}}
        engine, _ = generate([staff], settings_for(night_staff=0, day_staff=0), existing)
        actual = counts(engine, 1)
        self.assertEqual(actual["night"] + actual["semi_night"], 4)
        self.assertEqual(actual["off"], 8)

    def test_excess_visible_offs_are_not_hidden_by_padding(self):
        settings = settings_for(night_staff=0, day_staff=0)
        settings["visible_work_types"].update(early=False, day=False, late=False)
        engine, result = generate([staff_member(1)], settings)
        self.assertEqual(counts(engine, 1)["off"], 30)
        warnings = [w for w in result["warnings"] if w["code"] == "off_count_excess"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("30", warnings[0]["message"])

    def test_period_crossing_a_month_keeps_exact_counts_and_week_limits(self):
        settings = settings_for(night_staff=0, day_staff=0)
        settings.update(calendar_start_day=16, week_start="monday")
        engine, _ = generate([staff_member(1, 8)], settings)
        self.assertEqual(engine.period_dates[0], "2026-09-16")
        self.assertEqual(engine.period_dates[-1], "2026-10-15")
        self.assertEqual(counts(engine, 1)["night"], 8)
        self.assertEqual(counts(engine, 1)["off"], 8)
        self.assertTrue(all(count <= 2 for count in engine.week_nights.values()))


if __name__ == "__main__":
    unittest.main()
