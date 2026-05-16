"""Anomaly taxonomy — A1-A8 unified numbering system.

Bridges the 16-dimension detection grid (F-01 to F-26) with a
higher-level taxonomy that enables:
  - Cross-case comparability
  - Statistical aggregation
  - Benchmark calibration
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnomalyCategory:
    code: str
    label: str
    description: str
    dimensions: list[int]
    f_codes: list[str]
    severity_base: float
    bidirectional: bool


TAXONOMY: list[AnomalyCategory] = [
    AnomalyCategory(
        code="A1",
        label="关键证据未回应",
        description="对一方当事人提交的核心证据，裁判文书未予回应、评述或采信/排除说理",
        dimensions=[2, 3, 10, 15],
        f_codes=["F-14", "F-15", "F-16", "F-19"],
        severity_base=0.85,
        bidirectional=True,
    ),
    AnomalyCategory(
        code="A2",
        label="事实认定跳跃",
        description="从证据到事实的推理链条存在断裂，关键中间环节缺失论证",
        dimensions=[3, 9],
        f_codes=["F-01", "F-02", "F-20", "F-21", "F-23"],
        severity_base=0.80,
        bidirectional=True,
    ),
    AnomalyCategory(
        code="A3",
        label="法律适用未解释",
        description="适用某一法条但未说明为何适用该法条而非另一法条，或未对法律概念进行界定",
        dimensions=[5, 6, 14],
        f_codes=["F-20"],
        severity_base=0.75,
        bidirectional=True,
    ),
    AnomalyCategory(
        code="A4",
        label="同类证据双重标准",
        description="对同类证据因提交方不同而采用不同的采信标准",
        dimensions=[2, 3],
        f_codes=["F-07", "F-09", "F-10", "F-12"],
        severity_base=0.90,
        bidirectional=True,
    ),
    AnomalyCategory(
        code="A5",
        label="程序时间线异常",
        description="程序行为的时间顺序存在逆序、超期、加速等异常模式",
        dimensions=[1, 10, 13],
        f_codes=["F-04", "F-05"],
        severity_base=0.70,
        bidirectional=False,
    ),
    AnomalyCategory(
        code="A6",
        label="回避核心争点",
        description="对当事人提出或应当审查的核心争议焦点，裁判文书予以回避、偏移或虚化",
        dimensions=[4, 8, 15],
        f_codes=["F-22", "F-25"],
        severity_base=0.85,
        bidirectional=True,
    ),
    AnomalyCategory(
        code="A7",
        label="机械复制模板化论证",
        description="说理部分呈现模板化特征，未针对个案具体情况进行实质性论证",
        dimensions=[8, 9],
        f_codes=["F-23", "F-24", "F-25"],
        severity_base=0.65,
        bidirectional=False,
    ),
    AnomalyCategory(
        code="A8",
        label="举证责任倒置异常",
        description="将本应由一方承担的举证责任不当转移给另一方，或对举证责任分配未予说明",
        dimensions=[2, 3, 6],
        f_codes=["F-26"],
        severity_base=0.90,
        bidirectional=True,
    ),
]


_CODE_MAP: dict[str, AnomalyCategory] = {c.code: c for c in TAXONOMY}


def get_category(code: str) -> AnomalyCategory | None:
    return _CODE_MAP.get(code)


def category_from_f_code(f_code: str) -> list[AnomalyCategory]:
    return [c for c in TAXONOMY if f_code in c.f_codes]


def dimension_to_categories(dim: int) -> list[AnomalyCategory]:
    return [c for c in TAXONOMY if dim in c.dimensions]


NEUTRALITY_PROMPT_ADDON = """
## 中立性校验指令

本检测框架定位为"AI司法推理审计框架"，而非维权工具。因此，在执行异常检测时，必须同时执行以下反向检测：

### 反向异常检测（Reverse Anomaly Detection）
- 如果异常点指向"法院偏袒被告/用人单位"，必须检查是否存在"原告/劳动者诉求膨胀"的对应异常
- 如果认定"证据被不当排除"，必须检查被排除证据本身是否存在可靠性问题
- 如果认定"举证责任倒置"，必须检查被倾斜方是否存在举证妨碍行为

### 原告诉求膨胀识别
- 原告是否存在将多项独立请求合并以制造"数量优势"的策略
- 原告提交的证据是否存在选择性截取、断章取义的情况
- 原告主张的金额/期限是否存在明显超出法律支持范围的部分

### 证据可信度反校验
- 对劳动者提交的电子证据（聊天记录、邮件等），校验是否存在编辑、删除、伪造痕迹
- 对用人单位提交的制度文件，校验是否经过民主程序、是否实际公示
- 对证人证言，校验证人与当事人的关系及证言的一致性

### 情绪化叙事过滤
- 如果文书分析中存在"显然""明摆着""不可能不知道"等情绪化表达，必须降级为"存疑"
- 禁止将"法官应该知道"作为异常判定的依据——必须以客观标准（法条、程序、先例）为准
- 对"价值判断"类结论，必须标注为"待验证"，而非"成立"

### 双向标注要求
每个检测到的异常点，必须标注：
- **指向获益方**：该异常使哪一方获益（原告/被告/不确定）
- **反向校验结果**：是否存在对该方有利的对应异常
- **净异常判定**：扣除反向异常后，该异常点是否仍然成立
"""
