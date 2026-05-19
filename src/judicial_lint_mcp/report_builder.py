"""Report builder — generate structured Markdown reports from detection results.

v0.5.1 bridge architecture: NO LLM calls.
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
            f"| 版本 | v0.5.1 Bridge Architecture |",
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
                conf_cn = _CONFIDENCE_CN.get(a.confidence, a.confidence)
                parts.append(f"**{i}. {a.item_name}**（置信度：{conf_cn}）\n")

                if a.description:
                    parts.append(f"- **具体表现**：{a.description}")

                location = a.original_text_location or a.original_text
                if location:
                    location = location.replace("\n", "\n> ")
                    parts.append(f"- **原文定位**：\n> {location}")

                if a.evidence_reference:
                    parts.append(f"- **证据对照**：{a.evidence_reference}")

                if a.legal_basis:
                    parts.append(f"- **法律依据**：{a.legal_basis}")

                if a.legal_analysis:
                    parts.append(f"- **法理分析**：{a.legal_analysis}")

                if a.beneficiary:
                    parts.append(f"- **指向获益方**：{a.beneficiary}")

                if a.f_code or a.a_code:
                    code_parts = []
                    if a.f_code:
                        code_parts.append(f"F编号：{a.f_code}")
                    if a.a_code:
                        code_parts.append(f"A分类：{a.a_code}")
                    parts.append(f"- **编码**：{'，'.join(code_parts)}")

                if a.deduction and a.deduction > 0:
                    parts.append(f"- **扣分**：-{a.deduction}")

                if a.alternative_explanation:
                    parts.append(f"- **替代解释**：{a.alternative_explanation}")

                if a.q1_alternative or a.q2_subjective_intent or a.q3_contradictory_evidence:
                    parts.append("")
                    parts.append("> [!IMPORTANT]")
                    parts.append("> **对抗校验**：")
                    if a.q1_alternative:
                        parts.append(f"> - Q1（替代解释）：{a.q1_alternative}")
                    if a.q2_subjective_intent:
                        parts.append(f"> - Q2（排除主观故意）：{a.q2_subjective_intent}")
                    if a.q3_contradictory_evidence:
                        parts.append(f"> - Q3（相反证据）：{a.q3_contradictory_evidence}")
                    if a.conclusion:
                        parts.append(f"> - 校验结论：{a.conclusion}")
                    if a.net_anomaly:
                        parts.append(f"> - 净异常判定：{a.net_anomaly}")

                if a.suggestion:
                    parts.append("")
                    parts.append("> [!TIP]")
                    sug = a.suggestion.replace("\n", "\n> ")
                    parts.append(f"> **修复建议**：{sug}")

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

    def build_html_report(self, result: DetectionResult) -> str:
        md_content = self.build_report(result)
        report_id = datetime.now().strftime("%Y%m%d%H%M")
        html_body = _md_to_rich_html(md_content)
        return _build_html_page(html_body, report_id)


def _md_to_rich_html(md_text: str) -> str:
    lines = md_text.split("\n")
    html_parts = []
    in_table = False
    table_rows = []
    table_aligns = []
    in_blockquote = False
    bq_type = ""
    bq_lines = []

    def _parse_align(sep_line):
        parts = [c.strip() for c in sep_line.split("|")[1:-1]]
        aligns = []
        for p in parts:
            p = p.strip()
            if p.startswith(":") and p.endswith(":"):
                aligns.append("center")
            elif p.endswith(":"):
                aligns.append("right")
            else:
                aligns.append("left")
        return aligns

    def close_blockquote():
        nonlocal in_blockquote, bq_type, bq_lines
        if not in_blockquote:
            return
        css_class = {
            "NOTE": "alert-note", "TIP": "alert-tip", "IMPORTANT": "alert-important",
            "WARNING": "alert-warning", "DANGER": "alert-danger", "CAUTION": "alert-caution",
        }.get(bq_type, "alert-note")
        icon = {
            "NOTE": "ℹ️", "TIP": "💡", "IMPORTANT": "❗",
            "WARNING": "⚠️", "DANGER": "🔴", "CAUTION": "🔴",
        }.get(bq_type, "ℹ️")
        inner = "<br>\n".join(bq_lines)
        html_parts.append(
            f'<div class="github-alert {css_class}">'
            f'<div class="alert-header">{icon} {bq_type}</div>'
            f'<div class="alert-body">{inner}</div></div>'
        )
        in_blockquote = False
        bq_type = ""
        bq_lines = []

    def close_table():
        nonlocal in_table, table_rows, table_aligns
        if not in_table:
            return
        html_parts.append('<div class="table-wrapper"><table>')
        for ri, row in enumerate(table_rows):
            tag = "th" if ri == 0 else "td"
            cells = [re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', c) for c in row]
            row_html = ""
            for ci, cell in enumerate(cells):
                align = table_aligns[ci] if ci < len(table_aligns) else "left"
                style = f' style="text-align:{align}"'
                row_html += f"<{tag}{style}>{cell}</{tag}>"
            html_parts.append(f"<tr>{row_html}</tr>")
        html_parts.append("</table></div>")
        in_table = False
        table_rows = []
        table_aligns = []

    def inline_format(text):
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        return text

    for line in lines:
        stripped = line.strip()

        bq_match = re.match(r'^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|DANGER|CAUTION)\]', stripped)
        if bq_match:
            close_blockquote()
            close_table()
            in_blockquote = True
            bq_type = bq_match.group(1)
            bq_lines = []
            continue

        if in_blockquote:
            if stripped.startswith(">"):
                content = re.sub(r'^>\s?', '', stripped)
                bq_lines.append(inline_format(content))
                continue
            else:
                close_blockquote()

        if stripped.startswith("|") and "|" in stripped[1:]:
            sep_match = re.match(r'^\|[\s:|-]+\|$', stripped)
            if sep_match:
                table_aligns = _parse_align(stripped)
                continue
            if not in_table:
                close_table()
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            table_rows.append(cells)
            in_table = True
            continue
        else:
            close_table()

        if stripped.startswith("#### "):
            html_parts.append(f'<h4>{inline_format(stripped[5:])}</h4>')
        elif stripped.startswith("### "):
            html_parts.append(f'<h3>{inline_format(stripped[4:])}</h3>')
        elif stripped.startswith("## "):
            html_parts.append(f'<h2>{inline_format(stripped[3:])}</h2>')
        elif stripped.startswith("# "):
            html_parts.append(f'<h1>{inline_format(stripped[2:])}</h1>')
        elif stripped == "---":
            html_parts.append("<hr>")
        elif stripped.startswith("- "):
            html_parts.append(f'<ul><li>{inline_format(stripped[2:])}</li></ul>')
        elif stripped == "":
            html_parts.append("")
        else:
            html_parts.append(f'<p>{inline_format(stripped)}</p>')

    close_blockquote()
    close_table()

    merged = "\n".join(html_parts)
    merged = re.sub(r'</ul>\s*<ul>', '', merged)
    merged = re.sub(r'<p>\s*</p>', '', merged)
    return merged


def _build_html_page(body_html: str, report_id: str) -> str:
    return f'''<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>司法文书异常检测报告 {report_id}</title>
<style>
:root {{
  --bg-primary: #0d1117;
  --bg-secondary: #161b22;
  --bg-tertiary: #21262d;
  --bg-card: #1c2128;
  --text-primary: #e6edf3;
  --text-secondary: #8b949e;
  --text-muted: #6e7681;
  --border-color: #30363d;
  --accent-blue: #58a6ff;
  --accent-green: #3fb950;
  --accent-yellow: #d29922;
  --accent-orange: #db6d28;
  --accent-red: #f85149;
  --accent-purple: #bc8cff;
  --link-color: #58a6ff;
  --code-bg: #161b22;
  --table-stripe: rgba(110,118,129,0.1);
  --shadow: 0 2px 8px rgba(0,0,0,0.3);
}}
[data-theme="light"] {{
  --bg-primary: #ffffff;
  --bg-secondary: #f6f8fa;
  --bg-tertiary: #eaeef2;
  --bg-card: #ffffff;
  --text-primary: #1f2328;
  --text-secondary: #656d76;
  --text-muted: #8c959f;
  --border-color: #d0d7de;
  --accent-blue: #0969da;
  --accent-green: #1a7f37;
  --accent-yellow: #9a6700;
  --accent-orange: #bc4c00;
  --accent-red: #cf222e;
  --accent-purple: #8250df;
  --link-color: #0969da;
  --code-bg: #f6f8fa;
  --table-stripe: rgba(175,184,193,0.15);
  --shadow: 0 2px 8px rgba(0,0,0,0.08);
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  line-height: 1.75;
  padding: 0;
  -webkit-font-smoothing: antialiased;
}}
.theme-toggle {{
  position: fixed; top: 16px; right: 24px; z-index: 1000;
  background: var(--bg-tertiary); border: 1px solid var(--border-color);
  color: var(--text-primary); padding: 8px 16px; border-radius: 20px;
  cursor: pointer; font-size: 14px; transition: all 0.2s;
  box-shadow: var(--shadow);
}}
.theme-toggle:hover {{ background: var(--accent-blue); color: #fff; }}
.report-container {{
  max-width: 960px; margin: 0 auto; padding: 40px 32px 80px;
}}
h1 {{
  font-size: 1.75em; font-weight: 700; margin: 32px 0 16px;
  padding-bottom: 12px; border-bottom: 2px solid var(--accent-red);
  color: var(--text-primary);
}}
h2 {{
  font-size: 1.4em; font-weight: 600; margin: 28px 0 14px;
  padding-bottom: 8px; border-bottom: 1px solid var(--border-color);
  color: var(--accent-blue);
}}
h3 {{
  font-size: 1.15em; font-weight: 600; margin: 20px 0 10px;
  color: var(--text-primary);
}}
h4 {{
  font-size: 1.05em; font-weight: 600; margin: 16px 0 8px;
  color: var(--text-secondary);
}}
p {{ margin: 8px 0; color: var(--text-primary); }}
strong {{ color: var(--text-primary); font-weight: 600; }}
em {{ color: var(--text-secondary); }}
code {{
  background: var(--code-bg); padding: 2px 6px; border-radius: 4px;
  font-size: 0.9em; font-family: "Cascadia Code", "Fira Code", monospace;
  border: 1px solid var(--border-color);
}}
a {{ color: var(--link-color); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
hr {{
  border: none; border-top: 1px solid var(--border-color);
  margin: 24px 0;
}}
ul {{ margin: 8px 0 8px 24px; }}
li {{ margin: 4px 0; }}
.table-wrapper {{
  overflow-x: auto; margin: 16px 0;
  border: 1px solid var(--border-color); border-radius: 8px;
  box-shadow: var(--shadow);
}}
table {{
  width: 100%; border-collapse: collapse; font-size: 0.9em;
}}
th {{
  background: var(--bg-tertiary); color: var(--text-primary);
  font-weight: 600; text-align: left; padding: 10px 14px;
  border-bottom: 2px solid var(--border-color); white-space: nowrap;
}}
td {{
  padding: 9px 14px; border-bottom: 1px solid var(--border-color);
  color: var(--text-primary); vertical-align: top;
}}
tr:nth-child(even) td {{ background: var(--table-stripe); }}
tr:hover td {{ background: rgba(88,166,255,0.08); }}
.github-alert {{
  border-radius: 8px; padding: 16px 20px; margin: 16px 0;
  border-left: 4px solid; box-shadow: var(--shadow);
}}
.alert-note {{
  background: rgba(88,166,255,0.1); border-color: var(--accent-blue);
}}
.alert-tip {{
  background: rgba(63,185,80,0.1); border-color: var(--accent-green);
}}
.alert-important {{
  background: rgba(188,140,255,0.1); border-color: var(--accent-purple);
}}
.alert-warning {{
  background: rgba(210,153,34,0.1); border-color: var(--accent-yellow);
}}
.alert-danger {{
  background: rgba(248,81,73,0.15); border-color: var(--accent-red);
}}
.alert-caution {{
  background: rgba(248,81,73,0.15); border-color: var(--accent-red);
}}
.alert-header {{
  font-weight: 700; font-size: 0.95em; margin-bottom: 6px;
  text-transform: uppercase; letter-spacing: 0.5px;
}}
.alert-note .alert-header {{ color: var(--accent-blue); }}
.alert-tip .alert-header {{ color: var(--accent-green); }}
.alert-important .alert-header {{ color: var(--accent-purple); }}
.alert-warning .alert-header {{ color: var(--accent-yellow); }}
.alert-danger .alert-header {{ color: var(--accent-red); }}
.alert-caution .alert-header {{ color: var(--accent-red); }}
.alert-body {{ color: var(--text-primary); font-size: 0.93em; line-height: 1.7; }}
.risk-badge {{
  display: inline-block; padding: 4px 14px; border-radius: 16px;
  font-weight: 700; font-size: 1.1em; margin: 4px 2px;
}}
.risk-critical {{ background: rgba(248,81,73,0.2); color: var(--accent-red); }}
.risk-high {{ background: rgba(219,109,40,0.2); color: var(--accent-orange); }}
.risk-medium {{ background: rgba(210,153,34,0.2); color: var(--accent-yellow); }}
.risk-low {{ background: rgba(63,185,80,0.2); color: var(--accent-green); }}
.footer {{
  margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--border-color);
  color: var(--text-muted); font-size: 0.85em; text-align: center;
}}
@media (max-width: 768px) {{
  .report-container {{ padding: 20px 16px 60px; }}
  .theme-toggle {{ top: 8px; right: 12px; padding: 6px 12px; font-size: 12px; }}
  table {{ font-size: 0.82em; }}
  th, td {{ padding: 6px 8px; }}
}}
@media print {{
  .theme-toggle {{ display: none; }}
  body {{ background: #fff; color: #000; }}
  .github-alert {{ break-inside: avoid; }}
  .table-wrapper {{ box-shadow: none; }}
}}
</style>
</head>
<body>
<button class="theme-toggle" onclick="toggleTheme()" id="themeBtn">☀️ Light</button>
<div class="report-container">
{body_html}
<div class="footer">
<p>司法文书异常检测报告 · v0.5.1 Bridge Architecture · {report_id}</p>
<p>本报告由 AI 辅助生成，仅供参考，不构成法律意见。</p>
</div>
</div>
<script>
(function(){{
  var s=localStorage.getItem("report-theme");
  if(s)document.documentElement.setAttribute("data-theme",s);
  updateBtn();
}})();
function toggleTheme(){{
  var h=document.documentElement;
  var cur=h.getAttribute("data-theme");
  var next=cur==="dark"?"light":"dark";
  h.setAttribute("data-theme",next);
  localStorage.setItem("report-theme",next);
  updateBtn();
}}
function updateBtn(){{
  var b=document.getElementById("themeBtn");
  var d=document.documentElement.getAttribute("data-theme");
  b.textContent=d==="dark"?"☀️ Light":"🌙 Dark";
}}
</script>
</body>
</html>'''
