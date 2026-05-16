"""CLI entry point for judicial-lint"""

import click
import asyncio
import json
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from .config import AppConfig
from .detector import DetectionEngine

console = Console()


@click.group()
@click.version_option(version="0.1.0")
@click.option("--config", "-c", type=click.Path(), help="配置文件路径")
@click.option("--verbose", "-v", is_flag=True, help="详细输出")
@click.pass_context
def cli(ctx, config, verbose):
    """司法文书异常检测工具 - judicial-lint"""
    ctx.ensure_object(dict)
    ctx.obj["config_file"] = config
    ctx.obj["verbose"] = verbose


@cli.command()
@click.argument("case_dir", type=click.Path(exists=True))
@click.option("--dimensions", "-d", multiple=True, help="指定检测维度")
@click.option("--model", "-m", help="LLM 模型名称")
@click.option("--output", "-o", type=click.Path(), help="输出文件路径")
@click.option("--format", "output_format", type=click.Choice(["markdown", "json", "both"]), default="markdown", help="输出格式")
@click.option("--no-adversarial", is_flag=True, help="禁用对抗校验")
@click.pass_context
def analyze(ctx, case_dir, dimensions, model, output, output_format, no_adversarial):
    """对案件目录进行异常检测"""
    config_file = ctx.obj.get("config_file")
    if config_file:
        config = AppConfig.from_file(config_file)
    else:
        config = AppConfig.from_env()
    
    if model:
        config.llm.model = model
    if dimensions:
        config.detection.dimensions = list(dimensions)
    if no_adversarial:
        config.detection.enable_adversarial_check = False
    
    async def run():
        engine = DetectionEngine(config)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("正在检测...", total=None)
            result = await engine.run_detection(case_dir)
            progress.update(task, description="检测完成！")
        
        # Output results
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            if output_format in ["markdown", "both"]:
                md_path = output_path.with_suffix(".md") if output_path.suffix != ".md" else output_path
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(result.report_markdown)
                console.print(f"[green]Markdown 报告已保存至：{md_path}[/green]")
            
            if output_format in ["json", "both"]:
                json_path = output_path.with_suffix(".json") if output_path.suffix != ".json" else output_path
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)
                console.print(f"[green]JSON 报告已保存至：{json_path}[/green]")
        else:
            console.print(Panel(result.report_markdown, title="检测报告", border_style="blue"))
        
        # Summary
        summary_table = Table(title="检测摘要")
        summary_table.add_column("项目", style="cyan")
        summary_table.add_column("值", style="green")
        summary_table.add_row("案件名称", result.case_name)
        summary_table.add_row("综合异常等级", result.risk_level)
        summary_table.add_row("材料完整性", f"{result.completeness_score:.1f}%")
        summary_table.add_row("总 Token 消耗", str(result.total_tokens))
        console.print(summary_table)
    
    asyncio.run(run())


@cli.command()
@click.argument("case_dir", type=click.Path(exists=True))
@click.option("--dimensions", "-d", multiple=True, help="指定检测维度")
def dry_run(case_dir, dimensions):
    """预览检测流程和 Token 消耗"""
    from .detector import FileLoader
    from .prompts import DIMENSION_PROMPTS
    
    loader = FileLoader(case_dir)
    loader.load()
    completeness, missing = loader.validate()
    materials = loader.get_materials_text()
    
    dims = list(dimensions) if dimensions else list(DIMENSION_PROMPTS.keys())
    
    console.print(Panel(
        f"材料完整性：{completeness:.1f}/100\n"
        f"缺失材料：{', '.join(missing) if missing else '无'}\n"
        f"材料总字符：{len(materials)}\n"
        f"预估 Token：{int(len(materials) * 0.5)}",
        title="材料分析",
        border_style="cyan",
    ))
    
    table = Table(title="检测维度预估")
    table.add_column("维度", style="cyan")
    table.add_column("Prompt 字符", justify="right")
    table.add_column("预估 Token", justify="right")
    
    total_tokens = 0
    for dim in dims:
        if dim in DIMENSION_PROMPTS:
            prompt = DIMENSION_PROMPTS[dim]
            tokens = int(len(prompt) * 0.5)
            total_tokens += tokens
            table.add_row(dim, str(len(prompt)), str(tokens))
    
    table.add_row("总计", "", str(total_tokens), style="bold green")
    console.print(table)


@cli.command()
def list_dimensions():
    """列出所有可用的检测维度"""
    from .prompts import DIMENSION_PROMPTS
    
    table = Table(title="可用检测维度")
    table.add_column("维度 ID", style="cyan")
    table.add_column("说明", style="green")
    
    descriptions = {
        "procedure": "程序操作与正当性检测",
        "evidence": "证据采信与审查一致性检测",
        "fact_finding": "事实认定与关键情节记录检测（26项）",
        "law_application": "法律适用与检索脱节检测",
        "discretion": "自由裁量权滥用与惯常脱离检测",
        "logic": "逻辑闭环断裂检测",
        "temporal": "时间一致性检测",
        "semantic_drift": "语义漂移检测",
        "negative_space": "缺失信息分析（负空间检测）",
        "case_deviation": "类案偏离量化检测",
        "procedure_graph": "程序行为链建模检测",
        "coupling": "惯性耦合组合高风险检测",
    }
    
    for dim in DIMENSION_PROMPTS:
        table.add_row(dim, descriptions.get(dim, ""))
    
    console.print(table)


def main():
    """CLI entry point"""
    cli()


if __name__ == "__main__":
    main()
