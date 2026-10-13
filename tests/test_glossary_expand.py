"""test_glossary_expand.py — 单元测试 glossary_expand.py"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.glossary_expand as ge
from scripts.glossary_expand import (
    BUILTIN_G_SECTION, dedupe_pairs, expand_glossary,
    find_g_section, parse_g_section,
)


class TestFindGSection(unittest.TestCase):

    def test_g_heading(self):
        md = """## 前言

content

## G. ASR 易错词

- 错词 → 正确词

## 其他

content
"""
        section = find_g_section(md)
        self.assertIsNotNone(section)
        start, end = section
        # G 节内容应包含"- 错词 → 正确词"
        self.assertIn('- 错词 → 正确词', md[start:end])

    def test_g_alt_heading(self):
        md = "## 杂项\n\n## G ASR errors\n\n- a → b\n"
        section = find_g_section(md)
        self.assertIsNotNone(section)

    def test_no_g_section(self):
        md = "## 介绍\n\n## 内容\n\nno G section\n"
        section = find_g_section(md)
        self.assertIsNone(section)


class TestParseGSection(unittest.TestCase):

    def test_basic_parse(self):
        text = """## G. ASR 易错

- 皮气护理 → 皮质护理
- 牛仔库 → 牛仔裤
- 心客 → 新客
"""
        pairs = parse_g_section(text)
        self.assertEqual(len(pairs), 3)
        self.assertIn({'wrong': '皮气护理', 'right': '皮质护理'}, pairs)

    def test_skip_too_long(self):
        text = """- averylongwrongtoken1234567890 → short
- 短 → 短
"""
        pairs = parse_g_section(text)
        # 太长的被过滤
        for p in pairs:
            self.assertLessEqual(len(p['wrong']), 15)


class TestDedupePairs(unittest.TestCase):

    def test_dedupe(self):
        pairs = [
            {'wrong': 'a', 'right': 'b'},
            {'wrong': 'a', 'right': 'b'},
            {'wrong': 'a', 'right': 'c'},
        ]
        out = dedupe_pairs(pairs)
        self.assertEqual(len(out), 2)


class TestExpandGlossary(unittest.TestCase):

    def test_builtin_fallback(self):
        """源文件不存在时 fallback 到内置"""
        pairs, source = expand_glossary(Path('/nonexistent/file.md'))
        self.assertEqual(source, 'builtin')
        self.assertGreater(len(pairs), 20)

    def test_builtin_section(self):
        """内置 BUILTIN_G_SECTION 应能解析"""
        pairs = parse_g_section(BUILTIN_G_SECTION)
        self.assertGreater(len(pairs), 20)


class TestEndToEnd(unittest.TestCase):

    def test_main_writes_json(self):
        """main() 写 JSON 文件"""
        import io
        import contextlib
        from scripts.glossary_expand import main
        tmpdir = tempfile.mkdtemp()
        out_path = Path(tmpdir) / 'asr_error.json'
        old_argv = sys.argv
        sys.argv = ['x', '-o', str(out_path)]
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                rc = main()
            self.assertEqual(rc, 0)
            self.assertTrue(out_path.exists())
            data = json.loads(out_path.read_text(encoding='utf-8'))
            self.assertGreater(len(data), 20)
        finally:
            sys.argv = old_argv
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
