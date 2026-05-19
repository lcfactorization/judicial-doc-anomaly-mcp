"""Tests for the detection engine"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from judicial_lint_mcp.config import AppConfig, DetectionConfig, LLMConfig
from judicial_lint_mcp.detector import DetectionEngine, DetectionResult, FileLoader
from judicial_lint_mcp.response_parser import ResponseParser


@pytest.fixture
def sample_case_dir(tmp_path):
    """Create a temporary sample case directory"""
    case_dir = tmp_path / "sample_case"
    case_dir.mkdir()

    # Create sample judgment
    judgment = """
# 民事判决书

（2025）某9999民初9999号

原告：张某，男，1980年1月1日生，汉族，住某市某区。
被告：某科技有限公司，住所地某市某区。

## 诉讼请求
原告请求被告支付二倍工资差额50000元。

## 经审理查明
2024年3月1日，原告入职被告公司，双方未签订书面劳动合同。

## 本院认为
关于二倍工资，原告主张被告未与其签订书面劳动合同，要求被告支付二倍工资差额。
本院认为，原告提供的微信聊天记录不足以证明双方存在劳动关系。

## 判决结果
一、驳回原告张某的诉讼请求。
"""
    (case_dir / "判决书.md").write_text(judgment, encoding="utf-8")

    # Create sample evidence list
    evidence = """
# 证据清单

证据1：劳动合同原件（原告提交）
证据2：工资银行流水（原告提交）
证据3：工作证（原告提交）
证据4：微信聊天记录（被告提交）
"""
    (case_dir / "证据清单.md").write_text(evidence, encoding="utf-8")

    return case_dir


@pytest.fixture
def mock_config():
    """Create a mock configuration"""
    return AppConfig(
        llm=LLMConfig(
            provider="openai",
            api_key="test-key",
            model="gpt-4",
        ),
        detection=DetectionConfig(
            dimensions=["procedure", "evidence"],
            enable_adversarial_check=False,
            step_confirmation=False,
        ),
    )


class TestFileLoader:
    """Test file loading and validation"""

    def test_load_markdown_files(self, sample_case_dir):
        loader = FileLoader(str(sample_case_dir))
        files = loader.load()

        assert "判决书" in files
        assert "证据清单" in files
        assert "民事判决书" in files["判决书"]

    def test_validate_completeness(self, sample_case_dir):
        loader = FileLoader(str(sample_case_dir))
        loader.load()
        score, missing = loader.validate()

        assert score > 0
        assert isinstance(missing, list)

    def test_get_materials_text(self, sample_case_dir):
        loader = FileLoader(str(sample_case_dir))
        loader.load()
        text = loader.get_materials_text()

        assert len(text) > 0
        assert "# 判决书" in text


class TestDetectionEngine:
    """Test detection engine"""

    @pytest.mark.asyncio
    async def test_run_detection_mocked(self, sample_case_dir, mock_config):
        """Test detection with mocked LLM calls"""
        with patch("judicial_lint_mcp.detector.LLMCaller") as MockCaller:
            mock_instance = MagicMock()
            mock_instance.acall = AsyncMock(
                return_value=(
                    "发现以下异常：\n1. 举证责任分配错误\n2. 证据未评价",
                    {"total_tokens": 1000},
                )
            )
            mock_instance.estimate_tokens = MagicMock(return_value=500)
            MockCaller.return_value = mock_instance

            engine = DetectionEngine(mock_config)
            result = await engine.run_detection(str(sample_case_dir))

            assert isinstance(result, DetectionResult)
            assert result.case_name != ""
            assert result.completeness_score > 0

    def test_parse_dimension_result(self, mock_config):
        """Test parsing of dimension results via ResponseParser"""
        parser = ResponseParser()

        response = "\n#### 1. 异常项：举证责任分配错误\n- **具体表现**：法院将本应由用人单位承担的举证责任转由劳动者承担\n- **指向获益方**：被告\n- **异常程度**：高度可能"

        result = parser.parse_dimension_result("evidence", response)

        assert result.dimension == "evidence"
        assert len(result.anomalies) > 0


class TestConfig:
    """Test configuration loading"""

    def test_default_config(self):
        config = AppConfig()
        assert config.llm.provider == "openai"
        assert config.llm.temperature == 0.1

    def test_config_from_file(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
llm:
  provider: deepseek
  model: deepseek-chat
  temperature: 0.2
""",
            encoding="utf-8",
        )

        config = AppConfig.from_file(str(config_file))
        assert config.llm.provider == "deepseek"
        assert config.llm.model == "deepseek-chat"
        assert config.llm.temperature == 0.2
