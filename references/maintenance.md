# 维护与自进化机制

skill 维护触发条件与流程；普通任务无需读取。

## lessons.md 记录

每次使用本 skill 完成（或中断）后，必须向 `lessons.md` 追加：

```markdown
### YYYY-MM-DD — 简短标题
- **场景**：
- **顺利**：
- **摩擦**：
- **修正**：
- **规则**：
```

## 自动升级触发

| 触发条件 | 动作 |
|---------|------|
| 同类摩擦出现 ≥ 2 次 | 更新 `references/gotchas.md` 加入警示 |
| 同类规则被记录 ≥ 2 次 | 升级为正式验收项或步骤 |
| 累计 5+ 条新记录 | 运行 `scripts/validate_skill.py` 与 `scripts/test_renumber.py` 全面审查 |
| description 需调整 | 先用 `evals/routing.json` 验证，再写入 |

## 版本号

每次结构性变更更新根 SKILL.md frontmatter 的 `metadata.version`。当前 v4.0.0。

## 与 self-improving-agent 联动

- 执行层面的错误 → `.learnings/ERRORS.md`（self-improving-agent 处理）；
- 流程/设计层面的摩擦 → `lessons.md`；
- 跨 skill 适用的教训 → `MEMORY.md`。