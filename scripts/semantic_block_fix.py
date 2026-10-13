#!/usr/bin/env python3
"""semantic_block_fix.py — D3 D0 段级语义净化(v4.21 沉淀)

D0 阶段(B1 切块之前)必跑,阻断 LLM 净化放大 ASR 同音错词。
对每 H2 块做段级语义修复:
  - 断句合并(同一句话被拆成两半)
  - 移除 ASR 串扰短句
  - 修复不通顺短句(不改变字面)
  - 删除段首/段末孤立词(对 / 那个 / 对吧 / 是吧 / 嗯 / 啊 等)

设计要点(整合 M-13 / 阶段 A3):
  - 复用 chunking.py 统一切分(无重复定义)
  - 用 safe_llm_call(A1 沉淀)统一 timeout/retry
  - fail-soft:LLM 失败时返回原内容
  - --max-chars 控制单块上限(SKILL Gotcha:超 8K LLM 自由发挥)

用法:
  python scripts/semantic_block_fix.py <input.md> -o <output.md> [--workers 3]
  python scripts/semantic_block_fix.py <input.md> -o <output.md> --max-chars 8000

退出码:
  0 = 成功
  1 = 输入错误
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
try:
    from scripts._llm_vision import call_vision, safe_llm_call  # noqa: E402
except ImportError:
    from _llm_vision import call_vision, safe_llm_call  # type: ignore  # noqa: E402
from utils import read_file_safely, write_file_safely, log, make_verbose_status_callback  # noqa: E402
try:
    from scripts.chunking import chunk_for_llm  # noqa: E402
except ImportError:
    from chunking import chunk_for_llm  # type: ignore  # noqa: E402


DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_MAX_CHARS = 8000

# D0 段级净化 prompt(规约 26 NO-ORPHAN-WORDS + M-13 衍生)
# 设计:只做段级合并/删除,**不改字面**(与 C1 _purify_smooth 一致)
D0_SEMANTIC_PROMPT = """你是中文电商培训 ASR 转录稿的"段级语义净化 D0"专家(v4.21 D3)。

## 任务
对以下 Markdown 章节做**段级**修复,**只做合并/删除/重排,不改变字面表述**。

## 必须修复(段级)
1. **断句合并**:同一句话被 ASR 拆成两半(如"今天我们\n讲电钻"),合并为一句
2. **ASR 串扰**:同一段被前后重复,删除后半部分(只去重)
3. **段首/段末孤立词**:删除"对/那个/对吧/是吧/嗯/啊/哦"等填充词
4. **不通顺短句**:"嗯...就是...那个..."删除,保留实义部分

## 绝对禁止
1. ❌ 同义改写(把"今天讲电钻"改成"电钻是经典")
2. ❌ 润色用词(把"标签权重"改成"权重标签")
3. ❌ 删除原 H2/H3/H4 标题
4. ❌ 改变章节数量
5. ❌ 改动标题文字
6. ❌ 新增原块没有的句子

## 输出
完整输出 Markdown 章节(只做段级修改,字面尽量保留)。

---

## 输入章节

{content}

---

## 输出章节(直接给完整 Markdown,不要解释)
"""


def fix_block(content: str, model: str = DEFAULT_MODEL, on_status=None) -> str:
    """对单块做 D0 段级净化。LLM 失败时返回原内容(fail-soft)。"""
    if not content.strip():
        return content

    prompt = D0_SEMANTIC_PROMPT.format(content=content)
    response, status = safe_llm_call(prompt, model=model, on_status=on_status)

    if status != "ok":
        log(f"[d0] LLM status={status};降级保留原内容")
        return content

    if not response or not response.strip():
        return content

    cleaned = _strip_md_wrapper(response)
    return cleaned if cleaned.strip() else content


def _strip_md_wrapper(text: str) -> str:
    """去 LLM 响应外层 ```markdown ... ``` 包装。"""
    m = re.search(r'^```(?:markdown)?\s*\n(.*?)\n```\s*$', text.strip(), re.DOTALL)
    return m.group(1) if m else text


def semantic_block_fix(
    input_path: Path,
    output_path: Path,
    model: str = DEFAULT_MODEL,
    workers: int = 3,
    max_chars: int = DEFAULT_MAX_CHARS,
    verbose: bool = False,
) -> int:
    """D3 D0 段级语义净化主入口。"""
    if not input_path.exists():
        log(f"ERROR: 输入文件不存在:{input_path}")
        return 1

    content = read_file_safely(input_path)
    preamble, chunks = chunk_for_llm(content, max_chars=max_chars)
    log(f"[d0] 切分:{len(chunks)} 个 H2 块 (max_chars={max_chars})")

    if not chunks:
        write_file_safely(output_path, content)
        log(f"[d0] 无 H2,直接写原文 {output_path}")
        return 0

    on_status = make_verbose_status_callback("d0") if verbose else None

    cleaned_chunks: list[str] = [''] * len(chunks)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_idx = {
            executor.submit(fix_block, c.raw_text, model, on_status): i
            for i, c in enumerate(chunks)
        }
        for future in as_completed(future_to_idx):
            i = future_to_idx[future]
            try:
                cleaned_chunks[i] = future.result()
            except Exception as e:
                log(f"[d0] chunk {i+1} 异常:{type(e).__name__}: {e};降级原内容")
                cleaned_chunks[i] = chunks[i].raw_text

    output = preamble + ''.join(cleaned_chunks)
    if not output.endswith('\n'):
        output += '\n'

    write_file_safely(output_path, output)
    log(f"[d0] wrote {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description='v4.21 D3 D0 段级语义净化(在 B1 切块前阻断 LLM 放大 ASR 错词)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('input', type=Path, help='输入 raw transcript.md 路径')
    parser.add_argument('-o', '--output', type=Path, required=True, help='输出 cleaned.md 路径')
    parser.add_argument('--model', default=DEFAULT_MODEL, help='LLM 模型 ID')
    parser.add_argument('--workers', type=int, default=3, help='并发 LLM 数')
    parser.add_argument('--max-chars', type=int, default=DEFAULT_MAX_CHARS,
                        help=f'单块字符上限(默认 {DEFAULT_MAX_CHARS})')
    parser.add_argument('--verbose', action='store_true',
                        help='verbose 模式:LLM status 写到 stderr')
    args = parser.parse_args()

    return semantic_block_fix(
        args.input, args.output,
        model=args.model,
        workers=args.workers,
        max_chars=args.max_chars,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
