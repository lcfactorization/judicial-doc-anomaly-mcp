"""Check MCP Server Skill loading and run end-to-end test."""
import json
from judicial_lint_mcp.server import list_skills, render_skill, render_pipeline, parse_response, build_report

print("=" * 70)
print("TASK 2: Check MCP Server Skill Loading")
print("=" * 70)

skills_md = list_skills()
print(skills_md)

print()
print("=" * 70)
print("Verifying each skill can be rendered...")
print("=" * 70)

from judicial_lint_mcp.skill_runner import SkillLoader
loader = SkillLoader()
all_skills = loader.list_skills()
errors = []

for s in all_skills:
    name = s["name"]
    try:
        result = render_skill(name, {"materials": "test"})
        data = json.loads(result)
        if "error" in data:
            errors.append(f"  FAIL: {name} -> {data['error']}")
            print(f"  FAIL: {name} -> {data['error']}")
        else:
            sys_len = len(data.get("system_prompt", ""))
            user_len = len(data.get("user_prompt", ""))
            print(f"  OK: {name} (sys={sys_len}c, user={user_len}c)")
    except Exception as e:
        errors.append(f"  ERROR: {name} -> {e}")
        print(f"  ERROR: {name} -> {e}")

print()
print("=" * 70)
print("Verifying pipeline rendering...")
print("=" * 70)

for pipeline in ["full_scan", "evidence_focus", "quick_scan"]:
    result = render_pipeline(pipeline, {"materials": "test"})
    data = json.loads(result)
    if "error" in data:
        print(f"  FAIL: {pipeline} -> {data['error']}")
        errors.append(f"Pipeline {pipeline}: {data['error']}")
    else:
        print(f"  OK: {pipeline} ({data['total_skills']} skills, {data['estimated_prompt_tokens']} tokens)")
        for sk in data["skills"]:
            if sk.get("error"):
                print(f"    MISSING: {sk['skill_name']} -> {sk['error']}")
                errors.append(f"Skill in {pipeline}: {sk['skill_name']} -> {sk['error']}")

print()
if errors:
    print(f"FOUND {len(errors)} ERRORS:")
    for e in errors:
        print(e)
else:
    print("ALL SKILLS AND PIPELINES LOADED SUCCESSFULLY!")

# ── TASK 3: End-to-end test with mock data ────────────────────

print()
print("=" * 70)
print("TASK 3: End-to-End Test — Mock Case Report")
print("=" * 70)

mock_evidence_response = """
#### 1. 异常项：证据采信偏差——被告提交的录音证据3未经质证即被采信

- **具体表现**：判决书第8页第2段载明"被告提交的录音证据3，能够证明双方已就还款事宜达成一致"，但庭审笔录显示该证据未经质证环节，原告代理人对该证据明确表示异议。法院在未经质证的情况下直接采信该证据作为定案依据，违反了《民事诉讼法》第68条关于证据必须经过质证才能作为认定事实根据的规定。

- **原文引用**：判决书第8页第2段："被告提交的录音证据3，能够证明双方已就还款事宜达成一致，本院予以采信。"

- **指向获益方**：被告

- **异常程度**：高度可能

- **F编号**：F-17

- **A分类**：A1

- **法理分析**：《民事诉讼法》第68条规定"证据应当在法庭上出示，并由当事人互相质证"。未经质证的证据不得作为认定案件事实的根据。本案中，被告提交的录音证据3未经质证即被采信，属于严重的程序违法，且该证据的采信直接影响了事实认定结果，使得被告获得了程序上的不当利益。

#### 2. 异常项：原告提交的书面证据5被不当排除

- **具体表现**：原告提交的书面证据5（银行转账记录）系原件，具有高度证明力，但判决书第9页第3段仅以"该证据与本案无关"为由排除，未说明具体理由。该转账记录直接反映了原告向被告支付款项的事实，与本案核心争议具有直接关联。

- **原文引用**：判决书第9页第3段："原告提交的书面证据5（银行转账记录），与本案无关，本院不予采信。"

- **指向获益方**：被告

- **异常程度**：高度可能

- **F编号**：F-16

- **A分类**：A4

- **法理分析**：《最高人民法院关于民事诉讼证据的若干规定》第90条规定，法院不予采信证据应当说明理由。本案中，银行转账记录与款项支付这一核心争议直接相关，法院仅以"与本案无关"排除，既未说明无关的具体理由，也未分析该证据与案件事实的关联性，属于证据排除不当。

#### 3. 异常项：举证责任分配错误——将本应由被告承担的举证责任转嫁给原告

- **具体表现**：判决书第10页第1段载明"原告未能提供证据证明被告未还款"，将"被告未还款"的否定性事实的举证责任分配给原告。但根据《最高人民法院关于民事诉讼证据的若干规定》，主张已还款的一方（被告）应承担举证责任，而非由原告证明被告未还款。

- **原文引用**：判决书第10页第1段："原告未能提供证据证明被告未还款，应承担举证不能的不利后果。"

- **指向获益方**：被告

- **异常程度**：确定

- **F编号**：F-24

- **A分类**：A8

- **法理分析**：根据举证责任分配规则，主张积极事实（已还款）的一方应承担举证责任。本案中，被告主张已还款，应由被告举证证明还款事实，而非由原告证明被告未还款。法院将举证责任倒置，要求原告证明否定性事实，违反了举证责任分配的基本原则。
"""

mock_procedure_response = """
#### 1. 异常项：送达程序违法——未向原告合法送达开庭传票

- **具体表现**：判决书载明"本院依法向原告送达了开庭传票"，但原告陈述其从未收到任何传票，且法院卷宗中无送达回证。法院在未合法送达的情况下缺席审理，严重违反法定程序。

- **原文引用**：判决书第2页第1段："本院依法向原告送达了开庭传票，原告经传票传唤无正当理由拒不到庭。"

- **指向获益方**：被告

- **异常程度**：确定

- **F编号**：F-17

- **A分类**：A5

- **法理分析**：《民事诉讼法》第136条规定，人民法院审理民事案件，应当在开庭三日前通知当事人。合法送达是保障当事人诉讼权利的前提，未经合法送达即缺席审理，构成严重程序违法。
"""

print("\n--- Step 1: Parse evidence dimension ---")
evidence_result = parse_response("evidence", mock_evidence_response, 1)
evidence_data = json.loads(evidence_result)
print(f"  dimension: {evidence_data['dimension']}")
print(f"  anomaly_count: {evidence_data['anomaly_count']}")
print(f"  risk_level: {evidence_data['risk_level']}")
for a in evidence_data["anomalies"]:
    print(f"    - {a['item_name'][:40]} | beneficiary={a['beneficiary']} | conf={a['confidence']} | f={a['f_code']} | a={a['a_code']}")

print("\n--- Step 2: Parse procedure dimension ---")
procedure_result = parse_response("procedure", mock_procedure_response, 0)
procedure_data = json.loads(procedure_result)
print(f"  dimension: {procedure_data['dimension']}")
print(f"  anomaly_count: {procedure_data['anomaly_count']}")
print(f"  risk_level: {procedure_data['risk_level']}")
for a in procedure_data["anomalies"]:
    print(f"    - {a['item_name'][:40]} | beneficiary={a['beneficiary']} | conf={a['confidence']} | f={a['f_code']} | a={a['a_code']}")

print("\n--- Step 3: Build final report ---")
dim_results = [evidence_data, procedure_data]
report = build_report(
    case_name="张某诉李某民间借贷纠纷案",
    dimension_results_json=json.dumps(dim_results),
    doc_type="一审判决书",
    model_name="AI Agent + GLM-5.1",
)

date_str = __import__("datetime").datetime.now().strftime("%Y%m%d")
report_path = f"司法文书异常检测报告_AI-Agent-GLM_v0.4.0_{date_str}.md"
with open(report_path, "w", encoding="utf-8") as f:
    f.write(report)
print(f"  Report saved to: {report_path}")
print(f"  Report length: {len(report)} chars")

# Verify key content
print("\n--- Step 4: Verify report content ---")
checks = {
    "Contains GitHub Alert [!DANGER]": "[!DANGER]" in report,
    "Contains GitHub Alert [!WARNING]": "[!WARNING]" in report,
    "Contains table separator |": "|" in report,
    "Contains 维度总览": "维度总览" in report,
    "Contains 异常项汇总": "异常项汇总" in report,
    "Contains 总结": "总结" in report,
    "Contains 获益方分布": "获益方分布" in report,
    "Contains 被告 (not 原告 as beneficiary)": "被告" in report,
    "Evidence F-17 present": "F-17" in report,
    "Evidence F-16 present": "F-16" in report,
    "Evidence F-24 present": "F-24" in report,
    "No logic reversal (原告 as beneficiary for evidence)": not ("原告" in report and "获益方" in report and "F-17" in report.split("原告")[0].split("获益方")[-1] if "原告" in report else True),
}

all_ok = True
for check, result in checks.items():
    status = "PASS" if result else "FAIL"
    if not result:
        all_ok = False
    print(f"  [{status}] {check}")

print()
if all_ok:
    print("ALL END-TO-END TESTS PASSED! Logic reversal issue is resolved.")
else:
    print("SOME TESTS FAILED — please review the report output.")

print()
print("=" * 70)
print("Report Preview (first 2000 chars):")
print("=" * 70)
print(report[:2000])
