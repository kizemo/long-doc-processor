#!/usr/bin/env python3
"""_post_terms_fix.py — skill 标准 ASR 错词修复工具(v4.16 沉淀,2026-10-12 补齐)

数据驱动 + 自动发现配置:
  1. CWD 下的 asr_corrections.yaml            (项目级,最高优先级)
  2. CWD/output/test-crv2/asr_corrections.yaml (蒋太帅 / 智篆 / 老草等 v4.6+ 项目约定)
  3. skill 内置 references/asr_corrections.yaml (兜底,~39 条)

用法:
  # 默认(无项目配置):直接跑使用 skill 内置默认
  python scripts/_post_terms_fix.py <input.md> <output.md>

  # 指定配置
  python scripts/_post_terms_fix.py <input.md> <output.md> --config my-rules.yaml

  # 自检(加载默认 + 跑 dry-run sample)
  python scripts/_post_terms_fix.py --selftest

设计要点(SKILL.md v4.16 changelog):
  - 排序:按 from 字符数降序,长词在前词在前、短词在后(避免短词误匹配)
  - 上下文:可选 context 字段,替换前必须出现在 from 的 ±50 字符窗口内
  - LLM 是错词放大器:本工具必须在 LLM 净化**之前**跑
  - 必须先于 _purify_smooth 跑(同条 Gotcha)

退出码:
  0 = 成功
  1 = 文件读写错误
  2 = 配置错误
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# scripts/ 同级 utils.py 复用
sys.path.insert(0, str(Path(__file__).parent))
from utils import read_file_safely, write_file_safely, log  # noqa: E402


# 路径解析 ---------------------------------------------------------

def get_skill_root() -> Path:
    """返回 skill 安装根目录(scripts/_post_terms_fix.py -> skill 根)"""
    return Path(__file__).resolve().parent.parent


def find_config_path(cwd: Path, explicit: Path | None = None) -> tuple[Path, str]:
    """自动发现 ASR 错词配置文件。

    优先级:explicit > CWD > CWD/output/test-crv2 > skill 内置

    Returns:
        (config_path, source_label) where source_label ∈
        {"explicit", "cwd", "test-crv2", "builtin"}
    """
    builtin = get_skill_root() / 'references' / 'asr_corrections.yaml'

    if explicit:
        if not explicit.exists():
            raise FileNotFoundError(f"--config 指定的文件不存在: {explicit}")
        return explicit, "explicit"

    candidates = [
        (cwd / 'asr_corrections.yaml', "cwd"),
        (cwd / 'output' / 'test-crv2' / 'asr_corrections.yaml', "test-crv2"),
        (builtin, "builtin"),
    ]
    for path, label in candidates:
        if path.exists():
            return path, label

    # builtin 必须存在(否则 skill 不完整),如真缺失兜底抛错
    raise FileNotFoundError(
        f"找不到任何 ASR 错词配置;skill 内置 {builtin} 也缺失。"
        f"请检查 references/asr_corrections.yaml 是否丢失。"
    )


# 配置加载 ---------------------------------------------------------

def load_rules(config_path: Path) -> list[dict[str, str]]:
    """加载 YAML 配置,提取 rules 列表。

    校验每条规则至少含 from + to,context 缺失视为空字符串(无 context 限制)。
    """
    try:
        import yaml
    except ImportError as e:
        raise RuntimeError("PyYAML 未安装;pip install pyyaml") from e

    text = read_file_safely(config_path)
    data = yaml.safe_load(text) or {}
    rules_raw = data.get('rules', [])
    if not isinstance(rules_raw, list):
        raise ValueError(f"配置文件 {config_path} 的 'rules' 字段不是列表")

    rules: list[dict[str, str]] = []
    for i, r in enumerate(rules_raw):
        if not isinstance(r, dict):
            raise ValueError(f"配置 {config_path} 第 {i+1} 条不是 dict: {r!r}")
        if 'from' not in r or 'to' not in r:
            raise ValueError(f"配置 {config_path} 第 {i+1} 条缺少 from/to: {r!r}")
        rules.append({
            'from': str(r['from']),
            'to': str(r['to']),
            'context': str(r.get('context', '') or ''),
        })

    return rules


def sort_rules_long_first(rules: list[dict[str, str]]) -> list[dict[str, str]]:
    """按 from 字符数降序排序,长词在前(避免短词误匹配)。

    SKILL.md v4.16 changelog 明确: "项目级 ASR 错词规则按长词在前、短词在后顺序"。
    """
    return sorted(rules, key=lambda r: (-len(r['from']), r['from']))


# 替换核心 ---------------------------------------------------------

def apply_rule(content: str, rule: dict[str, str], window: int = 50) -> tuple[str, int]:
    """应用单条规则,返回(新内容, 替换次数)。

    - 若 context 为空:无脑替换
    - 若 context 非空:仅当 context 关键词出现在 from 周边 ±window 字符窗口内才替换
    """
    pattern = re.compile(re.escape(rule['from']))
    context = rule['context']
    count = 0

    def repl(match: re.Match) -> str:
        nonlocal count
        if context:
            start = max(0, match.start() - window)
            end = min(len(content), match.end() + window)
            if context not in content[start:end]:
                return match.group(0)  # 跳过
        count += 1
        return rule['to']

    new_content = pattern.sub(repl, content)
    return new_content, count


def apply_corrections(content: str, rules: list[dict[str, str]],
                     window: int = 50) -> tuple[str, dict[str, int]]:
    """应用所有规则,返回(新内容, 每条规则的替换次数)。"""
    counts: dict[str, int] = {}
    for rule in rules:
        content, n = apply_rule(content, rule, window)
        if n > 0:
            label = f"{rule['from']}→{rule['to']}"
            if rule['context']:
                label += f" (ctx={rule['context']})"
            counts[label] = n
    return content, counts


# 文件级包装 -------------------------------------------------------

def post_terms_fix_file(input_path: Path, output_path: Path,
                        config_path: Path | None = None) -> dict[str, int]:
    """对单个 md 文件做 ASR 错词修复。

    Returns: 每条规则的替换次数
    """
    cwd = Path.cwd()
    cfg_path, source = find_config_path(cwd, config_path)
    log(f"[post-terms-fix] config: {cfg_path} (source={source})")

    rules = load_rules(cfg_path)
    rules = sort_rules_long_first(rules)
    log(f"[post-terms-fix] loaded {len(rules)} rules (sorted long-first)")

    content = read_file_safely(input_path)
    new_content, counts = apply_corrections(content, rules)

    write_file_safely(output_path, new_content)
    log(f"[post-terms-fix] wrote {output_path}")
    total = sum(counts.values())
    log(f"[post-terms-fix] total replacements: {total} (across {len(counts)} rules)")

    return counts


# 自检 ------------------------------------------------------------

SELFTEST_SAMPLE = """
讲师介绍了皮气护理的重要性,牛仔库也是今年流行趋势。
权占数据看,GMV 提升 30%。掀车策略在双 11 应用很广。
摩特图点击率提升到 5%。演书服季节性销售达 100 万。
主视图对转化影响巨大,推广课学员反馈很好。
气氛需求是核心,加入段决定展示效果。
心客转化率比老客高。同店打爆产品是大忌。
GGC 模型错误,改为 GGV 重新评估。AI助力效果显著。
"""


def selftest() -> int:
    """自检:用一段含 ~12 条已知错词的样本验证默认规则全部命中。

    Returns: 0 = 通过, 1 = 失败
    """
    log("=== _post_terms_fix.py 自检 ===")

    # 1. 加载默认配置
    try:
        cfg_path, _ = find_config_path(Path.cwd())
        rules = load_rules(cfg_path)
        rules = sort_rules_long_first(rules)
        log(f"加载默认配置 OK: {len(rules)} rules (source=builtin)")
    except Exception as e:
        log(f"FAIL 加载默认配置: {e}")
        return 1

    # 2. 应用到 SELFTEST_SAMPLE
    fixed, counts = apply_corrections(SELFTEST_SAMPLE, rules)
    log(f"样本替换统计: {counts}")

    # 3. 验证已知错词全部修正
    expected_fixed_substrings = [
        ("皮质护理", "皮气护理"),
        ("牛仔裤", "牛仔库"),
        ("全站", "权占"),
        ("四轮推车", "掀车"),
        ("模特图", "摩特图"),
        ("演出服", "演书服"),
        ("客户需求", "气氛需求"),
        ("价格段", "加入段"),
        ("新客", "心客"),
        ("GGV", "GGC"),
        ("AI 助力", "AI助力"),
        ("打散", "打爆"),  # 同店
    ]
    failed: list[str] = []
    for correct, wrong in expected_fixed_substrings:
        if correct not in fixed:
            failed.append(f"  - {wrong} → {correct} 未命中")
        if wrong in fixed and "心客" not in wrong and "打爆" not in wrong:
            # 心客/打爆 在没有 context 时不应替换(其他上下文不应误伤)
            failed.append(f"  - {wrong} 仍残留(可能误伤)")

    if failed:
        log("FAIL 自检:")
        for line in failed:
            log(line)
        return 1

    log(f"PASS 自检: {len(expected_fixed_substrings)} 条已知错词全部修正")
    return 0


# CLI 入口 ---------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='skill 标准 ASR 错词修复工具 (v4.16 沉淀)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('input', nargs='?', help='输入 md 文件路径')
    parser.add_argument('output', nargs='?', help='输出 md 文件路径')
    parser.add_argument('--config', type=Path, help='指定 YAML 配置路径(覆盖自动发现)')
    parser.add_argument('--selftest', action='store_true', help='自检模式')

    args = parser.parse_args()

    if args.selftest:
        return selftest()

    if not args.input or not args.output:
        parser.error("需要 <input> <output>,或用 --selftest")

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    if not input_path.exists():
        log(f"ERROR: 输入文件不存在: {input_path}")
        return 1

    try:
        post_terms_fix_file(input_path, output_path, args.config)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        log(f"ERROR: {e}")
        return 2
    except Exception as e:
        log(f"ERROR: 意外错误: {e}")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
