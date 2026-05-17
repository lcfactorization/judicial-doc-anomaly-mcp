# judicial-lint-mcp — AI Agent ↔ Skills Bridge (v0.5.0)

> **MCP Server 桥接器**：连接 AI Agent 与司法文书审查 Skills，零 LLM 调用，支持长上下文。
> 
> **Bridge Architecture**: Connects AI Agents to judicial document review Skills. Zero LLM calls. Long-context support.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Server-green.svg)](https://modelcontextprotocol.io/)
[![Version](https://img.shields.io/badge/version-0.5.0-blue)](https://github.com/lcfactorization/judicial-doc-anomaly-mcp/releases)

---

## 这是什么？ / What is this?

**judicial-lint-mcp** 是一个 **MCP Server 桥接器**，它自己不调用任何 LLM，而是：

1. 把预制的 **Skills**（检测模板、维度定义、Pipeline 规则）加载为结构化数据
2. **渲染** 为 Agent 可直接发送给 LLM 的 Prompt
3. **解析** Agent 拿回的 LLM 响应 → 结构化 JSON
4. **构建** 格式化的 Markdown 检测报告

**Workflow 示意 / How it works：**

```
Agent (你)                   MCP Server (judicial-lint)           Skills 文件
   │                              │                              │
   ├─ list_skills() ──────────────►──────── 加载 skills/ 目录 ────┤
   │◄─ 返回 Skill 列表 ────────────┤                              │
   │                              │                              │
   ├─ plan_pipeline("full_scan") ──►────── 读取 Pipeline 定义 ────┤
   │◄─ 返回阶段计划 (无 Prompt) ───┤                              │
   │                              │                              │
   ├─ render_skill("dim/01") ──────►────── 渲染模板+注入材料 ────┤
   │◄─ System Prompt + User Prompt│                              │
   │                              │                              │
   │   你调用自己的 LLM  ←─────────┤  (MCP Server 不调 LLM!)       │
   │   获得 LLM 响应              │                              │
   │                              │                              │
   ├─ parse_response(响应文本) ────►────── 解析为结构化 JSON ─────┤
   │◄─ {"dimension":..., "anomalies":[...]}                       │
   │                              │                              │
   ├─ build_report(JSON数据) ──────►────── 组装 Markdown 报告 ────┤
   │◄─ 完整检测报告 ──────────────┤                              │
```

**核心设计理念 / Key Principles：**

| 原则 | 说明 |
|:---|:---|
| 🔌 **零 LLM 调用** | MCP Server 不调用任何 LLM，Agent 完全自主掌控 |
| 📦 **Skills 文件化** | 所有检测逻辑以 Markdown 文件存储，可独立编辑更新 |
| 🔄 **长上下文支持** | 提供 token 预估、材料压缩、分步渲染、断点续传 |
| 🎯 **按需渲染** | 16 个检测维度独立渲染，一次只发一个给 LLM，避免注意力衰减 |
| 📊 **结构化输出** | 解析 LLM 响应为 JSON，再组装为标准化报告 |

---

## 中文文档

### 安装

```bash
# 1. 克隆仓库
git clone https://github.com/lcfactorization/judicial-doc-anomaly-mcp.git
cd judicial-doc-anomaly-mcp

# 2. 安装（无需配置 API Key — MCP Server 不调 LLM）
pip install -e .

# 3. 验证
judicial-lint --version
# → judicial-lint 0.5.0
```

**不需要** `.env` 文件！Server 本身不调用任何 LLM。

> 如果你本地有旧版的 `.env` 文件（含 API Key），可以删除或保留——v0.5.0 不再读取它。

### 在 AI IDE 中配置（Claude Desktop / Cursor / Trae CN / QClaw）

```json
{
  "mcpServers": {
    "judicial-lint": {
      "command": "python",
      "args": ["-m", "judicial_lint_mcp.server"],
      "cwd": "/path/to/judicial-doc-anomaly-mcp"
    }
  }
}
```

> ⚠️ 将 `/path/to/` 替换为你的实际路径。Windows 用 `C:\\Users\\你的用户名\\...`。

### 使用方式

配置完成后，在 AI IDE 中直接对话。典型工作流：

```
你: 帮我检测 ./case 目录下的司法文书异常

Agent 会自动调用:
  list_skills → 了解有哪些检测能力
  plan_pipeline("full_scan") → 获取 5 阶段执行计划
  render_skill("dimensions/01_procedure", {materials: ...}) → 获取程序维度 Prompt
  → Agent 将 Prompt 发给自己的 LLM
  → parse_response(LLM响应) → 获得结构化结果
  → 逐维度重复...
  build_report(所有维度结果) → 输出完整检测报告
```

### MCP Tools（10 个工具）

| 工具 | 用途 | 关键参数 |
|:---|:---|:---|
| `list_skills` | 列出所有可用检测 Skills | — |
| `plan_pipeline` | 获取 Pipeline 阶段计划（不含 Prompt，避免上下文溢出） | `pipeline_name` |
| `pipeline_progress` | 查询/更新 Pipeline 执行进度，支持断点续传 | `action`, `pipeline_id` |
| `render_skill` | 渲染单个 Skill 为 System + User Prompt | `skill_name`, `variables` |
| `render_pipeline` | 渲染整条 Pipeline（返回一系列 Prompt 列表） | `pipeline_name`, `variables` |
| `estimate_tokens` | 预估 Skill/Pipeline + 材料的总 token 数 | `skill_name`/`pipeline_name`, `materials_chars` |
| `compact_materials` | 压缩案件材料以适应 token 预算 | `text`, `target_tokens` |
| `parse_response` | 将 LLM 响应解析为结构化 JSON | `skill_name`, `response_text` |
| `build_report` | 用结构化数据组装 Markdown 检测报告 | `report_data` (JSON) |
| `write_skill` | 更新 Skill 文件内容 | `skill_name`, `content` |

### MCP Resources（3 个资源）

| Resource URI | 说明 |
|:---|:---|
| `judicial-lint://skills` | 全部可用 Skill 列表（含标题、类型、层级、依赖） |
| `judicial-lint://taxonomy` | A1-A8 异常分类体系（供 Agent 参考） |
| `judicial-lint://system` | 全局 System Prompt（供 Agent 在调用 LLM 时使用） |

### Skills 结构

```
skills/
├── _system.md          # 全局 System Prompt
├── _taxonomy.md        # A1-A8 异常分类体系
├── _neutrality.md      # 中立性校验机制
├── _output_format.md    # 输出格式规范
├── dimensions/         # 16 个检测维度（每个维度一个独立 Skill）
│   ├── 01_procedure.md
│   ├── 02_evidence.md
│   ├── 03_fact_finding.md
│   ├── ...
│   └── 16_coupling.md
├── phases/             # 检测阶段 Skill
│   ├── preprocessor.md
│   ├── graph.md
│   ├── quality.md
│   ├── adversarial.md
│   └── quick_check.md
└── pipelines/          # Pipeline 定义（组合多个 Skill）
    ├── full_scan.md
    ├── quick_scan.md
    └── evidence_focus.md
```

### 长上下文支持（v0.5.0 新增）

| 功能 | 工具 | 说明 |
|:---|:---|:---|
| Token 预算 | `estimate_tokens` | 渲染前预估，超出上下文窗口时自动推荐应对策略 |
| 材料压缩 | `compact_materials` | 两阶段压缩（关键事实提取 → 纲要生成） |
| 分步渲染 | `render_skill` | 每次只渲染一个维度，不一次性发送所有 Prompt |
| 断点续传 | `plan_pipeline` + `pipeline_progress` | 记录执行阶段，支持中断后从断点恢复 |

### 项目架构

```
src/judicial_lint_mcp/
├── __init__.py
├── server.py           # MCP Server 入口 (FastMCP, 10 Tools + 3 Resources)
├── skill_runner.py     # Skill 加载器 + 模板渲染器 (v0.5.0 核心)
├── report_builder.py   # 报告构建器：结构化数据 → Markdown 报告
├── response_parser.py  # 响应解析器：LLM 响应 → 结构化 JSON
├── config.py           # 配置管理 (Pydantic models)
├── models.py           # 数据模型定义
├── prompts.py          # Prompt 模板 (兼容旧版，新版优先使用 Skills)
├── llm_caller.py       # LLM 调用器 (为需要直接调用的场景保留)
├── detector.py         # 核心检测引擎 (兼容旧版)
├── preprocessor.py     # 结构化预处理 (时间线、证据索引)
├── graph_builder.py    # 图结构建模 (证据图/程序图/推理图)
├── quality_assessor.py # 七维度质量评估 (100 分制)
├── adversarial.py      # 多角色对抗审查 (5 角色)
├── taxonomy.py         # A1-A8 异常分类 + 中立性机制
├── benchmark.py        # 基准案例库 (6 个案例)
└── cli.py              # CLI 命令行入口
```

### 从旧版升级

v0.1.0 / v0.2.0 是**直接调用 LLM** 的异常检测工具。v0.5.0 重构为 **Skills 桥接器**，自己不再调用 LLM：

| 对比 | 旧版 (v0.1-0.2) | 新版 (v0.5.0) |
|:---|:---|:---|
| LLM 调用 | MCP Server 直接调 LLM | Agent 调 LLM，Server 只渲染 Prompt |
| API Key | 必须配置 | **不需要** |
| 检测引擎 | 内置 4 阶段 Pipeline | Agent 自由编排 |
| Skills 管理 | 硬编码在 prompts.py | **独立文件，可编辑更新** |
| 上下文管理 | 固定截断策略 | **Token 预估 + 材料压缩 + 断点续传** |

升级只需重新 `git pull && pip install -e .`，旧 `.env` 可以删除。

---

## English Documentation

### What is this?

**judicial-lint-mcp** is an **MCP Server bridge** — it does NOT call any LLM itself. Instead, it:

1. Loads pre-built **Skills** (detection templates, dimension definitions, pipeline rules)
2. **Renders** them as prompts for the Agent to send to its own LLM
3. **Parses** LLM responses into structured JSON
4. **Builds** formatted Markdown detection reports

The Agent retains full control over LLM selection, parameters, and decision-making.

### Install

```bash
git clone https://github.com/lcfactorization/judicial-doc-anomaly-mcp.git
cd judicial-doc-anomaly-mcp
pip install -e .
judicial-lint --version  # → 0.5.0
```

**No API key needed!** The server makes zero LLM calls.

### AI IDE Configuration

```json
{
  "mcpServers": {
    "judicial-lint": {
      "command": "python",
      "args": ["-m", "judicial_lint_mcp.server"],
      "cwd": "/path/to/judicial-doc-anomaly-mcp"
    }
  }
}
```

Replace `/path/to/` with your actual path.

### MCP Tools (10)

| Tool | Purpose |
|:---|:---|
| `list_skills` | List all available detection skills |
| `plan_pipeline` | Get pipeline phase plan (metadata only, no prompts) |
| `pipeline_progress` | Track/resume pipeline execution progress |
| `render_skill` | Render a single skill as System + User Prompt |
| `render_pipeline` | Render an entire pipeline (returns list of prompts) |
| `estimate_tokens` | Estimate total tokens for skill/pipeline + materials |
| `compact_materials` | Compress case materials to fit token budget |
| `parse_response` | Parse LLM response into structured JSON |
| `build_report` | Build Markdown report from structured data |
| `write_skill` | Update skill file content |

### MCP Resources (3)

| URI | Content |
|:---|:---|
| `judicial-lint://skills` | Full skill list with metadata |
| `judicial-lint://taxonomy` | A1-A8 anomaly classification |
| `judicial-lint://system` | Global system prompt |

### Skills Structure

```
skills/
├── _system.md          # Global System Prompt
├── _taxonomy.md        # A1-A8 Taxonomy
├── _neutrality.md      # Neutrality Mechanism
├── _output_format.md    # Output Format
├── dimensions/         # 16 detection dimensions
├── phases/             # Detection phase skills
└── pipelines/          # Pipeline definitions
```

### Long-Context Support (v0.5.0)

| Feature | Tool |
|:---|:---|
| Token budgeting | `estimate_tokens` |
| Material compression | `compact_materials` |
| Step-by-step rendering | `render_skill` (one at a time) |
| Resume from breakpoint | `plan_pipeline` + `pipeline_progress` |

---

## License / 许可证

MIT License — see [LICENSE](LICENSE).

## Contributing / 贡献

Pull requests welcome! For major changes, please open an issue first.

欢迎提交 Pull Request！如有重大改动，请先创建 Issue 讨论。

## Citation / 引用

```bibtex
@software{judicial_lint_mcp,
  title = {Judicial Document Anomaly Detection MCP Server},
  author = {lcfactorization},
  year = {2026},
  url = {https://github.com/lcfactorization/judicial-doc-anomaly-mcp},
  license = {MIT}
}
```