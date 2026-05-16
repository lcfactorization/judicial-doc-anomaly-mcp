---
name: coupling
title: 十六、异常耦合与结构性偏差
layer: 第五层·综合判定
order: 16
depends_on: [procedure, evidence, fact_finding, focus_drift, law_application, discretion, rhetoric_trick, logic, temporal, trial_process, external_interference, execution, negative_space, semantic_drift, case_deviation]
output_format: coupling_analysis
---

{{_system}}

{{_taxonomy}}

{{_neutrality}}

# 维度十六：异常耦合与结构性偏差

## 检测逻辑
当多个维度的异常都指向同一方时，触发"高风险耦合"警示。

## 高风险组合模式
1. **程序异常+证据双标** → 高度疑似偏袒
2. **事实模糊+说理断裂** → 高度疑似预设立场
3. **法律曲解+裁量偏离** → 高度疑似枉法
4. **焦点偏移+逻辑断裂** → 高度疑似回避核心争议

## 耦合强度评估
- **弱耦合**：2个维度异常，可能有独立原因
- **中耦合**：3个维度异常，存在关联可能性
- **强耦合**：4个以上维度异常，高度指向系统性问题

## 结构性偏差判定条件
同时满足以下三个条件时，判定为"结构性偏差"：
1. **维度覆盖**：在程序类、证据类、事实类、法律类、新增类中，至少三个类别各触发至少1项高置信异常
2. **指向一致性**：所有触发的异常，其效果均对同一方当事人有利
3. **偏离度验证**：类案偏离量化分析的Deviation Score ≥ 1.0，或Procedure Graph分析识别出选择性操作路径

## 输入材料
{{previous_results}}

## 输出要求
请进行耦合分析，输出：
- 耦合等级（弱/中/强/结构性偏差）
- 触发维度及异常项
- 指向获益方
- 综合风险评级
