#!/usr/bin/env python3
"""fix_bad_extract_terms_inline.py — v4.12 asr_terms.json 自动清理

清理 asr_terms.json 中的 garbage 条目(误把 markdown structural chars 当作 ASR 错词)。
属于 v4.12 表格污染修复防线(`validate_terms.py` 自动调用)。

清理规则:
  1. _is_pure_punctuation: from 或 to 仅由 markdown structural chars / 空白组成
  2. _is_dangerous_wrong_token: from 含 `|` / `#` / `>` / `` ` `` / `~` 等 markdown structural
  3. _is_too_short: from < 2 字符(过短易误匹配)
  4. _is_numeric_only: from 纯数字

用法:
  python scripts/fix_bad_extract_terms_inline.py <asr_terms.json>
  python scripts/fix_bad_extract_terms_inline.py <asr_terms.json> --dry-run  # 只检查不写

退出码:
  0 = 清理完成(或无需清理)
  1 = 清理后仍有问题
  2 = 输入错误
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
from utils import read_file_safely, write_file_safely, log  # noqa: E402


# markdown structural chars (v4.12 案例)
_MARKDOWN_STRUCTURAL = set('|`#><-_+~!\\')


def _is_pure_punctuation(s: str) -> bool:
    """from 或 to 仅由空白或 markdown structural chars 组成。"""
    if not s.strip():
        return True
    return all(c in _MARKDOWN_STRUCTURAL or c.isspace() for c in s)


def _is_dangerous_wrong_token(s: str) -> bool:
    """from 含 markdown structural char(误把 `|` 当作 ASR 错词)。"""
    return any(c in _MARKDOWN_STRUCTURAL for c in s)


def _is_too_short(s: str, min_len: int = 2) -> bool:
    """from < min_len 字符,过短易误匹配。"""
    return len(s) < min_len


def _is_numeric_only(s: str) -> bool:
    """from 纯数字。"""
    return bool(re.fullmatch(r'\d+', s))


def _is_self_mapping(rule: dict) -> bool:
    """from == to(无效规则)。"""
    return rule.get('from') == rule.get('to')


def is_garbage_rule(rule: dict) -> tuple[bool, str]:
    """判断单条规则是否 garbage,返回 (是否垃圾, 原因)。

    检查顺序:specific 在前(精确诊断),general 在后(兜底)。
    """
    if not isinstance(rule, dict):
        return True, "规则不是 dict"

    from_word = str(rule.get('from', ''))
    to_word = str(rule.get('to', ''))

    if not from_word:
        return True, "缺少 from"
    if not to_word:
        return True, "缺少 to"

    # specific 检查先于 general
    if _is_pure_punctuation(from_word):
        return True, f"from 仅由 markdown 符号/空白组成:{from_word!r}"
    if _is_pure_punctuation(to_word):
        return True, f"to 仅由 markdown 符号/空白组成:{to_word!r}"
    if _is_dangerous_wrong_token(from_word):
        return True, f"from 含 markdown structural char:{from_word!r}"
    if _is_self_mapping(rule):
        return True, f"from == to:{from_word!r}"
    if _is_numeric_only(from_word):
        return True, f"from 纯数字:{from_word!r}"
    if _is_too_short(from_word):
        return True, f"from 过短({len(from_word)} < 2):{from_word!r}"

    return False, ""


def clean_terms(input_path: Path, output_path: Path | None = None) -> tuple[int, list[str]]:
    """清理 asr_terms.json,返回 (清理条数, 原因列表)。"""
    if output_path is None:
        output_path = input_path

    text = read_file_safely(input_path)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        log(f"ERROR: JSON 解析失败:{e}")
        return 0, []

    rules = data.get('rules', [])
    if not isinstance(rules, list):
        log("ERROR: 'rules' 字段不是列表")
        return 0, []

    cleaned: list[dict] = []
    removed_reasons: list[str] = []
    for rule in rules:
        is_garbage, reason = is_garbage_rule(rule)
        if is_garbage:
            removed_reasons.append(reason)
            continue
        cleaned.append(rule)

    removed_count = len(rules) - len(cleaned)
    if removed_count > 0:
        data['rules'] = cleaned
        write_file_safely(output_path, json.dumps(data, ensure_ascii=False, indent=2))
        log(f"[fix-bad] 清理 {removed_count} 条 garbage,剩余 {len(cleaned)} 条")
    else:
        log(f"[fix-bad] 无 garbage,保持 {len(cleaned)} 条")

    return removed_count, removed_reasons


def main() -> int:
    parser = argparse.ArgumentParser(description='v4.12 asr_terms.json garbage 清理')
    parser.add_argument('input', type=Path, help='输入 asr_terms.json 路径')
    parser.add_argument('-o', '--output', type=Path, help='输出路径(默认覆盖 input)')
    parser.add_argument('--dry-run', action='store_true', help='只检查不写')
    args = parser.parse_args()

    if not args.input.exists():
        log(f"ERROR: 输入文件不存在:{args.input}")
        return 2

    if args.dry_run:
        text = read_file_safely(args.input)
        data = json.loads(text)
        rules = data.get('rules', [])
        garbage_count = sum(1 for r in rules if is_garbage_rule(r)[0])
        log(f"[fix-bad] dry-run: 总 {len(rules)} 条,garbage {garbage_count} 条")
        for rule in rules:
            is_g, reason = is_garbage_rule(rule)
            if is_g:
                log(f"  - {rule.get('from')!r} → {rule.get('to')!r}: {reason}")
        return 0

    removed, reasons = clean_terms(args.input, args.output)
    if removed > 0:
        log(f"[fix-bad] 清理了 {removed} 条:")
        for r in reasons[:10]:
            log(f"  - {r}")
        if len(reasons) > 10:
            log(f"  ... and {len(reasons) - 10} more")
    return 0 if removed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
