# -*- coding: utf-8 -*-
"""
特征词自动提取器

支持两种模式：
A. 纯意图清单 → AI生成三维度特征词（核心词/发散词/同义词）
B. 匹配结果 → 从原始问/转写/标杆中提取特征词

分批调用 AI（5~10 意图/批），每批带全局意图上下文。
"""

import json
import math
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Union
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.common.llm_api import call_llm_api_json, DEFAULT_INTERVAL
from scripts.common.file_manager import FileManager
from scripts.common.config import ConfigManager


# 层级名称映射（新名→配置键）
LAYER_MAP = {
    '核心词': 'L1', '发散词': 'L2', '同义词': 'L3',
    'L1_事项词': 'L1', 'L2_动作词': 'L2', 'L3_场景词': 'L3',
    # 新提示词输出格式映射
    'core': 'L1', 'important': 'L2', 'related': 'L3',
}

BATCH_SIZE_EXTRACT = 8  # 每批提取的意图数


def get_layer_key(layer_name: str) -> str:
    """将层级名称统一转为配置键（L1/L2/L3）"""
    if layer_name in LAYER_MAP:
        return LAYER_MAP[layer_name]
    prefix = layer_name[:2]
    for name, key in LAYER_MAP.items():
        if name.startswith(prefix):
            return key
    return 'L3'


def _build_extract_prompt() -> str:
    """构建特征词提取的 system prompt（政务服务领域专家版）"""
    return """# 角色定位

请作为政务服务领域专家，根据提供的「意图名称」，严格按照以下规范提取特征词，确保提取结果准确、专业，贴合政务服务业务场景，同时保持各环节逻辑连贯、无遗漏。

# 提取规范

1. 分词规范：根据「意图名称」进行智能分词，形成特征词集合segments，需严格保持政务专业术语的完整性（例如"失业保险金""办理流程"等术语不可拆分，避免拆分后失去业务含义）。

2. 动宾识别：分析「意图名称」的动宾结构，从segments特征词集合中，准确筛选出表示动作的动词（action）和表示动作对象的宾语（object），确保动宾对应贴合意图核心。

3. 核心词提取：从segments特征词集合中，筛选出最能体现意图核心含义、不可或缺的词，组成核心词集合core（需覆盖意图名称的核心业务要素）。

4. 重要词提取：根据意图含义推断关键的业务细节词，组成重要词集合important，需注意与core核心词集合无重复，重点提取描述业务细节、办理要求的相关词汇（如流程、材料、具体信息项等）。

5. 相关词推测：站在**前来办事的群众（办理人）视角**，推测他们在咨询窗口或热线电话中**实际会怎么说、怎么问**，组成related相关词集合。必须包含以下三类表述：
   - 办理人视角词：办理人描述自身处境、诉求的用语（如"我被辞退了""我要领钱""我换了城市工作"）
   - 俗称/别称词：政务术语对应的民间通俗叫法（如"失业保险金"→"失业金""失业补贴"；"就业失业登记证"→"失业证"）
   - 口语化表述词：群众日常口头表达的非正式用语（如"没工作了""被开了""怎么办""去哪办""要带什么东西"）

6. 同义词整理：梳理core核心词集合和important重要词集合中所有词汇的同义词、近义词、简称与全称、通俗叫法与规范叫法，形成synonyms同义词节点，确保同义词贴合政务服务场景，准确对应原词含义，不添加无关词汇。

# 输出要求

对每个意图，严格按照以下JSON格式输出：

```json
{
  "意图映射表": {
    "意图名称": {
      "segments": ["失业保险金", "申领"],
      "object": "失业保险金",
      "action": "申领",
      "keywords": {
        "core": ["失业保险金", "申领"],
        "important": ["失业人员", "申请", "领取"],
        "related": ["领失业金", "被辞退了", "没工作了", "怎么领钱", "失业补贴", "被开除", "去哪里办", "要带什么"]
      },
      "synonyms": {
        "失业保险金": ["失业金", "失业补助金", "失业补贴"],
        "申领": ["申请", "办理", "领取", "领"]
      }
    }
  }
}
```

# 注意事项

- 同一个词可以出现在多个意图下
- 每个意图的每个层级至少提取1个词
- core核心词通常最少（1-3个），related相关词应尽量丰富（至少5个以上），充分覆盖群众口语表达
- 去除虚词（"的""了"等助词），但保留有实际含义的口语化短语（如"怎么办""去哪办"）
- 保持简洁，每个词不超过6个字
- related相关词的核心原则：想象一个普通群众打12345热线或到窗口咨询时会怎么说，用他们的语言来提取
"""



def _build_extract_from_results_prompt() -> str:
    """构建从匹配结果中提取特征词的 system prompt"""
    return """你是一个特征词提取专家。我会给你一批意图匹配失败的案例，每条包含：原始问、标杆意图、三层转写结果。

你的任务是从这些文本中提取特征词，补充到标杆意图的特征词库中。

提取规则：
1. **核心词**：原始问/转写中出现的、直接指向标杆意图的专业术语
2. **发散词**：口语化表达、接近标杆意图的动作词或搭配
3. **同义词**：如果只能提取到模糊的词，放到同义词层
4. 优先提取核心词，提取不到核心词就提取发散词
5. 一个词只归入一个层级

请输出JSON格式：
```json
{
  "意图映射表": {
    "标杆意图名1": {
      "核心词": ["词1"],
      "发散词": ["词2", "词3"],
      "同义词": ["词4"]
    }
  }
}
```"""



def _convert_new_format(intent_data: dict) -> dict:
    """将新格式AI输出转换为内部三层格式（核心词/发散词/同义词）

    新格式: {segments, object, action, keywords: {core, important, related}, synonyms: {词: [同义词]}}
    内部格式: {核心词: [...], 发散词: [...], 同义词: [...]}
    """
    # 如果已经是旧格式（含 核心词/发散词/同义词 键），直接返回
    if '核心词' in intent_data or 'L1_事项词' in intent_data:
        return intent_data

    keywords = intent_data.get('keywords', {})
    synonyms_map = intent_data.get('synonyms', {})

    # 核心词 = core
    core_words = list(keywords.get('core', []))

    # 发散词 = important + related（去重）
    important_words = list(keywords.get('important', []))
    related_words = list(keywords.get('related', []))
    diverge_words = important_words + [w for w in related_words if w not in important_words]

    # 同义词 = synonyms 字典中所有同义词展平去重（排除已在核心词/发散词中的）
    synonym_words = []
    for original, syns in synonyms_map.items():
        for s in syns:
            if s not in core_words and s not in diverge_words and s not in synonym_words:
                synonym_words.append(s)

    return {
        '核心词': core_words,
        '发散词': diverge_words,
        '同义词': synonym_words,
    }


class FeatureExtractor:
    """特征词自动提取器

    支持两种模式：
    A. 纯意图清单 → AI生成特征词
    B. 匹配结果 → 从文本中提取特征词（仅处理权重缺失/特征词未命中）
    """

    def __init__(self, file_manager: FileManager = None,
                 config: ConfigManager = None):
        self.file_manager = file_manager or FileManager()
        self.config = config or ConfigManager()

    # ─── 模式A：从意图清单生成 ───

    def extract_from_intents(self, intents: List[str],
                              progress_callback=None,
                              intent_descriptions: dict = None) -> dict:
        """从意图清单AI生成特征词（政务服务领域专家版）

        Args:
            intents: 意图名称列表
            progress_callback: fn(current, total, message)
            intent_descriptions: 可选，{意图名: 描述文本} 映射

        Returns:
            {"意图映射表": {意图名: {核心词: [...], 发散词: [...], 同义词: [...]}}}
        """
        result_map = {}
        total_batches = math.ceil(len(intents) / BATCH_SIZE_EXTRACT)
        system_prompt = _build_extract_prompt()

        for batch_idx in range(total_batches):
            start = batch_idx * BATCH_SIZE_EXTRACT
            end = min(start + BATCH_SIZE_EXTRACT, len(intents))
            batch = intents[start:end]

            if progress_callback:
                progress_callback(batch_idx + 1, total_batches,
                                  f'提取特征词 [{batch_idx+1}/{total_batches}]：{batch[0]}...')

            # 构建意图信息（含描述，如有）
            intent_info = []
            for name in batch:
                desc = (intent_descriptions or {}).get(name, '')
                if desc:
                    intent_info.append(f'- 意图名称：{name}\n  意图描述：{desc}')
                else:
                    intent_info.append(f'- 意图名称：{name}')

            user_content = f"""全部意图列表（共{len(intents)}个）：
{json.dumps(intents, ensure_ascii=False)}

请为以下意图提取特征词：

{chr(10).join(intent_info)}"""

            ai_result = call_llm_api_json(system_prompt, user_content)
            if ai_result and '意图映射表' in ai_result:
                for name, layers in ai_result['意图映射表'].items():
                    # 自动转换新格式→内部三层格式
                    result_map[name] = _convert_new_format(layers)

            if batch_idx < total_batches - 1:
                time.sleep(DEFAULT_INTERVAL)

        return {'意图映射表': result_map}

    # ─── 模式B：从匹配结果提取 ───

    def extract_from_match_results(self, results: List[dict],
                                    progress_callback=None) -> dict:
        """从匹配分析结果中提取特征词

        仅处理诊断类别为"权重分表意图不全"和"特征词未命中"的行。

        Args:
            results: 分析结果列表（从 Excel 解析的 dict 列表）
            progress_callback: fn(current, total, message)

        Returns:
            {"意图映射表": {标杆意图: {核心词/发散词/同义词: [...]}}}
        """
        actionable = self._filter_actionable(results)
        if not actionable:
            return {'意图映射表': {}}

        result_map = {}
        total_batches = math.ceil(len(actionable) / BATCH_SIZE_EXTRACT)
        system_prompt = _build_extract_from_results_prompt()

        for batch_idx in range(total_batches):
            start = batch_idx * BATCH_SIZE_EXTRACT
            end = min(start + BATCH_SIZE_EXTRACT, len(actionable))
            batch = actionable[start:end]

            if progress_callback:
                progress_callback(batch_idx + 1, total_batches,
                                  f'从结果提取 [{batch_idx+1}/{total_batches}]')

            cases = []
            for item in batch:
                case = {
                    '原始问': item.get('原始问题', ''),
                    '标杆意图': item.get('标杆意图', ''),
                    '转写结果': item.get('转写结果', ''),
                }
                cases.append(case)

            user_content = f"""以下是需要补充特征词的失败案例：
{json.dumps(cases, ensure_ascii=False, indent=2)}

请从原始问和转写结果中提取特征词，归入标杆意图的核心词/发散词/同义词三个层级。"""

            ai_result = call_llm_api_json(system_prompt, user_content)
            if ai_result and '意图映射表' in ai_result:
                for name, layers in ai_result['意图映射表'].items():
                    if name in result_map:
                        for layer, words in layers.items():
                            existing = result_map[name].get(layer, [])
                            result_map[name][layer] = list(set(existing + words))
                    else:
                        result_map[name] = layers

            if batch_idx < total_batches - 1:
                time.sleep(DEFAULT_INTERVAL)

        return {'意图映射表': result_map}

    def _filter_actionable(self, results: List[dict]) -> List[dict]:
        """筛选可自动处理的行（权重缺失 / 特征词未命中）"""
        actionable = []
        for r in results:
            diag = r.get('分析结果', '') or r.get('诊断分析', '')
            diag_type = ''
            if isinstance(diag, dict):
                diag_type = diag.get('诊断类别', '')
            elif isinstance(diag, str):
                if '权重分表意图不全' in diag:
                    diag_type = '权重分表意图不全'
                elif '特征词未命中' in diag:
                    diag_type = '特征词未命中'
            if diag_type in ('权重分表意图不全', '特征词未命中'):
                actionable.append(r)
        return actionable

    # ─── 合并到权重词表 ───

    def merge_into_weights(self, new_features: dict,
                            weights_path: str) -> dict:
        """将新提取的特征词增量合并到现有权重词表

        支持冷启动：如果 weights_path 文件不存在，自动初始化空词表。
        如果 new_features 中包含 '词权重表'（AI打分结果），优先使用AI分数。

        Returns:
            {"changelog": str, "stats": dict, "merged_data": dict}
        """
        p = Path(weights_path)
        if p.exists():
            weights_data = self.file_manager.load_json(p)
        else:
            # 冷启动：文件不存在，初始化空词表
            weights_data = {'意图映射表': {}, '词权重表': {}}
        existing_map = weights_data.get('意图映射表', {})
        existing_weights = weights_data.get('词权重表', {})

        new_map = new_features.get('意图映射表', {})
        new_weights = new_features.get('词权重表', {})  # AI打分结果
        changelog_lines = []
        new_word_count = 0
        new_intent_count = 0

        def _get_ai_weight(word):
            """从AI打分结果中获取权重，返回 {权重, 理由} 或默认值"""
            if word in new_weights:
                w_info = new_weights[word]
                # 新格式：{意图: {权重, 理由}} → 取第一个意图的分数
                if isinstance(w_info, dict) and '权重' not in w_info:
                    for intent_name, score_info in w_info.items():
                        if isinstance(score_info, dict) and '权重' in score_info:
                            return score_info
                # 旧格式：{权重, 理由}
                if isinstance(w_info, dict) and '权重' in w_info:
                    return w_info
            return {'权重': 0.5, '理由': '待AI打分'}

        for intent, layers in new_map.items():
            if intent not in existing_map:
                existing_map[intent] = layers
                new_intent_count += 1
                changelog_lines.append(f'[新增意图] {intent}')
                for layer, words in layers.items():
                    for w in words:
                        new_word_count += 1
                        changelog_lines.append(f'  + {layer}: {w}')
                        if w not in existing_weights:
                            existing_weights[w] = _get_ai_weight(w)
            else:
                for layer, words in layers.items():
                    existing_layer = existing_map[intent].get(layer, [])
                    for w in words:
                        if w not in existing_layer:
                            existing_layer.append(w)
                            new_word_count += 1
                            changelog_lines.append(
                                f'[补充] {intent} → {layer}: {w}')
                            if w not in existing_weights:
                                existing_weights[w] = _get_ai_weight(w)
                    existing_map[intent][layer] = existing_layer

        weights_data['意图映射表'] = existing_map
        weights_data['词权重表'] = existing_weights

        return {
            'changelog': '\n'.join(changelog_lines) if changelog_lines else '无变化',
            'stats': {
                '新增意图数': new_intent_count,
                '新增特征词数': new_word_count,
                '总意图数': len(existing_map),
                '总词数': len(existing_weights)
            },
            'merged_data': weights_data
        }

    # ─── 兼容旧工作流 ───

    def load_intent_list(self, file_path: Union[str, Path]) -> List[Dict]:
        """加载意图清单文件"""
        return self.file_manager.load_intent_list(file_path)

    def prepare_for_ai(self, intent_list: List[Dict]) -> str:
        """准备AI分析输入（兼容旧工作流）"""
        intents = []
        for item in intent_list:
            name = (item.get("意图名称") or item.get("意图")
                    or item.get("name", ""))
            intents.append(name)
        prompt = _build_extract_prompt()
        return f"{prompt}\n\n请为以下意图生成特征词：\n{json.dumps(intents, ensure_ascii=False)}"
