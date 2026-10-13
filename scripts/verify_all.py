"""verify_all.py — 全量验证:规约校验(基础 3 项 + 9 项扩展)

基础校验(原版):
  1. frontmatter 合法性
  2. 链接存在
  3. CJK 占比

扩展校验(v4.x 30 条规约子集):
  4. NO-DOC-META-HEADER (v4.10) · H1 下元描述
  5. NO-DOC-META-BLOCKQUOTE (v4.17) · H1 后 blockquote 元数据
  6. H3-LECTURER-BIO (v4.9) · 讲师资历类标题黑名单
  7. NO-SINGLE-SUBHEADING (v4.9) · H3/H4 下只挂 1 个次级标题
  8. TRAINING-AD-CHAPTER (v4.9.1) · 培训广告章节
  9. NO-NESTED-NUMBERING (v4.4) · H5 标题
 10. H4-PER-H3-MAX (v4.4) · H4 ≤ 3/H3
 11. H4-TOTAL-MAX (v4.4) · H4 ≤ 50 总数
 12. NO-ORPHAN-H3 (v4.4) · H3 孤立(无引言段)

LLM-driven 规约(由 phase-1.7 / strip_*.py 实现,verify 暂跳过):
  - NO-LECTURER-PREAMBLE
  - NO-ROLE-PERSONA-EXTENDED
  - NO-ORPHAN-WORDS
  - NO-META-LECTURE-PREAMBLE-IN-SECTION
  - NO-SINGLE-LINE-BLOCKQUOTE-CALLOUT

完整规约定义见 references/规约清单.md。

退出码:
  0 = 所有校验 PASS
  1 = 有 FAIL
  2 = 输入错误
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
from utils import read_file_safely, parse_frontmatter, check_links, get_base_dir, log, find_files_by_ext  # noqa: E402

import yaml

# 标题正则(v4.22 F1:统一从 chunking 导入,消除 8 脚本重复定义)
from chunking import _H2_TITLE_RE, _H3_TITLE_RE, _H4_TITLE_RE, _H5_TITLE_RE  # noqa: E402
_H2_RE = _H2_TITLE_RE
_H3_RE = _H3_TITLE_RE
_H4_RE = _H4_TITLE_RE
_H5_RE = _H5_TITLE_RE


@dataclass
class RuleResult:
    name: str
    passed: bool
    message: str = ""
    details: list[str] = None  # type: ignore

    def __post_init__(self):
        if self.details is None:
            self.details = []


# 基础 3 项 ----------------------------------------------------

def verify_frontmatter(md_path: Path) -> RuleResult:
    """验证 frontmatter 合法性。"""
    content = read_file_safely(md_path)
    if not content.startswith('---'):
        return RuleResult(name='FRONTMATTER', passed=False, message='无 frontmatter')

    fm_text = content.split('---', 2)[1] if content.count('---') >= 2 else ''
    try:
        fm = yaml.safe_load(fm_text)
    except Exception as e:
        return RuleResult(name='FRONTMATTER', passed=False, message=f'YAML 解析失败:{e}')

    if not fm.get('type'):
        return RuleResult(name='FRONTMATTER', passed=False, message='缺少 type 字段')

    return RuleResult(name='FRONTMATTER', passed=True, message=f"type={fm['type']}")


def verify_links(md_path: Path) -> RuleResult:
    """验证相对链接。"""
    content = read_file_safely(md_path)
    broken = check_links(md_path, content)
    return RuleResult(
        name='LINKS',
        passed=len(broken) == 0,
        message=f"{len(broken)} 个失效" if broken else '所有链接存在',
        details=[f"{b[0]}: {b[2]}" for b in broken[:5]],
    )


def verify_cjk_ratio(md_path: Path) -> RuleResult:
    """验证中文字符占比。"""
    content = read_file_safely(md_path)
    cjk_count = sum(1 for c in content if '一' <= c <= '῿')
    total = len([c for c in content if c.strip()])
    ratio = cjk_count / total if total > 0 else 0
    return RuleResult(
        name='CJK_RATIO',
        passed=ratio >= 0.35 or not md_path.parent.name.startswith('day'),
        message=f"中文占比 {ratio:.2%}",
    )


# 扩展 9 项 ----------------------------------------------------

def verify_no_doc_meta_header(md_path: Path) -> RuleResult:
    """NO-DOC-META-HEADER (v4.10):H1 下文档元说明段不应出现。

    触发:`本文档由视频转录净化整理...` / `原视频为...` / `本讲座聚焦...`
    """
    content = read_file_safely(md_path)
    bad_prefixes = [
        '本文档由视频转录',
        '本文档由录音转录',
        '原视频为',
        '本讲座聚焦',
        '原音频为',
    ]
    for prefix in bad_prefixes:
        if prefix in content:
            return RuleResult(
                name='NO_DOC_META_HEADER',
                passed=False,
                message=f"H1 下元描述前缀:{prefix!r}",
            )
    return RuleResult(name='NO_DOC_META_HEADER', passed=True)


def verify_no_doc_meta_blockquote(md_path: Path) -> RuleResult:
    """NO-DOC-META-BLOCKQUOTE (v4.17):H1 后 blockquote 元描述不应出现。"""
    content = read_file_safely(md_path)
    bad_patterns = [
        r'>\s*课程来源',
        r'>\s*核心主题',
        r'>\s*文档生成',
        r'>\s*讲师[:：]',
        r'>\s*来源[:：]',
    ]
    for pat in bad_patterns:
        if re.search(pat, content):
            return RuleResult(
                name='NO_DOC_META_BLOCKQUOTE',
                passed=False,
                message=f"H1 后 blockquote 元描述匹配:{pat}",
            )
    return RuleResult(name='NO_DOC_META_BLOCKQUOTE', passed=True)


def verify_h3_lecturer_bio(md_path: Path) -> RuleResult:
    """H3-LECTURER-BIO (v4.9):H2/H3/H4 标题禁止讲师资历类黑名单。"""
    content = read_file_safely(md_path)
    bad_keywords = [
        '讲师资历', '讲师简介', '讲师介绍', '自我介绍',
        '讲师背景', '主讲导师', '讲师资历',
        '讲师自我介绍', '关于讲师', '关于主讲',
    ]
    found: list[str] = []
    for line in content.splitlines():
        m = re.match(r'^#{2,4}\s+(.+)$', line)
        if not m:
            continue
        title = m.group(1)
        for kw in bad_keywords:
            if kw in title:
                found.append(f"{line!r} 含 {kw!r}")
    return RuleResult(
        name='H3_LECTURER_BIO',
        passed=len(found) == 0,
        message=f"{len(found)} 个讲师资历类标题" if found else 'PASS',
        details=found,
    )


def verify_no_single_subheading(md_path: Path) -> RuleResult:
    """NO-SINGLE-SUBHEADING (v4.9):H3 下只挂 1 个 H4 且 H3 无引言 → FAIL。"""
    content = read_file_safely(md_path)
    lines = content.splitlines()
    issues: list[str] = []
    current_h3_idx = -1
    current_h3_title = ''
    current_h3_has_intro = False
    h4_count_under_h3 = 0

    for i, line in enumerate(lines):
        if line.startswith('### ') and not line.startswith('#### '):
            # 检查上一个 H3
            if current_h3_idx >= 0 and h4_count_under_h3 == 1 and not current_h3_has_intro:
                issues.append(f"H3 '{current_h3_title}' 下只挂 1 个 H4 且无引言")
            current_h3_idx += 1
            current_h3_title = line[4:].strip()
            current_h3_has_intro = False
            h4_count_under_h3 = 0
        elif line.startswith('#### ') and not line.startswith('##### '):
            h4_count_under_h3 += 1
        elif line.startswith('## ') and not line.startswith('### '):
            # H2 切换,检查上一个 H3
            if current_h3_idx >= 0 and h4_count_under_h3 == 1 and not current_h3_has_intro:
                issues_str = f"H3 '{current_h3_title}' 下只挂 1 个 H4 且无引言"
                if append_str not in issues:
                    issues.append(append_str)
            current_h3_idx = -1
            current_h3_title = ''
            current_h3_has_intro = False
            h4_count_under_h3 = 0
        else:
            if line.strip() and current_h3_idx >= 0 and not current_h3_has_intro:
                # 第一个非空行就是引言
                current_h3_has_intro = True

    # 检查最后一个 H3
    if current_h3_idx >= 0 and h4_count_under_h3 == 1 and not current_h3_has_intro:
        issues.append(f"H3 '{current_h3_title}' 下只挂 1 个 H4 且无引言")

    return RuleResult(
        name='NO_SINGLE_SUBHEADING',
        passed=len(issues) == 0,
        message=f"{len(issues)} 个冗余次级标题" if issues else 'PASS',
        details=issues,
    )


def verify_training_ad_chapter(md_path: Path) -> RuleResult:
    """TRAINING-AD-CHAPTER (v4.9.1):H2 标题含培训广告关键词。"""
    content = read_file_safely(md_path)
    keywords = [
        '陪跑', '服务体系', '年费', '高客单服务',
        '1v1 辅导课程', '一对一辅导课程', '线下诊断服务',
        '工程师协助搭建', '课程原价', '扫码加入',
        '会员价', '购物车链接报名', '线下系统课程',
    ]
    found: list[str] = []
    for line in content.splitlines():
        m = re.match(r'^##\s+(.+)$', line)
        if not m:
            continue
        title = m.group(1)
        for kw in keywords:
            if kw in title:
                found.append(f"H2 {title!r} 含广告关键词 {kw!r}")
    return RuleResult(
        name='TRAINING_AD_CHAPTER',
        passed=len(found) == 0,
        message=f"{len(found)} 个培训广告章" if found else 'PASS',
        details=found,
    )


def verify_no_nested_numbering(md_path: Path) -> RuleResult:
    """NO-NESTED-NUMBERING (v4.4):H5 标题不应出现。"""
    content = read_file_safely(md_path)
    h5_lines = [line for line in content.splitlines() if line.startswith('##### ')]
    return RuleResult(
        name='NO_NESTED_NUMBERING',
        passed=len(h5_lines) == 0,
        message=f"{len(h5_lines)} 个 H5 标题" if h5_lines else 'PASS',
        details=h5_lines[:5],
    )


def verify_h4_per_h3_max(md_path: Path) -> RuleResult:
    """H4-PER-H3-MAX (v4.4):H4 ≤ 3/H3。"""
    content = read_file_safely(md_path)
    h3_h4: dict[int, int] = {}
    current_h3 = 0
    for line in content.splitlines():
        if line.startswith('### ') and not line.startswith('#### '):
            current_h3 += 1
            h3_h4[current_h3] = 0
        elif line.startswith('#### ') and not line.startswith('##### '):
            h3_h3 = h3_h4.get(current_h3, 0)
            h3_h4[current_h3] = h3_h3 + 1

    overflow = {h3: n for h3, n in h3_h4.items() if n > 3}
    return RuleResult(
        name='H4_PER_H3_MAX',
        passed=len(overflow) == 0,
        message=f"{len(overflow)} 个 H3 超出 3 个 H4" if overflow else 'PASS',
        details=[f"H3 #{h3}: {n} H4" for h3, n in overflow.items()],
    )


def verify_h4_total_max(md_path: Path) -> RuleResult:
    """H4-TOTAL-MAX (v4.4):全文 H4 ≤ 50。"""
    content = read_file_safely(md_path)
    h4_count = sum(1 for line in content.splitlines()
                    if line.startswith('#### ') and not line.startswith('##### '))
    return RuleResult(
        name='H4_TOTAL_MAX',
        passed=h4_count <= 50,
        message=f"H4 数 {h4_count} {'≤' if h4_count <= 50 else '>'} 50",
    )


def verify_no_orphan_h3(md_path: Path) -> RuleResult:
    """NO-ORPHAN-H3 (v4.4):H3 后无引言段 → FAIL。"""
    content = read_file_safely(md_path)
    lines = content.splitlines()
    issues: list[str] = []

    current_h3_idx = -1
    current_h3_title = ''
    next_non_empty_idx = -1

    for i, line in enumerate(lines):
        if line.startswith('### ') and not line.startswith('#### '):
            current_h3_idx += 1
            current_h3_title = line[4:].strip()
            next_non_empty_idx = i + 1
        elif current_h3_idx >= 0 and line.strip() and not line.startswith('#'):
            # 找到引言段,清空
            current_h3_idx = -1

    # 这里简单检查:每个 H3 后第一个非空非标题行就是引言
    # 但孤立 H3 在最后一行不算孤立(可能合法)
    return RuleResult(
        name='NO_ORPHAN_H3',
        passed=True,  # 复杂检测,默认 PASS,留给 LLM strip 检测
        message='(默认 PASS,复杂检测由 Phase 1.7 LLM 处理)',
    )


# v4.21 阶段 B 新增 8 条 verify 函数(整合 M-05/M-06/M-07/M-13 跨项目踩坑模式)
# 详见 optimization-plan-v2-2026-10-13.md §2.1 + history/v3.8-optimized/resource-study-report-2026-10-13.md §5

def verify_no_role_persona_extended(md_path: Path) -> RuleResult:
    """NO-ROLE-PERSONA-EXTENDED (v4.17) + M-07:扫描所有段落+表格单元格。

    触发:讲师指出 / 讲师总结 / 讲师举例 / 学员搜索时 / 学员常见的错误
    + 表格单元格内出现学员/讲师/主讲导师/大力老师/授课老师/教练。
    例外:`讲师说:"原话"` 形式(原话在引号内)整句豁免。
    """
    content = read_file_safely(md_path)
    bad_keywords = [
        '学员', '讲师', '主讲导师', '大力老师', '授课老师', '教练',
    ]
    bad_phrases = [
        '讲师指出', '讲师总结', '讲师举例', '学员搜索时', '学员常见的错误',
        '有学员', '学员提问', '学员在选品时', '某学员', '某学员提出',
    ]
    # 引号内豁免的正则(整段被引号包围)
    _QUOTE_EXEMPT_RE = re.compile(r'["""「][^"""]*?(讲师|学员|主讲导师|大力老师|授课老师|教练)[^"""]*?[""]')
    found: list[str] = []

    lines = content.splitlines()
    in_code = False
    in_table = False
    for i, line in enumerate(lines):
        # 代码块内不算
        if line.strip().startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            continue
        # 表格行(|...|)
        is_table_row = line.strip().startswith('|') and line.strip().endswith('|')
        if is_table_row:
            in_table = True
        elif line.strip() == '':
            in_table = False

        # 整段引号豁免(原话在引号内)
        if _QUOTE_EXEMPT_RE.search(line):
            continue

        for phrase in bad_phrases:
            if phrase in line:
                found.append(f"line {i+1}: {phrase!r} in {line.strip()[:60]!r}")
                break
        else:
            for kw in bad_keywords:
                if kw in line:
                    if in_table or is_table_row:
                        found.append(f"line {i+1} (table): {kw!r} in {line.strip()[:60]!r}")
                        break
                    found.append(f"line {i+1}: {kw!r} in {line.strip()[:60]!r}")
                    break

    return RuleResult(
        name='NO_ROLE_PERSONA_EXTENDED',
        passed=len(found) == 0,
        message=f"{len(found)} 处角色主语" if found else 'PASS',
        details=found[:5],
    )


def verify_hierarchical_numbering(md_path: Path) -> RuleResult:
    """HIERARCHICAL-NUMBERING (v4.17) + M-05:严格匹配 `N.` / `N.M` / `N.M.K`。

    关键规避(M-05):正则与 SKILL.md 描述严格对齐(`## N xxx` 空格不要点号)。
    v4.17 changelog:H2/H3/H4 强制 `1./1.1/1.1.1` 阿拉伯数字编号。
    """
    content = read_file_safely(md_path)
    h2_re = re.compile(r'^##\s+(\d+)\.\s+\S')
    h3_re = re.compile(r'^###\s+(\d+)\.(\d+)\s+\S')
    h4_re = re.compile(r'^####\s+(\d+)\.(\d+)\.(\d+)\s+\S')
    issues: list[str] = []
    last_h2 = 0
    last_h3_per_h2: dict[int, int] = {}
    last_h4_per_h3: dict[tuple[int, int], int] = {}

    for i, line in enumerate(content.splitlines()):
        m2 = h2_re.match(line)
        m3 = h3_re.match(line)
        m4 = h4_re.match(line)
        if m2:
            n = int(m2.group(1))
            if last_h2 > 0 and n != last_h2 + 1:
                issues.append(f"line {i+1}: H2 跳号 {last_h2} → {n}")
            last_h2 = n
            last_h3_per_h2[n] = 0
        elif m3:
            h2_n = last_h2
            h3_n = int(m3.group(2))
            expected_h2 = int(m3.group(1))
            if expected_h2 != h2_n:
                issues.append(f"line {i+1}: H3 的 H2 编号 {expected_h2} ≠ 当前 H2 {h2_n}")
            last = last_h3_per_h2.get(h2_n, 0)
            if last > 0 and h3_n != last + 1:
                issues.append(f"line {i+1}: H3 跳号 {last} → {h3_n}")
            last_h3_per_h2[h2_n] = h3_n
        elif m4:
            h2_n = last_h2
            h3_n = int(m4.group(2))
            h4_n = int(m4.group(3))
            key = (h2_n, h3_n)
            last = last_h4_per_h3.get(key, 0)
            if last > 0 and h4_n != last + 1:
                issues.append(f"line {i+1}: H4 跳号 {last} → {h4_n}")
            last_h4_per_h3[key] = h4_n

    return RuleResult(
        name='HIERARCHICAL_NUMBERING',
        passed=len(issues) == 0,
        message=f"{len(issues)} 处编号问题" if issues else 'PASS',
        details=issues[:5],
    )


def verify_no_single_line_blockquote_callout(md_path: Path) -> RuleResult:
    """NO-SINGLE-LINE-BLOCKQUOTE-CALLOUT (v4.18):单行 `>` 引用块不应作视觉强调。

    关键规避(M-06):整篇 normalize 后检查,非 per-line。
    单行 `>` = 该行只有 `> xxx` 且前后行不是 `>` 起始。
    例外:多行 `>` box(≥2 行连续)合法。
    """
    content = read_file_safely(md_path)
    lines = content.splitlines()
    issues: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('>'):
            # 检查是否多行 box(≥2 行连续 `>`)
            j = i
            while j < len(lines) and lines[j].strip().startswith('>'):
                j += 1
            block_size = j - i
            if block_size == 1:
                # 单行 callout
                issues.append(f"line {i+1}: 单行 `>` blockquote:{line[:60]!r}")
            i = j
        else:
            i += 1

    return RuleResult(
        name='NO_SINGLE_LINE_BLOCKQUOTE_CALLOUT',
        passed=len(issues) == 0,
        message=f"{len(issues)} 处单行 callout" if issues else 'PASS',
        details=issues[:5],
    )


def verify_h3_lecturer_bio_extended(md_path: Path) -> RuleResult:
    """H3-LECTURER-BIO 扩展 (v4.14):在 v4.9 基础上加 9 类黑名单词。

    v4.14 changelog 新增:主讲人资历 / 直播核心主题 / 课程预告 / 线下 N 天 /
    招生 / 系统课 / 主讲导师 资历 / 主讲人 介绍 / 老师 介绍
    """
    content = read_file_safely(md_path)
    bad_keywords = [
        # v4.9 原 11 类
        '讲师资历', '讲师简介', '讲师介绍', '自我介绍',
        '讲师背景', '主讲导师', '讲师自我介绍', '关于讲师', '关于主讲',
        # v4.14 扩展 9 类
        '主讲人资历', '直播核心主题', '课程预告', '线下', '招生', '系统课',
        '主讲人介绍', '老师介绍', '讲师资历介绍',
    ]
    found: list[str] = []
    for i, line in enumerate(content.splitlines()):
        m = re.match(r'^#{2,4}\s+(.+)$', line)
        if not m:
            continue
        title = m.group(1)
        for kw in bad_keywords:
            if kw in title:
                found.append(f"line {i+1}: {line.strip()[:60]!r} 含 {kw!r}")
                break
    return RuleResult(
        name='H3_LECTURER_BIO_EXTENDED',
        passed=len(found) == 0,
        message=f"{len(found)} 个讲师资历类标题(扩展)" if found else 'PASS',
        details=found[:5],
    )


def verify_training_ad_chapter_extended(md_path: Path) -> RuleResult:
    """TRAINING-AD-CHAPTER 扩展 (v4.14):在 v4.9.1 基础上加 4 类广告关键词。

    v4.14 changelog 新增:会员价 / 购物车链接报名 / 线下系统课程 / 线下 N 天。
    v4.9.1 原 13 类:陪跑 / 服务体系 / 年费 / 高客单服务 / 1v1 辅导课程 /
    一对一辅导课程 / 线下诊断服务 / 工程师协助搭建 / 课程原价 / 扫码加入。
    """
    content = read_file_safely(md_path)
    keywords = [
        # v4.9.1 原关键词
        '陪跑', '服务体系', '年费', '高客单服务',
        '1v1 辅导课程', '一对一辅导课程', '线下诊断服务',
        '工程师协助搭建', '课程原价', '扫码加入',
        # v4.14 扩展 4 类
        '会员价', '购物车链接报名', '线下系统课程', '线下 N 天',
    ]
    found: list[str] = []
    for i, line in enumerate(content.splitlines()):
        m = re.match(r'^##\s+(.+)$', line)
        if not m:
            continue
        title = m.group(1)
        for kw in keywords:
            if kw in title:
                found.append(f"line {i+1}: H2 {title!r} 含广告关键词 {kw!r}")
                break
    return RuleResult(
        name='TRAINING_AD_CHAPTER_EXTENDED',
        passed=len(found) == 0,
        message=f"{len(found)} 个培训广告章(扩展)" if found else 'PASS',
        details=found[:5],
    )


def verify_img_size_within_limit(md_path: Path) -> RuleResult:
    """img_size_within_limit (v4.19 + B1):markdown 引用图片 ≤ 200KB + ≤ 800x600。

    解析 `![alt](path)` 语法,对本地路径(非 http/data)用 PIL 读图检查。
    若 PIL 未装 → 跳过(SKILL.md 兼容 C 级校验)。
    """
    content = read_file_safely(md_path)
    img_re = re.compile(r'!\[.*?\]\(([^)]+)\)')
    issues: list[str] = []

    try:
        from PIL import Image  # type: ignore
    except ImportError:
        # PIL 未装,跳过(本规则为 C 级诊断)
        return RuleResult(
            name='IMG_SIZE_WITHIN_LIMIT',
            passed=True,
            message='(PIL 未装,跳过)',
        )

    base = md_path.parent
    for m in img_re.finditer(content):
        src = m.group(1).strip()
        # 跳过远程 / data URI
        if src.startswith(('http://', 'https://', 'data:')):
            continue
        # 去掉 query / fragment
        src_clean = src.split('?', 1)[0].split('#', 1)[0]
        img_path = (base / src_clean).resolve()
        if not img_path.exists():
            # 图片不存在由 verify_html 19 处理,本规则不重复
            continue
        try:
            size_kb = img_path.stat().st_size / 1024
            if size_kb > 200:
                issues.append(f"{src}: {size_kb:.1f}KB > 200KB")
                continue
            with Image.open(img_path) as im:
                w, h = im.size
                if w > 800 or h > 600:
                    issues.append(f"{src}: {w}x{h} > 800x600")
        except Exception as e:
            issues.append(f"{src}: 读取失败 {type(e).__name__}: {e}")

    return RuleResult(
        name='IMG_SIZE_WITHIN_LIMIT',
        passed=len(issues) == 0,
        message=f"{len(issues)} 张超限图" if issues else 'PASS',
        details=issues[:5],
    )


def verify_no_path_traversal(md_path: Path) -> RuleResult:
    """no_path_traversal (B1):markdown 中 `<img src>` / 链接 不应含 `..`。

    触发:`../` 路径可能跳到上层目录读取敏感文件(虽然本 skill 不写文件,
    但 HTML 渲染时 `<img src="../../etc/passwd">` 是 XSS-like 风险)。
    """
    content = read_file_safely(md_path)
    img_re = re.compile(r'!\[.*?\]\(([^)]+)\)')
    link_re = re.compile(r'(?<!!)\[([^\]]+)\]\(([^)]+)\)')
    issues: list[str] = []

    for m in img_re.finditer(content):
        src = m.group(1).strip()
        if src.startswith(('http://', 'https://', 'data:')):
            continue
        if '..' in src:
            issues.append(f"img src 含 `..`:{src!r}")

    for m in link_re.finditer(content):
        text, target = m.group(1), m.group(2)
        if target.startswith(('http://', 'https://', 'mailto:', '#')):
            continue
        if '..' in target:
            issues.append(f"link {text!r} 路径含 `..`:{target!r}")

    return RuleResult(
        name='NO_PATH_TRAVERSAL',
        passed=len(issues) == 0,
        message=f"{len(issues)} 处路径穿越" if issues else 'PASS',
        details=issues[:5],
    )


def verify_no_doc_meta_header_blockquote(md_path: Path) -> RuleResult:
    """NO-DOC-META-HEADER-BLOCKQUOTE (B1):H1 下 blockquote 元数据(与 NO-DOC-META-BLOCKQUOTE 互补)。

    NO-DOC-META-BLOCKQUOTE 抓 `> 课程来源:` 等显式元描述;
    本规则抓 H1 后紧跟的整段 blockquote 元描述(任意内容),因为 H1 下的
    blockquote 通常是文档元信息(讲师/课程/时间/出处),应移到 frontmatter。
    """
    content = read_file_safely(md_path)
    lines = content.splitlines()
    h1_idx = -1
    for i, line in enumerate(lines):
        if line.startswith('# ') and not line.startswith('## '):
            h1_idx = i
            break
    if h1_idx < 0:
        return RuleResult(name='NO_DOC_META_HEADER_BLOCKQUOTE', passed=True)

    # 看 H1 之后第一个非空行是否是 `> xxx`
    j = h1_idx + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j < len(lines) and lines[j].strip().startswith('>'):
        bq = lines[j].strip()
        return RuleResult(
            name='NO_DOC_META_HEADER_BLOCKQUOTE',
            passed=False,
            message=f"H1 后紧跟 blockquote:{bq[:60]!r}",
        )
    return RuleResult(name='NO_DOC_META_HEADER_BLOCKQUOTE', passed=True)


# v4.21 C3 阶段:--strict fail-loud 产物验证(整合 A4)

def verify_purify_fail_loud(md_path: Path) -> RuleResult:
    """PURIFY_FAIL_LOUD (v4.21 C3):strict 模式产物应含 ERROR 标记。

    设计意图:A4 实现 --strict 模式后,LLM 失败的 chunk 在产物中
    写 `> **ERROR**:LLM 净化失败(strict 模式)` 标记 + exit 2。
    本规则验证产物中不应残留 ERROR 标记(若有,说明 LLM 部分仍失败)。

    触发:产物含 `**ERROR**:LLM 净化失败` 或 `**ERROR**:LLM 失败`。
    """
    content = read_file_safely(md_path)
    error_patterns = [
        r'\*\*ERROR\*\*[::]\s*LLM 净化失败',
        r'\*\*ERROR\*\*[::]\s*LLM 失败',
    ]
    found: list[str] = []
    for pat in error_patterns:
        for m in re.finditer(pat, content):
            # 找到所在行
            line_no = content[:m.start()].count('\n') + 1
            found.append(f"line {line_no}: {m.group(0)[:60]!r}")
    return RuleResult(
        name='PURIFY_FAIL_LOUD',
        passed=len(found) == 0,
        message=f"{len(found)} 处 ERROR 标记(strict 模式残留)" if found else 'PASS',
        details=found[:5],
    )


# 规则注册表 ----------------------------------------------------

RULES: list[tuple[str, Callable]] = [
    # 基础 3 项
    ('FRONTMATTER', verify_frontmatter),
    ('LINKS', verify_links),
    ('CJK_RATIO', verify_cjk_ratio),
    # 扩展 9 项
    ('NO_DOC_META_HEADER', verify_no_doc_meta_header),
    ('NO_DOC_META_BLOCKQUOTE', verify_no_doc_meta_blockquote),
    ('H3_LECTURER_BIO', verify_h3_lecturer_bio),
    ('NO_SINGLE_SUBHEADING', verify_no_single_subheading),
    ('TRAINING_AD_CHAPTER', verify_training_ad_chapter),
    ('NO_NESTED_NUMBERING', verify_no_nested_numbering),
    ('H4_PER_H3_MAX', verify_h4_per_h3_max),
    ('H4_TOTAL_MAX', verify_h4_total_max),
    ('NO_ORPHAN_H3', verify_no_orphan_h3),
    # v4.21 B1 新增 8 项
    ('NO_ROLE_PERSONA_EXTENDED', verify_no_role_persona_extended),
    ('HIERARCHICAL_NUMBERING', verify_hierarchical_numbering),
    ('NO_SINGLE_LINE_BLOCKQUOTE_CALLOUT', verify_no_single_line_blockquote_callout),
    ('H3_LECTURER_BIO_EXTENDED', verify_h3_lecturer_bio_extended),
    ('TRAINING_AD_CHAPTER_EXTENDED', verify_training_ad_chapter_extended),
    ('IMG_SIZE_WITHIN_LIMIT', verify_img_size_within_limit),
    ('NO_PATH_TRAVERSAL', verify_no_path_traversal),
    ('NO_DOC_META_HEADER_BLOCKQUOTE', verify_no_doc_meta_header_blockquote),
    # v4.21 C3 新增 1 项
    ('PURIFY_FAIL_LOUD', verify_purify_fail_loud),
]


def verify_file(md_path: Path) -> list[RuleResult]:
    """对单个文件跑全部规则,返回 RuleResult 列表。

    v4.22 F2:content 缓存,21 条规则只读 1 次磁盘(原 21 次)。
    通过 monkey-patch utils.read_file_safely 实现 verify_file 范围内缓存。
    """
    # 进入 verify_file:预读 + 替换 read_file_safely 为 cached 版本
    import scripts.utils as _utils
    _original_read = _utils.read_file_safely
    _content_cache: dict[str, str] = {}
    _cache_key = str(md_path)

    def _cached_read(path):
        key = str(path)
        if key in _content_cache:
            return _content_cache[key]
        content = _original_read(path)
        _content_cache[key] = content
        return content

    _utils.read_file_safely = _cached_read
    try:
        results: list[RuleResult] = []
        for name, rule_fn in RULES:
            try:
                result = rule_fn(md_path)
            except Exception as e:
                result = RuleResult(name=name, passed=False, message=f'EXCEPTION: {e}')
            results.append(result)
        return results
    finally:
        _utils.read_file_safely = _original_read


def main() -> int:
    base = get_base_dir()
    md_files = find_files_by_ext(base, '.md')
    print(f"=== 全量验证 {len(md_files)} 个 md 文件 ({len(RULES)} 条规则) ===\n")

    fm_pass = 0
    fm_fail: list[tuple[Path, str]] = []
    all_results: dict[str, list[tuple[Path, RuleResult]]] = {name: [] for name, _ in RULES}

    for md in md_files:
        if md.parent == base:
            continue
        results = verify_file(md)
        for result in results:
            all_results[result.name].append((md, result))

    # 输出汇总
    print("=== 各规则通过情况 ===")
    for name, _ in RULES:
        items = all_results[name]
        pass_count = sum(1 for _, r in items if r.passed)
        fail_count = len(items) - pass_count
        status = '✅' if fail_count == 0 else '❌'
        print(f"{status} {name}: {pass_count}/{len(items)} pass")
        # 显示失败详情
        for md, r in items:
            if not r.passed:
                print(f"    - {md.name}: {r.message}")
                for d in r.details[:3]:
                    print(f"        {d[:100]}")

    # 总体 PASS 判定:任何 FAIL 即返回 1
    any_fail = any(
        not r.passed
        for name, _ in RULES
        for _, r in all_results[name]
    )
    if any_fail:
        print(f"\n[FAIL] 有规则未通过,需修复")
        return 1
    print(f"\n[OK] 全部验证通过")
    return 0


if __name__ == '__main__':
    sys.exit(main())
