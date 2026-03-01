#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成实体分析 Excel 报告
- 总结 Sheet + 7种类型 Sheet（人、企业、机构、服务、费用、保险、其他）
- 每个类型 Sheet 内按词频排序
- 每个条款单独成行
- 包含关系总结
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd


# 新的实体分类映射
CATEGORY_MAPPING = {
    # 人
    "自然人": "人",
    
    # 企业
    "企业法人": "企业",
    
    # 机构
    "政府机关": "机构",
    "事业单位": "机构",
    "社会组织": "机构",
    "司法机关": "机构",
    
    # 服务
    "权利动作": "服务",
    "义务动作": "服务",
    "管理动作": "服务",
    "处罚动作": "服务",
    
    # 费用
    "资金类": "费用",
    
    # 保险
    "制度类": "保险",
    
    # 其他
    "证件类": "其他",
    "时限类": "其他",
}

# 7种类型
CATEGORY_TYPES = ["人", "企业", "机构", "服务", "费用", "保险", "其他"]


def get_simple_category(original_category: str) -> str:
    """将原始分类映射到简化分类"""
    return CATEGORY_MAPPING.get(original_category, "其他")


def load_relation_summaries(summaries_path: str) -> dict:
    """
    加载关系总结数据
    支持 v1.0 格式: {entity, related, article, summary}
    支持 v2.0 格式: {article, topic, entities: [{name, role, relevance, summary}]}
    返回 {(entity, article): {summary, role, relevance}} 的映射
    """
    if not Path(summaries_path).exists():
        return {}
    
    with open(summaries_path, "r", encoding="utf-8") as f:
        items = json.load(f)
    
    summaries = {}
    
    for item in items:
        # v2.0 格式: 按条款组织，包含实体列表
        if "entities" in item and isinstance(item["entities"], list):
            article = item.get("article", "")
            topic = item.get("topic", "")
            for entity_info in item["entities"]:
                name = entity_info.get("name", "")
                key = (name, article)
                summaries[key] = {
                    "summary": entity_info.get("summary", topic),
                    "role": entity_info.get("role", ""),
                    "relevance": entity_info.get("relevance", ""),
                    "topic": topic
                }
        # v1.0 格式: 旧的 entity-related-article 格式
        elif "entity" in item and "related" in item:
            key = (item["entity"], item.get("article", ""))
            summaries[key] = {
                "summary": item.get("summary", ""),
                "role": "",
                "relevance": ""
            }
    
    return summaries


def generate_excel_report(data_path: str, output_path: str, summaries_path: str = None):
    """
    生成 Excel 报告
    - 总结 Sheet + 7种类型 Sheet
    - 每个条款单独成行
    - 包含关系总结
    """
    # 读取分析数据
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    entities = data.get("entities_analysis", [])
    articles_content = data.get("articles_content", {})  # 条款编号 -> 条款内容
    
    # 加载关系总结
    if summaries_path is None:
        summaries_path = str(Path(data_path).parent / "relation_summaries.json")
    relation_summaries = load_relation_summaries(summaries_path)
    print(f"加载关系总结: {len(relation_summaries)} 条")
    
    # 为每个实体添加简化分类
    for entity in entities:
        entity["simple_category"] = get_simple_category(entity["category"])
    
    # 按词频降序排序
    entities.sort(key=lambda x: x["frequency"], reverse=True)
    
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        
        # ========== Sheet 1: 总结 ==========
        summary_rows = []
        for entity in entities:
            summary_rows.append({
                "对象": entity["entity"],
                "词频": entity["frequency"],
                "类型": entity["simple_category"]
            })
        
        summary_df = pd.DataFrame(summary_rows)
        summary_df.to_excel(writer, sheet_name="总结", index=False)
        
        ws = writer.sheets["总结"]
        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 10
        ws.column_dimensions['C'].width = 12
        
        # ========== 按7种类型生成 Sheet ==========
        for cat_type in CATEGORY_TYPES:
            # 筛选该类型的实体
            type_entities = [e for e in entities if e["simple_category"] == cat_type]
            
            if not type_entities:
                continue
            
            # 构建该类型的数据行 - 每个条款单独成行
            rows = []
            for entity in type_entities:
                entity_name = entity["entity"]
                relations = entity.get("relations", [])
                
                if relations:
                    for rel in relations:
                        common_articles = rel.get("common_articles", [])
                        related_entity = rel["related_entity"]
                        related_cat = get_simple_category(rel.get("related_category", ""))
                        
                            # 每个条款单独成行
                        for article_id in common_articles:
                            content = articles_content.get(article_id, "")
                            # 移除截断，显示完整内容
                            # content_preview = content[:150] + "..." if len(content) > 150 else content
                            
                            # 获取关系总结 - 支持 v2.0 和 v1.0 格式
                            summary_info = relation_summaries.get((entity_name, article_id), {})
                            if isinstance(summary_info, dict):
                                relation_summary = summary_info.get("summary", "")
                                entity_role = summary_info.get("role", "")
                                relevance = summary_info.get("relevance", "")
                            else:
                                # 旧格式兼容
                                relation_summary = summary_info if isinstance(summary_info, str) else ""
                                entity_role = ""
                                relevance = ""
                            
                            rows.append({
                                "实体": entity_name,
                                "词频": entity["frequency"],
                                "实体角色": entity_role,
                                "关联程度": relevance,
                                "关联实体": related_entity,
                                "关联实体类型": related_cat,
                                "所在条款": article_id,
                                "具体条款内容": content,  # 使用完整内容
                                "关系总结": relation_summary
                            })
                else:
                    # 没有关联实体的也要显示
                    appears_in = entity.get("appears_in", [])
                    for article_id in appears_in:
                        content = articles_content.get(article_id, "")
                        
                        # 获取关系总结 - 支持 v2.0 格式
                        summary_info = relation_summaries.get((entity_name, article_id), {})
                        if isinstance(summary_info, dict):
                            relation_summary = summary_info.get("summary", "")
                            entity_role = summary_info.get("role", "")
                            relevance = summary_info.get("relevance", "")
                        else:
                            relation_summary = ""
                            entity_role = ""
                            relevance = ""
                        
                        rows.append({
                            "实体": entity_name,
                            "词频": entity["frequency"],
                            "实体角色": entity_role,
                            "关联程度": relevance,
                            "关联实体": "-",
                            "关联实体类型": "-",
                            "所在条款": article_id,
                            "具体条款内容": content,
                            "关系总结": relation_summary
                        })
            
            if rows:
                df = pd.DataFrame(rows)
                df.to_excel(writer, sheet_name=cat_type, index=False)
                
                ws = writer.sheets[cat_type]
                ws.column_dimensions['A'].width = 20   # 实体
                ws.column_dimensions['B'].width = 8    # 词频
                ws.column_dimensions['C'].width = 20   # 关联实体
                ws.column_dimensions['D'].width = 12   # 关联实体类型
                ws.column_dimensions['E'].width = 12   # 所在条款
                ws.column_dimensions['F'].width = 80   # 具体条款内容
                ws.column_dimensions['G'].width = 50   # 关系总结
                
                # 统计有关系总结的行数
                summary_count = sum(1 for r in rows if r["关系总结"])
                print(f"  {cat_type} Sheet: {len(rows)} 行, 关系总结 {summary_count} 条")
    
    print(f"\nExcel 报告已生成: {output_path}")
    print(f"总实体数: {len(entities)}")
    print(f"Sheet 数量: {1 + len([t for t in CATEGORY_TYPES if any(e['simple_category'] == t for e in entities)])}")


def main():
    import sys
    
    # 用法: python generate_excel.py [数据目录或文件]
    # 示例: python generate_excel.py result/广东省失业保险条例
    
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        
        # 如果输入的是目录
        if input_path.is_dir():
            data_path = input_path / "analysis_data.json"
            regulation_name = input_path.name
            output_dir = input_path
        # 如果输入的是文件
        elif input_path.is_file():
            data_path = input_path
            output_dir = input_path.parent
            regulation_name = output_dir.name
        else:
            print(f"错误: 路径不存在: {input_path}")
            return
    else:
        # 默认路径（向后兼容）
        data_path = Path("result/analysis_data.json")
        output_dir = Path("result")
        regulation_name = "实体分析"
    
    if not data_path.exists():
        print(f"错误: 数据文件不存在: {data_path}")
        return
    
    # 输出报告路径（包含法规名称）
    output_path = output_dir / f"{regulation_name}_实体分析报告.xlsx"
    
    # 关系总结文件路径
    summaries_path = output_dir / "relation_summaries.json"
    
    print(f"法规名称: {regulation_name}")
    print(f"数据文件: {data_path}")
    print(f"输出报告: {output_path}")
    
    generate_excel_report(str(data_path), str(output_path), str(summaries_path))


if __name__ == "__main__":
    main()

