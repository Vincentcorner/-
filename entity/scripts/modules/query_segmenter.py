# -*- coding: utf-8 -*-
"""
模块4：AC自动机分词器

使用 Aho-Corasick 自动机进行本地多模式字符串匹配
不使用AI，结果确定性强，可复现

依赖：pip install pyahocorasick
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

try:
    import ahocorasick
except ImportError:
    ahocorasick = None
    print("警告: pyahocorasick 未安装，请运行 pip install pyahocorasick")

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.common.file_manager import FileManager
from scripts.common.logger import WrapperLogger
from scripts.common.config import ConfigManager


class QuerySegmenter:
    """AC自动机分词器 - 本地多模式匹配
    
    特点：
    1. 一次扫描即可匹配所有模式词
    2. 时间复杂度 O(n + m)，n为文本长度，m为匹配结果数
    3. 无需AI调用，本地高效执行
    4. 结果确定性强，可复现
    """
    
    def __init__(self, file_manager: FileManager = None, config: ConfigManager = None):
        """
        初始化分词器
        
        Args:
            file_manager: 文件管理器实例
            config: 配置管理器实例
        """
        self.file_manager = file_manager or FileManager()
        self.config = config or ConfigManager()
        self.automaton = None
        self.negative_automaton = None
        self._logger: Optional[WrapperLogger] = None
        self._is_built = False
    
    def init_logger(self, domain: str):
        """初始化日志记录器"""
        logs_dir = self.file_manager.get_logs_dir(domain)
        self._logger = WrapperLogger(logs_dir, domain)
    
    def build_automaton(self, weighted_words: Dict):
        """
        构建AC自动机
        
        从带权重特征词库构建自动机
        
        Args:
            weighted_words: 带权重的特征词数据，结构如下：
                {
                    "意图映射表": {
                        "意图1": {"L1_事项词": [...], "L2_动作词": [...], ...}
                    },
                    "词权重表": {
                        "词1": {"权重": 0.95, ...}
                    }
                }
        """
        if ahocorasick is None:
            raise ImportError("请先安装 pyahocorasick: pip install pyahocorasick")
        
        # 构建正向匹配自动机
        self.automaton = ahocorasick.Automaton()
        
        intent_map = weighted_words.get("意图映射表", {})
        weight_table = weighted_words.get("词权重表", {})
        
        # 用于合并同一个词对应的多个意图
        word_intent_map: Dict[str, Dict] = {}
        
        for intent, layers in intent_map.items():
            for layer, words in layers.items():
                for word in words:
                    # 兼容新旧两种词权重格式
                    weight_entry = weight_table.get(word, {})
                    if '权重' in weight_entry:
                        # 旧格式：{"权重": 0.95} — 所有意图共享同一权重
                        weight = weight_entry['权重']
                    elif intent in weight_entry:
                        # 新格式：{"意图A": {"权重": x}} — 按意图独立权重
                        intent_w = weight_entry[intent]
                        weight = intent_w.get('有效权重',
                                              intent_w.get('权重', 0.5))
                    else:
                        weight = 0.5
                    
                    if word not in word_intent_map:
                        word_intent_map[word] = {}
                    
                    word_intent_map[word][intent] = {
                        "层级": layer,
                        "权重": weight
                    }
        
        # 添加词到自动机
        for word, intent_info in word_intent_map.items():
            self.automaton.add_word(word, (word, intent_info))
        
        self.automaton.make_automaton()
        self._is_built = True
        
        # 可选：构建负面清单自动机
        if "负面清单" in weighted_words:
            self._build_negative_automaton(weighted_words["负面清单"])
    
    def _build_negative_automaton(self, negative_list: Dict):
        """构建负面清单自动机"""
        if ahocorasick is None:
            return
        
        self.negative_automaton = ahocorasick.Automaton()
        for term, domains in negative_list.items():
            self.negative_automaton.add_word(term, domains)
        self.negative_automaton.make_automaton()
    
    def load_and_build(self, weighted_words_path: Union[str, Path]):
        """
        加载特征词文件并构建自动机
        
        Args:
            weighted_words_path: 带权重特征词文件路径
        """
        weighted_words = self.file_manager.load_json(weighted_words_path)
        self.build_automaton(weighted_words)
    
    def segment(self, rewritten_query: str, domain: str = None) -> List[Dict]:
        """
        使用AC自动机进行切词匹配
        
        算法流程：
        1. 遍历文本，找出所有匹配的关键词
        2. 过滤子串词汇（保留最长匹配）
        3. 应用负面清单过滤
        4. 返回匹配结果
        
        Args:
            rewritten_query: 转写后的标准表达
            domain: 业务领域（用于日志记录）
            
        Returns:
            匹配结果列表，每项包含：
            {
                "词": "失业保险金",
                "意图": "失业保险金申领",
                "层级": "L1_事项词",
                "权重": 0.95
            }
        """
        if not self._is_built or self.automaton is None:
            raise ValueError("自动机未初始化，请先调用 build_automaton() 或 load_and_build()")
        
        # Step 1: 收集所有匹配
        raw_matches: List[Tuple[int, str, Dict]] = []
        for end_pos, (word, intent_info) in self.automaton.iter(rewritten_query):
            start_pos = end_pos - len(word) + 1
            raw_matches.append((start_pos, word, intent_info))
        
        # Step 2: 过滤子串（保留最长匹配）
        filtered_matches = self._filter_substrings(raw_matches)
        
        # Step 3: 展开为结果列表
        matched_words = []
        for word, intent_info in filtered_matches:
            for intent, info in intent_info.items():
                matched_words.append({
                    "词": word,
                    "意图": intent,
                    "层级": info["层级"],
                    "权重": info["权重"]
                })
        
        # Step 4: 应用负面清单过滤
        if self.negative_automaton and domain:
            matched_words = self._apply_negative_filter(rewritten_query, matched_words)
        
        # Step 5: 记录日志
        if domain and self._logger is None:
            self.init_logger(domain)
        
        if self._logger:
            self._logger.log_step(
                step="切词匹配",
                input_data=rewritten_query,
                output_data=[w["词"] for w in matched_words],
                details={"匹配详情": matched_words}
            )
        
        return matched_words
    
    def _filter_substrings(self, matches: List[Tuple[int, str, Dict]]) -> List[Tuple[str, Dict]]:
        """
        过滤子串词汇 — 仅在同意图内过滤，不同意图的子串保留
        
        例如：
        - "失业保险金"和"保险金"属于同一意图 → 只保留"失业保险金"
        - "保险金"属于意图A、"失业保险金"属于意图B → 两者均保留
        
        Args:
            matches: 原始匹配列表，每项为 (start_pos, word, intent_info)
        Returns:
            过滤后的匹配列表 [(word, intent_info), ...]
        """
        if not matches:
            return []
        
        # 按起始位置和长度排序（相同位置优先长的）
        sorted_matches = sorted(matches, key=lambda x: (x[0], -len(x[1])))
        
        # 按意图分组记录已覆盖的范围
        intent_covered: Dict[str, List[Tuple[int, int]]] = {}
        result_map: Dict[str, Dict] = {}  # word -> merged intent_info
        
        for start_pos, word, intent_info in sorted_matches:
            end_pos = start_pos + len(word)
            
            # 对每个关联意图单独判断是否被覆盖
            kept_intents = {}
            for intent, info in intent_info.items():
                covered = intent_covered.get(intent, [])
                is_covered = any(
                    s <= start_pos and end_pos <= e
                    for s, e in covered
                )
                if not is_covered:
                    kept_intents[intent] = info
                    covered.append((start_pos, end_pos))
                    intent_covered[intent] = covered
            
            if kept_intents:
                if word in result_map:
                    result_map[word].update(kept_intents)
                else:
                    result_map[word] = kept_intents
        
        return [(word, info) for word, info in result_map.items()]
    
    def _apply_negative_filter(self, query: str, matched_words: List[Dict]) -> List[Dict]:
        """应用负面清单过滤"""
        if self.negative_automaton is None:
            return matched_words
        
        # 收集需要排除的领域
        negative_domains: Set[str] = set()
        for _, domains in self.negative_automaton.iter(query):
            if isinstance(domains, (list, set)):
                negative_domains.update(domains)
            else:
                negative_domains.add(domains)
        
        if not negative_domains:
            return matched_words
        
        # 过滤掉命中负面清单的词
        return [w for w in matched_words if w.get("领域") not in negative_domains]
    
    def save_logger(self):
        """保存日志到文件"""
        if self._logger:
            self._logger.save()
    
    def get_statistics(self) -> Dict:
        """获取自动机统计信息"""
        if not self._is_built:
            return {"状态": "未构建"}
        
        return {
            "状态": "已构建",
            "词汇数量": len(self.automaton) if self.automaton else 0,
            "有负面清单": self.negative_automaton is not None
        }
