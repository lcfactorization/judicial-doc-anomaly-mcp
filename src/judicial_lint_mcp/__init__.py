"""Judicial Document Anomaly Detection MCP Server"""

__version__ = "0.2.0"

from .taxonomy import TAXONOMY, AnomalyCategory, get_category, category_from_f_code, dimension_to_categories, NEUTRALITY_PROMPT_ADDON
from .benchmark import BENCHMARKS, BenchmarkCase, get_benchmark, get_benchmarks_by_category
