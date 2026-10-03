import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from server import Handler


class CalendarDateApiTest(unittest.TestCase):
    def request(self, body):
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        handler = Handler.__new__(Handler)
        handler.path = "/api/calendar-date"
        handler.headers = {"Content-Length": str(len(payload))}
        handler.rfile = io.BytesIO(payload)
        result = []
        handler.send_json = lambda status, data: result.append((status, data))
        handler.do_POST()
        return result[0]

    def test_hire_change_proposes_related_dates_without_saving_them(self):
        def item(event_id, title, due_date):
            return {"id": event_id, "title": title, "start_date": due_date, "due_date": due_date,
                    "date_basis": "用户明确" if event_id in ("hire", "move") else "建议日期"}

        original = [
            item("hire", "到岗入职并核对单位参保、公积金", "2026-10-15"),
            item("commute", "通勤试走", "2026-10-14"),
            item("move", "搬入新住处并完成入住检查", "2026-10-14"),
            item("handover", "确认搬家安排与旧住处交接", "2026-10-13"),
        ]
        status, data = self.request({"event_id": "hire", "due_date": "2026-10-12",
                                     "profile": {"start_date": "2026-10-15", "move_deadline": "2026-10-14"},
                                     "calendar": {"confirmed": original}})
        self.assertEqual(status, 200)
        self.assertEqual(data["event"]["due_date"], "2026-10-12")
        self.assertEqual({change["id"] for change in data["related_changes"]}, {"commute", "move", "handover"})
        self.assertEqual(original[1]["due_date"], "2026-10-14")
        self.assertEqual(data["profile"]["start_date"], "2026-10-12")
        self.assertEqual(data["profile"]["move_deadline"], "2026-10-14")

    def test_existing_pending_is_not_overwritten(self):
        event = {"id": "hire", "title": "入职", "due_date": "2026-10-15"}
        status, data = self.request({"event_id": "hire", "due_date": "2026-10-12",
                                     "calendar": {"confirmed": [event], "pending": [event]}})
        self.assertEqual(status, 409)
        self.assertIn("待确认", data["error"])


if __name__ == "__main__":
    unittest.main()
