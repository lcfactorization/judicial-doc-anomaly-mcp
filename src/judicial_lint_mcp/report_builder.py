"""Report builder — generate structured Markdown reports from detection results.

v0.5.0 bridge architecture: NO LLM calls.
Uses table-heavy format with GitHub Alerts style, concise summaries.
"""

import logging
import re
from datetime import datetime

from .models import DetectionResult, DimensionResult

logger = logging.getLogger(__name__)

_RISK_CN = {
    "low": "🟢 低风险",
    "medium": "🟡 中风险",
    "high": "🟠 高风险",
    "critical": "🔴 极高风险",
}

_CONFIDENCE_CN = {"high": "高度", "medium": "中度", "low": "低度", "critical": "极高"}

_DIM_LABELS = {
    "procedure": "维度一：程序操作与正当性",
    "evidence": "维度二：证据采信与审查标准",
    "fact_finding": "维度三：事实认定与关键情节",
    "focus_drift": "维度四：争议焦点偏移与遗漏",
    "law_application": "维度五：法律适用与推理链条",
    "discretion": "维度六：自由裁量权行使",
    "rhetoric_trick": "维度七：修辞手法与论证技巧",
    "logic": "维度八：逻辑闭环与论证自洽",
    "temporal": "维度九：时间线一致性",
    "trial_process": "维度十：庭审/听证/调查过程",
    "external_interference": "维度十一：外部干预与异常关联",
    "execution": "维度十二：执行阶段异常",
    "negative_space": "维度十三：缺失信息与负空间",
    "semantic_drift": "维度十四：语义漂移检测",
    "case_deviation": "维度十五：类案偏离量化",
    "coupling": "维度十六：惯性耦合判定",
}


class ReportBuilder:
    """Build structured Markdown reports from DetectionResult."""

    def build_report(self, result: DetectionResult) -> str:
        logger.info("build_report: 开始生成报告, 维度数=%d", len(result.dimension_results))

        total_anomalies = sum(len(r.anomalies) for r in result.dimension_results)
        high_count = sum(
            1 for r in result.dimension_results for a in r.anomalies if a.confidence == "high"
        )
        medium_count = sum(
            1 for r in result.dimension_results for a in r.anomalies if a.confidence == "medium"
        )
        low_count = total_anomalies - high_count - medium_count

        risk_level = self._assess_risk(result.dimension_results)
        risk_cn = _RISK_CN.get(risk_level, risk_level)
        logger.info(
            "build_report: 统计完成 total=%d, high=%d, medium=%d, low=%d, risk=%s",
            total_anomalies, high_count, medium_count, low_count, risk_level,
        )

        for r in result.dimension_results:
            for a in r.anomalies:
                logger.info(
                    "build_report: 维度=%s, 异常项=%s, beneficiary=%s, confidence=%s, f_code=%s",
                    r.dimension, a.item_name[:30], a.beneficiary, a.confidence, a.f_code,
                )

        report_id = datetime.now().strftime("%Y%m%d%H%M")

        parts = []

        parts.append(self._build_header(result, report_id, risk_cn, total_anomalies, high_count, medium_count, low_count))

        parts.append(self._build_overview_table(result.dimension_results))

        parts.append(self._build_anomaly_summary_table(result.dimension_results))

        parts.append(self._build_risk_alerts(risk_level, high_count, total_anomalies))

        parts.append(self._build_dimension_details(result.dimension_results))

        parts.append(self._build_conclusion(risk_level, total_anomalies, high_count, result.dimension_results))

        report = "\n\n".join(parts)
        logger.info("build_report: 报告生成完成, 总长度=%d", len(report))
        return report

    def _build_header(self, result, report_id, risk_cn, total, high, medium, low) -> str:
        lines = [
            f"# 司法文书异常检测报告",
            "",
            f"| 项目 | 内容 |",
            f"|------|------|",
            f"| 报告编号 | {report_id} |",
            f"| 案件名称 | {result.case_name} |",
            f"| 文书类型 | {result.doc_type} |",
            f"| 检测模型 | {result.model_name} |",
            f"| 检测时间 | {result.detection_time} |",
            f"| 风险等级 | {risk_cn} |",
            f"| 异常总数 | {total}（高度 {high} / 中度 {medium} / 低度 {low}）|",
            f"| 检测维度 | {len(result.dimension_results)} |",
            f"| 版本 | v0.5.0 Bridge Architecture |",
        ]
        return "\n".join(lines)

    def _build_overview_table(self, dimension_results: list[DimensionResult]) -> str:
        lines = [
            "## 维度总览",
            "",
            "| 维度 | 风险等级 | 异常数 | 高度 | 中度 | 低度 |",
            "|------|:---:|:---:|:---:|:---:|:---:|",
        ]

        for r in dimension_results:
            dim_cn = _DIM_LABELS.get(r.dimension, r.dimension)
            risk_cn = _RISK_CN.get(r.risk_level, r.risk_level)
            high = sum(1 for a in r.anomalies if a.confidence == "high")
            medium = sum(1 for a in r.anomalies if a.confidence == "medium")
            low = len(r.anomalies) - high - medium
            lines.append(f"| {dim_cn} | {risk_cn} | {len(r.anomalies)} | {high} | {medium} | {low} |")

        return "\n".join(lines)

    def _build_anomaly_summary_table(self, dimension_results: list[DimensionResult]) -> str:
        lines = [
            "## 异常项汇总",
            "",
            "| # | 维度 | 异常项 | 获益方 | F编号 | A分类 | 置信度 | 简要表现 |",
            "|:---:|------|------|:---:|:---:|:---:|:---:|------|",
        ]

        seq = 0
        for r in dimension_results:
            dim_cn = _DIM_LABELS.get(r.dimension, r.dimension)
            dim_short = dim_cn.replace("维度一：", "D1·").replace("维度二：", "D2·").replace("维度三：", "D3·").replace("维度四：", "D4·").replace("维度五：", "D5·").replace("维度六：", "D6·").replace("维度七：", "D7·").replace("维度八：", "D8·").replace("维度九：", "D9·").replace("维度十：", "D10·").replace("维度十一：", "D11·").replace("维度十二：", "D12·").replace("维度十三：", "D13·").replace("维度十四：", "D14·").replace("维度十五：", "D15·").replace("维度十六：", "D16·")
            for a in r.anomalies:
                seq += 1
                desc = a.description.replace("\n", " ").replace("|", "／")[:200]
                beneficiary = a.beneficiary or "—"
                f_code = a.f_code or "—"
                a_code = a.a_code or "—"
                conf_cn = _CONFIDENCE_CN.get(a.confidence, a.confidence)
                lines.append(
                    f"| {seq} | {dim_short} | {a.item_name[:50]} | {beneficiary} | {f_code} | {a_code} | {conf_cn} | {desc} |"
                )

        if seq == 0:
            lines.append("| - | - | 未发现异常 | - | - | - | - | - |")

        return "\n".join(lines)

    def _build_risk_alerts(self, risk_level: str, high_count: int, total: int) -> str:
        alerts = []

        if risk_level == "critical":
            alerts.append("> [!DANGER]")
            alerts.append(f"> 检出 {high_count} 项高置信度异常，风险等级极高，强烈建议启动程序内救济。")
        elif risk_level == "high":
            alerts.append("> [!WARNING]")
            alerts.append(f"> 检出 {high_count} 项高置信度异常，存在系统性偏差风险，建议优先审查。")

        if total > 5:
            alerts.append("> [!IMPORTANT]")
            alerts.append(f"> 异常项总数达 {total} 项，建议启动多维度联合审查。")

        if total == 0:
            alerts.append("> [!NOTE]")
            alerts.append("> 未检出显著异常，文书整体质量尚可。")

        return "\n".join(alerts) if alerts else ""

    def _build_dimension_details(self, dimension_results: list[DimensionResult]) -> str:
        parts = ["## 各维度详细检测"]

        for r in dimension_results:
            dim_cn = _DIM_LABELS.get(r.dimension, r.dimension)
            risk_cn = _RISK_CN.get(r.risk_level, r.risk_level)

            parts.append(f"\n### {dim_cn}\n")
            parts.append(f"**风险等级**：{risk_cn}  |  **异常项数**：{len(r.anomalies)}\n")

            if not r.anomalies:
                parts.append("> [!NOTE]")
                parts.append("> 本维度未发现显著异常。")
                continue

            parts.append("| # | 异常项 | 获益方 | F编号 | A分类 | 置信度 |")
            parts.append("|:---:|------|:---:|:---:|:---:|:---:|")
            for i, a in enumerate(r.anomalies, 1):
                conf_cn = _CONFIDENCE_CN.get(a.confidence, a.confidence)
                parts.append(
                    f"| {i} | {a.item_name[:60]} | {a.beneficiary or '—'} | {a.f_code or '—'} | {a.a_code or '—'} | {conf_cn} |"
                )
            parts.append("")

            if r.risk_level in ("high", "critical"):
                summary = r.summary[:300] if r.summary else ""
                summary = re.sub(r"[#*]", "", summary).strip()
                summary = re.sub(r"^维度[一二三四五六七八九十]+[：:]\s*", "", summary)
                summary = re.sub(r"^(审查报告|检测报告|总结|综合结论)[：:]*\s*", "", summary)
                summary = summary.replace("\n", " ")
                if summary:
                    parts.append("> [!WARNING]")
                    parts.append(f"> 本维度存在 {len(r.anomalies)} 项异常，风险等级{risk_cn}。{summary}")
                    parts.append("")

            for i, a in enumerate(r.anomalies, 1):
                parts.append(f"**{i}. {a.item_name}**\n")
                if a.description:
                    parts.append(f"- **具体表现**：{a.description}")
                if a.original_text:
                    original = a.original_text.replace("\n", "\n> ")
                    parts.append(f"- **原文引用**：\n> {original}")
                if a.legal_analysis:
                    parts.append(f"- **法理分析**：{a.legal_analysis}")
                parts.append("")

        return "\n".join(parts)

    def _build_conclusion(self, risk_level: str, total: int, high: int, dimension_results: list[DimensionResult]) -> str:
        parts = ["## 总结\n"]

        risk_cn = _RISK_CN.get(risk_level, risk_level)
        parts.append(f"**综合风险等级**：{risk_cn}\n")

        high_dims = [
            _DIM_LABELS.get(r.dimension, r.dimension)
            for r in dimension_results
            if r.risk_level in ("high", "critical")
        ]

        if high_dims:
            parts.append("> [!IMPORTANT]")
            parts.append(f"> 高风险维度：{', '.join(high_dims)}")
            parts.append("")

        beneficiary_stats = {}
        for r in dimension_results:
            for a in r.anomalies:
                b = a.beneficiary or "未标注"
                beneficiary_stats[b] = beneficiary_stats.get(b, 0) + 1

        if beneficiary_stats:
            parts.append("**获益方分布**：\n")
            parts.append("| 获益方 | 异常数 | 占比 |")
            parts.append("|------|:---:|:---:|")
            for b, count in sorted(beneficiary_stats.items(), key=lambda x: -x[1]):
                pct = f"{count / total * 100:.0f}%" if total > 0 else "0%"
                parts.append(f"| {b} | {count} | {pct} |")
            parts.append("")

        if risk_level in ("high", "critical"):
            parts.append("> [!DANGER]")
            parts.append("> 综合评估：文书存在显著异常，建议启动程序内救济（上诉/再审/检察监督）。")
        elif risk_level == "medium":
            parts.append("> [!WARNING]")
            parts.append("> 综合评估：文书存在一定异常，建议进一步审查关键维度。")
        else:
            parts.append("> [!NOTE]")
            parts.append("> 综合评估：文书整体质量尚可，未发现显著异常。")

        return "\n".join(parts)

    @staticmethod
    def _assess_risk(dimension_results: list[DimensionResult]) -> str:
        high_dims = sum(1 for r in dimension_results if r.risk_level in ("high", "critical"))
        total_high = sum(
            1 for r in dimension_results for a in r.anomalies if a.confidence == "high"
        )

        if high_dims >= 3 or total_high >= 5:
            return "critical"
        if high_dims >= 1 or total_high >= 2:
            return "high"
        if any(r.anomalies for r in dimension_results):
            return "medium"
        return "low"
