# 高价值失败模式

按 append-mostly 维护：发现新失败模式直接追加；不删除已记录项除非证明已不适用。

## 编码与 BOM

- PowerShell `Set-Content -Encoding UTF8` 等价于带 BOM UTF8，会导致 `re.sub(r'^# ', ...)` 不匹配。修复：用字节级 `WriteAllBytes` 或 `UTF8Encoding($false)`。
- Python 在 PowerShell 默认 GBK 输出，含 emoji 的 `print` 失败。修复：执行前 `$env:PYTHONIOENCODING='utf-8'`。

## 标题降级

- 禁止连续 `re.sub(r'^## ', '### ', ...)` 与 `re.sub(r'^# ', '## ', ...)`，会级联把刚降级的 H1 再降级一次。
- 修复：用占位符两步法：先 `###X` → `PLACEHOLDER_H3` → `## PLACEHOLDER_H3` → 回填 `### X`。**占位符绝对不能含 `#`**。

## 终端与跨平台

- 跨平台含中文 + 空格的路径，`shell_command` 调用 Python 偶尔会被解析成多个 token。修复：`cd "<源目录>"; python "脚本路径" "参数路径"`。
- `sed -i ''` 是 macOS 写法，在 Windows 上无效。统一使用 Python `re.sub` 完成相同工作。

## 保留率与信息量

- 净化后保留率 9–55% 不必然是错误；可能是大段广告/重复口头禅被删除。必须复核 5 类资产完整性，并填写 `## 统计` 区块。
- 重复口头禅 ≥ 3 遍为典型噪声，可整段删除。

## Word 输出（legacy）

- `markdown_to_docx.py` 不支持 H5：H5 标题以 `##### xxx` 形式残留为纯文本。若需要更深层级，扩展 converter 或保持原 H4 不变。
- `#####` 残留是 converter 硬上限信号，超出 H4 时必须扩展或调整降级策略。

## HTML 输出（v4.0+）

- `<img>` 必须含 `alt`；否则 verify_html.py 失败。
- 图片相对路径必须以 `img/` 开头且文件存在；缺失时 Phase 3 立即报错。
- 单文件 HTML 应内嵌 CSS，避免外部依赖；不得引用 CDN。
- **Markdown 输入头部的 YAML frontmatter**（`---\ntitle: ...\n---`）由 `markdown_to_html.py` 自动剥离；禁止出现在最终 HTML 中（`verify_html.py` #17b 检查 `<p>---</p>` 等伪段落）。
- **配图生成**：Claude / MiniMax-M3 会话内调用 **MiniMax-M3**（环境变量 `MINIMAX_IMAGE_GEN=1`），不依赖外部 image gen 服务；`.prompt.txt` 占位由主代理读取后生成图片。
- **配图视觉规范**（详见 `references/image-style.md`）：
  - 文字容器宽度 ≥ 文字宽度 × 1.2，长文本自动换行；
  - 深色背景必须配浅色文字（白色 / 浅灰），禁止深色文字配深色背景；
  - 文字与背景对比度 ≥ 4.5:1（WCAG AA）；
  - 字号：标题 ≥ 36px，正文 ≥ 24px。
- `scripts/generate_image.py` 默认自动注入视觉规范段到 prompt；禁用请加 `--no-style-suffix`。

## 子代理与弱 runtime

- Codex 多 agent 派发不可用时，主代理串行执行；不得跳过 `qa-gates.md` 验收。
- `multi_agent_v1__spawn_agent` 在 Codex 某些版本不可用，回退到主代理串行。

## frontmatter 与 description

- description 必须以 `Load when...` 开头；不写"This skill does..."。
- description 改动必须由 routing eval 支持，不能凭印象修改。