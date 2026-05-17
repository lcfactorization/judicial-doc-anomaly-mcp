---
name: full_scan
title: 全量16维扫描流水线
type: pipeline
version: "0.5.0"
---

# 全量16维扫描流水线

## 流水线定义

### Phase 0: 预处理
- skill: phases/preprocessor
- input: case_dir
- output: preprocessed_data

### Phase 1: 图结构建模
- skill: phases/graph
- input: preprocessed_data
- output: graph_result

### Phase 2: 16维度逐项检测
- skill: dimensions/01_procedure
- skill: dimensions/02_evidence
- skill: dimensions/03_fact_finding
- skill: dimensions/04_focus_drift
- skill: dimensions/05_law_application
- skill: dimensions/06_discretion
- skill: dimensions/07_rhetoric_trick
- skill: dimensions/08_logic
- skill: dimensions/09_temporal
- skill: dimensions/10_trial_process
- skill: dimensions/11_external_interference
- skill: dimensions/12_execution
- skill: dimensions/13_negative_space
- skill: dimensions/14_semantic_drift
- skill: dimensions/15_case_deviation
- input: materials + context from previous dimensions
- output: dimension_results

### Phase 3: 耦合分析
- skill: dimensions/16_coupling
- input: dimension_results
- output: coupling_result

### Phase 4: 对抗审查
- skill: phases/adversarial
- input: dimension_results + coupling_result
- output: adversarial_result

### Phase 5: 质量评估
- skill: phases/quality
- input: materials + dimension_results
- output: quality_result

### Phase 6: 翻案速查
- skill: phases/quick_check
- input: materials + dimension_results
- output: quick_check_result

### Phase 7: 报告生成
- type: report
- template: REPORT_TEMPLATE
- input: all results
- output: final_report
