# -*- coding: utf-8 -*-
"""
工作流脚本：意图匹配 + 标杆对比

支持批量处理：
1. 从Excel文件读取原始问题（第一列）
2. AI诉求转写（准备提示词，由AI助手完成转写）
3. 意图匹配（AC自动机 + 权重计算）
4. 标杆数据对比（根据原始问匹配标杆的转写和意图）
5. 输出对比结果
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.common.file_manager import FileManager
from scripts.common.config import ConfigManager
from scripts.modules.query_segmenter import QuerySegmenter
from scripts.modules.weight_calculator import WeightCalculator
from scripts.modules.query_rewriter import QueryRewriter


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="意图匹配 + 标杆对比工作流"
    )
    parser.add_argument(
        "--domain", "-d",
        required=True,
        help="领域名称，如 '失业保险'"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="输入Excel文件路径（读取第一列作为原始问题）"
    )
    parser.add_argument(
        "--weighted-words", "-w",
        required=True,
        help="带权重特征词文件路径"
    )
    parser.add_argument(
        "--benchmark", "-b",
        help="标杆数据文件路径（默认使用 originalfile/{domain}/深圳原始数据（部分）.xlsx）"
    )
    parser.add_argument(
        "--prepare-rewrite",
        action="store_true",
        help="准备AI转写输入（生成提示词供AI分析）"
    )
    parser.add_argument(
        "--rewrite-file",
        help="AI转写结果文件路径（每行一个转写结果，与输入问题一一对应）"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.4,
        help="最低得分阈值（默认0.4）"
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="返回Top-K个意图（默认5）"
    )
    parser.add_argument(
        "--output", "-o",
        help="输出文件路径（默认保存到 result/{domain}/benchmark_compare/）"
    )
    parser.add_argument(
        "--use-rewritten",
        action="store_true",
        help="使用'改写后问题'列进行匹配（而非'原始问'列）"
    )
    
    return parser.parse_args()


def load_input_questions(file_path: Path, file_manager: FileManager, use_rewritten: bool = False) -> Tuple[List[str], List[str]]:
    """
    从Excel文件读取问题
    
    Args:
        file_path: Excel文件路径
        file_manager: 文件管理器
        use_rewritten: 是否使用改写后问题列进行匹配
        
    Returns:
        (原始问题列表, 匹配用问题列表)
    """
    df = file_manager.load_excel(file_path)
    
    # 读取原始问列
    raw_questions = []
    if "原始问" in df.columns:
        raw_questions = [str(q).strip() if pd.notna(q) else "" for q in df["原始问"]]
    elif len(df.columns) > 0:
        raw_questions = [str(q).strip() if pd.notna(q) else "" for q in df.iloc[:, 0]]
    
    # 读取匹配用问题
    if use_rewritten and "改写后问题" in df.columns:
        match_questions = [str(q).strip() if pd.notna(q) else raw_questions[i] for i, q in enumerate(df["改写后问题"])]
        print(f"[加载] 使用'改写后问题'列进行匹配")
    else:
        match_questions = raw_questions
        print(f"[加载] 使用'原始问'列进行匹配")
    
    # 过滤空行
    valid_pairs = [(r, m) for r, m in zip(raw_questions, match_questions) if r.strip()]
    raw_questions = [p[0] for p in valid_pairs]
    match_questions = [p[1] for p in valid_pairs]
    
    return raw_questions, match_questions


def load_benchmark_data(file_path: Path, file_manager: FileManager, use_rewritten: bool = False) -> Dict[str, Dict]:
    """
    加载标杆数据，构建查询键 -> 标杆信息的映射
    
    Args:
        file_path: 标杆文件路径
        file_manager: 文件管理器
        use_rewritten: 是否使用"改写后问题"列作为查询键（默认使用"原始问"）
        
    Returns:
        查询键 -> {改写后问题, 意图, 原始问} 的映射
    """
    df = file_manager.load_excel(file_path)
    
    key_col = "改写后问题" if use_rewritten else "原始问"
    print(f"[标杆] 使用'{key_col}'列作为匹配键")
    
    benchmark_map = {}
    for _, row in df.iterrows():
        raw_question = str(row.get("原始问", "")).strip()
        rewritten_question = str(row.get("改写后问题", "")).strip()
        key = rewritten_question if use_rewritten else raw_question
        if key:
            benchmark_map[key] = {
                "原始问": raw_question,
                "标杆转写": rewritten_question,
                "标杆意图": str(row.get("意图", "")).strip(),
            }
    
    return benchmark_map


def prepare_rewrite_prompt(questions: List[str], rewriter: QueryRewriter) -> str:
    """
    准备批量AI转写的提示词
    
    Args:
        questions: 原始问题列表
        rewriter: 转写器实例
        
    Returns:
        格式化的提示词
    """
    prompt = """# 批量诉求转写任务

请将以下用户的口语化诉求转写为标准化的业务表达。

## 转写规则

1. **保留核心语义**：不改变用户的原始意图
2. **规范化表达**：使用业务标准术语
3. **简化冗余**：去除无关的寒暄语和重复内容
4. **补全省略**：补充必要但被省略的信息

## 示例

| 用户原始诉求 | 转写后 |
|-------------|--------|
| 我想领失业金 | 失业保险金申领 |
| 公司倒闭了怎么办 | 失业保险金申领、企业职工失业登记 |
| 返还的钱怎么查 | 稳岗返还查询 |

## 输出格式

请按原始顺序输出转写结果，每行一个。如有多个可能的意图，用顿号分隔。

---

## 待转写的用户诉求

"""
    for i, q in enumerate(questions, 1):
        prompt += f"{i}. {q}\n"
    
    return prompt


def load_rewrite_results(file_path: Path) -> List[str]:
    """
    从文件加载AI转写结果
    
    Args:
        file_path: 转写结果文件路径
        
    Returns:
        转写结果列表
    """
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    results = []
    for line in lines:
        line = line.strip()
        if line:
            # 去除编号前缀 "1. xxx" -> "xxx"
            if ". " in line and line.split(". ")[0].isdigit():
                line = ". ".join(line.split(". ")[1:])
            results.append(line)
    
    return results


def match_intent(query: str, segmenter: QuerySegmenter, calculator: WeightCalculator,
                 domain: str, threshold: float, top_k: int) -> Tuple[str, float, List[Dict]]:
    """
    对单个查询进行意图匹配
    
    Args:
        query: 转写后的查询
        segmenter: 分词器
        calculator: 权重计算器
        domain: 领域
        threshold: 阈值
        top_k: 返回数量
        
    Returns:
        (最佳意图, 置信分, top_k意图列表)
    """
    matched_words = segmenter.segment(query, domain)
    
    if not matched_words:
        return "(无匹配)", 0, []
    
    top_intents = calculator.calculate_with_config(
        matched_words, 
        domain=domain, 
        threshold=threshold, 
        top_k=top_k
    )
    
    if not top_intents:
        return "(无候选)", 0, []
    
    best_intent = top_intents[0]["意图"]
    raw_score = top_intents[0]["得分"]
    
    # 置信分映射
    if raw_score >= 1.0:
        confidence = min(80 + int(raw_score * 10), 99)
    else:
        confidence = int(raw_score * 100)
    
    return best_intent, confidence, top_intents


def format_top2_intents(top_intents: List[Dict]) -> str:
    """格式化top2意图"""
    if not top_intents:
        return ""
    intents = [i["意图"] for i in top_intents[:2]]
    return "、".join(intents)


def run_compare(args, file_manager: FileManager, config: ConfigManager):
    """
    执行对比流程
    """
    import pandas as pd
    
    # 路径处理
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = file_manager.base_dir / input_path
    
    weighted_path = Path(args.weighted_words)
    if not weighted_path.is_absolute():
        weighted_path = file_manager.base_dir / weighted_path
    
    # 标杆数据路径
    if args.benchmark:
        benchmark_path = Path(args.benchmark)
    else:
        benchmark_path = file_manager.base_dir / "originalfile" / args.domain / "深圳原始数据（部分）.xlsx"
    
    # 加载输入问题
    print(f"[加载] 输入文件: {input_path}")
    questions, match_queries = load_input_questions(input_path, file_manager, getattr(args, 'use_rewritten', False))
    print(f"[加载] 共 {len(questions)} 个问题")
    
    # 加载标杆数据
    print(f"[加载] 标杆数据: {benchmark_path}")
    use_rewritten = getattr(args, 'use_rewritten', False)
    benchmark_map = load_benchmark_data(benchmark_path, file_manager, use_rewritten)
    print(f"[加载] 标杆数据共 {len(benchmark_map)} 条")
    
    # 如果是准备转写模式
    if args.prepare_rewrite:
        rewriter = QueryRewriter(file_manager, config)
        prompt = prepare_rewrite_prompt(questions, rewriter)
        
        # 保存提示词到文件
        output_dir = file_manager.get_domain_dir(args.domain) / "benchmark_compare"
        output_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = output_dir / "rewrite_prompt.md"
        
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt)
        
        print("\n" + "=" * 80)
        print("【AI转写提示词已生成】")
        print(f"保存位置: {prompt_file}")
        print("=" * 80)
        print("\n请将以上提示词发送给AI助手进行转写，然后将结果保存到文件，再运行：")
        print(f"python {Path(__file__).name} -d {args.domain} -i {args.input} -w {args.weighted_words} --rewrite-file 转写结果.txt")
        print("=" * 80)
        print("\n--- 提示词内容 ---\n")
        print(prompt)
        return
    
    # 加载转写结果或使用已有的匹配查询
    if args.rewrite_file:
        rewrite_path = Path(args.rewrite_file)
        if not rewrite_path.is_absolute():
            rewrite_path = file_manager.base_dir / rewrite_path
        rewrites = load_rewrite_results(rewrite_path)
        print(f"[加载] 转写结果: {len(rewrites)} 条")
    else:
        # 使用 match_queries（可能是改写后问题或原始问题）
        rewrites = match_queries
    
    # 补齐转写结果

    while len(rewrites) < len(questions):
        rewrites.append(questions[len(rewrites)])
    
    # 初始化匹配模块
    print("[初始化] 加载特征词库...")
    segmenter = QuerySegmenter(file_manager, config)
    segmenter.load_and_build(weighted_path)
    calculator = WeightCalculator(file_manager, config)
    
    # 批量处理
    results = []
    print(f"\n[处理] 开始意图匹配...")
    
    for i, (question, rewrite) in enumerate(zip(questions, rewrites)):
        # 意图匹配
        best_intent, confidence, top_intents = match_intent(
            rewrite, segmenter, calculator,
            args.domain, args.threshold, args.top_k
        )
        
        # 查找标杆数据（根据 use_rewritten 参数决定使用转写结果还是原始问作为查询键）
        lookup_key = rewrite if use_rewritten else question
        benchmark = benchmark_map.get(lookup_key, {})
        benchmark_rewrite = benchmark.get("标杆转写", "")
        benchmark_intent = benchmark.get("标杆意图", "")
        
        # 判断是否一致
        is_match = "是" if best_intent == benchmark_intent else "否"
        
        result = {
            "原始问题": question,
            "AI转写结果": rewrite,
            "算法意图": best_intent,
            "top2意图": format_top2_intents(top_intents),
            "置信分": confidence,
            "标杆转写": benchmark_rewrite,
            "标杆意图": benchmark_intent,
            "是否一致": is_match,
        }
        results.append(result)
        
        # 进度显示
        status = "✓" if is_match == "是" else "✗"
        print(f"[{i+1}/{len(questions)}] {status} {question[:20]}... -> {best_intent} (标杆: {benchmark_intent})")
    
    # 保存结果（自动创建递增批次子目录）
    output_dir = file_manager.get_benchmark_compare_dir(args.domain)
    
    output_file = output_dir / "compare_results.xlsx"
    file_manager.save_excel(results, output_file)
    file_manager.save_json(results, output_dir / "compare_results.json")
    
    # 统计
    match_count = sum(1 for r in results if r["是否一致"] == "是")
    total_count = len(results)
    match_rate = match_count / total_count * 100 if total_count > 0 else 0
    
    print("\n" + "=" * 80)
    print(f"【对比完成】")
    print(f"总数: {total_count} | 一致: {match_count} | 一致率: {match_rate:.1f}%")
    print(f"结果保存: {output_file}")
    print("=" * 80)


def main():
    args = parse_args()
    
    # 初始化
    file_manager = FileManager()
    config = ConfigManager()
    
    run_compare(args, file_manager, config)


if __name__ == "__main__":
    main()
