"""Full test: run all dimensions on mock case."""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv

load_dotenv()

from judicial_lint_mcp.config import AppConfig
from judicial_lint_mcp.detector import DetectionEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("full-test")


async def main():
    case_dir = r".\test_cases\mock_role_evidence_case"

    config = AppConfig.from_env()
    config.detection.enable_adversarial_check = False
    config.detection.enable_graph_building = False
    config.detection.enable_quality_assessment = False
    config.detection.enable_quick_check = False

    logger.info("完整测试: 运行全部维度")
    logger.info("模型: %s", config.llm.model)
    logger.info("案件目录: %s", case_dir)
    logger.info("维度: %s", config.detection.dimensions)

    engine = DetectionEngine(config)
    result = await engine.run_detection(case_dir)

    logger.info("检测完成 | 维度: %d | 异常项: %d | 风险: %s",
                len(result.dimension_results),
                sum(len(r.anomalies) for r in result.dimension_results),
                result.risk_level)

    for r in result.dimension_results:
        logger.info("维度: %s | 异常数: %d", r.dimension, len(r.anomalies))
        for a in r.anomalies:
            logger.info("  异常: %s | 获益方: %s | 置信度: %s",
                        a.item_name[:50], a.beneficiary, a.confidence)

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report_v10_full_test.md"
    report_path.write_text(result.report_markdown, encoding="utf-8")
    logger.info("报告已保存至: %s", report_path)


if __name__ == "__main__":
    asyncio.run(main())
