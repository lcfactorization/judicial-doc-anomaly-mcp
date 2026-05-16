"""Judicial Document Anomaly Detection MCP Server"""

__version__ = "0.2.0"

from .benchmark import (
    BENCHMARKS,
    BenchmarkCase,
    get_benchmark,
    get_benchmarks_by_category,
)
from .taxonomy import (
    NEUTRALITY_PROMPT_ADDON,
    TAXONOMY,
    AnomalyCategory,
    category_from_f_code,
    dimension_to_categories,
    get_category,
)
