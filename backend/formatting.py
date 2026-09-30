"""Convert common model Markdown to clean chat text."""

from __future__ import annotations

import re


def plain_text(answer: str) -> str:
    answer = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1：\2", answer)
    lines = []
    for line in answer.splitlines():
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
        line = re.sub(r"^\s{0,3}[-*+]\s+", "", line)
        if re.match(r"^\s*```", line):
            continue
        line = line.replace("**", "").replace("`", "")
        lines.append(line.rstrip())
    return "\n".join(lines).strip()
