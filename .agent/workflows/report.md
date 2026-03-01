---
description: 根据已有数据生成 Excel 报告（本地）
---

# /report 工作流

根据已有的分析数据和关系总结生成 Excel 报告。

## 使用方式
```
/report <法规名>                     # 处理指定法规
/report                              # 处理默认目录
```

## 前置条件
- 已执行 `/analyze` 生成 `analysis_data.json`
- 可选：已执行 `/summarize` 生成 `relation_summaries.json`

## 执行步骤

// turbo-all

### 1. 生成 Excel 报告
```bash
python3 scripts/generate_excel.py "result/<法规名>"
```

### 2. 显示报告统计
```bash
regulation_name="<法规名>"
python3 -c "
import pandas as pd
xlsx = pd.ExcelFile('result/${regulation_name}/${regulation_name}_实体分析报告.xlsx')
print('Sheet 列表:', xlsx.sheet_names)
for sheet in xlsx.sheet_names[1:]:
    df = pd.read_excel(xlsx, sheet)
    summary_count = df['关系总结'].notna().sum() if '关系总结' in df.columns else 0
    print(f'  {sheet}: {len(df)} 行, 关系总结 {summary_count} 条')
"
```

### 3. 打开报告
```bash
open "result/<法规名>/<法规名>_实体分析报告.xlsx"
```

## 输出产物
```
result/<法规名>/
└── <法规名>_实体分析报告.xlsx
```
