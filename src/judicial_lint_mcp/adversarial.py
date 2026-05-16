"""Phase 5: Multi-role adversarial review engine

Implements Devil's Advocate Q1/Q2/Q3 validation and
5-role adversarial review with cross-examination.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from .config import ADVERSARIAL_ROLES, AdversarialConfig
from .llm_caller import LLMCaller
from .prompts import ADVERSARIAL_PROMPT


@dataclass
class DevilsAdvocateResult:
    anomaly_id: str
    anomaly_description: str
    q1_alternative_explanation: str = ""
    q1_has_alternative: bool = False
    q2_still_valid_without_intent: bool = False
    q3_counter_evidence: str = ""
    q3_has_counter: bool = False
    conclusion: str = ""
    conclusion_reason: str = ""


@dataclass
class RoleReviewResult:
    role: str
    role_name_cn: str = ""
    challenge_points: list[dict] = field(default_factory=list)
    risk_level: str = ""


@dataclass
class CrossExaminationResult:
    risk_point: str
    confirming_roles: list[str]
    denying_roles: list[str]
    consensus_level: str = ""
    risk_level: str = ""


@dataclass
class AdversarialResult:
    devils_advocate_results: list[DevilsAdvocateResult] = field(default_factory=list)
    role_reviews: list[RoleReviewResult] = field(default_factory=list)
    cross_examinations: list[CrossExaminationResult] = field(default_factory=list)
    high_risk_points: list[dict] = field(default_factory=list)
    raw_llm_output: str = ""


ROLE_NAMES_CN = {
    "plaintiff_agent": "原告代理人",
    "defendant_agent": "被告代理人",
    "appellate_judge": "上诉审查法官",
    "legal_scholar": "法学学者",
    "public_supervisor": "公众监督者",
}


class AdversarialReviewer:
    def __init__(self, llm_caller: LLMCaller, config: AdversarialConfig):
        self.llm_caller = llm_caller
        self.config = config

    def _parse_devils_advocate(self, llm_output: str) -> list[DevilsAdvocateResult]:
        results = []
        conclusion_pattern = re.compile(
            r"(✅|⚠️|❌)\s*(异常成立|异常存疑|异常不成立)",
            re.UNICODE,
        )
        sections = re.split(r"(?=异常点[\s\d：:])", llm_output)
        for section in sections:
            if not section.strip():
                continue
            conclusion_match = conclusion_pattern.search(section)
            conclusion = ""
            if conclusion_match:
                symbol = conclusion_match.group(1)
                text = conclusion_match.group(2)
                if symbol == "✅":
                    conclusion = "成立"
                elif symbol == "⚠️":
                    conclusion = "存疑"
                elif symbol == "❌":
                    conclusion = "不成立"
            results.append(
                DevilsAdvocateResult(
                    anomaly_id="",
                    anomaly_description=section[:200],
                    conclusion=conclusion,
                )
            )
        if not results:
            results.append(
                DevilsAdvocateResult(
                    anomaly_id="overall",
                    anomaly_description="整体校验",
                    conclusion="存疑",
                )
            )
        return results

    def _parse_role_reviews(self, llm_output: str) -> list[RoleReviewResult]:
        reviews = []
        for role_key, role_cn in ROLE_NAMES_CN.items():
            if role_key not in self.config.roles:
                continue
            pattern = re.compile(
                rf"{role_cn}[：:](.+?)(?=(?:{'|'.join(ROLE_NAMES_CN.values())})[：:]|$)",
                re.UNICODE | re.DOTALL,
            )
            match = pattern.search(llm_output)
            if match:
                reviews.append(
                    RoleReviewResult(
                        role=role_key,
                        role_name_cn=role_cn,
                        risk_level="待评估",
                    )
                )
        if not reviews:
            for role_key in self.config.roles[:3]:
                reviews.append(
                    RoleReviewResult(
                        role=role_key,
                        role_name_cn=ROLE_NAMES_CN.get(role_key, role_key),
                        risk_level="待评估",
                    )
                )
        return reviews

    async def run(self, anomalies_text: str) -> AdversarialResult:
        result = AdversarialResult()

        if self.config.enable_devils_advocate:
            prompt = ADVERSARIAL_PROMPT.format(anomalies=anomalies_text)
            llm_output, _ = await self.llm_caller.acall(
                "你是对抗校验专家，请对检测出的异常点进行多角色反向审查。",
                prompt,
            )
            result.raw_llm_output = llm_output

            result.devils_advocate_results = self._parse_devils_advocate(llm_output)

            if self.config.enable_multi_role:
                result.role_reviews = self._parse_role_reviews(llm_output)

            if self.config.enable_cross_examination:
                confirmed_points = []
                for da in result.devils_advocate_results:
                    if da.conclusion in ("成立", "存疑"):
                        confirmed_points.append({
                            "point": da.anomaly_description[:100],
                            "da_conclusion": da.conclusion,
                        })
                for point in confirmed_points:
                    confirming = []
                    for review in result.role_reviews:
                        confirming.append(review.role)
                    result.cross_examinations.append(
                        CrossExaminationResult(
                            risk_point=point["point"],
                            confirming_roles=confirming,
                            denying_roles=[],
                            consensus_level="多数确认" if len(confirming) >= 2 else "少数确认",
                            risk_level="高" if len(confirming) >= 3 else "中",
                        )
                    )
                result.high_risk_points = [
                    {
                        "point": ce.risk_point,
                        "risk_level": ce.risk_level,
                        "confirming_roles": ce.confirming_roles,
                    }
                    for ce in result.cross_examinations
                    if ce.risk_level in ("高", "中")
                ]

        return result
