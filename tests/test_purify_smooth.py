"""test_purify_smooth.py — 单元测试 _purify_smooth.py

覆盖维度:
1. H2 切分(preamble + h2_blocks 数量)
2. 超大 H2 按 H3 切分(单块 ≤ max_chars 强制约束)
3. Markdown wrapper 剥离(LLM 返回 ```markdown ... ```)
4. 标题守恒校验(所有 H2/H3/H4 标题必出现)
5. 完整 smooth_document 流程(mock LLM)
6. dry-run 模式(只切不调 LLM)
7. CLI --help / --dry-run
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts._purify_smooth as smooth
from scripts._purify_smooth import (
    H2Block,
    MAX_CHUNK_CHARS,
    SMOOTH_PROMPT_TEMPLATE,
    _split_by_chars,
    _strip_markdown_wrapper,
    split_by_h2,
    split_oversized_h2,
    smooth_block,
    smooth_document,
    validate_title_preservation,
)


# 测试样本 ---------------------------------------------------------

SAMPLE_MD = """# 培训讲义

> 课程来源: 2026-09-12 直播

## 1. 产品裂变底层逻辑

电钻的案例展示了需求差异。

### 1.1 电钻案例

电钻是经典案例。

### 1.2 指甲剪案例

指甲剪也展示了同一逻辑。

## 2. 隐性需求挖掘

用户搜索关键词时,常隐藏真实需求。

### 2.1 关键词维度

关键词告诉搜索路径。

## 7. 总结与行动建议

三个关键点。

### 7.1 全文要点回顾

- 要点 1
- 要点 2

### 7.2 可执行行动清单

按时间顺序拆解。
"""


# H2 切分 --------------------------------------------------------

class TestSplitByH2(unittest.TestCase):
    """H2 切分正确性"""

    def test_basic_split(self):
        preamble, blocks = split_by_h2(SAMPLE_MD)
        # preamble 含 H1 + blockquote
        self.assertIn('# 培训讲义', preamble)
        self.assertIn('> 课程来源', preamble)
        # blocks 含 3 个 H2
        self.assertEqual(len(blocks), 3)
        self.assertTrue(blocks[0].title_line.startswith('## 1.'))
        self.assertTrue(blocks[1].title_line.startswith('## 2.'))
        self.assertTrue(blocks[2].title_line.startswith('## 7.'))

    def test_block_content(self):
        _, blocks = split_by_h2(SAMPLE_MD)
        # 第一个 H2 块含 H3 + 正文
        self.assertIn('电钻的案例', blocks[0].raw_text)
        self.assertIn('### 1.1', blocks[0].raw_text)
        # 不含其他 H2 标题
        self.assertNotIn('## 2.', blocks[0].raw_text)

    def test_empty_doc(self):
        preamble, blocks = split_by_h2("")
        self.assertEqual(preamble, "")
        self.assertEqual(blocks, [])

    def test_no_h2(self):
        """无 H2 标题时,全部内容归 preamble"""
        md = "# Title\n\ncontent\n\nmore"
        preamble, blocks = split_by_h2(md)
        self.assertIn("Title", preamble)
        self.assertEqual(blocks, [])

    def test_h1_not_treated_as_h2(self):
        """H1 不被误判为 H2"""
        md = "# Title\n\n## 1. Chapter\n\ncontent"
        preamble, blocks = split_by_h2(md)
        self.assertEqual(len(blocks), 1)
        self.assertTrue(blocks[0].title_line.startswith('## 1.'))


# 超大 H2 切分 ----------------------------------------------------

class TestSplitOversizedH2(unittest.TestCase):
    """超大 H2 按 H3 切分(单块 ≤ MAX_CHUNK_CHARS)"""

    def test_under_limit_no_split(self):
        block = H2Block(
            title_line='## 1. Small\n',
            content_lines=['content'],
            raw_text='## 1. Small\n\ncontent'
        )
        chunks = split_oversized_h2(block, max_chars=8000)
        self.assertEqual(len(chunks), 1)

    def test_over_limit_split_by_h3(self):
        """超大 H2 按 H3 切分"""
        # 构造一个 ~12K 字符的 H2,含 4 个 H3
        h3_lines = []
        for i in range(4):
            h3_lines.append(f'### {i+1}.1 Subsection {i+1}\n')
            h3_lines.append('\n')
            h3_lines.append('lorem ipsum ' * 200)  # 2400 chars per H3
            h3_lines.append('\n\n')
        h3_content = ''.join(h3_lines)
        big_text = '## 1. Big Chapter\n\n' + 'preamble ' * 500 + '\n\n' + h3_content
        block = H2Block(
            title_line='## 1. Big Chapter\n',
            content_lines=[],
            raw_text=big_text,
        )
        self.assertGreater(len(block.raw_text), 8000)

        chunks = split_oversized_h2(block, max_chars=8000)
        # 至少有 1 个 preamble + 4 个 H3 子块
        self.assertGreaterEqual(len(chunks), 4)
        # 每个子块 ≤ max_chars
        for c in chunks:
            self.assertLessEqual(len(c.raw_text), 8000,
                                  f"chunk size {len(c.raw_text)} 超过 8000")

    def test_over_limit_no_h3_force_split(self):
        """超大 H2 无 H3 时按字符强切"""
        big_text = '## 1. Big\n\n' + 'lorem ipsum ' * 1000  # ~12K chars
        block = H2Block(
            title_line='## 1. Big\n',
            content_lines=[],
            raw_text=big_text,
        )
        chunks = split_oversized_h2(block, max_chars=8000)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c.raw_text), 8000)


# Markdown wrapper 剥离 ----------------------------------------------

class TestStripMarkdownWrapper(unittest.TestCase):
    """剥离 LLM 响应的 ```markdown 包装"""

    def test_no_wrapper(self):
        text = "plain markdown content"
        self.assertEqual(_strip_markdown_wrapper(text), text)

    def test_markdown_wrapper(self):
        text = "```markdown\n# Title\ncontent\n```"
        self.assertEqual(_strip_markdown_wrapper(text), "# Title\ncontent")

    def test_plain_code_wrapper(self):
        text = "```\n# Title\ncontent\n```"
        self.assertEqual(_strip_markdown_wrapper(text), "# Title\ncontent")

    def test_wrapper_with_whitespace(self):
        text = "```markdown   \n# Title\n```\n  "
        result = _strip_markdown_wrapper(text)
        self.assertIn('# Title', result)


# 标题守恒校验 ---------------------------------------------------

class TestValidateTitlePreservation(unittest.TestCase):
    """所有原 H2/H3/H4 标题必出现在输出"""

    def test_all_preserved(self):
        original = [H2Block('', [], SAMPLE_MD)]
        ok, msg = validate_title_preservation(original, SAMPLE_MD)
        self.assertTrue(ok, msg)

    def test_missing_h2(self):
        original = [H2Block('', [], SAMPLE_MD)]
        modified = SAMPLE_MD.replace('## 1. 产品裂变底层逻辑', '')
        ok, msg = validate_title_preservation(original, modified)
        self.assertFalse(ok)
        self.assertIn('产品裂变', msg)

    def test_missing_h3(self):
        original = [H2Block('', [], SAMPLE_MD)]
        modified = SAMPLE_MD.replace('### 1.1 电钻案例', '### 1.1 改写案例')
        ok, msg = validate_title_preservation(original, modified)
        self.assertFalse(ok)


# Smooth block (mocked) ----------------------------------------------

class TestSmoothBlockMocked(unittest.TestCase):
    """smooth_block 函数(LLM 调用 mock)"""

    def test_returns_smoothed_text(self):
        block = H2Block('', [], '## 1. x\n\ncontent')
        with patch('scripts._purify_smooth.call_vision') as mock_llm:
            mock_llm.return_value = '## 1. x\n\nsmoothed content'
            result = smooth_block(block)
            self.assertEqual(result, '## 1. x\n\nsmoothed content')

    def test_strips_markdown_wrapper(self):
        block = H2Block('', [], '## 1. x\n\ncontent')
        with patch('scripts._purify_smooth.call_vision') as mock_llm:
            mock_llm.return_value = '```markdown\n## 1. x\n\nsmoothed\n```'
            result = smooth_block(block)
            self.assertEqual(result, '## 1. x\n\nsmoothed')

    def test_llm_failure_returns_original(self):
        """LLM 失败 → 返回原文(fail-soft)"""
        block = H2Block('', [], '## 1. x\n\ncontent')
        with patch('scripts._purify_smooth.call_vision') as mock_llm:
            mock_llm.side_effect = RuntimeError("API timeout")
            result = smooth_block(block)
            self.assertEqual(result, block.raw_text)

    def test_llm_empty_returns_original(self):
        """LLM 返回空 → 返回原文"""
        block = H2Block('', [], '## 1. x\n\ncontent')
        with patch('scripts._purify_smooth.call_vision') as mock_llm:
            mock_llm.return_value = ""
            result = smooth_block(block)
            self.assertEqual(result, block.raw_text)

    def test_empty_block_returns_unchanged(self):
        """空块短路,不调 LLM"""
        block = H2Block('', [], '   \n')
        with patch('scripts._purify_smooth.call_vision') as mock_llm:
            result = smooth_block(block)
            self.assertEqual(result, '   \n')
            mock_llm.assert_not_called()


# Smooth document (mocked full flow) --------------------------------

class TestSmoothDocumentMocked(unittest.TestCase):
    """smooth_document 全流程(LLM mock)"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.input_path = Path(self.tmpdir) / 'cleaned.md'
        self.input_path.write_text(SAMPLE_MD, encoding='utf-8')
        self.output_path = Path(self.tmpdir) / 'smoothed.md'

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_dry_run_no_llm_call(self):
        """dry-run 不调 LLM,只输出切分信息"""
        with patch('scripts._purify_smooth.call_vision') as mock_llm:
            rc = smooth_document(self.input_path, self.output_path, dry_run=True)
            self.assertEqual(rc, 0)
            mock_llm.assert_not_called()
        # 不应生成输出文件(dry-run 跳过)
        self.assertFalse(self.output_path.exists())

    def test_full_flow_writes_smoothed(self):
        """完整流程:mock LLM 返回原标题 + 微调正文"""
        def mock_llm_response(prompt, images, model='claude-sonnet-4-5'):
            # 简单 mock:返回输入内容的轻微变体(标题保留)
            # 实际从 prompt 提取 h2_content 不易,直接返回包装过的 SAMPLE_MD
            return '```markdown\n' + SAMPLE_MD + '\n```'

        with patch('scripts._purify_smooth.call_vision',
                   side_effect=mock_llm_response):
            rc = smooth_document(
                self.input_path, self.output_path,
                workers=1,
            )
            self.assertEqual(rc, 0)
        self.assertTrue(self.output_path.exists())
        content = self.output_path.read_text(encoding='utf-8')
        # 标题守恒
        self.assertIn('## 1. 产品裂变底层逻辑', content)
        self.assertIn('### 1.1 电钻案例', content)

    def test_max_chars_configurable(self):
        """max_chars 参数生效:大文档 + 小 max_chars → 更多 LLM chunks"""
        # 构造 6K 字符的大 H2(超 200 chars 上限)
        big_h2 = '## 1. Big Chapter\n\n' + 'lorem ipsum ' * 600
        big_md = f"# Title\n\n{big_h2}\n\n## 2. Small\n\nshort"
        big_input = Path(self.tmpdir) / 'big.md'
        big_input.write_text(big_md, encoding='utf-8')

        with patch('scripts._purify_smooth.call_vision') as mock_llm:
            mock_llm.return_value = big_md  # mock LLM 返回原输入
            rc = smooth_document(
                big_input, Path(self.tmpdir) / 'big_smoothed.md',
                workers=1, max_chars=500,
            )
            self.assertEqual(rc, 0)
            # mock 调用次数应大于 H2 数(2 个 H2 → 多个 chunk)
            self.assertGreater(mock_llm.call_count, 2,
                              f"期望 >2 次 LLM 调用,实际 {mock_llm.call_count}")

    def test_small_doc_one_chunk_per_h2(self):
        """小文档 + 大 max_chars → 每个 H2 = 1 chunk(无 H3 切分)"""
        with patch('scripts._purify_smooth.call_vision') as mock_llm:
            mock_llm.return_value = SAMPLE_MD
            rc = smooth_document(
                self.input_path, self.output_path,
                workers=1, max_chars=8000,
            )
            self.assertEqual(rc, 0)
            # SAMPLE_MD 3 个 H2,每个 ≤ 8K → 应是 3 次调用
            self.assertEqual(mock_llm.call_count, 3)

    def test_input_not_found(self):
        """输入不存在时返回错误码"""
        bad_path = Path(self.tmpdir) / 'nonexistent.md'
        rc = smooth_document(bad_path, self.output_path)
        self.assertEqual(rc, 1)


# Prompt 模板 -----------------------------------------------------

class TestPromptTemplate(unittest.TestCase):
    """prompt 模板含关键约束"""

    def test_contains_required_keywords(self):
        prompt = SMOOTH_PROMPT_TEMPLATE
        # 必须含 5 类硬约束
        for kw in ['新增', '标题', '章节数量', '虚构', '表格结构']:
            self.assertIn(kw, prompt, f"prompt 缺关键词:{kw}")
        # 必须含 7 类清理目标
        for kw in ['时间戳', '粗口', 'ASR', '中英俄', '不通顺', '重复']:
            self.assertIn(kw, prompt, f"prompt 缺清理关键词:{kw}")
        # 必须显式禁止
        self.assertIn('❌', prompt)


if __name__ == '__main__':
    unittest.main(verbosity=2)
