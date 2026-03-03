# -*- coding: utf-8 -*-
"""
模块3：诉求转写器

将用户的原始诉求转写为标准化表达
AI分析由AI助手通过工作流命令完成
"""

import sys
from pathlib import Path
from typing import Dict, Optional, Union

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.common.file_manager import FileManager
from scripts.common.logger import WrapperLogger
from scripts.common.config import ConfigManager


class QueryRewriter:
    """诉求转写器
    
    将用户的口语化表达转写为标准化的业务表达
    例如："我想领失业金" → "失业保险金申领"
    """
    
    PROMPT_NAME = "query_rewrite_prompt"
    
    def __init__(self, file_manager: FileManager = None, config: ConfigManager = None):
        """
        初始化诉求转写器
        
        Args:
            file_manager: 文件管理器实例
            config: 配置管理器实例
        """
        self.file_manager = file_manager or FileManager()
        self.config = config or ConfigManager()
        self._logger: Optional[WrapperLogger] = None
    
    def init_logger(self, domain: str):
        """
        初始化日志记录器
        
        Args:
            domain: 业务领域名称
        """
        logs_dir = self.file_manager.get_logs_dir(domain)
        self._logger = WrapperLogger(logs_dir, domain)
    
    def prepare_for_ai(self, query: str, domain: str = None) -> str:
        """
        准备AI转写所需的输入数据
        
        Args:
            query: 用户原始诉求
            domain: 业务领域（可选，用于加载领域相关提示词）
            
        Returns:
            格式化的输入文本，供AI助手分析
        """
        # 加载提示词模板
        try:
            prompt_template = self.file_manager.load_prompt(self.PROMPT_NAME)
        except FileNotFoundError:
            prompt_template = self._get_default_prompt()
        
        # 组合提示词和用户输入
        return f"{prompt_template}\n\n## 待转写的用户诉求\n\n{query}"
    
    def _get_default_prompt(self) -> str:
        """获取默认转写提示词"""
        return """# 诉求转写任务

请将用户的口语化诉求转写为标准化的业务表达。

## 转写规则

1. **保留核心语义**：不改变用户的原始意图
2. **规范化表达**：使用业务标准术语
3. **简化冗余**：去除无关的寒暄语和重复内容
4. **补全省略**：补充必要但被省略的信息

## 示例

| 用户原始诉求 | 转写后 |
|-------------|--------|
| 我想领失业金 | 失业保险金申领 |
| 公司倒闭了怎么办 | 失业保险金申领、企业职工失业登记 |
| 返还的钱怎么查 | 稳岗返还查询 |

## 输出格式

请直接输出转写后的内容，如有多个可能的意图，用顿号分隔。
"""
    
    def log_rewrite(self, query: str, rewritten: str, domain: str):
        """
        记录转写结果到wrapper日志
        
        Args:
            query: 用户原始诉求
            rewritten: 转写后的结果
            domain: 业务领域
        """
        if self._logger is None:
            self.init_logger(domain)
        
        self._logger.log_step(
            step="诉求转写",
            input_data=query,
            output_data=rewritten
        )
    
    def save_logger(self):
        """保存日志到文件"""
        if self._logger:
            self._logger.save()
    
    def get_rewrite_result(self, query: str, ai_output: str, domain: str) -> Dict:
        """
        处理并记录转写结果
        
        Args:
            query: 用户原始诉求
            ai_output: AI助手的转写结果
            domain: 业务领域
            
        Returns:
            转写结果数据
        """
        # 清理AI输出
        rewritten = ai_output.strip()
        
        # 记录日志
        self.log_rewrite(query, rewritten, domain)
        
        return {
            "原始诉求": query,
            "转写结果": rewritten,
            "领域": domain
        }
