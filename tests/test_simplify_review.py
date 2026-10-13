"""test_simplify_review.py — E5 simplify review 报告存在性测试

覆盖:
  1. references/SIMPLIFY_REVIEW_v4.21.md 存在
  2. 报告含关键章节(整体成果 / 各阶段沉淀物 / 局限 / 建议)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(__file__.replace("\\", "/").rsplit("/", 2)[0]))


REVIEW_PATH = Path("references/SIMPLIFY_REVIEW_v4.21.md")


class TestSimplifyReview(unittest.TestCase):

    def test_review_exists(self):
        """simplify review 报告存在。"""
        self.assertTrue(REVIEW_PATH.exists(), f"{REVIEW_PATH} 不存在")

    def test_review_contains_achievement_section(self):
        """含"整体成果"段。"""
        text = REVIEW_PATH.read_text(encoding="utf-8")
        self.assertIn("整体成果", text)

    def test_review_contains_sediment_section(self):
        """含"沉淀物"段。"""
        text = REVIEW_PATH.read_text(encoding="utf-8")
        self.assertIn("沉淀物", text)

    def test_review_contains_limitation_section(self):
        """含"已知局限"段。"""
        text = REVIEW_PATH.read_text(encoding="utf-8")
        self.assertIn("已知局限", text)

    def test_review_contains_recommendation_section(self):
        """含"v4.22 优先做"段。"""
        text = REVIEW_PATH.read_text(encoding="utf-8")
        self.assertIn("v4.22 优先做", text)

    def test_review_lists_all_5_phases(self):
        """5 阶段全部覆盖。"""
        text = REVIEW_PATH.read_text(encoding="utf-8")
        for stage in ["A 阶段", "B 阶段", "C 阶段", "D 阶段", "E 阶段"]:
            self.assertIn(stage, text, f"缺阶段:{stage}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
