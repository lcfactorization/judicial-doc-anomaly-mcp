"""Tests for the red-flag escalation layer (v0.6.0, second feature commit).

Covers:
  - Fatal marks in taxonomy: A9/F-27 fatal=True; F-28 fatal=False with severity_base >= 0.75;
    A1-A8 conservatively NOT fatal
  - is_fatal() helper over (f_code, a_code) pairs
  - Report red-flag banner: rendered at the very top with codes/dimension/item/beneficiary/
    confidence/excerpt columns and consequence text; final red-flag verdict line
  - red_flag_escalation=False keeps legacy behavior (no banner)
  - Non-fatal anomalies do not trigger the banner
  - D17 dimension file contains the admin-decision (行政文书模式) section
"""

import json

import judicial_lint_mcp.server as server_module
from judicial_lint_mcp.models import AnomalyItem, DetectionResult, DimensionResult
from judicial_lint_mcp.report_builder import ReportBuilder
from judicial_lint_mcp.server import build_report
from judicial_lint_mcp.skill_runner import SKILLS_DIR, SkillLoader
from judicial_lint_mcp.taxonomy import (
    F_CODES,
    TAXONOMY,
    get_category,
    get_f_code,
    is_fatal,
)


def _fatal_item(**overrides) -> AnomalyItem:
    base = {
        "dimension": "claim_support",
        "item_name": "遗漏诉讼请求",
        "description": "某项诉讼请求在判决主文与说理中均无对应处置",
        "beneficiary": "原告",
        "confidence": "high",
        "f_code": "F-27",
        "a_code": "A9",
        "original_text": "原文引用：某劳动者主张的未休年休假工资未获回应（占位示例）",
        "original_text_location": "第5页第2段",
        "legal_analysis": "处分原则与两审终审制度要求对诉请逐项裁判",
    }
    base.update(overrides)
    return AnomalyItem(**base)


# ── Fatal Marks in Taxonomy ──────────────────────────────────


class TestFatalTaxonomy:
    def test_a9_is_fatal(self):
        cat = get_category("A9")
        assert cat is not None
        assert cat.fatal is True

    def test_f27_is_fatal(self):
        meta = get_f_code("F-27")
        assert meta is not None
        assert meta.fatal is True
        assert meta.label == "遗漏诉讼请求"

    def test_f28_not_fatal_with_severity_at_least_075(self):
        meta = get_f_code("F-28")
        assert meta is not None
        assert meta.fatal is False
        assert meta.severity_base >= 0.75

    def test_a1_to_a8_conservatively_not_fatal(self):
        """A1-A8 标签均非'剥夺诉讼权利/程序违法且可致发回重审'性质，保守不标 fatal。"""
        for cat in TAXONOMY:
            if cat.code == "A9":
                continue
            assert cat.fatal is False, f"{cat.code} 不应标记 fatal"

    def test_all_categories_have_fatal_field(self):
        for cat in TAXONOMY:
            assert isinstance(cat.fatal, bool)

    def test_is_fatal_helper(self):
        assert is_fatal(f_code="F-27", a_code="") is True
        assert is_fatal(f_code="", a_code="A9") is True
        assert is_fatal(f_code="F-28", a_code="A9") is True  # A9 fatal 主导
        assert is_fatal(f_code="", a_code="") is False
        assert is_fatal(f_code="F-01", a_code="A1") is False
        assert is_fatal(f_code="UNKNOWN", a_code="A1") is False

    def test_f_codes_registry_codes_valid(self):
        assert set(F_CODES) == {"F-27", "F-28"}
        for meta in F_CODES.values():
            assert meta.label
            assert 0.0 < meta.severity_base <= 1.0


# ── Red-Flag Banner in Report ────────────────────────────────


def _detection_result(items: list[AnomalyItem]) -> DetectionResult:
    return DetectionResult(
        case_name="（20XX）X民终XXXX号（占位）",
        doc_type="判决书",
        trial_stage="二审",
        model_name="AI Agent",
        detection_time="2026-10-26 00:00:00",
        dimension_results=[
            DimensionResult(
                dimension="claim_support",
                anomalies=items,
                risk_level="high",
                summary="诉请支持度检测发现遗漏诉请",
            )
        ],
    )


class TestRedFlagBanner:
    def setup_method(self):
        self.builder = ReportBuilder()

    def test_fatal_item_triggers_banner_at_top(self):
        report = self.builder.build_report(_detection_result([_fatal_item()]))
        assert "红旗预警" in report
        # 区块必须在报告最顶部（先于报告主标题）
        assert report.strip().startswith("# 🚩 红旗预警")
        assert report.index("红旗预警") < report.index("# 司法文书异常检测报告")

    def test_banner_lists_item_fields(self):
        report = self.builder.build_report(_detection_result([_fatal_item()]))
        assert "F-27" in report and "A9" in report
        assert "维度十七：诉请支持度与回应完整性" in report
        assert "遗漏诉讼请求" in report
        assert "原告" in report
        assert "高度" in report  # 置信度中文
        assert "原文引用" in report  # 原文摘录

    def test_banner_contains_omission_consequence_text(self):
        report = self.builder.build_report(_detection_result([_fatal_item()]))
        assert "存在二审撤销原判发回重审的强信号" in report
        assert "第一百七十七条第一款第四项" in report
        assert "任何综合评分不得掩盖上述信号" in report

    def test_banner_contains_final_verdict_line(self):
        report = self.builder.build_report(_detection_result([_fatal_item()]))
        assert "红旗终评：本报告异常等级按最高 fatal 项呈现" in report

    def test_banner_counts_multiple_fatal_items(self):
        items = [
            _fatal_item(),
            _fatal_item(
                item_name="变更诉请未审理",
                original_text="原文引用：庭审中增加的诉讼请求未审理（占位）",
            ),
        ]
        report = self.builder.build_report(_detection_result(items))
        assert "检出 2 项 fatal 级异常" in report

    def test_non_fatal_items_no_banner(self):
        non_fatal = AnomalyItem(
            dimension="procedure",
            item_name="程序瑕疵",
            description="送达时间记录不完整",
            beneficiary="原告",
            confidence="medium",
            f_code="F-01",
            a_code="A1",
            original_text="原文引用：送达回证缺失（占位）",
        )
        report = self.builder.build_report(_detection_result([non_fatal]))
        assert "红旗预警" not in report
        assert "# 司法文书异常检测报告" in report

    def test_empty_result_no_banner(self):
        report = self.builder.build_report(_detection_result([]))
        assert "红旗预警" not in report

    def test_fatal_by_f_code_alone(self):
        """仅 F 码 fatal（a_code 缺失）也应触发红旗。"""
        item = _fatal_item(a_code="")
        report = self.builder.build_report(_detection_result([item]))
        assert "红旗预警" in report


# ── server.build_report 开关 ─────────────────────────────────


class TestServerBuildReportSwitch:
    def _dim_data(self) -> str:
        return json.dumps([
            {
                "dimension": "claim_support",
                "anomalies": [{
                    "item_name": "遗漏诉讼请求",
                    "description": "某项诉讼请求未获审理（占位描述）",
                    "beneficiary": "原告",
                    "confidence": "high",
                    "f_code": "F-27",
                    "a_code": "A9",
                    "original_text": "原文引用：判决书对该项诉请未作回应（占位）",
                }],
                "risk_level": "high",
                "summary": "发现遗漏诉请",
            }
        ])

    def test_default_on_via_server_tool(self):
        report = build_report("（20XX）X民终XXXX号", self._dim_data())
        assert "红旗预警" in report
        assert "存在二审撤销原判发回重审的强信号" in report

    def test_switch_off_via_server_tool(self):
        report = build_report("（20XX）X民终XXXX号", self._dim_data(), red_flag_escalation=False)
        assert "红旗预警" not in report
        assert "# 司法文书异常检测报告" in report

    def test_html_report_inherits_banner(self):
        from judicial_lint_mcp.server import build_report_html

        html = build_report_html("（20XX）X民终XXXX号", self._dim_data())
        assert "红旗预警" in html
        assert "<!DOCTYPE html>" in html

    def test_builder_direct_default_is_on(self):
        result = _detection_result([_fatal_item()])
        assert "红旗预警" in server_module.ReportBuilder().build_report(result)


# ── D17 行政文书模式小节 ─────────────────────────────────────


class TestD17AdminMode:
    def test_admin_mode_section_exists(self):
        loader = SkillLoader()
        _, body = loader.load("dimensions/17_claim_support")
        assert "## 行政文书模式" in body

    def test_admin_mode_cites_norms(self):
        loader = SkillLoader()
        _, body = loader.load("dimensions/17_claim_support")
        assert "行政复议法" in body
        assert "第六十三条" in body
        assert "第六十四条" in body
        assert "行政诉讼法" in body
        assert "第七十条" in body and "第七十七条" in body

    def test_admin_mode_six_revocation_grounds(self):
        loader = SkillLoader()
        _, body = loader.load("dimensions/17_claim_support")
        grounds = [
            "主要证据不足", "适用法律法规错误", "违反法定程序",
            "超越职权", "滥用职权", "明显不当",
        ]
        for ground in grounds:
            assert ground in body, f"缺少撤销情形：{ground}"

    def test_admin_mode_file_on_disk(self):
        text = (SKILLS_DIR / "dimensions" / "17_claim_support.md").read_text(encoding="utf-8")
        assert "行政文书模式" in text
