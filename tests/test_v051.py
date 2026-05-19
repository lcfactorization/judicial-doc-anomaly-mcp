"""Comprehensive unit tests for v0.5.1 changes.

Covers:
  - PipelineStateManager (TTL, persistence, concurrency, cleanup)
  - ErrorCode + make_error (structured error responses)
  - Token estimation (CJK/Latin heuristic)
  - JSON wrapper stripping in ResponseParser
  - Data anonymization
  - Audit trail
  - Anti-Laziness directive injection
  - render_skill_batch
"""

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from judicial_lint_mcp.error_codes import ErrorCode, make_error
from judicial_lint_mcp.pipeline_state import PipelineStateManager
from judicial_lint_mcp.response_parser import ResponseParser


# ── PipelineStateManager ──────────────────────────────────────


class TestPipelineStateManager:
    def test_save_and_get(self, tmp_path):
        mgr = PipelineStateManager(ttl=timedelta(hours=1), persist=False)
        mgr.save("s1", {"pipeline": "full_scan", "skills": ["a", "b"]})
        result = mgr.get("s1")
        assert result is not None
        assert result["pipeline"] == "full_scan"
        assert "updated_at" in result

    def test_get_missing_returns_none(self):
        mgr = PipelineStateManager(persist=False)
        assert mgr.get("nonexistent") is None

    def test_update(self):
        mgr = PipelineStateManager(persist=False)
        mgr.save("s1", {"completed": [], "skills": ["a", "b"]})
        mgr.update("s1", {"completed": ["a"]})
        result = mgr.get("s1")
        assert result["completed"] == ["a"]

    def test_update_missing_returns_none(self):
        mgr = PipelineStateManager(persist=False)
        assert mgr.update("nonexistent", {"x": 1}) is None

    def test_delete(self):
        mgr = PipelineStateManager(persist=False)
        mgr.save("s1", {"pipeline": "test"})
        mgr.delete("s1")
        assert mgr.get("s1") is None

    def test_ttl_expiration(self):
        mgr = PipelineStateManager(ttl=timedelta(seconds=0), persist=False)
        mgr.save("s1", {"pipeline": "test"})
        time.sleep(0.05)
        assert mgr.get("s1") is None

    def test_cleanup_expired(self):
        mgr = PipelineStateManager(ttl=timedelta(seconds=0), persist=False)
        mgr.save("s1", {"pipeline": "test"})
        time.sleep(0.05)
        removed = mgr.cleanup_expired()
        assert removed >= 1

    def test_concurrent_access(self):
        mgr = PipelineStateManager(persist=False)
        errors = []

        def writer(sid):
            try:
                for i in range(50):
                    mgr.save(sid, {"i": i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(f"s{i % 3}",)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_persistence_to_disk(self, tmp_path):
        with patch("judicial_lint_mcp.pipeline_state._STATE_DIR", tmp_path):
            mgr1 = PipelineStateManager(ttl=timedelta(hours=1), persist=True)
            mgr1.save("s1", {"pipeline": "full_scan", "skills": ["a"]})

            mgr2 = PipelineStateManager(ttl=timedelta(hours=1), persist=True)
            result = mgr2.get("s1")
            assert result is not None
            assert result["pipeline"] == "full_scan"

    def test_persistence_cleanup_on_load(self, tmp_path):
        expired_file = tmp_path / "s_expired.json"
        expired_file.write_text(
            json.dumps({"updated_at": (datetime.now() - timedelta(days=2)).isoformat()}),
            encoding="utf-8",
        )

        with patch("judicial_lint_mcp.pipeline_state._STATE_DIR", tmp_path):
            mgr = PipelineStateManager(ttl=timedelta(hours=1), persist=True)
            assert mgr.get("s_expired") is None


# ── ErrorCode + make_error ────────────────────────────────────


class TestErrorCode:
    def test_make_error_structure(self):
        result = json.loads(make_error(ErrorCode.SKILL_NOT_FOUND, "Skill 不存在", {"skill_name": "test"}))
        assert result["success"] is False
        assert result["error"]["code"] == "SKILL_404"
        assert result["error"]["message"] == "Skill 不存在"
        assert result["error"]["retryable"] is False
        assert result["error"]["details"]["skill_name"] == "test"

    def test_retryable_codes(self):
        for code in [ErrorCode.TOKEN_OVERFLOW, ErrorCode.RENDER_FAILED, ErrorCode.STATE_ERROR]:
            result = json.loads(make_error(code, "test"))
            assert result["error"]["retryable"] is True

    def test_non_retryable_codes(self):
        for code in [ErrorCode.SKILL_NOT_FOUND, ErrorCode.SESSION_NOT_FOUND, ErrorCode.INVALID_PARAMS]:
            result = json.loads(make_error(code, "test"))
            assert result["error"]["retryable"] is False

    def test_make_error_without_details(self):
        result = json.loads(make_error(ErrorCode.INTERNAL_ERROR, "内部错误"))
        assert "details" not in result["error"]


# ── Token Estimation ─────────────────────────────────────────


class TestTokenEstimation:
    def test_cjk_heavy_text(self):
        from judicial_lint_mcp.server import _estimate_tokens

        cjk_text = "这是一个中文测试文本，用于验证CJK字符的token估算精度。"
        tokens = _estimate_tokens(cjk_text)
        assert tokens > 0
        assert tokens < len(cjk_text)

    def test_latin_heavy_text(self):
        from judicial_lint_mcp.server import _estimate_tokens

        latin_text = "This is a test string for verifying Latin character token estimation accuracy."
        tokens = _estimate_tokens(latin_text)
        assert tokens > 0
        assert tokens < len(latin_text)

    def test_mixed_text(self):
        from judicial_lint_mcp.server import _estimate_tokens

        mixed = "判决书第5页第3段'关于加班工资的认定'部分，根据《劳动争议司法解释（一）》第42条"
        tokens = _estimate_tokens(mixed)
        assert tokens > 0

    def test_empty_text(self):
        from judicial_lint_mcp.server import _estimate_tokens

        assert _estimate_tokens("") == 0

    def test_cjk_vs_latin_ratio(self):
        from judicial_lint_mcp.server import _estimate_tokens

        cjk = "中" * 100
        latin = "a" * 100
        cjk_tokens = _estimate_tokens(cjk)
        latin_tokens = _estimate_tokens(latin)
        assert cjk_tokens > latin_tokens


# ── JSON Wrapper Stripping ───────────────────────────────────


class TestJsonWrapperStripping:
    def setup_method(self):
        self.parser = ResponseParser()

    def test_strip_json_code_fence(self):
        wrapped = '```json\n{"content": "#### 1. 异常项：测试\\n- 具体表现：xxx"}\n```'
        result = self.parser._strip_json_wrapper(wrapped)
        assert "异常项" in result
        assert "```" not in result

    def test_strip_plain_json(self):
        wrapped = '{"response": "#### 1. 异常项：测试\\n- 具体表现：xxx"}'
        result = self.parser._strip_json_wrapper(wrapped)
        assert "异常项" in result

    def test_no_wrapper_passthrough(self):
        text = "#### 1. 异常项：测试\n- 具体表现：xxx"
        result = self.parser._strip_json_wrapper(text)
        assert result == text

    def test_invalid_json_in_fence(self):
        wrapped = '```json\n{invalid json}\n```'
        result = self.parser._strip_json_wrapper(wrapped)
        assert "invalid" in result

    def test_json_with_result_key(self):
        wrapped = '{"result": "#### 1. 异常项：举证责任分配异常"}'
        result = self.parser._strip_json_wrapper(wrapped)
        assert "举证责任" in result

    def test_json_without_known_key(self):
        wrapped = '{"anomalies": [{"name": "test"}]}'
        result = self.parser._strip_json_wrapper(wrapped)
        parsed = json.loads(result)
        assert "anomalies" in parsed


# ── Data Anonymization ───────────────────────────────────────


class TestAnonymization:
    def test_anonymize_phone(self):
        from judicial_lint_mcp.server import _anonymize_text

        text = "联系电话：13800000000"
        result = _anonymize_text(text)
        assert "13800000000" not in result
        assert "1**********" in result

    def test_anonymize_date(self):
        from judicial_lint_mcp.server import _anonymize_text

        text = "入职日期2023-01-15"
        result = _anonymize_text(text)
        assert "2023-01-15" not in result

    def test_anonymize_case_number(self):
        from judicial_lint_mcp.server import _anonymize_text

        text = "（2025）某0602民初XXXX号"
        result = _anonymize_text(text)
        assert "XXXX" not in result

    def test_anonymize_id_number(self):
        from judicial_lint_mcp.server import _anonymize_text

        text = "身份证号：320123200001010000"
        result = _anonymize_text(text)
        assert "320123200001010000" not in result

    def test_preserve_non_sensitive(self):
        from judicial_lint_mcp.server import _anonymize_text

        text = "原告主张加班工资"
        result = _anonymize_text(text)
        assert "加班工资" in result


# ── Audit Trail ──────────────────────────────────────────────


class TestAuditTrail:
    def test_record_and_retrieve(self):
        from judicial_lint_mcp.server import _audit_log, _record_audit

        _audit_log.clear()
        _record_audit("s1", "plan_pipeline", "created", "pipeline=full_scan")
        _record_audit("s1", "render_skill", "complete", "skill=01_procedure")
        _record_audit("s2", "plan_pipeline", "created", "pipeline=evidence_focus")

        assert len(_audit_log) == 3
        assert _audit_log[0]["session_id"] == "s1"
        assert _audit_log[0]["tool"] == "plan_pipeline"

    def test_audit_has_timestamp(self):
        from judicial_lint_mcp.server import _audit_log, _record_audit

        _audit_log.clear()
        _record_audit("s1", "test", "action")
        assert "timestamp" in _audit_log[0]


# ── Anti-Laziness Directive ──────────────────────────────────


class TestAntiLaziness:
    def test_directive_exists(self):
        from judicial_lint_mcp.server import ANTI_LAZINESS_DIRECTIVE

        assert "Anti-Laziness" in ANTI_LAZINESS_DIRECTIVE
        assert "render_skill" in ANTI_LAZINESS_DIRECTIVE
        assert "build_report" in ANTI_LAZINESS_DIRECTIVE


# ── ResponseParser Integration ───────────────────────────────


class TestResponseParserIntegration:
    def setup_method(self):
        self.parser = ResponseParser()

    def test_parse_full_anomaly(self):
        response = "\n#### 1. 异常项：举证责任分配异常\n\n- **具体表现**：考勤记录已证明加班事实，但判决书将加班工资的举证责任分配给劳动者\n- **原文定位**：判决书第5页第3段\n- **证据对照**：被上诉人掌握考勤记录但未完整提交\n- **指向获益方**：被告\n- **异常程度**：高度可能\n- **法理分析**：根据《劳动争议司法解释（一）》第42条，应适用举证妨碍规则\n- **法律依据**：《劳动争议司法解释（一）》第42条\n- **修复建议**：在证据采信部分补充说明为何不适用举证妨碍规则\n- **Q1（替代解释）**：用人单位可能因考勤系统故障导致记录不完整\n- **Q2（排除主观故意）**：未见选择性忽略\n- **Q3（相反证据）**：用人单位提交的工资表显示已支付部分加班费\n- **对抗结论**：存疑\n- **净异常判定**：存疑\n- **扣分**：5"

        result = self.parser.parse_dimension_result("evidence", response, 1)
        assert len(result.anomalies) >= 1
        a = result.anomalies[0]
        assert "举证责任" in a.item_name
        assert a.original_text_location != ""
        assert a.evidence_reference != ""
        assert a.legal_basis != ""
        assert a.suggestion != ""
        assert a.q1_alternative != ""
        assert "5" in a.suggestion or a.deduction > 0

    def test_parse_json_wrapped_response(self):
        response = json.dumps({
            "content": "\n#### 1. 异常项：程序异常\n- **具体表现**：未送达答辩状副本\n- **指向获益方**：原告\n- **异常程度**：确定"
        })
        result = self.parser.parse_dimension_result("procedure", response, 0)
        assert len(result.anomalies) >= 1
        assert "程序异常" in result.anomalies[0].item_name

    def test_parse_empty_response(self):
        result = self.parser.parse_dimension_result("test", "", 0)
        assert len(result.anomalies) >= 1

    def test_confidence_mapping(self):
        assert ResponseParser._map_confidence("确定") == "high"
        assert ResponseParser._map_confidence("高度可能") == "high"
        assert ResponseParser._map_confidence("可能") == "medium"
        assert ResponseParser._map_confidence("疑似") == "low"
        assert ResponseParser._map_confidence("") == "medium"


# ── Error Code Enum Completeness ─────────────────────────────


class TestErrorCodeCompleteness:
    def test_all_codes_have_values(self):
        for code in ErrorCode:
            assert len(code.value) > 0
            assert "_" in code.value

    def test_all_codes_serializable(self):
        for code in ErrorCode:
            result = json.loads(make_error(code, "test"))
            assert result["success"] is False
            assert result["error"]["code"] == code.value


# ── debug_render Tool ────────────────────────────────────────


class TestDebugRender:
    def test_debug_render_skill_not_found(self):
        from judicial_lint_mcp.server import debug_render

        result = json.loads(debug_render("dimensions/99_nonexistent"))
        assert result["success"] is False
        assert result["error"]["code"] == "SKILL_404"

    def test_debug_render_no_diff(self):
        from judicial_lint_mcp.server import debug_render

        result = json.loads(debug_render("dimensions/01_procedure", variables={"materials": "测试材料"}, show_diff=False))
        assert "skill_name" in result
        assert "variables_provided" in result
        assert "materials" in result["variables_provided"]
        assert "variables_unresolved" in result

    def test_debug_render_with_diff(self):
        from judicial_lint_mcp.server import debug_render

        result = json.loads(debug_render("dimensions/01_procedure", variables={"materials": "测试材料"}, show_diff=True))
        assert "diff" in result
        assert "diff_count" in result
        assert isinstance(result["diff_count"], int)


# ── render_skill_batch Edge Cases ────────────────────────────


class TestRenderSkillBatch:
    def test_batch_skill_not_found(self):
        from judicial_lint_mcp.server import render_skill_batch

        result = json.loads(render_skill_batch(["dimensions/99_fake"]))
        assert result["success"] is False
        assert result["error"]["code"] == "SKILL_404"

    def test_batch_empty_list(self):
        from judicial_lint_mcp.server import render_skill_batch

        result = json.loads(render_skill_batch([]))
        assert result["total_skills"] == 0


# ── Pipeline State Edge Cases ────────────────────────────────


class TestPipelineStateEdgeCases:
    def test_delete_nonexistent(self):
        mgr = PipelineStateManager(persist=False)
        mgr.delete("nonexistent")

    def test_save_overwrite(self):
        mgr = PipelineStateManager(persist=False)
        mgr.save("s1", {"v": 1})
        mgr.save("s1", {"v": 2})
        assert mgr.get("s1")["v"] == 2

    def test_cleanup_no_expired(self):
        mgr = PipelineStateManager(ttl=timedelta(hours=1), persist=False)
        mgr.save("s1", {"v": 1})
        removed = mgr.cleanup_expired()
        assert removed == 0


# ── compact_materials Edge Cases ─────────────────────────────


class TestCompactMaterialsEdgeCases:
    def test_compact_short_text_no_compression(self):
        from judicial_lint_mcp.server import compact_materials

        short_text = "这是一段短文本"
        result = json.loads(compact_materials(short_text, max_tokens=10000))
        assert result["compression_ratio"] == 1.0
        assert result["strategy_used"] == "none_needed"

    def test_compact_truncate_strategy(self):
        from judicial_lint_mcp.server import compact_materials

        long_text = "测试内容" * 5000
        result = json.loads(compact_materials(long_text, max_tokens=100, strategy="truncate"))
        assert result["compacted_tokens"] <= 150

    def test_compact_outline_strategy(self):
        from judicial_lint_mcp.server import compact_materials

        text = "# 标题一\n详细内容\n\n## 标题二\n更多内容"
        result = json.loads(compact_materials(text, max_tokens=100, strategy="outline"))
        assert "标题" in result["compacted"]


# ── parse_response Edge Cases ────────────────────────────────


class TestParseResponseEdgeCases:
    def setup_method(self):
        self.parser = ResponseParser()

    def test_parse_with_markdown_code_block(self):
        response = '```json\n{"content": "#### 1. 异常项：代码块包裹\\n- **具体表现**：测试"}\n```'
        result = self.parser.parse_dimension_result("test", response, 0)
        assert len(result.anomalies) >= 1

    def test_parse_multiple_anomalies(self):
        response = (
            "\n#### 1. 异常项：异常A\n- **具体表现**：描述A\n- **指向获益方**：被告\n- **异常程度**：高度可能\n\n"
            "#### 2. 异常项：异常B\n- **具体表现**：描述B\n- **指向获益方**：原告\n- **异常程度**：可能"
        )
        result = self.parser.parse_dimension_result("test", response, 0)
        assert len(result.anomalies) >= 2

    def test_parse_no_anomaly(self):
        response = "本维度未发现异常。"
        result = self.parser.parse_dimension_result("test", response, 0)
        assert result.dimension == "test"


# ── Anonymization Edge Cases ─────────────────────────────────


class TestAnonymizationEdgeCases:
    def test_anonymize_address(self):
        from judicial_lint_mcp.server import _anonymize_text

        text = "住址：某省某市某区测试路100号"
        result = _anonymize_text(text)
        assert "测试路100号" not in result

    def test_anonymize_preserves_structure(self):
        from judicial_lint_mcp.server import _anonymize_text

        text = "原告张某与被告李某劳动争议一案"
        result = _anonymize_text(text)
        assert "原告" in result
        assert "被告" in result
        assert "劳动争议" in result


# ── Server Tool Integration Tests ────────────────────────────


class TestEstimateTokensTool:
    def test_estimate_with_skill_name(self):
        from judicial_lint_mcp.server import estimate_tokens

        result = json.loads(estimate_tokens(skill_name="dimensions/01_procedure", materials_chars=5000))
        assert "estimated_tokens" in result
        assert "breakdown" in result
        assert result["breakdown"]["materials"] > 0

    def test_estimate_skill_not_found(self):
        from judicial_lint_mcp.server import estimate_tokens

        result = json.loads(estimate_tokens(skill_name="dimensions/99_fake"))
        assert result["success"] is False
        assert result["error"]["code"] == "SKILL_404"

    def test_estimate_with_pipeline_name(self):
        from judicial_lint_mcp.server import estimate_tokens

        result = json.loads(estimate_tokens(pipeline_name="full_scan", materials_chars=5000))
        assert "estimated_tokens" in result
        assert "breakdown" in result


class TestRenderSkillTool:
    def test_render_skill_success(self):
        from judicial_lint_mcp.server import render_skill

        result = json.loads(render_skill("dimensions/01_procedure", variables={"materials": "测试案件材料"}))
        assert result["skill_name"] == "procedure"
        assert "system_prompt" in result
        assert "user_prompt" in result
        assert "token_estimate" in result

    def test_render_skill_not_found(self):
        from judicial_lint_mcp.server import render_skill

        result = json.loads(render_skill("dimensions/99_nonexistent"))
        assert result["success"] is False
        assert result["error"]["code"] == "SKILL_404"


class TestParseResponseTool:
    def test_parse_response_success(self):
        from judicial_lint_mcp.server import parse_response

        response = "\n#### 1. 异常项：程序违法\n- **具体表现**：未送达答辩状\n- **指向获益方**：原告\n- **异常程度**：确定"
        result = json.loads(parse_response("procedure", response, 0))
        assert result["dimension"] == "procedure"
        assert result["anomaly_count"] >= 1
        assert "anomalies" in result


class TestBuildReportTool:
    def test_build_report_success(self):
        from judicial_lint_mcp.server import build_report

        dim_data = [{
            "dimension": "procedure",
            "anomalies": [{
                "item_name": "程序违法",
                "description": "未送达答辩状",
                "beneficiary": "原告",
                "confidence": "high",
                "f_code": "F-01",
                "a_code": "A1",
                "original_text": "原文引用",
                "original_text_location": "第3页",
                "evidence_reference": "证据1",
                "legal_analysis": "分析",
                "legal_basis": "民诉法第125条",
                "suggestion": "建议补充送达回证",
                "deduction": 5,
            }],
            "risk_level": "high",
            "summary": "程序存在违法",
        }]
        report = build_report("测试案件", json.dumps(dim_data), "判决书", "mock-llm")
        assert "程序违法" in report
        assert "高风险" in report

    def test_build_report_invalid_json(self):
        from judicial_lint_mcp.server import build_report

        result = build_report("测试案件", "invalid json{{{", "判决书", "mock-llm")
        assert "PARSE_400" in result


class TestListSkillsTool:
    def test_list_skills(self):
        from judicial_lint_mcp.server import list_skills

        result = list_skills()
        assert "可用 Skills" in result or "Skill" in result


class TestPipelineProgressTool:
    def test_pipeline_progress_session_not_found(self):
        from judicial_lint_mcp.server import pipeline_progress

        result = json.loads(pipeline_progress(session_id="nonexistent_session"))
        assert result["success"] is False
        assert result["error"]["code"] == "SESSION_404"

    def test_pipeline_progress_complete_without_skill(self):
        from judicial_lint_mcp.server import pipeline_progress, _state_mgr

        _state_mgr.save("s_test", {"skills": ["a"], "completed": [], "current_index": 0, "results": {}})
        result = json.loads(pipeline_progress(session_id="s_test", action="complete"))
        assert result["success"] is False
        assert result["error"]["code"] == "PARAM_400"


class TestGetAuditTrailTool:
    def test_get_audit_trail(self):
        from judicial_lint_mcp.server import _audit_log, get_audit_trail

        _audit_log.clear()
        from judicial_lint_mcp.server import _record_audit
        _record_audit("s1", "test", "action")
        result = json.loads(get_audit_trail(session_id="s1"))
        assert result["total"] >= 1

    def test_get_audit_trail_empty(self):
        from judicial_lint_mcp.server import _audit_log, get_audit_trail

        _audit_log.clear()
        result = json.loads(get_audit_trail())
        assert result["total"] == 0


class TestWriteSkillTool:
    def test_write_skill(self, tmp_path):
        from judicial_lint_mcp.server import write_skill

        result = write_skill("_test_skill", "# Test Skill\n测试内容")
        assert "已写入" in result or "test_skill" in result.lower()


class TestCompactMaterialsAnonymize:
    def test_compact_with_anonymize(self):
        from judicial_lint_mcp.server import compact_materials

        text = "原告张某，电话13800000000，案号（2025）某9999民初XXXX号"
        result = json.loads(compact_materials(text, max_tokens=10000, anonymize=True))
        assert result["anonymized"] is True
        assert "13800000000" not in result["compacted"]


# ── Plan Pipeline + Progress Full Flow ───────────────────────


class TestPlanPipelineFlow:
    def test_plan_pipeline_full_scan(self):
        from judicial_lint_mcp.server import plan_pipeline

        result = json.loads(plan_pipeline(pipeline_name="full_scan"))
        assert "session_id" in result
        assert "skills" in result
        assert "anti_laziness_directive" in result
        assert "Anti-Laziness" in result["anti_laziness_directive"]

    def test_plan_pipeline_not_found(self):
        from judicial_lint_mcp.server import plan_pipeline

        result = json.loads(plan_pipeline(pipeline_name="nonexistent_pipeline"))
        assert result["success"] is False
        assert result["error"]["code"] == "PIPELINE_404"

    def test_pipeline_progress_complete_and_resume(self):
        from judicial_lint_mcp.server import plan_pipeline, pipeline_progress, _state_mgr

        plan_result = json.loads(plan_pipeline(pipeline_name="full_scan"))
        session_id = plan_result["session_id"]

        status = json.loads(pipeline_progress(session_id=session_id, action="status"))
        assert status["completed_count"] == 0
        assert status["progress_pct"] == 0

        skills = plan_result["skills"]
        if len(skills) > 0:
            first_skill = skills[0]["skill_name"]
            complete = json.loads(pipeline_progress(
                session_id=session_id, action="complete",
                skill_name=first_skill, result_summary="测试完成",
            ))
            assert complete["completed_count"] == 1
            assert complete["progress_pct"] > 0

            resume = json.loads(pipeline_progress(session_id=session_id, action="resume"))
            assert "remaining_skills" in resume

    def test_pipeline_progress_reset(self):
        from judicial_lint_mcp.server import plan_pipeline, pipeline_progress

        plan_result = json.loads(plan_pipeline(pipeline_name="full_scan"))
        session_id = plan_result["session_id"]

        skills = plan_result["skills"]
        if len(skills) > 0:
            first_skill = skills[0]["skill_name"]
            pipeline_progress(session_id=session_id, action="complete", skill_name=first_skill)

        reset = json.loads(pipeline_progress(session_id=session_id, action="reset"))
        assert reset["completed_count"] == 0


# ── render_skill_batch with real skills ──────────────────────


class TestRenderSkillBatchReal:
    def test_batch_with_real_skills(self):
        from judicial_lint_mcp.server import render_skill_batch

        result = json.loads(render_skill_batch(
            ["dimensions/01_procedure", "dimensions/02_evidence"],
            variables={"materials": "测试案件材料"},
        ))
        assert "skills" in result
        assert result["total_skills"] == 2
        assert result["total_estimated_tokens"] > 0


# ── Material Compaction Internal Functions ───────────────────


class TestMaterialCompactionInternal:
    def test_extract_key_facts_with_sections(self):
        from judicial_lint_mcp.server import _extract_key_facts

        text = (
            "# 争议焦点\n原告主张加班工资\n被告辩称不存在加班\n\n"
            "## 事实认定\n法院认定原告存在加班事实\n\n"
            "## 无关内容\n" + "普通段落" * 50 + "\n"
        )
        result = _extract_key_facts(text, 500)
        assert "争议焦点" in result
        assert len(result) <= 600

    def test_outline_compact(self):
        from judicial_lint_mcp.server import _outline_compact

        text = "# 标题一\n详细内容行1\n详细内容行2\n\n## 标题二\n1. 列表项1\n2. 列表项2\n\n三、中文序号段落"
        result = _outline_compact(text, 500)
        assert "标题一" in result
        assert "标题二" in result

    def test_section_outline(self):
        from judicial_lint_mcp.server import _section_outline

        content = "# 标题\n行1\n行2\n行3\n行4\n行5"
        result = _section_outline(content)
        assert "标题" in result
        assert "共5行" in result


# ── MCP Resources ────────────────────────────────────────────


class TestMCPResources:
    def test_skills_resource(self):
        from judicial_lint_mcp.server import get_skills_resource

        result = get_skills_resource()
        assert "Skills" in result or "skill" in result.lower()

    def test_taxonomy_resource(self):
        from judicial_lint_mcp.server import get_taxonomy_resource

        result = get_taxonomy_resource()
        assert len(result) > 0

    def test_system_resource(self):
        from judicial_lint_mcp.server import get_system_resource

        result = get_system_resource()
        assert len(result) > 0


# ── render_pipeline (deprecated) ─────────────────────────────


class TestRenderPipelineDeprecated:
    def test_render_pipeline_deprecated(self):
        from judicial_lint_mcp.server import render_pipeline

        result = json.loads(render_pipeline("full_scan", variables={"materials": "测试"}))
        assert "warning" in result
        assert "弃用" in result["warning"]

    def test_render_pipeline_not_found(self):
        from judicial_lint_mcp.server import render_pipeline

        result = json.loads(render_pipeline("nonexistent_pipeline"))
        assert result["success"] is False
        assert result["error"]["code"] == "PIPELINE_404"


# ── HTML Report Generation ──────────────────────────────────


class TestBuildReportHtmlTool:
    def test_build_report_html_success(self):
        from judicial_lint_mcp.server import build_report_html

        dim_data = [{
            "dimension": "procedure",
            "anomalies": [{
                "item_name": "程序违法",
                "description": "未送达答辩状",
                "beneficiary": "原告",
                "confidence": "high",
                "f_code": "F-01",
                "a_code": "A1",
                "original_text": "原文引用",
                "original_text_location": "第3页",
                "evidence_reference": "证据1",
                "legal_analysis": "分析",
                "legal_basis": "民诉法第125条",
                "suggestion": "建议补充送达回证",
                "deduction": 5,
            }],
            "risk_level": "high",
            "summary": "程序存在违法",
        }]
        html = build_report_html("测试案件", json.dumps(dim_data), "判决书", "mock-llm")
        assert "<!DOCTYPE html>" in html
        assert "程序违法" in html
        assert "高风险" in html
        assert "data-theme" in html
        assert "toggleTheme" in html

    def test_build_report_html_invalid_json(self):
        from judicial_lint_mcp.server import build_report_html

        result = build_report_html("测试案件", "invalid json{{{", "判决书", "mock-llm")
        assert "PARSE_400" in result

    def test_build_report_html_no_anomalies(self):
        from judicial_lint_mcp.server import build_report_html

        dim_data = [{
            "dimension": "procedure",
            "anomalies": [],
            "risk_level": "low",
            "summary": "无异常",
        }]
        html = build_report_html("测试案件", json.dumps(dim_data))
        assert "<!DOCTYPE html>" in html
        assert "低风险" in html

    def test_md_to_rich_html_table(self):
        from judicial_lint_mcp.report_builder import _md_to_rich_html

        md = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
        html = _md_to_rich_html(md)
        assert "<table>" in html
        assert "<th" in html
        assert "<td" in html

    def test_md_to_rich_html_alerts(self):
        from judicial_lint_mcp.report_builder import _md_to_rich_html

        md = "> [!WARNING]\n> 这是警告\n> [!TIP]\n> 这是提示"
        html = _md_to_rich_html(md)
        assert "alert-warning" in html
        assert "alert-tip" in html

    def test_md_to_rich_html_headings(self):
        from judicial_lint_mcp.report_builder import _md_to_rich_html

        md = "# 标题一\n## 标题二\n### 标题三\n#### 标题四"
        html = _md_to_rich_html(md)
        assert "<h1>" in html
        assert "<h2>" in html
        assert "<h3>" in html
        assert "<h4>" in html
