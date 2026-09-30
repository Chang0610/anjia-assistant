import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from server import openai_answer


class OpenAIAdapterTest(unittest.TestCase):
    def test_responses_request_and_text_extraction(self):
        model_data = {"answer": "先确认入职日期。", "calendar_intent": "none", "operations": [], "profile_updates": [{"field": "company_location", "value": "张江高科"}]}
        response = {"output": [{"type": "reasoning"}, {"type": "message", "content": [{"type": "output_text", "text": json.dumps(model_data)}]}]}
        captured = {}

        def fake_urlopen(request, timeout, context):
            captured["request"] = request
            captured["timeout"] = timeout
            captured["context"] = context
            return io.BytesIO(json.dumps(response).encode())

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "gpt-5.6-luna"}):
            with patch("urllib.request.urlopen", fake_urlopen):
                answer = openai_answer([{"role": "user", "content": "我要搬去上海"}], {"policies": []}, {"confirmed": [], "pending": None}, {"destination_city": "上海"})
        self.assertEqual(answer, model_data)
        self.assertEqual(captured["request"].full_url, "https://api.openai.com/v1/responses")
        body = json.loads(captured["request"].data)
        self.assertEqual(body["model"], "gpt-5.6-luna")
        self.assertIs(body["store"], False)
        self.assertEqual(body["input"][-1]["content"], "我要搬去上海")
        self.assertIn('"destination_city": "上海"', body["input"][0]["content"])
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertIn("目前信息总结", body["instructions"])
        self.assertIn("信息待确认", body["instructions"])
        self.assertIn("0–3个", body["instructions"])
        self.assertIn("总共也只能有1–3项", body["instructions"])


if __name__ == "__main__":
    unittest.main()
