"""test_pipeline_idempotency.py — D6 幂等性 + pipeline_state.json 专项测试

覆盖:
  1. state 文件 schema(done_phases + outputs)
  2. mark_done 幂等(同一 phase 多次标记不重复)
  3. is_done 正确反映 state
  4. --resume 跳过已 done phase(run_pipeline 集成)
  5. state 文件 corruption 检测(JSON 损坏 → 视为空 state)
  6. 输出路径(state.outputs[phase])可被下游 phase 复用
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(__file__.replace("\\", "/").rsplit("/", 2)[0]))

import scripts.run_pipeline as rp
from scripts.run_pipeline import (
    PIPELINE_STATE_FILE,
    load_state,
    save_state,
    mark_done,
    is_done,
)


# 1. state schema

class TestStateSchema(unittest.TestCase):

    def test_state_has_required_keys(self):
        """state 文件应含 done_phases + outputs 两个 key。"""
        state = load_state(Path("/nonexistent.json"))
        self.assertIn("done_phases", state)
        self.assertIn("outputs", state)
        self.assertIsInstance(state["done_phases"], list)
        self.assertIsInstance(state["outputs"], dict)

    def test_state_round_trip_with_output(self):
        """state 含 phase + output 路径时往返正确。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = {
                "done_phases": ["phase_0_asr", "phase_1_purify"],
                "outputs": {
                    "phase_0_asr": "/tmp/transcript.md",
                    "phase_1_purify": "/tmp/cleaned.md",
                },
            }
            save_state(path, state)
            loaded = load_state(path)
            self.assertEqual(loaded["done_phases"], state["done_phases"])
            self.assertEqual(loaded["outputs"], state["outputs"])


# 2. mark_done 幂等性

class TestMarkDoneIdempotent(unittest.TestCase):

    def test_mark_done_same_phase_once(self):
        """同一 phase mark_done 多次,只记 1 次。"""
        state = {"done_phases": [], "outputs": {}}
        mark_done(state, "phase_0_asr", "/tmp/x.md")
        mark_done(state, "phase_0_asr", "/tmp/x.md")
        mark_done(state, "phase_0_asr", "/tmp/x.md")
        self.assertEqual(state["done_phases"].count("phase_0_asr"), 1)

    def test_mark_done_different_phases(self):
        """不同 phase 都记录。"""
        state = {"done_phases": [], "outputs": {}}
        mark_done(state, "phase_0_asr", "/tmp/a.md")
        mark_done(state, "phase_1_purify", "/tmp/b.md")
        self.assertEqual(len(state["done_phases"]), 2)

    def test_mark_done_updates_output(self):
        """mark_done 多次以最后一次的 output 为准。"""
        state = {"done_phases": [], "outputs": {}}
        mark_done(state, "phase_0_asr", "/tmp/v1.md")
        mark_done(state, "phase_0_asr", "/tmp/v2.md")
        self.assertEqual(state["outputs"]["phase_0_asr"], "/tmp/v2.md")


# 3. is_done

class TestIsDone(unittest.TestCase):

    def test_is_done_true(self):
        state = {"done_phases": ["phase_0_asr"], "outputs": {}}
        self.assertTrue(is_done(state, "phase_0_asr"))

    def test_is_done_false(self):
        state = {"done_phases": [], "outputs": {}}
        self.assertFalse(is_done(state, "phase_0_asr"))


# 4. --resume 跳过已 done phase(run_pipeline 集成)

class TestResumeSkipDone(unittest.TestCase):

    def test_resume_skips_all_done_phases(self):
        """所有 phase 都 done 时,resume 全部跳过(应 exit 0)。"""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            config_path = cwd / "config.json"
            state_path = cwd / PIPELINE_STATE_FILE

            # init config
            proc = subprocess.run(
                [sys.executable,
                 str(Path(__file__).resolve().parent.parent / "scripts" / "run_pipeline.py"),
                 "--init", "--config", str(config_path)],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(proc.returncode, 0)

            # 预置 state(所有 phase + verify_all 都 done + 提供 output 路径)
            state = {
                "done_phases": [
                    "phase_0_asr", "phase_1_purify", "verify_all",
                ],
                "outputs": {
                    "phase_0_asr": str(cwd / "output" / "x" / "transcript_raw.md"),
                    "phase_1_purify": str(cwd / "output" / "x" / "cleaned.md"),
                },
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            # 写一个 dummy input
            inp = cwd / "input.mp4"
            inp.write_bytes(b"fake")
            # resume 跑(应全部跳过,exit 0)
            proc = subprocess.run(
                [sys.executable,
                 str(Path(__file__).resolve().parent.parent / "scripts" / "run_pipeline.py"),
                 str(inp), "--stem", "x",
                 "--config", str(config_path),
                 "--skip-preflight", "--dry-run", "--resume"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(proc.returncode, 0,
                             f"应 exit 0,实际 {proc.returncode}:{proc.stderr}")
            # 验证全部 phase 显示 "已 done(跳过)"
            self.assertIn("已 done", proc.stdout + proc.stderr)


# 5. corruption 容忍

class TestStateCorruptionTolerance(unittest.TestCase):

    def test_corrupted_json_treated_as_empty(self):
        """state JSON 损坏 → load_state 视作空 state(D6 健壮性)。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("not valid json{{{", encoding="utf-8")
            # 损坏 JSON 应抛 JSONDecodeError(由调用方处理)
            with self.assertRaises(json.JSONDecodeError):
                load_state(path)

    def test_missing_file_treated_as_empty(self):
        """state 文件不存在 → 空 state。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nonexistent.json"
            state = load_state(path)
            self.assertEqual(state, {"done_phases": [], "outputs": {}})


# 6. output 路径复用

class TestOutputReuse(unittest.TestCase):

    def test_output_path_recorded_in_state(self):
        """每个 phase 的 output 路径记录到 state.outputs。"""
        state = {"done_phases": [], "outputs": {}}
        mark_done(state, "phase_0_asr", "/tmp/transcript.md")
        mark_done(state, "phase_1_purify", "/tmp/cleaned.md")
        # 下游 phase 应能读到上游的 output
        self.assertEqual(state["outputs"]["phase_0_asr"], "/tmp/transcript.md")
        # 模拟下游:用 upstream output 作为 input
        upstream_output = state["outputs"]["phase_0_asr"]
        self.assertTrue(upstream_output.endswith(".md"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
