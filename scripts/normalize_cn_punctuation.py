#!/usr/bin/env python3
"""normalize_cn_punctuation.py — v4.21 中文标点规范化(NO-HALF-WIDTH-PUNCT-IN-CN-CONTEXT)

## 背景
中文培训讲义/课程笔记常出现"半角英式标点 + 中文正文"的混杂排版,严重影响阅读体验。
本脚本在文本行进过程中以**行级 + 段落级**两层防护,把 12 类半角标点转为中文全角,
同时严格**不动**:
  - Markdown 结构(`#`, `-`(列表), `|`(表格), `>`(引用), `[](...)` 链接, `![]()` 图片)
  - 代码块(` ``` ... ``` ` 三行围栏 / inline `` ` ``)
  - `URL`(http/https)
  - 数字上下文(`2024-09-02`, `1.`, `2-3 倍`, `1,000`)
  - 英文短语(`API`, `JSON`, `OAIPL`)

## 替换映射 (12 类,使用显式 Unicode codepoint 避免输入法/编辑器干扰)

| 半角 | 全角 | Unicode |
|------|--------|---------|
| `,` | `,` | U+FF0C |
| `;` | `;` | U+FF1B |
| `.` | `。` | U+3002 |
| `:` | `:` | U+FF1A |
| `!` | `!` | U+FF01 |
| `?` | `?` | U+FF1F |
| `(` | `(` | U+FF08 |
| `)` | `)` | U+FF09 |
| `"..."` | `"..."` | U+201C / U+201D |
| `'...'` | `'...'` | U+2018 / U+2019 |
| `--` | `——` | U+2014 × 2 |
| `...` | `……` | U+2026 × 2 |

## 用法
    python scripts/normalize_cn_punctuation.py <input.md> <output.md>
    python scripts/normalize_cn_punctuation.py <input.md> -i  # 原地覆盖

## 退出码
    0 = 成功
    1 = 文件读写错误
    2 = 参数错误

## v4.21 新增 (2026-10-14 玺承 2026 双十一项目反馈)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
from utils import read_file_safely, write_file_safely, log  # noqa: E402


# 显式 Unicode 转义 — 避免输入法/编辑器把全角转半角 --------
# 改用 chr() 取字符,杜绝 Write 工具被字符转换工具串改
_FULLWIDTH = {
    ',': chr(0xFF0C),    # 全角逗号
    ';': chr(0xFF1B),    # 全角分号
    '.': chr(0x3002),    # 句号
    ':': chr(0xFF1A),    # 全角冒号
    '!': chr(0xFF01),    # 全角叹号
    '?': chr(0xFF1F),    # 全角问号
    '(': chr(0xFF08),    # 全角左括号
    ')': chr(0xFF09),    # 全角右括号
    '...': chr(0x2026) + chr(0x2026),    # 中文省略号
    '——': chr(0x2014) + chr(0x2014),    # 中文 em-dash
}
_FW_COMMA = _FULLWIDTH[',']
_FW_SEMI = _FULLWIDTH[';']
_FW_PERIOD = _FULLWIDTH['.']
_FW_COLON = _FULLWIDTH[':']
_FW_EXCL = _FULLWIDTH['!']
_FW_QUEST = _FULLWIDTH['?']
_FW_LPAREN = _FULLWIDTH['(']
_FW_RPAREN = _FULLWIDTH[')']
_FW_ELLIPSIS = _FULLWIDTH['...']
_FW_EMDASH = _FULLWIDTH['——']

# 中文弯引号 **必须单独定义**。
# 2026-10-24 实测坑：原先它们被塞进 _FULLWIDTH，key 写成 '"' / "'" 各两次 ——
# 后者覆盖前者，导致 _FW_LDQUO 和 _FW_RDQUO 实际都是右引号 chr(0x201D)。
# 结果：每一对半角引号都被渲染成 ”内容”，左引号全部丢失
#（实测 8 对 → 正文左引号 27 个 / 右引号 43 个，差 16）。
_FW_LDQUO = chr(0x201C)   # 中文左双引号 “
_FW_RDQUO = chr(0x201D)   # 中文右双引号 ”
_FW_LSQUO = chr(0x2018)   # 中文左单引号 ‘
_FW_RSQUO = chr(0x2019)   # 中文右单引号 ’


# 正则常量 ---------------------------------------------------------

_CN = r'[\u4e00-\u9fff]'
# 包括:
#   - \u4e00-\u9fff  CJK 统一表意
#   - \u3000-\u303f  CJK 符号和标点(含全角空格)
#   - \uff00-\uffef  半角/全角形式(含全角字母/标点)
_CN_OR_BIG = '[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]'

# 上下文友好模式:含中文+ markdown 标记(空格/换行/`*`/`-`/`+`/数字/单位符/拉丁字母)
# 用于 lookbehind/lookahead,让 `**text**,**text**` 与 `(8月28日)` `10%-20%`
# 与 `(M几级)` 与 `"text",text` (中英引号后接逗号) 这类含混合上下文的也匹配。
_CN_OR_MD = r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\u2018\u2019\u201c\u201d\s*\-+\d%°a-zA-Z]'

# 跳过区段(inline 级别):
#   - inline code: `xxx`
#   - image syntax: ![alt](url)
#   - link syntax: [text](url)
#   - bare URL: http(s)://...
#   - 数字内部连接符: 3.5 / 1,000 / 10:30  (2026-10-24 回归: 小数被写成 "3。5")
_INLINE_SKIP = re.compile(
    r"(`[^`]+`|!\[[^\]]*\]\([^)]+\)|\[[^\]]+\]\([^)]+\)|https?://\S+|\d+(?:[.,:]\d+)+)"
)

# markdown 有序列表标记(行首 "1. " / "12. ")—— 必须原样保留。
# 2026-10-24 回归: 原先 `_PERIOD_BETWEEN_CN` 把 "1. " 的点号全角化成 "1。",
# Markdown 有序列表结构被摧毁(渲染成普通段落)。
_OL_LIST_MARKER = re.compile(r'^(\s*\d+\.)(\s+)')

# 中文(或上下文) **之间** 的逗号 — 支持 `**text**,text` 模式
_COMMA_BETWEEN_CN = re.compile(rf'(?<={_CN_OR_MD}),(?={_CN_OR_MD})')
# 中文(或上下文) 分号
_SEMI_BETWEEN_CN = re.compile(rf'(?<={_CN_OR_MD});(?={_CN_OR_MD})')
# 中文(或上下文) 句点
_PERIOD_BETWEEN_CN = re.compile(rf'(?<={_CN_OR_MD})\.(?={_CN_OR_MD})')
# 中文 + 半角句号 + 行末/空白后
# 2026-10-24 补齐: 逗号/冒号/叹号/问号都有"行末"规则,唯独句号没有 → 行为不一致。
# 安全前提:
#   - 前一个字符必须是中文/全角标点(_CN_OR_BIG 不含 ASCII 字母数字与句点)
#     ⇒ "README.md." / "i.e." / "No." / "3.5" / "1. " 都不会被误伤
#   - 后一个字符必须是空白或行末 ⇒ "等等..." 里的三个点都不匹配(后一个点是句点)
_PERIOD_END_OF_LINE = re.compile(rf'(?<={_CN_OR_BIG})\.(?=\s|$)')
# 中文(或上下文) 冒号 — 双向 + 行末 (后跟换行/字符串结尾)
_COLON_BETWEEN_CN = re.compile(rf'(?<={_CN_OR_MD}):(?={_CN_OR_MD})')
_COLON_END_OF_LINE = re.compile(rf'(?<={_CN_OR_BIG}):(?=\s|$)')
# 中文(或上下文) 叹号
_EXCLAIM_AFTER_CN = re.compile(rf'(?<={_CN_OR_MD})!')
# 中文(或上下文) 问号
_QUESTION_AFTER_CN = re.compile(rf'(?<={_CN_OR_MD})\?')
# 左括号:后跟中文或上下文
_LPAREN_OPEN = re.compile(rf'\((?={_CN_OR_MD})')
# 右括号:前是中文或上下文
_LPAREN_CLOSE = re.compile(rf'(?<={_CN_OR_MD})\)')
# 中文 + 半角逗号 + 行末(用于"基本盘:"等)
_COMMA_END_OF_LINE = re.compile(rf'(?<={_CN_OR_BIG}),(?=\s|$)')

# 引号(中文引号自动开/合交替)
_DOUBLE_QUOTE = re.compile(r'"([^"\n]+)"')
_SINGLE_QUOTE = re.compile(r"'([^'\n]+)'")

# 连续省略号
_ELLIPSIS = re.compile(r'\.{3,}')

# em-dash (-- → ——)
_EMDASH_BETWEEN_CN = re.compile(rf'(?<={_CN_OR_BIG})\s--\s(?={_CN_OR_BIG})')


# YAML frontmatter 最大行数上限 —— 超过则认为首个 --- 是水平线,不存在 frontmatter
_FRONTMATTER_MAX_LINES = 200

# 转换函数 -------------------------------------------------------

class PunctuationState:
    """逐行处理时维护的状态。"""

    def __init__(self):
        self.in_fenced_code = False
        self.dquote_open = False  # 中文双引号开/合交替
        self.squote_open = False  # 中文单引号开/合交替

    def transform_line(self, line: str) -> tuple[str, dict]:
        """处理单行,返回 (新行, 替换统计 dict)。"""
        counts: dict[str, int] = {}
        stripped = line.lstrip()

        # fenced code 切换
        if stripped.startswith('```'):
            self.in_fenced_code = not self.in_fenced_code
            return line, counts
        if self.in_fenced_code:
            return line, counts

        # 跳过 markdown 表格行(以 | 开头或 ---|---| 之类的纯表格行)
        if stripped.startswith('|') or stripped.startswith('|---') or re.match(r'^[\s|:-]+$', stripped):
            return line, counts

        # 跳过 markdown 标题行(以 # 开头,虽然内部不应有半角)
        if stripped.startswith('#'):
            return line, counts

        # 保护 markdown 有序列表标记(行首 "1. ")—— 2026-10-24 回归:
        #   "1. **因为**..." 曾被规范化成 "1。 **因为**...", 有序列表退化成普通段落。
        ol_prefix = ''
        m_ol = _OL_LIST_MARKER.match(line)
        if m_ol:
            ol_prefix = m_ol.group(0)
            line = line[m_ol.end():]

        # 跳过列表项标记(以 `- ` `* ` `数字. ` 开头但内容很短的)
        # 注意:正文可能以 `- `开头但是表格内容,这里只跳过明显是 list item 的
        if re.match(r'^\s*([-*+]|\d+\.)\s+\S', line) and len(line) < 200:
            # 短 list item,不替换
            pass  # 仍然要转换

        # 行内标记先保护(inline code / 链接 / 图片 / URL / 数字上下文)
        parts = _INLINE_SKIP.split(line)
        new_parts = []
        for part in parts:
            if _INLINE_SKIP.fullmatch(part):
                new_parts.append(part)
                continue
            new_part, cnt = self._transform_segment(part)
            for k, v in cnt.items():
                counts[k] = counts.get(k, 0) + v
            new_parts.append(new_part)

        return ol_prefix + ''.join(new_parts), counts

    def _transform_segment(self, seg: str) -> tuple[str, dict]:
        """对纯文本段做标点转换。"""
        counts: dict[str, int] = {}

        # ===== 第一步:引号转换(必须在其他标点之前,避免 ASCII 引号阻断 lookbehind) =====

        # 8. 半角双引号 → 中文双引号
        #    一对半角引号本身就一定是「开 → 合」，所以恒定渲染成 “...”。
        #    2026-10-24 修正：原先这里按 dquote_open 交替，第 2 对被渲染成 ”...“，
        #    右引号跑到左边；中文里这是错的。
        def _dquote_repl(m):
            inner = m.group(1)
            self.dquote_open = not self.dquote_open
            return f'{_FW_LDQUO}{inner}{_FW_RDQUO}'
        seg, n = _DOUBLE_QUOTE.subn(_dquote_repl, seg)
        if n: counts['双引号→中文'] = counts.get('双引号→中文', 0) + n

        # 9. 半角单引号 → 中文单引号(同双引号,恒定「开 → 合」)
        def _squote_repl(m):
            inner = m.group(1)
            self.squote_open = not self.squote_open
            return f'{_FW_LSQUO}{inner}{_FW_RSQUO}'
        seg, n = _SINGLE_QUOTE.subn(_squote_repl, seg)
        if n: counts['单引号→中文'] = counts.get('单引号→中文', 0) + n

        # ===== 第二步:其他标点(在中文上下文中替换) =====

        # 1. 半角逗号 → 中文逗号 (中文之间)
        seg, n = _COMMA_BETWEEN_CN.subn(_FW_COMMA, seg)
        if n: counts[f',→{_FW_COMMA}'] = counts.get(f',→{_FW_COMMA}', 0) + n

        # 2. 半角分号 → 中文分号 (中文之间)
        seg, n = _SEMI_BETWEEN_CN.subn(_FW_SEMI, seg)
        if n: counts[f';→{_FW_SEMI}'] = counts.get(f';→{_FW_SEMI}', 0) + n

        # 3. 半角句号 → 中文句号 (中文之间)
        seg, n = _PERIOD_BETWEEN_CN.subn(_FW_PERIOD, seg)
        if n: counts[f'.→{_FW_PERIOD}'] = counts.get(f'.→{_FW_PERIOD}', 0) + n

        # 3b. 半角句号 → 中文句号 (中文 + 行末/空白)
        seg, n = _PERIOD_END_OF_LINE.subn(_FW_PERIOD, seg)
        if n: counts[f'.→{_FW_PERIOD}'] = counts.get(f'.→{_FW_PERIOD}', 0) + n

        # 4. 半角冒号 → 中文冒号 (中文之间 + 行末)
        seg, n = _COLON_BETWEEN_CN.subn(_FW_COLON, seg)
        if n: counts[f':→{_FW_COLON}'] = counts.get(f':→{_FW_COLON}', 0) + n
        seg, n = _COLON_END_OF_LINE.subn(_FW_COLON, seg)
        if n: counts[f':→{_FW_COLON}'] = counts.get(f':→{_FW_COLON}', 0) + n

        # 4b. 半角逗号 → 中文逗号 (中文 + 行末,基本盘:,)
        seg, n = _COMMA_END_OF_LINE.subn(_FW_COMMA, seg)
        if n: counts[f',→{_FW_COMMA}'] = counts.get(f',→{_FW_COMMA}', 0) + n

        # 5. 半角叹号 → 中文叹号
        seg, n = _EXCLAIM_AFTER_CN.subn(_FW_EXCL, seg)
        if n: counts[f'!→{_FW_EXCL}'] = counts.get(f'!→{_FW_EXCL}', 0) + n

        # 6. 半角问号 → 中文问号
        seg, n = _QUESTION_AFTER_CN.subn(_FW_QUEST, seg)
        if n: counts[f'?→{_FW_QUEST}'] = counts.get(f'?→{_FW_QUEST}', 0) + n

        # 7. 半角括号 → 中文括号
        seg, n = _LPAREN_OPEN.subn(_FW_LPAREN, seg)
        if n: counts[f'(→{_FW_LPAREN}'] = counts.get(f'(→{_FW_LPAREN}', 0) + n
        seg, n = _LPAREN_CLOSE.subn(_FW_RPAREN, seg)
        if n: counts[f')→{_FW_RPAREN}'] = counts.get(f')→{_FW_RPAREN}', 0) + n

        # 10. 连续省略号 → 中文省略号
        seg, n = _ELLIPSIS.subn(_FW_ELLIPSIS, seg)
        if n: counts['...→……'] = counts.get('...→……', 0) + n

        # 11. em-dash (-- → ——) 在中文之间
        seg, n = _EMDASH_BETWEEN_CN.subn(_FW_EMDASH, seg)
        if n: counts['--→——'] = counts.get('--→——', 0) + n

        return seg, counts


def detect_frontmatter_range(lines: list[str]) -> tuple[int, int] | None:
    """识别 YAML frontmatter 区域,返回 (起始行号, 结束行号)(含)。

    规则(与 Jekyll / Obsidian / pandoc 一致):
    - 首行 strip 后必须是 `---`
    - 从第 2 行开始找闭合标记 `---` 或 `...`(YAML 文档结束符)
    - 闭合标记必须在 _FRONTMATTER_MAX_LINES 行以内,否则认为"首个 --- 是水平线",
      不存在 frontmatter

    2026-10-24 实测坑：原先没有这层保护，frontmatter 里的
    `type: lecture-notes` 被改成 `type： lecture-notes`、`.mp4` 被改成 `。mp4`，
    YAML 直接失效 → verify_all 的 FRONTMATTER 规则报 `'str' object has no attribute 'get'`。
    """
    if not lines:
        return None
    if lines[0].strip() != '---':
        return None
    limit = min(len(lines), _FRONTMATTER_MAX_LINES)
    for i in range(1, limit):
        s = lines[i].strip()
        if s == '---' or s == '...':
            return 0, i
    return None


def normalize_markdown(text: str) -> tuple[str, dict]:
    """规范化整篇 markdown,返回 (新文本, 总统计)。

    YAML frontmatter 区域**整段原样返回**(见 detect_frontmatter_range)。
    """
    state = PunctuationState()
    total_counts: dict[str, int] = {}
    output = []
    lines = text.split('\n')
    fm = detect_frontmatter_range(lines)
    fm_start, fm_end = fm if fm else (-1, -1)
    for idx, line in enumerate(lines):
        if fm_start <= idx <= fm_end:
            output.append(line)  # frontmatter 原样保留
            continue
        new_line, cnt = state.transform_line(line)
        output.append(new_line)
        for k, v in cnt.items():
            total_counts[k] = total_counts.get(k, 0) + v
    return '\n'.join(output), total_counts


# CLI --------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='中文标点规范化(NO-HALF-WIDTH-PUNCT-IN-CN-CONTEXT)')
    parser.add_argument('input', nargs='?', help='输入 md 路径')
    parser.add_argument('output', nargs='?', help='输出 md 路径')
    parser.add_argument('-i', '--in-place', action='store_true', help='原地覆盖')
    args = parser.parse_args()

    if not args.input:
        parser.error('缺少输入文件')

    inp = Path(args.input)
    if args.in_place:
        out = inp
    elif args.output:
        out = Path(args.output)
    else:
        parser.error('需要 <input> <output> 或 -i/--in-place')

    text = read_file_safely(inp)
    new_text, counts = normalize_markdown(text)
    write_file_safely(out, new_text)

    log(f"normalize_cn_punctuation: {inp.name}")
    total = 0
    for k, v in counts.items():
        if v > 0:
            log(f"  {k}: {v} 次")
            total += v
    log(f"总计 {total} 处替换 → {out}")


if __name__ == '__main__':
    main()