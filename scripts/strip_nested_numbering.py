#!/usr/bin/env python3
"""strip_nested_numbering.py — NO-NESTED-NUMBERING 规约(regex 实现)

检测并修复 markdown 中嵌套编号违规:
  1. H4 数量 ≤ 3 / H3(H4-PER-H3-MAX)
  2. H4 总量 ≤ 50(H4-TOTAL-MAX)
  3. 同 H2 下 H3 编号连续(1, 2, 3 ...)
  4. 同 H3 下 H4 编号连续(1.1, 1.2, 1.3 ...)

违规处理:
  - 超过每 H3 上限的 H4:合并到父 H3(降级为加粗子标题)
  - 同 H2 下 H3 编号跳号:自动重排为连续
  - H4 编号跳号:自动重排

用法:
  python scripts/strip_nested_numbering.py <input.md> -o <output.md>
  python scripts/strip_nested_numbering.py <input.md> -o <output.md> --dry-run  # 只检查不写

退出码:
  0 = 无违规或已修复
  1 = 修复后仍有问题
  2 = 输入错误
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
from utils import read_file_safely, write_file_safely, log  # noqa: E402


# 配置 ---------------------------------------------------------

H4_PER_H3_MAX = 3  # v4.4 H4-PER-H3-MAX
H4_TOTAL_MAX = 50  # v4.4 H4-TOTAL-MAX


# 标题正则
_H2_RE = re.compile(r'^##\s+(.+?)$', re.MULTILINE)
_H3_RE = re.compile(r'^###\s+(.+?)$', re.MULTILINE)
_H4_RE = re.compile(r'^####\s+(.+?)$', re.MULTILINE)

# 编号匹配:`1` / `1.` / `1.1` / `1.1.1` / `1.1.1.` 全部接受,后接空格 + 标题
_NUMBERING_PREFIX = re.compile(r'^(\d+(?:\.\d+)*)\.?\s+(.+?)$')


def detect_violations(text: str) -> list[str]:
    """检测所有违规,返回违规列表(每条是描述字符串)。"""
    violations: list[str] = []
    lines = text.splitlines()

    h4_total = 0
    current_h2_idx = -1
    current_h3_idx = -1
    h3_count_in_h2: dict[int, list[int]] = {}
    h4_count_in_h3: dict[tuple[int, int], list[int]] = {}

    for line in lines:
        if line.startswith('## ') and not line.startswith('### '):
            current_h2_idx += 1
            current_h3_idx = -1
        elif line.startswith('### ') and not line.startswith('#### '):
            current_h3_idx += 1
            m = _NUMBERING_PREFIX.match(line[4:].strip())
            if m and current_h2_idx >= 0:
                nums = m.group(1).split('.')
                if len(nums) == 2 and int(nums[0]) == current_h2_idx + 1:
                    n = int(nums[1])
                    h3_count_in_h2.setdefault(current_h2_idx, []).append(n)
        elif line.startswith('#### ') and not line.startswith('##### '):
            h4_total += 1
            m = _NUMBERING_PREFIX.match(line[5:].strip())
            if m and current_h2_idx >= 0 and current_h3_idx >= 0:
                nums = m.group(1).split('.')
                if len(nums) == 3:
                    h3_num = int(nums[1])
                    if h3_num == current_h3_idx + 1:
                        n = int(nums[2])
                        h4_count_in_h3.setdefault(
                            (current_h2_idx, current_h3_idx), []
                        ).append(n)

    # H4-TOTAL-MAX
    if h4_total > H4_TOTAL_MAX:
        violations.append(f"H4 总量 {h4_total} > 上限 {H4_TOTAL_MAX}")

    # H3 跳号检测
    for h2_idx, h3_nums in h3_count_in_h2.items():
        if not h3_nums:
            continue
        expected = list(range(1, max(h3_nums) + 1))
        if sorted(h3_nums) != expected:
            violations.append(f"H2-{h2_idx+1} 下 H3 编号跳号:{h3_nums}")

    # H4 跳号 + 超过 H4-PER-H3-MAX
    for (h2_idx, h3_idx), h4_nums in h4_count_in_h3.items():
        if len(h4_nums) > H4_PER_H3_MAX:
            violations.append(
                f"H2-{h2_idx+1}/H3-{h3_idx+1} 下 H4 数 {len(h4_nums)} > 上限 {H4_PER_H3_MAX}"
            )
        if h4_nums:
            expected = list(range(1, max(h4_nums) + 1))
            if sorted(h4_nums) != expected:
                violations.append(
                    f"H2-{h2_idx+1}/H3-{h3_idx+1} 下 H4 编号跳号:{h4_nums}"
                )

    return violations


def renumber_headings(text: str) -> tuple[str, int]:
    """重排所有标题编号为连续,返回 (新文本, 修改行数)。"""
    lines = text.splitlines(keepends=True)
    new_lines: list[str] = []
    modifications = 0

    h2_idx = -1
    h3_idx = -1
    h4_idx = -1
    h3_renumber = 0  # 实际 H3 序号
    h4_renumber = 0

    for line in lines:
        # H2
        if line.startswith('## ') and not line.startswith('### '):
            h2_idx += 1
            h3_idx = -1
            h4_idx = -1
            m = _NUMBERING_PREFIX.match(line[3:].strip())
            if m:
                new_title = m.group(2)
                new_line = f"## {h2_idx + 1}. {new_title}\n"
                if line != new_line:
                    new_lines.append(new_line)
                    modifications += 1
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        # H3
        elif line.startswith('### ') and not line.startswith('#### '):
            h3_idx += 1
            h4_idx = -1
            h3_renumber += 1
            h4_renumber = 0
            m = _NUMBERING_PREFIX.match(line[4:].strip())
            if m:
                new_title = m.group(2)
                new_line = f"### {h2_idx + 1}.{h3_renumber} {new_title}\n"
                if line != new_line:
                    new_lines.append(new_line)
                    modifications += 1
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        # H4
        elif line.startswith('#### ') and not line.startswith('##### '):
            h4_idx += 1
            h4_renumber += 1
            m = _NUMBERING_PREFIX.match(line[5:].strip())
            if m:
                new_title = m.group(2)
                new_line = f"#### {h2_idx + 1}.{h3_renumber}.{h4_renumber} {new_title}\n"
                if line != new_line:
                    new_lines.append(new_line)
                    modifications += 1
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    return ''.join(new_lines), modifications


def merge_excess_h4(text: str) -> tuple[str, int]:
    """把超过 H4-PER-H3-MAX 的 H4 降级为加粗段落。

    保留前 H4_PER_H3_MAX 个 H4,超出部分转为 `**old_h4_title**` 段落。
    """
    lines = text.splitlines(keepends=True)
    new_lines: list[str] = []
    h4_count = 0
    modifications = 0

    for line in lines:
        if line.startswith('#### ') and not line.startswith('##### '):
            h4_count += 1
            if h4_count > H4_PER_H3_MAX:
                # 降级为加粗段落
                m = _NUMBERING_PREFIX.match(line[5:].strip())
                if m:
                    # m.group(1) 已是 "1.1.4",无需再加 .
                    title = f"{m.group(1)} {m.group(2)}"
                else:
                    title = line[5:].strip()
                new_line = f"**{title}**\n"
                new_lines.append(new_line)
                modifications += 1
            else:
                new_lines.append(line)
        elif line.startswith('### ') and not line.startswith('#### '):
            h4_count = 0
            new_lines.append(line)
        else:
            new_lines.append(line)

    return ''.join(new_lines), modifications


def main() -> int:
    parser = argparse.ArgumentParser(
        description='NO-NESTED-NUMBERING 规约:检测 + 修复嵌套编号',
    )
    parser.add_argument('input', type=Path, help='输入 md 路径')
    parser.add_argument('-o', '--output', type=Path, required=True, help='输出 md 路径')
    parser.add_argument('--dry-run', action='store_true', help='只检测不修复')
    args = parser.parse_args()

    if not args.input.exists():
        log(f"ERROR: 输入文件不存在:{args.input}")
        return 2

    text = read_file_safely(args.input)

    # 检测
    violations = detect_violations(text)
    if violations:
        log(f"[strip-nested] 检测到 {len(violations)} 个违规:")
        for v in violations:
            log(f"  - {v}")
    else:
        log("[strip-nested] 无违规")

    if args.dry_run:
        return 1 if violations else 0

    # 修复:先合并超量 H4,再重排编号
    text, m1 = merge_excess_h4(text)
    text, m2 = renumber_headings(text)
    log(f"[strip-nested] 修复:{m1} 个 H4 降级 + {m2} 个标题重编号")

    # 重新检测
    violations_after = detect_violations(text)
    if violations_after:
        log(f"[strip-nested] WARN: 修复后仍 {len(violations_after)} 个违规")

    write_file_safely(args.output, text)
    log(f"[strip-nested] wrote {args.output}")
    return 1 if violations_after else 0


if __name__ == '__main__':
    sys.exit(main())
