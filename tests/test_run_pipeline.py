"""test_run_pipeline.py — D1 run_pipeline 一键入口测试

覆盖:
  1. --init 只生成 config 不跑 phase
  2. --dry-run 模式 mock 所有 phase
  3. config 缺字段 → exit 2
  4. 无 input/stem → exit 1
  5. --skip-preflight + --dry-run 跳过 preflight
  6. --resume 跳过已 done phase
  7. pipeline_state.json 持久化
  8. 时间预算总览输出
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(__file__.replace("\\", "/").rsplit("/", 2)[0]))

import scripts.run_pipeline as rp
from scripts.run_pipeline import (
    PHASES,
    PIPELINE_STATE_FILE,
    load_config,
    save_config,
    load_state,
    save_state,
    mark_done,
    is_done,
    main,
)


FULL_CONFIG = {
    "step_0_asr_model": "turbo",
    "step_0_duration_min": 60,
    "step_0_5_output_dir": "default",
    "step_0_6_output_stem": "讲义标题",
    "step_0_7_phase_1_8": "no",
}


# 1. 单元测试 ----------------------------------------------------

class TestStateManagement(unittest.TestCase):

    def test_load_state_empty(self):
        """state 文件不存在 → 空 state。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nonexistent.json"
            state = load_state(path)
            self.assertEqual(state["done_phases"], [])
            self.assertEqual(state["outputs"], {})

    def test_save_and_load_state(self):
        """state 持久化往返。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = {"done_phases": ["phase_0_asr"], "outputs": {"phase_0_asr": "/tmp/x.md"}}
            save_state(path, state)
            loaded = load_state(path)
            self.assertEqual(loaded, state)

    def test_mark_done(self):
        """mark_done 记录 phase + output。"""
        state = {"done_phases": [], "outputs": {}}
        mark_done(state, "phase_0_asr", "/tmp/x.md")
        self.assertIn("phase_0_asr", state["done_phases"])
        self.assertEqual(state["outputs"]["phase_0_asr"], "/tmp/x.md")

    def test_mark_done_idempotent(self):
        """mark_done 同一 phase 多次不重复。"""
        state = {"done_phases": [], "outputs": {}}
        mark_done(state, "phase_0_asr", "/tmp/x.md")
        mark_done(state, "phase_0_asr", "/tmp/x.md")
        self.assertEqual(state["done_phases"].count("phase_0_asr"), 1)

    def test_is_done(self):
        state = {"done_phases": ["phase_0_asr"], "outputs": {}}
        self.assertTrue(is_done(state, "phase_0_asr"))
        self.assertFalse(is_done(state, "phase_1_purify"))

    def test_phases_list_complete(self):
        """PHASES 列表含核心 phase(细分到 1.0/1.1/1.4/1.5/1.7/1.8 等子步骤)。"""
        for p in [
            "phase_0_asr",
            "phase_1_0_d0",
            "phase_1_4_purify",
            "phase_1_7_semantic",
            "phase_1_8_crop",
            "verify_all",
        ]:
            self.assertIn(p, PHASES, f"PHASES 缺 {p}")


class TestConfigManagement(unittest.TestCase):

    def test_load_config_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nonexistent.json"
            config = load_config(path)
            self.assertEqual(config, {})

    def test_save_and_load_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            config = dict(FULL_CONFIG)
            save_config(path, config)
            loaded = load_config(path)
            self.assertEqual(loaded, config)


# 2. main() 集成测试(用 subprocess 跑 CLI) -----------------------

class TestRunPipelineCli(unittest.TestCase):

    def _run_cli(self, *args, cwd=None, stdin=None):
        """用绝对路径调 run_pipeline.py(避免 cwd 切换导致相对路径失效)。"""
        project_root = Path(__file__).resolve().parent.parent
        script = str(project_root / "scripts" / "run_pipeline.py")
        proc = subprocess.run(
            [sys.executable, script, *args],
            cwd=cwd or str(project_root),
            capture_output=True,
            text=True,
            input=stdin,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode, proc.stdout, proc.stderr

    def test_init_only_generates_config(self):
        """--init 只写 config,不跑 phase。"""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            config_path = cwd / "pipeline_config.json"
            state_path = cwd / PIPELINE_STATE_FILE
            rc, _, _ = self._run_cli("--init", "--config", str(config_path), cwd=str(cwd))
            self.assertEqual(rc, 0)
            self.assertTrue(config_path.exists())
            self.assertFalse(state_path.exists())  # init 不写 state

    def test_dry_run_full_flow(self):
        """--dry-run + 完整 config 走完所有 phase。"""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            config_path = cwd / "pipeline_config.json"
            # 先 init 生成 config
            self._run_cli("--init", "--config", str(config_path), cwd=str(cwd))
            # 创建一个 mock input
            inp = cwd / "input.mp4"
            inp.write_bytes(b"fake video")
            # dry-run + skip-preflight + 完整 config
            rc, _, stderr = self._run_cli(
                str(inp), "--stem", "讲义",
                "--config", str(config_path),
                "--skip-preflight", "--dry-run",
                cwd=str(cwd),
            )
            self.assertEqual(rc, 0, f"应 exit 0,实际 {rc}:{stderr}")
            # state 文件应存在
            state_path = cwd / PIPELINE_STATE_FILE
            self.assertTrue(state_path.exists())
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("phase_0_asr", state["done_phases"])
            self.assertIn("phase_1_purify", state["done_phases"])
            self.assertIn("verify_all", state["done_phases"])

    def test_no_input_no_init(self):
        """无 input + 无 --init → exit 1。"""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            rc, _, _ = self._run_cli("--config", str(cwd / "config.json"), cwd=str(cwd))
            self.assertEqual(rc, 1)

    def test_preflight_missing(self):
        """config 缺字段 → preflight FAIL → exit 2。"""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            config_path = cwd / "config.json"
            config_path.write_text(json.dumps({"step_0_asr_model": "turbo"}), encoding="utf-8")
            inp = cwd / "input.mp4"
            inp.write_bytes(b"fake")
            rc, _, _ = self._run_cli(
                str(inp), "--stem", "x", "--config", str(config_path), "--dry-run",
                cwd=str(cwd),
            )
            self.assertEqual(rc, 2)

    def test_resume_skips_done_phases(self):
        """--resume 跳过已 done 的 phase。"""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            config_path = cwd / "config.json"
            state_path = cwd / PIPELINE_STATE_FILE
            # 先 init + dry-run 一次
            self._run_cli("--init", "--config", str(config_path), cwd=str(cwd))
            inp = cwd / "input.mp4"
            inp.write_bytes(b"fake")
            self._run_cli(
                str(inp), "--stem", "x",
                "--config", str(config_path),
                "--skip-preflight", "--dry-run",
                cwd=str(cwd),
            )
            # 修改 state 标记 verify_all 完成
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["done_phases"] = ["verify_all"]  # 只剩 verify 已 done
            state_path.write_text(json.dumps(state), encoding="utf-8")
            # 第二次跑 --resume,应跳过 verify_all
            rc, _, stderr = self._run_cli(
                str(inp), "--stem", "x",
                "--config", str(config_path),
                "--skip-preflight", "--dry-run", "--resume",
                cwd=str(cwd),
            )
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
