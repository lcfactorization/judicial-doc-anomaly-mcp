"""Core detection engine for judicial document anomaly detection"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from .config import AppConfig, DetectionConfig
from .llm_caller import LLMLLMCaller
from .prompts import DIMENSION_PROMPTS, ADVERSARIAL_CHECK_PROMPT, REPORT_TEMPLATE


class AnomalyItem(BaseModel):
    """Single anomaly detection result"""
    dimension: str
    item_name: str
    description: str
    beneficiary: str = ""
    confidence: str = "high"  # high, medium, low
    original_text: str = ""
    legal_analysis: str = ""


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
            with open(md_file, "r", encoding="utf-8") as f:
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
        self.llm = LLMLLMCaller(config.llm, cache_dir=config.cache_dir)
        self.file_loader: Optional[FileLoader] = None
        self.context_history: list[dict] = []
        self.total_tokens = 0
    
    async def run_detection(
        self,
        case_dir: str,
        dimensions: Optional[list[str]] = None,
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
            
            dim_result = await self._run_dimension(dim, materials_text, dimension_results)
            dimension_results.append(dim_result)
            
            # Step confirmation (anti-attention-decay)
            if self.config.detection.step_confirmation:
                await self._confirm_step(dim, dim_result)
        
        result.dimension_results = dimension_results
        
        # Phase 5: Adversarial check
        if self.config.detection.enable_adversarial_check:
            result.adversarial_results = await self._run_adversarial_check(dimension_results)
        
        # Phase 6: Coupling analysis
        result.coupling_analysis = await self._run_coupling_analysis(dimension_results)
        
        # Calculate overall risk level
        result.risk_level, result.risk_reason = self._calculate_risk_level(dimension_results)
        
        # Generate remedies
        result.remedies = self._generate_remedies(dimension_results)
        
        # Generate report
        result.total_tokens = self.total_tokens
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
            for prev in previous_results[-3:]:  # Only include last 3 to avoid context overflow
                context += f"\n### {prev.dimension}\n{prev.summary}\n"
                for a in prev.anomalies[:5]:  # Limit anomalies in context
                    context += f"- {a.item_name}: {a.description}\n"
        
        # Truncate materials if too long
        max_tokens = self.config.detection.max_context_tokens
        if self.llm.estimate_tokens(materials) > max_tokens * 0.7:
            materials = materials[:int(max_tokens * 0.7 / 1.5)]
        
        user_prompt = prompt_template.format(materials=materials + context)
        system_prompt = "你是专业的司法文书审查专家，请严格按照检测要求进行系统性审查。"
        
        response, usage = await self.llm.acall(system_prompt, user_prompt)
        self.total_tokens += usage.get("total_tokens", 0)
        
        # Parse response into structured result
        return self._parse_dimension_result(dim, response)
    
    async def _confirm_step(self, dim: str, result: DimensionResult):
        """Confirm key findings after each step (anti-attention-decay)"""
        if not result.anomalies:
            return
        
        # Create confirmation prompt
        anomalies_summary = "\n".join([
            f"- {a.item_name}: {a.description[:100]}..."
            for a in result.anomalies[:3]
        ])
        
        confirm_prompt = f"""
请仅回答"是"或"否"：
以下异常点是否在判决书中有明确原文支撑？

{anomalies_summary}
"""
        system_prompt = "请仅回答是或否，不要展开解释。"
        
        try:
            response, _ = await self.llm.acall(system_prompt, confirm_prompt)
            # Log confirmation result for audit trail
            self.context_history.append({
                "dimension": dim,
                "confirmed": "是" in response,
                "anomaly_count": len(result.anomalies),
            })
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
        prompt = ADVERSARIAL_CHECK_PROMPT.format(anomalies=anomalies_text)
        
        system_prompt = "你是对抗校验专家（Devil's Advocate），请对检测出的异常点进行反向审查。"
        response, usage = await self.llm.acall(system_prompt, prompt)
        self.total_tokens += usage.get("total_tokens", 0)
        
        return response
    
    async def _run_coupling_analysis(self, results: list[DimensionResult]) -> str:
        """Run coupling analysis across dimensions"""
        # Count anomalies by beneficiary
        beneficiary_counts: dict[str, int] = {}
        for r in results:
            for a in r.anomalies:
                if a.beneficiary:
                    beneficiary_counts[a.beneficiary] = beneficiary_counts.get(a.beneficiary, 0) + 1
        
        # Determine coupling level
        max_count = max(beneficiary_counts.values()) if beneficiary_counts else 0
        max_beneficiary = max(beneficiary_counts, key=beneficiary_counts.get) if beneficiary_counts else ""
        
        if max_count >= 7:
            level = "结构性偏差"
        elif max_count >= 5:
            level = "高度耦合"
        elif max_count >= 3:
            level = "中度耦合"
        else:
            level = "低度耦合"
        
        # Build analysis
        analysis = f"## 惯性耦合分析结果\n\n"
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
    
    def _calculate_risk_level(self, results: list[DimensionResult]) -> tuple[str, str]:
        """Calculate overall risk level"""
        total_anomalies = sum(len(r.anomalies) for r in results)
        high_confidence = sum(
            1 for r in results for a in r.anomalies if a.confidence == "high"
        )
        
        if total_anomalies >= 10 and high_confidence >= 5:
            return "结构性偏差", f"检测到{total_anomalies}项异常，其中{high_confidence}项高置信度异常"
        elif total_anomalies >= 5 and high_confidence >= 3:
            return "高度异常", f"检测到{total_anomalies}项异常，其中{high_confidence}项高置信度异常"
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
    
    def _generate_report(self, result: DetectionResult) -> str:
        """Generate final markdown report"""
        # Build anomaly table
        table_rows = []
        for r in result.dimension_results:
            for a in r.anomalies:
                table_rows.append(
                    f"| {r.dimension} | {a.item_name} | {a.description[:50]}... | {a.beneficiary} | {a.confidence} |"
                )
        
        anomaly_table = "\n".join(table_rows) if table_rows else "| - | - | 未发现异常 | - | - |"
        
        # Build dimension details
        dimension_details = ""
        for r in result.dimension_results:
            dimension_details += f"\n## {r.dimension}\n\n"
            dimension_details += f"**风险等级**：{r.risk_level}\n\n"
            dimension_details += f"**摘要**：{r.summary}\n\n"
            for i, a in enumerate(r.anomalies, 1):
                dimension_details += f"### {i}. {a.item_name}\n"
                dimension_details += f"- **描述**：{a.description}\n"
                dimension_details += f"- **原文引用**：{a.original_text}\n"
                dimension_details += f"- **获益方**：{a.beneficiary}\n"
                dimension_details += f"- **置信度**：{a.confidence}\n"
                dimension_details += f"- **法理分析**：{a.legal_analysis}\n\n"
        
        return REPORT_TEMPLATE.format(
            case_name=result.case_name,
            doc_type=result.doc_type,
            model_name=result.model_name,
            detection_time=result.detection_time,
            completeness_score=result.completeness_score,
            legal_basis=result.legal_basis or "待补充",
            risk_level=result.risk_level,
            risk_reason=result.risk_reason,
            anomaly_table=anomaly_table,
            dimension_details=dimension_details,
            adversarial_results=result.adversarial_results or "未执行对抗校验",
            coupling_analysis=result.coupling_analysis or "未执行耦合分析",
            remedies=result.remedies,
            version="0.1.0",
        )
    
    def _parse_dimension_result(self, dim: str, response: str) -> DimensionResult:
        """Parse LLM response into structured dimension result"""
        result = DimensionResult(dimension=dim)
        
        # Simple parsing: extract anomalies from response
        # In production, this should use more sophisticated parsing
        lines = response.split("\n")
        current_anomaly = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Try to detect anomaly items
            if any(keyword in line for keyword in ["异常", "问题", "瑕疵", "错误"]):
                if current_anomaly:
                    result.anomalies.append(current_anomaly)
                current_anomaly = AnomalyItem(
                    dimension=dim,
                    item_name=line[:50],
                    description=line,
                )
            elif current_anomaly and len(current_anomaly.description) < 500:
                current_anomaly.description += "\n" + line
        
        if current_anomaly:
            result.anomalies.append(current_anomaly)
        
        # Extract summary (first paragraph)
        paragraphs = response.split("\n\n")
        if paragraphs:
            result.summary = paragraphs[0][:200]
        
        return result
    
    def _extract_case_name(self, materials: str) -> str:
        """Extract case name from materials"""
        for line in materials.split("\n")[:50]:
            if any(kw in line for kw in ["案号", "案件", "民事判决", "行政判决"]):
                return line.strip()[:100]
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
