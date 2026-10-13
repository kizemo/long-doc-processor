"""test_verify_all_b1.py — B1 阶段新增 8 个 verify 函数单元测试

8 个新规约 × PASS + FAIL = 16 基础 case + 14 边界 case = 30 tests
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.verify_all as va
from scripts.verify_all import (
    verify_no_role_persona_extended,
    verify_hierarchical_numbering,
    verify_no_single_line_blockquote_callout,
    verify_h3_lecturer_bio_extended,
    verify_training_ad_chapter_extended,
    verify_img_size_within_limit,
    verify_no_path_traversal,
    verify_no_doc_meta_header_blockquote,
)


# 公共 helper ----------------------------------------------------

GOOD_MD = """---
type: lecture
---

# 培训讲义

## 1. 第一章

引言段:这是某母婴店的案例,因为 GMV 提升 30%。

### 1.1 案例 A

content

#### 1.1.1 子标题 A1

content

### 1.2 案例 B

content

## 2. 第二章

引言段:这是某服装店的案例。

### 2.1 数据

content

## 3. 总结与行动建议

### 3.1 全文要点回顾

- 要点 1
- 要点 2

### 3.2 行动清单

| 步骤 | 行动 |
|---|---|
| 1 | review |

### 3.3 决策流程

start → end
"""


def _write_md(content: str, name: str = 'test.md'):
    tmpdir = tempfile.mkdtemp()
    path = Path(tmpdir) / name
    path.write_text(content, encoding='utf-8')
    return path, tmpdir


def _cleanup(tmp):
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


# 1. NO_ROLE_PERSONA_EXTENDED (8 tests) ---------------------------

class TestNoRolePersonaExtended(unittest.TestCase):

    def test_pass(self):
        path, tmp = _write_md(GOOD_MD)
        try:
            self.assertTrue(verify_no_role_persona_extended(path).passed)
        finally:
            _cleanup(tmp)

    def test_fail_paragraph_lecturer(self):
        md = GOOD_MD + "\n讲师认为这是关键。\n"
        path, tmp = _write_md(md)
        try:
            r = verify_no_role_persona_extended(path)
            self.assertFalse(r.passed)
        finally:
            _cleanup(tmp)

    def test_fail_table_cell(self):
        """M-07:表格单元格内出现 学员/讲师 也 FAIL。"""
        md = """# Title

## 1. 一章

| 列1 | 列2 |
|---|---|
| 数据 | 学员问的问题 |
"""
        path, tmp = _write_md(md)
        try:
            r = verify_no_role_persona_extended(path)
            self.assertFalse(r.passed)
            self.assertIn("table", ' '.join(r.details).lower())
        finally:
            _cleanup(tmp)

    def test_quote_exempt(self):
        """引号内讲师原话是合法例外。"""
        md = """# Title

## 1. 一章

"讲师认为这是关键指标"。
"""
        path, tmp = _write_md(md)
        try:
            self.assertTrue(verify_no_role_persona_extended(path).passed)
        finally:
            _cleanup(tmp)


# 2. HIERARCHICAL_NUMBERING (4 tests) ----------------------------

class TestHierarchicalNumbering(unittest.TestCase):

    def test_pass_sequential(self):
        path, tmp = _write_md(GOOD_MD)
        try:
            r = verify_hierarchical_numbering(path)
            self.assertTrue(r.passed, f"应 PASS,实际 {r.message}: {r.details}")
        finally:
            _cleanup(tmp)

    def test_fail_skip_h2(self):
        """H2 跳号:1 → 3。"""
        md = """# Title

## 1. 一章

content

## 3. 跳到 3

content
"""
        path, tmp = _write_md(md)
        try:
            r = verify_hierarchical_numbering(path)
            self.assertFalse(r.passed)
        finally:
            _cleanup(tmp)

    def test_fail_skip_h3(self):
        """H3 跳号:1.1 → 1.3。"""
        md = """# Title

## 1. 一章

### 1.1 案例 A

content

### 1.3 跳到 1.3

content
"""
        path, tmp = _write_md(md)
        try:
            r = verify_hierarchical_numbering(path)
            self.assertFalse(r.passed)
        finally:
            _cleanup(tmp)

    def test_pass_no_h2(self):
        """无 H2 编号 → PASS(空状态)。"""
        md = """# Title

content only
"""
        path, tmp = _write_md(md)
        try:
            self.assertTrue(verify_hierarchical_numbering(path).passed)
        finally:
            _cleanup(tmp)


# 3. NO_SINGLE_LINE_BLOCKQUOTE_CALLOUT (4 tests) ----------------

class TestNoSingleLineBlockquoteCallout(unittest.TestCase):

    def test_pass(self):
        path, tmp = _write_md(GOOD_MD)
        try:
            self.assertTrue(verify_no_single_line_blockquote_callout(path).passed)
        finally:
            _cleanup(tmp)

    def test_fail_single_line_callout(self):
        """单行 `>` 引用块作视觉强调 → FAIL。"""
        md = """# Title

## 1. 一章

> 这是单行 callout

content
"""
        path, tmp = _write_md(md)
        try:
            r = verify_no_single_line_blockquote_callout(path)
            self.assertFalse(r.passed)
        finally:
            _cleanup(tmp)

    def test_pass_multiline_box(self):
        """多行 `>` box (≥2 行) 合法。"""
        md = """# Title

## 1. 一章

> 这是 box 第 1 行
> 这是 box 第 2 行
> 这是 box 第 3 行

content
"""
        path, tmp = _write_md(md)
        try:
            self.assertTrue(verify_no_single_line_blockquote_callout(path).passed)
        finally:
            _cleanup(tmp)

    def test_pass_normal_blockquote(self):
        """H1 后的 `> 课程来源:` 仍算单行 callout → FAIL(本规则抓所有单行)。"""
        md = """# Title

> 课程来源: 2026-09-12 直播
> 核心主题: 电商培训

## 1. 一章

content
"""
        path, tmp = _write_md(md)
        try:
            r = verify_no_single_line_blockquote_callout(path)
            # 2 行连续算 box → PASS(本规则是单行 callout 检测,box 合法)
            self.assertTrue(r.passed)
        finally:
            _cleanup(tmp)


# 4. H3_LECTURER_BIO_EXTENDED (4 tests) --------------------------

class TestH3LecturerBioExtended(unittest.TestCase):

    def test_pass(self):
        path, tmp = _write_md(GOOD_MD)
        try:
            self.assertTrue(verify_h3_lecturer_bio_extended(path).passed)
        finally:
            _cleanup(tmp)

    def test_fail_v4_14_keyword(self):
        """v4.14 新关键词:主讲人资历。"""
        md = """# Title

## 1. 主讲人资历

content
"""
        path, tmp = _write_md(md)
        try:
            r = verify_h3_lecturer_bio_extended(path)
            self.assertFalse(r.passed)
        finally:
            _cleanup(tmp)

    def test_fail_offline_keyword(self):
        """v4.14 新关键词:线下 / 招生。"""
        md = """# Title

## 1. 一章

### 1.1 线下 5 天集训

content
"""
        path, tmp = _write_md(md)
        try:
            r = verify_h3_lecturer_bio_extended(path)
            self.assertFalse(r.passed)
        finally:
            _cleanup(tmp)

    def test_fail_recruitment(self):
        """v4.14 新关键词:招生 / 系统课。"""
        md = """# Title

## 1. 招生说明

### 1.1 系统课价格

content
"""
        path, tmp = _write_md(md)
        try:
            r = verify_h3_lecturer_bio_extended(path)
            self.assertFalse(r.passed)
        finally:
            _cleanup(tmp)


# 5. TRAINING_AD_CHAPTER_EXTENDED (4 tests) ---------------------

class TestTrainingAdChapterExtended(unittest.TestCase):

    def test_pass(self):
        path, tmp = _write_md(GOOD_MD)
        try:
            self.assertTrue(verify_training_ad_chapter_extended(path).passed)
        finally:
            _cleanup(tmp)

    def test_fail_member_price(self):
        """v4.14 新关键词:会员价。"""
        md = """# Title

## 1. 会员价优惠

content
"""
        path, tmp = _write_md(md)
        try:
            r = verify_training_ad_chapter_extended(path)
            self.assertFalse(r.passed)
        finally:
            _cleanup(tmp)

    def test_fail_offline_system(self):
        """v4.14 新关键词:线下系统课程。"""
        md = """# Title

## 1. 线下系统课程介绍

content
"""
        path, tmp = _write_md(md)
        try:
            r = verify_training_ad_chapter_extended(path)
            self.assertFalse(r.passed)
        finally:
            _cleanup(tmp)

    def test_fail_cart_link(self):
        """v4.14 新关键词:购物车链接报名。"""
        md = """# Title

## 1. 购物车链接报名流程

content
"""
        path, tmp = _write_md(md)
        try:
            r = verify_training_ad_chapter_extended(path)
            self.assertFalse(r.passed)
        finally:
            _cleanup(tmp)


# 6. IMG_SIZE_WITHIN_LIMIT (3 tests) ----------------------------

class TestImgSizeWithinLimit(unittest.TestCase):

    def test_pass_no_img(self):
        """无图 → PASS。"""
        path, tmp = _write_md(GOOD_MD)
        try:
            r = verify_img_size_within_limit(path)
            self.assertTrue(r.passed)
        finally:
            _cleanup(tmp)

    def test_pass_small_img(self):
        """小图(<200KB,<800x600) → PASS。"""
        from PIL import Image
        path, tmp = _write_md(GOOD_MD)
        try:
            # 写一张 100x100 的小 png
            img_path = Path(tmp) / "small.png"
            Image.new("RGB", (100, 100), color="red").save(img_path)
            md_with_img = GOOD_MD + f"\n\n![small]({img_path.name})\n"
            md_file = Path(tmp) / "with_img.md"
            md_file.write_text(md_with_img, encoding="utf-8")
            r = verify_img_size_within_limit(md_file)
            self.assertTrue(r.passed, f"应 PASS,实际 {r.message}: {r.details}")
        finally:
            _cleanup(tmp)

    def test_fail_oversize_dim(self):
        """超 800x600 → FAIL。"""
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("PIL 未装,跳过")
        path, tmp = _write_md(GOOD_MD)
        try:
            img_path = Path(tmp) / "big.png"
            Image.new("RGB", (1000, 1000), color="red").save(img_path)
            md_with_img = GOOD_MD + f"\n\n![big]({img_path.name})\n"
            md_file = Path(tmp) / "with_img.md"
            md_file.write_text(md_with_img, encoding="utf-8")
            r = verify_img_size_within_limit(md_file)
            self.assertFalse(r.passed)
        finally:
            _cleanup(tmp)


# 7. NO_PATH_TRAVERSAL (3 tests) --------------------------------

class TestNoPathTraversal(unittest.TestCase):

    def test_pass(self):
        path, tmp = _write_md(GOOD_MD)
        try:
            self.assertTrue(verify_no_path_traversal(path).passed)
        finally:
            _cleanup(tmp)

    def test_fail_img_path_traversal(self):
        md = """# Title

## 1. 一章

![img](../../etc/passwd)
"""
        path, tmp = _write_md(md)
        try:
            r = verify_no_path_traversal(path)
            self.assertFalse(r.passed)
        finally:
            _cleanup(tmp)

    def test_fail_link_path_traversal(self):
        md = """# Title

## 1. 一章

[link](../../../sensitive)
"""
        path, tmp = _write_md(md)
        try:
            r = verify_no_path_traversal(path)
            self.assertFalse(r.passed)
        finally:
            _cleanup(tmp)


# 8. NO_DOC_META_HEADER_BLOCKQUOTE (2 tests) --------------------

class TestNoDocMetaHeaderBlockquote(unittest.TestCase):

    def test_pass(self):
        path, tmp = _write_md(GOOD_MD)
        try:
            self.assertTrue(verify_no_doc_meta_header_blockquote(path).passed)
        finally:
            _cleanup(tmp)

    def test_fail_h1_followed_by_blockquote(self):
        """H1 后紧跟 blockquote → FAIL。"""
        md = """# Title

> 课程来源: 2026-09-12

## 1. 一章

content
"""
        path, tmp = _write_md(md)
        try:
            r = verify_no_doc_meta_header_blockquote(path)
            self.assertFalse(r.passed)
        finally:
            _cleanup(tmp)


# 9. 集成测试(2 tests) ------------------------------------------

class TestB1Integration(unittest.TestCase):

    def test_good_md_passes_all_b1_rules(self):
        """GOOD_MD 应通过所有 8 个 B1 新规约。"""
        path, tmp = _write_md(GOOD_MD)
        try:
            rules = [
                verify_no_role_persona_extended,
                verify_hierarchical_numbering,
                verify_no_single_line_blockquote_callout,
                verify_h3_lecturer_bio_extended,
                verify_training_ad_chapter_extended,
                verify_img_size_within_limit,
                verify_no_path_traversal,
                verify_no_doc_meta_header_blockquote,
            ]
            for rule in rules:
                r = rule(path)
                self.assertTrue(
                    r.passed,
                    f"{rule.__name__} 应 PASS,实际 {r.message}: {r.details}"
                )
        finally:
            _cleanup(tmp)

    def test_all_8_rules_registered(self):
        """RULES 注册表应含全部 8 个 B1 新规约。"""
        names = [name for name, _ in va.RULES]
        for name in [
            'NO_ROLE_PERSONA_EXTENDED',
            'HIERARCHICAL_NUMBERING',
            'NO_SINGLE_LINE_BLOCKQUOTE_CALLOUT',
            'H3_LECTURER_BIO_EXTENDED',
            'TRAINING_AD_CHAPTER_EXTENDED',
            'IMG_SIZE_WITHIN_LIMIT',
            'NO_PATH_TRAVERSAL',
            'NO_DOC_META_HEADER_BLOCKQUOTE',
        ]:
            self.assertIn(name, names, f"{name} 未注册")


if __name__ == '__main__':
    unittest.main(verbosity=2)
