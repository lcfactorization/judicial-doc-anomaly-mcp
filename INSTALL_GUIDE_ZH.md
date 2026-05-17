# 司法文书异常检测 MCP Server — 从零安装指南（v0.5.0）

> 本指南面向零基础用户，Windows / macOS / Linux 均适用。

---

## 目录

1. [这是什么工具？](#1-这是什么工具)
2. [安装前准备](#2-安装前准备)
3. [安装 MCP Server](#3-安装-mcp-server)
4. [配置 AI IDE](#4-配置-ai-ide)
5. [第一次使用](#5-第一次使用)
6. [典型工作流示例](#6-典型工作流示例)
7. [常见问题](#7-常见问题)

---

## 1. 这是什么工具？

**judicial-lint-mcp v0.5.0** 是一个 **MCP Server 桥接器**。

它的核心功能是：把预制的 **司法文书检测 Skills**（16 个检测维度的 Prompt 模板）加载、渲染、解析，**自己不调用任何 LLM**。

也就是说：你告诉 AI Agent 去做检测，Agent 会自动调用这个 MCP Server 获取检测 Prompt，再发给它自己的 LLM，最后把结果组装成报告。

---

## 2. 安装前准备

### 需要准备什么？

| 项目 | 说明 |
|:---|:---|
| Python | 3.10 或更高，[下载地址](https://www.python.org/downloads/) |
| Git | [下载地址](https://git-scm.com/download/win) |
| AI IDE | Claude Desktop、Cursor、Trae CN、QClaw 任选其一 |

### 检查 Python 版本

打开命令行（Windows 按 `Win+R`，输入 `cmd`，回车）：

```bash
python --version
# 应显示 Python 3.10.x 或更高
```

如果显示 `python` 不是命令，尝试：

```bash
python3 --version
```

---

## 3. 安装 MCP Server

### 3.1 克隆仓库

```bash
git clone https://github.com/lcfactorization/judicial-doc-anomaly-mcp.git
cd judicial-doc-anomaly-mcp
```

### 3.2 安装

```bash
pip install -e .
```

> ⚠️ **不需要配置 API Key！** v0.5.0 的 MCP Server 不调用任何 LLM，不需要任何密钥。

### 3.3 验证安装

```bash
judicial-lint --version
# → judicial-lint 0.5.0
```

看到版本号即安装成功。

---

## 4. 配置 AI IDE

### 4.1 找到配置文件

| AI IDE | 配置文件路径 |
|:---|:---|
| **QClaw** | `C:\Users\你的用户名\.qclaw\config.json` 或 Settings → MCP |
| **Claude Desktop** | `%APPDATA%\Claude\claude_desktop_config.json` |
| **Cursor** | `~/.cursor/mcp.json`（或 Settings → MCP）|
| **Trae CN** | `~/.trae/mcp.json`（或 Settings → MCP）|

### 4.2 添加配置

打开配置文件，在 `mcpServers` 中添加：

```json
{
  "mcpServers": {
    "judicial-lint": {
      "command": "python",
      "args": ["-m", "judicial_lint_mcp.server"],
      "cwd": "C:\\Users\\你的用户名\\Documents\\Obsidian Vault\\judicial-doc-anomaly-mcp"
    }
  }
}
```

> ⚠️ Windows 用户注意路径格式：用 `\\` 或 `/`，不要用单个 `\`

**QClaw 用户**：也可以在 Settings → MCP 页面直接添加，cwd 填写你的实际路径。

### 4.3 重启 AI IDE

保存配置后，**完全退出并重新启动** AI IDE，让 MCP Server 加载。

---

## 5. 第一次使用

重启 AI IDE 后，在对话中直接说：

```
请用 judicial-lint 检测 ./test_cases/mock_role_evidence_case 目录下的司法文书
```

Agent 会自动调用 MCP Server 的工具链，输出检测报告。

---

## 6. 典型工作流示例

当你说"帮我检测案件"时，Agent 会：

```
Step 1: list_skills()
  → 列出全部 16 个检测维度 + 5 个阶段 + 3 条 Pipeline

Step 2: plan_pipeline("full_scan")
  → 获取 5 阶段执行计划（预处理→图建模→逐维度检测→质量评估→对抗审查）

Step 3: render_skill("dimensions/01_procedure", materials=判决书文本)
  → 渲染程序维度检测 Prompt

Step 4: Agent 把 Prompt 发给自己的 LLM（例如 Qwen、GLM、GPT）

Step 5: parse_response(LLM的回复)
  → 解析为结构化 JSON

Step 6: 对剩余 15 个维度重复 Step 3-5

Step 7: build_report(所有维度结果)
  → 生成完整 Markdown 检测报告
```

---

## 7. 常见问题

### Q: 安装时报错 `ModuleNotFoundError: No module named 'mcp'`

```bash
pip install mcp
pip install -e .
```

### Q: AI IDE 中看不到 judicial-lint 工具

1. 确认配置文件格式正确（JSON 语法无误）
2. 重启 AI IDE（不是刷新，是完全退出再打开）
3. 检查 cwd 路径是否正确

### Q: 检测结果为空？

MCP Server 只负责渲染 Prompt，不调 LLM。如果结果为空，可能是：
- Agent 没有正确调用 LLM
- 案件材料为空或格式不对

### Q: Windows 路径怎么写？

用双反斜杠或正斜杠：
```
# ✅ 正确
"C:\\Users\\stere\\Projects\\judicial-doc-anomaly-mcp"
"C:/Users/stere/Projects/judicial-doc-anomaly-mcp"

# ❌ 错误
"C:\Users\stere\Projects\judicial-doc-anomaly-mcp"
```

---

## 更新到新版本

```bash
cd judicial-doc-anomaly-mcp
git pull
pip install -e .
```

旧版配置不需要改动，MCP Server 自动使用最新版本。
