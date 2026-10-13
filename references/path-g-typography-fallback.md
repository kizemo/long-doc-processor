# Path G · 排版补救 (Typography Fallback)

> **版本**: v4.20 (2026-09-30)
> **触发**: long-doc-processor 加载后, Step 0.7 必做首问判定
> **沉淀**: 边界 2026-06-03_AI 助力主图点击率低项目第三轮迭代(用户反馈"勉强图比无图更糟")
> **位置**: 集成在 `references/phase-1.8-decision.md` 的 AskUserQuestion 选项 C

---

## 1. 什么是 Path G

Path G 是 **Phase 1.8 视频截图流的官方替代方案**, 不是失败回退。

**核心思路**: 当视频本身没有 H3 想要的演示帧时,**不勉强使用低质图**(登录页/空表/AI 加载/纯讲师头像),改用**排版强化**替代截图。

**反模式**: "勉强用" — 算法 PASS ≠ 视觉可用。用户在 2026-06-03 项目中明确反馈"勉强图比无图更糟, 宁可放弃"。

---

## 2. 何时触发 Path G (判定流程)

```
Phase 1.8 跑完 (8 张硬上限)
   │
   ├─ < 8 张图 → 已是低质量信号
   │
   ├─ 8 张全部 PASS 但人工目视发现低质 (登录页/空表/AI加载)
   │   → 触发 Path G: 放弃, 用 typography 替代
   │
   ├─ 视频本身无 H3 演示 (e.g. 案例教学但视频没演示该案例)
   │   → 触发 Path G
   │
   └─ 8 张图全部高质量 → 正常交付, 不触发
```

**关键判据**: **人工目视** 是终极判定(不是 OCR 关键词, 不是 Jaccard, 不是算法自动评估)。

---

## 3. 排版强化 6 模式 (Path G 的核心)

当 Path G 触发时,用以下 6 种排版模式强化文档, 替代缺失的截图。

### 4.1 标题分级编号 (HIERARCHICAL-NUMBERING, v4.17 已强制)

```markdown
# AI 助力主图点击率低 · 主图优化实战课

## 1. 产品裂变 · 平台展示规则与客户需求

### 1.1 本节核心结论

### 1.2 指甲剪案例拆解

### 1.3 案例后台数据看板
```

**作用**: 让读者通过编号快速定位章节, 不依赖截图辅助。

### 4.2 加粗 inline (替代"核心判定/关键指标")

```markdown
**核心结论**: 指甲剪产品在生意参谋的"平台展示规则"会按照不同价位段/人群/类目差异化展示。

**关键指标**:
- 显性需求 vs 隐性需求 比例: 4:1
- 评价/问大家 命中关键词密度: 23%
- 平台搜索结果首页位置: Top 3
```

**作用**: 强调关键信息, 视觉上比截图更突出。

### 4.3 表格 (替代"数据截图")

```markdown
| H3 | 平台 | 数据维度 | 案例值 |
|---|---|---|---|
| 1.3 指甲剪 | 生意参谋 | 平台展示规则 | 按价位段、人群、类目差异化 |
| 3.2 SKU 销售属性 | 生意参谋 | 颜色/身高等属性 | 占比 TOP 3 贡献 60% |
| 4.1 达摩盘调研 | 达摩盘 | 市场榜单 | 收纳整理类目 TOP 5 |
```

**作用**: 表格比截图更适合数据对比。

### 4.4 SVG inline 流程图 (替代"流程截图/XMind 截图")

```html
<svg width="600" height="200" viewBox="0 0 600 200">
  <rect x="20" y="80" width="120" height="40" fill="#e0f0ff" stroke="#333"/>
  <text x="80" y="105" text-anchor="middle">抓取需求</text>
  <rect x="180" y="80" width="120" height="40" fill="#e0f0ff" stroke="#333"/>
  <text x="240" y="100" text-anchor="middle">竞争对手</text>
  <text x="240" y="115" text-anchor="middle">图片</text>
  <rect x="340" y="80" width="120" height="40" fill="#e0f0ff" stroke="#333"/>
  <text x="400" y="105" text-anchor="middle">站外高点击</text>
  <rect x="500" y="80" width="80" height="40" fill="#e0f0ff" stroke="#333"/>
  <text x="540" y="105" text-anchor="middle">主图</text>
  <line x1="140" y1="100" x2="180" y2="100" stroke="#333" marker-end="url(#arrow)"/>
  <line x1="300" y1="100" x2="340" y2="100" stroke="#333" marker-end="url(#arrow)"/>
  <line x1="460" y1="100" x2="500" y2="100" stroke="#333" marker-end="url(#arrow)"/>
</svg>
```

**作用**: SVG 可在浏览器渲染, 无需外部文件, 比截图更轻量。

### 4.5 代码块 (替代"操作步骤截图")

````markdown
```bash
# 5 步法: 主图生成完整流程

# Step 1: 抓取顾客需求
# - 关键词搜索(评价/问大家/显性需求)
# - 生成提示词 1 + 提示词 2

# Step 2: 竞争对手图片
# - 类目 TOP 100 商品主图收集

# Step 3: 站外高点击率图片
# - 跨类目优秀案例收集
```
````

**作用**: 操作步骤用代码块比截图清晰, 且可复制。

### 4.6 多行 blockquote (替代"核心结论 box")

```markdown
> **核心结论 box**:
>
> 1. 指甲剪案例平台展示规则会按人群/类目/价位段差异化
> 2. 1688 找货要认准"工厂直供"标签, 避开中间商加价 30%
> 3. 达笔 AI 主图生成需 3 层计划: 拉新/收割/控投产
```

**作用**: 多行 blockquote 是合法的"强调工具"(v4.18 规定), 单行禁用, 多行推荐。

---

## 4. Path G 实施步骤

```
Step 1: 跑 Phase 1.8 (默认 8 张上限 + 200KB)
   ↓
Step 2: 人工目视 8 张 (算法自动评估不等于视觉可用)
   - 接受: 截图清晰 + 内容匹配 H3
   - 拒绝: 登录页/空表/AI加载/纯讲师头像/XMind 凑数
   ↓
Step 3: 统计接受/拒绝比
   - 8/8 接受 → 正常交付, 不触发 Path G
   - 1-7/8 接受 → 部分接受 + 部分用 typography 替代
   - 0/8 接受 → 全部 Path G
   ↓
Step 4: 接受部分注入 cleaned.md (从 .v18.bak 恢复后)
   ↓
Step 5: 拒绝部分用 typography 强化 H3 内容 (4.1-4.6 模式)
   ↓
Step 6: 验证 (verify_html 应输出 INFO: no <img> tags found, 这是合法)
   ↓
Step 7: 移动测试 + 交付
```

---

## 5. verify_html 在 Path G 下的行为

**正常**: PASS `[19]: image exists: ...`
**Path G**: `INFO: no <img> tags found (skip 19/20)` — 这是**合法状态**,不是错误。

如果 verify_html 报 `INFO: no <img> tags found`, 不要去"修复"或"重新生成图", 这是 Path G 预期输出。

---

## 6. 反模式 (Path G 必须避免)

1. ❌ **不要勉强塞低质图**: 算法 PASS ≠ 视觉可用
2. ❌ **不要在跨笔记搜索时跳过主题匹配检查**: 任何图像搜索(笔记间/笔记内)都必须验证主题匹配
3. ❌ **不要把 Path G 当失败回退**: Path G 是合法方案, 不是"截图失败的备胎"
4. ❌ **不要在 Path G 文档里加 placeholder 图片占位符**: 文档应直接交付 typography 版, 不留 "image-1.png not found" 之类
5. ❌ **不要在 Path G 文档里硬塞 SVG infographic**: SVG 应仅在确有流程图价值时用, 不要为了"看起来有图"硬塞
6. ❌ **不要让 Path G 文档的可读性低于截图版**: typography 必须达到或超过截图的信息密度

---

## 7. 已知陷阱

| 陷阱 | 现象 | 解决 |
|---|---|---|
| 用户说"加点图更好" | Phase 1.8 已跑 8 张但都被拒绝 | 不要回去重跑,直接 Path G + 解释 |
| 跨笔记/网络主题不匹配仍尝试 | 错配图/无关图 | 必须先 OCR + 主题关键词过滤, 不匹配放弃 |
| SVG 写得太复杂 | 流程图变迷宫图 | SVG 仅 5-7 节点, 超过用 4.3 表格替代 |
| 表格列数过多 (>6 列) | 移动端溢出 | 拆表或多行 blockquote 替代 |
| `**加粗 inline**` 滥用 | 整段加粗,失去强调作用 | 每个 H3 内 ≤3 处加粗 |

---

## 8. 相关文档

- `references/phase-1.8-decision.md` — AskUserQuestion 卡片 3 选项 (A/B/C)
- `references/image-pipeline.md` — 文档图片通用处理 (OCR + 配图生成)
- `SKILL.md` § v4.20 — 变更说明 + 3 条硬规约
- `handoff-image-fix-v2-2026-09-30.md` (项目级) — 实际触发 Path G 的实战案例

---

## 9. 版本演进

- **v4.20 (2026-09-30)**: 首版, 边界 2026-06-03 项目第三轮迭代沉淀
- **未来 v4.21+**: 可选扩展
  - AI 图像生成 (Stable Diffusion LoRA / 通义万相) 作为 Path G+1
  - Stock photo API (Unsplash/Pexels) 作为 Path G+2
  - SVG infographic 自动生成器 (`scripts/_svg_infographic.py`)