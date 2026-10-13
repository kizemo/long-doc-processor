# long-doc-processor · P0/P1-3 完成进度 handoff

**交接日期**: 2026-10-12(本会话)
**承接自**: handoff-2026-10-12.md(P0/P1/P2 计划)
**本次完成**: P0 全部 + P1-3(transcribe_via_crv.py)

---

## 1. 已完成

### P0-1 · SKILL.md 加"实现状态说明" ✅
- 在 SKILL.md "## 运行时差异" 节前插入完整实现状态说明
- 3 个表格:
  - ✅ 已实现脚本(22 个,含校验方式)
  - ⚠️ SKILL 描述但未实现(18 个,带 LLM 兜底方案 + 优先级)
  - ⚠️ SKILL 引用但缺失 references(2 个)
- 用户 5 秒内看清文档-实现 gap

### P0-2 · `_post_terms_fix.py` ✅
- `scripts/_post_terms_fix.py` (~210 行)
- CLI: `python scripts/_post_terms_fix.py <input> <output>`(SKILL v4.16 changelog 签名)
- 优先级:explicit > CWD > output/test-crv2 > builtin
- 自动发现 + 长词在前短词在后排序
- 内置 --selftest(12/12 命中)
- 单元测试 17/17 PASS(覆盖加载/排序/单条规则/上下文边界/链式/wrapper)
- 端到端 18 处替换全部正确

### P0-3 · `references/asr_corrections.yaml` ✅
- 默认 41 条规则(从 SKILL.md v4.16 changelog + post_pass_terms.py + v4.11/13/15/17 changelog 沉淀)
- schema: `[{from: str, to: str, context: str(可选)}]`
- 长词在前短词后(运行时自动重排)

### P1-3 · `transcribe_via_crv.py` ✅
- `scripts/transcribe_via_crv.py` (~280 行)
- 调用 claude-real-video(crv)统一处理音视频
- 输出兼容 `<stem>_transcript.md`(与 asr_faster_whisper.py 输出格式一致)
- 失败兜底:`--no-fallback` 关闭时保留 ERROR transcript.md;默认 fallback 到 asr_faster_whisper.py
- 解析 audio.json / audio.srt / audio.txt 三层降级
- 单元测试 27/27 PASS(覆盖输入检测/时间戳格式/json/srt/txt 解析/优先级/产物目录发现/渲染)

---

## 2. 下阶段必交付(P1-1, P1-2, P2)

### P1-1 · `purify_v4_4_hierarchical.py`(LLM 驱动,需 prompt 设计)
**核心难点**:LLM 即使 prompt 写"1 H2 per chunk"仍会产出多 H2(SKILL Gotcha);
- 8 chunk 切分(每 chunk ≤ 8K chars)
- LLM 调 purification-prompt.md
- 强制 1 H2/chunk(若 LLM 违反,retry + 兜底拆分)
- 骨架对齐(读 `<stem>_skeleton.md` 作 anchor)
- 单元测试覆盖:切分边界/retry 触发/skeleton 校验

### P1-2 · `_purify_smooth.py`(LLM 驱动)
**核心约束**:
- 按 H2 切分(每 H2 独立调 LLM)
- 单块 ≤ 8K chars(超 → 切分到 H3)
- 禁止:LLM 新增内容 / 删原 / 改章节数 / 虚构案例
- 必须清理:时间戳 / 粗口 / ASR 装饰 / 串扰 / 错乱中英俄混杂 / 不通顺短句 / 重复词
- CLI: `python scripts/_purify_smooth.py <cleaned.md> -o <smoothed.md> --workers 3`

### P2-1 · 其他 14 个脚本
详见 task.md P2-1。

### P2-2 · 缺失 references
- `references/av-end-to-end-checklist.md` (~300 行,Step 0/0.5/0.6/0.7 完整 13 步 + 时间预算)
- `references/规约清单.md` (~200 行,30 条规约单一真相源)

### P2-3 · 扩展 `verify_all.py`
- 当前:仅 3 项(frontmatter/链接/CJK)
- 目标:30 条规约全验证
- 重点:H3-LECTURER-BIO / NO-SINGLE-SUBHEADING / TRAINING-AD-CHAPTER / NO-META-LECTURE-PREAMBLE-IN-SECTION / NO-SINGLE-LINE-BLOCKQUOTE-CALLOUT

---

## 3. 当前状态

### 文件统计
```
scripts/         24 个 .py + 1 个 .json + 1 个 .yaml = 26 个文件 (+4: _post_terms_fix.py / transcribe_via_crv.py / asr_corrections.yaml / tests)
references/      18 个 .md(已实现)
tests/           3 个测试文件 (test_crop_insert + test_post_terms_fix + test_transcribe_via_crv)
history/         完整备份(v3.8-optimized + openclaw-base)
task.md          已建立
```

### 测试通过
```
tests/test_post_terms_fix.py       17/17 ✅
tests/test_transcribe_via_crv.py   27/27 ✅ (含 10 subtests)
tests/test_crop_insert.py          (原有,未触动)
合计                              58 passed, 10 subtests passed
```

### 已沉淀到 lessons.md(2026-10-12)
- "`_post_terms_fix.py` + `references/asr_corrections.yaml` 补齐"
- "v4.20 SKILL.md 加实现状态说明节"
- (本次新加,可继续追加 P1-1/1-2/P2 完成经验)

---

## 4. 必读顺序(新会话接力)

1. `handoff-2026-10-12.md` — 背景 + 原 P0/P1/P2 计划
2. **本文件**(`handoff-2026-10-12-p1-progress.md`)— 本会话进度 + 下阶段
3. `task.md` — 当前勾选状态
4. `SKILL.md` 主体(已含"实现状态说明"节)
5. `references/purification-prompt.md` — P1-1 的 prompt 模板
6. `scripts/_post_terms_fix.py` + `transcribe_via_crv.py` — 已补齐脚本参考样式

---

## 5. 避坑提示(本会话发现)

1. **Write YAML 配置后必须 `cat` 自查重复条目**(首次写入心客/打爆 重复 2 次,立即清理)
2. **单元测试边界用例必须实际验证设计意图**(长词在前测试首版"权占 + 占有率"误以为 2 处匹配,实际 re.sub 是非重叠单次扫描)
3. **Python tuple 比较用 Unicode codepoint**(中文 `占` < `重`,影响排序预期)
4. **Windows bash 写 C:\Temp\ 用 `/c/Temp/`(MSYS2 风格)**
5. **`re.sub` 一次扫描找所有非重叠匹配,但只到替换串结束位置继续**(单次扫描机制)
6. **skill 脚本默认配置写在 `references/*.yaml` 而非 `*.yaml.example`**(自动发现路径就有 builtin 兜底,无需 example 副本)
7. **SKILL.md 描述与实际实现的 gap 必须在文档中显式标注**(否则加载时无法判断调用哪个)

---

## 6. 操作纪律(CLAUDE.md 红线,持续遵守)

- 任何删除走 `no-delete-gate.py` 二次确认(本次 0 删除)
- 临时文件写 `/c/Temp/`(本次 `/c/Temp/sample_input.md` + `sample_output.md`)
- 不动 `.claude-mem` / `.claude-flow` / `.codex` / `.copilot` / `.config`
- 不写危险 SQL
- 不 git reset --hard / clean -fd

---

<!-- Generated: 2026-10-12, source: P0 全部 + P1-3 补齐后进度快照 -->
