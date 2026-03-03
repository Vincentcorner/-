# -*- coding: utf-8 -*-
"""
将意图特征词关系Excel转换为feature_weight工作流所需的格式

输入: Excel文件，包含意图和对应的三层特征词
输出: feature_words.json 和 feature_words.xlsx
"""

import pandas as pd
import json
import sys
from pathlib import Path
from datetime import datetime


def read_excel_with_info(file_path: str) -> dict:
    """读取Excel文件并输出结构信息"""
    print(f"[读取] 文件: {file_path}")
    
    # 读取所有sheet
    xlsx = pd.ExcelFile(file_path)
    print(f"[读取] Sheet列表: {xlsx.sheet_names}")
    
    result = {}
    for sheet_name in xlsx.sheet_names:
        df = pd.read_excel(xlsx, sheet_name=sheet_name)
        print(f"\n[Sheet: {sheet_name}]")
        print(f"  列名: {df.columns.tolist()}")
        print(f"  行数: {len(df)}")
        if len(df) > 0:
            print(f"  前5行样本:")
            print(df.head().to_string(index=False))
        result[sheet_name] = df
    
    return result


def convert_to_feature_words_format(sheets: dict, domain: str = "失业保险") -> dict:
    """
    将Excel数据转换为feature_words.json格式
    
    期望格式:
    {
        "意图映射表": {
            "意图名称1": {
                "L1_事项词": ["词1", "词2"],
                "L2_动作词": ["词1", "词2"],
                "L3_场景词": ["词1", "词2"]
            }
        },
        "意图元数据": {},
        "词权重表": {},
        "元信息": {}
    }
    """
    intent_map = {}
    intent_metadata = {}
    
    # 尝试找到主数据sheet
    main_df = None
    for sheet_name, df in sheets.items():
        if len(df) > 0:
            main_df = df
            print(f"\n[转换] 使用Sheet: {sheet_name}")
            break
    
    if main_df is None:
        raise ValueError("未找到有效的数据Sheet")
    
    # 检测列名模式
    columns = main_df.columns.tolist()
    print(f"[转换] 列名: {columns}")
    
    # 尝试识别意图列和特征词列
    intent_col = None
    l1_col = None
    l2_col = None
    l3_col = None
    category_col = None
    domain_col = None
    
    for col in columns:
        col_str = str(col)
        col_lower = col_str.lower()
        if '意图名称' in col_str:
            intent_col = col
        elif '意图分类' in col_str:
            # 意图分类是意图名称的分类，如"咨询办事业务规则"
            category_col = col
        elif 'l1' in col_lower or '事项词' in col_str:
            l1_col = col
        elif 'l2' in col_lower or '动作词' in col_str or '诉求词' in col_str:
            l2_col = col
        elif 'l3' in col_lower or '场景词' in col_str or '情景词' in col_str:
            l3_col = col
        elif '业务领域' in col_str or col_str.strip() == '领域':
            domain_col = col
    
    # 如果没有找到，尝试通过位置推断
    if intent_col is None and len(columns) >= 1:
        # 假设第一列是意图
        intent_col = columns[0]
    
    print(f"[转换] 识别列映射:")
    print(f"  意图列: {intent_col}")
    print(f"  意图分类列: {category_col}")
    print(f"  领域列: {domain_col}")
    print(f"  L1列: {l1_col}")
    print(f"  L2列: {l2_col}")
    print(f"  L3列: {l3_col}")
    
    # 如果列映射不完整，尝试按列顺序处理
    if l1_col is None and l2_col is None and l3_col is None:
        # 尝试解析每行的数据
        for idx, row in main_df.iterrows():
            intent_name = str(row[intent_col]).strip() if intent_col else f"意图{idx+1}"
            if not intent_name or intent_name == 'nan':
                continue
            
            # 收集该行的所有非空值作为特征词
            all_words = []
            for col in columns:
                if col != intent_col and col != category_col:
                    val = row[col]
                    if pd.notna(val) and str(val).strip():
                        # 可能是逗号分隔的词列表
                        words = str(val).replace('，', ',').split(',')
                        all_words.extend([w.strip() for w in words if w.strip()])
            
            # 平均分配到三层
            n = len(all_words)
            l1_end = n // 3
            l2_end = 2 * n // 3
            
            intent_map[intent_name] = {
                "L1_事项词": all_words[:l1_end] if l1_end > 0 else [],
                "L2_动作词": all_words[l1_end:l2_end] if l2_end > l1_end else [],
                "L3_场景词": all_words[l2_end:] if n > l2_end else []
            }
            
            intent_metadata[intent_name] = {
                "领域": domain,
                "意图分类": str(row[category_col]) if category_col and pd.notna(row[category_col]) else "",
                "描述": ""
            }
    else:
        # 正常处理有明确列映射的情况
        for idx, row in main_df.iterrows():
            intent_name = str(row[intent_col]).strip() if intent_col else f"意图{idx+1}"
            if not intent_name or intent_name == 'nan':
                continue
            
            def parse_words(val):
                if pd.isna(val) or not str(val).strip():
                    return []
                # 支持逗号、顿号、空格分隔，以及竖线分隔
                words_str = str(val).replace('，', ',').replace('、', ',').replace('｜', ',').replace('|', ',')
                return [w.strip() for w in words_str.split(',') if w.strip()]
            
            intent_map[intent_name] = {
                "L1_事项词": parse_words(row[l1_col]) if l1_col else [],
                "L2_动作词": parse_words(row[l2_col]) if l2_col else [],
                "L3_场景词": parse_words(row[l3_col]) if l3_col else []
            }
            
            # 从Excel行数据中提取领域和意图分类（如果有对应列的话）
            row_domain = str(row[domain_col]).strip() if domain_col and pd.notna(row[domain_col]) else domain
            row_category = str(row[category_col]).strip() if category_col and pd.notna(row[category_col]) else ""
            
            intent_metadata[intent_name] = {
                "领域": row_domain,
                "意图分类": row_category,
                "描述": ""
            }
    
    result = {
        "意图映射表": intent_map,
        "意图元数据": intent_metadata,
        "词权重表": {},
        "元信息": {
            "版本": "1.0",
            "提取方式": "Excel导入",
            "转换时间": datetime.now().isoformat(),
            "意图数量": len(intent_map)
        }
    }
    
    return result


def save_result(result: dict, output_dir: Path, base_name: str = "feature_words"):
    """保存结果为JSON和Excel格式"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存JSON
    json_path = output_dir / f"{base_name}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[保存] JSON: {json_path}")
    
    # 保存Excel
    excel_path = output_dir / f"{base_name}.xlsx"
    
    # 转换为表格格式
    rows = []
    intent_map = result.get("意图映射表", {})
    intent_metadata = result.get("意图元数据", {})
    
    for intent_name, layers in intent_map.items():
        meta = intent_metadata.get(intent_name, {})
        rows.append({
            "领域": meta.get("领域", ""),
            "意图分类": meta.get("意图分类", ""),
            "意图名称": intent_name,
            "L1_事项词": ", ".join(layers.get("L1_事项词", [])),
            "L2_动作词": ", ".join(layers.get("L2_动作词", [])),
            "L3_场景词": ", ".join(layers.get("L3_场景词", []))
        })
    
    df = pd.DataFrame(rows)
    df.to_excel(excel_path, index=False)
    print(f"[保存] Excel: {excel_path}")
    
    return json_path, excel_path


def main():
    if len(sys.argv) < 2:
        print("用法: python convert_intent_features.py <输入Excel路径> [输出目录] [领域名称]")
        print("示例: python convert_intent_features.py input.xlsx ./output 失业保险")
        print("\n如果不指定输出目录，将自动使用 result/{领域}/intent_list/{日期}/ 格式")
        sys.exit(1)
    
    input_file = sys.argv[1]
    domain = sys.argv[3] if len(sys.argv) > 3 else "失业保险"
    
    # 确定输出目录
    output_dir_arg = sys.argv[2] if len(sys.argv) > 2 else ""
    if output_dir_arg and output_dir_arg.strip():
        output_dir = Path(output_dir_arg)
    else:
        # 使用标准目录结构: result/{领域}/intent_list/{日期}/
        base_dir = Path(__file__).parent.parent  # entity目录
        date_str = datetime.now().strftime("%Y%m%d")
        output_dir = base_dir / "result" / domain / "intent_list" / date_str
    
    print("="*60)
    print("意图特征词Excel转换工具")
    print("="*60)
    
    # 读取Excel
    sheets = read_excel_with_info(input_file)
    
    # 转换格式
    result = convert_to_feature_words_format(sheets, domain)
    
    # 保存结果
    json_path, excel_path = save_result(result, output_dir)
    
    # 打印摘要
    print("\n" + "="*60)
    print("[完成] 转换摘要:")
    intent_map = result.get("意图映射表", {})
    total_l1 = sum(len(v.get("L1_事项词", [])) for v in intent_map.values())
    total_l2 = sum(len(v.get("L2_动作词", [])) for v in intent_map.values())
    total_l3 = sum(len(v.get("L3_场景词", [])) for v in intent_map.values())
    
    print(f"  意图数量: {len(intent_map)}")
    print(f"  L1_事项词数量: {total_l1}")
    print(f"  L2_动作词数量: {total_l2}")
    print(f"  L3_场景词数量: {total_l3}")
    print(f"  总词数: {total_l1 + total_l2 + total_l3}")
    print(f"\n[输出目录]: {output_dir}")
    print("="*60)


if __name__ == "__main__":
    main()
