"""Core detection engine for judicial document anomaly detection v0.3.0

Refactored: parsing logic → response_parser.py, report generation → report_builder.py
This module retains: data models, FileLoader, DetectionEngine orchestration.
"""

import logging
import re
from datetime import datetime
from pathlib import Path

from .config import AppConfig
from .graph_builder import GraphBuilder
from .llm_caller import LLMCaller
from .models import AnomalyItem, DetectionResult, DimensionResult
from .prompts import ADVERSARIAL_PROMPT, DIMENSION_PROMPTS, SYSTEM_PROMPT
from .quality_assessor import QualityAssessor
from .report_builder import ReportBuilder
from .response_parser import ResponseParser
from .taxonomy import TAXONOMY, category_from_f_code, dimension_to_categories

logger = logging.getLogger(__name__)


class FileLoader:
    """Load and validate case materials from directory"""

    REQUIRED_FILES = ["判决书", "裁判文书"]
    RECOMMENDED_FILES = ["起诉状", "答辩状", "上诉状", "证据清单", "庭审笔录"]

    def __init__(self, case_dir: str):
        self.case_dir = Path(case_dir)
        self.files: dict[str, str] = {}
        self.missing_files: list[str] = []

    def load(self) -> dict[str, str]:
        if not self.case_dir.exists():
            raise FileNotFoundError(f"Case directory not found: {self.case_dir}")

        skipped = []
        for md_file in self.case_dir.glob("*.md"):
            name_lower = md_file.name.lower()
            if any(
                kw in name_lower
                for kw in (
                    "report",
                    "检测报告",
                    "异常检测",
                    "评估报告",
                    "deepseek_markdown",
                    "阅卷",
                )
            ):
                skipped.append(md_file.name)
                logger.info("FileLoader: 跳过文件 %s（匹配排除关键词）", md_file.name)
                continue
            with open(md_file, encoding="utf-8") as f:
                content = f.read()
            self.files[md_file.stem] = content
            logger.info("FileLoader: 加载文件 %s（%d 字符）", md_file.name, len(content))

        if skipped:
            logger.info("FileLoader: 共跳过 %d 个文件: %s", len(skipped), ", ".join(skipped))
        logger.info("FileLoader: 共加载 %d 个案件材料文件", len(self.files))
        return self.files

    def validate(self) -> tuple[float, list[str]]:
        all_filenames = " ".join(self.files.keys())

        missing = []
        for req in self.REQUIRED_FILES:
            if req not in all_filenames:
                missing.append(req)

        for rec in self.RECOMMENDED_FILES:
            if rec not in all_filenames:
                missing.append(rec)

        total = len(self.REQUIRED_FILES) + len(self.RECOMMENDED_FILES)
        found = total - len(missing)
        score = (found / total) * 100 if total > 0 else 0

        return score, missing

    def get_materials_text(self) -> str:
        parts = []
        for name, content in self.files.items():
            parts.append(f"# {name}\n\n{content}")
        return "\n\n---\n\n".join(parts)


class DetectionEngine:
    """Main detection engine that orchestrates the full workflow"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.llm = LLMCaller(config.llm, cache_dir=config.cache_dir)
        self.file_loader: FileLoader | None = None
        self.context_history: list[dict] = []
        self.total_tokens_used = 0
        self.parser = ResponseParser()
        self.report_builder = ReportBuilder(self.llm)

    async def run_detection(
        self,
        case_dir: str,
        dimensions: list[str] | None = None,
    ) -> DetectionResult:
        result = DetectionResult(
            detection_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            model_name=self.config.llm.model,
        )

        logger.info("=" * 60)
        logger.info("DetectionEngine.run_detection: 开始检测流程")
        logger.info("DetectionEngine: 案件目录=%s", case_dir)

        self.file_loader = FileLoader(case_dir)
        self.file_loader.load()
        completeness, missing = self.file_loader.validate()
        result.completeness_score = completeness
        logger.info("DetectionEngine: 材料完整性=%.1f/100, 缺失=%s", completeness, missing)

        materials_text = self.file_loader.get_materials_text()
        logger.info("DetectionEngine: 材料总字符数=%d", len(materials_text))

        result.case_name = self._extract_case_name(materials_text)
        result.doc_type = self._extract_doc_type(materials_text)
        logger.info("DetectionEngine: 案件名称=%s, 文书类型=%s", result.case_name, result.doc_type)

        dims = dimensions or self.config.detection.dimensions
        from .prompts import DIMENSION_ORDER, DIMENSION_LABELS
        logger.info("DetectionEngine: 检测维度列表（%d个）:", len(dims))
        for i, d in enumerate(dims, 1):
            label = DIMENSION_LABELS.get(d, d)
            abs_idx = DIMENSION_ORDER.index(d) + 1 if d in DIMENSION_ORDER else 99
            layer = ""
            if abs_idx <= 2:
                layer = "第一层·形式审查"
            elif abs_idx <= 6:
                layer = "第二层·内容审查"
            elif abs_idx <= 8:
                layer = "第三层·说理与逻辑"
            elif abs_idx <= 10:
                layer = "第四层·时间与过程"
            else:
                layer = "第五层·综合评判"
            logger.info("  D%d %s → %s [%s] (全局序号=%d)", i, d, label, layer, abs_idx)

        dimension_results = []
        for idx, dim in enumerate(dims, 1):
            if dim not in DIMENSION_PROMPTS:
                logger.warning("DetectionEngine: 维度 %s 不在 DIMENSION_PROMPTS 中，跳过", dim)
                continue

            logger.info("-" * 40)
            logger.info("DetectionEngine: [%d/%d] 开始检测维度 %s", idx, len(dims), dim)
            dim_result = await self._run_dimension(dim, materials_text, dimension_results)
            dimension_results.append(dim_result)
            logger.info(
                "DetectionEngine: [%d/%d] 维度 %s 检测完成, 异常项=%d, 风险=%s",
                idx,
                len(dims),
                dim,
                len(dim_result.anomalies),
                dim_result.risk_level,
            )

            if self.config.detection.step_confirmation:
                await self._confirm_step(dim, dim_result)

        result.dimension_results = dimension_results

        logger.info("DetectionEngine: Phase 5 - 对抗校验 (enable=%s)", self.config.detection.enable_adversarial_check)
        if self.config.detection.enable_adversarial_check:
            result.adversarial_results = await self._run_adversarial_check(dimension_results)

        logger.info("DetectionEngine: Phase 6 - 耦合分析")
        result.coupling_analysis = await self._run_coupling_analysis(dimension_results)

        logger.info("DetectionEngine: Phase 7 - 质量评估 (enable=%s)", self.config.detection.enable_quality_assessment)
        if self.config.detection.enable_quality_assessment:
            try:
                quality_result = await self._run_quality_assessment(materials_text, dimension_results)
                result.quality_score_table = quality_result
            except Exception as e:
                logger.error("DetectionEngine: 质量评估失败: %s", e, exc_info=True)
                result.quality_score_table = f"质量评估执行失败：{e}"

        logger.info("DetectionEngine: Phase 8 - 图构建 (enable=%s)", self.config.detection.enable_graph_building)
        if self.config.detection.enable_graph_building:
            try:
                graph_result = await self._run_graph_building(materials_text)
                result.mermaid_graph = graph_result
            except Exception as e:
                logger.error("DetectionEngine: 图构建失败: %s", e, exc_info=True)
                result.mermaid_graph = f"图构建执行失败：{e}"

        result.risk_level, result.risk_reason = self._calculate_risk_level(dimension_results)
        logger.info("DetectionEngine: 综合风险等级=%s, 理由=%s", result.risk_level, result.risk_reason[:100])

        result.remedies = self._generate_remedies(dimension_results)

        result.total_tokens_used = self.total_tokens_used
        result.report_markdown = await self.report_builder.build_report(result)
        logger.info("DetectionEngine: 报告生成完成, 总字符数=%d, 总token=%d", len(result.report_markdown), result.total_tokens_used)
        logger.info("=" * 60)

        return result

    async def _run_dimension(
        self,
        dim: str,
        materials: str,
        previous_results: list[DimensionResult],
    ) -> DimensionResult:
        from .prompts import DIMENSION_LABELS
        dim_label = DIMENSION_LABELS.get(dim, dim)
        logger.info("_run_dimension: 维度 %s (%s), 材料长度=%d, 前序结果=%d个", dim, dim_label, len(materials), len(previous_results))

        prompt_template = DIMENSION_PROMPTS[dim]

        context = ""
        if previous_results:
            context = "\n\n## 前序维度检测结果（作为参考上下文）\n"
            for prev in previous_results[-3:]:
                context += f"\n### {prev.dimension}\n{prev.summary}\n"
                for a in prev.anomalies[:5]:
                    context += f"- {a.item_name}: {a.description}\n"

        max_tokens = self.config.detection.max_context_tokens
        if self.llm.estimate_tokens(materials) > max_tokens * 0.7:
            materials = materials[: int(max_tokens * 0.7 / 1.5)]

        fmt_kwargs = {
            "materials": materials + context,
            "previous_results": materials + context,
        }
        user_prompt = prompt_template.format(**fmt_kwargs)
        system_prompt = (
            SYSTEM_PROMPT + "\n\n"
            "## 输出格式要求（必须严格遵守）\n"
            "对每个检测到的异常项，必须使用以下格式：\n\n"
            "#### 1. 异常项：[异常项名称]\n\n"
            "- 具体表现：[详细描述，引用原文段落并标注页码/段落/行号，内容必须完整不得省略]\n"
            "- 原文引用：[判决书原文，完整引用不得截断]\n"
            "- 指向获益方：[原告/被告/双方/无]\n"
            "- 异常程度：[疑似/可能/高度可能/确定]\n"
            "- 法理分析：[详细分析，引用具体法条原文，论证必须完整不得省略]\n\n"
            "注意事项：\n"
            "1. 每个异常项必须以'#### 序号. 异常项：'开头\n"
            "2. 具体表现和法理分析必须完整输出，不得用省略号或'略'代替\n"
            "3. 原文引用必须完整，不得截断\n"
            "4. 不要在开头添加角色扮演类语句（如'好的，作为专业的...'）\n"
            "5. 不要输出'总结'或'综合结论'作为单独的异常项\n"
            "6. 证据描述必须明确标注提交方（如'原告提交的录音证据5'）\n"
            "7. 所有当事人称谓必须使用一审术语\n"
        )

        response, usage = await self.llm.acall(system_prompt, user_prompt)
        self.total_tokens_used += usage.get("total_tokens", 0)

        from .prompts import DIMENSION_ORDER
        dim_index = (DIMENSION_ORDER.index(dim) + 1) if dim in DIMENSION_ORDER else 0
        return self.parser.parse_dimension_result(dim, response, dim_index)

    async def _confirm_step(self, dim: str, result: DimensionResult):
        if not result.anomalies:
            return

        anomalies_summary = "\n".join(
            [f"- {a.item_name}: {a.description[:100]}..." for a in result.anomalies[:3]]
        )

        confirm_prompt = f"""
请仅回答"是"或"否"：
以下异常点是否在判决书中有明确原文支撑？

{anomalies_summary}
"""
        system_prompt = "请仅回答是或否，不要展开解释。"

        try:
            response, _ = await self.llm.acall(system_prompt, confirm_prompt)
            self.context_history.append(
                {
                    "dimension": dim,
                    "confirmed": "是" in response,
                    "anomaly_count": len(result.anomalies),
                }
            )
        except Exception:
            pass

    async def _run_adversarial_check(self, results: list[DimensionResult]) -> str:
        all_anomalies = []
        for r in results:
            for a in r.anomalies:
                all_anomalies.append(f"[{r.dimension}] {a.item_name}: {a.description}")

        if not all_anomalies:
            return "未发现显著异常点，无需对抗校验。"

        anomalies_text = "\n".join(all_anomalies[:20])
        prompt = ADVERSARIAL_PROMPT.format(anomalies=anomalies_text)

        system_prompt = "你是对抗校验专家（Devil's Advocate），请对检测出的异常点进行反向审查。"
        response, usage = await self.llm.acall(system_prompt, prompt)
        self.total_tokens_used += usage.get("total_tokens", 0)

        return response

    async def _run_coupling_analysis(self, results: list[DimensionResult]) -> str:
        beneficiary_counts: dict[str, int] = {}
        for r in results:
            for a in r.anomalies:
                if a.beneficiary:
                    beneficiary_counts[a.beneficiary] = beneficiary_counts.get(a.beneficiary, 0) + 1

        max_count = max(beneficiary_counts.values()) if beneficiary_counts else 0
        max_beneficiary = (
            max(beneficiary_counts, key=beneficiary_counts.get) if beneficiary_counts else ""
        )

        if max_count >= 7:
            level = "结构性偏差"
        elif max_count >= 5:
            level = "高度耦合"
        elif max_count >= 3:
            level = "中度耦合"
        else:
            level = "低度耦合"

        analysis = "## 惯性耦合分析结果\n\n"
        analysis += f"**耦合等级**：{level}\n"
        analysis += f"**主要获益方**：{max_beneficiary}\n"
        analysis += f"**异常维度数**：{max_count}\n\n"

        analysis += "### 各维度异常统计\n"
        for r in results:
            analysis += f"- {r.dimension}: {len(r.anomalies)} 项异常\n"

        analysis += "\n### 耦合判定\n"
        if level in ["高度耦合", "结构性偏差"]:
            analysis += (
                f"多个维度的异常均指向**{max_beneficiary}**，"
                f"异常程度超出通常业务能力波动范围，"
                f"提示可能存在系统性的程序控制、证据筛选或法律适用倾向，"
                f"建议启动更高层级的审查程序。"
            )
        else:
            analysis += "未发现显著的系统性耦合异常。"

        return analysis

    async def _run_quality_assessment(
        self, materials: str, dimension_results: list[DimensionResult]
    ) -> str:
        assessor = QualityAssessor(self.llm)
        try:
            q_result = await assessor.assess(materials)
        except Exception:
            return "质量评估执行失败"

        lines = []
        lines.append("### 各维度评分\n")
        lines.append("| 维度 | 满分 | 扣分 | 得分 | 主要扣分项 |")
        lines.append("|:---|:---|:---|:---|:---|")

        for ds in q_result.dimension_scores:
            deductions = "; ".join(
                d.get("item", "")[:40] for d in ds.deduction_items[:3]
            ) or "-"
            lines.append(
                f"| {ds.dimension} | {ds.full_score} | {ds.deduction} | "
                f"{ds.score} | {deductions} |"
            )

        lines.append("")
        lines.append("### 综合评级\n")
        lines.append(f"- **加权总分**：{q_result.total_score:.1f}/100")
        lines.append(f"- **综合等级**：{q_result.grade}（{q_result.grade_description}）")

        if q_result.strengths:
            lines.append(f"- **核心优势**：{'；'.join(q_result.strengths[:3])}")
        if q_result.weaknesses:
            lines.append(f"- **核心不足**：{'；'.join(q_result.weaknesses[:3])}")

        return "\n".join(lines)

    async def _run_graph_building(self, materials: str) -> str:
        from .preprocessor import PreprocessResult

        builder = GraphBuilder(self.llm, self.config.graph)
        try:
            pre_result = PreprocessResult(materials_text=materials)
            g_result = await builder.run(pre_result)
        except Exception:
            return "图构建执行失败"

        parts = []
        if g_result.evidence_mermaid:
            parts.append("### 证据关系图\n")
            parts.append("```mermaid")
            parts.append(g_result.evidence_mermaid)
            parts.append("```\n")

        if g_result.procedure_mermaid:
            parts.append("### 程序行为图\n")
            parts.append("```mermaid")
            parts.append(g_result.procedure_mermaid)
            parts.append("```\n")

        if g_result.reasoning_mermaid:
            parts.append("### 法律推理图\n")
            parts.append("```mermaid")
            parts.append(g_result.reasoning_mermaid)
            parts.append("```\n")

        if g_result.anomaly_paths:
            parts.append("### 异常路径识别\n")
            for ap in g_result.anomaly_paths:
                parts.append(f"- **{ap.pattern}**：{ap.description}（{ap.meaning}）")

        return "\n".join(parts) if parts else "图构建未产生输出"

    def _calculate_risk_level(self, results: list[DimensionResult]) -> tuple[str, str]:
        total_anomalies = sum(len(r.anomalies) for r in results)
        high_confidence = sum(1 for r in results for a in r.anomalies if a.confidence == "high")

        if total_anomalies >= 10 and high_confidence >= 5:
            return "结构性偏差", f"检测到{total_anomalies}项异常，其中{high_confidence}项高置信度异常"
        elif total_anomalies >= 5 and high_confidence >= 3:
            return "高度异常", f"检测到{total_anomalies}项异常，其中{high_confidence}项高置信度异常"
        elif total_anomalies >= 2:
            return "中度异常", f"检测到{total_anomalies}项异常"
        else:
            return "低度异常", f"检测到{total_anomalies}项异常"

    def _generate_remedies(self, results: list[DimensionResult]) -> str:
        remedies = []

        procedure_anomalies = [a for r in results if r.dimension == "procedure" for a in r.anomalies]
        if procedure_anomalies:
            remedies.append("### 程序违法救济\n")
            remedies.append("- 如存在严重程序违法，可依据《民事诉讼法》第207条申请再审\n")
            remedies.append("- 程序违法是再审的法定事由，建议重点收集程序违法证据\n")

        evidence_anomalies = [
            a for r in results if r.dimension in ["evidence", "fact_finding"] for a in r.anomalies
        ]
        if evidence_anomalies:
            remedies.append("### 事实认定错误救济\n")
            remedies.append("- 事实认定错误属于再审法定事由\n")
            remedies.append("- 建议整理'事实认定错误快速对照清单'，逐项列明原审错误\n")
            remedies.append("- 收集新证据或原审未质证的证据作为再审依据\n")

        law_anomalies = [a for r in results if r.dimension == "law_application" for a in r.anomalies]
        if law_anomalies:
            remedies.append("### 法律适用错误救济\n")
            remedies.append("- 法律适用错误是上诉和再审的重要理由\n")
            remedies.append("- 建议检索类案裁判规则，形成类案偏离对比报告\n")

        if not remedies:
            remedies.append("未发现显著异常，暂无需特别救济措施。")

        return "\n".join(remedies)

    def _extract_case_name(self, materials: str) -> str:
        for line in materials.split("\n")[:80]:
            line = line.strip()
            if "案号" in line and len(line) < 80:
                return line
        m = re.search(r"[(（]\d{4}[)）].*?民[^\s]*?\d+\s*号", materials)
        if m:
            matched = m.group(0)
            ctx_start = max(0, m.start() - 40)
            ctx = materials[ctx_start : m.end() + 10]
            if any(kw in ctx for kw in ["判决书", "裁定书", "本案", "原告", "被告", "上诉人", "被上诉人"]):
                return matched
        m = re.search(r"[(（]\d{4}[)）].+?\d+\s*号", materials)
        if m:
            ctx_start = max(0, m.start() - 40)
            ctx = materials[ctx_start : m.end() + 10]
            if any(kw in ctx for kw in ["判决书", "裁定书", "本案", "原告", "被告", "上诉人", "被上诉人"]):
                return m.group(0)
        for line in materials.split("\n")[:30]:
            line = line.strip()
            if any(kw in line for kw in ["民事判决书", "行政判决书", "刑事判决书"]):
                return line[:100]
        return "未知案件"

    def _extract_doc_type(self, materials: str) -> str:
        if "判决书" in materials:
            return "判决书"
        elif "裁定书" in materials:
            return "裁定书"
        elif "裁决书" in materials:
            return "裁决书"
        elif "决定书" in materials:
            return "决定书"
        else:
            return "未知"
