#!/usr/bin/env python3
"""strip_role_persona.py — NO-ROLE-PERSONA 规约实现(LLM 改写)

清理正文中的"学员/讲师/主讲导师/大力老师/授课老师/教练"等角色主语,
改为通用角色:案例店铺 / 商家 / 运营团队 / 某案例。
**禁止 regex**(v4.17 Gotcha:regex 无法识别引号内讲师原话例外)。

用法:
  python scripts/strip_role_persona.py <input.md> -o <output.md> [--workers 3]

退出码:
  0 = 成功
  1 = 输入错误
  2 = LLM 调用全部失败 + 兜底写入 ERROR 标记
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
    from scripts._llm_vision import call_vision
except ImportError:
    from _llm_vision import call_vision  # type: ignore
from utils import read_file_safely, write_file_safely, log  # noqa: E402


DEFAULT_MODEL = "claude-sonnet-4-5"

# Prompt 模板
ROLE_PERSONA_PROMPT = """你是中文电商培训讲义文稿的"角色润色"专家。

## 任务
对以下 Markdown 章节做角色润色:**消除"学员/讲师/主讲导师/大力老师/授课老师/教练/学员提问"
等主语**,改为通用角色:`案例店铺 / 商家 / 运营团队 / 某案例`。

## 必须替换
| 原主语 | 改为 |
|---|---|
| `学员问...` / `学员提问...` / `学员搜索时...` / `学员常见的错误...` | `FAQ:` 开头 或直接陈述 |
| `学员在选品时...` | `选品时...` / `运营时...` |
| `讲师认为/说/指出/总结/举例` | 直接陈述事实 |
| `主讲导师 X 说...` | 直接陈述 |
| `大力老师 / 授课老师 / 教练` | 直接陈述 |
| `某学员提出` | `FAQ:` / `案例:` 开头 |
| `我(讲师)` | 直接陈述 |

## 例外(必须保留)
1. **引号内讲师/学员原话**:`讲师说："..."` / `学员说："..."` → 保留(包括 X 老师/某学员作为被引述者)
2. **建立权威的首次资历段**:`讲师 X,做电商 N 年` → 第 1 次可保留
3. **课程广告段**(由 verify 兜底,本 prompt 不动)

## 绝对禁止
1. ❌ 删除原标题(## / ### / #### 不动)
2. ❌ 新增原块没有的句子、案例、数据
3. ❌ 改变章节数量
4. ❌ 虚构数据或案例
5. ❌ 改动标题文字
6. ❌ 删除表格 / 列表结构

## 输出
完整输出 Markdown 章节。

---

## 输入章节

{content}

---

## 输出章节(直接给 Markdown,不要解释)
"""


def strip_block(content: str, model: str = DEFAULT_MODEL) -> str:
    """对单块做角色润色。LLM 失败时返回原内容(fail-soft)。"""
    if not content.strip():
        return content

    prompt = ROLE_PERSONA_PROMPT.format(content=content)
    try:
        response = call_vision(prompt, [], model=model)
    except Exception as e:
        log(f"[strip-persona] LLM 异常:{e};降级保留原内容")
        return content

    if not response or not response.strip():
        return content

    cleaned = _strip_md_wrapper(response)
    return cleaned if cleaned.strip() else content


def _strip_md_wrapper(text: str) -> str:
    m = re.search(r'^```(?:markdown)?\s*\n(.*?)\n```\s*$', text.strip(), re.DOTALL)
    return m.group(1) if m else text


def main() -> int:
    parser = argparse.ArgumentParser(
        description='NO-ROLE-PERSONA 规约:角色润色(LLM 改写)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('input', type=Path, help='输入 md 路径')
    parser.add_argument('-o', '--output', type=Path, required=True, help='输出 md 路径')
    parser.add_argument('--model', default=DEFAULT_MODEL, help='LLM 模型 ID')
    args = parser.parse_args()

    if not args.input.exists():
        log(f"ERROR: 输入文件不存在:{args.input}")
        return 1

    content = read_file_safely(args.input)
    cleaned = strip_block(content, args.model)
    write_file_safely(args.output, cleaned)
    log(f"[strip-persona] wrote {args.output}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
