"""test_strip_asr_terms.py — 单元测试 strip_asr_terms.py"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.strip_asr_terms as sat
from scripts.strip_asr_terms import (
    DEFAULT_RULES, apply_rules, sort_long_first, strip_asr_terms,
)


SAMPLE_MD = """# 培训讲义

皮气护理对皮质很重要。牛仔库也是今年流行趋势。
权占数据看 GMV 提升 30%。掀车策略在双 11 应用很广。
摩特图点击力提升到 5%。演书服季节性销售达 100 万。
主视图对转化影响巨大。心客转化率比老客高。
"""


class TestDefaultRules(unittest.TestCase):

    def test_default_rules_non_empty(self):
        self.assertGreater(len(DEFAULT_RULES), 20)

    def test_no_self_mapping(self):
        for r in DEFAULT_RULES:
            self.assertNotEqual(r['from'], r['to'])


class TestSortLongFirst(unittest.TestCase):

    def test_long_first(self):
        rules = [
            {'from': '心', 'to': '新', 'context': ''},
            {'from': '心客', 'to': '新客', 'context': ''},
        ]
        sorted_rules = sort_long_first(rules)
        self.assertEqual(sorted_rules[0]['from'], '心客')


class TestApplyRules(unittest.TestCase):

    def test_basic_replace(self):
        content = "心客转化率高"
        rules = [{'from': '心客', 'to': '新客', 'context': ''}]
        new_content, counts = apply_rules(content, rules)
        self.assertEqual(new_content, "新客转化率高")
        self.assertEqual(counts['心客→新客'], 1)

    def test_multiple_rules(self):
        content = "皮气护理 + 心客"
        rules = [
            {'from': '皮气护理', 'to': '皮质护理', 'context': ''},
            {'from': '心客', 'to': '新客', 'context': ''},
        ]
        new_content, counts = apply_rules(content, sort_long_first(rules))
        self.assertIn('皮质护理', new_content)
        self.assertIn('新客', new_content)

    def test_no_match(self):
        content = "无错词文本"
        rules = [{'from': '心客', 'to': '新客', 'context': ''}]
        new_content, counts = apply_rules(content, rules)
        self.assertEqual(new_content, content)
        self.assertEqual(counts, {})

    def test_no_self_mapping_when_apply(self):
        """from == to 应不产生替换"""
        content = "x"
        rules = [{'from': 'x', 'to': 'x'}]
        new_content, counts = apply_rules(content, rules)
        self.assertEqual(counts, {})


class TestStripAsrTerms(unittest.TestCase):

    def _write_md(self, content: str) -> tuple[Path, str]:
        tmpdir = tempfile.mkdtemp()
        path = Path(tmpdir) / 'test.md'
        path.write_text(content, encoding='utf-8')
        return path, tmpdir

    def test_end_to_end(self):
        path, tmpdir = self._write_md(SAMPLE_MD)
        try:
            output = Path(tmpdir) / 'output.md'
            counts = strip_asr_terms(path, output)
            self.assertGreater(sum(counts.values()), 5)
            text = output.read_text(encoding='utf-8')
            self.assertIn('皮质护理', text)
            self.assertIn('新客', text)
            self.assertIn('全站', text)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_dry_run_no_write(self):
        path, tmpdir = self._write_md(SAMPLE_MD)
        try:
            output = Path(tmpdir) / 'output.md'
            counts = strip_asr_terms(path, output, dry_run=True)
            self.assertGreater(sum(counts.values()), 5)
            # 输出文件不应生成
            self.assertFalse(output.exists())
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_input_not_found(self):
        """main() 对不存在的输入返回 exit code 1。"""
        import io
        import contextlib
        from scripts.strip_asr_terms import main
        bad = Path('/nonexistent/file.md')
        output = Path('/tmp/output.md')

        # 模拟 sys.argv
        old_argv = sys.argv
        sys.argv = ['x', str(bad), '-o', str(output)]
        try:
            # main() 在错误时 sys.exit(1),不 raise,直接返回
            with contextlib.redirect_stderr(io.StringIO()):
                rc = main()
            self.assertEqual(rc, 1)
        finally:
            sys.argv = old_argv


if __name__ == '__main__':
    unittest.main(verbosity=2)
