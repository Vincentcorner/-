# -*- coding: utf-8 -*-
"""
模块6：AI意图筛选器

从候选意图中选择最匹配用户诉求的意图
AI分析由AI助手通过工作流命令完成
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Union

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.common.file_manager import FileManager
from scripts.common.logger import WrapperLogger
from scripts.common.config import ConfigManager


class IntentSelector:
    """AI意图筛选器
    
    从Top-K候选意图中选择最匹配用户诉求的意图
    综合考虑：
    1. 权重得分
    2. 语义匹配度
    3. 上下文信息
    """
    
    PROMPT_NAME = "intent_select_prompt"
    
    def __init__(self, file_manager: FileManager = None, config: ConfigManager = None):
        """
        初始化意图筛选器
        
        Args:
            file_manager: 文件管理器实例
            config: 配置管理器实例
        """
        self.file_manager = file_manager or FileManager()
        self.config = config or ConfigManager()
        self._logger: Optional[WrapperLogger] = None
    
    def init_logger(self, domain: str):
        """初始化日志记录器"""
        logs_dir = self.file_manager.get_logs_dir(domain)
        self._logger = WrapperLogger(logs_dir, domain)
    
    def prepare_for_ai(self, top_k_intents: List[Dict], original_query: str) -> str:
        """
        准备AI筛选所需的输入数据
        
        Args:
            top_k_intents: 候选意图列表
            original_query: 用户原始诉求
            
        Returns:
            格式化的输入文本，供AI助手分析
        """
        # 加载提示词模板
        try:
            prompt_template = self.file_manager.load_prompt(self.PROMPT_NAME)
        except FileNotFoundError:
            prompt_template = self._get_default_prompt()
        
        # 格式化候选意图
        intents_text = self._format_candidates(top_k_intents)
        
        return f"""{prompt_template}

## 用户原始诉求

{original_query}

## 候选意图（按得分排序）

{intents_text}
"""
    
    def _format_candidates(self, intents: List[Dict]) -> str:
        """格式化候选意图列表"""
        lines = ["| 排名 | 意图 | 得分 | 命中词 |", "|------|------|------|--------|"]
        
        for i, intent in enumerate(intents, 1):
            intent_name = intent.get("意图", "")
            score = intent.get("得分", 0)
            hit_words = [h["词"] for h in intent.get("命中详情", [])]
            hit_str = ", ".join(hit_words[:5])
            if len(hit_words) > 5:
                hit_str += "..."
            
            lines.append(f"| {i} | {intent_name} | {score:.2f} | {hit_str} |")
        
        return "\n".join(lines)
    
    def _get_default_prompt(self) -> str:
        """获取默认筛选提示词"""
        return """# 意图筛选任务

请从候选意图中选择最匹配用户诉求的意图。

## 选择规则

1. **语义最匹配**：选择与用户表达语义最接近的意图
2. **得分参考**：得分高的意图优先考虑，但不是唯一标准
3. **上下文理解**：考虑用户可能的真实需求
4. **单一选择**：只选择一个最匹配的意图

## 输出格式

请按以下JSON格式输出：

```json
{
  "选中意图": "意图名称",
  "置信度": 0.95,
  "理由": "选择理由说明"
}
```
"""
    
    def parse_ai_result(self, ai_output: str) -> Dict:
        """
        解析AI助手的筛选结果
        
        Args:
            ai_output: AI助手的原始输出文本
            
        Returns:
            解析后的筛选结果
        """
        import json
        import re
        
        # 尝试提取JSON块
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', ai_output)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = ai_output
        
        try:
            result = json.loads(json_str)
            return self._normalize_selection(result)
        except json.JSONDecodeError:
            # 如果解析失败，尝试从文本中提取意图名称
            return self._extract_intent_from_text(ai_output)
    
    def _normalize_selection(self, result: Dict) -> Dict:
        """规范化筛选结果"""
        return {
            "选中意图": result.get("选中意图", result.get("intent", "")),
            "置信度": float(result.get("置信度", result.get("confidence", 0.8))),
            "理由": result.get("理由", result.get("reason", ""))
        }
    
    def _extract_intent_from_text(self, text: str) -> Dict:
        """从文本中提取意图名称"""
        # 简单的文本提取逻辑
        lines = text.strip().split("\n")
        for line in lines:
            if "选中" in line or "推荐" in line or "匹配" in line:
                # 尝试提取引号中的内容
                import re
                match = re.search(r'[「『"\'](.*?)[」』"\']', line)
                if match:
                    return {
                        "选中意图": match.group(1),
                        "置信度": 0.7,
                        "理由": "从文本中提取"
                    }
        
        return {
            "选中意图": "",
            "置信度": 0,
            "理由": "无法解析AI输出"
        }
    
    def log_selection(self, top_k_intents: List[Dict], original_query: str,
                      selected: Dict, domain: str):
        """
        记录意图筛选结果到wrapper日志
        
        Args:
            top_k_intents: 候选意图列表
            original_query: 用户原始诉求
            selected: AI选择的结果
            domain: 业务领域
        """
        if self._logger is None:
            self.init_logger(domain)
        
        self._logger.log_step(
            step="AI意图筛选",
            input_data={
                "原始诉求": original_query,
                "候选意图": [i["意图"] for i in top_k_intents]
            },
            output_data=selected
        )
    
    def select(self, top_k_intents: List[Dict], original_query: str,
               ai_output: str, domain: str) -> Dict:
        """
        完整的筛选流程
        
        Args:
            top_k_intents: 候选意图列表
            original_query: 用户原始诉求
            ai_output: AI助手的分析结果
            domain: 业务领域
            
        Returns:
            最终选择的意图结果
        """
        # 解析AI输出
        selected = self.parse_ai_result(ai_output)
        
        # 记录日志
        self.log_selection(top_k_intents, original_query, selected, domain)
        
        return selected
    
    def save_logger(self):
        """保存日志到文件"""
        if self._logger:
            self._logger.save()
    
    def get_fallback_result(self, top_k_intents: List[Dict]) -> Dict:
        """
        获取降级结果（当AI无法选择时使用）
        
        直接返回得分最高的意图
        
        Args:
            top_k_intents: 候选意图列表
            
        Returns:
            得分最高的意图
        """
        if not top_k_intents:
            return {
                "选中意图": "",
                "置信度": 0,
                "理由": "无候选意图"
            }
        
        best = top_k_intents[0]
        return {
            "选中意图": best["意图"],
            "置信度": min(best["得分"], 1.0),
            "理由": "降级策略：选择得分最高的意图"
        }
