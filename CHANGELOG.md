# Changelog

本文件自 v0.6.0 起维护。更早版本（v0.1.0 – v0.5.1）的变更记录见 Git 提交历史与 GitHub Releases。

## [0.6.0] — 2026-10-26

### 安全加固
- **write_skill 路径穿越防护**：写入前校验目标路径，`os.path.realpath` 解析后必须位于 Skills 目录之内；拒绝包含 `..`、绝对路径（盘符/根路径）或空名称的 `skill_name`，违规时返回不可重试错误（错误码 `PATH_400`）。
- **移除本地 `.env`**：删除曾存放真实 API Key 的本地 `.env` 文件（已被 `.gitignore` 排除，从未进入 Git 历史）；仓库仅保留脱敏的 `.env.example`。持有旧副本的用户应立即在服务商处轮换该 Key（详见 README「安全须知」）。
- **pyproject.toml 清理**：移除指向不存在的 `judicial_lint_mcp.gui:main` 的 `judicial-lint-gui` gui-scripts 入口。

### 新维度 D17：诉请支持度与回应完整性
- 新增 `skills/dimensions/17_claim_support.md`：从材料构建"诉请台账"（含诉的类型标注），与判决主文/说理逐项对齐，核算金额支持率与落差，对裁量点做四要素审查（裁量空间识别/依据论证/考量因素披露/回应诉辩主张），识别"另案处理"等衍生诉讼信号。
- 判定规则 CS-B01 至 CS-B10（台账缺行、诉请零回应、变更诉请未审理、金额核算不透明、结论式驳斥、未披露考量因素、未回应抗辩、偏离类案口径、高落差未强化说理、主文不明确）。
- `full_scan` 流水线追加 `dimensions/17_claim_support`（17 维全量扫描）。

### 分类体系（A 系列）扩展
- 新增 **A9 诉请回应缺失**（slug：`claim_response_missing`）：`taxonomy.py` 与 `skills/_taxonomy.md` 同步更新。
- 维度三（事实认定）检测项由 26 项扩展至 28 项：新增 **F-27 遗漏诉讼请求**、**F-28 结论式驳斥**，并映射到 A9。

### 文档与版本对齐
- README 工具数量校正为实际的 14 个并逐项列表；`render_pipeline` 标注为已弃用（改用 `plan_pipeline` + `render_skill`）。
- README 工具参数按实际代码修正：`parse_response`（`dimension`/`response`/`dimension_index`）、`compact_materials`（`materials`/`max_tokens`/`strategy`/`anonymize`）、`build_report`（`case_name`/`dimension_results_json`）、`pipeline_progress`（`session_id`/`action`/`skill_name`/`result_summary`）。
- 版本号统一至 0.6.0（`pyproject.toml`、`__init__.py`、`cli.py`、README 徽章）。
- 新增本 CHANGELOG。

### 测试
- 新增 `tests/test_v060.py`：D17 维度发现与渲染、full_scan 流水线包含 D17、A9 分类一致性、write_skill 路径穿越拒绝（`../evil.md`、绝对路径、嵌套穿越）及正常写入回归。
