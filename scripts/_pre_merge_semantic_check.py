#!/usr/bin/env python3
"""_pre_merge_semantic_check.py — v4.15 合并前语义检查(必跑)

在分块 purify → merge 之间检测 4 类问题:
  1. **H3 编号跳号**:同 H2 下 H3 是否连续(1, 2, 3...);自动重排
  2. **ASR 错词高发词**:摩特图→模特图 / 点几率→点击率 等 16 类;自动字典替换
  3. **人称角色残留**:学员/讲师/主讲导师/大力老师/授课老师/教练;自动字典替换
  4. **chunk 收束句**:part 末尾 `因此/综上/总之` 破坏承接;仅报告(人工 review)

用法:
  python scripts/_pre_merge_semantic_check.py <input.md> -o <output.md>

退出码:
  0 = 自动修复完成
  1 = 有报告项需人工 review
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
from utils import read_file_safely, write_file_safely, log  # noqa: E402


# v4.22 F1:heading 正则统一从 chunking 导入(with-title 模式)
from chunking import _H2_TITLE_RE, _H3_TITLE_RE  # noqa: E402
_H2_RE = _H2_TITLE_RE
_H3_RE = _H3_TITLE_RE
# _H3_NUM_RE 是特定 pattern(捕获 H3 编号数字),保留本地
_H3_NUM_RE = re.compile(r'^###\s+(\d+)\.(\d+)\s+', re.MULTILINE)


# v4.15 changelog 16 类 ASR 错词高发词
ASR_TERM_FIXES: list[tuple[str, str]] = [
    ('摩特图', '模特图'),
    ('点几率', '点击率'),
    ('内幕', '类目'),
    ('气氛需求', '客户需求'),
    ('推广课', '推广课程'),
    ('解论', '结论'),
    ('加密货币', '价格带'),
    ('收到人数', '收货人数'),
    ('加入段', '价格段'),
    ('高科赞', '高客单'),
    ('主视图', '主图'),
    ('心客', '新客'),
    ('权占', '全站'),
    ('主途', '主图'),
    ('打爆', '打散'),  # 同店打爆→同店打散
    ('GGC', 'GGV'),
]


# v4.15 changelog 人称角色残留
ROLE_PERSONA_FIXES: list[tuple[str, str]] = [
    ('大力老师', ''),  # 删除整词
    ('授课老师', ''),
    ('主讲导师', ''),
    ('学员', '案例店铺'),  # 通用角色
    ('讲师', ''),
    ('教练', ''),
]


# chunk 收束句模式:检测"因此/综上/总之"出现在行末或段落末
# 简化版:行内任意位置出现这些词即报(因为 chunk 切割时这些词应在段尾)
CHUNK_END_PATTERNS = re.compile(r'(因此|综上|总之)', re.MULTILINE)


def check_h3_skip_numbering(text: str) -> tuple[str, int]:
    """检查 H3 编号跳号,自动重排,返回 (新文本, 修改次数)。"""
    lines = text.splitlines(keepends=True)
    new_lines: list[str] = []
    modifications = 0
    current_h2 = -1
    h3_expected = 1  # 当前 H2 下应出现的 H3 编号

    for line in lines:
        m_h2 = re.match(r'^##\s+(\d+)\.?\s+', line)
        if m_h2:
            current_h2 = int(m_h2.group(1)) - 1
            h3_expected = 1
            new_lines.append(line)
            continue

        m_h3 = _H3_NUM_RE.match(line)
        if m_h3:
            current_h3 = int(m_h3.group(2))
            if current_h3 != h3_expected:
                # 重排
                new_line = re.sub(r'^###\s+\d+\.\d+\s+',
                                   f'### {current_h2 + 1}.{h3_expected} ',
                                   line,
                                   count=1)
                new_lines.append(new_line)
                modifications += 1
            else:
                new_lines.append(line)
            h3_expected += 1
        else:
            new_lines.append(line)

    return ''.join(new_lines), modifications


def apply_dict_fixes(content: str, fixes: list[tuple[str, str]]) -> tuple[str, int]:
    """应用字典替换,返回 (新内容, 总修改次数)。"""
    total = 0
    for wrong, right in fixes:
        if right == '':
            # 删除:用更宽松的边界处理
            pattern = re.compile(rf'\s*{re.escape(wrong)}\s*')
            new_content, n = pattern.subn('', content)
        else:
            pattern = re.compile(re.escape(wrong))
            new_content, n = pattern.subn(right, content)
        total += n
        content = new_content
    return content, total


def check_chunk_end_sentences(text: str) -> list[tuple[int, str]]:
    """找所有 chunk 末尾的收束句(因此/综上/总之),返回 [(行号, 行内容), ...]。

    "chunk 末尾"判定:每行单独看是否匹配收束句模式(简化版)。
    """
    issues: list[tuple[int, str]] = []
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if CHUNK_END_PATTERNS.search(s):
            issues.append((i, line.rstrip()))
    return issues


def pre_merge_semantic_check(input_path: Path, output_path: Path) -> int:
    """主入口:读 input → 应用 3 类自动修复 + 1 类报告。"""
    if not input_path.exists():
        log(f"ERROR: 输入文件不存在:{input_path}")
        return 1

    text = read_file_safely(input_path)

    # 自动修复 1:H3 跳号
    text, n_h3 = check_h3_skip_numbering(text)
    log(f"[pre-merge] H3 跳号重排:{n_h3} 处")

    # 自动修复 2:ASR 错词
    text, n_asr = apply_dict_fixes(text, ASR_TERM_FIXES)
    log(f"[pre-merge] ASR 错词替换:{n_asr} 处")

    # 自动修复 3:人称角色
    text, n_role = apply_dict_fixes(text, ROLE_PERSONA_FIXES)
    log(f"[pre-merge] 角色残留清理:{n_role} 处")

    # 报告(不修):chunk 收束句
    chunk_ends = check_chunk_end_sentences(text)
    log(f"[pre-merge] chunk 收束句:{len(chunk_ends)} 处(报告,人工 review)")

    write_file_safely(output_path, text)
    log(f"[pre-merge] wrote {output_path}")

    if chunk_ends:
        log(f"[pre-merge] WARN: chunk 收束句需人工 review:")
        for line_no, line_content in chunk_ends[:5]:
            log(f"  - line {line_no}: {line_content[:60]}")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='v4.15 合并前语义检查')
    parser.add_argument('input', type=Path, help='输入 md 路径')
    parser.add_argument('-o', '--output', type=Path, required=True, help='输出 md 路径')
    args = parser.parse_args()

    return pre_merge_semantic_check(args.input, args.output)


if __name__ == '__main__':
    sys.exit(main())
