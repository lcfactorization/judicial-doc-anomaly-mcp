"""Configuration management for judicial-lint-mcp"""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv


class LLMConfig(BaseModel):
    """LLM API configuration"""
    provider: str = Field(default="openai", description="LLM provider: openai, deepseek, qwen, etc.")
    api_key: str = Field(default="", description="API key")
    api_base: Optional[str] = Field(default=None, description="API base URL")
    model: str = Field(default="gpt-4", description="Model name")
    temperature: float = Field(default=0.1, description="Temperature for LLM calls")
    max_tokens: int = Field(default=8000, description="Max tokens per call")
    timeout: int = Field(default=120, description="Request timeout in seconds")


class DetectionConfig(BaseModel):
    """Detection workflow configuration"""
    dimensions: list[str] = Field(
        default=[
            "procedure",
            "evidence",
            "fact_finding",
            "law_application",
            "discretion",
            "logic",
            "temporal",
            "semantic_drift",
            "negative_space",
            "case_deviation",
            "procedure_graph",
            "coupling",
        ],
        description="Detection dimensions to run",
    )
    enable_adversarial_check: bool = Field(default=True, description="Enable devil's advocate validation")
    enable_web_search: bool = Field(default=False, description="Enable web search for legal research")
    max_context_tokens: int = Field(default=100000, description="Max context window size")
    step_confirmation: bool = Field(default=True, description="Require yes/no confirmation after each step")


class AppConfig(BaseModel):
    """Application configuration"""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    cache_dir: str = Field(default=".judicial_lint_cache", description="Cache directory")
    output_dir: str = Field(default="./output", description="Output directory")
    verbose: bool = Field(default=False, description="Verbose logging")

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load configuration from environment variables"""
        load_dotenv()
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
                dimensions=os.getenv("DETECTION_DIMENSIONS", "").split(",") if os.getenv("DETECTION_DIMENSIONS") else [],
                enable_adversarial_check=os.getenv("ENABLE_ADVERSARIAL_CHECK", "true").lower() == "true",
                enable_web_search=os.getenv("ENABLE_WEB_SEARCH", "false").lower() == "true",
            ),
            cache_dir=os.getenv("CACHE_DIR", ".judicial_lint_cache"),
            output_dir=os.getenv("OUTPUT_DIR", "./output"),
            verbose=os.getenv("VERBOSE", "false").lower() == "true",
        )

    @classmethod
    def from_file(cls, path: str) -> "AppConfig":
        """Load configuration from YAML file"""
        import yaml
        config_path = Path(path)
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return cls(**data)
        return cls()
