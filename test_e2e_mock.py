"""Mock end-to-end test for generate_report with A1-A8 classification and 16-dimension scoring."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from judicial_lint_mcp.config import AppConfig
from judicial_lint_mcp.preprocessor import PreprocessResult, CaseInfo, TimelineEntry, EvidenceEntry, ClaimEntry
from judicial_lint_mcp.detector import DetectionResult, DimensionResult, AnomalyItem
from judicial_lint_mcp.quality_assessor import QualityAssessmentResult, DimensionScore
from judicial_lint_mcp.adversarial import AdversarialResult, DevilsAdvocateResult, RoleReviewResult
from judicial_lint_mcp.server import generate_report, benchmark_compare


async def test_generate_report():
    mock_config = AppConfig.from_env()
    mock_llm = MagicMock()

    case_info = CaseInfo(
        case_number="(2024)粤01民初123号",
        case_name="张某诉李某劳动争议",
        case_type="民事判决书",
        parties=["张某", "李某"],
    )
    timeline = [
        TimelineEntry(date="2024-01-15", event="立案受理", source="案卷"),
        TimelineEntry(date="2024-03-20", event="开庭审理", source="案卷"),
    ]
    evidence = [
        EvidenceEntry(evidence_id="E1", evidence_type="书证", submitted_by="原告", description="微信聊天记录")
    ]
    claims = [ClaimEntry(claim_id="C1", party="原告", claim_content="确认劳动关系")]
    preprocess_result = PreprocessResult(
        materials_text="模拟案件材料文本",
        case_info=case_info,
        completeness_score=75.0,
        missing_items=["庭审笔录"],
        timeline=timeline,
        evidence_index=evidence,
        claims_map=claims,
    )

    anomaly1 = AnomalyItem(
        dimension="evidence",
        item_name="微信证据未回应",
        description="原告提交的微信聊天记录未被评述",
        beneficiary="被告",
        confidence="high",
        f_code="F-14",
        a_code="A1",
        reverse_check="无反向异常",
        net_anomaly="成立",
    )
    dim_result = DimensionResult(
        dimension="evidence",
        anomalies=[anomaly1],
        summary="证据采信存在异常",
        risk_level="high",
    )
    detection_result = DetectionResult(
        dimension_results=[dim_result],
        risk_level="中度异常",
        risk_reason="证据采信维度存在高严重度异常",
        report_markdown="## 证据采信检测\n发现1项异常",
    )

    dim_scores = [
        DimensionScore(
            dimension="程序合规性", full_score=20, deduction=4, score=16, weight=0.20, weighted_score=3.2
        )
    ]
    quality_result = QualityAssessmentResult(
        dimension_scores=dim_scores,
        total_score=72,
        grade="C",
        grade_description="中等质量",
        strengths=["程序基本合规"],
        weaknesses=["事实认定说理不充分"],
        improvement_suggestions=["加强证据评述"],
    )

    da_result = DevilsAdvocateResult(
        anomaly_id="DA-1",
        anomaly_description="微信证据未回应",
        q1_alternative_explanation="可能因证据形式瑕疵被排除",
        q1_has_alternative=True,
        q2_still_valid_without_intent=False,
        q3_counter_evidence="被告提交了相反证据",
        q3_has_counter=True,
        conclusion="存疑",
        conclusion_reason="存在替代解释且存在反证",
    )
    adversarial_result = AdversarialResult(
        devils_advocate_results=[da_result],
        role_reviews=[
            RoleReviewResult(
                role="defendant_agent",
                role_name_cn="被告代理人",
                challenge_points=[{"point": "证据审查不充分", "severity": "中"}],
                risk_level="中",
            )
        ],
        cross_examinations=[],
        high_risk_points=[{"risk_level": "中", "point": "微信证据未回应"}],
    )

    with (
        patch("judicial_lint_mcp.server._load_config", return_value=mock_config),
        patch("judicial_lint_mcp.server._make_llm_caller", return_value=mock_llm),
        patch("judicial_lint_mcp.server.Preprocessor") as MockPreprocessor,
        patch("judicial_lint_mcp.server.DetectionEngine") as MockEngine,
        patch("judicial_lint_mcp.server.QualityAssessor") as MockAssessor,
        patch("judicial_lint_mcp.server.AdversarialReviewer") as MockReviewer,
    ):
        MockPreprocessor.return_value.run = AsyncMock(return_value=preprocess_result)
        MockEngine.return_value.run_detection = AsyncMock(return_value=detection_result)
        MockAssessor.return_value.assess = AsyncMock(return_value=quality_result)
        MockReviewer.return_value.run = AsyncMock(return_value=adversarial_result)

        report = await generate_report(case_dir="tests/fixtures/sample_case")

    print("=== generate_report 输出 ===")
    print(report[:3000])
    print(f"\n... (total {len(report)} chars)")

    has_a_code = "A1" in report
    has_beneficiary = "被告" in report
    has_quality_score = "72" in report
    has_quality_grade = "C" in report
    has_adversarial = "存疑" in report
    has_risk_level = "中度异常" in report
    has_timeline = "2024-01-15" in report

    print("\n=== 验证结果 ===")
    checks = [
        ("A系列分类映射", has_a_code),
        ("指向获益方(被告)", has_beneficiary),
        ("质量评估分数(72)", has_quality_score),
        ("质量等级(C)", has_quality_grade),
        ("对抗审查(存疑)", has_adversarial),
        ("风险等级(中度异常)", has_risk_level),
        ("时间线(2024-01-15)", has_timeline),
    ]
    all_pass = True
    for name, ok in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  {status} {name}")

    return all_pass


def test_benchmark_compare():
    result = benchmark_compare("A1,A4,A6", "劳动争议")
    has_similarity = "0.50" in result
    has_bm001 = "BM-001" in result
    has_calibration = "校准建议" in result
    has_high_sim = "高度相似" in result

    print("\n=== benchmark_compare 验证 ===")
    checks = [
        ("Jaccard相似度(0.50)", has_similarity),
        ("基准案例BM-001", has_bm001),
        ("校准建议", has_calibration),
        ("高度相似判定", has_high_sim),
    ]
    all_pass = True
    for name, ok in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  {status} {name}")
    return all_pass


if __name__ == "__main__":
    e2e_pass = asyncio.run(test_generate_report())
    bench_pass = test_benchmark_compare()
    if e2e_pass and bench_pass:
        print("\n✅ 全部端到端测试通过")
    else:
        print("\n❌ 存在测试失败")
