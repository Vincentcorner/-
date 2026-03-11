# -*- coding: utf-8 -*-
"""
全局词表管理模块

负责全局词表的 CRUD 操作，确保 JSON + Excel 双格式实时同步。
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import openpyxl
from openpyxl import Workbook


# 全局词表路径
_PROJECT_ROOT = Path(__file__).parent.parent.parent
VOCAB_DIR = _PROJECT_ROOT / 'result' / 'global' / 'weighted'
VOCAB_JSON = VOCAB_DIR / 'weighted_words.json'
VOCAB_EXCEL = VOCAB_DIR / 'weighted_words.xlsx'


def _ensure_dir():
    VOCAB_DIR.mkdir(parents=True, exist_ok=True)


def load() -> dict:
    """读取全局词表 JSON，不存在则返回空结构"""
    _ensure_dir()
    if VOCAB_JSON.exists():
        with open(VOCAB_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"意图映射表": {}, "词权重表": {}}


def save(data: dict):
    """同时写入 JSON 和 Excel（双写同步）"""
    _ensure_dir()
    # --- JSON ---
    with open(VOCAB_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # --- Excel ---
    _save_excel(data)


def _save_excel(data: dict):
    """将词表数据写为 Excel"""
    wb = Workbook()
    ws = wb.active
    ws.title = "全局词表"
    ws.append(["意图名称", "特征词", "层级", "公式权重", "备注"])

    intent_map = data.get("意图映射表", {})
    weight_map = data.get("词权重表", {})

    for intent, layers in intent_map.items():
        for layer, words in layers.items():
            for word in words:
                w_info = weight_map.get(word, {})
                formula_w = w_info.get("公式权重", {}).get(intent, "")
                if isinstance(formula_w, (int, float)):
                    formula_w = round(formula_w, 4)
                remark = w_info.get("备注", "")
                ws.append([intent, word, layer, formula_w, remark])

    # 列宽自适应
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            val = str(cell.value or "")
            max_len = max(max_len, len(val))
        ws.column_dimensions[col_letter].width = min(max_len + 4, 60)

    wb.save(str(VOCAB_EXCEL))


def add_word(intent: str, word: str, layer: str,
             remark: str = None) -> str:
    """
    人工补词

    Args:
        intent: 意图名称
        word: 特征词
        layer: 层级（核心词/发散词/同义词）
        remark: 自定义备注（默认自动生成）

    Returns:
        空字符串表示成功，否则返回错误信息
    """
    data = load()
    intent_map = data.setdefault("意图映射表", {})
    layers = intent_map.setdefault(intent, {})

    # 检查重复
    for existing_layer, words in layers.items():
        if word in words:
            return f"该特征词已存在于意图「{intent}」的「{existing_layer}」层级中"

    # 添加
    layer_words = layers.setdefault(layer, [])
    layer_words.append(word)

    # 备注
    if not remark:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        remark = f"人工补充@{ts}"
    weight_map = data.setdefault("词权重表", {})
    if word not in weight_map:
        weight_map[word] = {"公式权重": {}, "备注": remark}
    else:
        # 已有词条，追加备注
        old_remark = weight_map[word].get("备注", "")
        weight_map[word]["备注"] = f"{old_remark}; {remark}" if old_remark else remark

    save(data)
    return ""


def merge_intent_map(new_features: dict, source: str = "AI提取"):
    """
    将新提取的特征词合并到全局词表

    Args:
        new_features: {意图: {层级: [词]}}
        source: 来源标注
    """
    data = load()
    intent_map = data.setdefault("意图映射表", {})
    weight_map = data.setdefault("词权重表", {})
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    added_count = 0
    for intent, layers in new_features.items():
        existing = intent_map.setdefault(intent, {})
        for layer, words in layers.items():
            existing_words = existing.setdefault(layer, [])
            for word in words:
                if word not in existing_words:
                    existing_words.append(word)
                    added_count += 1
                    # 初始化词权重条目
                    if word not in weight_map:
                        weight_map[word] = {
                            "公式权重": {},
                            "备注": f"{source}@{ts}"
                        }

    save(data)
    return added_count


def update_formula_weights(weight_matrix: dict, remark_prefix: str = "冷启动"):
    """
    更新词权重表中的公式权重

    Args:
        weight_matrix: {词: {意图: 权重值}}
        remark_prefix: 备注前缀
    """
    data = load()
    weight_map = data.setdefault("词权重表", {})
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    for word, intent_weights in weight_matrix.items():
        if word not in weight_map:
            weight_map[word] = {"公式权重": {}, "备注": ""}
        weight_map[word]["公式权重"] = {
            intent: round(w, 4) for intent, w in intent_weights.items()
        }
        if remark_prefix == "冷启动":
            weight_map[word]["备注"] = f"冷启动@{ts}"

    save(data)


def update_corrected_weights(weight_matrix: dict, old_matrix: dict, weight_diff: dict):
    """
    纠偏后更新权重，增量追加备注

    Args:
        weight_matrix: 新权重 {词: {意图: W}}
        old_matrix: 旧权重 {词: {意图: W}}
        weight_diff: 变化 {词: {意图: {old, new, change, hit_count}}}
    """
    data = load()
    weight_map = data.setdefault("词权重表", {})
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    for word, intent_weights in weight_matrix.items():
        if word not in weight_map:
            weight_map[word] = {"公式权重": {}, "备注": ""}
        weight_map[word]["公式权重"] = {
            intent: round(w, 4) for intent, w in intent_weights.items()
        }

        # 如果有纠偏变化，追加备注
        if word in weight_diff:
            parts = []
            for intent, diff in weight_diff[word].items():
                parts.append(
                    f"{diff['old']}→{diff['new']},命中{diff['hit_count']}次"
                )
            correction_note = f"纠偏@{ts}: {'; '.join(parts)}"
            old_remark = weight_map[word].get("备注", "")
            weight_map[word]["备注"] = f"{old_remark}; {correction_note}" if old_remark else correction_note

    save(data)


def has_formula_weights() -> bool:
    """检查词权重表中是否已有公式权重"""
    data = load()
    weight_map = data.get("词权重表", {})
    for w_info in weight_map.values():
        fw = w_info.get("公式权重", {})
        if fw:
            return True
    return False


def get_excel_path() -> str:
    """返回 Excel 文件路径"""
    return str(VOCAB_EXCEL)


def get_all_words_and_intents() -> Tuple[List[str], List[str], dict]:
    """
    从全局词表提取所有词和意图列表

    Returns:
        (all_words, all_intents, intent_word_map)
    """
    data = load()
    intent_map = data.get("意图映射表", {})

    all_words = set()
    intent_word_map = {}

    for intent, layers in intent_map.items():
        words = []
        for layer, word_list in layers.items():
            words.extend(word_list)
            all_words.update(word_list)
        intent_word_map[intent] = words

    return list(all_words), list(intent_map.keys()), intent_word_map


def merge_from_excel(file_path: str, source: str = "Excel导入") -> dict:
    """
    从用户上传的 Excel 合并特征词到全局词表

    自动识别列名（支持多种格式）：
    - 意图名称 / 意图 / intent
    - 特征词 / 词 / word / keyword
    - 层级 / 类型 / layer / type（可选，默认"核心词"）

    Returns:
        {"added": 新增词数, "skipped": 跳过词数, "intents": 涉及意图数, "details": [...]}
    """
    import pandas as pd

    df = pd.read_excel(file_path)
    cols = list(df.columns)

    # 自动识别列名
    intent_col = None
    word_col = None
    layer_col = None

    for c in cols:
        cl = str(c).strip().lower()
        if cl in ('意图名称', '意图', '意图名', 'intent', 'intent_name'):
            intent_col = c
        elif cl in ('特征词', '词', '关键词', 'word', 'keyword', 'feature_word'):
            word_col = c
        elif cl in ('层级', '类型', '分类', 'layer', 'type', 'category'):
            layer_col = c

    if not intent_col:
        raise ValueError(f"未找到意图列，当前列名: {cols}。需要列名为: 意图名称/意图")
    if not word_col:
        raise ValueError(f"未找到特征词列，当前列名: {cols}。需要列名为: 特征词/词")

    data = load()
    intent_map = data.setdefault("意图映射表", {})
    weight_map = data.setdefault("词权重表", {})
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    added = 0
    skipped = 0
    details = []

    for _, row in df.iterrows():
        intent = str(row[intent_col]).strip()
        word = str(row[word_col]).strip()
        layer = str(row[layer_col]).strip() if layer_col and pd.notna(row.get(layer_col)) else "核心词"

        if not intent or not word or intent == 'nan' or word == 'nan':
            continue

        # 规范化层级名称
        layer_map = {
            '核心': '核心词', '核心词': '核心词', 'l1': '核心词',
            '发散': '发散词', '发散词': '发散词', 'l2': '发散词',
            '同义': '同义词', '同义词': '同义词', 'l3': '同义词',
        }
        layer = layer_map.get(layer.lower(), layer)

        # 合并
        existing = intent_map.setdefault(intent, {})
        layer_words = existing.setdefault(layer, [])

        if word in layer_words:
            skipped += 1
            continue

        layer_words.append(word)
        added += 1
        details.append(f"+ {intent} / {layer} / {word}")

        if word not in weight_map:
            weight_map[word] = {"公式权重": {}, "备注": f"{source}@{ts}"}

    save(data)

    intents_involved = len(set(
        str(row[intent_col]).strip() for _, row in df.iterrows()
        if str(row[intent_col]).strip() and str(row[intent_col]).strip() != 'nan'
    ))

    return {
        "added": added,
        "skipped": skipped,
        "intents": intents_involved,
        "details": details
    }

