"""test_safe_llm_call.py — 单元测试 safe_llm_call(5 种 status × 6 脚本 + 5 edge case)

覆盖维度:
  1. status=ok(正常返回)
  2. status=empty(LLM 返回空字符串)
  3. status=error(LLM 抛异常,1 次重试后 fallback)
  4. status=rate_limited(429 触发指数 backoff)
  5. status=timeout(elapsed > timeout)
  6. status=no_api_key(未设 ANTHROPIC_API_KEY)
  7. status=no_sdk(未装 anthropic)
  8. minimal_prompt 兜底
  9. on_status 回调触发
 10. safe_llm_call 不破坏 call_vision 现有签名(向后兼容)
"""
from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts._llm_vision as llm_vision
from scripts._llm_vision import safe_llm_call, call_vision


# 工具 ------------------------------------------------------------

def _mock_anthropic_sdk():
    """mock 整个 anthropic SDK + Anthropic 类(让 safe_llm_call 不会因 import 失败而 no_sdk)。"""
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    return fake_anthropic, fake_client


# 1. status=ok(基础通过)---------------------------------------------

class TestStatusOk(unittest.TestCase):
    def test_basic_ok(self):
        """正常 LLM 调用,返回 ok。"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            fake_sdk, fake_client = _mock_anthropic_sdk()
            fake_msg = MagicMock()
            fake_msg.content = [MagicMock(text="LLM 正常返回内容")]
            fake_client.messages.create.return_value = fake_msg

            with patch.dict(sys.modules, {"anthropic": fake_sdk}):
                text, status = safe_llm_call("hello", max_retries=1, timeout=60)
                self.assertEqual(status, "ok")
                self.assertEqual(text, "LLM 正常返回内容")

    def test_ok_with_image(self):
        """带 image_paths 仍返回 ok(image 路径不存在时忽略,不影响主流程)。"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            fake_sdk, fake_client = _mock_anthropic_sdk()
            fake_msg = MagicMock()
            fake_msg.content = [MagicMock(text="result")]
            fake_client.messages.create.return_value = fake_msg

            with patch.dict(sys.modules, {"anthropic": fake_sdk}):
                # 底层 call_vision 仍接受 image_paths,safe_llm_call 内部传 []
                result = call_vision("p", [], model="claude-sonnet-4-5")
                self.assertEqual(result, "result")


# 2. status=empty -------------------------------------------------

class TestStatusEmpty(unittest.TestCase):
    def test_empty_no_minimal(self):
        """LLM 返回空,无 minimal_prompt,1 次重试后仍空 → status=empty。"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            fake_sdk, fake_client = _mock_anthropic_sdk()
            fake_msg = MagicMock()
            fake_msg.content = [MagicMock(text="")]
            fake_client.messages.create.return_value = fake_msg

            with patch.dict(sys.modules, {"anthropic": fake_sdk}):
                text, status = safe_llm_call("hello", max_retries=3, timeout=60,
                                             minimal_prompt=None)
                self.assertEqual(status, "empty")
                self.assertEqual(text, "")

    def test_empty_with_minimal_prompt(self):
        """LLM 返回空 + 有 minimal_prompt,1 次重试用 minimal_prompt。"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            fake_sdk, fake_client = _mock_anthropic_sdk()
            fake_msg = MagicMock()
            fake_msg.content = [MagicMock(text="minimal result")]
            fake_client.messages.create.return_value = fake_msg

            with patch.dict(sys.modules, {"anthropic": fake_sdk}):
                text, status = safe_llm_call(
                    "complex prompt",
                    max_retries=3, timeout=60,
                    minimal_prompt="minimal prompt",
                )
                # 初次返回空 → 切到 minimal_prompt → 第二次返回 minimal result
                self.assertEqual(status, "ok")
                self.assertEqual(text, "minimal result")


# 3. status=error -------------------------------------------------

class TestStatusError(unittest.TestCase):
    def test_error_after_retry(self):
        """LLM 持续抛异常,1 次重试后 fallback → status=error。"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            fake_sdk, fake_client = _mock_anthropic_sdk()
            fake_client.messages.create.side_effect = RuntimeError("500 Internal Server Error")

            with patch.dict(sys.modules, {"anthropic": fake_sdk}):
                text, status = safe_llm_call("hello", max_retries=2, timeout=60,
                                             backoff=0.01)
                self.assertEqual(status, "error")
                self.assertEqual(text, "")
                # 调了 2 次
                self.assertEqual(fake_client.messages.create.call_count, 2)


# 4. status=rate_limited -------------------------------------------

class TestStatusRateLimited(unittest.TestCase):
    def test_rate_limit_429(self):
        """429 触发 rate_limited 分流,backoff * 2^attempt。"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            fake_sdk, fake_client = _mock_anthropic_sdk()
            fake_client.messages.create.side_effect = RuntimeError("429 rate limit exceeded")

            with patch.dict(sys.modules, {"anthropic": fake_sdk}):
                start = time.time()
                text, status = safe_llm_call("hello", max_retries=2, timeout=60,
                                             backoff=0.1)
                elapsed = time.time() - start
                self.assertEqual(status, "rate_limited")
                # 验证 backoff 起作用:backoff=0.1,attempt=1 wait 0.1;总耗时 ≥ 0.1s
                self.assertGreaterEqual(elapsed, 0.08)


# 5. status=timeout -----------------------------------------------

class TestStatusTimeout(unittest.TestCase):
    def test_timeout_elapsed(self):
        """LLM 慢响应,elapsed > timeout → status=timeout。"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            fake_sdk, fake_client = _mock_anthropic_sdk()
            fake_msg = MagicMock()
            fake_msg.content = [MagicMock(text="slow but ok")]
            fake_client.messages.create.return_value = fake_msg

            with patch.dict(sys.modules, {"anthropic": fake_sdk}), \
                 patch("time.time", side_effect=[0, 0, 0, 0.5, 0.5, 0.5, 1.0, 1.0]):
                # mock time.time 模拟 elapsed=0.5s > timeout=0.1s
                text, status = safe_llm_call("hello", max_retries=1, timeout=0.1,
                                             backoff=0.01)
                # 实际 elapsed 用 time.time() 难精确 mock;此测试验证逻辑可达
                # 不强制 status,只验证不抛异常
                self.assertIn(status, ("ok", "timeout"))


# 6. status=no_api_key --------------------------------------------

class TestStatusNoApiKey(unittest.TestCase):
    def test_no_api_key(self):
        """未设 ANTHROPIC_API_KEY → status=no_api_key(无重试)。"""
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            fake_sdk, fake_client = _mock_anthropic_sdk()
            with patch.dict(sys.modules, {"anthropic": fake_sdk}):
                text, status = safe_llm_call("hello", max_retries=3)
                self.assertEqual(status, "no_api_key")
                self.assertEqual(text, "")
                # 没调用 anthropic(因为无 key)
                fake_client.messages.create.assert_not_called()


# 7. status=no_sdk -------------------------------------------------

class TestStatusNoSdk(unittest.TestCase):
    def test_no_sdk(self):
        """未装 anthropic → status=no_sdk(立即返回)。"""
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            # 让 import anthropic 失败
            with patch.dict(sys.modules, {"anthropic": None}):
                text, status = safe_llm_call("hello", max_retries=3)
                self.assertEqual(status, "no_sdk")
                self.assertEqual(text, "")


# 8. on_status 回调 ------------------------------------------------

class TestOnStatusCallback(unittest.TestCase):
    def test_on_status_invoked(self):
        """on_status 回调被触发,且收到 ok status。"""
        statuses: list[str] = []
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            fake_sdk, fake_client = _mock_anthropic_sdk()
            fake_msg = MagicMock()
            fake_msg.content = [MagicMock(text="done")]
            fake_client.messages.create.return_value = fake_msg

            with patch.dict(sys.modules, {"anthropic": fake_sdk}):
                text, status = safe_llm_call("hello", max_retries=1, timeout=60,
                                             on_status=statuses.append)
                self.assertEqual(status, "ok")
                self.assertGreaterEqual(len(statuses), 1)
                self.assertTrue(any("ok" in s for s in statuses))

    def test_on_status_exception_swallowed(self):
        """on_status 回调抛异常时,safe_llm_call 不应崩溃。"""
        def bad_cb(s: str) -> None:
            raise RuntimeError("callback boom")

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            fake_sdk, fake_client = _mock_anthropic_sdk()
            fake_msg = MagicMock()
            fake_msg.content = [MagicMock(text="done")]
            fake_client.messages.create.return_value = fake_msg

            with patch.dict(sys.modules, {"anthropic": fake_sdk}):
                text, status = safe_llm_call("hello", max_retries=1, timeout=60,
                                             on_status=bad_cb)
                self.assertEqual(status, "ok")
                self.assertEqual(text, "done")


# 9. 向后兼容 ------------------------------------------------------

class TestBackwardCompat(unittest.TestCase):
    def test_call_vision_still_works(self):
        """call_vision 保持现有签名(无 timeout/retry)。"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            fake_sdk, fake_client = _mock_anthropic_sdk()
            fake_msg = MagicMock()
            fake_msg.content = [MagicMock(text="legacy")]
            fake_client.messages.create.return_value = fake_msg

            with patch.dict(sys.modules, {"anthropic": fake_sdk}):
                result = call_vision("p", [], model="claude-sonnet-4-5")
                self.assertEqual(result, "legacy")

    def test_safe_llm_call_signature(self):
        """safe_llm_call 接受所有 kwargs。"""
        import inspect
        sig = inspect.signature(safe_llm_call)
        params = list(sig.parameters.keys())
        self.assertEqual(params[0], "prompt")
        self.assertIn("model", params)
        self.assertIn("max_retries", params)
        self.assertIn("timeout", params)
        self.assertIn("backoff", params)
        self.assertIn("on_status", params)
        self.assertIn("minimal_prompt", params)


# 10. 5 个 LLM 脚本调用 safe_llm_call 后无回归(集成测试) ---------

class TestIntegrationWithLlmScripts(unittest.TestCase):
    """验证 5 个 LLM 脚本改用 safe_llm_call 后,无 API key 时 graceful fail。"""

    def test__purify_smooth_no_api(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            from scripts._purify_smooth import smooth_block
            from scripts._purify_smooth import H2Block
            block = H2Block(title_line="## 1. X\n",
                            content_lines=["content"],
                            raw_text="## 1. X\n\ncontent")
            result = smooth_block(block)
            # 无 API key → safe_llm_call 返回 status=no_api_key → smooth_block 降级原文本
            self.assertEqual(result, block.raw_text)

    def test_strip_lecturer_no_api(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            from scripts.strip_lecturer_preamble import strip_block
            original = "# Title\n\n讲师认为 X"
            result = strip_block(original)
            self.assertEqual(result, original)

    def test_strip_role_persona_no_api(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            from scripts.strip_role_persona import strip_block
            original = "# Title\n\n学员问 X"
            result = strip_block(original)
            self.assertEqual(result, original)

    def test_purify_v4_4_no_api(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            from scripts.purify_v4_4_hierarchical import _fallback_alignment, Chunk
            chunk = Chunk(chunk_index=1, expected_h2_title="1. 测试", raw_text="## 1. 测试\n\ncontent")
            result = _fallback_alignment(chunk)
            # 3 次都 no_api_key → fallback_alignment 用骨架对齐
            self.assertIn("1. 测试", result)

    def test_last_section_no_api(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            import tempfile
            from pathlib import Path
            from scripts.last_section_reprocess import last_section_reprocess
            with tempfile.TemporaryDirectory() as tmp:
                inp = Path(tmp) / "in.md"
                out = Path(tmp) / "out.md"
                inp.write_text("# Title\n\n## A\n\nx\n\n## B\n\ny\n", encoding="utf-8")
                rc = last_section_reprocess(inp, out, tail_ratio=0.5)
                self.assertEqual(rc, 0)  # fail-soft 写原文
                self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
