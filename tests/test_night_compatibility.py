"""夜勤相性は片側の登録だけで両方向に適用する。"""

import unittest
from unittest.mock import patch

from services.shift_generator import _Generator, _symbol_work_key
from test_shift_generator import counts, generate, settings_for, staff_member


class NightCompatibilityTests(unittest.TestCase):
    def assert_no_shared_night(self, engine, left_id, right_id):
        for day in engine.period_dates:
            self.assertFalse(
                all(_symbol_work_key(engine.grid[(sid, day)], engine.settings) == "night"
                    for sid in (left_id, right_id)),
                f"{day}: {left_id} と {right_id} が同じ夜勤",
            )

    def test_one_sided_setting_blocks_either_assignment_order(self):
        staff = [staff_member(1, 4), staff_member(2, 4)]
        staff[0]["night_incompatible_ids"] = [2]
        for first, second in ((1, 2), (2, 1)):
            for symbol in ("夜", "準夜"):
                with self.subTest(first=first, symbol=symbol):
                    with patch("services.shift_generator.list_staff", return_value=staff):
                        engine = _Generator(2026, 9, settings_for())
                    engine._phase_manual({(first, "2026-09-01"): {"symbol": symbol, "source": "manual"}})
                    self.assertFalse(engine._can_work(staff[second - 1], "night", "2026-09-01"))

    def test_both_staffing_modes_respect_pairs_and_fixed_counts(self):
        for mode in ("work_type", "time_slot"):
            with self.subTest(mode=mode):
                staff = [staff_member(sid, 5) for sid in range(1, 13)]
                staff[0]["night_incompatible_ids"] = [2]
                engine, _ = generate(staff, settings_for(mode, night_staff=2), seed=0)
                self.assert_no_shared_night(engine, 1, 2)
                for member in staff:
                    self.assertEqual(engine.night_counts[member["id"]], 5)
                    self.assertEqual(counts(engine, member["id"])["off"], 8)
                for day in engine.period_dates:
                    self.assertGreaterEqual(engine._count_work_on_day(day, "night"), 2)

    def test_fixed_quota_top_up_does_not_override_pair_constraint(self):
        staff = [staff_member(1, 1), staff_member(2, 1)]
        staff[0]["night_incompatible_ids"] = [2]
        existing = {
            (1, "2026-09-01"): {"symbol": "夜", "source": "manual"},
            (2, "2026-09-02"): {"symbol": "明", "source": "manual"},
            (2, "2026-09-03"): {"symbol": "×", "source": "manual"},
        }
        # 職員2が追加可能な夜勤は1日だけ。NGを無視して固定回数を埋めない。
        existing.update({(2, f"2026-09-{day:02d}"): {"symbol": "×", "source": "leave"}
                         for day in range(4, 31)})
        engine, result = generate(staff, settings_for(night_staff=0, day_staff=0), existing)
        self.assert_no_shared_night(engine, 1, 2)
        self.assertEqual(engine.night_counts[2], 0)
        self.assertTrue(any(w["code"] == "night_count_shortfall" for w in result["warnings"]))

    def test_staffing_shortage_does_not_override_pair_constraint(self):
        staff = [staff_member(1, 5), staff_member(2, 5)]
        staff[0]["night_incompatible_ids"] = [2]
        for mode in ("work_type", "time_slot"):
            with self.subTest(mode=mode):
                engine, result = generate(staff, settings_for(mode, night_staff=2), seed=0)
                self.assert_no_shared_night(engine, 1, 2)
                self.assertTrue(any(w["code"] in {"understaffed", "time_slot_understaffed"}
                                    for w in result["warnings"]))

    def test_manual_conflicts_are_preserved_and_reported_once_per_pair(self):
        staff = [staff_member(1, 2), staff_member(2, 2)]
        staff[0]["night_incompatible_ids"] = [2]
        staff[1]["night_incompatible_ids"] = [1]
        existing = {(sid, day): {"symbol": "準夜" if sid == 2 else "夜", "source": "manual"}
                    for sid in (1, 2) for day in ("2026-09-01", "2026-09-08")}
        engine, result = generate(staff, settings_for(night_staff=0, day_staff=0), existing)
        assignments = {(sid, day): (symbol, source) for sid, day, symbol, source in result["assignments"]}
        for key, cell in existing.items():
            self.assertEqual(assignments[key], (cell["symbol"], cell["source"]))
        warnings = [w for w in result["warnings"] if w["code"] == "night_incompatibility_conflict"]
        self.assertEqual(len(warnings), 1)
        for expected in ("職員1", "職員2", "2026-09-01", "2026-09-08"):
            self.assertIn(expected, warnings[0]["message"])

    def test_compatible_staff_can_share_night_and_ignored_ids_do_not_self_block(self):
        staff = [staff_member(1, 4), staff_member(2, 4)]
        staff[0]["night_incompatible_ids"] = [1, 999]
        with patch("services.shift_generator.list_staff", return_value=staff):
            engine = _Generator(2026, 9, settings_for())
        engine._phase_manual({(1, "2026-09-01"): {"symbol": "夜", "source": "manual"}})
        self.assertTrue(engine._can_work(staff[1], "night", "2026-09-01"))
        self.assertTrue(engine._can_work(staff[0], "night", "2026-09-08"))

    def test_pair_setting_does_not_block_daytime_work_or_a_different_night(self):
        staff = [staff_member(1, 4), staff_member(2, 4)]
        staff[0]["night_incompatible_ids"] = [2]
        with patch("services.shift_generator.list_staff", return_value=staff):
            engine = _Generator(2026, 9, settings_for())
        engine._phase_manual({(1, "2026-09-01"): {"symbol": "夜", "source": "manual"}})
        self.assertTrue(engine._can_work(staff[1], "day", "2026-09-01"))
        self.assertTrue(engine._can_work(staff[1], "night", "2026-09-02"))

    def test_day_incompatibility_also_blocks_nights_in_either_direction(self):
        staff = [staff_member(1, 4), staff_member(2, 4)]
        staff[0]["day_incompatible_ids"] = [2]
        with patch("services.shift_generator.list_staff", return_value=staff):
            engine = _Generator(2026, 9, settings_for())
        engine._phase_manual({(1, "2026-09-01"): {"symbol": "夜", "source": "manual"}})
        self.assertFalse(engine._can_work(staff[1], "night", "2026-09-01"))


if __name__ == "__main__":
    unittest.main()
