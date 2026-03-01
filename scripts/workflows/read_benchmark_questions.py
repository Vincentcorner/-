# -*- coding: utf-8 -*-
"""
读取标杆数据的问题列表，支持两种转写模式：
1. 有"改写后问题"列 → 直接使用
2. 无"改写后问题"列 → 输出需要AI转写的问题

输出 JSON 格式供后续处理
"""
import json
import sys
from pathlib import Path
import pandas as pd

# 配置
PROJECT_ROOT = Path(r"d:\数字研究院工作\认知世界大模型\第三个路径\norelation\entity")


def read_benchmark_questions(domain: str, limit: int = 10, excel_path: str = None):
    """
    读取标杆数据的问题列表
    
    Args:
        domain: 领域名称
        limit: 处理数量限制
        excel_path: 自定义Excel路径，默认使用标杆数据
        
    Returns:
        dict: {
            "has_rewrite": bool,  # 是否有现成的转写结果
            "records": [
                {
                    "index": int,
                    "原始问": str,
                    "改写后问题": str or None,  # 如果有
                    "标杆意图": str or None
                }
            ]
        }
    """
    # 确定文件路径
    if excel_path:
        file_path = Path(excel_path)
    else:
        file_path = PROJECT_ROOT / "originalfile" / domain / "深圳原始数据（部分）.xlsx"
    
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    # 读取 Excel
    df = pd.read_excel(file_path)
    
    # 检测列名（支持多种可能的列名）
    original_col = None
    rewrite_col = None
    intent_col = None
    
    for col in df.columns:
        col_lower = col.lower().strip()
        if col in ["原始问", "原始问题"] or "原始" in col:
            original_col = col
        elif col in ["改写后问题", "转写问", "转写结果", "改写问题"] or "改写" in col or "转写" in col:
            rewrite_col = col
        elif col in ["意图", "标杆意图"] and intent_col is None:
            intent_col = col
    
    # 如果没找到原始问列，使用第一列
    if original_col is None:
        original_col = df.columns[0]
    
    # 判断是否有转写列
    has_rewrite = rewrite_col is not None and df[rewrite_col].notna().any()
    
    # 提取数据
    records = []
    for i, row in df.head(limit).iterrows():
        record = {
            "index": i + 1,
            "原始问": str(row[original_col]) if pd.notna(row[original_col]) else "",
            "改写后问题": None,
            "标杆意图": None
        }
        
        # 如果有转写列且有值
        if rewrite_col and pd.notna(row.get(rewrite_col)):
            record["改写后问题"] = str(row[rewrite_col])
        
        # 如果有意图列
        if intent_col and pd.notna(row.get(intent_col)):
            record["标杆意图"] = str(row[intent_col])
        
        records.append(record)
    
    result = {
        "文件路径": str(file_path),
        "总行数": int(len(df)),
        "处理数量": int(len(records)),
        "检测到的列": {
            "原始问列": str(original_col) if original_col else None,
            "转写列": str(rewrite_col) if rewrite_col else None,
            "意图列": str(intent_col) if intent_col else None
        },
        "has_rewrite": bool(has_rewrite),
        "records": records
    }
    
    return result


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="读取标杆数据问题列表")
    parser.add_argument("--domain", "-d", required=True, help="领域名称")
    parser.add_argument("--limit", "-n", type=int, default=10, help="处理数量")
    parser.add_argument("--file", "-f", help="自定义Excel文件路径")
    parser.add_argument("--output", "-o", help="输出JSON文件路径")
    
    args = parser.parse_args()
    
    result = read_benchmark_questions(args.domain, args.limit, args.file)
    
    # 输出结果
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到: {output_path}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # 打印摘要
    print("\n" + "=" * 60)
    print(f"【摘要】")
    print(f"  文件: {result['文件路径']}")
    print(f"  总行数/处理数: {result['总行数']} / {result['处理数量']}")
    print(f"  有现成转写: {'✓ 是' if result['has_rewrite'] else '✗ 否（需要AI转写）'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
