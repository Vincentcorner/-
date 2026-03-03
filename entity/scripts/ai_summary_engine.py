#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent 驱动的实体关系总结引擎 (本地模拟版)
模拟 Agent 的分析逻辑，通过深度模式匹配实现业务化总结。
"""

import json
import re
import sys
from pathlib import Path

def smart_summarize(entity, related, article, content):
    """
    基于 Agent 分析逻辑的智能总结函数
    """
    summary = ""
    # 预处理内容，移除无关字符
    clean_content = re.sub(r'\s+', '', content)
    
    # === 1. 失业保险金 - 资金流向 ===
    if "失业保险基金" in [entity, related] and "用于下列支出" in content:
        items = []
        if "失业保险金" in content: items.append("失业保险金")
        if "医疗补助金" in content: items.append("医疗补助")
        if "丧葬" in content: items.append("丧葬抚恤")
        return f"失业保险基金用于支付{'、'.join(items[:2])}等待遇"

    # === 2. 领取条件 ===
    if "条件" in content and "领取" in content and ("具备" in content or "符合" in content):
        if "缴费" in content and "1年" in content:
            return f"{entity}申领失业保险金需满足缴费满一年等条件"
        return f"{entity}需满足特定条件方可领取失业保险金"

    # === 3. 停止领取 ===
    if "停止领取" in content and ("重新就业" in content or "兵役" in content):
        return f"{entity}出现重新就业等情形时应停止领取待遇"

    # === 4. 领取期限 ===
    if "期限" in content and "缴费时间" in content and "最长" in content:
        return f"{entity}领取期限根据累计缴费年限确定，最长24个月"

    # === 5. 单位义务 ===
    if "出具" in content and ("终止" in content or "解除" in content) and "证明" in content:
        # 修正：明确主体是“城镇企业事业单位”
        if "企业" in entity or "单位" in entity:
             return f"{entity}需为职工出具解除劳动关系证明并办理备案"
        elif "失业人员" in entity or "职工" in entity:
             return "所在单位需为该人员出具解除劳动关系证明并办理备案"

    # === 6. 经办机构职责 ===
    if "社会保险经办机构" in [entity, related] and ("职责" in content or "负责" in content):
        duties = []
        if "登记" in content: duties.append("登记")
        if "核定" in content: duties.append("核定待遇")
        if "发放" in content: duties.append("发放")
        return f"社保经办机构负责失业人员的{'、'.join(duties)}等管理工作"

    # === 7. 死亡待遇 ===
    if "死亡" in content and ("丧葬" in content or "抚恤" in content):
        return f"{entity}领取期间死亡可享受丧葬补助金和抚恤金"

    # === 8. 患病医疗 ===
    if "患病" in content or "就医" in content:
        if "医疗补助金" in content:
            return f"{entity}领取期间患病可申请医疗补助金"

    # === 9. 农民合同制工人 ===
    if "农民合同制工人" in [entity, related] and "一次性" in content:
        return "农民合同制工人失业后可领取一次性生活补助"

    # === 10. 法律责任 ===
    if "骗取" in content or "虚构" in content:
        if "责令退还" in content:
            return f"{entity}骗取待遇将被责令退还并处罚"
        if "追究刑事责任" in content:
            return f"{entity}违规行为构成犯罪的将依法追究刑责"

    # === 11. 缴费 ===
    if "缴纳" in content and "费率" in content:
        return f"{entity}按规定费率缴纳失业保险费"
    
    # === 12. 转移 ===
    if "转移" in content and "跨" in content:
        return f"{entity}跨统筹地区流动时失业保险关系随之转移"

    # === 通用兜底策略 (优化版) ===
    # 尝试提取主谓宾结构
    # 提取第一句
    first_sentence = re.split(r'[。；]', content)[0]
    if len(first_sentence) < 25:
        return first_sentence
    
    return f"{entity}与{related}在该条款中存在业务关联"

def main():
    if len(sys.argv) < 2:
        print("Usage: python ai_summary_engine.py <result_dir>")
        return

    result_dir = Path(sys.argv[1])
    items_path = result_dir / "relation_items.json"
    
    if not items_path.exists():
        print(f"File not found: {items_path}")
        return

    print(f"处理文件: {items_path}")
    
    with open(items_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    count = 0
    for item in items:
        new_summary = smart_summarize(
            item["entity"], 
            item["related"], 
            item["article"], 
            item["content"]
        )
        if new_summary:
            item["summary"] = new_summary
            count += 1

    summaries_path = result_dir / "relation_summaries.json"
    with open(summaries_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print(f"已更新 {count} 条总结")
    print(f"保存至: {summaries_path}")

if __name__ == "__main__":
    main()
