import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from demo import answer


class DemoTest(unittest.TestCase):
    def test_demo_is_explicit_and_uses_area_data(self):
        result = answer([{"role": "user", "content": "公司在张江高科，通勤40分钟，月租3000元，接受合租，哪里可以住？"}])
        self.assertIn("未调用大模型", result)
        self.assertIn("浦东张江", result)
        self.assertIn("挂牌样本", result)


if __name__ == "__main__":
    unittest.main()
