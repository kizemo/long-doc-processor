# long-doc-processor · P0/P1 全 + P2 部分完成 handoff

**交接日期**: 2026-10-12(本会话完整进度)
**承接自**: handoff-2026-10-12.md + handoff-2026-10-12-p1-progress.md
**本次完成**: P0 全部(3/3) + P1 全部(3/3) + P2 部分(7/11 脚本 + 0 references + 0 verify_all 扩展)

---

## 1. 已完成总览(本会话 2 个连续回合)

### 第一回合(P0 + P1-3)
- ✅ P0-1: SKILL.md 加"实现状态说明"节
- ✅ P0-2: `scripts/_post_terms_fix.py`(CLI + YAML 数据驱动 + --selftest,17 tests)
- ✅ P0-3: `references/asr_corrections.yaml`(41 条默认规则)
- ✅ P1-3: `scripts/transcribe_via_crv.py`(claude-real-video 包装 + 兜底,27 tests)
- 单元测试:17 + 27 + 14 = 58 passed

### 第二回合(P1-1/2 + P2 部分)
- ✅ P1-1: `scripts/purify_v4_4_hierarchical.py`(LLM 驱动 + skeleton + retry,27 tests)
- ✅ P1-2: `scripts/_purify_smooth.py`(per H2 通顺化 + dry-run,26 tests)
- ✅ P2-1: `scripts/extract_skeleton.py`(无 LLM,~100 行,6 tests)
- ✅ P2-1: `scripts/per_section_stats.py`(无 LLM,~150 行,13 tests)
- ✅ P2-1: `scripts/regression_test.py`(无 LLM + sample case,9 tests)
- 单元测试新增:27 + 26 + 6 + 13 + 9 = 81 → 累计 139 passed

---

## 2. 当前总览

### 文件统计
```
scripts/                28 个 .py + 1 .json + 1 .yaml = 30 个文件
                         (新: _post_terms_fix / transcribe_via_crv /
                              purify_v4_4_hierarchical / _purify_smooth /
                              extract_skeleton / per_section_stats / regression_test)
references/             18 个 .md(无新增)
                        + 1 个 .yaml (新: asr_corrections.yaml)
tests/                  8 个测试文件
                        + 1 个 regression_cases/sample_cleaned.json
                        (新: test_post_terms_fix / test_transcribe_via_crv /
                             test_purify_smooth / test_purify_v4_4_hierarchical /
                             test_extract_skeleton / test_per_section_stats /
                             test_regression_test)
history/                完整备份(v3.8-optimized + openclaw-base,无变动)
task.md                 已建立并持续更新
SKILL.md                加"实现状态说明"节,所有 P0/P1 + 3 P2 脚本标 ✅
```

### 测试通过
```
test_crop_insert.py                  14 tests ✅ (原有)
test_post_terms_fix.py               17 tests ✅
test_transcribe_via_crv.py           27 tests ✅
test_purify_smooth.py                26 tests ✅
test_purify_v4_4_hierarchical.py     27 tests ✅
test_extract_skeleton.py              6 tests ✅
test_per_section_stats.py            13 tests ✅
test_regression_test.py               9 tests ✅
─────────────────────────────────────────────
合计                                139 tests PASSED in 0.73s
```

regression_test.py 端到端:1/1 case PASS

---

## 3. 下阶段必交付(P2 剩余)

### P2-1 · 补齐其他脚本(剩 11 个)

按优先级:

**正则脚本(无 LLM,易实现)**:
- [ ] `strip_nested_numbering.py`(regex,检测嵌套编号 + 强制降级)
- [ ] `check_no_markdown_corruption.py`(regex,表格完整性 + 污染词)
- [ ] `fix_bad_extract_terms_inline.py`(regex,清理 garbage 条目)

**LLM 驱动脚本(需 prompt 设计)**:
- [ ] `strip_lecturer_preamble.py`(NO-LECTURER-PREAMBLE,LLM 改写铺垫)
- [ ] `strip_role_persona.py`(NO-ROLE-PERSONA,LLM 改写人称)
- [ ] `strip_asr_terms.py`(ASR-TERM-FIX,rule-based)
- [ ] `last_section_reprocess.py`(LAST-SECTION-COMPLETE)
- [ ] `_pre_merge_semantic_check.py`(v4.15 4 类自动修复)
- [ ] `asr_quality_check.py`(v4.11 3-pass)
- [ ] `glossary_expand.py`(从电商术语表 G 节生成 asr_error_dict)
- [ ] `build_per_lecture_asr_corrections.py`(扫孤字 + Jaccard 候选)

### P2-2 · 补齐缺失 references(2 个)

- [ ] `references/av-end-to-end-checklist.md`(Step 0/0.5/0.6/0.7 完整 13 步 + 时间预算)
- [ ] `references/规约清单.md`(30 条规约单一真相源)

### P2-3 · 扩展 `verify_all.py` 到 30 条规约校验
当前: frontmatter / 链接 / CJK ratio(3 项)
目标: 完整 30 条规约校验

---

## 4. SKILL.md "实现状态" 状态(2026-10-12)

| P 等级 | 已补齐 | 未补齐 |
|---|---|---|
| P0(必须) | _post_terms_fix.py | (无) |
| P1(重要) | purify_v4_4_hierarchical.py / _purify_smooth.py / transcribe_via_crv.py | (无) |
| P2(可选) | extract_skeleton.py / per_section_stats.py / regression_test.py | 11 脚本 + 2 reference + verify_all 扩展 |

未实现脚本 18 → 11(P0/P1/P2 补齐 7 个,剩 11 个待办)

---

## 5. 环境提示

- `ANTHROPIC_API_KEY` 本机 **未设置**(2026-10-12)
- LLM 驱动脚本已设计为 graceful fail:LLM 失败 → 保留原文 + 兜底骨架对齐
- 单元测试用 `unittest.mock` patch LLM 调用,无 API key 也可跑
- `claude-real-video` (crv) 在 PATH,`transcribe_via_crv.py` 可实测
- pytest 9.1.1 + Python 3.14.6 + Windows bash (MSYS2)

---

## 6. 操作纪律(CLAUDE.md 红线,持续遵守)

- 0 删除(本会话全程无 `rm` / `Remove-Item`)
- 临时文件写 `/c/Temp/`(MSYS2 风格)
- 不动 `.claude-mem` / `.claude-flow` / `.codex` / `.copilot` / `.config`
- 每次改动后跑 `python -m pytest tests/` + 对应 CLI 验证

---

## 7. 避坑提示(本会话发现)

1. **CLI 直接 import `scripts._*` 失败**:需在脚本顶部 `sys.path.insert(0, Path(__file__).parent.parent)`
2. **`re.sub` 是非重叠单次扫描**:长词在前只能匹配第一次出现的位置;长词在前 sort key 让其消耗文本
3. **测试边界用例必须实际验证设计意图**:不能凭直觉假设
4. **YAML 配置写入后必 `cat` 自查重复条目**
5. **Windows bash 写 C:\Temp\ 用 `/c/Temp/`(MSYS2 风格)**
6. **`regression test case` 路径用基于 case 文件的相对路径**,不要基于 CWD
7. **`^|` 表格正则要求独占一行**,不能混入行中间
8. **SKILL.md 描述与实际实现的 gap 必须在文档中显式标注**

---

## 8. 必读顺序(新会话接力)

1. 本文件 `handoff-2026-10-12-p2-progress.md`(本会话全部进度)
2. `task.md`(勾选状态)
3. `SKILL.md`(已含实现状态说明)
4. `scripts/_purify_smooth.py` / `purify_v4_4_hierarchical.py`(已补齐的 LLM 脚本作为参考样式)
5. `scripts/extract_skeleton.py` / `per_section_stats.py` / `regression_test.py`(已补齐的非 LLM 脚本)
6. `tests/test_purify_smooth.py`(单元测试 + mock LLM 模式参考)
7. 任意未实现脚本的 SKILL.md 引用位置(在"实现状态说明"节)

---

<!-- Generated: 2026-10-12, source: P0 全部 + P1 全部 + P2 部分(7 脚本) -->
