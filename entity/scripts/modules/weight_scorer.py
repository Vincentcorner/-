# -*- coding: utf-8 -*-
"""
AI 权重打分器

一意图一词一分 + IDF 衰减 + 反向校验。
分批调用 AI（10~15 词/批），应用打分规则卡。
"""

import json
import math
import time
import sys
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.common.llm_api import call_llm_api_json, DEFAULT_INTERVAL
from scripts.common.file_manager import FileManager
from scripts.common.config import ConfigManager
from scripts.modules.feature_extractor import get_layer_key


BATCH_SIZE_SCORE = 12  # 每批打分的词数


def _build_score_prompt() -> str:
    """构建打分 system prompt（政务服务领域专家版，含打分规则卡）"""
    return """# 角色定位

请作为政务服务领域打分专家，为每个特征词在其所属意图下打权重分。确保打分贴合政务服务业务场景，权重能准确反映词汇对意图识别的区分度。

## 打分规则卡（4个维度）

### 1. 专业度（基础分）
| 分值范围 | 判断标准 | 核心问题 |
|----------|---------|----------|
| 0.90~1.00 | 强专业：该词是该意图的专业术语，无歧义 | 这个词只能指一件事吗？ |
| 0.75~0.89 | 半专业：常用表达，歧义较小 | 用户说这个词，80%+是这个意思？ |
| 0.60~0.74 | 通用：宽泛表达，歧义较大 | 这个词只能作为辅助？ |

### 2. 排他性（扣分）
- 该词关联 2~3 个意图 → 扣 0.05
- 该词关联 4+ 个意图 → 扣 0.10

### 3. 上下文独立性（加分）
- 该词单独出现就能确定意图 → 加 0.05

### 4. 最终权重
`权重 = 专业度基础分 - 排他性扣分 + 上下文加分`
取值范围：[0.50, 1.00]

## 同词同分原则

**重要**：同一个词在所有意图中应该有相同的权重分。

## 输出格式

对于每个词在每个意图下，请输出：
```json
{
  "打分结果": {
    "词1": {
      "意图A": { "权重": 0.95, "理由": "..." },
      "意图B": { "权重": 0.80, "理由": "..." }
    }
  }
}
```"""


class WeightScorer:
    """AI 权重打分器

    核心流程：分批 AI 打分 → IDF 衰减 → 反向校验
    """

    def __init__(self, file_manager: FileManager = None,
                 config: ConfigManager = None):
        self.file_manager = file_manager or FileManager()
        self.config = config or ConfigManager()
        self.layer_weights = self.config.get_layer_weights()

    # ─── AI 打分 ───

    def score_features(self, intent_map: dict,
                        all_intents: List[str] = None,
                        progress_callback=None) -> dict:
        """对每个意图的每个特征词独立 AI 打分

        Args:
            intent_map: {"意图名": {"核心词": [...], "发散词": [...], ...}}
            all_intents: 全部意图名列表（提供全局上下文）
            progress_callback: fn(current, total, message)

        Returns:
            {"词权重表": {"词": {"意图": {"权重": float, "理由": str}}}}
        """
        if all_intents is None:
            all_intents = list(intent_map.keys())

        # 构建 (词, 意图, 层级) 三元组列表
        word_intent_pairs = []
        for intent, layers in intent_map.items():
            for layer, words in layers.items():
                for word in words:
                    word_intent_pairs.append((word, intent, layer))

        result_weights = {}
        total_batches = math.ceil(len(word_intent_pairs) / BATCH_SIZE_SCORE)
        system_prompt = _build_score_prompt()

        for batch_idx in range(total_batches):
            start = batch_idx * BATCH_SIZE_SCORE
            end = min(start + BATCH_SIZE_SCORE, len(word_intent_pairs))
            batch = word_intent_pairs[start:end]

            if progress_callback:
                progress_callback(batch_idx + 1, total_batches,
                                  f'AI打分 [{batch_idx+1}/{total_batches}]')

            # 整理当前批次的词→意图映射
            batch_info = {}
            for word, intent, layer in batch:
                if word not in batch_info:
                    batch_info[word] = []
                batch_info[word].append({
                    '意图': intent,
                    '层级': layer,
                    '该词关联意图总数': self._count_word_intents(
                        word, intent_map)
                })

            user_content = f"""全部意图列表（共{len(all_intents)}个）：
{json.dumps(all_intents, ensure_ascii=False)}

请为以下特征词打分：
{json.dumps(batch_info, ensure_ascii=False, indent=2)}"""

            ai_result = call_llm_api_json(system_prompt, user_content)
            if ai_result and '打分结果' in ai_result:
                for word, intent_scores in ai_result['打分结果'].items():
                    if word not in result_weights:
                        result_weights[word] = {}
                    for intent, score_info in intent_scores.items():
                        result_weights[word][intent] = score_info

            if batch_idx < total_batches - 1:
                time.sleep(DEFAULT_INTERVAL)

        return {'词权重表': result_weights}

    def _count_word_intents(self, word: str, intent_map: dict) -> int:
        """统计一个词关联了多少个意图"""
        count = 0
        for intent, layers in intent_map.items():
            for layer, words in layers.items():
                if word in words:
                    count += 1
                    break
        return count

    # ─── IDF 衰减 ───

    def apply_idf_decay(self, weights_data: dict) -> dict:
        """对词权重施加 IDF 衰减

        公式 F4：IDF(word) = 1 / log₂(关联意图数 + 1)
        有效权重 = AI基础权重 × IDF(word)

        Args:
            weights_data: 完整权重词表（含意图映射表和词权重表）

        Returns:
            施加 IDF 后的权重词表（修改原数据并返回）
        """
        intent_map = weights_data.get('意图映射表', {})
        weight_table = weights_data.get('词权重表', {})

        # 统计每个词关联的意图数
        word_intent_count = defaultdict(int)
        for intent, layers in intent_map.items():
            seen_words = set()
            for layer, words in layers.items():
                for w in words:
                    if w not in seen_words:
                        word_intent_count[w] += 1
                        seen_words.add(w)

        # 施加 IDF
        for word, entry in weight_table.items():
            intent_count = word_intent_count.get(word, 1)
            idf = 1.0 / math.log2(intent_count + 1)

            if isinstance(entry, dict) and '权重' in entry:
                # 旧格式：全局权重
                base = entry['权重']
                entry['有效权重'] = round(base * idf, 4)
                entry['IDF'] = round(idf, 4)
                entry['关联意图数'] = intent_count
            elif isinstance(entry, dict):
                # 新格式：按意图的权重
                for intent_name, score_info in entry.items():
                    if isinstance(score_info, dict) and '权重' in score_info:
                        base = score_info['权重']
                        score_info['有效权重'] = round(base * idf, 4)
                        score_info['IDF'] = round(idf, 4)
                        score_info['关联意图数'] = intent_count

        return weights_data

    # ─── 反向校验 ───

    def reverse_validate(self, weights_data: dict,
                          benchmark_data: List[dict],
                          margin: float = 0.1) -> List[dict]:
        """反向校验：用标杆数据反推权重是否合理

        公式 F7：反向权重 = (标杆应得分 - 已知贡献) / 层级权重

        Args:
            weights_data: 权重词表
            benchmark_data: 标杆数据列表
            margin: 标杆应得分的安全边际

        Returns:
            偏差警告列表
        """
        intent_map = weights_data.get('意图映射表', {})
        weight_table = weights_data.get('词权重表', {})
        warnings = []

        for item in benchmark_data:
            benchmark = item.get('标杆意图', '')
            algo_intent = item.get('算法意图', '')
            is_match = item.get('是否一致', '')

            if is_match == '✓' or not benchmark:
                continue

            benchmark_features = intent_map.get(benchmark, {})
            if not benchmark_features:
                continue

            # 获取竞争意图得分
            detail = item.get('详情', {})
            all_scores = detail.get('全量意图得分_无阈值', [])
            algo_score = 0
            for s in all_scores:
                if s.get('意图') == algo_intent:
                    algo_score = s.get('得分', 0)
                    break

            target_score = algo_score + margin

            # 计算标杆意图当前已有分
            current_score = 0
            missing_words = []
            for layer, words in benchmark_features.items():
                layer_key = get_layer_key(layer)
                lw = self.layer_weights.get(layer_key, 0.6)
                for word in words:
                    ww = self._get_word_weight(word, benchmark, weight_table)
                    if ww > 0:
                        current_score += lw * ww
                    else:
                        missing_words.append((word, layer))

            gap = target_score - current_score
            if gap > 0.05:
                warning = {
                    '标杆意图': benchmark,
                    '算法意图': algo_intent,
                    '竞争得分': algo_score,
                    '需要达到': round(target_score, 4),
                    '当前得分': round(current_score, 4),
                    '差距': round(gap, 4),
                    '建议': ''
                }
                if missing_words:
                    suggested = round(
                        gap / max(len(missing_words), 1) /
                        self.layer_weights.get('L2', 0.8), 4)
                    suggested = min(suggested, 1.0)
                    warning['建议'] = (
                        f'为未打分词 {[w for w, _ in missing_words[:3]]} '
                        f'建议权重 ≥ {suggested}')
                else:
                    warning['建议'] = '所有词已打分但仍不够，需补充特征词'
                warnings.append(warning)

        return warnings

    def _get_word_weight(self, word: str, intent: str,
                          weight_table: dict) -> float:
        """获取词在特定意图下的权重（兼容新旧格式）"""
        entry = weight_table.get(word, {})
        if not entry:
            return 0
        if '权重' in entry:
            return entry.get('有效权重', entry['权重'])
        intent_entry = entry.get(intent, {})
        if intent_entry:
            return intent_entry.get('有效权重',
                                     intent_entry.get('权重', 0))
        return 0

    # ─── 变更日志 ───

    def generate_changelog(self, old_weights: dict,
                            new_weights: dict) -> str:
        """生成权重变更日志"""
        old_table = old_weights.get('词权重表', {})
        new_table = new_weights.get('词权重表', {})
        lines = []

        for word in set(list(old_table.keys()) + list(new_table.keys())):
            old_entry = old_table.get(word)
            new_entry = new_table.get(word)
            if old_entry is None:
                lines.append(f'[新增词] {word}')
            elif new_entry is None:
                lines.append(f'[删除词] {word}')
            elif old_entry != new_entry:
                lines.append(f'[变更] {word}')

        return '\n'.join(lines) if lines else '无变化'
