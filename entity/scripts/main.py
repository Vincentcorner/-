#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
法律法规主体实体提取工具 - 主入口

用法:
    # 提取单个文件
    python main.py --input path/to/file.pdf --output path/to/output/
    
    # 批量提取
    python main.py --input path/to/input_dir/ --output path/to/output/ --batch
    
    # 仅使用规则提取（不调用 LLM）
    python main.py --input path/to/file.pdf --no-llm
"""

import argparse
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from parse_document import parse_document, get_supported_files
from extract_entities import extract_entities
from export_results import export_results


def process_file(
    input_path: str,
    output_dir: str,
    use_llm: bool = True,
    formats: list = None,
    api_key: str = None
) -> dict:
    """
    处理单个文件
    
    Args:
        input_path: 输入文件路径
        output_dir: 输出目录
        use_llm: 是否使用 LLM
        formats: 输出格式列表
        api_key: API Key
        
    Returns:
        处理结果
    """
    print(f"\n处理文件: {input_path}")
    
    # 解析文档
    print("  [1/3] 解析文档...")
    text = parse_document(input_path)
    print(f"       提取文本 {len(text)} 字符")
    
    # 提取实体
    print("  [2/3] 提取实体...")
    entities = extract_entities(text, use_llm=use_llm, api_key=api_key)
    total = sum(len(v) for v in entities.values())
    print(f"       发现 {total} 个实体")
    
    # 导出结果
    print("  [3/3] 导出结果...")
    outputs = export_results(input_path, entities, output_dir, formats)
    for fmt, path in outputs.items():
        print(f"       {fmt}: {path}")
    
    return {
        "input": input_path,
        "entities_count": total,
        "outputs": outputs
    }


def main():
    parser = argparse.ArgumentParser(
        description="法律法规主体实体提取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py --input originalfile/法律.pdf --output result/
  python main.py --input originalfile/ --output result/ --batch
  python main.py --input originalfile/法律.pdf --no-llm --format json md
        """
    )
    
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="输入文件或目录路径"
    )
    
    parser.add_argument(
        "--output", "-o",
        default="result/",
        help="输出目录路径 (默认: result/)"
    )
    
    parser.add_argument(
        "--batch", "-b",
        action="store_true",
        help="批量处理模式（处理目录下所有文件）"
    )
    
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="禁用 LLM 提取，仅使用规则匹配"
    )
    
    parser.add_argument(
        "--format", "-f",
        nargs="+",
        choices=["json", "xlsx", "md", "all"],
        default=["all"],
        help="输出格式 (默认: all)"
    )
    
    parser.add_argument(
        "--api-key",
        help="LLM API Key（也可通过 DASHSCOPE_API_KEY 环境变量设置）"
    )
    
    args = parser.parse_args()
    
    # 处理格式参数
    if "all" in args.format:
        formats = ["json", "xlsx", "md"]
    else:
        formats = args.format
    
    # 获取 API Key
    api_key = args.api_key or os.environ.get("DASHSCOPE_API_KEY")
    use_llm = not args.no_llm
    
    if use_llm and not api_key:
        print("警告: 未设置 API Key，将仅使用规则提取")
        print("      设置方法: export DASHSCOPE_API_KEY='your-key'")
        use_llm = False
    
    # 确保输出目录存在
    Path(args.output).mkdir(parents=True, exist_ok=True)
    
    # 收集要处理的文件
    input_path = Path(args.input)
    
    if input_path.is_file():
        files = [str(input_path)]
    elif input_path.is_dir():
        if not args.batch:
            print("错误: 输入是目录，请使用 --batch 选项")
            sys.exit(1)
        files = get_supported_files(str(input_path))
        if not files:
            print(f"错误: 目录中没有找到支持的文件 (.docx, .pdf, .txt)")
            sys.exit(1)
    else:
        print(f"错误: 输入路径不存在: {args.input}")
        sys.exit(1)
    
    print(f"=" * 60)
    print(f"法律法规主体实体提取工具")
    print(f"=" * 60)
    print(f"待处理文件: {len(files)} 个")
    print(f"使用 LLM: {'是' if use_llm else '否'}")
    print(f"输出格式: {', '.join(formats)}")
    print(f"输出目录: {args.output}")
    
    # 处理文件
    results = []
    for file_path in files:
        try:
            result = process_file(
                file_path,
                args.output,
                use_llm=use_llm,
                formats=formats,
                api_key=api_key
            )
            results.append(result)
        except Exception as e:
            print(f"  错误: {e}")
            results.append({
                "input": file_path,
                "error": str(e)
            })
    
    # 输出汇总
    print(f"\n{'=' * 60}")
    print("处理完成!")
    print(f"成功: {len([r for r in results if 'error' not in r])}")
    print(f"失败: {len([r for r in results if 'error' in r])}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
