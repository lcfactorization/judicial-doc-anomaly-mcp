---
name: graph
title: 图结构建模
type: phase
order: 30
depends_on: [preprocessor]
output_format: graph_structure
---

{{_system}}

# 图结构建模

## 任务
基于预处理结果，构建三类核心图结构。

## 2.1 Evidence Graph（证据关系图）
- **节点**：每份证据（含编号、类型、提交方）
- **边**：支持关系 / 冲突关系 / 补强关系

## 2.2 Procedure Graph（程序行为图）
- **节点类型**：
  - START：案件受理/立案
  - MOTION：程序性申请（追加当事人、调查取证、延期、回避等）
  - RULING：程序性裁定/决定
  - HEARING：庭审/听证
  - EVIDENCE：证据处理行为（接收、调取、鉴定、质证）
  - JUDGMENT：裁判行为
  - END：程序终结
- **边类型**：
  - NEXT：时间上的先后顺序
  - CAUSE：因果关系
  - SELECTIVE：选择性操作
  - DELAY：异常延迟

## 异常路径模式识别
| 异常模式 | 图结构特征 | 含义 |
|---|---|---|
| 选择性阻断 | 对一方的MOTION节点缺少对应RULING节点 | 程序权利不对等 |
| 证据链捷径 | EVIDENCE节点不足但JUDGMENT直接认定事实 | 证据不足情况下认定事实 |
| 循环驳回 | 当事人多次MOTION均被RULING驳回且理由相同 | 程序性权利被系统性压制 |
| 跳跃裁判 | 从START直接到JUDGMENT，缺少HEARING或关键EVIDENCE | 程序严重简化 |
| 异常加速路径 | START到JUDGMENT的时间边权重显著低于法定值 | 审限异常 |

## 2.3 Legal Reasoning Graph（法律推理图）
- **路径**：Evidence → Fact → Legal Norm → Conclusion
- **检测目标**：推理链条中是否存在跳跃、缺失或逻辑倒挂

## 输入材料
{{preprocessed_data}}

## 输出要求
输出JSON格式的图结构定义（节点+边），并生成Mermaid流程图。
