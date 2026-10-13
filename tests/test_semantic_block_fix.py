"""test_semantic_block_fix.py — D3 D0 段级语义净化测试

覆盖:
  1. D0 脚本存在 + CLI 签名
  2. prompt 含 D0 核心约束(段级/不字面/孤立词/ASR 串扰)
  3. 切分使用 chunking.py(C2 集成)
  4. LLM mock 集成(每 H2 块独立调)
  5. fail-soft:LLM 失败 → 降级原内容
  6. 显式禁止同义改写(与 C1 一致)
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(__file__.replace("\\", "/").rsplit("/", 2)[0]))

import scripts.semantic_block_fix as sbf
from scripts.semantic_block_fix import (
    D0_SEMANTIC_PROMPT,
    DEFAULT_MAX_CHARS,
    fix_block,
    semantic_block_fix,
)


SAMPLE_MD = """# Title

## 1. 一章

嗯,今天讲电钻案例。

电钻展示了平台规则。

## 2. 二章

对吧,搜索时,常隐藏需求。
"""


# 1. 基础存在性 + 签名

class TestD3Basic(unittest.TestCase):

    def test_script_exists(self):
        """semantic_block_fix.py 在 scripts/。"""
        path = Path("scripts/semantic_block_fix.py")
        self.assertTrue(path.exists())

    def test_default_max_chars_is_8000(self):
        """默认 8000(SKILL Gotcha:超 8K LLM 自由发挥)。"""
        self.assertEqual(DEFAULT_MAX_CHARS, 8000)


# 2. prompt 含 D0 核心约束

class TestD0PromptConstraints(unittest.TestCase):

    def test_contains_d0_marker(self):
        """含 v4.21 D3 标识。"""
        self.assertIn("D0", D0_SEMANTIC_PROMPT)
        self.assertIn("v4.21", D0_SEMANTIC_PROMPT)

    def test_contains_segment_level_marker(self):
        """含段级修改标识。"""
        self.assertIn("段级", D0_SEMANTIC_PROMPT)

    def test_prohibits_paraphrase(self):
        """显式禁止同义改写(与 C1 一致)。"""
        self.assertIn("同义改写", D0_SEMANTIC_PROMPT)

    def test_prohibits_polishing(self):
        """显式禁止润色用词。"""
        self.assertIn("润色用词", D0_SEMANTIC_PROMPT)

    def test_targets_orphan_words(self):
        """段首/段末孤立词删除(规约 26)。"""
        for kw in ["对/那个/对吧/是吧/嗯/啊/哦"]:
            self.assertIn(kw, D0_SEMANTIC_PROMPT, f"缺孤立词关键词 {kw}")

    def test_targets_asr_crosstalk(self):
        """ASR 串扰删除(规约 26)。"""
        self.assertIn("ASR 串扰", D0_SEMANTIC_PROMPT)


# 3. 切分使用 chunking.py (C2 集成)

class TestD3ChunkingIntegration(unittest.TestCase):

    def test_uses_chunk_for_llm(self):
        """semantic_block_fix 用 chunk_for_llm 切分(C2 统一)。"""
        import inspect
        src = inspect.getsource(semantic_block_fix)
        self.assertIn("chunk_for_llm", src, "D3 没用 chunk_for_llm")

    def test_chunks_count(self):
        """SAMPLE_MD 切出 2 个 H2 块。"""
        from scripts.chunking import chunk_for_llm
        _, chunks = chunk_for_llm(SAMPLE_MD, max_chars=8000)
        self.assertEqual(len(chunks), 2)


# 4. LLM mock 集成

class TestD3LlmMocked(unittest.TestCase):

    def test_fix_block_returns_cleaned(self):
        """LLM 正常 → 返回清理后内容。"""
        with patch('scripts.semantic_block_fix.safe_llm_call') as mock:
            mock.return_value = ("```markdown\ncleaned content\n```", "ok")
            result = fix_block("original content")
            self.assertIn("cleaned content", result)

    def test_fix_block_llm_failure_keeps_original(self):
        """LLM 失败 → 返回原内容(fail-soft)。"""
        with patch('scripts.semantic_block_fix.safe_llm_call') as mock:
            mock.return_value = ("", "error")
            original = "original content"
            result = fix_block(original)
            self.assertEqual(result, original)

    def test_semantic_block_fix_2_h2_chunks(self):
        """SAMPLE_MD 有 2 个 H2 → 2 次 LLM 调用。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.md"
            out = Path(tmp) / "out.md"
            inp.write_text(SAMPLE_MD, encoding="utf-8")

            with patch('scripts.semantic_block_fix.safe_llm_call') as mock:
                mock.return_value = ("```markdown\ncleaned\n```", "ok")
                rc = semantic_block_fix(inp, out, workers=1)
                self.assertEqual(rc, 0)
                # 2 个 H2 块 → 2 次 LLM 调用
                self.assertEqual(mock.call_count, 2)
                self.assertTrue(out.exists())

    def test_input_not_found(self):
        """输入不存在 → exit 1。"""
        with tempfile.TemporaryDirectory() as tmp:
            rc = semantic_block_fix(
                Path(tmp) / "nonexistent.md",
                Path(tmp) / "out.md",
            )
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
