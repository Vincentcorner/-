#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强版实体分析器 - 词频统计、条款定位、上下文提取
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Set, Tuple

from article_parser import (
    parse_articles, 
    find_entity_in_articles,
    find_entity_pair_in_articles,
    count_entity_frequency,
    extract_context
)


# ========== 主体类实体 ==========
SUBJECT_ENTITIES = {
    "自然人": [
        "失业人员", "职工", "劳动者", "用人单位职工", "灵活就业人员",
        "申请人", "举报人", "投诉人", "法定代理人", "被申请人",
        "公民", "当事人", "法定代表人", "监护人", "债权人", "债务人"
    ],
    "企业法人": [
        "企业", "用人单位", "律师事务所", "会计师事务所", 
        "公司", "集团", "法人", "营利法人"
    ],
    "政府机关": [
        "国务院", "人民政府", "省人民政府", "市人民政府",
        "社会保险行政部门", "财政部门", "税务部门", "审计机关",
        "公安机关", "民政部门", "发展改革部门", "卫生健康部门",
        "人力资源社会保障部门", "行政机关", "主管部门"
    ],
    "司法机关": [
        "人民法院", "人民检察院", "仲裁机构", "仲裁委员会"
    ],
    "社会组织": [
        "社会团体", "社会服务机构", "基金会", "工会",
        "社会保险监督委员会", "协会", "居民委员会", "村民委员会"
    ],
    "事业单位": [
        "事业单位", "社会保险经办机构", "公共就业服务机构",
        "社会保险费征收机构", "职业培训机构", "职业技能鉴定机构",
        "创业培训定点机构", "学校", "医院", "研究院"
    ]
}

# ========== 客体类实体 ==========
OBJECT_ENTITIES = {
    "资金类": [
        "失业保险金", "失业保险基金", "失业保险费", "医疗补助金",
        "丧葬补助金", "抚恤金", "职业培训补贴", "职业介绍补贴",
        "稳岗补贴", "一次性生活补助", "缴费工资", "社会保险费"
    ],
    "证件类": [
        "身份证明", "终止劳动关系证明", "解除劳动关系证明",
        "就业失业登记凭证", "社会保障卡", "参保凭证", "缴费记录"
    ],
    "制度类": [
        "失业保险制度", "失业保险待遇", "劳动合同", "聘用合同",
        "劳动关系", "失业登记", "社会保险", "基本医疗保险"
    ],
    "时限类": [
        "缴费时间", "领取期限", "失业保险金领取期间",
        "法定劳动年龄", "十二个月", "二十四个月"
    ]
}

# ========== 动作类实体 ==========
ACTION_ENTITIES = {
    "权利动作": [
        "申请", "领取", "享受", "查询", "举报", "投诉", "复议", "诉讼"
    ],
    "义务动作": [
        "缴纳", "参加", "告知", "出具", "登记", "申报", "代扣代缴"
    ],
    "管理动作": [
        "审核", "发放", "征收", "监督", "检查", "管理", "统筹",
        "转移", "接续", "归集", "支付", "拨付"
    ],
    "处罚动作": [
        "处罚", "责令", "追缴", "退还", "没收", "赔偿"
    ]
}

# 合并所有实体类型（用于向后兼容）
ENTITY_CATEGORIES = {**SUBJECT_ENTITIES}


def get_all_entities_flat() -> List[Dict]:
    """获取所有实体的扁平列表，包含类型信息"""
    all_entities = []
    
    # 主体类实体
    for category, entities in SUBJECT_ENTITIES.items():
        for entity in entities:
            all_entities.append({
                "entity": entity,
                "category": category,
                "entity_type": "主体类"
            })
    
    # 客体类实体
    for category, entities in OBJECT_ENTITIES.items():
        for entity in entities:
            all_entities.append({
                "entity": entity,
                "category": category,
                "entity_type": "客体类"
            })
    
    # 动作类实体
    for category, entities in ACTION_ENTITIES.items():
        for entity in entities:
            all_entities.append({
                "entity": entity,
                "category": category,
                "entity_type": "动作类"
            })
    
    return all_entities


def analyze_entities_enhanced(text: str) -> Dict:
    """
    增强版实体分析 - 支持主体类、客体类、动作类实体
    
    Args:
        text: 法律法规全文
        
    Returns:
        包含词频、条款定位的分析结果
    """
    # 解析条款
    articles = parse_articles(text)
    
    # 获取所有实体定义
    all_entity_defs = get_all_entities_flat()
    
    # 识别所有实体及其词频
    entities_with_freq = []
    
    for entity_def in all_entity_defs:
        entity = entity_def["entity"]
        freq = count_entity_frequency(text, entity)
        if freq > 0:
            # 找到实体出现的条款
            article_ids = find_entity_in_articles(articles, entity)
            
            entities_with_freq.append({
                "entity": entity,
                "frequency": freq,
                "category": entity_def["category"],
                "entity_type": entity_def["entity_type"],
                "articles": article_ids
            })
    
    # 按词频降序排序
    entities_with_freq.sort(key=lambda x: x["frequency"], reverse=True)
    
    return {
        "articles": articles,
        "entities": entities_with_freq
    }


def find_entity_relations(
    articles: List[Dict],
    entity1: str,
    entities_list: List[Dict]
) -> List[Dict]:
    """
    查找主体实体与其他实体的关联关系
    
    Args:
        articles: 条款列表
        entity1: 主体实体
        entities_list: 所有实体列表
        
    Returns:
        关联关系列表
    """
    relations = []
    
    for entity_info in entities_list:
        entity2 = entity_info["entity"]
        if entity1 == entity2:
            continue
        
        # 查找两个实体同时出现的条款
        common_articles = find_entity_pair_in_articles(articles, entity1, entity2)
        
        if common_articles:
            # 提取上下文
            context = extract_context(articles, entity1, entity2)
            
            relations.append({
                "related_entity": entity2,
                "related_category": entity_info["category"],
                "common_articles": common_articles,
                "context": context
            })
    
    return relations


def export_analysis_data(
    text: str,
    output_path: str
) -> Dict:
    """
    导出分析数据供 Agent 使用
    
    Args:
        text: 法律法规全文
        output_path: 输出文件路径
        
    Returns:
        分析结果数据
    """
    # 分析实体
    analysis = analyze_entities_enhanced(text)
    articles = analysis["articles"]
    entities = analysis["entities"]
    
    # 构建条款内容映射（条款编号 -> 条款内容）
    articles_content = {}
    for article in articles:
        articles_content[article["article_id"]] = article["content"]
    
    # 为每个实体找关联关系
    result = {
        "total_articles": len(articles),
        "total_entities": len(entities),
        "articles_content": articles_content,
        "entities_analysis": []
    }
    
    for entity_info in entities:
        entity = entity_info["entity"]
        
        # 查找关联实体
        relations = find_entity_relations(articles, entity, entities)
        
        # 只保留前5个最相关的关联实体
        relations = relations[:5]
        
        result["entities_analysis"].append({
            "entity": entity,
            "frequency": entity_info["frequency"],
            "category": entity_info["category"],
            "appears_in": entity_info["articles"],
            "relations": relations
        })
    
    # 保存结果
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    return result


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    
    from parse_document import parse_document
    
    # 用法: python entity_analyzer.py <文件路径> [输出目录]
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        
        # 从文件名提取法规名称
        regulation_name = Path(file_path).stem
        
        # 确定输出目录（默认按法规名称创建子目录）
        if len(sys.argv) > 2:
            output_dir = Path(sys.argv[2])
        else:
            output_dir = Path("result") / regulation_name
        
        # 创建输出目录
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 解析文档
        text = parse_document(file_path)
        
        # 导出分析数据
        output_path = output_dir / "analysis_data.json"
        result = export_analysis_data(text, str(output_path))
        
        print(f"分析完成！")
        print(f"法规名称: {regulation_name}")
        print(f"条款数: {result['total_articles']}")
        print(f"实体数: {result['total_entities']}")
        print(f"结果保存至: {output_path}")
    else:
        print("用法: python entity_analyzer.py <文件路径> [输出目录]")
        print("示例: python entity_analyzer.py originalfile/广东省失业保险条例.pdf")
        print("      输出将保存到: result/广东省失业保险条例/")

