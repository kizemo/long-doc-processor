"""test_chunking_unified.py — C2 阶段 chunking.py 统一集成测试

覆盖:
  1. _purify_smooth 删除了重复定义,改 import 自 chunking
  2. H2Block / split_by_h2 / split_oversized_h2 / chunk_for_llm 行为一致
  3. _purify_smooth 中的 H2Block 就是 chunking.H2Block(同一对象)
  4. MAX_CHUNK_CHARS = chunking.MAX_CHARS = 8000
  5. _split_by_chars 也从 chunking 导入
  6. _purify_smooth.smooth_document 用 chunk_for_llm 一次性切分
"""
from __future__ import annotations

import sys
import unittest

sys.path.insert(0, str(__file__.replace("\\", "/").rsplit("/", 2)[0]))

import scripts._purify_smooth as smooth
import scripts.chunking as chunking
from scripts.chunking import H2Block, MAX_CHARS


class TestChunkingUnified(unittest.TestCase):
    """v4.21 C2 阶段:_purify_smooth 不再定义 H2Block 等,从 chunking 导入。"""

    def test_purify_smooth_h2block_is_chunking_h2block(self):
        """_purify_smooth.H2Block === chunking.H2Block(同一对象,非副本)。"""
        self.assertIs(smooth.H2Block, chunking.H2Block)

    def test_purify_smooth_split_by_h2_is_chunking(self):
        """split_by_h2 是同一函数。"""
        self.assertIs(smooth.split_by_h2, chunking.split_by_h2)

    def test_purify_smooth_split_oversized_h2_is_chunking(self):
        """split_oversized_h2 是同一函数。"""
        self.assertIs(smooth.split_oversized_h2, chunking.split_oversized_h2)

    def test_purify_smooth_max_chunk_chars_is_8000(self):
        """MAX_CHUNK_CHARS = 8000(从 chunking 导入)。"""
        self.assertEqual(smooth.MAX_CHUNK_CHARS, 8000)
        self.assertEqual(smooth.MAX_CHUNK_CHARS, MAX_CHARS)

    def test_split_by_chars_imported(self):
        """_split_by_chars 也从 chunking 导入。"""
        self.assertIs(smooth._split_by_chars, chunking._split_by_chars)

    def test_purify_smooth_no_local_h2block_definition(self):
        """_purify_smooth 模块 dict 中不应再有 H2Block / split_by_h2 的本地定义。

        通过 inspect.getsource 验证 _purify_smooth.py 中没有 `def split_by_h2` 或 `@dataclass\nclass H2Block`。
        """
        import inspect
        src = inspect.getsource(smooth)
        # 不应再定义 H2Block 类
        self.assertNotIn("class H2Block", src, "_purify_smooth 仍含 H2Block 类定义")
        # 不应再定义 split_by_h2 函数
        self.assertNotIn("def split_by_h2(", src, "_purify_smooth 仍含 split_by_h2 函数")
        # 不应再定义 split_oversized_h2 函数
        self.assertNotIn("def split_oversized_h2(", src, "_purify_smooth 仍含 split_oversized_h2 函数")

    def test_chunk_for_llm_imported(self):
        """chunk_for_llm 公共入口已 import。"""
        self.assertTrue(hasattr(smooth, "chunk_for_llm"))
        self.assertIs(smooth.chunk_for_llm, chunking.chunk_for_llm)


class TestBehaviorConsistent(unittest.TestCase):
    """chunking 重构后行为不变(同输入同输出)。"""

    SAMPLE = """# Title

> intro

## 1. 一章

content of 1

### 1.1 sub

sub content

## 2. 二章

content of 2
"""

    def test_split_by_h2_same_output(self):
        """_purify_smooth.split_by_h2 输出与 chunking.split_by_h2 一致。"""
        p1, b1 = smooth.split_by_h2(self.SAMPLE)
        p2, b2 = chunking.split_by_h2(self.SAMPLE)
        self.assertEqual(p1, p2)
        self.assertEqual(len(b1), len(b2))
        for a, b in zip(b1, b2):
            self.assertEqual(a.title_line, b.title_line)
            self.assertEqual(a.raw_text, b.raw_text)

    def test_split_oversized_h2_same_output(self):
        """split_oversized_h2 输出一致(用同一 H2Block 输入)。"""
        preamble, blocks = smooth.split_by_h2(self.SAMPLE)
        b = blocks[0]
        out1 = smooth.split_oversized_h2(b, max_chars=500)
        out2 = chunking.split_oversized_h2(b, max_chars=500)
        self.assertEqual(len(out1), len(out2))
        for a, b2 in zip(out1, out2):
            self.assertEqual(a.raw_text, b2.raw_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
