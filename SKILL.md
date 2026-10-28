---
name: long-doc-processor
description: Load when the user mentions 整合文档, 合并多份讲义, 长文档净化, 培训录音转文字, 讲座视频转写, mp3/mp4 转 markdown, 视频抽关键帧, 多份 markdown 合并, .doc 课程稿转录, XMind 大纲, 生成讲义 HTML, 电商术语校验, 同音 ASR 误听修正, ASR 错词纠正, 通顺化重写, 删除时间戳, 清除粗口, 删除讲师角色说明, 标题分级编号, 笔记质量深度优化, 关键帧裁剪与插入（Phase 1.8：抽帧/评分/裁剪/注入 H3 段首/8 张硬上限/单图 200KB/加图/配图/crop）, 视频无演示帧改排版补救（Path G）, 中文标点全角规范化（Step 1.5）, markdown 表格污染巡检. 内置硬门禁：标题两级骨架（H3 密度与 H4 局部密度）、章节实质资产、总结与行动建议章节、讲师/学员角色前缀清除、半角标点归零、术语校正先于 LLM 净化、中间产物落 AV_DIR/tmp、交付目录三选一。Do NOT load for single-clip video watching (use claude-real-video), one-off summary, small doc edits, or anything handled by docx/pdf/officecli.
metadata:
  short-description: 多格式输入(音视频+文档+导图) → 文本 + 净化 + 通顺化 + 合并 + HTML + ASR 质量 4-pass 检查(含 markdown 结构巡检) + v4.20 Path G 排版补救 + v4.21 CN 中文标点规范化(NO-HALF-WIDTH-PUNCT-IN-CN-CONTEXT) + v4.18 LLM 语义优化(含 10 条规约) + v4.22 音视频处理内存硬上限(memory_guard) + v4.24 结构重排(Phase 2.5 / H3 两级骨架 / 标题去场次标签) + v4.25 目录规约(Step 0.5 OUT 三选一 / 中间件与脚本固定 AV_DIR/tmp)
  version: 4.23.0
  license: see-license-file
  allowed-tools: Read Bash Edit Write Glob Grep python
---

# long-doc-processor v4.24

> **v4.24 重大变更**（2026-10-28 阿呆万相台无界 2 天课程笔记暴露「H3 扁平化」结构性缺陷）：
>
> **问题**：19.4 万字符的 2 天课程笔记产出 **434 个 H3 / 0 个 H4**，
> 平均每章 72 个 H3（第 1 章 138、第 2 章 163），每个 H3 只有 1–3 段正文。
> 阅读时无法建立层级认知，目录长达数百行。根因不是 LLM 偷懒，而是**门禁把 H4 事实上锁死**：
> `H4_PER_H3_MAX ≤ 3` + `H4_TOTAL_MAX ≤ 50`（全文绝对上限，与文档规模无关）
> ⇒ 400+ 知识点要落位就只能全部压平成 H3；再叠加 `NO_SINGLE_SUBHEADING`
> 「H3 下只挂 1 个 H4 且无引言即 FAIL」，等于禁止「一个 H3 带一个 H4」。
>
> 1. **新增 `scripts/restructure_outline.py`**：结构诊断 → 导出逐章分组清单 →
>    校验并应用 LLM 分组计划（`--audit` / `--plan-out` / `--apply-plan`）。
>    守恒校验覆盖并集完整、无重复、无遗漏、章节归属、序号递增、组数上限。
> 2. **新增 `references/phase-2.5-restructure.md`**：Phase 2（合并）之后、
>    Phase 3（渲染）之前的独立阶段。触发条件 = `--audit` 报 H3 超预算。
> 3. **门禁比例化**（`verify_all.py`）：`H4_PER_H3_MAX` 3 → **18**；
>    `H4_TOTAL_MAX` 50 → **max(50, 字符数/400)**；新增 `H3_PER_H2_MAX ≤ 18`（单章）、
>    `H3_TOTAL_MAX ≤ max(20, 字符数/3000)`（全文）、
>    `NO_SESSION_LABEL_IN_HEADING`（标题禁残留 ASR 场次标签）。
> 4. **标题去场次标签**：`clean_title()` 统一剥离 `第一天上午 / 第二天下午2` 等前缀；
>    场次溯源只留在 `_handoff.md` / `_purge_stats.md`，不进标题、不进正文块引用。

> **v4.23 changelog preserved below**


> **v4.23 变更**（2026-10-24 玺承《理清2027年确定增长》实跑暴露的标点规范化数据损坏）：
>
> 1. **`normalize_cn_punctuation.py` 增加 YAML frontmatter 保护。**
>    原实现没有 frontmatter 概念，会把 `type: lecture-notes` 改成 `type： lecture-notes`、
>    把 `xxx.mp4` 改成 `xxx。mp4` ⇒ YAML 直接失效，
>    `verify_all.py` 的 FRONTMATTER 规则报 `'str' object has no attribute 'get'`。
>    新增 `detect_frontmatter_range()`：首行必须是 `---`，闭合标记 `---` 或 `...`
>    须在 200 行内（超过则视为水平线，不是 frontmatter），
>    该区间**整段原样返回**，正文照常规范化。
> 2. **`normalize_cn_punctuation.py` 保护数字上下文与有序列表标记。**
>    原实现的 `_CN_OR_MD` 含 `\d`，导致：
>    - 小数点被全角化：`增长3.5倍` → `增长3。5倍`、`净利润0.24亿` → `净利润0。24亿`
>      （**业务数字被改错**），实测一次实跑损坏 10 处；
>    - 有序列表标记被全角化：`1. **因为**…` → `1。 **因为**…`，
>      Markdown 有序列表退化成普通段落（实测 6 行）。
>    修法：`_INLINE_SKIP` 增加 `\d+(?:[.,:]\d+)+`（覆盖 `3.5` / `1,000` / `10:30`）；
>    新增 `_OL_LIST_MARKER`，行首 `N. ` 标记整段原样保留。
> 3. **`normalize_cn_punctuation.py` 补齐句号的"行末"规则。**
>    逗号/冒号/叹号/问号都有"中文 + 行末"规则，唯独句号没有（行为不一致）。
>    新增 `_PERIOD_END_OF_LINE`：`(?<={_CN_OR_BIG})\.(?=\s|$)`。
>    安全前提：前一个字符必须是中文/全角标点（`_CN_OR_BIG` 不含 ASCII 字母数字与句点）
>    ⇒ `README.md.` / `i.e.` / `No.` / `3.5` / `1. ` 都不会被误伤；
>    后一个字符必须是空白或行末 ⇒ `等等...` 的三个点都不匹配（后一个点是句点）。
> 4. **回归测试 74 → 80 项**：新增 5 项 frontmatter 保护 + 6 项数字/列表保护用例。
>    `tests/test_normalize_cn_punctuation.py`。
>
> **v4.22 changelog preserved below**

> **v4.22 重大变更**（2026-10-24 机器稳定性事故教训移植到本技能）：
>
> 1. **新增 `scripts/memory_guard.py`：音视频处理的内核级 commit 硬上限。**
>    本机曾 4 次被 ffmpeg 打死（单进程提交 99~107 GB → 系统 commit limit 被打穿 →
>    dwm / 输入法 / 远程控制连锁死）。本技能的音视频路径此前**没有任何内存上限**，
>    现在所有子进程都在 Job Object 的 `JOB_OBJECT_LIMIT_PROCESS_MEMORY` 里跑
>    （`CREATE_SUSPENDED → AssignProcessToJobObject → NtResumeProcess`，零竞态）。
>    详见 `references/memory-safety.md`。
> 2. **新增预算层**：`transcribe_via_crv.py` 在启动前先算账
>    （`estimate_asr_peak_mb()`：整轨解码 64 KB/s + 模型权重 × 1.3），
>    超时长上限或超硬上限 ⇒ **exit 4 拒绝启动**，连模型都不加载。
> 3. **新增进程内上限**：`asr_faster_whisper.py` 在加载模型前给当前进程装上限
>    （`install_self_memory_ceiling`），越限得到干净的 `MemoryError` 而不是拖垮机器。
> 4. **修掉 GBK 解码崩溃**：本机 `locale.getpreferredencoding()` 是 cp936，
>    原先 4 处 `subprocess.run(text=True)` 没指定 encoding → 子进程输出里一个
>    GBK 非法字节就让读取线程抛 `UnicodeDecodeError`。现已全部显式
>    `encoding="utf-8", errors="replace"`。
> 5. **修掉「静默无操作」这个最危险的失败模式**：`_llm_vision.call_vision()`
>    在后端不可用时返回空串 → 净化步骤 fail-soft 保留原文 → 流水线「成功」结束 →
>    交付一份**根本没净化过**的 cleaned.md，且全程无报错。
>    现在后端不可用会抛 `LLMBackendError`（带修复指引）；
>    `verify_all.py` 新增规则 `LLM_STEPS_EXECUTED`，
>    用「净化产物 vs 原始转写」的字符重合度把它抓出来。
> 6. **新增 `scripts/llm_env.py`**：把本机运行时配置里的 provider 映射成
>    Anthropic SDK 认的环境变量，并**显式检测占位符密钥**
>    （否则会用 6 字符的假 key 跑到一半才 401）。
> 7. **`verify_all.py` 补上 CLI 参数**：SKILL.md 一直写的是
>    `verify_all.py <cleaned.md> --raw-md <transcript.md> --html <final.html>`，
>    但脚本根本不读参数。现在支持了（位置参数 + `--raw-md` + `--html`）。
> 8. **`_crop_insert_frames.py` 补上 `--inset-pct`**：5% 内缩是给**未经校准的
>    LLM 坐标**兜底用的（坐标有 ±5% 偏差时内缩可避免切掉主体）。
>    但 crop_box 若已由人工目视校准，内缩反而会切掉画面边缘的内容
>    （实测：整页 PPT 表格被内缩切掉整列）。现在可传 `--inset-pct 0`，
>    **默认值 0.05 保持不变**，既有行为不受影响。
> 9. **`post_pass_terms.py` 补上 `--file` / `--dry-run`**：该脚本原先只扫描技能
>    自带的 `day{N}/2026-08-*` 项目笔记，**无法作用于任意文档** ——
>    而 SKILL.md 把 L3 post-pass 列为「必跑」。现在 `--file <md>` 可处理指定文件，
>    `--dry-run` 只报告不落盘（替换规则表 `safe_replacements_2.json` 是某个具体
>    项目的词条，含 `心里→新客` 这种无上下文规则，**跑之前必须先 dry-run**）。
> 10. **post-proc 链路订正**：SKILL.md 写的 `validate_terms → post_pass_terms → …`
>    中 `validate_terms.py` **在本技能里不存在**（实际对应物是
>    `extract_terms.py` + `fix_bad_extract_terms.py`）。见 Gotchas。
>
> **v4.21 changelog preserved below**

> **v4.21 重大变更**（2026-10-14 玺承 2026 双十一备战全攻略项目反馈沉淀）：
>
> 1. **新增硬规约 `NO-HALF-WIDTH-PUNCT-IN-CN-CONTEXT`**: 中文正文严禁出现半角英式标点 `,` `;` `:` `.` `?` `!` `(` `)` `"` `'` `--` `...`(即使 ASR 转录产物 / LLM 净化产物 / 讲师口述时常用键盘符号),全部必须转为**中文标点规范** `，` `;` `：` `。` `？` `！` `（` `）` `"` `"` `'` `'` `——` `……`。脚本：`scripts/normalize_cn_punctuation.py`(行级 fenced code + inline code + URL 三层防护)
> 2. **新增 Phase 1.5 标点规范化步骤**: 在 `_post_tags_fix.py`(L1 错词) → 分块净化 → `_purify_smooth` → Phase 1.7 LLM Semantic Pass → L3 post-pass → **本标点规范化** → 渲染 HTML 之间插入,作为渲染前的最后一道工序。LLM 净化后标点常常回退到半角(LLM 默认输出英文键盘标点),必须由脚本兜底
> 3. **新增 `references/cn-punctuation.md`**: 完整替换映射表 + 行级状态机说明 + 反模式(数字上下文/URL/代码块保护)+ 实测数据(玺承 2026 双十一项目 562 处替换)
> 4. **verify_all.py 新增规则 43 `NO_HALF_WIDTH_PUNCT`**: 行级扫描,中文之间残留 `,;:?!()` 任一半角符号即 FAIL;统计每类符号残留次数,输出位置(line:col)
> 5. **qa-gates 新增规则 44**: HTML 渲染后必须二次扫描 `<p>` 节点文本,中文上下文残留半角标点 FAIL
> 6. **新增 SKILL Gotchas 2 条**(详见文末"高优先级 gotchas"段):
>    - 禁止 LLM 净化产物保留半角标点(LLM 默认输出英文键盘标点是默认行为,必须用 `normalize_cn_punctuation.py` 兜底)
>    - 禁止在标点规范化时破坏 markdown 结构(`#` `-`(列表)/ `|`(表格)/ `[]()` `()` / `![]()` / `` ` `` 都必须保留)
> 7. **保留 v4.20 Path G 排版补救**: 排版强化是中文标点规范化的有力助手(`**加粗 inline**` + 表格 + SVG inline 都比纯文本更耐看)
>
> **v4.20 changelog preserved below**

> **v4.20 重大变更**（2026-09-30 边界 2026-06-03_AI 助力主图点击率低第三轮迭代沉淀）：
>
> 1. **新增 Path G「排版补救」**: Phase 1.8 视频截图流的官方替代方案。当视频本身无 H3 演示帧(登录页/空表/AI 加载/纯讲师头像)时,**不勉强使用低质图**;改用排版强化(`**加粗 inline**`/表格/SVG inline/代码块)替代, verify_html 接受 `INFO: no <img> tags found` 作为合法状态。详见 `references/path-g-typography-fallback.md`
> 2. **新增 2 条硬规约**:
>    - **NO-FORCE-LOW-QUALITY-IMAGE**: 截图质量不达标必须放弃, 宁可少配图。"勉强用"是反模式 — 用户反馈证明勉强图比无图更糟
>    - **PATH-G-TYPOGRAPHY-FALLBACK**: Path G 是 Phase 1.8 的官方替代(非降级), 不是失败回退。Path G 文档用 typography 替代截图, 质量更高
> 3. **新增 `references/path-g-typography-fallback.md`**: Path G 完整步骤 + 排版强化 6 模式 + 反模式 + 何时触发判定流程(~150 行)
> 4. **更新 `references/phase-1.8-decision.md`**: AskUserQuestion 卡片增加第 3 选项 C(Path G 排版补救), Step 0.7 必做首问改为 3 选项
> 5. **qa-gates 新增规则 43**: 图像质量 PASS 才注入;否则切换 Path G
> 6. **新增 SKILL Gotchas 2 条**（详见文末"高优先级 gotchas"段）:
>    - 禁止把勉强可用的低质图塞进文档(算法 PASS ≠ 视觉可用, 必须人工目视二次确认)
>    - 禁止 Phase 1.8 失败后直接跳到"无图版"(应先尝试 Path G 排版强化)
> 7. **保留 v4.17 HIERARCHICAL-NUMBERING 规约**: 标题分级编号(1./1.1/1.1.1)是 Path G 的关键排版强化手段, 必须保留
>
> **v4.19 changelog preserved below**

> **v4.19 重大变更**（2026-09-29 边界 2026-06-03_AI 助力主图点击率低第二轮迭代沉淀）：
>
> 1. **新增 Phase 1.8「原帧智能裁剪与插入」**：视频原始关键帧经两阶段 LLM 决策后裁剪为局部画面,补充插入到 cleaned.md 对应 H3 子节,与文字并行阅读。脚本：`scripts/_crop_insert_frames.py` + `_stage1_score.py` + `_stage2_decide.py` + `_llm_vision.py`
> 2. **三阶段流水线**：
>    - **Stage 1** LLM 评分筛选（1 次调用, OCR-only）：输出 Top-8 候选 + h3_hint
>    - **Stage 2** LLM 逐帧决策（≤8 次串行, 看帧 + ASR）：输出 h3_target + crop_box + caption
>    - **Stage 3** PIL 裁剪 + Markdown 注入
> 3. **新规约 5+1 条硬约束**：
>    - 8 张硬上限（整篇讲座最多插入 8 张图）
>    - 单图 ≤ 200KB + 800x600 max
>    - crop_box 0-1 归一化 + 5% padding 内缩 + 边界 clamp
>    - score ≥ 0.65 阈值（防 LLM 噪声）
>    - 注入位置：H3 段首下一行（单独 ![]() 行）
>    - 多模态 LLM（Claude vision / GPT-4V）必需
> 4. **qa-gates 35-38 重编号**：原"配图视觉规范"4 项（35-38）已重编号为 39-42;Phase 1.8 新增 35-38：Top-8 限制 / 200KB 限制 / H3 存在 / caption 非空
> 5. **跳过不阻塞**：任意 Stage 失败 → 跳过该帧 / 整个 Phase 1.8 → 不阻塞 Phase 3
> 6. **新增 SKILL Gotchas 3 条**（详见本文末"高优先级 gotchas"段）：
>    - 禁止用脚本 regex 强制按时间戳插图（必须用 LLM 语义匹配）
>    - 禁止跳过 Stage 2 直接用 Stage 1 的 h3_hint（Stage 1 只看 OCR,可能猜错）
>    - 禁止 LLM 把讲师当主题插入（即使 prompt 强排除,仍可能误判,score<0.65 兜底）
> 7. **新增 `references/phase-1.8-frame-crop.md`**：完整步骤文档 + prompt 模板 + 反模式 + 实测数据 + 已知陷阱（~280 行）
> 8. **新增单元测试**：`tests/test_crop_insert.py` 含 14 tests 覆盖 Stage 1/2/3 + 边界 case（crlf / clamp / ocr 缺失 / json markdown wrap）
> 9. **新增 Phase 1.8 首问判定（Step 0.7）**：v4.8 必做首问 3 步升级为 4 步。新增第 4 步"是否插入截图"——若用户消息命中"插入截图/插图/配图/加图/原帧/裁剪/crop/Phase 1.8"等关键词则直接调用 Phase 1.8,否则用 2 选项 AskUserQuestion 卡片（A 跑 / B 跳过）让任务发布者选。判定逻辑详见 `references/phase-1.8-decision.md`。

> **v4.18 重大变更**（2026-09-29 边界 2026-06-03_AI 助力主图点击率低项目第二轮迭代沉淀）：
>
> 1. **新增 2 条硬规约**（用户最新要求 + 边界项目第二轮反馈）：
>    - **NO-META-LECTURE-PREAMBLE-IN-SECTION**：章节正文内禁止讲师铺垫/课间安排内容（课程安排/教学策略/回顾上次/现场写不单独发资料/章节标题"课程说明与本节目标"），应提炼为一句话目标陈述或直接删除。LLM 净化阶段倾向保留这些"过渡段"作为章节引子,但实质上不增加信息量
>    - **NO-SINGLE-LINE-BLOCKQUOTE-CALLOUT**：单行 `>` 引用块不应作为视觉强调工具。核心判定/核心逻辑/关键指标/操作要点应转为 `**加粗 inline**` 段落或合并到上下文。例外：多行 `>` 块（≥2 行）作为"核心结论 box"展示是合法的
> 2. **更新 `references/phase-1.7-semantic-pass.md`**：新增"## v4.18 新增 2 条硬规约"章节，含规约 5 + 规约 6 完整触发模式 + 改写示范 + 反模式 + 实测效果表
> 3. **Phase 1.7 强制 LLM 调用扩展**：6 条规约（4 + 2）必须全部由 LLM 调用处理，脚本 regex 无法识别"课程安排 vs 实质内容"或"多行 box vs 单行 callout"
> 4. **规约计数器升级**：v4.17 起 4 条 → v4.18 起 6 条
> 5. **新增 SKILL Gotchas 2 条**（详见本文末"高优先级 gotchas"段）：
>    - 禁止 LLM 优化时新增单行 `>` blockquote（视觉强调一律 `**加粗 inline**`）
>    - 禁止 LLM 优化时保留讲师铺垫段（课程安排/教学策略/回顾上次类直接删）

> **v4.17 重大变更**（2026-09-29 边界 2026-06-03_AI 助力主图点击率低项目复盘沉淀）：
>
> 1. **新增 4 条硬规约**（用户最新要求 + 2026-09-29 边界项目反馈）：
>    - **NO-DOC-META-BLOCKQUOTE**: H1 后 blockquote 元描述（"课程来源 / 核心主题 / 文档生成"）整段删除，违则任务未达标
>    - **NO-ROLE-PERSONA-EXTENDED**: 全文删"讲师/学员"主语前缀（讲师指出/讲师总结/讲师举例/学员搜索时/学员常见的错误 → 直接陈述事实），例外：引号内原话可保留
>    - **HIERARCHICAL-NUMBERING**: H2/H3/H4 强制 `1./1.1/1.1.1` 阿拉伯数字编号，连续递增不缺号；总结章固定 = `7. 总结与行动建议` + `7.1` + `7.2` + `7.3`
>    - **NO-ORPHAN-WORDS**: 修复 ASR 同音错词残留 + 段首/段末孤立无语义词组（"好/对/那个/对吧/是吧" 等）
> 2. **强制 LLM 语义分析**（不是脚本 regex）：4 条新规约**必须**由 LLM 调用处理，不允许用纯 regex 脚本批量替换。理由：纯 regex 无法判断"讲师总结"是否在引号内（例外），无法识别"主语省略 vs 主语前置"的语义差异，无法修复跨段连贯性问题
> 3. **净化流程新增 Phase 1.7（LLM Semantic Pass）**：在合并完成后 → 渲染 HTML 前，新增一次 LLM 调用做语义优化（4 条规约 + 整体质量深化），输出 `cleaned.semantic.md`，再合并为最终 cleaned.md
> 4. **整体质量深化**（v4.17 在规约外补强）：
>    - 连贯性：每章开头加 1-2 句承接上文的过渡
>    - 重复检测：同一观点/案例多处出现 → 合并到首次处，后续用"参见 N.M 节"引用
>    - 数据一致性：同一指标全文必须一致（"100 收货人数首页"不能在别处变成"100 收货人数上第 1 页"）
>    - 表格/列表后必加一句总结
>    - 标题长度 H2 ≤15 字 / H3 ≤20 字
> 5. **更新 `references/purification-prompt.md`**：新增"## 11. 4 条硬规约 + LLM 语义分析" 章节
> 7. **新增 `references/phase-1.7-semantic-pass.md`**：LLM 语义优化步骤文档 + 反模式 + 完整 prompt 模板
> 8. **新增 SKILL Gotchas 4 条**（详见本文末"高优先级 gotchas"段）：
>    - 禁止用脚本 regex 处理"讲师/学员"前缀（无法识别引号例外）
>    - 禁止用 sed/awk 批量替换 ASR 错词（破坏上下文）
>    - 禁止跳过 Phase 1.7 直接渲染 HTML（4 条规约全靠 LLM 守）
>    - 禁止用 markdown 渲染器把 `<hr>` 当成段落（会触发 verify_html frontmatter artifact FAIL）

> **v4.16 重大变更**（2026-09-17 智篆 2026-07-26 项目复盘沉淀）：
> 1. **新增 `_purify_smooth.py`（Phase 1.5B 通顺化重写步骤）**：PURIFY_PROMPT 的"清理+保留"模式不能让 LLM 主动删除不通顺段、粗口、ASR 串扰。新增独立步骤专门重写为通顺书面语
>    - 关键约束：禁止 LLM 新增内容 / 禁止删除原标题 / 禁止改变章节数量 / 禁止虚构案例
>    - 必须清理：行首时间戳 / 粗口 / ASR 装饰 / ASR 串扰 / 错乱中英俄混杂 / 不通顺短句 / 重复词
>    - 调用：`python scripts/_purify_smooth.py <cleaned.md> -o <smoothed.md> --workers 3`
> 2. **新增 skill 标准 ASR 错词工具** `scripts/_post_terms_fix.py` + 数据驱动配置 `references/asr_corrections.yaml`：
>    - **无需复制脚本**：skill 直接提供可执行命令 `python scripts/_post_terms_fix.py <input> <output>`
>    - **数据驱动**：错词规则在 YAML 文件而非 Python 源，更易维护 + 项目级覆盖
>    - **自动发现配置**：CWD 下的 `asr_corrections.yaml` → 上溯找到的 `AV_DIR/tmp/asr_corrections.yaml` → skill 内置默认
>    - 必须**先于** `_purify_smooth` 跑（LLM 是错词放大器，v4.7 老草任务证实）
>    - 智篆 2026-09-17 用户反馈错词样例：石木床→实木床、权占→全站、掀车→四轮推车、复构→复购、点击力→点击率
>    - 用法：
>      ```bash
>      # 项目级：cp references/asr_corrections.yaml.example 到 AV_DIR/tmp/asr_corrections.yaml，编辑后跑
>      python scripts/_post_terms_fix.py <input.md> <output.md>
>      # 默认（无项目配置）：直接跑使用 skill 内置默认 24 条规则
>      python scripts/_post_terms_fix.py <input.md> <output.md>
>      ```
>
> 3. **PURIFY_PROMPT 历史 bug 修复**：`scripts/purify_chunks.py` 原 prompt"保留时间戳行格式"是 design bug——净化文档应去除时间戳。LLM 现在仍可能保留时间戳，需在 _purify_smooth 后做后处理（参考 v4.16 项目级模板）
> 4. **3 阶段流水线确立**：
>    ```
>    purify_chunks.py → scripts/_post_terms_fix.py（skill 标准 + 项目级 YAML）→ scripts/_purify_smooth.py
>    → strip_lecturer_preamble / strip_role_persona / strip_asr_terms
>    → post_pass_terms → verify_all
>    ```
> 5. **新增 `references/phase-1.5-smoothing.md`**：完整步骤文档 + 反模式 + 实测数据
> 6. **新增 SKILL Gotchas 4 条**（详见本文末"高优先级 gotchas"段）：
>    - 不要让 _purify_smooth 单块 > 8K chars（LLM 会"自由发挥"编造内容）
>    - 不要跳过 _post_terms_fix 直接 _purify_smooth（LLM 保留 ASR 错词）
>    - 不要用 SMOOTH_PROMPT 处理跨章节合并（每 H2 必须独立调 LLM）
>    - 项目级 ASR 错词规则按"长词在前、短词在后"顺序（避免短词误匹配）

> **v4.15 重大变更**（2026-08-21 玺承 6 章电商场景化营销课复盘沉淀）：
> 1. **新增 Step 2.0 合并前语义检查**（必做）：跑 `scripts/_pre_merge_semantic_check.py` 在分块 purify → merge 之间检测 4 类问题：
>    - **H3 编号跳号**：同 H2 下 H3 是否连续（1, 2, 3...）；自动重排为连续编号
>    - **ASR 错词高发词**：摩特图→模特图、点几率→点击率 等 16 类；自动字典替换
>    - **人称角色残留**：学员/讲师/主讲导师/大力老师/授课老师/教练；自动字典替换
>    - **chunk 收束句**：part 末尾 `因此/综上/总之` 破坏承接；仅报告（人工 review）
> 2. **新增 `scripts/_pre_merge_semantic_check.py`**：自动检测 + 自动修复上述 3 类 + 输出报告
> 3. **新增 `references/pre-merge-semantic-check.md`**：流程说明 + 检测维度 + 与 `asr_quality_check.py` (v4.11) 的区别
> 4. **v4.9.1 必做清单第 3 步硬约束升级**：合并完成后 → 渲染 HTML 前必须新增 `## N 总结与行动建议` H2（N = 当前 H2 计数 + 1），含 N.1 全文要点回顾 / N.2 可执行行动清单（表格）/ N.3 决策流程图；缺失即任务未达标（verify 已加 LAST-SECTION-COMPLETE 强制 5 类资产齐全）

> **v4.14 重大变更**（2026-08-16 边界下半年增长路径任务复盘沉淀）：
> 1. **CHAPTER-1-SUBSTANTIVE**：第 1 章必须含 ≥3 类实质资产（概念/案例/数据/逻辑/表格），缺则 FAIL
> 2. **9 类 H3-LECTURER-BIO 黑名单扩展**：`主讲人资历/直播核心主题/课程预告/线下 N 天/招生/系统课` 等
> 3. **4 类 TRAINING-AD-CHAPTER 关键词扩展**：`会员价/购物车链接报名/线下系统课程/线下 N 天` 等
> 4. **purify prompt 新增"## 10. 章节内容类型约束"**：整 H3 铺垫删除 + 整章铺垫替换

> **v4.13 重大变更**（2026-08-03 鬼脚七 D0 段级净化复盘沉淀）：
> 1. **D0 段级语义净化必跑**（B1 之后切块之前）：阻断 LLM 净化放大 ASR 同音错词
> 2. **21 条同音错词硬约束**：皮气护理→皮质护理 / 牛仔库→牛仔裤 / 心中式→新中式 / 带梦图→带门图 等
> 3. **asr_faster_whisper.py 支持 initial_prompt 术语注入**（crv-audio 不支持时降级路径）

> **v4.12 重大变更**（2026-08-11 鬼脚七线下课 `|` → "医疗器械标签" 表格污染复盘沉淀）：
> 1. **表格分隔符 `|` 误入 ASR 字典的缺陷全线修复**（3 道防线）：
>    - **`extract_terms.py`** 新增 `extract_from_text_safe()` 双层过滤 + main() 默认走 safe；`_is_dangerous_wrong_token()` 排除 `|` `#` `>` `` ` `` `~` 等 markdown structural chars；`_is_pure_punctuation()` 排除纯符号 wrong token
>    - **`strip_asr_terms.py`** 新增 wrong token 守卫：对 `|`, `#`, `>`, `<`, `-`, `+`, `_`, `~`, `` ` ``, `!`, `\\` 等单字符跳过替换
>    - **`validate_terms.py`** 自动调用 `fix_bad_extract_terms_inline.py` 清理 asr_terms.json 中 garbage 条目
> 2. **自动巡检·表格完整性**：
>    - **`scripts/check_no_markdown_corruption.py`**：检查表格列数均匀性 + 已知污染词残留 + 断裂标题 + HTML vs md 表格数对比
> 3. **`fix_bad_extract_terms_inline.py`** v4.12 重写（支持 CLI path arg + 强化过滤逻辑）
> 4. **post-proc 链路扩展**：
>    ```
>    validate_terms.py（内设 extract_terms + auto_cleanup）
>    → post_pass_terms.py
>    → asr_quality_check.py
>    → check_no_markdown_corruption.py
>    → verify_all.py
>    ```

> **v4.11 重大变更**（2026-08-11 鬼脚七线下课《人群资产模块》复盘沉淀）：
> 1. **3 个 ASR 质量保障脚本**（post-proc 链路）：
>    - **`scripts/glossary_expand.py`**：从 `references/电商术语表.md` G 节反向生成 `asr_error_dict.json`（ASR 错词 → 正确词），跑一次覆盖整张词表
>    - **`scripts/asr_quality_check.py`**：v4.11 3-pass 流水线。Pass 1 = `asr_error_dict.json` 字典替换（高置信度）；Pass 2 = 孤字/双字扫描 review 候选；输出 markdown 报告到 `reports/asr_quality_report.md`
>    - **`scripts/build_per_lecture_asr_corrections.py`**：扫单字/双字孤字 + Jaccard 字形相似度与 `asr_error_dict.json` 模糊比对；输出 `reports/asr_corrections_candidates.{md,json}` 给人工 review
> 2. **post-proc 链路顺序**（合并后必经）：
>    ```
>    validate_terms.py → post_pass_terms.py → asr_quality_check.py → verify_all.py
>    ```
> 3. **`references/电商术语表.md` G 节追加 10 条新 ASR 易错词**（鬼脚七线下课 1.8/2.1 段反查）：数据筛毯→数据筛选、最大化作间法→最大化筛选法、识别确论→精确识别、继程→决策、蒸柔→蒸馏、建国资产→沉淀资产、放弹→放量、相产品均头→相似产品、相产品国际→同价位、GGC→GGV
> 4. **`asr_full_glossary.json` 自动化建议**：v4.11 起 strong 修正 ASR error → 自动追加到 `references/电商术语表.md` G 节，下次启动自动修复

> ## ⚡ 必做首问（v4.19 强制，**不执行这 4 步禁止跑 ASR / 截图**）
>
> 加载本 skill 后，**第一件事**是依次询问用户 4 个问题，**用户确认前不要执行任何 ASR / 净化 / 截图 / 渲染命令**。
>
> | 顺序 | 步骤 | 必问什么 | 文档位置 |
> |------|------|---------|---------|
> | **1** | **Step 0 · ASR 模型选择 + 时长预估** | 5 个 whisper 模型（turbo GPU / large-v3 GPU / turbo CPU / base CPU / small CPU）× 6 档音频时长（30/60/90/120/180 min）预估表，用户选 1 个 | `references/av-end-to-end-checklist.md` § Step 0 |
> | **2** | **Step 0.5 · 输出目录与中间目录** | 3 选 1：① 与音视频同目录 ② 音视频目录下建同名子目录（默认）③ 音视频目录下建 `output`；另固定：**所有中间文件与脚本放 `AV_DIR/tmp/`** | `references/av-end-to-end-checklist.md` § Step 0.5 |
> | **3** | **Step 0.6 · 输出文件名（OUTPUT_STEM）** | 区分 `INPUT_STEM`（音视频文件名）vs `OUTPUT_STEM`（选项②时 = 子目录名；选项①③单独确认）；最终交付的 `<OUTPUT_STEM>_cleaned.md` + `<OUTPUT_STEM>_final.html` 必须等于子目录名 | `references/av-end-to-end-checklist.md` § Step 0.6 |
> | **4** | **Step 0.7 · 是否插入截图（Phase 1.8）** | 若用户消息命中关键词（"插入截图/插图/配图/加图/原帧/裁剪/crop/Phase 1.8"）→ 直接调用 Phase 1.8 三阶段流水线；否则用 AskUserQuestion 卡片让任务发布者选择（2 选项：A 跑 Phase 1.8 / B 跳过直接渲染） | `references/phase-1.8-decision.md` |
>
> **违反这 4 步的后果**：
> - 默认选 ASR 模型 → 选高精度浪费数小时 / 选低质浪费精力
> - 跳过目录命名 → 用户后悔但已跑一半
> - 跳过文件名 → 输出 md/html 与子目录名不一致，难以追溯
> - 跳过截图询问 → 默认不插入图，用户期望图缺失（如果本意是插入）或反向（浪费 LLM API）
>
> **强约束**：即使用户说"用上次的方式"/"和少壮一样"或类似指令，也要**重新走这 4 步**（因为 Step 0.5/0.6/0.7 用户可能换名 / 改主意）。

---

> **v4.10 重大变更**（2026-08-10 边界标品《爆款突围与全域利润闭环》复盘沉淀）：
> 1. **3 条新规约**（v4.10 起 33 条）：
>    - **`NO-DOC-META-HEADER`**：禁止 H1 标题下文档元说明（"本文档由视频转录净化整理..." / "原视频为..." / "本讲座聚焦..."）。元描述是冗余信息，最终读者关心的是内容不是元数据；2026-08-10 边界标品任务首版 H1 下出现 1 段文档元描述是反例
>    - **`NO-ROLE-PERSONA`**：正文禁止人称角色（"学员/讲师/主讲导师/大力老师/授课老师/教练/某学员提出"）。改为通用角色（"案例店铺/商家/运营团队/某案例"）。例外：直接引用讲师原话（带引号）可保留；2026-08-10 边界标品任务 11 处"学员"用法全部需润色是反例
>    - **`FAQ-PATTERN`**：问答体例统一用 "FAQ：" 开头（替代"有学员提出/学员问/Q：/提问："）
> 2. **新脚本 `scripts/strip_role_persona.py`**：LLM 驱动改写人称角色 → 通用角色（v4.10 强制）
> 3. **`verify_all.py` 新增 2 个函数**：`verify_NO_DOC_META_HEADER` + `verify_NO_ROLE_PERSONA`（含 FAQ-PATTERN 检查）
> 4. **`purify_v4_4_hierarchical.py` prompt 增角色润色硬约束**：禁止出现"学员/讲师/主讲导师"等词，改用"案例店铺/商家/运营团队"
>
> **v4.9 重大变更**（2026-08-05 边界大城《爆款起爆实战体系》复盘沉淀）：
> 1. **讲师资历类 H2/H3/H4 标题黑名单**（`H3-LECTURER-BIO` verify 新规）：禁止 `讲师资历 / 讲师简介 / 讲师介绍 / 自我介绍` 等 11 类模式出现在标题中；与 `NO-LECTURER-PREAMBLE`（仅查文本铺垫句式）互补，覆盖整段讲师铺垫的反模式
> 2. **D0 禁止保留 H5 标题**（`purify_v4_4_hierarchical.py` prompt 增 `L5 禁用 + 加粗子标题 fallback`）：4 级嵌套 `N.M.Z.W` 必须降级为 H4 下的 `**N.M.Z.W 标题**` 加粗子标题，不再保留为独立 `#####` 标题
> 3. **冗余次级标题检测**（`NO-SINGLE-SUBHEADING` verify 新规）：H3 下只挂 1 个 H4 且 H3 无引言，或 H4 下只挂 1 个加粗子标题且 H4 无引言 → FAIL；修复 = 删冗余层级合并到父级
> 4. **必做"总结与行动建议"章节**（合并后强制新增 `## N 总结与行动建议` H2）：含 `N.1 全文要点回顾` / `N.2 可执行行动清单`（表格）/ `N.3 决策流程图` 三段；缺失即任务未达标（verify 暂未自动查，靠 Gotchas 强制）
> 5. **新增/修改 3 个脚本/规约**：
>    - `scripts/verify_all.py` 加 `verify_H3_LECTURER_BIO` + `verify_NO_SINGLE_SUBHEADING` 函数，注册到 RULES（v4.9 起规约从 28 → 30 条）
>    - `scripts/purify_v4_4_hierarchical.py` prompt 标题规范增 `L5 禁用` 段
>    - `SKILL.md` Gotchas 表增 4 条 + frontmatter description 加 4 条触发条件
>
> **v4.8 重大变更**（2026-08-04 少壮 A1 端到端复盘沉淀）：
> 1. **A1 ASR 升级路径**：venv `torch 2.11.0+cu128` + `crv-audio --whisper-model turbo` + RTX 3090 GPU 推理；138 min 音频 ~37 min 推理（4× realtime），关键错词 grep = 0
> 2. **D0 + 8 块 split + 强制 1 H2/chunk 兜底**：v4.7 引入 D0 段级净化（`semantic_block_fix.py`），v4.8 验证 LLM 即使 prompt 写"1 H2 per chunk"仍会产出多 H2（实测 8 块首次 26 H2），需 retry + 项目级 merge 脚本强制对齐 skeleton
> 3. **LAST-SECTION-COMPLETE 启发式补丁**：末段 H2 必须含 ≥2 H3 + 5 类资产（概念/案例/数据/逻辑/表格）齐全；v4.8 验证启发式正则 + 补内容（定义/逻辑词/表格）是标准修复路径
> 4. **output/ 目录规范强化**：v4.8 强制 `output/<stem>_final.html` + `output/<stem>_cleaned.md` 必交付；不再允许 cleaned.md 仅在 lecture 根目录
> 5. **3 条新 gotcha**（详见 `references/gotchas.md`）：
>    - skill 脚本 `--help` 也会执行 main() 副作用（argparse SystemExit(0) 之前 main 已跑完）
>    - `reorganize_to_skeleton.py` 是 蒋太帅 MP3 硬编码版本（SKELETON_CHAPTERS / 路径 / 关键词表都写死），不能复用到其他讲座
>    - `purify_v4_4_hierarchical.py` LLM 经常违反"1 H2 per chunk"规约，需 retry + merge 兜底
> 6. **术语表验证**：2026-08-04 少壮 A1 端到端验证 `references/电商术语表.md` 3721 行内容覆盖度 — 22 处 ASR 替换全部命中表内 ASR 易错词清单
> 7. **Step 0 新增（ASR 模型选择 + 时长预估）**：5 个 whisper 模型选项（turbo GPU / large-v3 GPU / turbo CPU / base CPU / small CPU）× 6 档音频时长（30/60/90/120/180 min）预估表；新会话首问必做，禁用默认模型
> 8. **Step 0.5 新增（输出目录命名）**：默认在音视频父目录新建与**第一个音视频同名**子目录；用户可手动指定其他名 / 选不建子目录；handoff 必记 `输出目录 = ...`
> 9. **Step 0.6 新增（输出文件名 = OUTPUT_STEM = 子目录名）**：区分 `INPUT_STEM`（音视频文件名）vs `OUTPUT_STEM`（选项②时 = 子目录名；选项①③单独确认）；最终 `<OUTPUT_STEM>_cleaned.md` + `<OUTPUT_STEM>_final.html` 与子目录名强制一致
>
> **v4.7 重大变更**（2026-08-02 老草任务复盘沉淀）：
> 1. **术语纠错三层防线**：
>    - **L1 ASR 注入**：`extract_top_terms.py` 抽 Top-K 术语 → `initial_prompt` 注入 faster-whisper
>    - **L2 术语校验**（已有 `validate_terms.py`，1-to-1 ASR 易错替换）
>    - **L3 post-pass**：`post_pass_terms.py` 必跑，处理上下文敏感术语（心客→新客、欧→O、达木→达摩、同店打爆→打散）
> 2. **新发现**：**LLM 净化阶段是术语错误放大器而非纠正器**（老草实测 raw 转录 14 处错 → cleaned.md 36 处错）。结论：必须 L3 post-pass 兜底。
> 3. **新增 5 条术语表条目**：AI 人群 / AI 新客 / O 人群 / O 新客 / 同店打散原则（vendored 术语表 `references/电商术语表.md`）
> 4. **新增 2 个脚本**：
>    - `scripts/extract_top_terms.py` — 从术语表抽 Top-K → `asr_top_terms.txt`
>    - `scripts/post_pass_terms.py` — 上下文安全替换（10 条规则）
> 5. **新增 1 个 reference**：`references/phase-0-asr-term-injection.md`（三层防线完整设计文档）
>
> **v4.4 重大变更**：
> 1. **音视频主路径改为 `claude-real-video`**（crv 视频 / crv-audio 音频）；whisper 路径降为兜底
> 2. **H4 规则修正**：H4-FORBIDDEN → H4-PER-H3-MAX（≤3 / H3）+ H4-TOTAL-MAX（≤50）
> 3. **NO-INFO-LOSS 阈值提升**：25% → 45%
> 4. **新增 4 条结构连续性规约**：NO-ORPHAN-H3 / LAST-SECTION-COMPLETE / H3-NAMING-CONSISTENT / LOGIC-CHAIN
> 5. **新增 3 个脚本**：transcribe_via_crv.py（claude-real-video 包装）、last_section_reprocess.py（末段修复）、per_section_stats.py（章节统计）、extract_skeleton.py（hierarchical pipeline 骨架）
>
> **v4.3 变更（保留）**：整合原 `law` skill（已删除）。音视频强制电商术语校验（调 vendored 术语表 `references/电商术语表.md`，现 ~498 条 ASR 易错映射）。

按需读取引用文件；不要一次性读取整个 `references/`。

## 🚫 Gotchas（必看，反模式清单）

| 不要做 | 因为 |
|---|---|
| **不要保留讲师资历/讲师简介/讲师介绍/自我介绍类 H2/H3/H4 标题** | v4.9 必查（H3-LECTURER-BIO）：这类段是讲师铺垫/培训广告，2026-08-05 大城任务保留 14 行 `1.1 讲师资历与学员痛点` 段是反例；改为删除整段 |
| **不要在 D0 purify 后保留 `##### N.M.Z.W` 4 级嵌套 H5 标题** | v4.9 禁止 H5（verify H4-NUMBERING 仅识别 N.M.Z 三级）；必须降级为 H4 下的加粗子标题 `**N.M.Z.W 标题**`；2026-08-05 大城任务 20 个 H5 残留是反例 |
| **不要让 H3/H4 下只挂 1 个次级标题且自身无引言** | v4.9 必查（NO-SINGLE-SUBHEADING）：冗余结构应合并（删 H3 升级 H4，或删加粗子标题并入 H4）；2026-08-05 大城任务 7 处冗余（6 H4 + 1 H3）反例 |
| **不要跳过合并后的"总结与行动建议"章节** | v4.9 必做：所有 long-doc 任务合并完成 → 渲染前必须新增 `## N 总结与行动建议` H2，含 N.1 全文要点回顾 / N.2 可执行行动清单（表格）/ N.3 决策流程图；缺失视为任务未达标 |
| **不要把单个音视频总结当长文档处理** | 用户问"总结一下这段视频"应路由到 `claude-real-video`；本 skill 用于"多份素材合并 + 结构化 + 出 HTML" |
| **不要把短文档（< 5 页）丢进来** | 流水线开销比收益大；用 `docx` 直接转即可 |
| **不要在 SKILL.md/正文里复读每条规约定义** | 规约细节在 `references/规约清单.md`，跑 verify 即可；正文里只放"做 / 不做"决策信号 |
| **不要在 `<stem>_transcript_raw.md` 上跑净化** | 它含 ASR 时间戳；净化输入应是术语校验后的 `<stem>_transcript.md` |
| **不要靠 LLM 净化纠正术语错误** | 实测 LLM 是放大器（raw 14 处错 → cleaned 36 处错）。必跑 `post_pass_terms.py` L3 兜底 |
| **不要把术语替换留到下次再说** | 每条新术语同步在 `post_pass_terms.py` 的 `SAFE_REPLACEMENTS` 表加一条 |
| **不要试图合并跨语言文档** | 中英混排会触发乱码 + 编号冲突；先单独跑 |
| **不要跨会话复用 `crv-out-*` 目录** | claude-real-video 自动升级 whisper 模型，缓存可能漂移 |
| **不要把"v4.4 重大变更"当正文读** | changelog 是给开发者看的；模型只看当前生效的指令 |
| **不要用 `python <skill-script> --help` 探查 CLI** | 部分 skill 脚本（已知 `reorganize_to_skeleton.py`）的 main() 守卫失效，`--help` 也会执行 main() 副作用并写垃圾到工作目录；改用 `Read` 工具读脚本顶部 argparse 段 |
| **不要在非 蒋太帅 MP3 项目用 `reorganize_to_skeleton.py`** | 该脚本 `SKELETON_CHAPTERS` / 路径 / 关键词表都硬编码 蒋太帅；少壮/老草/其他讲座调用必报 FileNotFoundError 或归类错乱；改写项目级 merge 脚本替代 |
| **不要默认选 ASR 模型** | v4.8 起 Step 0 必做：向用户展示 5 个模型选项 + 时长预估表，用户选定后再执行；默认选 turbo GPU 浪费时间（高精度但慢）或 base CPU 浪费精力（快但低质） |
| **不要把交付物放在 Step 0.5 选定的 `OUT` 之外** | v4.25：`<OUT>/<stem>_cleaned.md` + `<OUT>/<stem>_final.html` 必须同在 `OUT` 根目录；`OUT` 由 Step 0.5 三选一定（① `AV_DIR` ② `AV_DIR/<首个音视频名>` ③ `AV_DIR/output`）；中间件一律进 `AV_DIR/tmp/` |
| **不要跳过 Step 0 / Step 0.5 直接开始 ASR** | 新会话首问 2 步：Step 0 选 ASR 模型 + 时长预估；Step 0.5 三选一定 `OUT`（① 同目录 ② 同名子目录 ③ `output`）；用户决策后再执行 |
| **不要混淆 INPUT_STEM 与 OUTPUT_STEM** | `INPUT_STEM` = 音视频文件名；`OUTPUT_STEM` = 交付文档文件名；选项②时二者相同，选项①③时 `OUTPUT_STEM` 单独确认（别用音频流水号 `01.第一天上午` 当文档名） |
| **不要在 H1 标题下保留文档元描述（"本文档由视频转录净化整理..."）** | v4.10 必查（NO-DOC-META-HEADER）：元描述是冗余信息，最终读者关心内容不是元数据；2026-08-10 边界标品任务首版 H1 下出现 1 段 90 字符元描述是反例，必须删除 |
| **不要在正文保留"学员/讲师/主讲导师/大力老师"等人称角色** | v4.10 必查（NO-ROLE-PERSONA）：通用角色化润色是核心原则，"案例店铺/商家/运营团队/某案例"替代人称；2026-08-10 边界标品任务 11 处"学员"用法全部需要润色是反例；例外：直接引用讲师原话（带引号）可保留 |
| **不要用"有学员提出/学员问/Q："作为问答体例开头** | v4.10 必查（FAQ-PATTERN）：统一用 "FAQ：" 开头；2026-08-10 边界标品任务 1 处"有学员提出：新店铺..."改为 "FAQ：新店铺..." 是反例修复示范 |
| **不要在 markdown 引用图片路径用反引号（`img/xxx.jpg`）** | 渲染会变成 `<code>` 而非 `<img>`；改用真正的图片语法 `![alt](img/xxx.jpg)`；2026-08-10 边界标品任务 5 张关键帧笔记初始用反引号导致 verify_html 不识别 `<img>` 是反例 |
| **不要绕过 `memory_guard` 直接 `subprocess.run` 跑音视频处理** | 本机被 ffmpeg 打死过 4 次（单进程提交 99~107 GB，系统 commit limit 被打穿，dwm / 输入法 / 远程控制连锁死）；上限必须由内核在**分配点**强制，`CREATE_SUSPENDED → AssignProcessToJobObject → NtResumeProcess` 零竞态（`references/memory-safety.md`） |
| **不要在长音视频上裸跑「先看看会怎样」** | 危险形态是**间歇性**的（8 次炸 1 次）；采样监控（20 ms 轮询 + 6 GB 就杀）拦不住分配风暴；先跑预算检查（`estimate_asr_peak_mb`），超了换小模型或分段 |
| **不要用 `text=True` 却不指定 `encoding` 读子进程输出** | 本机 locale 是 cp936(GBK)，子进程输出里一个 GBK 非法字节就让读取线程抛 `UnicodeDecodeError`；必须 `encoding="utf-8", errors="replace"` |
| **不要在 LLM 后端不可用时假装跑完了** | `call_vision` 后端不可用会抛 `LLMBackendError`；若你绕过了它，净化步骤会 fail-soft 保留原文，交付一份**没净化过**的 cleaned.md 且全程无报错。`verify_all.py` 的 `LLM_STEPS_EXECUTED` 规则就是抓这个的 |
| **不要相信「流水线 exit 0 = 质量达标」** | exit 0 只说明没崩；质量判据是 `verify_all.py` 全部 PASS + `regression_test.py` 通过 |
| **不要在 crop_box 已目视校准后还留着 5% 内缩** | 5% 内缩是给未校准的 LLM 坐标兜底的；坐标已人工量过就传 `--inset-pct 0`，否则整页 PPT 表格会被切掉整列（实测） |
| **不要对任意文档直接跑 `post_pass_terms.py`** | 它的规则表 `safe_replacements_2.json` 来自某个具体项目，含 `心里→新客` 这类**无上下文**规则，会把正常中文改错；且脚本原先只认技能自带的 `day{N}/` 目录。现在用 `--file <md> --dry-run` 先看命中再决定 |

## 任务识别与路由

| 输入/请求 | 首先读取 | 条件读取 |
|---|---|---|
| **任何 long-doc 任务启动前** | `references/启动清单.md` | — |
| **音视频端到端流程（mp3/mp4 → HTML）** | `references/av-end-to-end-checklist.md` | 含 13 步 + 时间预算 + 反模式清单（v4.6 蒋太帅任务复盘沉淀，v4.7 补 L1/L3 防线步骤）**+ `references/memory-safety.md`（v4.22：内存硬上限红线，必读）**|
| **音视频（.mp3/.m4a/.wav/.mp4/.mkv/.mov/...）** | `references/phase-0-asr.md` | 视频同时读 `references/image-pipeline.md`（关键帧节）。**v4.4 起主路径调 `claude-real-video`**（`crv` 视频 / `crv-audio` 音频），whisper 降为兜底。**v4.7 起术语纠错走 L1/L2/L3 三层防线**（详见 `references/phase-0-asr-term-injection.md`）**v4.22 起：所有音视频子进程必须走 `scripts/memory_guard.py`，跑之前先过预算检查**|
| `.doc/.docx/XMind` 原始输入 | `references/phase-0-input.md` | 含图片时 `references/image-pipeline.md` |
| 视频关键帧（已有 `frames/` 子目录）| `references/image-pipeline.md`（视频关键帧节）| 配合转录文本时 `references/phase-1-purification.md` |
| 单份长文档净化 | `references/phase-1-purification.md` | Step 2 先读 `references/content-rules.md`（直播/培训转录）再读 `references/purification-prompt.md`；含图片再读 `image-pipeline.md` |
| 多份已净化 Markdown 合并 | `references/phase-2-merge.md` | `references/qa-gates.md`、相关 `references/gotchas.md` |
| **已合并文档结构重排（H3 过多 / 需要两级骨架）** | `references/phase-2.5-restructure.md` | `scripts/restructure_outline.py`、`references/qa-gates.md`（Phase 2.5 节）|| 最终输出 HTML 渲染 | `references/phase-3-render-html.md` | `references/image-pipeline.md`、`scripts/verify_html.py` |
| 多份独立文档逐份处理 | `references/batch-processing.md` | 当前文档对应 Phase reference |
| 验收失败或异常 | `references/qa-gates.md` | 按错误类型读 `references/gotchas.md` |
| 维护 skill 或复盘 | `references/maintenance.md` | 必要时读 `lessons.md` |

## 规约与验证（必读）

> **本 skill 所有规约的单一真相源：`references/规约清单.md`。**

每次 long-doc 任务**结束前必须**：

```bash
python scripts/verify_all.py <output.md>     # 跑完整规约校验
python scripts/regression_test.py            # 历史案例回归
```

任意一条不通过 = 任务未达标。`verify_html 6/6 PASS` ≠ 达标，必须也通过 `verify_all`。

各规约剥离脚本（LLM 驱动，不用纯 regex）：

| 脚本 | 规约 | 输入 → 输出 |
|---|---|---|
| `scripts/strip_lecturer_preamble.py` | NO-LECTURER-PREAMBLE | md → md（LLM 改写铺垫） |
| `scripts/strip_asr_terms.py` | ASR-TERM-FIX / TERMS-OK | md → md（rule-based） |
| `scripts/strip_nested_numbering.py` | NO-NESTED-NUMBERING | md → md（regex） |
| `scripts/renumber_headings.py` | NUMBERING-* | md → md（已有） |
| `scripts/asr_transcribe.py` | ASR-PRESENCE / ASR-LANG（兜底） | 音视频 → md（whisper.cpp 路径，claude-real-video 不可用时降级） |
| `scripts/transcribe_via_crv.py` | ASR-PRESENCE / ASR-LANG（v4.4 主路径） | 音视频 → md（调 `claude-real-video` 的 `crv` / `crv-audio`，输出兼容格式） |
| `scripts/validate_terms.py` | TERMS-OK | md → md（术语校验 + 报告，**L2 防线**）|
| `scripts/extract_top_terms.py` | （v4.7 新增；**L1 防线**） | `references/电商术语表.md` → `asr_top_terms.txt`（Top-K 97 条术语，~400 chars）|
| `scripts/post_pass_terms.py` | （v4.7 新增；**L3 防线**）| cleaned.md → cleaned.md（上下文安全替换，10 条规则：心客→新客/欧→O/达木→达摩/打爆→打散）|
| `scripts/extract_skeleton.py` | （v4.4 新增；hierarchical pipeline） | raw.md → 全文骨架 md（注入 chunk prompt） |
| `scripts/last_section_reprocess.py` | LAST-SECTION-COMPLETE / H3-NAMING-CONSISTENT / LOGIC-CHAIN | cleaned.md → cleaned.md（末段独立 LLM 修复） |
| `scripts/per_section_stats.py` | （诊断工具） | cleaned.md → 章节保留率 + 5 类资产报告 |

## 三段式总流程

```
Phase 0 输入准备（按后缀分桶）
  ├── 文本类(.docx/.xmind/.md)  → Step 0.5/0.6 现有路径
  └── 音视频类(.mp3/.mp4/...)   → Step 0.4 claude-real-video（v4.4 主路径）
                                   → Step 0.4.1 L1 ASR 注入（v4.7，opt-in：调 faster-whisper `initial_prompt` 用 `asr_top_terms.txt`）
                                   → Step 0.4.5 L2 电商术语校验（validate_terms.py）
                                   → Step 0.7 视频抽帧（crv 已含，无需再跑）
                ↓
Phase 1 单文档净化（hierarchical pipeline；v4.4 新增 Step 1.5 骨架 + 2.5 per-section + 2.6 末段）
                                   → Step 1.99 L3 post-pass（v4.7 必跑：post_pass_terms.py，cleaned.md + final.html 都跑）
                ↓
Phase 2 多文档合并 → Phase 2.5 结构重排（v4.24）→ Phase 3 渲染 HTML
                                                    ↓
                                         scripts/verify_all.py（强制 27 条规约）
                                                    ↓
                                         scripts/regression_test.py（强制）
                                                    ↓ 全部通过
                                                    产物回写源目录
```

每个阶段入口都在对应的 reference；阶段之间不要跳过 `qa-gates.md`。

## 核心不变量

- **信息量守恒**：净化可重写语句，但禁止减少独立信息单元；
- **禁止编造**：不添加原文没有的章节、案例、数据；
- **产物回写源目录**：`.final.html` 与 `img/` 子目录放在源文件所在目录，不写入 skill 安装目录；
- **不输出 .docx**：最终交付物为可独立打开的 HTML；
- **净化统计仅在会话总结**：4 类噪声清理估算、保留率、保留率说明等**不写入 HTML**；
- **图片若存在则处理**：抽取 → OCR → 冲突时以 OCR 为准 → 必要时生成新配图；视频关键帧按 `image-pipeline.md` 视频节再生；
- **讲者铺垫 = 0**：所有"讲师认为/说/指出/..."直接改写为观点陈述，不得保留主语（LLM 驱动，详见 `scripts/strip_lecturer_preamble.py`）。
- **讲师自我介绍/资历 = 0（v4.9 新增）**：H2/H3/H4 标题禁止出现 `讲师资历 / 讲师简介 / 讲师介绍 / 自我介绍 / 讲师背景` 等黑名单模式；讲师开场/收场的个人介绍段必须删除整段，不得保留（verify 强制 `H3-LECTURER-BIO`）。

## 必做清单（v4.9.1 合并后强制 4 步）

合并完成 → 渲染 HTML 前，**必做这 4 步**（缺一步视为任务未达标）：

1. **讲师铺垫清理**：跑 `scripts/strip_lecturer_preamble.py` 改写铺垫句式；检查 H2/H3/H4 标题是否含讲师自我介绍/资历类黑名单词（`讲师资历 / 讲师简介 / 自我介绍` 等），命中则**删除整段**
2. **冗余次级标题合并**：检查 H3/H4 下是否只挂 1 个次级标题且自身无引言段；命中则**合并**（删 H3 升级其唯一 H4 为 H3，或删加粗子标题并入 H4）
3. **总结与行动建议章节**：在 cleaned.md 末尾新增 `## N 总结与行动建议` H2（N = 当前 H2 计数 + 1），必须含 3 段：
   - **N.1 全文要点回顾**：用 bullet list 总结前 N-1 个 H2 章节的核心要点（每章 1 个 bullet）
   - **N.2 可执行行动清单**：表格形式（`阶段 / 关键动作 / 量化指标` 3 列），按时间顺序拆解
   - **N.3 决策流程图**：用 `因为 ... 所以 ...` 逻辑链列出决策要素，含 `1./2./3.` 编号
4. **培训广告章节删除（v4.9.1 新增）**：检查 H2 标题/正文是否含培训广告类关键词（陪跑 / 服务体系 / 年费 / 高客单服务 / 1v1 辅导课程 / 一对一辅导课程 / 线下诊断服务 / 工程师协助搭建 / 课程原价 / 扫码加入 等），命中则**整章删除**（对应 `TRAINING-AD-CHAPTER` 规约自动检测，详见 `references/规约清单.md`）
5. **verify 全套校验**：跑 `python scripts/verify_all.py <cleaned.md> --raw-md <transcript.md> --html <final.html>` 确认所有规约（含 v4.9 `H3-LECTURER-BIO` + `NO-SINGLE-SUBHEADING` + v4.9.1 `TRAINING-AD-CHAPTER` 等 30 条）PASS

## 项目级 wrapper 推荐（v4.9.1 新增）

**背景**：`scripts/purify_v4_4_hierarchical.py` 即使 prompt 写"每 chunk 1 H2"，LLM 仍倾向产出多 H2；强行降级会破坏 LLM 反映的"自然子主题"结构。**蒋太帅之外的项目**应使用项目级 wrapper。

**已沉淀的 wrapper**（放 `references/project_wrappers/`）：
- **`_purify_strict.py`**：项目级 strict purify，prompt 硬约束（必须用骨架 H2 名、每 H3 ≥ 2 段正文、H3 编号与 H2 一致、禁止 `## 第N章...` 风格、禁止加粗子标题替代 H3/H4）。阿不项目实测：7 块重跑产出 0 空 H3 + 0 编号错位。
- **`_merge_parts_v2.py`**：项目级 merge v2，**不做 H2→H3 降级**（信任 LLM 结构），只做 H1 加总 + "第N章"前缀 + 检测空 H3 合并。

**何时使用**：
- 默认：新会话启动 long-doc 任务，**直接用项目级 wrapper**，不用 skill 原版 `purify_v4_4_hierarchical.py` + 已废弃的 `_merge_parts_to_skeleton.py`
- 例外：蒋太帅项目仍可用原版（因为骨架短 + 7 章恰好对齐）

**调用示例**：
```bash
PYTHONIOENCODING=utf-8 python references/project_wrappers/_purify_strict.py \
    # 自动读 AV_DIR/tmp/<stem>_skeleton.md + AV_DIR/tmp/parts/part*.md,输出 part*_strict.md
PYTHONIOENCODING=utf-8 python references/project_wrappers/_merge_parts_v2.py \
    # 自动合并 part*_strict.md → <stem>_cleaned.md
```

**详见 `references/gotchas.md` "信任 LLM 结构,不要强行 H2→H3 降级" 段**

## 通用质量门与停止条件

```
执行 → 验收 → 通过则继续
             ↓
          失败则最多修正 2 次
             ↓
      连续 3 次同类失败 → 暂停并请求人工介入
```

保留率仅作诊断指标；若低于 55% 必须解释原因并复核 5 类实质资产完整性。HTML 渲染失败立即停止并报告依赖缺失；图片生成模型不可用时跳过该张配图但不阻塞整体交付，并在最终报告中列出缺失图位。

## 高优先级 gotchas（短版）

- 输出文件名禁止 `merged_document_final.docx` 等通用名，使用文章标题或 `<源名>_final.html`；
- 标题降级必须用占位符回填两步法，禁止连续 `re.sub` 同前缀；
- `Set-Content -Encoding UTF8` 等价于带 BOM；写文件请用字节级或显式 `UTF8Encoding($false)`；
- 终端输出含 emoji 时先设 `PYTHONIOENCODING=utf-8`；
- 跨平台含中文路径，shell 调用 Python 推荐先 `cd` 源目录再执行；
- **讲者铺垫不能用纯 regex**：变体太多，LLM 语义处理才稳定（见 `scripts/strip_lecturer_preamble.py`）；
- **术语纠错不能用单一防线**：L1（ASR prompt）+ L2（validate_terms）+ L3（post_pass_terms）缺一不可，老草任务复盘证实 LLM 净化会放大而非纠正错词；
- **新术语加进术语表时**：必须同步更新 `scripts/post_pass_terms.py` 的 `SAFE_REPLACEMENTS` 表（一条新术语 = 一条新替换规则），否则下次任务该错词仍会漏网；
- **不要跳过 `_post_terms_fix` 直接 `_purify_smooth`**（v4.16 新增）：LLM 是错词放大器（v4.7 老草任务实证），必须先规则替换 ASR 错词（石木床→实木床、权占→全站等），再让 LLM 通顺化
- **不要让 `_purify_smooth` 单块 > 8K chars**（v4.16 新增）：LLM 任务过重会"自由发挥"编造通用模板（如"价格带布局的重要性"、"总结与展望"），实测智篆 2026-09-17 项目首版 v7 跑了 26 块，每块编造了不存在的章节；必须按 H2 切分 + 长 H2 按 H3 再切
- **不要用 `SMOOTH_PROMPT` 处理跨章节合并**（v4.16 新增）：每 H2 章节必须独立调 LLM，否则 LLM 会编造跨章节内容
- **项目级 ASR 错词规则按"长词在前、短词在后"顺序**（v4.16 新增）：避免短词误匹配（如"权占"必须在"权值"前替换）。详见 `scripts/_post_terms_fix.py`（skill 标准 + 数据驱动 YAML 配置）
- **PURIFY_PROMPT 不删时间戳是历史 bug**（v4.16 文档化）：原 prompt "保留时间戳行格式"是 v4.5 之前的设计 bug，LLM 输出仍可能保留 `[XXXXXs → XXXXXs]` 前缀；`_purify_smooth` 强制删除，但要在 verify 后做最终检查（`grep -c "^\["` 应为 0）
- **不要用 `_purify_smooth` 单步解决所有问题**（v4.16 新增）：通顺化只能改写原文，不会修复 LLM 删减过度的章节。如果 verify NO-INFO-LOSS FAIL（CJK 保留率 < 35%），需手动 enrich 第 1 章和末段补 5 类资产

更细的失败模式见 `references/gotchas.md`。

## 工作目录与产物布局（v4.25 改版）

三个目录变量，**先定后跑**。Step 0.5 必问，详见 `references/av-end-to-end-checklist.md` § Step 0.5。

| 变量 | 取值 | 谁决定 |
|---|---|---|
| `AV_DIR` | 第一个音视频所在目录 | 客观事实,自动取(**不是** CWD,**不是** skill 安装目录) |
| `OUT` | 交付目录 | **Step 0.5 三选一**:① `AV_DIR` 本身 ② `AV_DIR/<第一个音视频名>`(默认) ③ `AV_DIR/output` |
| `TMP` | `AV_DIR/tmp` | 固定,**无选项** |

### 目录形状

```
AV_DIR/
├── 01.第一天上午.mp3                 ← 用户原始素材（不动）
├── tmp/                            ← 全部中间文件与脚本（固定）
│   ├── <stem>_transcript_raw.md
│   ├── <stem>_transcript.md
│   ├── <stem>_terms_report.json
│   ├── <stem>_skeleton.md
│   ├── parts/
│   ├── crv-out-*/
│   ├── asr_corrections.yaml        ← 项目级错词表
│   └── *.py                        ← 一次性脚本 / 补丁 / 审计报告
└── <OUT>/                          ← 交付目录（三选一）
    ├── <stem>_cleaned.md           ← ⭐ 净化主产物
    ├── <stem>_final.html           ← ⭐ 最终交付
    └── img/                        ← 配图（Phase 1.8 跑过才有）
```

### 两条硬约束

1. **交付目录只放交付物**:`<stem>_cleaned.md` / `<stem>_final.html` / `img/`。任何 `.json` / `.py` / `_raw` / `_transcript` / `_skeleton` / `crv-out-*` / `parts/` 出现在 `OUT` 根目录即违规。
2. **中间文件与脚本一律进 `TMP`**：包括临时 markdown、审计报告、分组计划 JSON、补丁脚本、ASR 产物、关键帧目录。

### 旧文档里的路径怎么读

v4.24 及更早的示例把 `output/` 写死。v4.25 起按下表读：

| 旧写法 | 新读法 |
|---|---|
| `output/<stem>_cleaned.md`、`output/<stem>_final.html` | `<OUT>/<stem>_cleaned.md`、`<OUT>/<stem>_final.html` |
| `output/test-crv2/...`(中间产物) | `<TMP>/...` |
| `output/crv-out-*`、`output/parts/` | `<TMP>/crv-out-*`、`<TMP>/parts/` |

用户选 ③ 时 `<OUT>` 物理上就叫 `output/`，旧写法恰好仍然成立 —— 三种选择只是目录名不同，流程完全一致。

**verify_all.py 调用**:

```bash
python <SKILL>/scripts/verify_all.py <OUT>/<stem>_cleaned.md \
  --raw-md <TMP>/<stem>_transcript.md \
  --html <OUT>/<stem>_final.html
```

**regression_test.py**：蒋太帅 case 默认 path 指向源目录根的 `<stem>_numbered.md`(兼容旧 `test_cases.json`)；按 v4.25 收纳时把 numbered.md 放到它期望的位置即可，不改脚本。

完成时必须向用户报告三个绝对路径(`AV_DIR` / `OUT` / `TMP`)、`TMP` 里关键中间件清单、`<OUT>/img/` 中已生成的图片清单,并附上 `verify_all.py`、`verify_html.py`、`regression_test.py` 的输出。

## 实现状态说明（2026-10-12 重建)

> **本节用途**:让用户在加载 skill 时,**5 秒内**看清 SKILL.md 描述的脚本哪些是真有、哪些只是 changelog 提及。当脚本未实现时,本节给出**当前 LLM 兜底方案**。

### ✅ 已实现脚本(22 个,可直接调用)

| 脚本 | 来源 | 验证方式 |
|---|---|---|
| `scripts/doc_to_md.py` | v3.8 字节级继承 | 单元测试 |
| `scripts/markdown_to_docx.py` | v3.8 字节级继承 | `validate_skill.py` |
| `scripts/markdown_to_html.py` | v3.8 字节级继承 | `verify_html.py` |
| `scripts/generate_image.py` | v3.8 字节级继承 | 单元测试 |
| `scripts/ocr_images.py` | v3.8 字节级继承 | 单元测试 |
| `scripts/renumber_headings.py` | v3.8 字节级继承 | `tests/test_renumber.py` |
| `scripts/test_renumber.py` | v3.8 字节级继承 | 自跑 |
| `scripts/validate_skill.py` | v3.8 字节级继承 | 自跑 |
| `scripts/verify_docx.py` | v3.8 字节级继承 | 自跑 |
| `scripts/verify_html.py` | v3.8 字节级继承 | 自跑 |
| `scripts/xmind_to_md.py` | v3.8 字节级继承 | 单元测试 |
| `scripts/asr_faster_whisper.py` | v4.x 增量(2026-09-28) | 单元测试 |
| `scripts/extract_terms.py` | v4.x 增量(2026-09-28) | 单元测试 |
| `scripts/fix_bad_extract_terms.py` | v4.x 增量(2026-09-28) | 单元测试 |
| `scripts/post_pass_terms.py` | v4.x 增量(2026-09-28,**简化版**) | 自跑 |
| `scripts/safe_replacements_2.json` | v4.x 增量(2026-09-28) | 配 post_pass_terms.py |
| `scripts/utils.py` | v4.x 增量(2026-09-28) | 跨脚本共用 |
| `scripts/verify_all.py` | v4.x 增量(2026-09-28,**仅 3 项**) | 自跑 |
| `scripts/_crop_insert_frames.py` | v4.x 增量(2026-09-29,Phase 1.8 Stage 3) | `tests/test_crop_insert.py` |
| `scripts/_stage1_score.py` | v4.x 增量(2026-09-29,Phase 1.8 Stage 1) | `tests/test_crop_insert.py` |
| `scripts/_stage2_decide.py` | v4.x 增量(2026-09-29,Phase 1.8 Stage 2) | `tests/test_crop_insert.py` |
| `scripts/_llm_vision.py` | v4.x 增量(2026-09-29) | 跨脚本共用 |

### ⚠️ SKILL 描述但**未实现**的脚本(18 个,LLM 兜底)

> 这些脚本在 SKILL.md 主体 / 规约表 / Gotchas 中被引用,但 `scripts/` 下没有对应文件。
> 当前由主代理或子代理的 **LLM 直接执行**相应步骤兜底(不阻塞交付,只是不可复用)。

| 脚本 | SKILL 引用位置 | LLM 包底方案 | 优先级 |
|---|---|---|---|
| `_post_terms_fix.py` | v4.16 changelog | **P0 已补齐**(2026-10-12) | P0 ✅ |
| `purify_v4_4_hierarchical.py` | v4.4 changelog | **P1 已补齐**(2026-10-12) | P1 ✅ |
| `_purify_smooth.py` | v4.16 changelog | **P1 已补齐**(2026-10-12) | P1 ✅ |
| `transcribe_via_crv.py` | v4.4 changelog | **P1 已补齐**(2026-10-12) | P1 ✅ |
| `extract_skeleton.py` | v4.4 changelog | **P2 已补齐**(2026-10-12) | P2 ✅ |
| `per_section_stats.py` | v4.4 changelog | **P2 已补齐**(2026-10-12) | P2 ✅ |
| `regression_test.py` | 必跑命令 | **P2 已补齐**(2026-10-12) | P2 ✅ |
| `strip_lecturer_preamble.py` | 规约表 | **P2 已补齐**(2026-10-12) | P2 ✅ |
| `strip_role_persona.py` | 规约表 | **P2 已补齐**(2026-10-12) | P2 ✅ |
| `strip_nested_numbering.py` | 规约表 | **P2 已补齐**(2026-10-12) | P2 ✅ |
| `check_no_markdown_corruption.py` | v4.12 changelog | **P2 已补齐**(2026-10-12) | P2 ✅ |
| `fix_bad_extract_terms_inline.py` | v4.12 changelog | **P2 已补齐**(2026-10-12) | P2 ✅ |
| `strip_asr_terms.py` | 规约表 | **P2 已补齐**(2026-10-12) | P2 ✅ |
| `last_section_reprocess.py` | v4.4 changelog | **P2 已补齐**(2026-10-12) | P2 ✅ |
| `_pre_merge_semantic_check.py` | v4.15 changelog | **P2 已补齐**(2026-10-12) | P2 ✅ |
| `asr_quality_check.py` | v4.11 changelog | **P2 已补齐**(2026-10-12) | P2 ✅ |
| `glossary_expand.py` | v4.11 changelog | **P2 已补齐**(2026-10-12) | P2 ✅ |
| `build_per_lecture_asr_corrections.py` | v4.11 changelog | **P2 已补齐**(2026-10-12) | P2 ✅ |

**全部 18 个未实现脚本均已补齐 ✅**

### ⚠️ SKILL.md 引用但**未实现**的 references

> 2026-10-12 全部补齐 ✅

### ⚠️ `verify_all.py` 当前实现 12 项校验

| 已实现(12 项) | SKILL.md 描述 |
|---|---|
| FRONTMATTER / LINKS / CJK_RATIO | 30 条规约校验(基础 3 项) |
| NO_DOC_META_HEADER (v4.10) | |
| NO_DOC_META_BLOCKQUOTE (v4.17) | |
| H3_LECTURER_BIO (v4.9) | |
| NO_SINGLE_SUBHEADING (v4.9) | |
| TRAINING_AD_CHAPTER (v4.9.1) | |
| NO_NESTED_NUMBERING (v4.4) | |
| H4_PER_H3_MAX (v4.4) | |
| H4_TOTAL_MAX (v4.4) | |
| NO_ORPHAN_H3 (v4.4) | |

LLM-driven 规约(NO-LECTURER-PREAMBLE / NO-ROLE-PERSONA-EXTENDED 等)仍由 Phase 1.7 / strip_*.py 负责,verify 暂跳过。
完整 30 条规约定义见 `references/规约清单.md`。

**补齐路线图**:见 `task.md` P0/P1/P2 三段;每补齐一个脚本立即跑单元测试 + verify_all.py。

### ⚠️ SKILL.md 引用但**未实现**的 references

> 2026-10-12 全部补齐 ✅

### ⚠️ `verify_all.py` 当前实现 12 项校验(2026-10-12 扩展)

| 已实现(12 项) | SKILL.md 描述 |
|---|---|
| FRONTMATTER / LINKS / CJK_RATIO | 30 条规约校验(基础 3 项) |
| NO_DOC_META_HEADER (v4.10) | |
| NO_DOC_META_BLOCKQUOTE (v4.17) | |
| H3_LECTURER_BIO (v4.9) | |
| NO_SINGLE_SUBHEADING (v4.9) | |
| TRAINING_AD_CHAPTER (v4.9.1) | |
| NO_NESTED_NUMBERING (v4.4) | |
| H4_PER_H3_MAX (v4.4) | |
| H4_TOTAL_MAX (v4.4) | |
| NO_ORPHAN_H3 (v4.4) | |

LLM-driven 规约(NO-LECTURER-PREAMBLE / NO-ROLE-PERSONA-EXTENDED 等)仍由 Phase 1.7 / strip_*.py 负责,verify 暂跳过。
完整 30 条规约定义见 `references/规约清单.md`。

---

## 运行时差异

Claude Code / Codex / 弱 runtime 之间的工具与路径差异见 `references/runtime-compatibility.md`；普通任务无需加载。

## v4.17 新增 Gotchas（4 条）

- **禁止用脚本 regex 处理"讲师/学员"角色前缀**：regex 无法识别"讲师总结"是否在引号内（v4.10 规则例外），无法区分"讲师"作名词（讲师证）vs 作主语（讲师指出）。Phase 1.7 必须由 LLM 调用处理，不允许 `sed 's/讲师//g'` 类批量替换。详见 `references/phase-1.7-semantic-pass.md`。
- **禁止用 sed/awk 批量替换 ASR 同音错词**：v4.7 老草任务实证 LLM 是错词放大器，v4.16 智篆任务证实 dict 替换后 LLM 仍可能引入新错词。错词修复必须在 LLM 净化**之前**用 `_post_terms_fix.py` 字典替换，**之后**用 LLM 二次语义校验，禁止跳过 LLM 这一关直接靠 regex。
- **禁止跳过 Phase 1.7 直接 Phase 3**：v4.18 起 6 条硬规约（NO-DOC-META-BLOCKQUOTE / NO-ROLE-PERSONA-EXTENDED / HIERARCHICAL-NUMBERING / NO-ORPHAN-WORDS / NO-META-LECTURE-PREAMBLE-IN-SECTION / NO-SINGLE-LINE-BLOCKQUOTE-CALLOUT）全靠 Phase 1.7 LLM Semantic Pass 守。跳过此步 → cleaned.md 直接含角色污染 / 无编号 / 错词残留 / 转录元数据 / 讲师铺垫段 / 单行 blockquote，verify_html.py 不会 catch 这些。
- **禁止用 markdown 渲染器把 `<hr>` 当成段落**：markdown_to_html.py 不识别 `---` 为 HR，会渲染成 `<p>---</p>`，触发 verify_html.py 的 frontmatter artifact FAIL `17b`。要么删除 `---` 行，要么直接写 `<hr>` HTML 标签，要么用 `===` 替代（部分 markdown 渲染器支持 `===` 作为 H1 下划线，但更稳的是直接删 `---`）。
- **禁止 LLM 优化时"自由发挥"重写内容**：Phase 1.7 LLM Semantic Pass 必须严格按 6 条规约 + 整体质量深化清单执行，禁止新增章节、删除原文没有的总结章内容、把 H2 标题加粗。LLM 是工具不是作者。
- **禁止 LLM 优化时新增单行 `>` blockquote**（v4.18 新增）：LLM 倾向用 `>` 引用块作为视觉强调工具，但单行 blockquote 是视觉噪声（占行高 + 颜色差异小）。视觉强调一律用 `**加粗 inline**` 段落或合并到上下文。例外：多行 `>` box（≥2 行）作为"核心结论 box"是合法的。详见 `references/phase-1.7-semantic-pass.md` 规约 6。
- **禁止 LLM 优化时保留讲师铺垫段**（v4.18 新增）：章节正文内禁止出现课程安排/教学策略/回顾上次/现场写不单独发资料类讲师铺垫。这些是 ASR 转录产物，不增加信息量，应提炼为一句话目标陈述或直接删除。章节标题如"课程说明与本节目标/本节说明/课程概览"应改为实质性标题（如"本节核心结论"）。详见 `references/phase-1.7-semantic-pass.md` 规约 5。

## v4.18 新增 Gotchas（2 条）

- **禁止 LLM 优化时新增单行 `>` blockquote**（v4.18）：LLM 倾向用 `>` 引用块作为视觉强调工具，但单行 blockquote 是视觉噪声（占行高 + 颜色差异小）。视觉强调一律用 `**加粗 inline**` 段落或合并到上下文。例外：多行 `>` box（≥2 行）作为"核心结论 box"是合法的。详见 `references/phase-1.7-semantic-pass.md` 规约 6。
- **禁止 LLM 优化时保留讲师铺垫段**（v4.18）：章节正文内禁止出现课程安排/教学策略/回顾上次/现场写不单独发资料类讲师铺垫。这些是 ASR 转录产物，不增加信息量，应提炼为一句话目标陈述或直接删除。详见 `references/phase-1.7-semantic-pass.md` 规约 5。

## v4.19 新增 Gotchas（3 条）

- **禁止用脚本 regex 强制按时间戳插图**（v4.19 新增）：Phase 1.8 必须用 LLM 语义匹配（Stage 1 OCR-only 猜 H3 → Stage 2 看帧 + ASR 决定 h3_target），时间戳 ±60s 容差不够鲁棒,ASR 错位会插错位置。LLM 看帧 + ASR 上下文才是正解。详见 `references/phase-1.8-frame-crop.md` §11 反模式。
- **禁止跳过 Stage 2 直接用 Stage 1 的 h3_hint**（v4.19 新增）：Stage 1 只看 OCR,可能猜错 H3;Stage 2 看实际帧 + ASR 才决定 h3_target,二者分工不同,合并会丢失精度。`crop_decisions.json` 必须经过 Stage 2 产出,不允许直接拿 `top8.json` 当输入跑 Stage 3。详见 `references/phase-1.8-frame-crop.md` §4.2 h3_hint 与 h3_target 关系。
- **禁止 LLM 把讲师当主题插入**（v4.19 新增）：即使 prompt 强排除讲师/片头/logo,LLM 仍可能误判把讲师头像当主题。`score ≥ 0.65` 是兜底阈值,低于此分数的帧 Stage 3 自动跳过,不插入 cleaned.md。Stage 3 必须包含 caption 非空校验（qa-gates 规则 38）。详见 `references/phase-1.8-frame-crop.md` §12 已知陷阱。

## v4.21 新增 Gotchas（2 条）

- **禁止 LLM 净化产物保留半角标点**（v4.21 新增）：LLM 默认输出英文键盘标点（`,` `;` `:` `.` 等）是默认行为，即便经过 6 条硬规约强制规约，标点仍会回退到半角。**脚本 `normalize_cn_punctuation.py` 是最终兜底，必须跑**。详见 `references/cn-punctuation.md`。

## v4.24 新增 Gotchas（3 条）

- **不要用「绝对条数」卡 H4**（v4.24 新增）：`H4_TOTAL_MAX = 50` 这类与文档规模无关的常量，在 5 万字符文档上合理，在 20 万字符文档上就是「禁止使用 H4」。判据：**任何标题层级的数量上限都必须按文档字符数比例化**（`max(基数, 字符数/每个标题承载字符数)`），否则长文档只会被压成扁平结构。同理 `H4_PER_H3_MAX ≤ 3` 会让「一个 H3 带 4–18 个 H4」这种最自然的讲义结构直接不可能。
- **不要靠 `NO_SINGLE_SUBHEADING` 兜「一个 H3 只挂一个 H4」**（v4.24 新增）：该规则本意是消除冗余层级，但当它是唯一出路时，会把「H3 下只放 1 个 H4」全部判死，逼模型把 H4 提升成 H3。正确做法：允许 H3 带 1..N 个 H4，只在**整篇 H4 极少**或**该 H4 与 H3 完全同义**时才判冗余。
- **场次标签不是标题内容**（v4.24 新增）：ASR 分场转录会在每个 H3 前留 `第二天上午：` 前缀（本项目 431/434 命中）。这是采集痕迹而非信息，必须剥离。但**不要**改成 `> 覆盖：第一天上午` 块引用注记 —— 会直接撞 `NO-DOC-META-BLOCKQUOTE`。溯源写到 `_handoff.md` / `_purge_stats.md` 即可。
- **禁止在标点规范化时破坏 markdown 结构**（v4.21 新增）：`#` 标题 / `-` 列表项 / `|` 表格 / `[](url)` 链接 / `![]()` 图片 / `` ` `` inline code / ` ``` ` fenced code 都必须保留为半角。修复半角反引号替代的常见错误是用 sed/awk 全文替换，会破坏上述结构。必须用行级状态机 + 正则保护。详见 `references/cn-punctuation.md` §三层防护。