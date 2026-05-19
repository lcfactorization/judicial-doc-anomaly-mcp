"""Skill Loader & Template Renderer — loads SKILL.md files, renders templates.

v0.5.1 bridge architecture: NO LLM calls.
This module only provides SkillLoader (file I/O) and TemplateRenderer (variable substitution).
LLM calling is the Agent's responsibility.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


@dataclass
class SkillMeta:
    name: str = ""
    title: str = ""
    type: str = ""
    layer: str = ""
    order: int = 0
    depends_on: list[str] = field(default_factory=list)
    output_format: str = ""
    version: str = "0.5.0"


class SkillLoader:
    """Load and parse SKILL.md files from the skills/ directory."""

    def __init__(self, skills_dir: Path | str | None = None):
        self.skills_dir = Path(skills_dir) if skills_dir else SKILLS_DIR
        self._cache: dict[str, tuple[SkillMeta, str]] = {}

    def _parse_frontmatter(self, content: str) -> tuple[dict, str]:
        fm = {}
        body = content
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
        if m:
            for line in m.group(1).strip().split("\n"):
                if ":" in line:
                    key, _, val = line.partition(":")
                    val = val.strip().strip('"').strip("'")
                    if val.startswith("[") and val.endswith("]"):
                        val = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
                    fm[key.strip()] = val
            body = m.group(2)
        return fm, body

    def load(self, skill_name: str) -> tuple[SkillMeta, str]:
        if skill_name in self._cache:
            logger.info("load: 命中缓存 skill=%s", skill_name)
            return self._cache[skill_name]

        parts = skill_name.split("/")
        skill_path = self.skills_dir / Path(*parts)

        if skill_path.is_dir():
            skill_path = skill_path / "skill.md"
        if not skill_path.suffix:
            skill_path = skill_path.with_suffix(".md")

        if not skill_path.exists():
            logger.error("load: Skill 不存在 skill=%s, path=%s", skill_name, skill_path)
            raise FileNotFoundError(f"Skill not found: {skill_name} (looked at {skill_path})")

        logger.info("load: 加载 skill=%s, path=%s", skill_name, skill_path)
        content = skill_path.read_text(encoding="utf-8")
        fm, body = self._parse_frontmatter(content)

        meta = SkillMeta(
            name=fm.get("name", skill_name),
            title=fm.get("title", ""),
            type=fm.get("type", ""),
            layer=fm.get("layer", ""),
            order=int(fm.get("order", 0)),
            depends_on=fm.get("depends_on", []) if isinstance(fm.get("depends_on"), list) else [],
            output_format=fm.get("output_format", ""),
            version=fm.get("version", "0.5.0"),
        )

        logger.info(
            "load: 解析完成 skill=%s, title=%s, type=%s, layer=%s, order=%d, output_format=%s, body_len=%d",
            meta.name, meta.title, meta.type, meta.layer, meta.order, meta.output_format, len(body),
        )

        self._cache[skill_name] = (meta, body)
        return meta, body

    def list_skills(self, category: str | None = None) -> list[dict]:
        logger.info("list_skills: 扫描目录=%s, category=%s", self.skills_dir, category)
        results = []
        for md_file in sorted(self.skills_dir.rglob("*.md")):
            rel = md_file.relative_to(self.skills_dir)
            if rel.name.startswith("_"):
                continue
            skill_name = str(rel.with_suffix("")).replace("\\", "/")
            try:
                meta, _ = self.load(skill_name)
                if category and meta.type != category:
                    continue
                results.append({
                    "name": meta.name,
                    "title": meta.title,
                    "type": meta.type,
                    "layer": meta.layer,
                    "order": meta.order,
                    "depends_on": meta.depends_on,
                    "output_format": meta.output_format,
                })
            except Exception as e:
                logger.warning("list_skills: failed to load %s: %s", skill_name, e)
        logger.info("list_skills: 找到 %d 个 skills (category=%s)", len(results), category)
        return results

    def load_system_skill(self, name: str) -> str:
        if not name.startswith("_"):
            name = f"_{name}"
        path = self.skills_dir / f"{name}.md"
        if not path.exists():
            logger.warning("load_system_skill: 系统技能不存在 name=%s, path=%s", name, path)
            return ""
        logger.info("load_system_skill: 加载 name=%s, path=%s", name, path)
        _, body = self._parse_frontmatter(path.read_text(encoding="utf-8"))
        logger.info("load_system_skill: 完成 name=%s, body_len=%d", name, len(body))
        return body


class TemplateRenderer:
    """Render {{variable}} templates in SKILL.md content."""

    SYSTEM_SKILLS = ["_system", "_taxonomy", "_neutrality", "_output_format"]

    def __init__(self, loader: SkillLoader):
        self.loader = loader
        self._system_cache: dict[str, str] = {}

    def _get_system_content(self, name: str) -> str:
        if name not in self._system_cache:
            self._system_cache[name] = self.loader.load_system_skill(name)
        return self._system_cache[name]

    def render(self, template: str, variables: dict | None = None) -> str:
        variables = variables or {}
        logger.info("render: 模板长度=%d, 变量keys=%s", len(template), list(variables.keys()))

        for sys_name in self.SYSTEM_SKILLS:
            placeholder = "{{" + sys_name + "}}"
            if placeholder in template:
                content = self._get_system_content(sys_name)
                logger.info("render: 替换系统变量 %s, 内容长度=%d", sys_name, len(content))
                template = template.replace(placeholder, content)

        for key, value in variables.items():
            placeholder = "{{" + key + "}}"
            if placeholder in template:
                logger.info("render: 替换用户变量 %s, 值长度=%d", key, len(str(value)))
            template = template.replace(placeholder, str(value))

        cleaned = re.findall(r"\{\{([_a-zA-Z][_a-zA-Z0-9]*)\}\}", template)
        if cleaned:
            logger.warning("render: 未替换的变量占位符: %s", cleaned)
        template = re.sub(r"\{\{[_a-zA-Z][_a-zA-Z0-9]*\}\}", "", template)

        result = template.strip()
        logger.info("render: 渲染完成, 结果长度=%d", len(result))
        return result
