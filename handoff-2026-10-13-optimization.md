# long-doc-processor · 优化执行 handoff(阶段 A + B)

**交接日期**: 2026-10-13
**承接自**: handoff-2026-10-12.md + handoff-2026-10-12-p1-progress.md + handoff-2026-10-12-p2-progress.md
**本会话完成**: 4 维度 review + 优化方案制定 + 同步 dev → runtime
**下次会话任务**: 执行优化方案**阶段 A(稳定性)** + **阶段 B(规约闭环)**

---

## 1. 完整项目背景(必读链路)

| 文档 | 路径 | 用途 |
|---|---|---|
| 项目根 | `F:/soft/00selfmade/long-doc-processor/` | 开发目录,本次任务在 dev 迭代 |
| 项目根 README | `F:/soft/00selfmade/long-doc-processor/README.md` | 项目说明 |
| 原始背景 handoff | `F:/soft/00selfmade/long-doc-processor/handoff-2026-10-12.md` | 2026-10-12 重建背景 + P0/P1/P2 计划 |
| P0/P1/P2 进度 handoff | `F:/soft/00selfmade/long-doc-processor/handoff-2026-10-12-p1-progress.md` | 第一回合(7 脚本 + 1 YAML) |
| P2 完整 handoff | `F:/soft/00selfmade/long-doc-processor/handoff-2026-10-12-p2-progress.md` | 第二回合(7 脚本 + 2 references + verify 扩展) |
| **本次 handoff** | `F:/soft/00selfmade/long-doc-processor/handoff-2026-10-13-optimization.md` | **本文件** |
| 主 SKILL | `F:/soft/00selfmade/long-doc-processor/SKILL.md` | v4.20 主文档(已含"实现状态说明") |
| **优化方案** | `F:/soft/00selfmade/long-doc-processor/optimization-plan-2026-10-13.md` | **A+B+C+D+E 完整方案,本次只做 A+B** |
| 必读规范 | `F:/soft/00selfmade/long-doc-processor/references/规约清单.md` | 30 条规约单一真相源 |
| Runtime SKILL | `~/.claude/skills/long-doc-processor/SKILL.md` | Claude Desktop 实际加载路径(已同步 v4.20) |
| Runtime scripts | `~/.claude/skills/long-doc-processor/scripts/` | 39 个脚本(已同步) |

---

## 2. 项目状态基线(2026-10-13 同步后)

```
scripts/                 39 个 .py
references/              21 个(20 md + 1 yaml)
tests/                   19 个 test 文件
unit tests              282 个 PASSED in ~1.0s
runtime 同步状态:        已同步(2026-10-13,backup 在 /c/Temp/runtime_SKILL_backup_20261013.md)
```

**所有 P0/P1/P2 脚本已补齐**(原 SKILL 描述 18 个未实现脚本,全部 ✅)。

---

## 3. 4 维度 review 关键发现(2026-10-13)

**核心症结**:`prompt 给自由度 + verify 不闭环 + fail-soft 静默` → 规约"知道但守不住"。

### 维度 1:稳定性(🔴 P0)
- `_llm_vision.py:42,64` LLM 调用**无 timeout** → 30K 文档卡就废整夜
- `utils.log` 线程不安全 → Windows 3 worker 并发 stderr 乱行
- `strip_lecturer_preamble` / `strip_role_persona` 全文单次 LLM(超 8K 限制)
- `purify_v4_4_hierarchical` 无 MAX_CHARS 硬约束 → 3 retry 烧光 → 兜底到 fallback(只换标题,正文未净化)
- `transcribe_via_crv` fallback subprocess 无 timeout

### 维度 2:输出质量(🔴 P0)
- `verify_html.py` 只覆盖 **7/30 规约**(23 条 HTML 层无强校验)
- `check_no_markdown_corruption.py` 污染词清单仅 **3 条**(漏掉 16+ ASR 错词)
- `_purify_smooth` prompt 过度宽松 → LLM 自由发挥 30%+ 句意
- `verify_all.py` rglob 含 references/ → 误报讲师黑名单(应加 `--target-glob`)
- `check_no_markdown_corruption` 列数算法 `count('|')` 偏高 1 → 应 `(count - 1)`

### 维度 3:工作流(🟠 P1)
- 无 `run_pipeline.py` 一键入口
- 必做首问 4 步无强制钩子(纯 LLM 自觉)
- v4.9.1 必做 4 步无自动串联
- `semantic_block_fix.py`(D0)v4.13 提了未建
- Phase 1.7 无 orchestrator / Phase 1.8 3 阶段需手动串
- 时间预算无埋点 / 幂等性不保证

### 维度 4:代码质量(🟡 P2)
- 87 处 `encoding='utf-8'` 直接用,应走 utils
- 23+ 处 argparse boilerplate 重复
- 5+ 处 heading 正则重复
- 10+ 处 `except Exception: print(...)` 静默吞

---

## 4. 下次会话任务:阶段 A(稳定性)+ 阶段 B(规约闭环)

### 阶段 A 详细任务(6 项,~2-3h)

#### A1. `safe_llm_call` 装饰器 — 必做
- **位置**:`scripts/_llm_vision.py`
- **设计**:
```python
def safe_llm_call(
    prompt: str,
    *,
    model: str = "claude-sonnet-4-5",
    max_retries: int = 3,
    timeout: int = 120,
    backoff: float = 2.0,
) -> tuple[str, str]:
    """Returns: (response_text, status)
    status ∈ {"ok", "empty", "timeout", "error", "rate_limited"}
    """
```
- **影响**:5 个 LLM 脚本用 `safe_llm_call` 替换直接 `call_vision` 调用:
  - `_purify_smooth.py`
  - `purify_v4_4_hierarchical.py`
  - `strip_lecturer_preamble.py`
  - `strip_role_persona.py`
  - `last_section_reprocess.py`
  - `transcribe_via_crv.py`(failover 调用)
- **测试**:加 30 个 mock 测试覆盖 5 种 status 路径(每个脚本 5 个)

#### A2. `utils.log` 线程安全 — 必做
- **位置**:`scripts/utils.py:43-45`
- **设计**:
```python
import threading
_log_lock = threading.Lock()

def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    with _log_lock:
        print(f"[{ts}] {msg}", file=sys.stderr, flush=True)
```
- **影响**:全脚本(无 API 变更,直接 import)
- **测试**:`tests/test_utils.py` 加 1 个并发 log 测试(2 thread × 100 行不交错)

#### A3. 全文单次 LLM 修复 — 推荐
- **位置**:`strip_lecturer_preamble.py` / `strip_role_persona.py`
- **设计**:复用 `_purify_smooth.split_by_h2` + `smooth_block` 模式 → 按 H2 chunking + 并发 LLM
- **影响**:主体重写(CLI 不变)
- **测试**:现有 4 tests 改用 mock 验证 chunking + LLM 并发

#### A4. `purify_v4_4_hierarchical` MAX_CHARS 硬约束 + fail-loud — 推荐
- **位置**:`purify_v4_4_hierarchical.py`
- **设计**:
  - 加 `--max-chars` CLI 参数(默认 8000)
  - 切分前 assert 单块 ≤ max_chars,否则报错而非 retry
  - LLM 失败时**写 ERROR 标记到输出** + exit 2(而非静默返回原文)
- **影响**:`main()` 函数 + `purify_chunk` 内部

#### A5. `transcribe_via_crv` fallback timeout — 推荐
- **位置**:`_fallback_to_faster_whisper`
- **设计**:`subprocess.run(..., timeout=7200)`(与主路径一致)+ 失败时 exit 3
- **测试**:mock subprocess 加 timeout 测试

#### A6. 静默 `except` 修复 + gotcha 增条 — 必做
- **位置**:`markdown_to_docx.py:858-862` / `verify_all.py:358` 等 10+ 处
- **设计**:统一加 `log(...)` 记录异常类别;SKILL.md "高优先级 gotchas" 加 "禁止静默 except,必须 log 异常"

### 阶段 B 详细任务(2 项,~3-4h)

#### B1. `verify_html.py` 扩到 30 条规约 — 必做
- **位置**:`scripts/verify_html.py`
- **设计**:加 8 个新 verify 函数:
  - `verify_NO_ROLE_PERSONA_EXTENDED`:反查 `讲师指出|讲师总结|学员搜索时|学员常见的错误|学员在选品时`
  - `verify_HIERARCHICAL_NUMBERING`:H2/H3/H4 编号连续
  - `verify_NO_SINGLE_LINE_BLOCKQUOTE_CALLOUT`:单行 `>` 计数
  - `verify_H3_LECTURER_BIO`:H2/H3/H4 标题黑名单词
  - `verify_TRAINING_AD_CHAPTER`:H2 含培训广告关键词
  - `verify_img_size_within_limit`:PIL 读 `<img src>` 文件,check ≤ 200KB + ≤ 800x600
  - `verify_no_path_traversal`:img 路径不含 `..`
  - `verify_NO_DOC_META_HEADER_BLOCKQUOTE`:H1 下 blockquote 元数据
- **测试**:`tests/test_verify_html_extended.py` 覆盖 30 条规则各 1 个 PASS/FAIL sample

#### B2. `check_no_markdown_corruption.py` 污染词扩到 30+ — 推荐
- **位置**:`scripts/check_no_markdown_corruption.py:30-40`
- **设计**:
  - `CORRUPTION_TOKENS` 直接抄 `references/asr_corrections.yaml` 41 条
  - 加 NO-ORPHAN-WORDS 模式(段首/段末"好/对/那个/对吧/是吧")
  - 修正列数算法 `line.count('|') - 1`
- **测试**:`tests/test_check_no_markdown_corruption.py` 加 5 个 sample

---

## 5. 环境与约束

- **CWD**:`F:/soft/00selfmade/long-doc-processor/`
- **Python**:3.14.6(MSYS2 bash)
- **pytest**:9.1.1
- **ANTHROPIC_API_KEY**:**未设置**(LLM 调用 graceful fail,测试用 mock)
- **claude-real-video** 在 PATH(`transcribe_via_crv.py` 可实测)
- **CLAUDE.md 红线**:
  - 0 删除(本会话全程无 `rm` / `Remove-Item`)
  - 临时文件写 `/c/Temp/`(MSYS2 风格)
  - 不动 `.claude-mem` / `.claude-flow` / `.codex` / `.copilot` / `.config`
  - 任何删除走 `no-delete-gate.py` 二次确认
  - 每次改动后跑 `python -m pytest tests/` + 对应 CLI 验证

---

## 6. 完整路径索引

### 必改的脚本(本任务)
- `F:/soft/00selfmade/long-doc-processor/scripts/_llm_vision.py`(A1)
- `F:/soft/00selfmade/long-doc-processor/scripts/utils.py`(A2)
- `F:/soft/00selfmade/long-doc-processor/scripts/_purify_smooth.py`(A1)
- `F:/soft/00selfmade/long-doc-processor/scripts/purify_v4_4_hierarchical.py`(A1 + A4)
- `F:/soft/00selfmade/long-doc-processor/scripts/strip_lecturer_preamble.py`(A1 + A3)
- `F:/soft/00selfmade/long-doc-processor/scripts/strip_role_persona.py`(A1 + A3)
- `F:/soft/00selfmade/long-doc-processor/scripts/last_section_reprocess.py`(A1)
- `F:/soft/00selfmade/long-doc-processor/scripts/transcribe_via_crv.py`(A1 + A5)
- `F:/soft/00selfmade/long-doc-processor/scripts/markdown_to_docx.py`(A6)
- `F:/soft/00selfmade/long-doc-processor/scripts/verify_all.py`(A6 + B2)
- `F:/soft/00selfmade/long-doc-processor/scripts/verify_html.py`(B1)
- `F:/soft/00selfmade/long-doc-processor/scripts/check_no_markdown_corruption.py`(B2)

### 必加的 tests
- `F:/soft/00selfmade/long-doc-processor/tests/test_safe_llm_call.py`(A1)
- `F:/soft/00selfmade/long-doc-processor/tests/test_utils_concurrent.py`(A2)
- `F:/soft/00selfmade/long-doc-processor/tests/test_strip_chunking.py`(A3)
- `F:/soft/00selfmade/long-doc-processor/tests/test_purify_max_chars.py`(A4)
- `F:/soft/00selfmade/long-doc-processor/tests/test_transcribe_timeout.py`(A5)
- `F:/soft/00selfmade/long-doc-processor/tests/test_verify_html_extended.py`(B1)
- `F:/soft/00selfmade/long-doc-processor/tests/test_check_no_markdown_corruption_extended.py`(B2)

### 沉淀位置
- `F:/soft/00selfmade/long-doc-processor/history/v3.8-optimized/lessons.md`(每完成一项追加)
- `F:/soft/00selfmade/long-doc-processor/task.md`(勾选)
- `F:/soft/00selfmade/long-doc-processor/optimization-plan-2026-10-13.md`(更新阶段 A + B 状态为 ✅)

---

## 7. 工作流约定(本任务)

1. **每个子任务**:
   - 改之前先读 SKILL.md/plan 确认接口契约
   - 写之前先写 unit test(参见各脚本已有 test 文件)
   - 改完后跑 `python -m pytest tests/test_<script>.py -v` 验证
   - 改完后跑对应 CLI `--help` 验证签名未坏
2. **每个阶段结束**:
   - 跑 `python -m pytest tests/` 全套(目标 ≥ 320 tests PASS)
   - 同步 dev → runtime:`cp -u scripts/*.py ~/.claude/skills/long-doc-processor/scripts/`
   - 追加 lessons.md 一条
3. **写完后**:
   - 改 `optimization-plan-2026-10-13.md` 阶段 A + B 标 ✅
   - 改 task.md 勾选
   - 写本次 handoff 增量

---

## 8. 风险与回滚

- **A1 改 6 个脚本**:每个 LLM 脚本都改 1-2 行,出问题回滚 git diff
- **A2 改 utils.log**:全脚本影响,先 282 tests 验证无回归
- **B1 改 verify_html.py**:30 条规则原 7 条 + 新 23 条,加 30 个 test 覆盖
- **运行时回滚**:
  ```bash
  # runtime SKILL.md 已在 /c/Temp/runtime_SKILL_backup_20261013.md 备份
  cp /c/Temp/runtime_SKILL_backup_20261013.md ~/.claude/skills/long-doc-processor/SKILL.md
  # runtime scripts 用 `cp -u` 增量同步(只覆盖不删)
  ```

---

## 9. 验证清单(完成时跑)

```bash
# 1. 单元测试
cd F:/soft/00selfmade/long-doc-processor && python -m pytest tests/ -v
# 期望: ≥ 320 tests PASSED(原 282 + 新 30+ for A+B)

# 2. CLI 签名检查
python scripts/_purify_smooth.py --help
python scripts/purify_v4_4_hierarchical.py --help
python scripts/_llm_vision.py --help
python scripts/verify_html.py --help
python scripts/check_no_markdown_corruption.py --help
# 期望:每个都显示新增的 --max-chars / 新规约检查项

# 3. 端到端 sanity
python scripts/verify_all.py  # 跑当前 md 集
python scripts/regression_test.py  # 1/1 case PASS

# 4. 同步 runtime
cp -u F:/soft/00selfmade/long-doc-processor/scripts/*.py ~/.claude/skills/long-doc-processor/scripts/
echo "runtime 同步 OK"
```

---

## 10. 下次会话的"小目标"里程碑

| 里程碑 | 状态 |
|---|---|
| A1 `safe_llm_call` + 6 脚本改用 | ☐ |
| A2 `utils.log` 线程安全 | ☐ |
| A3 `strip_*` 复用 chunking | ☐ |
| A4 `purify_v4_4` MAX_CHARS + fail-loud | ☐ |
| A5 `transcribe_via_crv` fallback timeout | ☐ |
| A6 静默 except 修复 + gotcha | ☐ |
| B1 `verify_html` 30 条规约 | ☐ |
| B2 `check_no_md_corruption` 30 污染词 | ☐ |
| 全套 tests ≥ 320 PASS | ☐ |
| runtime 同步 OK | ☐ |
| lessons.md 追加 | ☐ |

**预计 5-7h 完成**(8 个子任务,每个 30-60 min)

---

<!-- Generated: 2026-10-13, source: 优化方案 v1 → 阶段 A + B 实施 -->
