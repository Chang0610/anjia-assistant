import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from formatting import plain_text


class FormattingTest(unittest.TestCase):
    def test_removes_common_markdown_without_losing_source(self):
        source = "### 下一步\n- **确认入职时间**\n- 查看[官方入口](https://example.com/a-b)\n`待核验`"
        self.assertEqual(plain_text(source), "下一步\n确认入职时间\n查看官方入口：https://example.com/a-b\n待核验")


if __name__ == "__main__":
    unittest.main()
