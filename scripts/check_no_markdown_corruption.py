#!/usr/bin/env python3
"""check_no_markdown_corruption.py — v4.12 表格完整性 + 污染词检测

检测 4 类 markdown 损坏:
  1. 表格列数不均匀(数据 N 列数不等)
  2. 已知污染词残留(garbage 字段如 `| 医疗器械标签` 等)
  3. 断裂标题(标题行后无任何正文)
  4. (可选)HTML vs md 表格数对比

用法:
  python scripts/check_no_markdown_corruption.py <input.md>
  python scripts/check_no_markdown_corruption.py <input.md> --html <output.html>
  python scripts/check_no_markdown_corruption.py <input.md> --output report.md

退出码:
  0 = 无损坏
  1 = 检测到损坏
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


# 已知污染词(v4.12 changelog 案例)
CORRUPTION_TOKENS = [
    '医疗器械标签',  # 鬼脚七线下课 '|' → '医疗器械标签' 表格污染
    '同价位',        # 同 product 同价位
    '店铺绩效',
]


# 表格检测正则
_TABLE_ROW_RE = re.compile(r'^\s*\|.*\|\s*$')  # 行首尾有 | 且含 |
_TABLE_SEP_RE = re.compile(r'^\s*\|?[\s:|-]+\|?\s*$')  # 表格分隔行 |---|---|
_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)$')


def find_tables(text: str) -> list[tuple[int, list[str]]]:
    """找所有 markdown 表格块,返回 [(start_line_idx, [lines]), ...]。

    表格定义:连续的 `|...|` 行(≥ 2 行),中间可有 `|---|---|` 分隔行。
    """
    lines = text.splitlines()
    tables: list[tuple[int, list[str]]] = []
    i = 0
    while i < len(lines):
        if _TABLE_ROW_RE.match(lines[i]):
            start = i
            table_lines = []
            while i < len(lines) and _TABLE_ROW_RE.match(lines[i]):
                table_lines.append(lines[i])
                i += 1
            if len(table_lines) >= 2:
                tables.append((start, table_lines))
        else:
            i += 1
    return tables


def check_table_column_consistency(tables: list[tuple[int, list[str]]]) -> list[str]:
    """检测表格列数不均匀。"""
    issues: list[str] = []
    for start_line, table_lines in tables:
        col_counts = [line.count('|') for line in table_lines]
        if not col_counts:
            continue
        most_common = max(set(col_counts), key=col_counts.count)
        for i, count in enumerate(col_counts):
            if count != most_common:
                issues.append(
                    f"表格(line {start_line + i + 1})列数 {count} ≠ 主列数 {most_common}"
                )
    return issues


def check_corruption_tokens(text: str) -> list[str]:
    """检测已知污染词残留。"""
    issues: list[str] = []
    for token in CORRUPTION_TOKENS:
        if token in text:
            issues.append(f"检测到污染词:{token!r}")
    return issues


def check_broken_headings(text: str) -> list[str]:
    """检测标题后无正文(孤立标题)。"""
    lines = text.splitlines()
    issues: list[str] = []
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if not m:
            continue
        # 找下一个非空行
        next_content_idx = i + 1
        while next_content_idx < len(lines) and not lines[next_content_idx].strip():
            next_content_idx += 1
        if next_content_idx >= len(lines):
            issues.append(f"标题(line {i+1}){m.group(2)!r} 后无任何内容")
            continue
        # 下个非空行是另一个标题?则当前标题孤立
        next_m = _HEADING_RE.match(lines[next_content_idx])
        if next_m:
            issues.append(
                f"标题(line {i+1}){m.group(2)!r} 后无正文,直接接下一个标题"
            )
    return issues


def count_html_tables(html: str) -> int:
    """粗略数 HTML 中的 <table> 数量。

    单个正则已覆盖 `<table>` / `<table ...>` / `<table\n...>` 三种起始形式,
    不再用 `html.count('<table>')` 重复统计。
    """
    return len(re.findall(r'<table[\s|>]', html))


def check_html_vs_md(md_text: str, html_text: str) -> list[str]:
    """对比 markdown 表格数 vs HTML 表格数(防止渲染丢失)。"""
    md_table_count = len(find_tables(md_text))
    html_table_count = count_html_tables(html_text)
    issues: list[str] = []
    if md_table_count != html_table_count:
        issues.append(
            f"表格数不一致:md={md_table_count} vs html={html_table_count}"
        )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description='v4.12 表格 + 污染词巡检')
    parser.add_argument('input', type=Path, help='输入 md 路径')
    parser.add_argument('--html', type=Path, help='HTML 路径(可选,启用 md vs html 对比)')
    parser.add_argument('--output', type=Path, help='报告输出路径(默认 stdout)')
    args = parser.parse_args()

    if not args.input.exists():
        log(f"ERROR: 输入文件不存在:{args.input}")
        return 2

    text = read_file_safely(args.input)
    tables = find_tables(text)

    all_issues: list[str] = []
    all_issues.extend(check_table_column_consistency(tables))
    all_issues.extend(check_corruption_tokens(text))
    all_issues.extend(check_broken_headings(text))
    if args.html and args.html.exists():
        html = read_file_safely(args.html)
        all_issues.extend(check_html_vs_md(text, html))

    report = f"# Markdown 损坏巡检报告\n\n文件:`{args.input.name}`\n表格数:{len(tables)}\n\n"
    if all_issues:
        report += f"## ❌ 检测到 {len(all_issues)} 个问题\n\n"
        for issue in all_issues:
            report += f"- {issue}\n"
    else:
        report += "## ✅ 无损坏\n"

    if args.output:
        write_file_safely(args.output, report)
        log(f"[check] wrote {args.output}")
    else:
        print(report)

    return 1 if all_issues else 0


if __name__ == '__main__':
    sys.exit(main())
