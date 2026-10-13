"""test_verbose_status.py — C4 阶段 safe_llm_call verbose status 测试

覆盖:
  1. make_verbose_status_callback 工厂函数存在
  2. --verbose flag 在 5 个 LLM 脚本 CLI 中注册
  3. safe_llm_call 接 on_status 后,status 变化时触发回调
  4. 默认(无 --verbose)不传 on_status,行为不变(向后兼容)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(__file__.replace("\\", "/").rsplit("/", 2)[0]))

import scripts.utils as u
from scripts.utils import make_verbose_status_callback


# 1. 工厂函数 ------------------------------------------------------

class TestVerboseStatusCallback(unittest.TestCase):

    def test_factory_exists(self):
        """make_verbose_status_callback 在 utils.py 暴露。"""
        self.assertTrue(hasattr(u, "make_verbose_status_callback"))

    def test_factory_returns_callable(self):
        """工厂返回 callable。"""
        cb = make_verbose_status_callback("test")
        self.assertTrue(callable(cb))

    def test_callback_writes_to_stderr(self):
        """callback 写到 stderr(log 函数,带时间戳)。"""
        import io
        captured = io.StringIO()
        original_stderr = sys.stderr

        class _Tee:
            def __init__(self, cap):
                self._cap = cap
            def write(self, s):
                self._cap.write(s)
                return len(s)
            def flush(self):
                pass
            def reconfigure(self, **kwargs):
                pass

        try:
            sys.stderr = _Tee(captured)
            cb = make_verbose_status_callback("test-prefix")
            cb("ok (attempt 1)")
            output = captured.getvalue()
            self.assertIn("test-prefix", output)
            self.assertIn("ok (attempt 1)", output)
        finally:
            sys.stderr = original_stderr


# 2. CLI --verbose flag 注册 --------------------------------------

class TestVerboseCliRegistration(unittest.TestCase):
    """5 个 LLM 脚本 CLI 都有 --verbose flag。"""

    SCRIPTS = [
        "scripts/_purify_smooth.py",
        "scripts/purify_v4_4_hierarchical.py",
        "scripts/strip_lecturer_preamble.py",
        "scripts/strip_role_persona.py",
        "scripts/last_section_reprocess.py",
    ]

    def test_all_5_scripts_have_verbose_flag(self):
        """5 个 LLM 脚本源码均含 --verbose。"""
        for script in self.SCRIPTS:
            path = Path(script)
            self.assertTrue(path.exists(), f"{script} 不存在")
            src = path.read_text(encoding="utf-8")
            self.assertIn("--verbose", src, f"{script} 缺 --verbose flag")
            self.assertIn("make_verbose_status_callback", src,
                          f"{script} 缺 verbose status callback")

    def test_all_5_scripts_pass_on_status(self):
        """5 个脚本都把 on_status 传给 safe_llm_call。"""
        for script in self.SCRIPTS:
            src = Path(script).read_text(encoding="utf-8")
            self.assertIn("on_status=", src,
                          f"{script} 未把 on_status 传给 safe_llm_call")


# 3. safe_llm_call verbose 集成 ----------------------------------

class TestSafeLlmCallVerbose(unittest.TestCase):
    """safe_llm_call 接 on_status 后,各 status 触发回调。"""

    def test_on_status_invoked_on_ok(self):
        """status=ok 时回调被触发。"""
        with self._patch_env_and_sdk():
            statuses = []
            from scripts._llm_vision import safe_llm_call
            safe_llm_call("test", max_retries=1, on_status=statuses.append,
                         backoff=0.01, timeout=60)
            self.assertTrue(any("ok" in s for s in statuses),
                            f"ok status 应触发回调,实际 {statuses}")

    def test_on_status_invoked_on_no_api_key(self):
        """无 API key 时回调被触发(状态 no_api_key)。"""
        env = {k: v for k, v in __import__("os").environ.items()
               if k != "ANTHROPIC_API_KEY"}
        with __import__("contextlib").ExitStack() as stack:
            from unittest.mock import patch, MagicMock
            stack.enter_context(patch.dict(__import__("os").environ, env, clear=True))
            fake_sdk, _ = MagicMock(), MagicMock()
            stack.enter_context(patch.dict(sys.modules, {"anthropic": fake_sdk}))
            statuses = []
            from scripts._llm_vision import safe_llm_call
            safe_llm_call("test", max_retries=1, on_status=statuses.append)
            self.assertTrue(any("no_api_key" in s for s in statuses))

    def test_on_status_none_backward_compat(self):
        """on_status=None(默认)时不应崩溃(向后兼容)。"""
        with self._patch_env_and_sdk():
            from scripts._llm_vision import safe_llm_call
            # 不传 on_status → 默认 None
            text, status = safe_llm_call("test", max_retries=1, timeout=60)
            self.assertEqual(status, "ok")

    def _patch_env_and_sdk(self):
        """helper: 模拟有 API key + mock SDK。"""
        from contextlib import ExitStack
        from unittest.mock import patch, MagicMock
        stack = ExitStack()
        stack.enter_context(patch.dict(__import__("os").environ,
                                        {"ANTHROPIC_API_KEY": "sk-test"}))
        fake_sdk = MagicMock()
        fake_client = MagicMock()
        fake_msg = MagicMock()
        fake_msg.content = [MagicMock(text="result")]
        fake_client.messages.create.return_value = fake_msg
        fake_sdk.Anthropic.return_value = fake_client
        stack.enter_context(patch.dict(sys.modules, {"anthropic": fake_sdk}))
        return stack


if __name__ == "__main__":
    unittest.main(verbosity=2)
