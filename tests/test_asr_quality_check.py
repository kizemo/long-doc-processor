"""test_asr_quality_check.py — 单元测试"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.asr_quality_check as aqc
from scripts.asr_quality_check import (
    load_dict, pass1_dict_replace, pass2_isolated_tokens, render_report,
)


SAMPLE_TEXT = """# 培训讲义

皮气护理对皮质很重要。牛仔库也是今年流行趋势。
权占数据看 GMV 提升 30%。掀车策略在双 11 应用很广。

中文 中文 中文 中文 中文 中文

啦啦啦 啦啦 啦啦啦
"""


class TestLoadDict(unittest.TestCase):

    def _write_json(self, data) -> tuple[Path, str]:
        tmpdir = tempfile.mkdtemp()
        path = Path(tmpdir) / 'dict.json'
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return path, tmpdir

    def test_load_json_list(self):
        data = [{'from': '皮气', 'to': '皮质'}]
        path, tmpdir = self._write_json(data)
        try:
            rules = load_dict(path)
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0]['from'], '皮气')
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_load_json_dict(self):
        data = {'皮气': '皮质', '心客': '新客'}
        path, tmpdir = self._write_json(data)
        try:
            rules = load_dict(path)
            self.assertEqual(len(rules), 2)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_missing_file(self):
        rules = load_dict(Path('/nonexistent/dict.json'))
        self.assertEqual(rules, [])


class TestPass1DictReplace(unittest.TestCase):

    def test_basic_replace(self):
        content = "皮气护理 + 心客"
        rules = [{'from': '皮气护理', 'to': '皮质护理'}, {'from': '心客', 'to': '新客'}]
        new_content, counts = pass1_dict_replace(content, rules)
        self.assertIn('皮质护理', new_content)
        self.assertIn('新客', new_content)
        self.assertEqual(len(counts), 2)

    def test_skip_self_mapping(self):
        content = "abc"
        rules = [{'from': 'abc', 'to': 'abc'}]
        new_content, counts = pass1_dict_replace(content, rules)
        self.assertEqual(counts, {})

    def test_skip_empty(self):
        content = "text"
        rules = [{'from': '', 'to': '皮质'}]
        new_content, counts = pass1_dict_replace(content, rules)
        self.assertEqual(counts, {})


class TestPass2IsolatedTokens(unittest.TestCase):

    def test_find_2_chars(self):
        isolated = pass2_isolated_tokens(SAMPLE_TEXT)
        tokens = {tok for tok, _ in isolated}
        self.assertIn('中文', tokens)

    def test_min_count(self):
        text = "心 心 心"
        isolated = pass2_isolated_tokens(text, min_count=5)
        # 3 次 < 5 → 不入
        self.assertEqual(isolated, [])

    def test_no_match(self):
        text = "english only"
        isolated = pass2_isolated_tokens(text)
        self.assertEqual(isolated, [])


class TestRenderReport(unittest.TestCase):

    def test_with_counts(self):
        report = render_report({'皮气→皮质': 2}, [('心', 5)], 'test.md')
        self.assertIn('皮气→皮质', report)
        self.assertIn('`心`: 5', report)

    def test_empty_counts(self):
        report = render_report({}, [], 'test.md')
        self.assertIn('无替换', report)
        self.assertIn('(无)', report)


class TestIntegration(unittest.TestCase):

    def test_end_to_end(self):
        import io
        import contextlib
        from scripts.asr_quality_check import main

        tmpdir = tempfile.mkdtemp()
        in_path = Path(tmpdir) / 'in.md'
        dict_path = Path(tmpdir) / 'dict.json'
        out_dir = Path(tmpdir) / 'reports'

        in_path.write_text(SAMPLE_TEXT, encoding='utf-8')
        dict_path.write_text(
            json.dumps([{'from': '皮气护理', 'to': '皮质护理'}], ensure_ascii=False),
            encoding='utf-8',
        )

        old_argv = sys.argv
        sys.argv = ['x', str(in_path), '--dict', str(dict_path),
                    '--output-dir', str(out_dir)]
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                rc = main()
            self.assertEqual(rc, 0)
            # 报告应生成
            self.assertTrue((out_dir / 'asr_quality_report.md').exists())
        finally:
            sys.argv = old_argv
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
