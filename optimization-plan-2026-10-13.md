# long-doc-processor · 优化方案 v1(2026-10-13)

> **触发**:同步 dev → runtime 后,4 维度综合 review 完成(代码质量 / 稳定性 / 输出质量 / 工作流集成)
> **基线**:39 scripts + 20 references + 19 tests + 282 tests PASSED + runtime 已同步
> **目标**:提升 MD/HTML 输出质量 + 脚本稳定性 + 用户易用性

---

## 0. 综合诊断(4 维度汇总)

| 维度 | 关键问题 | 严重度 |
|---|---|---|
| **稳定性** | `_llm_vision` LLM 无 timeout → 30K 文档卡死;`utils.log` 线程不安全;`strip_*` 全文单次 LLM 超 8K 限制 | 🔴 P0 |
| **输出质量** | `_purify_smooth` prompt 过度宽松(LLM 自由发挥 30%+);`verify_html` 只覆盖 7/30 规约;`check_no_markdown_corruption` 污染词仅 3 条 | 🔴 P0 |
| **工作流** | 无 `run_pipeline.py` 一键入口;D0 净化脚本缺失;必做首问 4 步无强制钩子 | 🟠 P1 |
| **代码质量** | 87 处 `encoding='utf-8'` 重复;23+ 处 argparse boilerplate;heading 正则 5+ 处复制 | 🟡 P2 |
| **可观测性** | 时间预算无埋点;幂等性不保证;跨平台仅 Windows 测 | 🟡 P2 |

**核心症结**:`prompt 给自由度 + verify 不闭环 + fail-soft 静默` 三者叠加 → 规约"知道但守不住"。

---

## 1. 优化总览(分 5 阶段)

| 阶段 | 主题 | 工作量 | 风险 | 收益 |
|---|---|---|---|---|
| **A** | 稳定性骨架(LLM timeout + 线程安全 + safe_llm_call) | 中 | 低 | 🔴 消除 30K 卡死 / 跨 worker 乱行 |
| **B** | 规约闭环(verify_html 扩到 30 条 + check_no_md 污染词扩到 30) | 中 | 中 | 🔴 MD/HTML 真正"可机检" |
| **C** | 输出质量(prompt 收紧 + 切分统一 + strip_* 复用 chunking) | 大 | 中 | 🔴 净化后"真的干净" |
| **D** | 一键入口(run_pipeline.py + preflight_check + D0 脚本) | 大 | 低 | 🟠 用户跑得动 |
| **E** | 可维护性(utils 扩充 + 跨平台 CI + time_budget 埋点) | 中 | 低 | 🟡 长期健康 |

**建议执行顺序**:A → B → C → D → E(每阶段独立可交付、可回滚)

---

## 2. 阶段 A · 稳定性骨架(优先级 P0,建议先做)

### A1. `safe_llm_call` 装饰器(放 `scripts/_llm_vision.py`)

**问题**:
- `client.messages.create()` 无 timeout → API 挂起时 3 worker 全卡死
- `Anthropic()` 每次新建 → 3 worker 即 3 个 HTTP 连接
- LLM 失败/空响应/不合规混在一起,无法分类重试

**设计**:
```python
def safe_llm_call(
    prompt: str,
    *,
    model: str = "claude-sonnet-4-5",
    max_retries: int = 3,
    timeout: int = 120,
    backoff: float = 2.0,
) -> tuple[str, str]:
    """统一 LLM 调用,带 timeout / retry / backoff。

    Returns: (response_text, status)
    status ∈ {"ok", "empty", "timeout", "error", "rate_limited"}
    """
```

**影响范围**:`_post_terms_fix.py` 不受影响(rule-based);其他 6 个 LLM-driven 脚本:`_purify_smooth` / `purify_v4_4_hierarchical` / `strip_lecturer_preamble` / `strip_role_persona` / `last_section_reprocess` / `transcribe_via_crv` 全部改用。

**验证**:每个 LLM 脚本加 mock 测试覆盖 5 种 status 路径。

### A2. `utils.log` 线程安全

**问题**:多 worker 并发 `[smooth] chunk X 失败` 与 `[smooth] LLM 返回空` 交错成 `[smooth] [smooth] chunk chunk X` 乱行,grep 不可用。

**设计**:
```python
import threading
_log_lock = threading.Lock()

def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    with _log_lock:
        print(f"[{ts}] {msg}", file=sys.stderr, flush=True)
```

**影响范围**:`utils.log` 全局替换(已在所有脚本中 import,无 API 变更)。

### A3. 全文单次 LLM 调用修复

**问题**:`strip_lecturer_preamble` / `strip_role_persona` 全文送 LLM,30K 输入超 8K 限制会截断。

**设计**:复用 `_purify_smooth.split_by_h2` + `_purify_smooth.smooth_block` 模式 → 按 H2 chunking + 并发 LLM。

**影响范围**:`strip_lecturer_preamble` / `strip_role_persona` 主体重写,但 CLI 不变。

### A4. `purify_v4_4_hierarchical` MAX_CHARS 硬约束

**问题**:只控 chunk 数,50K 输入最坏单块 12K chars → 3 次 retry 烧光 → 兜底到 `_fallback_alignment`(只换标题,正文未净化)。

**设计**:加 `--max-chars` CLI 参数(默认 8000)+ 切分前 assert 单块 ≤ max_chars。LLM 失败时**写 ERROR 标记到输出**(而非静默返回原文)。

### A5. `transcribe_via_crv` fallback timeout

**问题**:`_fallback_to_faster_whisper` 调 `asr_faster_whisper.py` 无 timeout,whisper 死循环时整条 CRV 包装挂死。

**设计**:`subprocess.run(..., timeout=7200)`(与主路径一致)+ 失败时 exit code 3 区分主路径失败 vs fallback 失败。

**验证**:每条 timeout 改动加 `tests/test_timeout_*.py`(mock subprocess)。

### A6. 静默 `except` 修复

**问题**:`markdown_to_docx.py:858` `except OSError: pass` / `verify_all.py:358` 等 10+ 处静默吞异常。

**设计**:统一加 log 记录 + 在 SKILL.md "高优先级 gotchas" 加一条 "禁止静默 except,必须 log 异常类别"。

---

## 3. 阶段 B · 规约闭环(优先级 P0)

### B1. `verify_html.py` 扩到 30 条规约

**问题**:当前仅 7 项(17/17b/18/19/20/21/22),30 条规约中 23 条无 HTML 层强校验。

**设计**:加 8 个新 verify 函数:
- `verify_NO_ROLE_PERSONA_EXTENDED`:反查 `讲师指出|讲师总结|学员搜索时|学员常见的错误|学员在选品时`
- `verify_HIERARCHICAL_NUMBERING`:H2/H3/H4 编号连续
- `verify_NO_SINGLE_LINE_BLOCKQUOTE_CALLOUT`:单行 `>` 计数
- `verify_H3_LECTURER_BIO`:H2/H3/H4 标题黑名单词(参考 `verify_all.py` 同名函数)
- `verify_TRAINING_AD_CHAPTER`:H2 含培训广告关键词
- `verify_img_size_within_limit`:PIL 读 `<img src>` 文件,check ≤ 200KB + ≤ 800x600
- `verify_no_path_traversal`:img 路径不含 `..`
- `verify_NO_DOC_META_HEADER_BLOCKQUOTE`:H1 下 blockquote 元数据

**验证**:`tests/test_verify_html_extended.py` 覆盖 30 条规则各 1 个 PASS/FAIL sample。

### B2. `check_no_markdown_corruption.py` 污染词扩到 30 条

**问题**:当前仅 3 条(`医疗器械标签/同价位/店铺绩效`),Phase 1.7 规约 26 列出的 ASR 错词(`内幕/解论/摩特图/演书服/...`)全部漏检。

**设计**:`CORRUPTION_TOKENS` 直接抄 `references/asr_corrections.yaml` 41 条,加上从 `references/phase-1.7-semantic-pass.md` 规约 4 抽 NO-ORPHAN-WORDS 模式。

**附加修**:`line.count('|')` 列数算法修正 → `(line.count('|') - 1)`(去除两侧边界)。

### B3. `verify_all.py` 跨文件扫描范围

**问题**:当前扫 `base.rglob('*.md')` 含 references/,references 中含"讲师资历"是合理用法,误报。

**设计**:加 `--target-glob` 参数(默认 `output/**/*.md`),允许只扫 cleaned.md。

### B4. 跨脚本 verify 闭环

**问题**:`_post_terms_fix → _purify_smooth → strip_persona → Phase 1.7 → render` 5 步 LLM,**无任一环节跑 verify_all**。

**设计**:加 `enforce_post_pipeline_verify.sh` 脚本(可作为 verify hook),在每个 strip_* 后跑 `verify_all.py <current.md>` 自动报错。

---

## 4. 阶段 C · 输出质量(优先级 P0)

### C1. `_purify_smooth.py` prompt 收紧

**问题**:允许"同义改写"导致 LLM 自由发挥 30%+ 句意;6 条"禁止"无验证(只有 substring 检查)。

**设计**:
- 禁止"同义改写"改为"只删不改/只重排不重写"
- 加结构化校验段(必输出 verbatim 关键词):
  ```
  请在输出 markdown 末尾,以 HTML 注释形式列出 H2 标题的 verbatim 列表:
  <!-- H2_LIST:
  - 第 1 个 H2 标题原文
  - 第 2 个 H2 标题原文
  ...
  -->
  ```
- 脚本事后 parse H2_LIST 注释,缺则 fail-loud(而非 fail-soft)

### C2. 切分统一

**问题**:`_purify_smooth` / `purify_v4_4_hierarchical` / `last_section_reprocess` / `strip_lecturer_preamble` / `strip_role_persona` 各自有 H2 切分逻辑,不一致。

**设计**:抽 `scripts/chunking.py` 统一:
- `split_by_h2(text) -> [(h2_title, content), ...]`
- `split_oversized_h2(block, max_chars) -> [block, ...]`
- `extract_preamble(text) -> (preamble, body)`
- 5 个脚本 import 此模块

### C3. fail-soft → fail-loud 转换

**问题**:`_purify_smooth` / `purify_v4_4_hierarchical` LLM 失败时静默返回原文,ASR 错词永远卡在这一步。

**设计**:加 `--strict` CLI flag,strict 模式下 LLM 失败时 exit code 2 + 写 ERROR 标记到输出,迫使重跑。

**默认 fail-soft(向后兼容),strict 用于 CI / production pipeline。**

### C4. `_llm_vision.py` 改输出 verbose status

**问题**:LLM 失败时仅 stderr "ERROR: ..." 一行,根因难定位。

**设计**:返回 `(text, status, error_detail)`,status ∈ {ok/empty/timeout/error/rate_limited},error_detail 含 HTTP code / message。

---

## 5. 阶段 D · 一键入口(优先级 P1)

### D1. `run_pipeline.py` 一键脚本

**问题**:无端到端一键入口,用户跑一次需手动串 8+ 条命令。

**设计**:
```bash
python scripts/run_pipeline.py <input.mp4> --output-dir output/test-crv2/
  → 内部跑 Step 0/0.5/0.6/0.7 + Phase 0/1/2/3 + verify_all
  → 失败 exit code 区分阶段(2=Phase 0 fail / 3=Phase 1 fail ...)
  → 写 pipeline_state.json 支持 --resume
```

**集成**:`references/av-end-to-end-checklist.md` 13 步全自动化。

### D2. `preflight_check.py` 必做首问强制钩子

**问题**:Step 0/0.5/0.6/0.7 完全靠 LLM "自我提醒"。

**设计**:`preflight_check.py` 在 transcribe_via_crv.py 启动前调用,检查:
- `OUTPUT_STEM` 已设置
- `output/<OUTPUT_STEM>/` 子目录已建
- Phase 1.8 选项已记录到 `pipeline_state.json`

### D3. `semantic_block_fix.py` D0 净化脚本

**问题**:`av-end-to-end-checklist.md` §2.1 引用此脚本,但 `scripts/` 目录无此文件(13 步流程 Step 2.1 跑空)。

**设计**:LLM-driven + 30 条 default fix + fail-soft。复用 `safe_llm_call` + `chunking` 模式。

### D4. `enforce_post_merge_4steps.py`

**问题**:v4.9.1 必做 4 步(讲师铺垫/冗余次级/总结章/培训广告)全靠 LLM 自觉。

**设计**:`enforce_post_merge_4steps.py` 把 4 步固化成可执行链,verify_all 之前自动跑,FAIL 报红。

### D5. Phase 1.7 / 1.8 orchestrator

**问题**:Phase 1.7 无脚本入口;Phase 1.8 3 阶段无 orchestrator。

**设计**:
- `phase1_7_semantic.py`:per H2 并发 LLM,prompt from `references/phase-1.7-semantic-pass.md`
- `phase1_8_crop_insert.py`:串 `_stage1_score` → `_stage2_decide` → `_crop_insert_frames`,失败跳过不阻塞

### D6. 幂等性 + 断点续跑

**问题**:无 hash / 时间戳,重跑覆盖;失败无法从断点续跑。

**设计**:`pipeline_state.json`:
```json
{
  "stages": {
    "transcribe": {"status": "done", "output": "path.md", "timestamp": "..."},
    "purify": {"status": "pending"},
    "smooth": {"status": "skipped", "reason": "..."}
  }
}
```
`run_pipeline.py --resume` 跳过已 done 的 stage。

### D7. 时间预算埋点

**问题**:SKILL.md "60min 讲座 ~44min" 预估,无 wall-clock 埋点。

**设计**:`time_budget.py --phase` 入口/出口写时间戳,产出 `pipeline_timing.json`。

---

## 6. 阶段 E · 可维护性(优先级 P2)

### E1. utils 扩充

**设计**:新增 8 个工具函数到 `utils.py`:
- `read_file_safely` (已有)
- `write_file_safely` (已有)
- `log` (改线程安全)
- `split_by_h2` (从 `_purify_smooth` 抽)
- `split_oversized_h2` (从 `_purify_smooth` 抽)
- `extract_preamble` (从 `purify_v4_4_hierarchical` 抽)
- `with_locked_log` 装饰器
- `timeit` 阶段耗时埋点

### E2. argparse boilerplate 统一

**设计**:`utils.py` 加 `make_argparser(description, input_help, output_help)` → 23 处重复 boilerplate 收敛。

### E3. heading 正则统一

**设计**:`utils.py` 加 `H1_RE` / `H2_RE` / `H3_RE` / `H4_RE` / `H5_RE` 模块级常量,5+ 处复制收敛。

### E4. 跨平台 CI

**设计**:
- GitHub Actions matrix:`windows-latest` / `ubuntu-latest` / `macos-latest`
- `python -m pytest tests/` 在 3 平台跑通
- `references/runtime-compatibility.md` 扩到含 3 平台差异表

### E5. `simplify` 技能定期 review

**设计**:每发布 v4.x 跑一次 `simplify` 技能对全部 39 脚本 review,沉淀 lessons.md。

---

## 7. 风险评估

| 风险 | 等级 | 缓解 |
|---|---|---|
| LLM prompt 改坏导致输出回退 | 中 | 改前保留原 prompt 在 `_legacy_prompts.py`,加 `--prompt-version` 切换 |
| utils 改动影响所有 39 脚本 | 中 | 改动前全跑 282 tests + 手动 smoke test on 1 个真项目 |
| run_pipeline.py 引入新状态文件 | 低 | 状态文件可关(`--no-state`),向后兼容手工调用 |
| 跨平台 CI 暴露 Windows-only 假设 | 中 | 先用 `runtime-compatibility.md` 列出已知问题,再修 |

---

## 8. 工作量预估

| 阶段 | 脚本数 | 测试数 | 时间预算 | 风险 |
|---|---|---|---|---|
| A 稳定性 | 6 改 | +30 | 4-5h | 低 |
| B 规约闭环 | 2 改 | +20 | 3-4h | 中 |
| C 输出质量 | 5 改 + 1 新 | +15 | 6-8h | 中 |
| D 一键入口 | 4 新 + 3 改 | +25 | 8-10h | 中 |
| E 可维护性 | 10 改 | +10 | 3-4h | 低 |
| **合计** | **~13 新 + 26 改** | **+100 tests** | **24-31h** | - |

**单 session 预算建议**:每阶段 1 session(2-3h),共 5 个 session。**A 必须先做**(消除 30K 卡死是生产阻塞)。

---

## 9. 推荐下次 session 计划

**强烈建议下次 session 优先执行 阶段 A(稳定性)**:
- 风险最低(改动局部,影响小)
- 收益最大(消除最大生产风险:LLM 卡死)
- 改动集中(主要在 `_llm_vision.py` + `utils.py` + 5 个 LLM 脚本改 1 行)
- 单元测试可直接复用 282 个 + 加 30 个

**具体步骤**:
1. 加 `safe_llm_call(prompt, *, model, max_retries, timeout, backoff)` 到 `_llm_vision.py`
2. 改 5 个 LLM 脚本用 `safe_llm_call`(import + 替换)
3. 改 `utils.log` 加 `threading.Lock` + 时间戳
4. 加 30 个 mock 测试覆盖 5 种 status
5. 跑全套 tests,确认无回归
6. 同步 dev → runtime
7. 写 `lessons.md` 沉淀

预计 2-3h 完成。
