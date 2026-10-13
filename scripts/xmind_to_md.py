#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

"""
XMind 思维导图 → Markdown 大纲解析器
支持 XMind Zen 格式（ZIP 包内含 content.json）

用法：
  python3 xmind_to_md.py input.xmind [output.md]

功能：
  1. 解压 .xmind 为 ZIP，读取 content.json
  2. 递归提取节点结构，生成 Markdown 层级大纲
  3. 导图根节点 → H1，一级子节点 → H2，二级子节点 → H3 ...
  4. 输出 Markdown 格式标题骨架
"""

import json
import sys
import os
import zipfile
import tempfile


def extract_nodes(node, depth=0):
    """
    递归提取 XMind 节点结构
    
    Args:
        node: content.json 中的节点对象
        depth: 当前深度（0=根节点）
    
    Returns:
        list[str]: Markdown 标题行列表
    """
    title = node.get('title', '无标题').strip()
    if not title:
        title = '无标题'
    
    level = min(depth + 1, 4)  # 最多到 H4
    indent = '  ' * depth
    result = [f"{indent}{'#' * level} {title}"]
    
    children = node.get('children', {})
    for child in children.get('attached', []):
        result.extend(extract_nodes(child, depth + 1))
    
    return result


def xmind_to_md(xmind_path, output_path=None):
    """
    将 XMind 文件转换为 Markdown 大纲
    
    Args:
        xmind_path: .xmind 文件路径
        output_path: 输出 .md 文件路径（可选，默认同目录同名）
    
    Returns:
        str: Markdown 内容
    """
    if not os.path.exists(xmind_path):
        raise FileNotFoundError(f"文件不存在: {xmind_path}")
    
    with zipfile.ZipFile(xmind_path, 'r') as zf:
        # 查找 content.json
        content_files = [f for f in zf.namelist() if f.endswith('content.json')]
        if not content_files:
            raise ValueError("XMind 文件中未找到 content.json")
        
        content_json = zf.read(content_files[0]).decode('utf-8')
    
    data = json.loads(content_json)
    
    # 定位根节点（支持多种 XMind 版本格式）
    if isinstance(data, list):
        root = data[0].get('rootTopic', data[0])
    elif isinstance(data, dict):
        root = data.get('rootTopic', data)
    else:
        raise ValueError(f"无法解析 content.json 结构，类型: {type(data)}")
    
    structure = extract_nodes(root)
    markdown = '\n'.join(structure)
    
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown)
    
    return markdown


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 xmind_to_md.py input.xmind [output.md]")
        print("示例: python3 xmind_to_md.py 课程大纲.xmind 大纲.md")
        sys.exit(1)
    
    xmind_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not output_path:
        base = os.path.splitext(os.path.basename(xmind_path))[0]
        output_path = f"{base}_outline.md"
    
    try:
        md = xmind_to_md(xmind_path, output_path)
        print(f"✅ 导出完成: {output_path}")
        print(f"   结构行数: {len(md.splitlines())}")
        print(f"\n--- 预览（前10行）---")
        for line in md.splitlines()[:10]:
            print(line)
    except Exception as e:
        print(f"❌ 导出失败: {e}", file=sys.stderr)
        sys.exit(1)

