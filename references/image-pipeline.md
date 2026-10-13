# 图片处理流水线

输入文档或视频关键帧含图片时，必须按本文件执行 OCR 与（必要时）配图生成。

## Step 1 · 抽取图片

```bash
python scripts/ocr_images.py <输入.docx|xmind|md目录> <提取目录>
```

脚本从 `.docx`/XMind 中抽取内嵌图片，并把 Markdown 引用的本地图片复制到提取目录；每张图生成 `<hash>.png` 与 `<hash>.ocr.txt`。

## Step 2 · OCR 与冲突改写

OCR 文本按以下规则合并到主文档：

1. **冲突**：OCR 文本与同位置原文不一致（公式、专有名词、数据点）→ **以 OCR 文本为准**，原文被替换；
2. **补充**：OCR 文本含原文未覆盖信息 → 按原位或就近 H3 插入，标注 `[来源：图片OCR]`；
3. **同义**：OCR 与原文完全一致 → 不修改。

差异与最终覆盖写入 `references/qa-gates.md` 报告对应行。

## Step 3 · 必要性判定

仅当满足以下条件之一才触发配图生成：

- 原图是流程图、概念示意、数据可视化，且 Markdown 中无对应说明；
- 文本明确引用视觉内容（"如图所示"却无图）；
- 章节主题高度依赖视觉表达。

判定由主代理按本清单逐项比对，不为所有图片自动生成新图。

## Step 4 · 配图生成

```bash
python scripts/generate_image.py --prompt "<原图语义>" --out <源目录>/img/fig-1-2-data-flow.png
```

> **视觉规范**：每次调用 `generate_image.py` 时，脚本**自动注入** `references/image-style.md` 定义的视觉规范段（文字容器、对比度、字号等）；如需禁用，加 `--no-style-suffix`。
>
> 主代理应在 prompt 中清晰描述主题与布局，脚本负责追加样式规则；出图后须人工验收（详见 `image-style.md` §5）。

### 实现策略（可插拔）

- **Claude / MiniMax-M3 会话**：设置环境变量 `MINIMAX_IMAGE_GEN=1`，脚本生成 `.prompt.txt` 占位（含视觉规范），**主代理读取后调用 MiniMax-M3 图片大模型生成**并写入指定路径；
- **Codex / 其他 runtime**：按 `references/runtime-compatibility.md` 能力契约选择实现（本地 SDXL、`huashu-gpt-image` 等）；
- **不可用**：跳过该张配图，不阻塞整体交付；在会话任务总结中列出缺失图位。

### 命名与位置

- 文件名：`fig-{H2}-{H3}-{语义}.png`，例如 `fig-1-2-data-flow.png`；
- 位置：HTML 同级目录的 `img/` 子目录；
- 不覆盖原始输入图片；新图内容不与 OCR 文本重复。

## Step 5 · HTML 嵌入

- 渲染阶段把图片引用写入 `<img src="img/xxx.png" alt="..." data-source="ocr|original|generated">`；
- `alt` 简述图片内容；`data-source` 标注来源，便于审阅；
- 渲染时若引用文件缺失，Phase 3 立即报错并停止验收。

---

## 视频关键帧 → 配图再生（v4.1 新增）

输入含视频关键帧截图时（典型来源：`law` skill 流水线 `frames.py` 抽帧产物，或源目录 `frames/` 子目录下的 JPG 文件），按本节生成辅助配图。

### Step V1 · 关键帧 OCR 与分类

```bash
# 关键帧位于源目录的 frames/ 子目录
python scripts/ocr_images.py <源目录>/frames <源目录>/frames_ocr/
```

每帧生成 `<hash>.png` 与 `<hash>.ocr.txt`。主代理按下列清单逐项判定"重要辅助帧"：

| # | 类别 | 典型场景 |
|---|------|---------|
| 1 | 视觉化概念 | 框架图、模型图、关系图、对比图 |
| 2 | 视觉化理论 | 公式图、原理示意图、流程图 |
| 3 | 视觉化实操 | 操作步骤截图、界面截图、案例截图 |
| 4 | OCR 强相关 | 关键帧文本含专有名词、数据、流程节点，与正文主题强相关 |

**不满足任一条件的帧视为装饰帧**（讲师头像、片头片尾、空白过渡、纯背景），**跳过再生**。

### Step V2 · 重新生成

对判定为重要的帧：

```bash
python scripts/generate_image.py --prompt "<原关键帧 OCR 摘要 + 场景描述>" --out <源目录>/img/fig-keyframe-NN.png
```

- **Prompt 构造**：融合 OCR 文本关键信息 + 场景描述（如"电商直播讲解搜索权重时讲师手绘的对比图"）；
- **命名**：`fig-keyframe-NN.png`，NN 为两位顺序号；
- **位置**：HTML 同级目录 `img/` 子目录；
- **不覆盖原关键帧**；原关键帧保留在 `frames/` 不动。

### Step V3 · 定位插入

主代理按 OCR 文本与正文段落匹配，把重新生成的图片插入 HTML 对应位置：

| 匹配类型 | 插入位置 |
|---------|---------|
| 关键帧对应正文某 H3 子节 | 该 H3 段首或段中合适位置 |
| 关键帧对应跨节概念 | 第一个引用该概念的 H3 下方 |
| 关键帧无明确正文锚点 | 按主题相关性就近插入，并在 `alt` 注明位置依据 |

HTML 写入：

```html
<img src="img/fig-keyframe-NN.png"
     alt="<OCR 摘要 + 场景说明>"
     data-source="generated-from-keyframe">
```

### Step V4 · 错误处理

- 关键帧 OCR 失败 → 跳过该帧，不阻塞整体交付；
- 重新生成模型不可用 → 在会话任务总结中列出缺失图位与原因，跳过该帧；
- 关键帧全部为装饰 → 跳过整个本节，正常进入 Phase 1；
- 渲染时若引用文件缺失 → Phase 3 立即报错并停止验收。

### 验收（与 `references/qa-gates.md` 对应）

- 30. 关键帧 OCR 抽取完成；
- 31. 重要辅助帧已按 4 类清单判定；
- 32. 装饰帧（讲师头像/片头片尾/空白）已跳过；
- 33. 重新生成的图片保存到 `img/`，命名遵循 `fig-keyframe-NN.png`；
- 34. HTML 中按 OCR 文本与正文匹配位置插入，含 `alt` 与 `data-source="generated-from-keyframe"`。
