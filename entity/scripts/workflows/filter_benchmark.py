# -*- coding: utf-8 -*-
"""
筛选标杆问题：只保留意图在我们权重分表中存在的问题
然后用这些问题进行意图匹配对比
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime

def main():
    base_dir = Path(r"D:\数字研究院工作\认知世界大模型\第三个路径\norelation\entity")
    
    # 1. 读取我们的权重分表意图
    print("=" * 60)
    print("步骤1: 读取权重分表意图")
    print("=" * 60)
    weighted_path = base_dir / "result" / "失业保险" / "weighted" / "20260206" / "weighted_words.json"
    with open(weighted_path, 'r', encoding='utf-8') as f:
        weighted = json.load(f)
    
    our_intents = set(weighted.get('意图元数据', {}).keys())
    print(f"我们的意图数: {len(our_intents)}")
    
    # 2. 读取标杆数据
    print("\n" + "=" * 60)
    print("步骤2: 读取标杆数据")
    print("=" * 60)
    benchmark_path = base_dir / "originalfile" / "失业保险" / "深圳原始数据（部分）.xlsx"
    benchmark = pd.read_excel(benchmark_path)
    print(f"标杆数据: {len(benchmark)} 行")
    
    # 3. 筛选：只保留意图在我们权重分表中的问题
    print("\n" + "=" * 60)
    print("步骤3: 筛选标杆问题（仅保留我们有的意图）")
    print("=" * 60)
    
    matched_rows = []
    matched_intents = set()  # 匹配到的标杆意图
    
    for _, row in benchmark.iterrows():
        intent_str = str(row['意图']) if pd.notna(row['意图']) else ""
        row_intents = [i.strip() for i in intent_str.split(',')]
        
        # 检查是否有任何意图在我们的权重分表中
        for ri in row_intents:
            if ri in our_intents:
                matched_rows.append({
                    "原始问题": row['原始问'],
                    "标杆改写": row['改写后问题'] if pd.notna(row['改写后问题']) else "",
                    "主体": row['主体'] if pd.notna(row['主体']) else "",
                    "标杆意图": ri,  # 使用匹配到的意图
                    "领域": row['领域名称']
                })
                matched_intents.add(ri)
                break  # 一行只取一条
    
    print(f"匹配到的问题数: {len(matched_rows)}")
    print(f"匹配到的意图数: {len(matched_intents)}")
    
    print("\n匹配到的意图:")
    for intent in sorted(matched_intents):
        count = sum(1 for r in matched_rows if r['标杆意图'] == intent)
        print(f"  {intent}: {count}条")
    
    # 4. 保存筛选后的标杆问题
    print("\n" + "=" * 60)
    print("步骤4: 保存结果")
    print("=" * 60)
    
    output_dir = base_dir / "result" / "失业保险" / "alignment" / datetime.now().strftime("%Y%m%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    df = pd.DataFrame(matched_rows)
    output_file = output_dir / "filtered_benchmark_questions.xlsx"
    df.to_excel(output_file, index=False)
    print(f"保存到: {output_file}")
    
    # 同时输出未匹配的我们的意图（在标杆中找不到问题的）
    unmatched = our_intents - matched_intents
    print(f"\n我们有但标杆中没有问题的意图: {len(unmatched)}")
    
    return df

if __name__ == "__main__":
    main()
