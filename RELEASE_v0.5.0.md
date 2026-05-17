# judicial-lint-mcp v0.5.0 Release Notes

## 🎉 v0.5.0 — Skill Bridge 架构重构

> **核心变更：MCP Server 从"LLM 调用器"重构为"AI Agent ↔ Skills 桥接器"**，自己不调用任何 LLM，所有 LLM 调用由 Agent 自主管理。

---

## ⚡ 架构变更

### 旧版 (v0.1–v0.2)：MCP Server 直接调 LLM

```
Agent → MCP Server → [自动调 LLM] → 返回结果
```

### 新版 (v0.5.0)：MCP Server = 纯桥接器

```
Agent → MCP Server: render_skill() → 获取 Prompt
Agent → 自己的 LLM → 获得响应
Agent → MCP Server: parse_response() → 结构化 JSON
Agent → MCP Server: build_report() → Markdown 报告
```

**零 LLM 调用，零 API Key 需求。**

---

## 🔧 新增功能（v0.5.0）

### 长上下文支持（对抗 LLM 注意力衰减）

| 功能 | 工具 | 说明 |
|:---|:---|:---|
| Token 预算 | `estimate_tokens` | 渲染前预估，超出时自动推荐应对策略 |
| 材料压缩 | `compact_materials` | 两阶段压缩（关键事实提取 → 纲要生成）|
| 分步渲染 | `render_skill` | 每次只渲染一个 Skill，不一次性发送所有 Prompt |
| 断点续传 | `plan_pipeline` + `pipeline_progress` | 记录执行阶段，支持中断后恢复 |

### Skills 文件化管理

所有检测逻辑以 Markdown 文件存储，可独立编辑更新：

```
skills/
├── _system.md          # 全局 System Prompt
├── _taxonomy.md        # A1-A8 异常分类体系
├── _neutrality.md      # 中立性校验机制
├── _output_format.md    # 输出格式规范
├── dimensions/         # 16 个检测维度（每个维度一个独立 Skill）
├── phases/             # 检测阶段 Skill
└── pipelines/          # Pipeline 定义（组合多个 Skill）
```

### 10 个 MCP Tools

| 工具 | 用途 |
|:---|:---|
| `list_skills` | 列出所有可用检测 Skills |
| `plan_pipeline` | 获取 Pipeline 阶段计划（不含 Prompt，避免上下文溢出）|
| `pipeline_progress` | 查询/更新 Pipeline 执行进度，支持断点续传 |
| `render_skill` | 渲染单个 Skill 为 System + User Prompt |
| `render_pipeline` | 渲染整条 Pipeline（返回一系列 Prompt 列表）|
| `estimate_tokens` | 预估 Skill/Pipeline + 材料的总 token 数 |
| `compact_materials` | 压缩案件材料以适应 token 预算 |
| `parse_response` | 将 LLM 响应解析为结构化 JSON |
| `build_report` | 用结构化数据组装 Markdown 检测报告 |
| `write_skill` | 更新 Skill 文件内容 |

### 3 个 MCP Resources

| Resource URI | 说明 |
|:---|:---|
| `judicial-lint://skills` | 全部可用 Skill 列表（含标题、类型、层级、依赖）|
| `judicial-lint://taxonomy` | A1-A8 异常分类体系（供 Agent 参考）|
| `judicial-lint://system` | 全局 System Prompt（供 Agent 调用 LLM 时使用）|

---

## 📦 安装（已简化）

```bash
git clone https://github.com/lcfactorization/judicial-doc-anomaly-mcp.git
cd judicial-doc-anomaly-mcp
pip install -e .
```

**不需要配置 API Key！** `.env` 文件可选（仅 CLI 模式兼容旧版时需要）。

---

## 🔄 从旧版升级

| 对比 | 旧版 (v0.1–v0.2) | 新版 (v0.5.0) |
|:---|:---|:---|
| LLM 调用 | MCP Server 直接调 LLM | **Agent 调 LLM**，Server 只渲染 Prompt |
| API Key | 必须配置 | **不需要** |
| 检测引擎 | 内置 4 阶段 Pipeline | Agent 自由编排 |
| Skills 管理 | 硬编码在 prompts.py | **独立文件，可编辑更新** |
| 上下文管理 | 固定截断策略 | **Token 预估 + 材料压缩 + 断点续传** |

升级只需：
```bash
cd judicial-doc-anomaly-mcp
git pull
pip install -e .   # 重新安装
```
旧 `.env` 可以删除。

---

## 🐳 文件清单（v0.5.0）

```
89 个跟踪文件
├── src/judicial_lint_mcp/    (16 个 .py 文件)
├── skills/                   (27 个 .md 文件)
├── tests/                   (6 个测试文件)
├── benchmarks/              (3 个基准案例)
├── examples/sample_case/    (脱敏示例)
└── .github/workflows/       (CI 配置)
```

---

## 🪲 已知问题

- `docs/api.md` 内容为 TODO，待补充
- `CONTRIBUTING.md` 部分内容待补充
- CI 临时关闭了 `black --check` 和 `ruff check`（代码格式化检查），后续版本恢复

---

## 🚀 完整 Changelog

```
b455ea1 chore: update run_local_e2e.py
d5f11f4 docs: v0.5.0 - rewrite README, INSTALL_GUIDE, .env.example
3fe9d18 chore: v0.5.0 incremental update - refine skills, prompts, detector, e2e tests
eafd129 feat: v0.5.0 - skill bridge with long-context support + security cleanup
60d1bc0 feat: v0.4.0 - skill runner bridge, report builder, response parser, benchmarks, and e2e tests
```

---

## 📘 使用方式

安装配置后，在 AI IDE（Claude Desktop / Cursor / Trae CN / QClaw）对话中直接说：

```
请用 judicial-lint 检测 ./test_cases/mock_role_evidence_case 目录
```

Agent 会自动调用工具链，输出检测报告。

详细安装指南见 `INSTALL_GUIDE_ZH.md`。

---

**Full Changelog**: https://github.com/lcfactorization/judicial-doc-anomaly-mcp/commits/main
