# Phase 3 · 渲染 HTML

把合并并编号完成的 Markdown 渲染为可独立打开的 HTML 讲义。

## 调用

```bash
python scripts/markdown_to_html.py merged_numbered.md <标题>_final.html
```

脚本接收：合并编号后的 Markdown 文件路径、目标 HTML 文件路径。
脚本输出：可双击打开的单文件 HTML + 同级 `img/` 子目录。

## HTML 结构

- 单一 HTML 文件，内嵌 CSS（无外部依赖，可离线打开）；
- 顶部含 `<title>` 与简单目录（来自 H1/H2）；
- 标题层级用语义化标签：`h1`/`h2`/`h3`/`h4`；
- 图片统一相对路径 `img/xxx.png`；
- 代码块、表格、引用等 Markdown 元素使用对应 HTML 标签。

## 渲染验收

```bash
python scripts/verify_html.py <标题>_final.html
```

验收项见 `references/qa-gates.md` 第 17–22 项。

## 错误处理

- 渲染失败 → 立即停止并报告依赖缺失或模板错误；
- 缺少 `markdown_to_html.py` → 检查 skill 安装是否完整；
- 图片引用缺失 → 读取 `references/image-pipeline.md` 校验图片生成或 OCR 产物是否齐全。

## 输出

HTML 文件与 `img/` 子目录回写源文件所在目录，命名：

```text
<源名>_final.html
img/fig-1-2-data-flow.png
...
```
