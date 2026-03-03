#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实体提取器 - 结合 LLM 和词频统计提取主体实体
"""

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set


# 主体类型定义
ENTITY_CATEGORIES = {
    "自然人": [
        "公民", "当事人", "法定代理人", "监护人", "被告", "原告", "债权人", "债务人",
        "法定代表人", "受托人", "委托人", "继承人", "遗嘱人", "收养人", "被收养人",
        "甲方", "乙方", "丙方", "第三人", "申请人", "被申请人", "劳动者", "用人单位职工"
    ],
    "企业法人": [
        "公司", "集团", "企业", "法人", "营利法人", "非营利法人", "有限责任公司",
        "股份有限公司", "合伙企业", "个体工商户", "个人独资企业"
    ],
    "政府机关": [
        "国务院", "人民政府", "发展和改革委员会", "财政部", "商务部", "工业和信息化部",
        "自然资源部", "生态环境部", "住房和城乡建设部", "交通运输部", "水利部",
        "农业农村部", "卫生健康委员会", "市场监督管理局", "行政机关", "主管部门",
        "登记机关", "审批机关", "税务机关", "公安机关", "民政部门"
    ],
    "司法机关": [
        "人民法院", "最高人民法院", "高级人民法院", "中级人民法院", "基层人民法院",
        "人民检察院", "最高人民检察院", "仲裁机构", "仲裁委员会"
    ],
    "社会组织": [
        "协会", "学会", "基金会", "工会", "居民委员会", "村民委员会", "业主委员会",
        "商会", "联合会", "促进会", "研究会"
    ],
    "事业单位": [
        "学校", "医院", "研究院", "研究所", "图书馆", "博物馆", "档案馆",
        "大学", "学院", "中学", "小学", "幼儿园"
    ]
}

# 构建实体关键词集合（用于快速匹配）
ENTITY_KEYWORDS = set()
for entities in ENTITY_CATEGORIES.values():
    ENTITY_KEYWORDS.update(entities)


def extract_by_rules(text: str) -> Dict[str, Set[str]]:
    """
    基于规则和词频统计提取实体
    
    Args:
        text: 待提取的文本
        
    Returns:
        按类别分组的实体集合
    """
    try:
        import jieba
    except ImportError:
        raise ImportError("请安装 jieba: pip install jieba")
    
    results = {category: set() for category in ENTITY_CATEGORIES}
    
    # 使用 jieba 分词
    words = list(jieba.cut(text))
    
    # 统计词频
    word_freq = Counter(words)
    
    # 匹配预定义关键词
    for category, keywords in ENTITY_CATEGORIES.items():
        for keyword in keywords:
            if keyword in text:
                results[category].add(keyword)
    
    # 使用正则提取机构名称模式
    patterns = [
        # 政府机关模式
        (r'[省市县区][^\s，。；]{2,10}(?:局|厅|委|办|处|院|部)', "政府机关"),
        (r'国家[^\s，。；]{2,15}(?:局|委|部|总局)', "政府机关"),
        # 企业法人模式
        (r'[^\s，。；]{2,20}(?:有限公司|股份有限公司|集团公司|合伙企业)', "企业法人"),
        # 社会组织模式
        (r'[^\s，。；]{2,15}(?:协会|学会|基金会|促进会|联合会)', "社会组织"),
        # 事业单位模式
        (r'[^\s，。；]{2,15}(?:大学|学院|医院|研究院|研究所)', "事业单位"),
    ]
    
    for pattern, category in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if len(match) >= 3:  # 过滤过短的匹配
                results[category].add(match)
    
    return results


def extract_by_llm(text: str, api_key: Optional[str] = None) -> Dict[str, List[str]]:
    """
    使用 LLM 提取实体
    
    Args:
        text: 待提取的文本
        api_key: API Key（可选，默认从环境变量读取）
        
    Returns:
        按类别分组的实体列表
    """
    api_key = api_key or os.environ.get("DASHSCOPE_API_KEY")
    
    if not api_key:
        print("警告: 未设置 DASHSCOPE_API_KEY，跳过 LLM 提取")
        return {}
    
    try:
        import dashscope
        from dashscope import Generation
    except ImportError:
        print("警告: 未安装 dashscope，跳过 LLM 提取")
        return {}
    
    dashscope.api_key = api_key
    
    # 读取提示词模板
    prompt_path = Path(__file__).parent.parent / ".agent/skills/entity-extraction/prompts/extract_prompt.md"
    
    if prompt_path.exists():
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()
    else:
        # 使用内置提示词
        prompt_template = """请从以下法律法规文本中提取所有主体类实体，包括自然人、企业法人、政府机关、司法机关、社会组织、事业单位。
        
请以 JSON 格式输出：
{
  "自然人": [],
  "企业法人": [],
  "政府机关": [],
  "司法机关": [],
  "社会组织": [],
  "事业单位": []
}

文本内容：
{text}

请直接输出 JSON，不要包含其他说明。"""
    
    # 文本过长时截断
    max_length = 6000
    if len(text) > max_length:
        text = text[:max_length] + "..."
    
    prompt = prompt_template.replace("{text}", text)
    
    try:
        response = Generation.call(
            model="qwen-turbo",
            prompt=prompt,
            result_format="message"
        )
        
        if response.status_code == 200:
            content = response.output.choices[0].message.content
            # 提取 JSON 部分
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                return json.loads(json_match.group())
    except Exception as e:
        print(f"LLM 提取失败: {e}")
    
    return {}


def merge_results(
    rule_results: Dict[str, Set[str]], 
    llm_results: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    """
    合并规则提取和 LLM 提取的结果
    
    Args:
        rule_results: 规则提取结果
        llm_results: LLM 提取结果
        
    Returns:
        合并后的结果
    """
    merged = {}
    
    all_categories = set(rule_results.keys()) | set(llm_results.keys())
    
    for category in all_categories:
        entities = set()
        
        # 添加规则提取结果
        if category in rule_results:
            entities.update(rule_results[category])
        
        # 添加 LLM 提取结果
        if category in llm_results:
            entities.update(llm_results[category])
        
        # 转换为排序列表
        merged[category] = sorted(list(entities))
    
    return merged


def extract_entities(
    text: str, 
    use_llm: bool = True,
    api_key: Optional[str] = None
) -> Dict[str, List[str]]:
    """
    提取主体实体的主函数
    
    Args:
        text: 待提取的文本
        use_llm: 是否使用 LLM
        api_key: LLM API Key
        
    Returns:
        按类别分组的实体列表
    """
    # 规则提取
    rule_results = extract_by_rules(text)
    
    # LLM 提取
    llm_results = {}
    if use_llm:
        llm_results = extract_by_llm(text, api_key)
    
    # 合并结果
    return merge_results(rule_results, llm_results)


if __name__ == "__main__":
    # 测试代码
    test_text = """
    根据《中华人民共和国民法典》规定，自然人从出生时起到死亡时止，具有民事权利能力。
    公民依法享有民事权利，承担民事义务。法人是具有民事权利能力和民事行为能力的组织。
    国务院和地方各级人民政府是国家行政机关。人民法院依法独立行使审判权。
    居民委员会、村民委员会是基层群众性自治组织。
    中国证券监督管理委员会负责证券市场的监督管理工作。
    """
    
    results = extract_entities(test_text, use_llm=False)
    
    print("提取结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))
