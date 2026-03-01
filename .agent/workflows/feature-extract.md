---
description: 从意图清单中提取三层特征词（AI分析）
---

# 特征词提取工作流

从意图清单中提取三层特征词：L1_事项词、L2_动作词、L3_场景词。

## 使用方法

### 步骤1：准备AI输入

```powershell
python scripts/workflows/run_feature_extract.py --domain {领域} --input {意图清单文件} --prepare-only
```

执行后会输出格式化的提示词，将其发送给AI助手进行分析。

### 步骤2：保存AI结果

```powershell
python scripts/workflows/run_feature_extract.py --domain {领域} --input {意图清单文件} --ai-output "{AI返回的JSON}"
```

或将AI结果保存为文件后：

```powershell
python scripts/workflows/run_feature_extract.py --domain {领域} --input {意图清单文件} --ai-output ai_result.json
```

## 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--domain, -d` | 是 | 领域名称，如 "失业保险" |
| `--input, -i` | 是 | 意图清单文件路径（.json 或 .xlsx） |
| `--output-dir, -o` | 否 | 输出目录，默认 result/{领域}/intent_list/{YYYYMMDD}/ |
| `--date` | 否 | 日期目录，格式 YYYYMMDD |
| `--prepare-only` | 否 | 仅准备AI输入 |
| `--ai-output` | 否 | AI分析结果 |

## 输出文件

- `feature_words.json` - 三层特征词（JSON格式）
- `feature_words.xlsx` - 三层特征词（Excel格式）

## 示例

```powershell
# 步骤1
python scripts/workflows/run_feature_extract.py -d 失业保险 -i originalfile/意图清单.xlsx --prepare-only

# 步骤2（将AI返回的JSON粘贴到命令行）
python scripts/workflows/run_feature_extract.py -d 失业保险 -i originalfile/意图清单.xlsx --ai-output "{ ... AI返回的JSON ... }"
```
