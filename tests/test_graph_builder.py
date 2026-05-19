"""Tests for graph_builder module"""

from unittest.mock import AsyncMock, MagicMock

import networkx as nx
import pytest

from judicial_lint_mcp.config import GraphConfig
from judicial_lint_mcp.graph_builder import (
    GraphBuilder,
    GraphBuildResult,
)
from judicial_lint_mcp.preprocessor import (
    CaseInfo,
    EvidenceEntry,
    PreprocessResult,
    TimelineEntry,
)


@pytest.fixture
def graph_config():
    return GraphConfig(
        enable_evidence_graph=True,
        enable_procedure_graph=True,
        enable_reasoning_graph=True,
        output_mermaid=True,
    )


@pytest.fixture
def mock_llm_caller():
    caller = MagicMock()
    caller.acall = AsyncMock(
        return_value=("Graph building complete", {"total_tokens": 200})
    )
    return caller


@pytest.fixture
def sample_preprocess_result():
    return PreprocessResult(
        case_info=CaseInfo(
            case_number="（2025）某9999民初9999号",
            case_name="张某诉某科技有限公司",
        ),
        completeness_score=75.0,
        timeline=[
            TimelineEntry(date="2024-03-01", event="原告入职被告公司", source="文书"),
            TimelineEntry(date="2024-09-15", event="被告通知原告离职", source="文书"),
            TimelineEntry(date="2024-12-20", event="本院作出判决", source="文书"),
        ],
        evidence_index=[
            EvidenceEntry(
                evidence_id="原证1",
                evidence_type="书证",
                submitted_by="原告",
                description="银行流水",
            ),
            EvidenceEntry(
                evidence_id="被证1",
                evidence_type="书证",
                submitted_by="被告",
                description="项目合作协议",
            ),
        ],
        materials_text="测试材料内容",
    )


class TestGraphBuilderMermaid:

    def test_empty_graph_to_mermaid(self, mock_llm_caller, graph_config):
        gb = GraphBuilder(mock_llm_caller, graph_config)
        G = nx.DiGraph()
        mermaid = gb._nx_to_mermaid(G, "空图")
        assert "空图" in mermaid
        assert "graph TD" in mermaid

    def test_simple_graph_to_mermaid(self, mock_llm_caller, graph_config):
        gb = GraphBuilder(mock_llm_caller, graph_config)
        G = nx.DiGraph()
        G.add_node("A", node_type="START", label="立案")
        G.add_node("B", node_type="HEARING", label="庭审")
        G.add_edge("A", "B", edge_type="NEXT")
        mermaid = gb._nx_to_mermaid(G, "测试图")
        assert "graph TD" in mermaid
        assert "立案" in mermaid
        assert "庭审" in mermaid
        assert "NEXT" in mermaid

    def test_node_type_shapes(self, mock_llm_caller, graph_config):
        gb = GraphBuilder(mock_llm_caller, graph_config)
        G = nx.DiGraph()
        G.add_node("motion", node_type="MOTION", label="申请")
        G.add_node("ruling", node_type="RULING", label="裁定")
        G.add_node("judgment", node_type="JUDGMENT", label="判决")
        mermaid = gb._nx_to_mermaid(G)
        assert "申请" in mermaid
        assert "裁定" in mermaid
        assert "判决" in mermaid


class TestGraphBuilderProcedureAnomalies:

    def test_detect_selective_blocking(self, mock_llm_caller, graph_config):
        gb = GraphBuilder(mock_llm_caller, graph_config)
        G = nx.DiGraph()
        G.add_node("START", node_type="START", label="立案")
        G.add_node("motion1", node_type="MOTION", label="管辖权异议申请")
        G.add_node("hearing1", node_type="HEARING", label="庭审")
        G.add_node("END", node_type="END", label="终结")
        G.add_edge("START", "motion1", edge_type="NEXT")
        G.add_edge("START", "hearing1", edge_type="NEXT")
        G.add_edge("hearing1", "END", edge_type="NEXT")

        anomalies = gb._detect_procedure_anomalies(G)
        assert len(anomalies) >= 1
        assert any(a.pattern == "选择性阻断" for a in anomalies)

    def test_detect_jump_judgment(self, mock_llm_caller, graph_config):
        gb = GraphBuilder(mock_llm_caller, graph_config)
        G = nx.DiGraph()
        G.add_node("START", node_type="START", label="立案")
        G.add_node("judgment1", node_type="JUDGMENT", label="判决")
        G.add_edge("START", "judgment1", edge_type="NEXT")

        anomalies = gb._detect_procedure_anomalies(G)
        assert len(anomalies) >= 1
        assert any(a.pattern == "跳跃裁判" for a in anomalies)

    def test_no_anomalies_normal_flow(self, mock_llm_caller, graph_config):
        gb = GraphBuilder(mock_llm_caller, graph_config)
        G = nx.DiGraph()
        G.add_node("START", node_type="START", label="立案")
        G.add_node("hearing1", node_type="HEARING", label="庭审")
        G.add_node("END", node_type="END", label="终结")
        G.add_edge("START", "hearing1", edge_type="NEXT")
        G.add_edge("hearing1", "END", edge_type="NEXT")

        anomalies = gb._detect_procedure_anomalies(G)
        assert len(anomalies) == 0


class TestGraphBuilderEvidenceGraph:

    def test_build_evidence_graph(
        self, mock_llm_caller, graph_config, sample_preprocess_result
    ):
        gb = GraphBuilder(mock_llm_caller, graph_config)
        G = gb._build_evidence_graph_from_data(sample_preprocess_result.evidence_index)
        assert len(G.nodes) == 2
        assert "原证1" in G.nodes
        assert "被证1" in G.nodes
        assert G.nodes["原证1"]["node_type"] == "EVIDENCE"

    def test_build_evidence_graph_empty(self, mock_llm_caller, graph_config):
        gb = GraphBuilder(mock_llm_caller, graph_config)
        G = gb._build_evidence_graph_from_data([])
        assert len(G.nodes) == 0


class TestGraphBuilderProcedureGraph:

    def test_build_procedure_graph(
        self, mock_llm_caller, graph_config, sample_preprocess_result
    ):
        gb = GraphBuilder(mock_llm_caller, graph_config)
        G = gb._build_procedure_graph_from_data(sample_preprocess_result.timeline)
        assert "START" in G.nodes
        assert "END" in G.nodes
        assert G.nodes["START"]["node_type"] == "START"
        assert G.nodes["END"]["node_type"] == "END"
        assert len(G.nodes) == 5  # START + 3 events + END

    def test_build_procedure_graph_empty_timeline(self, mock_llm_caller, graph_config):
        gb = GraphBuilder(mock_llm_caller, graph_config)
        G = gb._build_procedure_graph_from_data([])
        assert "START" in G.nodes
        assert "END" in G.nodes
        assert G.has_edge("START", "END")


class TestGraphBuilderRun:

    @pytest.mark.asyncio
    async def test_run_all_graphs(
        self, mock_llm_caller, graph_config, sample_preprocess_result
    ):
        gb = GraphBuilder(mock_llm_caller, graph_config)
        result = await gb.run(sample_preprocess_result)

        assert isinstance(result, GraphBuildResult)
        assert result.evidence_graph is not None
        assert result.procedure_graph is not None
        assert result.reasoning_graph is not None
        assert result.evidence_mermaid != ""
        assert result.procedure_mermaid != ""
        assert result.reasoning_mermaid != ""

    @pytest.mark.asyncio
    async def test_run_disabled_graphs(self, mock_llm_caller, sample_preprocess_result):
        config = GraphConfig(
            enable_evidence_graph=False,
            enable_procedure_graph=False,
            enable_reasoning_graph=False,
        )
        gb = GraphBuilder(mock_llm_caller, config)
        result = await gb.run(sample_preprocess_result)

        assert result.evidence_graph is None
        assert result.procedure_graph is None
        assert result.reasoning_graph is None
