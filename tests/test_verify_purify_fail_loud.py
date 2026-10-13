"""test_verify_purify_fail_loud.py — C3 阶段 --strict 产物验证测试

覆盖:
  1. 干净 md → PASS
  2. 含 ERROR 标记的 strict 产物 → FAIL
  3. 含 ERROR 标记的多种变体
  4. 在 verify_all RULES 中注册
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(__file__.replace("\\", "/").rsplit("/", 2)[0]))

import scripts.verify_all as va
from scripts.verify_all import verify_purify_fail_loud


def _write_md(content: str, name: str = 'test.md'):
    tmpdir = tempfile.mkdtemp()
    path = Path(tmpdir) / name
    path.write_text(content, encoding='utf-8')
    return path, tmpdir


def _cleanup(tmp):
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


CLEAN_MD = """# Title

## 1. 一章

正常内容。
"""

ERROR_MARKED_MD = """# Title

## 1. 一章

> **ERROR**:LLM 净化失败(strict 模式)

原始 ASR 内容
"""


class TestVerifyPurifyFailLoud(unittest.TestCase):

    def test_pass_clean_md(self):
        """干净 md 不含 ERROR 标记 → PASS。"""
        path, tmp = _write_md(CLEAN_MD)
        try:
            r = verify_purify_fail_loud(path)
            self.assertTrue(r.passed)
        finally:
            _cleanup(tmp)

    def test_fail_with_error_marker(self):
        """含 ERROR 标记(strict 残留)→ FAIL。"""
        path, tmp = _write_md(ERROR_MARKED_MD)
        try:
            r = verify_purify_fail_loud(path)
            self.assertFalse(r.passed)
            self.assertIn("ERROR", r.message)
        finally:
            _cleanup(tmp)

    def test_fail_with_alternative_error_format(self):
        """替代 ERROR 标记格式 `**ERROR**:LLM 失败` 也能检测。"""
        md = """# Title

## 1. 一章

> **ERROR**:LLM 失败

content
"""
        path, tmp = _write_md(md)
        try:
            r = verify_purify_fail_loud(path)
            self.assertFalse(r.passed)
        finally:
            _cleanup(tmp)

    def test_pass_partial_keyword(self):
        """部分匹配 ERROR 不应触发(只在 strict 产物语境下)。"""
        md = """# Title

## 1. 一章

ERROR 监控日志中提到:网络抖动。
"""
        path, tmp = _write_md(md)
        try:
            # 单独 "ERROR 监控" 不是 strict 产物标记 → PASS
            r = verify_purify_fail_loud(path)
            self.assertTrue(r.passed)
        finally:
            _cleanup(tmp)

    def test_registered_in_rules(self):
        """PURIFY_FAIL_LOUD 应在 RULES 注册表中。"""
        names = [name for name, _ in va.RULES]
        self.assertIn('PURIFY_FAIL_LOUD', names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
