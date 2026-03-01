---
description: 对三层特征词进行权重打分（混合模式）
---

# 特征词权重打分工作流

对特征词进行权重打分，支持 AI打分 + 人工审核 的混合模式。

## 输入文件

**必须使用 `/feature-extract` 输出的 `feature_words.json` 文件作为输入。**

典型路径：`result/{领域}/intent_list/{YYYYMMDD}/feature_words.json`

## 使用方法

### 步骤1：准备AI打分输入

```
/feature-weight 请对以下特征词文件进行权重打分：
输入文件：result/失业保险/intent_list/20260206/feature_words.json
领域：失业保险
```

### 步骤2：AI返回打分结果后

AI会返回带权重的JSON，自动保存为：

- `weighted_words.json` - 用于后续匹配
- `weighted_words.xlsx` - 便于人工查看和调整

### 步骤3：人工审核调整（可选）

编辑 `weighted_words.xlsx` 的权重列后，可导入调整。

## 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--domain, -d` | 是 | 领域名称 |
| `--input, -i` | 是 | 特征词文件路径（feature_words.json） |
| `--output-dir, -o` | 否 | 输出目录 |
| `--prepare-only` | 否 | 仅准备AI打分输入 |
| `--ai-output` | 否 | AI打分结果 |
| `--import-manual` | 否 | 人工调整后的Excel文件 |
| `--finalize` | 否 | 直接使用AI结果作为最终权重 |

## 输出文件

- `weighted_words_ai.json` - AI打分原始结果
- `weighted_words_review.xlsx` - 供人工审核的Excel
- `weighted_words.json` - 最终权重（用于匹配）
- `weighted_words.xlsx` - 最终权重Excel版

## 打分规则

| 权重范围 | 判断标准 |
|----------|----------|
| 0.95-1.0 | 专业术语，无歧义 |
| 0.85-0.95 | 常用表达，歧义很小 |
| 0.75-0.85 | 通用动作词，有一定歧义 |
| 0.6-0.75 | 宽泛表达，歧义较大 |
