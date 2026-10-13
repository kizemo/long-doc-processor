# Phase 1.8 · 原帧智能裁剪与插入

> **版本**: v4.19 (2026-09-29)
> **触发场景**: 视频转写项目需要把原始关键帧经 LLM 决策后**裁剪**为局部画面,**插入**到 cleaned.md 对应 H3 子节,与文字并行阅读。
> **沉淀项目**: 边界 2026-06-03_AI助力主图点击率低 第二轮迭代

## 1. 目标

复用 crv 抽帧产物(`frames/` + `frames.json`),不重新抽帧。通过**两阶段 LLM 决策**(Stage 1 评分筛选 → Stage 2 逐帧决策)+ **Python 脚本执行**(Stage 3 PIL 裁剪 + Markdown 注入),把视频原始关键帧转换为高质量局部图,与 H3 段落正文并行展示。

## 2. 流水线架构

```
Phase 1.7 (LLM Semantic Pass)
       ↓ (产出 cleaned.md, H3 结构已稳定)
【新】Phase 1.8
  ┌──────────────────────────────────────────────┐
  │ Stage 1 · LLM 评分筛选(1 次 LLM 调用)        │
  │  输入: frames.json(N帧) + cleaned.md H3 列表  │
  │  输出: top8[{frame_id, score, h3_hint}]       │
  │  阈值: score ≥ 0.65 才进入 Stage 2            │
  ├──────────────────────────────────────────────┤
  │ Stage 2 · 逐帧 LLM 决策(≤8 次串行 LLM)       │
  │  输入: 单帧 + 全文 + 该帧 ±30s ASR 上下文     │
  │  输出: {h3_target, crop_box, caption, score}  │
  │  crop_box 格式: {x, y, w, h} 0-1 归一化坐标   │
  ├──────────────────────────────────────────────┤
  │ Stage 3 · Python 脚本执行                     │
  │  - PIL 读帧 → 裁剪 → resize ≤800x600         │
  │  - JPEG 压缩 ≤ 200KB                          │
  │  - 保存 img/fig-crop-NN-{semantic}.jpg       │
  │  - 注入 cleaned.md 对应 H3 段首下一行         │
  └──────────────────────────────────────────────┘
       ↓
Phase 2 (合并) — 已存在,本次不动
       ↓
Phase 3 (markdown → HTML)
       ↓
verify_html (5/5 + 新加规则 35-38)
```

## 3. Stage 1 · LLM 评分筛选(OCR-only)

### 3.1 输入

- `frames.json`:`[{frame_id, timestamp, ocr_text, image_path}, ...]` (N 张,典型 N=30-80)
- `cleaned.md`:取 H3 列表 `["1.1 课程说明", "1.2 案例 1:电钻", ...]`(典型 35 个左右)

### 3.2 Prompt 模板

```
你是电商培训视频内容匹配专家。下面是视频中 N 个候选关键帧(每帧:时间戳 + OCR文本)
和讲座净化后的 N 个 H3 子节标题。请为每帧评估"对讲座哪个 H3 子节有视觉辅助价值"。

排除规则(必须遵守):
- 讲师头像 / 半身像 / 头像特写
- 片头片尾 / 空白过渡帧
- 仅含 PPT chrome / logo / 水印
- OCR 文本与所有 H3 主题均不相关

评分规则:
- 1.0: 完美匹配,帧内容是该 H3 主题的核心视觉(公式图/案例截图/操作步骤)
- 0.8: 强相关,帧内容是 H3 的辅助视觉(对比图/数据图/示例)
- 0.6: 弱相关,可有可无
- 0.0-0.5: 不相关或装饰帧

输出 JSON 数组(按 score 降序,只返回 score ≥ 0.65 的帧):
[{"frame_id": "...", "score": 0.85, "h3_hint": "1.2", "rationale": "..."}]

若所有帧 score < 0.65,返回 []。
```

### 3.3 输出

`top8.json`,按 score 降序的 Top-8 候选帧。

## 4. Stage 2 · 逐帧 LLM 决策

### 4.1 输入(对 top8 中每一帧)

- 单帧图片(base64 编码)
- `cleaned.md` 全文(截断到 8K chars 防 prompt 过长)
- 该帧时间戳前后 30s 的 ASR transcript 段(`audio_paragraphs.md` 切片)
- `h3_hint` (来自 Stage 1,LLM 初始猜测的 H3)

### 4.2 h3_hint 与 h3_target 关系

- Stage 1 OCR-only 看到文字,**猜测**最可能的 H3,作为 h3_hint 输出
- Stage 2 看到实际帧 + 全文,**最终决定** h3_target(可与 h3_hint 相同或不同)
- h3_hint 注入 Stage 2 prompt,让 LLM 优先确认/微调,而不是从零搜索
- 若 Stage 2 判定 h3_hint 完全错误,LLM 可改选其它 H3

### 4.3 Prompt 模板

```
你是视觉内容分析专家。请分析这张视频关键帧,并决定它对应讲座哪个 H3 子节。

注意:已从 OCR 文本初步判断 h3_hint = "{h3_hint}",你可以确认或改选其它 H3。

裁剪规则:
- 必须排除讲师人像/头像/半身像
- 必须排除 PPT chrome/logo/水印/页眉页脚
- 必须保留主题内容(公式/表格/案例图/操作界面/数据图)
- 若整图无清晰主题,score=0,不裁剪不插入

帧 ID: {frame_id}
时间戳: {timestamp}s
ASR 上下文(±30s):
{asr_context}

cleaned.md 全文:
---
{full_md}
---

输出 JSON(单选):
{"frame_id": "{frame_id}", "h3_target": "1.2", "crop_box": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.7}, "caption": "...", "score": 0.85}
```

### 4.4 输出

`crop_decisions.json`,每帧一条决策。串行执行(按 score 降序),每帧一个独立 LLM 调用。

## 5. Stage 3 · Python 脚本执行

### 5.1 核心逻辑(`scripts/_crop_insert_frames.py`)

```python
# 伪代码
def main(frames_dir, frames_json, cleaned_md, decisions_json, output_dir):
    decisions = load_json(decisions_json)
    for i, dec in enumerate(decisions, 1):
        if dec['score'] < 0.65: continue
        # PIL 读帧 → 裁剪(5% padding) → resize → JPEG 压缩 ≤ 200KB
        # 保存 img/fig-crop-NN-{semantic}.jpg
        # 注入 cleaned.md 对应 H3 段首下一行
```

### 5.2 Markdown 注入格式

```markdown
### 1.2 案例 1:电钻

![电钻按工种拆分案例图](img/fig-crop-01-electric-drill.jpg)

电钻是反复引用的经典案例,用来引入"需求判断"。
...
```

## 6. 硬约束(5+1 条)

| # | 约束 | 实现位置 |
|---|---|---|
| 1 | **8 张硬上限**: 整篇讲座最多插入 8 张图(超过则截断) | `_crop_insert_frames.py` main() |
| 2 | **单图 ≤ 200KB**: JPEG quality=85 + optimize=True 强制保证 | `crop_frame()` 循环降 quality |
| 3 | **最大尺寸 800x600**: thumbnail() 限制,保持 HTML 加载快 | `crop_frame()` |
| 4 | **5% padding 内缩**: crop_box 转像素坐标时四周各缩 5% | `crop_box_to_pixels()` |
| 5 | **crop_box 0-1 归一化**: LLM 返回 {x,y,w,h} ∈ [0,1] | Stage 2 prompt 强约束 |
| 6 | **score ≥ 0.65 阈值**: Stage 1 和 Stage 2 输出都过滤 | `run_stage1()` + `run_stage2()` |

## 7. 数据契约

### 7.1 输入文件

| 文件 | 来源 | 内容 |
|---|---|---|
| `frames/` | Phase 0 (crv) | JPG 关键帧 |
| `frames.json` | Phase 0 (crv) | 帧元数据 `{id, ts, ocr, path}` |
| `cleaned.md` | Phase 1.7 后 | 含 H1/H2/H3/H4 结构 |
| `audio_paragraphs.md` | Phase 0 (faster-whisper) | ASR 段落化文本(带时间戳) |

### 7.2 中间产物

| 文件 | 内容 |
|---|---|
| `output/test-crv2/top8.json` | Stage 1 输出的 Top-8 候选 |
| `output/test-crv2/crop_decisions.json` | Stage 2 输出的逐帧决策 |

### 7.3 最终输出

| 文件 | 内容 |
|---|---|
| `output/cleaned.md` | 原文件 + 8 处 `![]()` 注入 |
| `output/img/fig-crop-NN-{semantic}.jpg` | 裁剪后图像(≤8 张) |
| `output/final.html` | Phase 3 重渲染(现有,自动含新图) |

## 8. 验收 (qa-gates 35-38)

- [ ] **规则 35**: cleaned.md 中 `![]()` 引用数 ≤ 8
- [ ] **规则 36**: `img/fig-crop-*.jpg` 文件存在且每张 ≤ 200KB
- [ ] **规则 37**: 每张图对应 H3 在 cleaned.md 中存在
- [ ] **规则 38**: 每张图 caption ≥ 5 字(非空占位)
- [ ] **原有 5/5 PASS** 仍保持(PASS[17] / PASS[17b] / PASS[18] / PASS[21] / PASS[22])

## 9. 错误处理

| 失败模式 | 处理 |
|---|---|
| Stage 1 LLM 返回 `[]`(无相关帧) | 跳过整个 Phase 1.8,记录日志 |
| Stage 2 任一帧 LLM 调用失败 | 该帧跳过,不阻塞其他帧 |
| Stage 2 crop_box 越界(超出 0-1) | clamp 到 [0, 1],脚本内做边界保护 |
| Stage 3 PIL 读帧失败 | 该帧跳过,不阻塞其他帧 |
| Stage 3 注入 cleaned.md 时 H3 不存在 | 记录 WARN,跳过该帧 |
| 任意 Stage 整体失败 | 跳过 Phase 1.8,Phase 3 用原 cleaned.md 继续渲染 |

## 10. 端到端执行流程

### 10.1 前置条件

```bash
export ANTHROPIC_API_KEY="sk-..."
```

### 10.2 执行步骤

```bash
# 1. 备份 cleaned.md(失败可回滚)
cp output/<stem>_cleaned.md output/<stem>_cleaned.v18.md.bak

# 2. Stage 1: 评分筛选(N → Top-8)
python scripts/_stage1_score.py \
  --frames-json output/test-crv2/frames.json \
  --cleaned-md output/<stem>_cleaned.md \
  --output-json output/test-crv2/top8.json \
  --max-count 8

# 3. Stage 2: 逐帧决策(≤8 次 LLM 调用)
python scripts/_stage2_decide.py \
  --frames-dir output/test-crv2/frames \
  --frames-json output/test-crv2/frames.json \
  --top8-json output/test-crv2/top8.json \
  --asr-md output/test-crv2/audio_paragraphs.md \
  --cleaned-md output/<stem>_cleaned.md \
  --output-json output/test-crv2/crop_decisions.json

# 4. Stage 3: 裁剪 + 注入(PIL)
python scripts/_crop_insert_frames.py \
  --frames-dir output/test-crv2/frames \
  --frames-json output/test-crv2/frames.json \
  --decisions-json output/test-crv2/crop_decisions.json \
  --cleaned-md output/<stem>_cleaned.md \
  --output-dir output/

# 5. 重渲染 HTML
python scripts/markdown_to_html.py \
  output/<stem>_cleaned.md \
  output/<stem>_final.html

# 6. verify_html 5/5 + 4 spot-check
python scripts/verify_html.py output/<stem>_final.html
```

### 10.3 4 项人工 spot-check

```bash
# 检查 img/ 文件存在 + 大小
ls -la output/img/fig-crop-*.jpg
# 期望: ≤8 个 .jpg, 每个 ≤ 200KB

# 检查 cleaned.md 中 ![]() 数 ≤ 8
grep -c "^!\[" output/<stem>_cleaned.md
# 期望: 0-8 之间

# 检查每张图对应 H3 在 cleaned.md 中存在
python -c "
import re
md = open('output/<stem>_cleaned.md', encoding='utf-8').read()
h3 = set(re.findall(r'^### (\d+\.\d+)', md, re.MULTILINE))
imgs = re.findall(r'!\[([^\]]*)\]\(img/fig-crop-\d+-([\w-]+)\.jpg\)', md)
print(f'H3 数: {len(h3)}, 图数: {len(imgs)}')
"

# 检查 caption ≥ 5 字
python -c "
import re
md = open('output/<stem>_cleaned.md', encoding='utf-8').read()
caps = re.findall(r'!\[([^\]]+)\]\(img/', md)
short = [c for c in caps if len(c) < 5]
print(f'short caption: {short if short else \"(无)\"}')
"
```

## 11. 反模式(不要做)

- ❌ **不要跳过 Stage 1**: 即使帧数 < 8,Stage 1 仍可筛选出最相关的子集,降低 Stage 2 API 成本
- ❌ **不要合并 Stage 1 + Stage 2**: 二者分工不同,Stage 1 OCR-only,Stage 2 看帧 + ASR
- ❌ **不要把 h3_hint 当 h3_target 用**: Stage 1 的猜测可能错,Stage 2 必须独立决定
- ❌ **不要 LLM 把讲师当主题插入**: 即使 prompt 强排除,仍可能误判,score<0.65 兜底
- ❌ **不要硬编码模型名**: 脚本支持 `claude-sonnet-4-5`(默认)/ `gpt-4-vision-preview`(fallback)
- ❌ **不要跳过边界 clamp**: LLM 视觉坐标偏差 ±5%,clamp 是兜底
- ❌ **不要覆盖原帧**: 输出 `fig-crop-NN-*.jpg` 写到 `output/img/`,不修改 `frames/`
- ❌ **不要把单图超过 200KB**: 8 张图导致 HTML 过大,加载慢
- ❌ **不要把图插入到 H2/H4**: 仅插入 H3 段首下一行(plan 决策)

## 12. 已知陷阱

| 陷阱 | 现象 | 解决 |
|---|---|---|
| LLM 视觉坐标偏差 ±5% | 主体裁切 | crop_box 内缩 5% padding + 边界 clamp |
| LLM 把讲师当主题 | 错误插入讲师头像 | prompt 强制排除 + score<0.65 兜底 |
| 8 张图导致 HTML 过大 | 加载慢 | 单图 ≤ 200KB + 800x600 max |
| 帧时间戳与 ASR 错位 | caption 失准 | ±60s 容差(Stage 2 window=30s + 切片) |
| LLM 调用超 60s | 单 Stage 失败 | 该帧跳过,其他继续 |
| multi-turn LLM 上下文污染 | 决策偏差 | 每帧独立调用,不共享 context |
| Stage 1/2 无 API key | 返回空响应 | 脚本优雅失败,跳过整个 Phase 1.8 |
| crop_decisions.json 缺字段 | Stage 3 抛 KeyError | `parse_stage2_response` 必填字段校验,缺则 None 跳过 |

## 13. 相关脚本

- `scripts/_llm_vision.py` — 通用多模态 LLM 调用封装 (~60 行)
- `scripts/_stage1_score.py` — Stage 1 LLM 评分筛选 (~80 行)
- `scripts/_stage2_decide.py` — Stage 2 逐帧 LLM 决策 (~120 行)
- `scripts/_crop_insert_frames.py` — Stage 3 PIL 裁剪 + Markdown 注入 (~150 行)

## 14. 相关 qa-gates

| 规则 | 内容 |
|---|---|
| **35** | cleaned.md 中 `![]()` 引用数 ≤ 8 |
| **36** | `img/fig-crop-*.jpg` 文件存在且每张 ≤ 200KB |
| **37** | 每张图对应 H3 在 cleaned.md 中存在 |
| **38** | 每张图 caption ≥ 5 字(非空占位) |

> 注:原"配图视觉规范"4 项(35-38)已重编号为 39-42,Phase 1.8 新规则占 35-38。

## 15. 版本演进

- **v4.19 (2026-09-29)**: 首版,边界 2026-06-03 项目第二轮迭代沉淀
- **未来 v4.20+**: 可选扩展 — 9-16 张上限(大型讲座)/ 多种 crop 模式(中心裁剪 vs LLM 坐标)/ 自动调色(用户要求时)