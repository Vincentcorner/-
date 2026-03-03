# -*- coding: utf-8 -*-
"""
日志管理模块

提供 wrapper 日志记录功能，用于追踪意图匹配全流程
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union


class WrapperLogger:
    """Wrapper日志记录器
    
    记录意图匹配的完整流程，包括：
    - 诉求转写
    - 切词匹配
    - 权重计算
    - AI意图筛选
    """
    
    def __init__(self, logs_dir: Union[str, Path], domain: str):
        """
        初始化日志记录器
        
        Args:
            logs_dir: 日志目录路径
            domain: 业务领域名称
        """
        self.logs_dir = Path(logs_dir)
        self.domain = domain
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # 当前日期的日志文件
        self.date = datetime.now().strftime("%Y%m%d")
        self.log_file = self.logs_dir / f"{self.date}.wrapper"
        
        # 当前会话的日志数据
        self.session_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
        self.session_logs: List[Dict] = []
    
    def log(self, entry: Dict):
        """
        记录一条日志
        
        Args:
            entry: 日志条目，应包含 step, input, output 等字段
        """
        log_entry = {
            "session_id": self.session_id,
            "domain": self.domain,
            "timestamp": datetime.now().isoformat(),
            **entry
        }
        self.session_logs.append(log_entry)
    
    def log_step(self, step: str, input_data: any, output_data: any, 
                 details: Dict = None):
        """
        记录一个处理步骤
        
        Args:
            step: 步骤名称，如 "诉求转写", "切词匹配"
            input_data: 输入数据
            output_data: 输出数据
            details: 附加详情
        """
        entry = {
            "step": step,
            "input": input_data,
            "output": output_data
        }
        if details:
            entry["details"] = details
        
        self.log(entry)
    
    def append(self, entry: Dict, domain: str = None):
        """
        追加日志（兼容旧接口）
        
        Args:
            entry: 日志条目
            domain: 领域名称（可选，会覆盖初始化时的domain）
        """
        if domain:
            entry["domain"] = domain
        self.log(entry)
    
    def save(self):
        """保存当前会话的日志到文件"""
        if not self.session_logs:
            return
        
        # 读取现有日志
        existing_logs = []
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    existing_logs = json.load(f)
            except json.JSONDecodeError:
                existing_logs = []
        
        # 追加新日志
        existing_logs.extend(self.session_logs)
        
        # 写回文件
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(existing_logs, f, ensure_ascii=False, indent=2)
        
        # 清空会话日志
        self.session_logs = []
    
    def get_session_logs(self) -> List[Dict]:
        """获取当前会话的日志"""
        return self.session_logs.copy()
    
    def get_latest_output(self, step: str) -> Optional[any]:
        """
        获取指定步骤的最新输出
        
        Args:
            step: 步骤名称
            
        Returns:
            该步骤的最新输出，不存在则返回None
        """
        for log in reversed(self.session_logs):
            if log.get("step") == step:
                return log.get("output")
        return None
    
    def load_logs(self, date: str = None) -> List[Dict]:
        """
        加载指定日期的日志
        
        Args:
            date: 日期字符串 YYYYMMDD，默认为今天
            
        Returns:
            日志列表
        """
        if date is None:
            date = self.date
        
        log_file = self.logs_dir / f"{date}.wrapper"
        if not log_file.exists():
            return []
        
        with open(log_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_session_summary(self) -> Dict:
        """
        获取当前会话的摘要
        
        Returns:
            会话摘要，包含各步骤的执行情况
        """
        summary = {
            "session_id": self.session_id,
            "domain": self.domain,
            "steps": [],
            "total_steps": len(self.session_logs)
        }
        
        for log in self.session_logs:
            step_info = {
                "step": log.get("step"),
                "timestamp": log.get("timestamp"),
                "has_output": log.get("output") is not None
            }
            summary["steps"].append(step_info)
        
        return summary


class SimpleLogger:
    """简单日志记录器
    
    用于记录一般性操作日志（非wrapper流程）
    """
    
    def __init__(self, log_file: Union[str, Path] = None):
        """
        初始化简单日志记录器
        
        Args:
            log_file: 日志文件路径，默认输出到控制台
        """
        self.log_file = Path(log_file) if log_file else None
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
    
    def _format_message(self, level: str, message: str) -> str:
        """格式化日志消息"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{timestamp}] [{level}] {message}"
    
    def _write(self, formatted_msg: str):
        """写入日志"""
        print(formatted_msg)
        if self.log_file:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(formatted_msg + "\n")
    
    def info(self, message: str):
        """记录信息日志"""
        self._write(self._format_message("INFO", message))
    
    def warning(self, message: str):
        """记录警告日志"""
        self._write(self._format_message("WARN", message))
    
    def error(self, message: str):
        """记录错误日志"""
        self._write(self._format_message("ERROR", message))
    
    def debug(self, message: str):
        """记录调试日志"""
        self._write(self._format_message("DEBUG", message))
