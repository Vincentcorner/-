---
description: 生成词表并打权重分（合并提取+打分为一步，支持分批处理）
---

# 词表生成工作流

从Excel输入（意图+改写后问题）生成带权重的全局词表。**支持自动API模式和手动分批处理**。

## 输入要求

Excel文件需包含以下两列：

- **意图**：目标意图名称（支持逗号分隔多意图）
- **改写后问题**：用户问题的规范化表达

## 自动模式（推荐）

一键调用大模型API完成所有批次的分析：

```powershell
// turbo
py scripts/workflows/run_wordlist.py -d {领域} -i {Excel文件路径} --batch-size 15 --auto
```

如需从上次中断处继续：

```powershell
// turbo
py scripts/workflows/run_wordlist.py -d {领域} -i {Excel文件路径} --batch-size 15 --auto --continue
```

## 手动模式（备选）

### 步骤1：准备当前批次

```powershell
// turbo
py scripts/workflows/run_wordlist.py -d {领域} -i {Excel文件路径} --batch-size 15 --continue --prepare-only
```

### 步骤2：AI分析生成特征词和权重

AI助手读取输出的提示词，直接生成JSON格式的分析结果。

### 步骤3：保存结果并更新进度

将AI生成的JSON保存为 `ai_result.json`，然后执行：

```powershell
py scripts/workflows/run_wordlist.py -d {领域} -i {Excel文件路径} --continue --ai-output ai_result.json
```

### 步骤4：检查是否还有待处理

如果还有待处理意图，重复步骤1-3，直到全部完成。

## 参数说明

| 参数 | 说明 |
|------|------|
| `--auto` | **自动模式**：直接调用API分析，无需手动交互 |
| `--batch-size 15` | 每批处理15个意图（默认） |
| `--continue` | 从上次中断处继续 |
| `--reset` | 重置进度从头开始 |
| `--status` | 查看当前进度状态 |

## 输出文件

| 文件 | 说明 |
|------|------|
| `weighted_words.json` | 全局词表（程序读取） |
| `weighted_words.xlsx` | 全局词表（人工查看） |
| `change_log.md` | 修改日志 |
| `.progress.json` | 进度追踪（隐藏文件） |
