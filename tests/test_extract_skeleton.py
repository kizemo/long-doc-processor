"""test_extract_skeleton.py — extract_skeleton.py 单元测试"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.extract_skeleton as es
from scripts.extract_skeleton import extract_skeleton


SAMPLE_INPUT = """# 培训讲义

## 1. 第一章

内容

### 1.1 子节 1

#### 1.1.1 子子节

子内容

## 2. 第二章

内容 2

### 2.1 子节

内容
"""


class TestExtractSkeleton(unittest.TestCase):

    def test_h1_h2_only_by_default(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write(SAMPLE_INPUT)
            tmp = Path(f.name)
        try:
            skeleton = extract_skeleton(tmp)
            # 默认只含 H1 + H2
            self.assertIn('# 培训讲义', skeleton)
            self.assertIn('## 1. 第一章', skeleton)
            self.assertIn('## 2. 第二章', skeleton)
            self.assertNotIn('### 1.1', skeleton)
            self.assertNotIn('#### 1.1.1', skeleton)
        finally:
            tmp.unlink()

    def test_include_h3(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write(SAMPLE_INPUT)
            tmp = Path(f.name)
        try:
            skeleton = extract_skeleton(tmp, include_h3=True)
            self.assertIn('### 1.1 子节 1', skeleton)
            self.assertIn('### 2.1 子节', skeleton)
        finally:
            tmp.unlink()

    def test_include_h4(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write(SAMPLE_INPUT)
            tmp = Path(f.name)
        try:
            skeleton = extract_skeleton(tmp, include_h3=True, include_h4=True)
            self.assertIn('#### 1.1.1 子子节', skeleton)
        finally:
            tmp.unlink()

    def test_skip_h2_before_h1(self):
        """无 H1 时,H2 不应被采纳"""
        md = "## orphan\n\ncontent\n\n# Title\n\n## 1. proper\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write(md)
            tmp = Path(f.name)
        try:
            skeleton = extract_skeleton(tmp)
            # orphan H2 在 H1 之前,应被跳过
            self.assertNotIn('## orphan', skeleton)
            self.assertIn('## 1. proper', skeleton)
        finally:
            tmp.unlink()

    def test_skip_level_skip(self):
        """不能从 H1 直接跳到 H3(中间要 H2)"""
        md = "# Title\n\n### 1.1 skip\n\ncontent\n\n## 1. ok\n\n### 1.2 ok\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write(md)
            tmp = Path(f.name)
        try:
            skeleton = extract_skeleton(tmp, include_h3=True)
            # "### 1.1 skip" 在 ## 1. ok 之前 → 应被跳过
            self.assertNotIn('### 1.1 skip', skeleton)
            self.assertIn('### 1.2 ok', skeleton)
        finally:
            tmp.unlink()

    def test_no_titles(self):
        md = "no titles here\n\njust content"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write(md)
            tmp = Path(f.name)
        try:
            skeleton = extract_skeleton(tmp)
            self.assertEqual(skeleton.strip(), "")
        finally:
            tmp.unlink()


if __name__ == '__main__':
    unittest.main(verbosity=2)
