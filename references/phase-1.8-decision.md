# Phase 1.8 首问判定逻辑

> **版本**: v4.20 (2026-09-30)
> **触发**: long-doc-processor skill 加载后,Step 0.7 必做首问判定
> **配套**: `scripts/_stage1_score.py` + `_stage2_decide.py` + `_crop_insert_frames.py` + `_llm_vision.py`
> **v4.20 新增**: 第 3 选项 C(Path G 排版补救) — 详见 `references/path-g-typography-fallback.md`

## 1. 决策树

```
用户消息命中"插入截图/插图/配图/加图/原帧/裁剪/crop/Phase 1.8"等关键词?
├── 是 → 直接调用 Phase 1.8 三阶段流水线
│        (默认参数: 8 张硬上限 / 200KB/张 / 800x600 max / score ≥ 0.65 / H3 注入)
│        └─ 跑完后人工目视,低质图触发 Path G (C 选项)
└── 否 → AskUserQuestion 卡片让任务发布者选 3 选项:
           A. 跑 Phase 1.8 (8 张硬上限 + 200KB/张 + H3 注入)  ← 推荐
           B. 跳过,直接渲染 HTML
           C. Path G 排版补救 (v4.20 新增): 用 typography 替代截图
              适合视频无演示帧/案例主题无图/用户主动放弃
              详见 references/path-g-typography-fallback.md
```

## 2. 触发关键词清单(中英文 ~15 个)

### 2.1 中文关键词

| 关键词 | 适用语义 |
|---|---|
| 插入截图 | 明确表达要加截图 |
| 插图 | 同上 |
| 配图 | 同上 |
| 加图 | 同上 |
| 加点图 | 同上 |
| 加一些截图 | 同上 |
| 原帧 | 指原视频关键帧裁剪(Phase 1.8 特有) |
| 关键帧裁剪 | 同上 |
| 截图注入 | 同上 |
| H3 加图 | 隐含 Phase 1.8 H3 注入逻辑 |

### 2.2 英文关键词

| 关键词 | 适用语义 |
|---|---|
| crop | 裁剪 |
| crop frame | 关键帧裁剪 |
| Phase 1.8 | 直接点名 |
| frame crop | 同上 |
| keyframe crop | 同上 |
| insert image | 插入图 |

### 2.3 不触发的关键词(避免误判)

- "配图"如果上下文是"讲解 AI 配图工具"→ 不触发(语义不是插入图)
- "截图"如果上下文是"截图给我看 bug"→ 不触发(语义不是文档插入图)

判定原则:**用户消息主谓宾结构**,目标是让最终 cleaned.md 含 `![]()` 行 → 才触发。

## 3. AskUserQuestion 卡片模板

```python
from AskUserQuestion import AskUserQuestion

AskUserQuestion(
    questions=[{
        "question": "本次任务是否需要在 cleaned.md 插入截图(Phase 1.8)?",
        "header": "插入截图",
        "options": [
            {
                "label": "跑 Phase 1.8 (8 张硬上限 + 200KB/张 + H3 注入)",
                "description": "LLM 评分筛选 Top-8 → 逐帧决策 → PIL 裁剪注入。需 ANTHROPIC_API_KEY,默认参数 8 张/200KB/800x600/score≥0.65。"
            },
            {
                "label": "跳过,直接渲染 HTML",
                "description": "不做截图,直接用现有 cleaned.md 渲染 final.html。适合纯文字讲座或用户主动要求无图版本。"
            },
            {
                "label": "Path G 排版补救 (v4.20 新增)",
                "description": "不插截图,改用 typography 强化文档: 加粗 inline / 表格 / SVG inline / 多行 blockquote. 适合视频无演示帧 / 主题无图 / 用户主动放弃. 详见 references/path-g-typography-fallback.md"
            }
        ],
        "multiSelect": False
    }]
)
```

## 4. Phase 1.8 默认参数

| 参数 | 默认 | 来源 |
|---|---|---|
| 8 张硬上限 | 8 | spec §2.2 |
| 单图大小 | ≤ 200KB | spec §6 错误处理 + qa-gates 规则 36 |
| 单图尺寸 | ≤ 800x600 | spec §3 Stage 3 |
| score 阈值 | ≥ 0.65 | spec §4.1 |
| crop_box padding | 5% 内缩 | spec §4.3 |
| 注入位置 | H3 段首下一行 | spec §4.3 |
| LLM 模型 | claude-sonnet-4-5 | scripts/_llm_vision.py 默认 |

用户不能调整这些参数(脚本不接受这些 flags)。如需调整,必须手动改 `_crop_insert_frames.py` 默认值。

## 5. 失败兜底(同 spec §6)

- Stage 1 LLM 返回 `[]` → 跳过整个 Phase 1.8,Phase 3 用原 cleaned.md
- Stage 2 任一帧 LLM 失败 → 该帧跳过,其他继续
- Stage 3 PIL 读帧失败 → 该帧跳过
- Stage 3 H3 不存在 → 该帧跳过,图保留在 `img/` 但不入 md
- 任意 Stage 整体失败 → 跳过 Phase 1.8,Phase 3 用原 cleaned.md 继续

**关键约束**: 任何失败**不阻塞** Phase 3 HTML 渲染。

## 6. 集成位置

```
Step 0 (ASR 模型选)
Step 0.5 (输出目录名)
Step 0.6 (OUTPUT_STEM)
Step 0.7 (是否插入截图)  ← 本文件
   │
   ├─ 用户选 A → 走 Phase 1.8 (在 Phase 1.7 LLM Semantic Pass 之后 → Phase 2 合并之前)
   └─ 用户选 B → 跳过,直接 Phase 3 渲染
```

Phase 1.8 必须在 **Phase 1.7 之后 → Phase 2 合并之前**插入(此时 H3 结构已稳定,cleaned.md 含 H1/H2/H3/H4)。

## 7. 相关文档

- `references/phase-1.8-frame-crop.md` — Phase 1.8 完整步骤文档(步骤 1-15)
- `scripts/_stage1_score.py` — Stage 1 LLM 评分
- `scripts/_stage2_decide.py` — Stage 2 逐帧决策
- `scripts/_crop_insert_frames.py` — Stage 3 PIL 裁剪 + Markdown 注入
- `scripts/_llm_vision.py` — 通用 LLM 调用封装

## 8. 反模式(不要做)

- ❌ **不要默认插入截图**:用户没说就默认跑 Phase 1.8 → 浪费 LLM API 配额(Stage 1 + 8 次 Stage 2 = 9 次调用)
- ❌ **不要把 AskUserQuestion 卡片用在关键词已明确的情境(浪费交互)**:用户说"加图"还问"是否加图"是反模式
- ❌ **不要在 Phase 2 合并之后再问**:Phase 1.8 必须 Phase 1.7 → Phase 2 之间,否则 H3 编号可能不稳
- ❌ **不要跳过 AskUserQuestion 直接假设"用户要图"**:用户没明确表态 → 应该问,而不是猜测
- ❌ **不要让用户在卡片里调参数**:卡片只 2 选项(跑/不跑),参数硬编码简化决策

## 9. 已知陷阱

| 陷阱 | 现象 | 解决 |
|---|---|---|
| 用户消息只说"原帧" | "原帧" 是 Phase 1.8 特有词,但其它上下文也可能用 | 检查完整句意,主谓宾是"插入/添加"才触发 |
| API key 未 export | -L → LLM 优雅失败,跳过 Phase 1.8 | 脚本已设计,Phase 3 仍能渲染 |
| 用户在 Phase 2 合并后改主意"要加图" | 已合并的 md 重做 Phase 1.8 复杂 | 重置流程:从 Phase 1.8 开始重做,清理合并产物 |
| LLM 返回 score 全 < 0.65 | top8.json 为空 | 跳过 Phase 1.8,Phase 3 用原 cleaned.md |

## 10. 版本演进

- **v4.19 (2026-09-29)**: 首版,边界 2026-06-03 项目第二轮迭代沉淀
- **未来 v4.20+**: 可选扩展 — 9-16 张上限(大型讲座)/ 自定义 caption 模板 / 用户在卡片里调 8/16 张上限