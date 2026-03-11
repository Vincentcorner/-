# -*- coding: utf-8 -*-
"""
功能模块

提供特征词提取、公式权重计算、诉求转写、分词匹配、权重计算、意图筛选等功能
"""

from .feature_extractor import FeatureExtractor
from .query_segmenter import QuerySegmenter
from .weight_calculator import WeightCalculator

# 以下模块可能仅有 .pyc，用 try-except 保护
try:
    from .query_rewriter import QueryRewriter
except ImportError:
    QueryRewriter = None

try:
    from .intent_selector import IntentSelector
except ImportError:
    IntentSelector = None

__all__ = [
    'FeatureExtractor',
    'QueryRewriter',
    'QuerySegmenter',
    'WeightCalculator',
    'IntentSelector'
]
