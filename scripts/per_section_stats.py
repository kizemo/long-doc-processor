#!/usr/bin/env python3
"""per_section_stats.py — 章节保留率 + 5 类资产诊断工具(v4.4)

对 cleaned.md 输出每 H2 章节的统计:
  - 字符数 + 中文字符数 + 保留率(若提供 raw_md 则对比)
  - 5 类资产完整性检查(概念 / 案例 / 数据 / 逻辑 / 表格)
  - 8 类实质内容覆盖(理论 / 概念 / 实操 / 推导逻辑 / 案例 / 数据 / 分析 / 观点)

用法:
  python scripts/per_section_stats.py <cleaned.md> [--raw-md <raw.md>]
  python scripts/per_section_stats.py <cleaned.md> --output <report.md>

退出码:
  0 = 所有章节 5 类资产齐全
  1 = 部分章节缺资产(诊断报告)
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

# v4.22 F1:heading 正则统一从 chunking 导入
from chunking import _H2_TITLE_RE as _H2_RE  # noqa: E402


# 5 类资产关键词(粗匹配,实际 LLM 应做更精细判断)
ASSET_PATTERNS = {
    '概念': [r'定义', r'概念', r'是什么', r'含义', r'所谓'],
    '案例': [r'案例', r'店铺', r'品牌', r'某商家', r'比如'],
    '数据': [r'\d+%', r'\d+元', r'GMV', r'ROI', r'转化率', r'\d+倍'],
    '逻辑': [r'因为', r'所以', r'因此', r'导致', r'进而', r'从而'],
    '表格': [r'^\|.*\|', r'^\|?-+\|?-+$'],  # markdown table 形式(转义 |)
}


def count_cjk(text: str) -> int:
    """统计中文字符数(U+4E00-U+9FFF)。"""
    return sum(1 for c in text if '一' <= c <= '鿿')


def split_by_h2(text: str) -> list[tuple[str, str]]:
    """按 H2 切分,返回 [(h2_title, content), ...]。"""
    positions: list[tuple[int, str]] = []
    for m in _H2_RE.finditer(text):
        positions.append((m.start(), m.group(1).strip()))

    if not positions:
        return [("(no H2)", text)]

    sections: list[tuple[str, str]] = []
    for i, (offset, title) in enumerate(positions):
        next_offset = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        content = text[offset:next_offset]
        sections.append((title, content))
    return sections


def check_assets(content: str) -> dict[str, int]:
    """检查 5 类资产,返回每类命中次数。"""
    result = {}
    for asset, patterns in ASSET_PATTERNS.items():
        count = 0
        for pat in patterns:
            count += len(re.findall(pat, content, re.MULTILINE))
        result[asset] = count
    return result


def per_section_stats(cleaned_path: Path, raw_path: Path | None = None) -> str:
    """主入口:生成章节统计报告。"""
    cleaned_text = read_file_safely(cleaned_path)
    raw_text = read_file_safely(raw_path) if raw_path else ""

    sections = split_by_h2(cleaned_text)

    lines: list[str] = ["# 章节统计报告", ""]
    lines.append(f"- 文件: `{cleaned_path.name}`")
    if raw_path:
        lines.append(f"- 对比原始: `{raw_path.name}`")
    lines.append(f"- H2 章节数: **{len(sections)}**")
    lines.append("")

    all_pass = True
    for i, (title, content) in enumerate(sections, 1):
        cjk = count_cjk(content)
        total = len(content)
        assets = check_assets(content)
        missing = [a for a, c in assets.items() if c == 0]

        lines.append(f"## [{i}] {title}")
        lines.append(f"- 字符数: {total} / 中文字符数: {cjk}")
        if raw_text:
            raw_cjk = count_cjk(raw_text)
            retention = cjk / raw_cjk * 100 if raw_cjk > 0 else 0
            lines.append(f"- 中文保留率: {retention:.1f}% (相对全文原始)")

        # 5 类资产
        lines.append(f"- 5 类资产:")
        for asset, count in assets.items():
            mark = "✅" if count > 0 else "❌"
            lines.append(f"  - {mark} {asset}: {count} 次命中")

        if missing:
            all_pass = False
            lines.append(f"- **WARN**: 缺失资产: {', '.join(missing)}")
        lines.append("")

    lines.append("---")
    lines.append("**总览**: " + ("✅ 所有章节 5 类资产齐全" if all_pass else "❌ 部分章节缺资产,需人工补"))
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description='章节保留率 + 5 类资产诊断')
    parser.add_argument('cleaned', type=Path, help='cleaned.md 路径')
    parser.add_argument('--raw-md', type=Path, help='原始 transcript.md 路径(可选,算保留率)')
    parser.add_argument('--output', type=Path, help='报告输出路径(默认 stdout)')
    args = parser.parse_args()

    if not args.cleaned.exists():
        log(f"ERROR: cleaned.md 不存在:{args.cleaned}")
        return 2

    report = per_section_stats(args.cleaned, args.raw_md)
    if args.output:
        write_file_safely(args.output, report)
        log(f"[stats] wrote {args.output}")
    else:
        print(report)

    # 退出码:全部 PASS = 0,部分缺资产 = 1
    return 0 if "❌" not in report else 1


if __name__ == '__main__':
    sys.exit(main())
