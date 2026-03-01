---
description: 基于实体分析结果生成意图清单（Claude智能分析）
---

# /intent 工作流 v1.0

基于实体分析结果，为每个实体生成结构化的意图清单。

## 使用方式
```
/intent <法规名>                     # 为指定法规生成意图清单
```

## 前置条件

需要先执行 `/extract` 工作流生成 `analysis_data.json`。

## 输入输出

- **输入**：`result/<法规名>/analysis_data.json`
- **输出**：`result/<法规名>/intent_list.json` 和 `*_意图清单.xlsx`

## 执行步骤

### 1. Claude 智能意图生成（模型）

读取提示词文档和实体数据：

```
提示词：prompts/intent_generation_prompt.md
数据源：result/<法规名>/analysis_data.json
```

**分析要点**：
1. 根据实体类型匹配适用的意图模板
2. 排除无效组合（参见提示词中的排除规则）
3. 生成结构化的意图描述

**输出格式**（保存到 `intent_list.json`）：
```json
[
  {
    "entity": "失业保险金",
    "category": "资金类",
    "intents": [
      {"type": "基础定义", "intent": "失业保险金的定义"},
      {"type": "资格条件", "intent": "失业保险金的申领条件"},
      {"type": "数值计算", "intent": "失业保险金的计算"}
    ]
  }
]
```

### 2. 生成 Excel 报告（本地）
// turbo
```bash
python3 scripts/generate_intent_excel.py "result/<法规名>"
```

### 3. 打开报告
// turbo
```bash
open "result/<法规名>/<法规名>_意图清单.xlsx"
```

## 提示词维护

意图生成规则保存在可编辑的提示词文档中：

```
prompts/intent_generation_prompt.md
```

如需调整意图类型或排除规则，直接编辑该文件即可。

## 变更日志

- **v1.0 (2026-01-19)**：初始版本，支持9种意图类型生成
