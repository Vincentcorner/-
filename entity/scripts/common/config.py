# -*- coding: utf-8 -*-
"""
配置管理模块

提供统一的配置加载和管理功能
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigManager:
    """配置管理器"""
    
    # 默认配置值
    DEFAULT_LAYER_WEIGHTS = {
        "L1": 1.0,
        "L2": 0.8,
        "L3": 0.6
    }
    
    DEFAULT_THRESHOLD = {
        "min_score": 0.4,
        "top_k": 10
    }
    
    DEFAULT_DOMAINS = {
        "失业保险": {
            "name": "失业保险",
            "description": "失业保险相关业务"
        }
    }
    
    def __init__(self, config_dir: str = None):
        """
        初始化配置管理器
        
        Args:
            config_dir: 配置目录路径，默认为项目根目录下的config/
        """
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            # 默认配置目录: scripts/common/config.py -> entity/config/
            self.config_dir = Path(__file__).parent.parent.parent / "config"
        
        self._cache: Dict[str, Any] = {}
    
    def _load_config_file(self, filename: str) -> Dict:
        """
        加载配置文件
        
        Args:
            filename: 配置文件名
            
        Returns:
            配置数据
        """
        config_file = self.config_dir / filename
        if not config_file.exists():
            return {}
        
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _get_cached(self, key: str, loader_func, default: Any) -> Any:
        """
        获取缓存的配置，如果不存在则加载
        
        Args:
            key: 缓存键
            loader_func: 加载函数
            default: 默认值
            
        Returns:
            配置值
        """
        if key not in self._cache:
            loaded = loader_func()
            self._cache[key] = loaded if loaded else default
        return self._cache[key]
    
    def get_layer_weights(self) -> Dict[str, float]:
        """
        获取层级权重配置
        
        Returns:
            层级权重字典，如 {"L1": 1.0, "L2": 0.8, "L3": 0.6}
        """
        return self._get_cached(
            "layer_weights",
            lambda: self._load_config_file("layer_weights.json"),
            self.DEFAULT_LAYER_WEIGHTS
        )
    
    def get_threshold_config(self) -> Dict[str, Any]:
        """
        获取阈值配置
        
        Returns:
            阈值配置字典，包含 min_score 和 top_k
        """
        return self._get_cached(
            "threshold",
            lambda: self._load_config_file("threshold.json"),
            self.DEFAULT_THRESHOLD
        )
    
    def get_domains(self) -> Dict[str, Dict]:
        """
        获取领域配置
        
        Returns:
            领域配置字典
        """
        return self._get_cached(
            "domains",
            lambda: self._load_config_file("domains.json"),
            self.DEFAULT_DOMAINS
        )
    
    def get_domain_config(self, domain: str) -> Optional[Dict]:
        """
        获取指定领域的配置
        
        Args:
            domain: 领域名称
            
        Returns:
            领域配置，不存在则返回None
        """
        domains = self.get_domains()
        return domains.get(domain)
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取通用配置项
        
        Args:
            key: 配置键，支持点号分隔的路径如 "threshold.top_k"
            default: 默认值
            
        Returns:
            配置值
        """
        # 解析配置键路径
        parts = key.split(".")
        
        if parts[0] == "layer_weights":
            config = self.get_layer_weights()
        elif parts[0] == "threshold":
            config = self.get_threshold_config()
        elif parts[0] == "domains":
            config = self.get_domains()
        else:
            return default
        
        # 遍历路径获取值
        for part in parts[1:]:
            if isinstance(config, dict):
                config = config.get(part)
            else:
                return default
            if config is None:
                return default
        
        return config if config is not None else default
    
    def reload(self):
        """重新加载所有配置（清除缓存）"""
        self._cache.clear()
    
    def save_config(self, filename: str, data: Dict):
        """
        保存配置到文件
        
        Args:
            filename: 配置文件名
            data: 配置数据
        """
        self.config_dir.mkdir(parents=True, exist_ok=True)
        config_file = self.config_dir / filename
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # 清除对应缓存
        cache_key = filename.replace('.json', '')
        if cache_key in self._cache:
            del self._cache[cache_key]
    
    def validate_domain(self, domain: str) -> bool:
        """
        验证领域是否有效
        
        Args:
            domain: 领域名称
            
        Returns:
            领域是否有效
        """
        domains = self.get_domains()
        return domain in domains
    
    def get_all_domains(self) -> list:
        """
        获取所有已配置的领域名称
        
        Returns:
            领域名称列表
        """
        return list(self.get_domains().keys())


# 全局配置实例
_config_manager: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    """获取全局配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
