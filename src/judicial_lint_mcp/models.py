"""Data models for judicial document anomaly detection.

Extracted from detector.py in v0.3.0 to break circular imports.
"""

from pydantic import BaseModel


class AnomalyItem(BaseModel):
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
    dimension: str
    anomalies: list[AnomalyItem] = []
    summary: str = ""
    risk_level: str = "low"


class DetectionResult(BaseModel):
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
