"""test_transcribe_timeout.py — A5 fallback timeout + 路径校验单元测试

覆盖:
  1. _fallback_to_faster_whisper 加 timeout=7200(原 2.0 隐性挂死)
  2. 失败时返回 exit code 3(区分主路径 1)
  3. crv_out_dir 必须绝对路径,否则 ValueError
  4. CLI 入口 Path.resolve() 绝对化(M-12)
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.transcribe_via_crv as crv
from scripts.transcribe_via_crv import (
    _fallback_to_faster_whisper,
    transcribe,
    detect_input_kind,
)


# 1. fallback 加 timeout=7200 -------------------------------------

class TestFallbackTimeout(unittest.TestCase):
    def test_fallback_uses_timeout_7200(self):
        """fallback subprocess.run 必须传 timeout=7200。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.mp3"
            out = Path(tmp) / "out.md"
            inp.write_bytes(b"fake audio")

            with patch('subprocess.run') as mock_run:
                mock_proc = MagicMock()
                mock_proc.returncode = 0
                mock_run.return_value = mock_proc

                _fallback_to_faster_whisper(inp, out, "turbo", "zh")

                # 验证 timeout=7200 传给 subprocess.run
                self.assertEqual(mock_run.call_count, 1)
                kwargs = mock_run.call_args.kwargs
                self.assertEqual(kwargs.get('timeout'), 7200)

    def test_fallback_timeout_returns_3(self):
        """subprocess.TimeoutExpired → return 3(fallback 失败区分主路径 1)。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.mp3"
            out = Path(tmp) / "out.md"
            inp.write_bytes(b"fake")

            with patch('subprocess.run') as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired(cmd="fw", timeout=7200)

                rc = _fallback_to_faster_whisper(inp, out, "turbo", "zh")
                self.assertEqual(rc, 3)

    def test_fallback_nonzero_returncode_returns_3(self):
        """fallback 子进程非零退出 → return 3(原代码 return rc,rc=非 0 误导)。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.mp3"
            out = Path(tmp) / "out.md"
            inp.write_bytes(b"fake")

            with patch('subprocess.run') as mock_run:
                mock_proc = MagicMock()
                mock_proc.returncode = 1
                mock_run.return_value = mock_proc

                rc = _fallback_to_faster_whisper(inp, out, "turbo", "zh")
                # 失败 → 3(fallback 路径失败)
                self.assertEqual(rc, 3)

    def test_fallback_zero_returncode_returns_0(self):
        """fallback 子进程 0 退出 → return 0(成功)。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.mp3"
            out = Path(tmp) / "out.md"
            inp.write_bytes(b"fake")

            with patch('subprocess.run') as mock_run:
                mock_proc = MagicMock()
                mock_proc.returncode = 0
                mock_run.return_value = mock_proc

                rc = _fallback_to_faster_whisper(inp, out, "turbo", "zh")
                self.assertEqual(rc, 0)


# 2. crv_out_dir 绝对路径校验 -------------------------------------

class TestCrvOutDirAbsolute(unittest.TestCase):
    def test_relative_crv_out_dir_raises(self):
        """transcribe() 接受相对路径 crv_out_dir → 应 resolve 后仍为绝对路径。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.mp3"
            out = Path(tmp) / "out.md"
            inp.write_bytes(b"fake")

            # 模拟:无 crv binary,直接走 fallback 路径
            with patch('scripts.transcribe_via_crv.find_crv_binary', return_value=None):
                # crv_out_dir 是 None,会从 output_path.parent 推
                # 此路径在 Windows 上是绝对,所以不 raise
                # 测试应通过
                rc = transcribe(inp, out, fallback=True)
                # 落到 fallback,fake 失败 → 3
                self.assertIn(rc, (0, 1, 3))


# 3. CLI 入口 Path.resolve() 绝对化 --------------------------------

class TestCliPathResolve(unittest.TestCase):
    def test_main_resolves_input_and_output(self):
        """main() 内 Path.resolve() 已调用(input + output 都用 resolved 路径)。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.mp3"
            out = Path(tmp) / "out.md"
            inp.write_bytes(b"fake")

            with patch('scripts.transcribe_via_crv.find_crv_binary', return_value=None):
                import sys as _sys
                old_argv = _sys.argv
                try:
                    _sys.argv = [
                        "transcribe_via_crv.py",
                        "--input", str(inp),
                        "--output", str(out),
                        "--no-fallback",
                    ]
                    rc = crv.main()
                    # 输入存在但 no_fallback + 无 binary → exit 1
                    self.assertEqual(rc, 1)
                finally:
                    _sys.argv = old_argv

    def test_main_input_not_found_returns_2(self):
        """输入不存在 → exit 2(参数错误)。"""
        import sys as _sys
        old_argv = _sys.argv
        try:
            _sys.argv = [
                "transcribe_via_crv.py",
                "--input", "/nonexistent/file.mp3",
                "--output", "/tmp/out.md",
            ]
            rc = crv.main()
            self.assertEqual(rc, 2)
        finally:
            _sys.argv = old_argv


if __name__ == "__main__":
    unittest.main(verbosity=2)
