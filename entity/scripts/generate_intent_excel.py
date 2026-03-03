#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成意图清单 Excel 报告
- 根据 intent_list.json 生成 Excel
- 每个实体的意图单独成行
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd


def generate_intent_excel(data_path: str, output_path: str):
    """
    生成意图清单 Excel 报告
    - 支持 v1.1 格式（含条款和条款明细）
    """
    # 读取意图数据
    with open(data_path, "r", encoding="utf-8") as f:
        intents_data = json.load(f)
    
    # 构建数据行
    rows = []
    for entity_item in intents_data:
        entity_name = entity_item.get("entity", "")
        category = entity_item.get("category", "")
        intents = entity_item.get("intents", [])
        
        for intent in intents:
            rows.append({
                "实体": entity_name,
                "实体类型": category,
                "意图类型": intent.get("type", ""),
                "意图描述": intent.get("intent", ""),
                "条款": intent.get("article", ""),
                "条款明细": intent.get("article_detail", "")
            })
    
    if not rows:
        print("警告: 没有意图数据")
        return
    
    # 创建 DataFrame
    df = pd.DataFrame(rows)
    
    # 写入 Excel
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="意图清单", index=False)
        
        ws = writer.sheets["意图清单"]
        ws.column_dimensions['A'].width = 20   # 实体
        ws.column_dimensions['B'].width = 12   # 实体类型
        ws.column_dimensions['C'].width = 12   # 意图类型
        ws.column_dimensions['D'].width = 40   # 意图描述
        ws.column_dimensions['E'].width = 12   # 条款
        ws.column_dimensions['F'].width = 80   # 条款明细
    
    # 统计有条款依据的意图数
    with_article = sum(1 for r in rows if r["条款"])
    
    print(f"\n意图清单已生成: {output_path}")
    print(f"总实体数: {len(intents_data)}")
    print(f"总意图数: {len(rows)}")
    print(f"有条款依据: {with_article} 条 ({with_article * 100 // len(rows)}%)")


def main():
    import sys
    
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        
        if input_path.is_dir():
            data_path = input_path / "intent_list.json"
            regulation_name = input_path.name
            output_dir = input_path
        elif input_path.is_file():
            data_path = input_path
            output_dir = input_path.parent
            regulation_name = output_dir.name
        else:
            print(f"错误: 路径不存在: {input_path}")
            return
    else:
        print("用法: python generate_intent_excel.py result/<法规名>")
        return
    
    if not data_path.exists():
        print(f"错误: 意图数据文件不存在: {data_path}")
        print("请先执行 /intent 工作流生成意图数据")
        return
    
    output_path = output_dir / f"{regulation_name}_意图清单.xlsx"
    
    print(f"法规名称: {regulation_name}")
    print(f"数据文件: {data_path}")
    print(f"输出报告: {output_path}")
    
    generate_intent_excel(str(data_path), str(output_path))


if __name__ == "__main__":
    main()
