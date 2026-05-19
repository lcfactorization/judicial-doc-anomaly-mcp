# Graph Report - judicial-doc-anomaly-mcp  (2026-05-19)

## Corpus Check
- 34 files · ~63,526 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 493 nodes · 1311 edges · 16 communities detected
- Extraction: 47% EXTRACTED · 53% INFERRED · 0% AMBIGUOUS · INFERRED: 698 edges (avg confidence: 0.59)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]

## God Nodes (most connected - your core abstractions)
1. `ResponseParser` - 75 edges
2. `PipelineStateManager` - 68 edges
3. `ErrorCode` - 47 edges
4. `LLMCaller` - 43 edges
5. `DetectionEngine` - 40 edges
6. `GraphBuilder` - 37 edges
7. `QualityAssessor` - 35 edges
8. `ReportBuilder` - 33 edges
9. `FileLoader` - 31 edges
10. `DimensionResult` - 31 edges

## Surprising Connections (you probably didn't know these)
- `LLM caller with multi-model support and long context management` --uses--> `LLMConfig`  [INFERRED]
  src\judicial_lint_mcp\llm_caller.py → src\judicial_lint_mcp\config.py
- `Handles LLM API calls with retry, caching, and context management` --uses--> `LLMConfig`  [INFERRED]
  src\judicial_lint_mcp\llm_caller.py → src\judicial_lint_mcp\config.py
- `Async version of call` --uses--> `LLMConfig`  [INFERRED]
  src\judicial_lint_mcp\llm_caller.py → src\judicial_lint_mcp\config.py
- `Phase 4.5: Quality assessment engine for judicial documents  Implements 7-dimens` --uses--> `LLMCaller`  [INFERRED]
  src\judicial_lint_mcp\quality_assessor.py → src\judicial_lint_mcp\llm_caller.py
- `main()` --calls--> `DetectionEngine`  [INFERRED]
  full_test.py → src\judicial_lint_mcp\detector.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.04
Nodes (47): Enum, test_compact_materials_with_anonymize(), test_pipeline_state_flow(), test_token_estimation_accuracy(), make_error(), Structured error codes for judicial-lint-mcp v0.5.1.  Provides consistent error, Pipeline state manager with persistence and TTL-based cleanup.  v0.5.1: Replaces, _build_system_prompt() (+39 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (46): Mock end-to-end test for v0.5.1 bridge architecture.  Tests the full pipeline: p, test_full_pipeline_mock(), Check MCP Server Skill loading and run end-to-end test., Core detection engine for judicial document anomaly detection v0.5.1  Refactored, Load and validate case materials from directory, Main detection engine that orchestrates the full workflow, ErrorCode, Judicial Document Anomaly Detection MCP Server (+38 more)

### Community 2 - "Community 2"
Cohesion: 0.08
Nodes (31): GraphConfig, AnomalyPath, GraphBuilder, GraphBuildResult, GraphEdge, GraphNode, Phase 2: Graph structure modeling for judicial documents  Builds Evidence Graph,, client() (+23 more)

### Community 3 - "Community 3"
Cohesion: 0.1
Nodes (26): BaseModel, main(), Full test: run all dimensions on real 4514 case., main(), Quick test: run only evidence dimension to verify beneficiary fix., AppConfig, DetectionConfig, from_env() (+18 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (20): _format_adversarial_result(), _format_graph_result(), _format_preprocess_result(), _format_quality_result(), main(), MockLLMCaller, Local end-to-end runner for judicial-lint-mcp v0.5.0  Simulates a detect_anomali, run_e2e() (+12 more)

### Community 5 - "Community 5"
Cohesion: 0.09
Nodes (5): PipelineStateManager, TestParseResponseEdgeCases, TestPipelineStateEdgeCases, TestPipelineStateManager, TestResponseParserIntegration

### Community 6 - "Community 6"
Cohesion: 0.13
Nodes (19): AdversarialResult, AdversarialReviewer, CrossExaminationResult, DevilsAdvocateResult, Phase 5: Multi-role adversarial review engine  Implements Devil's Advocate Q1/Q2, RoleReviewResult, AdversarialConfig, adversarial_config() (+11 more)

### Community 7 - "Community 7"
Cohesion: 0.1
Nodes (10): DimensionScore, QualityAssessmentResult, QualityAssessor, Phase 4.5: Quality assessment engine for judicial documents  Implements 7-dimens, Tests for quality_assessor module, test_assess_with_mock(), TestQualityAssessorAssess, TestQualityAssessorGrade (+2 more)

### Community 8 - "Community 8"
Cohesion: 0.18
Nodes (16): _call_tool(), cli(), _get_tool_function(), list_skills_cmd(), main(), parse(), pipeline(), CLI v0.5.1 — Simple Agent that uses MCP Server bridge tools.  This CLI demonstra (+8 more)

### Community 9 - "Community 9"
Cohesion: 0.31
Nodes (3): _anonymize_text(), TestAnonymization, TestAnonymizationEdgeCases

### Community 10 - "Community 10"
Cohesion: 0.25
Nodes (1): TestJsonWrapperStripping

### Community 11 - "Community 11"
Cohesion: 0.33
Nodes (2): AnomalyCategory, Anomaly taxonomy — A1-A8 unified numbering system.  Bridges the 16-dimension det

### Community 12 - "Community 12"
Cohesion: 0.4
Nodes (2): BenchmarkCase, Benchmark cases — reference cases for calibration.  Three categories:   - clearl

### Community 13 - "Community 13"
Cohesion: 0.67
Nodes (1): Real end-to-end test with DeepSeek API for A1-A8 classification and 16-dimension

### Community 14 - "Community 14"
Cohesion: 1.0
Nodes (1): Quick smoke test for v0.5.0 MCP Server bridge tools.

### Community 15 - "Community 15"
Cohesion: 1.0
Nodes (1): Tests for judicial-lint-mcp

## Knowledge Gaps
- **22 isolated node(s):** `Real end-to-end test with DeepSeek API for A1-A8 classification and 16-dimension`, `Quick smoke test for v0.5.0 MCP Server bridge tools.`, `BenchmarkCase`, `Benchmark cases — reference cases for calibration.  Three categories:   - clearl`, `CLI v0.5.1 — Simple Agent that uses MCP Server bridge tools.  This CLI demonstra` (+17 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 10`** (8 nodes): `TestJsonWrapperStripping`, `.setup_method()`, `.test_invalid_json_in_fence()`, `.test_json_with_result_key()`, `.test_json_without_known_key()`, `.test_no_wrapper_passthrough()`, `.test_strip_json_code_fence()`, `.test_strip_plain_json()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 11`** (6 nodes): `AnomalyCategory`, `category_from_f_code()`, `dimension_to_categories()`, `get_category()`, `Anomaly taxonomy — A1-A8 unified numbering system.  Bridges the 16-dimension det`, `taxonomy.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 12`** (5 nodes): `BenchmarkCase`, `get_benchmark()`, `get_benchmarks_by_category()`, `Benchmark cases — reference cases for calibration.  Three categories:   - clearl`, `benchmark.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 13`** (3 nodes): `main()`, `Real end-to-end test with DeepSeek API for A1-A8 classification and 16-dimension`, `test_e2e_real.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 14`** (2 nodes): `Quick smoke test for v0.5.0 MCP Server bridge tools.`, `test_v040.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 15`** (2 nodes): `__init__.py`, `Tests for judicial-lint-mcp`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ResponseParser` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`, `Community 5`, `Community 9`, `Community 10`?**
  _High betweenness centrality (0.296) - this node is a cross-community bridge._
- **Why does `LLMCaller` connect `Community 2` to `Community 1`, `Community 3`, `Community 4`, `Community 6`, `Community 7`?**
  _High betweenness centrality (0.176) - this node is a cross-community bridge._
- **Why does `DetectionEngine` connect `Community 3` to `Community 1`, `Community 2`, `Community 4`, `Community 7`?**
  _High betweenness centrality (0.125) - this node is a cross-community bridge._
- **Are the 69 inferred relationships involving `ResponseParser` (e.g. with `Mock end-to-end test for v0.5.1 bridge architecture.  Tests the full pipeline: p` and `FileLoader`) actually correct?**
  _`ResponseParser` has 69 INFERRED edges - model-reasoned connections that need verification._
- **Are the 57 inferred relationships involving `PipelineStateManager` (e.g. with `MCP Server v0.5.1 — Bridge Architecture with Long-Context Support.  MCP Server i` and `预估 Skill 或 Pipeline 的 token 用量，帮助 Agent 做预算决策。      调用 render_skill 之前先调用此工具，判断是`) actually correct?**
  _`PipelineStateManager` has 57 INFERRED edges - model-reasoned connections that need verification._
- **Are the 44 inferred relationships involving `ErrorCode` (e.g. with `MCP Server v0.5.1 — Bridge Architecture with Long-Context Support.  MCP Server i` and `预估 Skill 或 Pipeline 的 token 用量，帮助 Agent 做预算决策。      调用 render_skill 之前先调用此工具，判断是`) actually correct?**
  _`ErrorCode` has 44 INFERRED edges - model-reasoned connections that need verification._
- **Are the 33 inferred relationships involving `LLMCaller` (e.g. with `MockLLMCaller` and `Local end-to-end runner for judicial-lint-mcp v0.5.0  Simulates a detect_anomali`) actually correct?**
  _`LLMCaller` has 33 INFERRED edges - model-reasoned connections that need verification._