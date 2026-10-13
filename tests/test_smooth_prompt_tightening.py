"""test_smooth_prompt_tightening.py — C1 阶段 SMOOTH_PROMPT 收紧测试

覆盖:
  1. prompt 含"只删不改"硬约束
  2. prompt 含"只重排不重写"硬约束
  3. prompt 显式禁止"同义改写"
  4. prompt 显式禁止"润色用词"
  5. prompt 含 v4.21 收紧说明
  6. prompt 仍含 7 类清理(向后兼容)
"""
from __future__ import annotations

import sys
import unittest

sys.path.insert(0, str(__file__.replace("\\", "/").rsplit("/", 2)[0]))

import scripts._purify_smooth as smooth
from scripts._purify_smooth import SMOOTH_PROMPT_TEMPLATE


class TestSmoothPromptTightening(unittest.TestCase):
    """C1: prompt 收紧,禁止同义改写原句字面。"""

    def test_contains_only_delete_not_rewrite(self):
        """核心约束:只删不改。"""
        self.assertIn("只删不改", SMOOTH_PROMPT_TEMPLATE)

    def test_contains_only_rerank_not_rewrite(self):
        """核心约束:只重排不重写。"""
        self.assertIn("只重排不重写", SMOOTH_PROMPT_TEMPLATE)

    def test_explicitly_prohibits_paraphrase(self):
        """显式禁止同义改写。"""
        self.assertIn("同义改写", SMOOTH_PROMPT_TEMPLATE)
        # "禁止同义改写" 必须是显式禁止
        self.assertIn("禁止同义改写", SMOOTH_PROMPT_TEMPLATE)

    def test_explicitly_prohibits_polishing(self):
        """显式禁止润色用词。"""
        self.assertIn("润色用词", SMOOTH_PROMPT_TEMPLATE)
        self.assertIn("禁止润色用词", SMOOTH_PROMPT_TEMPLATE)

    def test_contains_v4_21_marker(self):
        """含 v4.21 收紧说明(版本号 + 收紧关键词)。"""
        self.assertIn("v4.21", SMOOTH_PROMPT_TEMPLATE)
        self.assertIn("收紧", SMOOTH_PROMPT_TEMPLATE)

    def test_still_contains_7_categories(self):
        """7 类必须清理仍存在(向后兼容)。"""
        for kw in [
            "行首时间戳",  # 1
            "粗口",         # 2
            "ASR 装饰",     # 3
            "ASR 串扰",     # 4
            "中英俄混杂",  # 5
            "不通顺短句",   # 6
            "重复词",       # 7
        ]:
            self.assertIn(kw, SMOOTH_PROMPT_TEMPLATE, f"缺失清理类别:{kw}")

    def test_still_contains_absolute_prohibitions(self):
        """原有绝对禁止项仍存在。"""
        for kw in [
            "虚构案例",
            "删除原标题",
            "改动标题文字",
            "改动表格结构",
            "改动列表项数量",
        ]:
            self.assertIn(kw, SMOOTH_PROMPT_TEMPLATE, f"缺失禁止项:{kw}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
