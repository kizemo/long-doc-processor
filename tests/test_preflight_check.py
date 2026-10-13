"""test_preflight_check.py — D2 preflight_check 必做首问检查测试

覆盖:
  1. 完整 config → PASS (exit 0)
  2. 缺字段 → FAIL (exit 2)
  3. 字段值为空 → FAIL
  4. step_0_7 非法值 → FAIL
  5. step_0_5 非法值 → FAIL
  6. step_0_duration_min 非数字 → FAIL
  7. config 文件不存在 → exit 1
  8. CLI 无 --config / --auto → exit 1
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(__file__.replace("\\", "/").rsplit("/", 2)[0]))

import scripts.preflight_check as pc
from scripts.preflight_check import check_config, REQUIRED_FIELDS, main


FULL_CONFIG = {
    "step_0_asr_model": "turbo",
    "step_0_duration_min": 60,
    "step_0_5_output_dir": "default",
    "step_0_6_output_stem": "讲义标题",
    "step_0_7_phase_1_8": "no",
}


# 1. 完整 config 通过检查

class TestPreflightCheckFunction(unittest.TestCase):

    def test_full_config_pass(self):
        ok, missing = check_config(FULL_CONFIG)
        self.assertTrue(ok)
        self.assertEqual(missing, [])

    def test_missing_field(self):
        config = {k: v for k, v in FULL_CONFIG.items() if k != "step_0_6_output_stem"}
        ok, missing = check_config(config)
        self.assertFalse(ok)
        self.assertTrue(any("step_0_6_output_stem" in m for m in missing))

    def test_empty_string_value(self):
        config = dict(FULL_CONFIG)
        config["step_0_6_output_stem"] = ""
        ok, missing = check_config(config)
        self.assertFalse(ok)
        self.assertTrue(any("step_0_6_output_stem" in m for m in missing))

    def test_tbd_value(self):
        config = dict(FULL_CONFIG)
        config["step_0_6_output_stem"] = "TBD"
        ok, missing = check_config(config)
        self.assertFalse(ok)

    def test_invalid_step_0_7(self):
        config = dict(FULL_CONFIG)
        config["step_0_7_phase_1_8"] = "maybe"
        ok, missing = check_config(config)
        self.assertFalse(ok)
        self.assertTrue(any("step_0_7_phase_1_8" in m for m in missing))

    def test_invalid_step_0_5(self):
        config = dict(FULL_CONFIG)
        config["step_0_5_output_dir"] = "random"
        ok, missing = check_config(config)
        self.assertFalse(ok)
        self.assertTrue(any("step_0_5_output_dir" in m for m in missing))

    def test_duration_not_numeric(self):
        config = dict(FULL_CONFIG)
        config["step_0_duration_min"] = "60min"  # 字符串
        ok, missing = check_config(config)
        self.assertFalse(ok)
        self.assertTrue(any("step_0_duration_min" in m for m in missing))

    def test_required_fields_count(self):
        """REQUIRED_FIELDS 包含 5 个必填项(Step 0/0.5/0.6/0.7 共 4 步,Step 0 拆 2 字段)。"""
        self.assertEqual(len(REQUIRED_FIELDS), 5)


# 2. CLI 集成(用 subprocess 跑 main)

class TestPreflightCli(unittest.TestCase):

    def _run_cli(self, *args, stdin=None):
        """helper:运行 preflight_check.py CLI,返回 (returncode, stdout, stderr)。"""
        proc = subprocess.run(
            [sys.executable, "scripts/preflight_check.py", *args],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True,
            text=True,
            input=stdin,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def test_cli_full_config_pass(self):
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        ) as f:
            json.dump(FULL_CONFIG, f)
            path = f.name
        try:
            rc, _, stderr = self._run_cli("--config", path)
            self.assertEqual(rc, 0, f"应 exit 0,实际 {rc}:{stderr}")
        finally:
            Path(path).unlink()

    def test_cli_missing_config(self):
        """--config 指向不存在的文件 → exit 1。"""
        rc, _, stderr = self._run_cli("--config", "/nonexistent/config.json")
        self.assertEqual(rc, 1)

    def test_cli_no_args(self):
        """无参数 → exit 1。"""
        rc, _, stderr = self._run_cli()
        self.assertEqual(rc, 1)

    def test_cli_auto_stdin(self):
        """--auto + stdin JSON → exit 0。"""
        rc, _, stderr = self._run_cli("--auto", stdin=json.dumps(FULL_CONFIG))
        self.assertEqual(rc, 0, f"应 exit 0,实际 {rc}:{stderr}")

    def test_cli_auto_stdin_missing(self):
        """--auto + 缺字段 stdin → exit 2。"""
        bad = {k: v for k, v in FULL_CONFIG.items() if k != "step_0_5_output_dir"}
        rc, _, stderr = self._run_cli("--auto", stdin=json.dumps(bad))
        self.assertEqual(rc, 2, f"应 exit 2,实际 {rc}:{stderr}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
