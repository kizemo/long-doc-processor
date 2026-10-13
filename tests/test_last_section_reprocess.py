"""test_last_section_reprocess.py — 单元测试"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.last_section_reprocess as lsr
from scripts.last_section_reprocess import (
    split_tail, _split_head_tail, _strip_md_wrapper,
    last_section_reprocess, LAST_SECTION_PROMPT,
)


SAMPLE_DOC = """# 培训讲义

## 1. 第一章

content

## 2. 第二章

content

## 3. 末段

content A

content B

content C
"""


class TestSplitHeadTail(unittest.TestCase):

    def test_basic_split(self):
        head, tail = _split_head_tail(SAMPLE_DOC, tail_ratio=0.25)
        # tail 应包含 "## 3. 末段"
        self.assertIn('## 3. 末段', tail)
        # head 应不包含
        self.assertNotIn('## 3. 末段', head)

    def test_tail_short_doc(self):
        """文档太短时,所有都进 tail"""
        short = "## 1. A\n\ncontent"
        head, tail = _split_head_tail(short, tail_ratio=0.25)
        # 文档 < 25% 时,cut_offset = 0,tail = 整个文档
        self.assertIn('## 1. A', tail)


class TestStripMdWrapper(unittest.TestCase):

    def test_no_wrapper(self):
        self.assertEqual(_strip_md_wrapper("plain text"), "plain text")

    def test_markdown_wrapper(self):
        text = "```markdown\n# Title\ncontent\n```"
        self.assertEqual(_strip_md_wrapper(text), "# Title\ncontent")


class TestPromptTemplate(unittest.TestCase):

    def test_prompt_contains_constraints(self):
        for kw in ['LAST-SECTION-COMPLETE', 'H3-NAMING-CONSISTENT', 'LOGIC-CHAIN',
                    '新增', '删除', '禁止']:
            self.assertIn(kw, LAST_SECTION_PROMPT)


class TestLastSectionReprocessMocked(unittest.TestCase):

    def _write_doc(self) -> tuple[Path, str]:
        tmpdir = tempfile.mkdtemp()
        path = Path(tmpdir) / 'in.md'
        path.write_text(SAMPLE_DOC, encoding='utf-8')
        return path, tmpdir

    def test_full_flow_writes_output(self):
        path, tmpdir = self._write_doc()
        try:
            output = Path(tmpdir) / 'out.md'
            with patch('scripts.last_section_reprocess.safe_llm_call') as mock:
                mock.return_value = ("```markdown\n## 3. 末段(修复)\n\ncontent with 5 assets\n```", "ok")
                rc = last_section_reprocess(path, output)
                self.assertEqual(rc, 0)
            self.assertTrue(output.exists())
            self.assertIn('## 3. 末段(修复)', output.read_text(encoding='utf-8'))
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_llm_failure_keeps_original(self):
        path, tmpdir = self._write_doc()
        try:
            output = Path(tmpdir) / 'out.md'
            with patch('scripts.last_section_reprocess.safe_llm_call') as mock:
                mock.return_value = ("", "error")
                rc = last_section_reprocess(path, output)
                self.assertEqual(rc, 0)
            # 写入原文
            self.assertTrue(output.exists())
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_llm_empty_returns_original(self):
        path, tmpdir = self._write_doc()
        try:
            output = Path(tmpdir) / 'out.md'
            with patch('scripts.last_section_reprocess.safe_llm_call') as mock:
                mock.return_value = ("", "empty")
                rc = last_section_reprocess(path, output)
                self.assertEqual(rc, 0)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_input_not_found(self):
        rc = last_section_reprocess(
            Path('/nonexistent/file.md'),
            Path('/tmp/out.md'),
        )
        self.assertEqual(rc, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
