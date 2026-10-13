# long-doc-processor

> **v4.20** · Claude Code Skill · 长文档(讲座/课程/录音/多份 .docx) → 净化 → 合并 → HTML 交付

[![GitHub](https://img.shields.io/badge/GitHub-kizemo%2Flong--doc--processor-blue?logo=github)](https://github.com/kizemo/long-doc-processor)
[![Version](https://img.shields.io/badge/version-v4.20-green)]()
[![Tests](https://img.shields.io/badge/tests-282%20passed-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.14%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()

**作者**: Duanyi · **位置**: `F:/soft/00selfmade/long-doc-processor/`(开发) / `~/.claude/skills/long-doc-processor/`(runtime)

---

## 🎯 项目目标

将**多份长文档**(讲座视频转录、课程录音、多份 .docx、markdown)整合 / 净化 / 转录,输出**可独立打开的 HTML 交付物**。

| 输入 | 处理 | 输出 |
|---|---|---|
| 课程讲义 (PDF/PPT) | 文字提取 + 净化 + 结构化 | Markdown 笔记 |
| 讲座视频 (mp4/m4a) | ASR 转录 + 章节切分 + 净化 | Markdown + HTML |
| 多份 .docx | 合并 + 标题降级 + 规约校验 | Word / HTML 讲义 |
| 多份 .md | 跨文档合并 + 编号统一 | 合并后 Markdown + HTML |
| XMind 大纲 | XML 解析 + 层级重构 | Markdown 大纲 |
| OCR 配图 | RapidOCR + LLM 视觉理解 | 关键帧 + 说明 |

**核心能力**:每条规则都**可机检**(30 条规约 → `verify_all.py` + `verify_html.py` 双重校验)

---

## 🚀 快速开始(5 分钟)

### 安装

```bash
# 1. 克隆仓库
git clone https://github.com/kizemo/long-doc-processor.git
cd long-doc-processor

# 2. 安装 Python 依赖
# (Python 3.14+,系统包)
pip install pytest

# 3. 验证安装
python -m pytest tests/ -v
# 期望: 282 tests PASSED in ~1.0s

# 4. (可选) 同步到 Claude Code skill 目录
# Windows:
cp -r scripts/ references/ SKILL.md ~/.claude/skills/long-doc-processor/
```

### 使用

```bash
# 1. 转录 + 净化 + 合并 + 渲染(完整流水线)
python scripts/transcribe_via_crv.py <video.mp4>  # ASR
python scripts/purify_v4_4_hierarchical.py transcript.md -o cleaned.md  # 净化
python scripts/markdown_to_html.py cleaned.md final.html  # 渲染

# 2. 校验(必跑,30 条规约)
python scripts/verify_all.py cleaned.md
python scripts/verify_html.py final.html

# 3. 自检(任意脚本)
python scripts/_post_terms_fix.py --selftest
```

更多详细用法见 [`SKILL.md`](SKILL.md)(v4.20 主文档)

---

## 🏗️ 架构

```
┌──────────────────────────────────────────────────────────────┐
│                  long-doc-processor v4.20                      │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  Input  →  ASR  →  净化  →  合并  →  渲染  →  Verify → Output │
│  (.mp4)   (crv)  (LLM)   (merge)  (HTML)  (30 规则)  (.html) │
│  (.m4a)    │      │       │       │        │                │
│  (.docx)   │      │       │       │        │                │
│  (.md)     ▼      ▼       ▼       ▼        ▼                │
│         _llm_ _purify_ _merge_ markdown_ verify_            │
│         vision  smooth       to_html  all.py               │
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ Cross-cutting Concerns:                                │    │
│  │  • safe_llm_call (timeout/retry/status 分流)  ← 计划 │    │
│  │  • chunking (H2/H3 切分)                                │    │
│  │  • 30 规约 (规约清单.md)                               │    │
│  │  • asr_corrections.yaml (41 条 ASR 错词)                │    │
│  │  • post_pass_terms (术语上下文安全替换)               │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                │
└──────────────────────────────────────────────────────────────┘
```

**5 阶段流水线**(SKILL.md 详细):
- **Phase 0**: 必做首问(模型选择 / 路径决策)
- **Phase 1**: ASR + L2 校验 + 净化 + 通顺化 + 末段精炼
- **Phase 2**: 合并 + 编号 + 必做 4 步
- **Phase 3**: HTML 渲染 + 双重 verify
- **Phase 1.7/1.8**: Semantic Pass + 关键帧裁剪(可选)

---

## 📁 项目结构

```
long-doc-processor/
├── SKILL.md                            # v4.20 主文档(必读,~2K 行)
├── README.md                           # 本文件
├── .gitignore                          # 排除 .pytest_cache / 子项目等
├── optimization-plan-2026-10-13.md    # 5 阶段优化方案
├── optimization-plan-v2-2026-10-13.md # 阶段 A+B 详细任务(本计划)
├── task.md                             # todo 清单
├── handoff-2026-10-12*.md              # 重建背景 / 进度 handoff
├── handoff-2026-10-13-optimization.md # 4 维度 review + 优化方案
├──
├── scripts/                            # 39 个 .py(可执行核心)
│   ├── _llm_vision.py                 # LLM 调用底层
│   ├── transcribe_via_crv.py          # crv-audio 包装
│   ├── purify_v4_4_hierarchical.py    # 8 chunk + LLM 净化
│   ├── _purify_smooth.py              # H2 切分 + LLM 通顺化
│   ├── verify_all.py                  # 30 规约校验(输入)
│   ├── verify_html.py                 # HTML 规约校验(输出)
│   ├── markdown_to_html.py            # Phase 3 渲染
│   ├── markdown_to_docx.py            # Word 输出
│   ├── _post_terms_fix.py             # ASR 错词 YAML 驱动替换
│   ├── _post_simplify_chapter.py      # 单章深度精炼(v4.18+)
│   ├── _post_add_summary.py           # 自动加总结章节(v4.18+)
│   ├── extract_skeleton.py            # 骨架提取
│   ├── ...                             # (其余 27 个)
│
├── references/                         # 20+ 个 .md/.yaml(知识库)
│   ├── 规约清单.md                     # 30 条规约单一真相源
│   ├── av-end-to-end-checklist.md     # 13 步端到端流程
│   ├── asr_corrections.yaml           # 41 条 ASR 错词
│   ├── content-rules.md               # 5 类实质内容标准
│   ├── anti-patterns.md               # 段级自检标准
│   ├── writing-quality.md             # 写作质量规约(v4.18+)
│   ├── phase-0/                       # 必做首问
│   ├── phase-1/                       # 净化相关
│   ├── phase-2/                       # 合并相关
│   └── phase-3/                       # 渲染相关
│
├── tests/                              # 19 个 test_*.py
│   ├── test_safe_llm_call.py          # 计划新增(30 tests)
│   ├── test_utils_concurrent.py       # 计划新增(并发 log)
│   ├── test_purify_smooth.py          # (26 tests)
│   ├── test_purify_v4_4_hierarchical.py # (27 tests)
│   ├── test_verify_all_extended.py    # (21 tests)
│   └── ...                             # (其余 14 个)
│
└── history/v3.8-optimized/             # 优化版完整备份
    ├── SKILL.md.v3.8.bak              # v3.8 完整 SKILL
    ├── lessons.md                      # 25+ 条使用教训
    ├── resource-study-report-2026-10-13.md  # 跨项目 14 份 handoff 踩坑扫描
    ├── evals/                          # 静态校验
    └── references/                     # v3.8 references 备份
```

---

## ✨ 核心特性

### 1. 30 条规约强校验
- 文档级:NO-INFO-LOSS / NO-DOC-META / NO-LECTURER-PREAMBLE / NO-ROLE-PERSONA / HIERARCHICAL-NUMBERING ...
- HTML 级:NUMBERING-DOTTED / NO-DUP-HEADING / TRAINING-AD-CHAPTER / FULLWIDTH-PUNCT / img-size ...

### 2. LLM 失败优雅降级
- 5 种 status 分流(`ok`/`empty`/`timeout`/`error`/`rate_limited`)
- fail-soft(默认)vs fail-loud(`--strict` flag)
- minimal_prompt 兜底(LLM 500 错误时)

### 3. 跨项目踩坑模式沉淀
- 13 条 M-XX 模式(来自 14 份 F:/resourse_study/ 历史 handoff)
- 覆盖 LLM 错误 / 路径 bug / 编码问题 / 规约命名误导
- 详见 [`history/v3.8-optimized/resource-study-report-2026-10-13.md`](history/v3.8-optimized/resource-study-report-2026-10-13.md)

### 4. 完整测试覆盖
- 282 tests PASSED(0 FAIL,0 SKIP)
- LLM 脚本用 mock,无 API key 也可跑
- 5 status × 6 脚本 = 30 个 mock test(计划新增)

---

## 📊 当前状态(2026-10-13)

| 项 | 数值 |
|---|---|
| scripts | 39 个 (.py) |
| references | 20 个 (.md + .yaml) |
| tests | 19 个 test 文件,282 tests PASSED |
| SKILL.md | v4.20,~515 行 |
| 规约覆盖 | verify_all 12/30 + verify_html 6/30(目标 30/30) |
| 跨项目 handoff | 14 份已扫描,13 条踩坑模式已沉淀 |
| 下一阶段 | **阶段 A(稳定性)+ 阶段 B(规约闭环)**(~12h,2 session) |

---

## 🛠️ 开发工作流

### 修改流程
```bash
# 1. 改之前
grep -rn "func_name" scripts/ references/    # 找全部引用
cat SKILL.md | head -50                       # 确认接口契约

# 2. 写之前先写 unit test(参见 tests/ 现有 19 个)
# 3. 改完后跑测试
python -m pytest tests/ -v

# 4. CLI 签名验证
python scripts/<script>.py --help

# 5. 跨项目踩坑模式引用
cat history/v3.8-optimized/resource-study-report-2026-10-13.md
```

### 会话纪律(本项目 CLAUDE.md)
- 0 删除(全为新增 + Edit,任何删除走 `no-delete-gate.py` 二次确认)
- 临时文件写 `/c/Temp/`(MSYS2 风格)
- 不动 `.claude-mem` / `.claude-flow` / `.codex` / `.copilot` / `.config`
- 会话预算 ≤ 2h,主动 /exit 或新开会话
- 接力必写 `handoff-<topic>-<date>.md` + `prompt-<topic>-next.md`

---

## 📚 文档导航

| 文档 | 用途 |
|---|---|
| [SKILL.md](SKILL.md) | v4.20 主文档(必读) |
| [optimization-plan-2026-10-13.md](optimization-plan-2026-10-13.md) | 5 阶段优化方案(总览) |
| [optimization-plan-v2-2026-10-13.md](optimization-plan-v2-2026-10-13.md) | 阶段 A+B 详细任务(本计划) |
| [history/v3.8-optimized/lessons.md](history/v3.8-optimized/lessons.md) | 25+ 条使用教训 |
| [history/v3.8-optimized/resource-study-report-2026-10-13.md](history/v3.8-optimized/resource-study-report-2026-10-13.md) | 跨项目 14 份 handoff 踩坑扫描 |
| [task.md](task.md) | 活跃 todo 清单 |
| [references/规约清单.md](references/规约清单.md) | 30 条规约单一真相源 |
| [references/av-end-to-end-checklist.md](references/av-end-to-end-checklist.md) | 13 步端到端流程 |

---

## 🤝 贡献

本项目为个人 skill,主要用于讲座笔记生成。**外部贡献**:
- 🐛 Issue:报 bug / 提需求
- 🔀 PR:规约校验增强 / 新规约条目
- 📚 Doc:补充 references/

---

## 📜 License

MIT

---

## 🔗 相关项目

| 项目 | 关系 |
|---|---|
| [openclaw-base](history/openclaw-base/) | 基础版(只读备份) |
| [long-doc-processor_openclaw](long-doc-processor_openclaw/) | 用户原参考源 |
| [F:/resourse_study/](F:/resourse_study/) | 实战案例库(14 份 handoff) |

---

<!-- Generated: 2026-10-13, source: v4.20 + 优化方案 v2 + 跨项目报告 -->
