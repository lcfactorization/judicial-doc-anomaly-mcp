from judicial_lint_mcp.server import (
    estimate_tokens, compact_materials, plan_pipeline, pipeline_progress,
    render_skill, list_skills
)
import json

print("=== Test 1: estimate_tokens ===")
r = estimate_tokens(pipeline_name="full_scan", materials_chars=138000)
d = json.loads(r)
print(f"  Total tokens: {d['estimated_tokens']:,}")
print(f"  Fits 128k: {d['fits_in_128k']}")
print(f"  Fits 200k: {d['fits_in_200k']}")
print(f"  Recommendation: {d['recommendation']}")
print(f"  Breakdown: {d['breakdown']}")

print()
print("=== Test 2: compact_materials ===")
sample = "争议焦点：" + "原告主张被告混同用工，" * 500 + "证据清单：" + "银行流水记录" * 500
r = compact_materials(materials=sample, max_tokens=500, strategy="extract_key_facts")
d = json.loads(r)
print(f"  Original tokens: {d['original_tokens']:,}")
print(f"  Compacted tokens: {d['compacted_tokens']:,}")
print(f"  Compression ratio: {d['compression_ratio']}")
print(f"  Strategy: {d['strategy_used']}")
print(f"  Compacted length: {len(d['compacted'])} chars")

print()
print("=== Test 3: plan_pipeline ===")
r = plan_pipeline(pipeline_name="full_scan")
d = json.loads(r)
print(f"  Pipeline: {d['pipeline']}")
print(f"  Total skills: {d['total_skills']}")
print(f"  Total estimated tokens: {d['total_estimated_tokens']:,}")
print(f"  Execution hint: {d['execution_hint']}")
print(f"  Session ID: {d['session_id']}")
print(f"  Skills:")
for s in d["skills"][:5]:
    print(f"    - {s['skill_name']}: ~{s['estimated_tokens']:,} tokens")
print(f"    ... ({len(d['skills'])} total)")

print()
print("=== Test 4: pipeline_progress ===")
sid = d["session_id"]
r = pipeline_progress(session_id=sid, action="status")
d2 = json.loads(r)
print(f"  Progress: {d2['completed_count']}/{d2['total_count']} ({d2['progress_pct']}%)")
print(f"  Next skill: {d2['next_skill']}")

r = pipeline_progress(session_id=sid, action="complete", skill_name="dimensions/01_procedure", result_summary="Found 3 anomalies")
d3 = json.loads(r)
print(f"  After complete: {d3['completed_count']}/{d3['total_count']} ({d3['progress_pct']}%)")
print(f"  Next skill: {d3['next_skill']}")

r = pipeline_progress(session_id=sid, action="resume")
d4 = json.loads(r)
print(f"  Resume: {len(d4['remaining_skills'])} remaining skills")

print()
print("=== Test 5: render_skill (single) ===")
r = render_skill(skill_name="dimensions/01_procedure", variables={"materials": "[test materials]"})
d5 = json.loads(r)
print(f"  Skill: {d5['skill_title']}")
print(f"  System prompt: {len(d5['system_prompt'])} chars")
print(f"  User prompt: {len(d5['user_prompt'])} chars")
print(f"  Token estimate: {d5['token_estimate']:,}")

print()
print("All tests passed!")
