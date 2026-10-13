# Phase 0 · 输入准备

把 `.doc/.docx/XMind/原始 Markdown/视频关键帧` 转成可净化的 Markdown 与辅助配图。产物回写源文件所在目录。

## Step 0.5 · .doc/.docx → Markdown

- 依赖：`python-docx`；
- 旧格式 `.doc` 在 Windows 上 `antiword` 不可用，优先用 `docx2txt` + `olefile`（已在 `law` 项目验证）；
- 脚本：`scripts/doc_to_md.py input.docx <源名>_raw.md`；
- 转换能力：标题层级保留、表格 → Markdown 表格、图片标注为 `[图片]`、加粗/斜体 → Markdown；
- **不输出 BOM**：用字节级读写，避免 PowerShell `Set-Content -Encoding UTF8` 自动加 BOM 导致 `re.sub(r'^# ', ...)` 不匹配。

## Step 0.6 · XMind → Markdown 大纲

- 脚本：`scripts/xmind_to_md.py 课程大纲.xmind 大纲.md`；
- 导图根节点 → H1，子节点 → H2/H3...，结构作为后续净化文档的标题骨架；
- 与转录文档组合：导图无而转录有的内容 → 补充分支；转录无而导图有的 → 保留空标题标 `[待补充]`。

## 验收（4 项）

- 表格已转为 Markdown 表格格式；
- 段落结构保留，标题层级正确；
- 字符数与原始差异 < 5%；
- 图片位置已标注。

## 含图片输入

若有图片，**先**读 `references/image-pipeline.md` 再继续 OCR 处理；不得跳过图片抽取。

## Step 0.7 · 视频关键帧接入（v4.1 新增）

若源目录含视频关键帧（典型：`frames/` 子目录下 JPG/PNG，或 `law` 流水线 `frames.py` 产物），按 `references/image-pipeline.md` "视频关键帧 → 配图再生" 节处理：

1. 抽取 OCR 文本 → 判定重要辅助帧；
2. 调用 `generate_image.py` 重新生成重要帧；
3. 按 OCR 与正文匹配，把再生图插入 HTML 正确位置。

关键帧原始文件保留在 `frames/`，不覆盖；再生图入 `img/fig-keyframe-NN.png`。
