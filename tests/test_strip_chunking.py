"""test_strip_chunking.py — A3 strip_* 复用 chunking 单元测试

覆盖:
  1. chunk_for_llm 按 H2 切分
  2. 超长 H2 按 H3 再切
  3. strip_document 并发调 LLM(每个 H2 块独立)
  4. CLI --max-chars 暴露
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.chunking import (
    H2Block,
    chunk_for_llm,
    split_by_h2,
    split_oversized_h2,
)
from scripts.strip_lecturer_preamble import (
    strip_document as lecturer_strip_document,
    strip_block as lecturer_strip_block,
)
from scripts.strip_role_persona import (
    strip_document as persona_strip_document,
    strip_block as persona_strip_block,
)


# 测试样本 ---------------------------------------------------------

SAMPLE_MD = """# 培训讲义

> 课程来源: 2026-09-12 直播

## 1. 产品裂变底层逻辑

讲师认为电钻是经典。

### 1.1 电钻案例

案例显示电钻展示了平台规则。

### 1.2 指甲剪案例

指甲剪也展示了同一逻辑。

## 2. 隐性需求挖掘

学员搜索时,常隐藏真实需求。

## 3. 转化路径

讲师总结:转化路径分 3 步。

### 3.1 步骤 1

直接陈述步骤 1。

### 3.2 步骤 2

直接陈述步骤 2。
"""


# 1. chunk_for_llm 按 H2 切分 -------------------------------------

class TestChunkForLlm(unittest.TestCase):
    def test_split_by_h2_basic(self):
        """split_by_h2 切出 3 个 H2 块 + preamble。"""
        preamble, blocks = split_by_h2(SAMPLE_MD)
        self.assertIn("课程来源", preamble)
        self.assertEqual(len(blocks), 3)
        self.assertTrue(blocks[0].title_line.startswith("## 1."))
        self.assertTrue(blocks[1].title_line.startswith("## 2."))
        self.assertTrue(blocks[2].title_line.startswith("## 3."))

    def test_no_h2_returns_empty(self):
        """无 H2 输入 → 返回 (text, [])。"""
        text = "# Title\n\ncontent only"
        preamble, blocks = split_by_h2(text)
        self.assertEqual(blocks, [])

    def test_oversized_split_by_h3(self):
        """超 8K H2 块按 H3 再切。"""
        # 构造一个 H2 含多 H3,总长 > 100 chars 触发切分
        big_h2 = "## 1. Big\n\n" + ("### 1." + str(0) + " sub\n\ncontent\n\n" * 50)
        preamble, blocks = split_by_h2(big_h2)
        self.assertEqual(len(blocks), 1)
        sub_blocks = split_oversized_h2(blocks[0], max_chars=500)
        # 应被切为多块
        self.assertGreater(len(sub_blocks), 1)

    def test_chunk_for_llm_end_to_end(self):
        """chunk_for_llm 完整流程:大文档切出 N 个 LLM-ready 块。"""
        # 构造大 H2 块,确保触发 H3 子块切分
        big_md = (
            "# Title\n\n"
            + "## 1. Big\n\n"
            + "intro content " * 30
            + "\n\n"
            + "### 1.1 sub\n\n" + ("content " * 30) + "\n\n"
            + "### 1.2 sub\n\n" + ("content " * 30) + "\n\n"
            + "## 2. Small\n\nshort\n"
        )
        preamble, chunks = chunk_for_llm(big_md, max_chars=500)
        # 大 H2 触发 H3 子切分 → 切出 >2 个 chunks
        self.assertGreater(len(chunks), 2)
        # 每块 ≤ max_chars
        for c in chunks:
            self.assertLessEqual(len(c.raw_text), 500)


# 2. strip_document 并发 LLM(每 H2 块独立调) --------------------

class TestStripLecturerDocumentChunked(unittest.TestCase):
    def test_strip_document_3_h2_chunks(self):
        """3 个 H2 → 3 次 LLM 调用(每个 H2 独立调)。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.md"
            out = Path(tmp) / "out.md"
            inp.write_text(SAMPLE_MD, encoding="utf-8")

            with patch('scripts.strip_lecturer_preamble.safe_llm_call') as mock_llm:
                def good_llm(*args, **kwargs):
                    return ("cleaned content", "ok")
                mock_llm.side_effect = good_llm

                rc = lecturer_strip_document(inp, out, workers=1)
                self.assertEqual(rc, 0)
                # SAMPLE_MD 有 3 个 H2,每个 ≤ 8K → 应是 3 次 LLM 调用
                self.assertEqual(mock_llm.call_count, 3)
                self.assertTrue(out.exists())

    def test_strip_document_max_chars_triggers_subchunk(self):
        """max_chars 小 → 触发 H3 再切,调用次数 > H2 数。"""
        # 构造大 H2 块确保触发 H3 子切分
        big_md = (
            "# Title\n\n"
            + "## 1. Big\n\n"
            + "intro content " * 30
            + "\n\n"
            + "### 1.1 sub\n\n" + ("content " * 30) + "\n\n"
            + "### 1.2 sub\n\n" + ("content " * 30) + "\n\n"
            + "## 2. Small\n\nshort\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.md"
            out = Path(tmp) / "out.md"
            inp.write_text(big_md, encoding="utf-8")

            with patch('scripts.strip_lecturer_preamble.safe_llm_call') as mock_llm:
                mock_llm.return_value = ("x", "ok")

                rc = lecturer_strip_document(inp, out, workers=1, max_chars=200)
                self.assertEqual(rc, 0)
                # max_chars=200 触发 H3 子块切分 → 调用次数 > 2(2 个 H2)
                self.assertGreater(mock_llm.call_count, 2)

    def test_strip_document_llm_failure_keeps_original(self):
        """LLM 失败 → 降级原内容(fail-soft)。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.md"
            out = Path(tmp) / "out.md"
            inp.write_text(SAMPLE_MD, encoding="utf-8")

            with patch('scripts.strip_lecturer_preamble.safe_llm_call') as mock_llm:
                mock_llm.return_value = ("", "error")

                rc = lecturer_strip_document(inp, out, workers=1)
                # fail-soft:即使 LLM 失败也返回 0(写入降级内容)
                self.assertEqual(rc, 0)
                self.assertTrue(out.exists())
                # 应保留原 H2 标题
                content = out.read_text(encoding="utf-8")
                self.assertIn("## 1. 产品裂变底层逻辑", content)


class TestStripRolePersonaDocumentChunked(unittest.TestCase):
    def test_strip_document_3_h2_chunks(self):
        """3 个 H2 → 3 次 LLM 调用。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.md"
            out = Path(tmp) / "out.md"
            inp.write_text(SAMPLE_MD, encoding="utf-8")

            with patch('scripts.strip_role_persona.safe_llm_call') as mock_llm:
                mock_llm.return_value = ("refactored", "ok")

                rc = persona_strip_document(inp, out, workers=1)
                self.assertEqual(rc, 0)
                self.assertEqual(mock_llm.call_count, 3)


# 3. CLI --max-chars 暴露 -----------------------------------------

class TestCliArgs(unittest.TestCase):
    def test_strip_lecturer_help_shows_max_chars(self):
        import importlib
        mod_lecturer = importlib.import_module("scripts.strip_lecturer_preamble")
        src = Path(mod_lecturer.__file__).read_text(encoding="utf-8")
        self.assertIn("--max-chars", src)
        self.assertIn("DEFAULT_MAX_CHARS", src)

    def test_strip_role_persona_help_shows_max_chars(self):
        import importlib
        mod_persona = importlib.import_module("scripts.strip_role_persona")
        src = Path(mod_persona.__file__).read_text(encoding="utf-8")
        self.assertIn("--max-chars", src)
        self.assertIn("DEFAULT_MAX_CHARS", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
