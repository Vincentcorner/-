# 法律法规实体提取工具

从法律法规文件（PDF/DOC）中自动提取主体类实体（个人、法人、组织机构等），分析实体关系并生成报告。

## 目录结构

```
entity/
├── .agent/                 # Agent 配置
│   ├── skills/
│   └── workflows/
├── changelog/              # 变更日志
├── originalfile/           # 原始文件
├── result/                 # 分析结果
├── scripts/                # 脚本
├── VERSION_HISTORY.md      # 版本历史
└── README.md
```

## 快速开始

```bash
# 完整流程
python scripts/entity_analyzer.py originalfile/法律.pdf
python scripts/generate_summaries.py result/<法规名>
python scripts/generate_excel.py result/<法规名>
```

## 工作流命令

使用 `/extract` 工作流可一键执行完整流程：
```
/extract originalfile/法律.pdf
```
