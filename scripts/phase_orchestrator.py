#!/usr/bin/env python3
"""phase_orchestrator.py — D5 Phase 1.7 / 1.8 orchestrator(v4.21)

D5 设计:串两个 orchestrator:
  - phase_1_7_orchestrator:strip_lecturer_preamble → strip_role_persona → last_section_reprocess
  - phase_1_8_orchestrator:跑 _crop_insert_frames.py(可选,按 Step 0.7)

这两个 orchestrator 独立运行,各自有 --dry-run / --verbose 模式。

用法:
  python scripts/phase_orchestrator.py --phase 1.7 --input in.md --output out.md
  python scripts/phase_orchestrator.py --phase 1.8 --input in.md --output out.md
  python scripts/phase_orchestrator.py --phase 1.7 --input in.md --output out.md --dry-run

退出码:
  0 = 成功
  1 = 输入错误
  2 = phase 参数错
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
from utils import log, time_budget  # noqa: E402


def run_phase_1_7(
    input_path: Path,
    output_path: Path,
    dry_run: bool = False,
    workers: int = 3,
) -> int:
    """Phase 1.7 orchestrator:strip_lecturer → strip_role_persona → last_section_reprocess。

    通过模块 import 直接调 strip_block / last_section_reprocess,避免 subprocess 开销。
    """
    budget: dict = {}
    log("[orchestrator 1.7] 开始 Phase 1.7 串行...")
    if not input_path.exists():
        log(f"ERROR: 输入文件不存在:{input_path}")
        return 1

    # 1. strip_lecturer_preamble
    with time_budget("phase_1.7_strip_lecturer", budget):
        try:
            try:
                from scripts.strip_lecturer_preamble import strip_document
            except ImportError:
                from strip_lecturer_preamble import strip_document  # type: ignore
            # 中间产物 → 临时文件
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.md', delete=False, encoding='utf-8'
            ) as f:
                tmp1 = Path(f.name)
            rc = strip_document(
                input_path, tmp1,
                workers=workers,
                dry_run=dry_run,  # type: ignore[arg-type]
            )
            if rc != 0:
                log(f"[orchestrator 1.7] strip_lecturer 失败 (rc={rc})")
                return rc
        except Exception as e:
            log(f"[orchestrator 1.7] strip_lecturer 异常:{type(e).__name__}: {e}")
            return 1

    # 2. strip_role_persona
    with time_budget("phase_1.7_strip_persona", budget):
        try:
            try:
                from scripts.strip_role_persona import strip_document as strip_persona_doc
            except ImportError:
                from strip_role_persona import strip_document as strip_persona_doc  # type: ignore
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.md', delete=False, encoding='utf-8'
            ) as f:
                tmp2 = Path(f.name)
            rc = strip_persona_doc(
                tmp1, tmp2,
                workers=workers,
                dry_run=dry_run,  # type: ignore[arg-type]
            )
            if rc != 0:
                log(f"[orchestrator 1.7] strip_role_persona 失败 (rc={rc})")
                return rc
        except Exception as e:
            log(f"[orchestrator 1.7] strip_role_persona 异常:{type(e).__name__}: {e}")
            return 1

    # 3. last_section_reprocess
    with time_budget("phase_1.7_last_section", budget):
        try:
            try:
                from scripts.last_section_reprocess import last_section_reprocess
            except ImportError:
                from last_section_reprocess import last_section_reprocess  # type: ignore
            rc = last_section_reprocess(tmp2, output_path, tail_ratio=0.25)
            if rc != 0:
                log(f"[orchestrator 1.7] last_section_reprocess 失败 (rc={rc})")
                return rc
        except Exception as e:
            log(f"[orchestrator 1.7] last_section_reprocess 异常:{type(e).__name__}: {e}")
            return 1
        finally:
            tmp1.unlink(missing_ok=True)
            tmp2.unlink(missing_ok=True)

    log("[orchestrator 1.7] ✅ 3 步全部完成")
    for phase, elapsed in budget.items():
        log(f"  {phase}: {elapsed:.1f}s")
    return 0


def run_phase_1_8(
    input_path: Path,
    output_path: Path,
    dry_run: bool = False,
) -> int:
    """Phase 1.8 orchestrator:跑 _crop_insert_frames(可选,按 Step 0.7)。

    v4.21 简化:dry-run 模式只 mock 复制 input → output。
    """
    log("[orchestrator 1.8] 开始 Phase 1.8 原帧智能裁剪...")
    if not input_path.exists():
        log(f"ERROR: 输入文件不存在:{input_path}")
        return 1

    if dry_run:
        # dry-run 模式:复制 input 到 output(模拟"无修改")
        shutil.copy(input_path, output_path)
        log(f"[orchestrator 1.8] (dry-run) 复制 {input_path} → {output_path}")
        return 0

    # 真实模式:跑 _crop_insert_frames.py(此处 v1 简化,后续可补)
    log("[orchestrator 1.8] 真实模式需 --dry-run(后续可集成 _crop_insert_frames.py)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description='v4.21 D5 Phase 1.7 / 1.8 orchestrator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--phase', required=True, choices=['1.7', '1.8'],
                        help='Phase 编号(1.7 = LLM Semantic Pass;1.8 = 原帧智能裁剪)')
    parser.add_argument('--input', type=Path, required=True, help='输入 md 路径')
    parser.add_argument('--output', type=Path, required=True, help='输出 md 路径')
    parser.add_argument('--workers', type=int, default=3, help='并发 LLM 数(1.7 only)')
    parser.add_argument('--dry-run', action='store_true', help='dry-run 模式')
    args = parser.parse_args()

    if args.phase == '1.7':
        return run_phase_1_7(args.input, args.output, args.dry_run, args.workers)
    elif args.phase == '1.8':
        return run_phase_1_8(args.input, args.output, args.dry_run)
    else:
        log(f"ERROR: --phase 必须是 1.7 或 1.8,实际 {args.phase}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
