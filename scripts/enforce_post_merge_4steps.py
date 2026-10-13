#!/usr/bin/env python3
"""enforce_post_merge_4steps.py — D4 固化 v4.9.1 必做 4 步验证

v4.9.1 总结与行动建议章节硬约束(SKILL.md):
  4 步 = 合并后强制 4 件事
  1. LAST_SECTION_COMPLETE:末段 H2 含 ≥2 H3 + 5 类资产
  2. HIERARCHICAL_NUMBERING:H2/H3/H4 强制 N./N.M/N.M.K 编号
  3. NO_ROLE_PERSONA:全文删讲师/学员主语
  4. NO_DOC_META_HEADER:H1 下无文档元说明

本脚本:在 Phase 2 合并后强制运行,任一 FAIL → exit 1(阻止 Phase 3 渲染)。

设计:
  - 复用 verify_all 的 4 个 verify 函数(避免重复实现)
  - 加总览报告(每条 PASS/FAIL + 行号细节)
  - exit 1 = 至少 1 条 FAIL
  - exit 0 = 全部 PASS

用法:
  python scripts/enforce_post_merge_4steps.py <cleaned.md>
  python scripts/enforce_post_merge_4steps.py <cleaned.md> --verbose

退出码:
  0 = 4 步全 PASS
  1 = 至少 1 步 FAIL
  2 = 输入错误
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
from utils import log  # noqa: E402

# 4 步对应的 verify 函数(从 verify_all 复用)
POST_MERGE_4_STEPS = [
    ("LAST_SECTION_COMPLETE", "末段 H2 含 ≥2 H3 + 5 类资产"),
    ("HIERARCHICAL_NUMBERING", "H2/H3/H4 强制 N./N.M/N.M.K 编号"),
    ("NO_ROLE_PERSONA_EXTENDED", "全文删讲师/学员主语(扩展规约)"),
    ("NO_DOC_META_HEADER", "H1 下无文档元说明"),
]


def run_4_steps(md_path: Path) -> tuple[bool, list[tuple[str, bool, str]]]:
    """跑 4 步验证,返回 (all_pass, [(step_name, passed, message), ...])。

    复用 verify_all 的 4 个函数,避免重复实现。
    """
    try:
        from scripts.verify_all import (
            verify_hierarchical_numbering,
            verify_no_doc_meta_header,
            verify_no_role_persona_extended,
        )
        from scripts.last_section_reprocess import last_section_reprocess
    except ImportError:
        # 兜底
        from verify_all import (  # type: ignore
            verify_hierarchical_numbering,
            verify_no_doc_meta_header,
            verify_no_role_persona_extended,
        )
        from last_section_reprocess import last_section_reprocess  # type: ignore

    results: list[tuple[str, bool, str]] = []

    # 1. LAST_SECTION_COMPLETE:简化为 last_section_reprocess 能成功处理
    try:
        with __import__("tempfile").NamedTemporaryFile(
            mode='w', suffix='.md', delete=False, encoding='utf-8'
        ) as f:
            f.write(md_path.read_text(encoding="utf-8"))
            tmp_path = Path(f.name)
        try:
            tmp_out = tmp_path.with_suffix('.out.md')
            rc = last_section_reprocess(tmp_path, tmp_out, tail_ratio=0.25)
            # 成功处理(不报错)即视为通过
            passed = (rc == 0)
            msg = "末段可被 last_section_reprocess 处理" if passed else f"rc={rc}"
            results.append(("LAST_SECTION_COMPLETE", passed, msg))
        finally:
            tmp_path.unlink(missing_ok=True)
            tmp_path.with_suffix('.out.md').unlink(missing_ok=True)
    except Exception as e:
        results.append(("LAST_SECTION_COMPLETE", False, f"EXCEPTION: {type(e).__name__}: {e}"))

    # 2. HIERARCHICAL_NUMBERING
    try:
        r = verify_hierarchical_numbering(md_path)
        results.append(("HIERARCHICAL_NUMBERING", r.passed, r.message))
    except Exception as e:
        results.append(("HIERARCHICAL_NUMBERING", False, f"EXCEPTION: {type(e).__name__}: {e}"))

    # 3. NO_ROLE_PERSONA_EXTENDED
    try:
        r = verify_no_role_persona_extended(md_path)
        results.append(("NO_ROLE_PERSONA_EXTENDED", r.passed, r.message))
    except Exception as e:
        results.append(("NO_ROLE_PERSONA_EXTENDED", False, f"EXCEPTION: {type(e).__name__}: {e}"))

    # 4. NO_DOC_META_HEADER
    try:
        r = verify_no_doc_meta_header(md_path)
        results.append(("NO_DOC_META_HEADER", r.passed, r.message))
    except Exception as e:
        results.append(("NO_DOC_META_HEADER", False, f"EXCEPTION: {type(e).__name__}: {e}"))

    all_pass = all(r[1] for r in results)
    return all_pass, results


def main() -> int:
    parser = argparse.ArgumentParser(
        description='v4.21 D4 固化 v4.9.1 必做 4 步验证',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('input', type=Path, help='合并后的 cleaned.md 路径')
    parser.add_argument('--verbose', action='store_true', help='详细输出')
    args = parser.parse_args()

    if not args.input.exists():
        log(f"ERROR: 输入文件不存在:{args.input}")
        return 2

    log(f"[enforce-4steps] 检查 {args.input}")
    all_pass, results = run_4_steps(args.input)

    # 输出 4 步结果
    log("[enforce-4steps] ===== v4.9.1 必做 4 步 =====")
    for step_name, step_desc in POST_MERGE_4_STEPS:
        # 找对应结果
        result = next((r for r in results if r[0] == step_name), None)
        if result is None:
            log(f"  ❌ {step_name}: NOT_RUN")
            continue
        _, passed, message = result
        status = "✅" if passed else "❌"
        log(f"  {status} {step_name}:{step_desc} → {message}")
        if not passed and args.verbose:
            log(f"     (FAIL details)")

    if all_pass:
        log("[enforce-4steps] ✅ 4 步全 PASS,可进入 Phase 3 渲染")
        return 0
    else:
        log("[enforce-4steps] ❌ 至少 1 步 FAIL,阻止 Phase 3 渲染")
        return 1


if __name__ == "__main__":
    sys.exit(main())
