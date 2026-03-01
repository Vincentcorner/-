---
description: 完整的意图匹配流程（含诉求转写+切词+权重+AI筛选+标杆对比）
---

# 意图匹配工作流

完整的意图匹配流程：三维度诉求转写（API） → 三维度各自独立 AC 匹配+得分汇总 → AI 意图筛选 → 标杆对比。

## 全自动模式（推荐）

一条命令完成全流程（API转写 + AC匹配 + AI筛选 + 标杆对比）：

```powershell
py scripts/batch_intent_match.py -d {领域} -c {数量} --auto-rewrite
```

## 参数说明

| 参数 | 说明 |
|------|------|
| `-f / --file` | 问题Excel文件（含原始问+意图列），默认标杆数据 |
| `-w / --weights` | 权重词表JSON路径 |
| `-d / --domain` | 领域名称 |
| `-c / --count` | 处理数量（默认50） |
| `-r / --rewrite` | 已有的三维度转写结果JSON |
| `--auto-rewrite` | **自动调用API进行三维度转写**（无需预先准备转写文件） |

## 执行流程

### Step 1: 读取问题列表

从 Excel 文件提取 **原始问** 和 **意图** 列。

### Step 2: 三维度诉求转写（API自动）

使用 `--auto-rewrite` 时，脚本自动调用 Qwen 32B API 对每个问题进行三维度转写：

- **情形提取**（scenario）
- **群众语言表达**（plain_language）
- **官方规范表述**（official_expression）

转写结果自动保存为 `auto_rewrite_3d.json`。

### Step 3: 三维度独立意图匹配

对每个问题的 3 个转写维度分别独立执行 AC 匹配 + 得分汇总，然后合并去重（同一意图取最高分）。

### Step 4: AI 意图筛选

> [!IMPORTANT]
> 当候选意图 ≥ 2 个时，调用 API 使用 `intent_select_prompt.md` 从中选出最终意图。单候选或无候选时直接取 Top-1。

### Step 5: 标杆对比 + 生成结果

输出对比结果表格：

| 原始问题 | 转写结果 | 转写来源 | 算法意图 | 全量意图 | 意图特征词 | 置信分 | 标杆意图 | 是否一致 |
|---------|---------|---------|---------|---------|-----------|-------|---------|---------|

保存到 `result/{领域}/benchmark_compare/{日期}/{批次}/`

## 配置文件位置

- 标杆数据：`originalfile/{领域}/深圳原始数据（部分）.xlsx`
- 权重词库：`result/{领域}/weighted/weighted_words.json`
- 三维度转写提示词：`prompts/query_rewrite_3d_prompt.md`
- 意图筛选提示词：`prompts/intent_select_prompt.md`
- 输出目录：`result/{领域}/benchmark_compare/{日期}/`

## 示例

```powershell
# 全自动：测试前10条（API转写 + AC匹配 + AI筛选）
py scripts/batch_intent_match.py -d 失业保险 -c 10 --auto-rewrite

# 指定已有转写文件（跳过API转写步骤）
py scripts/batch_intent_match.py -d 失业保险 -c 10 -r result/失业保险/benchmark_compare/20260211/auto_rewrite_3d.json
```
