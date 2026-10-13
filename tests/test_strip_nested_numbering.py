"""test_strip_nested_numbering.py — 单元测试 NO-NESTED-NUMBERING 规约"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.strip_nested_numbering as snn
from scripts.strip_nested_numbering import (
    detect_violations, merge_excess_h4, renumber_headings,
)


SAMPLE_OK = """# Title

## 1. 第一章

### 1.1 子节 1

#### 1.1.1 子子节 A
content

#### 1.1.2 子子节 B
content

### 1.2 子节 2

content

## 2. 第二章

content
"""


SAMPLE_H4_OVERFLOW = """# Title

## 1. 第一章

### 1.1 子节

#### 1.1.1 A
content

#### 1.1.2 B
content

#### 1.1.3 C
content

#### 1.1.4 D
content

#### 1.1.5 E
content
"""


SAMPLE_SKIP_NUMBERING = """# Title

## 1. 第一章

### 1.1 sub 1

### 1.3 sub 3   ← 跳号(应为 1.2)
content
"""


class TestDetectViolations(unittest.TestCase):

    def test_ok_no_violation(self):
        v = detect_violations(SAMPLE_OK)
        self.assertEqual(v, [], f"期望无违规,实际:{v}")

    def test_h4_overflow_per_h3(self):
        v = detect_violations(SAMPLE_H4_OVERFLOW)
        self.assertTrue(any('H4 数' in s for s in v))

    def test_h3_skip_numbering(self):
        v = detect_violations(SAMPLE_SKIP_NUMBERING)
        self.assertTrue(any('H3 编号跳号' in s for s in v))

    def test_h4_skip_numbering(self):
        md = """# Title

## 1. 第一章

### 1.1 sub

#### 1.1.1 a
content

#### 1.1.3 c   ← 跳号(应为 1.1.2)
content
"""
        v = detect_violations(md)
        self.assertTrue(any('H4 编号跳号' in s for s in v))


class TestMergeExcessH4(unittest.TestCase):

    def test_no_change_when_under_limit(self):
        new_text, n = merge_excess_h4(SAMPLE_OK)
        self.assertEqual(n, 0)
        self.assertEqual(new_text, SAMPLE_OK)

    def test_excess_h4_demoted(self):
        new_text, n = merge_excess_h4(SAMPLE_H4_OVERFLOW)
        self.assertGreater(n, 0)
        # 前 3 个 H4 保留
        self.assertIn('#### 1.1.1 A', new_text)
        self.assertIn('#### 1.1.3 C', new_text)
        # 第 4 个降级为加粗
        self.assertIn('**1.1.4 D**', new_text)
        self.assertIn('**1.1.5 E**', new_text)
        # 不再有 #### 1.1.4 / #### 1.1.5
        self.assertNotIn('#### 1.1.4', new_text)
        self.assertNotIn('#### 1.1.5', new_text)

    def test_h4_count_reset_after_h3(self):
        """H3 切换应重置 H4 计数"""
        md = """## 1. 一\n\n### 1.1 a\n\n#### 1.1.1\n#### 1.1.2\n#### 1.1.3\n#### 1.1.4\n\n### 1.2 b\n\n#### 1.2.1\n#### 1.2.2\n"""
        new_text, n = merge_excess_h4(md)
        # 第 4 个 1.1.x 应降级,但 1.2.x 全部保留
        self.assertIn('#### 1.2.1', new_text)
        self.assertIn('#### 1.2.2', new_text)
        self.assertGreater(n, 0)


class TestRenumberHeadings(unittest.TestCase):

    def test_renumber_skipped(self):
        new_text, n = renumber_headings(SAMPLE_SKIP_NUMBERING)
        self.assertGreater(n, 0)
        # 跳号的 1.3 应被改为 1.2
        self.assertIn('### 1.2 sub 3', new_text)

    def test_renumber_no_change_when_sequential(self):
        new_text, n = renumber_headings(SAMPLE_OK)
        self.assertEqual(n, 0)
        self.assertEqual(new_text, SAMPLE_OK)

    def test_renumber_h2(self):
        """H2 按源顺序重排(不改变标题内容)"""
        md = """## 3. 三章\n\n## 1. 一章\n\n## 2. 二章\n"""
        new_text, n = renumber_headings(md)
        # 源顺序是 三章 → 一章 → 二章,重排后是 1. 三章 / 2. 一章 / 3. 二章
        self.assertIn('## 1. 三章', new_text)
        self.assertIn('## 2. 一章', new_text)
        self.assertIn('## 3. 二章', new_text)
        # 原 H2 编号 3 / 1 / 2 全部被替换
        self.assertNotIn('## 3. 一章', new_text)
        self.assertNotIn('## 1. 二章', new_text)
        self.assertGreater(n, 0)


class TestIntegration(unittest.TestCase):
    """集成:合并 + 重排"""

    def test_full_pipeline(self):
        new_text, _ = merge_excess_h4(SAMPLE_H4_OVERFLOW)
        new_text, _ = renumber_headings(new_text)
        # 重排后 H4 应为 1.1.1 / 1.1.2 / 1.1.3(前 3),1.1.4 / 1.1.5 降级
        self.assertIn('#### 1.1.1 A', new_text)
        self.assertIn('#### 1.1.3 C', new_text)
        # 降级为加粗段落
        self.assertIn('**1.1.4 D**', new_text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
