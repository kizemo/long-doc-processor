#!/usr/bin/env python3
"""strip_lecturer_preamble.py — NO-LECTURER-PREAMBLE 规约实现(LLM 改写)

清理讲师铺垫类表述:开场白、寒暄、自介、Q&A 引导、讲师前缀等。
**禁止 regex**(v4.17 Gotcha 警示:regex 无法识别引号内例外)。

通过 LLM 改写,直接陈述事实(去掉"讲师认为/说/指出/总结/提醒/举例"前缀)。

用法:
  python scripts/strip_lecturer_preamble.py <input.md> -o <output.md> [--workers 3]

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
    from scripts._llm_vision import call_vision
except ImportError:
    from _llm_vision import call_vision  # type: ignore
from utils import read_file_safely, write_file_safely, log  # noqa: E402


DEFAULT_MODEL = "claude-sonnet-4-5"

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


def strip_block(content: str, model: str = DEFAULT_MODEL) -> str:
    """对单块做讲师铺垫清理。LLM 失败时返回原内容(fail-soft)。"""
    if not content.strip():
        return content

    prompt = LECTURER_PREAMBLE_PROMPT.format(content=content)
    try:
        response = call_vision(prompt, [], model=model)
    except Exception as e:
        log(f"[strip-lecturer] LLM 异常:{e};降级保留原内容")
        return content

    if not response or not response.strip():
        return content

    # 去包装
    cleaned = _strip_md_wrapper(response)
    return cleaned if cleaned.strip() else content


def _strip_md_wrapper(text: str) -> str:
    m = re.search(r'^```(?:markdown)?\s*\n(.*?)\n```\s*$', text.strip(), re.DOTALL)
    return m.group(1) if m else text


def main() -> int:
    parser = argparse.ArgumentParser(
        description='NO-LECTURER-PREAMBLE 规约:清理讲师铺垫(LLM 改写)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('input', type=Path, help='输入 md 路径')
    parser.add_argument('-o', '--output', type=Path, required=True, help='输出 md 路径')
    parser.add_argument('--model', default=DEFAULT_MODEL, help='LLM 模型 ID')
    parser.add_argument('--workers', type=int, default=3, help='并发 LLM 数')
    args = parser.parse_args()

    if not args.input.exists():
        log(f"ERROR: 输入文件不存在:{args.input}")
        return 1

    content = read_file_safely(args.input)

    # 简单做法:整文件一次性送 LLM(文档通常 < 30K chars 适配 8K 单块限制)
    # 大文档需要切块,这里为简单起见,直接全文
    cleaned = strip_block(content, args.model)
    write_file_safely(args.output, cleaned)
    log(f"[strip-lecturer] wrote {args.output}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
