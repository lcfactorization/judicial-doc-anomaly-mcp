---
name: quick_scan
title: 快速扫描流水线
type: pipeline
version: "0.3.0"
---

# 快速扫描流水线

## 适用场景
当用户需要快速了解文书是否存在明显异常时使用，只检测核心维度。

## 流水线定义

### Phase 0: 预处理
- skill: phases/preprocessor
- input: case_dir
- output: preprocessed_data

### Phase 1: 核心维度
- skill: dimensions/01_procedure
- skill: dimensions/02_evidence
- skill: dimensions/03_fact_finding
- skill: dimensions/08_logic
- input: materials
- output: dimension_results

### Phase 2: 耦合分析
- skill: dimensions/16_coupling
- input: dimension_results
- output: coupling_result

### Phase 3: 翻案速查
- skill: phases/quick_check
- input: materials + dimension_results
- output: quick_check_result

### Phase 4: 报告生成
- type: report
- template: REPORT_TEMPLATE
- input: all results
- output: final_report
