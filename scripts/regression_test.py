#!/usr/bin/env python3
"""regression_test.py — 历史案例回归测试(SKILL.md "必跑")

跑历史项目案例,验证 purified output 仍符合规约。

测试用例位置: tests/regression_cases/*.json
每 json 包含:
  - name: 项目名
  - input_md: 输入 cleaned.md 路径
  - expected: dict[str, Any],期望通过的项目
    - h2_count_min: 最少 H2 数
    - h3_count_min: 最少 H3 数
    - cjk_retention_min: 最低中文保留率(0-100)
    - must_contain: 必须包含的字符串列表
    - must_not_contain: 不能包含的字符串列表(转录元数据 / 讲师前缀等)

用法:
  python scripts/regression_test.py
  python scripts/regression_test.py --case <case_name>  # 只跑指定 case
  python scripts/regression_test.py --cases-dir <path>  # 自定义 cases 目录

退出码:
  0 = 所有 case PASS
  1 = 至少一个 case FAIL
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
from utils import read_file_safely, log  # noqa: E402


# 默认 cases 目录(项目根 + tests/regression_cases)
DEFAULT_CASES_DIR = Path(__file__).resolve().parent.parent / 'tests' / 'regression_cases'


_H2_RE = re.compile(r'^##\s+', re.MULTILINE)
_H3_RE = re.compile(r'^###\s+', re.MULTILINE)


def count_cjk(text: str) -> int:
    return sum(1 for c in text if '一' <= c <= '῿')


def run_case(case_path: Path) -> tuple[bool, list[str]]:
    """跑单个 case,返回 (是否 PASS, 错误列表)。"""
    case = json.loads(read_file_safely(case_path))
    name = case.get('name', case_path.stem)
    # 相对路径基于 case 文件目录解析(便于 case 目录移动)
    base_dir = case_path.parent
    input_path = (base_dir / case['input_md']).resolve() if not Path(case['input_md']).is_absolute() else Path(case['input_md']).resolve()
    expected = case.get('expected', {})

    if not input_path.exists():
        return False, [f"输入文件不存在:{input_path}"]

    text = read_file_safely(input_path)
    errors: list[str] = []

    # H2 数量
    h2_count = len(_H2_RE.findall(text))
    h2_min = expected.get('h2_count_min', 0)
    if h2_count < h2_min:
        errors.append(f"H2 数 {h2_count} < 期望 {h2_min}")

    # H3 数量
    h3_count = len(_H3_RE.findall(text))
    h3_min = expected.get('h3_count_min', 0)
    if h3_count < h3_min:
        errors.append(f"H3 数 {h3_count} < 期望 {h3_min}")

    # 中文保留率
    cjk_retention_min = expected.get('cjk_retention_min')
    if cjk_retention_min is not None and 'raw_md' in case:
        raw_path_str = case['raw_md']
        raw_path = (base_dir / raw_path_str).resolve() if not Path(raw_path_str).is_absolute() else Path(raw_path_str).resolve()
        raw_text = read_file_safely(raw_path)
        cjk = count_cjk(text)
        raw_cjk = count_cjk(raw_text)
        if raw_cjk > 0:
            retention = cjk / raw_cjk * 100
            if retention < cjk_retention_min:
                errors.append(f"中文保留率 {retention:.1f}% < {cjk_retention_min}%")

    # must_contain
    for s in expected.get('must_contain', []):
        if s not in text:
            errors.append(f"缺少字符串:{s!r}")

    # must_not_contain(检测转录元数据 / 讲师前缀污染)
    for s in expected.get('must_not_contain', []):
        if s in text:
            errors.append(f"不应含字符串:{s!r}")

    passed = len(errors) == 0
    return passed, errors


def main() -> int:
    parser = argparse.ArgumentParser(description='历史案例回归测试')
    parser.add_argument('--case', help='只跑指定 case 名(stem 匹配)')
    parser.add_argument('--cases-dir', type=Path, default=DEFAULT_CASES_DIR,
                        help=f'cases 目录(默认 {DEFAULT_CASES_DIR})')
    args = parser.parse_args()

    if not args.cases_dir.exists():
        log(f"WARN: cases 目录不存在:{args.cases_dir}")
        log(f"提示:创建 {args.cases_dir} 并放入 <name>.json 测试用例")
        return 0  # 无 case 不是失败

    cases = sorted(args.cases_dir.glob('*.json'))
    if args.case:
        cases = [c for c in cases if c.stem == args.case]
        if not cases:
            log(f"ERROR: case {args.case!r} 未找到")
            return 1

    log(f"[regression] {len(cases)} cases")

    passed = 0
    failed = 0
    for case_path in cases:
        ok, errors = run_case(case_path)
        name = case_path.stem
        if ok:
            log(f"  ✅ {name}")
            passed += 1
        else:
            log(f"  ❌ {name}")
            for e in errors:
                log(f"     - {e}")
            failed += 1

    log(f"\n[regression] {passed} pass, {failed} fail")
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
