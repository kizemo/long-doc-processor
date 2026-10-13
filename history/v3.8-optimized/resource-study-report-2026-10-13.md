# 跨项目踩坑模式扫描报告 · 基于 F:/resourse_study/ 14 份 handoff

> **生成时间**: 2026-10-13
> **调研范围**: `F:/resourse_study/` 下 long-doc-processor 真实运行产出的 14 份 handoff + 30+ 项目级 wrapper 脚本
> **目的**: 提取 v4.20 后续优化(阶段 A + B)的"沉淀参考"——这些经验来自多次真实讲座处理,已稳定复现,可作为优化方案的事实支撑
> **关系**: 本报告**不重复** `lessons.md` 已有条目(那些是 long-doc-processor 自跑记录),只补 **F:/resourse_study/ 跨项目沉淀但未写入 lessons.md 的模式**

---

## 1. 调研样本清单(按时间倒序)

| 序号 | handoff 文件 | 项目 / 阶段 | 关键技术决策 | verify 结果 |
|---|---|---|---|---|
| 1 | `Claude Code/claude prompt playbook/handoff-2026-10-12.md` | 视频无音轨,改视觉路线 | 跳过 ASR,RapidOCR + 关键帧 Read | verify_html 6/6 PASS |
| 2 | `智篆/2026-08_煜东系列课/.../handoff-测款数据解读v4.18重做-2026-09-17.md` | v4.18 全流水线重做 | `_post_simplify_chapter` + `_post_add_summary` + 41 verify | verify 37/38 PASS |
| 3 | `智篆/2026-08-19_AI爆款全流程实战_煜东/handoff-yudong-finalize-20260823.md` | 10 段 ASR 收尾 | srt→md 中间层,跳过 LLM 净化 | verify 38/0 PASS |
| 4 | `智篆/2026-09-06_无界精英班_老草/handoff-无界精英班-2026-09-09-2.md` | 8 段串行 ASR | strict purify wrapper + post 补图 | verify 38/0 PASS |
| 5 | `智篆/2026-08-12_尖刀连/.../handoff-尖刀连-2026-08-final.md` | 17 段 4 天连跑 | watcher SKILL_DIR 路径 bug 修复 | verify 38/0 PASS |
| 6 | `智篆/2026-07-25_三日课/.../handoff-caicai-2026-08-07.md` | 单视频 49.6 min | 项目级 strict purify wrapper | verify 35/35 PASS |
| 7 | `智篆/智篆商业线上课/2026_新品孵化/handoff-xinpin-fuhua-20260826.md` | 4 段课程合并 | large-v3→turbo GPU 切换 | 接力状态 |
| 8 | `智篆/2026-08-19_AI爆款全流程实战_煜东/handoff-yudong-asr-20260822.md` | ASR 10 段 | (前序) | — |
| 9 | `边界/output/handoff-边界-标品非标品-2026-08-10.md` | 165 min 长视频 | 二次 LLM 合并 28→17→11 章 | verify_all 35/35 |
| 10 | `边界/2026-07-15_.../爆款起爆实战体系_大城/handoff-边界大城-2026-08-05-v4.md` | 4 段 v3.8 → v4.0 强化 | CLAUDE.md §8 强化 | verify 25/28 |
| 11 | `边界/2026-07-15_.../爆款起爆实战体系_大城/handoff-边界大城-2026-08-05.md` | (v3 前序) | f-string escape bug | — |
| 12 | `边界/2026-07-15_.../爆款起爆实战体系_大城/handoff-边界大城-2026-08-04-v2.md` | (v2 前序) | — | — |
| 13 | `鬼脚七线下课/.../handoff-update.md` | 第 5 章重做 + ASR 规则级替换 | — | verify 35/37 |
| 14 | `鬼脚七线下课/.../人群资产模块协同联动AI闭环体系_handoff.md` | 6 段音频完整闭环 | 极简 prompt 兜底 LLM 500 错误 | verify 35/37 |

---

## 2. 关键踩坑模式 13 条(按出现频次排序)

### 模式 M-01:`_wait_and_finalize.py:32` SKILL_DIR 路径 bug  ⚠️ P0
- **出现**:尖刀连 2026-08-19 + 多个 crv-audio 项目
- **现象**:`Path("/c/Users/Duanyi/.claude/skills/long-doc-processor/scripts")` 在 Windows Python subprocess 转义后变 `F:\c\...`
- **修复**:用 `Path(__file__).parent` 或绝对 Windows 路径
- **优化建议**:**A1 safe_llm_call 的 SKILL_DIR 引用也用 `Path(__file__).parent`,绝不硬编码 `/c/...`**

### 模式 M-02:LLM 间歇 500 错误 / 内容过滤器 1026  ⚠️ P0
- **出现**:鬼脚七 part5b + 边界大城
- **现象**:strict prompt 30s 后抛 `500 Internal Server Error`(L1);`1026 input new_sensitive` 内容过滤误判(L2)
- **修复**:拆小段(30K chars)+ 备 minimal prompt("把下列 ASR 重写为通顺中文 markdown");L2 改手动 Edit + regex
- **优化建议**:**A1 safe_llm_call 必须返回 `(text, status, error_detail)` 而非 raise**,让调用方能 5 种 status 分流;minimal prompt 作为兜底

### 模式 M-03:crv-audio 输出路径与 watcher 期望错位  ⚠️ P0
- **出现**:煜东 2026-08-23(本会话新发现)
- **现象**:crv-audio 写 `output/<dir>/audio.{srt,txt,json}`,watcher 找 `output/parts/*transcript_raw*.md`,watcher 永远 count=0
- **修复**:写 srt→md 中间层(`_srt_to_cleaned_md.py`),或让 ASR 包装脚本直接产 `parts/transcript_raw.md`
- **优化建议**:**A1 阶段** transcribe_via_crv.py 路径契约明确化:输出 `output/test-crv2/<stem>/audio.{json,srt,txt}`,新增 `_srt_to_md.py` 作为标准中间层

### 模式 M-04:`_pipeline_all.py` f-string escape + GBK 兜底  🟠 P1
- **出现**:边界大城 v3 阶段
- **现象**:f-string 中 `r'\n\n+'` 触发 `SyntaxError`;Python 默认 GBK stdout 中文 print 乱码
- **修复**:用 `chr(10)+chr(10)` 绕开 escape;脚本顶部 `sys.stdout.reconfigure(encoding='utf-8')` + `PYTHONIOENCODING=utf-8`
- **优化建议**:**A2 阶段** utils.py 统一处理(已有 log 函数,加 stdout reconfigure)

### 模式 M-05:NUMBERING-DOTTED 正则实际**不期望点号**  ⚠️ P0
- **出现**:煜东 2026-08-23(命名误导)
- **现象**:verify 正则 `^## \d+ `,要 `## 1 xxx`(空格不要点号),命名却叫 DOTTED
- **修复**:prompt 用 `## {chapter_title}` 漏编号 → post_process `fix_h2_numbering()` 自动加 `1/2/3` 前缀
- **优化建议**:**B1 阶段** verify_html.py 加 `verify_HIERARCHICAL_NUMBERING` 时,**正则与 SKILL.md 描述严格对齐**(先看 SKILL 再写测试,避免重蹈"命名误导")

### 模式 M-06:FULLWIDTH-PUNCT 跨行命中需整篇 normalize  ⚠️ P0
- **出现**:煜东 2026-08-23
- **现象**:单条字幕 normalize 看不到 `CJK,半角\nCJK` 模式(半角逗号在行末,下一行才接到 CJK),必须对整篇 text 兜底
- **修复**:`re.sub(r'([\u4e00-\u9fff]),\n([\u4e00-\u9fff])', r'\1,\n\2', text)` 跨行
- **优化建议**:**B1 阶段** `verify_NO_HALFPUNCT_ADJ_CJK` 必须**整篇** normalize 后检查,非 per-line

### 模式 M-07:禁用词"学员"即使表格也 FAIL  ⚠️ P0
- **出现**:煜东 2026-08-23
- **现象**:verify NO-ROLE-PERSONA regex `学员`,表格里出现也 FAIL
- **修复**:统一用"互动方"/"案例店铺"/"商家"
- **优化建议**:**B1 阶段** `verify_NO_ROLE_PERSONA_EXTENDED` 必须包含**表格单元格**扫描(不只段落)

### 模式 M-08:末章 5 类资产齐全硬要求  ⚠️ P0
- **出现**:智篆老草 v4.16 + 煜东 v4.18
- **现象**:LAST-SECTION-COMPLETE verify,每章 ≥2 H3 + 5 类资产(概念/案例/数据/逻辑/表格)
- **修复**:统一模板 + 末章必须有"因为...所以..."逻辑链
- **优化建议**:**B1 阶段** `verify_LAST_SECTION_COMPLETE` 应**有 detailed 模式**输出每章 5 类资产数量(便于定位缺失)

### 模式 M-09:PARAGRAPH-LENGTH 每条内容独立成段  🟠 P1
- **出现**:智篆老草 + 煜东
- **现象**:16 张图堆成 1 个 627 字符段 → FAIL
- **修复**:每张图/每条内容后插空行
- **优化建议**:**B1 阶段** `verify_PARAGRAPH_LENGTH` 要区分"内容段"和"图/表段"(后两类不计入长度统计)

### 模式 M-10:v4.18 simplify 保留率 45-55% 是正确区间  🟠 P1
- **出现**:智篆煜东 v4.18 重做
- **现象**:v4.17 太狠(30%),v4.18 调整后 45-55% 是合理的;NO-INFO-LOSS CJK < 35% 时放宽到 60%
- **修复**:保留率作为参考,不作为硬 FAIL
- **优化建议**:**B1 阶段** `verify_NO_INFO_LOSS` 应**双指标**:CJK 字符保留率(主) + 5 类资产完整率(辅);任一 FAIL 才 FAIL

### 模式 M-11:CJK 60% 阈值 FAIL 是数字/英文术语(可忽略)  🟡 P2
- **出现**:智篆煜东
- **现象**:电商内容含 SAB/SKU/64%/37%/ROI/CTR,字符比例与内容质量无关
- **修复**:`verify_ASR_LANG` CJK < 60% 改为 WARN 而非 FAIL
- **优化建议**:**B1 阶段** 电商类专项规则:Jaccard 字形相似度(参考 `build_per_lecture_asr_corrections.py`)

### 模式 M-12:crv-audio 必须用绝对路径 + Windows 编码  ⚠️ P0
- **出现**:边界 标品非标品 + 多个项目
- **现象**:crv-audio 内部用 stdin 相对路径,`file not found`;Windows terminal GBK 触发 UnicodeEncodeError
- **修复**:`F:/resourse_study/.../xxx.mp4` 绝对路径 + `PYTHONIOENCODING=utf-8 PYTHONUTF8=1`
- **优化建议**:**A1 阶段** transcribe_via_crv.py 入口必须 `Path(input).resolve()` 绝对化

### 模式 M-13:scenedetect 对直播录屏太慢 → ffmpeg 等距抽帧  🟠 P1
- **出现**:边界 标品非标品
- **现象**:165 min 直播录屏(画面静止)scenedetect 5+ min 无产出
- **修复**:`ffmpeg -vf "select='not(mod(n,120))'"` 每 120s 一张,2 min 抽 83 张
- **优化建议**:**A1 阶段** long-doc-processor SKILL.md 加"gotcha: 直播录屏 scenedetect 不适用,用 ffmpeg 等距抽帧"

---

## 3. 13 条踩坑与阶段 A/B 任务对照

| 任务 | 涉及模式 | 优先级 |
|---|---|---|
| **A1 safe_llm_call 装饰器** | M-01, M-02, M-03, M-12 | P0 |
| **A2 utils.log 线程安全** | M-04 | P1 |
| **A3 strip_* 复用 chunking** | (M-13 的 H2 切分通用化) | P1 |
| **A4 purify_v4_4 MAX_CHARS 硬约束** | (M-02 拆小段的逻辑上界) | P1 |
| **A5 transcribe_via_crv fallback timeout** | M-03(路径错位) | P0 |
| **A6 静默 except 修复** | M-02(LLM 异常分类) | P0 |
| **B1 verify_html 30 条规约** | M-05, M-06, M-07, M-08, M-09, M-10 | P0 |
| **B2 check_no_md_corruption 30 污染词** | M-11(ASR 易错扩展) | P1 |

---

## 4. 阶段 A 优化建议补充(基于 14 份 handoff)

### A1.safe_llm_call 设计补充
- **接口**:除 `(prompt, *, model, max_retries, timeout, backoff)`,加 `on_status: Callable[[str], None]` 回调,让调用方在 5 种 status 间分流
- **status 分流逻辑**(从 M-02):
  - `ok` → 返回 text
  - `empty` → 1 次重试,失败兜底原文
  - `timeout` → 重试(max_retries),最终 exit 2
  - `error` → 1 次重试,失败写 ERROR 标记
  - `rate_limited` → 指数 backoff(backoff * 2^attempt),写入 retry log
- **minimal_prompt 兜底**:当 status=error 时,fallback 到 `_minimal_prompt.md`(从 M-02 鬼脚七经验)
- **影响范围**:5 个 LLM 脚本:`_purify_smooth` / `purify_v4_4_hierarchical` / `strip_lecturer_preamble` / `strip_role_persona` / `last_section_reprocess`;`transcribe_via_crv` 的 fail-over 调用也用

### A2.utils.log 补充
- **M-04 关联**:除线程锁,还应加 `sys.stdout.reconfigure(encoding='utf-8')` + 设置 `PYTHONIOENCODING` 环境变量检查
- **影响**:全脚本,0 API 变更,直接 import 即可

### A3.strip_* chunking 复用
- **设计**:抽 `scripts/chunking.py` 统一 `split_by_h2(text) -> [(h2_title, content), ...]`
- **来源**:`_purify_smooth.split_by_h2` + `_purify_smooth.smooth_block` 已实现,直接抽
- **M-13 关联**:直播录屏场景可加 `ffmpeg_extract_keyframes` 作为可选前置

### A4.purify_v4_4 MAX_CHARS 硬约束
- **M-02 关联**:拆小段(30K chars) + assert 单块 ≤ max_chars
- **新增**:`--max-chars` CLI(默认 8000) + LLM 失败时**写 ERROR 标记到输出**(而非静默返回原文)
- **影响**:fail-soft → fail-loud 转换,生产环境可开 `--strict` 强制

### A5.transcribe_via_crv fallback timeout
- **M-03 关联**:除 `subprocess.run(..., timeout=7200)`,**同时校验输出路径**:`assert Path(output_dir).is_absolute()`,否则 raise
- **M-12 关联**:入口处 `Path(input_video).resolve()` 绝对化

### A6.静默 except 修复
- **M-02 关联**:静默 `except` + log 异常类别,5 种 status 走不同路径
- **SKILL.md 加 gotcha**:"禁止静默 except,必须 log 异常类别"

---

## 5. 阶段 B 优化建议补充

### B1.verify_html 30 条规约补充
- **M-05 关联**:`verify_HIERARCHICAL_NUMBERING` 正则必须**与 SKILL.md 描述一致**(`## N xxx` 空格不要点号);先看 SKILL 再写测试
- **M-06 关联**:`verify_NO_HALFPUNCT_ADJ_CJK` 必须**整篇** normalize 后检查,非 per-line
- **M-07 关联**:`verify_NO_ROLE_PERSONA_EXTENDED` 包含**表格单元格**扫描(不只段落)
- **M-08 关联**:`verify_LAST_SECTION_COMPLETE` 输出**每章 5 类资产数量** detailed 模式
- **M-09 关联**:`verify_PARAGRAPH_LENGTH` 区分"内容段"和"图/表段"
- **M-10 关联**:`verify_NO_INFO_LOSS` 双指标(CJK 字符保留率 + 5 类资产完整率)
- **M-11 关联**:`verify_ASR_LANG` CJK < 60% 改为 WARN 而非 FAIL(电商类)

### B2.check_no_md_corruption 30 污染词补充
- **M-11 关联**:`build_per_lecture_asr_corrections.py` Jaccard 字形相似度(已实现) → 作为可选 enrich 步骤
- **数据源**:`references/asr_corrections.yaml` 41 条 + 智篆历史 safe_replacements_2.json + 鬼脚七"拆电→拆店"等规则级同音错(共 50+ 条)

---

## 6. 阶段 C/D 长期方向(超出 A/B)

### C.prompt 收紧 + chunking 统一(M-02/M-05/M-06 延伸)
- 抽 `scripts/chunking.py`(`split_by_h2` + `split_oversized_h2` + `extract_preamble`)
- 5 个 LLM 脚本全部 import 此模块
- prompt 加 "H2 标题 verbatim 列表(HTML 注释)"结构化输出校验段(LLM 漏编号自动 catch)

### D.一键入口(M-01/M-03/M-12 延伸)
- `run_pipeline.py` 串 Step 0/0.5/0.6/0.7 + Phase 0/1/2/3 + verify_all
- SKILL_DIR 强制 `Path(__file__).parent`(防 M-01 重犯)
- crv-audio 路径契约化,新增 `_srt_to_md.py` 标准中间层(防 M-03 重犯)
- OUTPUT_STEM 绝对路径校验(防 M-12 重犯)

### E.可维护性
- `lessons.md` 加"跨项目踩坑模式索引"(引用本报告)
- `history/v3.8-optimized/lessons.md` 与本报告双向引用

---

## 7. 沉淀建议

1. **追加到 `lessons.md`**:本次"跨项目踩坑模式扫描"作为 `2026-10-13` 新条目,引用本报告 13 条模式索引
2. **`optimization-plan-2026-10-13.md` 阶段 A/B 各小节**:在原任务设计下方,加"基于跨项目 handoff 的补充"链接本报告
3. **本报告作为 long-doc-processor 后续优化的"事实支撑"**:v4.21+ 任何新规约/新脚本,优先 grep 本报告找是否已有踩坑经验

---

## 8. 数据来源完整性

- 14 份 handoff 全部已读(2026-08-04 ~ 2026-10-12)
- 30+ 项目级 wrapper 脚本快速浏览(`_purify_wujie.py` / `_merge_wujie.py` / `_post_process_wujie.py` / `_srt_to_cleaned_md.py` / `_llm_merge.py` 等)
- `boundary/output/test-crv2/` 中间产物抽样(标品非标品 8 段)
- `.superpowers/sdd/frame-crop/progress.md`(SDD ledger 范式)
- 1 份 `.learnings/ERRORS.md`(2026-08-02 Windows runner bug,已修)
- 0 份 `.learnings/LEARNINGS.md` / `FEATURE_REQUESTS.md`(空白)

**结论**:F:/resourse_study/ 是一个**高度丰富的 long-doc-processor 实战案例库**,但 lessons.md 沉淀(2026-10-12 重建)与跨项目 handoff 沉淀**严重脱节**。本次报告填补此 gap。

---

**下次会话接力建议**:读取本报告 + `lessons.md` 最新条目,即可掌握 long-doc-processor v4.20 全量优化上下文(自身 lessons + 跨项目踩坑)。
