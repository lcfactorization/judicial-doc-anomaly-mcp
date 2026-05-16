"""CLI v0.4.0 — Simple Agent that uses MCP Server bridge tools.

This CLI demonstrates how an AI Agent would use the MCP Server:
  1. render_skill / render_pipeline → get prompts
  2. Send prompts to LLM (via API)
  3. parse_response → parse LLM output into structured data
  4. build_report → generate formatted Markdown report

The MCP Server does NOT call any LLM. It only provides
Skill loading, template rendering, response parsing, and report building.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


def _get_tool_function(tool_name: str):
    from .server import (
        build_report,
        list_skills,
        parse_response,
        render_pipeline,
        render_skill,
        write_skill,
    )

    tools = {
        "render_skill": render_skill,
        "render_pipeline": render_pipeline,
        "parse_response": parse_response,
        "build_report": build_report,
        "list_skills": list_skills,
        "write_skill": write_skill,
    }
    return tools.get(tool_name)


def _call_tool(tool_name: str, arguments: dict) -> str:
    fn = _get_tool_function(tool_name)
    if not fn:
        return f"未知工具：{tool_name}"
    return fn(**arguments)


@click.group()
@click.version_option(version="0.4.0")
@click.pass_context
def cli(ctx):
    """司法文书异常检测工具 v0.4.0 (Bridge Architecture)"""
    ctx.ensure_object(dict)


@cli.command()
@click.argument("skill_name")
@click.option("--variable", "-v", multiple=True, help="模板变量 key=value")
@click.option("--output", "-o", type=click.Path(), help="输出文件路径")
def render(skill_name, variable, output):
    """渲染单个 Skill 的提示词（供 Agent 发送给 LLM）"""
    variables = {}
    for v in variable:
        if "=" in v:
            k, val = v.split("=", 1)
            variables[k] = val

    result = _call_tool("render_skill", {
        "skill_name": skill_name,
        "variables": variables or None,
    })

    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(result, encoding="utf-8")
        console.print(f"[green]提示词已保存至：{output}[/green]")
    else:
        try:
            data = json.loads(result)
            if "error" in data:
                console.print(f"[red]{data['error']}[/red]")
            else:
                console.print(Panel(
                    f"Skill: {data['skill_title']}\n"
                    f"System Prompt: {len(data['system_prompt'])} 字符\n"
                    f"User Prompt: {len(data['user_prompt'])} 字符",
                    title=f"渲染结果：{skill_name}",
                ))
                console.print(f"\n## System Prompt\n\n{data['system_prompt'][:500]}...\n")
                console.print(f"\n## User Prompt\n\n{data['user_prompt'][:500]}...")
        except json.JSONDecodeError:
            console.print(result)


@cli.command()
@click.argument("pipeline_name")
@click.option("--variable", "-v", multiple=True, help="模板变量 key=value")
@click.option("--output", "-o", type=click.Path(), help="输出文件路径")
def pipeline(pipeline_name, variable, output):
    """渲染流水线中所有 Skill 的提示词"""
    variables = {}
    for v in variable:
        if "=" in v:
            k, val = v.split("=", 1)
            variables[k] = val

    result = _call_tool("render_pipeline", {
        "pipeline_name": pipeline_name,
        "variables": variables or None,
    })

    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(result, encoding="utf-8")
        console.print(f"[green]流水线提示词已保存至：{output}[/green]")
    else:
        try:
            data = json.loads(result)
            if "error" in data:
                console.print(f"[red]{data['error']}[/red]")
            else:
                table = Table(title=f"流水线：{pipeline_name}")
                table.add_column("#", style="cyan")
                table.add_column("Skill", style="green")
                table.add_column("标题")
                table.add_column("System", justify="right")
                table.add_column("User", justify="right")
                for i, s in enumerate(data["skills"], 1):
                    table.add_row(
                        str(i),
                        s["skill_name"],
                        s.get("skill_title", ""),
                        f"{len(s.get('system_prompt', ''))} 字符",
                        f"{len(s.get('user_prompt', ''))} 字符",
                    )
                console.print(table)
                console.print(f"\n总 Skill 数：{data['total_skills']}")
                console.print(f"预估 Prompt 字符数：{data['estimated_prompt_chars']}")
                console.print(f"预估 Prompt token：{data['estimated_prompt_tokens']}")
        except json.JSONDecodeError:
            console.print(result)


@cli.command(name="list")
@click.option("--category", "-t", help="按类型筛选 (dimension/phase/pipeline)")
def list_skills_cmd(category):
    """列出所有可用的 Skills"""
    result = _call_tool("list_skills", {"category": category})
    console.print(result)


@cli.command()
@click.argument("dimension")
@click.argument("response_file", type=click.Path(exists=True))
@click.option("--index", "-i", default=0, help="维度索引（0-15）")
@click.option("--output", "-o", type=click.Path(), help="输出文件路径")
def parse(dimension, response_file, index, output):
    """解析 LLM 响应为结构化异常数据"""
    response_text = Path(response_file).read_text(encoding="utf-8")

    result = _call_tool("parse_response", {
        "dimension": dimension,
        "response": response_text,
        "dimension_index": index,
    })

    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(result, encoding="utf-8")
        console.print(f"[green]解析结果已保存至：{output}[/green]")
    else:
        try:
            data = json.loads(result)
            console.print(Panel(
                f"维度：{data['dimension']}\n"
                f"异常数：{data['anomaly_count']}\n"
                f"风险等级：{data['risk_level']}",
                title="解析结果",
            ))
        except json.JSONDecodeError:
            console.print(result)


@cli.command()
@click.argument("case_name")
@click.argument("results_file", type=click.Path(exists=True))
@click.option("--doc-type", "-d", default="判决书", help="文书类型")
@click.option("--model", "-m", default="AI Agent", help="模型名称")
@click.option("--output", "-o", type=click.Path(), help="输出文件路径")
def report(case_name, results_file, doc_type, model, output):
    """从结构化数据生成检测报告"""
    results_json = Path(results_file).read_text(encoding="utf-8")

    result = _call_tool("build_report", {
        "case_name": case_name,
        "dimension_results_json": results_json,
        "doc_type": doc_type,
        "model_name": model,
    })

    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(result, encoding="utf-8")
        console.print(f"[green]报告已保存至：{output}[/green]")
    else:
        date_str = datetime.now().strftime("%Y%m%d")
        default_name = f"司法文书异常检测报告_AI-Agent_v0.4.0_{date_str}.md"
        default_path = Path(".") / default_name
        default_path.write_text(result, encoding="utf-8")
        console.print(f"[green]报告已保存至：{default_path}[/green]")


@cli.command()
@click.argument("skill_name")
@click.argument("content_file", type=click.Path(exists=True))
def write(skill_name, content_file):
    """写入或更新 SKILL.md 文件（供 Agent 迭代优化提示词）"""
    content = Path(content_file).read_text(encoding="utf-8")
    result = _call_tool("write_skill", {
        "skill_name": skill_name,
        "content": content,
    })
    console.print(result)


@cli.command()
def serve():
    """启动 MCP Server（stdio 模式）"""
    from .server import main as server_main
    server_main()


def main():
    cli()


if __name__ == "__main__":
    main()
