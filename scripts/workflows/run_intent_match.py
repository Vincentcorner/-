# -*- coding: utf-8 -*-
"""
工作流脚本：意图匹配（合并诉求转写，支持批量处理）

完整的意图匹配流程，包括：
1. 诉求转写（可选，已转写则跳过）
2. 切词匹配（AC自动机）
3. 权重计算
4. AI意图筛选（可选）
5. 结果保存到 intent_match 目录

批量处理：使用 | 分隔多个问题
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.common.file_manager import FileManager
from scripts.common.config import ConfigManager
from scripts.modules.query_segmenter import QuerySegmenter
from scripts.modules.weight_calculator import WeightCalculator
from scripts.modules.intent_selector import IntentSelector


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="意图匹配工作流（含诉求转写，支持批量处理）"
    )
    parser.add_argument(
        "--domain", "-d",
        required=True,
        help="领域名称，如 '失业保险'"
    )
    parser.add_argument(
        "--raw-query", "-r",
        help="用户原始诉求（口语化表达），多个用 | 分隔"
    )
    parser.add_argument(
        "--rewrite", 
        help="转写后的标准表达，多个用 | 分隔（与 raw-query 一一对应）"
    )
    parser.add_argument(
        "--query", "-q",
        help="用户诉求（兼容旧参数，等同于 --rewrite），多个用 | 分隔"
    )
    parser.add_argument(
        "--weighted-words", "-w",
        required=True,
        help="带权重特征词文件路径"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        help="最低得分阈值，默认使用配置值"
    )
    parser.add_argument(
        "--top-k",
        type=int,
        help="返回Top-K个意图，默认使用配置值"
    )
    parser.add_argument(
        "--no-ai-select",
        action="store_true",
        help="跳过AI意图筛选，直接返回权重计算结果"
    )
    parser.add_argument(
        "--prepare-rewrite",
        action="store_true",
        help="准备AI转写输入"
    )
    parser.add_argument(
        "--prepare-ai-select",
        action="store_true",
        help="准备AI筛选输入（需要人工将结果发送给AI）"
    )
    parser.add_argument(
        "--ai-select-output",
        help="AI筛选结果"
    )
    parser.add_argument(
        "--output-json",
        action="store_true",
        help="以JSON格式输出结果"
    )
    
    return parser.parse_args()


def get_intent_category(intent_name: str, weighted_words_path: Path, file_manager: FileManager) -> str:
    """获取意图的分类"""
    try:
        data = file_manager.load_json(weighted_words_path)
        metadata = data.get("意图元数据", {})
        if intent_name in metadata:
            return metadata[intent_name].get("意图分类", "")
    except:
        pass
    return ""


def format_keywords_for_table(matched_words: list, top_intents: list) -> str:
    """格式化关键词，按意图分组显示 【意图】词:权重, 词:权重"""
    intent_keywords = {}
    for match in matched_words:
        intent = match["意图"]
        word = match["词"]
        weight = match["权重"]
        if intent not in intent_keywords:
            intent_keywords[intent] = []
        intent_keywords[intent].append(f"{word}:{weight}")
    
    # 只显示top意图的关键词
    result_parts = []
    for intent_info in top_intents[:5]:  # 最多5个意图
        intent_name = intent_info["意图"]
        if intent_name in intent_keywords:
            keywords_str = ", ".join(intent_keywords[intent_name][:5])  # 每意图最多5个词
            result_parts.append(f"【{intent_name}】{keywords_str}")
    return "\n".join(result_parts)


def format_top2_intents(top_intents: list) -> str:
    """格式化top2意图"""
    if not top_intents:
        return ""
    intents = [i["意图"] for i in top_intents[:2]]
    return "、".join(intents)


def save_results_to_file(results: list, file_manager: FileManager, domain: str):
    """保存多条匹配结果到文件"""
    output_dir = file_manager.get_intent_match_dir(domain)
    
    # 读取现有结果或创建新列表
    result_file = output_dir / "intent_match_results.json"
    if result_file.exists():
        try:
            existing = file_manager.load_json(result_file)
            if isinstance(existing, list):
                existing.extend(results)
            else:
                existing = results
        except:
            existing = results
    else:
        existing = results
    
    # 保存JSON和Excel
    file_manager.save_json(existing, result_file)
    file_manager.save_excel(existing, output_dir / "intent_match_results.xlsx")
    
    return output_dir


def print_batch_table(results: list, domain: str):
    """打印批量结果表格"""
    print("\n" + "=" * 120)
    print(f"【意图匹配结果】 共 {len(results)} 条")
    print("=" * 120)
    
    # 表头
    print(f"{'序号':<4} | {'原始问题':<25} | {'诉求分类':<18} | {'top2意图':<35} | {'大模型意图':<20} | {'置信分':<6}")
    print("-" * 120)
    
    for i, result in enumerate(results, 1):
        raw = result.get("原始诉求", "")[:20] + "..." if len(result.get("原始诉求", "")) > 20 else result.get("原始诉求", "")
        category = result.get("诉求分类", "")[:15] if result.get("诉求分类") else ""
        top2 = result.get("top2意图", "")[:32] + "..." if len(result.get("top2意图", "")) > 32 else result.get("top2意图", "")
        final = result.get("大模型意图", "")[:18] if result.get("大模型意图") else ""
        conf = f"[{result.get('置信分', '')}]" if result.get('置信分') else ""
        
        print(f"{i:<4} | {raw:<25} | {category:<18} | {top2:<35} | {final:<20} | {conf:<6}")
    
    print("=" * 120)


def process_single_query(query: str, raw_query: str, args, segmenter, calculator, weighted_words_path, file_manager):
    """处理单个查询，返回结果字典"""
    matched_words = segmenter.segment(query, args.domain)
    
    if not matched_words:
        return {
            "原始问题（必填）": raw_query or query,
            "业务领域": args.domain,
            "诉求分类（必填）": "",
            "关键词": "",
            "top2意图": "",
            "大模型意图": "(无匹配)",
            "置信分": 0,
            "转写结果": query,
            "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    
    # 权重计算
    calc_kwargs = {"domain": args.domain}
    if args.threshold is not None:
        calc_kwargs["threshold"] = args.threshold
    if args.top_k is not None:
        calc_kwargs["top_k"] = args.top_k
    
    if args.threshold or args.top_k:
        top_k_intents = calculator.calculate_with_config(matched_words, **calc_kwargs)
    else:
        top_k_intents = calculator.calculate(matched_words, args.domain)
    
    if not top_k_intents:
        return {
            "原始问题（必填）": raw_query or query,
            "业务领域": args.domain,
            "诉求分类（必填）": "",
            "关键词": format_keywords_for_table(matched_words, []),
            "top2意图": "",
            "大模型意图": "(无候选)",
            "置信分": 0,
            "转写结果": query,
            "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    
    # 确定最终意图
    final_intent = top_k_intents[0]["意图"]
    # 置信分：基于得分，但得分可能>1，需要合理映射
    raw_score = top_k_intents[0]["得分"]
    # 如果得分>1，映射到80-100区间；否则直接*100
    if raw_score >= 1.0:
        confidence = min(80 + int(raw_score * 10), 99)
    else:
        confidence = int(raw_score * 100)
    
    # 获取诉求分类
    category = get_intent_category(final_intent, weighted_words_path, file_manager)
    
    return {
        "原始问题（必填）": raw_query or query,
        "业务领域": args.domain,
        "诉求分类（必填）": category,
        "关键词": format_keywords_for_table(matched_words, top_k_intents),
        "top2意图": format_top2_intents(top_k_intents),
        "大模型意图": final_intent,
        "置信分": confidence,
        "转写结果": query,
        "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


def main():
    args = parse_args()
    
    # 初始化
    file_manager = FileManager()
    config = ConfigManager()
    
    # 确定输入路径
    weighted_words_path = Path(args.weighted_words)
    if not weighted_words_path.is_absolute():
        weighted_words_path = file_manager.base_dir / weighted_words_path
    
    # 解析输入（支持 | 分隔的批量输入）
    raw_queries = []
    rewrite_queries = []
    
    if args.raw_query:
        raw_queries = [q.strip() for q in args.raw_query.split("|") if q.strip()]
    
    rewrite_input = args.rewrite or args.query or ""
    if rewrite_input:
        rewrite_queries = [q.strip() for q in rewrite_input.split("|") if q.strip()]
    
    # 确定要处理的查询列表
    if rewrite_queries:
        queries = rewrite_queries
        # 如果有原始诉求，确保数量匹配
        if raw_queries and len(raw_queries) != len(queries):
            print(f"[警告] 原始诉求数量({len(raw_queries)})与转写结果数量({len(queries)})不匹配")
            raw_queries = raw_queries + [""] * (len(queries) - len(raw_queries))
    elif raw_queries:
        queries = raw_queries
        rewrite_queries = [""] * len(queries)
    else:
        print("[错误] 请提供 --raw-query 或 --rewrite 参数")
        sys.exit(1)
    
    # 补齐原始诉求列表
    if not raw_queries:
        raw_queries = [""] * len(queries)
    
    print(f"[意图匹配] 领域: {args.domain}")
    print(f"[意图匹配] 待处理: {len(queries)} 条问题")
    
    # 初始化处理模块（只加载一次）
    segmenter = QuerySegmenter(file_manager, config)
    segmenter.load_and_build(weighted_words_path)
    calculator = WeightCalculator(file_manager, config)
    
    # 批量处理
    results = []
    for i, query in enumerate(queries):
        raw = raw_queries[i] if i < len(raw_queries) else ""
        result = process_single_query(query, raw, args, segmenter, calculator, weighted_words_path, file_manager)
        results.append(result)
        print(f"[意图匹配] [{i+1}/{len(queries)}] {query[:20]}... -> {result['大模型意图']}")
    
    # 保存结果
    output_dir = save_results_to_file(results, file_manager, args.domain)
    print(f"[意图匹配] 结果已保存到: {output_dir}")
    
    # 输出结果
    if args.output_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_batch_table(results, args.domain)


if __name__ == "__main__":
    main()
