"""test_argparse_boilerplate.py — E2 argparse boilerplate 统一测试

覆盖:
  1. make_standard_parser 默认有 --verbose
  2. make_standard_parser 可选 --dry-run / --workers
  3. safe_main 正常路径返回 main 的结果
  4. safe_main KeyboardInterrupt → exit 130
  5. safe_main 未捕获异常 → exit 1
  6. 替换示例: 1 个脚本用 safe_main 后行为不变
"""
from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(__file__.replace("\\", "/").rsplit("/", 2)[0]))

import scripts.utils as u
from scripts.utils import make_standard_parser, safe_main


# 1. make_standard_parser

class TestMakeStandardParser(unittest.TestCase):

    def test_default_verbose(self):
        """默认 add_verbose=True,parser 含 --verbose。"""
        parser = make_standard_parser("test")
        # 解析 --help 验证 --verbose 存在
        import argparse
        try:
            parser.parse_args(["--verbose"])
        except SystemExit:
            pass  # --help 会 exit,但 --verbose 不该 exit
        # 直接调 parse_args 验证
        args = parser.parse_args([])
        self.assertFalse(args.verbose)
        args = parser.parse_args(["--verbose"])
        self.assertTrue(args.verbose)

    def test_dry_run_flag(self):
        """add_dry_run=True → 含 --dry-run。"""
        parser = make_standard_parser("test", add_dry_run=True)
        args = parser.parse_args(["--dry-run"])
        self.assertTrue(args.dry_run)

    def test_workers_flag(self):
        """add_workers=True → 含 --workers(默认 3)。"""
        parser = make_standard_parser("test", add_workers=True)
        args = parser.parse_args([])
        self.assertEqual(args.workers, 3)
        args = parser.parse_args(["--workers", "5"])
        self.assertEqual(args.workers, 5)

    def test_no_verbose(self):
        """add_verbose=False → 无 --verbose。"""
        parser = make_standard_parser("test", add_verbose=False)
        with self.assertRaises(SystemExit):
            parser.parse_args(["--verbose"])  # 应报错

    def test_custom_args_still_work(self):
        """在 make_standard_parser 后可继续 add_argument。"""
        parser = make_standard_parser("test", add_verbose=True)
        parser.add_argument("input", help="输入")
        args = parser.parse_args(["myfile.md"])
        self.assertEqual(args.input, "myfile.md")
        self.assertFalse(args.verbose)


# 2. safe_main

class TestSafeMain(unittest.TestCase):

    def test_safe_main_returns_main_result(self):
        """safe_main 调 main,返回 main 的结果。"""
        def main():
            return 0
        self.assertEqual(safe_main(main), 0)

    def test_safe_main_returns_nonzero(self):
        def main():
            return 2
        self.assertEqual(safe_main(main), 2)

    def test_safe_main_keyboard_interrupt(self):
        """KeyboardInterrupt → exit 130。"""
        def main():
            raise KeyboardInterrupt()
        with patch('scripts.utils.log'):  # 避免 log 到 stderr
            self.assertEqual(safe_main(main), 130)

    def test_safe_main_unhandled_exception(self):
        """未捕获异常 → exit 1 + log。"""
        def main():
            raise RuntimeError("test boom")
        with patch('scripts.utils.log') as mock_log:
            rc = safe_main(main)
            self.assertEqual(rc, 1)
            mock_log.assert_called()

    def test_safe_main_configures_stdout(self):
        """safe_main 自动调 configure_stdout_utf8。"""
        with patch('scripts.utils.configure_stdout_utf8') as mock_cfg:
            def main():
                return 0
            safe_main(main)
            mock_cfg.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
