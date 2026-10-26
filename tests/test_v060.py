"""Comprehensive unit tests for v0.6.0 changes.

Covers:
  - D17 dimension skill (17_claim_support): discovery, frontmatter, template placeholder
  - list_skills / full_scan pipeline include D17
  - A9 taxonomy entry (taxonomy.py + _taxonomy.md) and F-27/F-28 in dimension 03
  - write_skill path-traversal hardening (reject '../', absolute paths, nested traversal;
    allow normal in-tree writes)
"""

import json

import judicial_lint_mcp.server as server_module
from judicial_lint_mcp.server import list_skills, plan_pipeline, render_skill, write_skill
from judicial_lint_mcp.skill_runner import SKILLS_DIR, SkillLoader
from judicial_lint_mcp.taxonomy import TAXONOMY, get_category

# ── D17 Dimension Skill Discovery ────────────────────────────


class TestD17DimensionSkill:
    def test_loader_discovers_17_claim_support(self):
        loader = SkillLoader()
        meta, body = loader.load("dimensions/17_claim_support")
        assert meta.name == "claim_support"
        assert meta.title
        assert meta.layer
        assert meta.order == 17
        assert meta.depends_on
        assert meta.output_format

    def test_template_contains_materials_placeholder(self):
        loader = SkillLoader()
        _, body = loader.load("dimensions/17_claim_support")
        assert "{{materials}}" in body

    def test_template_contains_all_cs_rules(self):
        loader = SkillLoader()
        _, body = loader.load("dimensions/17_claim_support")
        for code in [f"CS-B{i:02d}" for i in range(1, 11)]:
            assert code in body, f"missing rule {code}"

    def test_template_contains_normative_basis(self):
        loader = SkillLoader()
        _, body = loader.load("dimensions/17_claim_support")
        assert "法发〔2018〕10号" in body
        assert "法发〔2024〕16号" in body
        assert "A9" in body

    def test_render_skill_17_claim_support(self):
        result = json.loads(render_skill(
            "dimensions/17_claim_support",
            variables={"materials": "某劳动者与某用人单位劳动争议测试材料"},
        ))
        assert result["skill_name"] == "claim_support"
        assert "system_prompt" in result
        assert "user_prompt" in result
        # 材料占位符必须被替换，不得残留在渲染结果中
        assert "{{materials}}" not in result["user_prompt"]
        assert "测试材料" in result["user_prompt"]

    def test_render_skill_17_includes_taxonomy(self):
        result = json.loads(render_skill(
            "dimensions/17_claim_support",
            variables={"materials": "测试材料"},
        ))
        # structured_anomaly 类型应包含分类体系与中立性指令
        assert "A9" in result["system_prompt"] or "诉请回应缺失" in result["system_prompt"]


# ── list_skills / full_scan Pipeline Include D17 ─────────────


class TestD17InSkillListing:
    def test_list_skills_contains_17(self):
        result = list_skills()
        assert "claim_support" in result
        assert "诉请支持度" in result

    def test_loader_list_skills_meta(self):
        loader = SkillLoader()
        names = [s["name"] for s in loader.list_skills()]
        assert "claim_support" in names

    def test_dimension_count(self):
        loader = SkillLoader()
        dims = loader.list_skills()
        discovered = {s["name"] for s in dims}
        # 17 个维度文件（01-17）全部被发现（list_skills 展示 frontmatter 的 name）
        for name in ["procedure", "evidence", "fact_finding", "coupling", "claim_support"]:
            assert name in discovered, f"missing dimension skill {name}"
        assert len(dims) >= 17


class TestD17InFullScanPipeline:
    def test_full_scan_contains_17_claim_support(self):
        result = json.loads(plan_pipeline(pipeline_name="full_scan"))
        skill_names = [s["skill_name"] for s in result["skills"]]
        assert "claim_support" in skill_names

    def test_full_scan_has_17_dimensions(self):
        loader = SkillLoader()
        _, body = loader.load("pipelines/full_scan")
        dim_refs = [
            line.split(":", 1)[1].strip()
            for line in body.split("\n")
            if line.strip().startswith("- skill:") and "dimensions/" in line
        ]
        assert len(dim_refs) == 17
        assert "dimensions/17_claim_support" in dim_refs

    def test_full_scan_title_updated(self):
        loader = SkillLoader()
        meta, body = loader.load("pipelines/full_scan")
        assert "17" in meta.title
        assert "dimensions/17_claim_support" in body


# ── A9 Taxonomy ──────────────────────────────────────────────


class TestA9Taxonomy:
    def test_a9_exists_in_taxonomy_py(self):
        cat = get_category("A9")
        assert cat is not None
        assert cat.label == "诉请回应缺失"
        assert "F-27" in cat.f_codes
        assert "F-28" in cat.f_codes
        assert 17 in cat.dimensions
        assert 3 in cat.dimensions

    def test_a9_is_last_and_codes_unique(self):
        codes = [c.code for c in TAXONOMY]
        assert len(codes) == len(set(codes))
        assert codes == [f"A{i}" for i in range(1, len(codes) + 1)]

    def test_a9_in_taxonomy_md(self):
        text = (SKILLS_DIR / "_taxonomy.md").read_text(encoding="utf-8")
        assert "| A9 |" in text
        assert "诉请回应缺失" in text
        assert "claim_response_missing" in text
        assert "A1-A9" in text

    def test_f27_f28_in_dimension_03(self):
        loader = SkillLoader()
        meta, body = loader.load("dimensions/03_fact_finding")
        assert "F-27" in body
        assert "F-28" in body
        assert "遗漏诉讼请求" in body
        assert "结论式驳斥" in body
        assert "28" in meta.title

    def test_f_codes_mapping_helpers_cover_a9(self):
        from judicial_lint_mcp.taxonomy import category_from_f_code, dimension_to_categories

        assert any(c.code == "A9" for c in category_from_f_code("F-27"))
        assert any(c.code == "A9" for c in category_from_f_code("F-28"))
        assert any(c.code == "A9" for c in dimension_to_categories(17))


# ── write_skill Path Traversal Hardening ─────────────────────


def _patch_loader(tmp_path, monkeypatch) -> SkillLoader:
    """将 server 模块的全局 loader 指向临时 Skills 目录，避免污染真实仓库文件。"""
    loader = SkillLoader(skills_dir=tmp_path)
    monkeypatch.setattr(server_module, "_loader", loader)
    return loader


class TestWriteSkillPathHardening:
    def test_reject_parent_traversal(self, tmp_path, monkeypatch):
        _patch_loader(tmp_path, monkeypatch)
        result = json.loads(write_skill("../evil.md", "# evil"))
        assert result["success"] is False
        assert result["error"]["code"] == "PATH_400"
        assert result["error"]["retryable"] is False
        assert not (tmp_path.parent / "evil.md").exists()

    def test_reject_absolute_windows_path(self, tmp_path, monkeypatch):
        _patch_loader(tmp_path, monkeypatch)
        evil_abs = str(tmp_path.parent / "evil_abs.md")
        result = json.loads(write_skill(evil_abs, "# evil"))
        assert result["success"] is False
        assert result["error"]["code"] == "PATH_400"
        assert not (tmp_path.parent / "evil_abs.md").exists()

    def test_reject_rooted_path(self, tmp_path, monkeypatch):
        _patch_loader(tmp_path, monkeypatch)
        result = json.loads(write_skill("/evil_rooted.md", "# evil"))
        assert result["success"] is False
        assert result["error"]["code"] == "PATH_400"
        assert not (tmp_path / "evil_rooted.md").exists()

    def test_reject_nested_traversal(self, tmp_path, monkeypatch):
        _patch_loader(tmp_path, monkeypatch)
        result = json.loads(write_skill("dimensions/../../evil_nested.md", "# evil"))
        assert result["success"] is False
        assert result["error"]["code"] == "PATH_400"
        assert not (tmp_path.parent / "evil_nested.md").exists()

    def test_reject_empty_name(self, tmp_path, monkeypatch):
        _patch_loader(tmp_path, monkeypatch)
        result = json.loads(write_skill("", "# evil"))
        assert result["success"] is False
        assert result["error"]["code"] == "PARAM_400"

    def test_allow_normal_write_inside_skills_dir(self, tmp_path, monkeypatch):
        _patch_loader(tmp_path, monkeypatch)
        result = write_skill("dimensions/02_evidence", "---\nname: evidence\n---\n# 测试")
        assert "已写入" in result
        assert (tmp_path / "dimensions" / "02_evidence.md").exists()

    def test_allow_system_skill_write(self, tmp_path, monkeypatch):
        _patch_loader(tmp_path, monkeypatch)
        result = write_skill("_test_skill", "# test")
        assert "已写入" in result
        assert (tmp_path / "_test_skill.md").exists()

    def test_traversal_does_not_leak_real_skills_dir(self, tmp_path, monkeypatch):
        """确保穿越目标不会被解析到真实仓库的 skills 目录。"""
        _patch_loader(tmp_path, monkeypatch)
        result = json.loads(write_skill("../17_claim_support.md", "# tampered"))
        assert result["success"] is False
        assert not (tmp_path.parent / "17_claim_support.md").exists()
        real_file = SKILLS_DIR / "dimensions" / "17_claim_support.md"
        assert "tampered" not in real_file.read_text(encoding="utf-8")
