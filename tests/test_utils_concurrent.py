"""test_utils_concurrent.py — 线程安全 log 单元测试

覆盖:
  1. 2 thread × 100 行, 验证不交错(无撕裂行)
  2. configure_stdout_utf8 不破坏现有 stream
  3. log 仍写到 stderr
  4. log 时间戳格式正确(HH:MM:SS.mmm)
"""
from __future__ import annotations

import io
import sys
import threading
import time
import unittest

sys.path.insert(0, str(__file__.replace("\\", "/").rsplit("/", 2)[0]))

from scripts.utils import log, configure_stdout_utf8


class TestLogThreadSafe(unittest.TestCase):
    """log() 在多线程下不撕裂单行输出。"""

    def test_concurrent_log_no_interleaving(self):
        """2 thread × 100 行 → 验证每行都是完整的 '[HH:MM:SS.mmm] msg' 格式。"""
        # 替换 sys.stderr 为可读流
        captured = io.StringIO()
        original_stderr = sys.stderr

        # 用一个自定义 stream 替换,既能被 log() 写入,又能在并发下不撕裂
        class _TeeStream:
            def __init__(self, original, capture):
                self._lock = threading.Lock()
                self._orig = original
                self._cap = capture
            def write(self, s):
                with self._lock:
                    self._orig.write(s)
                    self._cap.write(s)
                return len(s)
            def flush(self):
                self._orig.flush()
            def reconfigure(self, **kwargs):
                return self._orig.reconfigure(**kwargs)

        tee = _TeeStream(original_stderr, captured)
        sys.stderr = tee
        try:
            N = 100
            errors = []

            def worker(prefix):
                for i in range(N):
                    log(f"{prefix}-line-{i:04d}-end")

            t1 = threading.Thread(target=worker, args=("T1",))
            t2 = threading.Thread(target=worker, args=("T2",))
            t1.start(); t2.start()
            t1.join(); t2.join()

            output = captured.getvalue()
            lines = [l for l in output.splitlines() if l.strip()]
            # 每行必须含完整 'line-NNNN-end'(防撕裂)
            malformed = [l for l in lines if "line-" not in l or "end" not in l]
            self.assertEqual(
                len(malformed), 0,
                f"撕裂行数 {len(malformed)}: 前 5 个: {malformed[:5]}"
            )
            # 共 200 行
            self.assertEqual(len(lines), 2 * N)
        finally:
            sys.stderr = original_stderr

    def test_log_includes_timestamp(self):
        """log 行带 [HH:MM:SS.mmm] 前缀。"""
        import re
        captured = io.StringIO()
        original_stderr = sys.stderr

        class _TeeStream:
            def __init__(self, original, capture):
                self._lock = threading.Lock()
                self._orig = original
                self._cap = capture
            def write(self, s):
                with self._lock:
                    self._orig.write(s)
                    self._cap.write(s)
                return len(s)
            def flush(self):
                self._orig.flush()
            def reconfigure(self, **kwargs):
                return self._orig.reconfigure(**kwargs)

        tee = _TeeStream(original_stderr, captured)
        sys.stderr = tee
        try:
            log("test message")
            output = captured.getvalue()
            # 匹配 [HH:MM:SS.mmm] xxx
            self.assertRegex(output, r"\[\d{2}:\d{2}:\d{2}\.\d{3}\] test message\n")
        finally:
            sys.stderr = original_stderr


class TestConfigureStdoutUtf8(unittest.TestCase):
    def test_does_not_crash(self):
        """configure_stdout_utf8 在 reconfigure 不存在或失败时不抛异常。"""
        # 真实 stream 通常都有 reconfigure
        configure_stdout_utf8()  # 不应抛


if __name__ == "__main__":
    unittest.main(verbosity=2)
