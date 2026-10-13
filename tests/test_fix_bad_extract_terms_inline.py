"""test_fix_bad_extract_terms_inline.py — 单元测试 v4.12 garbage 清理"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.fix_bad_extract_terms_inline as fbeti
from scripts.fix_bad_extract_terms_inline import (
    clean_terms, is_garbage_rule,
    _is_dangerous_wrong_token, _is_numeric_only, _is_pure_punctuation, _is_self_mapping, _is_too_short,
)


class TestHelperFunctions(unittest.TestCase):

    def test_pure_punctuation(self):
        self.assertTrue(_is_pure_punctuation("|"))
        self.assertTrue(_is_pure_punctuation("# "))
        self.assertTrue(_is_pure_punctuation("  "))
        self.assertFalse(_is_pure_punctuation("|x"))
        self.assertFalse(_is_pure_punctuation("hello"))

    def test_dangerous_wrong_token(self):
        self.assertTrue(_is_dangerous_wrong_token("|"))
        self.assertTrue(_is_dangerous_wrong_token("a|b"))
        self.assertTrue(_is_dangerous_wrong_token("###"))
        self.assertTrue(_is_dangerous_wrong_token("`code`"))
        self.assertFalse(_is_dangerous_wrong_token("石木床"))
        self.assertFalse(_is_dangerous_wrong_token("权占"))

    def test_too_short(self):
        self.assertTrue(_is_too_short("a"))
        self.assertTrue(_is_too_short(""))
        self.assertFalse(_is_too_short("ab"))
        self.assertFalse(_is_too_short("石木床"))

    def test_numeric_only(self):
        self.assertTrue(_is_numeric_only("123"))
        self.assertTrue(_is_numeric_only("0"))
        self.assertFalse(_is_numeric_only("123a"))
        self.assertFalse(_is_numeric_only("GMV"))

    def test_self_mapping(self):
        self.assertTrue(_is_self_mapping({'from': 'x', 'to': 'x'}))
        self.assertFalse(_is_self_mapping({'from': 'x', 'to': 'y'}))


class TestIsGarbageRule(unittest.TestCase):

    def test_valid_rule(self):
        ok, reason = is_garbage_rule({'from': '石木床', 'to': '实木床'})
        self.assertFalse(ok)
        self.assertEqual(reason, '')

    def test_garbage_pipe_token_pipe(self):
        """v4.12 经典 bug: `|` 被作为 ASR 错词"""
        ok, reason = is_garbage_rule({'from': '|', 'to': '医疗器械标签'})
        self.assertTrue(ok)
        # 接受两种检测路径(pure_punctuation 或 dangerous_wrong_token 都触发)
        self.assertTrue(
            'markdown' in reason,
            f"reason 应含 'markdown',实际:{reason}"
        )

    def test_garbage_self_mapping(self):
        ok, reason = is_garbage_rule({'from': 'x', 'to': 'x'})
        self.assertTrue(ok)
        self.assertIn('from == to', reason)

    def test_garbage_too_short(self):
        ok, reason = is_garbage_rule({'from': 'a', 'to': 'b'})
        self.assertTrue(ok)
        self.assertIn('过短', reason)

    def test_garbage_numeric_only(self):
        ok, reason = is_garbage_rule({'from': '123', 'to': '一二三'})
        self.assertTrue(ok)
        self.assertIn('纯数字', reason)

    def test_garbage_missing_from(self):
        ok, reason = is_garbage_rule({'to': 'b'})
        self.assertTrue(ok)
        self.assertIn('缺少 from', reason)

    def test_garbage_missing_to(self):
        ok, reason = is_garbage_rule({'from': 'a'})
        self.assertTrue(ok)
        self.assertIn('缺少 to', reason)

    def test_garbage_too_punct(self):
        """to 仅由 markdown 符号组成"""
        ok, reason = is_garbage_rule({'from': 'ab', 'to': '|'})
        self.assertTrue(ok)
        self.assertIn('仅由 markdown 符号', reason)


class TestCleanTerms(unittest.TestCase):

    def _write_terms(self, rules: list) -> tuple[Path, Path]:
        tmpdir = tempfile.mkdtemp()
        input_path = Path(tmpdir) / 'asr_terms.json'
        output_path = Path(tmpdir) / 'asr_terms_clean.json'
        data = {'rules': rules}
        input_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return input_path, output_path

    def test_clean_pipe_self(self):
        """v4.12 案例:`|` → '医疗器械标签' 应被清理"""
        rules = [
            {'from': '石木床', 'to': '实木床'},     # 正常
            {'from': '|', 'to': '医疗器械标签'},    # garbage
            {'from': '权占', 'to': '全站'},         # 正常
        ]
        ip, op = self._write_terms(rules)
        try:
            removed, reasons = clean_terms(ip, op)
            self.assertEqual(removed, 1)
            self.assertTrue(any('|' in r for r in reasons))
            # 验证输出
            cleaned = json.loads(op.read_text(encoding='utf-8'))
            self.assertEqual(len(cleaned['rules']), 2)
            self.assertNotIn('|', [r['from'] for r in cleaned['rules']])
        finally:
            import shutil
            shutil.rmtree(ip.parent, ignore_errors=True)

    def test_clean_multiple_garbage(self):
        rules = [
            {'from': '石木床', 'to': '实木床'},     # 正常
            {'from': '|', 'to': '医疗器械标签'},    # garbage
            {'from': 'a', 'to': 'b'},              # too short
            {'from': 'x', 'to': 'x'},              # self map
            {'from': '权占', 'to': '全站'},         # 正常
        ]
        ip, op = self._write_terms(rules)
        try:
            removed, reasons = clean_terms(ip, op)
            self.assertEqual(removed, 3)
        finally:
            import shutil
            shutil.rmtree(ip.parent, ignore_errors=True)

    def test_clean_no_garbage(self):
        rules = [
            {'from': '石木床', 'to': '实木床'},
            {'from': '权占', 'to': '全站'},
        ]
        ip, op = self._write_terms(rules)
        try:
            removed, _ = clean_terms(ip, op)
            self.assertEqual(removed, 0)
        finally:
            import shutil
            shutil.rmtree(ip.parent, ignore_errors=True)

    def test_clean_default_overwrites_input(self):
        """不指定 output_path 时,覆盖输入"""
        ip, _ = self._write_terms([{'from': '|', 'to': 'x'}, {'from': 'a', 'to': 'b'}])
        try:
            removed, _ = clean_terms(ip)  # 默认覆盖 input
            self.assertEqual(removed, 2)
            # 重新读,应是空 rules
            data = json.loads(ip.read_text(encoding='utf-8'))
            self.assertEqual(data['rules'], [])
        finally:
            import shutil
            shutil.rmtree(ip.parent, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
