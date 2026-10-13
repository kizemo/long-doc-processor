# OOXML 有序列表编号经验

> L0: lvlOverride+startOverride 是 OOXML 重启编号的唯一安全方式

## 正确方案

```xml
<!-- numbering.xml 中为每个独立列表添加 -->
<w:num w:numId="10">
  <w:abstractNumId w:val="7"/>  <!-- 共享ListNumber的absId -->
  <w:lvlOverride w:ilvl="0">
    <w:startOverride w:val="1"/>  <!-- 强制从1开始 -->
  </w:lvlOverride>
</w:num>
```

## 失败方案（已废弃）

1. ❌ 创建新 abstractNum + 唯一 nsid → etree.tostring 序列化破坏 XML，ListBullet 被污染
2. ❌ 填充空 abstractNum 的 lvl 定义 → 激活未预期的编号合并
3. ❌ numPr 放在 pStyle 之前 → 样式默认 numId=5 覆盖手动设置

## 段落 numPr 正确位置

```python
# ❌ 错误：numPr 在 pStyle 之前
pPr.insert(0, numPr)

# ✅ 正确：numPr 在 pStyle 之后
idx = list(pPr).index(pStyle) if pStyle in pPr else len(list(pPr))
pPr.insert(idx + 1, numPr)
```

## 版本记录

- v2.6 (2026-05-27): 发现并验证 lvlOverride 方案
- 对应 markdown_to_docx.py v2.7+
