# 安全运行检测任务操作指南

> 本文档说明如何在脱敏环境下安全运行 judicial-lint-mcp v0.5.1 检测流程，防止敏感信息泄露。

---

## 1. 项目结构概览

```
judicial-doc-anomaly-mcp/
├── src/judicial_lint_mcp/    # 核心代码（MCP Server）
│   ├── server.py             # MCP 工具函数入口
│   ├── report_builder.py     # Markdown + HTML 报告生成
│   ├── detector.py           # 检测引擎
│   ├── preprocessor.py       # 文书预处理
│   └── ...
├── skills/                   # 16维度检测模板
├── tests/                    # 测试用例（已脱敏）
├── test_cases/               # 模拟案例（已脱敏）
├── examples/                 # 示例文书（已脱敏）
├── output/                   # 🚫 生成报告（.gitignore 排除）
├── run_detection.py          # 🚫 检测脚本（.gitignore 排除，含案件数据）
├── .env                      # 🚫 API Key（.gitignore 排除）
└── .env.example              # ✅ 配置模板（无敏感信息）
```

## 2. 敏感信息保护机制

### 2.1 `.gitignore` 排除项

以下文件/目录包含敏感信息，已被 `.gitignore` 排除，**不会被提交到 Git**：

| 排除项 | 原因 |
|--------|------|
| `.env` | 包含真实 API Key |
| `output/` | 生成的检测报告可能含 PII |
| `run_detection.py` | 包含真实案件数据（当事人、案号等） |
| `*检测报告*.html` | HTML 报告可能含 PII |
| `*检测报告*.md` | Markdown 报告可能含 PII |
| `graphify-out/` | LLM 缓存可能含案件数据 |
| `reports/` | 旧版报告目录 |

### 2.2 代码中的匿名化标记

项目中所有测试用例和示例数据已使用统一标记进行匿名化：

| 标记格式 | 用途 | 示例 |
|---------|------|------|
| `[匿名化XX]` | 真实名称替换 | `[匿名化上诉人]`、`[匿名化公司A]` |
| `[匿名化省/市/区]` | 真实地名替换 | `[匿名化省][匿名化市][匿名化区]` |
| `某XXXX` | 真实案号替换 | `（2025）某0602民初XXXX号` |
| `13800000000` | 测试用手机号 | 匹配脱敏正则但不指向真实号码 |
| `320123200001010000` | 测试用身份证号 | 格式正确但不指向真实个人 |

## 3. 运行检测任务

### 3.1 方式一：通过 AI Agent（推荐）

v0.5.1 采用 Bridge Architecture，**MCP Server 不调用任何 LLM**，由 AI Agent 提供智能分析：

```
1. 启动 MCP Server
2. AI Agent 调用 list_skills() 获取可用 Skills
3. AI Agent 调用 plan_pipeline() 获取检测计划
4. AI Agent 逐维度分析文书内容（使用自身 LLM 能力）
5. AI Agent 调用 parse_response() 提交分析结果
6. AI Agent 调用 build_report() 生成 Markdown 报告
7. AI Agent 调用 build_report_html() 生成 HTML 报告（可选）
```

### 3.2 方式二：通过 CLI

```bash
# 安装依赖
pip install -e .

# 运行 CLI（需要 AI Agent 后端）
python -m judicial_lint_mcp.cli detect --input 判决书.md
```

### 3.3 方式三：通过 Python 脚本

```python
import json
from judicial_lint_mcp.server import build_report, build_report_html

# 1. 准备案件数据（⚠️ 注意脱敏）
case_name = "[匿名化上诉人]与[匿名化公司A]劳动争议"
doc_type = "民事判决书（二审）"

# 2. AI Agent 分析后构建维度结果
dimension_results = [
    {
        "dimension": "procedure",
        "risk_level": "high",
        "summary": "程序操作维度摘要...",
        "anomalies": [
            {
                "item_name": "异常项名称",
                "description": "具体表现描述...",
                "beneficiary": "被上诉人（用人单位）",
                "confidence": "high",
                "f_code": "F-03",
                "a_code": "A1",
            }
        ]
    },
    # ... 其他15个维度
]

dim_json = json.dumps(dimension_results, ensure_ascii=False)

# 3. 生成 Markdown 报告
md_report = build_report(
    case_name=case_name,
    dimension_results_json=dim_json,
    doc_type=doc_type,
    model_name="AI Agent (v0.5.1 Bridge)",
)

# 4. 生成 HTML 报告（可选）
html_report = build_report_html(
    case_name=case_name,
    dimension_results_json=dim_json,
    doc_type=doc_type,
    model_name="AI Agent (v0.5.1 Bridge)",
)

# 5. 保存报告
from pathlib import Path
output_dir = Path("output")
output_dir.mkdir(exist_ok=True)
(output_dir / "report.md").write_text(md_report, encoding="utf-8")
(output_dir / "report.html").write_text(html_report, encoding="utf-8")
```

## 4. 新增案件的安全操作流程

当需要检测新的司法文书时，请遵循以下安全流程：

### Step 1：准备文书

```bash
# 将文书放入项目根目录或指定目录
# ⚠️ 文书文件不应提交到 Git（已在 .gitignore 中排除）
```

### Step 2：AI Agent 分析

- AI Agent 读取文书内容
- 逐维度进行异常检测分析
- 构建结构化的 `dimension_results` 数据

### Step 3：生成报告

- 调用 `build_report()` 生成 Markdown
- 调用 `build_report_html()` 生成 HTML（可选）
- 报告保存到 `output/` 目录（.gitignore 排除）

### Step 4：脱敏检查

生成报告后，运行以下命令验证无敏感信息泄露：

```bash
# 检查真实案号
grep -r "苏06民终\|苏0602民初\|粤0106民初" output/

# 检查真实人名/公司名
grep -r "南通\|伯仲\|速润\|陈自强\|王永鑫" output/

# 检查手机号
grep -rP "1[3-9]\d{9}" output/

# 检查身份证号
grep -rP "\d{6}(19|20)\d{2}(0[1-9]|1[0-2])\d{2}\d{3}[\dXx]" output/

# 检查 API Key
grep -rP "sk-[a-f0-9]{10,}" output/
```

### Step 5：如需提交代码

```bash
# 确认 output/ 和 .env 不在跟踪列表中
git status

# 只提交代码和已脱敏的测试数据
git add src/ skills/ tests/ examples/
git commit -m "feat: update detection logic"
```

## 5. 内置脱敏功能

v0.5.1 的 `compact_materials` 工具支持自动脱敏：

```python
from judicial_lint_mcp.server import compact_materials

result = compact_materials(
    materials="原告张某，电话13800000000，案号（2025）某0602民初XXXX号",
    max_tokens=10000,
    anonymize=True  # 启用自动脱敏
)
```

自动脱敏覆盖：
- 手机号 → `1**********`
- 身份证号 → `****`
- 地址 → `某地`
- 案号 → `（****）某号`
- 日期 → `****-**-**`
- 中文姓名（2-4字，后跟特定称谓）→ `某甲`

## 6. 注意事项

1. **禁止独立 LLM 调用**：v0.5.1 Bridge Architecture 不使用独立 LLM API Key，所有智能分析由 AI Agent 提供
2. **output/ 目录不提交**：生成的报告可能含 PII，始终被 .gitignore 排除
3. **run_detection.py 不提交**：该脚本包含案件数据，始终被 .gitignore 排除
4. **测试数据已脱敏**：`tests/` 和 `examples/` 中的数据已全部匿名化，可安全提交
5. **新增文书需脱敏**：检测新文书时，报告中的敏感信息需手动检查或使用 `anonymize=True` 自动处理
