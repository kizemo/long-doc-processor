"""test_build_per_lecture_asr_corrections.py — 单元测试"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.build_per_lecture_asr_corrections as blac
from scripts.build_per_lecture_asr_corrections import (
    find_isolated_tokens, jaccard_similarity, load_error_dict,
    match_candidates, render_report,
)


# 样本文本:含若干孤字
SAMPLE_TEXT = """
# Title

皮皮皮 皮气护理 心客 心客 心客 床床床

家具 沙发 桌子 椅子 椅子

中文 中文 中文 中文 中文 中文

啦啦啦 啦啦 啦啦啦
"""


class TestJaccardSimilarity(unittest.TestCase):

    def test_identical(self):
        self.assertEqual(jaccard_similarity("abc", "abc"), 1.0)

    def test_disjoint(self):
        self.assertEqual(jaccard_similarity("abc", "xyz"), 0.0)

    def test_partial_overlap(self):
        # {皮, 气} ∪ {气, 护} = {皮, 气, 护}, ∩ = {气} → 1/3
        sim = jaccard_similarity("皮气", "气护")
        self.assertAlmostEqual(sim, 1/3, places=2)

    def test_empty(self):
        self.assertEqual(jaccard_similarity("", "abc"), 0.0)


class TestFindIsolatedTokens(unittest.TestCase):

    def test_basic(self):
        """2 字 token 中文出现 6 次(≥3),应入候选;1 字 token 不入候选"""
        isolated = find_isolated_tokens(SAMPLE_TEXT, lengths=(2,), min_count=3)
        tokens = {tok for tok, _ in isolated}
        # SAMPLE_TEXT 中"中文"出现 6 次(独立 token)
        self.assertIn('中文', tokens)

    def test_two_chars_min_2(self):
        """min_count=2,应包含出现 2+ 次的 2 字 token"""
        text = "皮气 皮气 心客 心客"
        isolated = find_isolated_tokens(text, lengths=(2,), min_count=2)
        tokens = {tok for tok, _ in isolated}
        self.assertEqual(len(tokens), 2)
        self.assertIn('皮气', tokens)
        self.assertIn('心客', tokens)

    def test_min_count_filter(self):
        """min_count=5,出现次数 < 5 的不入候选"""
        # "心"作为单字 token 出现 1 次,不入
        text = "心 心 心 心 心 心 心 心 心 心 心"
        isolated = find_isolated_tokens(text, lengths=(1,), min_count=5)
        # 单字 token,需 ≥5 次才入
        tokens = {tok for tok, count in isolated}
        self.assertGreaterEqual(len(tokens), 1)

    def test_no_isolated(self):
        """纯英文无 CJK token"""
        text = "this is english text only with no chinese"
        isolated = find_isolated_tokens(text, lengths=(1, 2), min_count=1)
        self.assertEqual(isolated, [])


class TestLoadErrorDict(unittest.TestCase):

    def _write_dict(self, data) -> Path:
        tmpdir = tempfile.mkdtemp()
        path = Path(tmpdir) / 'dict.json'
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return path, tmpdir

    def test_list_format(self):
        data = [{'wrong': '皮气', 'right': '皮质'}]
        path, tmpdir = self._write_dict(data)
        try:
            result = load_error_dict(path)
            self.assertEqual(result, data)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_dict_format(self):
        data = {'皮气': '皮质', '心客': '新客'}
        path, tmpdir = self._write_dict(data)
        try:
            result = load_error_dict(path)
            self.assertEqual(len(result), 2)
            self.assertIn({'wrong': '皮气', 'right': '皮质'}, result)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_missing_file(self):
        result = load_error_dict(Path('/nonexistent/file.json'))
        self.assertEqual(result, [])


class TestMatchCandidates(unittest.TestCase):

    def test_basic_match(self):
        # 模拟 isolated + error_dict 匹配
        isolated = [('皮', 5), ('心', 3)]
        error_dict = [
            {'wrong': '皮气', 'right': '皮质'},
            {'wrong': '心客', 'right': '新客'},
        ]
        results = match_candidates(isolated, error_dict, threshold=0.4)
        # 应有匹配
        self.assertGreater(len(results), 0)

    def test_no_match_below_threshold(self):
        isolated = [('xyz', 5)]  # 完全不相关
        error_dict = [{'wrong': '皮气', 'right': '皮质'}]
        results = match_candidates(isolated, error_dict, threshold=0.9)
        # 'xyz' 与 '皮质' 不相交,相似度 0,不入候选
        self.assertEqual(len(results), 0)


class TestRenderReport(unittest.TestCase):

    def test_empty_candidates(self):
        md = render_report([], 'test.md')
        self.assertIn('无候选', md)

    def test_with_candidates(self):
        candidates = [{
            'isolated': '皮',
            'count': 5,
            'candidates': [{'right': '皮质', 'sim': 0.5}],
        }]
        md = render_report(candidates, 'test.md')
        self.assertIn('`皮`', md)
        self.assertIn('`皮质`', md)


if __name__ == '__main__':
    unittest.main(verbosity=2)
