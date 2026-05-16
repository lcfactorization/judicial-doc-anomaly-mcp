# 司法文书异常检测 MCP Server - 从零开始安装指南

> 本指南面向零基础用户，手把手教你在 Windows 11 上安装并使用司法文书异常检测工具。

---

## 目录

1. [这是什么工具？](#1-这是什么工具)
2. [安装前准备](#2-安装前准备)
3. [在 Trae CN 中使用](#3-在-trae-cn-中使用)
4. [在 Cursor 中使用](#4-在-cursor-中使用)
5. [在 Claude Desktop 中使用](#5-在-claude-desktop-中使用)
6. [命令行独立使用](#6-命令行独立使用)
7. [准备测试案例](#7-准备测试案例)
8. [第一次测试](#8-第一次测试)
9. [常见问题](#9-常见问题)

---

## 1. 这是什么工具？

这是一个**司法文书异常检测工具**，可以自动分析判决书、裁决书等法律文书，检测出：

- 程序操作是否异常
- 证据采信是否双标
- 事实认定是否有错误（26项精细检测）
- 法律适用是否正确
- 逻辑是否自相矛盾
- 是否存在偏向某一方的"结构性偏差"

**相比直接复制 SKILL.md 到 AI 对话框的优势：**

| 对比项 | SKILL.md 手动操作 | MCP Server 自动化工具 |
|--------|-------------------|----------------------|
| 操作步骤 | 每次都要复制粘贴提示词 | 一行命令自动运行 |
| 上下文管理 | 容易丢失前面检测结果 | 自动拼接上下文，不丢失 |
| 多轮迭代 | 手动一步步来 | 自动按维度顺序检测 |
| 结果一致性 | 每次操作可能有差异 | 标准化流程，结果稳定 |
| 成本可控 | 无法预估 Token 消耗 | 提供 `--dry-run` 预览 |

---

## 2. 安装前准备

### 2.1 安装 Python

1. 打开浏览器，访问：https://www.python.org/downloads/
2. 点击黄色按钮 "Download Python 3.12.x"（或最新版本）
3. 下载完成后，双击安装程序
4. **重要**：勾选底部的 "Add Python to PATH"
5. 点击 "Install Now"
6. 安装完成后，打开 PowerShell（按 Win 键，输入 PowerShell，回车）
7. 输入以下命令验证：

```powershell
python --version
```

如果显示版本号（如 Python 3.12.3），说明安装成功。

### 2.2 安装 Git（可选，用于从 GitHub 下载）

1. 访问：https://git-scm.com/download/win
2. 下载并安装
3. 验证：

```powershell
git --version
```

### 2.3 获取 LLM API Key

你需要一个 AI 模型的 API Key，推荐以下任一：

| 提供商 | 推荐模型 | 申请地址 | 价格参考 |
|--------|---------|---------|---------|
| DeepSeek | deepseek-chat | https://platform.deepseek.com | 便宜，中文能力强 |
| 阿里通义 | qwen-plus | https://dashscope.console.aliyun.com | 中文优秀 |
| OpenAI | gpt-4o | https://platform.openai.com | 效果好，较贵 |
| 智谱 | glm-4 | https://open.bigmodel.cn | 国产，性价比高 |

**以 DeepSeek 为例：**

1. 注册账号
2. 进入控制台，找到 "API Keys"
3. 点击 "创建 API Key"
4. 复制保存（只显示一次）

---

## 3. 在 Trae CN 中使用

### 3.1 下载项目

**方法一：使用 Git（推荐）**

打开 PowerShell，输入：

```powershell
# 切换到你想存放项目的目录
cd Documents

# 下载项目
git clone https://github.com/Justice-and-Equity/judicial-doc-anomaly-mcp.git

# 进入项目目录
cd judicial-doc-anomaly-mcp
```

**方法二：手动下载**

1. 访问 GitHub 项目页面
2. 点击绿色 "Code" 按钮
3. 点击 "Download ZIP"
4. 解压到任意目录

### 3.2 安装依赖

```powershell
# 进入项目目录
cd judicial-doc-anomaly-mcp

# 创建虚拟环境（推荐）
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 如果上面命令报错，执行以下命令允许脚本运行
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 再次激活
.\venv\Scripts\Activate.ps1

# 安装依赖
pip install -e .
```

看到 "Successfully installed judicial-lint-mcp" 说明安装成功。

### 3.3 配置 API Key

```powershell
# 复制环境变量模板
Copy-Item .env.example .env

# 用记事本编辑
notepad .env
```

在打开的文件中，修改以下内容：

```ini
LLM_PROVIDER=deepseek
LLM_API_KEY=你的API密钥粘贴在这里
LLM_MODEL=deepseek-chat
```

保存并关闭。

### 3.4 在 Trae CN 中配置 MCP Server

1. 打开 Trae CN
2. 点击左下角设置图标（齿轮）
3. 找到 "MCP Servers" 或 "AI 服务" 设置
4. 点击 "添加 MCP Server"
5. 填写以下信息：

| 字段 | 值 |
|------|-----|
| 名称 | `judicial-lint` |
| 命令 | `python` |
| 参数 | `-m judicial_lint_mcp.server` |
| 工作目录 | `C:\Users\你的用户名\Documents\judicial-doc-anomaly-mcp` |

6. 保存配置
7. 重启 Trae CN

### 3.5 在 Trae CN 中使用

1. 打开任意对话
2. 输入：

```
请用 judicial-lint 检测 C:\Users\你的用户名\Documents\my_case 目录
```

3. AI 会自动调用检测工具并返回报告

---

## 4. 在 Cursor 中使用

### 4.1 安装项目

步骤同 3.1 和 3.2。

### 4.2 配置 MCP Server

1. 打开 Cursor
2. 按 `Ctrl + Shift + P` 打开命令面板
3. 输入 "Cursor Settings"，回车
4. 找到 "MCP" 或 "Features" 标签
5. 点击 "Edit MCP Settings"
6. 在打开的 JSON 文件中添加：

```json
{
  "mcpServers": {
    "judicial-lint": {
      "command": "python",
      "args": ["-m", "judicial_lint_mcp.server"],
      "cwd": "C:\\Users\\你的用户名\\Documents\\judicial-doc-anomaly-mcp"
    }
  }
}
```

7. 保存文件
8. 重启 Cursor

### 4.3 使用

在 Cursor 的 AI 对话中输入：

```
用 judicial-lint 分析这个案件目录：C:\path\to\your\case
```

---

## 5. 在 Claude Desktop 中使用

### 5.1 安装项目

步骤同 3.1 和 3.2。

### 5.2 配置 MCP Server

1. 找到 Claude Desktop 配置文件：
   - 按 `Win + R`
   - 输入 `%APPDATA%\Claude`
   - 回车
2. 找到 `claude_desktop_config.json` 文件
3. 用记事本打开，添加：

```json
{
  "mcpServers": {
    "judicial-lint": {
      "command": "python",
      "args": ["-m", "judicial_lint_mcp.server"],
      "cwd": "C:\\Users\\你的用户名\\Documents\\judicial-doc-anomaly-mcp"
    }
  }
}
```

4. 保存
5. 重启 Claude Desktop

### 5.3 使用

在对话中输入：

```
请检测 C:\path\to\case 目录下的司法文书
```

---

## 6. 命令行独立使用

如果不想在 AI IDE 中使用，也可以直接在命令行运行：

```powershell
# 激活虚拟环境（如果还没激活）
cd judicial-doc-anomaly-mcp
.\venv\Scripts\Activate.ps1

# 查看可用检测维度
judicial-lint list-dimensions

# 预览检测流程（不实际调用 AI，不花钱）
judicial-lint dry-run C:\path\to\your\case

# 执行检测，输出到文件
judicial-lint analyze C:\path\to\your\case -o report.md

# 指定模型和维度
judicial-lint analyze C:\path\to\your\case `
  -m deepseek-chat `
  -d procedure -d evidence -d fact_finding `
  -o report.md
```

---

## 7. 准备测试案例

### 7.1 创建案例目录

```powershell
# 创建测试案例目录
mkdir C:\Users\你的用户名\Documents\test_case
```

### 7.2 转换文书为 Markdown

将你的司法文书转换为 `.md` 格式，放在该目录下：

```
test_case/
├── 判决书.md          # 必需
├── 起诉状.md          # 推荐
├── 答辩状.md          # 推荐
├── 证据清单.md        # 推荐
├── 庭审笔录.md        # 推荐
├── 上诉状.md          # 推荐
└── 时间线.md          # 推荐
```

**转换方法：**

1. 打开 Word/PDF 文书
2. 复制全文
3. 新建文本文件，粘贴
4. 保存为 `.md` 扩展名

或使用工具批量转换：
- PDF → Markdown：使用 `markitdown` 工具
- Word → Markdown：复制粘贴即可

### 7.3 脱敏处理

在上传或测试前，建议对敏感信息进行脱敏：

- 姓名 → 张某、李某
- 公司名 → A公司、B公司
- 金额 → 可保留（不影响检测）
- 案号 → 可保留

---

## 8. 第一次测试

### 8.1 Dry Run（不花钱）

```powershell
judicial-lint dry-run C:\Users\你的用户名\Documents\test_case
```

这会显示：
- 材料完整性评分
- 缺失哪些材料
- 预估 Token 消耗

### 8.2 单维度测试（省钱）

```powershell
# 只检测一个维度，成本低
judicial-lint analyze C:\Users\你的用户名\Documents\test_case `
  -d fact_finding `
  -o test_report.md
```

### 8.3 全维度测试

```powershell
# 检测全部 12 个维度
judicial-lint analyze C:\Users\你的用户名\Documents\test_case `
  -o full_report.md
```

### 8.4 查看报告

```powershell
# 用默认程序打开 Markdown 报告
start full_report.md

# 或用 VS Code 打开
code full_report.md
```

### 8.5 对比 SKILL.md 效果

**测试方法：**

1. 用 MCP Server 检测同一案件，保存报告
2. 将相同材料复制，粘贴到 AI 对话框，附上 SKILL.md 提示词
3. 对比两份报告：
   - 检测出的异常点数量
   - 是否有遗漏
   - 分析深度
   - 一致性

**预期结果：**

MCP Server 应该：
- 检测出更多异常点（因为分步迭代，不丢失上下文）
- 分析更深入（每步有对抗校验）
- 结果更稳定（标准化流程）
- 有量化评级（耦合分析、风险等级）

---

## 9. 常见问题

### Q1: 安装时提示权限错误怎么办？

```
ERROR: Could not install packages due to an OSError: [WinError 5] 拒绝访问
```

**解决方法：**

```powershell
# 方法一：使用虚拟环境（推荐）
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e .

# 方法二：安装到用户目录
pip install -e . --user

# 方法三：以管理员身份运行 PowerShell
# 右键 PowerShell → 以管理员身份运行
```

### Q2: 激活虚拟环境时报错？

```
.\venv\Scripts\Activate.ps1 : 无法加载文件...
```

**解决方法：**

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Q3: 如何知道检测花了多少钱？

```powershell
# 检测前预览
judicial-lint dry-run ./case

# 检测完成后会显示总 Token 消耗
```

**成本参考（以 DeepSeek 为例）：**

| 检测范围 | 预估 Token | 预估费用 |
|---------|-----------|---------|
| 单维度 | ~10,000 | ~¥0.01 |
| 3个维度 | ~30,000 | ~¥0.03 |
| 全维度 | ~120,000 | ~¥0.12 |

### Q4: 检测速度慢怎么办？

- 使用更快的模型（如 `deepseek-chat` 比 `gpt-4` 快）
- 减少检测维度（`-d procedure -d evidence`）
- 确保网络稳定

### Q5: 报告质量不好怎么办？

- 换用更强的模型（`gpt-4o` 或 `claude-3-opus`）
- 确保材料完整（至少要有判决书）
- 材料质量影响检测结果

### Q6: 如何在多个 AI IDE 之间共享配置？

将项目放在公共目录，各 IDE 配置相同的 `cwd` 路径即可。

### Q7: 如何更新到最新版本？

```powershell
cd judicial-doc-anomaly-mcp
git pull
pip install -e .
```

---

## 10. 下一步

- 阅读完整文档：[README.md](README.md)
- 查看示例：[examples/](examples/)
- 报告问题：[GitHub Issues](https://github.com/Justice-and-Equity/judicial-doc-anomaly-mcp/issues)
- 参与贡献：欢迎提交 Pull Request

---

**祝你使用愉快！如有问题，欢迎反馈。**
