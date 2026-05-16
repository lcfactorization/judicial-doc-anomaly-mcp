"""MCP Server entry point for judicial document anomaly detection v0.2.0"""

import asyncio
import json
import logging
import time
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from .config import AppConfig, ALL_DIMENSIONS
from .detector import DetectionEngine
from .llm_caller import LLMCaller
from .preprocessor import Preprocessor
from .graph_builder import GraphBuilder
from .quality_assessor import QualityAssessor
from .adversarial import AdversarialReviewer
from .prompts import DIMENSION_PROMPTS, DIMENSION_SUFFIX, QUICK_CHECK_PROMPT, SYSTEM_PROMPT
from .taxonomy import TAXONOMY, get_category, category_from_f_code, dimension_to_categories, NEUTRALITY_PROMPT_ADDON
from .benchmark import BENCHMARKS, get_benchmark, get_benchmarks_by_category

logger = logging.getLogger("judicial-lint")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)

mcp = FastMCP("judicial-lint")


def _load_config(arguments: dict) -> AppConfig:
    config_file = arguments.get("config_file")
    if config_file:
        return AppConfig.from_file(config_file)
    config = AppConfig.from_env()
    if arguments.get("model"):
        config.llm.model = arguments["model"]
    return config


def _make_llm_caller(config: AppConfig) -> LLMCaller:
    return LLMCaller(config.llm, cache_dir=config.cache_dir)


# ── MCP Resources ──────────────────────────────────────────────

@mcp.resource("judicial-lint://taxonomy")
def get_taxonomy_resource() -> str:
    lines = ["# 异常分类体系（A系列编号）\n"]
    for cat in TAXONOMY:
        lines.append(f"## {cat.code} {cat.label}")
        lines.append(f"- 描述：{cat.description}")
        lines.append(f"- 关联维度：{', '.join(f'D{d}' for d in cat.dimensions)}")
        lines.append(f"- 关联F编号：{', '.join(cat.f_codes)}")
        lines.append(f"- 基础严重度：{cat.severity_base}")
        lines.append(f"- 双向适用：{'是' if cat.bidirectional else '否'}")
        lines.append("")
    return "\n".join(lines)


@mcp.resource("judicial-lint://neutrality")
def get_neutrality_resource() -> str:
    return NEUTRALITY_PROMPT_ADDON


@mcp.resource("judicial-lint://dimensions")
def get_dimensions_resource() -> str:
    lines = ["# 十六维检测框架概要\n"]
    for i, (key, prompt) in enumerate(DIMENSION_PROMPTS.items(), 1):
        first_line = prompt.strip().split("\n")[0].lstrip("# ").strip()
        lines.append(f"## D{i} {key}")
        lines.append(f"- 标题：{first_line}")
        related = dimension_to_categories(i)
        if related:
            lines.append(f"- 关联A分类：{', '.join(c.code for c in related)}")
        lines.append("")
    return "\n".join(lines)


@mcp.resource("judicial-lint://benchmarks")
def get_benchmarks_resource() -> str:
    lines = ["# 基准案例库\n"]
    for cat_name in ["clearly_anomalous", "high_quality", "borderline"]:
        cases = get_benchmarks_by_category(cat_name)
        cat_label = {"clearly_anomalous": "明显异常", "high_quality": "高质量", "borderline": "边界模糊"}[cat_name]
        lines.append(f"## {cat_label}（{len(cases)}个）\n")
        for b in cases:
            lines.append(f"### {b.case_id}")
            lines.append(f"- 案由：{b.cause}")
            lines.append(f"- 关键异常：{', '.join(b.key_anomalies) if b.key_anomalies else '无'}")
            lines.append(f"- 预期等级：{b.expected_grade}")
            lines.append(f"- 摘要：{b.summary}")
            lines.append(f"- 判定理由：{b.reasoning}")
            lines.append("")
    return "\n".join(lines)


# ── MCP Tools ──────────────────────────────────────────────────

@mcp.tool()
async def detect_anomalies(
    case_dir: str,
    dimensions: list[str] | None = None,
    model: str | None = None,
    output_format: str = "markdown",
    enable_preprocessing: bool = True,
    enable_graph: bool = True,
    enable_quality: bool = True,
    enable_adversarial: bool = True,
    enable_quick_check: bool = True,
    config_file: str | None = None,
) -> str:
    """对案件目录下的司法文书进行十六维异常检测、图结构建模、质量评估和对抗审查。
    每个异常点将映射到A1-A8分类体系，并标注指向获益方、反向校验结果和净异常判定。"""
    arguments = {
        "case_dir": case_dir, "dimensions": dimensions, "model": model,
        "output_format": output_format, "enable_preprocessing": enable_preprocessing,
        "enable_graph": enable_graph, "enable_quality": enable_quality,
        "enable_adversarial": enable_adversarial, "enable_quick_check": enable_quick_check,
        "config_file": config_file,
    }

    t0 = time.perf_counter()
    logger.info("=" * 60)
    logger.info("detect_anomalies 开始 | 案件目录: %s", case_dir)

    config = _load_config(arguments)

    if dimensions:
        config.detection.dimensions = dimensions
    if enable_adversarial is not None:
        config.detection.enable_adversarial_check = enable_adversarial
    if enable_graph is not None:
        config.detection.enable_graph_building = enable_graph
    if enable_quality is not None:
        config.detection.enable_quality_assessment = enable_quality
    if enable_quick_check is not None:
        config.detection.enable_quick_check = enable_quick_check

    logger.info("配置加载完成 | 模型: %s | 维度: %s | 预处理: %s | 图: %s | 质量: %s | 对抗: %s | 速查: %s",
                config.llm.model, len(config.detection.dimensions),
                enable_preprocessing,
                config.detection.enable_graph_building,
                config.detection.enable_quality_assessment,
                config.detection.enable_adversarial_check,
                config.detection.enable_quick_check)

    llm_caller = _make_llm_caller(config)
    report_sections = []

    if enable_preprocessing:
        t1 = time.perf_counter()
        preprocessor = Preprocessor(llm_caller)
        preprocess_result = await preprocessor.run(case_dir)
        logger.info("[Phase 0-1] 预处理完成 | 完整性: %.1f | 时间线: %d | 证据: %d | 诉请: %d | 耗时: %.2fs",
                    preprocess_result.completeness_score,
                    len(preprocess_result.timeline),
                    len(preprocess_result.evidence_index),
                    len(preprocess_result.claims_map),
                    time.perf_counter() - t1)
        report_sections.append(_format_preprocess_result(preprocess_result))
    else:
        from .detector import FileLoader
        loader = FileLoader(case_dir)
        loader.load()
        materials_text = loader.get_materials_text()
        preprocess_result = None
        logger.info("[Phase 0-1] 预处理已跳过 | 材料字符数: %d", len(materials_text))

    t2 = time.perf_counter()
    engine = DetectionEngine(config)
    detection_result = await engine.run_detection(case_dir)
    anomaly_count = sum(len(r.anomalies) for r in detection_result.dimension_results)
    logger.info("[Phase 1-4] 维度检测完成 | 维度: %d | 异常项: %d | 风险: %s | 耗时: %.2fs",
                len(detection_result.dimension_results),
                anomaly_count,
                detection_result.risk_level,
                time.perf_counter() - t2)
    report_sections.append(detection_result.report_markdown)

    if config.detection.enable_graph_building and preprocess_result:
        t3 = time.perf_counter()
        graph_builder = GraphBuilder(llm_caller, config.graph)
        graph_result = await graph_builder.run(preprocess_result)
        logger.info("[Phase 2] 图构建完成 | 证据图: %s | 程序图: %s | 推理图: %s | 异常路径: %d | 耗时: %.2fs",
                    "✓" if graph_result.evidence_mermaid else "✗",
                    "✓" if graph_result.procedure_mermaid else "✗",
                    "✓" if graph_result.reasoning_mermaid else "✗",
                    len(graph_result.anomaly_paths),
                    time.perf_counter() - t3)
        report_sections.append(_format_graph_result(graph_result))

    if config.detection.enable_quality_assessment:
        t4 = time.perf_counter()
        if preprocess_result:
            materials_text = preprocess_result.materials_text
        else:
            materials_text = detection_result.report_markdown
        assessor = QualityAssessor(llm_caller)
        quality_result = await assessor.assess(materials_text)
        logger.info("[Phase 4.5] 质量评估完成 | 总分: %d/100 | 等级: %s | 耗时: %.2fs",
                    quality_result.total_score, quality_result.grade,
                    time.perf_counter() - t4)
        report_sections.append(_format_quality_result(quality_result))

    if config.detection.enable_adversarial_check:
        t5 = time.perf_counter()
        anomalies_text = _extract_anomalies_text(detection_result)
        reviewer = AdversarialReviewer(llm_caller, config.adversarial)
        adversarial_result = await reviewer.run(anomalies_text)
        da_count = len(adversarial_result.devils_advocate_results) if adversarial_result.devils_advocate_results else 0
        rr_count = len(adversarial_result.role_reviews) if adversarial_result.role_reviews else 0
        hr_count = len(adversarial_result.high_risk_points) if adversarial_result.high_risk_points else 0
        logger.info("[Phase 5] 对抗审查完成 | DA校验: %d | 角色审查: %d | 高风险点: %d | 耗时: %.2fs",
                    da_count, rr_count, hr_count, time.perf_counter() - t5)
        report_sections.append(_format_adversarial_result(adversarial_result))

    if config.detection.enable_quick_check:
        t6 = time.perf_counter()
        if preprocess_result:
            materials_text = preprocess_result.materials_text
        else:
            materials_text = detection_result.report_markdown
        quick_check_prompt = QUICK_CHECK_PROMPT.format(materials=materials_text)
        quick_check_output = await llm_caller.acall(
            "你是事实认定审查专家，请逐项对照检查。", quick_check_prompt
        )
        logger.info("[Quick Check] 速查表完成 | 耗时: %.2fs", time.perf_counter() - t6)
        report_sections.append(f"# 事实认定错误快速对照清单\n\n{quick_check_output[0]}")

    full_report = "\n\n---\n\n".join(report_sections)

    total_time = time.perf_counter() - t0
    logger.info("=" * 60)
    logger.info("detect_anomalies 完成 | 报告长度: %d 字符 | 段落: %d | 总耗时: %.2fs",
                len(full_report), len(report_sections), total_time)
    logger.info("=" * 60)

    if output_format == "json":
        return json.dumps({
            "version": "0.2.0",
            "case_dir": case_dir,
            "report_length": len(full_report),
            "sections": len(report_sections),
        }, ensure_ascii=False, indent=2)
    elif output_format == "both":
        return full_report + "\n\n---\n\n" + json.dumps({
            "version": "0.2.0",
            "case_dir": case_dir,
        }, ensure_ascii=False, indent=2)
    else:
        return full_report


@mcp.tool()
async def quality_assessment(case_dir: str, model: str | None = None) -> str:
    """对司法文书进行七维度质量评估打分（A-F等级，100分制）"""
    config = _load_config({"model": model})
    llm_caller = _make_llm_caller(config)

    preprocessor = Preprocessor(llm_caller)
    preprocess_result = await preprocessor.run(case_dir)

    assessor = QualityAssessor(llm_caller)
    quality_result = await assessor.assess(preprocess_result.materials_text)

    return _format_quality_result(quality_result)


@mcp.tool()
async def build_graph(case_dir: str, model: str | None = None) -> str:
    """构建案件图结构模型（证据关系图、程序行为图、法律推理图），输出Mermaid可视化"""
    config = _load_config({"model": model})
    llm_caller = _make_llm_caller(config)

    preprocessor = Preprocessor(llm_caller)
    preprocess_result = await preprocessor.run(case_dir)

    graph_builder = GraphBuilder(llm_caller, config.graph)
    graph_result = await graph_builder.run(preprocess_result)

    return _format_graph_result(graph_result)


@mcp.tool()
async def quick_check(case_dir: str, model: str | None = None, document: str | None = None) -> str:
    """快速异常检测：支持26项翻案速查表（传入case_dir）或单文档快速扫描（传入document）。
    检测结果将映射到A1-A8分类体系，并标注指向获益方和反向校验结果。"""
    config = _load_config({"model": model})
    llm_caller = _make_llm_caller(config)

    if document:
        from .prompts import QUICK_ANOMALY_CHECK_PROMPT
        prompt = QUICK_ANOMALY_CHECK_PROMPT.format(document=document)
        output, _ = await llm_caller.acall(SYSTEM_PROMPT, prompt)
        return f"# 快速异常检测\n\n{output}"

    if not case_dir:
        return "错误：必须提供 case_dir 或 document 参数"

    preprocessor = Preprocessor(llm_caller)
    preprocess_result = await preprocessor.run(case_dir)

    prompt = QUICK_CHECK_PROMPT.format(materials=preprocess_result.materials_text)
    output, _ = await llm_caller.acall("你是事实认定审查专家，请逐项对照检查。", prompt)

    return f"# 事实认定错误快速对照清单\n\n{output}"


@mcp.tool()
async def dry_run(case_dir: str, dimensions: list[str] | None = None) -> str:
    """预览检测流程，显示将调用的 prompt 和预估 token 数，不实际调用 LLM"""
    from .detector import FileLoader

    loader = FileLoader(case_dir)
    loader.load()
    completeness, missing = loader.validate()
    materials = loader.get_materials_text()
    dims = dimensions or list(DIMENSION_PROMPTS.keys())

    output = [
        "# 检测流程预览（Dry Run）v0.2.0",
        f"\n## 材料完整性评分：{completeness:.1f}/100",
        f"\n## 缺失材料：{', '.join(missing) if missing else '无'}",
        f"\n## 材料总字符数：{len(materials)}",
        f"\n## 预估材料 token 数：{int(len(materials) * 0.5)}",
        f"\n## 将执行的检测维度（{len(dims)}个）：{', '.join(dims)}",
        f"\n## 预估总 token 消耗：{int(len(materials) * 0.5 * len(dims) * 1.2)}",
        f"\n## 新增模块状态：",
        f"- 结构化预处理：启用",
        f"- 图结构建模：启用",
        f"- 质量评估：启用",
        f"- 对抗审查：启用",
        f"- 翻案速查表：启用",
        f"- A系列分类映射：启用",
        f"- 中立性校验：启用",
        f"- 基准案例库：{len(BENCHMARKS)}个",
        f"\n\n## 各维度 Prompt 预览：\n",
    ]

    for dim in dims:
        if dim in DIMENSION_PROMPTS:
            prompt = DIMENSION_PROMPTS[dim]
            output.append(f"### {dim}")
            output.append(f"- Prompt 长度：{len(prompt)} 字符")
            output.append(f"- 预估 token：{int(len(prompt) * 0.5)}")
            output.append(f"- Prompt 内容：\n```\n{prompt[:200]}...\n```\n")

    return "\n".join(output)


@mcp.tool()
def get_detection_rules(dimension: str | None = None) -> str:
    """获取内置的检测规则与法条参考"""
    if dimension:
        if dimension in DIMENSION_PROMPTS:
            return DIMENSION_PROMPTS[dimension] + DIMENSION_SUFFIX
        else:
            return f"未知维度：{dimension}"
    else:
        output = ["# 全部检测维度规则（v0.2.0 十六维）\n"]
        for dim, prompt in DIMENSION_PROMPTS.items():
            output.append(f"\n## {dim}\n{prompt}\n{DIMENSION_SUFFIX}\n")
        return "\n".join(output)


@mcp.tool()
def benchmark_compare(anomaly_codes: str, cause: str | None = None) -> str:
    """将当前案件的异常分类与基准案例库进行对比，计算Jaccard相似度，返回最相似的基准案例和校准建议。
    anomaly_codes: 逗号分隔的A编号（如 'A1,A4,A6'）
    cause: 可选案由（用于筛选同类基准案例）"""
    codes = [c.strip().upper() for c in anomaly_codes.split(",") if c.strip()]
    if not codes:
        return "错误：anomaly_codes 不能为空"

    input_set = set(codes)
    results = []

    for bm in BENCHMARKS:
        if cause and bm.cause != cause:
            continue
        bm_set = set(bm.key_anomalies)
        if not bm_set and not input_set:
            similarity = 1.0
        elif not bm_set or not input_set:
            similarity = 0.0
        else:
            intersection = input_set & bm_set
            union = input_set | bm_set
            similarity = len(intersection) / len(union)
        results.append((bm, similarity))

    results.sort(key=lambda x: x[1], reverse=True)

    lines = ["# 基准案例对比结果\n"]
    lines.append(f"**当前案件异常分类**：{', '.join(codes)}\n")
    if cause:
        lines.append(f"**案由筛选**：{cause}\n")
    lines.append("## 相似度排序\n")
    lines.append("| 基准案例 | 类别 | 案由 | 异常分类 | Jaccard相似度 | 预期等级 |")
    lines.append("|---------|------|------|---------|-------------|---------|")
    for bm, sim in results:
        lines.append(f"| {bm.case_id} | {bm.category} | {bm.cause} | {', '.join(bm.key_anomalies) or '无'} | {sim:.2f} | {bm.expected_grade} |")

    if results:
        best_bm, best_sim = results[0]
        lines.append(f"\n## 校准建议\n")
        lines.append(f"最相似基准案例：**{best_bm.case_id}**（{best_bm.category}，相似度 {best_sim:.2f}）")
        lines.append(f"- 预期等级：{best_bm.expected_grade}")
        lines.append(f"- 判定理由：{best_bm.reasoning}")
        if best_sim >= 0.5:
            lines.append(f"- 校准结论：当前案件与已知异常案例高度相似，建议重点关注")
        elif best_sim >= 0.2:
            lines.append(f"- 校准结论：当前案件与部分异常案例有交集，需进一步分析")
        else:
            lines.append(f"- 校准结论：当前案件与基准案例差异较大，可能属于独立模式")

    return "\n".join(lines)


@mcp.tool()
async def scan_dimension(case_dir: str, dimension: int, model: str | None = None) -> str:
    """对指定维度进行单独扫描检测（1-16），返回该维度的异常检测结果。
    检测结果将映射到A1-A8分类体系，并标注指向获益方和反向校验结果。"""
    dim_keys = list(DIMENSION_PROMPTS.keys())
    if dimension < 1 or dimension > len(dim_keys):
        return f"错误：维度编号必须在 1-{len(dim_keys)} 之间"

    dim_key = dim_keys[dimension - 1]
    config = _load_config({"model": model})
    config.detection.dimensions = [dim_key]
    llm_caller = _make_llm_caller(config)

    preprocessor = Preprocessor(llm_caller)
    preprocess_result = await preprocessor.run(case_dir)

    prompt = DIMENSION_PROMPTS[dim_key] + DIMENSION_SUFFIX
    formatted = prompt.format(materials=preprocess_result.materials_text)
    output, _ = await llm_caller.acall(SYSTEM_PROMPT, formatted)

    related_cats = dimension_to_categories(dimension)
    cat_info = ""
    if related_cats:
        cat_info = f"\n\n**关联A系列分类**：{', '.join(f'{c.code} {c.label}' for c in related_cats)}"

    return f"# 维度{dimension}（{dim_key}）单独扫描结果{cat_info}\n\n{output}"


@mcp.tool()
async def adversarial_check(case_dir: str, model: str | None = None) -> str:
    """独立执行多角色对抗审查，对已检测的异常点进行反向校验。
    包含Devil's Advocate校验和五角色多维对抗审查，并执行反向异常检测。"""
    config = _load_config({"model": model})
    llm_caller = _make_llm_caller(config)

    engine = DetectionEngine(config)
    detection_result = await engine.run_detection(case_dir)
    anomalies_text = _extract_anomalies_text(detection_result)

    if anomalies_text == "未发现显著异常":
        return "未检测到异常点，无需执行对抗审查"

    reviewer = AdversarialReviewer(llm_caller, config.adversarial)
    adversarial_result = await reviewer.run(anomalies_text)

    return _format_adversarial_result(adversarial_result)


@mcp.tool()
async def generate_report(case_dir: str, model: str | None = None) -> str:
    """运行完整检测流程并生成结构化报告，包含异常等级判定和救济建议。
    报告中每个异常点映射到A1-A8分类，并标注指向获益方、反向校验结果和净异常判定。"""
    config = _load_config({"model": model})
    llm_caller = _make_llm_caller(config)

    preprocessor = Preprocessor(llm_caller)
    preprocess_result = await preprocessor.run(case_dir)

    engine = DetectionEngine(config)
    detection_result = await engine.run_detection(case_dir)

    assessor = QualityAssessor(llm_caller)
    quality_result = await assessor.assess(preprocess_result.materials_text)

    anomalies_text = _extract_anomalies_text(detection_result)
    reviewer = AdversarialReviewer(llm_caller, config.adversarial)
    adversarial_result = await reviewer.run(anomalies_text)

    from .prompts import REPORT_TEMPLATE
    from . import __version__
    from datetime import datetime

    report = REPORT_TEMPLATE.format(
        case_name=preprocess_result.case_info.case_name or "未知",
        doc_type=preprocess_result.case_info.case_type or "未知",
        model_name=config.llm.model,
        detection_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        completeness_score=f"{preprocess_result.completeness_score:.1f}",
        legal_basis="《民事诉讼法》《行政诉讼法》《行政处罚法》等",
        version=__version__,
        risk_level=detection_result.risk_level,
        risk_reason=detection_result.risk_reason if hasattr(detection_result, 'risk_reason') else "综合多维度分析",
        anomaly_table=_build_anomaly_table(detection_result),
        dimension_details=detection_result.report_markdown,
        timeline_table=_build_timeline_table(preprocess_result),
        temporal_anomalies="（见维度检测时间一致性分析）",
        semantic_drift_table="（见维度检测语义漂移分析）",
        negative_space_analysis="（见维度检测缺失信息分析）",
        deviation_table="（见维度检测类案偏离分析）",
        procedure_graph_text="（见图结构建模结果）",
        mermaid_graph="（见build_graph工具输出）",
        anomaly_paths="（见图结构建模结果）",
        adversarial_table=_build_adversarial_table(adversarial_result),
        coupling_analysis="（见维度检测耦合分析）",
        quality_score_table=_build_quality_score_table(quality_result),
        quality_total_score=str(quality_result.total_score),
        quality_grade=quality_result.grade,
        quality_strengths="；".join(quality_result.strengths) if quality_result.strengths else "无",
        quality_weaknesses="；".join(quality_result.weaknesses) if quality_result.weaknesses else "无",
        quick_check_results="（见quick_check工具输出）",
        remedies="（见检测报告救济建议部分）",
    )

    return report


# ── Formatting helpers ─────────────────────────────────────────

def _build_anomaly_table(detection_result) -> str:
    rows = []
    for r in detection_result.dimension_results:
        for a in r.anomalies:
            a_code = a.a_code if a.a_code else ""
            if not a_code:
                related = category_from_f_code(getattr(a, 'f_code', ''))
                a_code = related[0].code if related else ""
            beneficiary = getattr(a, 'beneficiary', '不确定')
            reverse = getattr(a, 'reverse_check', '-')
            net = getattr(a, 'net_anomaly', '-')
            rows.append(f"| {r.dimension} | {a.item_name} | {a.description[:40]} | {beneficiary} | {a_code} | {reverse} | {net} |")
    return "\n".join(rows) if rows else "| - | 未发现异常 | - | - | - | - | - |"


def _build_timeline_table(preprocess_result) -> str:
    rows = []
    for entry in preprocess_result.timeline[:20]:
        rows.append(f"| {entry.date} | {entry.event[:60]} | {getattr(entry, 'source', '案卷')} |")
    return "\n".join(rows) if rows else "| - | 无时间线数据 | - |"


def _build_adversarial_table(adversarial_result) -> str:
    rows = []
    if adversarial_result.devils_advocate_results:
        for da in adversarial_result.devils_advocate_results:
            rows.append(f"| {da.anomaly_description[:40]} | {getattr(da, 'alternative_explanation', '-')[:30]} | {'✅' if da.conclusion == '成立' else '⚠️' if da.conclusion == '存疑' else '❌'} | {'✅' if da.conclusion == '成立' else '⚠️' if da.conclusion == '存疑' else '❌'} | {'✅' if da.conclusion == '成立' else '⚠️' if da.conclusion == '存疑' else '❌'} | {da.conclusion} |")
    return "\n".join(rows) if rows else "| - | - | - | - | - | - |"


def _build_quality_score_table(quality_result) -> str:
    rows = []
    for ds in quality_result.dimension_scores:
        rows.append(f"| {ds.dimension} | {ds.full_score} | {ds.full_score - ds.score} | {ds.score} | {getattr(ds, 'deduction_items', '-')[:40]} |")
    return "\n".join(rows) if rows else "| - | - | - | - | - |"


def _format_preprocess_result(result) -> str:
    lines = ["# 结构化预处理结果\n"]
    ci = result.case_info
    if ci.case_number:
        lines.append(f"**案号**：{ci.case_number}")
    if ci.case_name:
        lines.append(f"**案件名称**：{ci.case_name}")
    if ci.parties:
        lines.append(f"**当事人**：{', '.join(ci.parties)}")
    lines.append(f"\n**材料完整性评分**：{result.completeness_score:.1f}/100")
    if result.missing_items:
        lines.append(f"**缺失材料**：{', '.join(result.missing_items)}")
    if result.timeline:
        lines.append(f"\n## 时间线（{len(result.timeline)}个事件）\n")
        for entry in result.timeline[:20]:
            lines.append(f"- {entry.date}: {entry.event[:80]}")
    if result.evidence_index:
        lines.append(f"\n## 证据索引（{len(result.evidence_index)}项）\n")
        for ev in result.evidence_index[:15]:
            lines.append(f"- {ev.evidence_id} [{ev.evidence_type}] {ev.description[:60]}")
    if result.claims_map:
        lines.append(f"\n## 诉请映射（{len(result.claims_map)}项）\n")
        for cl in result.claims_map:
            lines.append(f"- {cl.claim_id} [{cl.party}] {cl.claim_content[:60]}")
    return "\n".join(lines)


def _format_graph_result(result) -> str:
    lines = ["# 图结构建模结果\n"]
    if result.evidence_mermaid:
        lines.append("## 证据关系图\n```mermaid\n" + result.evidence_mermaid + "\n```\n")
    if result.procedure_mermaid:
        lines.append("## 程序行为图\n```mermaid\n" + result.procedure_mermaid + "\n```\n")
    if result.reasoning_mermaid:
        lines.append("## 法律推理图\n```mermaid\n" + result.reasoning_mermaid + "\n```\n")
    if result.anomaly_paths:
        lines.append(f"\n## 异常路径检测（{len(result.anomaly_paths)}项）\n")
        for ap in result.anomaly_paths:
            lines.append(f"- **{ap.pattern}**：{ap.description}（{ap.meaning}）")
    return "\n".join(lines)


def _format_quality_result(result) -> str:
    lines = ["# 文书质量评估结果\n"]
    lines.append(f"**总分**：{result.total_score}/100  **等级**：{result.grade}（{result.grade_description}）\n")
    lines.append("| 维度 | 满分 | 得分 | 权重 | 加权分 |")
    lines.append("|------|------|------|------|--------|")
    for ds in result.dimension_scores:
        lines.append(f"| {ds.dimension} | {ds.full_score} | {ds.score} | {ds.weight:.0%} | {ds.weighted_score:.1f} |")
    if result.strengths:
        lines.append(f"\n## 核心优势\n")
        for s in result.strengths:
            lines.append(f"- {s}")
    if result.weaknesses:
        lines.append(f"\n## 核心不足\n")
        for w in result.weaknesses:
            lines.append(f"- {w}")
    if result.improvement_suggestions:
        lines.append(f"\n## 改进建议\n")
        for s in result.improvement_suggestions:
            lines.append(f"- {s}")
    return "\n".join(lines)


def _format_adversarial_result(result) -> str:
    lines = ["# 多角色对抗审查结果\n"]
    if result.devils_advocate_results:
        lines.append("## Devil's Advocate 校验\n")
        for da in result.devils_advocate_results:
            status = {"成立": "✅", "存疑": "⚠️", "不成立": "❌"}.get(da.conclusion, "❓")
            lines.append(f"- {status} {da.anomaly_description[:80]} → {da.conclusion}")
    if result.role_reviews:
        lines.append(f"\n## 角色审查（{len(result.role_reviews)}个角色）\n")
        for rr in result.role_reviews:
            lines.append(f"- **{rr.role_name_cn}**：风险等级 {rr.risk_level}")
    if result.cross_examinations:
        lines.append(f"\n## 交叉质证\n")
        for ce in result.cross_examinations:
            lines.append(f"- {ce.risk_point[:60]}：{ce.consensus_level}（风险：{ce.risk_level}）")
    if result.high_risk_points:
        lines.append(f"\n## 高风险点（{len(result.high_risk_points)}项）\n")
        for hp in result.high_risk_points:
            lines.append(f"- [{hp['risk_level']}] {hp['point'][:60]}")
    return "\n".join(lines)


def _extract_anomalies_text(detection_result) -> str:
    anomalies = []
    for r in detection_result.dimension_results:
        for a in r.anomalies:
            anomalies.append(f"[{r.dimension}] {a.item_name}: {a.description}")
    return "\n".join(anomalies[:30]) if anomalies else "未发现显著异常"


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
