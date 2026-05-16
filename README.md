# 司法文书异常检测 MCP Server / Judicial Document Anomaly Detection MCP Server

> 将司法文书审查 SKILL.md 工程化为可安装的 MCP Server 和 CLI 工具，实现自动化、标准化、可重复的 16 维度深度检测，含 A1-A8 异常分类体系、中立性校验机制和基准案例库。
> 
> Engineering the judicial document review SKILL.md into an installable MCP Server and CLI tool for automated, standardized, reproducible 16-dimensional deep analysis, with A1-A8 anomaly taxonomy, neutrality mechanisms, and benchmark calibration.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Server-green.svg)](https://modelcontextprotocol.io/)

---

## 中文文档

### 这是什么？

这是一个**司法文书异常检测自动化工具**，可以分析判决书、裁决书、行政决定书等法律文书，自动检测出程序违法、证据采信双标、事实认定错误、法律适用错误、逻辑断裂等异常点。每个异常点自动映射到 **A1-A8 统一分类体系**，并执行**中立性反向校验**，确保检测结果客观公正。

**核心优势（相比手动复制 SKILL.md 到 AI 对话框）：**

| 对比项 | 手动操作 SKILL.md | 本 MCP Server 工具 |
|--------|-------------------|-------------------|
| 操作步骤 | 每次复制粘贴提示词 | 一行命令自动运行 |
| 上下文管理 | 容易丢失中间检测结果 | 自动拼接上下文 |
| 多轮迭代 | 手动一步步执行 | 自动按维度顺序检测 |
| 结果一致性 | 每次操作可能有差异 | 标准化流程，结果稳定 |
| 成本可控 | 无法预估 Token 消耗 | `dry_run` 预览成本 |
| 分类标准化 | 无统一编号 | A1-A8 统一分类 |
| 中立性保障 | 无反向校验 | 自动反向异常检测 |
| 结果校准 | 无参照 | 6 个基准案例对比 |

### 快速安装

```bash
# 1. 克隆仓库
git clone https://github.com/lcfactorization/judicial-doc-anomaly-mcp.git
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

### A系列异常分类体系

每个检测到的异常点自动映射到以下统一分类：

| 编号 | 分类名称 | 描述 | 严重度基数 | 双向适用 |
|------|---------|------|-----------|---------|
| A1 | 关键证据未回应 | 对核心证据未予回应或说理 | 0.85 | 是 |
| A2 | 事实认定跳跃 | 推理链条存在断裂 | 0.80 | 是 |
| A3 | 法律适用未解释 | 适用法条但未说明理由 | 0.75 | 是 |
| A4 | 同类证据双重标准 | 对同类证据采用不同标准 | 0.90 | 是 |
| A5 | 程序时间线异常 | 时间顺序异常或超期 | 0.70 | 否 |
| A6 | 回避核心争点 | 对核心争议予以回避 | 0.85 | 是 |
| A7 | 机械复制模板化论证 | 说理呈现模板化特征 | 0.65 | 否 |
| A8 | 举证责任倒置异常 | 举证责任不当转移 | 0.90 | 是 |

### 中立性校验机制

本工具定位为"AI司法推理审计框架"，而非维权工具。内置四大中立性保障：

1. **反向异常检测**：异常指向被告获益时，自动检查原告是否存在诉求膨胀
2. **原告诉求膨胀识别**：识别选择性截取、断章取义等策略
3. **证据可信度反校验**：校验电子证据编辑痕迹、制度文件公示情况
4. **情绪化叙事过滤**：将情绪化判断降级为"存疑"

每个异常点标注：**指向获益方** + **反向校验结果** + **净异常判定**

### 检测维度（16 维）

| 维度 | 说明 | 检测项数 |
|------|------|---------|
| procedure | 程序操作与正当性 | 8 |
| evidence | 证据采信一致性 | 5 |
| fact_finding | 事实认定（核心，26项F编号） | 26 |
| law_application | 法律适用 | 5 |
| discretion | 自由裁量权 | 4 |
| logic | 逻辑闭环 | 4 |
| temporal | 时间一致性 | 4 |
| semantic_drift | 语义漂移 | 4 |
| negative_space | 负空间检测 | 5 |
| case_deviation | 类案偏离量化 | 4 |
| procedure_graph | 程序行为链 | 4 |
| coupling | 惯性耦合分析 | - |
| quality | 文书质量评估（7维100分制） | 7 |
| adversarial | 多角色对抗审查（5角色） | 5 |
| graph | 图结构建模（3类图+Mermaid） | 3 |
| quick_check | 26项翻案速查表 | 26 |

### MCP Tools（11个工具）

| 工具 | 说明 |
|------|------|
| `detect_anomalies` | 完整十六维异常检测（含图建模、质量评估、对抗审查） |
| `quality_assessment` | 七维度质量评估打分（A-F等级，100分制） |
| `build_graph` | 构建证据关系图、程序行为图、法律推理图 |
| `quick_check` | 快速异常检测（翻案速查表 / 单文档扫描） |
| `scan_dimension` | 单维度扫描检测（1-16） |
| `benchmark_compare` | 与基准案例库对比，计算Jaccard相似度 |
| `adversarial_check` | 独立多角色对抗审查 |
| `generate_report` | 生成结构化检测报告 |
| `dry_run` | 预览检测流程和预估Token消耗 |
| `get_detection_rules` | 获取内置检测规则与法条参考 |

### MCP Resources（4个资源）

| 资源URI | 说明 |
|---------|------|
| `judicial-lint://taxonomy` | A1-A8 异常分类体系完整描述 |
| `judicial-lint://neutrality` | 中立性校验机制完整描述 |
| `judicial-lint://dimensions` | 十六维检测框架概要 |
| `judicial-lint://benchmarks` | 基准案例库（6个案例） |

### 基准案例库

| 类别 | 数量 | 用途 |
|------|------|------|
| 明显异常 | 2 | 校准高置信异常检测 |
| 高质量 | 2 | 校准低误报率 |
| 边界模糊 | 2 | 校准灰色地带判定 |

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

An **automated judicial document anomaly detection tool** that analyzes judgments, arbitral awards, and administrative decisions to automatically detect procedural violations, inconsistent evidence evaluation, factual errors, misapplication of law, logical inconsistencies, and other anomalies. Each anomaly is automatically mapped to the **A1-A8 unified taxonomy** with **neutrality reverse-verification** ensuring objective results.

**Key Advantages (vs. manually pasting SKILL.md into AI chat):**

| Aspect | Manual SKILL.md | This MCP Server |
|--------|-----------------|-----------------|
| Steps | Copy-paste prompts each time | One command, fully automated |
| Context | Loses intermediate results | Auto-appends context |
| Iteration | Manual step-by-step | Auto sequential detection |
| Consistency | Varies per run | Standardized, stable |
| Cost | Unpredictable | `dry_run` preview |
| Classification | No unified numbering | A1-A8 taxonomy |
| Neutrality | No reverse check | Auto reverse anomaly detection |
| Calibration | No reference | 6 benchmark cases |

### Quick Install

```bash
# 1. Clone
git clone https://github.com/lcfactorization/judicial-doc-anomaly-mcp.git
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

### A-Series Anomaly Taxonomy

| Code | Category | Description | Severity | Bidirectional |
|------|----------|-------------|----------|---------------|
| A1 | Key Evidence Unaddressed | Core evidence not responded to | 0.85 | Yes |
| A2 | Fact-Finding Leap | Reasoning chain broken | 0.80 | Yes |
| A3 | Law Application Unexplained | Law applied without reasoning | 0.75 | Yes |
| A4 | Dual Standard for Same Evidence | Different standards for same evidence type | 0.90 | Yes |
| A5 | Procedural Timeline Anomaly | Timeline out of order or overdue | 0.70 | No |
| A6 | Core Dispute Avoided | Key dispute points sidestepped | 0.85 | Yes |
| A7 | Template-Style Reasoning | Boilerplate reasoning, not case-specific | 0.65 | No |
| A8 | Burden of Proof Reversal | Burden improperly shifted | 0.90 | Yes |

### Detection Dimensions (16)

| Dimension | Description | Items |
|-----------|-------------|-------|
| procedure | Procedural operations & legitimacy | 8 |
| evidence | Evidence evaluation consistency | 5 |
| fact_finding | Fact-finding (core, 26 F-codes) | 26 |
| law_application | Law application accuracy | 5 |
| discretion | Discretionary power abuse | 4 |
| logic | Logical coherence | 4 |
| temporal | Temporal consistency | 4 |
| semantic_drift | Semantic drift detection | 4 |
| negative_space | Missing information analysis | 5 |
| case_deviation | Case deviation quantification | 4 |
| procedure_graph | Procedural behavior chain | 4 |
| coupling | Inertial coupling analysis | - |
| quality | Quality assessment (7-dim, 100-point) | 7 |
| adversarial | Multi-role adversarial review (5 roles) | 5 |
| graph | Graph modeling (3 types + Mermaid) | 3 |
| quick_check | 26-item reversal checklist | 26 |

### MCP Tools (11)

| Tool | Description |
|------|-------------|
| `detect_anomalies` | Full 16-dimension detection (with graph, quality, adversarial) |
| `quality_assessment` | 7-dimension quality scoring (A-F grade, 100-point) |
| `build_graph` | Build evidence, procedure, reasoning graphs |
| `quick_check` | Quick anomaly detection (reversal checklist / single document) |
| `scan_dimension` | Single dimension scan (1-16) |
| `benchmark_compare` | Compare with benchmark cases (Jaccard similarity) |
| `adversarial_check` | Independent multi-role adversarial review |
| `generate_report` | Generate structured detection report |
| `dry_run` | Preview detection flow and estimated token cost |
| `get_detection_rules` | Get built-in detection rules and legal references |

### MCP Resources (4)

| Resource URI | Description |
|-------------|-------------|
| `judicial-lint://taxonomy` | A1-A8 anomaly taxonomy |
| `judicial-lint://neutrality` | Neutrality verification mechanism |
| `judicial-lint://dimensions` | 16-dimension detection framework |
| `judicial-lint://benchmarks` | Benchmark case library (6 cases) |

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
├── prompts.py         # Prompt templates (SYSTEM_PROMPT, 16 dims, quality, adversarial) / 提示词模板
├── llm_caller.py      # LLM caller (multi-model, cache, token stats) / LLM调用器
├── detector.py        # Core detection engine / 核心检测引擎
├── preprocessor.py    # Structured preprocessing (timeline, evidence index) / 结构化预处理
├── graph_builder.py   # Graph modeling (evidence, procedure, reasoning) / 图结构建模
├── quality_assessor.py # 7-dimension quality assessment / 七维度质量评估
├── adversarial.py     # Multi-role adversarial review / 多角色对抗审查
├── taxonomy.py        # A1-A8 anomaly taxonomy + neutrality mechanism / A系列分类+中立性机制
├── benchmark.py       # Benchmark case library (6 cases) / 基准案例库
├── server.py          # MCP Server (FastMCP) / MCP服务器入口
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
  author = {lcfactorization},
  year = {2026},
  url = {https://github.com/lcfactorization/judicial-doc-anomaly-mcp},
  license = {MIT}
}
```
