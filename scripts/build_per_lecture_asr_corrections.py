#!/usr/bin/env python3
"""build_per_lecture_asr_corrections.py — v4.11 扫孤字 + Jaccard 相似度候选

扫 cleaned.md(单讲义)的孤字(1 字 / 2 字)和高相似度候选,生成人工 review 报告。

用法:
  python scripts/build_per_lecture_asr_corrections.py <cleaned.md> --output-dir reports/
  python scripts/build_per_lecture_asr_corrections.py <cleaned.md> --output-dir reports/ --dict asr_error_dict.json

输出:
  reports/asr_corrections_candidates.md  ← 人工可读
  reports/asr_corrections_candidates.json ← 程序可读

退出码:
  0 = 成功
  1 = 输入错误
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
from utils import read_file_safely, log  # noqa: E402


# 默认 Jaccard 阈值(相似度 ≥ 0.5 才列入候选)
DEFAULT_JACCARD_THRESHOLD = 0.5

# 孤字长度阈值(1 字 / 2 字)
ISOLATED_LENGTHS = (1, 2)

# 中文字符正则
_CJK_RE = re.compile(r'[\u4e00-\u9fff]')


def jaccard_similarity(a: str, b: str) -> float:
    """Jaccard 字形相似度 = |A ∩ B| / |A ∪ B|。

    A, B 是字符集合(2-gram 也可,但字符集对中文 ASR 错词更直观)。
    """
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def find_isolated_tokens(text: str, lengths: tuple[int, ...] = ISOLATED_LENGTHS,
                          min_count: int = 3) -> list[tuple[str, int]]:
    """扫所有孤字(1 字 / 2 字),返回 [(token, count), ...],count ≥ min_count。

    孤字定义:被标点 / 空白 / markdown 边界切出的独立 token,
    且 token 的 CJK 字符长度 ∈ lengths。

    实现:用 ASCII 非字母数字字符做 split,过滤出 CJK-only 的 token。
    """
    from collections import Counter

    # 用 ASCII 标点 / 空白 / markdown 符号切分
    # 保留 CJK 字符作为 token
    tokens = re.split(r'[\s\W]+', text, flags=re.UNICODE)
    # 过滤:仅保留纯 CJK(可能有数字 + CJK 混合,简单过滤非纯 CJK)
    cjk_re = re.compile(r'^[\u4e00-\u9fff]+$')
    counter = Counter()
    for tok in tokens:
        if not tok:
            continue
        if cjk_re.match(tok) and len(tok) in lengths:
            counter[tok] += 1

    return [(tok, count) for tok, count in counter.most_common()
            if count >= min_count]


def load_error_dict(dict_path: Path | None) -> list[dict[str, str]]:
    """加载 asr_error_dict.json,失败时返回空列表。"""
    if not dict_path or not dict_path.exists():
        return []
    try:
        data = json.loads(read_file_safely(dict_path))
        # 支持两种格式:[{wrong, right}, ...] 或 {wrong: right, ...}
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [{'wrong': w, 'right': r} for w, r in data.items()]
    except json.JSONDecodeError:
        pass
    return []


def match_candidates(isolated: list[tuple[str, int]],
                     error_dict: list[dict[str, str]],
                     threshold: float = DEFAULT_JACCARD_THRESHOLD
                     ) -> list[dict]:
    """对每个孤字,找 Jaccard 相似度 ≥ threshold 的候选。

    Returns: [{'isolated': 'word', 'count': N, 'candidates': [{'right': '...', 'sim': 0.8}, ...]}, ...]
    """
    results: list[dict] = []
    for tok, count in isolated:
        candidates: list[dict] = []
        for entry in error_dict:
            right = entry.get('right', '')
            if not right:
                continue
            sim = jaccard_similarity(tok, right)
            if sim >= threshold:
                candidates.append({'right': right, 'sim': round(sim, 3)})
        candidates.sort(key=lambda x: x['sim'], reverse=True)
        if candidates:
            results.append({
                'isolated': tok,
                'count': count,
                'candidates': candidates[:5],  # 取 top 5
            })
    return results


def render_report(candidates: list[dict], source_md: str) -> str:
    """生成人工可读 report (markdown)。"""
    lines: list[str] = ['# ASR 错词候选 review 报告', '']
    lines.append(f"源文件:`{source_md}`")
    lines.append(f"候选数:{len(candidates)}")
    lines.append('')
    lines.append('## 候选列表')
    lines.append('')
    if not candidates:
        lines.append('(无候选 — 孤字与 asr_error_dict 相似度均 < 阈值)')
        return '\n'.join(lines)

    lines.append('| 孤字 | 出现次数 | Top 候选 (Jaccard 相似度) |')
    lines.append('|---|---|---|')
    for c in candidates:
        cand_str = ', '.join(
            f"`{x['right']}` ({x['sim']})"
            for x in c['candidates']
        )
        lines.append(f"| `{c['isolated']}` | {c['count']} | {cand_str} |")
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='v4.11 扫孤字 + Jaccard 相似度候选',
    )
    parser.add_argument('input', type=Path, help='cleaned.md 路径')
    parser.add_argument('--output-dir', type=Path, default=Path('reports'),
                        help='输出目录(默认 reports/)')
    parser.add_argument('--dict', type=Path, help='asr_error_dict.json 路径(可选)')
    parser.add_argument('--threshold', type=float, default=DEFAULT_JACCARD_THRESHOLD,
                        help=f'Jaccard 阈值(默认 {DEFAULT_JACCARD_THRESHOLD})')
    args = parser.parse_args()

    if not args.input.exists():
        log(f"ERROR: 输入文件不存在:{args.input}")
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)

    text = read_file_safely(args.input)
    isolated = find_isolated_tokens(text)
    log(f"[corrections] 找到 {len(isolated)} 个孤字(1-2 字,出现 ≥3 次)")

    error_dict = load_error_dict(args.dict)
    log(f"[corrections] 加载 asr_error_dict: {len(error_dict)} 条")

    candidates = match_candidates(isolated, error_dict, args.threshold)
    log(f"[corrections] 候选:{len(candidates)} 个孤字匹配")

    # 写 md report
    md_report = render_report(candidates, args.input.name)
    md_path = args.output_dir / 'asr_corrections_candidates.md'
    md_path.write_text(md_report, encoding='utf-8')
    log(f"[corrections] wrote {md_path}")

    # 写 json report
    json_report = {
        'source': str(args.input),
        'threshold': args.threshold,
        'isolated_count': len(isolated),
        'candidates': candidates,
    }
    json_path = args.output_dir / 'asr_corrections_candidates.json'
    json_path.write_text(json.dumps(json_report, ensure_ascii=False, indent=2),
                          encoding='utf-8')
    log(f"[corrections] wrote {json_path}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
