#!/usr/bin/env python3
"""last_section_reprocess.py — LAST-SECTION-COMPLETE / H3-NAMING-CONSISTENT / LOGIC-CHAIN

对 cleaned.md 末段独立 LLM 修复:
  - 末段 H2 必须含 ≥2 H3 + 5 类资产(概念/案例/数据/逻辑/表格)
  - H3 命名风格一致
  - 因果链完整(因为...所以...)

用法:
  python scripts/last_section_reprocess.py <cleaned.md> -o <last_quarter.md>
  python scripts/last_section_reprocess.py <cleaned.md> -o <last_quarter.md> --tail 0.25

退出码:
  0 = 成功(LLM 调用成功 或 fail-soft 保留原文)
  1 = 输入错误
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from scripts._llm_vision import call_vision, safe_llm_call
except ImportError:
    from _llm_vision import call_vision, safe_llm_call  # type: ignore
from utils import (  # noqa: E402
    read_file_safely, write_file_safely, log,
    make_verbose_status_callback, make_standard_parser, safe_main,
)


DEFAULT_MODEL = "claude-sonnet-4-5"
TAIL_RATIO = 0.25  # 默认末段 25%


LAST_SECTION_PROMPT = """你是中文电商培训讲义文稿的"末段修复"专家。

## 任务
对以下 cleaned.md 的**末段(最后 25%)**做独立 LLM 修复,确保:
1. **LAST-SECTION-COMPLETE**:末段 H2 必须含 ≥2 H3 + 5 类资产(概念/案例/数据/逻辑/表格)
2. **H3-NAMING-CONSISTENT**:H3 命名风格一致(同 H2 下用同一种格式,如"案例 1"/`### 案例`/数字编号 不可混用)
3. **LOGIC-CHAIN**:因果链完整(因 → 推论 → 结论 → 建议,每一环节不缺失)

## 必须保留
1. 原 H2 标题文字(不动)
2. 5 类核心资产(若有,务必保留)
3. 信息量守恒(不删实质内容)

## 绝对禁止
1. ❌ 新增原段没有的章节
2. ❌ 删除原 H2/H3/H4 标题
3. ❌ 改动表格结构
4. ❌ 虚构数据 / 案例

## 输出
完整末段 markdown(从末段 H2 开始到文件末尾)。

---

## 末段内容

{last_section}

---

## 输出末段(直接给 markdown,不要解释)
"""


def split_tail(text: str, tail_ratio: float = TAIL_RATIO) -> str:
    """取文本最后 tail_ratio 比例。简单做法:从末尾向上找第 1 个 H2 标题边界。"""
    # 从末尾向前找 N% 字符位置
    cut_offset = int(len(text) * (1 - tail_ratio))
    # 找该位置之后的第一个 H2 边界
    rest = text[cut_offset:]
    m = re.search(r'^## ', rest, re.MULTILINE)
    if m:
        return text[cut_offset + m.start():]
    # 否则直接切
    return text[cut_offset:]


def last_section_reprocess(input_path: Path, output_path: Path,
                            tail_ratio: float = TAIL_RATIO,
                            model: str = DEFAULT_MODEL,
                            verbose: bool = False) -> int:
    """主入口:读 cleaned → 切末段 → 调 LLM → 重组 + 写。"""
    if not input_path.exists():
        log(f"ERROR: 输入文件不存在:{input_path}")
        return 1

    full_text = read_file_safely(input_path)
    head, tail = _split_head_tail(full_text, tail_ratio)
    log(f"[last-section] 末段长度:{len(tail)} chars (总长 {len(full_text)})")

    # 调 LLM
    prompt = LAST_SECTION_PROMPT.format(last_section=tail)
    on_status = make_verbose_status_callback("last-section") if verbose else None
    response, status = safe_llm_call(prompt, model=model, on_status=on_status)
    if status != "ok":
        log(f"[last-section] LLM status={status};fail-soft 保留原文")
        response = ""

    if response and response.strip():
        new_tail = _strip_md_wrapper(response)
        if new_tail.strip():
            new_full = head + new_tail
            write_file_safely(output_path, new_full)
            log(f"[last-section] wrote {output_path}")
            return 0

    # fail-soft:写回原文
    write_file_safely(output_path, full_text)
    log(f"[last-section] LLM 返回空,降级写原文")
    return 0


def _split_head_tail(text: str, tail_ratio: float) -> tuple[str, str]:
    """把文本分为 head(前 N%) + tail(末 1-N%)。tail 从最近 H2 边界开始。

    算法:
      1. 按字符数切到 ~75% 位置(对应 tail_ratio=0.25)
      2. 向左找最近 H2 边界(切前最后 H2),保证 H2 在 tail 中
      3. 向右对齐到换行,避免切到行中间
      4. H2 之前的为 head,H2 之后为 tail
    """
    cut_offset = int(len(text) * (1 - tail_ratio))
    # 1. 找 cut_offset 之前的最近 H2 边界
    head_part = text[:cut_offset]
    last_h2 = None
    for m in re.finditer(r'^##\s+', head_part, re.MULTILINE):
        last_h2 = m
    if last_h2:
        # tail 从 H2 行开始
        tail_start = last_h2.start()
    else:
        # head_part 中无 H2,直接对齐到下一行
        nl_pos = text.find('\n', cut_offset)
        tail_start = nl_pos + 1 if nl_pos != -1 else cut_offset
    return text[:tail_start], text[tail_start:]


def _strip_md_wrapper(text: str) -> str:
    m = re.search(r'^```(?:markdown)?\s*\n(.*?)\n```\s*$', text.strip(), re.DOTALL)
    return m.group(1) if m else text


def main() -> int:
    # v4.22 F4:用 make_standard_parser 统一 boilerplate
    parser = make_standard_parser(
        'LAST-SECTION-COMPLETE 规约:末段独立修复(LLM)',
    )
    parser.add_argument('input', type=Path, help='cleaned.md 路径')
    parser.add_argument('-o', '--output', type=Path, required=True, help='输出 md 路径')
    parser.add_argument('--tail', type=float, default=TAIL_RATIO,
                        help=f'末段比例(默认 {TAIL_RATIO})')
    parser.add_argument('--model', default=DEFAULT_MODEL, help='LLM 模型 ID')
    args = parser.parse_args()

    return last_section_reprocess(
        args.input, args.output,
        tail_ratio=args.tail, model=args.model,
        verbose=args.verbose,
    )


if __name__ == '__main__':
    sys.exit(safe_main(main))
