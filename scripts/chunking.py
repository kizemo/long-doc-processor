"""chunking.py — 通用 markdown 切分工具(v4.21 新增,A3 沉淀)

封装 3 类切分模式:
  - split_by_h2:按 H2 标题切分(preamble + H2 块列表)
  - split_oversized_h2:超长 H2 块按 H3 再切
  - split_by_chars:兜底按字符数强切

设计来源:`_purify_smooth.split_by_h2` + `split_oversized_h2` 抽出,
供 strip_lecturer_preamble / strip_role_persona / purify_v4_4 共用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# H1 / H2 / H3 / H4 / H5 标题正则(E3 集中,v4.21 E 阶段)
# match 系列:仅匹配标题起始(matched at `## ` 等),用于判断"是否是某级标题"
# with_title 系列:捕获标题文字,用于提取
_H1_RE = re.compile(r'^#\s+', re.MULTILINE)
_H2_RE = re.compile(r'^##\s+', re.MULTILINE)
_H3_RE = re.compile(r'^###\s+', re.MULTILINE)
_H4_RE = re.compile(r'^####\s+', re.MULTILINE)
_H5_RE = re.compile(r'^#####\s+', re.MULTILINE)

# 带标题文字捕获的版本(用于提取标题)
_H1_TITLE_RE = re.compile(r'^#\s+(.+?)$', re.MULTILINE)
_H2_TITLE_RE = re.compile(r'^##\s+(.+?)$', re.MULTILINE)
_H3_TITLE_RE = re.compile(r'^###\s+(.+?)$', re.MULTILINE)
_H4_TITLE_RE = re.compile(r'^####\s+(.+?)$', re.MULTILINE)
_H5_TITLE_RE = re.compile(r'^#####\s+(.+?)$', re.MULTILINE)

# 标题检测辅助
HEADING_RE = {
    1: _H1_RE,
    2: _H2_RE,
    3: _H3_RE,
    4: _H4_RE,
    5: _H5_RE,
}
HEADING_TITLE_RE = {
    1: _H1_TITLE_RE,
    2: _H2_TITLE_RE,
    3: _H3_TITLE_RE,
    4: _H4_TITLE_RE,
    5: _H5_TITLE_RE,
}


# 单 chunk 字符上限(SKILL Gotcha:超出会让 LLM 自由发挥编造内容)
# v4.21 C2 阶段:集中到 chunking.py,各脚本 import 此常量
MAX_CHARS = 8000
# 兼容别名(老代码可能 import 此名)
DEFAULT_MAX_CHARS = MAX_CHARS


@dataclass
class H2Block:
    """一个 H2 章节的切片(与 _purify_smooth 兼容)。

    Attributes:
        title_line: `## 1. xxx` 行(含换行符)
        content_lines: 该 H2 下的所有行(H3/正文/表格)
        raw_text: 整个块原始文本(便于送 LLM)
    """
    title_line: str
    content_lines: list[str]
    raw_text: str


def split_by_h2(text: str) -> tuple[str, list[H2Block]]:
    """按 H2 标题切分 markdown。

    Args:
        text: 完整 markdown 文本

    Returns:
        (preamble, h2_blocks)
        - preamble: 第一个 H2 之前的所有内容(通常含 H1 + frontmatter)
        - h2_blocks: 按顺序排列的 H2 章节列表
    """
    # 找所有 H2 标题的位置
    h2_positions: list[tuple[int, str]] = []  # (offset, full_line)
    for m in _H2_RE.finditer(text):
        line_start = m.start()
        # 行结束位置
        line_end = text.find('\n', line_start)
        if line_end == -1:
            line_end = len(text)
        h2_positions.append((line_start, text[line_start:line_end + 1]))

    if not h2_positions:
        return text, []

    preamble = text[:h2_positions[0][0]]
    blocks: list[H2Block] = []
    for i, (offset, line) in enumerate(h2_positions):
        next_offset = h2_positions[i + 1][0] if i + 1 < len(h2_positions) else len(text)
        block_text = text[offset:next_offset]
        # 拆分 title_line 和 content_lines
        lines = block_text.splitlines(keepends=True)
        blocks.append(H2Block(
            title_line=lines[0] if lines else line,
            content_lines=lines[1:] if len(lines) > 1 else [],
            raw_text=block_text,
        ))
    return preamble, blocks


def split_oversized_h2(
    block: H2Block, max_chars: int = MAX_CHARS
) -> list[H2Block]:
    """对超大 H2 块按 H3 切分(每个子块仍属同一 H2)。

    SKILL Gotcha:单块 > 8K chars 会让 LLM 自由发挥编造内容。
    若无 H3 子节,兜底按字符数强切。

    Args:
        block: 单个 H2Block
        max_chars: 单块字符上限(默认 8000 = MAX_CHARS)

    Returns:
        切分后的 H2Block 列表(若无需切分则返回 [block])
    """
    if len(block.raw_text) <= max_chars:
        return [block]

    # 按 ### 切
    h3_positions = [m.start() for m in _H3_RE.finditer(block.raw_text)]

    if not h3_positions:
        # 无 H3 子节,只能强行按字符切(SKILL Gotcha 边缘 case)
        return _split_by_chars(block, max_chars)

    # 切分:preamble (text before first ###) + H3 sub-blocks
    chunks: list[H2Block] = []
    preamble_end = h3_positions[0]
    preamble_text = block.raw_text[:preamble_end]
    if preamble_text.strip():
        chunks.append(H2Block(
            title_line=block.title_line,
            content_lines=preamble_text[len(block.title_line):].splitlines(keepends=True),
            raw_text=block.title_line + preamble_text[len(block.title_line):],
        ))

    for i, start in enumerate(h3_positions):
        end = h3_positions[i + 1] if i + 1 < len(h3_positions) else len(block.raw_text)
        sub_text = block.raw_text[start:end]
        chunks.append(H2Block(
            title_line='',  # 子块无独立 H2 title(归属主 H2)
            content_lines=sub_text.splitlines(keepends=True),
            raw_text=sub_text,
        ))

    # 进一步检查每个子块 ≤ max_chars
    final: list[H2Block] = []
    for c in chunks:
        if len(c.raw_text) <= max_chars:
            final.append(c)
        else:
            final.extend(_split_by_chars(c, max_chars))
    return final


def _split_by_chars(block: H2Block, max_chars: int) -> list[H2Block]:
    """兜底:按字符数强行切。

    v4.21 C2 阶段:作为公共 helper 暴露在 chunking.py(原 _purify_smooth 内嵌)。
    """
    text = block.raw_text
    chunks: list[H2Block] = []
    for i in range(0, len(text), max_chars):
        sub_text = text[i:i + max_chars]
        chunks.append(H2Block(
            title_line='',
            content_lines=[sub_text],
            raw_text=sub_text,
        ))
    return chunks


# v4.21 C2 兼容别名:旧代码 import 自 _purify_smooth
# (_purify_smooth 中 re-export 这些)
def _smooth_split_by_chars(block: H2Block, max_chars: int) -> list[H2Block]:
    """_purify_smooth 兼容别名(老测试可能 import 此名)。"""
    return _split_by_chars(block, max_chars)


def chunk_for_llm(
    text: str,
    max_chars: int = MAX_CHARS,
) -> tuple[str, list[H2Block]]:
    """组合 split_by_h2 + split_oversized_h2,直接产出 LLM-ready chunks。

    Args:
        text: 完整 markdown 文本
        max_chars: 单 chunk 字符上限

    Returns:
        (preamble, h2_blocks_ready) — 后续调 LLM 并重组即可
    """
    preamble, blocks = split_by_h2(text)
    all_chunks: list[H2Block] = []
    for b in blocks:
        all_chunks.extend(split_oversized_h2(b, max_chars))
    return preamble, all_chunks
