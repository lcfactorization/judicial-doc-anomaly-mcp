"""Phase 2: Graph structure modeling for judicial documents

Builds Evidence Graph, Procedure Graph, and Legal Reasoning Graph
using networkx for graph computation and Mermaid for visualization.
"""

import re
from dataclasses import dataclass, field

import networkx as nx

from .config import GraphConfig
from .llm_caller import LLMCaller
from .preprocessor import PreprocessResult
from .prompts import GRAPH_BUILDING_PROMPT


@dataclass
class GraphNode:
    node_id: str
    node_type: str
    label: str
    attributes: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    source: str
    target: str
    edge_type: str
    label: str = ""
    attributes: dict = field(default_factory=dict)


@dataclass
class AnomalyPath:
    pattern: str
    description: str
    meaning: str
    involved_nodes: list[str] = field(default_factory=list)


@dataclass
class GraphBuildResult:
    evidence_graph: nx.DiGraph | None = None
    procedure_graph: nx.DiGraph | None = None
    reasoning_graph: nx.DiGraph | None = None
    evidence_mermaid: str = ""
    procedure_mermaid: str = ""
    reasoning_mermaid: str = ""
    anomaly_paths: list[AnomalyPath] = field(default_factory=list)
    raw_llm_output: str = ""


class GraphBuilder:
    def __init__(self, llm_caller: LLMCaller, config: GraphConfig):
        self.llm_caller = llm_caller
        self.config = config

    def _nx_to_mermaid(self, graph: nx.DiGraph, title: str = "") -> str:
        if not graph.nodes:
            return f'graph TD\n    empty["{title}: 无数据"]\n'
        lines = ["graph TD"]
        node_type_shapes = {
            "START": ("([", "])"),
            "END": ("([", "])"),
            "MOTION": ("{{", "}}"),
            "RULING": ("[", "]"),
            "HEARING": ("([", "])"),
            "EVIDENCE": ("(", ")"),
            "JUDGMENT": ("[[", "]]"),
            "FACT": ("(", ")"),
            "NORM": ("{{", "}}"),
            "CONCLUSION": ("[[", "]]"),
        }
        for node_id, data in graph.nodes(data=True):
            label = data.get("label", node_id)
            ntype = data.get("node_type", "")
            shape = node_type_shapes.get(ntype, ("[", "]"))
            safe_id = re.sub(r"[^a-zA-Z0-9_]", "_", node_id)
            lines.append(f'    {safe_id}{shape[0]}"{label}"{shape[1]}')
        for src, tgt, data in graph.edges(data=True):
            edge_label = data.get("edge_type", "")
            safe_src = re.sub(r"[^a-zA-Z0-9_]", "_", src)
            safe_tgt = re.sub(r"[^a-zA-Z0-9_]", "_", tgt)
            if edge_label:
                lines.append(f'    {safe_src} -->|"{edge_label}"| {safe_tgt}')
            else:
                lines.append(f"    {safe_src} --> {safe_tgt}")
        return "\n".join(lines)

    def _detect_procedure_anomalies(self, graph: nx.DiGraph) -> list[AnomalyPath]:
        anomalies = []
        motions = [
            n for n, d in graph.nodes(data=True) if d.get("node_type") == "MOTION"
        ]
        rulings = [
            n for n, d in graph.nodes(data=True) if d.get("node_type") == "RULING"
        ]
        for motion in motions:
            has_ruling = any(
                graph.has_edge(motion, r) or graph.has_edge(r, motion) for r in rulings
            )
            motion_data = graph.nodes[motion]
            if not has_ruling:
                anomalies.append(
                    AnomalyPath(
                        pattern="选择性阻断",
                        description=f"程序性申请'{motion_data.get('label', motion)}'缺少对应裁定节点",
                        meaning="程序权利不对等",
                        involved_nodes=[motion],
                    )
                )
        starts = [n for n, d in graph.nodes(data=True) if d.get("node_type") == "START"]
        judgments = [
            n for n, d in graph.nodes(data=True) if d.get("node_type") == "JUDGMENT"
        ]
        hearings = [
            n for n, d in graph.nodes(data=True) if d.get("node_type") == "HEARING"
        ]
        if starts and judgments and not hearings:
            anomalies.append(
                AnomalyPath(
                    pattern="跳跃裁判",
                    description="从立案直接到裁判，缺少庭审节点",
                    meaning="程序严重简化，可能剥夺辩论权",
                    involved_nodes=starts + judgments,
                )
            )
        return anomalies

    def _build_evidence_graph_from_data(self, evidence_index: list) -> nx.DiGraph:
        G = nx.DiGraph()
        for ev in evidence_index:
            G.add_node(
                ev.evidence_id,
                node_type="EVIDENCE",
                label=f"{ev.evidence_id}: {ev.description[:30]}",
                evidence_type=ev.evidence_type,
                submitted_by=ev.submitted_by,
            )
        return G

    def _build_procedure_graph_from_data(self, timeline: list) -> nx.DiGraph:
        G = nx.DiGraph()
        G.add_node("START", node_type="START", label="立案受理")
        G.add_node("END", node_type="END", label="程序终结")
        prev_node = "START"
        for i, entry in enumerate(timeline):
            node_id = f"event_{i:03d}"
            G.add_node(
                node_id,
                node_type="HEARING",
                label=f"{entry.date}: {entry.event[:40]}",
            )
            G.add_edge(prev_node, node_id, edge_type="NEXT")
            prev_node = node_id
        G.add_edge(prev_node, "END", edge_type="NEXT")
        return G

    async def run(self, preprocess_result: PreprocessResult) -> GraphBuildResult:
        result = GraphBuildResult()

        if self.config.enable_evidence_graph:
            result.evidence_graph = self._build_evidence_graph_from_data(
                preprocess_result.evidence_index
            )
            result.evidence_mermaid = self._nx_to_mermaid(
                result.evidence_graph, "证据关系图"
            )

        if self.config.enable_procedure_graph:
            result.procedure_graph = self._build_procedure_graph_from_data(
                preprocess_result.timeline
            )
            result.procedure_mermaid = self._nx_to_mermaid(
                result.procedure_graph, "程序行为图"
            )
            result.anomaly_paths = self._detect_procedure_anomalies(
                result.procedure_graph
            )

        if self.config.enable_reasoning_graph:
            result.reasoning_graph = nx.DiGraph()
            result.reasoning_graph.add_node(
                "evidence", node_type="EVIDENCE", label="证据"
            )
            result.reasoning_graph.add_node("fact", node_type="FACT", label="事实认定")
            result.reasoning_graph.add_node("norm", node_type="NORM", label="法律规范")
            result.reasoning_graph.add_node(
                "conclusion", node_type="CONCLUSION", label="裁判结论"
            )
            result.reasoning_graph.add_edge("evidence", "fact", edge_type="支撑")
            result.reasoning_graph.add_edge("fact", "norm", edge_type="适用")
            result.reasoning_graph.add_edge("norm", "conclusion", edge_type="推导")
            result.reasoning_mermaid = self._nx_to_mermaid(
                result.reasoning_graph, "法律推理图"
            )

        prompt = GRAPH_BUILDING_PROMPT.format(
            preprocessed_data=preprocess_result.materials_text[:8000]
        )
        result.raw_llm_output, _ = await self.llm_caller.acall(
            "你是司法案件图结构建模专家，请构建证据关系图、程序行为图和法律推理图。",
            prompt,
        )

        return result
