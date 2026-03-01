---
description: 仅执行本地解析和实体识别（不调用模型）
---

# /analyze 工作流

执行本地解析和实体识别，不生成关系总结（不消耗 token）。

## 使用方式
```
/analyze <文件名>
```

## 输出目录结构
```
result/<法规名>/
└── analysis_data.json    # 实体分析数据（含条款内容）
```

## 执行步骤

// turbo-all

### 1. 解析文档 + 实体识别
```bash
python3 scripts/entity_analyzer.py "originalfile/<文件名>"
```

### 2. 显示分析结果摘要
```bash
regulation_name="<法规名>"
python3 -c "
import json
with open('result/${regulation_name}/analysis_data.json', 'r') as f:
    data = json.load(f)
print(f'条款数: {data[\"total_articles\"]}')
print(f'实体数: {data[\"total_entities\"]}')
print('\n前10个高频实体:')
for e in data['entities_analysis'][:10]:
    print(f'  {e[\"entity\"]} ({e[\"category\"]}): {e[\"frequency\"]}次')
"
```

## 后续步骤
- 执行 `/summarize <法规名>` 生成关系总结
- 或执行 `/report <法规名>` 直接生成报告（无关系总结）
