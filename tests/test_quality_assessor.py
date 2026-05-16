"""Tests for quality_assessor module"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from judicial_lint_mcp.quality_assessor import (
    QualityAssessor,
    QualityAssessmentResult,
    DimensionScore,
)
from judicial_lint_mcp.config import QUALITY_DIMENSIONS, QUALITY_WEIGHTS, QUALITY_FULL_SCORES


@pytest.fixture
def mock_llm_caller():
    caller = MagicMock()
    caller.acall = AsyncMock(return_value=("", {"total_tokens": 0}))
    return caller


MOCK_QUALITY_OUTPUT = """
# 文书质量评估

程序合规性：15/20
事实认定质量：10/20
证据采信规范性：8/15
法律适用准确性：12/15
说理充分性：8/15
文书规范性：7/10
权利保障性：3/5

核心优势：文书格式规范，程序基本完整
核心不足：事实认定说理不充分，证据采信存在双标
改进建议：加强证据评价的完整性，补充事实认定说理
"""


class TestQualityAssessorGrade:

    def test_grade_a(self, mock_llm_caller):
        qa = QualityAssessor(mock_llm_caller)
        grade, desc = qa._determine_grade(95.0)
        assert grade == "A"
        assert desc == "优秀"

    def test_grade_b(self, mock_llm_caller):
        qa = QualityAssessor(mock_llm_caller)
        grade, desc = qa._determine_grade(80.0)
        assert grade == "B"

    def test_grade_c(self, mock_llm_caller):
        qa = QualityAssessor(mock_llm_caller)
        grade, desc = qa._determine_grade(65.0)
        assert grade == "C"

    def test_grade_d(self, mock_llm_caller):
        qa = QualityAssessor(mock_llm_caller)
        grade, desc = qa._determine_grade(50.0)
        assert grade == "D"

    def test_grade_f(self, mock_llm_caller):
        qa = QualityAssessor(mock_llm_caller)
        grade, desc = qa._determine_grade(20.0)
        assert grade == "F"

    def test_grade_boundary_90(self, mock_llm_caller):
        qa = QualityAssessor(mock_llm_caller)
        grade, desc = qa._determine_grade(90.0)
        assert grade == "A"

    def test_grade_boundary_89(self, mock_llm_caller):
        qa = QualityAssessor(mock_llm_caller)
        grade, desc = qa._determine_grade(89.0)
        assert grade == "B"


class TestQualityAssessorParse:

    def test_parse_full_output(self, mock_llm_caller):
        qa = QualityAssessor(mock_llm_caller)
        result = qa._parse_llm_output(MOCK_QUALITY_OUTPUT)

        assert isinstance(result, QualityAssessmentResult)
        assert len(result.dimension_scores) == 7
        assert result.total_score > 0
        assert result.grade in ("A", "B", "C", "D", "F")

    def test_parse_dimension_scores(self, mock_llm_caller):
        qa = QualityAssessor(mock_llm_caller)
        result = qa._parse_llm_output(MOCK_QUALITY_OUTPUT)

        dim_map = {ds.dimension: ds for ds in result.dimension_scores}
        assert dim_map["procedural_compliance"].score == 15
        assert dim_map["fact_finding_quality"].score == 10
        assert dim_map["evidence_admission_norm"].score == 8
        assert dim_map["law_application_accuracy"].score == 12
        assert dim_map["reasoning_sufficiency"].score == 8
        assert dim_map["document_normativity"].score == 7
        assert dim_map["rights_protection"].score == 3

    def test_parse_weighted_scores(self, mock_llm_caller):
        qa = QualityAssessor(mock_llm_caller)
        result = qa._parse_llm_output(MOCK_QUALITY_OUTPUT)

        for ds in result.dimension_scores:
            expected_weighted = ds.score * ds.weight
            assert abs(ds.weighted_score - expected_weighted) < 0.01

    def test_parse_total_score(self, mock_llm_caller):
        qa = QualityAssessor(mock_llm_caller)
        result = qa._parse_llm_output(MOCK_QUALITY_OUTPUT)

        expected_total = sum(ds.score * ds.weight for ds in result.dimension_scores)
        assert abs(result.total_score - round(expected_total, 1)) < 0.2

    def test_parse_strengths_weaknesses(self, mock_llm_caller):
        qa = QualityAssessor(mock_llm_caller)
        result = qa._parse_llm_output(MOCK_QUALITY_OUTPUT)

        assert len(result.strengths) > 0
        assert len(result.weaknesses) > 0
        assert len(result.improvement_suggestions) > 0

    def test_parse_empty_output(self, mock_llm_caller):
        qa = QualityAssessor(mock_llm_caller)
        result = qa._parse_llm_output("")

        assert isinstance(result, QualityAssessmentResult)
        assert len(result.dimension_scores) == 7
        for ds in result.dimension_scores:
            assert ds.score == ds.full_score

    def test_parse_partial_output(self, mock_llm_caller):
        qa = QualityAssessor(mock_llm_caller)
        partial = "程序合规性：18/20\n事实认定质量：15/20\n"
        result = qa._parse_llm_output(partial)

        dim_map = {ds.dimension: ds for ds in result.dimension_scores}
        assert dim_map["procedural_compliance"].score == 18
        assert dim_map["fact_finding_quality"].score == 15
        assert dim_map["evidence_admission_norm"].score == dim_map["evidence_admission_norm"].full_score


class TestQualityAssessorAssess:

    @pytest.mark.asyncio
    async def test_assess_with_mock(self, mock_llm_caller):
        mock_llm_caller.acall = AsyncMock(return_value=(MOCK_QUALITY_OUTPUT, {"total_tokens": 500}))
        qa = QualityAssessor(mock_llm_caller)
        result = await qa.assess("测试材料")

        assert isinstance(result, QualityAssessmentResult)
        assert result.total_score > 0
        assert result.grade in ("A", "B", "C", "D", "F")
        assert result.raw_llm_output == MOCK_QUALITY_OUTPUT


class TestQualityWeights:

    def test_weights_sum_to_one(self):
        total = sum(QUALITY_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01

    def test_full_scores_sum_to_100(self):
        total = sum(QUALITY_FULL_SCORES.values())
        assert total == 100

    def test_dimensions_match_weights(self):
        assert set(QUALITY_DIMENSIONS) == set(QUALITY_WEIGHTS.keys())

    def test_dimensions_match_full_scores(self):
        assert set(QUALITY_DIMENSIONS) == set(QUALITY_FULL_SCORES.keys())
