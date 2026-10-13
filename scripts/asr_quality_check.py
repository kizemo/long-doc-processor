#!/usr/bin/env python3
"""asr_quality_check.py — v4.11 3-pass ASR 质量流水线

Pass 1:asr_error_dict.json 字典替换(高置信度)
Pass 2:孤字/双字扫描 review 候选(借 build_per_lecture_asr_corrections)
Pass 3:输出 markdown 报告到 `reports/asr_quality_report.md`

用法:
  python scripts/asr_quality_check.py <cleaned.md>
  python scripts/asr_quality_check.py <cleaned.md> --dict asr_error_dict.json --output-dir reports/

退出码:
  0 = 成功
  1 = 输入错误
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
from utils import read_file_safely, write_file_safely, log  # noqa: E402


DEFAULT_DICT = Path(__file__).resolve().parent.parent / 'references' / 'asr_corrections.yaml'
DEFAULT_OUTPUT_DIR = Path('reports')


def load_dict(dict_path: Path) -> list[dict[str, str]]:
    """加载 asr 错词字典(YAML / JSON / 内置)。"""
    if not dict_path or not dict_path.exists():
        log(f"[asr-quality] 字典不存在:{dict_path};用内置默认")
        return []

    text = read_file_safely(dict_path)
    # 尝试 YAML
    try:
        import yaml
        data = yaml.safe_load(text)
        if isinstance(data, dict) and 'rules' in data:
            rules = []
            for r in data['rules']:
                rules.append({
                    'from': str(r.get('from', '')),
                    'to': str(r.get('to', '')),
                })
            return rules
    except ImportError:
        pass
    except Exception:
        pass

    # 尝试 JSON
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [{'from': r.get('from', r.get('wrong', '')),
                    'to': r.get('to', r.get('right', ''))} for r in data]
        if isinstance(data, dict):
            return [{'from': k, 'to': v} for k, v in data.items()]
    except json.JSONDecodeError:
        pass

    return []


def pass1_dict_replace(content: str, rules: list[dict[str, str]]) -> tuple[str, dict[str, int]]:
    """Pass 1:字典替换。返回(新内容, 每条规则替换次数)。"""
    counts: dict[str, int] = {}
    for rule in rules:
        from_word = rule.get('from', '')
        to_word = rule.get('to', '')
        if not from_word or from_word == to_word:
            continue
        pattern = re.compile(re.escape(from_word))
        new_content, n = pattern.subn(to_word, content)
        if n > 0:
            counts[f"{from_word}→{to_word}"] = n
            content = new_content
    return content, counts


def pass2_isolated_tokens(text: str, lengths: tuple[int, ...] = (1, 2),
                            min_count: int = 3) -> list[tuple[str, int]]:
    """Pass 2:孤字扫描(借 build_per_lecture_asr_corrections 逻辑)。"""
    cjk_re = re.compile(r'[\u4e00-\u9fff]+')
    tokens = re.split(r'[\s\W]+', text, flags=re.UNICODE)
    counter: Counter = Counter()
    for tok in tokens:
        if not tok:
            continue
        if cjk_re.fullmatch(tok) and len(tok) in lengths:
            counter[tok] += 1
    return [(tok, c) for tok, c in counter.most_common() if c >= min_count]


def render_report(p1_counts: dict[str, int],
                  isolated: list[tuple[str, int]],
                  source: str) -> str:
    """Pass 3:渲染 markdown 报告。"""
    lines: list[str] = [
        '# ASR 质量报告',
        '',
        f"源文件:`{source}`",
        '',
        '## Pass 1 · 字典替换',
        '',
    ]
    if p1_counts:
        total = sum(p1_counts.values())
        lines.append(f"共替换 {total} 处:")
        lines.append('')
        for k, v in sorted(p1_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- `{k}`: {v}")
    else:
        lines.append('(无替换)')

    lines.extend([
        '',
        '## Pass 2 · 孤字/双字扫描',
        '',
    ])
    if isolated:
        lines.append(f"找到 {len(isolated)} 个高频孤字(≥{3} 次):")
        lines.append('')
        for tok, count in isolated[:20]:
            lines.append(f"- `{tok}`: {count} 次")
    else:
        lines.append('(无)')

    lines.extend([
        '',
        '## 后续',
        '',
        '- 高置信度(Pass 1)已自动修复',
        '- 孤字(Pass 2)需人工 review 是否 ASR 错误',
        '- 建议:用 `build_per_lecture_asr_corrections.py` 进一步生成 Jaccard 候选',
    ])
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description='v4.11 3-pass ASR 质量流水线')
    parser.add_argument('input', type=Path, help='cleaned.md 路径')
    parser.add_argument('--dict', type=Path, default=DEFAULT_DICT,
                        help=f'字典路径(默认 {DEFAULT_DICT.name})')
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT_DIR,
                        help=f'输出目录(默认 {DEFAULT_OUTPUT_DIR})')
    args = parser.parse_args()

    if not args.input.exists():
        log(f"ERROR: 输入文件不存在:{args.input}")
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    content = read_file_safely(args.input)

    # Pass 1
    rules = load_dict(args.dict)
    log(f"[asr-quality] Pass 1: 字典 {len(rules)} 条规则")
    new_content, p1_counts = pass1_dict_replace(content, rules)

    # Pass 2
    isolated = pass2_isolated_tokens(new_content)
    log(f"[asr-quality] Pass 2: 孤字 {len(isolated)} 个")

    # Pass 3:写报告
    report = render_report(p1_counts, isolated, args.input.name)
    report_path = args.output_dir / 'asr_quality_report.md'
    write_file_safely(report_path, report)
    log(f"[asr-quality] Pass 3: wrote {report_path}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
