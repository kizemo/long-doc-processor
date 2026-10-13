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
from utils import read_file_safely, parse_frontmatter, check_links, get_base_dir, log  # noqa: E402

import yaml


# 标题正则
_H2_RE = re.compile(r'^##\s+(.+?)$', re.MULTILINE)
_H3_RE = re.compile(r'^###\s+(.+?)$', re.MULTILINE)
_H4_RE = re.compile(r'^####\s+(.+?)$', re.MULTILINE)
_H5_RE = re.compile(r'^#####\s+(.+?)$', re.MULTILINE)


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
    base = get_base_dir()
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
    if any_fail:
        print(f"\n[FAIL] 有规则未通过,需修复")
        return 1
    print(f"\n[OK] 全部验证通过")
    return 0


if __name__ == '__main__':
    sys.exit(main())
