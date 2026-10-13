#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_terms.py — 从 `media-to-doc/docs/电商术语表.md` 抽取 ASR 易错映射。

输出 JSON 格式：
[
  {"wrong": "浅客", "right": "潜客"},
  ...
]

来源：电商术语表（用户维护）。本文件路径可通过 --source 覆盖。

注意：术语表有多种 ASR 字段格式：
  - `ASR 易错：词1 / 词2 / 词3`
  - `ASR 易错：词1、词2、词3`

抽取策略：
  - 遍历所有 H2/H3 标题
  - 找含 `ASR 易错` 或 `ASR 易错词` 的行
  - 解析其右边的 `wrong / right` 列表
  - 跳过 `同义词` / `口语化` 等字段（只取 `ASR 易错`）

用法：
  python extract_terms.py [--source <path>] [--out <path>]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_SOURCE = Path(r"F:\soft\00selfmade\media-to-doc\docs\电商术语表.md")


def extract_from_text(text: str) -> list[dict]:
    """从术语表 markdown 抽取 ASR 易错 → 规范词 映射。

    期望格式：
        - **GMV**\(通用\)
            - 定义：...
            - **英文缩写：...**
            - ASR 易错：词1 / 词2 / 词3   ← 提取这里的 right
            - 口语化：...
            - 同义词：...

    仅捕获"形如 `- **NAME**(\(类型\))?` "的顶级项作为规范词；其他形如
    `**英文缩写：**` / `定义：` / `口语化：` / `同义词：` 的行不更新 right。
    """
    pairs: list[dict] = []
    current_right: str | None = None
    # 顶级项匹配：行首 `- **NAME**`（NAME 不含 `:`，避免捕获"英文缩写："）
    # 注：原文档里 `(通用\)` 实际是 `\\(通用\\)`（双反斜杠 + 括号，markdown 转义）
    top_re = re.compile(r"^[-*]\s*\*\*([^*]+?)\*\*\s*(?:\\?\([^)]*\\?\))?\s*$")
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        m = top_re.match(s)
        if m:
            name = m.group(1).strip()
            # 排除 "英文缩写: ..." / "定义: ..." / "口语化: ..." 等字段
            if any(sep in name for sep in ("：", ":", "=", "（", "）")):
                continue
            current_right = name
            continue
        # 检测 "ASR 易错" 字段
        if "ASR 易错" in s and current_right:
            after = s.split("ASR 易错", 1)[1]
            after = re.sub(r"^[\s*]*[：:]\s*", "", after)
            tokens = re.split(r"[/／、，,；;]+", after)
            for tok in tokens:
                tok = tok.strip()
                if not tok or len(tok) > 15:
                    continue
                if any(c in tok for c in "（）。，,；; "):
                    continue
                if "识别" in tok or "正确" in tok:
                    continue
                if tok == current_right:
                    continue
                pairs.append({"wrong": tok, "right": current_right})
    return pairs


def dedupe_pairs(pairs: list[dict]) -> list[dict]:
    """去重：保留首次出现的 (wrong, right) 组合。"""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for p in pairs:
        key = (p["wrong"], p["right"])
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    p.add_argument("--out", type=Path, default=None,
                   help="输出 JSON 路径；默认 stdout")
    args = p.parse_args()

    if not args.source.exists():
        print(f"错误：源文件不存在 {args.source}", file=sys.stderr)
        sys.exit(2)

    text = args.source.read_text(encoding="utf-8")
    pairs = dedupe_pairs(extract_from_text(text))
    print(f"从 {args.source.name} 抽取 {len(pairs)} 条 ASR 易错映射", file=sys.stderr)

    output = json.dumps(pairs, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(output, encoding="utf-8")
        print(f"已写出 {args.out}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()