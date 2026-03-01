# -*- coding: utf-8 -*-
"""
修改日志管理模块

负责记录词表的增量变更：
- 新增意图
- 新增特征词
- 修改特征词权重
- 生成人类可读的 Markdown 日志
- 管理历史版本存档
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


class ChangeLogManager:
    """修改日志管理器
    
    管理词表的增量变更记录和历史版本存档
    """
    
    def __init__(self, output_dir: Path):
        """
        初始化修改日志管理器
        
        Args:
            output_dir: 输出目录（如 result/失业保险/weighted/）
        """
        self.output_dir = Path(output_dir)
        self.history_dir = self.output_dir / "history"
        self.changelog_path = self.output_dir / "change_log.md"
        
    def compare_wordlists(self, old_data: Dict, new_data: Dict) -> Dict:
        """
        比较新旧词表，识别变更
        
        Args:
            old_data: 旧的词表数据
            new_data: 新的词表数据
            
        Returns:
            变更详情字典
        """
        changes = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "new_intents": [],
            "new_words": [],
            "modified_words": [],
            "removed_words": [],
            "stats": {}
        }
        
        old_intent_map = old_data.get("意图映射表", {})
        new_intent_map = new_data.get("意图映射表", {})
        old_weight_table = old_data.get("词权重表", {})
        new_weight_table = new_data.get("词权重表", {})
        
        # 检测新增意图
        old_intents = set(old_intent_map.keys())
        new_intents = set(new_intent_map.keys())
        changes["new_intents"] = list(new_intents - old_intents)
        
        # 检测新增/修改的词汇
        old_words = set(old_weight_table.keys())
        new_words = set(new_weight_table.keys())
        
        # 新增词汇
        for word in (new_words - old_words):
            weight_info = new_weight_table.get(word, {})
            # 找出该词关联的意图和层级
            intents, layers = self._find_word_context(word, new_intent_map)
            changes["new_words"].append({
                "词汇": word,
                "权重": weight_info.get("权重", 0.5),
                "层级": ", ".join(layers),
                "关联意图": ", ".join(list(intents)[:3]) + ("..." if len(intents) > 3 else ""),
                "理由": weight_info.get("理由", "")
            })
        
        # 修改的词汇（权重变化）
        for word in (old_words & new_words):
            old_weight = old_weight_table.get(word, {}).get("权重", 0.5)
            new_weight = new_weight_table.get(word, {}).get("权重", 0.5)
            if abs(old_weight - new_weight) > 0.01:  # 权重变化超过0.01才记录
                changes["modified_words"].append({
                    "词汇": word,
                    "原权重": old_weight,
                    "新权重": new_weight,
                    "修改原因": new_weight_table.get(word, {}).get("理由", "AI重新评估")
                })
        
        # 删除的词汇
        changes["removed_words"] = list(old_words - new_words)
        
        # 统计信息
        changes["stats"] = {
            "新增意图数": len(changes["new_intents"]),
            "新增词数": len(changes["new_words"]),
            "修改词数": len(changes["modified_words"]),
            "删除词数": len(changes["removed_words"])
        }
        
        return changes
    
    def _find_word_context(self, word: str, intent_map: Dict) -> Tuple[Set[str], Set[str]]:
        """找出词汇关联的意图和层级"""
        intents = set()
        layers = set()
        for intent, layer_data in intent_map.items():
            for layer, words in layer_data.items():
                if word in words:
                    intents.add(intent)
                    layers.add(layer)
        return intents, layers
    
    def append_changelog(self, changes: Dict, source_file: str = ""):
        """
        追加修改日志到 change_log.md
        
        Args:
            changes: 变更详情
            source_file: 来源文件路径
        """
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成日志条目
        log_entry = self._format_changelog_entry(changes, source_file)
        
        # 读取现有日志（如果存在）
        existing_content = ""
        if self.changelog_path.exists():
            with open(self.changelog_path, 'r', encoding='utf-8') as f:
                existing_content = f.read()
        
        # 如果是新文件，添加标题
        if not existing_content:
            existing_content = "# 词表更新日志\n\n"
        
        # 在标题后插入新条目
        header = "# 词表更新日志\n\n"
        if existing_content.startswith(header):
            new_content = header + log_entry + "\n---\n\n" + existing_content[len(header):]
        else:
            new_content = header + log_entry + "\n---\n\n" + existing_content
        
        # 写入文件
        with open(self.changelog_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
    
    def _format_changelog_entry(self, changes: Dict, source_file: str) -> str:
        """格式化日志条目为Markdown"""
        lines = []
        
        # 时间戳
        lines.append(f"## {changes['timestamp']}")
        lines.append("")
        
        # 来源
        if source_file:
            lines.append(f"### 来源")
            lines.append(f"基于 `{source_file}` 自动提取")
            lines.append("")
        
        # 统计摘要
        stats = changes.get("stats", {})
        lines.append(f"### 变更摘要")
        lines.append(f"- 新增意图: {stats.get('新增意图数', 0)}")
        lines.append(f"- 新增词汇: {stats.get('新增词数', 0)}")
        lines.append(f"- 修改词汇: {stats.get('修改词数', 0)}")
        lines.append(f"- 删除词汇: {stats.get('删除词数', 0)}")
        lines.append("")
        
        # 新增意图
        if changes.get("new_intents"):
            lines.append("### 新增意图")
            for intent in changes["new_intents"]:
                lines.append(f"- {intent}")
            lines.append("")
        
        # 新增词汇
        if changes.get("new_words"):
            lines.append("### 新增特征词")
            lines.append("| 词汇 | 层级 | 权重 | 关联意图 |")
            lines.append("|-----|------|------|---------|")
            for word_info in changes["new_words"][:20]:  # 最多显示20个
                lines.append(f"| {word_info['词汇']} | {word_info['层级']} | {word_info['权重']} | {word_info['关联意图']} |")
            if len(changes["new_words"]) > 20:
                lines.append(f"| ... | ... | ... | (共{len(changes['new_words'])}个) |")
            lines.append("")
        
        # 修改的词汇
        if changes.get("modified_words"):
            lines.append("### 修改特征词")
            lines.append("| 词汇 | 原权重 | 新权重 | 修改原因 |")
            lines.append("|-----|-------|-------|---------|")
            for word_info in changes["modified_words"][:10]:
                lines.append(f"| {word_info['词汇']} | {word_info['原权重']} | {word_info['新权重']} | {word_info['修改原因']} |")
            if len(changes["modified_words"]) > 10:
                lines.append(f"| ... | ... | ... | (共{len(changes['modified_words'])}个) |")
            lines.append("")
        
        return "\n".join(lines)
    
    def save_history_snapshot(self, current_data: Dict, changes: Dict):
        """
        保存历史版本快照
        
        Args:
            current_data: 当前词表数据（变更前）
            changes: 变更详情
        """
        if not changes.get("stats") or all(v == 0 for v in changes["stats"].values()):
            return  # 无变更，不保存快照
        
        # 创建历史目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_dir = self.history_dir / timestamp
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存快照
        with open(snapshot_dir / "snapshot.json", 'w', encoding='utf-8') as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
        
        # 保存变更记录
        with open(snapshot_dir / "changes.json", 'w', encoding='utf-8') as f:
            json.dump(changes, f, ensure_ascii=False, indent=2)
    
    def get_latest_wordlist(self) -> Optional[Dict]:
        """
        获取最新的全局词表
        
        Returns:
            词表数据，不存在则返回None
        """
        wordlist_path = self.output_dir / "weighted_words.json"
        if wordlist_path.exists():
            with open(wordlist_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
