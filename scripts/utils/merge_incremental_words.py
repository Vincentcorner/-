# -*- coding: utf-8 -*-
"""
合并增量词表到主词表

将增量词表文件中的新词合并到原始weighted_words.json中
"""

import json
import sys
from datetime import datetime
from pathlib import Path

def merge_incremental_words(original_path: str, incremental_path: str, output_path: str = None):
    """
    合并增量词表到主词表
    
    Args:
        original_path: 原始weighted_words.json路径
        incremental_path: 增量词表路径
        output_path: 输出路径（默认覆盖原文件）
    """
    # 读取原始文件
    with open(original_path, 'r', encoding='utf-8') as f:
        original = json.load(f)
    
    # 读取增量文件
    with open(incremental_path, 'r', encoding='utf-8') as f:
        incremental = json.load(f)
    
    # 合并意图映射表
    intent_mapping = original.get("意图映射表", {})
    incremental_mapping = incremental.get("意图映射表_增量", {})
    
    for intent_name, layers in incremental_mapping.items():
        if intent_name not in intent_mapping:
            # 新意图，创建空结构
            intent_mapping[intent_name] = {
                "L1_事项词": [],
                "L2_动作词": [],
                "L3_场景词": []
            }
        
        # 合并各层级的新词
        for layer_key, new_words in layers.items():
            # 转换增量键名到原始键名
            original_layer_key = layer_key.replace("_新增", "")
            if original_layer_key not in intent_mapping[intent_name]:
                intent_mapping[intent_name][original_layer_key] = []
            
            # 添加新词（去重）
            existing_words = set(intent_mapping[intent_name][original_layer_key])
            for word in new_words:
                if word not in existing_words:
                    intent_mapping[intent_name][original_layer_key].append(word)
                    existing_words.add(word)
    
    original["意图映射表"] = intent_mapping
    
    # 合并词权重表
    weight_table = original.get("词权重表", {})
    incremental_weights = incremental.get("词权重表_增量", {})
    
    added_words = []
    for word, weight_info in incremental_weights.items():
        if word not in weight_table:
            weight_table[word] = weight_info
            added_words.append(word)
    
    original["词权重表"] = weight_table
    
    # 更新元信息
    meta = original.get("元信息", {})
    meta["最后更新时间"] = datetime.now().isoformat()
    meta["增量更新来源"] = str(incremental_path)
    meta["新增词数量"] = len(added_words)
    original["元信息"] = meta
    
    # 保存
    output = output_path or original_path
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(original, f, ensure_ascii=False, indent=2)
    
    print(f"[合并完成] 新增 {len(added_words)} 个词到词权重表")
    print(f"[合并完成] 更新了 {len(incremental_mapping)} 个意图的特征词")
    print(f"[合并完成] 输出文件: {output}")
    
    return added_words


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: py merge_incremental_words.py <原始词表路径> <增量词表路径> [输出路径]")
        sys.exit(1)
    
    original_path = sys.argv[1]
    incremental_path = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else None
    
    merge_incremental_words(original_path, incremental_path, output_path)
