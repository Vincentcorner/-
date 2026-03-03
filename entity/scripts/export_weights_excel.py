# -*- coding: utf-8 -*-
"""
全局词表 JSON → Excel 导出工具

将 weighted_words.json 转为人工可查阅的 Excel 格式。
支持命令行和模块两种使用方式。

用法：
    py scripts/export_weights_excel.py <json路径> [--output <xlsx路径>]
    py scripts/export_weights_excel.py result/global/weighted/weighted_words.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

import pandas as pd


def flatten_weights_for_excel(data: Dict) -> List[Dict]:
    """将权重词表JSON展平为Excel行格式

    Args:
        data: 权重词表原始数据 (含 意图映射表 + 词权重表)

    Returns:
        展平后的行列表，每行: {意图, 层级, 特征词, 权重, 理由}
    """
    intent_map = data.get('意图映射表', {})
    weight_table = data.get('词权重表', {})

    rows = []
    for intent, layers in intent_map.items():
        for layer, words in layers.items():
            for word in words:
                weight_info = weight_table.get(word, {})
                # 兼容新格式（一意图一词一分）和旧格式（全局权重）
                if isinstance(weight_info, dict):
                    if '权重' in weight_info:
                        # 旧格式：{权重: float, 理由: str}
                        weight = weight_info.get('权重', 0.5)
                        reason = weight_info.get('理由', '')
                    elif intent in weight_info:
                        # 新格式：{意图名: {权重: float, 理由: str}}
                        intent_score = weight_info.get(intent, {})
                        weight = intent_score.get('权重', 0.5)
                        reason = intent_score.get('理由', '')
                    else:
                        weight = 0.5
                        reason = '待打分'
                else:
                    weight = float(weight_info) if weight_info else 0.5
                    reason = ''

                rows.append({
                    '意图': intent,
                    '层级': layer,
                    '特征词': word,
                    '权重': weight,
                    '理由': reason,
                })

    # 按意图名 → 层级 → 权重降序排列
    layer_order = {
        '核心词': 1, '发散词': 2, '同义词': 3,
        'L1_事项词': 1, 'L2_动作词': 2, 'L3_场景词': 3,
    }
    rows.sort(key=lambda r: (r['意图'], layer_order.get(r['层级'], 99), -r['权重']))

    return rows


def export_to_excel(data: Dict, output_path: str) -> str:
    """导出权重词表为Excel文件

    Args:
        data: 权重词表原始JSON数据
        output_path: 输出xlsx路径

    Returns:
        实际保存的文件路径
    """
    rows = flatten_weights_for_excel(data)
    if not rows:
        print('[警告] 词表为空，无数据可导出')
        return output_path

    df = pd.DataFrame(rows)

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # Sheet1: 按意图展开的完整词表
        df.to_excel(writer, sheet_name='词表明细', index=False)
        ws = writer.sheets['词表明细']
        ws.column_dimensions['A'].width = 25  # 意图
        ws.column_dimensions['B'].width = 12  # 层级
        ws.column_dimensions['C'].width = 18  # 特征词
        ws.column_dimensions['D'].width = 8   # 权重
        ws.column_dimensions['E'].width = 30  # 理由

        # Sheet2: 汇总统计
        intent_map = data.get('意图映射表', {})
        weight_table = data.get('词权重表', {})
        summary_rows = []
        for intent, layers in intent_map.items():
            total_words = sum(len(words) for words in layers.values())
            summary_rows.append({
                '意图': intent,
                '层级数': len(layers),
                '特征词总数': total_words,
            })
        if summary_rows:
            summary_df = pd.DataFrame(summary_rows)
            summary_df.to_excel(writer, sheet_name='意图汇总', index=False)
            ws2 = writer.sheets['意图汇总']
            ws2.column_dimensions['A'].width = 25
            ws2.column_dimensions['B'].width = 10
            ws2.column_dimensions['C'].width = 12

    print(f'[导出完成] {output_path} ({len(rows)} 行, {len(data.get("意图映射表", {}))} 个意图)')
    return output_path


def main():
    parser = argparse.ArgumentParser(description='权重词表 JSON → Excel 导出')
    parser.add_argument('json_path', help='weighted_words.json 文件路径')
    parser.add_argument('--output', '-o', help='输出xlsx路径，默认同目录下 weighted_words.xlsx')
    args = parser.parse_args()

    json_path = Path(args.json_path)
    if not json_path.exists():
        print(f'[错误] 文件不存在: {json_path}')
        sys.exit(1)

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    output_path = args.output or str(json_path.with_suffix('.xlsx'))
    export_to_excel(data, output_path)


if __name__ == '__main__':
    main()
