#!/usr/bin/env python3
"""verify_html.py — Phase 3 HTML 输出验收。

Usage:
    python verify_html.py <output.html>

按 qa-gates.md 第 17-22 项验收：
17. HTML 文件可解析
18. <title> 与首个 H1 一致
19. 所有 <img> 引用的文件存在
20. 所有 <img> 含 alt 属性
21. img/ 子目录与 HTML 在同一父目录
22. 顶层 H1 有且仅有一个
"""
from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path


class Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.h1_count = 0
        self.first_h1: str | None = None
        self.imgs: list[tuple[str, str]] = []  # (src, alt)
        self.in_title = False
        self.in_h1 = False
        self.title_buf: list[str] = []
        self.h1_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag == "h1":
            self.in_h1 = True
            self.h1_count += 1
            self.h1_buf = []
        elif tag == "img":
            src = a.get("src") or ""
            alt = a.get("alt") or ""
            self.imgs.append((src, alt))

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
            self.title = "".join(self.title_buf).strip()
        elif tag == "h1":
            self.in_h1 = False
            if self.first_h1 is None:
                self.first_h1 = "".join(self.h1_buf).strip()

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_buf.append(data)
        if self.in_h1:
            self.h1_buf.append(data)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python verify_html.py <output.html>", file=sys.stderr)
        return 2
    html_path = Path(argv[1])
    if not html_path.exists():
        print(f"FAIL: file not found: {html_path}")
        return 1
    text = html_path.read_text(encoding="utf-8", errors="ignore")

    parser = Parser()
    issues: list[str] = []
    try:
        parser.feed(text)
    except Exception as exc:
        print(f"FAIL[17]: HTML parse error: {exc}")
        return 1

    # 17
    print("PASS[17]: HTML parsed")

    # 17b: 禁止 YAML frontmatter 残留（防止 Markdown 头部的 --- 块被渲染为段落）
    frontmatter_artifacts = [
        "<p>---</p>",
        "<p>title:",
        "<p>source:",
        "<p>date:",
        "<p>author:",
    ]
    for artifact in frontmatter_artifacts:
        if artifact in text:
            issues.append(f"17b: frontmatter artifact detected: '{artifact}'")
    if not any(a in text for a in frontmatter_artifacts):
        print("PASS[17b]: no YAML frontmatter artifacts")

    # 18
    if parser.title and parser.first_h1:
        if parser.title.strip() != parser.first_h1.strip():
            issues.append(f"18: title '{parser.title}' != first H1 '{parser.first_h1}'")
        else:
            print(f"PASS[18]: title matches H1: {parser.title}")
    else:
        issues.append("18: missing title or H1")

    # 19 + 20
    parent = html_path.parent
    for src, alt in parser.imgs:
        if not alt:
            issues.append(f"20: <img src='{src}'> missing alt")
        if src.startswith(("http://", "https://", "data:")):
            continue
        ref = (parent / src).resolve()
        if not ref.exists():
            issues.append(f"19: <img src='{src}'> file not found at {ref}")
        else:
            print(f"PASS[19]: image exists: {src}")
    if not parser.imgs:
        print("INFO: no <img> tags found (skip 19/20)")

    # 21
    img_dir = parent / "img"
    if img_dir.exists() and not img_dir.is_dir():
        issues.append("21: img exists but is not a directory")
    else:
        print(f"PASS[21]: img/ handled (exists={img_dir.exists()})")

    # 22
    if parser.h1_count == 1:
        print(f"PASS[22]: exactly one H1: {parser.first_h1}")
    else:
        issues.append(f"22: expected exactly 1 H1, found {parser.h1_count}")

    if issues:
        for issue in issues:
            print(f"FAIL: {issue}")
        return 1
    print("OK: verify_html passed all checks")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))