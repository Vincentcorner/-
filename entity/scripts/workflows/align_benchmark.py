# -*- coding: utf-8 -*-
"""
对齐标杆意图与权重分表意图，生成对比清单
"""

import pandas as pd
import json
from pathlib import Path
from difflib import SequenceMatcher
from datetime import datetime

def similarity(a: str, b: str) -> float:
    """计算两个字符串的相似度"""
    return SequenceMatcher(None, a, b).ratio()

def find_best_match(intent: str, candidates: set, threshold: float = 0.6) -> tuple:
    """在候选集中找到最佳匹配"""
    best_match = None
    best_score = 0
    for candidate in candidates:
        score = similarity(intent, candidate)
        if score > best_score:
            best_score = score
            best_match = candidate
    if best_score >= threshold:
        return best_match, best_score
    return None, 0

def main():
    base_dir = Path(r"D:\数字研究院工作\认知世界大模型\第三个路径\norelation\entity")
    
    # 1. 读取标杆数据
    print("=" * 60)
    print("步骤1: 读取标杆数据")
    print("=" * 60)
    benchmark_path = base_dir / "originalfile" / "失业保险" / "深圳原始数据（部分）.xlsx"
    benchmark = pd.read_excel(benchmark_path)
    print(f"标杆数据: {len(benchmark)} 行")
    print(f"列: {benchmark.columns.tolist()}")
    
    # 展开标杆意图（一个格子可能有多个意图）
    benchmark_intents = set()
    for intent_str in benchmark['意图'].dropna():
        for intent in str(intent_str).split(','):
            benchmark_intents.add(intent.strip())
    print(f"标杆意图数（去重展开后）: {len(benchmark_intents)}")
    
    # 2. 读取我们的权重分表
    print("\n" + "=" * 60)
    print("步骤2: 读取权重分表")
    print("=" * 60)
    weighted_path = base_dir / "result" / "失业保险" / "weighted" / "20260206" / "weighted_words.json"
    with open(weighted_path, 'r', encoding='utf-8') as f:
        weighted = json.load(f)
    
    our_intents = set(weighted.get('意图元数据', {}).keys())
    print(f"我们的意图数: {len(our_intents)}")
    
    # 3. 意图对齐
    print("\n" + "=" * 60)
    print("步骤3: 意图对齐（精确匹配 + 模糊匹配）")
    print("=" * 60)
    
    intent_mapping = {}  # 我们的意图 -> 标杆意图
    exact_matches = 0
    fuzzy_matches = 0
    no_matches = []
    
    for our_intent in sorted(our_intents):
        # 先尝试精确匹配
        if our_intent in benchmark_intents:
            intent_mapping[our_intent] = {"标杆意图": our_intent, "匹配类型": "精确", "相似度": 1.0}
            exact_matches += 1
        else:
            # 模糊匹配
            match, score = find_best_match(our_intent, benchmark_intents, threshold=0.65)
            if match:
                intent_mapping[our_intent] = {"标杆意图": match, "匹配类型": "模糊", "相似度": round(score, 2)}
                fuzzy_matches += 1
            else:
                no_matches.append(our_intent)
    
    print(f"精确匹配: {exact_matches}")
    print(f"模糊匹配: {fuzzy_matches}")
    print(f"无匹配: {len(no_matches)}")
    
    # 4. 输出匹配结果
    print("\n" + "=" * 60)
    print("步骤4: 意图对齐清单")
    print("=" * 60)
    
    alignment_data = []
    for our_intent, mapping in sorted(intent_mapping.items()):
        alignment_data.append({
            "我们的意图": our_intent,
            "标杆意图": mapping["标杆意图"],
            "匹配类型": mapping["匹配类型"],
            "相似度": mapping["相似度"]
        })
        if len(alignment_data) <= 20:
            print(f"  {our_intent} -> {mapping['标杆意图']} ({mapping['匹配类型']}, {mapping['相似度']})")
    
    if len(alignment_data) > 20:
        print(f"  ... 共 {len(alignment_data)} 条")
    
    # 5. 找到匹配意图对应的原始问题
    print("\n" + "=" * 60)
    print("步骤5: 根据匹配意图获取标杆问题清单")
    print("=" * 60)
    
    matched_benchmark_intents = set(m["标杆意图"] for m in intent_mapping.values())
    
    # 筛选标杆数据中包含匹配意图的行
    matched_rows = []
    for _, row in benchmark.iterrows():
        intent_str = str(row['意图']) if pd.notna(row['意图']) else ""
        row_intents = [i.strip() for i in intent_str.split(',')]
        
        for ri in row_intents:
            if ri in matched_benchmark_intents:
                matched_rows.append({
                    "原始问题": row['原始问'],
                    "标杆改写": row['改写后问题'],
                    "主体": row['主体'] if pd.notna(row['主体']) else "",
                    "标杆意图": ri,
                    "领域": row['领域名称']
                })
                break  # 一行只取一条
    
    print(f"匹配到的标杆问题: {len(matched_rows)} 条")
    
    # 6. 保存结果
    print("\n" + "=" * 60)
    print("步骤6: 保存结果")
    print("=" * 60)
    
    output_dir = base_dir / "result" / "失业保险" / "alignment" / datetime.now().strftime("%Y%m%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存意图对齐表
    alignment_df = pd.DataFrame(alignment_data)
    alignment_df.to_excel(output_dir / "intent_alignment.xlsx", index=False)
    print(f"意图对齐表: {output_dir / 'intent_alignment.xlsx'}")
    
    # 保存匹配的标杆问题清单
    matched_df = pd.DataFrame(matched_rows)
    matched_df.to_excel(output_dir / "benchmark_questions.xlsx", index=False)
    print(f"标杆问题清单: {output_dir / 'benchmark_questions.xlsx'}")
    
    # 保存无匹配意图
    no_match_df = pd.DataFrame({"无匹配意图": no_matches})
    no_match_df.to_excel(output_dir / "unmatched_intents.xlsx", index=False)
    print(f"无匹配意图: {output_dir / 'unmatched_intents.xlsx'}")
    
    # 保存JSON版本
    result = {
        "意图对齐": intent_mapping,
        "无匹配意图": no_matches,
        "统计": {
            "我们意图总数": len(our_intents),
            "标杆意图总数": len(benchmark_intents),
            "精确匹配": exact_matches,
            "模糊匹配": fuzzy_matches,
            "无匹配": len(no_matches)
        }
    }
    with open(output_dir / "alignment_result.json", 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n完成! 结果保存到: {output_dir}")
    
    return matched_df

if __name__ == "__main__":
    main()
