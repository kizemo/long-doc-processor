#!/usr/bin/env python3
"""extract_skeleton.py — 从 raw.md 提取 H1/H2/H3 骨架,供 purify_v4_4_hierarchical.py 作 anchor

输出: `<stem>_skeleton.md`,仅含标题层级(无正文),便于:
1. 给 LLM 当 anchor(约束"输出 N 个 H2 且标题文字 = skeleton")
2. 末段修复(last_section_reprocess.py)判断缺失章节

用法:
  python scripts/extract_skeleton.py <raw.md> -o <skeleton.md>
  python scripts/extract_skeleton.py <raw.md> -o <skeleton.md> --include-h3  # 含 H3
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


# v4.22 F1:heading 正则统一从 chunking 导入(等价 pattern)
from chunking import _H1_TITLE_RE, _H2_TITLE_RE, _H3_TITLE_RE, _H4_TITLE_RE  # noqa: E402
_H1_RE = _H1_TITLE_RE
_H2_RE = _H2_TITLE_RE
_H3_RE = _H3_TITLE_RE
_H4_RE = _H4_TITLE_RE


def extract_skeleton(input_path: Path, include_h3: bool = False,
                    include_h4: bool = False) -> str:
    """从 input.md 抽取标题层级,生成 skeleton.md 内容。

    Args:
        include_h3: 是否保留 H3 子节(默认 False,只 H1+H2)
        include_h4: 是否保留 H4(默认 False)

    Returns:
        skeleton.md 内容(纯标题,带空行分隔)
    """
    content = read_file_safely(input_path)

    # 收集所有标题行,按行号排序去重
    titles: list[tuple[int, str]] = []  # (offset, line)

    for m in _H1_RE.finditer(content):
        titles.append((m.start(), m.group(0)))
    for m in _H2_RE.finditer(content):
        titles.append((m.start(), m.group(0)))
    if include_h3:
        for m in _H3_RE.finditer(content):
            titles.append((m.start(), m.group(0)))
    if include_h4:
        for m in _H4_RE.finditer(content):
            titles.append((m.start(), m.group(0)))

    # 按行号排序
    titles.sort(key=lambda x: x[0])

    # 去重(保留第一次出现)
    seen: set[str] = set()
    unique: list[str] = []
    for _, line in titles:
        if line not in seen:
            seen.add(line)
            unique.append(line)

    # 重新计算层级深度,确保 H1 前无 H2/H3/H4
    lines: list[str] = []
    prev_level = 0
    for line in unique:
        m = re.match(r'^(#+)', line)
        if m:
            level = len(m.group(1))
            # 跳级检查:H1 之前不能有 H2+
            if prev_level == 0 and level > 1:
                continue
            # 跳级:不能从 H1 直接跳到 H3(中间要 H2)
            if prev_level == 1 and level == 3:
                continue
            lines.append(line)
            prev_level = level

    return '\n\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description='提取 markdown 骨架(H1+H2) 用于 LLM anchor')
    parser.add_argument('input', type=Path, help='输入 raw/transcript md 路径')
    parser.add_argument('-o', '--output', type=Path, required=True, help='输出 skeleton.md 路径')
    parser.add_argument('--include-h3', action='store_true', help='包含 H3 子节')
    parser.add_argument('--include-h4', action='store_true', help='包含 H4')
    args = parser.parse_args()

    if not args.input.exists():
        log(f"ERROR: 输入文件不存在:{args.input}")
        return 1

    skeleton = extract_skeleton(args.input, include_h3=args.include_h3, include_h4=args.include_h4)
    write_file_safely(args.output, skeleton)
    log(f"[skeleton] wrote {args.output} ({len(skeleton.splitlines())} lines)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
