"""test_heading_regex_unified.py — E3 heading 正则统一测试

覆盖:
  1. chunking.py 集中暴露 _H1_RE~_H5_RE + with-title 版本
  2. HEADING_RE dict 通过 level(1-5)访问
  3. 各正则行为正确(区分 H1~H5)
"""
from __future__ import annotations

import re
import sys
import unittest

sys.path.insert(0, str(__file__.replace("\\", "/").rsplit("/", 2)[0]))

import scripts.chunking as chunking
from scripts.chunking import (
    _H1_RE, _H2_RE, _H3_RE, _H4_RE, _H5_RE,
    _H1_TITLE_RE, _H2_TITLE_RE, _H3_TITLE_RE, _H4_TITLE_RE, _H5_TITLE_RE,
    HEADING_RE, HEADING_TITLE_RE,
)


SAMPLE_MD = """# H1 Title
## H2 Title
### H3 Title
#### H4 Title
##### H5 Title
content
"""


# 1. 正则存在性

class TestHeadingRegexExposed(unittest.TestCase):

    def test_all_5_match_re(self):
        """_H1_RE~_H5_RE 都在 chunking 暴露。"""
        for level in range(1, 6):
            self.assertTrue(hasattr(chunking, f"_H{level}_RE"),
                            f"_H{level}_RE 应在 chunking 暴露")

    def test_all_5_title_re(self):
        """_H{N}_TITLE_RE 都在 chunking 暴露。"""
        for level in range(1, 6):
            self.assertTrue(hasattr(chunking, f"_H{level}_TITLE_RE"),
                            f"_H{level}_TITLE_RE 应在 chunking 暴露")

    def test_heading_re_dict(self):
        """HEADING_RE dict 含 5 个 level。"""
        for level in range(1, 6):
            self.assertIn(level, HEADING_RE)
            self.assertIn(level, HEADING_TITLE_RE)


# 2. 行为正确性

class TestHeadingRegexBehavior(unittest.TestCase):

    def test_h1_matches_only_h1(self):
        """_H1_RE 只匹配 H1(`# `),不匹配 H2/H3。"""
        self.assertEqual(len(_H1_RE.findall(SAMPLE_MD)), 1)

    def test_h2_matches_h2(self):
        """_H2_RE 匹配 H2,且不误匹配 H1/H3(因 `## ` 在 H3 也含 `##`?)。"""
        # 注:`## ` 严格在 H2 行,_H2_RE 不会匹配 H3(`### `)
        matches = _H2_RE.findall(SAMPLE_MD)
        self.assertEqual(len(matches), 1)

    def test_h3_matches_h3(self):
        matches = _H3_RE.findall(SAMPLE_MD)
        self.assertEqual(len(matches), 1)

    def test_h2_title_capture(self):
        """_H2_TITLE_RE 捕获标题文字(去除 `## ` 前缀)。"""
        matches = _H2_TITLE_RE.findall(SAMPLE_MD)
        self.assertEqual(matches, ["H2 Title"])

    def test_h3_title_capture(self):
        matches = _H3_TITLE_RE.findall(SAMPLE_MD)
        self.assertEqual(matches, ["H3 Title"])

    def test_heading_re_dict_lookup(self):
        """HEADING_RE[2] 应等于 _H2_RE。"""
        self.assertIs(HEADING_RE[2], _H2_RE)
        self.assertIs(HEADING_RE[3], _H3_RE)
        self.assertIs(HEADING_TITLE_RE[1], _H1_TITLE_RE)

    def test_h4_h5_distinct(self):
        """H4 vs H5 互不误匹配。"""
        h4 = _H4_RE.findall(SAMPLE_MD)
        h5 = _H5_RE.findall(SAMPLE_MD)
        self.assertEqual(len(h4), 1)
        self.assertEqual(len(h5), 1)


# 3. 兼容性 — 旧 _H2_RE(无 group)在 chunking 暴露

class TestBackwardCompat(unittest.TestCase):

    def test_old_h2_re_still_in_chunking(self):
        """旧代码 import 自 chunking 的 _H2_RE 仍可工作。"""
        self.assertIsNotNone(_H2_RE)
        # 与 chunking 内的 _H2_RE 同对象
        self.assertIs(_H2_RE, chunking._H2_RE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
