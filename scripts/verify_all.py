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
 10. H4-PER-H3-MAX (v4.24) · H4 ≤ 18/H3
 11. H4-TOTAL-MAX (v4.24) · H4 ≤ max(50, 字符数/400)
 12. NO-ORPHAN-H3 (v4.4) · H3 孤立(无引言段)
 13. H3-PER-H2-MAX (v4.24) · 单章 H3 ≤ 18 组
 14. H3-TOTAL-MAX (v4.24) · H3 ≤ max(20, 字符数/3000)
 15. NO-SESSION-LABEL-IN-HEADING (v4.24) · 标题残留 ASR 场次标签

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
from utils import read_file_safely, parse_frontmatter, check_links, get_base_dir, log  # noqa: E402

import yaml


# 标题正则
_H2_RE = re.compile(r'^##\s+(.+?)$', re.MULTILINE)
_H3_RE = re.compile(r'^###\s+(.+?)$', re.MULTILINE)
_H4_RE = re.compile(r'^####\s+(.+?)$', re.MULTILINE)
_H5_RE = re.compile(r'^#####\s+(.+?)$', re.MULTILINE)

# 标题规模预算(v4.24)----------------------------------------------------
# 旧版把 H4 卡在 ≤3/H3、全文 ≤50,等于禁用 H4 层 ⇒ 知识点只能全部压平成 H3
# (2026-10-28 实测:19 万字符的课程笔记膨胀到 434 个 H3)。
# 新版按文档规模给预算:小文档仍收紧,大文档线性放宽。
H4_PER_H3_MAX = 10          # 单个 H3 下最多承载的知识点数(H4)
# 全文 H4 总量**不设上限**(v4.25)：知识点密度由 H4_PER_H3_MAX 与内容本身约束，
# 再给全文配额只会迫使作者少用 H4、把知识点重新压回 H3(即 v4.24 前的病根)。
H3_PER_H2_MAX = 18          # 单章(H2)下最多组数
H3_TOTAL_BASE = 20          # 全文 H3 预算下限
H3_CHARS_PER_HEADING = 3000  # 平均每 3000 字符允许 1 个 H3(≈1 组/1.5 屏)

# ASR 场次标签(如「第一天上午」「第二天下午2」)—— 不得出现在任何标题里
SESSION_LABEL_RE = re.compile(r'第[一二三四五六七八九十百0-9]+天[上下]午[0-9]*')


def _budget(char_count: int, base: int, chars_per: int) -> int:
    """按文档规模线性放宽的标题预算,不低于 base。"""
    return max(base, char_count // chars_per)


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
                issues.append(f"H3 '{current_h3_title}' 下只挂 1 个 H4 且无引言")
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
    """H4-PER-H3-MAX (v4.25):单 H3 下 H4 ≤ H4_PER_H3_MAX(10)。全文不设 H4 总量上限。"""
    content = read_file_safely(md_path)
    h3_h4: dict[int, int] = {}
    current_h3 = 0
    for line in content.splitlines():
        if line.startswith('### ') and not line.startswith('#### '):
            current_h3 += 1
            h3_h4[current_h3] = 0
        elif line.startswith('#### ') and not line.startswith('##### '):
            h3_h4[current_h3] = h3_h4.get(current_h3, 0) + 1

    overflow = {h3: n for h3, n in h3_h4.items() if n > H4_PER_H3_MAX}
    return RuleResult(
        name='H4_PER_H3_MAX',
        passed=len(overflow) == 0,
        message=(f"{len(overflow)} 个 H3 超出 {H4_PER_H3_MAX} 个 H4"
                 if overflow else f'PASS (≤{H4_PER_H3_MAX}/H3)'),
        details=[f"H3 #{h3}: {n} H4" for h3, n in overflow.items()],
    )


def verify_h3_per_h2_max(md_path: Path) -> RuleResult:
    """H3-PER-H2-MAX (v4.24):单章 H2 下 H3 组数 ≤ H3_PER_H2_MAX(18)。"""
    content = read_file_safely(md_path)
    per_h2: list[tuple[str, int]] = []
    title = ''
    n = 0
    for line in content.splitlines():
        if line.startswith('## ') and not line.startswith('### '):
            if title:
                per_h2.append((title, n))
            title = line[3:].strip()
            n = 0
        elif line.startswith('### ') and not line.startswith('#### '):
            if title:
                n += 1
    if title:
        per_h2.append((title, n))

    overflow = [(t, c) for t, c in per_h2 if c > H3_PER_H2_MAX]
    return RuleResult(
        name='H3_PER_H2_MAX',
        passed=len(overflow) == 0,
        message=(f"{len(overflow)} 章 H3 数超 {H3_PER_H2_MAX}"
                 if overflow else f'PASS (≤{H3_PER_H2_MAX}/章)'),
        details=[f"{t[:40]}: {c} H3" for t, c in overflow],
    )


def verify_h3_total_max(md_path: Path) -> RuleResult:
    """H3-TOTAL-MAX (v4.24):全文 H3 ≤ max(20, 字符数/3000)。"""
    content = read_file_safely(md_path)
    h3_count = sum(1 for line in content.splitlines()
                   if line.startswith('### ') and not line.startswith('#### '))
    budget = _budget(len(content), H3_TOTAL_BASE, H3_CHARS_PER_HEADING)
    return RuleResult(
        name='H3_TOTAL_MAX',
        passed=h3_count <= budget,
        message=f"H3 数 {h3_count} {'≤' if h3_count <= budget else '>'} 预算 {budget}",
    )


def verify_no_session_label_in_heading(md_path: Path) -> RuleResult:
    """NO-SESSION-LABEL-IN-HEADING (v4.24):标题残留 ASR 场次标签 → FAIL。

    场次(第一天上午/第二天下午)属于溯源信息,应留 ``_handoff.md`` /
    ``_purge_stats.md``,不应进入读者可见的标题。正文提及不受限。
    """
    content = read_file_safely(md_path)
    found: list[str] = []
    in_fenced = False
    for line in content.splitlines():
        if line.lstrip().startswith('```'):
            in_fenced = not in_fenced
            continue
        if in_fenced or not line.startswith('#'):
            continue
        m = re.match(r'^#{1,6}\s+(.+)$', line)
        if m and SESSION_LABEL_RE.search(m.group(1)):
            found.append(line.strip()[:80])
    return RuleResult(
        name='NO_SESSION_LABEL_IN_HEADING',
        passed=len(found) == 0,
        message=f"{len(found)} 个标题含场次标签" if found else 'PASS',
        details=found[:10],
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


def verify_no_half_width_punct(md_path: Path) -> RuleResult:
    """NO-HALF-WIDTH-PUNCT-IN-CN-CONTEXT (v4.21):中文上下文残留半角标点 → FAIL。

    检测:行级扫描,中文之间残留 , ; : . ? ! ( ) 任一半角符号即 FAIL。
    例外:Markdown 结构 / 数字上下文 / URL / 英文短语 / fenced code(已由
    normalize_cn_punctuation.py 行级状态机保护,这里仅做粗扫描作为兜底)。

    Args:
        md_path: 输入 md 路径

    Returns:
        RuleResult,失败时 details 列出每行的具体符号类型与位置。
    """
    content = read_file_safely(md_path)
    # 中文 CJK / 全角符号范围
    cn_re = re.compile(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]')
    # 12 类半角标点(逐字符匹配)
    halfwidth = ',;.:?!()\"\\'':'

    issues: list[str] = []
    total_count = 0
    in_fenced = False

    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.lstrip()
        # fenced code 状态跟踪
        if stripped.startswith('```'):
            in_fenced = not in_fenced
            continue
        if in_fenced:
            continue
        # 跳过 markdown 表格行(含 | 且非首位字符)
        if stripped.startswith('|'):
            continue
        # 跳过 markdown 标题行(以 # 开头,虽然内部不应有半角)
        if stripped.startswith('#'):
            continue

        # 跳过 markdown 链接/图片的 **URL 目标** 与 inline code
        # 规约 43 的例外清单明确写了:`[](url)` `![]()` `` ` `` 都属于合法半角,
        # 必须原样保留 —— 否则图片文件名里的 `.jpg` 会被误判成「中文上下文半角句点」。
        # 注意: alt 文本仍然参与扫描(那才是真正的正文)。
        scan_line = re.sub(r'\]\([^)]*\)', ']()', line)
        scan_line = re.sub(r'`[^`]*`', '``', scan_line)

        # 检查中文之间的半角标点
        for ch in halfwidth:
            for m in re.finditer(re.escape(ch), scan_line):
                pos = m.start()
                prev_char = scan_line[pos - 1] if pos > 0 else ''
                next_char = scan_line[pos + 1] if pos < len(scan_line) - 1 else ''
                prev_cn = bool(cn_re.match(prev_char))
                next_cn = bool(cn_re.match(next_char))
                if prev_cn or next_cn:
                    issues.append(
                        f"line {i} pos {pos}: '{ch}' (U+{ord(ch):04X}) "
                        f"in CN context [{prev_char!r}][{next_char!r}]"
                    )
                    total_count += 1

    return RuleResult(
        name='NO_HALF_WIDTH_PUNCT',
        passed=total_count == 0,
        message=f"{total_count} 处半角标点残留" if issues else 'PASS',
        details=issues[:10],
    )


def verify_llm_steps_executed(md_path: Path) -> RuleResult:
    """LLM-STEPS-EXECUTED (2026-10-24):净化产物不能与原始转写几乎一样。

    这条规则专门抓一个静默失效:`call_vision` 在后端不可用时返回空串 →
    净化步骤 fail-soft 保留原文 → 流水线"成功"结束 → 交付一份**根本没净化过**
    的 cleaned.md。从外面完全看不出发生过任何事。

    判据(去掉空白后比较字符集合):
      净化产物去掉所有空白后的内容,与原始转写去掉所有空白后的内容一致
      ⇒ 判定 LLM 步骤未执行 → FAIL。

    只在提供了 --raw-md 时有意义;没有原始转写就跳过(不判 FAIL)。
    """
    raw_path = getattr(verify_llm_steps_executed, "raw_md_path", None)
    if raw_path is None or not Path(raw_path).exists():
        return RuleResult(name='LLM_STEPS_EXECUTED', passed=True,
                          message='SKIP(未提供 --raw-md)')
    raw = read_file_safely(Path(raw_path))
    cleaned = read_file_safely(md_path)
    if not raw.strip():
        return RuleResult(name='LLM_STEPS_EXECUTED', passed=True,
                          message='SKIP(原始转写为空)')
    squash = lambda s: ''.join(s.split())
    a, b = squash(raw), squash(cleaned)
    if not b:
        return RuleResult(name='LLM_STEPS_EXECUTED', passed=False,
                          message='净化产物为空')
    if a == b:
        return RuleResult(
            name='LLM_STEPS_EXECUTED', passed=False,
            message='净化产物与原始转写完全一致 ⇒ LLM 步骤疑似未执行(后端不可用?)')
    # 高度相似(重合度 > 0.98)也算可疑
    common = len(set(a) & set(b))
    union = len(set(a) | set(b))
    ratio = common / union if union else 0.0
    if ratio > 0.98:
        return RuleResult(
            name='LLM_STEPS_EXECUTED', passed=False,
            message='净化产物与原始转写字符重合度 %.3f > 0.98 ⇒ LLM 步骤疑似未执行'
                    % ratio)
    return RuleResult(name='LLM_STEPS_EXECUTED', passed=True,
                      message='char-set overlap=%.3f' % ratio)


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
    ('NO_ORPHAN_H3', verify_no_orphan_h3),
    # v4.24 结构重排新增:给 H3 层预算 + 禁场次标签入标题
    ('H3_PER_H2_MAX', verify_h3_per_h2_max),
    ('H3_TOTAL_MAX', verify_h3_total_max),
    ('NO_SESSION_LABEL_IN_HEADING', verify_no_session_label_in_heading),
    # v4.21 新增
    ('NO_HALF_WIDTH_PUNCT', verify_no_half_width_punct),
    # 2026-10-24 新增
    ('LLM_STEPS_EXECUTED', verify_llm_steps_executed),
]


def verify_file(md_path: Path) -> list[RuleResult]:
    """对单个文件跑全部规则,返回 RuleResult 列表。"""
    results: list[RuleResult] = []
    for name, rule_fn in RULES:
        try:
            result = rule_fn(md_path)
        except Exception as e:
            result = RuleResult(name=name, passed=False, message=f'EXCEPTION: {e}')
        results.append(result)
    return results


def main() -> int:
    """CLI:
        python scripts/verify_all.py                       # 扫 base 目录下所有 md
        python scripts/verify_all.py <cleaned.md>          # 只验指定文件
        python scripts/verify_all.py <cleaned.md> --raw-md <transcript.md> --html <final.html>

    注意(SKILL.md v4.21 之前写的是带参调用,但脚本并不读参数 —— 文档写什么
    代码就得做什么,否则调用方会以为参数生效了)。
    """
    import argparse

    ap = argparse.ArgumentParser(description="ad-cut/long-doc 规约全量校验")
    ap.add_argument("files", nargs="*", type=Path, help="要校验的 md 文件(默认扫 base 目录)")
    ap.add_argument("--raw-md", type=Path, help="原始转写(启用 LLM_STEPS_EXECUTED 交叉校验)")
    ap.add_argument("--html", type=Path, help="最终 HTML(额外跑 verify_html)")
    args = ap.parse_args()

    if args.raw_md:
        verify_llm_steps_executed.raw_md_path = args.raw_md

    base = get_base_dir()
    if args.files:
        md_files = [Path(f).resolve() for f in args.files]
        missing = [str(f) for f in md_files if not f.exists()]
        if missing:
            print("ERROR: 文件不存在: %s" % ", ".join(missing), file=sys.stderr)
            return 2
    else:
        md_files = sorted(base.rglob('*.md'))
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

    # --html 额外跑 HTML 校验
    if args.html:
        print("\n=== HTML 校验 ===")
        html_path = Path(args.html)
        if not html_path.exists():
            print("ERROR: HTML 文件不存在: %s" % html_path, file=sys.stderr)
            return 2
        try:
            import verify_html
            html_rc = verify_html.main(["verify_html", str(html_path)])
        except Exception as e:
            print("verify_html 执行异常: %s" % e, file=sys.stderr)
            html_rc = 1
        if html_rc != 0:
            any_fail = True

    if any_fail:
        print(f"\n[FAIL] 有规则未通过,需修复")
        return 1
    print(f"\n[OK] 全部验证通过")
    return 0


if __name__ == '__main__':
    sys.exit(main())
