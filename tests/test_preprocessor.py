"""Tests for preprocessor module"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from judicial_lint_mcp.preprocessor import (
    Preprocessor,
    PreprocessResult,
)


@pytest.fixture
def sample_case_dir(tmp_path):
    case_dir = tmp_path / "test_case"
    case_dir.mkdir()

    judgment = """# 民事判决书

（2025）苏0602民初4514号

原告：张某，男，1980年1月15日生。
被告：某科技有限公司。

2024年3月1日，原告入职被告公司。
2024年9月15日，被告通知原告离职。
2024年12月20日，本院作出判决。
"""
    (case_dir / "判决书.md").write_text(judgment, encoding="utf-8")

    evidence = """# 证据清单

证据1：银行流水（原告提交）
证据2：工作证照片（原告提交）
证据3：《项目合作协议》（被告提交）
"""
    (case_dir / "证据清单.md").write_text(evidence, encoding="utf-8")

    complaint = """# 起诉状

原告请求被告支付二倍工资差额75000元。
"""
    (case_dir / "起诉状.md").write_text(complaint, encoding="utf-8")

    return case_dir


@pytest.fixture
def mock_llm_caller():
    caller = MagicMock()
    caller.acall = AsyncMock(
        return_value=(
            json.dumps(
                {
                    "case_info": {
                        "case_number": "（2025）苏0602民初4514号",
                        "case_name": "张某诉某科技有限公司劳动争议案",
                        "parties": ["张某", "某科技有限公司"],
                        "case_type": "劳动争议",
                        "cause_of_action": "二倍工资差额",
                        "judgment_result": "驳回全部诉讼请求",
                        "court": "某市某区人民法院",
                        "judge_date": "2024-12-20",
                    },
                    "evidence_index": [
                        {
                            "evidence_id": "原证1",
                            "evidence_type": "书证",
                            "submitted_by": "原告",
                            "description": "银行流水",
                            "proof_object": "劳动关系存在",
                            "cross_exam_status": "已质证",
                            "admission_status": "采信部分",
                        },
                        {
                            "evidence_id": "被证1",
                            "evidence_type": "书证",
                            "submitted_by": "被告",
                            "description": "项目合作协议",
                            "proof_object": "合作关系",
                            "cross_exam_status": "已质证",
                            "admission_status": "采信",
                        },
                    ],
                    "claims_map": [
                        {
                            "claim_id": "诉请1",
                            "party": "原告",
                            "claim_content": "支付二倍工资差额75000元",
                            "evidence_refs": ["原证1"],
                            "response_status": "驳回",
                        },
                    ],
                    "missing_items": ["庭审笔录", "送达回证"],
                }
            ),
            {"total_tokens": 500},
        )
    )
    return caller


class TestPreprocessorLoadMaterials:

    def test_load_md_files(self, sample_case_dir, mock_llm_caller):
        p = Preprocessor(mock_llm_caller)
        materials = p._load_materials(str(sample_case_dir))
        assert "判决书.md" in materials
        assert "证据清单.md" in materials
        assert "起诉状.md" in materials

    def test_load_empty_dir(self, tmp_path, mock_llm_caller):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        p = Preprocessor(mock_llm_caller)
        materials = p._load_materials(str(empty_dir))
        assert materials == {}

    def test_load_nonexistent_dir(self, mock_llm_caller):
        p = Preprocessor(mock_llm_caller)
        materials = p._load_materials("/nonexistent/path")
        assert materials == {}

    def test_only_loads_md_txt(self, tmp_path, mock_llm_caller):
        case_dir = tmp_path / "mixed"
        case_dir.mkdir()
        (case_dir / "判决书.md").write_text("content", encoding="utf-8")
        (case_dir / "notes.txt").write_text("notes", encoding="utf-8")
        (case_dir / "image.png").write_bytes(b"\x89PNG")
        p = Preprocessor(mock_llm_caller)
        materials = p._load_materials(str(case_dir))
        assert "判决书.md" in materials
        assert "notes.txt" in materials
        assert "image.png" not in materials


class TestPreprocessorCompleteness:

    def test_completeness_score_positive(self, mock_llm_caller):
        p = Preprocessor(mock_llm_caller)
        materials = {"判决书.md": "content", "证据清单.md": "content"}
        score = p._calculate_completeness(materials)
        assert score > 0

    def test_completeness_score_empty(self, mock_llm_caller):
        p = Preprocessor(mock_llm_caller)
        score = p._calculate_completeness({})
        assert score == 0.0

    def test_completeness_score_with_judgment(self, mock_llm_caller):
        p = Preprocessor(mock_llm_caller)
        materials = {"判决书.md": "民事判决书内容包含判决书字样"}
        score = p._calculate_completeness(materials)
        assert score > 0


class TestPreprocessorTimeline:

    def test_extract_timeline_from_text(self, mock_llm_caller):
        p = Preprocessor(mock_llm_caller)
        text = "2024年3月1日，原告入职。2024年9月15日，被告通知离职。"
        timeline = p._extract_timeline(text)
        assert len(timeline) >= 2
        assert timeline[0].date == "2024-03-01"
        assert timeline[1].date == "2024-09-15"

    def test_extract_timeline_no_dates(self, mock_llm_caller):
        p = Preprocessor(mock_llm_caller)
        text = "这是一段没有日期的文字。"
        timeline = p._extract_timeline(text)
        assert len(timeline) == 0

    def test_extract_timeline_various_formats(self, mock_llm_caller):
        p = Preprocessor(mock_llm_caller)
        text = "2024/3/1入职 2024-09-15离职 2025.1.10开庭"
        timeline = p._extract_timeline(text)
        assert len(timeline) >= 3


class TestPreprocessorRun:

    @pytest.mark.asyncio
    async def test_run_with_mock_llm(self, sample_case_dir, mock_llm_caller):
        p = Preprocessor(mock_llm_caller)
        result = await p.run(str(sample_case_dir))

        assert isinstance(result, PreprocessResult)
        assert result.completeness_score > 0
        assert len(result.timeline) > 0
        assert result.case_info.case_number == "（2025）苏0602民初4514号"
        assert len(result.evidence_index) == 2
        assert len(result.claims_map) == 1
        assert "庭审笔录" in result.missing_items

    @pytest.mark.asyncio
    async def test_run_empty_dir(self, tmp_path, mock_llm_caller):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        p = Preprocessor(mock_llm_caller)
        result = await p.run(str(empty_dir))
        assert "未找到任何案件材料" in result.missing_items

    @pytest.mark.asyncio
    async def test_run_llm_parse_failure(self, sample_case_dir):
        caller = MagicMock()
        caller.acall = AsyncMock(
            return_value=("This is not JSON", {"total_tokens": 100})
        )
        p = Preprocessor(caller)
        result = await p.run(str(sample_case_dir))
        assert isinstance(result, PreprocessResult)
        assert result.case_info.case_number == ""
