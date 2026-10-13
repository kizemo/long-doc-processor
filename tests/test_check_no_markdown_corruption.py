"""test_check_no_markdown_corruption.py — 单元测试 v4.12 表格 + 污染词检测"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.check_no_markdown_corruption as cnmc
from scripts.check_no_markdown_corruption import (
    check_broken_headings,
    check_corruption_tokens,
    check_html_vs_md,
    check_table_column_consistency,
    count_html_tables,
    find_tables,
)


# 测试样本 ---------------------------------------------------------

GOOD_MD = """# Title

## 1. 一章

| 列 1 | 列 2 |
|---|---|
| a | b |
| c | d |

content here

## 2. 二章

content
"""


BAD_TABLE = """# Title

## 1. 一章

| 列 1 | 列 2 | 列 3 |
|---|---|
| a | b |
| c | d |
| e |
"""


CORRUPT_TOKEN = """# Title

此处出现医疗器械标签 作为污染词
"""


BROKEN_HEADING = """# Title

## 1. 孤立标题

## 2. 下一标题
"""


class TestFindTables(unittest.TestCase):

    def test_no_table(self):
        tables = find_tables("# Title\n\ncontent")
        self.assertEqual(tables, [])

    def test_single_table(self):
        tables = find_tables(GOOD_MD)
        self.assertEqual(len(tables), 1)
        start, lines = tables[0]
        self.assertGreaterEqual(len(lines), 3)  # header + sep + ≥1 row

    def test_multiple_tables(self):
        md = """# Title

| a | b |
|---|---|
| 1 | 2 |

content

| c | d |
|---|---|
| 3 | 4 |
"""
        tables = find_tables(md)
        self.assertEqual(len(tables), 2)


class TestCheckTableColumnConsistency(unittest.TestCase):

    def test_consistent_table(self):
        tables = find_tables(GOOD_MD)
        issues = check_table_column_consistency(tables)
        self.assertEqual(issues, [])

    def test_inconsistent_table(self):
        tables = find_tables(BAD_TABLE)
        issues = check_table_column_consistency(tables)
        self.assertGreater(len(issues), 0)
        self.assertTrue(any('列数' in s for s in issues))


class TestCheckCorruptionTokens(unittest.TestCase):

    def test_no_corruption(self):
        issues = check_corruption_tokens(GOOD_MD)
        self.assertEqual(issues, [])

    def test_medical_token(self):
        issues = check_corruption_tokens(CORRUPT_TOKEN)
        self.assertGreater(len(issues), 0)
        self.assertTrue(any('医疗器械标签' in s for s in issues))

    def test_position_token(self):
        issues = check_corruption_tokens("text contains 同价位 marker")
        self.assertGreater(len(issues), 0)


class TestCheckBrokenHeadings(unittest.TestCase):

    def test_heading_with_content(self):
        text = """## 1. 一章

content here
"""
        issues = check_broken_headings(text)
        self.assertEqual(issues, [])

    def test_isolated_heading(self):
        issues = check_broken_headings(BROKEN_HEADING)
        self.assertGreater(len(issues), 0)
        self.assertTrue(any('孤立标题' in s for s in issues))

    def test_end_heading(self):
        text = """# Title

content

## 末尾标题"""
        issues = check_broken_headings(text)
        self.assertGreater(len(issues), 0)


class TestCheckHtmlVsMd(unittest.TestCase):

    def test_matching_count(self):
        md = "| a | b |\n|---|---|\n| 1 | 2 |\n"
        html = "<table><tr><td>a</td><td>b</td></tr></table>"
        issues = check_html_vs_md(md, html)
        self.assertEqual(issues, [])

    def test_mismatch(self):
        md = "| a | b |\n|---|---|\n| 1 | 2 |\n"
        html = "<p>no table</p>"
        issues = check_html_vs_md(md, html)
        self.assertGreater(len(issues), 0)
        self.assertTrue(any('不一致' in s for s in issues))


class TestCountHtmlTables(unittest.TestCase):

    def test_count(self):
        html = "<table><tr><td>1</td></tr></table>\n<table><tr><td>2</td></tr></table>"
        self.assertEqual(count_html_tables(html), 2)

    def test_with_attrs(self):
        html = '<table class="x"><tr><td>1</td></tr></table>'
        self.assertEqual(count_html_tables(html), 1)

    def test_no_table(self):
        self.assertEqual(count_html_tables("<p>hello</p>"), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
