#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成关系总结数据
基于条款内容，为每个实体-关联实体对生成业务关系总结

v2.0 (2026-01-19): 增加智能总结生成策略
- 优先使用法规专用映射
- 基于内容关键词智能提取
- 最后使用条款核心描述
"""

import json
import re
from pathlib import Path


def extract_article_core(content: str) -> str:
    """从条款内容中提取核心描述（第一个完整句子）"""
    if not content:
        return ""
    
    # 移除噪声文本
    content = re.sub(r'\d{4}年第\d+期刊登.*?电子公报发布', '', content)
    content = re.sub(r'第[一二三四五六七八九十]+章\s+\S+', '', content)
    
    # 提取第一个句子（到第一个句号、分号或条件列举）
    match = re.match(r'^[^。；:：]+[。；]?', content.strip())
    if match:
        core = match.group(0).strip()
        # 截断过长的句子
        if len(core) > 60:
            core = core[:57] + "..."
        return core
    
    return content[:60] + "..." if len(content) > 60 else content


def generate_smart_summary(entity: str, related: str, article: str, content: str) -> str:
    """
    智能生成关系总结
    优先级: 1.实体-角色分析 -> 2.关键词提取 -> 3.条款核心描述
    """
    if not content:
        return f"在{article}中，{entity}与{related}存在关联"
    
    content_text = content[:300]
    
    # === 1. 基于实体角色的分析 ===
    
    # 灵活就业人员相关
    if "灵活就业人员" in entity:
        if "参加" in related:
            if "自愿" in content_text:
                return "灵活就业人员参加失业保险遵循自愿原则"
            elif "缴费基数" in content_text or "申报" in content_text:
                return "灵活就业人员按规定申报失业保险缴费基数"
            elif "缴费时间" in content_text or "累积" in content_text:
                return "灵活就业人员参保缴费时间可累积计算"
            elif "条件" in content_text and "领取" in content_text:
                return "参保的灵活就业人员符合条件可领取失业保险金"
            elif "待遇" in content_text:
                return "参保的灵活就业人员可享受失业保险待遇"
            elif "停保" in content_text:
                return "灵活就业人员停止参保需办理停保手续"
            elif "转移" in content_text:
                return "灵活就业人员失业保险关系可跨区域转移"
            elif "监督" in content_text or "政策" in content_text:
                return "人社部门负责灵活就业人员参保政策制定和监督"
            elif "补贴" in content_text:
                return "享受失业待遇期间不得同时享受社保补贴"
            elif "承诺" in content_text:
                return "灵活就业人员需每月承诺不存在停发待遇情形"
            elif "真实性" in content_text or "法律责任" in content_text:
                return "灵活就业人员需对申报材料真实性负责"
            elif "评估" in content_text or "施行" in content_text:
                return "参保的灵活就业人员实行专项统计和评估管理"
            else:
                return "灵活就业人员可依规参加失业保险"
        elif "登记" in related:
            if "就业登记" in content_text:
                return "灵活就业人员参保需办理就业登记"
            elif "失业登记" in content_text:
                return "灵活就业人员失业后需办理失业登记"
            elif "实名制" in content_text:
                return "税务机关对灵活就业人员进行实名制登记"
            else:
                return "灵活就业人员参保需办理相关登记手续"
        elif "社会保险" in related:
            if "经办机构" in content_text:
                return "灵活就业人员可到社保经办机构办理业务"
            elif "补贴" in content_text:
                return "享受失业待遇期间不得同时享受社保补贴"
            elif "承诺" in content_text:
                return "灵活就业人员需向社保机构承诺无停发情形"
            elif "欺诈" in content_text or "骗取" in content_text:
                return "骗取待遇者按社保法规处理并纳入失信名单"
            else:
                return "灵活就业人员纳入社会保险制度保障"
        elif "失业保险待遇" in related:
            if "条件" in content_text:
                return "符合条件的灵活就业人员可享受失业保险待遇"
            elif "申领" in content_text:
                return "灵活就业人员可通过多渠道申领失业保险待遇"
            elif "期限" in content_text:
                return "灵活就业人员待遇期限按条例规定计算"
            elif "停止" in content_text or "停发" in content_text:
                return "出现规定情形应停止领取失业保险待遇"
            elif "骗取" in content_text:
                return "骗取失业保险待遇将依法处理"
            else:
                return "灵活就业人员失业后可享受失业保险待遇"
        elif "申请" in related:
            if "停保" in content_text:
                return "灵活就业人员申请办理停保手续向税务机关提出"
            else:
                return "灵活就业人员可申请参加失业保险"
    
    # 失业人员相关
    if "失业人员" in entity:
        if "领取" in related:
            if "条件" in content_text:
                return "失业人员须符合条件方可领取失业保险金"
            elif "期限" in content_text:
                return "失业人员按缴费年限确定领取期限"
            else:
                return "失业人员依规领取失业保险金"
        elif "失业保险金" in related:
            return "失业人员符合条件可领取失业保险金"
    
    # 用人单位相关
    if "用人单位" in entity:
        if "职工" in related:
            return "用人单位应为职工办理失业保险参保"
        elif "缴" in related or "费" in related:
            return "用人单位按规定缴纳失业保险费"
    
    # 社保经办机构相关
    if "社会保险经办机构" in entity or "经办机构" in entity:
        if "审核" in content_text:
            return f"社保经办机构负责{related}审核工作"
        elif "支付" in content_text or "发放" in content_text:
            return f"社保经办机构负责{related}支付发放"
        else:
            return f"社保经办机构提供{related}经办服务"
    
    # 税务机关相关
    if "税务机关" in entity:
        if "缴费" in content_text:
            return f"税务机关负责{related}缴费手续办理"
        elif "登记" in content_text:
            return f"税务机关对{related}进行实名制登记"
        elif "共享" in content_text:
            return f"税务机关向社保机构共享{related}参保信息"
        else:
            return f"税务机关负责{related}相关征缴工作"
    
    # 平台相关
    if "平台" in entity or "平台" in related:
        if "补助" in content_text:
            return "鼓励新业态平台对从业人员缴费予以补助"
        elif "暂停" in content_text:
            return "被平台暂停服务资格可作为失业原因"
        elif "核实" in content_text:
            return "社保经办机构通过向平台核实审核材料"
        elif "吊销" in content_text or "关闭" in content_text:
            return "平台被吊销关闭是法定失业原因之一"
    
    # 失业保险金相关
    if "失业保险金" in entity:
        if "领取" in related or "领取" in content_text:
            if "条件" in content_text:
                return "失业保险金须满足条件方可领取"
            elif "停止" in content_text:
                return "出现规定情形应停止领取失业保险金"
            else:
                return "失业保险金是失业保险的核心待遇"
    
    # 失业保险费相关
    if "失业保险费" in entity:
        if "缴纳" in related:
            return "失业保险费按规定缴纳"
        elif "补缴" in content_text:
            return "灵活就业人员失业保险费不实施补缴"
        elif "退费" in content_text:
            return "已缴纳的失业保险费不退费"
    
    # === 2. 基于关键词的智能提取 ===
    
    if "缴费基数" in content_text:
        return f"{entity}按规定申报失业保险缴费基数"
    if "领取条件" in content_text or ("条件" in content_text and "领取" in content_text):
        return f"{entity}须符合条件方可领取待遇"
    if "停止领取" in content_text:
        return f"{entity}出现规定情形应停止领取待遇"
    if "办理登记" in content_text or "就业登记" in content_text:
        return f"{entity}需办理就业或失业登记"
    if "监督检查" in content_text:
        return f"相关部门对{entity}进行监督检查"
    if "欺诈" in content_text or "骗取" in content_text:
        return f"{entity}骗取待遇将依法处理"
    
    # === 3. 回退到条款核心描述 ===
    core = extract_article_core(content)
    if core:
        return core
    
    return f"在{article}中，{entity}与{related}存在业务关联"


def main():
    import sys
    
    # 用法: python generate_summaries.py [法规目录]
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        if input_path.is_dir():
            data_dir = input_path
        elif input_path.is_file():
            data_dir = input_path.parent
        else:
            print(f"错误: 路径不存在: {input_path}")
            return
    else:
        data_dir = Path("result")
    
    # 检查分析数据文件
    analysis_path = data_dir / "analysis_data.json"
    if not analysis_path.exists():
        print(f"错误: 分析数据不存在: {analysis_path}")
        return
    
    # 读取分析数据
    with open(analysis_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    entities = data.get("entities_analysis", [])
    articles = data.get("articles_content", {})
    
    # 生成关系项目列表
    items = []
    for e in entities:
        for rel in e.get("relations", []):
            for art_id in rel.get("common_articles", []):
                items.append({
                    "entity": e["entity"],
                    "entity_cat": e["category"],
                    "related": rel["related_entity"],
                    "related_cat": rel["related_category"],
                    "article": art_id,
                    "content": articles.get(art_id, "")
                })
    
    print(f"法规目录: {data_dir}")
    print(f"共 {len(items)} 条关系记录")
    
    # 为每条记录生成关系总结
    for item in items:
        summary = generate_smart_summary(
            item["entity"],
            item["related"],
            item["article"],
            item["content"]
        )
        item["summary"] = summary
    
    # 保存关系项目
    relation_items_path = data_dir / "relation_items.json"
    with open(relation_items_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    
    # 保存关系总结
    summaries_path = data_dir / "relation_summaries.json"
    with open(summaries_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    
    print(f"关系项目已保存: {relation_items_path}")
    print(f"关系总结已保存: {summaries_path}")
    
    # 显示样本
    print("\n=== 样本 ===")
    for item in items[:5]:
        print(f"{item['entity']} - {item['related']} @ {item['article']}")
        print(f"  总结: {item['summary']}")


if __name__ == "__main__":
    main()
