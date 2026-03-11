# -*- coding: utf-8 -*-
"""
权重分计算模块（移植自 Demo1）

基于公式的权重分计算：embedding → cosine sim → IDF × Dirichlet关联度
支持冷启动和纠偏两种模式，带 embedding 缓存和 RPM 限流重试。
"""

import json
import math
import os
import time
import sys
import io
from pathlib import Path
from typing import Dict, List, Tuple, Callable, Optional

import numpy as np

# 添加项目根目录到路径
_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.llm_api import _load_api_key, _load_api_config

# ========== 配置 ==========
EMBEDDING_MODEL = "BAAI/bge-large-zh-v1.5"
EMBEDDING_BATCH_SIZE = 32
API_CALL_INTERVAL = 3  # 秒
DEFAULT_K = 5  # Dirichlet 平滑先验强度系数
CACHE_DIR = _PROJECT_ROOT / 'result' / 'global' / 'weighted'
CACHE_FILE = CACHE_DIR / 'embedding_cache.json'


# ========== 限流器 ==========
class RateLimiter:
    """API 调用频率控制器"""
    def __init__(self, interval=API_CALL_INTERVAL):
        self.interval = interval
        self.last_call = 0

    def wait(self):
        elapsed = time.time() - self.last_call
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self.last_call = time.time()


_rate_limiter = RateLimiter()


# ========== Embedding 缓存 ==========
_embedding_cache = {}


def _load_cache():
    global _embedding_cache
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                _embedding_cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            _embedding_cache = {}


def _save_cache():
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(_embedding_cache, f, ensure_ascii=False)
    except IOError:
        pass


# 启动时加载缓存
_load_cache()


def _get_embedding_client():
    """获取 OpenAI 客户端（用于 embedding）"""
    from openai import OpenAI
    api_key = _load_api_key()
    api_base, _ = _load_api_config()
    return OpenAI(api_key=api_key, base_url=api_base)


def get_embeddings(texts: list, progress_cb: Callable = None) -> dict:
    """
    批量获取文本的 embedding 向量（带缓存 + RPM 重试）

    Args:
        texts: 文本列表
        progress_cb: fn(message) 进度回调

    Returns:
        {文本: 向量列表}
    """
    result = {}
    uncached = []

    for text in texts:
        if text in _embedding_cache:
            result[text] = _embedding_cache[text]
        else:
            uncached.append(text)

    if not uncached:
        if progress_cb:
            progress_cb(f"全部 {len(texts)} 个文本已有缓存，无需调用API")
        return result

    client = _get_embedding_client()
    total_batches = (len(uncached) + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE

    if progress_cb:
        progress_cb(f"需请求 {len(uncached)} 个新embedding，分 {total_batches} 批（已缓存 {len(texts)-len(uncached)} 个）")

    for i in range(0, len(uncached), EMBEDDING_BATCH_SIZE):
        batch = uncached[i:i + EMBEDDING_BATCH_SIZE]
        batch_idx = i // EMBEDDING_BATCH_SIZE + 1

        if progress_cb:
            progress_cb(f"embedding 批次 {batch_idx}/{total_batches}，当前批 {len(batch)} 个文本...")

        # 带重试的 API 调用
        for attempt in range(5):
            _rate_limiter.wait()
            try:
                response = client.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=batch
                )
                break
            except Exception as e:
                err_str = str(e)
                if "RPM limit" in err_str or "403" in err_str or "429" in err_str:
                    wait_time = 15 * (attempt + 1)
                    msg = f"embedding 批次 {batch_idx}/{total_batches} RPM限流，等待 {wait_time}s 后重试 (第{attempt+1}次)"
                    print(f"[embedding] {msg}")
                    if progress_cb:
                        progress_cb(msg)
                    time.sleep(wait_time)
                else:
                    msg = f"embedding 批次 {batch_idx}/{total_batches} 请求失败: {e}"
                    print(f"[embedding] {msg}")
                    if progress_cb:
                        progress_cb(msg)
                    raise
        else:
            msg = f"embedding 批次 {batch_idx}/{total_batches} 重试5次仍失败，跳过"
            print(f"[embedding] {msg}")
            if progress_cb:
                progress_cb(msg)
            continue

        for j, item in enumerate(response.data):
            vec = item.embedding
            result[batch[j]] = vec
            _embedding_cache[batch[j]] = vec

        # 每5批或最后一批保存缓存
        if batch_idx % 5 == 0 or batch_idx == total_batches:
            _save_cache()
            if progress_cb:
                progress_cb(f"embedding 进度: {batch_idx}/{total_batches} 批完成，已保存缓存")

    _save_cache()
    return result


def cosine_similarity(vec_a: list, vec_b: list) -> float:
    a = np.array(vec_a)
    b = np.array(vec_b)
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return float(dot / norm) if norm != 0 else 0.0


def compute_sim_matrix(words: list, intents: list,
                       progress_cb: Callable = None) -> dict:
    """计算所有词与所有意图之间的 cosine similarity 矩阵"""
    all_texts = list(set(words + intents))

    if progress_cb:
        progress_cb(f"开始计算 sim 矩阵：{len(words)} 个词 × {len(intents)} 个意图")

    embeddings = get_embeddings(all_texts, progress_cb)

    sim_matrix = {}
    for word in words:
        sim_matrix[word] = {}
        for intent in intents:
            if word in embeddings and intent in embeddings:
                sim_matrix[word][intent] = cosine_similarity(
                    embeddings[word], embeddings[intent]
                )
            else:
                sim_matrix[word][intent] = 0.0

    if progress_cb:
        progress_cb(f"sim 矩阵计算完成: {len(words)}×{len(intents)}")

    return sim_matrix


# ========== 公式 F1-F3 ==========

def calc_idf(word: str, intent_word_map: dict, N: int = None) -> float:
    """F2: IDF(t) = log₂(N / df(t))"""
    if N is None:
        N = len(intent_word_map)
    if N == 0:
        return 0.0
    df = sum(1 for words in intent_word_map.values() if word in words)
    if df == 0:
        return 0.0
    return math.log2(N / df)


def calc_relevance(word: str, intent: str, sim_matrix: dict,
                   real_counts: dict, k: float, intents: list) -> float:
    """F3: Dirichlet 平滑关联度"""
    sim_ti = sim_matrix.get(word, {}).get(intent, 0.0)
    sum_sim = sum(sim_matrix.get(word, {}).get(i, 0.0) for i in intents)
    real_ti = real_counts.get(word, {}).get(intent, 0)
    real_any = sum(real_counts.get(word, {}).values()) if word in real_counts else 0

    numerator = real_ti + k * sim_ti
    denominator = real_any + k * sum_sim
    return (numerator / denominator) if denominator != 0 else 0.0


def build_weight_matrix(intent_word_map: dict, sim_matrix: dict,
                        real_counts: dict, k: float) -> dict:
    """对所有词×意图计算完整权重矩阵: W(t,I) = 关联度(t,I) × IDF(t)"""
    weight_matrix = {}
    intents = list(intent_word_map.keys())
    N = len(intents)

    all_words = set()
    for words in intent_word_map.values():
        all_words.update(words)

    for word in all_words:
        weight_matrix[word] = {}
        idf = calc_idf(word, intent_word_map, N)
        for intent in intents:
            if word in intent_word_map.get(intent, []):
                relevance = calc_relevance(word, intent, sim_matrix,
                                           real_counts, k, intents)
                weight_matrix[word][intent] = round(relevance * idf, 4)

    return weight_matrix


# ========== 高层接口 ==========

def cold_start(intent_word_map: dict, k: float = DEFAULT_K,
               progress_cb: Callable = None) -> dict:
    """
    冷启动：embedding → sim → IDF × rel → weight_matrix

    Returns:
        {
            "weight_matrix": {词: {意图: W}},
            "sim_matrix": {词: {意图: sim}},
            "idf_values": {词: idf}
        }
    """
    intents = list(intent_word_map.keys())
    all_words = list(set(w for ws in intent_word_map.values() for w in ws))

    if progress_cb:
        progress_cb(f"冷启动: {len(all_words)} 个词, {len(intents)} 个意图")

    # 计算 sim 矩阵
    sim_matrix = compute_sim_matrix(all_words, intents, progress_cb)

    if progress_cb:
        progress_cb("计算 IDF 和权重矩阵...")

    # 计算权重
    weight_matrix = build_weight_matrix(intent_word_map, sim_matrix, {}, k)
    idf_values = {w: calc_idf(w, intent_word_map) for w in all_words}

    if progress_cb:
        progress_cb(f"冷启动完成: 权重矩阵包含 {len(weight_matrix)} 个词")

    return {
        "weight_matrix": weight_matrix,
        "sim_matrix": sim_matrix,
        "idf_values": idf_values
    }


def correct(intent_word_map: dict, test_cases: list,
            sim_matrix: dict = None, old_weight_matrix: dict = None,
            k: float = DEFAULT_K,
            progress_cb: Callable = None) -> dict:
    """
    纠偏：用测试集命中数据重算权重

    Args:
        intent_word_map: {意图: [词]}
        test_cases: [{原始问, 标杆意图}]
        sim_matrix: 已有的sim矩阵（无则先冷启动）
        old_weight_matrix: 旧权重矩阵（用于计算diff）
        k: Dirichlet 参数
        progress_cb: 进度回调

    Returns:
        {
            "weight_matrix": 新权重,
            "weight_diff": 变化记录,
            "real_counts": 命中计数,
            "sim_matrix": sim矩阵
        }
    """
    intents = list(intent_word_map.keys())
    all_words = list(set(w for ws in intent_word_map.values() for w in ws))

    # 如果没有 sim 矩阵，先做冷启动
    if not sim_matrix:
        if progress_cb:
            progress_cb("无 sim 矩阵，先执行 embedding 计算...")
        sim_matrix = compute_sim_matrix(all_words, intents, progress_cb)

    if not old_weight_matrix:
        old_weight_matrix = build_weight_matrix(intent_word_map, sim_matrix, {}, k)

    if progress_cb:
        progress_cb(f"开始纠偏匹配: {len(test_cases)} 条测试数据")

    # 构建 real_counts: 子串匹配
    real_counts = {}
    sorted_words = sorted(all_words, key=len, reverse=True)

    for idx, case in enumerate(test_cases):
        question = case.get("原始问", case.get("测试问题", ""))
        benchmark = case.get("标杆意图", "")
        if not question or not benchmark:
            continue

        # 子串匹配
        for word in sorted_words:
            if word in question:
                if word in intent_word_map.get(benchmark, []):
                    if word not in real_counts:
                        real_counts[word] = {}
                    real_counts[word][benchmark] = real_counts[word].get(benchmark, 0) + 1

        if progress_cb and (idx + 1) % 20 == 0:
            progress_cb(f"纠偏匹配进度: {idx+1}/{len(test_cases)}")

    if progress_cb:
        progress_cb(f"纠偏匹配完成，共 {len(real_counts)} 个词有命中记录，重算权重...")

    # 重算权重
    new_wm = build_weight_matrix(intent_word_map, sim_matrix, real_counts, k)

    # 计算 diff
    weight_diff = {}
    for word, intent_data in new_wm.items():
        for intent, new_w in intent_data.items():
            old_w = old_weight_matrix.get(word, {}).get(intent, 0)
            if round(new_w, 4) != round(old_w, 4):
                if word not in weight_diff:
                    weight_diff[word] = {}
                weight_diff[word][intent] = {
                    "old": round(old_w, 4),
                    "new": round(new_w, 4),
                    "change": round(new_w - old_w, 4),
                    "hit_count": real_counts.get(word, {}).get(intent, 0)
                }

    if progress_cb:
        changed = sum(len(v) for v in weight_diff.values())
        progress_cb(f"纠偏完成: {changed} 个词×意图权重发生变化")

    return {
        "weight_matrix": new_wm,
        "weight_diff": weight_diff,
        "real_counts": real_counts,
        "sim_matrix": sim_matrix
    }
