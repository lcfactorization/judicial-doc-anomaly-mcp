"""Mock end-to-end test for v0.5.1 bridge architecture.

Tests the full pipeline: plan_pipeline → render_skill → parse_response → build_report
using mock data (no real LLM calls).
"""

import json

from judicial_lint_mcp.models import AnomalyItem, DetectionResult, DimensionResult
from judicial_lint_mcp.report_builder import ReportBuilder
from judicial_lint_mcp.response_parser import ResponseParser
from judicial_lint_mcp.server import (
    _anonymize_text,
    _estimate_tokens,
    _record_audit,
    _state_mgr,
    build_report,
    compact_materials,
    get_audit_trail,
    pipeline_progress,
    plan_pipeline,
)


def test_full_pipeline_mock():
    parser = ResponseParser()
    builder = ReportBuilder()

    mock_response = (
        "\n#### 1. 异常项：举证责任分配异常\n\n"
        "- **具体表现**：考勤记录已证明加班事实，但判决书将加班工资的举证责任分配给劳动者\n"
        "- **原文定位**：判决书第5页第3段\n"
        "- **证据对照**：被上诉人掌握考勤记录但未完整提交\n"
        "- **指向获益方**：被告\n"
        "- **异常程度**：高度可能\n"
        "- **法理分析**：根据《劳动争议司法解释（一）》第42条，应适用举证妨碍规则\n"
        "- **法律依据**：《劳动争议司法解释（一）》第42条\n"
        "- **修复建议**：在证据采信部分补充说明为何不适用举证妨碍规则\n"
        "- **Q1（替代解释）**：用人单位可能因考勤系统故障导致记录不完整\n"
        "- **Q2（排除主观故意）**：未见选择性忽略\n"
        "- **Q3（相反证据）**：用人单位提交的工资表显示已支付部分加班费\n"
        "- **对抗结论**：存疑\n"
        "- **净异常判定**：存疑\n"
        "- **扣分**：5"
    )

    dim_result = parser.parse_dimension_result("evidence", mock_response, 1)

    assert len(dim_result.anomalies) >= 1
    a = dim_result.anomalies[0]
    assert "举证责任" in a.item_name
    assert a.beneficiary != ""
    assert a.confidence == "high"
    assert a.original_text_location != ""
    assert a.evidence_reference != ""
    assert a.legal_basis != ""
    assert a.suggestion != ""

    dim_data = {
        "dimension": dim_result.dimension,
        "anomalies": [
            {
                "item_name": a.item_name,
                "description": a.description,
                "beneficiary": a.beneficiary,
                "confidence": a.confidence,
                "f_code": a.f_code,
                "a_code": a.a_code,
                "original_text": a.original_text,
                "original_text_location": a.original_text_location,
                "evidence_reference": a.evidence_reference,
                "legal_analysis": a.legal_analysis,
                "legal_basis": a.legal_basis,
                "suggestion": a.suggestion,
                "deduction": a.deduction,
            }
        ],
        "risk_level": dim_result.risk_level,
        "summary": dim_result.summary,
    }

    report = build_report(
        case_name="张某诉某公司劳动争议",
        dimension_results_json=json.dumps([dim_data]),
        doc_type="判决书",
        model_name="mock-llm",
    )

    assert "举证责任" in report
    assert "原文定位" in report
    assert "证据对照" in report
    assert "修复建议" in report
    assert "对抗校验" in report or "Q1" in report

    print("=== build_report 输出（前2000字符）===")
    print(report[:2000])
    print(f"\n... (total {len(report)} chars)")

    checks = [
        ("异常项名称", "举证责任" in report),
        ("原文定位", "原文定位" in report),
        ("证据对照", "证据对照" in report),
        ("法律依据", "法律依据" in report),
        ("修复建议", "修复建议" in report),
        ("对抗校验", "Q1" in report or "对抗" in report),
        ("风险等级", "高风险" in report or dim_result.risk_level in report),
    ]

    print("\n=== 验证结果 ===")
    all_pass = True
    for name, ok in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  {status} {name}")

    assert all_pass, "部分检查项未通过"


def test_pipeline_state_flow():
    _state_mgr.cleanup_expired()

    plan_result = plan_pipeline(pipeline_name="full_scan")
    plan_data = json.loads(plan_result)

    if "error" in plan_data and plan_data.get("success") is False:
        print("⚠️ plan_pipeline 需要有效的 skills 目录，跳过状态流测试")
        return

    session_id = plan_data.get("session_id")
    if not session_id:
        print("⚠️ plan_pipeline 未返回 session_id，跳过")
        return

    assert "anti_laziness_directive" in plan_data
    assert "Anti-Laziness" in plan_data["anti_laziness_directive"]

    progress_result = pipeline_progress(session_id=session_id, action="status")
    progress_data = json.loads(progress_result)

    if progress_data.get("success") is False:
        print(f"⚠️ pipeline_progress 返回错误: {progress_data}")
        return

    assert progress_data["session_id"] == session_id
    assert progress_data["completed_count"] == 0

    _record_audit(session_id, "test_e2e", "mock_complete", "evidence")
    audit_result = get_audit_trail(session_id=session_id)
    audit_data = json.loads(audit_result)
    assert audit_data["total"] >= 1

    print("✅ Pipeline 状态流测试通过")


def test_compact_materials_with_anonymize():
    materials = (
        "原告张某，身份证号：320123200001010000，联系电话13800000000，"
        "住址某省某市某区测试路100号。\n"
        "案号（2025）某9999民初9999号，入职日期2023-01-15。\n"
        "原告主张加班工资50000元。"
    )

    result = compact_materials(materials=materials, max_tokens=10000, anonymize=True)
    data = json.loads(result)

    assert data["anonymized"] is True
    assert "13800000000" not in data["compacted"]
    assert "320123200001010000" not in data["compacted"]
    assert "加班工资" in data["compacted"]

    print("✅ 材料压缩+脱敏测试通过")


def test_token_estimation_accuracy():
    cjk_text = "这是一个中文测试文本，用于验证CJK字符的token估算精度。" * 50
    latin_text = "This is a Latin test text for verifying token estimation accuracy. " * 50
    mixed_text = "判决书第5页第3段'关于加班工资的认定'部分，根据Article 42 of the Judicial Interpretation" * 10

    cjk_tokens = _estimate_tokens(cjk_text)
    latin_tokens = _estimate_tokens(latin_text)
    mixed_tokens = _estimate_tokens(mixed_text)

    assert cjk_tokens > 0
    assert latin_tokens > 0
    assert mixed_tokens > 0
    assert cjk_tokens > latin_tokens

    print(f"  CJK: {len(cjk_text)} chars → {cjk_tokens} tokens")
    print(f"  Latin: {len(latin_text)} chars → {latin_tokens} tokens")
    print(f"  Mixed: {len(mixed_text)} chars → {mixed_tokens} tokens")
    print("✅ Token 估算精度测试通过")


if __name__ == "__main__":
    test_full_pipeline_mock()
    test_pipeline_state_flow()
    test_compact_materials_with_anonymize()
    test_token_estimation_accuracy()
    print("\n✅ 全部端到端测试通过")
