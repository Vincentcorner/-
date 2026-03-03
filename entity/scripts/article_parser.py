#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
条款解析器 - 将法律法规文档按条款拆分
"""

import re
from typing import Dict, List, Tuple


def parse_articles(text: str) -> List[Dict]:
    """
    将法律法规文本按条款拆分
    
    Args:
        text: 法律法规全文
        
    Returns:
        条款列表，每个条款包含编号和内容
    """
    articles = []
    
    # 匹配 "第X条" 模式
    pattern = r'第([一二三四五六七八九十百零〇\d]+)条\s*'
    
    # 找到所有条款位置
    matches = list(re.finditer(pattern, text))
    
    for i, match in enumerate(matches):
        article_num = match.group(1)
        start = match.end()
        
        # 确定条款结束位置
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(text)
        
        content = text[start:end].strip()
        
        # 清理内容中的换行和多余空格
        content = re.sub(r'\s+', ' ', content)
        
        articles.append({
            "article_id": f"第{article_num}条",
            "article_num": article_num,
            "content": content
        })
    
    return articles


def find_entity_in_articles(
    articles: List[Dict], 
    entity: str
) -> List[str]:
    """
    查找实体出现在哪些条款中
    
    Args:
        articles: 条款列表
        entity: 要查找的实体
        
    Returns:
        包含该实体的条款编号列表
    """
    result = []
    for article in articles:
        if entity in article["content"]:
            result.append(article["article_id"])
    return result


def find_entity_pair_in_articles(
    articles: List[Dict],
    entity1: str,
    entity2: str
) -> List[str]:
    """
    查找两个实体同时出现的条款
    
    Args:
        articles: 条款列表
        entity1: 主体实体
        entity2: 关联实体
        
    Returns:
        两个实体同时出现的条款编号列表
    """
    result = []
    for article in articles:
        content = article["content"]
        if entity1 in content and entity2 in content:
            result.append(article["article_id"])
    return result


def extract_context(
    articles: List[Dict],
    entity1: str,
    entity2: str,
    max_length: int = 100
) -> str:
    """
    提取两个实体共同出现的上下文
    
    Args:
        articles: 条款列表
        entity1: 主体实体
        entity2: 关联实体
        max_length: 上下文最大长度
        
    Returns:
        上下文文本
    """
    for article in articles:
        content = article["content"]
        if entity1 in content and entity2 in content:
            # 找到两个实体之间的文本
            pos1 = content.find(entity1)
            pos2 = content.find(entity2)
            
            start = min(pos1, pos2)
            end = max(pos1 + len(entity1), pos2 + len(entity2))
            
            # 扩展一些上下文
            start = max(0, start - 20)
            end = min(len(content), end + 20)
            
            context = content[start:end]
            if len(context) > max_length:
                context = context[:max_length] + "..."
            
            return context
    
    return ""


def count_entity_frequency(text: str, entity: str) -> int:
    """
    统计实体在文本中出现的次数
    
    Args:
        text: 文本内容
        entity: 实体名称
        
    Returns:
        出现次数
    """
    return text.count(entity)


if __name__ == "__main__":
    # 测试代码
    test_text = """
    第一条 为了保障失业人员的基本生活，预防失业，促进就业，根据《中华人民共和国社会保险法》等有关法律、行政法规，结合本省实际，制定本条例。
    第二条 本省行政区域内下列单位和人员应当参加失业保险：企业、事业单位及其职工。
    第三条 省人民政府统筹全省失业保险工作，社会保险行政部门主管失业保险工作。
    """
    
    articles = parse_articles(test_text)
    
    print("解析结果:")
    for article in articles:
        print(f"\n{article['article_id']}:")
        print(f"  {article['content'][:50]}...")
    
    print("\n查找 '失业人员' 出现的条款:")
    print(find_entity_in_articles(articles, "失业人员"))
