# 司法文书异常检测 MCP Server / Judicial Document Anomaly Detection MCP Server

> 将司法文书审查 SKILL.md 工程化为可安装的 MCP Server 和 CLI 工具，实现自动化、标准化、可重复的 12 维度深度检测。
> 
> Engineering the judicial document review SKILL.md into an installable MCP Server and CLI tool for automated, standardized, reproducible 12-dimensional deep analysis.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Server-green.svg)](https://modelcontextprotocol.io/)

---

## 中文文档

### 这是什么？

这是一个**司法文书异常检测自动化工具**，可以分析判决书、裁决书、行政决定书等法律文书，自动检测出程序违法、证据采信双标、事实认定错误、法律适用错误、逻辑断裂等异常点。

**核心优势（相比手动复制 SKILL.md 到 AI 对话框）：**

| 对比项 | 手动操作 SKILL.md | 本 MCP Server 工具 |
|--------|-------------------|-------------------|
| 操作步骤 | 每次复制粘贴提示词 | 一行命令自动运行 |
| 上下文管理 | 容易丢失中间检测结果 | 自动拼接上下文 |
| 多轮迭代 | 手动一步步执行 | 自动按维度顺序检测 |
| 结果一致性 | 每次操作可能有差异 | 标准化流程，结果稳定 |
| 成本可控 | 无法预估 Token 消耗 | `--dry-run` 预览成本 |

### 快速安装

```bash
# 1. 克隆仓库
git clone https://github.com/Justice-and-Equity/judicial-doc-anomaly-mcp.git
cd judicial-doc-anomaly-mcp

# 2. 安装
pip install -e .

# 3. 配置 API Key
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY=你的密钥

# 4. 使用
judicial-lint analyze ./案件目录 -o 报告.md
```

### 在 AI IDE 中使用

**Claude Desktop / Cursor / Trae CN 配置：**

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

配置后，在对话中直接说：*"请用 judicial-lint 检测 /path/to/case 目录"*

### 检测维度（12 维）

| 维度 | 说明 | 检测项数 |
|------|------|---------|
| procedure | 程序操作与正当性 | 8 |
| evidence | 证据采信一致性 | 5 |
| fact_finding | 事实认定（核心） | 26 |
| law_application | 法律适用 | 5 |
| discretion | 自由裁量权 | 4 |
| logic | 逻辑闭环 | 4 |
| temporal | 时间一致性 | 4 |
| semantic_drift | 语义漂移 | 4 |
| negative_space | 负空间检测 | 5 |
| case_deviation | 类案偏离量化 | 4 |
| procedure_graph | 程序行为链 | 4 |
| coupling | 惯性耦合分析 | - |

### 对抗注意力衰减

本工具采用 4 重机制对抗 LLM 长上下文注意力失效：

1. **分步迭代**：每维度独立调用，不一次性输入全部材料
2. **上下文重述**：每步将前序结论作为上下文附加
3. **步骤确认**：每步后要求模型二次确认（是/否）
4. **上下文截断**：仅保留最近 3 个维度结果

### 成本参考

| 检测范围 | 预估 Token | DeepSeek 费用 |
|---------|-----------|--------------|
| 单维度 | ~10,000 | ~¥0.01 |
| 3 维度 | ~30,000 | ~¥0.03 |
| 全维度 | ~120,000 | ~¥0.12 |

### 详细文档

- [中文安装指南（小白友好）](INSTALL_GUIDE_ZH.md)
- [API 文档](docs/api.md)（待补充）
- [贡献指南](CONTRIBUTING.md)（待补充）

---

## English Documentation

### What is this?

An **automated judicial document anomaly detection tool** that analyzes judgments, arbitral awards, and administrative decisions to automatically detect procedural violations, inconsistent evidence evaluation, factual errors, misapplication of law, logical inconsistencies, and other anomalies.

**Key Advantages (vs. manually pasting SKILL.md into AI chat):**

| Aspect | Manual SKILL.md | This MCP Server |
|--------|-----------------|-----------------|
| Steps | Copy-paste prompts each time | One command, fully automated |
| Context | Loses intermediate results | Auto-appends context |
| Iteration | Manual step-by-step | Auto sequential detection |
| Consistency | Varies per run | Standardized, stable |
| Cost | Unpredictable | `--dry-run` preview |

### Quick Install

```bash
# 1. Clone
git clone https://github.com/Justice-and-Equity/judicial-doc-anomaly-mcp.git
cd judicial-doc-anomaly-mcp

# 2. Install
pip install -e .

# 3. Configure API Key
cp .env.example .env
# Edit .env and set LLM_API_KEY=your_key

# 4. Use
judicial-lint analyze ./case_directory -o report.md
```

### Use in AI IDEs

**Claude Desktop / Cursor / Trae CN Configuration:**

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

Then simply say: *"Please detect anomalies in /path/to/case directory using judicial-lint"*

### Detection Dimensions (12)

| Dimension | Description | Items |
|-----------|-------------|-------|
| procedure | Procedural operations & legitimacy | 8 |
| evidence | Evidence evaluation consistency | 5 |
| fact_finding | Fact-finding (core) | 26 |
| law_application | Law application accuracy | 5 |
| discretion | Discretionary power abuse | 4 |
| logic | Logical coherence | 4 |
| temporal | Temporal consistency | 4 |
| semantic_drift | Semantic drift detection | 4 |
| negative_space | Missing information analysis | 5 |
| case_deviation | Case deviation quantification | 4 |
| procedure_graph | Procedural behavior chain | 4 |
| coupling | Inertial coupling analysis | - |

### Anti-Attention-Decay Mechanism

4-layer defense against LLM long-context attention failure:

1. **Step-by-step iteration**: Each dimension called independently
2. **Context restatement**: Previous conclusions appended as context
3. **Step confirmation**: Yes/no confirmation after each step
4. **Context truncation**: Only last 3 dimensions retained

### Cost Reference

| Scope | Est. Tokens | DeepSeek Cost |
|-------|------------|---------------|
| Single dimension | ~10,000 | ~$0.002 |
| 3 dimensions | ~30,000 | ~$0.005 |
| Full detection | ~120,000 | ~$0.02 |

### More Documentation

- [Detailed Install Guide (Chinese)](INSTALL_GUIDE_ZH.md)
- [API Docs](docs/api.md) (TODO)
- [Contributing Guide](CONTRIBUTING.md) (TODO)

---

## Architecture / 架构

```
src/judicial_lint_mcp/
├── __init__.py
├── config.py          # Configuration management / 配置管理
├── prompts.py         # Prompt templates from SKILL.md / 提示词模板
├── llm_caller.py      # LLM caller (multi-model, cache) / LLM调用器
├── detector.py        # Core detection engine / 核心检测引擎
├── server.py          # MCP Server entry / MCP服务器入口
└── cli.py             # CLI entry / 命令行入口
```

## License / 许可证

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing / 贡献

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

欢迎提交 Pull Request！如有重大改动，请先创建 Issue 讨论。

## Citation / 引用

If you use this tool in your research or practice, please cite:

```bibtex
@software{judicial_lint_mcp,
  title = {Judicial Document Anomaly Detection MCP Server},
  author = {Justice-and-Equity},
  year = {2026},
  url = {https://github.com/Justice-and-Equity/judicial-doc-anomaly-mcp},
  license = {MIT}
}
```
