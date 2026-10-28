#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

"""
.doc/.docx → Markdown 转换脚本
读取 Word 文档，提取文本、段落结构、表格，输出为 Markdown

用法：
  python3 doc_to_md.py input.docx [output.md]

功能：
  1. 读取 .docx（python-docx）或 .doc（需 textract/antiword）
  2. 保留段落结构（标题样式 → # 层级）
  3. 表格转为 Markdown 表格格式
  4. 图片标注为 [图片]
  5. 加粗/斜体转为 Markdown **/** 
  6. 列表转为 Markdown - / 1. 格式

前置依赖：
  pip install python-docx
"""

import sys
import os
import re

try:
    from docx import Document
    from docx.enum.style import WD_STYLE_TYPE
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False


# Word 内置标题样式 → Markdown 标题层级映射
HEADING_MAP = {
    'Title': '#',
    'Heading 1': '##',
    'Heading 2': '###',
    'Heading 3': '####',
    'Heading 4': '#####',
}


def is_code_block(text):
    """判断文本是否为代码块"""
    return bool(re.match(r'^```', text.strip()))


def extract_paragraph_text(para):
    """提取段落文本，保留加粗/斜体标记"""
    result = []
    for run in para.runs:
        text = run.text
        if not text:
            continue
        if run.bold and run.italic:
            text = f"***{text}***"
        elif run.bold:
            text = f"**{text}**"
        elif run.italic:
            text = f"*{text}*"
        result.append(text)
    return ''.join(result)


def table_to_markdown(table):
    """将 Word 表格转为 Markdown 表格"""
    rows = []
    for row in table.rows:
        cells = [cell.text.strip().replace('\n', ' ') for cell in row.cells]
        rows.append(cells)
    
    if not rows:
        return ''
    
    # 计算列宽
    col_count = max(len(r) for r in rows)
    for i, r in enumerate(rows):
        while len(r) < col_count:
            r.append('')
    
    # 构建 Markdown 表格
    lines = []
    # 表头
    lines.append('| ' + ' | '.join(rows[0]) + ' |')
    # 分隔线
    lines.append('| ' + ' | '.join(['---'] * col_count) + ' |')
    # 数据行
    for row in rows[1:]:
        lines.append('| ' + ' | '.join(row) + ' |')
    
    return '\n'.join(lines)


def extract_images(para):
    """提取段落中的图片引用"""
    images = []
    for run in para.runs:
        if run._element.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing'):
            images.append('[图片]')
        elif run._element.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pict'):
            images.append('[图片]')
    return images


def docx_to_md(docx_path, output_path=None):
    """
    将 .docx 文件转换为 Markdown
    
    Args:
        docx_path: .docx 文件路径
        output_path: 输出 .md 文件路径（可选）
    
    Returns:
        str: Markdown 内容
    """
    if not HAS_DOCX:
        raise ImportError("请先安装 python-docx: pip install python-docx")
    
    doc = Document(docx_path)
    md_lines = []
    code_block_open = False
    
    for para in doc.paragraphs:
        text = extract_paragraph_text(para).strip()
        
        # 检查图片
        images = extract_images(para)
        for img in images:
            md_lines.append(f'\n{img}\n')
        
        if not text:
            md_lines.append('')
            continue
        
        # 代码块
        if is_code_block(text):
            code_block_open = not code_block_open
            md_lines.append(text)
            continue
        if code_block_open:
            md_lines.append(text)
            continue
        
        # 标题处理
        style_name = para.style.name if para.style else ''
        if style_name in HEADING_MAP:
            prefix = HEADING_MAP[style_name]
            md_lines.append(f'{prefix} {text}')
        else:
            # 正文
            md_lines.append(text)
    
    # 处理表格
    for table in doc.tables:
        md_lines.append('')
        md_lines.append(table_to_markdown(table))
        md_lines.append('')
    
    markdown = '\n\n'.join(md_lines)
    # 清理多余空行
    markdown = re.sub(r'\n{3,}', '\n\n', markdown)
    
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown)
    
    return markdown


def doc_to_md_legacy(doc_path, output_path=None):
    """
    .doc（老格式）转 Markdown（需要 antiword 命令行工具）
    
    macOS 安装: brew install antiword
    """
    import subprocess
    import tempfile
    
    result = subprocess.run(
        ['antiword', '-m', 'UTF-8.txt', doc_path],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace"
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"antiword 转换失败: {result.stderr}\n请安装 antiword: brew install antiword")
    
    text = result.stdout
    # 基本处理：每段一行
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    markdown = '\n\n'.join(lines)
    
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown)
    
    return markdown


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法:")
        print("  .docx: python3 doc_to_md.py input.docx [output.md]")
        print("  .doc:  python3 doc_to_md.py input.doc [output.md]")
        print("  示例:  python3 doc_to_md.py 课程讲义.docx 讲义_raw.md")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not output_path:
        base = os.path.splitext(os.path.basename(input_path))[0]
        output_path = f"{base}_raw.md"
    
    ext = os.path.splitext(input_path)[1].lower()
    
    try:
        if ext == '.docx':
            md = docx_to_md(input_path, output_path)
        elif ext == '.doc':
            md = doc_to_md_legacy(input_path, output_path)
        else:
            print(f"❌ 不支持的文件格式: {ext}，仅支持 .doc 和 .docx", file=sys.stderr)
            sys.exit(1)
        
        print(f"✅ 转换完成: {output_path}")
        print(f"   字符数: {len(md)}")
        print(f"   行数: {len(md.splitlines())}")
    except Exception as e:
        print(f"❌ 转换失败: {e}", file=sys.stderr)
        sys.exit(1)

