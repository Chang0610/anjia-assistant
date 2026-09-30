import io
import json
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from knowledge import CITY_KNOWLEDGE, context_for
from evidence_tags import annotate_answer
from server import openai_answer


def evidence(question):
    return context_for([{"role": "user", "content": question}])


class ImportedKnowledgeTest(unittest.TestCase):
    def test_snapshot_and_references(self):
        self.assertEqual(Counter(r["status"] for r in CITY_KNOWLEDGE["knowledge_entries"]),
                         {"verified": 31, "pending_verification": 26, "sample_reference": 2})
        self.assertEqual(len(CITY_KNOWLEDGE["entries"]), 41)
        self.assertEqual(len(CITY_KNOWLEDGE["task_templates"]), 12)
        ids = {r["id"] for r in CITY_KNOWLEDGE["entries"]}
        for row in CITY_KNOWLEDGE["knowledge_entries"]:
            self.assertTrue(set(row.get("entry_ids") or []) <= ids)

    def test_rent_round_two_and_pending_amount(self):
        city = evidence("没有网签可以提取公积金吗")["city_knowledge"]
        rows = {r["id"]: r for r in city["knowledge_entries"]}
        self.assertEqual(rows["ke_rent_001"]["status"], "verified")
        self.assertEqual(rows["ke_rent_006"]["status"], "pending_verification")
        self.assertIn("4000", json.dumps(rows["ke_rent_006"], ensure_ascii=False))
        self.assertEqual(rows["ke_rent_015"]["status"], "pending_verification")
        self.assertEqual({g["id"] for g in city["data_gaps"] if g["severity"] == "P0"}, {"dg_grad_001"})
        rent = next(t for t in city["task_templates"] if t["template_id"] == "tpl_rent")
        self.assertIn("ke_rent_001", rent["available_knowledge_entry_ids"])

    def test_hotlines_and_incomplete_records(self):
        city = evidence("电力热线和货拉拉搬家")["city_knowledge"]
        rows = {r["id"]: r for r in city["knowledge_entries"]}
        power = rows["hotline-electricity-001"]
        self.assertEqual(power["status"], "verified")
        self.assertIn("95598", power["summary"])
        self.assertTrue(power["evidence"][0]["url"])
        self.assertEqual(rows["moving-huolala-001"]["status"], "pending_verification")
        self.assertEqual(rows["moving-huolala-001"]["imported_status"], "verified")
        incomplete = next(e for e in city["entries"] if e["id"] == "entry-ziroom-001")
        self.assertEqual(incomplete["status"], "pending_verification")

    def test_topic_history_and_price_gaps(self):
        result = context_for([{"role": "user", "content": "我要带猫搬去上海"},
                              {"role": "assistant", "content": "请确认日期"},
                              {"role": "user", "content": "下个月"}])
        self.assertIn("宠物", {r["category"] for r in result["city_knowledge"]["knowledge_entries"]})
        result = evidence("水电燃气宽带费用")
        self.assertTrue(all(r["data_status"] == "pending_verification"
                            for r in result["utilities"] if r["utility"] == "gas"))

    def test_shared_url_does_not_upgrade_pending_policy(self):
        data = evidence("租房公积金")
        row = next(r for r in data["city_knowledge"]["knowledge_entries"] if r["id"] == "ke_rent_006")
        labels = annotate_answer("信息依据或入口：" + row["evidence"][0]["url"], data)
        self.assertIn("信息待确认", labels[0]["tags"])
        self.assertNotIn("知识来源已核验", labels[0]["tags"])

    def test_model_request_contains_actual_new_evidence(self):
        question = "电力热线是什么，入职体检怎么安排，租房公积金和落户怎么核验"
        captured = {}
        def respond(request, **kwargs):
            captured.update(json.loads(request.data))
            return io.BytesIO(json.dumps({"output": [{"type": "message", "content": [{
                "type": "output_text", "text": json.dumps({
                    "answer": "向HR核验", "operations": [], "profile_updates": []
                })}]}]}).encode())
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}), patch("urllib.request.urlopen", respond):
            openai_answer([{"role": "user", "content": question}], evidence(question), {}, {})
        payload = captured["input"][0]["content"]
        for term in ("hotline-electricity-001", "ke_health_001", "ke_rent_006", "dg_grad_001", "tpl_rent", "fallback"):
            self.assertIn(term, payload)
        self.assertIn("pending_verification", captured["instructions"])
        self.assertIn("不承诺资格", captured["instructions"])


if __name__ == "__main__":
    unittest.main()
