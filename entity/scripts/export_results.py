#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结果导出器 - 支持 JSON、Excel、Markdown 格式导出
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def export_json(data: Dict[str, Any], output_path: str) -> str:
    """
    导出为 JSON 格式
    
    Args:
        data: 要导出的数据
        output_path: 输出文件路径
        
    Returns:
        输出文件路径
    """
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return output_path


def export_excel(data: Dict[str, Any], output_path: str) -> str:
    """
    导出为 Excel 格式
    
    Args:
        data: 要导出的数据
        output_path: 输出文件路径
        
    Returns:
        输出文件路径
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("请安装 pandas: pip install pandas openpyxl")
    
    entities = data.get("entities", {})
    
    # 转换为表格格式
    rows = []
    for category, entity_list in entities.items():
        for entity in entity_list:
            rows.append({
                "类别": category,
                "实体名称": entity
            })
    
    df = pd.DataFrame(rows)
    
    # 添加统计信息表
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="实体列表", index=False)
        
        # 统计表
        stats = data.get("statistics", {}).get("by_category", {})
        stats_df = pd.DataFrame([
            {"类别": k, "数量": v} for k, v in stats.items()
        ])
        stats_df.to_excel(writer, sheet_name="统计信息", index=False)
    
    return output_path


def export_markdown(data: Dict[str, Any], output_path: str) -> str:
    """
    导出为 Markdown 格式
    
    Args:
        data: 要导出的数据
        output_path: 输出文件路径
        
    Returns:
        输出文件路径
    """
    lines = []
    
    # 标题
    lines.append("# 法律法规主体实体提取报告\n")
    
    # 基本信息
    lines.append("## 基本信息\n")
    lines.append(f"- **源文件**: {data.get('source_file', '未知')}")
    lines.append(f"- **提取时间**: {data.get('extract_time', '未知')}")
    lines.append(f"- **实体总数**: {data.get('statistics', {}).get('total_entities', 0)}\n")
    
    # 实体列表
    lines.append("## 提取结果\n")
    
    entities = data.get("entities", {})
    for category, entity_list in entities.items():
        if entity_list:
            lines.append(f"### {category}\n")
            for entity in entity_list:
                lines.append(f"- {entity}")
            lines.append("")
    
    # 统计信息
    lines.append("## 统计信息\n")
    lines.append("| 类别 | 数量 |")
    lines.append("|------|------|")
    
    stats = data.get("statistics", {}).get("by_category", {})
    for category, count in stats.items():
        lines.append(f"| {category} | {count} |")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    return output_path


def build_result_data(
    source_file: str,
    entities: Dict[str, list]
) -> Dict[str, Any]:
    """
    构建结果数据结构
    
    Args:
        source_file: 源文件路径
        entities: 提取的实体
        
    Returns:
        完整的结果数据
    """
    # 计算统计信息
    total = sum(len(v) for v in entities.values())
    by_category = {k: len(v) for k, v in entities.items()}
    
    return {
        "source_file": Path(source_file).name,
        "extract_time": datetime.now().isoformat(),
        "entities": entities,
        "statistics": {
            "total_entities": total,
            "by_category": by_category
        }
    }


def export_results(
    source_file: str,
    entities: Dict[str, list],
    output_dir: str,
    formats: list = None
) -> Dict[str, str]:
    """
    导出提取结果
    
    Args:
        source_file: 源文件路径
        entities: 提取的实体
        output_dir: 输出目录
        formats: 输出格式列表 (json/xlsx/md)，默认全部
        
    Returns:
        各格式输出文件路径
    """
    if formats is None:
        formats = ["json", "xlsx", "md"]
    
    # 确保输出目录存在
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 构建数据
    data = build_result_data(source_file, entities)
    
    # 生成基础文件名
    base_name = Path(source_file).stem + "_entities"
    
    outputs = {}
    
    if "json" in formats:
        json_path = output_path / f"{base_name}.json"
        outputs["json"] = export_json(data, str(json_path))
    
    if "xlsx" in formats:
        xlsx_path = output_path / f"{base_name}.xlsx"
        outputs["xlsx"] = export_excel(data, str(xlsx_path))
    
    if "md" in formats:
        md_path = output_path / f"{base_name}.md"
        outputs["md"] = export_markdown(data, str(md_path))
    
    return outputs


if __name__ == "__main__":
    # 测试代码
    test_entities = {
        "自然人": ["公民", "当事人", "法定代理人"],
        "政府机关": ["国务院", "民政部门"],
        "司法机关": ["人民法院"],
        "企业法人": [],
        "社会组织": ["居民委员会"],
        "事业单位": []
    }
    
    outputs = export_results(
        source_file="test.pdf",
        entities=test_entities,
        output_dir="./test_output",
        formats=["json", "md"]  # 跳过 xlsx 以避免依赖问题
    )
    
    print("导出完成:")
    for fmt, path in outputs.items():
        print(f"  {fmt}: {path}")
