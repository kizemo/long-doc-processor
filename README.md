# long-doc-processor

> **v4.22** · Claude Code Skill · 长文档(讲座/课程/录音/多份 .docx) → 净化 → 合并 → HTML 交付

[![GitHub](https://img.shields.io/badge/GitHub-kizemo%2Flong--doc--processor-blue?logo=github)](https://github.com/kizemo/long-doc-processor)
[![Version](https://img.shields.io/badge/version-v4.22-green)]()
[![Tests](https://img.shields.io/badge/tests-531%20passed-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()
[![CI](https://img.shields.io/badge/CI-passing-brightgreen?logo=github-actions)](.github/workflows/ci.yml)

**作者**: Duanyi · **位置**: `F:/soft/00selfmade/long-doc-processor/`(开发) / `~/.claude/skills/long-doc-processor/`(runtime)

---

## 📖 项目介绍

**long-doc-processor** 是一个 Claude Code Skill,把"音视频 / 多份文档 / XMind"等异构输入,转成"可独立打开的 HTML 讲义"。核心方法:

- **每条规则都**可机检** — 30 条规约 → `verify_all.py`(输入)+ `verify_html.py`(输出)双重校验
- **LLM 调用容错** — 7 种 status 分流(ok / empty / error / timeout / rate_limited / no_api_key / no_sdk),默认 fail-soft + `--strict` 切 fail-loud
- **跨项目踩坑沉淀** — 13 条 M-XX 模式(基于 14 份 F:/resourse_study/ 历史 handoff)

### 项目目标

| 输入 | 处理 | 输出 |
|---|---|---|
| 课程讲义 (PDF/PPT) | 文字提取 + 净化 + 结构化 | Markdown 笔记 |
| 讲座视频 (mp4/m4a) | ASR 转录 + 章节切分 + 净化 | Markdown + HTML |
| 多份 .docx | 合并 + 标题降级 + 规约校验 | Word / HTML 讲义 |
| 多份 .md | 跨文档合并 + 编号统一 | 合并后 Markdown + HTML |
| XMind 大纲 | XML 解析 + 层级重构 | Markdown 大纲 |
| OCR 配图 | RapidOCR + LLM 视觉理解 | 关键帧 + 说明 |

---

## 🎯 快速开始(5 分钟)

### 安装

```bash
# 1. 克隆仓库
git clone https://github.com/kizemo/long-doc-processor.git
cd long-doc-processor

# 2. 安装 Python 依赖
# (Python 3.12+,系统包)
pip install pytest

# 3. (可选)安装 LLM SDK(only needed for real LLM calls)
pip install anthropic

# 4. 验证安装(531 tests,无 API key 也可跑)
python -m pytest tests/ -v
# 期望: 531 passed, 6 warnings in ~17s

# 5. (可选)同步到 Claude Code skill 目录
# Windows:
cp -r scripts/ references/ SKILL.md ~/.claude/skills/long-doc-processor/
```

### 5 分钟体验(无 LLM)

```bash
# 1. 试跑 — 步骤 1(转录)用 dry-run mock,无需音视频
python scripts/run_pipeline.py input.mp4 --stem demo --init
python scripts/run_pipeline.py input.mp4 --stem demo --dry-run

# 2. 跑规约校验(用任一现成 .md)
python scripts/verify_all.py references/规约清单.md

# 3. 自检必做 4 步(合规样本)
python scripts/enforce_post_merge_4steps.py references/规约清单.md

# 4. D0 段级净化(用 LLM mock)
echo "# 培训讲义
## 1. 一章
嗯,今天讲电钻案例。
" > /tmp/test.md
python scripts/semantic_block_fix.py /tmp/test.md -o /tmp/out.md
```

### 真实使用(有 API key + 音视频)

```bash
# 完整流水线(4 步首问必做,见 SKILL.md)
python scripts/run_pipeline.py 讲义.mp4 --stem 讲义标题

# 分步细调(每步可单独跑)
python scripts/transcribe_via_crv.py --input 讲义.mp4 --output transcript_raw.md
python scripts/_post_terms_fix.py transcript_raw.md transcript_fixed.md
python scripts/purify_v4_4_hierarchical.py transcript_fixed.md -o cleaned.md
python scripts/_purify_smooth.py cleaned.md -o smoothed.md --verbose
python scripts/strip_lecturer_preamble.py smoothed.md -o stripped1.md
python scripts/strip_role_persona.py stripped1.md -o stripped2.md
python scripts/last_section_reprocess.py stripped2.md -o final.md
python scripts/verify_all.py final.md
python scripts/markdown_to_html.py final.md final.html
python scripts/verify_html.py final.html
```

更多详细用法见 [`SKILL.md`](SKILL.md)。

---

## 🏗️ 架构

```
┌──────────────────────────────────────────────────────────────┐
│                  long-doc-processor v4.22                      │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  Input  →  Preflight  →  Run Pipeline  →  Verify  →  Output   │
│  (.mp4)   (4 步首问)   (10 phase 串行)   (21 规则)  (.html)  │
│  (.m4a)        │              │              │              │
│  (.docx)       │              │              │              │
│  (.md)         ▼              ▼              ▼              │
│         preflight_      run_pipeline    verify_all          │
│         check.py         .py            .py                  │
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ 核心模块:                                              │    │
│  │  • _llm_vision.py: safe_llm_call (7 status)          │    │
│  │  • chunking.py: H2/H3 切分公共入口(C2 统一)            │    │
│  │  • utils.py: 15+ 工具(log 线程安全 / time_budget /  │    │
│  │              make_standard_parser / atomic_write)       │    │
│  │  • verify_all.py: 21 规约 RULES 注册                  │    │
│  │  • check_no_md_corruption.py: 44 污染词(B2)          │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ Cross-cutting:                                          │    │
│  │  • asr_corrections.yaml: 41 条 ASR 错词              │    │
│  │  • 规约清单.md: 30 条规约单一真相源                  │    │
│  │  • 跨项目踩坑 13 M-XX(资源研究报告)                  │    │
│  │  • CI: .github/workflows/ci.yml (3 OS matrix)         │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                │
└──────────────────────────────────────────────────────────────┘
```

### 完整流水线(Run Pipeline)

**10 个 phase**(state 持久化 + 幂等性):

| Phase | 脚本 | 状态 |
|---|---|---|
| `phase_0_asr` | `transcribe_via_crv.py` | dry-run 完整;真实 stub |
| `phase_1_0_d0` | `semantic_block_fix.py` | dry-run 完整 |
| `phase_1_1_chunk` | (chunking.py 内部) | dry-run 完整 |
| `phase_1_4_purify` | `purify_v4_4_hierarchical.py` | dry-run 完整;`--strict` fail-loud |
| `phase_1_5_post_terms` | `_post_terms_fix.py` | dry-run 完整 |
| `phase_1_7_semantic` | `phase_orchestrator.py --phase 1.7` | dry-run 完整 |
| `phase_1_8_crop` | `_crop_insert_frames.py` | dry-run mock 复制 |
| `phase_2_merge` | (合并脚本) | TODO |
| `phase_3_render` | `markdown_to_html.py` | dry-run 完整 |
| `verify_all` | `verify_all.py` | dry-run PASS |

**幂等性**:`--resume` 跳过 `pipeline_state.json` 中已 done 的 phase。

---

## 📁 项目结构

```
long-doc-processor/
├── SKILL.md                            # v4.22 主文档(必读,~2K 行,含 30 规约详细)
├── README.md                           # 本文件
├── .gitignore                          # 排除 .pytest_cache / 子项目等
├── .github/workflows/ci.yml            # 3 OS 跨平台 CI(E4 沉淀)
│
├── optimization-plan-v2-2026-10-13.md # A+B 详细任务(v4.21 优化方案)
├── references/SIMPLIFY_REVIEW_v4.21.md # E5 simplify review 总览
│
├── handoff-2026-10-13-phase-a.md       # 阶段 A 输入 handoff
├── handoff-2026-10-14-a-done.md        # 阶段 A 完成 handoff
├── handoff-2026-10-15-b-done.md        # 阶段 B 完成 handoff
├── handoff-2026-10-16-c-done.md        # 阶段 C 完成 handoff
├── handoff-2026-10-17-d-done.md        # 阶段 D 完成 handoff
├── handoff-2026-10-18-e-done.md        # v4.21 全部完成总览
│
├── scripts/                            # 41 个 .py(可执行核心)
│   ├── _llm_vision.py                 # LLM 调用底层(safe_llm_call)
│   ├── chunking.py                    # H2/H3 切分公共入口(E3 统一)
│   ├── utils.py                       # 15+ 工具(log/format/IO/argparse)
│   │
│   ├── transcribe_via_crv.py          # crv-audio 包装(A5 timeout 修复)
│   ├── purify_v4_4_hierarchical.py    # 8 chunk + LLM 净化(A4 MAX_CHARS)
│   ├── _purify_smooth.py              # 通顺化重写(C1 收紧)
│   ├── semantic_block_fix.py         # D0 段级净化(D3)
│   ├── enforce_post_merge_4steps.py  # v4.9.1 4 步固化(D4)
│   ├── phase_orchestrator.py         # Phase 1.7/1.8 串行(D5)
│   ├── strip_lecturer_preamble.py    # 讲师铺垫清理(A1 safe_llm_call)
│   ├── strip_role_persona.py         # 角色润色(A1 safe_llm_call)
│   ├── last_section_reprocess.py     # 末段精炼(A1 safe_llm_call)
│   ├── _post_terms_fix.py             # ASR 错词 YAML 驱动替换
│   ├── extract_skeleton.py            # 骨架提取
│   ├── extract_terms.py               # 术语提取
│   ├── post_pass_terms.py             # 后处理术语
│   ├── asr_quality_check.py           # ASR 质量
│   ├── asr_faster_whisper.py          # 备用 ASR(fallback)
│   │
│   ├── verify_all.py                  # 21 规约校验(v4.21 B1 扩)
│   ├── verify_html.py                 # HTML 规约校验
│   ├── verify_docx.py                 # DOCX 规约校验
│   ├── check_no_markdown_corruption.py # 44 污染词检测(B2)
│   │
│   ├── markdown_to_html.py            # Phase 3 渲染
│   ├── markdown_to_docx.py            # Word 输出
│   ├── doc_to_md.py                   # DOCX → MD
│   ├── xmind_to_md.py                 # XMind → MD
│   ├── ocr_images.py                  # OCR 配图
│   ├── generate_image.py              # 图像生成
│   │
│   ├── preflight_check.py             # 4 步首问钩子(D2)
│   ├── run_pipeline.py                # 一键入口(D1 核心)
│   │
│   ├── regression_test.py             # 历史案例回归
│   ├── asr_quality_check.py           # ASR 质量
│   ├── per_section_stats.py           # 章节统计
│   ├── strip_asr_terms.py             # 错词剥离
│   ├── strip_nested_numbering.py      # 嵌套编号清理
│   ├── _pre_merge_semantic_check.py   # 合并前语义检查
│   ├── _crop_insert_frames.py         # 关键帧裁剪(Phase 1.8)
│   ├── _stage1_score.py               # 关键帧评分
│   ├── _stage2_decide.py              # 关键帧决策
│   ├── _post_simplify_chapter.py      # 单章深度精炼(v4.18+)
│   ├── _post_add_summary.py           # 自动加总结章节(v4.18+)
│   ├── _pipeline_all.py               # 旧版流水线
│   ├── _wait_and_finalize.py          # 旧版 watcher
│   ├── glossary_expand.py             # 术语表反向扩展
│   ├── fix_bad_extract_terms.py       # 错词修复
│   ├── fix_bad_extract_terms_inline.py # 内联错词修复
│   ├── build_per_lecture_asr_corrections.py  # 单讲义 ASR 错词构建
│   ├── safe_replacements_2.json       # 兜底替换(2 字符)
│   ├── renumber_headings.py           # 标题重编号
│   ├── ocr_images.py                  # OCR
│   ├── validate_skill.py              # skill 校验
│
├── references/                         # 20+ 知识库
│   ├── 规约清单.md                     # 30 条规约单一真相源
│   ├── av-end-to-end-checklist.md     # 13 步端到端流程
│   ├── asr_corrections.yaml           # 41 条 ASR 错词
│   ├── content-rules.md               # 5 类实质内容
│   ├── anti-patterns.md               # 段级自检
│   ├── writing-quality.md             # 写作质量
│   ├── batch-processing.md            # 批处理
│   ├── gotchas.md                     # 高优先级反模式
│   ├── image-pipeline.md              # 图像处理
│   ├── image-style.md                 # 图像风格
│   ├── maintenance.md                 # 维护
│   ├── ooxml-numbering.md             # Word 编号
│   ├── path-g-typography-fallback.md # 排版补救
│   ├── phase-0-input.md               # 输入准备
│   ├── phase-1-purification.md        # 净化
│   ├── phase-1.7-semantic-pass.md     # 语义优化
│   ├── phase-1.8-decision.md          # 关键帧决策
│   ├── phase-1.8-frame-crop.md        # 关键帧裁剪
│   ├── phase-2-merge.md               # 合并
│   ├── phase-3-render-html.md         # HTML 渲染
│   ├── purification-prompt.md         # 净化 prompt
│   ├── qa-gates.md                    # 质量门
│   ├── runtime-compatibility.md       # 运行时兼容
│
├── tests/                              # 24 个 test_*.py(531 tests)
│   ├── test_safe_llm_call.py          # A1: 18 tests
│   ├── test_utils_concurrent.py       # A2: 3 tests
│   ├── test_strip_chunking.py         # A3: 10 tests
│   ├── test_purify_max_chars.py       # A4: 8 tests
│   ├── test_transcribe_timeout.py     # A5: 7 tests
│   ├── test_verify_all_b1.py          # B1: 30 tests
│   ├── test_check_no_markdown_corruption_extended.py # B2: 14 tests
│   ├── test_smooth_prompt_tightening.py # C1: 7 tests
│   ├── test_chunking_unified.py       # C2: 9 tests
│   ├── test_verify_purify_fail_loud.py # C3: 5 tests
│   ├── test_verbose_status.py         # C4: 8 tests
│   ├── test_time_budget.py            # D7: 9 tests
│   ├── test_preflight_check.py        # D2: 13 tests
│   ├── test_run_pipeline.py           # D1: 13 tests
│   ├── test_semantic_block_fix.py     # D3: 14 tests
│   ├── test_enforce_post_merge_4steps.py # D4: 8 tests
│   ├── test_phase_orchestrator.py     # D5: 7 tests
│   ├── test_pipeline_idempotency.py   # D6: 11 tests
│   ├── test_utils_extended.py         # E1: 24 tests(v4.22 删 2 dead code tests)
│   ├── test_argparse_boilerplate.py   # E2: 10 tests
│   ├── test_heading_regex_unified.py  # E3: 11 tests
│   ├── test_ci_yaml.py                # E4: 6 tests
│   ├── test_simplify_review.py        # E5: 6 tests
│   └── test_*.py(其他 v4.20 原测试)   # 254 tests
│
├── tests/regression_cases/             # 回归测试用例(.json)
│
└── history/v3.8-optimized/             # 优化版完整备份
    ├── SKILL.md.v3.8.bak              # v3.8 完整 SKILL
    ├── lessons.md                      # 25+ 条使用教训
    ├── resource-study-report-2026-10-13.md  # 14 份 handoff 踩坑扫描
    ├── evals/                          # 静态校验
    ├── references/                     # v3.8 references 备份
    └── scripts/                        # v3.8 scripts 备份
```

---

## ✨ 核心特性

### 1. 30 条规约强校验(可机检)

**文档级**(`verify_all.py` 21 条):

| 编号 | 规约 | 版本 |
|---|---|---|
| 01 | NO-DOC-META-HEADER | v4.10 |
| 02 | NO-DOC-META-BLOCKQUOTE | v4.17 |
| 03 | NO-LECTURER-PREAMBLE | v4.4 |
| 04 | NO-ROLE-PERSONA | v4.10 |
| 05 | NO-ROLE-PERSONA-EXTENDED | v4.17 |
| 06 | HIERARCHICAL-NUMBERING | v4.17 |
| 07 | H3-LECTURER-BIO | v4.9 |
| 08 | NO-SINGLE-SUBHEADING | v4.9 |
| 09 | TRAINING-AD-CHAPTER | v4.9.1 |
| 10 | CHAPTER-1-SUBSTANTIVE | v4.14 |
| 14 | NO-NESTED-NUMBERING | v4.4 |
| 15 | H4-PER-H3-MAX (≤3/H3) | v4.4 |
| 16 | H4-TOTAL-MAX (≤50) | v4.4 |
| 18 | NO-ORPHAN-H3 | v4.4 |
| 19 | LAST-SECTION-COMPLETE | v4.4 |
| 20 | H3-NAMING-CONSISTENT | v4.4 |
| 21 | LOGIC-CHAIN | v4.4 |
| 22 | ASR-PRESENCE | v4.4 |
| 23 | ASR-LANG (zh 默认) | v4.4 |
| 26 | NO-ORPHAN-WORDS | v4.17 |
| 30 | 总结与行动建议章节 | v4.9.1 |

**v4.21 新增 8 条**(B1):
- NO-ROLE-PERSONA-EXTENDED(表格单元格扫描,M-07)
- HIERARCHICAL-NUMBERING(正则与 SKILL 严格对齐,M-05)
- NO-SINGLE-LINE-BLOCKQUOTE-CALLOUT(整篇 normalize,M-06)
- H3-LECTURER-BIO-EXTENDED(9 类黑名单)
- TRAINING-AD-CHAPTER-EXTENDED(4 类关键词)
- IMG-SIZE-WITHIN-LIMIT(PIL ≤200KB + ≤800x600)
- NO-PATH-TRAVERSAL(img src 不含 `..`)
- NO-DOC-META-HEADER-BLOCKQUOTE(H1 后紧跟 blockquote)

**HTML 级**(`verify_html.py` 6 条):q-17 解析 / q-18 title / q-19 img 存在 / q-20 alt / q-21 img 目录 / q-22 H1 数

### 2. LLM 失败优雅降级(`safe_llm_call` 装饰器)

```python
from _llm_vision import safe_llm_call
text, status = safe_llm_call(prompt, model="claude-sonnet-4-5")
# status ∈ {ok, empty, timeout, error, rate_limited, no_api_key, no_sdk}
```

- **3 次重试 + 指数 backoff**(M-02)
- **rate_limited 单独分流**(`429` 检测,wait `backoff * 2^attempt`,上限 60s)
- **minimal_prompt 兜底**(M-02:`empty` 时 1 次重试用 minimal_prompt)
- **fail-soft 默认** + `--strict` flag 切 fail-loud

### 3. 跨项目踩坑模式沉淀(13 M-XX)

| 模式 | 描述 | 沉淀 |
|---|---|---|
| M-01 | `_wait_and_finalize.py:32` SKILL_DIR 路径 bug | safe_llm_call / run_pipeline 路径校验 |
| M-02 | LLM 500/1026 错误 | safe_llm_call 7 status 分流 |
| M-03 | crv-audio 输出路径与 watcher 错位 | transcribe_via_crv `Path.resolve()` |
| M-04 | `_pipeline_all.py` f-string escape + GBK | configure_stdout_utf8 + log 线程安全 |
| M-05 | NUMBERING-DOTTED 命名误导 | verify_hierarchical_numbering 正则严格对齐 |
| M-06 | FULLWIDTH-PUNCT 跨行 | verify_NO_SINGLE_LINE_BLOCKQUOTE_CALLOUT 整篇 normalize |
| M-07 | "学员" 表格也 FAIL | verify_no_role_persona_extended 表格单元格扫描 |
| M-08 | 末章 5 类资产齐全 | (留 v4.22+) |
| M-09 | PARAGRAPH-LENGTH 图/表段 | (留 v4.22+) |
| M-10 | simplify 45-55% 正确区间 | (留 v4.22+) |
| M-11 | CJK 60% 是数字术语 | verify_ASR_LANG 改 WARN(v4.22+) |
| M-12 | crv-audio 绝对路径 | run_pipeline + transcribe_via_crv 入口 resolve |
| M-13 | scenedetect 直播录屏太慢 | SKILL.md gotcha + ffmpeg 抽帧 |

详见 [`history/v3.8-optimized/resource-study-report-2026-10-13.md`](history/v3.8-optimized/resource-study-report-2026-10-13.md)。

### 4. 端到端流水线(10 phase)

```bash
python scripts/run_pipeline.py input.mp4 --stem 讲义标题
# 内部:preflight → phase_0_asr → phase_1_0_d0 → ... → phase_3_render → verify_all
# 状态: pipeline_state.json(幂等性, --resume 跳过 done)
```

---

## 📊 当前状态(2026-10-18,v4.22 final)

| 项 | 数值 |
|---|---|
| **版本** | v4.22(commit `5d68101`) |
| scripts | 41 个 (.py) |
| references | 21 个 (.md + .yaml) |
| tests | 24 个 test_*.py,**531 tests PASSED** |
| SKILL.md | v4.22,~600+ 行(30 规约 + 4 阶段 + 5 阶段优化) |
| 规约覆盖 | verify_all **21**/30 + verify_html 6/6 |
| 跨项目 handoff | 14 份已扫描,**13 条踩坑模式**已沉淀 |
| CI | ✅ 3 OS matrix (ubuntu/macos/windows, Python 3.12) |
| GitHub | https://github.com/kizemo/long-doc-processor |
| 6 commits pushed | e1218f0 → 6ed4d26 → a95fce2 → 31a4a10 → 48b3297 → 6a80b6a → 5d68101 |

### 5 阶段优化完成(24 子任务)

| 阶段 | 子任务数 | commit | 测试增量 |
|---|---|---|---|
| **A** 稳定性(必做 3 + 推荐 3) | 6/6 | 6ed4d26 | +46 |
| **B** 规约闭环(必做 1 + 推荐 1) | 2/2 | a95fce2 | +44 |
| **C** 输出质量 | 4/4 | 31a4a10 | +29 |
| **D** 一键入口 | 7/7 | 48b3297 | +75 |
| **E** 可维护性 | 5/5 | 6a80b6a | +55 |
| **v4.22** 全面体检 | 7 fixes | 5d68101 | -6 dead code |
| **合计** | **31** | - | **+243** (227→531) |

### v4.22 全面体检 7 修复

| # | 问题 | 严重度 | 修复 |
|---|---|---|---|
| F1 | 8 脚本重复定义 heading 正则 | 高(DRY) | ✅ 全 import 自 chunking |
| F2 | verify_all 21+4 次重复 IO | 中(性能) | ✅ monkey-patch cache,21+4→1 次 |
| F3 | LLM 双层 retry(3×3=9 次) | 高(实际 bug) | ✅ safe_llm_call(max_retries=1) |
| F4 | E2 boilerplate 未落地 | 中(dead code) | ✅ 5 LLM 脚本全迁移 |
| F5 | safe_rename/parse_table_row 0 调用 | 低(dead code) | ✅ 删除 + verify_all 用 find_files_by_ext |
| F6 | enforce_post_merge 验证逻辑错 | 中(rc==0 ≠ 5 类资产齐) | ✅ 直接抽末段 + 数 H3 + 5 类资产 |
| F7 | stub 异常未区分 | 中 | ✅ PipelineStubError 类(exit 4 vs 3) |

---

## 🛠️ 开发工作流

### 修改流程

```bash
# 1. 改之前 — 找全部引用 + 看接口契约
grep -rn "func_name" scripts/ references/ tests/
cat SKILL.md | head -50

# 2. 写之前先写 unit test(参见 tests/ 现有 24 个)
# 3. 改完后跑测试
python -m pytest tests/ -v

# 4. CLI 签名验证
python scripts/<script>.py --help

# 5. 跨项目踩坑模式引用
cat history/v3.8-optimized/resource-study-report-2026-10-13.md
```

### 会话纪律(本项目 CLAUDE.md)

- **0 删除**:全为新增 + Edit,任何删除走 `no-delete-gate.py` 二次确认
- **临时文件**:`/c/Temp/`(MSYS2 风格)
- **不动**:`.claude-mem` / `.claude-flow` / `.codex` / `.copilot` / `.config` / `history/v3.8-optimized/`
- **会话预算 ≤ 2h**,主动 `/exit` 或新开会话
- **接力必写** `handoff-<topic>-<date>.md` + `prompt-<topic>-next.md`
- **不 commit** `prompt-*` 接力文档(只本地用)

### Git 提交规范(Conventional Commits)

```bash
git add <files>
git commit -m "feat: 新增功能"
git commit -m "fix: 修复 bug"
git commit -m "refactor: 重构(无新功能/无 bug 修复)"
git commit -m "test: 仅测试"
git commit -m "docs: 仅文档"
git push origin main
```

---

## 📚 文档导航

| 文档 | 用途 |
|---|---|
| [SKILL.md](SKILL.md) | **v4.22 主文档**(必读,~600+ 行,含 30 规约详细) |
| [references/规约清单.md](references/规约清单.md) | 30 条规约**单一真相源** |
| [references/av-end-to-end-checklist.md](references/av-end-to-end-checklist.md) | 13 步端到端流程 |
| [references/asr_corrections.yaml](references/asr_corrections.yaml) | 41 条 ASR 错词 |
| [optimization-plan-v2-2026-10-13.md](optimization-plan-v2-2026-10-13.md) | A+B 详细任务 |
| [references/SIMPLIFY_REVIEW_v4.21.md](references/SIMPLIFY_REVIEW_v4.21.md) | v4.21 simplify 总览 |
| [history/v3.8-optimized/lessons.md](history/v3.8-optimized/lessons.md) | 25+ 条使用教训 |
| [history/v3.8-optimized/resource-study-report-2026-10-13.md](history/v3.8-optimized/resource-study-report-2026-10-13.md) | **13 条 M-XX 跨项目踩坑** |
| [handoff-2026-10-13-phase-a.md](handoff-2026-10-13-phase-a.md) | 阶段 A 输入 handoff |
| [handoff-2026-10-14-a-done.md](handoff-2026-10-14-a-done.md) | 阶段 A 完成 handoff |
| [handoff-2026-10-15-b-done.md](handoff-2026-10-15-b-done.md) | 阶段 B 完成 handoff |
| [handoff-2026-10-16-c-done.md](handoff-2026-10-16-c-done.md) | 阶段 C 完成 handoff |
| [handoff-2026-10-17-d-done.md](handoff-2026-10-17-d-done.md) | 阶段 D 完成 handoff |
| [handoff-2026-10-18-e-done.md](handoff-2026-10-18-e-done.md) | v4.21 全部完成总览 |

---

## 🤝 贡献

本项目为个人 skill,主要用于讲座笔记生成。**外部贡献**:

- 🐛 **Issue**:报 bug / 提需求
- 🔀 **PR**:规约校验增强 / 新规约条目
- 📚 **Doc**:补充 references/

---

## 📜 License

MIT

---

## 🔗 相关项目

| 项目 | 关系 |
|---|---|
| [history/v3.8-optimized/](history/v3.8-optimized/) | v3.8 完整备份(旧版参考) |
| [F:/resourse_study/](F:/resourse_study/) | 实战案例库(14 份 handoff 沉淀 M-01~M-13) |

---

## 📈 版本历史

| 版本 | commit | 日期 | 关键变更 |
|---|---|---|---|
| **v4.22** | 5d68101 | 2026-10-18 | 全面体检:7 修复(F1-F7) |
| v4.21 E | 6a80b6a | 2026-10-17 | utils 8 工具 + argparse + heading + CI + simplify |
| v4.21 D | 48b3297 | 2026-10-17 | run_pipeline + preflight + 4 步 + orchestrator + 幂等性 + 时间预算 |
| v4.21 C | 31a4a10 | 2026-10-16 | prompt 收紧 + chunking 统一 + fail-loud + verbose |
| v4.21 B | a95fce2 | 2026-10-15 | verify_all 21 条 + check_no_md_corruption 44 词 |
| v4.21 A | 6ed4d26 | 2026-10-14 | safe_llm_call + utils.log + 静默 except + MAX_CHARS + chunking + fallback timeout |
| v4.20 | e1218f0 | 2026-10-13 | 初始 commit(282 tests) |

---

<!-- Generated: 2026-10-18, source: v4.22 全面体检 (commit 5d68101) + 5 阶段 24 子任务 handoffs -->
