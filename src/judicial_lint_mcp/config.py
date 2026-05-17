"""Configuration management for judicial-lint-mcp v0.5.0"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

ALL_DIMENSIONS = [
    "procedure",
    "evidence",
    "fact_finding",
    "focus_drift",
    "law_application",
    "discretion",
    "rhetoric_trick",
    "logic",
    "temporal",
    "trial_process",
    "external_interference",
    "execution",
    "negative_space",
    "semantic_drift",
    "case_deviation",
    "coupling",
]

QUALITY_DIMENSIONS = [
    "procedural_compliance",
    "fact_finding_quality",
    "evidence_admission_norm",
    "law_application_accuracy",
    "reasoning_sufficiency",
    "document_normativity",
    "rights_protection",
]

QUALITY_WEIGHTS = {
    "procedural_compliance": 0.20,
    "fact_finding_quality": 0.20,
    "evidence_admission_norm": 0.15,
    "law_application_accuracy": 0.15,
    "reasoning_sufficiency": 0.15,
    "document_normativity": 0.10,
    "rights_protection": 0.05,
}

QUALITY_FULL_SCORES = {
    "procedural_compliance": 20,
    "fact_finding_quality": 20,
    "evidence_admission_norm": 15,
    "law_application_accuracy": 15,
    "reasoning_sufficiency": 15,
    "document_normativity": 10,
    "rights_protection": 5,
}

QUALITY_GRADES = {
    "A": (90, 100, "优秀"),
    "B": (75, 89, "良好"),
    "C": (60, 74, "合格"),
    "D": (40, 59, "不合格"),
    "F": (0, 39, "严重缺陷"),
}

ANOMALY_SEVERITY_LEVELS = ["疑似", "可能", "高度可能", "确定"]

ADVERSARIAL_ROLES = [
    "plaintiff_agent",
    "defendant_agent",
    "appellate_judge",
    "legal_scholar",
    "public_supervisor",
]

COUPLING_THRESHOLDS = {
    "low": 2,
    "medium": 3,
    "high": 5,
    "structural": 7,
}

DEVIATION_THRESHOLDS = {
    "normal": 0.5,
    "mild": 1.0,
    "moderate": 2.0,
    "severe": float("inf"),
}

MATERIAL_PRIORITY = {
    "required": ["核心文书全文"],
    "strongly_recommended": [
        "起诉状/答辩状/上诉状/申请书/投诉书",
        "双方证据清单及证据内容摘要/全文",
        "多阶段程序文书",
    ],
    "recommended": [
        "庭审/听证/调查笔录",
        "程序性裁定/通知/决定",
        "时间线材料",
        "案件背景与外部信息说明",
    ],
}


class LLMConfig(BaseModel):
    provider: str = Field(
        default="openai", description="LLM provider: openai, deepseek, qwen, etc."
    )
    api_key: str = Field(default="", description="API key")
    api_base: str | None = Field(default=None, description="API base URL")
    model: str = Field(default="gpt-4", description="Model name")
    temperature: float = Field(default=0.1, description="Temperature for LLM calls")
    max_tokens: int = Field(default=8000, description="Max tokens per call")
    timeout: int = Field(default=120, description="Request timeout in seconds")


class DetectionConfig(BaseModel):
    dimensions: list[str] = Field(
        default=ALL_DIMENSIONS,
        description="16 detection dimensions to run",
    )
    enable_adversarial_check: bool = Field(
        default=True, description="Enable devil's advocate validation"
    )
    enable_web_search: bool = Field(
        default=False, description="Enable web search for legal research"
    )
    enable_graph_building: bool = Field(
        default=True, description="Enable graph structure modeling"
    )
    enable_quality_assessment: bool = Field(
        default=True, description="Enable 7-dimension quality assessment"
    )
    enable_quick_check: bool = Field(
        default=True, description="Enable 26-item quick check table"
    )
    max_context_tokens: int = Field(
        default=100000, description="Max context window size"
    )
    step_confirmation: bool = Field(
        default=True, description="Require yes/no confirmation after each step"
    )
    anomaly_severity_levels: list[str] = Field(
        default=ANOMALY_SEVERITY_LEVELS,
        description="Anomaly severity levels: 疑似/可能/高度可能/确定",
    )


class QualityConfig(BaseModel):
    dimensions: list[str] = Field(
        default=QUALITY_DIMENSIONS,
        description="7 quality assessment dimensions",
    )
    weights: dict[str, float] = Field(
        default=QUALITY_WEIGHTS,
        description="Weight for each quality dimension",
    )
    full_scores: dict[str, int] = Field(
        default=QUALITY_FULL_SCORES,
        description="Full score for each quality dimension",
    )
    grades: dict[str, tuple] = Field(
        default=QUALITY_GRADES,
        description="Grade thresholds: A/B/C/D/F",
    )


class AdversarialConfig(BaseModel):
    roles: list[str] = Field(
        default=ADVERSARIAL_ROLES,
        description="Adversarial review roles",
    )
    enable_devils_advocate: bool = Field(
        default=True, description="Enable Devil's Advocate Q1/Q2/Q3"
    )
    enable_multi_role: bool = Field(
        default=True, description="Enable 5-role adversarial review"
    )
    enable_cross_examination: bool = Field(
        default=True, description="Enable cross-examination between roles"
    )


class GraphConfig(BaseModel):
    enable_evidence_graph: bool = Field(
        default=True, description="Build Evidence Graph"
    )
    enable_procedure_graph: bool = Field(
        default=True, description="Build Procedure Graph"
    )
    enable_reasoning_graph: bool = Field(
        default=True, description="Build Legal Reasoning Graph"
    )
    output_mermaid: bool = Field(
        default=True, description="Output Mermaid diagram format"
    )


class AppConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    quality: QualityConfig = Field(default_factory=QualityConfig)
    adversarial: AdversarialConfig = Field(default_factory=AdversarialConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    cache_dir: str = Field(
        default=".judicial_lint_cache", description="Cache directory"
    )
    output_dir: str = Field(default="./output", description="Output directory")
    verbose: bool = Field(default=False, description="Verbose logging")

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv()
        dimensions_str = os.getenv("DETECTION_DIMENSIONS", "")
        dimensions = dimensions_str.split(",") if dimensions_str else ALL_DIMENSIONS
        return cls(
            llm=LLMConfig(
                provider=os.getenv("LLM_PROVIDER", "openai"),
                api_key=os.getenv("LLM_API_KEY", ""),
                api_base=os.getenv("LLM_API_BASE") or None,
                model=os.getenv("LLM_MODEL", "gpt-4"),
                temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
                max_tokens=int(os.getenv("LLM_MAX_TOKENS", "8000")),
                timeout=int(os.getenv("LLM_TIMEOUT", "120")),
            ),
            detection=DetectionConfig(
                dimensions=dimensions,
                enable_adversarial_check=os.getenv(
                    "ENABLE_ADVERSARIAL_CHECK", "true"
                ).lower()
                == "true",
                enable_web_search=os.getenv("ENABLE_WEB_SEARCH", "false").lower()
                == "true",
                enable_graph_building=os.getenv("ENABLE_GRAPH_BUILDING", "true").lower()
                == "true",
                enable_quality_assessment=os.getenv(
                    "ENABLE_QUALITY_ASSESSMENT", "true"
                ).lower()
                == "true",
                enable_quick_check=os.getenv("ENABLE_QUICK_CHECK", "true").lower()
                == "true",
            ),
            cache_dir=os.getenv("CACHE_DIR", ".judicial_lint_cache"),
            output_dir=os.getenv("OUTPUT_DIR", "./output"),
            verbose=os.getenv("VERBOSE", "false").lower() == "true",
        )

    @classmethod
    def from_file(cls, path: str) -> "AppConfig":
        import yaml

        config_path = Path(path)
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return cls(**data)
        return cls()
