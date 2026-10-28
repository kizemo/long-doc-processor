#!/usr/bin/env python3
"""_purify_smooth.py — v4.16 通顺化重写脚本

对 <stem>_cleaned.md 按 H2 切分,每 H2 独立调 LLM 做通顺化重写。

SKILL.md v4.16 changelog 关键约束:
  - 禁止 LLM 新增内容 / 禁止删除原标题 / 禁止改变章节数量 / 禁止虚构案例
  - 必须清理: 行首时间戳 / 粗口 / ASR 装饰 / ASR 串扰 / 错乱中英俄混杂 /
              不通顺短句 / 重复词
  - 单块 ≤ 8K chars(SKILL Gotcha:超出会让 LLM 自由发挥编造内容)
  - 每 H2 必须独立调 LLM(不要跨章节合并)

用法:
  python scripts/_purify_smooth.py <cleaned.md> -o <smoothed.md> --workers 3
  python scripts/_purify_smooth.py <cleaned.md> -o <smoothed.md> --model claude-sonnet-4-5
  python scripts/_purify_smooth.py <cleaned.md> -o <smoothed.md> --dry-run  # 只输出切分信息

输出格式: 与 cleaned.md 完全一致,仅替换各 H2 章节的正文内容(标题原样)
"""
from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 让 CLI 也能直接 import scripts.* 模块(不依赖 pytest 加 rootdir)
sys.path.insert(0, str(Path(__file__).parent))            # scripts/ for utils
sys.path.insert(0, str(Path(__file__).parent.parent))     # project root for 'scripts' package
try:
    from scripts._llm_vision import call_vision  # noqa: E402
except ImportError:
    # 兜底:直接 import(脚本与 _llm_vision.py 同目录)
    from _llm_vision import call_vision  # noqa: E402
from utils import read_file_safely, write_file_safely, log  # noqa: E402


# 配置 ------------------------------------------------------------

MAX_CHUNK_CHARS = 8000  # SKILL Gotcha:超出会让 LLM 自由发挥
DEFAULT_MODEL = "claude-sonnet-4-5"


# Prompt 模板 --------------------------------------------------------

SMOOTH_PROMPT_TEMPLATE = """你是中文电商培训讲义文稿的"通顺化重写"专家。

## 任务
对以下一份已净化的 Markdown 章节做通顺化重写,**只改写不通顺的句子**,
**禁止删除或新增任何实质内容**(同义改写 OK)。

## 必须清理
1. **行首时间戳**:`[HH:MM:SS]` / `[00:00:00]` / `(2026-09-12 ...)` 等转录痕迹
2. **粗口**:骂人字眼(整体删除或同义替换)
3. **ASR 装饰**:`[掌声]` / `[笑声]` / `[音乐]` / `[沉默]` / `<|...|>` 等
4. **ASR 串扰**:同一句话被前后重复(上半句 + 下半句独立),合并为一句
5. **错乱中英俄混杂**:明显不属于这段话的英文单词残留(整体删除或同义改写)
6. **不通顺短句**:段落中独立的"嗯..." "啊..." "那个..." "就是..." 等
7. **重复词**:同一段内同一非专有名词 ≥ 3 次重复,合并或删除冗余

## 绝对禁止(违反则任务失败)
1. ❌ 新增任何原文没有的句子、案例、数据、概念
2. ❌ 删除原标题(## / ### / #### 不动,**只能清理标题下正文**)
3. ❌ 改变章节数量
4. ❌ 虚构案例、店铺、数据
5. ❌ 改动标题文字(包括编号)
6. ❌ 改动表格结构(列数 / 行数 / 表头)
7. ❌ 改动列表项数量

## 输出
- 完整输出 Markdown 章节(不是 diff)
- 保留所有 H2 / H3 / H4 标题**原样**
- 保留所有表格 / 列表 / 引用块 / 加粗 / 行内代码
- 保留所有图片引用(`![](...)`)
- 保留所有超链接(`[text](url)`)

---

## 输入章节(请原样重写,只清理 7 类问题)

{h2_content}

---

## 输出章节(直接给完整 Markdown,不要解释)
"""


# 切分逻辑 ---------------------------------------------------------

@dataclass
class H2Block:
    """一个 H2 章节的切片"""
    title_line: str       # `## 1. xxx` 行(含换行符)
    content_lines: list[str]  # 该 H2 下的所有行(H3/正文/表格)
    raw_text: str         # 整个块原始文本(便于送 LLM)


_H2_RE = re.compile(r'^##\s+', re.MULTILINE)


def split_by_h2(text: str) -> tuple[str, list[H2Block]]:
    """按 H2 标题切分 markdown。

    Returns:
        (preamble, h2_blocks)
        - preamble: 第一个 H2 之前的所有内容(通常含 H1 + frontmatter)
        - h2_blocks: 按顺序排列的 H2 章节列表
    """
    # 找所有 H2 标题的行号
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


def split_oversized_h2(block: H2Block, max_chars: int = MAX_CHUNK_CHARS) -> list[H2Block]:
    """对超大 H2 块按 H3 切分(每个子块仍属同一 H2)。

    SKILL Gotcha:单块 > 8K chars 会让 LLM 自由发挥编造内容。
    """
    if len(block.raw_text) <= max_chars:
        return [block]

    # 按 ### 切
    h3_re = re.compile(r'^###\s+', re.MULTILINE)
    h3_positions = [m.start() for m in h3_re.finditer(block.raw_text)]

    if not h3_positions:
        # 无 H3 子节,只能强行按字符切(SKILL Gotcha 边缘 case)
        log(f"[smooth] WARN: H2 块 {len(block.raw_text)} 字符无 H3,按 8K 强切")
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
    """兜底:按字符数强行切。"""
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


# LLM 调用 ---------------------------------------------------------

def smooth_block(block: H2Block, model: str = DEFAULT_MODEL) -> str:
    """调 LLM 对单个 H2 块做通顺化重写,返回新文本。

    容错:LLM 失败 / 返回非 markdown 时返回原文本(降级)。
    """
    if not block.raw_text.strip():
        return block.raw_text

    prompt = SMOOTH_PROMPT_TEMPLATE.format(h2_content=block.raw_text)
    try:
        response = call_vision(prompt, [], model=model)
    except Exception as e:
        log(f"[smooth] LLM 调用失败: {e};降级保留原文本")
        return block.raw_text

    if not response or not response.strip():
        log(f"[smooth] LLM 返回空;降级保留原文本")
        return block.raw_text

    # 去包装:```markdown ... ``` 或 ``` ... ```
    cleaned = _strip_markdown_wrapper(response)
    return cleaned if cleaned.strip() else block.raw_text


def _strip_markdown_wrapper(text: str) -> str:
    """去掉 LLM 响应外层的 ```markdown ... ``` 包装。"""
    m = re.search(r'^```(?:markdown)?\s*\n(.*?)\n```\s*$', text.strip(), re.DOTALL)
    if m:
        return m.group(1)
    return text


# 标题守恒校验 -------------------------------------------------------

def validate_title_preservation(original: list[H2Block], smoothed_text: str) -> tuple[bool, str]:
    """校验所有原 H2/H3/H4 标题仍出现在输出中。"""
    missing: list[str] = []
    for block in original:
        # 抽所有标题行
        for line in block.raw_text.splitlines():
            if re.match(r'^#{2,4}\s+', line):
                title = line.strip()
                if title not in smoothed_text:
                    missing.append(title)
    if missing:
        return False, f"标题守恒失败:缺失 {missing[:5]}{'...' if len(missing) > 5 else ''}"
    return True, ""


# 主流程 -----------------------------------------------------------

def smooth_document(input_path: Path, output_path: Path,
                    model: str = DEFAULT_MODEL,
                    workers: int = 3,
                    max_chars: int = MAX_CHUNK_CHARS,
                    dry_run: bool = False) -> int:
    """主入口:读 cleaned.md → 切 H2 → 并发调 LLM → 写 smoothed.md。"""
    if not input_path.exists():
        log(f"ERROR: 输入文件不存在:{input_path}")
        return 1

    content = read_file_safely(input_path)
    preamble, h2_blocks = split_by_h2(content)

    log(f"[smooth] 切分:{len(h2_blocks)} 个 H2 章节")

    # 二次切分(超大块按 H3 拆)
    all_chunks: list[H2Block] = []
    for block in h2_blocks:
        all_chunks.extend(split_oversized_h2(block, max_chars))
    log(f"[smooth] 二次切分后:共 {len(all_chunks)} 个 LLM 单元(每块 ≤ {max_chars} chars)")

    if dry_run:
        log("[smooth] dry-run 模式,跳过 LLM 调用")
        for i, c in enumerate(all_chunks, 1):
            log(f"  [{i}] {len(c.raw_text)} chars, title={'YES' if c.title_line else 'no'}")
            log(f"       preview: {c.raw_text[:60].strip()}...")
        return 0

    # 并发调 LLM
    smoothed_blocks: list[str] = [''] * len(all_chunks)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_idx = {
            executor.submit(smooth_block, block, model): i
            for i, block in enumerate(all_chunks)
        }
        for future in as_completed(future_to_idx):
            i = future_to_idx[future]
            try:
                smoothed_blocks[i] = future.result()
            except Exception as e:
                log(f"[smooth] chunk {i} 失败: {e};降级用原文")
                smoothed_blocks[i] = all_chunks[i].raw_text

    # 重组输出(preamble + 所有 smoothed blocks)
    output = preamble
    for chunk_text in smoothed_blocks:
        output += chunk_text
    if not output.endswith('\n'):
        output += '\n'

    # 标题守恒校验
    original_titles = [H2Block(title_line='', content_lines=[], raw_text=b.raw_text)
                       for b in h2_blocks]
    ok, msg = validate_title_preservation(original_titles, output)
    if not ok:
        log(f"[smooth] WARN: {msg}")
    else:
        log(f"[smooth] 标题守恒校验 PASS")

    write_file_safely(output_path, output)
    log(f"[smooth] DONE: {output_path}")
    return 0


# CLI -------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='v4.16 通顺化重写(per H2 独立 LLM)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('input', help='输入 cleaned.md 路径')
    parser.add_argument('-o', '--output', required=True, type=Path,
                        help='输出 smoothed.md 路径')
    parser.add_argument('--model', default=DEFAULT_MODEL, help='LLM 模型 ID')
    parser.add_argument('--workers', type=int, default=3, help='并发 LLM 调用数')
    parser.add_argument('--max-chars', type=int, default=MAX_CHUNK_CHARS,
                        help=f'单块字符上限(默认 {MAX_CHUNK_CHARS},SKILL Gotcha)')
    parser.add_argument('--dry-run', action='store_true', help='只输出切分信息,不调 LLM')
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        log(f"ERROR: 输入文件不存在:{input_path}")
        return 1

    return smooth_document(
        input_path, args.output,
        model=args.model,
        workers=args.workers,
        max_chars=args.max_chars,
        dry_run=args.dry_run,
    )


if __name__ == '__main__':
    sys.exit(main())
