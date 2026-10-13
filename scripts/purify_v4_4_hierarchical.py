#!/usr/bin/env python3
"""purify_v4_4_hierarchical.py — v4.4 核心净化(hierarchical pipeline)

按骨架 H2 切分 → LLM 净化 → retry 兜底 → 强制对齐骨架。

SKILL.md v4.4 changelog 关键约束:
  - 8 chunk 切分(每 chunk 1 H2 期望)
  - LLM 调 references/purification-prompt.md
  - 强制 1 H2/chunk(SKILL Gotcha:LLM 经常违反,实测 8 块首次 26 H2)
  - retry + 项目级 merge 兜底

用法:
  python scripts/purify_v4_4_hierarchical.py <input.md> -o <output.md> --n-chunks 8
  python scripts/purify_v4_4_hierarchical.py <input.md> -o <output.md> --skeleton <skeleton.md>
  python scripts/purify_v4_4_hierarchical.py <input.md> -o <output.md> --dry-run  # 只切不调 LLM
"""
from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 让 CLI 直接 import 同包脚本
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from scripts._llm_vision import call_vision
except ImportError:
    from _llm_vision import call_vision  # type: ignore
from utils import read_file_safely, write_file_safely, log  # noqa: E402


# 配置 ------------------------------------------------------------

DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_N_CHUNKS = 8
PURIFICATION_PROMPT_PATH = "references/purification-prompt.md"


# Prompt 模板 --------------------------------------------------------

PURIFY_CHUNK_PROMPT_TEMPLATE = """你是中文电商培训讲义文稿的"净化"专家。

## 任务
对以下一份 ASR 转录段落做净化:
- **保留**:5 类核心资产(概念 / 案例 / 数据 / 逻辑 / 表格)+ 8 类实质内容
- **删除**:4 类噪声(纪律语 / 引导语 / 寒暄 / 口语填充词)+ 直播广告 7 类 + 直播间互动
- **重写**:不通顺句子,但**不删原文信息单元**(信息量守恒)

## 骨架约束(必须遵守)
本块在 cleaned.md 中对应的 H2 标题为:
{skeleton_h2}

请**保留此标题**作为本块输出的 ## 标题,标题文字完全一致。
本块**只输出 1 个 H2**,不要新增额外 H2,不要把内容塞到其它 H2。

## 章节数量约束
本 chunk 在 cleaned.md 完整结构中应为第 {chunk_index}/{total_chunks} 个 H2。
不要输出任何前置/后置 H2(否则骨架错位)。

## 完整净化规约
参见 references/purification-prompt.md(本项目内置),其全部规则本块均需执行。

## 输入块(原始 ASR 转录)
{chunk_text}

## 输出要求
- 完整 Markdown(不是 diff)
- H1 / frontmatter 不要输出(只输出 ## + 内容)
- 表格 / 列表 / 引用块保留
- 时间戳行 `[HH:MM:SS] xxx` 必须删除
- 行末口语填充词"对吧/是吧/嗯/啊"必须删除
- 不新增原块没有的句子、案例、数据

## 输出块(直接给完整 Markdown,不要解释)
"""


# 数据结构 --------------------------------------------------------

@dataclass
class Chunk:
    """一个 H2 chunk(包含标题 + 正文)"""
    chunk_index: int              # 1-based 序号
    expected_h2_title: str       # 期望输出的 H2 标题
    raw_text: str                # 原始 ASR 内容(去掉 H1/preamble)
    cleaned_text: str = ""       # LLM 输出(初始化后填)
    retry_count: int = 0         # LLM 调用次数(retry 计数)
    h2_actual_count: int = 0     # 实际输出的 H2 数(用于 verify)


# 骨架提取 + chunk 切分 ----------------------------------------------

_H2_RE = re.compile(r'^##\s+(.+?)$', re.MULTILINE)
_H1_RE = re.compile(r'^#\s+(.+?)$', re.MULTILINE)


def extract_h2_titles(md_text: str) -> list[str]:
    """提取 markdown 中所有 H2 标题(去掉 '# ' 前缀)。"""
    titles: list[str] = []
    for m in _H2_RE.finditer(md_text):
        title = m.group(1).strip()
        titles.append(title)
    return titles


def extract_skeleton_h2(skeleton_path: Path) -> list[str]:
    """读 skeleton 文件,提取所有 H2 标题。"""
    if not skeleton_path.exists():
        return []
    content = read_file_safely(skeleton_path)
    return extract_h2_titles(content)


def split_into_chunks(md_text: str, skeleton_h2: list[str],
                      n_chunks: int = DEFAULT_N_CHUNKS) -> list[Chunk]:
    """按 H2 切分输入 md 为 chunks。

    策略:
      1. 优先按 H2 边界切:每 H2 = 1 chunk(如果 H2 数 ≤ n_chunks)
      2. 否则按 char count 切:每 chunk ≈ len/N,优先 H2 边界
      3. skeleton_h2 非空时,以 skeleton 为准(用于 anchor)

    Returns: Chunk 列表(每个 chunk 含期望 H2 标题)
    """
    # 抽 preamble(第一个 H2 之前的所有内容)
    first_h2_match = _H2_RE.search(md_text)
    if first_h2_match:
        preamble = md_text[:first_h2_match.start()]
    else:
        preamble = md_text  # 无 H2,全部当 preamble

    # 找所有 H2 标题 + 位置
    h2_positions: list[tuple[int, str]] = []
    for m in _H2_RE.finditer(md_text):
        title = m.group(1).strip()
        h2_positions.append((m.start(), title))

    if not h2_positions:
        # 无 H2:整个 preamble 作为 1 个 chunk
        return [Chunk(
            chunk_index=1,
            expected_h2_title="(no H2)",
            raw_text=preamble,
        )]

    # 切分:每个 H2 章节 = 1 chunk
    chunks: list[Chunk] = []
    n_h2 = len(h2_positions)
    target_count = min(n_chunks, n_h2)

    if target_count >= n_h2:
        # 每个 H2 = 1 chunk(直接 1:1 切)
        for i, (offset, title) in enumerate(h2_positions):
            next_offset = h2_positions[i + 1][0] if i + 1 < n_h2 else len(md_text)
            block_text = md_text[offset:next_offset]
            expected_title = (skeleton_h2[i] if i < len(skeleton_h2) else title)
            chunks.append(Chunk(
                chunk_index=i + 1,
                expected_h2_title=expected_title,
                raw_text=block_text,
            ))
        return chunks

    # H2 多于 target_count:合并相邻 H2 到同一 chunk(尽量均匀)
    h2_per_chunk = n_h2 // target_count
    remainder = n_h2 % target_count
    cur_h2_idx = 0
    for c in range(target_count):
        chunk_h2_count = h2_per_chunk + (1 if c < remainder else 0)
        if cur_h2_idx >= n_h2:
            break
        start_offset = h2_positions[cur_h2_idx][0]
        end_h2_idx = min(cur_h2_idx + chunk_h2_count, n_h2)
        end_offset = h2_positions[end_h2_idx][0] if end_h2_idx < n_h2 else len(md_text)
        block_text = md_text[start_offset:end_offset]
        # 期望标题 = skeleton[cur_h2_idx](若 skeleton 短则用实际首个)
        expected_title = (skeleton_h2[cur_h2_idx] if cur_h2_idx < len(skeleton_h2)
                          else h2_positions[cur_h2_idx][1])
        chunks.append(Chunk(
            chunk_index=c + 1,
            expected_h2_title=expected_title,
            raw_text=block_text,
        ))
        cur_h2_idx = end_h2_idx
    return chunks


# LLM 净化 ---------------------------------------------------------

def purify_chunk(chunk: Chunk, model: str, total_chunks: int) -> str:
    """调 LLM 对单个 chunk 做净化,带 retry 逻辑。

    Retry 触发:输出 H2 数 ≠ 1(LLM 经常违反"1 H2/chunk"规约)
    重试 prompt 加强:加 "⚠️ 第 N 次调用:必须只输出 1 个 H2,标题文字 = {skeleton_h2}"
    """
    prompt = PURIFY_CHUNK_PROMPT_TEMPLATE.format(
        skeleton_h2=chunk.expected_h2_title,
        chunk_index=chunk.chunk_index,
        total_chunks=total_chunks,
        chunk_text=chunk.raw_text,
    )

    for attempt in range(1, 4):  # 最多 3 次(初 + 2 retry)
        chunk.retry_count = attempt
        try:
            response = call_vision(prompt, [], model=model)
        except Exception as e:
            log(f"[purify] chunk {chunk.chunk_index} 第 {attempt} 次 LLM 异常:{e}")
            response = ""

        if not response or not response.strip():
            log(f"[purify] chunk {chunk.chunk_index} 第 {attempt} 次 LLM 返回空")
            continue

        cleaned = _strip_markdown_wrapper(response)
        # verify H2 count
        h2_count = len(re.findall(r'^##\s+', cleaned, re.MULTILINE))
        chunk.h2_actual_count = h2_count

        if h2_count == 1:
            return cleaned

        log(f"[purify] chunk {chunk.chunk_index} 第 {attempt} 次输出 H2={h2_count} ≠ 1,准备 retry")
        # 加强 prompt:加 ⚠️ 警告
        prompt = _strengthen_prompt(prompt, attempt + 1, h2_count)

    # 3 次都失败,降级兜底
    log(f"[purify] chunk {chunk.chunk_index} 3 次 LLM 均不合规,降级到骨架对齐")
    return _fallback_alignment(chunk)


def _strip_markdown_wrapper(text: str) -> str:
    """去 LLM 响应外层 ```markdown ... ``` 包装。"""
    m = re.search(r'^```(?:markdown)?\s*\n(.*?)\n```\s*$', text.strip(), re.DOTALL)
    return m.group(1) if m else text


def _strengthen_prompt(base_prompt: str, attempt: int, observed_h2: int) -> str:
    """retry 时在 prompt 末尾加警告。"""
    warning = (f"\n\n⚠️ 第 {attempt} 次调用警告:上次输出 {observed_h2} 个 H2,违反 1 H2/chunk 约束。"
               f"本次必须只输出 1 个 H2,标题文字完全等于上述期望。")
    return base_prompt + warning


def _fallback_alignment(chunk: Chunk) -> str:
    """LLM 兜底:直接用骨架 H2 替换 raw_text 中的第一个 H2 标题。"""
    # 在 raw_text 中找到第一个 ## 标题行
    lines = chunk.raw_text.splitlines(keepends=True)
    replaced = False
    new_lines: list[str] = []
    for line in lines:
        if not replaced and re.match(r'^##\s+', line):
            new_lines.append(f"## {chunk.expected_h2_title}\n")
            replaced = True
        else:
            new_lines.append(line)
    # 兜底:如果原始没有 H2 标题,直接在开头加
    if not replaced:
        new_lines.insert(0, f"## {chunk.expected_h2_title}\n")
    return ''.join(new_lines)


# 主流程 -----------------------------------------------------------

def purify_document(input_path: Path, output_path: Path,
                    skeleton_path: Path | None = None,
                    n_chunks: int = DEFAULT_N_CHUNKS,
                    model: str = DEFAULT_MODEL,
                    workers: int = 3,
                    dry_run: bool = False) -> int:
    """主入口:读 input → 切 chunk → 并发调 LLM → 写 cleaned.md。"""
    if not input_path.exists():
        log(f"ERROR: 输入文件不存在:{input_path}")
        return 1

    content = read_file_safely(input_path)

    # 读 skeleton(若有)
    skeleton_h2: list[str] = []
    if skeleton_path and skeleton_path.exists():
        skeleton_h2 = extract_skeleton_h2(skeleton_path)
        log(f"[purify] 读 skeleton:{len(skeleton_h2)} 个 H2 from {skeleton_path.name}")
    else:
        log("[purify] skeleton 未指定,使用 input 中现有 H2 标题")

    # 切分
    chunks = split_into_chunks(content, skeleton_h2, n_chunks=n_chunks)
    log(f"[purify] 切分为 {len(chunks)} 个 chunk (n_chunks={n_chunks})")

    if dry_run:
        log("[purify] dry-run,跳过 LLM")
        for c in chunks:
            log(f"  [{c.chunk_index}] {len(c.raw_text)} chars, expected H2: {c.expected_h2_title[:40]}")
        return 0

    # 并发调 LLM
    cleaned_chunks: list[str] = [''] * len(chunks)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_idx = {
            executor.submit(purify_chunk, c, model, len(chunks)): i
            for i, c in enumerate(chunks)
        }
        for future in as_completed(future_to_idx):
            i = future_to_idx[future]
            try:
                cleaned_chunks[i] = future.result()
            except Exception as e:
                log(f"[purify] chunk {i+1} 异常:{e};降级用骨架对齐")
                cleaned_chunks[i] = _fallback_alignment(chunks[i])

    # 重组 cleaned.md(preamble + 所有 chunks)
    first_h2_match = _H2_RE.search(content)
    preamble = content[:first_h2_match.start()] if first_h2_match else ""
    output = preamble + '\n'.join(cleaned_chunks)
    if not output.endswith('\n'):
        output += '\n'

    # 写文件
    write_file_safely(output_path, output)
    log(f"[purify] DONE: {output_path}")
    return 0


# CLI -------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='v4.4 hierarchical 净化(8 chunk + LLM + 骨架对齐 + retry)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('input', type=Path, help='输入 raw/transcript md 路径')
    parser.add_argument('-o', '--output', type=Path, required=True, help='输出 cleaned.md 路径')
    parser.add_argument('--skeleton', type=Path, help='skeleton.md 路径(可选,提供 H2 锚点)')
    parser.add_argument('--n-chunks', type=int, default=DEFAULT_N_CHUNKS,
                        help=f'目标 chunk 数(默认 {DEFAULT_N_CHUNKS})')
    parser.add_argument('--workers', type=int, default=3, help='并发 LLM 数')
    parser.add_argument('--model', default=DEFAULT_MODEL, help='LLM 模型 ID')
    parser.add_argument('--dry-run', action='store_true', help='只切分不调 LLM')
    args = parser.parse_args()

    return purify_document(
        args.input, args.output,
        skeleton_path=args.skeleton,
        n_chunks=args.n_chunks,
        model=args.model,
        workers=args.workers,
        dry_run=args.dry_run,
    )


if __name__ == '__main__':
    sys.exit(main())
