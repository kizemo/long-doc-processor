# long-doc-processor 技能优化计划 v2(2026-10-13)

> **整合来源**:
> 1. `optimization-plan-2026-10-13.md`(5 阶段 A/B/C/D/E 方案)
> 2. `handoff-2026-10-13-optimization.md`(4 维度 review + 6+2 子任务)
> 3. `resource-study-report-2026-10-13.md`(13 条跨项目踩坑模式 M-01~M-13)
> 4. `lessons.md`(本项目自跑记录 20+ 条)
> 5. `references/规约清单.md`(30 条规约单一真相源)
>
> **基线**:v4.20 + 39 scripts + 20 references + 19 tests + 282 tests PASSED
> **目标**:v4.21 阶段 A + 阶段 B 完成,330+ tests PASSED,跨项目踩坑模式被显式规避
> **范围**:本计划聚焦 A + B(用户原任务),C/D/E 仅给方向指引

---

## 0. 优先级矩阵(阶段 A 6 项 + 阶段 B 2 项)

| ID | 任务 | 风险 | 收益 | 必做 | 估时 |
|---|---|---|---|---|---|
| **A1** | `safe_llm_call` 装饰器(避 M-01/M-02/M-12) | 低 | 🔴 消除 30K 卡死 | ✅ | 2h |
| **A2** | `utils.log` 线程安全 + stdout reconfigure(避 M-04) | 极低 | 🟠 消除 3 worker 乱行 | ✅ | 0.5h |
| **A3** | `strip_*` 复用 chunking(避 M-13) | 中 | 🟠 30K 输入不超 8K | 推荐 | 2h |
| **A4** | `purify_v4_4` MAX_CHARS 硬约束 + fail-loud(避 M-02) | 中 | 🔴 不再静默返回原文 | 推荐 | 1.5h |
| **A5** | `transcribe_via_crv` fallback timeout + 路径校验(避 M-03) | 低 | 🟠 消除 6h 挂死 | 推荐 | 1h |
| **A6** | 静默 `except` 修复 + gotcha 增条(避 M-02) | 极低 | 🟠 异常可分类 | ✅ | 0.5h |
| **B1** | `verify_html` 扩 30 条(避 M-05/M-06/M-07/M-08/M-09/M-10) | 中 | 🔴 规约真正闭环 | ✅ | 3h |
| **B2** | `check_no_md_corruption` 30 污染词(避 M-11) | 低 | 🟠 ASR 易错扩 10x | 推荐 | 1.5h |

**必做(✅)**:A1, A2, A6, B1 = 4 项
**推荐(顺序可调)**:A3, A4, A5, B2 = 4 项
**总预算**:~12h,2 个 session 完成(每 session ≤2h,符合 CLAUDE.md 红线)

---

## 1. 阶段 A 详细任务(含 M-XX 模式映射)

### A1. `safe_llm_call` 装饰器 ⭐ 必做 ⭐
**位置**:`scripts/_llm_vision.py`(顶层函数,非方法)

**接口设计**(整合 M-01/M-02/M-12 经验):
```python
def safe_llm_call(
    prompt: str,
    *,
    model: str = "claude-sonnet-4-5",
    max_retries: int = 3,
    timeout: int = 120,
    backoff: float = 2.0,
    on_status: Callable[[str], None] | None = None,
    minimal_prompt: str | None = None,  # M-02 兜底
) -> tuple[str, str]:
    """统一 LLM 调用,带 timeout / retry / backoff / status 分流。

    Returns: (response_text, status)
    status ∈ {"ok", "empty", "timeout", "error", "rate_limited"}
    """
```

**status 分流逻辑**(M-02 5 路径):
| status | 处理 |
|---|---|
| `ok` | 返回 text |
| `empty` | 1 次重试,失败 fallback minimal_prompt(M-02) |
| `timeout` | 重试 max_retries 次,最终 exit 2 |
| `error` | 1 次重试,失败 fallback minimal_prompt |
| `rate_limited` | 指数 backoff(`backoff * 2^attempt`),写入 retry log |

**影响范围(5 个 LLM 脚本)**:
- `_purify_smooth.py` 替换直接 `call_vision`
- `purify_v4_4_hierarchical.py` 替换
- `strip_lecturer_preamble.py` 替换
- `strip_role_persona.py` 替换
- `last_section_reprocess.py` 替换
- `transcribe_via_crv.py` failover 调用也用(若 LLM 部分)

**测试**:`tests/test_safe_llm_call.py` 30 个 mock:
- 5 个 status × 5 个脚本 = 25
- + 5 个 edge case(超时/空/minimal_prompt 兜底/无 API key/on_status 回调)

**M-XX 规避**:
- M-01:SKILL_DIR 用 `Path(__file__).parent`,绝不硬编码
- M-02:返回 status 而非 raise,调用方可 5 种分流
- M-12:`Path(input).resolve()` 绝对化(如调用方传文件)

---

### A2. `utils.log` 线程安全 ⭐ 必做 ⭐
**位置**:`scripts/utils.py:43-45`

**设计**(整合 M-04):
```python
import threading
import sys

_log_lock = threading.Lock()

def log(msg: str) -> None:
    """线程安全 log(stderr),Windows 兼容 UTF-8。"""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    with _log_lock:
        print(f"[{ts}] {msg}", file=sys.stderr, flush=True)

def configure_stdout_utf8() -> None:
    """M-04:Windows terminal 默认 GBK,reconfigure 避免 UnicodeEncodeError。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
```

**调用约定**:所有脚本 `if __name__ == "__main__": configure_stdout_utf8()`(一次)
**影响范围**:全 39 脚本,0 API 变更,直接 import 即可
**测试**:`tests/test_utils_concurrent.py` 1 个并发 log 测试(2 thread × 100 行不交错)

---

### A3. `strip_*` 复用 chunking 模式
**位置**:`scripts/strip_lecturer_preamble.py` + `scripts/strip_role_persona.py`

**设计**:
- 抽 `scripts/chunking.py`:`split_by_h2(text) -> [(h2_title, content), ...]`(从 `_purify_smooth` 抄)
- `strip_*` 主体重写:按 H2 chunking + 并发 LLM(safe_llm_call)
- CLI 签名不变(`<input> <output>`)
- `--max-chars` 默认 8000,超长 H2 按 H3 再切

**M-XX 规避**:
- M-13:直播录屏可加 `ffmpeg_extract_keyframes` 作为可选前置(SKILL.md gotcha 加条)

**测试**:`tests/test_strip_chunking.py` 现有 4 tests 改用 mock 验证 chunking + LLM 并发

---

### A4. `purify_v4_4_hierarchical` MAX_CHARS 硬约束 + fail-loud
**位置**:`scripts/purify_v4_4_hierarchical.py`

**设计**(M-02 衍生):
- 加 `--max-chars` CLI 参数(默认 8000)
- 切分前 `assert single_block <= max_chars`,否则 raise(而非 retry)
- LLM 失败时**写 ERROR 标记到输出** + exit 2(而非静默返回原文)
- 新增 `--strict` flag,strict 模式 fail-loud,默认 fail-soft(向后兼容)

**影响**:`main()` 函数 + `purify_chunk` 内部

**测试**:`tests/test_purify_max_chars.py`:
- 超 max_chars 输入 → raise
- LLM 失败 + --strict → 写 ERROR + exit 2
- LLM 失败 + 默认 → 静默 + 原文(fail-soft 兼容)

---

### A5. `transcribe_via_crv` fallback timeout + 路径校验
**位置**:`scripts/transcribe_via_crv.py` 的 `_fallback_to_faster_whisper`

**设计**(M-03/M-12 整合):
- `subprocess.run(..., timeout=7200)`(与主路径一致)
- 入口处 `Path(input_video).resolve()` 绝对化(M-12)
- 失败时 exit code 3(区分主路径失败 vs fallback 失败)
- crv-audio 路径断言:`assert output_dir.is_absolute()`,否则 raise(M-03 衍生)

**测试**:`tests/test_transcribe_timeout.py` mock subprocess 加 timeout 测试

---

### A6. 静默 `except` 修复 ⭐ 必做 ⭐
**位置**:`markdown_to_docx.py:858-862` / `verify_all.py:358` 等 10+ 处

**设计**(M-02 衍生):
- 统一加 `log(...)` 记录异常类别
- 改为 `except Exception as e: log(f"<func>: {type(e).__name__}: {e}"); raise`
- SKILL.md "高优先级 gotchas" 加条:"禁止静默 except,必须 log 异常类别 + raise 或 fallback"

**影响**:`grep -rn 'except.*pass\|except.*continue' scripts/` 找全 10+ 处

**测试**:现有 282 tests 应无回归(纯 log 增)

---

## 2. 阶段 B 详细任务(含 M-XX 模式映射)

### B1. `verify_html.py` 扩到 30 条规约 ⭐ 必做 ⭐
**位置**:`scripts/verify_html.py`

**8 个新 verify 函数**(M-05/M-06/M-07/M-08/M-09/M-10 衍生):

| 函数 | 关联模式 | 关键点 |
|---|---|---|
| `verify_NO_ROLE_PERSONA_EXTENDED` | M-07 | **表格单元格**也要扫(不只段落) |
| `verify_HIERARCHICAL_NUMBERING` | M-05 | 正则与 SKILL.md 描述**严格对齐**(`## N xxx` 空格不要点号) |
| `verify_NO_SINGLE_LINE_BLOCKQUOTE_CALLOUT` | (新) | 单行 `>` 计数 |
| `verify_H3_LECTURER_BIO` | (现) | H2/H3/H4 标题黑名单词 |
| `verify_TRAINING_AD_CHAPTER` | (新) | H2 含培训广告关键词 |
| `verify_img_size_within_limit` | (新) | PIL 读 `<img src>` 文件,check ≤ 200KB + ≤ 800x600 |
| `verify_no_path_traversal` | (新) | img 路径不含 `..` |
| `verify_NO_DOC_META_HEADER_BLOCKQUOTE` | (新) | H1 下 blockquote 元数据 |

**关键规避**:
- M-05:正则与 SKILL 描述对齐,**先看 SKILL 再写测试**
- M-06:全篇 normalize 后检查,非 per-line
- M-07:包含表格单元格
- M-08:`verify_LAST_SECTION_COMPLETE` 详细模式输出每章 5 类资产数量
- M-09:PARAGRAPH-LENGTH 区分"内容段"和"图/表段"
- M-10:NO-INFO-LOSS 双指标(CJK 字符保留率 + 5 类资产完整率)

**测试**:`tests/test_verify_html_extended.py` 30 个 case(每规约 1 PASS + 1 FAIL)

---

### B2. `check_no_markdown_corruption.py` 扩 30 污染词
**位置**:`scripts/check_no_markdown_corruption.py:30-40`

**设计**(M-11 衍生):
- `CORRUPTION_TOKENS` 直接抄 `references/asr_corrections.yaml` 41 条
- 加 NO-ORPHAN-WORDS 模式(段首/段末"好/对/那个/对吧/是吧")
- 列数算法修正:`line.count('|') - 1`(去除两侧边界)
- `build_per_lecture_asr_corrections.py` Jaccard 字形相似度作为可选 enrich

**测试**:`tests/test_check_no_markdown_corruption_extended.py` 5 个 sample

---

## 3. 阶段 C/D/E 方向指引(超出本计划)

### C. 输出质量(P0,6-8h)
- C1 `_purify_smooth` prompt 收紧("只删不改/只重排不重写")
- C2 切分统一(`chunking.py`)
- C3 fail-soft → fail-loud(`--strict` flag,生产环境开)
- C4 `_llm_vision.py` verbose status

### D. 一键入口(P1,8-10h)
- D1 `run_pipeline.py` 串 Step 0/0.5/0.6/0.7 + Phase 0/1/2/3 + verify_all
- D2 `preflight_check.py` 必做首问强制钩子
- D3 `semantic_block_fix.py` D0 净化脚本
- D4 `enforce_post_merge_4steps.py` 固化 v4.9.1 必做 4 步
- D5 Phase 1.7/1.8 orchestrator
- D6 幂等性 + 断点续跑(`pipeline_state.json`)
- D7 时间预算埋点

### E. 可维护性(P2,3-4h)
- E1 utils 扩充(8 个工具函数)
- E2 argparse boilerplate 统一
- E3 heading 正则统一
- E4 跨平台 CI(GitHub Actions matrix)
- E5 `simplify` 技能定期 review

---

## 4. 13 条跨项目踩坑模式总览(本计划核心事实支撑)

| 模式 | 描述 | 阶段 A/B 任务 |
|---|---|---|
| M-01 | `_wait_and_finalize.py:32` SKILL_DIR 路径 bug | A1, D1 |
| M-02 | LLM 500 / 1026 错误 | A1, A4, A6 |
| M-03 | crv-audio 输出路径与 watcher 期望错位 | A5, D1 |
| M-04 | `_pipeline_all.py` f-string escape + GBK | A2 |
| M-05 | NUMBERING-DOTTED 实际不期望点号 | B1 |
| M-06 | FULLWIDTH-PUNCT 跨行命中 | B1 |
| M-07 | 禁用词"学员" 表格也 FAIL | B1 |
| M-08 | 末章 5 类资产齐全 | B1 |
| M-09 | PARAGRAPH-LENGTH 每条独立成段 | B1 |
| M-10 | v4.18 simplify 45-55% 是正确区间 | B1 |
| M-11 | CJK 60% 阈值 FAIL 是数字术语 | B2 |
| M-12 | crv-audio 必须绝对路径 | A1, A5 |
| M-13 | scenedetect 直播录屏太慢 | A3, SKILL.md gotcha |

**完整报告**:`history/v3.8-optimized/resource-study-report-2026-10-13.md`

---

## 5. 执行约束(CLAUDE.md 红线)

1. **0 删除**:全为新增 + Edit;任何删除走 `no-delete-gate.py` 二次确认
2. **临时文件**:`/c/Temp/`(MSYS2 风格)
3. **不动**:`.claude-mem` / `.claude-flow` / `.codex` / `.copilot` / `.config`
4. **每次改动后**:`python -m pytest tests/` + 对应 CLI `--help` 验证
5. **会话预算** ≤ 2h,主动 /exit 或新开会话
6. **任务交接**:写 `handoff-<topic>-<date>.md` + `prompt-<topic>-next.md`

---

## 6. 验收清单(本计划完成时)

```bash
# 1. 单元测试
cd F:/soft/00selfmade/long-doc-processor && python -m pytest tests/ -v
# 期望: ≥ 330 tests PASSED(原 282 + 新 30+ for A+B + 新 B1 30)

# 2. CLI 签名检查
python scripts/_purify_smooth.py --help       # 期望显示新增 --max-chars
python scripts/purify_v4_4_hierarchical.py --help
python scripts/_llm_vision.py --help           # 期望显示 safe_llm_call
python scripts/verify_html.py --help          # 期望显示 30 条新 verify
python scripts/check_no_markdown_corruption.py --help

# 3. 端到端
python scripts/verify_all.py
python scripts/regression_test.py
```

**GitHub 化目标**(本计划附带):
- `kizemo/long-doc-processor` public 仓库建立
- 仅 commit 核心:SKILL.md + scripts/ + references/ + tests/ + README + 优化方案 + lessons + 跨项目报告
- 排除:.pytest_cache + handoff-*.md 接力文档 + history/openclaw-base/ + long-doc-processor_openclaw/
- README 扩展:GitHub 徽章 + 快速开始 + 架构图

---

**下次会话接力**:读完本计划 + `optimization-plan-2026-10-13.md` + `resource-study-report-2026-10-13.md` 即可全量执行。
