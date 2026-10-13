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


# 已知污染词(v4.12 changelog 案例 + v4.21 B2 扩到 41 条)
# 来源:references/asr_corrections.yaml 41 条 ASR 易错词(同源数据)
# 这些词在 ASR 输出后 _post_terms_fix 应已替换为 to;
# 残留 = 上一步漏掉,需手动 Edit 修复。
CORRUPTION_TOKENS = [
    # v4.12 原 3 条
    '医疗器械标签',  # 鬼脚七线下课 '|' → '医疗器械标签' 表格污染
    '同价位',        # 同 product 同价位
    '店铺绩效',
    # v4.21 B2 新增 38 条(从 asr_corrections.yaml 41 条取,排除 GGC/AI助力 等英文)
    # 长词(4-7 字)
    '皮气护理', '最大化作间法', '相产品均头', '相产品国际',
    '建国资产', '数据筛毯', '气氛需求', '收获人数', '识别确论',
    # 中词(3 字)
    '心中式', '带梦图', '牛仔库', '推广课', '加入段', '加密货币',
    '石木床', '掀车', '摩特图', '演书服', '桌教店', '主视图',
    '高科赞', '点击力', '空投产', '空点机',
    # 短词(2 字)
    '权占', '点几率', '汉堡国', '心客', '打笔', '放弹', '蒸柔',
    '继程', '燃品', '主途', '复构', '解论', '内幕',
    # 英文 / 特殊
    '打爆',  # 同店语境
    'AI助力',  # 缺空格
    'GGC',  # ASR 把 GGV 听成 GGC
]
# handoff B2 目标 ≥ 30 污染词;实际 44 条(v4.12 原 3 + asr_corrections.yaml 41)
assert len(CORRUPTION_TOKENS) >= 30, f"期望 ≥ 30 条,实际 {len(CORRUPTION_TOKENS)}"


# 段首/段末孤立词(M-11 衍生,NO-ORPHAN-WORDS 模式)
# ASR 转录中常见的"好/对/那个/对吧/是吧"段首/段末填充词
# 单独成段(段长 < 阈值) → 视为孤立,应被 Phase 1.7 LLM 删除
ORPHAN_WORD_TOKENS = [
    '好', '对', '那个', '对吧', '是吧', '嗯', '啊', '哦', '呢', '这个', '然后',
]
ORPHAN_PARAGRAPH_MAX_LEN = 20  # 孤立段长度阈值(纯孤立词 + 标点)


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
    """检测表格列数不均匀。

    v4.21 B2 修正:列数算法 `line.count('|') - 1`(去除两侧边界 `|`),
    原算法用 `line.count('|')` 多计 1 列,导致边界表格误判。
    """
    issues: list[str] = []
    for start_line, table_lines in tables:
        # B2 修正:列数 = 总 `|` 数 - 1(两侧边界)
        col_counts = [max(0, line.count('|') - 1) for line in table_lines]
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
    """检测已知污染词残留(41 条 CORRUPTION_TOKENS)。"""
    issues: list[str] = []
    for token in CORRUPTION_TOKENS:
        if token in text:
            issues.append(f"检测到污染词:{token!r}")
    return issues


def check_no_orphan_words(text: str) -> list[str]:
    """NO-ORPHAN-WORDS 模式(M-11 衍生,规约 26):段首/段末孤立无语义词组。

    算法:按段落(连续非空行)切分,检查每段是否只由 ORPHAN_WORD_TOKENS + 标点组成
    且段长 ≤ ORPHAN_PARAGRAPH_MAX_LEN(20 字符)。
    命中 → 报告"孤立段",供 Phase 1.7 LLM 删除。
    """
    issues: list[str] = []
    lines = text.splitlines()
    para_start = 0
    in_para = False
    for i, line in enumerate(lines):
        if line.strip():
            if not in_para:
                para_start = i
                in_para = True
        else:
            if in_para:
                # 段结束,检查
                para_text = '\n'.join(lines[para_start:i]).strip()
                _check_orphan_para(para_text, para_start + 1, issues)
                in_para = False
    # 文档末尾段
    if in_para:
        para_text = '\n'.join(lines[para_start:]).strip()
        _check_orphan_para(para_text, para_start + 1, issues)
    return issues


def _check_orphan_para(para: str, line_no: int, issues: list[str]) -> None:
    """检查单段是否孤立词段。"""
    if len(para) > ORPHAN_PARAGRAPH_MAX_LEN:
        return
    # 去掉标点
    cleaned = re.sub(r'[^\w\s]', '', para).strip()
    if not cleaned:
        return
    # 检查是否只由孤立词 + 标点组成
    words = cleaned.split()
    if not words:
        return
    all_orphan = all(w in ORPHAN_WORD_TOKENS for w in words)
    if all_orphan:
        issues.append(
            f"孤立段(line {line_no}):{para[:40]!r} 仅由段首/段末填充词组成"
        )


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
    all_issues.extend(check_no_orphan_words(text))
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
