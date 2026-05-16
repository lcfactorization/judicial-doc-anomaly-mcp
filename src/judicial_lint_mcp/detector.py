"""Core detection engine for judicial document anomaly detection"""

import logging
import re
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from .config import AppConfig
from .graph_builder import GraphBuilder
from .llm_caller import LLMCaller
from .prompts import ADVERSARIAL_PROMPT, DIMENSION_PROMPTS, REPORT_TEMPLATE
from .quality_assessor import QualityAssessor
from .taxonomy import TAXONOMY, category_from_f_code, dimension_to_categories

logger = logging.getLogger(__name__)


class AnomalyItem(BaseModel):
    """Single anomaly detection result"""

    dimension: str
    item_name: str = ""
    description: str = ""
    beneficiary: str = ""
    confidence: str = "medium"
    original_text: str = ""
    legal_analysis: str = ""
    f_code: str = ""
    a_code: str = ""
    reverse_check: str = ""
    net_anomaly: str = ""


class DimensionResult(BaseModel):
    """Result for one dimension"""

    dimension: str
    anomalies: list[AnomalyItem] = []
    summary: str = ""
    risk_level: str = "low"  # low, medium, high, critical


class DetectionResult(BaseModel):
    """Complete detection result"""

    case_name: str = ""
    doc_type: str = ""
    model_name: str = ""
    detection_time: str = ""
    completeness_score: float = 0.0
    legal_basis: str = ""
    dimension_results: list[DimensionResult] = []
    adversarial_results: str = ""
    coupling_analysis: str = ""
    quality_score_table: str = ""
    mermaid_graph: str = ""
    risk_level: str = "low"
    risk_reason: str = ""
    remedies: str = ""
    total_tokens_used: int = 0
    report_markdown: str = ""


class FileLoader:
    """Load and validate case materials from directory"""

    REQUIRED_FILES = ["判决书", "裁判文书"]
    RECOMMENDED_FILES = ["起诉状", "答辩状", "上诉状", "证据清单", "庭审笔录"]

    def __init__(self, case_dir: str):
        self.case_dir = Path(case_dir)
        self.files: dict[str, str] = {}
        self.missing_files: list[str] = []

    def load(self) -> dict[str, str]:
        """Load all markdown files from case directory"""
        if not self.case_dir.exists():
            raise FileNotFoundError(f"Case directory not found: {self.case_dir}")

        for md_file in self.case_dir.glob("*.md"):
            name_lower = md_file.name.lower()
            if any(kw in name_lower for kw in (
                "report", "检测报告", "异常检测", "评估报告",
                "deepseek_markdown", "阅卷",
            )):
                continue
            with open(md_file, encoding="utf-8") as f:
                content = f.read()
            self.files[md_file.stem] = content

        return self.files

    def validate(self) -> tuple[float, list[str]]:
        """Validate material completeness, return (score, missing_files)"""
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
        """Combine all materials into single text"""
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

    async def run_detection(
        self,
        case_dir: str,
        dimensions: list[str] | None = None,
    ) -> DetectionResult:
        """
        Run full detection workflow on case directory.

        Args:
            case_dir: Path to case directory containing .md files
            dimensions: List of dimensions to run (None = all)

        Returns:
            DetectionResult with full report
        """
        result = DetectionResult(
            detection_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            model_name=self.config.llm.model,
        )

        # Phase 0: Load and validate materials
        self.file_loader = FileLoader(case_dir)
        self.file_loader.load()
        completeness, missing = self.file_loader.validate()
        result.completeness_score = completeness

        materials_text = self.file_loader.get_materials_text()

        # Extract case info from materials
        result.case_name = self._extract_case_name(materials_text)
        result.doc_type = self._extract_doc_type(materials_text)

        dims = dimensions or self.config.detection.dimensions

        # Phase 1-4: Run dimension-by-dimension detection
        dimension_results = []
        for dim in dims:
            if dim not in DIMENSION_PROMPTS:
                continue

            dim_result = await self._run_dimension(
                dim, materials_text, dimension_results
            )
            dimension_results.append(dim_result)

            # Step confirmation (anti-attention-decay)
            if self.config.detection.step_confirmation:
                await self._confirm_step(dim, dim_result)

        result.dimension_results = dimension_results

        # Phase 5: Adversarial check
        if self.config.detection.enable_adversarial_check:
            result.adversarial_results = await self._run_adversarial_check(
                dimension_results
            )

        # Phase 6: Coupling analysis
        result.coupling_analysis = await self._run_coupling_analysis(dimension_results)

        # Phase 7: Quality assessment
        if self.config.detection.enable_quality_assessment:
            try:
                quality_result = await self._run_quality_assessment(
                    materials_text, dimension_results
                )
                result.quality_score_table = quality_result
            except Exception as e:
                result.quality_score_table = f"质量评估执行失败：{e}"

        # Phase 8: Graph building
        if self.config.detection.enable_graph_building:
            try:
                graph_result = await self._run_graph_building(materials_text)
                result.mermaid_graph = graph_result
            except Exception as e:
                result.mermaid_graph = f"图构建执行失败：{e}"

        # Calculate overall risk level
        result.risk_level, result.risk_reason = self._calculate_risk_level(
            dimension_results
        )

        # Generate remedies
        result.remedies = self._generate_remedies(dimension_results)

        # Generate report
        result.total_tokens_used = self.total_tokens_used
        result.report_markdown = self._generate_report(result)

        return result

    async def _run_dimension(
        self,
        dim: str,
        materials: str,
        previous_results: list[DimensionResult],
    ) -> DimensionResult:
        """Run single dimension detection"""
        prompt_template = DIMENSION_PROMPTS[dim]

        # Build context from previous results (anti-attention-decay)
        context = ""
        if previous_results:
            context = "\n\n## 前序维度检测结果（作为参考上下文）\n"
            for prev in previous_results[
                -3:
            ]:  # Only include last 3 to avoid context overflow
                context += f"\n### {prev.dimension}\n{prev.summary}\n"
                for a in prev.anomalies[:5]:  # Limit anomalies in context
                    context += f"- {a.item_name}: {a.description}\n"

        # Truncate materials if too long
        max_tokens = self.config.detection.max_context_tokens
        if self.llm.estimate_tokens(materials) > max_tokens * 0.7:
            materials = materials[: int(max_tokens * 0.7 / 1.5)]

        fmt_kwargs = {
            "materials": materials + context,
            "previous_results": materials + context,
        }
        user_prompt = prompt_template.format(**fmt_kwargs)
        system_prompt = "你是专业的司法文书审查专家，请严格按照检测要求进行系统性审查。"

        response, usage = await self.llm.acall(system_prompt, user_prompt)
        self.total_tokens_used += usage.get("total_tokens", 0)

        # Parse response into structured result
        return self._parse_dimension_result(dim, response)

    async def _confirm_step(self, dim: str, result: DimensionResult):
        """Confirm key findings after each step (anti-attention-decay)"""
        if not result.anomalies:
            return

        # Create confirmation prompt
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
            # Log confirmation result for audit trail
            self.context_history.append(
                {
                    "dimension": dim,
                    "confirmed": "是" in response,
                    "anomaly_count": len(result.anomalies),
                }
            )
        except Exception:
            pass  # Non-critical, continue

    async def _run_adversarial_check(self, results: list[DimensionResult]) -> str:
        """Run devil's advocate validation"""
        all_anomalies = []
        for r in results:
            for a in r.anomalies:
                all_anomalies.append(f"[{r.dimension}] {a.item_name}: {a.description}")

        if not all_anomalies:
            return "未发现显著异常点，无需对抗校验。"

        anomalies_text = "\n".join(all_anomalies[:20])  # Limit to top 20
        prompt = ADVERSARIAL_PROMPT.format(anomalies=anomalies_text)

        system_prompt = (
            "你是对抗校验专家（Devil's Advocate），请对检测出的异常点进行反向审查。"
        )
        response, usage = await self.llm.acall(system_prompt, prompt)
        self.total_tokens_used += usage.get("total_tokens", 0)

        return response

    async def _run_coupling_analysis(self, results: list[DimensionResult]) -> str:
        """Run coupling analysis across dimensions"""
        # Count anomalies by beneficiary
        beneficiary_counts: dict[str, int] = {}
        for r in results:
            for a in r.anomalies:
                if a.beneficiary:
                    beneficiary_counts[a.beneficiary] = (
                        beneficiary_counts.get(a.beneficiary, 0) + 1
                    )

        # Determine coupling level
        max_count = max(beneficiary_counts.values()) if beneficiary_counts else 0
        max_beneficiary = (
            max(beneficiary_counts, key=beneficiary_counts.get)
            if beneficiary_counts
            else ""
        )

        if max_count >= 7:
            level = "结构性偏差"
        elif max_count >= 5:
            level = "高度耦合"
        elif max_count >= 3:
            level = "中度耦合"
        else:
            level = "低度耦合"

        # Build analysis
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
        """Calculate overall risk level"""
        total_anomalies = sum(len(r.anomalies) for r in results)
        high_confidence = sum(
            1 for r in results for a in r.anomalies if a.confidence == "high"
        )

        if total_anomalies >= 10 and high_confidence >= 5:
            return (
                "结构性偏差",
                f"检测到{total_anomalies}项异常，其中{high_confidence}项高置信度异常",
            )
        elif total_anomalies >= 5 and high_confidence >= 3:
            return (
                "高度异常",
                f"检测到{total_anomalies}项异常，其中{high_confidence}项高置信度异常",
            )
        elif total_anomalies >= 2:
            return "中度异常", f"检测到{total_anomalies}项异常"
        else:
            return "低度异常", f"检测到{total_anomalies}项异常"

    def _generate_remedies(self, results: list[DimensionResult]) -> str:
        """Generate remedial suggestions"""
        remedies = []

        procedure_anomalies = [
            a for r in results if r.dimension == "procedure" for a in r.anomalies
        ]
        if procedure_anomalies:
            remedies.append("### 程序违法救济\n")
            remedies.append(
                "- 如存在严重程序违法，可依据《民事诉讼法》第207条申请再审\n"
            )
            remedies.append("- 程序违法是再审的法定事由，建议重点收集程序违法证据\n")

        evidence_anomalies = [
            a
            for r in results
            if r.dimension in ["evidence", "fact_finding"]
            for a in r.anomalies
        ]
        if evidence_anomalies:
            remedies.append("### 事实认定错误救济\n")
            remedies.append("- 事实认定错误属于再审法定事由\n")
            remedies.append("- 建议整理'事实认定错误快速对照清单'，逐项列明原审错误\n")
            remedies.append("- 收集新证据或原审未质证的证据作为再审依据\n")

        law_anomalies = [
            a for r in results if r.dimension == "law_application" for a in r.anomalies
        ]
        if law_anomalies:
            remedies.append("### 法律适用错误救济\n")
            remedies.append("- 法律适用错误是上诉和再审的重要理由\n")
            remedies.append("- 建议检索类案裁判规则，形成类案偏离对比报告\n")

        if not remedies:
            remedies.append("未发现显著异常，暂无需特别救济措施。")

        return "\n".join(remedies)

    _CONFIDENCE_CN = {"high": "高度", "medium": "中度", "low": "低度", "critical": "极高"}
    _RISK_CN = {"low": "🟢 低风险", "medium": "🟡 中风险", "high": "🟠 高风险", "critical": "🔴 极高风险"}
    _RISK_CN_SHORT = {"low": "低", "medium": "中", "high": "高", "critical": "极高"}

    def _generate_report(self, result: DetectionResult) -> str:
        seq = 0
        table_rows = []
        for r in result.dimension_results:
            dim_cn = self._dim_label(r.dimension)
            for a in r.anomalies:
                seq += 1
                desc_short = a.description[:80].replace("\n", " ").replace("|", "／")
                beneficiary = a.beneficiary or "—"
                a_code = a.a_code or "—"
                conf_cn = self._CONFIDENCE_CN.get(a.confidence, a.confidence)
                table_rows.append(
                    f"| {seq} | {dim_cn} | {a.item_name[:30]} | {desc_short} | "
                    f"{beneficiary} | {a_code} | {conf_cn} |"
                )

        anomaly_table = (
            "\n".join(table_rows)
            if table_rows
            else "| - | - | 未发现异常 | - | - | - | - |"
        )

        total_anomalies = sum(len(r.anomalies) for r in result.dimension_results)
        high_count = sum(
            1 for r in result.dimension_results for a in r.anomalies if a.confidence == "high"
        )
        medium_count = sum(
            1 for r in result.dimension_results for a in r.anomalies if a.confidence == "medium"
        )
        low_count = total_anomalies - high_count - medium_count

        dimension_details = ""
        for r in result.dimension_results:
            dim_cn = self._dim_label(r.dimension)
            risk_cn = self._RISK_CN.get(r.risk_level, r.risk_level)
            dimension_details += f"\n### {dim_cn}\n\n"
            dimension_details += f"**风险等级**：{risk_cn}  |  **异常项数**：{len(r.anomalies)}\n\n"

            if r.anomalies:
                dimension_details += "| 序号 | 异常项 | 获益方 | 异常分类 | F编号 | 置信度 | 简要表现 |\n"
                dimension_details += "|:---:|:---|:---|:---:|:---:|:---:|:---|\n"
                for i, a in enumerate(r.anomalies, 1):
                    conf_cn = self._CONFIDENCE_CN.get(a.confidence, a.confidence)
                    desc_cell = a.description[:60].replace("\n", " ").replace("|", "／")
                    dimension_details += (
                        f"| {i} | {a.item_name[:25]} | {a.beneficiary or '—'} | "
                        f"{a.a_code or '—'} | {a.f_code or '—'} | {conf_cn} | {desc_cell} |\n"
                    )
                dimension_details += "\n"

                if r.risk_level in ("high", "critical"):
                    dim_summary = r.summary[:200].replace("\n", " ") if r.summary else ""
                    dimension_details += f"> [!WARNING]\n"
                    dimension_details += f"> 本维度存在 {len(r.anomalies)} 项异常，风险等级{risk_cn}。{dim_summary}\n\n"

                for i, a in enumerate(r.anomalies, 1):
                    dimension_details += f"\n**{i}. {a.item_name}**\n\n"
                    if a.description:
                        dimension_details += f"- **具体表现**：{a.description[:300]}\n"
                    if a.original_text:
                        original_short = a.original_text[:200].replace("\n", " ")
                        dimension_details += f"- **原文引用**：> {original_short}\n"
                    if a.legal_analysis:
                        legal_short = a.legal_analysis[:300].replace("\n", " ")
                        dimension_details += f"- **法理分析**：{legal_short}\n"
                    dimension_details += "\n"
            else:
                dimension_details += "✅ 本维度未发现显著异常。\n\n"

        adversarial_section = result.adversarial_results or "未执行对抗校验"
        coupling_section = result.coupling_analysis or "未执行耦合分析"
        quality_section = result.quality_score_table or "未执行质量评估"
        graph_section = result.mermaid_graph or ""

        risk_cn = self._RISK_CN.get(result.risk_level, result.risk_level)
        report_id = datetime.now().strftime("%Y%m%d%H%M")

        risk_detail_lines = []
        if high_count > 0:
            risk_detail_lines.append(f"> [!WARNING]")
            risk_detail_lines.append(f"> 检出 {high_count} 项高置信度异常，建议优先审查。")
        if total_anomalies > 5:
            risk_detail_lines.append(f"> [!IMPORTANT]")
            risk_detail_lines.append(f"> 异常项总数达 {total_anomalies} 项，存在系统性偏差风险，建议启动多维度联合审查。")
        risk_detail_block = "\n".join(risk_detail_lines) if risk_detail_lines else ""

        report = REPORT_TEMPLATE.format(
            report_id=report_id,
            case_name=result.case_name,
            doc_type=result.doc_type,
            model_name=result.model_name,
            detection_time=result.detection_time,
            completeness_score=f"{result.completeness_score:.1f}",
            version="0.2.0",
            risk_level=risk_cn,
            risk_reason=result.risk_reason,
            risk_detail_block=risk_detail_block,
            anomaly_table=anomaly_table,
            total_dims=len(result.dimension_results),
            total_anomalies=total_anomalies,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
            dimension_details=dimension_details,
            adversarial_table=adversarial_section,
            coupling_analysis=coupling_section,
            quality_score_table=quality_section,
            quick_check_results="未执行速查",
            remedies=result.remedies,
        )

        if graph_section:
            report += f"\n\n---\n\n## 附录：图结构分析\n\n{graph_section}\n"

        return report

    def _dim_label(self, dim: str) -> str:
        from .prompts import DIMENSION_LABELS
        return DIMENSION_LABELS.get(dim, dim)

    def _parse_dimension_result(self, dim: str, response: str) -> DimensionResult:
        result = DimensionResult(dimension=dim)

        dim_categories = dimension_to_categories(
            list(DIMENSION_PROMPTS.keys()).index(dim) + 1
            if dim in DIMENSION_PROMPTS else 0
        )

        sections = re.split(r"\n####\s+\*?\*?\d+\.?\s*", response)
        if len(sections) < 2:
            sections = re.split(r"\n###\s+", response)

        if len(sections) < 2:
            sections = re.split(r"\n(?=异常项[：:])", response)

        for section in sections[1:]:
            section = section.strip()
            if not section or len(section) < 20:
                continue

            anomaly = AnomalyItem(dimension=dim)

            header_match = re.match(r"异常项[：:]\s*(.+?)(?:\*?\*?\s*$)", section)
            if header_match:
                anomaly.item_name = header_match.group(1).strip().rstrip("*").strip()
            else:
                first_line = section.split("\n")[0].strip().rstrip("*").strip()
                anomaly.item_name = first_line[:60]

            anomaly.description = self._extract_field(section, r"具体表现\*?\*?[：:]", 800)
            if not anomaly.description:
                anomaly.description = self._extract_field(section, r"异常表现\*?\*?[：:]", 800)

            meta = self._parse_meta_line(section)
            if meta.get("confidence"):
                anomaly.confidence = self._map_confidence(meta["confidence"])
            else:
                confidence_text = self._extract_field(section, r"异常程度\*?\*?[：:]", 100)
                anomaly.confidence = self._map_confidence(confidence_text)

            anomaly.legal_analysis = self._extract_field(section, r"法理分析\*?\*?[：:]", 600)

            anomaly.original_text = self._extract_field(section, r"原文(?:引用|定位)\*?\*?[：:]", 400)

            if meta.get("beneficiary"):
                anomaly.beneficiary = self._normalize_beneficiary(meta["beneficiary"])
            else:
                beneficiary_text = self._extract_field(section, r"(?:指向)?获益方\*?\*?[：:]", 100)
                anomaly.beneficiary = self._normalize_beneficiary(
                    beneficiary_text or self._infer_beneficiary(section)
                )

            if meta.get("f_code"):
                anomaly.f_code = meta["f_code"]
            else:
                anomaly.f_code = self._infer_f_code(section)

            if meta.get("a_code"):
                anomaly.a_code = meta["a_code"]
            else:
                anomaly.a_code = self._map_to_a_code(anomaly, dim_categories)

            anomaly.reverse_check = ""
            anomaly.net_anomaly = ""

            result.anomalies.append(anomaly)

        if not result.anomalies:
            result.anomalies.append(AnomalyItem(
                dimension=dim,
                item_name=f"{dim} 维度检测结果",
                description=response[:2000],
                confidence="medium",
            ))

        paragraphs = [p.strip() for p in response.split("\n\n") if p.strip()]
        result.summary = paragraphs[0][:300] if paragraphs else response[:200]

        high_count = sum(1 for a in result.anomalies if a.confidence == "high")
        if high_count >= 3:
            result.risk_level = "critical"
        elif high_count >= 1:
            result.risk_level = "high"
        elif result.anomalies:
            result.risk_level = "medium"

        return result

    _FIELD_BOUNDARY = r"\n\*\s+\*\*"

    def _parse_meta_line(self, text: str) -> dict:
        """Parse metadata lines like:
        *   **A分类**：A5
        *   **置信度**：高度可能
        *   **指向获益方**：被上诉人（...）
        """
        result = {}
        for line in text.split("\n")[:10]:
            line = line.strip()
            a_m = re.search(r"\*\*A分类\*\*[：:]\s*(\S+)", line)
            if a_m:
                result["a_code"] = a_m.group(1).strip()
            f_m = re.search(r"\*\*F编号\*\*[：:]\s*([Ff][-‐]\d{2})", line)
            if f_m:
                result["f_code"] = f_m.group(1).strip()
            c_m = re.search(r"\*\*置信度\*\*[：:]\s*([^*|\n]+)", line)
            if c_m:
                result["confidence"] = c_m.group(1).strip()
            b_m = re.search(r"\*\*(?:指向)?获益方\*\*[：:]\s*(.+?)(?:\*\*|\n|$)", line)
            if b_m:
                result["beneficiary"] = b_m.group(1).strip()
        return result

    def _extract_field(self, text: str, pattern: str, max_len: int = 500) -> str:
        m = re.search(
            rf"{pattern}\s*\n?(.+?)(?={self._FIELD_BOUNDARY}|\n####|\n###|\Z)",
            text,
            re.DOTALL,
        )
        if not m:
            m = re.search(
                rf"{pattern}\s*(.+?)(?={self._FIELD_BOUNDARY}|\n####|\n###|\Z)",
                text,
                re.DOTALL,
            )
        if m:
            value = m.group(1).strip()
            value = re.sub(r"\n\*\s+", "\n", value)
            value = re.sub(r"\*{1,3}", "", value)
            value = re.sub(r"\n{3,}", "\n\n", value)
            return value[:max_len]
        return ""

    def _map_confidence(self, text: str) -> str:
        if not text:
            return "medium"
        t = text.lower()
        if "确定" in t:
            return "high"
        if "高度可能" in t:
            return "high"
        if "可能" in t:
            return "medium"
        if "疑似" in t:
            return "low"
        return "medium"

    def _normalize_beneficiary(self, text: str) -> str:
        if not text:
            return ""
        t = text.strip()
        if any(kw in t for kw in ["原告", "上诉人", "劳动者", "员工", "职工", "申请人"]):
            return "原告/上诉人"
        if any(kw in t for kw in ["被告", "被上诉人", "用人单位", "公司", "单位", "被申请人"]):
            return "被告/被上诉人"
        if "双方" in t or "均" in t:
            return "双方"
        return t[:20]

    def _infer_beneficiary(self, text: str) -> str:
        plaintiff_kw = ["对原告不利", "损害劳动者", "侵害员工", "偏袒被告", "偏袒用人单位", "偏袒公司"]
        defendant_kw = ["对被告不利", "偏袒原告", "偏袒劳动者"]
        for kw in plaintiff_kw:
            if kw in text:
                return "被告/被上诉人"
        for kw in defendant_kw:
            if kw in text:
                return "原告/上诉人"
        return ""

    def _infer_f_code(self, text: str) -> str:
        f_patterns = [
            (r"举证责任.{0,5}(?:分配|倒置|转移)", "F-24"),
            (r"无证据支撑|找不到.*证据|没有.*证据", "F-01"),
            (r"孤证|单一证据", "F-03"),
            (r"前后矛盾|相互矛盾", "F-04"),
            (r"时间线|时间.*混乱|时间.*错误", "F-05"),
            (r"金额.*错误|主体.*错误|认定.*错误", "F-06"),
            (r"证人.*陈述|证人.*证言", "F-07"),
            (r"利害关系.*证言|利害关系人", "F-08"),
            (r"弱证据|拔高.*效力", "F-09"),
            (r"瑕疵.*采信|瑕疵.*证据", "F-10"),
            (r"逾期.*证据|超过.*举证", "F-11"),
            (r"无原件|复印件.*定案", "F-12"),
            (r"来源违法|违法.*证据", "F-13"),
            (r"只字不提|完全.*未提及|未.*提及", "F-14"),
            (r"原件.*无视|原件.*不采信", "F-15"),
            (r"未说明理由.*不采信|不予采信.*理由", "F-16"),
            (r"未经质证", "F-17"),
            (r"只看.*对方|不审查.*抗辩", "F-18"),
            (r"与本案无关.*排除", "F-19"),
            (r"推定.*代替|以推定", "F-20"),
            (r"未否认.*认可|沉默.*认可", "F-21"),
            (r"因果倒置|因果.*混淆", "F-22"),
            (r"选择性引用|仅引用.*有利", "F-23"),
            (r"证明标准", "F-25"),
            (r"举证期限.*双标|举证期限.*不同", "F-26"),
            (r"双重标准|双标|采信标准不一|审查标准不一", "F-10"),
            (r"程序.*违法|程序.*异常|送达.*异常|辩论权|质证权|管辖权", "F-17"),
            (r"回避.*争[议点]|焦点.*偏移|核心.*回避", "F-14"),
            (r"模板化|模板.*论证|机械.*复制", "A7"),
        ]
        for pattern, code in f_patterns:
            if re.search(pattern, text):
                return code
        return ""

    def _map_to_a_code(self, anomaly: AnomalyItem, dim_categories: list) -> str:
        if anomaly.f_code and anomaly.f_code.startswith("A"):
            return anomaly.f_code
        if dim_categories:
            return dim_categories[0].code if dim_categories else ""
        desc = anomaly.description + anomaly.item_name
        a_mappings = [
            (r"未回应|未予回应|未.*评述|未.*采信|关键证据.*未", "A1"),
            (r"事实认定.*跳跃|推理.*断裂|中间环节.*缺失|论证.*缺失", "A2"),
            (r"法律适用.*未解释|未说明.*为何适用|法条.*未说明", "A3"),
            (r"双重标准|双标|采信标准不一|审查标准不一|同类证据.*不同", "A4"),
            (r"程序.*时间.*异常|时间.*逆序|超期|加速.*审结|审限", "A5"),
            (r"回避.*争[议点]|焦点.*偏移|核心.*回避|虚化", "A6"),
            (r"模板化|模板.*论证|机械.*复制|通用模板", "A7"),
            (r"举证责任.*倒置|举证责任.*转移|举证责任.*分配.*错误", "A8"),
        ]
        for pattern, code in a_mappings:
            if re.search(pattern, desc):
                return code
        return ""

    def _extract_case_name(self, materials: str) -> str:
        for line in materials.split("\n")[:80]:
            line = line.strip()
            if "案号" in line and len(line) < 80:
                return line
        m = re.search(r"[(（]\d{4}[)）].+?\d+\s*号", materials)
        if m:
            ctx_start = max(0, m.start() - 40)
            ctx = materials[ctx_start:m.end() + 10]
            if any(kw in ctx for kw in ["判决书", "裁定书", "本案", "原告", "被告", "上诉人", "被上诉人"]):
                return m.group(0)
        for line in materials.split("\n")[:30]:
            line = line.strip()
            if any(kw in line for kw in ["民事判决书", "行政判决书", "刑事判决书"]):
                return line[:100]
        return "未知案件"

    def _extract_doc_type(self, materials: str) -> str:
        """Extract document type from materials"""
        if "判决书" in materials:
            return "判决书"
        elif "裁定书" in materials:
            return "裁定书"
        elif "裁决书" in materials:
            return "裁决书"
        elif "决定书" in materials:
            return "决定书"
        return "未知"
