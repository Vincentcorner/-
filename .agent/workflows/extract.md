---
description: 完整的法规实体提取流程（本地解析+Claude智能分析+报告生成）
---

# /extract 工作流 v2.1

执行完整的法律法规实体提取流程，由 Claude 进行智能主题分析。

## 使用方式
```
/extract <文件名>                    # 处理单个文件
/extract 文件1.pdf 文件2.pdf         # 处理多个文件
```

## 输出目录结构
```
result/
├── <法规名>/
│   ├── analysis_data.json          # 实体分析数据
│   ├── relation_summaries.json     # 关系总结（Claude生成）
│   └── *_实体分析报告.xlsx          # Excel 报告
```

## 执行步骤

### 1. 解析文档 + 实体识别（本地）
// turbo
```bash
python3 scripts/entity_analyzer.py "originalfile/<文件名>"
```
输出：`result/<法规名>/analysis_data.json`

### 2. Claude 智能主题分析（模型）

读取提示词和数据：
```
提示词：prompts/topic_analysis_prompt.md
数据源：result/<法规名>/analysis_data.json
输出到：result/<法规名>/relation_summaries.json
```

按提示词要求对每个条款进行主题分析，生成关系总结。

### 3. 生成 Excel 报告（本地）
// turbo
```bash
python3 scripts/generate_excel.py "result/<法规名>"
```

### 4. 打开报告
// turbo
```bash
open "result/<法规名>/<法规名>_实体分析报告.xlsx"
```

## 提示词维护

主题分析规则保存在可编辑的提示词文档中：

```
prompts/topic_analysis_prompt.md
```

## 变更日志

- **v2.1 (2026-01-19)**：提示词抽取到独立文件，便于维护
- **v2.0 (2026-01-19)**：步骤2改为Claude智能分析，支持主题提取和实体角色判断
- **v1.0**：基于规则的本地总结生成
