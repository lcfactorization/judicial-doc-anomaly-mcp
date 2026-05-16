"""Benchmark cases — reference cases for calibration.

Three categories:
  - clearly_anomalous: cases with well-documented procedural errors
  - high_quality: cases demonstrating rigorous legal reasoning
  - borderline: cases where anomaly assessment is genuinely ambiguous

Each entry is anonymised and suitable for model calibration.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    category: str
    cause: str
    key_anomalies: list[str]
    expected_grade: str
    summary: str
    reasoning: str


BENCHMARKS: list[BenchmarkCase] = [
    BenchmarkCase(
        case_id="BM-001",
        category="clearly_anomalous",
        cause="劳动争议",
        key_anomalies=["A4", "A6", "A8"],
        expected_grade="高度异常",
        summary=(
            "用人单位通过微信告知劳动者岗位和待遇，法院认定微信内容构成书面劳动合同，"
            "但未对是否符合《劳动合同法》第17条9项必备条款逐一审查。"
            "用人单位应举证证明已签订书面劳动合同，法院却将举证责任转移给劳动者。"
        ),
        reasoning=(
            "A4（同类证据双重标准）+ A6（回避核心争点）+ A8（举证责任倒置）"
            "三个高严重度异常同时出现，且均指向对用人单位有利，"
            "满足高度异常的判定条件（多高置信异常+部分耦合）。"
        ),
    ),
    BenchmarkCase(
        case_id="BM-002",
        category="clearly_anomalous",
        cause="民间借贷纠纷",
        key_anomalies=["A1", "A2", "A5"],
        expected_grade="高度异常",
        summary=(
            "原告提交银行转账凭证证明借款交付，法院以'不能排除其他法律关系'为由"
            "否定借款事实，但未回应原告补充的微信聊天记录证据。"
            "审理期限超出法定期限8个月，且未出具延期审理裁定。"
        ),
        reasoning=(
            "A1（关键证据未回应）+ A2（事实认定跳跃）+ A5（程序时间线异常）"
            "覆盖证据类+事实类+程序类三个维度类别，存在部分耦合。"
        ),
    ),
    BenchmarkCase(
        case_id="BM-003",
        category="high_quality",
        cause="合同纠纷",
        key_anomalies=[],
        expected_grade="低度异常",
        summary=(
            "法院对双方提交的证据逐一评述，对不采信的证据说明了理由，"
            "争议焦点归纳完整，法律适用准确，说理充分，审限合规。"
            "唯一可议之处为自由裁量金额略高于类案均值但仍在合理区间。"
        ),
        reasoning=(
            "无A系列异常触发，裁量幅度在正常范围内（Deviation Score < 0.5），"
            "判定为低度异常（仅1-2个孤立微弱信号）。"
        ),
    ),
    BenchmarkCase(
        case_id="BM-004",
        category="high_quality",
        cause="劳动争议",
        key_anomalies=[],
        expected_grade="低度异常",
        summary=(
            "法院对劳动合同解除的合法性进行了完整的三段论论证，"
            "证据采信标准一致，举证责任分配正确，"
            "经济补偿金计算有明确法条依据和计算过程。"
        ),
        reasoning=("各项检测均未触发异常，为高质量判决的标杆案例。"),
    ),
    BenchmarkCase(
        case_id="BM-005",
        category="borderline",
        cause="侵权责任纠纷",
        key_anomalies=["A3", "A7"],
        expected_grade="中度异常",
        summary=(
            "法院适用了公平责任原则而非过错责任原则，但说理部分较为简略。"
            "判决书部分段落呈现模板化特征，但核心争议焦点有回应。"
            "法律适用虽有争议空间但并非明显错误。"
        ),
        reasoning=(
            "A3（法律适用未充分解释）+ A7（模板化论证）两个异常，"
            "但严重度较低，且指向不一致（A3可能因法官业务能力，A7为常见现象），"
            "判定为中度异常。"
        ),
    ),
    BenchmarkCase(
        case_id="BM-006",
        category="borderline",
        cause="买卖合同纠纷",
        key_anomalies=["A2"],
        expected_grade="中度异常",
        summary=(
            "法院在认定货物质量是否合格时，跳过了鉴定环节直接以感官判断定案，"
            "但被告未在法定期限内申请鉴定。"
            "异常信号存在，但被告自身行为也构成举证妨碍。"
        ),
        reasoning=(
            "A2（事实认定跳跃）成立，但反向校验发现被告存在举证妨碍，"
            "净异常判定为存疑。双向审计后降级为中度异常。"
        ),
    ),
]


def get_benchmarks_by_category(category: str) -> list[BenchmarkCase]:
    return [b for b in BENCHMARKS if b.category == category]


def get_benchmark(case_id: str) -> BenchmarkCase | None:
    for b in BENCHMARKS:
        if b.case_id == case_id:
            return b
    return None
