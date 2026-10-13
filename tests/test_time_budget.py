"""test_time_budget.py — D7 阶段时间预算埋点测试

覆盖:
  1. time_budget context manager 存在
  2. 进入退出时自动 log 耗时
  3. budget dict 累积所有 phase 耗时
  4. format_budget_summary 输出多行总览
  5. 异常时仍能记录耗时(finally 块)
"""
from __future__ import annotations

import io
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(__file__.replace("\\", "/").rsplit("/", 2)[0]))

import scripts.utils as u
from scripts.utils import time_budget, format_budget_summary


class TestTimeBudget(unittest.TestCase):

    def test_time_budget_exists(self):
        """time_budget 在 utils 暴露。"""
        self.assertTrue(hasattr(u, "time_budget"))

    def test_time_budget_records_elapsed(self):
        """进入 + 退出后,budget dict 含 phase 耗时。"""
        budget = {}
        with time_budget("test_phase", budget):
            time.sleep(0.05)  # 50ms
        self.assertIn("test_phase", budget)
        self.assertGreaterEqual(budget["test_phase"], 0.05)

    def test_time_budget_multiple_phases(self):
        """多次调用累积多个 phase 耗时。"""
        budget = {}
        with time_budget("phase_a", budget):
            time.sleep(0.02)
        with time_budget("phase_b", budget):
            time.sleep(0.02)
        self.assertEqual(len(budget), 2)
        self.assertIn("phase_a", budget)
        self.assertIn("phase_b", budget)

    def test_time_budget_records_on_exception(self):
        """异常时仍记录耗时(finally 块)。"""
        budget = {}
        with self.assertRaises(RuntimeError):
            with time_budget("error_phase", budget):
                time.sleep(0.01)
                raise RuntimeError("test")
        # 仍记录了耗时
        self.assertIn("error_phase", budget)
        self.assertGreaterEqual(budget["error_phase"], 0.01)

    def test_time_budget_log_to_stderr(self):
        """退出时 log 耗时到 stderr(线程安全)。"""
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
            with time_budget("logged_phase"):
                time.sleep(0.01)
            output = captured.getvalue()
            self.assertIn("[time] logged_phase:", output)
            self.assertIn("s", output)
        finally:
            sys.stderr = original_stderr


class TestFormatBudgetSummary(unittest.TestCase):

    def test_empty_budget(self):
        """空 budget 返回提示字符串。"""
        result = format_budget_summary({})
        self.assertIn("无 phase", result)

    def test_single_phase(self):
        """单 phase 输出总耗时 + 该 phase。"""
        result = format_budget_summary({"phase_a": 5.0})
        self.assertIn("总耗时 5.0s", result)
        self.assertIn("phase_a", result)

    def test_multiple_phases_sorted(self):
        """多 phase 按耗时降序排列。"""
        result = format_budget_summary({
            "phase_a": 1.0,
            "phase_b": 5.0,
            "phase_c": 3.0,
        })
        # phase_b 应在 phase_c 前(降序)
        b_idx = result.index("phase_b")
        c_idx = result.index("phase_c")
        a_idx = result.index("phase_a")
        self.assertLess(b_idx, c_idx)
        self.assertLess(c_idx, a_idx)

    def test_percentage_displayed(self):
        """百分比显示。"""
        result = format_budget_summary({"phase_a": 5.0, "phase_b": 5.0})
        # 各 50%
        self.assertIn("50.0%", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
