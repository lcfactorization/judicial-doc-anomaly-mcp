"""Local end-to-end runner for judicial-lint-mcp v0.2.0

Simulates a detect_anomalies call with a desensitized test case directory.
Supports two modes:
  --mock    Use mock LLM responses (no API key needed, default)
  --live    Use real LLM API (requires LLM_API_KEY env var)

Usage:
  python run_local_e2e.py
  python run_local_e2e.py --live --model deepseek-chat
  python run_local_e2e.py --case-dir path/to/case
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from judicial_lint_mcp.adversarial import AdversarialReviewer
from judicial_lint_mcp.config import AppConfig
from judicial_lint_mcp.graph_builder import GraphBuilder
from judicial_lint_mcp.preprocessor import Preprocessor
from judicial_lint_mcp.quality_assessor import QualityAssessor
from judicial_lint_mcp.server import (
    _format_adversarial_result,
    _format_graph_result,
    _format_preprocess_result,
    _format_quality_result,
)

logger = logging.getLogger("e2e-runner")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)

MOCK_PREPROCESSOR_OUTPUT = r"""```json
{
  "case_number": "（2025）苏9902民初9999号",
  "case_name": "张某诉某科技有限公司劳动争议案",
  "parties": ["张某", "某科技有限公司"],
  "case_type": "劳动争议",
  "timeline": [
    {"date": "2024-03-01", "event": "原告入职被告公司"},
    {"date": "2024-06-15", "event": "被告未签订书面劳动合同满三个月"},
    {"date": "2024-09-10", "event": "被告口头解除劳动关系"},
    {"date": "2024-09-15", "event": "原告申请劳动仲裁"},
    {"date": "2024-10-20", "event": "仲裁委不予受理"},
    {"date": "2024-11-01", "event": "原告向法院起诉"},
    {"date": "2025-01-15", "event": "法院开庭审理"},
    {"date": "2025-03-20", "event": "法院作出判决"}
  ],
  "evidence_index": [
    {"evidence_id": "原证1", "evidence_type": "书证", "description": "银行工资流水", "source_party": "原告", "authenticity": "被告认可"},
    {"evidence_id": "原证2", "evidence_type": "书证", "description": "微信工作群聊天记录", "source_party": "原告", "authenticity": "被告不认可"},
    {"evidence_id": "被证1", "evidence_type": "书证", "description": "考勤记录", "source_party": "被告", "authenticity": "原告不认可"},
    {"evidence_id": "被证2", "evidence_type": "证人证言", "description": "同事李某证言", "source_party": "被告", "authenticity": "原告不认可"}
  ],
  "claims_map": [
    {"claim_id": "诉请1", "party": "原告", "claim_content": "未签劳动合同二倍工资差额", "amount": "45000元"},
    {"claim_id": "诉请2", "party": "原告", "claim_content": "违法解除赔偿金", "amount": "15000元"}
  ],
  "missing_items": ["庭审笔录", "仲裁裁决书全文"]
}
```"""

MOCK_GRAPH_OUTPUT = r"""```json
{
  "evidence_graph": {
    "nodes": [
      {"id": "原证1", "label": "银行工资流水", "type": "DOCUMENT"},
      {"id": "原证2", "label": "微信聊天记录", "type": "ELECTRONIC"},
      {"id": "被证1", "label": "考勤记录", "type": "DOCUMENT"},
      {"id": "被证2", "label": "同事证言", "type": "TESTIMONY"}
    ],
    "edges": [
      {"source": "原证1", "target": "被证1", "relation": "contradicts", "label": "工资与考勤矛盾"},
      {"source": "原证2", "target": "被证2", "relation": "contradicts", "label": "工作记录与证言矛盾"}
    ]
  },
  "procedure_graph": {
    "nodes": [
      {"id": "START", "label": "立案", "type": "START"},
      {"id": "filing", "label": "受理", "type": "FILING"},
      {"id": "evidence_exchange", "label": "证据交换", "type": "EVIDENCE_EXCHANGE"},
      {"id": "trial", "label": "开庭审理", "type": "TRIAL"},
      {"id": "judgment", "label": "判决", "type": "JUDGMENT"}
    ],
    "edges": [
      {"source": "START", "target": "filing", "relation": "NEXT"},
      {"source": "filing", "target": "evidence_exchange", "relation": "NEXT"},
      {"source": "evidence_exchange", "target": "trial", "relation": "NEXT"},
      {"source": "trial", "target": "judgment", "relation": "NEXT"}
    ]
  },
  "reasoning_graph": {
    "nodes": [
      {"id": "claim1", "label": "二倍工资诉请", "type": "CLAIM"},
      {"id": "fact1", "label": "未签书面合同", "type": "FACT"},
      {"id": "law1", "label": "劳动合同法第82条", "type": "LAW"},
      {"id": "conclusion1", "label": "驳回诉请", "type": "CONCLUSION"}
    ],
    "edges": [
      {"source": "claim1", "target": "fact1", "relation": "based_on"},
      {"source": "fact1", "target": "law1", "relation": "applies"},
      {"source": "law1", "target": "conclusion1", "relation": "leads_to"}
    ]
  }
}
```"""

MOCK_QUALITY_OUTPUT = """## 文书质量评估

### 维度评分
| 维度 | 满分 | 得分 | 权重 | 加权分 |
|------|------|------|------|--------|
| 程序合规性 | 20 | 12 | 20% | 2.4 |
| 事实认定质量 | 20 | 8 | 20% | 1.6 |
| 证据采信规范性 | 15 | 7 | 15% | 1.1 |
| 法律适用准确性 | 15 | 10 | 15% | 1.5 |
| 说理充分性 | 15 | 6 | 15% | 0.9 |
| 文书规范性 | 10 | 7 | 10% | 0.7 |
| 权利保障性 | 5 | 2 | 5% | 0.1 |

**加权总分**：8.3/100
**综合等级**：F（严重缺陷）

### 核心优势
- 文书格式基本规范
- 案件基本信息记录完整

### 核心不足
- 事实认定缺乏充分说理
- 证据采信存在明显双标
- 举证责任分配错误
- 原告关键证据被不当排除

### 改进建议
- 应当对原告证据逐项说明采信或不采信理由
- 应当正确分配举证责任
- 应当对被告证据进行实质审查"""

MOCK_ADVERSARIAL_OUTPUT = """## Devil's Advocate 校验

### Q1: 反向论证
**异常1：举证责任倒置**
- 原论证：法院将举证责任分配给原告
- 反向论证：劳动争议中用人单位应承担举证责任
- 结论：**存疑** - 原判决举证责任分配确有不当

**异常2：证据双标采信**
- 原论证：被告证据采信，原告同类证据不采信
- 反向论证：可能存在证据形式差异
- 结论：**成立** - 采信标准确不一致

### Q2: 最善意解释
法院可能在自由裁量范围内做出了判断，但举证责任倒置和证据双标采信难以用善意解释覆盖。

### Q3: 重新裁判
如果重新裁判，应当：
1. 将举证责任分配给被告
2. 对双方证据适用同一采信标准
3. 对原告笔迹鉴定申请予以准许

## 角色审查

### 不利方代理人（原告代理人）
- 风险等级：高
- 关键质疑：举证责任分配错误、证据采信双标
- 建议上诉理由：程序违法、事实认定错误

### 上诉审查法官
- 风险等级：中高
- 关键质疑：说理不充分、举证责任倒置
- 发回重审可能性：较高

### 法学学者
- 风险等级：中
- 关键质疑：法律适用存在争议空间
- 学术观点：劳动争议举证责任倒置已有明确司法解释

### 公众监督者
- 风险等级：高
- 关键质疑：可能存在地方保护主义
- 舆论风险：劳动权益保障不力

### 制度设计者
- 风险等级：中
- 关键质疑：程序设计是否合理
- 制度建议：加强劳动争议举证责任规则执行

## 交叉质证

| 风险点 | 原告代理人 | 上诉法官 | 学者 | 公众 | 制度 | 共识度 |
|--------|-----------|---------|------|------|------|--------|
| 举证责任倒置 | 高 | 中高 | 中 | 高 | 中 | 较高 |
| 证据双标采信 | 高 | 高 | 中 | 高 | 中 | 高 |

## 高风险点
- [高] 举证责任倒置违反劳动法司法解释
- [高] 证据采信标准不一致构成程序违法
- [中高] 原告笔迹鉴定申请被拒缺乏理由"""


class MockLLMCaller:
    def __init__(self):
        self.call_count = 0
        self._responses = self._build_response_queue()

    def _build_response_queue(self):
        return [
            MOCK_PREPROCESSOR_OUTPUT,
            MOCK_GRAPH_OUTPUT,
            MOCK_QUALITY_OUTPUT,
            MOCK_ADVERSARIAL_OUTPUT,
        ]

    def call(self, system_prompt, user_prompt, **kwargs):
        self.call_count += 1
        idx = (self.call_count - 1) % len(self._responses)
        return self._responses[idx], {"total_tokens": 500}

    async def acall(self, system_prompt, user_prompt, **kwargs):
        self.call_count += 1
        idx = (self.call_count - 1) % len(self._responses)
        return self._responses[idx], {"total_tokens": 500}


async def run_e2e(case_dir: str, mock_mode: bool = True, model: str = "gpt-4"):
    t_start = time.perf_counter()

    logger.info("=" * 60)
    logger.info("judicial-lint-mcp v0.2.0 端到端测试")
    logger.info("案件目录: %s", case_dir)
    logger.info("模式: %s", "Mock LLM" if mock_mode else f"Live LLM ({model})")
    logger.info("=" * 60)

    if mock_mode:
        llm_caller = MockLLMCaller()
        config = AppConfig()
    else:
        config = AppConfig.from_env()
        if model:
            config.llm.model = model
        from judicial_lint_mcp.llm_caller import LLMCaller

        llm_caller = LLMCaller(config.llm, cache_dir=config.cache_dir)

    report_sections = []

    # Phase 0-1: Preprocessing
    t1 = time.perf_counter()
    logger.info("[Phase 0-1] 开始预处理...")
    preprocessor = Preprocessor(llm_caller)
    preprocess_result = await preprocessor.run(case_dir)
    logger.info(
        "[Phase 0-1] 预处理完成 | 完整性: %.1f | 时间线: %d | 证据: %d | 诉请: %d | 耗时: %.2fs",
        preprocess_result.completeness_score,
        len(preprocess_result.timeline),
        len(preprocess_result.evidence_index),
        len(preprocess_result.claims_map),
        time.perf_counter() - t1,
    )
    report_sections.append(_format_preprocess_result(preprocess_result))

    # Phase 2: Graph building
    t2 = time.perf_counter()
    logger.info("[Phase 2] 开始图构建...")
    graph_builder = GraphBuilder(llm_caller, config.graph)
    graph_result = await graph_builder.run(preprocess_result)
    logger.info(
        "[Phase 2] 图构建完成 | 证据图: %s | 程序图: %s | 推理图: %s | 异常路径: %d | 耗时: %.2fs",
        "✓" if graph_result.evidence_mermaid else "✗",
        "✓" if graph_result.procedure_mermaid else "✗",
        "✓" if graph_result.reasoning_mermaid else "✗",
        len(graph_result.anomaly_paths),
        time.perf_counter() - t2,
    )
    report_sections.append(_format_graph_result(graph_result))

    # Phase 4.5: Quality assessment
    t3 = time.perf_counter()
    logger.info("[Phase 4.5] 开始质量评估...")
    assessor = QualityAssessor(llm_caller)
    quality_result = await assessor.assess(preprocess_result.materials_text)
    logger.info(
        "[Phase 4.5] 质量评估完成 | 总分: %d/100 | 等级: %s | 耗时: %.2fs",
        quality_result.total_score,
        quality_result.grade,
        time.perf_counter() - t3,
    )
    report_sections.append(_format_quality_result(quality_result))

    # Phase 5: Adversarial review
    t4 = time.perf_counter()
    logger.info("[Phase 5] 开始对抗审查...")
    reviewer = AdversarialReviewer(llm_caller, config.adversarial)
    adversarial_result = await reviewer.run("测试异常文本")
    da_count = (
        len(adversarial_result.devils_advocate_results)
        if adversarial_result.devils_advocate_results
        else 0
    )
    rr_count = (
        len(adversarial_result.role_reviews) if adversarial_result.role_reviews else 0
    )
    hr_count = (
        len(adversarial_result.high_risk_points)
        if adversarial_result.high_risk_points
        else 0
    )
    logger.info(
        "[Phase 5] 对抗审查完成 | DA校验: %d | 角色审查: %d | 高风险点: %d | 耗时: %.2fs",
        da_count,
        rr_count,
        hr_count,
        time.perf_counter() - t4,
    )
    report_sections.append(_format_adversarial_result(adversarial_result))

    total_time = time.perf_counter() - t_start
    logger.info("=" * 60)
    logger.info(
        "端到端测试完成 | 总耗时: %.2fs | LLM调用次数: %d",
        total_time,
        llm_caller.call_count if hasattr(llm_caller, "call_count") else "?",
    )
    logger.info("=" * 60)

    full_report = "\n\n---\n\n".join(report_sections)

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "e2e_report.md"
    report_path.write_text(full_report, encoding="utf-8")
    logger.info("报告已保存至: %s", report_path)

    print("\n" + "=" * 60)
    print("完整检测报告")
    print("=" * 60)
    print(full_report)

    return full_report


def main():
    parser = argparse.ArgumentParser(
        description="judicial-lint-mcp v0.2.0 本地端到端测试"
    )
    parser.add_argument(
        "--case-dir",
        type=str,
        default=str(Path(__file__).parent / "tests" / "fixtures" / "sample_case"),
        help="案件目录路径",
    )
    parser.add_argument(
        "--live", action="store_true", help="使用真实LLM API（需要LLM_API_KEY环境变量）"
    )
    parser.add_argument(
        "--model", type=str, default="gpt-4", help="LLM模型名称（仅--live模式有效）"
    )
    args = parser.parse_args()

    case_dir = Path(args.case_dir)
    if not case_dir.exists():
        logger.error("案件目录不存在: %s", case_dir)
        sys.exit(1)

    files = list(case_dir.glob("*.md")) + list(case_dir.glob("*.txt"))
    logger.info("案件目录: %s | 文件数: %d", case_dir, len(files))
    for f in sorted(files):
        logger.info("  - %s (%d 字符)", f.name, f.stat().st_size)

    asyncio.run(
        run_e2e(
            case_dir=str(case_dir),
            mock_mode=not args.live,
            model=args.model,
        )
    )


if __name__ == "__main__":
    main()
