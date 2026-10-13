# Phase 2 · 多文档合并（Step 5–10）

合并多份已净化 Markdown，输出可由 Phase 3 渲染的合并稿。

## Step 5 · 接收文档 + 统计结构

统计每篇 L1/L2/L3 数量与字符数，输出表格到源目录。

## Step 5.5 · 去除尾部 `## 统计` 区块

合并前移除每篇净化文档末尾的 `## 统计` 区块；用 Python `re.sub` 单次完成，避免与标题降级互相覆盖。

## Step 6 · LLM 分析合并方案

提取 L1/L2 摘要 → LLM 判断重复/交叉 → 输出合并大纲与章节归属映射（精确到每个 L1）。

## Step 7 · 执行文档合并

- 去统计 → 降级标题（H1→H2, H2→H3, H3→H4）→ 在文件顶部添加总 H1；
- **占位符策略**：降级必须用不含 `#` 前缀的占位符（如 `PLACEHOLDER_H2`），回填一步完成；禁止连续 `re.sub` 同前缀导致级联；
- 输出 `<标题>_merged.md` 到源目录。

## Step 8 · 标题自动编号

- 强制步骤，不可跳过；
- 脚本：`scripts/renumber_headings.py merged.md merged_numbered.md [--scheme chinese|dotted] [--on-collision {increment|fail|skip}] [--preview]`；
- 默认 `chinese` + `increment`；先 `--preview` 看冲突。

## Step 9 · 去空行 + 结构验证

```python
# 去多余空行（用 Python 不用 sed，避免平台差异）
content = re.sub(r'\n{3,}', '\n\n', open(p).read())
```

- `--verify-only` 跑一遍，确认输出 `✅ 全部通过`。

## Step 10 · 16 项结构自检

验收清单与退出条件见 `references/qa-gates.md`；本阶段只引用，不复制。

## 合并后含图片

若合并稿里含图片占位符 `[图片]`，按 `references/image-pipeline.md` 在 Phase 3 渲染前处理。
