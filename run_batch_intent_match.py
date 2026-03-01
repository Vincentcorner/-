# -*- coding: utf-8 -*-
"""
批量意图匹配脚本 - 使用现有转写结果
"""
import json
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(r"d:\数字研究院工作\认知世界大模型\第三个路径\norelation\entity")
sys.path.insert(0, str(project_root))

from scripts.common.file_manager import FileManager
from scripts.common.config import ConfigManager
from scripts.modules.query_segmenter import QuerySegmenter
from scripts.modules.weight_calculator import WeightCalculator

# 配置
DOMAIN = "失业保险"
WEIGHTED_WORDS_PATH = project_root / "result" / "失业保险" / "weighted" / "20260206" / "weighted_words.json"

def format_top2_intents(top_intents: list) -> str:
    if not top_intents:
        return ""
    intents = [i["意图"] for i in top_intents[:2]]
    return "、".join(intents)

def check_intent_match(algorithm_intent: str, benchmark_intents: str) -> bool:
    if not benchmark_intents:
        return False
    benchmark_list = [i.strip() for i in benchmark_intents.split(",")]
    return algorithm_intent in benchmark_list

def main():
    # 读取问题数据
    with open(project_root / "temp_questions.json", 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    has_rewrite = data["has_rewrite"]
    records = data["records"]
    
    print(f"【意图匹配】领域: {DOMAIN}")
    print(f"【意图匹配】使用现有转写: {'✓' if has_rewrite else '✗'}")
    print(f"【意图匹配】待处理: {len(records)} 条")
    
    # 初始化
    file_manager = FileManager()
    config = ConfigManager()
    segmenter = QuerySegmenter(file_manager, config)
    segmenter.load_and_build(WEIGHTED_WORDS_PATH)
    calculator = WeightCalculator(file_manager, config)
    
    # 处理每条数据
    results = []
    match_count = 0
    
    for item in records:
        # 使用转写结果或原始问题
        query = item.get("改写后问题") or item.get("原始问", "")
        raw_query = item.get("原始问", "")
        benchmark_intent = item.get("标杆意图", "")
        
        # AC自动机切词匹配
        matched_words = segmenter.segment(query, DOMAIN)
        
        # 权重计算获取Top-K
        top_k_intents = calculator.calculate(matched_words, DOMAIN) if matched_words else []
        
        # 确定算法意图
        algorithm_intent = top_k_intents[0]["意图"] if top_k_intents else "(无匹配)"
        top2_intent = format_top2_intents(top_k_intents)
        
        # 获取置信分
        if top_k_intents:
            raw_score = top_k_intents[0]["得分"]
            confidence = min(80 + int(raw_score * 10), 99) if raw_score >= 1.0 else int(raw_score * 100)
        else:
            confidence = 0
        
        # 检查是否一致
        is_match = check_intent_match(algorithm_intent, benchmark_intent)
        if is_match:
            match_count += 1
        
        result = {
            "序号": item["index"],
            "原始问题": raw_query,
            "转写结果": query,
            "转写来源": "文件" if has_rewrite else "AI",
            "算法意图": algorithm_intent,
            "Top2意图": top2_intent,
            "置信分": confidence,
            "标杆意图": benchmark_intent,
            "是否一致": "✓" if is_match else "✗"
        }
        results.append(result)
        
        print(f"[{item['index']:2d}] {raw_query[:25]:25s} -> {algorithm_intent:25s} {'✓' if is_match else '✗'}")
    
    # 保存结果
    output_dir = project_root / "result" / DOMAIN / "benchmark_compare" / datetime.now().strftime("%Y%m%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    json_file = output_dir / "compare_results.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    import pandas as pd
    df = pd.DataFrame(results)
    excel_file = output_dir / "compare_results.xlsx"
    df.to_excel(excel_file, index=False)
    
    print("\n" + "=" * 70)
    print(f"【统计】总计 {len(results)} 条，一致 {match_count} 条，准确率: {match_count/len(results)*100:.1f}%")
    print(f"【输出】{output_dir}")
    print("=" * 70)

if __name__ == "__main__":
    main()
