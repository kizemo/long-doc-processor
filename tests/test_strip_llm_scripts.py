"""test_strip_llm_scripts.py — 单元测试 strip_lecturer_preamble.py + strip_role_persona.py

两者结构相似,LLM 调用 mock 覆盖。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.strip_lecturer_preamble as slp
import scripts.strip_role_persona as srp
from scripts.strip_lecturer_preamble import strip_block as lecturer_strip_block
from scripts.strip_role_persona import strip_block as persona_strip_block


# LLM mock 通用 ---------------------------------------------------------

def _mock_llm_with_input(prefix: str, suffix: str):
    """生成 mock LLM,返回"<prefix>{input}<suffix>"形式的响应。

    用于 strip 类测试:验证 prompt 含输入内容,且产物不含污染词。
    """
    def factory(prompt, images, model):
        # 提取 prompt 中的输入章节(简单 split by '## 输入章节')
        if '## 输入章节' in prompt:
            chunk = prompt.split('## 输入章节')[-1]
            chunk = chunk.split('---')[0]
            return f"{prefix}{chunk.strip()}{suffix}"
        return prefix + suffix
    return factory


# strip_lecturer_preamble 测试 -----------------------------------------

class TestStripLecturerPreamble(unittest.TestCase):

    def test_strip_block_returns_cleaned(self):
        with patch('scripts.strip_lecturer_preamble.safe_llm_call') as mock:
            mock.return_value = ("```markdown\n# Title\n\ncleaned content\n```", "ok")
            result = lecturer_strip_block("# Title\n\n讲师认为 X")
            self.assertIn('cleaned content', result)
            self.assertNotIn('```markdown', result)

    def test_strip_block_llm_failure_keeps_original(self):
        with patch('scripts.strip_lecturer_preamble.safe_llm_call') as mock:
            mock.return_value = ("", "error")
            original = "# Title\n\n讲师认为 X"
            result = lecturer_strip_block(original)
            self.assertEqual(result, original)

    def test_strip_block_empty_input(self):
        result = lecturer_strip_block("")
        self.assertEqual(result, "")

    def test_prompt_contains_constraints(self):
        """prompt 含 5 类硬约束关键词"""
        from scripts.strip_lecturer_preamble import LECTURER_PREAMBLE_PROMPT
        for kw in ['讲师认为', '学员问', '引号', '删除', '禁止']:
            self.assertIn(kw, LECTURER_PREAMBLE_PROMPT)


# strip_role_persona 测试 ----------------------------------------------

class TestStripRolePersona(unittest.TestCase):

    def test_strip_block_returns_cleaned(self):
        with patch('scripts.strip_role_persona.safe_llm_call') as mock:
            mock.return_value = ("```markdown\n# Title\n\nrefactored content\n```", "ok")
            result = persona_strip_block("# Title\n\n学员问 X")
            self.assertIn('refactored content', result)

    def test_strip_block_llm_failure_keeps_original(self):
        with patch('scripts.strip_role_persona.safe_llm_call') as mock:
            mock.return_value = ("", "error")
            original = "# Title\n\n学员问 X"
            result = persona_strip_block(original)
            self.assertEqual(result, original)

    def test_strip_block_empty_input(self):
        result = persona_strip_block("")
        self.assertEqual(result, "")

    def test_prompt_contains_constraints(self):
        """prompt 含 5 类硬约束关键词"""
        from scripts.strip_role_persona import ROLE_PERSONA_PROMPT
        for kw in ['学员问', '讲师认为', '通用角色', '引号', '禁止']:
            self.assertIn(kw, ROLE_PERSONA_PROMPT)


if __name__ == '__main__':
    unittest.main(verbosity=2)
