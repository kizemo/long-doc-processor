#!/usr/bin/env python3
"""test_normalize_cn_punctuation.py — 单元测试(v4.21)

覆盖 12 类标点 + 4 类例外 + 边界 case:
- 中文之间全角转换
- 行末全角转换(中文 + 标点 + EOL)
- markdown 加粗标记上下文
- 中英混排(`(M几级)` `(8月28日)` `10%-20%`)
- 中英引号后接标点(`"text",text`)
- 表格行 / 列表项 / 标题 / fenced code 保护
"""
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / 'scripts'))

from normalize_cn_punctuation import normalize_markdown  # noqa: E402

# 显式 Unicode 常量,避免编辑器字符转换
FW_COMMA = chr(0xFF0C)
FW_SEMI = chr(0xFF1B)
FW_PERIOD = chr(0x3002)
FW_COLON = chr(0xFF1A)
FW_EXCL = chr(0xFF01)
FW_QUEST = chr(0xFF1F)
FW_LPAREN = chr(0xFF08)
FW_RPAREN = chr(0xFF09)
FW_LDQUO = chr(0x201C)
FW_RDQUO = chr(0x201D)
FW_LSQUO = chr(0x2018)
FW_RSQUO = chr(0x2019)
FW_ELLIPSIS = chr(0x2026) + chr(0x2026)
FW_EMDASH = chr(0x2014) + chr(0x2014)


def test_basic_chinese_comma():
    text = "今天,我们开会,讨论项目。"
    result, counts = normalize_markdown(text)
    assert FW_COMMA in result, f"expected full-width comma in {result!r}"
    assert result.count(',') == 0, f"should remove all half-width commas: {result!r}"


def test_chinese_semicolon():
    text = "甲;乙;丙"
    result, counts = normalize_markdown(text)
    assert FW_SEMI in result, f"expected full-width semicolon in {result!r}"


def test_chinese_period():
    text = "这是结束.这是下句"
    result, counts = normalize_markdown(text)
    assert FW_PERIOD in result, f"expected full-width period in {result!r}"


def test_chinese_colon():
    text = "目标:完成双十一备战"
    result, counts = normalize_markdown(text)
    assert FW_COLON in result, f"expected full-width colon in {result!r}"


def test_chinese_parens():
    text = "(中文括号)测试"
    result, counts = normalize_markdown(text)
    assert FW_LPAREN in result, f"expected full-width left paren in {result!r}"
    assert FW_RPAREN in result, f"expected full-width right paren in {result!r}"


def test_chinese_quotes_double():
    text = '"你好,世界"他说'
    result, counts = normalize_markdown(text)
    assert FW_LDQUO in result or FW_RDQUO in result, f"expected Chinese quote in {result!r}"


def test_double_quotes_paired_left_right():
    """回归(2026-10-24)：一对半角引号必须渲染成 “...”，不能是 ”...”。

    原 bug：_FULLWIDTH 里 '"' 这个 key 写了两次(左/右引号)，后者覆盖前者，
    于是 _FW_LDQUO 实际等于右引号 → 每一对半角引号都变成 ”...”，左引号全部丢失。
    旧测试只断言 `LDQUO in result or RDQUO in result`(OR)，抓不到这个 bug。
    """
    text = '他说"这是第一个"，然后说"这是第二个"。'
    result, counts = normalize_markdown(text)
    assert result.count(FW_LDQUO) == 2, f"expected 2 left double quotes in {result!r}"
    assert result.count(FW_RDQUO) == 2, f"expected 2 right double quotes in {result!r}"
    assert FW_LDQUO + "这是第一个" + FW_RDQUO in result, f"pair 1 not left-right: {result!r}"
    assert FW_LDQUO + "这是第二个" + FW_RDQUO in result, f"pair 2 not left-right: {result!r}"


def test_single_quotes_paired_left_right():
    """回归(2026-10-24)：单引号同样必须配对。"""
    text = "这是'甲'和'乙'两个词"
    result, counts = normalize_markdown(text)
    assert result.count(FW_LSQUO) == 2, f"expected 2 left single quotes in {result!r}"
    assert result.count(FW_RSQUO) == 2, f"expected 2 right single quotes in {result!r}"


def test_quote_constants_are_distinct():
    """左/右引号常量必须不同(防止 _FULLWIDTH 的重复 key 覆盖再次发生)。"""
    assert FW_LDQUO != FW_RDQUO, "left/right double quote constants must differ"
    assert FW_LSQUO != FW_RSQUO, "left/right single quote constants must differ"
    assert FW_LDQUO == chr(0x201C) and FW_RDQUO == chr(0x201D)
    assert FW_LSQUO == chr(0x2018) and FW_RSQUO == chr(0x2019)


def test_chinese_quotes_single():
    text = "'你好'他说"
    result, counts = normalize_markdown(text)
    assert FW_LSQUO in result or FW_RSQUO in result, f"expected Chinese single quote in {result!r}"


def test_chinese_ellipsis():
    text = "等待中...请稍候"
    result, counts = normalize_markdown(text)
    assert FW_ELLIPSIS in result, f"expected full-width ellipsis in {result!r}"


def test_chinese_emdash():
    text = "首先 -- 其次"
    result, counts = normalize_markdown(text)
    assert FW_EMDASH in result, f"expected em-dash in {result!r}"


def test_markdown_bold_context():
    text = "**目标只能有一个**,不能既要又"
    result, counts = normalize_markdown(text)
    # 至少有一个 `,` 替换为 `,`(第一个 `**target**` 后的 `,`)
    assert FW_COMMA in result, f"expected full-width comma in {result!r}"


def test_protect_fenced_code():
    text = "```\nfunction() { return x; }\n```"
    result, counts = normalize_markdown(text)
    assert "function() { return x; }" in result, f"code should be preserved: {result!r}"


def test_protect_table_row():
    text = "|---|---|---|"
    result, counts = normalize_markdown(text)
    assert "---|---|---" in result, f"table separator preserved: {result!r}"


def test_protect_markdown_heading():
    text = "## 1. 双十一"
    result, counts = normalize_markdown(text)
    assert "## 1." in result, f"heading preserved: {result!r}"


def test_protect_url():
    text = "请访问 https://example.com/test,获取详情"
    result, counts = normalize_markdown(text)
    assert "https://example.com/test" in result, f"URL preserved: {result!r}"


def test_eol_comma():
    text = "这是目标,"
    result, counts = normalize_markdown(text)
    assert "目标，" in result, f"expected EOL comma replaced: {result!r}"


def test_eol_colon():
    text = "这是目标:"
    result, counts = normalize_markdown(text)
    assert "目标：" in result, f"expected EOL colon replaced: {result!r}"


def test_mixed_parens_date():
    text = "(8月28日)到(9月26日)"
    result, counts = normalize_markdown(text)
    assert "（8月28日）" in result, f"date paren replaced: {result!r}"


def test_quoted_comma():
    text = '"结束",没说什么'
    result, counts = normalize_markdown(text)
    # 引号 + 全角逗号
    assert f'{FW_RDQUO}，' in result, f"quoted comma should be replaced: {result!r}"


def test_preserves_chinese_only():
    text = "今天是2026年10月14日,天气很好"
    result, counts = normalize_markdown(text)
    assert FW_COMMA in result, f"chinese comma replaced: {result!r}"
    assert "2026" in result, f"year preserved: {result!r}"


# --- frontmatter 保护(2026-10-24 回归) --------------------------------
#
# 原 bug：脚本没有 frontmatter 保护，把 YAML 里的
#   type: lecture-notes  →  type： lecture-notes
#   xxx.mp4               →  xxx。mp4
# 导致 YAML 失效，verify_all 的 FRONTMATTER 规则报
#   'str' object has no attribute 'get'


def test_frontmatter_preserved_verbatim():
    text = (
        "---\n"
        "type: lecture-notes\n"
        "title: 理清2027年确定增长\n"
        "source: 理清2027年确定增长_天鸣_no-ads.mp4\n"
        "date: 2026-10-24\n"
        "author: 天明\n"
        "---\n"
        "\n"
        "正文,开始。\n"
    )
    result, counts = normalize_markdown(text)
    head = result.split('---')[1]
    assert 'type: lecture-notes' in head, f"frontmatter colon broken: {head!r}"
    assert 'type：' not in result, f"frontmatter colon was full-widthed: {result!r}"
    assert '.mp4' in head, f"frontmatter extension broken: {head!r}"
    assert '。mp4' not in result, f"frontmatter dot was full-widthed: {result!r}"


def test_frontmatter_body_still_normalized():
    text = (
        "---\n"
        "type: lecture-notes\n"
        "---\n"
        "\n"
        "正文,开始。\n"
    )
    result, counts = normalize_markdown(text)
    assert 'type: lecture-notes' in result, f"frontmatter broken: {result!r}"
    assert '正文，开始。' in result, f"body not normalized: {result!r}"


def test_frontmatter_dot_yaml_end_marker():
    """YAML 允许用 ... 作为文档结束符。"""
    text = "---\ntype: lecture-notes\n...\n\n正文,开始。\n"
    result, counts = normalize_markdown(text)
    assert 'type: lecture-notes' in result, f"frontmatter broken: {result!r}"
    assert '正文，开始。' in result, f"body not normalized: {result!r}"


def test_leading_hr_is_not_frontmatter():
    """首行是水平线(下面没有闭合 ---)时，不应当作 frontmatter。"""
    text = "---\n\n正文,开始。\n"
    result, counts = normalize_markdown(text)
    assert '正文，开始。' in result, f"body not normalized: {result!r}"


def test_no_frontmatter_unaffected():
    text = "# 标题\n\n正文,开始。\n"
    result, counts = normalize_markdown(text)
    assert '正文，开始。' in result, f"body not normalized: {result!r}"


# --- 数字上下文 / 有序列表保护(2026-10-24 回归) ------------------------
#
# 原 bug：
#   1) "1. **因为**增长目标..."  →  "1。 **因为**增长目标..."
#      Markdown 有序列表退化成普通段落。
#   2) "增长3.5倍"  →  "增长3。5倍"；"净利润0.24亿" → "净利润0。24亿"
#      小数点被全角化 = 业务数字被改错。


def test_decimal_point_preserved():
    text = "要做到3.5倍的增长,净利润0.24亿"
    result, counts = normalize_markdown(text)
    assert '3.5倍' in result, f"decimal point broken: {result!r}"
    assert '0.24亿' in result, f"decimal point broken: {result!r}"
    assert '3。5' not in result, f"decimal full-widthed: {result!r}"
    assert '0。24' not in result, f"decimal full-widthed: {result!r}"


def test_thousands_separator_preserved():
    text = "目标人效500万,团队1000人,预算1,000元"
    result, counts = normalize_markdown(text)
    assert '1,000元' in result, f"thousands separator broken: {result!r}"
    assert '1，000' not in result, f"thousands separator full-widthed: {result!r}"


def test_time_preserved():
    text = "会议在10:30开始,请准时参加"
    result, counts = normalize_markdown(text)
    assert '10:30' in result, f"time broken: {result!r}"
    assert '10：30' not in result, f"time full-widthed: {result!r}"


def test_ordered_list_marker_preserved():
    text = "1. **因为**增长依据说不清,**所以**先回答增长从哪里来。\n2. **因为**人效决定利润,**所以**目标第一性变量是人效。\n"
    result, counts = normalize_markdown(text)
    assert '1. **因为**' in result, f"ordered list marker broken: {result!r}"
    assert '2. **因为**' in result, f"ordered list marker broken: {result!r}"
    assert '1。' not in result, f"ordered list marker full-widthed: {result!r}"
    assert '2。' not in result, f"ordered list marker full-widthed: {result!r}"


def test_ordered_list_marker_indented_preserved():
    text = "  10. 嵌套的有序列表项\n"
    result, counts = normalize_markdown(text)
    assert result.startswith('  10. '), f"indented ordered marker broken: {result!r}"


def test_sentence_ending_after_number_still_full_width():
    """数字后的句号仍应转全角(不是所有数字后面的点都要保留)。"""
    text = "增长3.5倍已经完成了."
    result, counts = normalize_markdown(text)
    assert result.rstrip().endswith(FW_PERIOD), f"sentence period not converted: {result!r}"


if __name__ == '__main__':
    tests = [
        test_basic_chinese_comma, test_chinese_semicolon,
        test_chinese_period, test_chinese_colon, test_chinese_parens,
        test_chinese_quotes_double, test_chinese_quotes_single,
        test_chinese_ellipsis, test_chinese_emdash,
        test_markdown_bold_context, test_protect_fenced_code,
        test_protect_table_row, test_protect_markdown_heading,
        test_protect_url, test_eol_comma, test_eol_colon,
        test_mixed_parens_date, test_quoted_comma,
        test_preserves_chinese_only,
        test_double_quotes_paired_left_right,
        test_single_quotes_paired_left_right,
        test_quote_constants_are_distinct,
        test_frontmatter_preserved_verbatim,
        test_frontmatter_body_still_normalized,
        test_frontmatter_dot_yaml_end_marker,
        test_leading_hr_is_not_frontmatter,
        test_no_frontmatter_unaffected,
        test_decimal_point_preserved,
        test_thousands_separator_preserved,
        test_time_preserved,
        test_ordered_list_marker_preserved,
        test_ordered_list_marker_indented_preserved,
        test_sentence_ending_after_number_still_full_width,
    ]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERR  {t.__name__}: {e}")
    print(f"\n{passed} pass, {failed} fail")
    sys.exit(0 if failed == 0 else 1)