"""test_pre_merge_semantic_check.py — 单元测试"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts._pre_merge_semantic_check as pmsc
from scripts._pre_merge_semantic_check import (
    ASR_TERM_FIXES, ROLE_PERSONA_FIXES,
    apply_dict_fixes, check_chunk_end_sentences, check_h3_skip_numbering,
    pre_merge_semantic_check,
)


SAMPLE_OK = """# Title

## 1. 第一章

### 1.1 sub

content

### 1.2 sub

content

## 2. 第二章

### 2.1 sub

content
"""


SAMPLE_H3_SKIP = """# Title

## 1. 第一章

### 1.1 sub1

### 1.3 sub3   ← 跳号

### 1.2 sub2   ← 顺序错乱
"""


SAMPLE_ASR_DIRTY = """# Title

摩特图点击率 5%。心客转化率高。
"""


SAMPLE_PERSONA_DIRTY = """# Title

大力老师讲解电商运营。
讲师指出,学员搜索时常见问题。
"""


SAMPLE_CHUNK_END = """# Title

第一段内容。GMV 提升 30%。因此。

第二段内容。转化率翻倍。综上。
"""


class TestCheckH3SkipNumbering(unittest.TestCase):

    def test_no_change_when_sequential(self):
        new_text, n = check_h3_skip_numbering(SAMPLE_OK)
        self.assertEqual(n, 0)

    def test_fix_skip(self):
        new_text, n = check_h3_skip_numbering(SAMPLE_H3_SKIP)
        self.assertGreater(n, 0)
        # 跳号应被重排为连续
        self.assertIn('### 1.1 sub1', new_text)
        self.assertIn('### 1.2 sub3', new_text)
        self.assertIn('### 1.3 sub2', new_text)

    def test_empty_input(self):
        new_text, n = check_h3_skip_numbering("")
        self.assertEqual(new_text, "")
        self.assertEqual(n, 0)


class TestApplyDictFixes(unittest.TestCase):

    def test_basic_replace(self):
        content = "摩特图 和 心客"
        fixes = [('摩特图', '模特图'), ('心客', '新客')]
        new_content, n = apply_dict_fixes(content, fixes)
        self.assertEqual(new_content, "模特图 和 新客")
        self.assertEqual(n, 2)

    def test_delete_fix(self):
        content = "大力老师 讲解"
        fixes = [('大力老师', '')]
        new_content, n = apply_dict_fixes(content, fixes)
        self.assertNotIn('大力老师', new_content)
        self.assertIn('讲解', new_content)

    def test_no_match(self):
        content = "无关文本"
        fixes = [('摩特图', '模特图')]
        new_content, n = apply_dict_fixes(content, fixes)
        self.assertEqual(new_content, content)
        self.assertEqual(n, 0)


class TestCheckChunkEndSentences(unittest.TestCase):

    def test_no_end(self):
        issues = check_chunk_end_sentences(SAMPLE_OK)
        self.assertEqual(issues, [])

    def test_detect_因此(self):
        issues = check_chunk_end_sentences(SAMPLE_CHUNK_END)
        self.assertGreater(len(issues), 0)
        self.assertTrue(any('因此' in line for _, line in issues))

    def test_detect_综上(self):
        text = "第一段。\n\n综上全文。"
        issues = check_chunk_end_sentences(text)
        self.assertGreater(len(issues), 0)


class TestIntegration(unittest.TestCase):

    def _write_md(self, content: str) -> tuple[Path, str]:
        tmpdir = tempfile.mkdtemp()
        path = Path(tmpdir) / 'in.md'
        path.write_text(content, encoding='utf-8')
        return path, tmpdir

    def test_clean_md_all_fixed(self):
        path, tmpdir = self._write_md(SAMPLE_OK)
        try:
            output = Path(tmpdir) / 'out.md'
            rc = pre_merge_semantic_check(path, output)
            self.assertEqual(rc, 0)
            # 输出应保留
            self.assertTrue(output.exists())
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_dirty_md_fixed_and_warned(self):
        path, tmpdir = self._write_md(SAMPLE_CHUNK_END)
        try:
            output = Path(tmpdir) / 'out.md'
            rc = pre_merge_semantic_check(path, output)
            # 收束句 → return 1
            self.assertEqual(rc, 1)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_input_not_found(self):
        rc = pre_merge_semantic_check(
            Path('/nonexistent/file.md'),
            Path('/tmp/out.md'),
        )
        self.assertEqual(rc, 1)


class TestFixesConfig(unittest.TestCase):

    def test_asr_fixes_non_empty(self):
        self.assertGreater(len(ASR_TERM_FIXES), 10)

    def test_role_fixes_non_empty(self):
        self.assertGreater(len(ROLE_PERSONA_FIXES), 3)

    def test_no_self_mapping(self):
        for wrong, right in ASR_TERM_FIXES:
            if right:  # 删除(empty)不算 self-mapping
                self.assertNotEqual(wrong, right, f"ASR {wrong} → {right}")
        for wrong, right in ROLE_PERSONA_FIXES:
            if right:
                self.assertNotEqual(wrong, right, f"ROLE {wrong} → {right}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
