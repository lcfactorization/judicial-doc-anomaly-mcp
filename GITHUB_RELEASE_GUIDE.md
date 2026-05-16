# GitHub 开源发布完整指南

> 从零开始，手把手教你将司法文书异常检测 MCP Server 发布到 GitHub，实现 MIT 许可、完全开源。

---

## 目录

1. [发布前准备](#1-发布前准备)
2. [创建 GitHub 仓库](#2-创建-github-仓库)
3. [上传项目到 GitHub](#3-上传项目到-github)
4. [完善项目文档](#4-完善项目文档)
5. [发布第一个 Release](#5-发布第一个-release)
6. [推广与维护](#6-推广与维护)
7. [常见问题](#7-常见问题)

---

## 1. 发布前准备

### 1.1 检查项目清单

在上传之前，确认以下文件都已创建：

```
judicial-doc-anomaly-mcp/
├── src/judicial_lint_mcp/     ✅ 源代码（6个文件）
├── tests/                     ✅ 测试文件
├── examples/sample_case/      ✅ 示例案件目录
├── pyproject.toml             ✅ Python 包配置
├── .env.example               ✅ 环境变量模板
├── config.example.yaml        ✅ 配置文件模板
├── LICENSE                    ⚠️ 需要创建（见下方）
├── README.md                  ✅ 中英双语说明
├── INSTALL_GUIDE_ZH.md        ✅ 中文安装指南
├── .gitignore                 ✅ Git 忽略文件
└── GITHUB_RELEASE_GUIDE.md    ✅ 本文件
```

### 1.2 创建 LICENSE 文件

在项目根目录创建 `LICENSE` 文件（纯文本，无扩展名）：

```text
MIT License

Copyright (c) 2026 Justice-and-Equity

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

**在 PowerShell 中创建：**

```powershell
cd judicial-doc-anomaly-mcp

@'
MIT License

Copyright (c) 2026 Justice-and-Equity

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'@ | Out-File -FilePath LICENSE -Encoding utf8
```

### 1.3 清理敏感信息

```powershell
# 检查是否有敏感文件
git status

# 确保 .env 不在跟踪列表中
# 如果之前误添加了，执行：
git rm --cached .env 2>$null

# 删除本地 .env 文件（如果有）
Remove-Item .env -ErrorAction SilentlyContinue
Remove-Item config.yaml -ErrorAction SilentlyContinue
```

### 1.4 确认 .gitignore 内容

确保 `.gitignore` 包含以下内容：

```gitignore
# 敏感信息
.env
*.key
*.pem
config.yaml

# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/
dist/
build/

# 缓存
.judicial_lint_cache/
.cache/

# 输出文件
output/
*.report.md

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
```

---

## 2. 创建 GitHub 仓库

### 2.1 登录 GitHub

1. 打开浏览器，访问 https://github.com
2. 登录你的账号（如果没有，点击 "Sign up" 注册）

### 2.2 创建新仓库

1. 点击右上角的 **"+"** 图标
2. 选择 **"New repository"**

3. 填写以下信息：

| 字段 | 填写内容 |
|------|---------|
| **Owner** | 选择你的账号或组织（如 `Justice-and-Equity`） |
| **Repository name** | `judicial-doc-anomaly-mcp` |
| **Description** | `MCP Server for automated judicial document anomaly detection. 12-dimensional analysis with anti-attention-decay mechanism.` |
| **Visibility** | ✅ **Public**（必须选公开才能开源） |
| **Initialize this repository with** | ❌ **不要勾选任何选项**（我们已有本地文件） |

4. 点击 **"Create repository"** 按钮

### 2.3 获取仓库地址

创建成功后，你会看到一个页面，显示类似这样的地址：

```
https://github.com/Justice-and-Equity/judicial-doc-anomaly-mcp.git
```

**复制这个地址，后面要用。**

---

## 3. 上传项目到 GitHub

### 3.1 安装 Git（如果还没装）

```powershell
# 检查是否已安装
git --version

# 如果提示找不到命令，下载并安装：
# 访问 https://git-scm.com/download/win
# 下载后双击安装，全部使用默认设置即可
```

### 3.2 初始化本地 Git 仓库

打开 PowerShell，进入项目目录：

```powershell
# 进入项目目录
cd C:\Users\你的用户名\Documents\judicial-doc-anomaly-mcp

# 初始化 Git 仓库
git init
```

### 3.3 添加远程仓库

```powershell
# 添加 GitHub 远程仓库地址
# 将下面的 URL 替换为你自己的仓库地址
git remote add origin https://github.com/Justice-and-Equity/judicial-doc-anomaly-mcp.git

# 验证是否添加成功
git remote -v
```

你应该看到类似输出：

```
origin  https://github.com/Justice-and-Equity/judicial-doc-anomaly-mcp.git (fetch)
origin  https://github.com/Justice-and-Equity/judicial-doc-anomaly-mcp.git (push)
```

### 3.4 添加并提交文件

```powershell
# 添加所有文件到暂存区
git add .

# 查看状态（确认没有敏感文件）
git status
```

检查输出，确保没有 `.env`、`config.yaml` 等敏感文件。

```powershell
# 提交文件
git commit -m "feat: initial release - judicial document anomaly detection MCP server

- 12-dimensional analysis framework (procedure, evidence, fact-finding x26, etc.)
- MCP Server for AI IDE integration (Claude Desktop, Cursor, Trae CN)
- CLI tool for batch processing and scripting
- Long-context anti-attention-decay mechanism
- Multi-model support (OpenAI, DeepSeek, Qwen, Zhipu, Moonshot)
- Local caching for cost control
- Dry-run mode for token estimation
- MIT License, fully open source"
```

### 3.5 推送到 GitHub

```powershell
# 将分支重命名为 main
git branch -M main

# 推送到 GitHub
git push -u origin main
```

### 3.6 身份验证

如果提示登录，有以下几种方式：

**方式一：使用 GitHub CLI（推荐）**

```powershell
# 安装 GitHub CLI
winget install GitHub.cli

# 登录
gh auth login

# 按提示操作：
# 1. 选择 GitHub.com
# 2. 选择 HTTPS
# 3. 选择 Login with a web browser
# 4. 复制验证码，在浏览器中完成认证

# 认证后再次推送
git push -u origin main
```

**方式二：使用 Personal Access Token**

1. 访问 https://github.com/settings/tokens
2. 点击 **"Generate new token"** → **"Generate new token (classic)"**
3. 填写 Note（如 `judicial-lint-mcp`）
4. 勾选 **`repo`** 权限
5. 点击 **"Generate token"**
6. **立即复制 Token**（只显示一次！）
7. 推送时输入：
   - Username: 你的 GitHub 用户名
   - Password: 粘贴刚才复制的 Token

### 3.7 验证上传

1. 刷新你的 GitHub 仓库页面
2. 确认所有文件都已显示
3. 检查 README.md 是否正确渲染

---

## 4. 完善项目文档

### 4.1 必须上传的文件清单

| 文件 | 用途 | 状态 |
|------|------|------|
| `README.md` | 项目首页，中英双语 | ✅ 已创建 |
| `LICENSE` | MIT 许可证 | ✅ 已创建 |
| `INSTALL_GUIDE_ZH.md` | 中文安装指南（小白友好） | ✅ 已创建 |
| `pyproject.toml` | Python 包配置 | ✅ 已创建 |
| `.env.example` | 环境变量模板 | ✅ 已创建 |
| `config.example.yaml` | 配置文件模板 | ✅ 已创建 |
| `src/` | 源代码 | ✅ 已创建 |
| `tests/` | 测试文件 | ✅ 已创建 |
| `examples/` | 示例案件 | ✅ 已创建 |

### 4.2 建议补充的文件

**CONTRIBUTING.md（贡献指南）：**

```markdown
# 贡献指南 / Contributing Guide

## 如何贡献

1. Fork 本仓库
2. 创建你的特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交你的改动 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 开发环境设置

```bash
pip install -e ".[dev]"
pytest
```

## 代码规范

- 使用 Black 格式化代码
- 遵循 PEP 8 规范
- 添加必要的注释

## 报告问题

请在 [Issues](https://github.com/Justice-and-Equity/judicial-doc-anomaly-mcp/issues) 中报告问题。
```

**创建命令：**

```powershell
@'
# 贡献指南 / Contributing Guide

## 如何贡献

1. Fork 本仓库
2. 创建你的特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交你的改动 (`git commit -m '"'"'feat: add amazing feature'"'"'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 开发环境设置

```bash
pip install -e ".[dev]"
pytest
```

## 代码规范

- 使用 Black 格式化代码
- 遵循 PEP 8 规范
- 添加必要的注释

## 报告问题

请在 [Issues](https://github.com/Justice-and-Equity/judicial-doc-anomaly-mcp/issues) 中报告问题。
'@ | Out-File -FilePath CONTRIBUTING.md -Encoding utf8
```

### 4.3 提交新增文件

```powershell
git add CONTRIBUTING.md
git commit -m "docs: add contributing guide"
git push
```

---

## 5. 发布第一个 Release

### 5.1 创建 Git Tag

```powershell
# 创建版本标签
git tag -a v0.1.0 -m "Initial release: judicial document anomaly detection MCP server"

# 推送标签到 GitHub
git push origin v0.1.0
```

### 5.2 在 GitHub 上创建 Release

1. 访问你的仓库页面
2. 点击右侧的 **"Releases"** 链接（或访问 `https://github.com/你的用户名/judicial-doc-anomaly-mcp/releases`）
3. 点击 **"Create a new release"**
4. 填写：

| 字段 | 内容 |
|------|------|
| **Choose a tag** | 选择 `v0.1.0` |
| **Release title** | `v0.1.0 - Initial Release` |
| **Description** | 见下方模板 |

**Release 描述模板：**

```markdown
## 🎉 首个发布版本 / Initial Release

### 功能 / Features

- ✅ 12 维度司法文书异常检测框架
- ✅ MCP Server（支持 Claude Desktop、Cursor、Trae CN）
- ✅ CLI 命令行工具
- ✅ 长上下文注意力衰减对抗机制
- ✅ 多模型支持（OpenAI、DeepSeek、Qwen、智谱、月之暗面）
- ✅ 本地缓存，成本可控
- ✅ Dry Run 模式预览 Token 消耗

### 安装 / Installation

```bash
git clone https://github.com/Justice-and-Equity/judicial-doc-anomaly-mcp.git
cd judicial-doc-anomaly-mcp
pip install -e .
```

### 快速开始 / Quick Start

```bash
# 配置 API Key
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY

# 检测案件
judicial-lint analyze ./case_directory -o report.md
```

### 文档 / Documentation

- [README.md](README.md) - 项目说明（中英双语）
- [INSTALL_GUIDE_ZH.md](INSTALL_GUIDE_ZH.md) - 中文安装指南（小白友好）
- [CONTRIBUTING.md](CONTRIBUTING.md) - 贡献指南

### 已知限制 / Known Limitations

- 需要 LLM API Key
- 事实认定检测的解析逻辑需要优化
- 类案偏离检测需要联网检索（待实现）

### 下一步 / Next Steps

- [ ] 优化 Prompt 解析逻辑
- [ ] 添加更多测试用例
- [ ] 实现联网类案检索
- [ ] 发布到 PyPI
```

5. 点击 **"Publish release"**

---

## 6. 推广与维护

### 6.1 添加 GitHub Topics

1. 访问你的仓库
2. 点击右侧 **"⚙️ Manage topics"**
3. 添加以下标签：

```
mcp
mcp-server
judicial
legal-tech
anomaly-detection
document-analysis
llm
ai
china-law
openai
deepseek
python
```

### 6.2 分享到社区

- **V2EX**: 发布到 /create 节点
- **知乎**: 写一篇文章介绍工具和使用方法
- **GitHub Trending**: 获得足够 Star 后可能上榜
- **Product Hunt**: 面向国际用户推广
- **法律科技社区**: 如 LegalTech 相关论坛

### 6.3 持续维护

```powershell
# 定期更新依赖
pip install --upgrade -r requirements.txt

# 运行测试
pytest

# 接收社区反馈
# 关注 Issues 和 Pull Requests
```

---

## 7. 常见问题

### Q1: 推送时提示权限被拒绝？

```
remote: Permission to Justice-and-Equity/judicial-doc-anomaly-mcp.git denied to user.
```

**解决：**

```powershell
# 检查当前认证信息
git config --global --list | findstr credential

# 清除缓存的凭据
git credential-manager uninstall  # Windows
# 或手动删除 Windows 凭据：
# 控制面板 → 凭据管理器 → Windows 凭据 → 删除 github.com

# 重新认证
gh auth login
```

### Q2: 如何更新已上传的文件？

```powershell
# 修改文件后
git add .
git commit -m "fix: update README"
git push
```

### Q3: 如何删除误上传的敏感文件？

```powershell
# 从 Git 历史中删除（但保留本地文件）
git rm --cached .env
git commit -m "chore: remove .env from tracking"
git push

# 如果已经推送了敏感信息，需要重写历史：
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch .env" \
  --prune-empty --tag-name-filter cat -- --all
git push --force
```

**警告：** 如果已经泄露了 API Key，请立即在对应平台撤销该 Key！

### Q4: 如何让别人通过 pip install 安装？

需要发布到 PyPI：

```powershell
# 安装发布工具
pip install build twine

# 构建包
python -m build

# 注册 PyPI 账号：https://pypi.org/account/register/

# 发布到 PyPI
twine upload dist/*
```

发布后，用户可以：

```bash
pip install judicial-lint-mcp
```

### Q5: 如何设置 GitHub Actions 自动测试？

创建 `.github/workflows/test.yml`：

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - run: pip install -e ".[dev]"
      - run: pytest
```

---

## 附录：完整 Git 命令速查表

```powershell
# 初始化
git init
git remote add origin <仓库URL>

# 日常操作
git add .                    # 添加所有文件
git status                   # 查看状态
git commit -m "说明"         # 提交
git push                     # 推送

# 分支
git branch                   # 查看分支
git branch -M main           # 重命名分支
git checkout -b feature      # 创建并切换分支

# 标签
git tag -a v0.1.0 -m "说明"  # 创建标签
git push origin v0.1.0       # 推送标签

# 同步
git pull                     # 拉取更新
git fetch                    # 获取远程更新

# 查看历史
git log                      # 查看提交历史
git log --oneline            # 简洁模式
```

---

**祝你发布顺利！🎉**

如有问题，欢迎参考：
- [GitHub 官方文档](https://docs.github.com/)
- [Git 官方文档](https://git-scm.com/doc)
