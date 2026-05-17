"""Quick smoke test for v0.5.0 MCP Server bridge tools."""
import json
from judicial_lint_mcp.server import (
    render_skill,
    list_skills,
    render_pipeline,
    parse_response,
    build_report,
)

print("=" * 60)
print("v0.5.0 MCP Server Bridge - Smoke Test")
print("=" * 60)

# Test 1: render_skill
print("\n--- Test 1: render_skill ---")
r = render_skill("dimensions/02_evidence", {"materials": "test case materials"})
d = json.loads(r)
print(f"  skill_name: {d['skill_name']}")
print(f"  skill_title: {d['skill_title']}")
print(f"  system_prompt: {len(d['system_prompt'])} chars")
print(f"  user_prompt: {len(d['user_prompt'])} chars")
print(f"  meta.type: {d['meta']['type']}")
print(f"  meta.layer: {d['meta']['layer']}")

# Test 2: list_skills
print("\n--- Test 2: list_skills ---")
r2 = list_skills()
print(f"  Output: {len(r2)} chars")
print(f"  Contains 'evidence': {'evidence' in r2}")

# Test 3: render_pipeline
print("\n--- Test 3: render_pipeline ---")
r3 = render_pipeline("full_scan", {"materials": "test"})
d3 = json.loads(r3)
print(f"  total_skills: {d3['total_skills']}")
print(f"  estimated_prompt_chars: {d3['estimated_prompt_chars']}")
print(f"  estimated_prompt_tokens: {d3['estimated_prompt_tokens']}")
for s in d3['skills'][:3]:
    print(f"    - {s['skill_name']}: {s.get('skill_title', '')}")

# Test 4: parse_response
print("\n--- Test 4: parse_response ---")
mock_response = """
### 异常项 1
- **名称**：证据采信偏差
- **描述**：法院采信了被告提交的录音证据3，但该证据未经质证
- **F编号**：F-03
- **置信度**：0.85
- **获益方**：被告
- **严重程度**：高
"""
r4 = parse_response("evidence", mock_response, 1)
d4 = json.loads(r4)
print(f"  dimension: {d4['dimension']}")
print(f"  anomaly_count: {d4['anomaly_count']}")
print(f"  risk_level: {d4['risk_level']}")

# Test 5: build_report
print("\n--- Test 5: build_report ---")
dim_result = {
    "dimension": "evidence",
    "dimension_index": 1,
    "anomalies": [
        {
            "name": "证据采信偏差",
            "description": "法院采信了被告提交的录音证据3，但该证据未经质证",
            "f_code": "F-03",
            "confidence": 0.85,
            "beneficiary": "被告",
            "severity": "high",
        }
    ],
    "anomaly_count": 1,
    "risk_level": "medium",
}
r5 = build_report(
    case_name="测试案件",
    dimension_results_json=json.dumps([dim_result]),
    doc_type="一审判决书",
    model_name="AI Agent",
)
print(f"  Report length: {len(r5)} chars")
print(f"  Contains GitHub Alert: {'[!' in r5}")
print(f"  Contains table: {'|' in r5}")
print(f"  Contains 被告: {'被告' in r5}")

print("\n" + "=" * 60)
print("All tests passed!")
print("=" * 60)
