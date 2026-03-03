# -*- coding: utf-8 -*-
"""
工作流脚本：三层特征词权重打分

对特征词进行权重打分（混合模式：AI打分 + 人工审核）
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.common.file_manager import FileManager
from scripts.common.config import ConfigManager
from scripts.modules.weight_scorer import WeightScorer


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="三层特征词权重打分工作流"
    )
    parser.add_argument(
        "--domain", "-d",
        required=True,
        help="领域名称，如 '失业保险'"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="特征词文件路径（feature_words.json）"
    )
    parser.add_argument(
        "--output-dir", "-o",
        help="输出目录，默认为输入文件同目录"
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="仅准备AI打分输入"
    )
    parser.add_argument(
        "--ai-output",
        help="AI打分结果文本或文件路径"
    )
    parser.add_argument(
        "--import-manual",
        help="导入人工调整后的Excel文件路径"
    )
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="合并并保存最终权重结果"
    )
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    # 初始化
    file_manager = FileManager()
    config = ConfigManager()
    scorer = WeightScorer(file_manager, config)
    
    # 确定输入输出路径
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = file_manager.base_dir / input_path
    
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        # 默认使用 weighted 目录: result/{领域}/weighted/{日期}/
        output_dir = file_manager.get_weighted_dir(args.domain)
    
    print(f"[权重打分] 领域: {args.domain}")
    print(f"[权重打分] 输入文件: {input_path}")
    print(f"[权重打分] 输出目录: {output_dir}")
    
    # 加载特征词数据
    feature_words = scorer.load_feature_words(input_path)
    
    if args.prepare_only:
        # 步骤1：准备AI打分输入
        ai_input = scorer.prepare_for_ai(feature_words)
        print("\n" + "="*60)
        print("请将以下内容发送给AI助手进行打分：")
        print("="*60)
        print(ai_input)
        print("="*60)
        
        # 统计词汇数量
        unique_words = scorer.collect_unique_words(feature_words)
        print(f"\n[权重打分] 待打分词汇数量: {len(unique_words)}")
        
    elif args.ai_output:
        # 步骤2：保存AI打分结果
        ai_output_path = Path(args.ai_output)
        if ai_output_path.exists():
            with open(ai_output_path, 'r', encoding='utf-8') as f:
                ai_output = f.read()
        else:
            ai_output = args.ai_output
        
        # 解析并保存AI结果
        weight_result = scorer.parse_ai_result(ai_output)
        scorer.save_ai_result(weight_result, feature_words, output_dir)
        
        print(f"\n[权重打分] AI打分结果已保存到:")
        print(f"  - {output_dir / 'weighted_words_ai.json'}")
        print(f"  - {output_dir / 'weighted_words_review.xlsx'} (供人工审核)")
        
        # 打印摘要
        summary = scorer.get_summary(weight_result)
        print("\n[权重打分] AI打分摘要：")
        for key, value in summary.items():
            print(f"  - {key}: {value}")
        
    elif args.import_manual:
        # 步骤3：导入人工调整
        manual_path = Path(args.import_manual)
        if not manual_path.exists():
            print(f"[错误] 文件不存在: {manual_path}")
            sys.exit(1)
        
        weight_result = scorer.import_manual_adjustment(manual_path)
        print(f"[权重打分] 已导入人工调整: {len(weight_result.get('词权重表', {}))} 个词")
        
        # 合并并保存最终结果
        scorer.merge_and_save(feature_words, weight_result, output_dir)
        
        print(f"\n[权重打分] 最终结果已保存到:")
        print(f"  - {output_dir / 'weighted_words.json'}")
        print(f"  - {output_dir / 'weighted_words.xlsx'}")
        
    elif args.finalize:
        # 直接使用AI打分结果作为最终结果（跳过人工审核）
        ai_result_path = output_dir / "weighted_words_ai.json"
        if not ai_result_path.exists():
            print(f"[错误] AI打分结果不存在: {ai_result_path}")
            sys.exit(1)
        
        weight_result = file_manager.load_json(ai_result_path)
        scorer.merge_and_save(feature_words, weight_result, output_dir)
        
        print(f"\n[权重打分] 已使用AI打分结果作为最终权重")
        print(f"  - {output_dir / 'weighted_words.json'}")
        print(f"  - {output_dir / 'weighted_words.xlsx'}")
        
    else:
        print("[错误] 请指定操作模式：")
        print("  --prepare-only  准备AI打分输入")
        print("  --ai-output     保存AI打分结果")
        print("  --import-manual 导入人工调整")
        print("  --finalize      使用AI结果作为最终权重")
        sys.exit(1)


if __name__ == "__main__":
    main()
