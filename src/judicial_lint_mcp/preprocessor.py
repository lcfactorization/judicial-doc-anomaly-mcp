"""Phase 0-1: Structured preprocessing for judicial documents

Handles material loading, completeness scoring, timeline construction,
evidence indexing, and claims mapping.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import MATERIAL_PRIORITY
from .llm_caller import LLMCaller
from .prompts import PREPROCESSOR_PROMPT

logger = logging.getLogger(__name__)


@dataclass
class CaseInfo:
    case_number: str = ""
    case_name: str = ""
    parties: list[str] = field(default_factory=list)
    case_type: str = ""
    cause_of_action: str = ""
    judgment_result: str = ""
    court: str = ""
    judge_date: str = ""


@dataclass
class TimelineEntry:
    date: str
    event: str
    source: str
    source_type: str = ""


@dataclass
class EvidenceEntry:
    evidence_id: str
    evidence_type: str
    submitted_by: str
    description: str
    proof_object: str = ""
    cross_exam_status: str = ""
    admission_status: str = ""


@dataclass
class ClaimEntry:
    claim_id: str
    party: str
    claim_content: str
    evidence_refs: list[str] = field(default_factory=list)
    response_status: str = ""


@dataclass
class PreprocessResult:
    case_info: CaseInfo = field(default_factory=CaseInfo)
    completeness_score: float = 0.0
    timeline: list[TimelineEntry] = field(default_factory=list)
    evidence_index: list[EvidenceEntry] = field(default_factory=list)
    claims_map: list[ClaimEntry] = field(default_factory=list)
    missing_items: list[str] = field(default_factory=list)
    materials_text: str = ""
    raw_llm_output: str = ""


class Preprocessor:
    def __init__(self, llm_caller: LLMCaller):
        self.llm_caller = llm_caller

    def _load_materials(self, case_dir: str) -> dict[str, str]:
        materials = {}
        case_path = Path(case_dir)
        if not case_path.exists():
            return materials
        skipped = []
        for file_path in sorted(case_path.rglob("*")):
            if file_path.is_file() and file_path.suffix.lower() in (
                ".md",
                ".txt",
                ".pdf",
            ):
                name_lower = file_path.name.lower()
                if any(kw in name_lower for kw in (
                    "report", "检测报告", "异常检测", "评估报告",
                    "deepseek_markdown", "阅卷",
                )):
                    skipped.append(file_path.name)
                    logger.info("Preprocessor: 跳过文件 %s（匹配排除关键词）", file_path.name)
                    continue
                try:
                    content = file_path.read_text(encoding="utf-8")
                    materials[file_path.name] = content
                    logger.info("Preprocessor: 加载材料 %s（%d 字符）", file_path.name, len(content))
                except Exception:
                    pass
        if skipped:
            logger.info("Preprocessor: 共跳过 %d 个文件: %s", len(skipped), ", ".join(skipped))
        logger.info("Preprocessor: 共加载 %d 个案件材料", len(materials))
        return materials

    def _calculate_completeness(self, materials: dict[str, str]) -> float:
        if not materials:
            return 0.0
        all_text = " ".join(list(materials.keys()) + list(materials.values())).lower()
        total_weight = 0.0
        achieved_weight = 0.0
        weight_map = {
            "required": 50,
            "strongly_recommended": 30,
            "recommended": 20,
        }
        keyword_map = {
            "核心文书全文": ["判决书", "裁定书", "裁决书", "决定书"],
            "起诉状/答辩状/上诉状/申请书/投诉书": [
                "起诉状",
                "答辩状",
                "上诉状",
                "申请书",
                "投诉书",
            ],
            "双方证据清单及证据内容摘要/全文": ["证据清单", "证据目录", "证据材料"],
            "庭审/听证/调查笔录": ["庭审笔录", "听证笔录", "调查笔录"],
            "程序性裁定/通知/决定": ["裁定", "通知", "决定"],
            "时间线材料": ["时间线", "时间轴", "年月日"],
            "案件背景与外部信息说明": ["背景", "说明"],
        }
        for priority, items in MATERIAL_PRIORITY.items():
            weight_per_item = weight_map[priority] / max(len(items), 1)
            for item in items:
                total_weight += weight_per_item
                keywords = keyword_map.get(item, [item])
                if any(kw in all_text for kw in keywords):
                    achieved_weight += weight_per_item
        if total_weight == 0:
            return 0.0
        return min((achieved_weight / total_weight) * 100, 100.0)

    def _extract_timeline(self, text: str) -> list[TimelineEntry]:
        entries = []
        date_pattern = re.compile(r"(\d{4})[年/\-\.](\d{1,2})[月/\-\.](\d{1,2})[日号]?")
        for match in date_pattern.finditer(text):
            year, month, day = match.groups()
            date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 80)
            context = text[start:end].strip()
            entries.append(TimelineEntry(date=date_str, event=context, source="文书"))
        return entries

    async def run(self, case_dir: str) -> PreprocessResult:
        materials = self._load_materials(case_dir)
        if not materials:
            return PreprocessResult(missing_items=["未找到任何案件材料"])

        for name in materials:
            if "上诉状" in name:
                logger.info("Preprocessor: 检测到上诉状 '%s'，视为原告判后补充说明处理", name)
                materials[name] = (
                    "【重要说明：以下文件名为'上诉状'，但在本检测中仅作为原告的判后补充说明使用，"
                    "相当于原告对一审判决的答疑和补充陈述。\n"
                    "阅读本文件时必须遵守以下规则：\n"
                    "1. 文件中的'上诉人'即一审'原告'，'被上诉人'即一审'被告'\n"
                    "2. 分析时必须使用一审术语（原告/被告），严禁使用二审术语（上诉人/被上诉人）\n"
                    "3. 本文件中提及的证据编号和证据内容，应结合证据清单确认归属方\n"
                    "4. 本文件中对一审判决的驳斥和日期矛盾部分可忽略，仅提取事实和证据补充信息】\n"
                    + materials[name]
                )

        materials_text = "\n\n---\n\n".join(
            f"## {name}\n{content}" for name, content in materials.items()
        )

        completeness_score = self._calculate_completeness(materials)
        timeline = self._extract_timeline(materials_text)

        prompt = PREPROCESSOR_PROMPT.format(materials=materials_text)
        llm_output, _ = await self.llm_caller.acall(
            "你是司法文书结构化分析专家，请提取案件关键信息。",
            prompt,
        )

        case_info = CaseInfo()
        evidence_index: list[EvidenceEntry] = []
        claims_map: list[ClaimEntry] = []
        missing_items: list[str] = []

        try:
            json_match = re.search(r"\{[\s\S]*\}", llm_output)
            if json_match:
                data = json.loads(json_match.group())
                if "case_info" in data:
                    ci = data["case_info"]
                    case_info = CaseInfo(
                        case_number=ci.get("case_number", ""),
                        case_name=ci.get("case_name", ""),
                        parties=ci.get("parties", []),
                        case_type=ci.get("case_type", ""),
                        cause_of_action=ci.get("cause_of_action", ""),
                        judgment_result=ci.get("judgment_result", ""),
                        court=ci.get("court", ""),
                        judge_date=ci.get("judge_date", ""),
                    )
                if "evidence_index" in data:
                    for ev in data["evidence_index"]:
                        evidence_index.append(
                            EvidenceEntry(
                                evidence_id=ev.get("evidence_id", ""),
                                evidence_type=ev.get("evidence_type", ""),
                                submitted_by=ev.get("submitted_by", ""),
                                description=ev.get("description", ""),
                                proof_object=ev.get("proof_object", ""),
                                cross_exam_status=ev.get("cross_exam_status", ""),
                                admission_status=ev.get("admission_status", ""),
                            )
                        )
                if "claims_map" in data:
                    for cl in data["claims_map"]:
                        claims_map.append(
                            ClaimEntry(
                                claim_id=cl.get("claim_id", ""),
                                party=cl.get("party", ""),
                                claim_content=cl.get("claim_content", ""),
                                evidence_refs=cl.get("evidence_refs", []),
                                response_status=cl.get("response_status", ""),
                            )
                        )
                if "missing_items" in data:
                    missing_items = data["missing_items"]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

        if not timeline:
            timeline = self._extract_timeline(llm_output)

        return PreprocessResult(
            case_info=case_info,
            completeness_score=completeness_score,
            timeline=timeline,
            evidence_index=evidence_index,
            claims_map=claims_map,
            missing_items=missing_items,
            materials_text=materials_text,
            raw_llm_output=llm_output,
        )
