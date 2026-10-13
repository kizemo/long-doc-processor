"""test_verify_all_extended.py — 单元测试 verify_all.py 扩展规则"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.verify_all as va
from scripts.verify_all import (
    verify_file, verify_no_doc_meta_header, verify_no_doc_meta_blockquote,
    verify_h3_lecturer_bio, verify_no_single_subheading,
    verify_training_ad_chapter, verify_no_nested_numbering,
    verify_h4_per_h3_max, verify_h4_total_max,
)


# 完整 cleaned.md 样本(满足 12 条规则)
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
"""


def _write_md(content: str, name: str = 'test.md') -> Path:
    tmpdir = tempfile.mkdtemp()
    path = Path(tmpdir) / name
    path.write_text(content, encoding='utf-8')
    return path, tmpdir


class TestVerifyNoDocMetaHeader(unittest.TestCase):

    def test_pass(self):
        path, tmp = _write_md(GOOD_MD)
        try:
            result = verify_no_doc_meta_header(path)
            self.assertTrue(result.passed)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fail_video_meta(self):
        path, tmp = _write_md(GOOD_MD + '\n本文档由视频转录净化整理...\n')
        try:
            result = verify_no_doc_meta_header(path)
            self.assertFalse(result.passed)
            self.assertIn('本文档', result.message)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fail_original_video(self):
        path, tmp = _write_md(GOOD_MD + '\n原视频为某录制课程\n')
        try:
            result = verify_no_doc_meta_header(path)
            self.assertFalse(result.passed)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestVerifyNoDocMetaBlockquote(unittest.TestCase):

    def test_pass(self):
        path, tmp = _write_md(GOOD_MD)
        try:
            result = verify_no_doc_meta_blockquote(path)
            self.assertTrue(result.passed)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fail_source(self):
        path, tmp = _write_md("# Title\n\n> 课程来源:某直播\n\ncontent\n")
        try:
            result = verify_no_doc_meta_blockquote(path)
            self.assertFalse(result.passed)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestVerifyH3LecturerBio(unittest.TestCase):

    def test_pass(self):
        path, tmp = _write_md(GOOD_MD)
        try:
            result = verify_h3_lecturer_bio(path)
            self.assertTrue(result.passed)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fail_bio_title(self):
        md = """# Title\n\n## 1. 讲师资历与学员痛点\n\ncontent\n"""
        path, tmp = _write_md(md)
        try:
            result = verify_h3_lecturer_bio(path)
            self.assertFalse(result.passed)
            self.assertIn('讲师', result.message)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fail_h4_self_intro(self):
        md = """# Title\n\n## 1. 一章\n\n#### 1.1 自我介绍\n\ncontent\n"""
        path, tmp = _write_md(md)
        try:
            result = verify_h3_lecturer_bio(path)
            self.assertFalse(result.passed)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestVerifyNoSingleSubheading(unittest.TestCase):

    def test_pass(self):
        path, tmp = _write_md(GOOD_MD)
        try:
            result = verify_no_single_subheading(path)
            self.assertTrue(result.passed)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fail_orphan_h3(self):
        md = """# Title\n\n## 1. 一章\n\n### 1.1 only one\n\n#### 1.1.1 only\n\n### 1.2 another\n\ncontent\n"""
        path, tmp = _write_md(md)
        try:
            result = verify_no_single_subheading(path)
            self.assertFalse(result.passed)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestVerifyTrainingAdChapter(unittest.TestCase):

    def test_pass(self):
        path, tmp = _write_md(GOOD_MD)
        try:
            result = verify_training_ad_chapter(path)
            self.assertTrue(result.passed)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fail_year_fee(self):
        md = """# Title\n\n## 1. 课程介绍与年费\n\ncontent\n"""
        path, tmp = _write_md(md)
        try:
            result = verify_training_ad_chapter(path)
            self.assertFalse(result.passed)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fail_qq_scan(self):
        md = """# Title\n\n## 1. 一章\n\ncontent\n\n## 2. 扫码加入我们\n\ncontent\n"""
        path, tmp = _write_md(md)
        try:
            result = verify_training_ad_chapter(path)
            self.assertFalse(result.passed)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestVerifyNoNestedNumbering(unittest.TestCase):

    def test_pass(self):
        path, tmp = _write_md(GOOD_MD)
        try:
            result = verify_no_nested_numbering(path)
            self.assertTrue(result.passed)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fail_h5(self):
        md = """# Title\n\n## 1. 一章\n\n##### 1.1.1.1 too deep\n\ncontent\n"""
        path, tmp = _write_md(md)
        try:
            result = verify_no_nested_numbering(path)
            self.assertFalse(result.passed)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestVerifyH4PerH3Max(unittest.TestCase):

    def test_pass(self):
        path, tmp = _write_md(GOOD_MD)
        try:
            result = verify_h4_per_h3_max(path)
            self.assertTrue(result.passed)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fail_4_h4(self):
        md = """# Title\n\n## 1. 一章\n\n### 1.1 sub\n\n#### 1.1.1 a\n#### 1.1.2 b\n#### 1.1.3 c\n#### 1.1.4 d\n"""
        path, tmp = _write_md(md)
        try:
            result = verify_h4_per_h3_max(path)
            self.assertFalse(result.passed)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestVerifyH4TotalMax(unittest.TestCase):

    def test_pass(self):
        path, tmp = _write_md(GOOD_MD)
        try:
            result = verify_h4_total_max(path)
            self.assertTrue(result.passed)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fail_too_many(self):
        md = """# Title\n\n## 1. 一章\n\n"""
        for i in range(51):
            md += f"### 1.{i+1} h3\n\n#### 1.{i+1}.1 h4\n\n"
        path, tmp = _write_md(md)
        try:
            result = verify_h4_total_max(path)
            self.assertFalse(result.passed)
            self.assertIn('50', result.message)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestVerifyAllIntegration(unittest.TestCase):

    def test_good_md_all_pass(self):
        """GOOD_MD 应通过所有扩展规则"""
        path, tmp = _write_md(GOOD_MD)
        try:
            results = verify_file(path)
            fails = [r for r in results if not r.passed and r.name != 'FRONTMATTER' and r.name != 'CJK_RATIO']
            # GOOD_MD 无 frontmatter + 字符少 → CJK_RATIO 失败正常
            # 但应通过所有扩展规则
            self.assertEqual(fails, [], f"扩展规则失败:{[(r.name, r.message) for r in fails]}")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_bad_md_multiple_fails(self):
        """明显坏的 MD 应触发多条规则"""
        bad_md = """# Title

本文档由视频转录净化整理...
原视频为某课程

> 课程来源:某直播
> 核心主题:某主题

## 1. 讲师资历与学员痛点

### 1.1 自我介绍

#### 1.1.1 more

#### 1.1.2 more

#### 1.1.3 more

#### 1.1.4 too many

##### 1.1.1.1 too deep

## 2. 陪跑服务

## 3. 扫码加入
"""
        path, tmp = _write_md(bad_md)
        try:
            results = verify_file(path)
            fails = [r for r in results if not r.passed]
            # 应有多条规则失败
            self.assertGreater(len(fails), 3,
                              f"期望 ≥3 条规则失败,实际 {len(fails)}:{[(r.name, r.message) for r in fails]}")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
