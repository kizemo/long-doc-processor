#!/usr/bin/env python3
"""strip_lecturer_preamble.py — NO-LECTURER-PREAMBLE 规约实现(LLM 改写)

清理讲师铺垫类表述:开场白、寒暄、自介、Q&A 引导、讲师前缀等。
**禁止 regex**(v4.17 Gotcha 警示:regex 无法识别引号内例外)。

v4.21 增强(A3):按 H2 切分 + 并发 LLM(共用 scripts/chunking.py),
原单块全文送 LLM 改为 N 个 H2 块独立调,避免 30K 输入超 8K 单块限制。

用法:
  python scripts/strip_lecturer_preamble.py <input.md> -o <output.md> [--workers 3]
  python scripts/strip_lecturer_preamble.py <input.md> -o <output.md> --max-chars 8000

退出码:
  0 = 成功
  1 = 输入错误
  2 = LLM 调用全部失败 + 兜底写入 ERROR 标记
"""
from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from scripts._llm_vision import call_vision, safe_llm_call
except ImportError:
    from _llm_vision import call_vision, safe_llm_call  # type: ignore
from utils import read_file_safely, write_file_safely, log, make_verbose_status_callback  # noqa: E402
try:
    from scripts.chunking import chunk_for_llm, H2Block  # noqa: E402
except ImportError:
    from chunking import chunk_for_llm, H2Block  # type: ignore


DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_MAX_CHARS = 8000  # SKILL Gotcha:超出会让 LLM 自由发挥

# Prompt 模板
LECTURER_PREAMBLE_PROMPT = """你是中文电商培训讲义文稿的"讲师铺垫清理"专家。

## 任务
对以下 Markdown 章节做讲师铺垫清理:**去掉"讲师认为/说/指出/总结/提醒/举例/补充"等
主语前缀,直接陈述事实**。

## 必须清理
1. **讲师前缀主语**:`讲师认为...` / `讲师说...` / `讲师指出...` / `讲师总结...` /
   `讲师提醒...` / `讲师举例...` / `讲师补充...` / `讲师强调...`
   → 直接陈述:`标签权重...` / `数据表明...` / `案例显示...`
2. **学员互动前缀**:`有学员问...` / `学员提问...` / `学员搜索时...`
   → 直接陈述或转 FAQ:`FAQ:` 开头(若适合)
3. **讲师自我介绍铺垫**:`我是 X,做电商 N 年...` (重复出现)
   → 第 1 次可保留建立权威,后续删除
4. **课程安排**:`今天我们讲...` / `下面我们看...` / `这一节讲...`
   → 删除或转一句话目标陈述

## 例外(必须保留)
1. **引号内讲师原话**:`讲师说："..."` → 保留
2. **课程广告检测**(由 verify 工具兜底,本 prompt 不动)
3. **讲师资历建立权威段**(首次出现)→ 保留

## 绝对禁止
1. ❌ 删除原 H1/H2/H3/H4 标题(只能清理其下正文)
2. ❌ 新增原块没有的句子、案例、数据
3. ❌ 改变章节数量
4. ❌ 改动表格 / 列表结构
5. ❌ 改动标题文字

## 输出
完整输出 Markdown 章节(不是 diff)。

---

## 输入章节

{content}

---

## 输出章节(直接给 Markdown,不要解释)
"""


def strip_block(content: str, model: str = DEFAULT_MODEL, on_status=None) -> str:
    """对单块做讲师铺垫清理。LLM 失败时返回原内容(fail-soft)。

    v4.21 改用 safe_llm_call 统一 timeout/retry/status 分流。
    v4.21 C4 阶段:on_status 回调(verbose 模式用)。
    """
    if not content.strip():
        return content

    prompt = LECTURER_PREAMBLE_PROMPT.format(content=content)
    response, status = safe_llm_call(prompt, model=model, on_status=on_status)

    if status != "ok":
        log(f"[strip-lecturer] LLM status={status};降级保留原内容")
        return content

    if not response or not response.strip():
        return content

    # 去包装
    cleaned = _strip_md_wrapper(response)
    return cleaned if cleaned.strip() else content


def _strip_md_wrapper(text: str) -> str:
    m = re.search(r'^```(?:markdown)?\s*\n(.*?)\n```\s*$', text.strip(), re.DOTALL)
    return m.group(1) if m else text


def strip_document(
    input_path: Path,
    output_path: Path,
    model: str = DEFAULT_MODEL,
    workers: int = 3,
    max_chars: int = DEFAULT_MAX_CHARS,
    verbose: bool = False,
) -> int:
    """主入口(v4.21 改):读 input → chunk_by_h2 → 并发 LLM → 重组 → 写输出。"""
    if not input_path.exists():
        log(f"ERROR: 输入文件不存在:{input_path}")
        return 1

    content = read_file_safely(input_path)
    preamble, chunks = chunk_for_llm(content, max_chars=max_chars)
    log(f"[strip-lecturer] 切分:{len(chunks)} 个 H2 块 (max_chars={max_chars})")

    if not chunks:
        # 无 H2,整篇当 preamble 写回
        write_file_safely(output_path, content)
        log(f"[strip-lecturer] 无 H2,直接写原文 {output_path}")
        return 0

    on_status = make_verbose_status_callback("strip-lecturer") if verbose else None

    # 并发调 LLM
    cleaned_chunks: list[str] = [''] * len(chunks)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_idx = {
            executor.submit(strip_block, c.raw_text, model, on_status): i
            for i, c in enumerate(chunks)
        }
        for future in as_completed(future_to_idx):
            i = future_to_idx[future]
            try:
                cleaned_chunks[i] = future.result()
            except Exception as e:
                log(f"[strip-lecturer] chunk {i+1} 异常:{type(e).__name__}: {e};降级原内容")
                cleaned_chunks[i] = chunks[i].raw_text

    # 重组输出
    output = preamble + ''.join(cleaned_chunks)
    if not output.endswith('\n'):
        output += '\n'

    write_file_safely(output_path, output)
    log(f"[strip-lecturer] wrote {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description='NO-LECTURER-PREAMBLE 规约:清理讲师铺垫(LLM 改写,H2 chunked)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('input', type=Path, help='输入 md 路径')
    parser.add_argument('-o', '--output', type=Path, required=True, help='输出 md 路径')
    parser.add_argument('--model', default=DEFAULT_MODEL, help='LLM 模型 ID')
    parser.add_argument('--workers', type=int, default=3, help='并发 LLM 数')
    parser.add_argument('--max-chars', type=int, default=DEFAULT_MAX_CHARS,
                        help=f'单块字符上限(默认 {DEFAULT_MAX_CHARS},v4.21 A3 沉淀)')
    parser.add_argument('--verbose', action='store_true',
                        help='verbose 模式:LLM status 写到 stderr(v4.21 C4)')
    args = parser.parse_args()

    return strip_document(
        args.input, args.output,
        model=args.model,
        workers=args.workers,
        max_chars=args.max_chars,
        verbose=args.verbose,
    )


if __name__ == '__main__':
    sys.exit(main())
