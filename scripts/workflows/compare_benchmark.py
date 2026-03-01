# -*- coding: utf-8 -*-
"""
对比意图匹配：用标杆问题清单进行匹配，并与标杆结果对比

输出格式：原始问题 | 业务领域 | 诉求分类 | 关键词 | top2意图 | 大模型意图 | 置信分 | 标杆改写 | 标杆意图
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.common.file_manager import FileManager
from scripts.common.config import ConfigManager
from scripts.modules.query_segmenter import QuerySegmenter
from scripts.modules.weight_calculator import WeightCalculator


def parse_args():
    parser = argparse.ArgumentParser(description="标杆对比意图匹配")
    parser.add_argument("--domain", "-d", required=True, help="领域名称")
    parser.add_argument("--benchmark", "-b", required=True, help="标杆问题清单Excel路径")
    parser.add_argument("--weighted-words", "-w", required=True, help="带权重特征词文件路径")
    parser.add_argument("--alignment", "-a", help="意图对齐JSON路径（可选）")
    parser.add_argument("--threshold", type=float, help="最低得分阈值")
    parser.add_argument("--top-k", type=int, help="返回Top-K个意图")
    parser.add_argument("--output", "-o", help="输出文件路径（可选）")
    return parser.parse_args()


def get_intent_category(intent_name: str, weighted_words_path: Path, file_manager: FileManager) -> str:
    try:
        data = file_manager.load_json(weighted_words_path)
        metadata = data.get("意图元数据", {})
        if intent_name in metadata:
            return metadata[intent_name].get("意图分类", "")
    except:
        pass
    return ""


def format_keywords_for_table(matched_words: list, top_intents: list) -> str:
    intent_keywords = {}
    for match in matched_words:
        intent = match["意图"]
        word = match["词"]
        weight = match["权重"]
        if intent not in intent_keywords:
            intent_keywords[intent] = []
        intent_keywords[intent].append(f"{word}:{weight}")
    
    result_parts = []
    for intent_info in top_intents[:3]:
        intent_name = intent_info["意图"]
        if intent_name in intent_keywords:
            keywords_str = ", ".join(intent_keywords[intent_name][:3])
            result_parts.append(f"【{intent_name}】{keywords_str}")
    return "\n".join(result_parts)


def format_top2_intents(top_intents: list) -> str:
    if not top_intents:
        return ""
    intents = [i["意图"] for i in top_intents[:2]]
    return "、".join(intents)


def main():
    args = parse_args()
    
    file_manager = FileManager()
    config = ConfigManager()
    
    # 路径处理
    weighted_words_path = Path(args.weighted_words)
    if not weighted_words_path.is_absolute():
        weighted_words_path = file_manager.base_dir / weighted_words_path
    
    benchmark_path = Path(args.benchmark)
    if not benchmark_path.is_absolute():
        benchmark_path = file_manager.base_dir / benchmark_path
    
    # 读取标杆问题清单
    print(f"[对比匹配] 读取标杆问题清单: {benchmark_path}")
    benchmark_df = pd.read_excel(benchmark_path)
    print(f"[对比匹配] 标杆问题数: {len(benchmark_df)}")
    
    # 读取意图对齐（如果有）
    alignment = {}
    if args.alignment:
        alignment_path = Path(args.alignment)
        if not alignment_path.is_absolute():
            alignment_path = file_manager.base_dir / alignment_path
        with open(alignment_path, 'r', encoding='utf-8') as f:
            alignment_data = json.load(f)
            alignment = alignment_data.get("意图对齐", {})
        print(f"[对比匹配] 加载意图对齐: {len(alignment)} 条")
    
    # 初始化处理模块
    segmenter = QuerySegmenter(file_manager, config)
    segmenter.load_and_build(weighted_words_path)
    calculator = WeightCalculator(file_manager, config)
    
    # 批量处理
    results = []
    for i, row in benchmark_df.iterrows():
        # 使用原始问题作为输入
        query = str(row.get('原始问题', row.get('原始问', '')))
        if not query or query == 'nan':
            continue
        
        # 标杆数据
        benchmark_rewrite = str(row.get('标杆改写', row.get('改写后问题', ''))) if pd.notna(row.get('标杆改写', row.get('改写后问题', ''))) else ""
        benchmark_intent = str(row.get('标杆意图', row.get('意图', ''))) if pd.notna(row.get('标杆意图', row.get('意图', ''))) else ""
        
        # 切词匹配
        matched_words = segmenter.segment(query, args.domain)
        
        if not matched_words:
            results.append({
                "原始问题（必填）": query,
                "业务领域": args.domain,
                "诉求分类（必填）": "",
                "关键词": "",
                "top2意图": "",
                "大模型意图": "(无匹配)",
                "置信分": 0,
                "标杆改写": benchmark_rewrite,
                "标杆意图": benchmark_intent,
                "匹配结果": "失败"
            })
            continue
        
        # 权重计算
        calc_kwargs = {"domain": args.domain}
        if args.threshold:
            calc_kwargs["threshold"] = args.threshold
        if args.top_k:
            calc_kwargs["top_k"] = args.top_k
        
        if args.threshold or args.top_k:
            top_k_intents = calculator.calculate_with_config(matched_words, **calc_kwargs)
        else:
            top_k_intents = calculator.calculate(matched_words, args.domain)
        
        if not top_k_intents:
            results.append({
                "原始问题（必填）": query,
                "业务领域": args.domain,
                "诉求分类（必填）": "",
                "关键词": format_keywords_for_table(matched_words, []),
                "top2意图": "",
                "大模型意图": "(无候选)",
                "置信分": 0,
                "标杆改写": benchmark_rewrite,
                "标杆意图": benchmark_intent,
                "匹配结果": "阈值过滤"
            })
            continue
        
        # 最终意图
        final_intent = top_k_intents[0]["意图"]
        raw_score = top_k_intents[0]["得分"]
        if raw_score >= 1.0:
            confidence = min(80 + int(raw_score * 10), 99)
        else:
            confidence = int(raw_score * 100)
        
        category = get_intent_category(final_intent, weighted_words_path, file_manager)
        
        # 判断是否与标杆意图匹配
        match_result = "不一致"
        if final_intent == benchmark_intent:
            match_result = "完全一致"
        elif alignment.get(final_intent, {}).get("标杆意图") == benchmark_intent:
            match_result = "对齐一致"
        elif benchmark_intent in format_top2_intents(top_k_intents):
            match_result = "Top2命中"
        
        results.append({
            "原始问题（必填）": query,
            "业务领域": args.domain,
            "诉求分类（必填）": category,
            "关键词": format_keywords_for_table(matched_words, top_k_intents),
            "top2意图": format_top2_intents(top_k_intents),
            "大模型意图": final_intent,
            "置信分": confidence,
            "标杆改写": benchmark_rewrite,
            "标杆意图": benchmark_intent,
            "匹配结果": match_result
        })
        
        if (i + 1) % 50 == 0:
            print(f"[对比匹配] 进度: {i+1}/{len(benchmark_df)}")
    
    print(f"[对比匹配] 处理完成: {len(results)} 条")
    
    # 统计
    match_stats = {}
    for r in results:
        status = r["匹配结果"]
        match_stats[status] = match_stats.get(status, 0) + 1
    
    print("\n[对比匹配] === 匹配统计 ===")
    for status, count in sorted(match_stats.items()):
        pct = count / len(results) * 100
        print(f"  {status}: {count} ({pct:.1f}%)")
    
    # 保存结果
    output_dir = file_manager.get_intent_match_dir(args.domain)
    output_file = output_dir / "benchmark_comparison.xlsx"
    if args.output:
        output_file = Path(args.output)
    
    df = pd.DataFrame(results)
    df.to_excel(output_file, index=False)
    print(f"\n[对比匹配] 结果已保存: {output_file}")


if __name__ == "__main__":
    main()
