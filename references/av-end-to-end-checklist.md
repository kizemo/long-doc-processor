# av-end-to-end-checklist.md · 音视频端到端流程清单

> **版本**:v4.20(2026-09-30 边界 2026-06-03 项目沉淀)
> **触发**:加载 long-doc-processor 后,处理 mp3 / mp4 / 视频讲座任务必读
> **配套**:`scripts/transcribe_via_crv.py` / `scripts/asr_faster_whisper.py` /
> `scripts/_purify_smooth.py` / `scripts/verify_html.py`
> **核心原则**:任何 ASR / 净化 / 截图 / 渲染动作前,**先做完 4 步首问**。

---

## 0 · 全流程总览

```
Step 0   · ASR 模型选择 + 时长预估(必做)
Step 0.5 · 输出目录命名(必做)
Step 0.6 · 输出文件名(必做)
Step 0.7 · 是否插入截图 Phase 1.8(必做)
   │
   ├─ Phase 0:音视频输入准备
   ├─ Phase 1:单文档净化(1.0 D0 段级 / 1.1 chunk 切 / 1.4 LLM 净化 / 1.5 平滑 / 1.7 LLM 语义优化 / 1.8 截图)
   ├─ Phase 2:多文档合并
   ├─ Phase 3:渲染 HTML
   ├─ verify_all.py(30 条规约)
   ├─ regression_test.py
   └─ 全部 PASS → 产物回写源目录
```

---

## Step 0 · ASR 模型选择 + 时长预估

### 0.1 模型选项(5 选 1)

| 模型 | 精度 | 速度(3090 GPU) | 适用 |
|---|---|---|---|
| `large-v3` | ★★★★★ | 4× realtime | 100+ 分钟长讲座,必须最高质量 |
| `large-v3-turbo` | ★★★★ | 7.8× realtime | **默认推荐**,速度 + 质量兼顾 |
| `medium` | ★★★ | ~10× | 短讲座(30 min 内) |
| `small` | ★★ | ~15× | 草稿,后续需重跑 |
| `base` | ★ | ~20× | 仅测试用途 |

### 0.2 时长预估表

| 时长 | large-v3 | large-v3-turbo | medium | small | base |
|---|---|---|---|---|---|
| 30 min | ~7.5 min | ~4 min | ~3 min | ~2 min | ~1.5 min |
| 60 min | ~15 min | ~7.8 min | ~6 min | ~4 min | ~3 min |
| 90 min | ~22 min | ~12 min | ~9 min | ~6 min | ~4.5 min |
| 120 min | ~30 min | ~15 min | ~12 min | ~8 min | ~6 min |
| 180 min | ~45 min | ~23 min | ~18 min | ~12 min | ~9 min |

### 0.3 必问用户

```text
Q: 请选择 ASR 模型 + 视频/音频时长
选项:
  A. turbo GPU(默认推荐) + 60 min
  B. large-v3 GPU + 120 min
  C. base CPU + 30 min
  D. 自定义(用户填)
```

**违反这步的后果**:默认选高精度浪费数小时 / 选低质浪费精力。

---

## Step 0.5 · 输出目录与中间目录（必做）

### 0.5.1 三个选项(3 选 1)

| 选项 | 交付目录 `OUT` | 说明 |
|---|---|---|
| ① 同目录 | `AV_DIR`(音视频所在目录本身) | 交付物直接躺在音视频旁边;单门课时最省事 |
| ② 同名子目录(默认) | `AV_DIR/<第一个音视频文件名>` | 与第一集同名;多门课共用一层时不互相污染 |
| ③ output 子目录 | `AV_DIR/output/` | 传统 `output/` 布局,兼容旧习惯 |

- `AV_DIR` = 第一个音视频所在目录(**不是** CWD,**不是** skill 安装目录)
- 三选一必问;即使用户说"和上次一样"也要重问(目录名可能已变)
- 交付目录只放交付物:`<OUTPUT_STEM>_cleaned.md` / `<OUTPUT_STEM>_final.html` / `img/`

### 0.5.2 中间目录 `TMP`(固定，无选项)

**所有中间文件与脚本一律放 `AV_DIR/tmp/`，不随上面三选项变化**:

| 内容 | 落到 |
|---|---|
| `*_transcript_raw.md` / `*_transcript.md` / `*_skeleton.md` / `*_terms_report.json` | `AV_DIR/tmp/` |
| `parts/` / `crv-out-*` / `audio.*` / `frames/` / `grids/` | `AV_DIR/tmp/` |
| `asr_corrections.yaml`(项目级错词表) | `AV_DIR/tmp/` |
| 一次性脚本 / 补丁 / 审计报告 / 分组计划 `*.json` | `AV_DIR/tmp/` |

理由：中间产物数量通常是交付物的 10 倍以上，混进交付目录会让用户分不清哪些是要的文件；
固定 `AV_DIR/tmp/` 也让"换机器接着跑"只需认一个目录。

### 0.5.3 命名规则

- 选项 ② 的子目录名 = 第一个音视频文件名(去扩展名):`01.第一天上午.mp3` → `AV_DIR/01.第一天上午/`
- 选项 ① / ③ 不产生子目录名,`OUTPUT_STEM` 独立确认(见 Step 0.6)
- 例:用户口头把 ② 命名成 `test-crv2` → `AV_DIR/test-crv2/`

---
## Step 0.6 · 输出文件名(OUTPUT_STEM)

### 0.6.1 INPUT_STEM vs OUTPUT_STEM

| 变量 | 含义 | 默认 |
|---|---|---|
| INPUT_STEM | 音视频文件名(去扩展名) | `原始课程` |
| OUTPUT_STEM | 最终产物文件名 stem | = INPUT_STEM(选项②时即子目录名;选项①③单独确认) |

### 0.6.2 产物文件命名

| 文件 | 命名 | 说明 |
|---|---|---|
| 最终 HTML | `<OUTPUT_STEM>_final.html` | ⭐ 主交付物 |
| 净化主产物 | `<OUTPUT_STEM>_cleaned.md` | Phase 3 输入 |
| 转录中间产物 | `<OUTPUT_STEM>_transcript_raw.md` | ASR 时间戳稿 |
| 转录净化 | `<OUTPUT_STEM>_transcript.md` | 术语校验后 |
| 骨架 | `<OUTPUT_STEM>_skeleton.md` | H2 锚点 |
| 末段修复 | `<OUTPUT_STEM>_last_quarter.md` | 末段独立产物 |

### 0.6.3 违规检测

```bash
# 检查命名一致性
python scripts/check_no_markdown_corruption.py output/<stem>_cleaned.md
```

---

## Step 0.7 · 是否插入截图(Phase 1.8)

### 0.7.1 触发关键词(15 个,中英文)

#### 中文
插入截图 / 插图 / 配图 / 加图 / 加点图 / 加一些截图 / 原帧 / 关键帧裁剪 / 截图注入 / H3 加图

#### 英文
crop / crop frame / Phase 1.8 / frame crop / keyframe crop / insert image

### 0.7.2 不触发的语义(避免误判)

- "配图"如果上下文是"讲解 AI 配图工具"→ 不触发
- "截图"如果上下文是"截图给我看 bug"→ 不触发

### 0.7.3 AskUserQuestion 卡片(3 选项)

```python
AskUserQuestion(questions=[{
    "question": "本次任务是否需要在 cleaned.md 插入截图(Phase 1.8)?",
    "header": "插入截图",
    "options": [
        {
            "label": "跑 Phase 1.8 (8 张硬上限 + 200KB/张)",
            "description": "LLM 评分筛选 Top-8 → 逐帧决策 → PIL 裁剪注入"
        },
        {
            "label": "跳过,直接渲染 HTML",
            "description": "纯文字讲座或用户主动要求无图"
        },
        {
            "label": "Path G 排版补救 (v4.20 新增)",
            "description": "用 typography 替代截图:加粗 inline / 表格 / SVG inline / 多行 blockquote"
        }
    ]
}])
```

### 0.7.4 Phase 1.8 默认参数

| 参数 | 默认 | 来源 |
|---|---|---|
| 8 张硬上限 | 8 | spec §2.2 |
| 单图大小 | ≤ 200KB | spec §6 错误处理 + qa-gates 规则 36 |
| 单图尺寸 | ≤ 800x600 | spec §3 Stage 3 |
| score 阈值 | ≥ 0.65 | spec §4.1 |
| crop_box padding | 5% 内缩 | spec §4.3 |
| 注入位置 | H3 段首下一行 | spec §4.3 |
| LLM 模型 | claude-sonnet-4-5 | scripts/_llm_vision.py 默认 |

---

## Step 1 · ASR 调用

### 1.1 v4.4 起主路径:`claude-real-video`

```bash
python scripts/transcribe_via_crv.py \
  --input <audio_or_video> \
  --output <transcript.md> \
  --model turbo \
  --lang zh
```

### 1.2 兜底路径:`faster-whisper`

(仅当 claude-real-video 不可用时)

```bash
python scripts/asr_faster_whisper.py \
  --input <audio.mp3> \
  --output <transcript.md> \
  --model large-v3-turbo
```

### 1.3 强制约束

**Step 2.0 合并前语义检查必跑**(`scripts/_pre_merge_semantic_check.py`,v4.15):
- H3 编号跳号检测 + 自动修复
- ASR 错词高发词检测 + 字典替换
- 人称角色残留检测 + 字典替换
- chunk 收束句检测(报告,人工 review)

---

## Step 2 · 切块 + 净化

### 2.1 D0 段级语义净化(B1 之后)

```bash
python scripts/semantic_block_fix.py
```

### 2.2 chunk 切分

按 15000-20000 字符/块,段落边界分割,输出 `part{N}_raw.txt`。

### 2.3 LLM 净化

```bash
python scripts/purify_v4_4_hierarchical.py \
  <input.md> -o <output.md> \
  --n-chunks 8 --workers 3
```

### 2.4 通顺化重写

```bash
python scripts/_purify_smooth.py \
  <cleaned.md> -o <smoothed.md> --workers 3
```

### 2.5 ASR 错词修复

```bash
python scripts/_post_terms_fix.py \
  <cleaned.md> <cleaned_post.md>
```

### 2.6 末段独立修复

```bash
python scripts/last_section_reprocess.py \
  <cleaned.md> -o <last_quarter.md>
```

---

## Step 3 · LLM 语义优化(Phase 1.7)

```bash
# 通过 Claude 子代理调用
# prompt 见 references/phase-1.7-semantic-pass.md
# 输出 <stem>_cleaned.semantic.md,覆盖到 <stem>_cleaned.md
```

**6 条硬规约(v4.18)**:
1. NO-DOC-META-BLOCKQUOTE
2. NO-ROLE-PERSONA-EXTENDED
3. HIERARCHICAL-NUMBERING
4. NO-ORPHAN-WORDS
5. NO-META-LECTURE-PREAMBLE-IN-SECTION
6. NO-SINGLE-LINE-BLOCKQUOTE-CALLOUT

---

## Step 4 · 合并 + 渲染

### 4.1 多文档合并

```bash
python scripts/merge_documents.py \
  --inputs <md1> <md2> ... \
  --output <merged.md>
```

### 4.2 总结与行动建议章节强制

合并后**必加** `## N 总结与行动建议` H2(N = 当前 H2 + 1):
- N.1 全文要点回顾(bullet list)
- N.2 可执行行动清单(表格)
- N.3 决策流程图(`因为 ... 所以 ...` 逻辑链)

### 4.3 HTML 渲染

```bash
python scripts/markdown_to_html.py \
  <cleaned.md> <final.html>
```

---

## Step 5 · 验证(必跑)

### 5.1 全量验证

```bash
python scripts/verify_all.py \
  <cleaned.md> \
  --raw-md <transcript.md> \
  --html <final.html>
```

### 5.2 HTML 验证

```bash
python scripts/verify_html.py <final.html>
```

### 5.3 历史回归

```bash
python scripts/regression_test.py
```

### 5.4 章节统计

```bash
python scripts/per_section_stats.py <cleaned.md> --raw-md <transcript.md>
```

---

## 时间预算

| 阶段 | 60 min 讲座 | 120 min 讲座 |
|---|---|---|
| Step 0 首问 | 1 min | 1 min |
| Step 1 ASR | 8 min | 15 min |
| Step 2 净化 | 15 min | 25 min |
| Step 3 语义优化 | 10 min | 15 min |
| Step 4 合并 + 渲染 | 5 min | 8 min |
| Step 5 验证 | 5 min | 8 min |
| **合计** | **44 min** | **72 min** |

---

## 反模式(不要做)

| ❌ 反模式 | ✅ 正确做法 |
|---|---|
| 默认选 ASR 模型 | 走 Step 0 必做首问 |
| 跳过 Step 0.5 | 用户后悔已跑一半 |
| 跳过 Step 0.6 | 输出 md/html 与子目录名不一致 |
| 跳过 Step 0.7 | 默认不插图,用户期望缺失 |
| 用 `python <script> --help` 探查 CLI | 改用 `Read` 工具读 argparse 段 |
| 跨会话复用 `crv-out-*` 目录 | claude-real-video 自动升级 whisper,缓存漂移 |
| 把 `<stem>_cleaned.md` 仅放 lecture 根目录 | 强制 `output/<stem>_cleaned.md` |
| 让用户在卡片里调 Phase 1.8 参数 | 卡片只 2 选项,参数硬编码 |

---

## 历史项目沉淀

| 项目 | 日期 | 时长 | 模型 | Phase 1.8 | 总结 |
|---|---|---|---|---|---|
| 蒋太帅 | 2026-05-29 | 60 min | turbo | 否 | v3.6 起点,需 renumber |
| 智篆 | 2026-09-17 | 90 min | turbo | 否 | v4.16 起点,5 大类错词 |
| 边界 2026-06-03 | 2026-09-29 | 60 min | large-v3 | 是 | v4.18 6 条硬规约 |
| 老草 | 2026-08-02 | 120 min | large-v3 | 否 | v4.7 三层防线 L1/L2/L3 |

---

## 相关 reference

- `phase-0-input.md` · 输入预处理
- `phase-1-purification.md` · 单文档净化
- `phase-1.7-semantic-pass.md` · LLM 语义优化
- `phase-1.8-decision.md` · 截图首问判定
- `phase-2-merge.md` · 多文档合并
- `phase-3-render-html.md` · 渲染 HTML
- `qa-gates.md` · 验收规约
- `规约清单.md` · 30 条规约单一真相源

---

<!-- Generated: 2026-10-12, source: SKILL.md v4.20 必做首问 + Step 0/0.5/0.6/0.7 -->
