"""test_purify_max_chars.py — A4 MAX_CHARS + --strict flag 单元测试

覆盖:
  1. 超 max_chars 输入 → AssertionError
  2. LLM 全部失败 + --strict → 写 ERROR 标记 + exit 2
  3. LLM 全部失败 + 默认 → fail-soft,降级用骨架对齐
  4. 正常流程仍可走(max_chars=8000 兼容默认)
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.purify_v4_4_hierarchical as pvh
from scripts.purify_v4_4_hierarchical import (
    DEFAULT_MAX_CHARS,
    Chunk,
    purify_chunk,
    purify_document,
    _fallback_alignment,
)


# 测试样本 ---------------------------------------------------------

SAMPLE_SMALL = """# 培训讲义

> 课程来源

## 1. 产品裂变底层逻辑

电钻是经典。

## 2. 隐性需求挖掘

关键词告诉路径。
"""

# 巨型 H2(> 8K chars,触发 max_chars assert)
SAMPLE_OVERSIZE = "# 培训讲义\n\n" + "## 1. Big\n\n" + ("lorem ipsum " * 1000) + "\n\n## 2. Small\n\nshort\n"


# 1. 超 max_chars 触发 assert -------------------------------------

class TestMaxCharsAssert(unittest.TestCase):
    def test_oversized_chunk_raises(self):
        """单 chunk 超过 max_chars → AssertionError。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.md"
            out = Path(tmp) / "out.md"
            inp.write_text(SAMPLE_OVERSIZE, encoding="utf-8")

            with self.assertRaises(AssertionError) as cm:
                purify_document(
                    inp, out,
                    workers=1,
                    max_chars=500,  # 强制触发
                )
            self.assertIn("max_chars", str(cm.exception))

    def test_max_chars_zero_raises(self):
        """max_chars=0 → AssertionError(参数校验)。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.md"
            out = Path(tmp) / "out.md"
            inp.write_text(SAMPLE_SMALL, encoding="utf-8")

            with self.assertRaises(AssertionError) as cm:
                purify_document(inp, out, max_chars=0)
            self.assertIn("max_chars 必须 > 0", str(cm.exception))


# 2. LLM 失败 + --strict → 写 ERROR 标记 + exit 2 ----------------

class TestStrictFailLoud(unittest.TestCase):
    def test_strict_writes_error_marker_and_exit_2(self):
        """LLM 全部失败 + --strict → 输出含 ERROR 标记 + return code 2。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.md"
            out = Path(tmp) / "out.md"
            inp.write_text(SAMPLE_SMALL, encoding="utf-8")

            with patch('scripts.purify_v4_4_hierarchical.safe_llm_call') as mock_llm:
                # 让 LLM 持续返回错误(模拟 all-retry 失败)
                mock_llm.return_value = ("", "error")

                rc = purify_document(
                    inp, out,
                    workers=1,
                    strict=True,
                )
                self.assertEqual(rc, 2)
                self.assertTrue(out.exists())
                content = out.read_text(encoding="utf-8")
                # 严格模式应写 ERROR 标记
                self.assertIn("**ERROR**", content)
                self.assertIn("LLM 净化失败", content)

    def test_strict_with_ok_does_not_write_error(self):
        """LLM 正常 + --strict → 不写 ERROR 标记 + return 0。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.md"
            out = Path(tmp) / "out.md"
            inp.write_text(SAMPLE_SMALL, encoding="utf-8")

            with patch('scripts.purify_v4_4_hierarchical.safe_llm_call') as mock_llm:
                def good_llm(*args, **kwargs):
                    return ("## 1. 产品裂变底层逻辑\n\ncleaned\n", "ok")
                mock_llm.side_effect = good_llm

                rc = purify_document(
                    inp, out,
                    workers=1,
                    strict=True,
                )
                self.assertEqual(rc, 0)
                self.assertTrue(out.exists())
                content = out.read_text(encoding="utf-8")
                self.assertNotIn("**ERROR**", content)


# 3. LLM 失败 + 默认 fail-soft → 降级用骨架对齐 -----------------

class TestFailSoftDefault(unittest.TestCase):
    def test_fail_soft_uses_skeleton_alignment(self):
        """LLM 全部失败 + 默认 → fail-soft,降级用骨架对齐(不写 ERROR)。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.md"
            out = Path(tmp) / "out.md"
            inp.write_text(SAMPLE_SMALL, encoding="utf-8")

            with patch('scripts.purify_v4_4_hierarchical.safe_llm_call') as mock_llm:
                mock_llm.return_value = ("", "error")

                rc = purify_document(
                    inp, out,
                    workers=1,
                    strict=False,  # 默认
                )
                # fail-soft:即使全部失败也返回 0
                self.assertEqual(rc, 0)
                self.assertTrue(out.exists())
                content = out.read_text(encoding="utf-8")
                # 不应写 ERROR 标记
                self.assertNotIn("**ERROR**", content)
                # 应保留原 H2 标题
                self.assertIn("## 1. 产品裂变底层逻辑", content)


# 4. 默认 max_chars 兼容正常流程 ---------------------------------

class TestBackwardCompat(unittest.TestCase):
    def test_default_max_chars_8000(self):
        """默认 max_chars=8000 兼容正常小文档。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.md"
            out = Path(tmp) / "out.md"
            inp.write_text(SAMPLE_SMALL, encoding="utf-8")

            with patch('scripts.purify_v4_4_hierarchical.safe_llm_call') as mock_llm:
                def good_llm(*args, **kwargs):
                    prompt = args[0] if args else kwargs.get('prompt', '')
                    import re
                    m = re.search(r"本块在 cleaned.md 中对应的 H2 标题为:\s*(.+?)$", prompt, re.MULTILINE)
                    h2 = m.group(1).strip() if m else "x"
                    return (f"## {h2}\n\ncleaned", "ok")
                mock_llm.side_effect = good_llm

                rc = purify_document(
                    inp, out,
                    workers=1,
                    max_chars=DEFAULT_MAX_CHARS,
                )
                self.assertEqual(rc, 0)
                content = out.read_text(encoding="utf-8")
                # 验证 H2 标题被保留
                self.assertIn("## 1. 产品裂变底层逻辑", content)
                self.assertIn("## 2. 隐性需求挖掘", content)

    def test_default_max_chars_constant(self):
        """DEFAULT_MAX_CHARS = 8000(SKILL Gotcha:超出会让 LLM 自由发挥)。"""
        self.assertEqual(DEFAULT_MAX_CHARS, 8000)


# 5. CLI --max-chars / --strict 暴露 -------------------------------

class TestCliArgs(unittest.TestCase):
    def test_help_shows_max_chars_and_strict(self):
        """--max-chars 和 --strict 在 argparse 中注册。"""
        import argparse
        # 复用 main() 的 parser 注册,验证参数存在
        import importlib
        mod = importlib.import_module("scripts.purify_v4_4_hierarchical")
        # 调用 main() with --help 会被 argparse 拦截,我们直接 import + 模拟解析
        # 简化:直接检查 main() 中 argparse 注册的 flag
        src = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertIn("--max-chars", src)
        self.assertIn("--strict", src)
        self.assertIn("MAX_CHARS", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
