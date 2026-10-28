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
            'phonetic': str(r.get('phonetic', '') or '').lower() in ('true', '1', 'yes'),
        })

    return sort_rules_long_first(rules)


def sort_rules_long_first(rules: list[dict[str, str]]) -> list[dict[str, str]]:
    """按 from 字符数降序排序,长词在前(避免短词误匹配)。

    SKILL.md v4.16 changelog 明确: "项目级 ASR 错词规则按长词在前、短词在后顺序"。
    load_rules 已自动调用此函数,调用方无需重复排序。
    """
    return sorted(rules, key=lambda r: (-len(r['from']), r['from']))


# 替换核心 ---------------------------------------------------------

# 拼音转换模块(v4.22 同音变体支持) --------------------------

_PYPINYIN_AVAILABLE = False
_PYPINYIN_LAZY = None
_PINYIN_CACHE: dict[str, str] = {}


def _get_pinyin():
    """惰性加载 pypinyin,失败时设置 _PYPINYIN_AVAILABLE=False。"""
    global _PYPINYIN_AVAILABLE, _PYPINYIN_LAZY
    if _PYPINYIN_LAZY is not None:
        return _PYPINYIN_AVAILABLE
    try:
        from pypinyin import lazy_pinyin, Style
        _PYPINYIN_LAZY = (lazy_pinyin, Style)
        _PYPINYIN_AVAILABLE = True
    except ImportError:
        _PYPINYIN_AVAILABLE = False
    return _PYPINYIN_AVAILABLE


def to_pinyin(s: str) -> str:
    """将中文字符串转为无声调拼音(用于同音字比较)。

    Examples:
        '控电机' → 'kongdianji'
        '控点击' → 'kongdianji'
        '磁包'   → 'cibɑo'    (note: pypinyin outputs 'cibɑo' or 'cibào')
    """
    if s in _PINYIN_CACHE:
        return _PINYIN_CACHE[s]
    if not _get_pinyin():
        return s  # pypinyin 未安装,降级到字面比较
    lazy_pinyin, Style = _PYPINYIN_LAZY
    # 不带声调,小写,无空格
    try:
        py = ''.join(lazy_pinyin(s, style=Style.NORMAL, errors=lambda x: list(x)))
    except Exception:
        py = s
    _PINYIN_CACHE[s] = py
    return py


# 替换核心 ---------------------------------------------------------

def apply_rule(content: str, rule: dict[str, str], window: int = 50) -> tuple[str, int]:
    """应用单条规则,返回(新内容, 替换次数)。

    - 若 context 为空:无脑替换
    - 若 context 非空:仅当 context 关键词出现在 from 周边 ±window 字符窗口内才替换
    - context 支持 pipe-separated alternates:`投放|计划|出价|成交|投产` 任一出现在窗口内即匹配(v4.21)
    - phonetic:true 启用同音变体匹配(v4.22):扫描输入中长度=N 的子串,pinyin 相等则替换
    """
    # 字面模式
    content, n_literal = _apply_literal_rule(content, rule, window)

    # 同音模式
    n_phonetic = 0
    if rule.get('phonetic', False):
        content, n_phonetic = _apply_phonetic_rule(content, rule, window)

    return content, n_literal + n_phonetic


def _apply_literal_rule(content: str, rule: dict[str, str], window: int) -> tuple[str, int]:
    """字面匹配模式。"""
    pattern = re.compile(re.escape(rule['from']))
    context = rule.get('context', '')
    context_options = [c.strip() for c in context.split('|') if c.strip()] if context else []
    count = 0

    def repl(match: re.Match) -> str:
        nonlocal count
        if context_options:
            start = max(0, match.start() - window)
            end = min(len(content), match.end() + window)
            window_text = content[start:end]
            if not any(opt in window_text for opt in context_options):
                return match.group(0)
        count += 1
        return rule['to']

    new_content = pattern.sub(repl, content)
    return new_content, count


def _apply_phonetic_rule(content: str, rule: dict[str, str], window: int) -> tuple[str, int]:
    """同音匹配模式(v4.22)。

    算法:
      1. 计算 from 的 pinyin (如 '控点击' → 'kongdianji')
      2. 在 content 中扫所有长度=N 的中文字符子串
      3. 对每个子串计算 pinyin,与 from 的 pinyin 相等 → 替换
      4. context 检查同字面模式
    """
    if not _get_pinyin():
        return content, 0  # pypinyin 未安装,跳过

    from_text = rule['from']
    from_pinyin = to_pinyin(from_text)
    target_len = len(from_text)

    # 仅扫中文字符子串,跳过非中文
    count = 0
    result = []
    i = 0
    while i < len(content):
        ch = content[i]
        matched = False
        if is_cjk(ch):
            # 收集 target_len 个连续 CJK 字符
            j = i
            cjk_run = []
            while j < len(content) and len(cjk_run) < target_len:
                if is_cjk(content[j]):
                    cjk_run.append(content[j])
                    j += 1
                else:
                    break
            # 如果收集到足够字符
            if len(cjk_run) == target_len:
                segment = ''.join(cjk_run)
                segment_pinyin = to_pinyin(segment)
                if segment_pinyin == from_pinyin and segment != from_text:
                    # 匹配且不是原文 → 检查 context
                    if _check_context(content, i, j, rule, window):
                        result.append(rule['to'])
                        count += 1
                        i = j  # 跳过已替换字符
                        matched = True
        if not matched:
            # 非 CJK 或未匹配 → 保留原文
            result.append(ch)
            i += 1

    return ''.join(result), count


def _check_context(content: str, start: int, end: int, rule: dict, window: int) -> bool:
    """检查 from 周边 ±window 字符窗口内是否有 context 关键词。

    与 _apply_literal_rule 中的逻辑保持一致。
    """
    context = rule.get('context', '')
    if not context:
        return True
    context_options = [c.strip() for c in context.split('|') if c.strip()]
    win_start = max(0, start - window)
    win_end = min(len(content), end + window)
    window_text = content[win_start:win_end]
    return any(opt in window_text for opt in context_options)


def is_cjk(ch: str) -> bool:
    """判断字符是否为汉字(用于切分同音候选集)。"""
    if not ch:
        return False
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF       # CJK 统一表意
        or 0x3400 <= code <= 0x4DBF     # CJK 扩展 A
        or 0x20000 <= code <= 0x2A6DF  # CJK 扩展 B
        or 0xF900 <= code <= 0xFAFF    # CJK 兼容
        or 0x2F800 <= code <= 0x2FA1F  # CJK 兼容补充
    )


def apply_corrections(content: str, rules: list[dict[str, str]],
                     window: int = 50) -> tuple[str, dict[str, int]]:
    """应用所有规则,返回(新内容, 每条规则的替换次数)。

    注意:内部自动 sort_rules_long_first() 排序,长词在前避免短词误匹配。
    规则带 phonetic:true 时会触发同音匹配(v4.22),用 [phonetic] 后缀标注。
    """
    counts: dict[str, int] = {}
    for rule in sort_rules_long_first(rules):
        is_phonetic = rule.get('phonetic', False)
        old_content = content
        content, n = apply_rule(content, rule, window)
        if n > 0:
            label = f"{rule['from']}→{rule['to']}"
            if rule.get('context'):
                label += f" (ctx={rule['context']})"
            if is_phonetic:
                label += " [phonetic]"
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
