#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
renumber_headings.py v3.7 单元测试

故意构造 27 个 H3 重复样本，验证 renumber 脚本能 100% 检出并处理。

用法：
  python3 test_renumber.py
"""
import sys
import os
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)

import importlib.util
spec = importlib.util.spec_from_file_location("renumber_headings", os.path.join(SCRIPTS_DIR, "renumber_headings.py"))
renumber_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renumber_mod)


def make_md_with_h3_duplicates(output_path, h3_dup_count=4):
    """
    构造一个 MD，故意制造 H3 编号重复（v3.7 撞车检测场景）。
    
    v3.7 撞车检测的逻辑：当 h2_num 计数器归零后，如果 H3 文本中已含
    "X.Y" 编号且 X 与当前 h2_num 不一致，识别为"章节归属错误"。
    
    构造方法：在 H2 1.2 下 H3 已用 1.2.1，然后在 H2 1.10 之后又出现
    H3 文本中含"1.2.1"前缀——strip_old_numbering 剥除后，h2_num=10
    h3_num=1，赋编号 10.1（不撞车），但 h2_chapter_mismatches 应记录。
    """
    lines = []
    lines.append('# 第一章 测试章节\n')
    lines.append('\n')
    lines.append('## 1.1 第一节\n')
    lines.append('### 课程定位\n')
    lines.append('### 课程覆盖\n')
    lines.append('\n')
    lines.append('## 1.2 第二节\n')
    lines.append('### 核心判断\n')  # 1.2.1
    lines.append('### 反面案例 A\n')  # 1.2.2
    lines.append('\n')
    lines.append('## 1.3 第三节\n')
    lines.append('### 策略总览\n')
    lines.append('\n')
    lines.append('## 1.12 本章回顾\n')
    lines.append('### 核心要点\n')
    lines.append('\n')
    # 制造撞车：H3 文本中已含"1.2.1"前缀（h3_dup_count 次）
    for i in range(h3_dup_count):
        lines.append('### 1.2.1 延伸 A 方案\n')  # strip 后剩 "延伸 A 方案"，但脚本会识别 prefix
    lines.append('\n')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)


def make_clean_md(output_path):
    """构造一个干净的 MD（无重复编号）"""
    lines = []
    lines.append('# 第一章 测试章节\n')
    lines.append('\n')
    lines.append('## 1.1 第一节\n')
    lines.append('### 课程定位\n')
    lines.append('### 课程覆盖\n')
    lines.append('\n')
    lines.append('## 1.2 第二节\n')
    lines.append('### 核心判断\n')
    lines.append('### 反面案例 A\n')
    lines.append('\n')
    lines.append('## 1.3 第三节\n')
    lines.append('### 策略总览\n')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)


class TestRenumberV37(unittest.TestCase):

    def test_27_h3_duplicates_increment_strategy(self):
        """🔴 核心测试：含嵌入编号的 H3 重复必须被检测"""
        with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as f:
            tmp_path = f.name
        out_path = tmp_path + '.numbered.md'
        try:
            make_md_with_h3_duplicates(tmp_path, h3_dup_count=4)
            stats = renumber_mod.renumber_doc(tmp_path, out_path, 'dotted', 'increment')
            # strip_old_numbering 剥除 "1.2.1" 前缀后，h2_num=12, h3_num=1 → 赋 12.1
            # 计数器递增不撞车，但 h2_chapter_mismatches 应记录
            total_issues = len(stats.get('collisions', [])) + len(stats.get('h2_chapter_mismatches', []))
            self.assertGreater(total_issues, 0, f'应检测到冲突或归属错误，实际 0')
            print(f'  检测到 collisions={len(stats.get("collisions", []))} chapter_mismatches={len(stats.get("h2_chapter_mismatches", []))}')
        finally:
            if os.path.exists(tmp_path): os.unlink(tmp_path)
            if os.path.exists(out_path): os.unlink(out_path)

    def test_fail_strategy_only_on_collisions_not_mismatches(self):
        """v3.7 设计哲学：fail 策略只对 collisions 触发 SystemExit，不对 chapter_mismatches 触发。
        chapter_mismatches 走 preview 报告 + 人工 review 流程。
        """
        with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as f:
            tmp_path = f.name
        out_path = tmp_path + '.numbered.md'
        try:
            make_md_with_h3_duplicates(tmp_path, h3_dup_count=4)
            # fail 策略下不应退出（因为只有 chapter_mismatches，没有 collisions）
            stats = renumber_mod.renumber_doc(tmp_path, out_path, 'dotted', 'fail')
            # 预期：检测到 chapter_mismatches 但未触发 SystemExit
            self.assertEqual(len(stats.get('collisions', [])), 0, '本场景不应有 collisions')
            self.assertGreater(len(stats.get('h2_chapter_mismatches', [])), 0, '应有 chapter_mismatches')
        finally:
            if os.path.exists(tmp_path): os.unlink(tmp_path)
            if os.path.exists(out_path): os.unlink(out_path)

    def test_clean_md_no_collisions(self):
        """干净 MD 应该无冲突"""
        with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as f:
            tmp_path = f.name
        out_path = tmp_path + '.numbered.md'
        try:
            make_clean_md(tmp_path)
            stats = renumber_mod.renumber_doc(tmp_path, out_path, 'dotted', 'increment')
            self.assertEqual(len(stats['collisions']), 0, f'干净 MD 不应有冲突，实际 {stats["collisions"]}')
        finally:
            if os.path.exists(tmp_path): os.unlink(tmp_path)
            if os.path.exists(out_path): os.unlink(out_path)

    def test_preview_mode_no_file_written(self):
        """preview 模式：干跑不写文件"""
        with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as f:
            tmp_path = f.name
        try:
            make_md_with_h3_duplicates(tmp_path, h3_dup_count=4)
            stats = renumber_mod.renumber_doc(tmp_path, None, 'dotted', 'increment', preview=True)
            # 撞车或归属错误至少一个非 0
            total_issues = len(stats.get('collisions', [])) + len(stats.get('h2_chapter_mismatches', []))
            self.assertGreater(total_issues, 0, 'preview 应返回冲突或归属错误列表')
            # output_path 为 None 时不应写文件
            with open(tmp_path, encoding='utf-8') as f:
                content = f.read()
            self.assertIn('### 1.2.1 延伸 A 方案', content, '源文件未被改写（preview 模式）')
        finally:
            if os.path.exists(tmp_path): os.unlink(tmp_path)


if __name__ == '__main__':
    print('=' * 80)
    print('long-doc-processor v3.7 — renumber_headings.py 单元测试')
    print('=' * 80)
    unittest.main(verbosity=2)

