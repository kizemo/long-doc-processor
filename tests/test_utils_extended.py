"""test_utils_extended.py — E1 阶段 utils 扩充 8 个工具函数测试

覆盖:
  1. find_files_by_ext:按后缀递归搜索
  2. safe_rename:Windows 文件锁重试
  3. compute_md5:文件 MD5 哈希
  4. atomic_write:原子写(临时文件 → rename)
  5. parse_table_row:markdown 表格行解析
  6. is_cjk:CJK 字符判断
  7. extract_first_h1:提取第一个 H1
  8. normalize_whitespace:空白规范化
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(__file__.replace("\\", "/").rsplit("/", 2)[0]))

import scripts.utils as u
from scripts.utils import (
    find_files_by_ext,
    compute_md5,
    atomic_write,
    is_cjk,
    extract_first_h1,
    normalize_whitespace,
)


# 1. find_files_by_ext

class TestFindFilesByExt(unittest.TestCase):
    def test_finds_md_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.md").write_text("a")
            (root / "b.md").write_text("b")
            (root / "sub").mkdir()
            (root / "sub" / "c.md").write_text("c")
            (root / "d.txt").write_text("d")
            md_files = find_files_by_ext(root, ".md")
            self.assertEqual(len(md_files), 3)
            self.assertTrue(all(f.suffix == ".md" for f in md_files))
            # 排序
            self.assertEqual(md_files[0].name, "a.md")
            self.assertEqual(md_files[-1].name, "c.md")

    def test_ext_without_dot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.json").write_text("{}")
            files = find_files_by_ext(root, "json")
            self.assertEqual(len(files), 1)

    def test_no_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = find_files_by_ext(root, ".md")
            self.assertEqual(files, [])


# 2. safe_rename

class TestSafeRename(unittest.TestCase):
    def test_safe_rename_removed(self):
        """v4.22 F5:safe_rename 已删(0 生产调用),此为占位 test。"""
        self.assertFalse(hasattr(u, "safe_rename"))


# 3. compute_md5

class TestComputeMd5(unittest.TestCase):
    def test_md5_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.md"
            p.write_text("hello world")
            md5_1 = compute_md5(p)
            md5_2 = compute_md5(p)
            self.assertEqual(md5_1, md5_2)
            # 已知 MD5("hello world" = 5eb63bbbe01eeed093cb22bb8f5acdc3)
            self.assertEqual(md5_1, "5eb63bbbe01eeed093cb22bb8f5acdc3")

    def test_md5_different_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            p1 = Path(tmp) / "a.md"
            p2 = Path(tmp) / "b.md"
            p1.write_text("aaa")
            p2.write_text("bbb")
            self.assertNotEqual(compute_md5(p1), compute_md5(p2))


# 4. atomic_write

class TestAtomicWrite(unittest.TestCase):
    def test_writes_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "out.md"
            atomic_write(p, "content")
            self.assertTrue(p.exists())
            self.assertEqual(p.read_text(encoding="utf-8"), "content")

    def test_overwrites_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "out.md"
            p.write_text("old")
            atomic_write(p, "new")
            self.assertEqual(p.read_text(encoding="utf-8"), "new")

    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sub" / "dir" / "out.md"
            atomic_write(p, "nested")
            self.assertTrue(p.exists())
            self.assertEqual(p.read_text(encoding="utf-8"), "nested")


# 5. parse_table_row — 已删(F5),保留 0-test 占位

class TestParseTableRow(unittest.TestCase):
    def test_parse_table_row_removed(self):
        self.assertFalse(hasattr(u, "parse_table_row"))


# 6. is_cjk

class TestIsCjk(unittest.TestCase):
    def test_cjk_chars(self):
        for ch in ['中', '文', '电', '商', '测']:
            self.assertTrue(is_cjk(ch), f"{ch!r} 应是 CJK")

    def test_non_cjk_chars(self):
        for ch in ['a', 'Z', '1', '!', ' ', '\n']:
            self.assertFalse(is_cjk(ch), f"{ch!r} 应不是 CJK")

    def test_invalid_input(self):
        """长度 ≠ 1 → False。"""
        self.assertFalse(is_cjk(""))
        self.assertFalse(is_cjk("ab"))


# 7. extract_first_h1

class TestExtractFirstH1(unittest.TestCase):
    def test_basic(self):
        text = "# Title\n\ncontent\n"
        self.assertEqual(extract_first_h1(text), "Title")

    def test_no_h1(self):
        self.assertIsNone(extract_first_h1("## H2\n\ncontent"))

    def test_h1_with_h2(self):
        text = "## H2 first\n\n# H1 second\n"
        self.assertEqual(extract_first_h1(text), "H1 second")

    def test_cjk_title(self):
        self.assertEqual(extract_first_h1("# 培训讲义\n"), "培训讲义")


# 8. normalize_whitespace

class TestNormalizeWhitespace(unittest.TestCase):
    def test_collapses_spaces(self):
        self.assertEqual(normalize_whitespace("a   b\t\tc"), "a b c")

    def test_strips_trailing(self):
        self.assertEqual(normalize_whitespace("hello   \n"), "hello")

    def test_collapses_blank_lines(self):
        self.assertEqual(normalize_whitespace("a\n\n\n\nb"), "a\n\nb")

    def test_strips_trailing_blanks(self):
        self.assertEqual(normalize_whitespace("a\n\n\n"), "a")

    def test_keeps_meaningful_blank_line(self):
        self.assertEqual(normalize_whitespace("# A\n\ncontent\n\n# B"), "# A\n\ncontent\n\n# B")


if __name__ == "__main__":
    unittest.main(verbosity=2)
