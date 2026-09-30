import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from profile import clean_profile, explicit_profile_updates, has_explicit_handover_date, merge_profile
from knowledge import extract_constraints


class ProfileTest(unittest.TestCase):
    def test_move_in_date_is_not_handover_date(self):
        self.assertFalse(has_explicit_handover_date('计划2026年10月14日搬入，10月15日入职'))
        self.assertTrue(has_explicit_handover_date('10月12日交房，10月14日搬入'))
        self.assertIn({'field': 'move_deadline', 'value': '2026年10月14日'}, explicit_profile_updates('计划2026年10月14日搬入，10月15日入职'))

    def test_merge_preserves_old_facts_and_applies_corrections(self):
        current = clean_profile({"company_location": "张江高科", "monthly_rent_budget": "月租3000元", "unknown": "忽略"})
        changed = merge_profile(current, [{"field": "monthly_rent_budget", "value": "月租3500元"}, {"field": "pets", "value": "养猫"}])
        self.assertEqual(changed["company_location"], "张江高科")
        self.assertEqual(changed["monthly_rent_budget"], "月租3500元")
        self.assertEqual(changed["pets"], "养猫")
        self.assertNotIn("unknown", changed)
        self.assertNotIn("pets", merge_profile(changed, [{"field": "pets", "value": None}]))

    def test_saved_constraints_used_when_new_question_omits_them(self):
        profile = {"company_location": "张江高科", "commute_preference": "40分钟内", "monthly_rent_budget": "3500元/月", "shared_housing": "接受合租"}
        constraints = extract_constraints([{"role": "user", "content": "现在有哪些区域可以考虑租房？"}], profile)
        self.assertEqual(constraints, {"office_hub": "张江高科", "commute_minutes": 40, "monthly_rent": 3500, "shared": True})

    def test_explicit_start_date_fallback(self):
        self.assertEqual(explicit_profile_updates("我2026年10月15日入职。"), [{"field": "start_date", "value": "2026年10月15日"}])

    def test_hotline_question_is_not_an_employment_date(self):
        self.assertEqual(explicit_profile_updates("上海电力热线是不是021-95558？入职体检可以直接帮我定项目吗？"), [])
        self.assertEqual(explicit_profile_updates("电话021-12315，入职事项怎么确认？"), [])
        self.assertEqual(explicit_profile_updates("我10-15入职。"), [{"field": "start_date", "value": "10-15"}])

    def test_latest_move_and_employment_dates_are_captured_together(self):
        self.assertEqual(
            explicit_profile_updates("把搬家完成时间改到2026年10月2日，入职时间仍是2026年10月7日"),
            [
                {"field": "start_date", "value": "2026年10月7日"},
                {"field": "move_deadline", "value": "2026年10月2日"},
            ],
        )

    def test_task_reminder_date_is_not_mistaken_for_employment_date(self):
        self.assertEqual(explicit_profile_updates("把向单位确认入职这个任务改到10月10日上午9点提醒"), [])
        updates = explicit_profile_updates("接受入职后搬家（目标2026-10-18），核验过渡条件", date(2026, 9, 23))
        self.assertIn({"field": "move_deadline", "value": "2026-10-18"}, updates)
        self.assertFalse(any(item["field"] == "start_date" for item in updates))

    def test_housing_handover_and_status_are_captured(self):
        updates = explicit_profile_updates("我已经找到房子了，10月15号交房。", date(2026, 9, 23))
        self.assertIn({"field": "housing_handover_date", "value": "10月15号"}, updates)
        self.assertIn({"field": "current_housing", "value": "我已经找到房子了，10月15号交房。"}, updates)
        delayed = explicit_profile_updates("房东说交房晚了三天，改到10月20日了。", date(2026, 9, 23))
        self.assertIn({"field": "housing_handover_date", "value": "10月20日"}, delayed)
        extended = explicit_profile_updates("交房从10月12日延到10月14日，宽带已经约好了。", date(2026, 9, 23))
        self.assertIn({"field": "housing_handover_date", "value": "10月14日"}, extended)

    def test_half_day_and_relative_full_process_deadline_are_captured(self):
        self.assertIn(
            {"field": "availability_constraints", "value": "周末仅半天可用，约3–4小时"},
            explicit_profile_updates("这个周末我只有半天有空，帮我重新安排。"),
        )
        updates = explicit_profile_updates("我今天（10月9日）开始规划，希望2周内完成搬家全流程，10月19日入职。", date(2026, 9, 23))
        self.assertIn({"field": "planning_start_date", "value": "2026-10-09"}, updates)
        self.assertIn({"field": "full_process_deadline", "value": "2026-10-23"}, updates)

    def test_new_profile_choices_drive_area_constraints(self):
        profile = {"company_location": "张江高科", "commute_preference": "30-60分钟", "monthly_rent_budget": "3500元", "shared_housing": "否"}
        constraints = extract_constraints([{"role": "user", "content": "哪些区域适合我？"}], profile)
        self.assertEqual(constraints, {"office_hub": "张江高科", "commute_minutes": 60, "monthly_rent": 3500, "shared": False})


if __name__ == "__main__":
    unittest.main()
