"""Response parser — extract structured anomaly items from LLM/Agent responses.

v0.5.0 bridge architecture: simplified terminology handling.
Removes hardcoded beneficiary normalization — Agent/LLM handles terminology
based on document context (仲裁/一审/二审/行政执法).
Only keeps core text parsing logic.
"""

import logging
import re

from .models import AnomalyItem, DimensionResult

logger = logging.getLogger(__name__)


class ResponseParser:
    """Parse LLM/Agent responses into structured DimensionResult objects."""

    _FIELD_BOUNDARY = r"\n\*\s+\*\*"
    _FIELD_BOUNDARY_ALT = (
        r"\n-\s+\*\*(?:原文引用|原文定位|指向获益方|获益方|异常程度|置信度|法理分析|具体表现|异常表现)"
    )

    def parse_dimension_result(self, dim: str, response: str, dim_index: int = 0) -> DimensionResult:
        logger.info("parse_dimension_result: 维度 %s, dim_index=%d, 响应长度=%d", dim, dim_index, len(response))

        result = DimensionResult(dimension=dim)

        sections = re.split(r"\n####\s+\*?\*?\d+\.?\s*", response)
        logger.info("parse_dimension_result: 维度 %s, ####分割段数=%d", dim, len(sections))
        if len(sections) < 2:
            sections = re.split(r"\n###\s+", response)
            logger.info("parse_dimension_result: 维度 %s, ###分割段数=%d", dim, len(sections))

        if len(sections) < 2:
            sections = re.split(r"\n(?=异常项[：:])", response)
            logger.info("parse_dimension_result: 维度 %s, 异常项分割段数=%d", dim, len(sections))

        for section in sections[1:]:
            section = section.strip()
            if not section or len(section) < 20:
                continue

            first_line_clean = re.sub(r"[#*]", "", section.split("\n")[0]).strip()
            if re.match(r"^(总结|综合结论|总体评价|审查报告$|建议$)", first_line_clean):
                continue

            anomaly = AnomalyItem(dimension=dim)

            header_match = re.match(r"异常项[：:]\s*(.+?)(?:\*?\*?\s*$)", section)
            if header_match:
                anomaly.item_name = header_match.group(1).strip().rstrip("*").strip()
            else:
                first_line = section.split("\n")[0].strip()
                first_line = re.sub(r"^[#*]+\s*", "", first_line)
                first_line = re.sub(r"\*+$", "", first_line).strip()
                first_line = re.sub(r"^维度[一二三四五六七八九十]+[：:]\s*", "", first_line)
                first_line = re.sub(r"^异常项[：:]\s*", "", first_line)
                first_line = re.sub(r"^\d+[\.、]\s*", "", first_line)
                if re.match(r"^(总结|综合结论|总体评价|审查报告)", first_line):
                    first_line = first_line.rstrip("报告").strip()
                anomaly.item_name = first_line[:60]

            anomaly.description = self._extract_field(section, r"具体表现\*?\*?[：:]", 3000)
            if not anomaly.description:
                anomaly.description = self._extract_field(section, r"异常表现\*?\*?[：:]", 3000)

            meta = self._parse_meta_line(section)
            if meta.get("confidence"):
                anomaly.confidence = self._map_confidence(meta["confidence"])
            else:
                confidence_text = self._extract_field(section, r"异常程度\*?\*?[：:]", 100)
                anomaly.confidence = self._map_confidence(confidence_text)

            anomaly.legal_analysis = self._extract_field(section, r"法理分析\*?\*?[：:]", 3000)

            anomaly.original_text = self._extract_field(section, r"原文(?:引用|定位)\*?\*?[：:]", 2000)

            if meta.get("beneficiary"):
                anomaly.beneficiary = meta["beneficiary"].strip()[:30]
            else:
                beneficiary_text = self._extract_field(section, r"(?:指向)?获益方\*?\*?[：:]", 200)
                anomaly.beneficiary = beneficiary_text.strip()[:30] if beneficiary_text else ""

            if meta.get("f_code"):
                anomaly.f_code = meta["f_code"]
            else:
                anomaly.f_code = self._infer_f_code(section)

            if meta.get("a_code"):
                anomaly.a_code = meta["a_code"]
            else:
                anomaly.a_code = self._infer_a_code(anomaly.item_name + " " + anomaly.description)

            anomaly.reverse_check = ""
            anomaly.net_anomaly = ""

            logger.info(
                "parse_dimension_result: 维度 %s, 异常项 #%d, name=%s, beneficiary=%s, confidence=%s, f_code=%s, a_code=%s",
                dim, len(result.anomalies) + 1, anomaly.item_name[:30], anomaly.beneficiary, anomaly.confidence, anomaly.f_code, anomaly.a_code,
            )

            result.anomalies.append(anomaly)

        if not result.anomalies:
            result.anomalies.append(
                AnomalyItem(
                    dimension=dim,
                    item_name=f"{dim} 维度检测结果",
                    description=response[:2000],
                    confidence="medium",
                )
            )

        paragraphs = [p.strip() for p in response.split("\n\n") if p.strip()]
        summary_candidates = []
        for p in paragraphs:
            cleaned = re.sub(r"[#*]", "", p).strip()
            if re.match(r"^(好的|作为|我将|我已|以下是|根据|基于|经检测|经审查)", cleaned):
                continue
            if len(cleaned) < 20:
                continue
            summary_candidates.append(p)
            break
        result.summary = (
            summary_candidates[0][:300]
            if summary_candidates
            else (paragraphs[0][:300] if paragraphs else response[:200])
        )

        high_count = sum(1 for a in result.anomalies if a.confidence == "high")
        if high_count >= 3:
            result.risk_level = "critical"
        elif high_count >= 1:
            result.risk_level = "high"
        elif result.anomalies:
            result.risk_level = "medium"

        logger.info(
            "parse_dimension_result: 维度 %s 解析完成, 异常项=%d, 风险=%s",
            dim, len(result.anomalies), result.risk_level,
        )

        return result

    def _parse_meta_line(self, text: str) -> dict:
        result = {}
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            a_m = re.search(r"\*\*A分类\*\*[：:]\s*(\S+)", line)
            if a_m:
                result["a_code"] = a_m.group(1).strip()
            f_m = re.search(r"\*\*F编号\*\*[：:]\s*([Ff][-‐]\d{2})", line)
            if f_m:
                result["f_code"] = f_m.group(1).strip()
            c_m = re.search(r"\*\*置信度\*\*[：:]\s*([^*|\n]+)", line)
            if c_m:
                result["confidence"] = c_m.group(1).strip()
            b_m = re.search(r"\*\*(?:指向)?获益方\*\*[：:]\s*(.+?)(?:\*\*|\n|$)", line)
            if b_m:
                result["beneficiary"] = b_m.group(1).strip()
            b_m2 = re.search(r"-\s+\*?\*?(?:指向)?获益方\*?\*?[：:]\s*(.+?)(?:\*?\*?|\n|$)", line)
            if b_m2 and "beneficiary" not in result:
                result["beneficiary"] = b_m2.group(1).strip()
        return result

    def _extract_field(self, text: str, pattern: str, max_len: int = 2000) -> str:
        boundary = rf"(?={self._FIELD_BOUNDARY}|{self._FIELD_BOUNDARY_ALT}|\n####|\n###|\Z)"
        m = re.search(rf"{pattern}\s*\n?(.+?){boundary}", text, re.DOTALL)
        if not m:
            m = re.search(rf"{pattern}\s*(.+?){boundary}", text, re.DOTALL)
        if m:
            value = m.group(1).strip()
            value = re.sub(r"\n\*\s+", "\n", value)
            value = re.sub(r"\*{1,3}", "", value)
            value = re.sub(r"\n{3,}", "\n\n", value)
            return value[:max_len]
        return ""

    @staticmethod
    def _map_confidence(text: str) -> str:
        if not text:
            return "medium"
        t = text.lower()
        if "确定" in t:
            return "high"
        if "高度可能" in t:
            return "high"
        if "可能" in t:
            return "medium"
        if "疑似" in t:
            return "low"
        return "medium"

    @staticmethod
    def _infer_f_code(text: str) -> str:
        f_patterns = [
            (r"举证责任.{0,5}(?:分配|倒置|转移)", "F-24"),
            (r"无证据支撑|找不到.*证据|没有.*证据", "F-01"),
            (r"孤证|单一证据", "F-03"),
            (r"前后矛盾|相互矛盾", "F-04"),
            (r"时间线|时间.*混乱|时间.*错误", "F-05"),
            (r"金额.*错误|主体.*错误|认定.*错误", "F-06"),
            (r"证人.*陈述|证人.*证言", "F-07"),
            (r"利害关系.*证言|利害关系人", "F-08"),
            (r"弱证据|拔高.*效力", "F-09"),
            (r"瑕疵.*采信|瑕疵.*证据", "F-10"),
            (r"逾期.*证据|超过.*举证", "F-11"),
            (r"无原件|复印件.*定案", "F-12"),
            (r"来源违法|违法.*证据", "F-13"),
            (r"只字不提|完全.*未提及|未.*提及", "F-14"),
            (r"原件.*无视|原件.*不采信", "F-15"),
            (r"未说明理由.*不采信|不予采信.*理由", "F-16"),
            (r"未经质证", "F-17"),
            (r"只看.*对方|不审查.*抗辩", "F-18"),
            (r"与本案无关.*排除", "F-19"),
            (r"推定.*代替|以推定", "F-20"),
            (r"未否认.*认可|沉默.*认可", "F-21"),
            (r"因果倒置|因果.*混淆", "F-22"),
            (r"选择性引用|仅引用.*有利", "F-23"),
            (r"证明标准", "F-25"),
            (r"举证期限.*双标|举证期限.*不同", "F-26"),
            (r"双重标准|双标|采信标准不一|审查标准不一", "F-10"),
            (r"程序.*违法|程序.*异常|送达.*异常|辩论权|质证权|管辖权", "F-17"),
            (r"回避.*争[议点]|焦点.*偏移|核心.*回避", "F-14"),
            (r"模板化|模板.*论证|机械.*复制", "A7"),
        ]
        for pattern, code in f_patterns:
            if re.search(pattern, text):
                return code
        return ""

    @staticmethod
    def _infer_a_code(text: str) -> str:
        a_mappings = [
            (r"未回应|未予回应|未.*评述|未.*采信|关键证据.*未", "A1"),
            (r"事实认定.*跳跃|推理.*断裂|中间环节.*缺失|论证.*缺失", "A2"),
            (r"法律适用.*未解释|未说明.*为何适用|法条.*未说明", "A3"),
            (r"双重标准|双标|采信标准不一|审查标准不一|同类证据.*不同", "A4"),
            (r"程序.*时间.*异常|时间.*逆序|超期|加速.*审结|审限", "A5"),
            (r"回避.*争[议点]|焦点.*偏移|核心.*回避|虚化", "A6"),
            (r"模板化|模板.*论证|机械.*复制|通用模板", "A7"),
            (r"举证责任.*倒置|举证责任.*转移|举证责任.*分配.*错误", "A8"),
        ]
        for pattern, code in a_mappings:
            if re.search(pattern, text):
                return code
        return ""
