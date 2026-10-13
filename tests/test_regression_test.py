"""test_regression_test.py — regression_test.py 单元测试

不调真实 LLM,只测试 case 加载 + 字段校验逻辑。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.regression_test as rt
from scripts.regression_test import run_case


SAMPLE_CLEANED = """# 培训讲义

## 1. 第一章

这是核心内容,因为 GMV 提升 30%。

### 1.1 子节

## 2. 第二章

数据表明转化率翻倍,因此销售额提升。

### 2.1 数据维度

## 7. 总结与行动建议

要点回顾。
"""


class TestRunCase(unittest.TestCase):

    def _write_case(self, expected: dict, raw: str | None = None) -> tuple[Path, Path]:
        tmpdir = tempfile.mkdtemp()
        case_path = Path(tmpdir) / 'case.json'
        cleaned = Path(tmpdir) / 'cleaned.md'
        cleaned.write_text(SAMPLE_CLEANED, encoding='utf-8')

        case = {
            'name': 'test_case',
            'input_md': str(cleaned),
            'expected': expected,
        }
        if raw:
            raw_path = Path(tmpdir) / 'raw.md'
            raw_path.write_text(raw, encoding='utf-8')
            case['raw_md'] = str(raw_path)

        case_path.write_text(json.dumps(case, ensure_ascii=False), encoding='utf-8')
        return case_path, Path(tmpdir)

    def test_h2_count_min_pass(self):
        case_path, tmpdir = self._write_case({'h2_count_min': 3})
        try:
            ok, errors = run_case(case_path)
            self.assertTrue(ok, errors)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_h2_count_min_fail(self):
        case_path, tmpdir = self._write_case({'h2_count_min': 10})
        try:
            ok, errors = run_case(case_path)
            self.assertFalse(ok)
            self.assertTrue(any('H2' in e for e in errors))
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_h3_count_min(self):
        case_path, tmpdir = self._write_case({'h3_count_min': 2})
        try:
            ok, _ = run_case(case_path)
            self.assertTrue(ok)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_must_contain(self):
        case_path, tmpdir = self._write_case({'must_contain': ['核心内容', '转化率']})
        try:
            ok, _ = run_case(case_path)
            self.assertTrue(ok)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_must_contain_fail(self):
        case_path, tmpdir = self._write_case({'must_contain': ['NONEXISTENT_STRING']})
        try:
            ok, errors = run_case(case_path)
            self.assertFalse(ok)
            self.assertTrue(any('NONEXISTENT' in e for e in errors))
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_must_not_contain(self):
        case_path, tmpdir = self._write_case({'must_not_contain': ['讲师认为', '学员搜索']})
        try:
            ok, _ = run_case(case_path)
            self.assertTrue(ok)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_must_not_contain_fail(self):
        """检测转录元数据 / 讲师前缀污染"""
        case_path, tmpdir = self._write_case({'must_not_contain': ['核心内容']})
        try:
            ok, errors = run_case(case_path)
            self.assertFalse(ok)
            self.assertTrue(any('核心内容' in e for e in errors))
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_cjk_retention_min(self):
        raw = SAMPLE_CLEANED + '\n\n## 8. 额外章节\n\n更多内容\n'
        case_path, tmpdir = self._write_case({'cjk_retention_min': 80}, raw=raw)
        try:
            ok, _ = run_case(case_path)
            self.assertTrue(ok)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_input_not_found(self):
        case = {
            'name': 'missing',
            'input_md': '/nonexistent/file.md',
            'expected': {},
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(case, f)
            case_path = Path(f.name)
        try:
            ok, errors = run_case(case_path)
            self.assertFalse(ok)
            self.assertTrue(any('不存在' in e for e in errors))
        finally:
            case_path.unlink()


if __name__ == '__main__':
    unittest.main(verbosity=2)
