#!/usr/bin/env python3
"""markdown_to_html.py — 把合并后的 Markdown 渲染为可独立打开的单文件 HTML。

Usage:
    python markdown_to_html.py <input.md> <output.html>

特点：
- 内嵌 CSS，无外部依赖；
- 图片相对路径以 img/xxx 形式写入；
- 标题层级映射为 h1/h2/h3/h4；
- 自动生成简易目录（来自 H1/H2）。
"""
from __future__ import annotations

import re
import sys
from html import escape
from pathlib import Path


CSS = """
body { font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; max-width: 920px; margin: 2rem auto; padding: 0 1rem; line-height: 1.7; color: #222; }
h1 { color: #003070; border-bottom: 2px solid #003070; padding-bottom: .3em; }
h2 { color: #003070; margin-top: 2em; }
h3 { color: #1a4480; }
h4 { color: #2a5490; }
code { background: #f4f4f4; padding: .1em .3em; border-radius: 3px; }
pre { background: #f4f4f4; padding: 1em; border-radius: 4px; overflow-x: auto; }
blockquote { border-left: 4px solid #003070; padding-left: 1em; color: #555; margin-left: 0; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { border: 1px solid #ccc; padding: .5em; }
th { background: #f0f4f8; }
img { max-width: 100%; height: auto; }
.toc { background: #f7f9fc; border: 1px solid #d0d8e0; padding: 1em 1.5em; margin-bottom: 2em; }
.toc ul { list-style: none; padding-left: 1em; }
"""


def slugify(text: str) -> str:
    s = re.sub(r"\s+", "-", text.strip())
    s = re.sub(r"[^\w\u4e00-\u9fff\-]+", "", s)
    return s or "section"


def render_inline(text: str) -> str:
    """处理行内元素：加粗、斜体、代码、图片、链接。"""
    # 图片
    text = re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        r'<img src="\2" alt="\1" data-source="original">',
        text,
    )
    # 链接
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )
    # 加粗
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # 斜体
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    # 行内代码
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def render_table(lines: list[str], start: int) -> tuple[str, int]:
    """渲染 Markdown 表格块。返回 HTML 与结束行索引。"""
    rows = []
    i = start
    while i < len(lines) and lines[i].strip().startswith("|"):
        rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
        i += 1
    if len(rows) < 2:
        return "", start
    header, *body = rows
    if not all(set(c.replace(":", "").strip()) <= set("- ") for c in rows[1]):
        body = rows[1:]
        header_row = header
    else:
        body = rows[2:]
        header_row = header
    html = ["<table>", "<thead><tr>"]
    for c in header_row:
        html.append(f"<th>{render_inline(escape(c))}</th>")
    html.append("</tr></thead><tbody>")
    for row in body:
        html.append("<tr>")
        for c in row:
            html.append(f"<td>{render_inline(escape(c))}</td>")
        html.append("</tr>")
    html.append("</tbody></table>")
    return "".join(html), i


def render(md: str, title: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    toc: list[str] = []
    in_code = False
    code_buf: list[str] = []
    in_list: str | None = None
    list_buf: list[str] = []

    def flush_list() -> None:
        nonlocal in_list, list_buf
        if in_list is not None and list_buf:
            tag = "ul" if in_list == "ul" else "ol"
            out.append(f"<{tag}>")
            for item in list_buf:
                out.append(f"<li>{render_inline(escape(item))}</li>")
            out.append(f"</{tag}>")
        in_list = None
        list_buf = []

    i = 0
    while i < len(lines):
        line = lines[i]
        if in_code:
            if line.strip().startswith("```"):
                out.append(f"<pre><code>{escape(chr(10).join(code_buf))}</code></pre>")
                code_buf = []
                in_code = False
            else:
                code_buf.append(line)
            i += 1
            continue
        if line.strip().startswith("```"):
            flush_list()
            in_code = True
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            flush_list()
            level = len(m.group(1))
            text = m.group(2).strip()
            anchor = slugify(text)
            tag = f"h{level}"
            out.append(f'<{tag} id="{anchor}">{render_inline(escape(text))}</{tag}>')
            if level <= 2:
                toc.append(f'<li><a href="#{anchor}">{escape(text)}</a></li>')
            i += 1
            continue
        if line.strip().startswith("|"):
            flush_list()
            table_html, i = render_table(lines, i)
            out.append(table_html)
            continue
        if line.startswith("> "):
            flush_list()
            out.append(f"<blockquote>{render_inline(escape(line[2:].strip()))}</blockquote>")
            i += 1
            continue
        ol_m = re.match(r"^(\d+)\.\s+(.*)$", line)
        ul_m = re.match(r"^[-*]\s+(.*)$", line)
        if ol_m or ul_m:
            new_kind = "ol" if ol_m else "ul"
            # ol 正则 group(2) 是内容；ul 正则 group(1) 是内容（group 索引不同）
            item = ol_m.group(2) if ol_m else ul_m.group(1)
            if in_list is not None and in_list != new_kind:
                flush_list()
            in_list = new_kind
            list_buf.append(item)
            i += 1
            continue
        if line.strip() == "":
            flush_list()
            i += 1
            continue
        flush_list()
        out.append(f"<p>{render_inline(escape(line))}</p>")
        i += 1

    flush_list()
    if in_code and code_buf:
        out.append(f"<pre><code>{escape(chr(10).join(code_buf))}</code></pre>")

    body = "\n".join(out)
    toc_html = ""
    if toc:
        toc_html = '<div class="toc"><strong>目录</strong><ul>' + "\n".join(toc) + "</ul></div>"
    return (
        "<!doctype html>\n"
        f"<html lang=\"zh-CN\"><head><meta charset=\"utf-8\">\n"
        f"<title>{escape(title)}</title>\n"
        f"<style>{CSS}</style></head>\n"
        f"<body>{toc_html}{body}</body></html>"
    )


def strip_yaml_frontmatter(md: str) -> tuple[str, bool]:
    """剥离文档开头的 YAML frontmatter（--- 包裹的元数据块）。

    返回 (处理后文本, 是否剥离成功)。
    """
    if not md.startswith("---"):
        return md, False
    # 找第二个 --- 作为结束标记
    lines = md.splitlines(keepends=True)
    if len(lines) < 2 or not lines[0].startswith("---"):
        return md, False
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].startswith("---"):
            end_idx = i
            break
    if end_idx is None:
        return md, False
    body = "".join(lines[end_idx + 1 :])
    return body.lstrip("\n"), True


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: python markdown_to_html.py <input.md> <output.html>", file=sys.stderr)
        return 2
    src = Path(argv[1])
    dst = Path(argv[2])
    if not src.exists():
        print(f"ERROR: input not found: {src}", file=sys.stderr)
        return 1
    md = src.read_text(encoding="utf-8")
    md, stripped = strip_yaml_frontmatter(md)
    if stripped:
        print(f"INFO: stripped YAML frontmatter from {src.name}")
    title_match = re.search(r"^#\s+(.+)$", md, re.M)
    title = title_match.group(1).strip() if title_match else dst.stem
    html = render(md, title)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(html, encoding="utf-8", newline="\n")
    print(f"OK: wrote {dst} ({len(html)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))