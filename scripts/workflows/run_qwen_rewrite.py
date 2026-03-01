# -*- coding: utf-8 -*-
"""
工作流脚本：千问大模型诉求转写

使用千问模型（DashScope OpenAI兼容API）对原始问题进行三维度转写：
- 情形提取（scenario）
- 群众语言表达（plain_language）
- 官方规范表述（official_expression）

输出目录结构: result/{领域}/大模型API测试/{日期}/{批次}/
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.common.file_manager import FileManager

# Windows 终端编码修复
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


# ========== 默认配置 ==========
DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
DEFAULT_API_BASE = "https://api.siliconflow.cn/v1"
DEFAULT_COUNT = 10


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="千问大模型诉求转写（三维度）"
    )
    parser.add_argument(
        "--domain", "-d",
        required=True,
        help="领域名称，如 '失业保险'"
    )
    parser.add_argument(
        "--input", "-i",
        help="输入Excel文件路径（默认使用标杆数据）"
    )
    parser.add_argument(
        "--count", "-c",
        type=int,
        default=DEFAULT_COUNT,
        help=f"处理条数（默认 {DEFAULT_COUNT}）"
    )
    parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help=f"API基础地址（默认 {DEFAULT_API_BASE}）"
    )
    parser.add_argument(
        "--api-key", "-k",
        required=True,
        help="API Key"
    )
    parser.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        help=f"模型名称（默认 {DEFAULT_MODEL}）"
    )
    parser.add_argument(
        "--output", "-o",
        help="输出目录路径（默认自动生成）"
    )
    return parser.parse_args()


def load_questions(file_path: Path, file_manager: FileManager, count: int) -> List[str]:
    """
    从Excel文件读取原始问题

    Args:
        file_path: Excel文件路径
        file_manager: 文件管理器
        count: 最大读取条数

    Returns:
        原始问题列表
    """
    df = file_manager.load_excel(file_path)

    # 读取"原始问"列，如果没有则读取第一列
    if "原始问" in df.columns:
        questions = [str(q).strip() for q in df["原始问"] if pd.notna(q) and str(q).strip()]
    elif len(df.columns) > 0:
        questions = [str(q).strip() for q in df.iloc[:, 0] if pd.notna(q) and str(q).strip()]
    else:
        questions = []

    return questions[:count]


def load_prompt(file_manager: FileManager) -> str:
    """加载三维度转写提示词"""
    prompt_path = file_manager.prompts_dir / "query_rewrite_3d_prompt.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"提示词文件不存在: {prompt_path}")

    with open(prompt_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取 ## 系统提示词 之后的顶层代码块内容
    # 提示词文件的结构是：顶层 ``` 包裹整个系统提示词，内部可能还有 ```json 等嵌套块
    lines = content.split('\n')
    in_block = False
    block_lines = []
    block_depth = 0

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('```'):
            if not in_block:
                # 进入顶层代码块
                in_block = True
                block_depth = 1
                continue
            elif stripped == '```' and block_depth == 1:
                # 退出顶层代码块
                break
            else:
                # 嵌套代码块的开始/结束，保留原文
                if stripped == '```':
                    block_depth -= 1
                else:
                    block_depth += 1
                block_lines.append(line.rstrip('\r'))
        elif in_block:
            block_lines.append(line.rstrip('\r'))

    if block_lines:
        return '\n'.join(block_lines).strip()

    # 如果没有代码块，返回全部内容
    return content



def call_qwen_api(question: str, system_prompt: str, api_key: str,
                  model: str, api_base: str = DEFAULT_API_BASE) -> Optional[Dict]:
    """
    调用千问API进行转写

    Args:
        question: 原始问题
        system_prompt: 系统提示词
        api_key: API Key
        model: 模型名称
        api_base: API基础地址

    Returns:
        转写结果字典，失败返回None
    """
    from openai import OpenAI

    client = OpenAI(
        api_key=api_key,
        base_url=api_base,
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            temperature=0.7,
            max_tokens=1024,
        )

        content = response.choices[0].message.content
        if not content:
            print(f"  [警告] API返回空内容")
            return None
        content = content.strip()

        # 提取JSON部分
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            result = json.loads(json_match.group())
            # 确保格式正确
            if "rewrite_results" in result:
                result["original_question"] = question
                return result

        # 如果解析失败，构造默认结构
        print(f"  [警告] JSON解析失败，原始返回: {content[:100]}...")
        return None

    except Exception as e:
        print(f"  [错误] API调用失败: {type(e).__name__}: {e}")
        return None


def get_output_dir(file_manager: FileManager, domain: str, custom_output: str = None) -> Path:
    """
    获取输出目录（自动创建递增批次子目录）

    目录结构: result/{domain}/大模型API测试/{date}/{batch}/

    Args:
        file_manager: 文件管理器
        domain: 领域名称
        custom_output: 自定义输出路径

    Returns:
        输出目录路径
    """
    if custom_output:
        output_dir = Path(custom_output)
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    test_base = file_manager.get_domain_dir(domain) / "大模型API测试"
    date_str = datetime.now().strftime("%Y%m%d")
    date_dir = test_base / date_str
    date_dir.mkdir(parents=True, exist_ok=True)

    # 找到下一个批次号
    existing_batches = [
        int(d.name) for d in date_dir.iterdir()
        if d.is_dir() and d.name.isdigit()
    ]
    next_batch = max(existing_batches, default=0) + 1

    batch_dir = date_dir / str(next_batch)
    batch_dir.mkdir(parents=True, exist_ok=True)

    return batch_dir


def save_results(results: List[Dict], output_dir: Path, file_manager: FileManager):
    """
    保存转写结果（JSON + Excel）

    Args:
        results: 转写结果列表
        output_dir: 输出目录
        file_manager: 文件管理器
    """
    # 保存JSON（原始嵌套格式）
    json_path = output_dir / "rewrite_3d.json"
    file_manager.save_json(results, json_path)

    # 保存Excel（展平格式，方便人工检查）
    excel_rows = []
    for item in results:
        rr = item.get("rewrite_results", {})
        excel_rows.append({
            "原始问题": item.get("original_question", ""),
            "情形提取": rr.get("scenario", ""),
            "群众语言表达": rr.get("plain_language", ""),
            "官方规范表述": rr.get("official_expression", ""),
        })

    excel_path = output_dir / "rewrite_3d.xlsx"
    file_manager.save_excel(excel_rows, excel_path)

    return json_path, excel_path


def main():
    args = parse_args()

    # 初始化
    file_manager = FileManager()

    # 确定输入文件
    if args.input:
        input_path = Path(args.input)
        if not input_path.is_absolute():
            input_path = file_manager.base_dir / input_path
    else:
        input_path = file_manager.base_dir / "originalfile" / args.domain / "深圳原始数据（部分）.xlsx"

    if not input_path.exists():
        print(f"[错误] 输入文件不存在: {input_path}")
        sys.exit(1)

    # 读取问题
    print(f"[加载] 输入文件: {input_path}")
    questions = load_questions(input_path, file_manager, args.count)
    print(f"[加载] 共 {len(questions)} 个问题")

    if not questions:
        print("[错误] 没有读取到任何问题")
        sys.exit(1)

    # 加载提示词
    print("[加载] 三维度转写提示词...")
    system_prompt = load_prompt(file_manager)
    print(f"[加载] 提示词长度: {len(system_prompt)} 字符")

    # 确定输出目录
    output_dir = get_output_dir(file_manager, args.domain, args.output)
    print(f"[输出] 目录: {output_dir}")

    # 开始转写
    print(f"\n{'=' * 60}")
    print(f"千问大模型诉求转写")
    print(f"模型: {args.model}")
    print(f"待处理: {len(questions)} 条")
    print(f"{'=' * 60}\n")

    results = []
    success_count = 0
    fail_count = 0

    for i, question in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] 转写: {question[:30]}...", end=" ")

        result = call_qwen_api(
            question=question,
            system_prompt=system_prompt,
            api_key=args.api_key,
            model=args.model,
            api_base=args.api_base,
        )

        if result:
            results.append(result)
            scenario = result["rewrite_results"].get("scenario", "")[:20]
            print(f"✓ 情形: {scenario}...")
            success_count += 1
        else:
            # 构造失败占位
            results.append({
                "original_question": question,
                "rewrite_results": {
                    "scenario": "(转写失败)",
                    "plain_language": "(转写失败)",
                    "official_expression": "(转写失败)"
                }
            })
            print("✗ 转写失败")
            fail_count += 1

        # 简单限流，避免超过API速率限制
        if i < len(questions):
            time.sleep(5)

    # 保存结果
    json_path, excel_path = save_results(results, output_dir, file_manager)

    # 汇总
    print(f"\n{'=' * 60}")
    print(f"【转写完成】")
    print(f"总数: {len(questions)} | 成功: {success_count} | 失败: {fail_count}")
    print(f"JSON: {json_path}")
    print(f"Excel: {excel_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
