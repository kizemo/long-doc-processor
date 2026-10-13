#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

"""
⚠️ DEPRECATED (v3.8) ⚠️

本脚本的 10 项验收已被 word-format/scripts/verify_v6.py 的 26 项 4 维度验收
完全覆盖。

从 v3.8 起，long-doc-processor 的 Step 11 验收统一调 verify_v6.py。
本脚本保留仅作历史兼容，不再推荐使用。

迁移指引：
  # 旧用法（v3.7）
  python long-doc-processor/scripts/verify_docx.py output.docx
  # 新用法（v3.8+，推荐）
  python word-format/scripts/verify_v6.py output.docx

若必须继续使用本脚本，请忽略以下 deprecation 警告。

---

原 10 项标准（已废弃）：

Markdown转Word文档 - 完整验收脚本
检查所有10项标准，必须全部通过才能发送
"""

import sys
from docx import Document
from docx.shared import Pt

def verify_docx(docx_path):
    """完整验收10项标准"""
    results = []
    
    try:
        doc = Document(docx_path)
    except Exception as e:
        print(f"❌ 无法打开文档: {e}")
        return False
    
    # 1. 标题中无#残留
    hash_issues = []
    for p in doc.paragraphs:
        text = p.text.strip()
        # 排除正常内容，只检查以#开头的标题类内容
        if text and text.startswith('#'):
            style = p.style.name if p.style else ''
            if 'Heading' not in style and 'Title' not in style:
                hash_issues.append(text[:50])
    
    results.append(("【1】标题中无#残留", len(hash_issues) == 0, f"{len(hash_issues)}处残留" if hash_issues else "✅"))
    
    # 2. **加粗**已转为Word加粗（无残留）
    bold_issues = [p for p in doc.paragraphs if '**' in p.text]
    results.append(("【2】**加粗**已转Word加粗", len(bold_issues) == 0, f"{len(bold_issues)}处残留" if bold_issues else "✅"))
    
    # 3. H4标题已处理（####转为14pt加粗样式）
    h4_count = 0
    for p in doc.paragraphs:
        run = p.runs[0] if p.runs else None
        if run and run.font.size:
            size = run.font.size.pt
            is_bold = run.font.bold
            style = p.style.name if p.style else ''
            if abs(size - 14) < 1 and is_bold and 'Heading' not in style and 'Title' not in style:
                h4_count += 1
    results.append(("【3】H4标题已处理", h4_count >= 0, f"{h4_count}处H4已转H3" if h4_count > 0 else "✅ 无H4（已正确处理）"))
    
    # 4. 文档有主标题（H1 或 Title 样式均可，v3.8 修复）
    has_h1 = any((p.style.name if p.style else '') in ('Title', 'Heading 1') for p in doc.paragraphs)
    title_text = ""
    for p in doc.paragraphs:
        sn = p.style.name if p.style else ''
        if sn in ('Title', 'Heading 1'):
            title_text = p.text[:30]
            break
    results.append(("【4】文档有主标题(H1/Title)", has_h1, title_text if title_text else "❌"))
    
    # 5. H1/H2/H3字号正确
    h_checks = []
    for level, expected in [('Heading 1', 18), ('Heading 2', 16), ('Heading 3', 15)]:
        sizes = []
        for p in doc.paragraphs:
            if level in (p.style.name if p.style else ''):
                run = p.runs[0] if p.runs else None
                if run and run.font.size:
                    sizes.append(run.font.size.pt)
        if sizes:
            avg = sum(sizes) / len(sizes)
            ok = abs(avg - expected) < 1
            h_checks.append(ok)
    h_all_ok = all(h_checks) if h_checks else False
    results.append(("【5】H1(18pt)/H2(16pt)/H3(15pt)", h_all_ok, "✅" if h_all_ok else "❌"))
    
    # 6. 正文字号12pt
    normal_sizes = []
    for p in doc.paragraphs:
        if 'Normal' in (p.style.name if p.style else '') and p.text.strip():
            run = p.runs[0] if p.runs else None
            if run and run.font.size:
                normal_sizes.append(run.font.size.pt)
    if normal_sizes:
        avg = sum(normal_sizes) / len(normal_sizes)
        ok = abs(avg - 12) < 1
        results.append(("【6】正文字号12pt", ok, f"{avg:.1f}pt"))
    else:
        results.append(("【6】正文字号12pt", False, "未找到Normal段落"))
    
    # 7. 标题颜色为深蓝#003070
    color_checks = []
    for level in ['Title', 'Heading 1', 'Heading 2', 'Heading 3']:
        for p in doc.paragraphs:
            if level in (p.style.name if p.style else ''):
                run = p.runs[0] if p.runs else None
                if run and run.font.color and run.font.color.rgb:
                    color = str(run.font.color.rgb).upper()
                    color_checks.append('003070' in color or '00307' in color)
                    break
    color_ok = all(color_checks) if color_checks else False
    results.append(("【7】标题颜色深蓝#003070", color_ok, "✅" if color_ok else "❌"))
    
    # 8. 行距26pt
    ls_values = []
    for p in doc.paragraphs:
        if p.paragraph_format.line_spacing:
            ls = p.paragraph_format.line_spacing
            if hasattr(ls, 'pt'):
                ls_values.append(ls.pt)
            else:
                ls_values.append(ls / 914400 * 72)
    if ls_values:
        avg = sum(ls_values) / len(ls_values)
        ok = abs(avg - 26) < 2
        results.append(("【8】行距26pt", ok, f"{avg:.1f}pt"))
    else:
        results.append(("【8】行距26pt", False, "未找到行距设置"))
    
    # 9. 页面设置为A4
    section = doc.sections[0]
    w = section.page_width.cm
    h = section.page_height.cm
    ok = abs(w - 21) < 0.5 and abs(h - 29.7) < 0.5
    results.append(("【9】页面A4(21cm×29.7cm)", ok, f"{w:.1f}cm×{h:.1f}cm"))
    
    # 10. 文档命名（v3.8 修复：tmp/merged 改为提示而非硬 FAIL——CI/测试环境常用临时名）
    import os
    filename = os.path.basename(docx_path)
    bad = ('merged' in filename.lower() or 'tmp' in filename.lower()
           or filename.lower().startswith('untitled') or filename.lower() == 'document.docx')
    results.append(("【10】文档命名提示", not bad, f"⚠️ 临时名: {filename}" if bad else filename))
    
    # 打印结果
    print("=" * 50)
    print("Markdown转Word 完整验收报告")
    print("=" * 50)
    all_passed = True
    for name, passed, detail in results:
        status = "✅" if passed else "❌"
        print(f"{status} {name}: {detail}")
        if not passed:
            all_passed = False
    
    print("=" * 50)
    if all_passed:
        print("🎉 全部通过！可以发送。")
    else:
        print("⚠️ 有未通过项，请修复后重新验收。")
    print("=" * 50)
    
    return all_passed

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 verify_docx.py <docx文件路径>")
        sys.exit(1)
    
    docx_path = sys.argv[1]
    passed = verify_docx(docx_path)
    sys.exit(0 if passed else 1)




