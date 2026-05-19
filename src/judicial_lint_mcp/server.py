"""MCP Server v0.5.1 — Bridge Architecture with Long-Context Support.

MCP Server is a BRIDGE between AI Agents and Skills.
It does NOT call any LLM. It only:
  1. Loads & renders SKILL.md templates → returns prompts for Agent to send to its own LLM
  2. Parses LLM responses from Agent → returns structured data
  3. Builds formatted reports from structured data
  4. Manages Skill discovery, pipeline definitions, and Skill file updates
  5. Provides token estimation, material compaction, and pipeline state management

v0.5.1 changes:
  - PipelineStateManager: thread-safe, TTL-expiring, file-persisted state (fixes memory leak & crash recovery)
  - Token estimation: mixed CJK/Latin heuristic instead of flat 2.0 ratio
  - Structured error codes: ErrorCode enum + make_error() with retryable flag
  - Anti-Laziness directive injected into plan_pipeline output
  - JSON parse_response: robust regex extraction + self-correction feedback on failure
  - compact_materials: anonymize option for data desensitization
  - Audit trail: every tool call logged with session_id for traceability
"""

import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .error_codes import ErrorCode, make_error
from .pipeline_state import PipelineStateManager
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

_state_mgr = PipelineStateManager()
_audit_lock = threading.Lock()
_audit_log: list[dict] = []


def _record_audit(session_id: str, tool: str, action: str, detail: str = "") -> None:
    entry = {
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "tool": tool,
        "action": action,
        "detail": detail,
    }
    with _audit_lock:
        _audit_log.append(entry)


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = len(re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', text))
    total_chars = len(text)
    non_cjk = total_chars - cjk
    return int(cjk / 1.5 + non_cjk / 4.0)


ANTI_LAZINESS_DIRECTIVE = (
    "\n\n---\n"
    "**⚠️ Anti-Laziness 指令（必须遵守）**：\n"
    "你必须在当前对话轮次中，静默且完整地调用完所有维度的 render_skill 和 parse_response，"
    "绝对不允许中途停顿、询问用户是否继续、或以'操作同理'等理由省略任何维度。"
    "每完成一个维度，立即调用下一个，直到全部完成后再调用 build_report。\n"
    "---\n"
)


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
def estimate_tokens(
    skill_name: str | None = None,
    pipeline_name: str | None = None,
    materials_chars: int = 0,
) -> str:
    """预估 Skill 或 Pipeline 的 token 用量，帮助 Agent 做预算决策。

    调用 render_skill 之前先调用此工具，判断是否会超出上下文窗口。
    如果预估超限，Agent 应使用 compact_materials 压缩材料后再调用 render_skill。

    skill_name: 单个 Skill 名称（如 'dimensions/02_evidence'）
    pipeline_name: 流水线名称（如 'full_scan'），与 skill_name 二选一
    materials_chars: 案件材料的字符数（用于估算变量注入后的总 token）

    返回 JSON 字符串，包含：
    - estimated_tokens: 预估总 token 数
    - breakdown: 分项 token 估算（system_prompt, user_prompt_template, materials）
    - fits_in_128k / fits_in_200k: 是否适配常见上下文窗口
    - recommendation: 建议操作（'proceed' / 'compact_materials' / 'use_skill_by_skill'）
    """
    try:
        breakdown = {
            "system_prompt": 0,
            "user_prompt_template": 0,
            "materials": _estimate_tokens(" " * materials_chars) if materials_chars else 0,
        }

        if pipeline_name:
            _, pipeline_body = _loader.load(f"pipelines/{pipeline_name}")
            skill_refs = _parse_pipeline_skills(pipeline_body)
            total_sys = 0
            total_user = 0
            for ref in skill_refs:
                try:
                    meta, body = _loader.load(ref)
                    sys_prompt = _build_system_prompt(meta)
                    total_sys += len(sys_prompt)
                    total_user += len(body)
                except FileNotFoundError:
                    pass
            breakdown["system_prompt"] = _estimate_tokens(" " * total_sys)
            breakdown["user_prompt_template"] = _estimate_tokens(" " * total_user)
            breakdown["skill_count"] = len(skill_refs)

        elif skill_name:
            meta, body = _loader.load(skill_name)
            sys_prompt = _build_system_prompt(meta)
            breakdown["system_prompt"] = _estimate_tokens(sys_prompt)
            breakdown["user_prompt_template"] = _estimate_tokens(body)

        total_tokens = sum(v for v in breakdown.values() if isinstance(v, int))

        fits_128k = total_tokens < 120_000
        fits_200k = total_tokens < 190_000

        if not fits_128k:
            recommendation = "use_skill_by_skill"
        elif total_tokens > 80_000:
            recommendation = "compact_materials"
        else:
            recommendation = "proceed"

        result = {
            "estimated_tokens": total_tokens,
            "breakdown": breakdown,
            "fits_in_128k": fits_128k,
            "fits_in_200k": fits_200k,
            "recommendation": recommendation,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    except FileNotFoundError as e:
        logger.error("estimate_tokens: skill not found: %s", e)
        return make_error(ErrorCode.SKILL_NOT_FOUND, f"Skill 不存在：{e}", {"skill_name": skill_name})
    except Exception as e:
        logger.error("estimate_tokens: %s", e, exc_info=True)
        return make_error(ErrorCode.INTERNAL_ERROR, f"估算异常：{e}")


@mcp.tool()
def compact_materials(
    materials: str,
    max_tokens: int = 40000,
    strategy: str = "extract_key_facts",
    anonymize: bool = False,
) -> str:
    """压缩案件材料以适配 token 预算。

    当案件材料过长时，Agent 应先调用此工具压缩材料，
    再将压缩结果作为 render_skill 的 variables.materials 传入。

    materials: 原始案件材料文本
    max_tokens: 压缩后的目标 token 数（默认 40000，约 80000 字符）
    strategy: 压缩策略
      - 'extract_key_facts': 提取关键事实和争议焦点（默认，适合检测用）
      - 'truncate': 简单截断到目标长度
      - 'outline': 保留文档结构大纲，删除详细内容
    anonymize: 是否自动脱敏（替换人名/地址/案号等敏感信息，默认 False）

    返回 JSON 字符串，包含：
    - compacted: 压缩后的文本
    - original_tokens: 原始 token 估算
    - compacted_tokens: 压缩后 token 估算
    - compression_ratio: 压缩比
    - strategy_used: 实际使用的策略
    - anonymized: 是否执行了脱敏
    """
    try:
        if anonymize:
            materials = _anonymize_text(materials)

        original_tokens = _estimate_tokens(materials)
        max_chars = int(max_tokens * 2.0)

        if original_tokens <= max_tokens:
            return json.dumps({
                "compacted": materials,
                "original_tokens": original_tokens,
                "compacted_tokens": original_tokens,
                "compression_ratio": 1.0,
                "strategy_used": "none_needed",
                "anonymized": anonymize,
            }, ensure_ascii=False)

        if strategy == "truncate":
            compacted = materials[:max_chars]

        elif strategy == "outline":
            compacted = _outline_compact(materials, max_chars)

        else:
            compacted = _extract_key_facts(materials, max_chars)

        compacted_tokens = _estimate_tokens(compacted)
        ratio = compacted_tokens / original_tokens if original_tokens > 0 else 1.0

        result = {
            "compacted": compacted,
            "original_tokens": original_tokens,
            "compacted_tokens": compacted_tokens,
            "compression_ratio": round(ratio, 2),
            "strategy_used": strategy,
            "anonymized": anonymize,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error("compact_materials: %s", e, exc_info=True)
        return make_error(ErrorCode.INTERNAL_ERROR, f"压缩异常：{e}")


@mcp.tool()
def plan_pipeline(
    pipeline_name: str,
    variables: dict | None = None,
) -> str:
    """规划流水线执行计划，返回 Skill 元数据列表（不含完整提示词）。

    v0.5.1: 替代旧版 render_pipeline（会一次性返回所有 Skill 的完整提示词，
    导致长上下文溢出）。Agent 应根据此计划逐个调用 render_skill。

    pipeline_name: 流水线名称（如 'full_scan'、'evidence_focus'、'quick_scan'）
    variables: 全局模板变量字典的 keys（仅用于估算，不传值）
        如 {"materials": "", "previous_results": ""}

    返回 JSON 字符串，包含：
    - pipeline: 流水线名称
    - skills: 按顺序排列的 Skill 元数据（skill_name, skill_title, meta, estimated_tokens）
    - total_skills: Skill 总数
    - total_estimated_tokens: 预估总 token 数
    - execution_hint: 执行建议（'one_by_one' / 'batch_3' / 'batch_5'）
    - session_id: 流水线会话 ID（用于 pipeline_state）
    """
    try:
        logger.info("plan_pipeline: 开始 pipeline=%s", pipeline_name)
        _, pipeline_body = _loader.load(f"pipelines/{pipeline_name}")
        skill_refs = _parse_pipeline_skills(pipeline_body)
        logger.info("plan_pipeline: 解析到 %d 个 skill", len(skill_refs))

        skills_plan = []
        total_tokens = 0

        for ref in skill_refs:
            try:
                meta, body = _loader.load(ref)
                sys_prompt = _build_system_prompt(meta)
                skill_tokens = _estimate_tokens(sys_prompt) + _estimate_tokens(body)
                total_tokens += skill_tokens

                skills_plan.append({
                    "skill_name": meta.name,
                    "skill_title": meta.title,
                    "meta": {
                        "type": meta.type,
                        "layer": meta.layer,
                        "order": meta.order,
                        "depends_on": meta.depends_on,
                        "output_format": meta.output_format,
                    },
                    "estimated_tokens": skill_tokens,
                })
            except FileNotFoundError:
                logger.warning("plan_pipeline: Skill 未找到 ref=%s", ref)
                skills_plan.append({
                    "skill_name": ref,
                    "skill_title": "",
                    "meta": {},
                    "estimated_tokens": 0,
                    "error": "Skill 未找到",
                })

        if total_tokens > 100_000:
            execution_hint = "one_by_one"
        elif total_tokens > 50_000:
            execution_hint = "batch_3"
        else:
            execution_hint = "batch_5"

        session_id = datetime.now().strftime("%Y%m%d%H%M%S")
        initial_state = {
            "pipeline": pipeline_name,
            "skills": skill_refs,
            "completed": [],
            "current_index": 0,
            "results": {},
        }
        _state_mgr.save(session_id, initial_state)
        _record_audit(session_id, "plan_pipeline", "created", f"pipeline={pipeline_name}, skills={len(skill_refs)}")

        result = {
            "pipeline": pipeline_name,
            "skills": skills_plan,
            "total_skills": len(skills_plan),
            "total_estimated_tokens": total_tokens,
            "execution_hint": execution_hint,
            "session_id": session_id,
            "anti_laziness_directive": ANTI_LAZINESS_DIRECTIVE,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    except FileNotFoundError as e:
        logger.error("plan_pipeline: %s", e)
        return make_error(ErrorCode.PIPELINE_NOT_FOUND, f"流水线不存在：{e}", {"pipeline_name": pipeline_name})
    except Exception as e:
        logger.error("plan_pipeline: %s", e, exc_info=True)
        return make_error(ErrorCode.INTERNAL_ERROR, f"规划异常：{e}")


@mcp.tool()
def pipeline_progress(
    session_id: str,
    action: str = "status",
    skill_name: str | None = None,
    result_summary: str | None = None,
) -> str:
    """管理流水线执行进度，支持断点续传。

    Agent 在每个 Skill 执行完成后应调用此工具更新进度。
    如果中途断开，可通过 action='resume' 获取未完成的 Skill 列表。

    session_id: 流水线会话 ID（由 plan_pipeline 返回）
    action: 操作类型
      - 'status': 查询当前进度（默认）
      - 'complete': 标记一个 Skill 为已完成
      - 'resume': 获取未完成的 Skill 列表（断点续传）
      - 'reset': 重置流水线进度
    skill_name: 要标记完成的 Skill 名称（action='complete' 时必填）
    result_summary: 该 Skill 的执行结果摘要（可选，用于断点续传时恢复上下文）

    返回 JSON 字符串，包含：
    - session_id: 会话 ID
    - action: 执行的操作
    - completed_count: 已完成 Skill 数
    - total_count: 总 Skill 数
    - progress_pct: 完成百分比
    - next_skill: 下一个待执行的 Skill 名称（如有）
    - remaining_skills: 剩余 Skill 列表（action='resume' 时）
    """
    try:
        state = _state_mgr.get(session_id)
        if state is None:
            return make_error(ErrorCode.SESSION_NOT_FOUND, f"会话不存在或已过期：{session_id}", {"session_id": session_id})

        if action == "complete":
            if not skill_name:
                return make_error(ErrorCode.INVALID_PARAMS, "action='complete' 需要 skill_name")
            if skill_name not in state["completed"]:
                state["completed"].append(skill_name)
            if result_summary:
                state["results"][skill_name] = result_summary
            state["current_index"] = min(
                state["skills"].index(skill_name) + 1 if skill_name in state["skills"] else state["current_index"],
                len(state["skills"]),
            )
            _state_mgr.save(session_id, state)
            _record_audit(session_id, "pipeline_progress", "complete", f"skill={skill_name}")
            logger.info("pipeline_progress: 完成 skill=%s, 进度=%d/%d", skill_name, len(state["completed"]), len(state["skills"]))

        elif action == "reset":
            state["completed"] = []
            state["current_index"] = 0
            state["results"] = {}
            _state_mgr.save(session_id, state)
            _record_audit(session_id, "pipeline_progress", "reset")
            logger.info("pipeline_progress: 重置 session=%s", session_id)

        remaining = [s for s in state["skills"] if s not in state["completed"]]
        next_skill = remaining[0] if remaining else None

        result = {
            "session_id": session_id,
            "action": action,
            "completed_count": len(state["completed"]),
            "total_count": len(state["skills"]),
            "progress_pct": round(len(state["completed"]) / len(state["skills"]) * 100) if state["skills"] else 100,
            "next_skill": next_skill,
        }

        if action == "resume":
            result["remaining_skills"] = remaining
            result["previous_results"] = state.get("results", {})

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error("pipeline_progress: %s", e, exc_info=True)
        return make_error(ErrorCode.STATE_ERROR, f"进度管理异常：{e}")


@mcp.tool()
def render_skill(
    skill_name: str,
    variables: dict | None = None,
) -> str:
    """加载并渲染一个 SKILL.md 模板，返回完整的 system_prompt 和 user_prompt，
    供 AI Agent 发送给自己的 LLM。

    建议：先调用 estimate_tokens 检查 token 用量，再调用此工具。
    对于长材料，先调用 compact_materials 压缩后再传入。

    skill_name: Skill 名称（如 'dimensions/02_evidence'、'phases/adversarial'）
    variables: 模板变量字典（如 {"materials": "案件材料文本", "previous_results": "前序结果"}）

    返回 JSON 字符串，包含：
    - skill_name: Skill 名称
    - skill_title: Skill 标题
    - system_prompt: 系统提示词（含术语规范、分类体系、中立性校验、输出格式要求）
    - user_prompt: 用户提示词（渲染后的 SKILL.md 正文）
    - meta: Skill 元数据（type, layer, order, depends_on, output_format）
    - token_estimate: 预估 token 数
    """
    try:
        logger.info("render_skill: 开始 skill=%s, variables=%s", skill_name, list(variables.keys()) if variables else "None")
        meta, body = _loader.load(skill_name)
        logger.info("render_skill: 加载成功 skill=%s, title=%s, body_len=%d", meta.name, meta.title, len(body))
        rendered = _renderer.render(body, variables)
        logger.info("render_skill: 渲染完成 skill=%s, rendered_len=%d", meta.name, len(rendered))
        system_prompt = _build_system_prompt(meta)
        logger.info("render_skill: 系统提示词构建完成 skill=%s, sys_prompt_len=%d", meta.name, len(system_prompt))

        total_chars = len(system_prompt) + len(rendered)

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
            "token_estimate": _estimate_tokens(" " * total_chars),
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    except FileNotFoundError as e:
        logger.error("render_skill: Skill 不存在: %s", e)
        return make_error(ErrorCode.SKILL_NOT_FOUND, f"Skill 不存在：{e}", {"skill_name": skill_name})
    except Exception as e:
        logger.error("render_skill: %s", e, exc_info=True)
        return make_error(ErrorCode.RENDER_FAILED, f"渲染异常：{e}", {"skill_name": skill_name})


@mcp.tool()
def render_pipeline(
    pipeline_name: str,
    variables: dict | None = None,
) -> str:
    """[已弃用] 请使用 plan_pipeline + render_skill 逐个调用。
    旧版一次性返回所有 Skill 的完整提示词，长流水线会导致上下文溢出。

    保留此工具仅用于向后兼容。对于超过 5 个 Skill 的流水线，强烈建议使用 plan_pipeline。
    """
    try:
        logger.warning("render_pipeline: 已弃用，建议使用 plan_pipeline + render_skill")
        _, pipeline_body = _loader.load(f"pipelines/{pipeline_name}")
        skill_refs = _parse_pipeline_skills(pipeline_body)

        skills_output = []
        total_chars = 0

        for ref in skill_refs:
            try:
                meta, body = _loader.load(ref)
                rendered = _renderer.render(body, variables)
                system_prompt = _build_system_prompt(meta)
                total_chars += len(system_prompt) + len(rendered)

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
            "estimated_prompt_tokens": _estimate_tokens(" " * total_chars),
            "warning": "此工具已弃用，建议使用 plan_pipeline + render_skill 逐个调用以避免上下文溢出",
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    except FileNotFoundError as e:
        logger.error("render_pipeline: %s", e)
        return make_error(ErrorCode.PIPELINE_NOT_FOUND, f"流水线不存在：{e}", {"pipeline_name": pipeline_name})
    except Exception as e:
        logger.error("render_pipeline: %s", e, exc_info=True)
        return make_error(ErrorCode.RENDER_FAILED, f"渲染异常：{e}", {"pipeline_name": pipeline_name})


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
                    "original_text_location": getattr(a, "original_text_location", ""),
                    "evidence_reference": getattr(a, "evidence_reference", ""),
                    "legal_analysis": a.legal_analysis,
                    "legal_basis": getattr(a, "legal_basis", ""),
                    "suggestion": getattr(a, "suggestion", ""),
                    "deduction": getattr(a, "deduction", 0),
                }
                for a in dim_result.anomalies
            ],
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    except json.JSONDecodeError as e:
        logger.error("parse_response: JSON 解析失败: %s", e)
        return make_error(ErrorCode.PARSE_FAILED, f"JSON 解析失败，请修复格式后重新调用", {
            "dimension": dimension,
            "error_detail": str(e),
            "retryable": True,
        })
    except Exception as e:
        logger.error("parse_response: %s", e, exc_info=True)
        return make_error(ErrorCode.PARSE_FAILED, f"解析异常：{e}", {"dimension": dimension})


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
                    original_text_location=a_data.get("original_text_location", ""),
                    evidence_reference=a_data.get("evidence_reference", ""),
                    legal_analysis=a_data.get("legal_analysis", ""),
                    legal_basis=a_data.get("legal_basis", ""),
                    suggestion=a_data.get("suggestion", ""),
                    deduction=a_data.get("deduction", 0),
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
        return make_error(ErrorCode.PARSE_FAILED, f"JSON 解析失败：{e}", {"case_name": case_name})
    except Exception as e:
        logger.error("build_report: %s", e, exc_info=True)
        return make_error(ErrorCode.INTERNAL_ERROR, f"报告生成异常：{e}", {"case_name": case_name})


@mcp.tool()
def build_report_html(
    case_name: str,
    dimension_results_json: str,
    doc_type: str = "判决书",
    model_name: str = "AI Agent",
) -> str:
    """从结构化异常数据生成精美的 HTML 格式检测报告（支持 dark/light 主题切换）。

    参数与 build_report 完全一致，输出为自包含的 HTML 页面。
    当用户明确要求 HTML 格式报告时使用此工具，默认使用 build_report 生成 Markdown。

    case_name: 案件名称
    dimension_results_json: JSON 字符串，包含所有维度的解析结果列表
        格式：[{"dimension": "procedure", "anomalies": [...], "risk_level": "high", "summary": "..."}, ...]
    doc_type: 文书类型（默认 '判决书'）
    model_name: 使用的模型名称（默认 'AI Agent'）

    返回自包含的 HTML 页面字符串，可直接保存为 .html 文件在浏览器中查看。
    """
    try:
        from .models import AnomalyItem, DetectionResult, DimensionResult

        logger.info("build_report_html: 开始 case=%s", case_name)
        dim_data_list = json.loads(dimension_results_json)
        dimension_results = []

        for dim_data in dim_data_list:
            anomalies = []
            for a_data in dim_data.get("anomalies", []):
                raw_conf = a_data.get("confidence", "medium")
                if isinstance(raw_conf, (int, float)):
                    raw_conf = "high" if raw_conf >= 0.8 else ("medium" if raw_conf >= 0.5 else "low")
                anomalies.append(AnomalyItem(
                    dimension=dim_data["dimension"],
                    item_name=a_data.get("item_name", ""),
                    description=a_data.get("description", ""),
                    beneficiary=a_data.get("beneficiary", ""),
                    confidence=str(raw_conf),
                    f_code=a_data.get("f_code", ""),
                    a_code=a_data.get("a_code", ""),
                    original_text=a_data.get("original_text", ""),
                    original_text_location=a_data.get("original_text_location", ""),
                    evidence_reference=a_data.get("evidence_reference", ""),
                    legal_analysis=a_data.get("legal_analysis", ""),
                    legal_basis=a_data.get("legal_basis", ""),
                    suggestion=a_data.get("suggestion", ""),
                    deduction=a_data.get("deduction", 0),
                ))

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

        html_report = _builder.build_html_report(detection_result)
        logger.info("build_report_html: 报告生成完成, 长度=%d", len(html_report))
        return html_report

    except json.JSONDecodeError as e:
        logger.error("build_report_html: JSON 解析失败: %s", e)
        return make_error(ErrorCode.PARSE_FAILED, f"JSON 解析失败：{e}", {"case_name": case_name})
    except Exception as e:
        logger.error("build_report_html: %s", e, exc_info=True)
        return make_error(ErrorCode.INTERNAL_ERROR, f"HTML报告生成异常：{e}", {"case_name": case_name})


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


# ── Material Compaction Helpers ────────────────────────────────


def _extract_key_facts(text: str, max_chars: int) -> str:
    sections = []
    current_section = []
    current_header = ""

    for line in text.split("\n"):
        if re.match(r"^#{1,4}\s+", line):
            if current_section:
                sections.append((current_header, "\n".join(current_section)))
            current_header = line.strip()
            current_section = [line]
        else:
            current_section.append(line)

    if current_section:
        sections.append((current_header, "\n".join(current_section)))

    key_patterns = [
        r"争议焦点|诉讼请求|判决如下|裁定如下|事实认定|证据|原告|被告|上诉|再审",
        r"劳动合同|工资|赔偿|解除|违法|二倍|经济补偿|混同用工|连带责任",
        r"举证责任|质证|采信|不予采纳|程序|管辖|送达|回避|期限",
    ]
    key_re = re.compile("|".join(key_patterns))

    priority_sections = []
    other_sections = []

    for header, content in sections:
        if key_re.search(content):
            priority_sections.append((header, content))
        else:
            other_sections.append((header, content))

    result_parts = []
    total_len = 0

    for header, content in priority_sections:
        if total_len + len(content) > max_chars:
            remaining = max_chars - total_len
            if remaining > 200:
                result_parts.append(content[:remaining] + "\n...[已截断]")
                total_len = max_chars
            break
        result_parts.append(content)
        total_len += len(content)

    if total_len < max_chars * 0.8:
        for header, content in other_sections:
            outline = _section_outline(content)
            if total_len + len(outline) > max_chars:
                break
            result_parts.append(outline)
            total_len += len(outline)

    return "\n\n".join(result_parts)


def _outline_compact(text: str, max_chars: int) -> str:
    lines = text.split("\n")
    outline_lines = []

    for line in lines:
        stripped = line.strip()
        if re.match(r"^#{1,4}\s+", stripped):
            outline_lines.append(stripped)
        elif re.match(r"^(\d+[\.\)、]|[-*]\s)", stripped):
            summary = stripped[:120] + ("..." if len(stripped) > 120 else "")
            outline_lines.append(summary)
        elif len(stripped) > 0 and stripped[0] in "一二三四五六七八九十":
            outline_lines.append(stripped[:120] + ("..." if len(stripped) > 120 else ""))

    result = "\n".join(outline_lines)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n...[已截断]"
    return result


def _section_outline(content: str) -> str:
    lines = content.split("\n")
    header = lines[0] if lines else ""
    body_lines = [l.strip() for l in lines[1:] if l.strip()]
    summary_count = min(3, len(body_lines))
    summary = "\n".join(body_lines[:summary_count])
    if len(body_lines) > 3:
        summary += f"\n...[共{len(body_lines)}行，已省略{len(body_lines) - 3}行]"
    return f"{header}\n{summary}" if header else summary


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


def _anonymize_text(text: str) -> str:
    text = re.sub(r'[\u4e00-\u9fff]{2,4}(?=（|[(]|先生|女士|同志|律师|法官|审判长|审判员|代理)', '某甲', text)
    text = re.sub(r'(身份证号[：:]?\s*)\d{6}[\dXx]{8,12}', r'\1****', text)
    text = re.sub(r'(住址[：:]?\s*)[\u4e00-\u9fff]+省[\u4e00-\u9fff]+市[\u4e00-\u9fff]+区[\u4e00-\u9fff]+路\d+号', r'\1某地', text)
    text = re.sub(r'（\d{4}）\S*号', '（****）某号', text)
    text = re.sub(r'\d{4}[-/]\d{2}[-/]\d{2}', '****-**-**', text)
    text = re.sub(r'1[3-9]\d{9}', '1**********', text)
    return text


@mcp.tool()
def get_audit_trail(
    session_id: str | None = None,
    limit: int = 50,
) -> str:
    """查询审查留痕日志，追踪工具调用链路。

    session_id: 可选，按会话 ID 筛选
    limit: 返回条目数上限（默认 50）

    返回 JSON 字符串，包含审计日志列表。
    """
    try:
        with _audit_lock:
            entries = list(_audit_log)
        if session_id:
            entries = [e for e in entries if e.get("session_id") == session_id]
        entries = entries[-limit:]
        return json.dumps({"audit_trail": entries, "total": len(entries)}, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("get_audit_trail: %s", e, exc_info=True)
        return make_error(ErrorCode.INTERNAL_ERROR, f"审计日志查询异常：{e}")


@mcp.tool()
def debug_render(
    skill_name: str,
    variables: dict | None = None,
    show_diff: bool = False,
) -> str:
    """调试模式：展示 Skill 渲染的中间过程，帮助排查模板变量替换和输出问题。

    当 render_skill 的输出不符合预期时，使用此工具查看渲染前后的差异。

    skill_name: Skill 名称（如 'dimensions/02_evidence'）
    variables: 模板变量字典
    show_diff: 是否显示渲染前后差异（默认 False）

    返回 JSON 字符串，包含：
    - skill_name: Skill 名称
    - template_raw: 原始模板文本（渲染前）
    - template_rendered: 渲染后文本
    - variables_provided: 提供的变量列表
    - variables_unresolved: 未解析的变量占位符列表
    - diff: 渲染前后差异（仅 show_diff=True 时）
    """
    try:
        meta, body = _loader.load(skill_name)
        raw_body = body
        rendered = _renderer.render(body, variables)

        unresolved = re.findall(r'\{\{(\w+)\}\}', rendered)

        result = {
            "skill_name": meta.name,
            "skill_title": meta.title,
            "template_raw_length": len(raw_body),
            "template_rendered_length": len(rendered),
            "variables_provided": list(variables.keys()) if variables else [],
            "variables_unresolved": unresolved,
        }

        if show_diff:
            diff_parts = []
            raw_lines = raw_body.splitlines()
            rendered_lines = rendered.splitlines()
            for i, (raw, rend) in enumerate(zip(raw_lines, rendered_lines)):
                if raw != rend:
                    diff_parts.append({
                        "line": i + 1,
                        "before": raw[:200],
                        "after": rend[:200],
                    })
            result["diff"] = diff_parts[:50]
            result["diff_count"] = len(diff_parts)

        return json.dumps(result, ensure_ascii=False, indent=2)

    except FileNotFoundError as e:
        return make_error(ErrorCode.SKILL_NOT_FOUND, f"Skill 不存在：{e}", {"skill_name": skill_name})
    except Exception as e:
        logger.error("debug_render: %s", e, exc_info=True)
        return make_error(ErrorCode.RENDER_FAILED, f"调试渲染异常：{e}", {"skill_name": skill_name})


@mcp.tool()
def render_skill_batch(
    skill_names: list[str],
    variables: dict | None = None,
) -> str:
    """批量渲染多个 Skill 模板，适合短文档场景以减少网络往返。

    仅建议在 estimate_tokens 显示总 token < 80000 时使用。
    长文档请使用 plan_pipeline + render_skill 逐个调用。

    skill_names: Skill 名称列表（如 ['dimensions/01_procedure', 'dimensions/02_evidence']）
    variables: 模板变量字典

    返回 JSON 字符串，包含所有 Skill 的渲染结果列表。
    """
    try:
        results = []
        total_chars = 0
        for sn in skill_names:
            meta, body = _loader.load(sn)
            rendered = _renderer.render(body, variables)
            system_prompt = _build_system_prompt(meta)
            total_chars += len(system_prompt) + len(rendered)
            results.append({
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

        total_tokens = _estimate_tokens(" " * total_chars)
        if total_tokens > 120_000:
            return make_error(ErrorCode.TOKEN_OVERFLOW, f"批量渲染总 token={total_tokens} 超限，请改用逐个调用", {
                "total_tokens": total_tokens,
                "skill_count": len(skill_names),
            })

        return json.dumps({
            "skills": results,
            "total_skills": len(results),
            "total_estimated_tokens": total_tokens,
        }, ensure_ascii=False, indent=2)

    except FileNotFoundError as e:
        return make_error(ErrorCode.SKILL_NOT_FOUND, f"Skill 不存在：{e}", {"skill_names": skill_names})
    except Exception as e:
        logger.error("render_skill_batch: %s", e, exc_info=True)
        return make_error(ErrorCode.RENDER_FAILED, f"批量渲染异常：{e}")


def main():
    mcp.run()


if __name__ == "__main__":
    main()
