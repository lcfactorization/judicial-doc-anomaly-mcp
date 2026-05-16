"""MCP Server entry point for judicial document anomaly detection"""

import asyncio
import json
from pathlib import Path
from mcp.server import Server
from mcp.types import TextContent, Tool
from .config import AppConfig
from .detector import DetectionEngine

# Create server instance
server = Server("judicial-lint")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools"""
    return [
        Tool(
            name="detect_anomalies",
            description="对案件目录下的司法文书进行异常检测，支持12维度深度扫描",
            inputSchema={
                "type": "object",
                "properties": {
                    "case_dir": {
                        "type": "string",
                        "description": "案件目录路径，包含所有转换好的 .md 文书",
                    },
                    "dimensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要检测的维度列表，可选值：procedure, evidence, fact_finding, law_application, discretion, logic, temporal, semantic_drift, negative_space, case_deviation, procedure_graph, coupling",
                    },
                    "model": {
                        "type": "string",
                        "description": "LLM 模型名称，如 gpt-4, deepseek-chat 等",
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["markdown", "json", "both"],
                        "description": "输出格式",
                        "default": "markdown",
                    },
                    "enable_adversarial": {
                        "type": "boolean",
                        "description": "是否启用对抗校验",
                        "default": True,
                    },
                    "config_file": {
                        "type": "string",
                        "description": "配置文件路径（可选）",
                    },
                },
                "required": ["case_dir"],
            },
        ),
        Tool(
            name="dry_run",
            description="预览检测流程，显示将调用的 prompt 和预估 token 数，不实际调用 LLM",
            inputSchema={
                "type": "object",
                "properties": {
                    "case_dir": {
                        "type": "string",
                        "description": "案件目录路径",
                    },
                    "dimensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要检测的维度列表",
                    },
                },
                "required": ["case_dir"],
            },
        ),
        Tool(
            name="get_detection_rules",
            description="获取内置的检测规则与法条参考",
            inputSchema={
                "type": "object",
                "properties": {
                    "dimension": {
                        "type": "string",
                        "description": "指定维度，不指定则返回全部",
                    },
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls"""
    if name == "detect_anomalies":
        return await _handle_detect_anomalies(arguments)
    elif name == "dry_run":
        return await _handle_dry_run(arguments)
    elif name == "get_detection_rules":
        return await _handle_get_detection_rules(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")


async def _handle_detect_anomalies(arguments: dict) -> list[TextContent]:
    """Handle detect_anomalies tool call"""
    case_dir = arguments.get("case_dir")
    if not case_dir:
        return [TextContent(type="text", text="错误：case_dir 参数不能为空")]
    
    # Load configuration
    config_file = arguments.get("config_file")
    if config_file:
        config = AppConfig.from_file(config_file)
    else:
        config = AppConfig.from_env()
    
    # Override with arguments
    if arguments.get("model"):
        config.llm.model = arguments["model"]
    if arguments.get("dimensions"):
        config.detection.dimensions = arguments["dimensions"]
    if arguments.get("enable_adversarial") is not None:
        config.detection.enable_adversarial_check = arguments["enable_adversarial"]
    
    # Run detection
    engine = DetectionEngine(config)
    result = await engine.run_detection(case_dir)
    
    # Format output
    output_format = arguments.get("output_format", "markdown")
    
    if output_format == "json":
        return [TextContent(
            type="text",
            text=json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
        )]
    elif output_format == "both":
        return [
            TextContent(type="text", text=result.report_markdown),
            TextContent(
                type="text",
                text=json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
            ),
        ]
    else:
        return [TextContent(type="text", text=result.report_markdown)]


async def _handle_dry_run(arguments: dict) -> list[TextContent]:
    """Handle dry_run tool call"""
    case_dir = arguments.get("case_dir")
    if not case_dir:
        return [TextContent(type="text", text="错误：case_dir 参数不能为空")]
    
    from .detector import FileLoader
    from .prompts import DIMENSION_PROMPTS
    
    # Load materials
    loader = FileLoader(case_dir)
    loader.load()
    completeness, missing = loader.validate()
    
    materials = loader.get_materials_text()
    
    # Estimate tokens
    dims = arguments.get("dimensions", list(DIMENSION_PROMPTS.keys()))
    
    output = [
        "# 检测流程预览（Dry Run）",
        f"\n## 材料完整性评分：{completeness:.1f}/100",
        f"\n## 缺失材料：{', '.join(missing) if missing else '无'}",
        f"\n## 材料总字符数：{len(materials)}",
        f"\n## 预估材料 token 数：{int(len(materials) * 0.5)}",
        f"\n## 将执行的检测维度：{', '.join(dims)}",
        f"\n## 预估总 token 消耗：{int(len(materials) * 0.5 * len(dims) * 1.2)}",
        f"\n\n## 各维度 Prompt 预览：\n",
    ]
    
    for dim in dims:
        if dim in DIMENSION_PROMPTS:
            prompt = DIMENSION_PROMPTS[dim]
            output.append(f"### {dim}")
            output.append(f"- Prompt 长度：{len(prompt)} 字符")
            output.append(f"- 预估 token：{int(len(prompt) * 0.5)}")
            output.append(f"- Prompt 内容：\n```\n{prompt[:200]}...\n```\n")
    
    return [TextContent(type="text", text="\n".join(output))]


async def _handle_get_detection_rules(arguments: dict) -> list[TextContent]:
    """Handle get_detection_rules tool call"""
    from .prompts import DIMENSION_PROMPTS
    
    dimension = arguments.get("dimension")
    if dimension:
        if dimension in DIMENSION_PROMPTS:
            return [TextContent(type="text", text=DIMENSION_PROMPTS[dimension])]
        else:
            return [TextContent(type="text", text=f"未知维度：{dimension}")]
    else:
        output = ["# 全部检测维度规则\n"]
        for dim, prompt in DIMENSION_PROMPTS.items():
            output.append(f"\n## {dim}\n{prompt}\n")
        return [TextContent(type="text", text="\n".join(output))]


def main():
    """Run MCP server"""
    import asyncio
    from mcp.server.stdio import stdio_server
    
    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    
    asyncio.run(run())


if __name__ == "__main__":
    main()
