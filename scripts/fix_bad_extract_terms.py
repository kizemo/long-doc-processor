#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_bad_extract_terms.py — 一次性清理 asr_terms.json 中 extract_terms.py 错误产生的空/符号型 wrong 条目。

背景:
- extract_terms.py 解析 markdown 表格时，把 '|' (空 cell) 错误识别为 wrong 词
- 导致 strip_asr_terms.py 跑 doc.replace('|', '医疗器械标签') 把整个文档的 | 都污染
- 现象:cleaned.md 中每张表格都变成 "医疗器械标签 单元格..."
"""
import json
import sys
from pathlib import Path

ASR_TERMS = Path(__file__).parent / "asr_terms.json"


def main():
    with ASR_TERMS.open(encoding='utf-8') as f:
        d = json.load(f)

    bad_set = {'|', ',', '/', '\\', '。', '、', ' ', '+', '=', '-', '*', '(', ')', '[', ']'}

    def is_bad(e: dict) -> bool:
        wrong = (e.get('wrong') or '').strip()
        right = (e.get('right') or '').strip()
        # 1. wrong 是纯符号/标点
        if wrong in bad_set:
            return True
        # 2. wrong == right (无意义)
        if wrong == right:
            return True
        # 3. wrong 过短 (≤1 字符) 容易误伤
        if len(wrong) < 2:
            return True
        return False

    clean = [e for e in d if not is_bad(e)]
    removed = [e for e in d if is_bad(e)]

    print(f'Before: {len(d)}, After: {len(clean)}, Removed: {len(removed)}', flush=True)
    for r in removed[:10]:
        print(f"  BAD: {r.get('wrong')!r} → {r.get('right')!r}", flush=True)
    if len(removed) > 10:
        print(f'  ... ({len(removed) - 10} more)', flush=True)

    with ASR_TERMS.open('w', encoding='utf-8') as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
    print(f'\n[OK] asr_terms.json 已清理 ({len(removed)} 条坏条目移除)', flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
