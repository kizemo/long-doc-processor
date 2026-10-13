# 运行时兼容性

描述 Claude Code、Codex 与弱 runtime 之间的差异。普通任务无需读取本文件；遇到工具/路径差异或缺能力时再读。

## 路径约定

所有 skill 内部引用一律相对于 skill 根目录：

- `scripts/<name>.py`
- `references/<name>.md`
- `evals/<name>.json`

禁止硬编码：

- `~/.codex/skills/long-doc-processor/...`
- `~/.openclaw/skills/long-doc-processor/...`
- `~/.claude/skills/long-doc-processor/...`

skill 安装位置由 runtime 决定；运行时用其标准解析（`$skill_root`、`SKILL_DIR` 或实际加载路径）。

## Claude Code

- 使用会话内可用工具：Read、Write、Edit、Bash、Glob、Grep；
- Python 调用通过 `Bash` 工具；
- 主代理模型：**MiniMax-M3**（Claude Code 会话内已配置的 LLM）；
- **图片大模型**：**MiniMax-M3**（与主代理同源；调用时设 `MINIMAX_IMAGE_GEN=1`，由 `scripts/generate_image.py` 生成 `.prompt.txt` 占位，主代理读取后调用 MiniMax-M3 出图）；
- 无 subagent 调度，由主代理串行执行。

## Codex

- 同样使用 Read/Write/Edit/Bash/Glob/Grep；
- Python 调用方式相同；
- subagent 通过 `multi_agent_v1__spawn_agent`（如不可用回退主代理串行）；
- 图片生成可选 `huashu-gpt-image` 或本地 SDXL。

## 弱 runtime（如 Cursor / 简单对话）

- 缺少 subagent：主代理串行执行；
- 缺少某些工具：按 `qa-gates.md` 验收门降级到最小可执行集；
- 输出位置仍为源文件目录。

## 安装目录

skill 安装到：

- Codex：`C:\Users\Duanyi\.codex\skills\long-doc-processor\`
- Claude Code：`C:\Users\Duanyi\.claude\skills\long-doc-processor\`

部署由 `validate_skill.py` 静态校验通过后复制完成。