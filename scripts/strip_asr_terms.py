#!/usr/bin/env python3
"""strip_asr_terms.py — ASR-TERM-FIX / TERM-OK 规约实现(rule-based)

简化版 ASR 错词字典替换:基于内置默认 30 条 ASR 易错映射(高频电商术语),
规则顺序:长词在前、短词在后(避免短词误匹配)。

与 _post_terms_fix.py 的差异:
  - _post_terms_fix:基于 YAML 数据驱动配置(可外部覆盖)+ 上下文检查
  - strip_asr_terms:内置默认规则(无 YAML)+ 无上下文(快速)

用法:
  python scripts/strip_asr_terms.py <input.md> -o <output.md>
  python scripts/strip_asr_terms.py <input.md> -o <output.md> --dry-run

退出码:
  0 = 成功
  1 = 输入错误
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


# 内置默认 ASR 易错映射(v4.11 changelog 沉淀 + 高频电商术语)
# 长词在前(运行时 sort)
DEFAULT_RULES: list[dict[str, str]] = [
    {'from': '皮气护理',     'to': '皮质护理'},
    {'from': '心中式',       'to': '新中式'},
    {'from': '带梦图',       'to': '带门图'},
    {'from': '牛仔库',       'to': '牛仔裤'},
    {'from': '最大化作间法', 'to': '最大化筛选法'},
    {'from': '气氛需求',     'to': '客户需求'},
    {'from': '推广课',       'to': '推广课程'},
    {'from': '数据筛毯',     'to': '数据筛选'},
    {'from': '收到人数',     'to': '收货人数'},
    {'from': '摩特图',       'to': '模特图'},
    {'from': '演书服',       'to': '演出服'},
    {'from': '掀车',         'to': '四轮推车'},
    {'from': '石木床',       'to': '实木床'},
    {'from': '主视图',       'to': '主图'},
    {'from': '点击力',       'to': '点击率'},
    {'from': '高科赞',       'to': '高客单'},
    {'from': '点几率',       'to': '点击率'},
    {'from': '权占',         'to': '全站'},
    {'from': '空投产',       'to': '控投产'},
    {'from': '空点机',       'to': '控点机'},
    {'from': '汉堡国',       'to': '汉堡包'},
    {'from': '心客',         'to': '新客'},
    {'from': '打笔',         'to': '打比'},
    {'from': '放弹',         'to': '放量'},
    {'from': '蒸柔',         'to': '蒸馏'},
    {'from': '继程',         'to': '决策'},
    {'from': '燃品',         'to': '产品'},
    {'from': '主途',         'to': '主图'},
    {'from': '复构',         'to': '复购'},
    {'from': '解论',         'to': '结论'},
    {'from': '内幕',         'to': '类目'},
    {'from': 'GGC',          'to': 'GGV'},
]


def sort_long_first(rules: list[dict[str, str]]) -> list[dict[str, str]]:
    """按 from 字符数降序,长词在前。"""
    return sorted(rules, key=lambda r: (-len(r['from']), r['from']))


def apply_rules(content: str, rules: list[dict[str, str]]) -> tuple[str, dict[str, int]]:
    """应用全部规则,返回(新内容, 每条规则替换次数)。

    跳过 from == to 的 self-mapping 规则(Python re.subn 会报告 1 次替换但内容不变)。
    """
    counts: dict[str, int] = {}
    for rule in rules:
        # 跳过 self-mapping(re.subn 会报告 1 但内容不变)
        if rule['from'] == rule['to']:
            continue
        pattern = re.compile(re.escape(rule['from']))
        new_content, n = pattern.subn(rule['to'], content)
        if n > 0:
            counts[f"{rule['from']}→{rule['to']}"] = n
        content = new_content
    return content, counts


def strip_asr_terms(input_path: Path, output_path: Path,
                     rules: list[dict[str, str]] | None = None,
                     dry_run: bool = False) -> dict[str, int]:
    """主入口:读 md → 应用规则 → 写输出。"""
    if rules is None:
        rules = DEFAULT_RULES
    rules = sort_long_first(rules)
    log(f"[strip-asr] 加载 {len(rules)} 条规则")

    content = read_file_safely(input_path)
    new_content, counts = apply_rules(content, rules)

    if dry_run:
        total = sum(counts.values())
        log(f"[strip-asr] dry-run: 预计 {total} 处替换")
        for k, v in counts.items():
            log(f"  - {k}: {v}")
        return counts

    write_file_safely(output_path, new_content)
    total = sum(counts.values())
    log(f"[strip-asr] wrote {output_path}, {total} 处替换")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description='ASR-TERM-FIX 规约(rule-based)')
    parser.add_argument('input', type=Path, help='输入 md 路径')
    parser.add_argument('-o', '--output', type=Path, required=True, help='输出 md 路径')
    parser.add_argument('--dry-run', action='store_true', help='只检查不写')
    args = parser.parse_args()

    if not args.input.exists():
        log(f"ERROR: 输入文件不存在:{args.input}")
        return 1

    strip_asr_terms(args.input, args.output, dry_run=args.dry_run)
    return 0


if __name__ == '__main__':
    sys.exit(main())
