# -*- coding: utf-8 -*-
"""
文件管理模块

提供统一的文件读写、目录管理、格式转换等功能
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union
import pandas as pd


class FileManager:
    """文件管理器"""
    
    def __init__(self, base_dir: str = None):
        """
        初始化文件管理器
        
        Args:
            base_dir: 项目根目录，默认为当前文件的上三级目录
        """
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            # 默认项目根目录: scripts/common/file_manager.py -> entity/
            self.base_dir = Path(__file__).parent.parent.parent
        
        self.result_dir = self.base_dir / "result"
        self.config_dir = self.base_dir / "config"
        self.prompts_dir = self.base_dir / "prompts"
    
    def get_domain_dir(self, domain: str) -> Path:
        """
        获取领域目录
        
        Args:
            domain: 领域名称，如 "失业保险"
            
        Returns:
            领域目录路径
        """
        return self.result_dir / domain
    
    def get_intent_list_dir(self, domain: str, date: str = None, 
                             create_new: bool = False) -> Path:
        """
        获取意图清单目录
        
        Args:
            domain: 领域名称
            date: 日期字符串，格式 YYYYMMDD 或 YYYYMMDD_HHMMSS
            create_new: 是否创建新的带时间戳的目录（避免覆盖）
            
        Returns:
            意图清单目录路径
        """
        intent_base = self.get_domain_dir(domain) / "intent_list"
        
        if create_new:
            # 创建新的带时间戳目录: YYYYMMDD_HHMMSS
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            intent_dir = intent_base / timestamp
        elif date:
            intent_dir = intent_base / date
        else:
            # 查找最新的目录
            latest = self.find_latest_version_dir(domain)
            if latest:
                return latest
            # 如果没有历史目录，创建新的
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            intent_dir = intent_base / timestamp
        
        intent_dir.mkdir(parents=True, exist_ok=True)
        return intent_dir
    
    def get_weighted_dir(self, domain: str, date: str = None,
                         create_new: bool = False) -> Path:
        """
        获取权重打分结果目录
        
        Args:
            domain: 领域名称
            date: 日期字符串，格式 YYYYMMDD
            create_new: 是否创建新的目录
            
        Returns:
            权重打分结果目录路径
        """
        weighted_base = self.get_domain_dir(domain) / "weighted"
        
        if date:
            weighted_dir = weighted_base / date
        else:
            # 使用今日日期
            date_str = datetime.now().strftime("%Y%m%d")
            weighted_dir = weighted_base / date_str
        
        weighted_dir.mkdir(parents=True, exist_ok=True)
        return weighted_dir
    
    def get_intent_match_dir(self, domain: str, date: str = None) -> Path:
        """
        获取意图匹配结果目录
        
        Args:
            domain: 领域名称
            date: 日期字符串，格式 YYYYMMDD
            
        Returns:
            意图匹配结果目录路径
        """
        match_base = self.get_domain_dir(domain) / "intent_match"
        
        if date:
            match_dir = match_base / date
        else:
            # 使用今日日期
            date_str = datetime.now().strftime("%Y%m%d")
            match_dir = match_base / date_str
        
        match_dir.mkdir(parents=True, exist_ok=True)
        return match_dir
    
    def get_benchmark_compare_dir(self, domain: str, date: str = None) -> Path:
        """
        获取标杆对比结果目录（自动创建递增批次子目录）
        
        目录结构: result/{domain}/benchmark_compare/{date}/{batch_number}/
        
        Args:
            domain: 领域名称
            date: 日期字符串，格式 YYYYMMDD，默认今日
            
        Returns:
            批次目录路径，如 result/失业保险/benchmark_compare/20260210/1/
        """
        compare_base = self.get_domain_dir(domain) / "benchmark_compare"
        
        if not date:
            date = datetime.now().strftime("%Y%m%d")
        
        date_dir = compare_base / date
        date_dir.mkdir(parents=True, exist_ok=True)
        
        # 找到下一个批次号
        existing_batches = [
            int(d.name) for d in date_dir.iterdir()
            if d.is_dir() and d.name.isdigit()
        ]
        next_batch = max(existing_batches, default=0) + 1
        
        batch_dir = date_dir / str(next_batch)
        batch_dir.mkdir(parents=True, exist_ok=True)
        
        return batch_dir
    
    def find_latest_version_dir(self, domain: str) -> Optional[Path]:
        """
        查找领域下最新的版本目录
        
        支持两种格式：
        - YYYYMMDD（纯日期）
        - YYYYMMDD_HHMMSS（带时间戳）
        
        Args:
            domain: 领域名称
            
        Returns:
            最新版本目录路径，不存在则返回None
        """
        intent_list_dir = self.get_domain_dir(domain) / "intent_list"
        if not intent_list_dir.exists():
            return None
        
        # 匹配 YYYYMMDD 或 YYYYMMDD_HHMMSS 格式
        version_dirs = []
        for d in intent_list_dir.iterdir():
            if d.is_dir():
                name = d.name
                # 纯日期格式 8位数字
                if len(name) == 8 and name.isdigit():
                    version_dirs.append((name + "_000000", d))
                # 带时间戳格式 YYYYMMDD_HHMMSS
                elif len(name) == 15 and name[8] == '_':
                    version_dirs.append((name, d))
        
        if not version_dirs:
            return None
        
        # 按版本号排序，返回最新的
        version_dirs.sort(key=lambda x: x[0], reverse=True)
        return version_dirs[0][1]
    
    def get_logs_dir(self, domain: str) -> Path:
        """
        获取日志目录
        
        Args:
            domain: 领域名称
            
        Returns:
            日志目录路径
        """
        logs_dir = self.get_domain_dir(domain) / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir
    
    # ========== 读取方法 ==========
    
    def load_json(self, file_path: Union[str, Path]) -> Dict:
        """
        加载JSON文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            JSON数据
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def load_excel(self, file_path: Union[str, Path], sheet_name: str = None) -> pd.DataFrame:
        """
        加载Excel文件
        
        Args:
            file_path: 文件路径
            sheet_name: 工作表名称，默认读取第一个
            
        Returns:
            DataFrame
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        if sheet_name:
            return pd.read_excel(file_path, sheet_name=sheet_name)
        else:
            return pd.read_excel(file_path)
    
    def load_intent_list(self, file_path: Union[str, Path]) -> List[Dict]:
        """
        加载意图清单（支持JSON和Excel格式）
        
        Args:
            file_path: 意图清单文件路径
            
        Returns:
            意图列表
        """
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()
        
        if suffix == '.json':
            data = self.load_json(file_path)
            return data if isinstance(data, list) else data.get('意图列表', [])
        elif suffix in ['.xlsx', '.xls']:
            df = self.load_excel(file_path)
            return df.to_dict('records')
        else:
            raise ValueError(f"不支持的文件格式: {suffix}")
    
    def load_prompt(self, prompt_name: str) -> str:
        """
        加载提示词模板
        
        Args:
            prompt_name: 提示词文件名（不含.md后缀）
            
        Returns:
            提示词内容
        """
        prompt_file = self.prompts_dir / f"{prompt_name}.md"
        if not prompt_file.exists():
            raise FileNotFoundError(f"提示词文件不存在: {prompt_file}")
        
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read()
    
    # ========== 写入方法 ==========
    
    def save_json(self, data: Union[Dict, List], file_path: Union[str, Path], 
                  ensure_ascii: bool = False, indent: int = 2):
        """
        保存JSON文件
        
        Args:
            data: 要保存的数据
            file_path: 文件路径
            ensure_ascii: 是否转义非ASCII字符
            indent: 缩进空格数
        """
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)
    
    def save_excel(self, data: Union[pd.DataFrame, List[Dict]], file_path: Union[str, Path],
                   sheet_name: str = "Sheet1", index: bool = False):
        """
        保存Excel文件
        
        Args:
            data: DataFrame或字典列表
            file_path: 文件路径
            sheet_name: 工作表名称
            index: 是否保存索引
        """
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        if isinstance(data, list):
            df = pd.DataFrame(data)
        else:
            df = data
        
        df.to_excel(file_path, sheet_name=sheet_name, index=index)
    
    def save_both_formats(self, data: Union[Dict, List], output_dir: Union[str, Path],
                          base_name: str, flatten_for_excel: bool = True):
        """
        同时保存JSON和Excel格式
        
        Args:
            data: 要保存的数据
            output_dir: 输出目录
            base_name: 基础文件名（不含扩展名）
            flatten_for_excel: 是否为Excel格式展平数据
        """
        output_dir = Path(output_dir)
        
        # 保存JSON
        self.save_json(data, output_dir / f"{base_name}.json")
        
        # 保存Excel
        if flatten_for_excel and isinstance(data, dict):
            excel_data = self._flatten_for_excel(data)
        elif isinstance(data, list):
            excel_data = data
        else:
            excel_data = [data]
        
        self.save_excel(excel_data, output_dir / f"{base_name}.xlsx")
    
    def _flatten_for_excel(self, data: Dict) -> List[Dict]:
        """
        将嵌套字典展平为列表格式，适合Excel显示
        
        Args:
            data: 嵌套字典数据
            
        Returns:
            展平后的列表
        """
        result = []
        
        # 尝试不同的展平策略
        if "意图映射表" in data:
            # 特征词格式
            for intent, layers in data.get("意图映射表", {}).items():
                for layer, words in layers.items():
                    for word in words:
                        weight = data.get("词权重表", {}).get(word, {}).get("权重", "")
                        result.append({
                            "意图": intent,
                            "层级": layer,
                            "特征词": word,
                            "权重": weight
                        })
        elif isinstance(data, dict):
            # 通用字典转列表
            for key, value in data.items():
                if isinstance(value, dict):
                    row = {"键": key}
                    row.update(value)
                    result.append(row)
                else:
                    result.append({"键": key, "值": value})
        
        return result if result else [data]
    
    # ========== 工具方法 ==========
    
    def ensure_dir(self, dir_path: Union[str, Path]) -> Path:
        """
        确保目录存在
        
        Args:
            dir_path: 目录路径
            
        Returns:
            目录Path对象
        """
        dir_path = Path(dir_path)
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path
    
    def list_files(self, dir_path: Union[str, Path], pattern: str = "*") -> List[Path]:
        """
        列出目录下匹配模式的文件
        
        Args:
            dir_path: 目录路径
            pattern: 文件匹配模式，如 "*.json"
            
        Returns:
            文件路径列表
        """
        dir_path = Path(dir_path)
        if not dir_path.exists():
            return []
        
        return list(dir_path.glob(pattern))
