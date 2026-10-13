#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown转Word脚本 v2.7

关键修正（v2.7）：
- 🔴 新增代码块（fenced code block）识别：```内的#注释不再被误解析为标题
- 代码块使用等宽字体（Courier New）+ 浅灰背景渲染

关键修正（v2.6）：
- lvlOverride+startOverride强制重启编号（替代nsid方案，兼容性更好）
- 不再创建新abstractNum，不修改已有abstractNum，避免干扰ListBullet

关键修正（v2.5）：
- 有序列表独立编号：每个独立列表从1开始

关键修正（v2.4）：
1. 标题中的#、##、###必须去除，只保留纯文本
2. **加粗**必须转为Word加粗Run，不是纯文本
3. 文档标题使用Title样式（22pt，居中）
4. H1使用Heading 1样式（18pt，居中）

关键修正（v2.3）：
5. MD表格必须转为Word表格
6. MD无序列表使用Word内置List Bullet样式
7. MD有序列表使用Word内置List Number样式
8. 每个独立有序列表从1开始编号（分配不同numId）

关键修正（v2.4）：
9. 添加页脚页码：「第 X 页 / Y 页」格式，居中对齐
10. 修复表格解析逻辑，支持有空行的表格
"""
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# v3.8 修复: 早校验 lxml 依赖
try:
    from lxml import etree
except ImportError:
    print('❌ 缺少依赖: lxml')
    print('   请运行: pip install lxml')
    print('   （markdown_to_docx.py 的有序列表编号修复和 verify_v6.py 都依赖 lxml）')
    sys.exit(2)

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import re

# ==================== 样式常量 ====================
FONT_NAME = '微软雅黑'
CODE_FONT = 'Courier New'
CODE_BG = 'F0F0F0'
DEEP_BLUE = RGBColor(0, 48, 112)
BLACK = RGBColor(0, 0, 0)

# ==================== 工具函数 ====================
def set_run_font(run, size, bold=False, color=BLACK):
    """设置run的字体（包含东亚字体）"""
    run.font.name = FONT_NAME
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    # 设置东亚字体
    r = run._element
    rPr = r.get_or_add_rPr()
    for child in list(rPr):
        if child.tag.endswith('}rFonts'):
            rPr.remove(child)
    rFonts = OxmlElement('w:rFonts')
    rFonts.set(qn('w:eastAsia'), FONT_NAME)
    rFonts.set(qn('w:ascii'), FONT_NAME)
    rFonts.set(qn('w:hAnsi'), FONT_NAME)
    rPr.insert(0, rFonts)

def set_para_alignment(para, align):
    """设置段落对齐"""
    pPr = para._element.get_or_add_pPr()
    if pPr is None:
        pPr = OxmlElement('w:pPr')
        para._element.insert(0, pPr)
    for child in list(pPr):
        if child.tag.endswith('}jc'):
            pPr.remove(child)
    jc = OxmlElement('w:jc')
    if align == WD_ALIGN_PARAGRAPH.CENTER:
        jc.set(qn('w:val'), 'center')
    elif align == WD_ALIGN_PARAGRAPH.LEFT:
        jc.set(qn('w:val'), 'left')
    pPr.insert(0, jc)

def set_para_spacing(para, before=None, after=None):
    """设置段落间距"""
    pPr = para._element.get_or_add_pPr()
    if pPr is None:
        pPr = OxmlElement('w:pPr')
        para._element.insert(0, pPr)
    for child in list(pPr):
        if child.tag.endswith('}spacing'):
            pPr.remove(child)
    spacing = OxmlElement('w:spacing')
    if before is not None:
        spacing.set(qn('w:before'), str(int(before * 20)))
    if after is not None:
        spacing.set(qn('w:after'), str(int(after * 20)))
    pPr.insert(0, spacing)

def set_para_line_spacing(para, line_spacing_pt):
    """设置行距为固定值"""
    pPr = para._element.get_or_add_pPr()
    if pPr is None:
        pPr = OxmlElement('w:pPr')
        para._element.insert(0, pPr)
    for child in list(pPr):
        if child.tag.endswith('}spacing'):
            pPr.remove(child)
    spacing = OxmlElement('w:spacing')
    spacing.set(qn('w:line'), str(int(line_spacing_pt * 20)))
    spacing.set(qn('w:lineRule'), 'exact')
    pPr.insert(0, spacing)

def add_paragraph_with_style(doc, text, style_name, font_size, bold, color, align=None, space_before=None, space_after=None, line_spacing=None):
    """添加带完整样式的段落"""
    p = doc.add_paragraph()
    p.style = style_name
    
    # 处理**加粗**格式
    parts = re.split(r'(\*\*.+?\*\*)', text)
    for part in parts:
        if part.startswith('**') and part.endswith('**'):
            # 加粗文本
            run_text = part[2:-2]
            run = p.add_run(run_text)
            set_run_font(run, font_size, True, color)
        elif part:
            # 普通文本
            run = p.add_run(part)
            set_run_font(run, font_size, bold, color)
    
    if align is not None:
        set_para_alignment(p, align)
    if space_before is not None or space_after is not None:
        set_para_spacing(p, space_before, space_after)
    if line_spacing is not None:
        set_para_line_spacing(p, line_spacing)
    
    return p

def set_page_setup(doc):
    """设置页面为A4，边距1.5/1.4/1.5/1.5cm，并添加页脚页码"""
    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(1.4)
    section.bottom_margin = Cm(1.5)
    section.left_margin = Cm(1.5)
    section.right_margin = Cm(1.5)


def apply_global_styles(doc):
    """覆盖 Word 默认标题样式（v3.8 修复）

    python-docx 默认 Heading 1/2/3 颜色是 #4F81BD（蓝色），与本技能要求的 #003070（深蓝）不一致。
    直接修改 styles.xml 中 Title/Heading 1-4 的 rPr，让所有未显式指定颜色的标题自动用深蓝。
    同时设置 docDefaults 字体为微软雅黑，Normal 字体为宋体（v2.7 规范 + 段总 13 项 #9）。
    """
    try:
        styles_part = doc.styles.element
        from lxml import etree
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        # 1) 设置 Heading 1/2/3/4/Title 颜色为 #003070
        target_color = '003070'
        for style_id in ['Title', 'Heading1', 'Heading2', 'Heading3', 'Heading4', 'Heading5']:
            style = None
            for s in styles_part.findall(f'{{{ns["w"]}}}style'):
                if s.get(f'{{{ns["w"]}}}styleId') == style_id:
                    style = s
                    break
            if style is None:
                continue
            rPr = style.find(f'{{{ns["w"]}}}rPr')
            if rPr is None:
                rPr = etree.SubElement(style, f'{{{ns["w"]}}}rPr')
            # 移除旧 color
            for color in rPr.findall(f'{{{ns["w"]}}}color'):
                rPr.remove(color)
            color = etree.SubElement(rPr, f'{{{ns["w"]}}}color')
            color.set(f'{{{ns["w"]}}}val', target_color)
            # 移除旧 sz
            for sz in rPr.findall(f'{{{ns["w"]}}}sz'):
                rPr.remove(sz)
            for szCs in rPr.findall(f'{{{ns["w"]}}}szCs'):
                rPr.remove(szCs)
            # 标题字号（半磅）
            size_map = {'Title': 44, 'Heading1': 36, 'Heading2': 32, 'Heading3': 30, 'Heading4': 28, 'Heading5': 26}
            sz = etree.SubElement(rPr, f'{{{ns["w"]}}}sz')
            sz.set(f'{{{ns["w"]}}}val', str(size_map[style_id]))
            szCs = etree.SubElement(rPr, f'{{{ns["w"]}}}szCs')
            szCs.set(f'{{{ns["w"]}}}val', str(size_map[style_id]))
            # 字体（东亚 = ascii = hAnsi = 微软雅黑）
            for rFonts in rPr.findall(f'{{{ns["w"]}}}rFonts'):
                rPr.remove(rFonts)
            rFonts = etree.SubElement(rPr, f'{{{ns["w"]}}}rFonts')
            rFonts.set(f'{{{ns["w"]}}}ascii', FONT_NAME)
            rFonts.set(f'{{{ns["w"]}}}hAnsi', FONT_NAME)
            rFonts.set(f'{{{ns["w"]}}}eastAsia', FONT_NAME)
            rFonts.set(f'{{{ns["w"]}}}cs', FONT_NAME)
        # 2) Normal 样式 = 宋体 12pt 黑色（v2.7 规范）
        for s in styles_part.findall(f'{{{ns["w"]}}}style'):
            if s.get(f'{{{ns["w"]}}}styleId') == 'Normal':
                rPr = s.find(f'{{{ns["w"]}}}rPr')
                if rPr is None:
                    rPr = etree.SubElement(s, f'{{{ns["w"]}}}rPr')
                # 字体
                for rFonts in rPr.findall(f'{{{ns["w"]}}}rFonts'):
                    rPr.remove(rFonts)
                rFonts = etree.SubElement(rPr, f'{{{ns["w"]}}}rFonts')
                rFonts.set(f'{{{ns["w"]}}}ascii', '宋体')
                rFonts.set(f'{{{ns["w"]}}}hAnsi', '宋体')
                rFonts.set(f'{{{ns["w"]}}}eastAsia', '宋体')
                rFonts.set(f'{{{ns["w"]}}}cs', '宋体')
                # 字号 12pt = 24 半磅
                for sz in rPr.findall(f'{{{ns["w"]}}}sz'):
                    rPr.remove(sz)
                for szCs in rPr.findall(f'{{{ns["w"]}}}szCs'):
                    rPr.remove(szCs)
                sz = etree.SubElement(rPr, f'{{{ns["w"]}}}sz')
                sz.set(f'{{{ns["w"]}}}val', '24')
                szCs = etree.SubElement(rPr, f'{{{ns["w"]}}}szCs')
                szCs.set(f'{{{ns["w"]}}}val', '24')
                # 颜色
                for color in rPr.findall(f'{{{ns["w"]}}}color'):
                    rPr.remove(color)
                color = etree.SubElement(rPr, f'{{{ns["w"]}}}color')
                color.set(f'{{{ns["w"]}}}val', '000000')
                break
        # 3) docDefaults 兜底字体 = 微软雅黑
        docDefaults = styles_part.find(f'{{{ns["w"]}}}docDefaults')
        if docDefaults is None:
            docDefaults = etree.Element(f'{{{ns["w"]}}}docDefaults')
            styles_part.insert(0, docDefaults)
        rPrDefault = docDefaults.find(f'{{{ns["w"]}}}rPrDefault')
        if rPrDefault is None:
            rPrDefault = etree.SubElement(docDefaults, f'{{{ns["w"]}}}rPrDefault')
        rPr = rPrDefault.find(f'{{{ns["w"]}}}rPr')
        if rPr is None:
            rPr = etree.SubElement(rPrDefault, f'{{{ns["w"]}}}rPr')
        for rFonts in rPr.findall(f'{{{ns["w"]}}}rFonts'):
            rPr.remove(rFonts)
        rFonts = etree.SubElement(rPr, f'{{{ns["w"]}}}rFonts')
        rFonts.set(f'{{{ns["w"]}}}ascii', FONT_NAME)
        rFonts.set(f'{{{ns["w"]}}}hAnsi', FONT_NAME)
        rFonts.set(f'{{{ns["w"]}}}eastAsia', FONT_NAME)
        rFonts.set(f'{{{ns["w"]}}}cs', FONT_NAME)
    except Exception as e:
        print(f'  ⚠️ 全局样式应用失败: {e}')
    
    # 添加页脚：当前页/总页数 格式（如 1/20），居中对齐
    # v3.8 修复: 直接通过 doc 取 section, 不依赖 set_page_setup 的局部变量
    section = doc.sections[0]
    footer = section.footer
    footer.is_linked_to_previous = False
    
    # 清除现有段落
    for para in footer.paragraphs:
        p = para._element
        p.getparent().remove(p)
    
    # 创建页脚段落
    footer_para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # 添加 "第 X 页 / Y 页" 格式
    # 第一部分："第 " + PAGE域
    r1 = footer_para.add_run('第 ')
    rPr1 = r1._r.get_or_add_rPr()
    rFonts1 = OxmlElement('w:rFonts')
    rFonts1.set(qn('w:eastAsia'), FONT_NAME)
    rFonts1.set(qn('w:ascii'), FONT_NAME)
    rFonts1.set(qn('w:hAnsi'), FONT_NAME)
    rPr1.insert(0, rFonts1)
    sz1 = OxmlElement('w:sz')
    sz1.set(qn('w:val'), '20')
    rPr1.append(sz1)
    
    # PAGE 域
    run_page = footer_para.add_run()
    run_page.font.size = Pt(10)
    rPr_page = run_page._r.get_or_add_rPr()
    # begin
    fldChar_begin = OxmlElement('w:fldChar')
    fldChar_begin.set(qn('w:fldCharType'), 'begin')
    rPr_page.append(fldChar_begin)
    # instrText
    instrText = OxmlElement('w:instrText')
    instrText.set(qn('xml:space'), 'preserve')
    instrText.text = ' PAGE '
    rPr_page.append(instrText)
    # separate
    fldChar_sep = OxmlElement('w:fldChar')
    fldChar_sep.set(qn('w:fldCharType'), 'separate')
    rPr_page.append(fldChar_sep)
    # placeholder text
    run_page2 = footer_para.add_run('1')
    run_page2.font.size = Pt(10)
    # end
    run_page3 = footer_para.add_run()
    rPr_page3 = run_page3._r.get_or_add_rPr()
    fldChar_end = OxmlElement('w:fldChar')
    fldChar_end.set(qn('w:fldCharType'), 'end')
    rPr_page3.append(fldChar_end)
    
    # 第二部分：" 页 / " + NUMPAGES域 + " 页"
    r2 = footer_para.add_run(' 页 / ')
    rPr2 = r2._r.get_or_add_rPr()
    rFonts2 = OxmlElement('w:rFonts')
    rFonts2.set(qn('w:eastAsia'), FONT_NAME)
    rFonts2.set(qn('w:ascii'), FONT_NAME)
    rFonts2.set(qn('w:hAnsi'), FONT_NAME)
    rPr2.insert(0, rFonts2)
    sz2 = OxmlElement('w:sz')
    sz2.set(qn('w:val'), '20')
    rPr2.append(sz2)
    
    # NUMPAGES 域
    run_np = footer_para.add_run()
    run_np.font.size = Pt(10)
    rPr_np = run_np._r.get_or_add_rPr()
    fldChar_begin2 = OxmlElement('w:fldChar')
    fldChar_begin2.set(qn('w:fldCharType'), 'begin')
    rPr_np.append(fldChar_begin2)
    instrText2 = OxmlElement('w:instrText')
    instrText2.set(qn('xml:space'), 'preserve')
    instrText2.text = ' NUMPAGES '
    rPr_np.append(instrText2)
    fldChar_sep2 = OxmlElement('w:fldChar')
    fldChar_sep2.set(qn('w:fldCharType'), 'separate')
    rPr_np.append(fldChar_sep2)
    run_np2 = footer_para.add_run('20')
    run_np2.font.size = Pt(10)
    run_np3 = footer_para.add_run()
    rPr_np3 = run_np3._r.get_or_add_rPr()
    fldChar_end2 = OxmlElement('w:fldChar')
    fldChar_end2.set(qn('w:fldCharType'), 'end')
    rPr_np3.append(fldChar_end2)
    
    # 第三部分：" 页"
    r3 = footer_para.add_run(' 页')
    rPr3 = r3._r.get_or_add_rPr()
    rFonts3 = OxmlElement('w:rFonts')
    rFonts3.set(qn('w:eastAsia'), FONT_NAME)
    rFonts3.set(qn('w:ascii'), FONT_NAME)
    rFonts3.set(qn('w:hAnsi'), FONT_NAME)
    rPr3.insert(0, rFonts3)
    sz3 = OxmlElement('w:sz')
    sz3.set(qn('w:val'), '20')
    rPr3.append(sz3)

# ==================== v2.3新增：表格处理 ====================
def is_markdown_table(line):
    """判断是否为Markdown表格行"""
    ls = line.strip()
    if not ls.startswith('|') or not ls.endswith('|'):
        return False
    # 跳过分隔行 |---|---|
    if re.match(r'^\|[\s\-:]+\|[\s\-:]+\|', ls):
        return False
    return True

def is_table_separator(line):
    """判断是否为表格分隔行"""
    ls = line.strip()
    return bool(re.match(r'^\|[\s\-:]+\|[\s\-:]+\|', ls))

def parse_markdown_table_row(line):
    """解析Markdown表格行，返回单元格列表"""
    ls = line.strip()
    # 去除首尾的|
    ls = ls.strip('|')
    # 按|分割
    cells = [cell.strip() for cell in ls.split('|')]
    return cells

def add_word_table(doc, rows_data):
    """将解析好的表格数据转为Word表格
    
    rows_data: [[cell1, cell2, ...], [cell1, cell2, ...], ...]
    """
    if not rows_data:
        return
    
    num_rows = len(rows_data)
    num_cols = len(rows_data[0]) if rows_data else 0
    
    if num_cols == 0:
        return
    
    # 创建表格
    table = doc.add_table(rows=num_rows, cols=num_cols)
    table.style = 'Table Grid'
    
    # 填充数据
    for row_idx, row_data in enumerate(rows_data):
        for col_idx, cell_text in enumerate(row_data):
            cell = table.cell(row_idx, col_idx)
            cell.text = ''
            
            # 添加单元格文本（处理**加粗**格式）
            p = cell.paragraphs[0]
            parts = re.split(r'(\*\*.+?\*\*)', cell_text)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    run_text = part[2:-2]
                    run = p.add_run(run_text)
                    set_run_font(run, 10, True, BLACK)  # 加粗
                elif part:
                    run = p.add_run(part)
                    set_run_font(run, 10, False, BLACK)  # 普通文本
            
            # 设置单元格内边距
            tc = cell._tc
            tcPr = tc.get_or_add_tcPr()
            # 使用tcMar元素设置单元格边距
            tcMar = OxmlElement('w:tcMar')
            for side in ['top', 'bottom', 'left', 'right']:
                ind = OxmlElement(f'w:{side}')
                ind.set(qn('w:val'), '60')
                ind.set(qn('w:type'), 'dxa')
                tcMar.append(ind)
            tcPr.append(tcMar)
    
    # 添加空行分隔
    doc.add_paragraph()

def add_code_block(doc, code_lines):
    """将代码块渲染为等宽字体段落（v2.7新增）"""
    for line in code_lines:
        p = doc.add_paragraph()
        p.style = 'Normal'
        # 浅灰背景
        pPr = p._element.get_or_add_pPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:fill'), CODE_BG)
        shd.set(qn('w:val'), 'clear')
        pPr.append(shd)
        # 等宽字体
        run = p.add_run(line)
        run.font.name = CODE_FONT
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(51, 51, 51)
        rPr = run._element.get_or_add_rPr()
        rFonts = OxmlElement('w:rFonts')
        rFonts.set(qn('w:ascii'), CODE_FONT)
        rFonts.set(qn('w:hAnsi'), CODE_FONT)
        rFonts.set(qn('w:eastAsia'), FONT_NAME)
        rPr.insert(0, rFonts)
        set_para_line_spacing(p, 16)
    # 代码块后加空行
    doc.add_paragraph()

def process_markdown_content(content, doc, state=None):
    """处理Markdown内容，识别代码块、表格，其余按行处理（v2.7新增代码块支持）"""
    if state is None:
        state = {'last_was_list_number': False, 'current_list_num_id': 1, 'max_num_id': 9}
    lines = content.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i]
        ls = line.strip()
        
        # 跳过空行
        if not ls:
            i += 1
            continue
        
        # ========== v2.7新增：识别代码块（fenced code block） ==========
        if ls.startswith('```'):
            code_lines = []
            i += 1
            while i < len(lines):
                if lines[i].strip().startswith('```'):
                    i += 1  # 跳过结束 ```
                    break
                code_lines.append(lines[i])
                i += 1
            if code_lines:
                add_code_block(doc, code_lines)
            continue
        
        # ========== 检查是否是表格 ==========
        if is_markdown_table(line) and not is_table_separator(line):
            # 收集表格所有行
            table_rows = []
            
            # 收集所有连续的表格行（跳过空行和分隔行）
            while i < len(lines):
                current_line = lines[i]
                current_ls = current_line.strip()
                
                # 如果是空行，跳过但继续收集
                if not current_ls:
                    i += 1
                    continue
                
                # 如果是分隔行，跳过但继续收集
                if is_table_separator(current_line):
                    i += 1
                    continue
                
                # 如果是表格行，收集
                if is_markdown_table(current_line):
                    table_rows.append(parse_markdown_table_row(current_line))
                    i += 1
                    continue
                
                # 如果是其他内容，结束表格收集
                break
            
            # 添加Word表格
            if table_rows:
                add_word_table(doc, table_rows)
            continue
        
        # ========== 非表格行，按原有逻辑处理 ==========
        process_single_line(ls, doc, state)
        i += 1

def process_single_line(ls, doc, state=None):
    """处理单行Markdown内容（不包括表格）"""
    if state is None:
        state = {'last_was_list_number': False, 'current_list_num_id': 1, 'max_num_id': 9}
    # 非有序列表时重置状态（确保下一个独立列表从1开始）
    if not re.match(r'^\d+\.\s', ls):
        state['last_was_list_number'] = False
    # ========== 文档标题：# 标题 -> Title样式（22pt，居中） ==========
    # 处理以#开头且不是"第X章"格式的单独标题
    if (ls.startswith('# ') or ls.startswith('#	')) and not ls.startswith('# 第'):
        title_text = ls.lstrip('#').strip()
        add_paragraph_with_style(
            doc, title_text, 'Title',
            font_size=22, bold=True, color=DEEP_BLUE,
            align=WD_ALIGN_PARAGRAPH.CENTER
        )
        return
    
    # ========== H1: 接受 # 第N章 x / # 总标题 ==========
    # v3.8 修复：原正则只匹配"# 第N章"，纯"# 总标题"走 Title 分支不一定是用户意图
    m = re.match(r'^# 第(\d+)章 (.+)', ls)
    if m:
        h1_text = f"第{m.group(1)}章 {m.group(2)}"
        add_paragraph_with_style(
            doc, h1_text, 'Heading 1',
            font_size=18, bold=True, color=DEEP_BLUE,
            align=WD_ALIGN_PARAGRAPH.CENTER,
            space_before=10, space_after=6
        )
        return
    
    # ========== H2: ## X.Y 标题 / ## N 标题 / ## 第N章 标题 -> Heading 2（16pt） ==========
    # v3.8 修复：兼容 renumber_headings.py 的 chinese 方案(## 第一章 xxx)与 dotted 方案(## 1 xxx)
    m = re.match(r'^## (\d+\.\d+) (.+)', ls)
    if m:
        h2_text = f"{m.group(1)} {m.group(2)}"
        add_paragraph_with_style(
            doc, h2_text, 'Heading 2',
            font_size=16, bold=True, color=DEEP_BLUE,
            align=WD_ALIGN_PARAGRAPH.LEFT,
            space_before=12, space_after=6
        )
        return
    m = re.match(r'^## (第[一二三四五六七八九十百千\d]+章)\s+(.+)', ls)
    if m:
        h2_text = f"{m.group(1)} {m.group(2)}"
        add_paragraph_with_style(
            doc, h2_text, 'Heading 2',
            font_size=16, bold=True, color=DEEP_BLUE,
            align=WD_ALIGN_PARAGRAPH.LEFT,
            space_before=12, space_after=6
        )
        return
    m = re.match(r'^## (\d+)\s+(.+)', ls)
    if m:
        h2_text = f"{m.group(1)} {m.group(2)}"
        add_paragraph_with_style(
            doc, h2_text, 'Heading 2',
            font_size=16, bold=True, color=DEEP_BLUE,
            align=WD_ALIGN_PARAGRAPH.LEFT,
            space_before=12, space_after=6
        )
        return
    
    # ========== H2 fallback: ## 纯文本标题（无编号） -> Heading 2 ==========
    m = re.match(r'^##\s+(.+)', ls)
    if m:
        h2_text = m.group(1).strip()
        add_paragraph_with_style(
            doc, h2_text, 'Heading 2',
            font_size=16, bold=True, color=DEEP_BLUE,
            align=WD_ALIGN_PARAGRAPH.LEFT,
            space_before=12, space_after=6
        )
        return
    
    # ========== H3: ### X.Y.Z 标题 / ### N.M 标题 -> Heading 3（15pt） ==========
    # v3.8 修复：renumber_headings.py 实际输出 ### N.M（两级），原正则要求 X.Y.Z（三级）
    m = re.match(r'^### (\d+\.\d+\.\d+) (.+)', ls)
    if m:
        h3_text = f"{m.group(1)} {m.group(2)}"
        add_paragraph_with_style(
            doc, h3_text, 'Heading 3',
            font_size=15, bold=True, color=DEEP_BLUE,
            align=WD_ALIGN_PARAGRAPH.LEFT,
            space_before=12, space_after=6,
            line_spacing=26
        )
        return
    m = re.match(r'^### (\d+\.\d+) (.+)', ls)
    if m:
        h3_text = f"{m.group(1)} {m.group(2)}"
        add_paragraph_with_style(
            doc, h3_text, 'Heading 3',
            font_size=15, bold=True, color=DEEP_BLUE,
            align=WD_ALIGN_PARAGRAPH.LEFT,
            space_before=12, space_after=6,
            line_spacing=26
        )
        return
    
    # ========== H3 fallback: ### 纯文本标题（无编号） -> Heading 3 ==========
    m = re.match(r'^###\s+(.+)', ls)
    if m:
        h3_text = m.group(1).strip()
        add_paragraph_with_style(
            doc, h3_text, 'Heading 3',
            font_size=15, bold=True, color=DEEP_BLUE,
            align=WD_ALIGN_PARAGRAPH.LEFT,
            space_before=12, space_after=6,
            line_spacing=26
        )
        return
    
    # ========== H4: #### X.Y.Z.W 标题 / #### N.M.Z 标题 -> Heading 4（14pt） ==========
    # v3.8 修复：renumber 输出 #### N.M.Z（三级）
    m = re.match(r'^#### (\d+\.\d+\.\d+\.\d+) (.+)', ls)
    if m:
        h4_text = f"{m.group(1)} {m.group(2)}"
        add_paragraph_with_style(
            doc, h4_text, 'Heading 4',
            font_size=14, bold=True, color=DEEP_BLUE,
            align=WD_ALIGN_PARAGRAPH.LEFT,
            space_before=6, space_after=3,
            line_spacing=26
        )
        return
    m = re.match(r'^#### (\d+\.\d+\.\d+) (.+)', ls)
    if m:
        h4_text = f"{m.group(1)} {m.group(2)}"
        add_paragraph_with_style(
            doc, h4_text, 'Heading 4',
            font_size=14, bold=True, color=DEEP_BLUE,
            align=WD_ALIGN_PARAGRAPH.LEFT,
            space_before=6, space_after=3,
            line_spacing=26
        )
        return
    
    # ========== H5: ##### 纯文本标题（无编号） -> Heading 5（13pt） ==========
    # v3.9 新增：支持 H5 标题（merge 阶段 H2-H4 降级 +1 后产生的 H5）
    m = re.match(r'^#####\s+(.+)', ls)
    if m:
        h5_text = m.group(1).strip()
        add_paragraph_with_style(
            doc, h5_text, 'Heading 5',
            font_size=13, bold=True, color=DEEP_BLUE,
            align=WD_ALIGN_PARAGRAPH.LEFT,
            space_before=4, space_after=2,
            line_spacing=26
        )
        return
    
    # ========== H4 fallback: #### 纯文本标题（无编号） -> Heading 4 ==========
    m = re.match(r'^####\s+(.+)', ls)
    if m:
        h4_text = m.group(1).strip()
        add_paragraph_with_style(
            doc, h4_text, 'Heading 4',
            font_size=14, bold=True, color=DEEP_BLUE,
            align=WD_ALIGN_PARAGRAPH.LEFT,
            space_before=6, space_after=3,
            line_spacing=26
        )
        return
    
    # ========== 无序列表：- item 或 * item ==========
    if ls.startswith('- ') or ls.startswith('* '):
        p = doc.add_paragraph(style='List Bullet')
        # 添加紧凑缩进（与有序列表一致）
        pPr = p._element.get_or_add_pPr()
        ind = OxmlElement('w:ind')
        ind.set(qn('w:left'), '360')
        ind.set(qn('w:hanging'), '360')
        pPr.append(ind)
        item_text = ls[2:]
        # 处理**加粗**格式
        parts = re.split(r'(\*\*.+?\*\*)', item_text)
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                run_text = part[2:-2]
                run = p.add_run(run_text)
                set_run_font(run, 12, True, BLACK)  # 加粗
            elif part:
                run = p.add_run(part)
                set_run_font(run, 12, False, BLACK)
        p.paragraph_format.space_after = Pt(3)
        set_para_line_spacing(p, 26)
        return
    
    # ========== 有序列表：1. item ==========
    m = re.match(r'^(\d+)\.\s(.+)', ls)
    if m:
        # 检查是否是新的独立列表（上一个段落不是List Number）
        if not state['last_was_list_number']:
            # 新列表：分配新的numId
            state['max_num_id'] += 1
            state['current_list_num_id'] = state['max_num_id']
        
        p = doc.add_paragraph(style='List Number')
        item_text = m.group(2)
        # 处理**加粗**格式
        parts = re.split(r'(\*\*.+?\*\*)', item_text)
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                run_text = part[2:-2]
                run = p.add_run(run_text)
                set_run_font(run, 12, True, BLACK)  # 加粗
            elif part:
                run = p.add_run(part)
                set_run_font(run, 12, False, BLACK)
        
        # 为段落添加numPr，使每个独立列表重新编号
        # 重要：numPr必须放在pStyle之后，否则样式中的numId会覆盖手动设置
        pPr = p._element.get_or_add_pPr()
        numPr = OxmlElement('w:numPr')
        ilvl = OxmlElement('w:ilvl')
        ilvl.set(qn('w:val'), '0')
        numId_elem = OxmlElement('w:numId')
        numId_elem.set(qn('w:val'), str(state['current_list_num_id']))
        numPr.append(ilvl)
        numPr.append(numId_elem)
        # 找到pStyle，在其后插入numPr（确保numPr优先级高于样式默认值）
        pstyle_elem = pPr.find(qn('w:pStyle'))
        if pstyle_elem is not None:
            idx = list(pPr).index(pstyle_elem)
            pPr.insert(idx + 1, numPr)
        else:
            pPr.insert(0, numPr)
        
        # 添加紧凑缩进（对齐无序列表，避免向右缩进过多）
        ind = OxmlElement('w:ind')
        ind.set(qn('w:left'), '360')
        ind.set(qn('w:hanging'), '360')
        pPr.append(ind)
        
        p.paragraph_format.space_after = Pt(3)
        set_para_line_spacing(p, 26)
        state['last_was_list_number'] = True
        return
    
    # ========== 正文：处理**加粗**格式 ==========
    p = doc.add_paragraph()
    p.style = 'Normal'
    
    parts = re.split(r'(\*\*.+?\*\*)', ls)
    for part in parts:
        if part.startswith('**') and part.endswith('**'):
            run_text = part[2:-2]
            run = p.add_run(run_text)
            set_run_font(run, 12, True, BLACK)  # 加粗
        elif part:
            run = p.add_run(part)
            set_run_font(run, 12, False, BLACK)
    
    set_para_line_spacing(p, 26)

def _fix_list_numbering(docx_path, max_num_id):
    """修复有序列表编号：lvlOverride+startOverride强制从1开始（v2.6）
    
    OOXML标准：每个独立列表不同numId，num中加lvlOverride/startOverride。
    不再创建新abstractNum或填充空的——避免干扰ListBullet等其他样式。
    """
    if max_num_id <= 9:
        return
    try:
        import zipfile, os
        from lxml import etree
        W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        
        with zipfile.ZipFile(docx_path, 'r') as zf:
            numbering_xml = zf.read('word/numbering.xml')
        
        root = etree.fromstring(numbering_xml)
        
        # 找到ListNumber的abstractNumId
        listnumber_abs_id = None
        for an in root.findall('.//w:abstractNum', ns):
            for lvl in an.findall(f'{W}lvl'):
                ps = lvl.find(f'{W}pStyle')
                if ps is not None and ps.get(f'{W}val') == 'ListNumber':
                    listnumber_abs_id = an.get(f'{W}abstractNumId')
                    break
            if listnumber_abs_id:
                break
        
        if listnumber_abs_id is None:
            listnumber_abs_id = '7'
        
        # 为numId 10+创建num定义，引用ListNumber的abstractNum但加lvlOverride重启
        for new_id in range(10, max_num_id + 1):
            num_exists = any(
                num.get(f'{W}numId') == str(new_id)
                for num in root.findall('.//w:num', ns)
            )
            if not num_exists:
                new_num = etree.Element(f'{W}num')
                new_num.set(f'{W}numId', str(new_id))
                
                abstract_ref = etree.SubElement(new_num, f'{W}abstractNumId')
                abstract_ref.set(f'{W}val', listnumber_abs_id)
                
                # lvlOverride + startOverride 强制从1开始
                lvlOverride = etree.SubElement(new_num, f'{W}lvlOverride')
                lvlOverride.set(f'{W}ilvl', '0')
                startOverride = etree.SubElement(lvlOverride, f'{W}startOverride')
                startOverride.set(f'{W}val', '1')
                
                root.append(new_num)
        
        # 重新写入
        new_xml = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
        temp_path = docx_path + '.tmp'
        with zipfile.ZipFile(docx_path, 'r') as zin:
            with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename == 'word/numbering.xml':
                        zout.writestr(item, new_xml)
                    else:
                        zout.writestr(item, zin.read(item.filename))
        # v3.8 修复: Windows 下 os.replace 偶发 WinError 5 (拒绝访问), 改用删+重命名+重试
        try:
            os.replace(temp_path, docx_path)
        except OSError:
            import time as _time; _time.sleep(0.1)
            try:
                if os.path.exists(docx_path): os.remove(docx_path)
            except OSError as _e:
                # v4.21 修复(A6):不再静默 except,记录异常类别便于排查 Windows 文件锁
                print(f'  [warn] os.remove 失败({type(_e).__name__}: {_e});继续 rename')
            os.rename(temp_path, docx_path)
    except Exception as e:
        print(f'  ⚠️ numbering修复失败: {e}')


def markdown_to_docx(input_md_path, output_docx_path):
    """将Markdown文件转换为Word文档（v2.5）
    
    关键修正（v2.5）：
    - 有序列表独立编号：每个独立列表从1开始（唯一nsid）
    
    关键修正（v2.4）：
    - 添加页脚页码
    
    关键修正（v2.3）：
    1. MD表格必须转为Word表格
    2. MD无序列表使用Word内置List Bullet样式
    3. MD有序列表使用Word内置List Number样式
    """
    # 读取md文件
    with open(input_md_path, 'r', encoding='utf-8-sig') as f:  # v3.8 修复: 用 utf-8-sig 去掉 BOM
        content = f.read()
    
    doc = Document()
    
    # 设置页面
    set_page_setup(doc)
    # v3.8 修复：覆盖默认标题颜色/字号/字体为深蓝 #003070 + 微软雅黑
    apply_global_styles(doc)
    
    # 去掉首页的空段落
    if doc.paragraphs and not doc.paragraphs[0].text.strip():
        doc.paragraphs[0]._element.getparent().remove(doc.paragraphs[0]._element)
    
    # 处理内容（带状态跟踪）
    state = {'last_was_list_number': False, 'current_list_num_id': 1, 'max_num_id': 9}
    process_markdown_content(content, doc, state)
    
    # 保存
    doc.save(output_docx_path)
    
    # 修复有序列表编号
    _fix_list_numbering(output_docx_path, state['max_num_id'])
    
    print(f"✅ Markdown已转换为Word: {output_docx_path}")

def main():
    if len(sys.argv) < 3:
        print("用法: python3 markdown_to_docx.py <输入.md> <输出.docx>")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    
    markdown_to_docx(input_path, output_path)

if __name__ == '__main__':
    main()








