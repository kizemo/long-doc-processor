#!/usr/bin/env python3
"""glossary_expand.py — v4.11 从术语表 G 节生成 asr_error_dict.json

读 `references/电商术语表.md` 的 G 节(ASR 易错词映射),反向生成
`asr_error_dict.json`,供 `_post_terms_fix.py` / `strip_asr_terms.py` 加载。

用法:
  python scripts/glossary_expand.py --out asr_error_dict.json
  python scripts/glossary_expand.py --source references/电商术语表.md --out asr_error_dict.json

输出格式(JSON):
  [
    {"wrong": "皮气护理", "right": "皮质护理"},
    ...
  ]

G 节识别:扫 markdown,找 `## G. ASR 易错` 或 `## G` 或 `### G. ASR 易错词` 类标题,
提取其下所有 `- 错词 → 正确词` 形式的条目。

退出码:
  0 = 成功
  1 = 输入错误
  2 = 未找到 G 节(自动 fallback 内置默认)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
from utils import log  # noqa: E402


DEFAULT_SOURCE = Path(__file__).resolve().parent.parent / 'references' / '电商术语表.md'

# 内置默认 G 节(若源文件不存在,用此兜底)
BUILTIN_G_SECTION = """## G. ASR 易错词

### G.1 电商通用

- 皮气护理 → 皮质护理
- 牛仔库 → 牛仔裤
- 心中式 → 新中式
- 带梦图 → 带门图
- 最大化作间法 → 最大化筛选法
- 气氛需求 → 客户需求
- 推广课 → 推广课程
- 数据筛毯 → 数据筛选
- 收到人数 → 收货人数
- 摩特图 → 模特图
- 演书服 → 演出服
- 掀车 → 四轮推车
- 石木床 → 实木床
- 主视图 → 主图
- 高科赞 → 高客单
- 点击力 → 点击率
- 权占 → 全站
- 空投产 → 控投产
- 空点机 → 控点机
- 汉堡国 → 汉堡包
- 心客 → 新客
- 打笔 → 打比
- 放弹 → 放量
- 蒸柔 → 蒸馏
- 继程 → 决策
- 燃品 → 产品
- 主途 → 主图
- 复构 → 复购
- 解论 → 结论
- 内幕 → 类目
- GGC → GGV
- AI助力 → AI 助力
"""


# G 节起始正则(支持多种标题)
_G_SECTION_RE = re.compile(
    r'^#{1,3}\s+G[.\s]+(?:ASR[.\s]*易错(?:词)?|asr[.\s]*errors?).*$',
    re.MULTILINE | re.IGNORECASE
)

# 条目正则 `- wrong → right`
_ENTRY_RE = re.compile(r'^\s*[-*]\s*([^→\n]+?)\s*→\s*([^\n]+?)\s*$', re.MULTILINE)


def find_g_section(text: str) -> tuple[int, int] | None:
    """找 G 节位置,返回 (start_offset, end_offset)。"""
    m = _G_SECTION_RE.search(text)
    if not m:
        return None
    start = m.end()
    # 找下一个同级或更高级标题
    section_header = m.group(0)
    header_level = section_header.count('#')
    rest = text[start:]
    # 找下一个同/更高 level 标题
    next_h_re = re.compile(r'^#{1,' + str(header_level) + r'}\s+', re.MULTILINE)
    nm = next_h_re.search(rest)
    end = start + nm.start() if nm else len(text)
    return (start, end)


def parse_g_section(section_text: str) -> list[dict[str, str]]:
    """从 G 节文本解析条目。"""
    pairs: list[dict[str, str]] = []
    for m in _ENTRY_RE.finditer(section_text):
        wrong = m.group(1).strip()
        right = m.group(2).strip()
        # 过滤掉表头行
        if wrong in ('wrong', 'right', 'key') or len(wrong) > 15 or len(right) > 15:
            continue
        pairs.append({'wrong': wrong, 'right': right})
    return pairs


def dedupe_pairs(pairs: list[dict[str, str]]) -> list[dict[str, str]]:
    """去重(保留首次出现)。"""
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for p in pairs:
        key = (p['wrong'], p['right'])
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def expand_glossary(source_path: Path = DEFAULT_SOURCE,
                     fallback: bool = True) -> tuple[list[dict], str]:
    """主入口:读源 → 解析 → 输出。

    Returns: (pairs, source_label)
    source_label ∈ {"file:<path>", "builtin"}
    """
    if source_path and source_path.exists():
        log(f"[glossary] 读 {source_path}")
        text = source_path.read_text(encoding='utf-8')
        section = find_g_section(text)
        if section:
            start, end = section
            pairs = parse_g_section(text[start:end])
            log(f"[glossary] G 节解析: {len(pairs)} 条")
            return dedupe_pairs(pairs), f"file:{source_path}"
        log(f"[glossary] 未找到 G 节,尝试 fallback")
        if fallback:
            pairs = parse_g_section(BUILTIN_G_SECTION)
            return dedupe_pairs(pairs), "builtin"
        return [], "file:<empty>"
    else:
        log(f"[glossary] 源文件不存在:{source_path},使用内置")
        pairs = parse_g_section(BUILTIN_G_SECTION)
        return dedupe_pairs(pairs), "builtin"


def main() -> int:
    parser = argparse.ArgumentParser(
        description='v4.11 从术语表 G 节生成 asr_error_dict.json',
    )
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE,
                        help=f'源 markdown 路径(默认 {DEFAULT_SOURCE.name})')
    parser.add_argument('-o', '--output', type=Path, default=Path('asr_error_dict.json'),
                        help='输出 JSON 路径')
    args = parser.parse_args()

    try:
        pairs, source = expand_glossary(args.source)
    except (OSError, FileNotFoundError) as e:
        log(f"ERROR: {e}")
        return 1

    output = json.dumps(pairs, ensure_ascii=False, indent=2)
    args.output.write_text(output, encoding='utf-8')
    log(f"[glossary] wrote {args.output} ({len(pairs)} pairs from {source})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
