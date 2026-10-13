#!/usr/bin/env python3
"""preflight_check.py — D2 必做首问强制钩子

v4.21 D 阶段:在跑任何 ASR / 净化 / 渲染前,强制 4 步首问检查(SKILL.md v4.19 必做)。

设计:
  - 读 `pipeline_config.json`(由 run_pipeline.py 生成,或在 D2 命令行手动指定)
  - 验证 4 步首问字段均已填写
  - 任一缺失 → exit 2 拒绝跑
  - 全填 → 输出 OK,exit 0

用法:
  python scripts/preflight_check.py --config pipeline_config.json
  python scripts/preflight_check.py --auto  # 从 stdin 读 JSON

退出码:
  0 = 4 步首问已完整填写
  1 = config 缺失
  2 = 必填项缺失
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
from utils import log  # noqa: E402


# 4 步必做首问(对应 SKILL.md "⚡ 必做首问")
REQUIRED_FIELDS = {
    "step_0_asr_model": "Step 0:ASR 模型(turbo/large-v3/medium/small/base)",
    "step_0_duration_min": "Step 0:音视频时长(分钟)",
    "step_0_5_output_dir": "Step 0.5:输出目录(default/manual/no-subdir)",
    "step_0_6_output_stem": "Step 0.6:OUTPUT_STEM(最终产物文件名 stem)",
    "step_0_7_phase_1_8": "Step 0.7:是否启用 Phase 1.8 截图(yes/no/path-g)",
}


def check_config(config: dict) -> tuple[bool, list[str]]:
    """检查 4 步首问字段。

    Returns:
        (ok, missing_list) — ok=True 时 missing_list 为空
    """
    missing: list[str] = []
    for field, desc in REQUIRED_FIELDS.items():
        if field not in config:
            missing.append(f"  - {field}:{desc}")
        elif config[field] in (None, "", "TBD"):
            missing.append(f"  - {field}:{desc} (值为空/TBD)")

    # 额外校验:duration 必须是数字
    if "step_0_duration_min" in config and not isinstance(
        config["step_0_duration_min"], (int, float)
    ):
        missing.append("  - step_0_duration_min:必须是数字(分钟)")

    # 额外校验:step_0_7 必须是 yes/no/path-g
    if "step_0_7_phase_1_8" in config and config["step_0_7_phase_1_8"] not in (
        "yes", "no", "path-g"
    ):
        missing.append(
            f"  - step_0_7_phase_1_8:必须是 yes/no/path-g,实际 {config['step_0_7_phase_1_8']!r}"
        )

    # 额外校验:step_0_5 必须是 default/manual/no-subdir
    if "step_0_5_output_dir" in config and config["step_0_5_output_dir"] not in (
        "default", "manual", "no-subdir"
    ):
        missing.append(
            f"  - step_0_5_output_dir:必须是 default/manual/no-subdir,"
            f"实际 {config['step_0_5_output_dir']!r}"
        )

    return len(missing) == 0, missing


def main() -> int:
    parser = argparse.ArgumentParser(
        description='v4.21 D2 必做首问检查(4 步)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--config', type=Path, help='pipeline_config.json 路径')
    parser.add_argument('--auto', action='store_true', help='从 stdin 读 JSON')
    args = parser.parse_args()

    config: dict = {}
    if args.config:
        if not args.config.exists():
            log(f"ERROR: 配置文件不存在:{args.config}")
            log("提示:先跑 run_pipeline.py --init 生成,或手动创建")
            return 1
        config = json.loads(args.config.read_text(encoding="utf-8"))
    elif args.auto:
        # 从 stdin 读 JSON
        raw = sys.stdin.read()
        if not raw.strip():
            log("ERROR: stdin 为空")
            return 1
        config = json.loads(raw)
    else:
        log("ERROR: 必须指定 --config <path> 或 --auto")
        return 1

    log("[preflight] 检查 4 步首问字段...")
    ok, missing = check_config(config)
    if not ok:
        log("[preflight] ❌ 必填项缺失:")
        for m in missing:
            log(m)
        log("\n[preflight] 请先完成 SKILL.md '⚡ 必做首问 4 步':")
        log("  1. Step 0   - ASR 模型 + 时长")
        log("  2. Step 0.5 - 输出目录命名")
        log("  3. Step 0.6 - OUTPUT_STEM")
        log("  4. Step 0.7 - 是否启用 Phase 1.8 截图")
        return 2

    log("[preflight] ✅ 4 步首问已完整填写:")
    for field, desc in REQUIRED_FIELDS.items():
        log(f"  - {field} = {config[field]!r}")
    log("[preflight] OK — 可继续跑 run_pipeline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
