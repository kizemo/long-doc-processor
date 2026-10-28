"""tests/test_restructure_outline.py — v4.24 结构重排（Phase 2.5）回归测试。

判别性写法：不只测「函数返回了什么」，而是测「阈值是否真的按文档规模变化」。
最关键的一条是 `test_h3_budget_proportional_discriminates`：
**同一份 61 组的分组计划**，在 19 万字符文档上必须判合规、在 3 万字符文档上必须判超限。
v4.24 之前的固定常量 `H3_TOTAL_MAX = 60` 会让前者也被判死（真实事故）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from restructure_outline import (  # noqa: E402
    GROUP_MIN_ITEMS,
    H3_CHARS_PER_HEADING,
    H3_PER_H2_MAX,
    H3_TOTAL_BASE,
    H4_PER_H3_MAX,
    apply_plan,
    clean_title,
    has_session_label,
    read_doc,
    validate_plan,
)

# ----------------------------------------------------------------------
# 合成文档 & 计划
# ----------------------------------------------------------------------

def _build_md(item_counts: list[int], body_chars: int = 60) -> str:
    """item_counts[ci] = 第 ci+1 章有几个 H3（每个 H3 带 1 段正文）。"""
    out = ["# 合成笔记", ""]
    for ci, n in enumerate(item_counts, 1):
        out += [f"## {ci}. 第{ci}章", ""]
        for k in range(1, n + 1):
            out += [f"### {ci}.{k} 第一天上午：知识点{ci}-{k}", "", "正" * body_chars, ""]
    return "\n".join(out)


def _doc(tmp_path: Path, item_counts: list[int], body_chars: int = 60):
    p = tmp_path / "d.md"
    p.write_text(_build_md(item_counts, body_chars), encoding="utf-8")
    return read_doc(p)


def _plan_from(doc, sizes_per_chapter: list[list[int]]) -> dict:
    """按「每章各组收几条」把 doc 的条目顺序切组。"""
    chapters = []
    for ci, ch in enumerate(doc.chapters):
        groups, pos = [], 0
        for gi, size in enumerate(sizes_per_chapter[ci], 1):
            ids = [it.idx for it in ch.items[pos:pos + size]]
            pos += size
            groups.append({"title": f"主题{ci + 1}-{gi}", "items": ids,
                           "intro": "这一组讲什么。"})
        chapters.append({"no": ch.no, "h2": ch.raw_title, "groups": groups})
    return {"chapters": chapters}


# ----------------------------------------------------------------------
# 1) 标题清洗：场次标签必修剥离
# ----------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("1.1 第一天上午：新品推广不能依赖硬推", "新品推广不能依赖硬推"),
    ("2.13 第二天下午：关键词出价的三种方式", "关键词出价的三种方式"),
    ("1.2 第一天上午 货品分层决定流量采购方式", "货品分层决定流量采购方式"),
    ("货品分层决定流量采购方式", "货品分层决定流量采购方式"),
])
def test_clean_title_strips_session_label(raw, expected):
    assert clean_title(raw) == expected


def test_clean_title_strips_old_numbering():
    # 旧编号必须剥干净，不能留下 "1.1" 或孤立的分隔符
    got = clean_title("3.7 掌握精准人群运营")
    assert got == "掌握精准人群运营"


def test_has_session_label_detects_and_clears():
    assert has_session_label("1.1 第一天上午：新品推广不能依赖硬推") is True
    assert has_session_label("1.1 新品推广不能依赖硬推") is False


# ----------------------------------------------------------------------
# 2) 解析：层级、条目数、字符数
# ----------------------------------------------------------------------

def test_read_doc_parses_levels(tmp_path):
    doc = _doc(tmp_path, [3, 2])
    assert len(doc.chapters) == 2
    assert doc.n_h3 == 5
    assert doc.n_chars > 0
    assert all("第一天上午" not in it.title for it in doc.items)


# ----------------------------------------------------------------------
# 3) 预算比例化（v4.24 核心修复）
# ----------------------------------------------------------------------

def test_h3_budget_floor_for_short_doc(tmp_path):
    doc = _doc(tmp_path, [3], body_chars=60)
    assert doc.h3_budget == H3_TOTAL_BASE


def test_h3_budget_grows_with_chars(tmp_path):
    doc = _doc(tmp_path, [40], body_chars=2000)
    assert doc.h3_budget == max(H3_TOTAL_BASE, doc.n_chars // H3_CHARS_PER_HEADING)
    assert doc.h3_budget > H3_TOTAL_BASE


def test_h3_budget_proportional_discriminates(tmp_path):
    """同一份 61 组：长文档合规、短文档超限。固定上限常量做不到这一点。"""
    # 61 组 = 每章 18/18/9/10/5/1 组，每组 2 条 ⇒ 122 条
    chapters_groups = [[2] * 18, [2] * 18, [2] * 9, [2] * 10, [2] * 5, [2] * 1]
    item_counts = [sum(g) for g in chapters_groups]
    assert sum(len(g) for g in chapters_groups) == 61

    # 长文档：约 19.5 万字符 ⇒ 预算 ≈ 65，61 组必须放行
    long_doc = _doc(tmp_path, item_counts, body_chars=1600)
    long_plan = _plan_from(long_doc, chapters_groups)
    assert long_doc.h3_budget >= 61, long_doc.h3_budget
    assert validate_plan(long_doc, long_plan) == []

    # 短文档：同样 61 组，预算 = 20 ⇒ 必须判超限
    short_dir = tmp_path / "short"
    short_dir.mkdir()
    short_doc = _doc(short_dir, item_counts, body_chars=10)
    short_plan = _plan_from(short_doc, chapters_groups)
    assert short_doc.h3_budget == H3_TOTAL_BASE
    assert validate_plan(short_doc, short_plan) != []


# ----------------------------------------------------------------------
# 4) 计划守恒校验
# ----------------------------------------------------------------------

def test_validate_plan_accepts_complete_plan(tmp_path):
    doc = _doc(tmp_path, [4, 4])
    plan = _plan_from(doc, [[2, 2], [2, 2]])
    assert validate_plan(doc, plan) == []


def test_validate_plan_rejects_missing_item(tmp_path):
    doc = _doc(tmp_path, [4])
    plan = _plan_from(doc, [[2, 2]])
    plan["chapters"][0]["groups"][1]["items"] = plan["chapters"][0]["groups"][1]["items"][:-1]
    assert validate_plan(doc, plan) != []


def test_validate_plan_rejects_duplicate_item(tmp_path):
    doc = _doc(tmp_path, [4])
    plan = _plan_from(doc, [[2, 2]])
    g = plan["chapters"][0]["groups"]
    g[1]["items"] = [g[0]["items"][0], g[1]["items"][1]]
    assert validate_plan(doc, plan) != []


def test_validate_plan_rejects_out_of_order(tmp_path):
    doc = _doc(tmp_path, [4])
    plan = _plan_from(doc, [[2, 2]])
    plan["chapters"][0]["groups"] = plan["chapters"][0]["groups"][::-1]
    assert validate_plan(doc, plan) != []


def test_validate_plan_rejects_single_item_group(tmp_path):
    doc = _doc(tmp_path, [3])
    plan = _plan_from(doc, [[1, 2]])   # 第一组只收 1 条
    assert validate_plan(doc, plan) != []
    # 显式放行时才允许单条组
    assert validate_plan(doc, plan, allow_single=True) == []


def test_validate_plan_reports_too_many_groups_per_chapter(tmp_path):
    doc = _doc(tmp_path, [(H3_PER_H2_MAX + 1) * 2])
    plan = _plan_from(doc, [[2] * (H3_PER_H2_MAX + 1)])
    assert validate_plan(doc, plan) != []


def test_validate_plan_reports_oversized_group(tmp_path):
    doc = _doc(tmp_path, [H4_PER_H3_MAX + 1])
    plan = _plan_from(doc, [[H4_PER_H3_MAX + 1]])
    assert validate_plan(doc, plan) != []


# ----------------------------------------------------------------------
# 5) 应用：层级重排 + 正文守恒 + 标签清零
# ----------------------------------------------------------------------

def test_apply_plan_promotes_groups_to_h3(tmp_path):
    doc = _doc(tmp_path, [4, 4], body_chars=200)
    plan = _plan_from(doc, [[2, 2], [2, 2]])
    out = apply_plan(doc, plan)

    h3 = [ln for ln in out.splitlines() if ln.startswith("### ")]
    h4 = [ln for ln in out.splitlines() if ln.startswith("#### ")]
    assert len(h3) == 4          # 4 个主题组
    assert len(h4) == 8          # 8 条知识点降为 H4
    assert "第一天上午" not in out
    # H4 用两级编号 1.1.1
    assert h4[0].startswith("#### 1.1.1 ")
    # 正文不能丢
    assert "正" * 200 in out


def test_apply_plan_keeps_group_intro(tmp_path):
    doc = _doc(tmp_path, [2])
    plan = _plan_from(doc, [[2]])
    out = apply_plan(doc, plan)
    assert "这一组讲什么。" in out


def test_group_min_items_matches_contract():
    assert GROUP_MIN_ITEMS == 2