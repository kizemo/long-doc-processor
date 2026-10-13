#!/usr/bin/env python3
"""run_pipeline.py — D1 一键入口(核心)

v4.21 D 阶段:串 SKILL.md 必做首问 4 步 + Phase 0/1/2/3 + verify_all。

设计:
  - 单命令:python scripts/run_pipeline.py <input.mp4> --stem 讲义标题
  - 内置 dry-run 模式:所有 phase mock,不调外部命令/网络
  - 串联 phase 顺序:
    Phase 0:ASR (transcribe_via_crv.py 或 faster-whisper)
    Phase 1.0:D0 段级净化 (semantic_block_fix.py)
    Phase 1.1:chunk 切 (purify_v4_4_hierarchical.py)
    Phase 1.4:LLM 净化
    Phase 1.5:_post_terms_fix
    Phase 1.7:LLM Semantic Pass (strip_lecturer_preamble + strip_role_persona + last_section_reprocess)
    Phase 1.8:原帧智能裁剪(可选,按 Step 0.7 决定)
    Phase 2:合并 (此处 v1 dry-run 跳过)
    Phase 3:渲染 HTML (此处 v1 dry-run 跳过)
    verify_all:全 21 条规约

  - D6 幂等性:写 pipeline_state.json,resume 时跳过已 done 的 phase
  - D7 时间预算:每个 phase 包 time_budget,exit 时输出总览

用法:
  python scripts/run_pipeline.py input.mp4 --stem 讲义标题
  python scripts/run_pipeline.py input.mp4 --stem 讲义标题 --dry-run
  python scripts/run_pipeline.py input.mp4 --stem 讲义标题 --resume
  python scripts/run_pipeline.py input.mp4 --stem 讲义标题 --init  # 只生成 config

退出码:
  0 = 全部 phase 成功 + verify_all PASS
  1 = 输入错误
  2 = preflight 缺失
  3 = 某 phase 失败
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
from utils import log, time_budget, format_budget_summary  # noqa: E402


# Phase 列表(D6 幂等性 key)
PHASES = [
    "phase_0_asr",
    "phase_1_0_d0",
    "phase_1_1_chunk",
    "phase_1_4_purify",
    "phase_1_5_post_terms",
    "phase_1_7_semantic",
    "phase_1_8_crop",
    "phase_2_merge",
    "phase_3_render",
    "verify_all",
]

PIPELINE_STATE_FILE = "pipeline_state.json"


# v4.22 F7:区分 stub 阶段(待实现)与真实 phase 错误
class PipelineStubError(NotImplementedError):
    """Stub 阶段抛此异常,提示用户该 phase 尚未实现真实模式(只 dry-run)。"""
    pass


def load_config(path: Path) -> dict:
    """读 pipeline_config.json(由 --init 生成或 preflight_check 写)。"""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(path: Path, config: dict) -> None:
    """写 pipeline_config.json。"""
    path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_state(path: Path) -> dict:
    """读 pipeline_state.json(D6 幂等性)。"""
    if not path.exists():
        return {"done_phases": [], "outputs": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict) -> None:
    """写 pipeline_state.json。"""
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def mark_done(state: dict, phase: str, output: str | None = None) -> None:
    """D6 幂等性:标记 phase 完成。"""
    if phase not in state["done_phases"]:
        state["done_phases"].append(phase)
    if output:
        state["outputs"][phase] = output


def is_done(state: dict, phase: str) -> bool:
    """D6 幂等性:检查 phase 是否已完成。"""
    return phase in state["done_phases"]


def run_phase_0_asr(input_path: Path, output_dir: Path, dry_run: bool, budget: dict) -> str:
    """Phase 0:ASR(dry-run 模式只 mock 输出 transcript_raw.md)。"""
    with time_budget("phase_0_asr", budget):
        if dry_run:
            # 写一个 mock transcript_raw.md
            output_dir.mkdir(parents=True, exist_ok=True)
            output = output_dir / "transcript_raw.md"
            output.write_text(
                "# mock transcript\n\n[00:00:00] mock 段 1\n[00:01:00] mock 段 2\n",
                encoding="utf-8",
            )
            log(f"[run-pipeline] phase_0_asr (dry-run): wrote {output}")
            return str(output)
        else:
            # 真实 ASR:调 transcribe_via_crv.py(v4.22 F7:用 PipelineStubError 区分)
            log("[run-pipeline] phase_0_asr: 真实 ASR(此处未实现,需 --dry-run)")
            raise PipelineStubError("phase_0_asr 真实模式未实现,请用 --dry-run 或先单独跑 transcribe_via_crv.py")


def run_phase_1_purify(
    input_md: Path,
    output_dir: Path,
    dry_run: bool,
    budget: dict,
) -> str:
    """Phase 1:净化(dry-run 模式 mock 所有 step)。"""
    with time_budget("phase_1_purify", budget):
        if dry_run:
            output_dir.mkdir(parents=True, exist_ok=True)
            output = output_dir / "cleaned.md"
            # mock 产物:从 input 抄(没 LLM 处理)
            output.write_text(input_md.read_text(encoding="utf-8"), encoding="utf-8")
            log(f"[run-pipeline] phase_1_purify (dry-run): wrote {output}")
            return str(output)
        else:
            log("[run-pipeline] phase_1_purify: 真实净化(此处未实现,需 --dry-run)")
            raise PipelineStubError("phase_1_purify 真实模式未实现,请用 --dry-run 或先单独跑 purify_v4_4_hierarchical.py")


def run_verify_all(input_md: Path, dry_run: bool, budget: dict) -> int:
    """verify_all:全 21 条规约检查(dry-run 模式直接 PASS)。"""
    with time_budget("verify_all", budget):
        if dry_run:
            log("[run-pipeline] verify_all (dry-run): mock PASS")
            return 0
        # 真实模式:调 verify_all.main()
        import scripts.verify_all as va
        results = va.verify_file(input_md)
        failed = [r for r in results if not r.passed]
        if failed:
            for r in failed:
                log(f"[run-pipeline] FAIL {r.name}: {r.message}")
            return 1
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description='v4.21 D1 一键入口(必做首问 + Phase 0-3 + verify_all)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('input', nargs='?', type=Path, help='输入音视频路径')
    parser.add_argument('--stem', help='OUTPUT_STEM(Step 0.6 必填)')
    parser.add_argument('--output-dir', type=Path, help='输出目录(默认 ./output/<stem>)')
    parser.add_argument('--dry-run', action='store_true',
                        help='dry-run 模式:所有 phase mock,不调 LLM/ASR')
    parser.add_argument('--init', action='store_true',
                        help='只初始化 pipeline_config.json,不跑 phase')
    parser.add_argument('--resume', action='store_true',
                        help='D6 幂等:跳过 pipeline_state.json 中已 done 的 phase')
    parser.add_argument('--config', type=Path, default=Path("pipeline_config.json"),
                        help='pipeline_config.json 路径(默认当前目录)')
    parser.add_argument('--skip-preflight', action='store_true',
                        help='跳过 preflight_check(仅 dry-run 测试用)')
    args = parser.parse_args()

    # 0. 基础校验
    if not args.init and not args.input:
        log("ERROR: 必须指定 input(除非 --init)")
        return 1
    if not args.init and not args.stem:
        log("ERROR: 必须指定 --stem(Step 0.6 OUTPUT_STEM)")
        return 1

    # 1. 加载/初始化 config
    if args.input:
        input_stem = args.input.stem
    else:
        input_stem = "<init>"

    config = load_config(args.config)
    if not config:
        log(f"WARN: {args.config} 不存在,生成默认 config")
        config = {
            "step_0_asr_model": "turbo",
            "step_0_duration_min": 60,
            "step_0_5_output_dir": "default",
            "step_0_6_output_stem": args.stem or input_stem,
            "step_0_7_phase_1_8": "no",
        }
        save_config(args.config, config)

    if args.init:
        # --init 模式:已写到 config(默认 or 已有),返回
        log(f"[run-pipeline] ✅ config 已写到 {args.config}")
        return 0

    # 2. preflight check(4 步首问)
    if not args.skip_preflight:
        log("[run-pipeline] Step 0:preflight_check 4 步首问...")
        # 兼容 scripts 包 / 顶级模块 两种 import 方式
        try:
            from scripts.preflight_check import check_config as pfc_check
        except ImportError:
            from preflight_check import check_config as pfc_check  # type: ignore
        ok, missing = pfc_check(config)
        if not ok:
            log("[run-pipeline] ❌ preflight 必填项缺失:")
            for m in missing:
                log(m)
            log("[run-pipeline] 提示:先跑 preflight_check.py 或在 config 中填写完整")
            return 2
        log("[run-pipeline] ✅ preflight PASS")

    # 3. 加载 state(D6 幂等性)
    state = load_state(args.config.parent / PIPELINE_STATE_FILE)
    budget: dict = {}

    # 4. 准备 output_dir
    output_dir = args.output_dir or (Path("output") / args.stem)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # 5. 串 phase
    log(f"[run-pipeline] 开始(共 {len(PHASES)} phase,resume={args.resume})")
    log(f"[run-pipeline] output_dir: {output_dir}")

    if not is_done(state, "phase_0_asr") or not args.resume:
        try:
            out = run_phase_0_asr(args.input, output_dir, args.dry_run, budget)
            mark_done(state, "phase_0_asr", out)
            save_state(args.config.parent / PIPELINE_STATE_FILE, state)
        except PipelineStubError as e:
            # v4.22 F7:stub 阶段(待实现),明确提示用户
            log(f"[run-pipeline] ⚠️ STUB: {e}")
            log("[run-pipeline] 提示:先单独跑该 phase 的脚本(如 transcribe_via_crv.py),或用 --dry-run")
            return 4
        except NotImplementedError as e:
            log(f"[run-pipeline] FAIL: {e}")
            return 3
    else:
        log("[run-pipeline] phase_0_asr 已 done(跳过)")

    if not is_done(state, "phase_1_purify") or not args.resume:
        transcript_path = Path(state["outputs"]["phase_0_asr"])
        try:
            out = run_phase_1_purify(transcript_path, output_dir, args.dry_run, budget)
            mark_done(state, "phase_1_purify", out)
            save_state(args.config.parent / PIPELINE_STATE_FILE, state)
        except NotImplementedError as e:
            log(f"[run-pipeline] FAIL: {e}")
            return 3
    else:
        log("[run-pipeline] phase_1_purify 已 done(跳过)")

    # 6. verify_all
    cleaned_path = Path(state["outputs"]["phase_1_purify"])
    rc = run_verify_all(cleaned_path, args.dry_run, budget)
    if rc != 0:
        log("[run-pipeline] verify_all FAIL")
        return 3
    mark_done(state, "verify_all", "pass")
    save_state(args.config.parent / PIPELINE_STATE_FILE, state)

    # 7. 时间预算总览(D7)
    log("[run-pipeline] ===== 时间预算总览 =====")
    log(format_budget_summary(budget))
    log("[run-pipeline] ✅ 全部 phase 成功")
    return 0


if __name__ == "__main__":
    sys.exit(main())
