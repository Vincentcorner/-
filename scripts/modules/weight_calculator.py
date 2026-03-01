# -*- coding: utf-8 -*-
"""
模块5：权重计算器

根据切词匹配结果计算意图得分
三层并行匹配，得分 = Σ(层级权重 × 词权重)
"""

import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Union

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.common.file_manager import FileManager
from scripts.common.logger import WrapperLogger
from scripts.common.config import ConfigManager


class WeightCalculator:
    """权重计算器
    
    计算算法：
    1. 三层并行匹配
    2. 得分 = Σ(层级权重 × 词权重)
    3. 筛选得分 >= 阈值的意图
    4. 返回所有超过阈值的意图（最多max_results个）
    """
    
    # 最大返回意图数量
    MAX_RESULTS = 10
    
    def __init__(self, file_manager: FileManager = None, config: ConfigManager = None):
        """
        初始化权重计算器
        
        Args:
            file_manager: 文件管理器实例
            config: 配置管理器实例
        """
        self.file_manager = file_manager or FileManager()
        self.config = config or ConfigManager()
        
        # 加载配置
        self.layer_weights = self.config.get_layer_weights()
        threshold_config = self.config.get_threshold_config()
        self.threshold = threshold_config.get("min_score", 0.4)
        # 保留top_k用于向后兼容，但默认使用MAX_RESULTS
        self.top_k = threshold_config.get("top_k", self.MAX_RESULTS)
        
        self._logger: Optional[WrapperLogger] = None
    
    def init_logger(self, domain: str):
        """初始化日志记录器"""
        logs_dir = self.file_manager.get_logs_dir(domain)
        self._logger = WrapperLogger(logs_dir, domain)
    
    # 层级名称映射（兼容新旧）
    LAYER_KEY_MAP = {
        'L1': 'L1', 'L2': 'L2', 'L3': 'L3',
        '核心': 'L1', '发散': 'L2', '同义': 'L3',
    }
    
    def _get_layer_key(self, layer: str) -> str:
        """将层级名称统一转为配置键（L1/L2/L3）"""
        prefix = layer[:2] if len(layer) >= 2 else layer
        return self.LAYER_KEY_MAP.get(prefix, 'L3')
    
    def calculate(self, matched_words: List[Dict], domain: str = None,
                  intent_map: Dict = None) -> List[Dict]:
        """
        计算意图匹配得分
        
        公式 F1: 单词得分 = 层级权重 × 词权重(意图级)
        公式 F2: 原始得分(I) = Σ 单词得分
        公式 F3: 归一化得分(I) = 原始得分 / 最大可能得分
        
        Args:
            matched_words: 切词匹配结果列表
            domain: 业务领域
            intent_map: 意图映射表（用于计算归一化，可选）
        """
        intent_scores: Dict[str, float] = defaultdict(float)
        hit_details: Dict[str, List[Dict]] = defaultdict(list)
        
        for match in matched_words:
            word = match["词"]
            intent = match["意图"]
            layer = match["层级"]
            word_weight = match["权重"]
            
            # 获取层级权重（兼容新旧层级名称）
            layer_key = self._get_layer_key(layer)
            layer_weight = self.layer_weights.get(layer_key, 0.6)
            
            # 计算得分 (F1)
            score = layer_weight * word_weight
            
            intent_scores[intent] += score
            hit_details[intent].append({
                "词": word,
                "层级": layer,
                "词权重": word_weight,
                "层级权重": layer_weight,
                "得分": round(score, 4)
            })
        
        # 归一化得分 (F3)：如果提供了 intent_map，计算每个意图的最大可能得分
        max_scores = {}
        if intent_map:
            for iname, layers in intent_map.items():
                max_s = 0
                for lname, words in layers.items():
                    lk = self._get_layer_key(lname)
                    lw = self.layer_weights.get(lk, 0.6)
                    # 每层取最高词权重 × 层级权重 × 词数
                    max_s += lw * len(words) * 1.0  # 假设最高词权重为 1.0
                max_scores[iname] = max(max_s, 0.01)  # 避免除以零
        
        # 筛选超过阈值的意图
        results = []
        for intent, total_score in intent_scores.items():
            # 归一化
            if intent in max_scores:
                norm_score = total_score / max_scores[intent]
            else:
                norm_score = total_score  # 无 intent_map 时不归一化
            
            if norm_score >= self.threshold:
                results.append({
                    "意图": intent,
                    "得分": round(norm_score, 4),
                    "原始得分": round(total_score, 4),
                    "命中词数": len(hit_details[intent]),
                    "命中详情": hit_details[intent]
                })
        
        # 按得分降序排序
        results.sort(key=lambda x: x["得分"], reverse=True)
        
        # 返回所有超过阈值的意图，最多MAX_RESULTS个
        max_results = min(self.top_k, self.MAX_RESULTS) if self.top_k else self.MAX_RESULTS
        top_results = results[:max_results]
        
        # 记录日志
        if domain:
            if self._logger is None:
                self.init_logger(domain)
            
            self._logger.log_step(
                step="权重计算",
                input_data={"匹配词数": len(matched_words)},
                output_data=top_results,
                details={
                    "阈值": self.threshold,
                    "最大返回数": max_results,
                    "总候选意图数": len(results),
                    "超过阈值意图数": len(results)
                }
            )
        
        return top_results
    
    def calculate_with_config(self, matched_words: List[Dict], 
                              layer_weights: Dict[str, float] = None,
                              threshold: float = None,
                              top_k: int = None,
                              domain: str = None) -> List[Dict]:
        """
        使用自定义配置计算意图得分
        
        Args:
            matched_words: 切词匹配结果
            layer_weights: 自定义层级权重
            threshold: 自定义阈值
            top_k: 自定义返回数量
            domain: 业务领域
            
        Returns:
            排序后的意图得分列表
        """
        # 临时覆盖配置
        original_layer_weights = self.layer_weights
        original_threshold = self.threshold
        original_top_k = self.top_k
        
        try:
            if layer_weights:
                self.layer_weights = layer_weights
            if threshold is not None:
                self.threshold = threshold
            if top_k is not None:
                self.top_k = top_k
            
            return self.calculate(matched_words, domain)
        finally:
            # 恢复原始配置
            self.layer_weights = original_layer_weights
            self.threshold = original_threshold
            self.top_k = original_top_k
    
    def save_logger(self):
        """保存日志到文件"""
        if self._logger:
            self._logger.save()
    
    def get_config(self) -> Dict:
        """获取当前配置"""
        return {
            "层级权重": self.layer_weights,
            "最低阈值": self.threshold,
            "Top-K": self.top_k
        }
