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

### 红旗预警升级机制（Red-Flag Escalation）
- `taxonomy.py`：`AnomalyCategory`（A 码）新增 `fatal: bool = False` 属性，新增 F 码元数据注册表 `F_CODES` 与 `is_fatal()` 判定函数；fatal 标记采用保守原则——**A9 诉请回应缺失、F-27 遗漏诉讼请求标 fatal=True**，F-28 结论式驳斥 fatal=False（severity_base 提至 0.75）；A1-A8 经逐一审查，其标签均非"剥夺当事人诉讼权利/程序违法且可致发回重审"性质（含最接近的 A5 程序时间线异常，因时间线偏差多为技术性而非当然剥夺权利），按"拿不准就不标"未标记。
- `report_builder.py`：检出 fatal 异常时在报告**最顶部**渲染"🚩 红旗预警"区块（逐条列出编码/维度/异常项/获益方/置信度/原文摘录 + 后果评估），遗漏诉请类后果标注"存在二审撤销原判发回重审的强信号（《民事诉讼法》第一百七十七条第一款第四项及遗漏诉讼请求的司法解释口径）"，其它 fatal 项标注再审监督/程序纠正风险；区块以"红旗终评：本报告异常等级按最高 fatal 项呈现"收尾；红旗信号独立于综合评分。
- `server.py`：`build_report` 工具新增 `red_flag_escalation: bool = True` 开关，透传 report_builder；False 时保持旧行为（无红旗区块）。
- D17 维度新增"行政文书模式"小节：评估行政处理/处罚决定书时，诉请台账对应申请人复议/诉讼请求，逐项回应与裁量四要素判定规则同用；后果切换为行政复议撤销/变更（《行政复议法》（2023修订）第六十三条、第六十四条）或行政诉讼撤销/变更（《行政诉讼法》第七十条、第七十七条，六项撤销情形）。

### 文档与版本对齐
- README 工具数量校正为实际的 14 个并逐项列表；`render_pipeline` 标注为已弃用（改用 `plan_pipeline` + `render_skill`）。
- README 工具参数按实际代码修正：`parse_response`（`dimension`/`response`/`dimension_index`）、`compact_materials`（`materials`/`max_tokens`/`strategy`/`anonymize`）、`build_report`（`case_name`/`dimension_results_json`）、`pipeline_progress`（`session_id`/`action`/`skill_name`/`result_summary`）。
- 版本号统一至 0.6.0（`pyproject.toml`、`__init__.py`、`cli.py`、README 徽章）。
- 新增本 CHANGELOG。

### 测试
- 新增 `tests/test_v060.py`：D17 维度发现与渲染、full_scan 流水线包含 D17、A9 分类一致性、write_skill 路径穿越拒绝（`../evil.md`、绝对路径、嵌套穿越）及正常写入回归。
- 新增 `tests/test_redflag.py`：A9/F-27 fatal 标记断言（A1-A8 保守不标记）、红旗区块渲染于报告顶部并含后果文案、`red_flag_escalation=False` 关闭开关、D17 行政文书模式小节。
