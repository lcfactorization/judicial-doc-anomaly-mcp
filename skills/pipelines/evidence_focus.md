---
name: evidence_focus
title: 证据采信专项流水线
type: pipeline
version: "0.5.0"
---

# 证据采信专项流水线

## 适用场景
当用户需要聚焦证据采信问题时使用，只检测与证据直接相关的维度。

## 流水线定义

### Phase 0: 预处理
- skill: phases/preprocessor
- input: case_dir
- output: preprocessed_data

### Phase 1: 证据相关维度
- skill: dimensions/02_evidence
- skill: dimensions/03_fact_finding
- skill: dimensions/13_negative_space
- input: materials
- output: dimension_results

### Phase 2: 耦合分析
- skill: dimensions/16_coupling
- input: dimension_results
- output: coupling_result

### Phase 3: 对抗审查
- skill: phases/adversarial
- input: dimension_results + coupling_result
- output: adversarial_result

### Phase 4: 翻案速查
- skill: phases/quick_check
- input: materials + dimension_results
- output: quick_check_result

### Phase 5: 报告生成
- type: report
- template: REPORT_TEMPLATE
- input: all results
- output: final_report
