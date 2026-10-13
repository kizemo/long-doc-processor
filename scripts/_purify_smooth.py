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
    from scripts._llm_vision import call_vision, safe_llm_call  # noqa: E402
except ImportError:
    # 兜底:直接 import(脚本与 _llm_vision.py 同目录)
    from _llm_vision import call_vision, safe_llm_call  # noqa: E402
from utils import read_file_safely, write_file_safely, log, make_verbose_status_callback  # noqa: E402

# v4.21 C2 阶段:切分逻辑统一从 chunking.py 导入(消除重复定义)
try:
    from scripts.chunking import (  # noqa: E402
        H2Block,
        split_by_h2,
        split_oversized_h2,
        chunk_for_llm,
        _split_by_chars,
    )
except ImportError:
    from chunking import (  # type: ignore  # noqa: E402
        H2Block,
        split_by_h2,
        split_oversized_h2,
        chunk_for_llm,
        _split_by_chars,
    )


# 配置 ------------------------------------------------------------

# MAX_CHUNK_CHARS 由 chunking.DEFAULT_MAX_CHARS 提供(8000)
# 此处 re-export 以保持向后兼容(test_purify_smooth.py 仍 import 此常量)
try:
    from scripts.chunking import DEFAULT_MAX_CHARS as MAX_CHUNK_CHARS  # noqa: E402
except ImportError:
    from chunking import DEFAULT_MAX_CHARS as MAX_CHUNK_CHARS  # type: ignore  # noqa: E402

DEFAULT_MODEL = "claude-sonnet-4-5"


# Prompt 模板 --------------------------------------------------------

# v4.21 C1 收紧 prompt(v4.16 → v4.21 关键变化):
#   - 原 v4.16: "只改写不通顺的句子" + "同义改写 OK" → 允许改字面
#   - 新 v4.21: "只删不改" + "只重排不重写" → 严禁改字面
# 设计原理(踩坑模式 M-02 / M-10 衍生):
#   - LLM "改写" 会引入风格污染(把讲师原话改成书面语,丢失口语特征)
#   - v4.18 智篆项目证实:同义改写过度导致 NO-INFO-LOSS FAIL
#   - 重排(句序/合并短句)是 OK 的,因为不改变字面表述
SMOOTH_PROMPT_TEMPLATE = """你是中文电商培训讲义文稿的"通顺化清理"专家。

## 核心约束(v4.21 收紧)
**只删不改、只重排不重写**。
- ❌ **禁止同义改写原句**(把"嗯...今天讲电钻"改成"电钻是经典"是违规)
- ❌ **禁止润色用词**(把"标签权重"改成"权重标签"是违规)
- ❌ **禁止合并逻辑**相关的完整句子(只允许合并 ASR 串扰的同一句话)
- ✅ **允许删除** ASR 装饰 / 时间戳 / 粗口 / 错乱中英俄混杂
- ✅ **允许重排**:把两段短句换位,合并同一句话被拆成两半的情况

## 任务
对以下一份已净化的 Markdown 章节做通顺化清理,**只做删除和重排**,
**禁止改写原句字面表述**。

## 必须清理(7 类,只删不重写)
1. **行首时间戳**:`[HH:MM:SS]` / `[00:00:00]` / `(2026-09-12 ...)` 等转录痕迹 → 整行删除
2. **粗口**:骂人字眼 → 整词删除
3. **ASR 装饰**:`[掌声]` / `[笑声]` / `[音乐]` / `[沉默]` / `<|...|>` → 整段删除
4. **ASR 串扰**:同一句话被前后重复(上半句 + 下半句独立)→ 合并为一句(只去重,不润色)
5. **错乱中英俄混杂**:明显不属于这段话的英文单词残留 → 整词删除
6. **不通顺短句**:`嗯...` / `啊...` / `那个...` / `就是...` 等填充 → 整词删除
7. **重复词**:同一段内同一非专有名词 ≥ 3 次重复 → 删除多余(保留 2 次)

## 允许重排(不改变字面)
- 两段短句换位(如顺序影响理解)
- 同一句话被拆开的两半合并(ASR 串扰)
- 列表项顺序调整(若影响逻辑连贯性)

## 绝对禁止(违反则任务失败)
1. ❌ **同义改写原句字面**(最重要!v4.21 收紧)
2. ❌ 润色用词/调整语序(影响读者理解)
3. ❌ 新增任何原文没有的句子、案例、数据、概念
4. ❌ 删除原标题(## / ### / #### 不动,**只能清理标题下正文**)
5. ❌ 改变章节数量
6. ❌ 虚构案例、店铺、数据
7. ❌ 改动标题文字(包括编号)
8. ❌ 改动表格结构(列数 / 行数 / 表头)
9. ❌ 改动列表项数量

## 输出
- 完整输出 Markdown 章节(不是 diff)
- 保留所有 H2 / H3 / H4 标题**原样**
- 保留所有表格 / 列表 / 引用块 / 加粗 / 行内代码
- 保留所有图片引用(`![](...)`)
- 保留所有超链接(`[text](url)`)
- 句子字面与原文**一致**(只删 + 重排,不改字)

---

## 输入章节(请**只删不重写**,严禁改字面)

{h2_content}

---

## 输出章节(直接给完整 Markdown,不要解释)
"""


# 切分逻辑(从 chunking.py 导入,C2 阶段统一)------------------------
# H2Block / split_by_h2 / split_oversized_h2 已在文件顶部从 chunking 导入
# 旧 _split_by_chars 也已从 chunking 导入(若需要)

def smooth_block(block: H2Block, model: str = DEFAULT_MODEL, on_status=None) -> str:
    """调 LLM 对单个 H2 块做通顺化重写,返回新文本。

    容错:LLM 失败 / 返回非 markdown 时返回原文本(降级)。
    v4.21 改用 safe_llm_call 统一 timeout/retry/status 分流。
    v4.21 C4 阶段:on_status 回调(verbose 模式用)。
    """
    if not block.raw_text.strip():
        return block.raw_text

    prompt = SMOOTH_PROMPT_TEMPLATE.format(h2_content=block.raw_text)
    response, status = safe_llm_call(prompt, model=model, on_status=on_status)

    if status != "ok":
        log(f"[smooth] LLM status={status};降级保留原文本")
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
                    dry_run: bool = False,
                    verbose: bool = False) -> int:
    """主入口:读 cleaned.md → 切 H2 → 并发调 LLM → 写 smoothed.md。

    v4.21 C2 阶段:用 chunk_for_llm 替代手写 split_by_h2 + split_oversized_h2 组合。
    v4.21 C4 阶段:verbose=True 时,LLM status 写到 stderr(便于 debug)。
    """
    if not input_path.exists():
        log(f"ERROR: 输入文件不存在:{input_path}")
        return 1

    content = read_file_safely(input_path)
    # v4.21 C2:用 chunk_for_llm 统一入口(替代 split_by_h2 + split_oversized_h2 二次循环)
    preamble, all_chunks = chunk_for_llm(content, max_chars=max_chars)

    log(f"[smooth] 切分:共 {len(all_chunks)} 个 LLM 单元(每块 ≤ {max_chars} chars)")

    if dry_run:
        log("[smooth] dry-run 模式,跳过 LLM 调用")
        for i, c in enumerate(all_chunks, 1):
            log(f"  [{i}] {len(c.raw_text)} chars, title={'YES' if c.title_line else 'no'}")
            log(f"       preview: {c.raw_text[:60].strip()}...")
        return 0

    # v4.21 C4:verbose 模式时,L2 LLM 脚本也支持 status 回调
    on_status = make_verbose_status_callback("smooth") if verbose else None

    # 并发调 LLM
    smoothed_blocks: list[str] = [''] * len(all_chunks)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_idx = {
            executor.submit(smooth_block, block, model, on_status): i
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

    # 标题守恒校验(v4.21 C2:用 all_chunks 替代原 h2_blocks,因 chunk_for_llm 已含 H3 切分)
    original_titles = [H2Block(title_line='', content_lines=[], raw_text=b.raw_text)
                       for b in all_chunks]
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
    parser.add_argument('--verbose', action='store_true',
                        help='verbose 模式:LLM status 写到 stderr(v4.21 C4)')
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
        verbose=args.verbose,
    )


if __name__ == '__main__':
    sys.exit(main())
