# -*- coding: utf-8 -*-
"""
工作流脚本：三层特征词提取

从意图清单中提取三层特征词（L1_事项词、L2_动作词、L3_场景词）
AI分析由AI助手完成，此脚本负责数据准备和结果保存
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.common.file_manager import FileManager
from scripts.common.config import ConfigManager
from scripts.modules.feature_extractor import FeatureExtractor


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="三层特征词提取工作流"
    )
    parser.add_argument(
        "--domain", "-d",
        required=True,
        help="领域名称，如 '失业保险'"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="意图清单文件路径（支持.json或.xlsx）"
    )
    parser.add_argument(
        "--output-dir", "-o",
        help="输出目录，默认为 result/{领域}/intent_list/{YYYYMMDD}/"
    )
    parser.add_argument(
        "--date",
        help="日期目录，格式YYYYMMDD，默认为今天"
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="仅准备AI输入，不保存结果（用于工作流第一步）"
    )
    parser.add_argument(
        "--ai-output",
        help="AI分析结果文本或文件路径（用于保存结果时）"
    )
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    # 初始化
    file_manager = FileManager()
    config = ConfigManager()
    extractor = FeatureExtractor(file_manager, config)
    
    # 确定输出目录（每次创建新版本目录，避免覆盖）
    if args.output_dir:
        output_dir = Path(args.output_dir)
    elif args.date:
        # 指定日期时使用该日期目录
        output_dir = file_manager.get_intent_list_dir(args.domain, args.date)
    else:
        # 创建新的带时间戳目录
        output_dir = file_manager.get_intent_list_dir(args.domain, create_new=True)
    
    print(f"[特征词提取] 领域: {args.domain}")
    print(f"[特征词提取] 输入文件: {args.input}")
    print(f"[特征词提取] 输出目录: {output_dir}")
    
    # 加载意图清单
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = file_manager.base_dir / input_path
    
    intent_list = extractor.load_intent_list(input_path)
    print(f"[特征词提取] 加载意图数量: {len(intent_list)}")
    
    if args.prepare_only:
        # 仅准备AI输入
        ai_input = extractor.prepare_for_ai(intent_list)
        print("\n" + "="*60)
        print("请将以下内容发送给AI助手进行分析：")
        print("="*60)
        print(ai_input)
        print("="*60)
        
        # 保存原始意图清单到输出目录
        file_manager.save_json(
            {"意图列表": intent_list},
            output_dir / "intent_list.json"
        )
        print(f"\n[特征词提取] 已保存意图清单到: {output_dir / 'intent_list.json'}")
        
    else:
        # 保存AI分析结果
        if not args.ai_output:
            print("[错误] 需要提供 --ai-output 参数（AI分析结果）")
            sys.exit(1)
        
        # 检查是文件路径还是直接的文本
        ai_output_path = Path(args.ai_output)
        if ai_output_path.exists():
            with open(ai_output_path, 'r', encoding='utf-8') as f:
                ai_output = f.read()
        else:
            ai_output = args.ai_output
        
        # 执行完整提取流程
        result = extractor.extract(input_path, output_dir, ai_output)
        
        # 打印摘要
        summary = extractor.get_summary(result)
        print("\n[特征词提取] 完成！摘要：")
        for key, value in summary.items():
            print(f"  - {key}: {value}")
        
        print(f"\n[特征词提取] 结果已保存到: {output_dir}")


if __name__ == "__main__":
    main()
