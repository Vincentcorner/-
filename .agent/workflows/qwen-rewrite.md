---
description: 使用千问大模型进行三维度诉求转写（自动调用API）
---

# 千问大模型诉求转写工作流

使用千问模型（DashScope API）自动对原始问题进行三维度转写：情形提取、群众语言表达、官方规范表述。

## 调用方式

用户提供：

- 领域名称（如"失业保险"）
- 处理条数（默认10条）
- 可选：自定义输入文件

## AI 执行步骤

### Step 1: 确认参数

1. **领域**：如"失业保险"
2. **问题来源**：默认标杆数据 `originalfile/{领域}/深圳原始数据（部分）.xlsx`
3. **处理数量**：默认10条
4. **模型**：默认 `Qwen/Qwen2.5-7B-Instruct`（SiliconFlow）

### Step 2: 执行转写脚本

// turbo

```bash
py scripts/workflows/run_qwen_rewrite.py -d {领域} -c {数量} -k sk-tdeaewbaihruwxzxyignlhqvoguifdqarsvjhsywrdpgmuoa
```

可选参数：

- `-i {文件路径}`：自定义输入Excel文件
- `-m {模型名}`：更换模型（默认 Qwen/Qwen2.5-7B-Instruct）
- `--api-base {地址}`：更换API地址（默认 SiliconFlow）
- `-o {目录}`：自定义输出目录

### Step 3: 检查结果

输出目录：`result/{领域}/大模型API测试/{日期}/{批次}/`

文件列表：

- `rewrite_3d.json`：三维度转写结果（JSON格式，与 intent-match 兼容）
- `rewrite_3d.xlsx`：转写结果（Excel格式，方便人工检查）

## 输出格式

JSON 格式与 intent-match 工作流的 rewrite 结果一致：

```json
[
  {
    "original_question": "原始问题",
    "rewrite_results": {
      "scenario": "情形描述",
      "plain_language": "群众语言表达",
      "official_expression": "官方规范表述"
    }
  }
]
```

## 示例

**用户**：@/qwen-rewrite 失业保险领域，测试前5条

**AI**：

```bash
py scripts/workflows/run_qwen_rewrite.py -d 失业保险 -c 5 -k sk-tdeaewbaihruwxzxyignlhqvoguifdqarsvjhsywrdpgmuoa
```
