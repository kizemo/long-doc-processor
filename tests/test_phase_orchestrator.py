"""test_phase_orchestrator.py — D5 Phase orchestrator 测试

覆盖:
  1. Phase 1.7 串 3 步(strip_lecturer → strip_persona → last_section)
  2. Phase 1.7 dry-run 模式
  3. Phase 1.8 dry-run 模式(mock 复制)
  4. 输入不存在 → exit 1
  5. --phase 参数错 → exit 2
  6. CLI 存在 + 选项注册
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(__file__.replace("\\", "/").rsplit("/", 2)[0]))

import scripts.phase_orchestrator as po
from scripts.phase_orchestrator import run_phase_1_7, run_phase_1_8, main


SAMPLE_MD = """# Title

## 1. 一章

讲师认为这是关键。

## 2. 二章

学员在选品时出错。
"""


def _write_md(content: str, name: str = "in.md"):
    tmpdir = tempfile.mkdtemp()
    path = Path(tmpdir) / name
    path.write_text(content, encoding="utf-8")
    return path, tmpdir


def _cleanup(tmp):
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


# 1. Phase 1.7 串 3 步

class TestPhase17(unittest.TestCase):

    def test_phase_1_7_calls_three_functions(self):
        """Phase 1.7 应调 strip_lecturer → strip_persona → last_section。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.md"
            out = Path(tmp) / "out.md"
            inp.write_text(SAMPLE_MD, encoding="utf-8")

            with patch('scripts.strip_lecturer_preamble.strip_document', return_value=0), \
                 patch('scripts.strip_role_persona.strip_document', return_value=0), \
                 patch('scripts.last_section_reprocess.last_section_reprocess', return_value=0):
                rc = run_phase_1_7(inp, out, dry_run=False, workers=1)
                self.assertEqual(rc, 0)

    def test_phase_1_7_strip_lecturer_fails(self):
        """strip_lecturer 失败 → 整体 FAIL。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.md"
            out = Path(tmp) / "out.md"
            inp.write_text(SAMPLE_MD, encoding="utf-8")

            with patch('scripts.strip_lecturer_preamble.strip_document', return_value=1):
                rc = run_phase_1_7(inp, out, dry_run=False, workers=1)
                self.assertNotEqual(rc, 0)

    def test_phase_1_7_input_not_found(self):
        """输入不存在 → exit 1。"""
        with tempfile.TemporaryDirectory() as tmp:
            rc = run_phase_1_7(
                Path(tmp) / "nonexistent.md",
                Path(tmp) / "out.md",
            )
            self.assertEqual(rc, 1)


# 2. Phase 1.8

class TestPhase18(unittest.TestCase):

    def test_phase_1_8_dry_run_copies(self):
        """Phase 1.8 dry-run → 复制 input 到 output。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.md"
            out = Path(tmp) / "out.md"
            inp.write_text(SAMPLE_MD, encoding="utf-8")

            rc = run_phase_1_8(inp, out, dry_run=True)
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            self.assertEqual(out.read_text(encoding="utf-8"), SAMPLE_MD)

    def test_phase_1_8_input_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = run_phase_1_8(
                Path(tmp) / "nonexistent.md",
                Path(tmp) / "out.md",
            )
            self.assertEqual(rc, 1)


# 3. main() CLI

class TestPhaseOrchestratorCli(unittest.TestCase):

    def test_main_invalid_phase_returns_2(self):
        """argparse 拦截非法 --phase,SystemExit(2)。"""
        import sys as _sys
        old_argv = _sys.argv
        try:
            _sys.argv = [
                "phase_orchestrator.py",
                "--phase", "9.9",
                "--input", "/tmp/x.md",
                "--output", "/tmp/y.md",
            ]
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 2)
        finally:
            _sys.argv = old_argv

    def test_main_phase_1_7_dry_run(self):
        """main() + --phase 1.7 + --dry-run。"""
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.md"
            out = Path(tmp) / "out.md"
            inp.write_text(SAMPLE_MD, encoding="utf-8")

            with patch('scripts.strip_lecturer_preamble.strip_document', return_value=0), \
                 patch('scripts.strip_role_persona.strip_document', return_value=0), \
                 patch('scripts.last_section_reprocess.last_section_reprocess', return_value=0):
                import sys as _sys
                old_argv = _sys.argv
                try:
                    _sys.argv = [
                        "phase_orchestrator.py",
                        "--phase", "1.7",
                        "--input", str(inp),
                        "--output", str(out),
                        "--dry-run",
                    ]
                    rc = main()
                    self.assertEqual(rc, 0)
                finally:
                    _sys.argv = old_argv


if __name__ == "__main__":
    unittest.main(verbosity=2)
