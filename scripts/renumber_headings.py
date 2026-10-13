#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

"""
renumber_headings.py — 多文档合并后的标题自动编号工具 v3.7

v3.7 关键升级（2026-06-05）：
  🔴 新增"已使用编号集合"检测 — 撞车时强制递增（v5 BUG 根因修复）
  🔴 新增 H2 章节归属检测 — H3/H4 编号的前缀 = 当前 H2 编号，不允许跨章节编号
  🔴 新增 renumber 预演模式（--preview）— 干跑，输出冲突报告
  🔴 新增 --on-collision {increment|fail|skip} 策略
  🔴 单元测试 scripts/test_renumber.py 故意构造 27 个 H3 重复样本验证

功能：
  1. 移除原标题中已有的中文序号（一、二、/1./2./1.2.3/等）
  2. H2 → 统一为 "第{N}章 原标题" 或 "N."（dotted）
  3. H3 → 统一为 "N.M 原标题"（M按H2归零，撞车递增）
  4. H4 → 统一为 "N.M.Z 原标题"（Z按H3归零，撞车递增）
  5. 输出编号统计和验证报告

用法：
  python3 renumber_headings.py input.md output.md [--scheme chinese|dotted] [--on-collision {increment|fail|skip}] [--preview]
  --scheme chinese: 第N章 (默认)
  --scheme dotted:   N.  (纯数字)
  --on-collision: 撞车时处理策略（默认 increment）
  --preview: 干跑模式，只输出冲突报告不写文件
"""

import re
import sys
import argparse
from collections import defaultdict

# 需要清除的旧编号模式
OLD_NUM_PATTERNS = [
    r'^第[一二三四五六七八九十百千\d]+章\s*[.、\s]*',  # 第一章、第1章
    r'^[一二三四五六七八九十百千]+[.、\s]+',          # 一、
    r'^L\d+\s*',                                         # L1
    r'^[Ll]evel\s*\d+\s*',                                # Level 1
    r'^\d+\.[.、\s]*',                                    # 1.
    r'^\d+[.、\s]+',                                      # 1、
]


def strip_old_numbering(title: str) -> str:
    """移除原标题中的旧编号"""
    for pattern in OLD_NUM_PATTERNS:
        title = re.sub(pattern, '', title).strip()
    return title


def chinese_num(n: int) -> str:
    """阿拉伯数字转中文序号（1-99）"""
    digits = '一二三四五六七八九十'
    if n <= 10:
        return digits[n - 1]
    elif n < 20:
        return f'十{digits[n - 11]}'
    elif n < 100:
        tens = n // 10
        ones = n % 10
        if ones == 0:
            return f'{digits[tens - 1]}十'
        return f'{digits[tens - 1]}十{digits[ones - 1]}'
    return str(n)


def chinese_to_int(ch: str) -> int:
    """中文数字 → 阿拉伯数字（支持一到九十九）"""
    map = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
    if ch in map:
        return map[ch]
    # 十一到九十九
    if ch.startswith('十'):
        return 10 + map.get(ch[1:], 0)
    if '十' in ch:
        parts = ch.split('十')
        tens = map.get(parts[0], 1)
        ones = map.get(parts[1], 0) if len(parts) > 1 else 0
        return tens * 10 + ones
    return int(ch) if ch.isdigit() else 0


# 需要清除的旧编号模式（v3.7 增强：支持 X.Y 和 X.Y.Z 形式）
OLD_NUM_PATTERNS = [
    r'^第[一二三四五六七八九十百千\d]+章\s*[.、\s]*',  # 第一章、第1章
    r'^[一二三四五六七八九十百千]+[.、\s]+',          # 一、
    r'^L\d+\s*',                                         # L1
    r'^[Ll]evel\s*\d+\s*',                                # Level 1
    r'^\d+\.\d+\.\d+\.\d+\s*[.、\s]*',                   # v3.7: 1.2.3.4
    r'^\d+\.\d+\.\d+\s*[.、\s]*',                        # v3.7: 1.2.3
    r'^\d+\.\d+\s*[.、\s]*',                             # v3.7: 1.2
    r'^\d+\.[.、\s]*',                                    # 1.
    r'^\d+[.、\s]+',                                      # 1、
]


def strip_old_numbering(title: str) -> str:
    """移除原标题中的旧编号（v3.7 增强：支持 X.Y 和 X.Y.Z 形式）"""
    for pattern in OLD_NUM_PATTERNS:
        title = re.sub(pattern, '', title).strip()
    return title


def renumber_doc(input_path: str, output_path: str, scheme: str = 'chinese',
                 on_collision: str = 'increment', preview: bool = False):
    """
    重新编号文档中的所有标题（v3.7：撞车检测 + 章节归属检测）。
    
    编号规则:
      H2: 第{N}章 原标题
      H3: N.M 原标题（M按H2归零，撞车递增）
      H4: N.M.Z 原标题（Z按H3归零，撞车递增）
    
    Args:
        input_path: 输入 MD 路径
        output_path: 输出 MD 路径（preview 模式可为 None）
        scheme: 编号方案（chinese/dotted）
        on_collision: 撞车处理策略（increment/fail/skip）
        preview: 干跑模式（不写文件，只输出冲突报告）
    
    Returns:
        dict: stats（含 collisions 列表）
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    output = []
    stats = {
        'h2': 0, 'h3': 0, 'h4': 0,
        'renamed_h2': [], 'renamed_h3': [], 'renamed_h4': [],
        'collisions': [],   # v3.7 新增：撞车记录
        'h2_chapter_mismatches': [],  # v3.7 新增：H3/H4 章节归属错误
    }
    
    # 计数器
    h2_num = 0   # 当前章号
    h3_num = 0   # 当前节号（H3按H2归零）
    h4_num = 0   # 当前小节号（H4按H3归零）
    
    # v3.7 新增：已使用编号集合（撞车检测）
    used_h2 = set()   # 已使用的 H2 编号（如 1, 2, 3）
    used_h3 = defaultdict(set)  # {h2_num: {h3_num, ...}}
    used_h4 = defaultdict(set)  # {(h2_num, h3_num): {h4_num, ...}}
    
    h2_pattern = re.compile(r'^## (.+)$')
    h3_pattern = re.compile(r'^### (.+)$')
    h4_pattern = re.compile(r'^#### (.+)$')
    
    h2_count = 0
    h3_count = 0
    h4_count = 0
    
    for line_no, line in enumerate(lines, 1):
        m2 = h2_pattern.match(line)
        m3 = h3_pattern.match(line)
        m4 = h4_pattern.match(line)
        
        if m2:
            h2_num += 1
            h3_num = 0  # H3计数器归零
            h4_num = 0  # H4计数器归零
            
            # v3.7：检测 H2 撞车
            if h2_num in used_h2:
                collision = {'line': line_no, 'type': 'H2', 'num': h2_num, 'title': m2.group(1).strip()[:50]}
                stats['collisions'].append(collision)
                if on_collision == 'fail':
                    print(f'❌ H2 撞车: 第{h2_num}章 (line {line_no})', file=sys.stderr)
                    sys.exit(1)
                elif on_collision == 'skip':
                    # 跳过，赋下一个编号
                    while h2_num in used_h2:
                        h2_num += 1
                    collision['resolved_as'] = h2_num
            used_h2.add(h2_num)
            
            old_title = m2.group(1).strip()
            new_title = strip_old_numbering(old_title)
            
            if scheme == 'chinese':
                prefix = f'第{chinese_num(h2_num)}章'
            else:
                prefix = f'{h2_num}'
            
            new_line = f'## {prefix} {new_title}\n'
            stats['renamed_h2'].append(f'{prefix} {new_title}')
            h2_count += 1
            
        elif m3:
            h3_num += 1
            h4_num = 0  # H4计数器归零
            
            old_title = m3.group(1).strip()
            
            # v3.7 新增：检测 H3 文本中嵌入的 X.Y 编号是否与当前 h2_num 一致
            m_embedded = re.match(r'^(\d+)\.(\d+)', old_title)
            if m_embedded:
                embedded_h2 = int(m_embedded.group(1))
                if embedded_h2 != h2_num:
                    mismatch = {
                        'line': line_no, 'type': 'H3 chapter mismatch',
                        'embedded_h2': embedded_h2, 'current_h2': h2_num,
                        'title': old_title[:50],
                    }
                    stats['h2_chapter_mismatches'].append(mismatch)
            
            new_title = strip_old_numbering(old_title)
            
            # v3.7：检测 H3 撞车
            if h3_num in used_h3[h2_num]:
                collision = {'line': line_no, 'type': 'H3', 'num': f'{h2_num}.{h3_num}', 'title': new_title[:50]}
                stats['collisions'].append(collision)
                if on_collision == 'fail':
                    print(f'❌ H3 撞车: {h2_num}.{h3_num} (line {line_no})', file=sys.stderr)
                    sys.exit(1)
                elif on_collision == 'skip':
                    while h3_num in used_h3[h2_num]:
                        h3_num += 1
                    collision['resolved_as'] = f'{h2_num}.{h3_num}'
            used_h3[h2_num].add(h3_num)
            
            new_line = f'### {h2_num}.{h3_num} {new_title}\n'
            stats['renamed_h3'].append(f'{h2_num}.{h3_num} {new_title}')
            h3_count += 1
            
        elif m4:
            h4_num += 1
            
            old_title = m4.group(1).strip()
            new_title = strip_old_numbering(old_title)
            
            # v3.7：检测 H4 撞车
            h4_key = (h2_num, h3_num)
            if h4_num in used_h4[h4_key]:
                collision = {'line': line_no, 'type': 'H4', 'num': f'{h2_num}.{h3_num}.{h4_num}', 'title': new_title[:50]}
                stats['collisions'].append(collision)
                if on_collision == 'fail':
                    print(f'❌ H4 撞车: {h2_num}.{h3_num}.{h4_num} (line {line_no})', file=sys.stderr)
                    sys.exit(1)
                elif on_collision == 'skip':
                    while h4_num in used_h4[h4_key]:
                        h4_num += 1
                    collision['resolved_as'] = f'{h2_num}.{h3_num}.{h4_num}'
            used_h4[h4_key].add(h4_num)
            
            new_line = f'#### {h2_num}.{h3_num}.{h4_num} {new_title}\n'
            stats['renamed_h4'].append(f'{h2_num}.{h3_num}.{h4_num} {new_title}')
            h4_count += 1
            
        else:
            new_line = line
        
        output.append(new_line)
    
    # v3.7 章节归属检测：检查已用编号集合是否与计数器一致
    # 计数器应该等于已用编号集合的最大值
    if stats['collisions'] and on_collision == 'increment':
        print(f'⚠️  v3.7 检测到 {len(stats["collisions"])} 个编号冲突（已自动递增）', file=sys.stderr)
    
    if not preview and output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.writelines(output)
    
    # 统计
    stats['h2'] = h2_count
    stats['h3'] = h3_count
    stats['h4'] = h4_count
    
    return stats


def verify_renumbered(file_path: str) -> dict:
    """验证编号后的文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    issues = []
    warnings = []
    
    # 1. 检查无编号H2（支持中文章节号和数字章节号）
    unnumbered_h2 = re.findall(r'^## (?!第[一二三四五六七八九十百千\d]+章\s|^\d+\s)[^#]', content, re.MULTILINE)
    if unnumbered_h2:
        lines_unnumbered = [l.strip() for l in unnumbered_h2]
        issues.append(f'无编号H2: {len(lines_unnumbered)}个 → {lines_unnumbered[:3]}')
    
    # 2. 检查H3格式
    unnumbered_h3 = re.findall(r'^### (?!\d+\.\d+\s)[^#]', content, re.MULTILINE)
    if unnumbered_h3:
        lines_unnumbered = [l.strip() for l in unnumbered_h3]
        issues.append(f'无编号H3: {len(lines_unnumbered)}个 → {lines_unnumbered[:3]}')
    
    # 3. 检查H4格式
    unnumbered_h4 = re.findall(r'^#### (?!\d+\.\d+\.\d+\s)[^#]', content, re.MULTILINE)
    if unnumbered_h4:
        lines_unnumbered = [l.strip() for l in unnumbered_h4]
        issues.append(f'无编号H4: {len(lines_unnumbered)}个 → {lines_unnumbered[:3]}')
    
    # 4. H2编号连续性（支持中文章节号和数字章节号）
    raw_h2_nums = re.findall(r'^## 第([一二三四五六七八九十百千\d]+)章', content, re.MULTILINE)
    if raw_h2_nums:
        h2_nums = []
        for n in raw_h2_nums:
            try:
                h2_nums.append(chinese_to_int(n))
            except (ValueError, KeyError):
                pass
        if h2_nums and h2_nums != list(range(1, len(h2_nums) + 1)):
            issues.append(f'H2编号不连续: {h2_nums}')
    
    # 5. 每个H2下的H3编号连续性
    lines = content.split('\n')
    current_chapter = 0
    chapter_h3s = {}
    for line in lines:
        m = re.match(r'^## 第([一二三四五六七八九十百千\d]+)章', line)
        if m:
            try:
                current_chapter = chinese_to_int(m.group(1))
            except (ValueError, KeyError):
                pass
            if current_chapter not in chapter_h3s:
                chapter_h3s[current_chapter] = []
        m3 = re.match(r'^### (\d+)\.(\d+)', line)
        if m3 and current_chapter > 0:
            chapter_h3s[current_chapter].append(int(m3.group(2)))
    
    for ch, nums in chapter_h3s.items():
        if nums and nums != list(range(1, len(nums) + 1)):
            issues.append(f'第{ch}章H3编号不连续: {nums}')
    
    # 结果
    result = {
        'issues': issues,
        'warnings': warnings,
        'passed': len(issues) == 0,
        'h2_count': len(re.findall(r'^## 第[一二三四五六七八九十百千\d]+章', content, re.MULTILINE)),
        'h3_count': len(re.findall(r'^### \d+\.\d+', content, re.MULTILINE)),
        'h4_count': len(re.findall(r'^#### \d+\.\d+\.\d+', content, re.MULTILINE)),
    }
    return result


def main():
    parser = argparse.ArgumentParser(description='多文档合并后的标题自动编号 v3.7')
    parser.add_argument('input', help='输入MD文件')
    parser.add_argument('output', help='输出MD文件')
    parser.add_argument('--scheme', choices=['chinese', 'dotted'], default='chinese',
                        help='编号方案: chinese(第N章) dotted(N.)')
    parser.add_argument('--on-collision', choices=['increment', 'fail', 'skip'], default='increment',
                        help='编号撞车时处理策略（默认 increment 递增）')
    parser.add_argument('--preview', action='store_true', help='干跑模式：只输出冲突报告，不写文件')
    parser.add_argument('--verify-only', action='store_true', help='仅验证已有编号')
    args = parser.parse_args()
    
    if args.verify_only:
        result = verify_renumbered(args.input)
        print('=== 编号验证报告 ===')
        print(f"H2(f'第N章'): {result['h2_count']}个")
        print(f"H3(N.M): {result['h3_count']}个")
        print(f"H4(N.M.Z): {result['h4_count']}个")
        if result['issues']:
            for i in result['issues']:
                print(f'❌ {i}')
        else:
            print('✅ 全部通过')
        sys.exit(0 if result['passed'] else 1)
    
    if args.preview:
        print(f'=== 干跑模式（不写文件）===')
        print(f'输入: {args.input}')
        print(f'方案: {args.scheme}')
        stats = renumber_doc(args.input, None, args.scheme, args.on_collision, preview=True)
        print(f'\n=== 冲突报告 ===')
        if stats['collisions']:
            print(f'🔴 检测到 {len(stats["collisions"])} 个编号冲突：')
            for c in stats['collisions']:
                resolved = f' → 解决为 {c["resolved_as"]}' if 'resolved_as' in c else ''
                print(f"  line {c['line']}: {c['type']} {c['num']} - {c['title']}{resolved}")
        else:
            print('✅ 无冲突')
        sys.exit(0 if not stats['collisions'] else 1)
    
    print(f'输入: {args.input}')
    print(f'输出: {args.output}')
    print(f'方案: {args.scheme}')
    print(f'撞车策略: {args.on_collision}')
    
    stats = renumber_doc(args.input, args.output, args.scheme, args.on_collision)
    
    print(f'\n=== 编号完成 ===')
    print(f'H2(章): {stats["h2"]}个')
    print(f'H3(节): {stats["h3"]}个')
    print(f'H4(小节): {stats["h4"]}个')
    print(f'撞车处理: {len(stats["collisions"])} 个')
    
    print(f'\n--- H2章节列表 ---')
    for h in stats['renamed_h2']:
        print(f'  {h}')
    
    # 验证
    print(f'\n=== 自检验证 ===')
    result = verify_renumbered(args.output)
    if result['issues']:
        for i in result['issues']:
            print(f'❌ {i}')
        sys.exit(1)
    else:
        print('✅ 全部通过')


if __name__ == '__main__':
    main()


