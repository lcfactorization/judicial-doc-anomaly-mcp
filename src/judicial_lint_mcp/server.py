"""MCP Server v0.4.0 — Bridge Architecture.

MCP Server is a BRIDGE between AI Agents and Skills.
It does NOT call any LLM. It only:
  1. Loads & renders SKILL.md templates → returns prompts for Agent to send to its own LLM
  2. Parses LLM responses from Agent → returns structured data
  3. Builds formatted reports from structured data
  4. Manages Skill discovery, pipeline definitions, and Skill file updates

Agent decides what to call, in what order, with what parameters.
Agent calls its own LLM with the prompts returned by this server.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .report_builder import ReportBuilder
from .response_parser import ResponseParser
from .skill_runner import SkillLoader, TemplateRenderer

logger = logging.getLogger("judicial-lint")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)

mcp = FastMCP("judicial-lint")

_parser = ResponseParser()
_builder = ReportBuilder()
_loader = SkillLoader()
_renderer = TemplateRenderer(_loader)


# ── MCP Resources ──────────────────────────────────────────────


@mcp.resource("judicial-lint://skills")
def get_skills_resource() -> str:
    try:
        skills = _loader.list_skills()
        lines = ["# 可用 Skills 列表\n"]
        for s in skills:
            lines.append(f"## {s['name']}")
            lines.append(f"- 标题：{s['title']}")
            lines.append(f"- 类型：{s['type']}")
            lines.append(f"- 层级：{s['layer']}")
            lines.append(f"- 顺序：{s['order']}")
            if s["depends_on"]:
                lines.append(f"- 依赖：{', '.join(s['depends_on'])}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skills resource error: %s", e)
        return f"# 错误\n无法加载 Skills 列表：{e}"


@mcp.resource("judicial-lint://taxonomy")
def get_taxonomy_resource() -> str:
    try:
        _, body = _loader.load("_taxonomy")
        return body
    except Exception as e:
        logger.error("taxonomy resource error: %s", e)
        return f"# 错误\n无法加载分类体系：{e}"


@mcp.resource("judicial-lint://system")
def get_system_resource() -> str:
    try:
        _, body = _loader.load("_system")
        return body
    except Exception as e:
        logger.error("system resource error: %s", e)
        return f"# 错误\n无法加载系统指令：{e}"


# ── MCP Tools ──────────────────────────────────────────────────


@mcp.tool()
def render_skill(
    skill_name: str,
    variables: dict | None = None,
) -> str:
    """加载并渲染一个 SKILL.md 模板，返回完整的 system_prompt 和 user_prompt，
    供 AI Agent 发送给自己的 LLM。

    skill_name: Skill 名称（如 'dimensions/02_evidence'、'phases/adversarial'）
    variables: 模板变量字典（如 {"materials": "案件材料文本", "previous_results": "前序结果"}）

    返回 JSON 字符串，包含：
    - skill_name: Skill 名称
    - skill_title: Skill 标题
    - system_prompt: 系统提示词（含术语规范、分类体系、中立性校验、输出格式要求）
    - user_prompt: 用户提示词（渲染后的 SKILL.md 正文）
    - meta: Skill 元数据（type, layer, order, depends_on, output_format）
    """
    try:
        logger.info("render_skill: 开始 skill=%s, variables=%s", skill_name, list(variables.keys()) if variables else "None")
        meta, body = _loader.load(skill_name)
        logger.info("render_skill: 加载成功 skill=%s, title=%s, body_len=%d", meta.name, meta.title, len(body))
        rendered = _renderer.render(body, variables)
        logger.info("render_skill: 渲染完成 skill=%s, rendered_len=%d", meta.name, len(rendered))
        system_prompt = _build_system_prompt(meta)
        logger.info("render_skill: 系统提示词构建完成 skill=%s, sys_prompt_len=%d", meta.name, len(system_prompt))

        result = {
            "skill_name": meta.name,
            "skill_title": meta.title,
            "system_prompt": system_prompt,
            "user_prompt": rendered,
            "meta": {
                "type": meta.type,
                "layer": meta.layer,
                "order": meta.order,
                "depends_on": meta.depends_on,
                "output_format": meta.output_format,
            },
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    except FileNotFoundError as e:
        logger.error("render_skill: Skill 不存在: %s", e)
        return json.dumps({"error": f"Skill 不存在：{e}"}, ensure_ascii=False)
    except Exception as e:
        logger.error("render_skill: %s", e, exc_info=True)
        return json.dumps({"error": f"渲染异常：{e}"}, ensure_ascii=False)


@mcp.tool()
def render_pipeline(
    pipeline_name: str,
    variables: dict | None = None,
) -> str:
    """加载并渲染一个流水线中的所有 SKILL.md 模板，返回每个 Skill 的完整提示词，
    供 AI Agent 按顺序发送给自己的 LLM。

    pipeline_name: 流水线名称（如 'full_scan'、'evidence_focus'、'quick_scan'）
    variables: 全局模板变量字典，会应用到每个 Skill（如 {"materials": "案件材料文本"}）

    返回 JSON 字符串，包含：
    - pipeline: 流水线名称
    - skills: 按顺序排列的 Skill 列表，每项包含 skill_name, skill_title, system_prompt, user_prompt, meta
    - total_skills: Skill 总数
    - estimated_prompt_chars: 预估提示词总字符数
    """
    try:
        logger.info("render_pipeline: 开始 pipeline=%s, variables=%s", pipeline_name, list(variables.keys()) if variables else "None")
        _, pipeline_body = _loader.load(f"pipelines/{pipeline_name}")
        logger.info("render_pipeline: 流水线加载成功 pipeline=%s, body_len=%d", pipeline_name, len(pipeline_body))
        skill_refs = _parse_pipeline_skills(pipeline_body)
        logger.info("render_pipeline: 解析到 %d 个 skill 引用: %s", len(skill_refs), skill_refs)

        skills_output = []
        total_chars = 0

        for ref in skill_refs:
            try:
                meta, body = _loader.load(ref)
                logger.info("render_pipeline: 加载 skill=%s, title=%s, body_len=%d", ref, meta.title, len(body))
                rendered = _renderer.render(body, variables)
                system_prompt = _build_system_prompt(meta)
                total_chars += len(system_prompt) + len(rendered)
                logger.info("render_pipeline: 渲染 skill=%s, sys_len=%d, user_len=%d", ref, len(system_prompt), len(rendered))

                skills_output.append({
                    "skill_name": meta.name,
                    "skill_title": meta.title,
                    "system_prompt": system_prompt,
                    "user_prompt": rendered,
                    "meta": {
                        "type": meta.type,
                        "layer": meta.layer,
                        "order": meta.order,
                        "depends_on": meta.depends_on,
                        "output_format": meta.output_format,
                    },
                })
            except FileNotFoundError:
                logger.warning("render_pipeline: Skill 未找到 ref=%s", ref)
                skills_output.append({
                    "skill_name": ref,
                    "skill_title": "",
                    "system_prompt": "",
                    "user_prompt": "",
                    "meta": {},
                    "error": "Skill 未找到",
                })

        result = {
            "pipeline": pipeline_name,
            "skills": skills_output,
            "total_skills": len(skills_output),
            "estimated_prompt_chars": total_chars,
            "estimated_prompt_tokens": int(total_chars * 0.5),
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    except FileNotFoundError as e:
        logger.error("render_pipeline: %s", e)
        return json.dumps({"error": f"流水线不存在：{e}"}, ensure_ascii=False)
    except Exception as e:
        logger.error("render_pipeline: %s", e, exc_info=True)
        return json.dumps({"error": f"渲染异常：{e}"}, ensure_ascii=False)


@mcp.tool()
def parse_response(
    dimension: str,
    response: str,
    dimension_index: int = 0,
) -> str:
    """将 LLM 的响应文本解析为结构化异常数据。
    AI Agent 获取 LLM 响应后，调用此工具将其转换为标准化的异常项列表。

    dimension: 维度标识（如 'procedure', 'evidence', 'fact_finding'）
    response: LLM 返回的原始响应文本
    dimension_index: 维度索引（0-15），用于分类体系映射

    返回 JSON 字符串，包含：
    - dimension: 维度标识
    - anomalies: 异常项列表，每项包含 item_name, description, beneficiary, confidence, f_code, a_code, original_text, legal_analysis
    - summary: 维度摘要
    - risk_level: 风险等级（low/medium/high/critical）
    - anomaly_count: 异常项数量
    """
    try:
        logger.info("parse_response: 开始 dimension=%s, dim_index=%d, response_len=%d", dimension, dimension_index, len(response))
        dim_result = _parser.parse_dimension_result(dimension, response, dimension_index)
        logger.info("parse_response: 完成 dimension=%s, anomaly_count=%d, risk_level=%s", dim_result.dimension, len(dim_result.anomalies), dim_result.risk_level)

        result = {
            "dimension": dim_result.dimension,
            "anomaly_count": len(dim_result.anomalies),
            "risk_level": dim_result.risk_level,
            "summary": dim_result.summary,
            "anomalies": [
                {
                    "item_name": a.item_name,
                    "description": a.description,
                    "beneficiary": a.beneficiary,
                    "confidence": a.confidence,
                    "f_code": a.f_code,
                    "a_code": a.a_code,
                    "original_text": a.original_text,
                    "legal_analysis": a.legal_analysis,
                }
                for a in dim_result.anomalies
            ],
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error("parse_response: %s", e, exc_info=True)
        return json.dumps({"error": f"解析异常：{e}"}, ensure_ascii=False)


@mcp.tool()
def build_report(
    case_name: str,
    dimension_results_json: str,
    doc_type: str = "判决书",
    model_name: str = "AI Agent",
) -> str:
    """从结构化异常数据生成格式化的 Markdown 检测报告。
    AI Agent 收集完所有维度的解析结果后，调用此工具生成最终报告。

    case_name: 案件名称
    dimension_results_json: JSON 字符串，包含所有维度的解析结果列表
        格式：[{"dimension": "procedure", "anomalies": [...], "risk_level": "high", "summary": "..."}, ...]
    doc_type: 文书类型（默认 '判决书'）
    model_name: 使用的模型名称（默认 'AI Agent'）

    返回格式化的 Markdown 报告文本。
    """
    try:
        from .models import AnomalyItem, DetectionResult, DimensionResult

        logger.info("build_report: 开始 case=%s, doc_type=%s, model=%s", case_name, doc_type, model_name)
        dim_data_list = json.loads(dimension_results_json)
        logger.info("build_report: 解析到 %d 个维度数据", len(dim_data_list))
        dimension_results = []

        for dim_data in dim_data_list:
            logger.info("build_report: 处理维度 %s, 异常项=%d", dim_data.get("dimension"), len(dim_data.get("anomalies", [])))
            anomalies = []
            for a_data in dim_data.get("anomalies", []):
                raw_conf = a_data.get("confidence", "medium")
                if isinstance(raw_conf, (int, float)):
                    raw_conf = "high" if raw_conf >= 0.8 else ("medium" if raw_conf >= 0.5 else "low")
                    logger.info("build_report: 置信度类型转换 %.2f → %s", a_data.get("confidence"), raw_conf)
                anomalies.append(AnomalyItem(
                    dimension=dim_data["dimension"],
                    item_name=a_data.get("item_name", ""),
                    description=a_data.get("description", ""),
                    beneficiary=a_data.get("beneficiary", ""),
                    confidence=str(raw_conf),
                    f_code=a_data.get("f_code", ""),
                    a_code=a_data.get("a_code", ""),
                    original_text=a_data.get("original_text", ""),
                    legal_analysis=a_data.get("legal_analysis", ""),
                ))
                logger.info(
                    "build_report: 异常项 item=%s, beneficiary=%s, confidence=%s, f_code=%s",
                    a_data.get("item_name", "")[:30], a_data.get("beneficiary", ""), raw_conf, a_data.get("f_code", ""),
                )

            dimension_results.append(DimensionResult(
                dimension=dim_data["dimension"],
                anomalies=anomalies,
                summary=dim_data.get("summary", ""),
                risk_level=dim_data.get("risk_level", "low"),
            ))

        detection_result = DetectionResult(
            case_name=case_name,
            doc_type=doc_type,
            model_name=model_name,
            detection_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            dimension_results=dimension_results,
        )

        report = _builder.build_report(detection_result)
        logger.info("build_report: 报告生成完成, 长度=%d", len(report))
        return report

    except json.JSONDecodeError as e:
        logger.error("build_report: JSON 解析失败: %s", e)
        return f"# 错误\nJSON 解析失败：{e}"
    except Exception as e:
        logger.error("build_report: %s", e, exc_info=True)
        return f"# 错误\n报告生成异常：{e}"


@mcp.tool()
def list_skills(
    category: str | None = None,
) -> str:
    """列出所有可用的 Skills，可选按类型筛选。

    category: 可选筛选类型（如 'dimension'、'phase'、'pipeline'）

    返回 Skill 列表（Markdown 表格格式）。
    """
    try:
        skills = _loader.list_skills(category)

        if not skills:
            return "当前没有可用的 Skill。请检查 skills/ 目录。"

        lines = ["# 可用 Skills\n"]
        lines.append("| 名称 | 标题 | 类型 | 层级 | 顺序 | 依赖 |")
        lines.append("|------|------|------|------|------|------|")
        for s in skills:
            deps = ", ".join(s["depends_on"]) if s["depends_on"] else "-"
            lines.append(
                f"| {s['name']} | {s['title']} | {s['type']} | {s['layer']} | {s['order']} | {deps} |"
            )
        return "\n".join(lines)

    except Exception as e:
        logger.error("list_skills: %s", e, exc_info=True)
        return f"# 错误\n无法列出 Skills：{e}"


@mcp.tool()
def write_skill(
    skill_name: str,
    content: str,
) -> str:
    """写入或更新一个 SKILL.md 文件。供 AI Agent 迭代优化提示词使用。

    skill_name: Skill 名称（如 'dimensions/02_evidence'、'_system'）
    content: 完整的 SKILL.md 内容（包含 frontmatter 和正文）

    返回操作结果。
    """
    try:
        parts = skill_name.split("/")
        target = _loader.skills_dir / Path(*parts)
        if target.is_dir():
            target = target / "skill.md"
        if not target.suffix:
            target = target.with_suffix(".md")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

        _loader._cache.pop(skill_name, None)

        return f"✅ Skill `{skill_name}` 已写入：{target}"

    except Exception as e:
        logger.error("write_skill: %s", e, exc_info=True)
        return f"# 错误\n写入异常：{e}"


# ── Helper Functions ───────────────────────────────────────────


def _build_system_prompt(meta) -> str:
    logger.info("_build_system_prompt: 构建 skill=%s, output_format=%s", meta.name, meta.output_format)
    system_content = _loader.load_system_skill("_system")
    taxonomy_content = _loader.load_system_skill("_taxonomy")
    neutrality_content = _loader.load_system_skill("_neutrality")
    output_format_content = _loader.load_system_skill("_output_format")
    logger.info(
        "_build_system_prompt: 系统技能加载完成 system=%d, taxonomy=%d, neutrality=%d, output_format=%d",
        len(system_content), len(taxonomy_content), len(neutrality_content), len(output_format_content),
    )

    parts = [system_content]

    if meta.output_format not in ("preprocessed_data", "graph_structure"):
        parts.append(taxonomy_content)
        parts.append(neutrality_content)

    if output_format_content:
        parts.append(output_format_content)
    else:
        parts.append(
            "\n## 输出格式要求（必须严格遵守）\n"
            "对每个检测到的异常项，必须使用以下格式：\n\n"
            "#### 1. 异常项：[异常项名称]\n\n"
            "- 具体表现：[详细描述，引用原文段落并标注页码/段落/行号，内容必须完整不得省略]\n"
            "- 原文引用：[判决书原文，完整引用不得截断]\n"
            "- 指向获益方：[原告/被告/双方/无]\n"
            "- 异常程度：[疑似/可能/高度可能/确定]\n"
            "- 法理分析：[详细分析，引用具体法条原文，论证必须完整不得省略]\n\n"
            "注意事项：\n"
            "1. 每个异常项必须以'#### 序号. 异常项：'开头\n"
            "2. 具体表现和法理分析必须完整输出，不得用省略号或'略'代替\n"
            "3. 原文引用必须完整，不得截断\n"
            "4. 不要在开头添加角色扮演类语句（如'好的，作为专业的...'）\n"
            "5. 不要输出'总结'或'综合结论'作为单独的异常项\n"
            "6. 证据描述必须明确标注提交方（如'原告提交的录音证据5'）\n"
            "7. 所有当事人称谓必须使用一审术语\n"
        )

    return "\n\n".join(p for p in parts if p)


def _parse_pipeline_skills(body: str) -> list[str]:
    skills = []
    for line in body.split("\n"):
        line = line.strip()
        if line.startswith("- skill:"):
            skill_name = line.split(":", 1)[1].strip()
            if skill_name and skill_name not in skills:
                skills.append(skill_name)
    logger.info("_parse_pipeline_skills: 解析到 %d 个 skill: %s", len(skills), skills)
    return skills


def main():
    mcp.run()


if __name__ == "__main__":
    main()
