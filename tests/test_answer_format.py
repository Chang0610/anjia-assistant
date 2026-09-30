import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from server import attach_operation_sources, compose_answer, conflict_quick_choices, enforce_response_mode, follow_up_questions, structured_answer_sources, CALENDAR_SCHEMA


class AnswerFormatTest(unittest.TestCase):
    def test_hard_deadline_conflict_has_concrete_choices(self):
        choices = conflict_quick_choices(['旧住处退租交接（硬截止 2026-10-12）早于完成搬家（2026-10-13）'])
        self.assertEqual(choices, ['把搬家提前到2026-10-11', '先核验旧住处交接与临时存放安排'])

    def test_follow_ups_only_contain_answerable_questions(self):
        raw = [
            '补充月租预算和通勤偏好后，再进行区域匹配。',
            '核对旧住处租赁合同中的退租通知期、验房和服务终止条款。',
            '你的每月租房预算是多少？',
            '旧住处退租需要提前多少天通知房东？',
        ]
        self.assertEqual(follow_up_questions(raw), raw[2:])
        answer = compose_answer({'response_mode': 'C', 'answer': '目前信息总结：待补充。', 'advice_items': [{
            'title': '确认租房条件', 'why': '便于筛选区域', 'when': '租房前',
            'prerequisite': '公司位置', 'completion': '预算确定', 'basis': '信息待确认',
        }], 'follow_ups': raw})
        self.assertIn('最后追问：\n1. 你的每月租房预算是多少？', answer)
        self.assertNotIn('补充月租预算和通勤偏好后', answer)

    def test_sources_are_bound_to_advice_and_unverified_urls_are_not_linked(self):
        result = {"answer": "目前信息总结：先核验。", "advice_items": [{"title": "核验公积金", "why": "入职", "when": "入职后", "prerequisite": "入职", "completion": "查到缴存记录", "basis": "首次就业从第二个月起", "sources": [
            {"source_name": "上海公积金中心", "source_url": "https://example.gov.cn/rule", "source_status": "官方来源已核验", "verified_at": "2099-01-01"},
            {"source_name": "未知站点", "source_url": "https://made-up.example/rule", "source_status": "官方来源已核验", "verified_at": "2099-01-01"},
        ]}]}
        answer = compose_answer(result)
        evidence = {"policies": [{"topic": "公积金", "source": "https://example.gov.cn/rule", "status": "官方来源已核验"}]}
        sources = structured_answer_sources(answer, result, evidence)[0]["sources"]
        self.assertEqual(sources[0]["source_url"], "https://example.gov.cn/rule")
        self.assertEqual(sources[0]["verified_at"], "")
        self.assertEqual(sources[1]["source_url"], "")
        self.assertEqual(sources[1]["source_status"], "信息待确认")

    def test_operation_schema_contains_range_deadline_and_dependencies(self):
        fields = CALENDAR_SCHEMA["properties"]["operations"]["items"]["properties"]
        self.assertTrue({"start_date", "due_date", "hard_deadline", "depends_on_ids", "sources"} <= set(fields))

    def test_plan_sources_use_evidence_status_and_real_date(self):
        result = {"operations": [{"action": "add", "date_basis": "建议日期", "sources": [
            {"source_name": "伪造名称", "source_url": "https://example.gov.cn/rule", "source_status": "官方来源已核验", "verified_at": "2099-01-01"},
            {"source_name": "未知", "source_url": "https://made-up.example/rule", "source_status": "官方来源已核验", "verified_at": "2099-01-01"},
        ]}]}
        evidence = {"policies": [{"topic": "公积金", "source": "https://example.gov.cn/rule", "status": "verified", "verified_at": "2026-09-23"}]}
        attach_operation_sources(result, evidence)
        sources = result["operations"][0]["sources"]
        self.assertEqual(sources[0]["verified_at"], "2026-09-23")
        self.assertEqual(sources[0]["source_name"], "公积金")
        self.assertEqual(sources[1]["source_url"], "")
        self.assertEqual(sources[1]["source_status"], "信息待确认")

    def test_structured_items_are_complete_and_limited(self):
        item = {"title": "确认住房", "why": "搬家前需要地址", "when": "10月10日前", "prerequisite": "确定公司位置", "completion": "签订合同", "basis": "信息待确认：向房东核验"}
        answer = compose_answer({"answer": "公司在张江。", "advice_items": [item] * 4, "follow_ups": ["能接受合租吗？"]})
        self.assertIn("目前信息总结：公司在张江。", answer)
        self.assertIn("近期要完成的事：", answer)
        self.assertIn("依据与状态：信息待确认", answer)
        self.assertEqual(answer.count("为何："), 3)
        self.assertIn("最后追问：", answer)

    def test_information_collection_mode_only_shows_key_questions(self):
        result = enforce_response_mode({
            "response_mode": "A", "answer": "还缺少安排所需的信息。",
            "advice_items": [{"title": "不应展示"}], "follow_ups": ["公司在哪个区域？", "入职日期是什么？", "月租预算是多少？", "多余问题"],
            "calendar_intent": "propose", "operations": [{"action": "add"}],
        })
        answer = compose_answer(result)
        self.assertEqual(result["calendar_intent"], "none")
        self.assertEqual(result["operations"], [])
        self.assertNotIn("不应展示", answer)
        self.assertIn("请补充：\n1. 公司在哪个区域？", answer)
        self.assertNotIn("多余问题", answer)

    def test_plan_generation_uses_confirmation_table_for_details(self):
        answer = compose_answer({
            "response_mode": "B", "answer": "已按时间顺序整理计划。",
            "advice_items": [{"title": "不应展示"}], "follow_ups": ["搬家日期是否可调整？"],
        })
        self.assertIn("已按时间顺序整理计划。", answer)
        self.assertIn("需要确认的假设：", answer)
        self.assertNotIn("事项详情：", answer)
