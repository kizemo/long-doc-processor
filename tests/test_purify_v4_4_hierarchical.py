"""test_purify_v4_4_hierarchical.py — 单元测试 purify_v4_4_hierarchical.py

覆盖维度:
1. H2 标题提取(extract_h2_titles)
2. skeleton 加载(extract_skeleton_h2)
3. chunk 切分(split_into_chunks):H2 数 ≤ n_chunks → 1:1 / > n_chunks → 合并
4. Chunk 数据结构
5. LLM 净化(purify_chunk) + retry + 兜底骨架对齐(_fallback_alignment)
6. Markdown wrapper 剥离
7. prompt 加强(_strengthen_prompt)
8. 完整 purify_document 流程(LLM mock)
9. dry-run 模式
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
    DEFAULT_N_CHUNKS,
    Chunk,
    extract_h2_titles,
    extract_skeleton_h2,
    purify_chunk,
    purify_document,
    split_into_chunks,
    _fallback_alignment,
    _strip_markdown_wrapper,
    _strengthen_prompt,
)


# 测试样本 ---------------------------------------------------------

SAMPLE_INPUT = """# 培训讲义

> 课程来源: 2026-09-12 直播

## 1. 产品裂变底层逻辑

嗯...今天讲电钻案例。电钻是经典。电钻是经典。电钻是经典。
[掌声] 大家看一下图片。

### 1.1 电钻案例

电钻展示了平台规则。

### 1.2 指甲剪案例

指甲剪也展示了同一逻辑。

## 2. 隐性需求挖掘

用户搜索时,常隐藏真实需求。

### 2.1 关键词维度

关键词告诉搜索路径。

## 7. 总结与行动建议

三个关键点。

### 7.1 全文要点回顾

- 要点 1
- 要点 2
"""

SAMPLE_SKELETON = """# 培训讲义骨架

## 1. 产品裂变底层逻辑

## 2. 隐性需求挖掘

## 7. 总结与行动建议
"""


# H2 标题提取 ---------------------------------------------------

class TestExtractH2Titles(unittest.TestCase):
    """extract_h2_titles 函数"""

    def test_basic_extraction(self):
        titles = extract_h2_titles(SAMPLE_INPUT)
        self.assertEqual(titles, ['1. 产品裂变底层逻辑', '2. 隐性需求挖掘', '7. 总结与行动建议'])

    def test_no_h2(self):
        titles = extract_h2_titles("# Title\n\ncontent")
        self.assertEqual(titles, [])

    def test_ignores_h3(self):
        titles = extract_h2_titles("## 1. A\n\n### 1.1 sub\n\n## 2. B\n")
        self.assertEqual(titles, ['1. A', '2. B'])

    def test_handles_h1_inside_content(self):
        """H1 在内容中不算 H2,但 H2 仍识别"""
        titles = extract_h2_titles("# Title\n\n## 1. A\n\n## 2. B\n")
        self.assertEqual(titles, ['1. A', '2. B'])


class TestExtractSkeletonH2(unittest.TestCase):
    """extract_skeleton_h2 文件读取"""

    def test_load_skeleton(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write(SAMPLE_SKELETON)
            tmp_path = Path(f.name)
        try:
            titles = extract_skeleton_h2(tmp_path)
            self.assertEqual(titles, ['1. 产品裂变底层逻辑', '2. 隐性需求挖掘', '7. 总结与行动建议'])
        finally:
            tmp_path.unlink()

    def test_missing_skeleton(self):
        titles = extract_skeleton_h2(Path('/nonexistent/skeleton.md'))
        self.assertEqual(titles, [])


# chunk 切分 -----------------------------------------------------

class TestSplitIntoChunks(unittest.TestCase):
    """split_into_chunks 函数"""

    def test_1_to_1_when_h2_le_n_chunks(self):
        """H2 数 ≤ n_chunks 时,每个 H2 = 1 chunk"""
        chunks = split_into_chunks(SAMPLE_INPUT, skeleton_h2=[], n_chunks=8)
        self.assertEqual(len(chunks), 3)  # 3 个 H2
        self.assertEqual(chunks[0].chunk_index, 1)
        self.assertEqual(chunks[0].expected_h2_title, '1. 产品裂变底层逻辑')
        self.assertIn('电钻案例', chunks[0].raw_text)

    def test_h2_exceeds_n_chunks_merged(self):
        """H2 数 > n_chunks 时,合并相邻 H2"""
        # 10 个 H2 + n_chunks=3 → 应分 3 个 chunk
        md = '\n\n'.join(f'## {i}. Title {i}\n\ncontent' for i in range(1, 11))
        chunks = split_into_chunks(md, skeleton_h2=[], n_chunks=3)
        self.assertEqual(len(chunks), 3)

    def test_skeleton_overrides_actual_title(self):
        """skeleton_h2 非空时,期望标题取 skeleton[0] 而非实际 H2"""
        # input 实际 H2: "1. 实际标题";skeleton H2: "1. 期望标题"
        md = "# Title\n\n## 1. 实际标题\n\ncontent"
        chunks = split_into_chunks(md, skeleton_h2=['1. 期望标题'], n_chunks=8)
        self.assertEqual(chunks[0].expected_h2_title, '1. 期望标题')

    def test_no_h2_single_chunk(self):
        """无 H2 时,整个 preamble 作为 1 chunk"""
        md = "# Title\n\ncontent without any H2"
        chunks = split_into_chunks(md, skeleton_h2=[], n_chunks=8)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].expected_h2_title, '(no H2)')

    def test_chunk_raw_text_complete(self):
        """chunk raw_text 含完整 H2 标题行"""
        chunks = split_into_chunks(SAMPLE_INPUT, skeleton_h2=[], n_chunks=8)
        # chunk[0] 的 raw_text 以 "## 1." 开头
        self.assertTrue(chunks[0].raw_text.startswith('## 1.'))


# Markdown wrapper 剥离 -------------------------------------------

class TestStripMarkdownWrapper(unittest.TestCase):
    """_strip_markdown_wrapper 函数"""

    def test_no_wrapper(self):
        self.assertEqual(_strip_markdown_wrapper("plain text"), "plain text")

    def test_markdown_wrapper(self):
        self.assertEqual(
            _strip_markdown_wrapper("```markdown\n# x\ncontent\n```"),
            "# x\ncontent"
        )

    def test_plain_code_wrapper(self):
        self.assertEqual(
            _strip_markdown_wrapper("```\n# x\n```"),
            "# x"
        )


# Fallback 骨架对齐 ----------------------------------------------

class TestFallbackAlignment(unittest.TestCase):
    """_fallback_alignment 函数(LLM 失败兜底)"""

    def test_replace_first_h2(self):
        chunk = Chunk(
            chunk_index=1,
            expected_h2_title='期望标题',
            raw_text='## 实际标题\n\ncontent',
        )
        result = _fallback_alignment(chunk)
        # 实际 H2 应被期望 H2 替换
        self.assertIn('## 期望标题', result)
        self.assertNotIn('## 实际标题', result)
        self.assertIn('content', result)

    def test_add_h2_when_missing(self):
        """原始没有 H2 时,在开头加"""
        chunk = Chunk(
            chunk_index=1,
            expected_h2_title='期望标题',
            raw_text='no heading here',
        )
        result = _fallback_alignment(chunk)
        self.assertTrue(result.startswith('## 期望标题'))
        self.assertIn('no heading here', result)


# prompt 加强 ---------------------------------------------------

class TestStrengthenPrompt(unittest.TestCase):
    """_strengthen_prompt 函数"""

    def test_adds_warning(self):
        base = "original prompt"
        strengthened = _strengthen_prompt(base, attempt=2, observed_h2=3)
        self.assertIn(base, strengthened)
        self.assertIn('第 2 次调用警告', strengthened)
        self.assertIn('3 个 H2', strengthened)


# LLM 净化 (mock) -------------------------------------------------

class TestPurifyChunkMocked(unittest.TestCase):
    """purify_chunk 函数(LLM mock)"""

    def test_successful_first_attempt(self):
        chunk = Chunk(
            chunk_index=1,
            expected_h2_title='1. Test',
            raw_text='## raw\n\ncontent',
        )
        with patch('scripts.purify_v4_4_hierarchical.call_vision') as mock:
            mock.return_value = '## 1. Test\n\ncleaned content'
            result = purify_chunk(chunk, 'model', total_chunks=3)
            self.assertEqual(result, '## 1. Test\n\ncleaned content')
            self.assertEqual(chunk.retry_count, 1)
            self.assertEqual(mock.call_count, 1)

    def test_retry_on_h2_count_mismatch(self):
        """首次输出 H2 ≠ 1 → retry"""
        chunk = Chunk(
            chunk_index=1,
            expected_h2_title='1. Test',
            raw_text='## raw\n\ncontent',
        )
        with patch('scripts.purify_v4_4_hierarchical.call_vision') as mock:
            # 第 1 次:2 个 H2;第 2 次:1 个 H2
            mock.side_effect = [
                '## 1. Test\n\n## 2. Other\n\ncontent',  # 2 H2 → retry
                '## 1. Test\n\ncleaned',                  # 1 H2 → ok
            ]
            result = purify_chunk(chunk, 'model', total_chunks=3)
            self.assertEqual(result, '## 1. Test\n\ncleaned')
            self.assertEqual(mock.call_count, 2)
            self.assertEqual(chunk.retry_count, 2)

    def test_max_retries_fallback(self):
        """3 次都不合规 → 兜底骨架对齐"""
        chunk = Chunk(
            chunk_index=1,
            expected_h2_title='期望 H2',
            raw_text='## 实际 H2\n\ncontent',
        )
        with patch('scripts.purify_v4_4_hierarchical.call_vision') as mock:
            mock.return_value = '## A\n\n## B\n\n## C\n\nbad'  # 3 H2
            result = purify_chunk(chunk, 'model', total_chunks=3)
            # 兜底后应为 expected H2 + content
            self.assertIn('## 期望 H2', result)
            self.assertEqual(mock.call_count, 3)

    def test_llm_empty_response_fallback(self):
        """LLM 连续返回空 → 兜底"""
        chunk = Chunk(
            chunk_index=1,
            expected_h2_title='期望 H2',
            raw_text='content',
        )
        with patch('scripts.purify_v4_4_hierarchical.call_vision') as mock:
            mock.return_value = ""
            result = purify_chunk(chunk, 'model', total_chunks=3)
            self.assertIn('## 期望 H2', result)

    def test_strips_markdown_wrapper(self):
        chunk = Chunk(
            chunk_index=1, expected_h2_title='x', raw_text='raw'
        )
        with patch('scripts.purify_v4_4_hierarchical.call_vision') as mock:
            mock.return_value = '```markdown\n## x\n\ncontent\n```'
            result = purify_chunk(chunk, 'model', total_chunks=1)
            self.assertEqual(result, '## x\n\ncontent')


# 主流程 (mock) --------------------------------------------------

class TestPurifyDocumentMocked(unittest.TestCase):
    """purify_document 全流程"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.input_path = Path(self.tmpdir) / 'input.md'
        self.input_path.write_text(SAMPLE_INPUT, encoding='utf-8')
        self.output_path = Path(self.tmpdir) / 'cleaned.md'

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_dry_run_no_llm(self):
        with patch('scripts.purify_v4_4_hierarchical.call_vision') as mock:
            rc = purify_document(self.input_path, self.output_path, dry_run=True)
            self.assertEqual(rc, 0)
            mock.assert_not_called()
        # dry-run 不应生成输出
        self.assertFalse(self.output_path.exists())

    def test_full_flow_writes_cleaned(self):
        def mock_llm(prompt, images, model):
            # mock:返回包装后的 chunk.expected_h2_title
            import re as _re
            m = _re.search(r"本块在 cleaned.md 中对应的 H2 标题为:\s*(.+?)$", prompt, _re.MULTILINE)
            h2 = m.group(1).strip() if m else "x"
            return f"```markdown\n## {h2}\n\ncleaned content\n```"

        with patch('scripts.purify_v4_4_hierarchical.call_vision', side_effect=mock_llm):
            rc = purify_document(self.input_path, self.output_path, workers=1)
            self.assertEqual(rc, 0)
        self.assertTrue(self.output_path.exists())
        content = self.output_path.read_text(encoding='utf-8')
        # preamble 保留
        self.assertIn('# 培训讲义', content)
        # 所有期望 H2 出现
        for h2 in ['1. 产品裂变底层逻辑', '2. 隐性需求挖掘', '7. 总结与行动建议']:
            self.assertIn(f'## {h2}', content)

    def test_skeleton_passed(self):
        skeleton_path = Path(self.tmpdir) / 'skeleton.md'
        skeleton_path.write_text(SAMPLE_SKELETON, encoding='utf-8')

        def mock_llm(prompt, images, model):
            # 从 prompt 提取期望 H2
            m = re.search(r"本块在 cleaned.md 中对应的 H2 标题为:\s*(.+?)$", prompt, re.MULTILINE)
            h2 = m.group(1).strip() if m else "x"
            return f'## {h2}\n\nok'

        with patch('scripts.purify_v4_4_hierarchical.call_vision', side_effect=mock_llm):
            rc = purify_document(
                self.input_path, self.output_path,
                skeleton_path=skeleton_path,
                workers=1,
            )
            self.assertEqual(rc, 0)

    def test_input_not_found(self):
        bad = Path(self.tmpdir) / 'nonexistent.md'
        rc = purify_document(bad, self.output_path)
        self.assertEqual(rc, 1)


# 集成:dry-run 端到端 --------------------------------------------

class TestDryRunE2E(unittest.TestCase):
    """dry-run 完整流程(无 LLM 调用)"""

    def test_dry_run_logs_chunks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / 'input.md'
            input_path.write_text(SAMPLE_INPUT, encoding='utf-8')
            output_path = Path(tmpdir) / 'cleaned.md'

            with patch('scripts.purify_v4_4_hierarchical.call_vision') as mock:
                rc = purify_document(
                    input_path, output_path,
                    n_chunks=8, dry_run=True,
                )
                self.assertEqual(rc, 0)
                mock.assert_not_called()
            # 不写文件
            self.assertFalse(output_path.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
