"""test_check_no_markdown_corruption_extended.py — B2 阶段测试

覆盖:
  1. CORRUPTION_TOKENS 扩到 ≥ 30 条
  2. NO-ORPHAN-WORDS 模式检测段首/段末孤立词
  3. 列数算法修正 line.count('|') - 1
  4. 5 个 sample(数据驱动)
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(__file__.replace("\\", "/").rsplit("/", 2)[0]))

import scripts.check_no_markdown_corruption as cnm
from scripts.check_no_markdown_corruption import (
    CORRUPTION_TOKENS,
    ORPHAN_WORD_TOKENS,
    check_corruption_tokens,
    check_no_orphan_words,
    check_table_column_consistency,
    find_tables,
    check_broken_headings,
    check_html_vs_md,
)


# 1. CORRUPTION_TOKENS 数量 + 内容 -------------------------------

class TestCorruptionTokensExtended(unittest.TestCase):
    def test_count_at_least_30(self):
        """CORRUPTION_TOKENS ≥ 30 条(B2 目标)。"""
        self.assertGreaterEqual(
            len(CORRUPTION_TOKENS), 30,
            f"期望 ≥ 30 条,实际 {len(CORRUPTION_TOKENS)}",
        )

    def test_includes_v4_12_originals(self):
        """v4.12 原始 3 条应保留。"""
        for kw in ['医疗器械标签', '同价位', '店铺绩效']:
            self.assertIn(kw, CORRUPTION_TOKENS, f"v4.12 原始词 {kw} 缺失")

    def test_includes_asr_corrections_samples(self):
        """asr_corrections.yaml 高频 ASR 错词样本应被覆盖。"""
        # 取 10 个高频 ASR 错词,确保在 CORRUPTION_TOKENS
        samples = [
            '皮气护理', '最大化作间法', '相产品均头', '数据筛毯',
            '心中式', '带梦图', '掀车', '摩特图',
            '高科赞', '点击力',
        ]
        for kw in samples:
            self.assertIn(kw, CORRUPTION_TOKENS, f"高频错词 {kw} 缺失")

    def test_detect_long_word(self):
        """长词(皮气护理)残留应被检测。"""
        issues = check_corruption_tokens("这是一段皮气护理的测试")
        self.assertTrue(any("皮气护理" in i for i in issues))

    def test_detect_short_word(self):
        """短词(权占)残留应被检测。"""
        issues = check_corruption_tokens("这个词权占了主导")
        self.assertTrue(any("权占" in i for i in issues))


# 2. NO-ORPHAN-WORDS 模式 ---------------------------------------

class TestNoOrphanWords(unittest.TestCase):

    def test_detect_orphan_paragraph(self):
        """段首/段末孤立词(单独成段)应被检测。"""
        text = """# Title

## 1. 一章

这是一段正常内容。

好

这是另一段正常内容。
"""
        issues = check_no_orphan_words(text)
        # 应检测到 "好" 单独成段
        self.assertTrue(any("孤立段" in i for i in issues),
                        f"应检测到孤立段,实际 {issues}")

    def test_pass_normal_paragraph(self):
        """正常段(含主语/谓语)不触发孤立词检测。"""
        text = """# Title

## 1. 一章

这是正常的段落,内容丰富。
"""
        issues = check_no_orphan_words(text)
        # 正常段不应触发
        self.assertEqual(issues, [], f"正常段不应触发,实际 {issues}")

    def test_pass_long_paragraph_with_orphan_word(self):
        """长段(含孤立词但非单独成段)不触发。"""
        text = """# Title

## 1. 一章

这是一段很长的内容,虽然开头有个"好"字,但后面有 50 个字以上,不算孤立段。
"""
        issues = check_no_orphan_words(text)
        # 长度 > 20 字符的段不算孤立
        self.assertEqual(issues, [], f"长段不应触发,实际 {issues}")

    def test_orphan_word_tokens_includes_filling_words(self):
        """ORPHAN_WORD_TOKENS 应包含 ASR 常见填充词。"""
        for kw in ['好', '对', '那个', '对吧', '是吧']:
            self.assertIn(kw, ORPHAN_WORD_TOKENS, f"孤立词 {kw} 缺失")


# 3. 列数算法修正 line.count('|') - 1 ---------------------------

class TestTableColumnCountFix(unittest.TestCase):
    def test_consistent_columns_after_fix(self):
        """列数均匀表格应 PASS(边界 `|` 已正确去除)。"""
        text = """| A | B | C |
|---|---|---|
| 1 | 2 | 3 |
| 4 | 5 | 6 |
"""
        tables = find_tables(text)
        issues = check_table_column_consistency(tables)
        # 3 列一致,无 issue
        self.assertEqual(issues, [], f"3 列一致表格不应有 issue,实际 {issues}")

    def test_inconsistent_columns(self):
        """列数不均表格应 FAIL。"""
        text = """| A | B | C |
|---|---|
| 1 | 2 |
| 3 | 4 | 5 |
"""
        tables = find_tables(text)
        issues = check_table_column_consistency(tables)
        self.assertGreater(len(issues), 0, f"列数不均应 FAIL,实际 {issues}")


# 4. 5 个 sample 端到端(整合测试) -------------------------------

class TestEndToEndSamples(unittest.TestCase):

    def test_sample_clean_md_no_issue(self):
        """干净 md → 无 issue。"""
        text = """# Title

> 简介:这是测试文档。

## 1. 一章

正常段落。

## 2. 二章

| A | B |
|---|---|
| 1 | 2 |
"""
        all_issues = []
        all_issues.extend(check_table_column_consistency(find_tables(text)))
        all_issues.extend(check_corruption_tokens(text))
        all_issues.extend(check_no_orphan_words(text))
        all_issues.extend(check_broken_headings(text))
        self.assertEqual(all_issues, [], f"干净 md 不应有 issue,实际 {all_issues}")

    def test_sample_dirty_md_multiple_issues(self):
        """脏 md → 多个 issue。"""
        text = """# Title

## 1. 一章

学员在选品时,常常出错。

## 2. 二章

皮气护理

好

## 3. 第三章

| A | B | C |
|---|---|
| 1 | 2 |

## 4. 第四章

## 5. 第五章
"""
        all_issues = []
        all_issues.extend(check_table_column_consistency(find_tables(text)))
        all_issues.extend(check_corruption_tokens(text))
        all_issues.extend(check_no_orphan_words(text))
        all_issues.extend(check_broken_headings(text))
        # 至少 3 类问题:污染词 / 孤立段 / 表格列数 / 断裂标题
        self.assertGreaterEqual(len(all_issues), 3,
                               f"应 ≥ 3 个 issue,实际 {len(all_issues)}: {all_issues}")

    def test_sample_html_vs_md_match(self):
        """md vs html 表格数一致 → 无 issue。"""
        text = "| A | B |\n|---|---|\n| 1 | 2 |\n"
        html = "<table><tr><td>A</td><td>B</td></tr><tr><td>1</td><td>2</td></tr></table>"
        issues = check_html_vs_md(text, html)
        # 1 个 md 表格,1 个 html 表格 → 一致
        self.assertEqual(issues, [], f"md vs html 应一致,实际 {issues}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
