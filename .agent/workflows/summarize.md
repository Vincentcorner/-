---
description: Claude 智能分析实体关系（基于主题提取）
---

# /summarize 工作流 v2.1

基于已有的实体分析数据，由 Claude 进行智能主题分析和关系总结。

## 使用方式
```
/summarize <法规名>                  # 处理指定法规
```

## 前置条件
已执行 `/analyze <文件名>` 生成 `result/<法规名>/analysis_data.json`

## 执行步骤

### Claude 智能分析

读取提示词和数据：
```
提示词：prompts/topic_analysis_prompt.md
数据源：result/<法规名>/analysis_data.json
输出到：result/<法规名>/relation_summaries.json
```

按提示词要求对每个条款进行主题分析，生成关系总结。

## 后续步骤

执行 `/report` 生成 Excel 报告，或手动执行：
```bash
python3 scripts/generate_excel.py "result/<法规名>"
```

## 提示词维护

主题分析规则保存在可编辑的提示词文档中：

```
prompts/topic_analysis_prompt.md
```

## 变更日志

- **v2.1 (2026-01-19)**：提示词抽取到独立文件，便于维护
- **v2.0 (2026-01-19)**：改为Claude直接分析，支持主题提取
