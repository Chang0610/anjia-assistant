import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from knowledge import AREA_DATA, area_references, context_for, extract_constraints


class KnowledgeTest(unittest.TestCase):
    def test_data_scope(self):
        self.assertEqual(len(AREA_DATA["areas"]), 8)
        self.assertTrue(all(not poi["verified"] for a in AREA_DATA["areas"] for group in a["facilities"].values() for poi in group))

    def test_constraints_and_estimates(self):
        messages = [{"role": "user", "content": "公司在张江高科，通勤40分钟内，月租3000元，接受合租"}]
        self.assertEqual(extract_constraints(messages), {"office_hub": "张江高科", "commute_minutes": 40, "monthly_rent": 3000, "shared": True})
        result = area_references(messages)
        self.assertTrue(result["areas"])
        self.assertTrue(all(a["commute_estimate"]["to"] == "张江高科" for a in result["areas"]))
        self.assertTrue(all(a["rent_status"] == "sample_reference" for a in result["areas"]))

    def test_no_claim_for_unknown_office(self):
        evidence = context_for([{"role": "user", "content": "公司在五角场，哪些区域符合30分钟通勤？"}])
        self.assertIsNone(evidence["area_data"]["constraints"]["office_hub"])
        self.assertTrue(all(a["commute_estimate"] is None for a in evidence["area_data"]["areas"]))

    def test_shared_housing_negation(self):
        messages = [{"role": "user", "content": "不接受合租，只想住整租，月租预算4000元"}]
        self.assertFalse(extract_constraints(messages)["shared"])

    def test_plan_request_includes_area_evidence(self):
        messages = [{"role": "user", "content": "请给我一份搬家计划"}]
        profile = {"company_location": "张江高科", "commute_preference": "30-60分钟", "monthly_rent_budget": "3500元", "shared_housing": "是"}
        evidence = context_for(messages, profile)
        self.assertEqual(evidence["area_data"]["constraints"]["commute_minutes"], 60)
        self.assertTrue(evidence["area_data"]["areas"])


if __name__ == "__main__":
    unittest.main()
