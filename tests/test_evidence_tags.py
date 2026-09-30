import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from evidence_tags import annotate_answer


class EvidenceTagTest(unittest.TestCase):
    def test_only_known_official_url_is_verified(self):
        official = "https://example.gov/known"
        evidence = {"policies": [{"source": official, "status": "官方来源已核验"}]}
        answer = "事项详情\n信息依据或入口：https://example.com/unknown\n信息依据或入口：" + official
        tags = annotate_answer(answer, evidence)
        self.assertEqual(tags[0]["tags"], ["入口或依据待核验"])
        self.assertIsNone(tags[0]["verified_url"])
        self.assertEqual(tags[1]["tags"], ["官方来源已核验"])
        self.assertEqual(tags[1]["verified_url"], official)

    def test_estimate_and_pending_are_distinguished(self):
        answer = "信息依据或入口：通勤估算，租金待核验，配套待地图核验\n信息依据或入口：信息待确认"
        tags = annotate_answer(answer, {})
        self.assertEqual(tags[0]["tags"], ["通勤估算", "配套待核验", "部分信息待确认"])
        self.assertEqual(tags[1]["tags"], ["信息待确认"])
