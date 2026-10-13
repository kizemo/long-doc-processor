"""test_per_section_stats.py — per_section_stats.py 单元测试"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.per_section_stats as pss
from scripts.per_section_stats import (
    check_assets, count_cjk, per_section_stats, split_by_h2,
)


SAMPLE_CLEANED = """# 培训讲义

## 1. 概念与案例

这是某母婴店的案例,因为 GMV 提升 30%。

| 列 | 值 |
|---|---|
| A | 1 |

## 2. 数据与逻辑

数据表明转化率提升 50%,因此销售额翻倍。

## 3. 总结

要点回顾。
"""


SAMPLE_RAW = """# 培训讲义原始

## 1. 概念与案例

这是某母婴店的案例,因为 GMV 提升 30%。案例展示了完整的转化路径。

## 2. 数据与逻辑

数据表明转化率提升 50%,因此销售额翻倍。数据来自内部系统。

## 3. 总结

要点回顾。

## 4. 行动

按时间顺序拆解。
"""


class TestCountCjk(unittest.TestCase):

    def test_basic(self):
        self.assertEqual(count_cjk("hello 中文"), 2)

    def test_all_chinese(self):
        self.assertEqual(count_cjk("中文测试"), 4)

    def test_empty(self):
        self.assertEqual(count_cjk(""), 0)

    def test_mixed_punctuation(self):
        # 标点不计入 CJK
        self.assertEqual(count_cjk("中文,english!"), 2)


class TestSplitByH2(unittest.TestCase):

    def test_basic_split(self):
        sections = split_by_h2(SAMPLE_CLEANED)
        self.assertEqual(len(sections), 3)
        self.assertEqual(sections[0][0], '1. 概念与案例')
        self.assertIn('母婴店', sections[0][1])

    def test_no_h2(self):
        sections = split_by_h2("# just title\n\ncontent")
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0][0], '(no H2)')


class TestCheckAssets(unittest.TestCase):

    def test_concept_case(self):
        content = "这是某概念的定义"
        assets = check_assets(content)
        self.assertGreater(assets['概念'], 0)

    def test_data_with_percentage(self):
        content = "GMV 提升 30%"
        assets = check_assets(content)
        self.assertGreater(assets['数据'], 0)

    def test_table_detected(self):
        content = "| A | B |\n|---|---|\n| 1 | 2 |"
        assets = check_assets(content)
        self.assertGreater(assets['表格'], 0)

    def test_all_five_present(self):
        # 表格正则 `^\|.*\|` 要求行首以 | 开头,所以表格须独占一行
        content = "概念定义 + 案例\n\n| 列1 | 列2 |\n|---|---|\n| a | b |\n\n因为 GMV 30% 所以转化率提升"
        assets = check_assets(content)
        for a in ['概念', '案例', '数据', '逻辑', '表格']:
            self.assertGreater(assets[a], 0, f"缺 {a}")


class TestPerSectionStats(unittest.TestCase):

    def test_full_report(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write(SAMPLE_CLEANED)
            tmp = Path(f.name)
        try:
            report = per_section_stats(tmp)
            self.assertIn('# 章节统计报告', report)
            self.assertIn('H2 章节数', report)
            self.assertIn('1. 概念与案例', report)
            self.assertIn('5 类资产', report)
        finally:
            tmp.unlink()

    def test_with_raw_retention(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cleaned = Path(tmpdir) / 'cleaned.md'
            raw = Path(tmpdir) / 'raw.md'
            cleaned.write_text(SAMPLE_CLEANED, encoding='utf-8')
            raw.write_text(SAMPLE_RAW, encoding='utf-8')
            report = per_section_stats(cleaned, raw)
            self.assertIn('保留率', report)

    def test_missing_assets_warning(self):
        """缺资产的章节应有 WARN"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            # 只 H2 + 简短内容,几乎不命中任何资产关键词
            f.write("## 1. 短章节\n\nhello world.\n")
            tmp = Path(f.name)
        try:
            report = per_section_stats(tmp)
            self.assertIn('WARN', report)
        finally:
            tmp.unlink()


if __name__ == '__main__':
    unittest.main(verbosity=2)
