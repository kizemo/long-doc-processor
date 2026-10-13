# Simplify Review v4.21 — long-doc-processor 优化阶段总览

> **生成时间**: 2026-10-17
> **覆盖范围**: v4.21 阶段 A/B/C/D/E 全部 28 子任务
> **目的**: 沉淀 v4.21 沉淀物的代码质量 review,作为 v4.22+ 改进参考

---

## 1. 整体成果

| 阶段 | 子任务 | 状态 | 测试增量 | commit |
|---|---|---|---|---|
| A | 6/6(必做 3 + 推荐 3) | ✅ | +46 | 6ed4d26 |
| B | 2/2(B1 必做 + B2 推荐) | ✅ | +44 | a95fce2 |
| C | 4/4(C1-C4 全部) | ✅ | +29 | 31a4a10 |
| D | 7/7(D1-D7 全部) | ✅ | +75 | 48b3297 |
| E | 5/5(E1-E5 全部) | ✅ | +55 | TBD |
| **合计** | **24/24** | ✅ | **+249** | |

**测试基线**:227 → **476 PASSED**(每会话 ~50+ tests,稳定增长)

---

## 2. 各阶段沉淀物(Simplify 视角)

### A 阶段:必做 3 + 推荐 3

**沉淀 1: safe_llm_call 装饰器**(`scripts/_llm_vision.py`)
- 7 种 status 分流(ok / empty / error / timeout / rate_limited / no_api_key / no_sdk)
- 整合 M-01(路径)/ M-02(LLM 错误分类)/ M-12(绝对路径)3 个跨项目踩坑模式
- **优点**: 调用方按 status 分流,5 脚本统一替换
- **可改进**: on_status 回调可加 JSON 输出,便于机器解析

**沉淀 2: utils.log 线程安全**(`scripts/utils.py`)
- 加 `_log_lock` 防 3 worker 撕裂
- 时间戳前缀便于排序
- **优点**: 单行 log 原子输出
- **可改进**: 可加 log level(DEBUG/INFO/WARN/ERROR)

**沉淀 3: chunking.py 统一**(`scripts/chunking.py`)
- 5 类 H 标题正则 + with-title 版本
- `chunk_for_llm` 公共入口
- **优点**: 5 脚本共用 1 个 chunking
- **可改进**: 未来可加 `chunk_by_size_with_overlap`(overlap 上下文保留)

### B 阶段:verify 20 条 + 污染词 44

**沉淀 4: verify_all 21 条规约**(`scripts/verify_all.py`)
- 跨项目踩坑整合(M-05/M-06/M-07/M-13)
- **优点**: 8 个新 verify 函数 + 30 tests
- **可改进**: verify_PURIFY_FAIL_LOUD 触发时只检测,未给具体修复建议

**沉淀 5: check_no_md_corruption 44 词**(`scripts/check_no_markdown_corruption.py`)
- 整合 `references/asr_corrections.yaml` 41 词
- NO-ORPHAN-WORDS 模式(规约 26)
- 列数算法修正(`line.count('|') - 1`)
- **优点**: 污染词覆盖完整
- **可改进**: Jaccard 相似度候选未集成,仅放在 M-11 设计建议

### C 阶段:prompt + chunking + verify + verbose

**沉淀 6: SMOOTH_PROMPT 收紧**(C1)
- "只删不改、只重排不重写"
- 显式禁止同义改写/润色用词
- **优点**: 阻断 v4.18 智篆 LLM 风格污染
- **可改进**: 7 类清理的"删除 vs 替换"边界可更细化

**沉淀 7: make_verbose_status_callback**(C4)
- 5 LLM 脚本统一 verbose 模式
- **优点**: 默认 off,向后兼容
- **可改进**: 可加 verbose level(NONE / BASIC / DETAILED)

### D 阶段:一键入口 + preflight + 4 步 + orchestrator

**沉淀 8: run_pipeline.py 核心**(`scripts/run_pipeline.py`)
- 10 phase 串行 + state 持久化 + 幂等性
- **优点**: 一键入口 + resume 支持
- **可改进**: phase 1.0/1.1/1.4/1.5/1.7/1.8/2/3 仅 phase_0_asr + phase_1_purify + verify_all 实现,其余 stub

**沉淀 9: preflight_check.py 4 步首问**(D2)
- 强制 5 字段填写完整
- **优点**: 杜绝"默认选 ASR"反模式
- **可改进**: 可加交互式 prompt(SKILL.md "⚡ 必做首问 4 步"卡片化)

**沉淀 10: enforce_post_merge_4steps.py**(D4)
- 复用 verify_all 函数(无重复实现)
- **优点**: 4 步是 v4.9.1 强制项,固化执行
- **可改进**: 可加更多 v4.x 规约(5+6+7+8 等 LLM-driven 规约目前仅靠 LLM 守)

### E 阶段:utils 8 + argparse + heading + CI

**沉淀 11: utils 8 个新工具函数**(E1)
- find_files_by_ext / safe_rename / compute_md5 / atomic_write / parse_table_row / is_cjk / extract_first_h1 / normalize_whitespace
- **优点**: 消除重复代码
- **可改进**: 可加 `parse_yaml_safe` / `parse_json_safe`(统一异常处理)

**沉淀 12: make_standard_parser + safe_main**(E2)
- argparse boilerplate 统一
- **优点**: 减少 boilerplate
- **可改进**: 现有 5 LLM 脚本还没用,需要后续迁移

---

## 3. 代码质量指标

| 指标 | 数值 | 评价 |
|---|---|---|
| 测试覆盖 | 476 / ~3000 行 | 高(unit test 充分) |
| 静默 except | 0 处 | ✅(A6 修复) |
| 代码重复 | 中(各 LLM 脚本模板类似) | 待 E2 全迁移后降低 |
| 文档完整 | 高(SKILL.md / handoff / prompt) | ✅ |
| 跨项目踩坑整合 | 13/13(M-01~M-13) | ✅ |
| CI/CD | 3 OS matrix 已配置(E4) | ✅ |
| 一键入口 | 有(D1 run_pipeline.py,但仅 stub 完整) | 部分 |

---

## 4. 已知局限(留给 v4.22+)

1. **run_pipeline phase stub**: phase 1.0/1.1/1.4/1.5/1.7/1.8/2/3 仅 stub,实际调 LLM/ASR/合并/渲染待补
2. **D1 真实模式**: dry-run 模式完善,真实模式会 NotImplementedError
3. **CI 未跑过**: `.github/workflows/ci.yml` 已配置,但未触发实际 CI run(需推到 GitHub 触发)
4. **E2 boilerplate 迁移**: 5 LLM 脚本还没用 make_standard_parser,后续可批量迁移
5. **E3 heading 正则迁移**: 8 个脚本还有本地 _H*_RE 定义,后续可逐步 import 自 chunking

---

## 5. 建议 v4.22 优先做

1. **P0**: 把 run_pipeline.py 的 phase 1.x 全部实现,真正支持端到端(需独立 session)
2. **P1**: CI 跑通后,3 OS 都应 476 PASS,确认跨平台兼容
3. **P2**: E2 boilerplate 全迁移(5 LLM 脚本)
4. **P2**: E3 heading 正则全迁移(8 个脚本)
5. **P3**: 增加 v4.22 跨项目踩坑模式(读 handoff-2026-10-12 等新案例)

---

**Generated**: 2026-10-17 by simplify 技能 review
**Reviewer**: Claude (v4.21 simplify pass)
