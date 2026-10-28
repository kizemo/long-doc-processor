#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""restructure_outline.py — 结构重排：把过碎的 H3 收敛为「分组 H3 + 条目 H4」。

## 为什么需要这个脚本（v4.22 复盘）

旧门禁 `H4_PER_H3_MAX`(<=3/H3) + `H4_TOTAL_MAX`(<=50) 事实上**禁止使用 H4**。v4.25 起改为单组 ≤10、全文 H4 不设上限。
一份 400+ 独立知识点的长课程笔记，在「每个 H3 至少 2 段正文」
「禁止单副标题」等规则叠加下，只能把全部知识点压平成 H3 ——
实测某 48 万字符笔记产出 **434 个 H3、0 个 H4**，编号长到 `### 1.116`，
标题还被塞进「第二天上午：」这类**ASR 场次分段标签**，阅读体验极差。

本脚本把这件事拆成两段，各司其职：

1. **LLM 只做语义归纳**：哪些 H3 属于同一主题、给它起什么组名；
2. **脚本做守恒校验与编号**：并集必须等于全集、无重复无遗漏、编号连续、
   场次标签必须清除、正文原样搬运（含 CRLF）。

结构安全不押在 LLM 输出上。

## 用法

```bash
# 1) 诊断当前结构（有多少 H3、各章分布、多少标题带场次标签）
python scripts/restructure_outline.py doc.md --audit

# 2) 导出待分组清单（每章一份 JSON，直接喂给 LLM）
python scripts/restructure_outline.py doc.md --plan-out plan_dir

# 3) 应用分组计划（先 --check-only 只校验，不写盘）
python scripts/restructure_outline.py doc.md --apply-plan plan_dir/plan.json \
    --out doc.restructured.md --check-only

# 4) 正式写盘
python scripts/restructure_outline.py doc.md --apply-plan plan_dir/plan.json \
    --out doc.restructured.md
```

## 分组计划格式（plan.json）

```json
{
  "chapters": [
    {
      "h2": "1. 搞懂无界底层逻辑",
      "groups": [
        {"title": "货品分层：从层级定义到达标阈值",
         "intro": "一句话导语，可省略。",
         "items": [12, 13, 18, 19]}
      ]
    }
  ]
}
```

`items` 里放的是 **全文 H3 的全局序号（1-based）**，与 `--plan-out`
导出的 `idx` 字段一一对应。脚本会强制校验：并集 == 全部序号、无重复、无遗漏、
每个序号只能落在一个组里、每组只能收本章的条目。

退出码：0 全绿；1 校验失败；2 用法错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- 常量

H2_PER_DOC_MAX = 15          # H2 章节数上限（规约：H2 编号 1-7 为常态，15 为硬顶）
H3_PER_H2_MAX = 18           # 每章 H3 分组数上限 —— 新增门禁，防止 H3 无限膨胀
H3_TOTAL_BASE = 20           # 全文 H3 预算基数（短文档兜底）
H3_CHARS_PER_HEADING = 3000  # 每多少个正文字符允许 1 个 H3（与 verify_all.py 同式）
H4_PER_H3_MAX = 10           # 每组的条目数上限（与 verify_all 同式，v4.25）
GROUP_MIN_ITEMS = 2          # 一个组至少收 2 条，否则等于没合并

# 标题里禁止出现的场次 / 时间分段标签。
# 来源：多场 ASR 分批转写后，合并时把「第一天上午」这类**文件名级分段标签**
# 当成了内容写进标题。它属于来源元信息，不属于知识结构。
SESSION_LABEL_RE = re.compile(
    r'第[一二三四五六七八九十\d]{1,3}节?天?次?(?:场|讲)?'
    r'(?:上午|下午|晚上|全天|上半场|下半场)?'
    r'(?:[（(]\s*续\s*[一二三四五六七八九十\d]*\s*[)）])?'
)
SESSION_LABEL_STRICT_RE = re.compile(
    r'(?:第[一二三四五六七八九十\d]{1,3}[天节次场讲]'
    r'(?:上午|下午|晚上|全天|上半场|下半场)?'
    r'|上午场|下午场|晚上场'
    r'|[（(]\s*续\s*[一二三四五六七八九十\d]*\s*[)）])'
)
OLD_NUM_RE = re.compile(r'^\s*\d+(?:\s*[.．]\s*\d+)*\s*[.．、,，:：·]?\s*')


# ---------------------------------------------------------------- 数据结构

@dataclass
class Item:
    """一个 H3 条目（重排后变成 H4）。"""
    idx: int                # 全文 1-based 序号
    chapter_no: str         # 所属 H2 编号，如 '1'
    chapter_pos: int        # 所属 H2 在文档中的 1-based 位置
    raw_title: str          # 原样标题（不含 '### '）
    body: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        """去掉旧编号 + 场次标签后的干净标题。"""
        return clean_title(self.raw_title)


@dataclass
class Chapter:
    no: str
    raw_title: str
    line: str
    intro: list[str] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)


@dataclass
class Doc:
    eol: str
    preamble: list[str]
    chapters: list[Chapter]
    items: list[Item]
    n_chars: int = 0

    @property
    def n_h3(self) -> int:
        return len(self.items)

    @property
    def h3_budget(self) -> int:
        """全文 H3 预算：按正文字符数比例化，不设与规模无关的绝对常量。"""
        return max(H3_TOTAL_BASE, self.n_chars // H3_CHARS_PER_HEADING)


# ---------------------------------------------------------------- 清洗

def clean_title(raw: str) -> str:
    """剥掉旧编号与场次标签，返回干净标题。"""
    t = raw.strip()
    # 反复剥前缀：旧编号 / 场次标签 / 残留分隔符
    for _ in range(4):
        before = t
        t = OLD_NUM_RE.sub('', t).strip()
        m = SESSION_LABEL_STRICT_RE.match(t)
        if m:
            t = t[m.end():].strip()
        t = t.lstrip(' :：,，、·-—')
        if t == before:
            break
    t = re.sub(r'[（(]\s*续\s*[一二三四五六七八九十\d]*\s*[)）]', '', t).strip()
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def has_session_label(title: str) -> bool:
    return bool(SESSION_LABEL_STRICT_RE.search(title))


# ---------------------------------------------------------------- 解析

def read_doc(path: Path) -> Doc:
    raw = path.read_bytes()
    # 保留原换行风格：正文原样搬运
    eol = '\r\n' if b'\r\n' in raw else '\n'
    text = raw.decode('utf-8-sig')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = text.split('\n')

    preamble: list[str] = []
    chapters: list[Chapter] = []
    items: list[Item] = []

    cur_ch: Chapter | None = None
    cur_item: Item | None = None
    idx = 0

    for line in lines:
        is_h2 = line.startswith('## ') and not line.startswith('### ')
        is_h3 = line.startswith('### ') and not line.startswith('#### ')

        if is_h2:
            m = re.match(r'^##\s+(\d+)\s*[.．、:：]?\s*(.*)$', line)
            no = m.group(1) if m else ''
            title = (m.group(2) if m else line[3:]).strip()
            cur_ch = Chapter(no=no, raw_title=title, line=line,
                             intro=[], items=[])
            chapters.append(cur_ch)
            cur_item = None
            continue

        if is_h3:
            if cur_ch is None:
                # 没有 H2 的 H3 —— 归入一个虚拟章，避免直接崩
                cur_ch = Chapter(no='', raw_title='', line='', intro=[],
                                 items=[])
                chapters.append(cur_ch)
            idx += 1
            cur_item = Item(idx=idx, chapter_no=cur_ch.no,
                            chapter_pos=len(chapters),
                            raw_title=line[4:].strip(), body=[])
            cur_ch.items.append(cur_item)
            items.append(cur_item)
            continue

        if cur_item is not None:
            cur_item.body.append(line)
        elif cur_ch is not None:
            cur_ch.intro.append(line)
        else:
            preamble.append(line)

    return Doc(eol=eol, preamble=preamble, chapters=chapters, items=items,
               n_chars=len(text))


def strip_blank_edges(lines: list[str]) -> list[str]:
    out = list(lines)
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out


# ---------------------------------------------------------------- 审计

def audit(doc: Doc) -> str:
    out: list[str] = []
    n_h2 = len(doc.chapters)
    n_h3 = doc.n_h3
    out.append('# 结构审计')
    out.append('')
    out.append(f'- H2 章节数：{n_h2}（上限 {H2_PER_DOC_MAX}）')
    out.append(f'- H3 条目数：{n_h3}（上限预算 {doc.h3_budget}）')
    out.append(f'- 每章 H3 数上限：{H3_PER_H2_MAX}')
    out.append(f'- 每组条目数上限：{H4_PER_H3_MAX}')
    out.append('')

    bad_titles = [it for it in doc.items if has_session_label(it.raw_title)]
    out.append(f'## 标题含场次标签：{len(bad_titles)} / {n_h3}')
    for it in bad_titles[:10]:
        out.append(f'  - #{it.idx} {it.raw_title}')
    if len(bad_titles) > 10:
        out.append(f'  - …共 {len(bad_titles)} 条')
    out.append('')

    dirty = [it for it in doc.items if clean_title(it.raw_title) !=
             re.sub(r'^\s*\d+(?:\s*[.．]\s*\d+)*\s*[.．、,，:：·]?\s*', '',
                    it.raw_title).strip()]
    out.append(f'## 去标签后标题会变化的条目：{len(dirty)}')
    out.append('')

    out.append('## 各章分布')
    out.append('')
    out.append('| 章 | H2 标题 | H3 数 | 建议分组数 | 平均每组 |')
    out.append('|---|---|---|---|---|')
    for ch in doc.chapters:
        n = len(ch.items)
        if n == 0:
            out.append(f'| {ch.no} | {ch.raw_title} | 0 | - | - |')
            continue
        g = max(1, min(H3_PER_H2_MAX, round(n / 8)))
        out.append(f'| {ch.no} | {ch.raw_title} | {n} | {g} | {n / g:.1f} |')
    out.append('')

    over = [(ch.no, len(ch.items)) for ch in doc.chapters
            if len(ch.items) > H3_PER_H2_MAX]
    out.append(f'## 超出每章 H3 上限的章：{len(over)}')
    for no, n in over:
        out.append(f'  - 第 {no} 章：{n} 个 H3 > {H3_PER_H2_MAX}')
    out.append('')

    # 尾段（最后一个 H3 的正文末尾）—— 重排后会被搬进最后一个 H4
    if doc.items:
        tail = strip_blank_edges(doc.items[-1].body)
        out.append(f'## 末条目 #{doc.items[-1].idx} 正文尾部 12 行')
        out.append('```')
        out.extend(tail[-12:] if tail else ['(空)'])
        out.append('```')
    return '\n'.join(out)


# ---------------------------------------------------------------- 导出计划

PREVIEW_CHARS = 70


def one_line(text: str, n: int = PREVIEW_CHARS) -> str:
    t = re.sub(r'\s+', ' ', text).strip()
    return t[:n] + ('…' if len(t) > n else '')


def plan_out(doc: Doc, out_dir: Path) -> list[Path]:
    """每章一份 JSON，供 LLM 只处理该章。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for ch in doc.chapters:
        payload = {
            'h2': f'{ch.no}. {ch.raw_title}'.strip(),
            'goal': ('把本章条目按语义归纳成 4-8 个主题组；每组 3-10 条。'
                     '组名要概括该组讲了什么，不要照抄条目名；'
                     '同一组内条目必须在逻辑上属于同一主题。'),
            'constraints': [
                f'每组至少 {GROUP_MIN_ITEMS} 条，最多 {H4_PER_H3_MAX} 条',
                '所有 idx 必须恰好出现一次，不得重复、不得遗漏',
                '组按原文顺序排列，组内条目也按原顺序',
                '组名 8-18 字，不得含「第一天上午」这类场次标签，不得带编号',
                'intro 写 1-2 句导语，说明这组解决什么问题（可为空字符串）',
            ],
            'items': [
                {
                    'idx': it.idx,
                    'title': it.title,
                    'preview': one_line(' '.join(it.body)),
                }
                for it in ch.items
            ],
            'output_schema': {
                'h2': f'{ch.no}. {ch.raw_title}'.strip(),
                'groups': [
                    {'title': '组名', 'intro': '导语', 'items': ['idx', '...']}
                ],
            },
        }
        p = out_dir / f'plan_ch{ch.no or "x"}.json'
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                     encoding='utf-8')
        written.append(p)
    return written


# ---------------------------------------------------------------- 应用计划

class PlanError(ValueError):
    pass


def load_plan(path: Path) -> dict:
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if 'chapters' not in data and 'groups' in data:
        # 单章格式：外面包一层
        data = {'chapters': [{'h2': data.get('h2', ''), 'groups': data['groups']}]}
    if 'chapters' not in data:
        raise PlanError("plan.json 缺少 'chapters' 字段")
    return data


def validate_plan(doc: Doc, plan: dict, allow_single: bool = False) -> list[str]:
    """返回问题列表；空列表 = 校验通过。"""
    problems: list[str] = []
    groups_all = []
    for ci, ch_plan in enumerate(plan['chapters'], 1):
        for gi, g in enumerate(ch_plan.get('groups', []), 1):
            groups_all.append((ci, gi, g))

    if not groups_all:
        problems.append('计划里没有任何 group')
        return problems

    seen: dict[int, str] = {}
    by_chapter: dict[int, list] = {}
    for ci, gi, g in groups_all:
        title = (g.get('title') or '').strip()
        items = g.get('items') or []
        tag = f'第{ci}章第{gi}组「{title or "(无标题)"}」'
        if not title:
            problems.append(f'{tag}：缺少 title')
        if has_session_label(title):
            problems.append(f'{tag}：组名含场次标签')
        if OLD_NUM_RE.match(title) and re.match(r'^\d', title):
            problems.append(f'{tag}：组名不应自带编号')
        if len(items) < GROUP_MIN_ITEMS and not allow_single:
            problems.append(f'{tag}：只有 {len(items)} 条，至少要 {GROUP_MIN_ITEMS} 条')
        if len(items) > H4_PER_H3_MAX:
            problems.append(f'{tag}：{len(items)} 条超过上限 {H4_PER_H3_MAX}')
        for raw in items:
            try:
                idx = int(raw)
            except (TypeError, ValueError):
                problems.append(f'{tag}：idx 不是整数：{raw!r}')
                continue
            if idx in seen:
                problems.append(f'{tag}：idx {idx} 重复（已属于 {seen[idx]}）')
                continue
            seen[idx] = tag
            by_chapter.setdefault(ci, []).append(idx)

    valid = {it.idx for it in doc.items}
    missing = sorted(valid - set(seen))
    extra = sorted(set(seen) - valid)
    if missing:
        problems.append(f'遗漏 {len(missing)} 条：{summarize_ids(missing)}')
    if extra:
        problems.append(f'越界 {len(extra)} 个 idx 不存在：{summarize_ids(extra)}')

    # 条目必须落在自己声明的章里
    pos_of = {it.idx: it.chapter_pos for it in doc.items}
    for ci, idxs in by_chapter.items():
        for idx in idxs:
            if pos_of.get(idx) != ci:
                problems.append(
                    f'idx {idx} 属于第 {pos_of.get(idx)} 章，却被放进计划第 {ci} 章')

    # 每章 H3 组数上限
    for ci, ch_plan in enumerate(plan['chapters'], 1):
        n = len(ch_plan.get('groups', []))
        if n > H3_PER_H2_MAX:
            problems.append(f'第{ci}章有 {n} 组，超过上限 {H3_PER_H2_MAX}')

    total_groups = len(groups_all)
    if total_groups > doc.h3_budget:
        problems.append(
            f'全文 {total_groups} 组，超过上限 {doc.h3_budget}'
            f'（字符数 {doc.n_chars} / {H3_CHARS_PER_HEADING}）')

    # 组内顺序 & 章节顺序必须递增（保证原文顺序）
    for ci, ch_plan in enumerate(plan['chapters'], 1):
        last = 0
        for gi, g in enumerate(ch_plan.get('groups', []), 1):
            for raw in g.get('items') or []:
                try:
                    idx = int(raw)
                except (TypeError, ValueError):
                    continue
                if idx < last:
                    problems.append(
                        f'第{ci}章第{gi}组：idx {idx} 小于前一条 {last}（顺序倒挂）')
                last = max(last, idx)

    return problems


def summarize_ids(ids: list[int], limit: int = 12) -> str:
    head = ', '.join(str(i) for i in ids[:limit])
    return head + (f' … (+{len(ids) - limit})' if len(ids) > limit else '')


def apply_plan(doc: Doc, plan: dict) -> str:
    """按计划重建全文，返回新文本（不含 BOM）。"""
    # 每个章的分组计划
    plan_by_chapter: dict[int, list[dict]] = {}
    for ci, ch_plan in enumerate(plan['chapters'], 1):
        plan_by_chapter[ci] = ch_plan.get('groups', [])

    item_by_idx = {it.idx: it for it in doc.items}
    out: list[str] = list(doc.preamble)

    for ci, ch in enumerate(doc.chapters, 1):
        if ch.line:
            out.append(ch.line)
        out.extend(ch.intro)

        groups = plan_by_chapter.get(ci)
        if groups is None:
            # 计划没覆盖这一章 —— 原样保留，交给校验兜住
            for it in ch.items:
                out.append('')
                out.append('### ' + it.raw_title)
                body = strip_blank_edges(it.body)
                if body:
                    out.append('')
                    out.extend(body)
            continue

        h2_no = ch.no or str(ci)
        for m, g in enumerate(groups, 1):
            title = clean_title(g.get('title') or '')
            out.append('')
            out.append(f'### {h2_no}.{m} {title}')
            intro = (g.get('intro') or '').strip()
            if intro:
                out.append('')
                out.append(intro)

            for z, raw_idx in enumerate(g.get('items') or [], 1):
                it = item_by_idx[int(raw_idx)]
                out.append('')
                out.append(f'#### {h2_no}.{m}.{z} {it.title}')
                body = strip_blank_edges(it.body)
                if body:
                    out.append('')
                    out.extend(body)

    # 末尾保证只有一个换行
    while out and not out[-1].strip():
        out.pop()
    return '\n'.join(out) + '\n'


# ---------------------------------------------------------------- 写盘

def atomic_write(path: Path, text: str, eol: str) -> None:
    """原子写：先写 tmp 再 replace，失败不毁旧文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.replace('\n', eol)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix='.tmp')
    tmp = Path(tmp_name)
    try:
        with open(fd, 'wb') as f:
            f.write(data.encode('utf-8'))
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description='结构重排：过碎 H3 → 分组 H3 + 条目 H4')
    ap.add_argument('md', type=Path, help='输入 md')
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--audit', action='store_true', help='只诊断，不写盘')
    mode.add_argument('--plan-out', type=Path,
                      help='导出每章待分组清单到该目录')
    mode.add_argument('--apply-plan', type=Path, help='应用分组计划 JSON')
    ap.add_argument('--out', type=Path, help='输出路径（--apply-plan 用）')
    ap.add_argument('--report', type=Path, help='把审计/校验报告写到文件')
    ap.add_argument('--check-only', action='store_true',
                    help='只校验计划，不写盘')
    ap.add_argument('--allow-single', action='store_true',
                    help='允许单条目组（默认不允许）')
    args = ap.parse_args(argv)

    if not args.md.exists():
        print(f'输入文件不存在：{args.md}', file=sys.stderr)
        return 2

    doc = read_doc(args.md)

    if args.audit:
        text = audit(doc)
        print(text)
        if args.report:
            args.report.write_text(text + '\n', encoding='utf-8')
        return 0

    if args.plan_out:
        files = plan_out(doc, args.plan_out)
        print(f'已导出 {len(files)} 份清单：')
        for p in files:
            print(f'  {p}')
        return 0

    # --apply-plan
    plan = load_plan(args.apply_plan)
    problems = validate_plan(doc, plan, allow_single=args.allow_single)
    report = ['# 分组计划校验', '']
    if problems:
        report.append(f'❌ {len(problems)} 个问题')
        report.extend(f'- {p}' for p in problems)
    else:
        report.append('✅ 全部通过（并集完整、无重复、无遗漏、顺序递增）')
    text = '\n'.join(report)
    print(text)
    if args.report:
        args.report.write_text(text + '\n', encoding='utf-8')
    if problems:
        return 1
    if args.check_only:
        return 0

    if not args.out:
        print('--apply-plan 需要 --out 指定输出路径', file=sys.stderr)
        return 2
    new_text = apply_plan(doc, plan)
    atomic_write(args.out, new_text, doc.eol)

    # 复核新文件的结构
    new_doc = read_doc(args.out)
    print(f'✅ 已写入 {args.out}')
    print(f'   H3(组) = {len(new_doc.chapters)} 章 / '
          f'{sum(len(c.items) for c in new_doc.chapters)} 条目')
    return 0


if __name__ == '__main__':
    sys.exit(main())