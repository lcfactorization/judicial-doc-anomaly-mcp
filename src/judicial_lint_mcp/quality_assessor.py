"""Phase 4.5: Quality assessment engine for judicial documents

Implements 7-dimension 100-point quality scoring system
with grade determination (A-F).
"""

import re
from dataclasses import dataclass, field

from .config import (
    QUALITY_DIMENSIONS,
    QUALITY_FULL_SCORES,
    QUALITY_GRADES,
    QUALITY_WEIGHTS,
)
from .llm_caller import LLMCaller
from .prompts import QUALITY_ASSESSMENT_PROMPT


@dataclass
class DimensionScore:
    dimension: str
    full_score: int
    deduction: int
    score: int
    deduction_items: list[dict] = field(default_factory=list)
    weight: float = 0.0
    weighted_score: float = 0.0


@dataclass
class QualityAssessmentResult:
    dimension_scores: list[DimensionScore] = field(default_factory=list)
    total_score: float = 0.0
    grade: str = ""
    grade_description: str = ""
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    improvement_suggestions: list[str] = field(default_factory=list)
    raw_llm_output: str = ""


class QualityAssessor:
    def __init__(self, llm_caller: LLMCaller):
        self.llm_caller = llm_caller

    def _determine_grade(self, total_score: float) -> tuple[str, str]:
        for grade, (low, high, desc) in QUALITY_GRADES.items():
            if low <= total_score <= high:
                return grade, desc
        return "F", "严重缺陷"

    def _parse_llm_output(self, llm_output: str) -> QualityAssessmentResult:
        result = QualityAssessmentResult()
        dimension_scores = []

        for dim_key in QUALITY_DIMENSIONS:
            full = QUALITY_FULL_SCORES.get(dim_key, 0)
            weight = QUALITY_WEIGHTS.get(dim_key, 0.0)
            ds = DimensionScore(
                dimension=dim_key,
                full_score=full,
                deduction=0,
                score=full,
                weight=weight,
                weighted_score=full * weight,
            )
            dimension_scores.append(ds)

        score_pattern = re.compile(
            r"(?:程序合规性|事实认定质量|证据采信规范性|法律适用准确性|说理充分性|文书规范性|权利保障性)"
            r"[：:]\s*(\d+)\s*(?:[/／]\s*(\d+))?",
            re.UNICODE,
        )
        dim_name_map = {
            "程序合规性": "procedural_compliance",
            "事实认定质量": "fact_finding_quality",
            "证据采信规范性": "evidence_admission_norm",
            "法律适用准确性": "law_application_accuracy",
            "说理充分性": "reasoning_sufficiency",
            "文书规范性": "document_normativity",
            "权利保障性": "rights_protection",
        }

        for match in score_pattern.finditer(llm_output):
            score_val = int(match.group(1))
            full_val = int(match.group(2)) if match.group(2) else None
            dim_cn = match.group(0).split("：")[0].split(":")[0].strip()
            dim_key = dim_name_map.get(dim_cn, "")
            if dim_key:
                for ds in dimension_scores:
                    if ds.dimension == dim_key:
                        ds.score = min(score_val, ds.full_score)
                        ds.deduction = ds.full_score - ds.score
                        ds.weighted_score = ds.score * ds.weight
                        if full_val:
                            ds.full_score = full_val
                        break

        total = sum(ds.weighted_score for ds in dimension_scores)
        grade, grade_desc = self._determine_grade(total)

        strengths = []
        weaknesses = []
        suggestions = []

        strength_pattern = re.compile(r"核心优势[：:]\s*(.+?)(?:\n|$)", re.UNICODE)
        weakness_pattern = re.compile(r"核心不足[：:]\s*(.+?)(?:\n|$)", re.UNICODE)
        suggest_pattern = re.compile(r"改进建议[：:]\s*(.+?)(?:\n|$)", re.UNICODE)

        for match in strength_pattern.finditer(llm_output):
            strengths.append(match.group(1).strip())
        for match in weakness_pattern.finditer(llm_output):
            weaknesses.append(match.group(1).strip())
        for match in suggest_pattern.finditer(llm_output):
            suggestions.append(match.group(1).strip())

        result.dimension_scores = dimension_scores
        result.total_score = round(total, 1)
        result.grade = grade
        result.grade_description = grade_desc
        result.strengths = strengths
        result.weaknesses = weaknesses
        result.improvement_suggestions = suggestions
        return result

    async def assess(self, materials_text: str) -> QualityAssessmentResult:
        prompt = QUALITY_ASSESSMENT_PROMPT.format(materials=materials_text)
        llm_output, _ = await self.llm_caller.acall(
            "你是司法文书质量评估专家，请对文书进行七维度评分。",
            prompt,
        )
        result = self._parse_llm_output(llm_output)
        result.raw_llm_output = llm_output
        return result
