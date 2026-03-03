# -*- coding: utf-8 -*-
"""
意图匹配 Web UI

Flask 后端：上传 Excel → 三维度转写 → AC匹配 → AI筛选 → 结果展示/下载
"""

import json
from datetime import datetime
import sys
import io
import os
import time
import uuid
import threading
import traceback
from pathlib import Path
from datetime import datetime
from queue import Queue

# Windows 终端编码修复
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask, request, jsonify, render_template, Response, send_file
import pandas as pd

from scripts.common.file_manager import FileManager
from scripts.common.config import ConfigManager
from scripts.common.llm_api import call_llm_api, call_llm_api_json, DEFAULT_INTERVAL
from scripts.modules.query_segmenter import QuerySegmenter
from scripts.modules.weight_calculator import WeightCalculator

app = Flask(__name__, template_folder=str(Path(__file__).parent / 'templates'))
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

# 上传目录
UPLOAD_DIR = project_root / 'uploads'
UPLOAD_DIR.mkdir(exist_ok=True)

# 全局任务状态
tasks = {}


# CORS + 全局错误处理
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


@app.errorhandler(Exception)
def handle_exception(e):
    tb = traceback.format_exc()
    print(f"[全局错误] {e}\n{tb}")
    return jsonify({'error': f'服务器错误: {str(e)}'}), 500


@app.errorhandler(413)
def handle_large_file(e):
    return jsonify({'error': '文件太大，最大支持 50MB'}), 413


# ===== 复用 batch_intent_match.py 的核心函数 =====

def load_rewrite_prompt() -> str:
    """加载三维度转写提示词"""
    prompt_path = project_root / "prompts" / "query_rewrite_3d_prompt.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"提示词文件不存在: {prompt_path}")
    with open(prompt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    lines = content.split('\n')
    in_block = False
    block_lines = []
    block_depth = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('```'):
            if not in_block:
                in_block = True
                block_depth = 1
                continue
            elif stripped == '```' and block_depth == 1:
                break
            else:
                if stripped == '```':
                    block_depth -= 1
                else:
                    block_depth += 1
                block_lines.append(line.rstrip('\r'))
        elif in_block:
            block_lines.append(line.rstrip('\r'))
    return '\n'.join(block_lines).strip() if block_lines else content


def load_intent_select_prompt() -> str:
    """加载意图筛选提示词"""
    prompt_path = project_root / "prompts" / "intent_select_prompt.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"提示词文件不存在: {prompt_path}")
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()


def match_4d(segmenter, calculator, rewrite_results: dict,
             raw_query: str, domain: str, intent_map: dict = None) -> tuple:
    """四路并行匹配：原始问 + 三维度转写
    
    公式 F5: 意图最终得分 = max(四路得分)
    公式 F6: 增强得分 = 基础得分 × (1 + 0.1 × (命中维度数 - 1))
    
    返回:
        results: 经阈值过滤后的意图列表
        all_hit_words: 所有命中词映射
        results_all: 全量意图列表（threshold=0）
    """
    intent_best = {}
    intent_best_all = {}
    all_hit_words = {}
    dim_hit_count = {}  # 统计每个意图命中了几个维度
    
    match_sources = {
        'raw_query': raw_query,
        'scenario': rewrite_results.get('scenario', ''),
        'plain_language': rewrite_results.get('plain_language', ''),
        'official_expression': rewrite_results.get('official_expression', ''),
    }
    
    for dim, text in match_sources.items():
        if not text or text == '无具体情形':
            continue
        matched_words = segmenter.segment(text, domain)
        # 阈值压到最低，获取全量意图
        intent_scores = calculator.calculate_with_config(
            matched_words, threshold=0, top_k=999, domain=domain
        )
        intent_scores_all = intent_scores  # 全量模式下两者等价
        for item in intent_scores:
            name = item['意图']
            if name not in intent_best or item['得分'] > intent_best[name]['得分']:
                intent_best[name] = item
            dim_hit_count.setdefault(name, set()).add(dim)
            for detail in item.get('命中详情', []):
                all_hit_words.setdefault(name, set()).add(detail['词'])
        for item in intent_scores_all:
            name = item['意图']
            if name not in intent_best_all or item['得分'] > intent_best_all[name]['得分']:
                intent_best_all[name] = item
            for detail in item.get('命中详情', []):
                all_hit_words.setdefault(name, set()).add(detail['词'])
    
    # 多源命中加分 (F6)
    for name, item in intent_best.items():
        hit_dims = len(dim_hit_count.get(name, set()))
        if hit_dims > 1:
            item['得分'] = round(item['得分'] * (1 + 0.1 * (hit_dims - 1)), 4)
    
    results = sorted(intent_best.values(), key=lambda x: x['得分'], reverse=True)
    results_all = sorted(intent_best_all.values(), key=lambda x: x['得分'], reverse=True)
    return results, all_hit_words, results_all


def format_intent_features(all_hit_words: dict, top_intents: list) -> str:
    parts = []
    for item in top_intents:
        name = item['意图']
        score = item['得分']
        words = all_hit_words.get(name, set())
        if words:
            parts.append(f"{name}({score:.2f})（{'、'.join(sorted(words))}）")
        else:
            parts.append(f"{name}({score:.2f})")
    return '、'.join(parts)


def format_rewrite_display(rewrite_results: dict) -> str:
    scenario = rewrite_results.get('scenario', '')
    plain = rewrite_results.get('plain_language', '')
    official = rewrite_results.get('official_expression', '')
    parts = []
    if scenario:
        parts.append(f"[情形] {scenario}")
    if plain:
        parts.append(f"[群众语言] {plain}")
    if official:
        parts.append(f"[官方表达] {official}")
    return ' | '.join(parts)


def ai_select_intent(question, rewrite_display, top_intents, all_hit_words, select_prompt):
    """AI筛选最终意图"""
    candidates_text = []
    for idx, item in enumerate(top_intents, 1):
        name = item['意图']
        score = item['得分']
        words = all_hit_words.get(name, set())
        words_str = '、'.join(sorted(words)) if words else '无'
        candidates_text.append(f"{idx}. {name}（得分: {score:.2f}, 命中词: {words_str}）")

    user_content = f"""用户诉求：{question}

转写结果：{rewrite_display}

候选意图：
{chr(10).join(candidates_text)}

请从以上候选意图中选择最匹配用户诉求的意图。"""

    result = call_llm_api_json(select_prompt, user_content)

    if result and '选中意图' in result:
        selected = result['选中意图']
        confidence = result.get('置信度', 0.8)
        valid_names = [item['意图'] for item in top_intents]
        if selected in valid_names:
            return selected, int(min(confidence * 100, 99))
        else:
            for name in valid_names:
                if selected in name or name in selected:
                    return name, int(min(confidence * 100, 99))

    return top_intents[0]['意图'], int(min(80 + top_intents[0]['得分'] * 10, 99))


def _find_benchmark_in_set(benchmark, name_set):
    """在名称集合中查找与标杆意图最匹配的名称
    
    匹配策略（优先级从高到低）：
    1. 完全相等
    2. 子串包含
    3. 共享关键词（去掉常见前缀后匹配）
    """
    if benchmark in name_set:
        return benchmark

    # 子串包含
    for name in name_set:
        if benchmark in name or name in benchmark:
            return name

    # 去掉常见动词前缀后匹配核心词
    prefixes = ['了解', '办理', '查询', '申请', '咨询', '申领', '领取', '获取', '查看', '知道']
    benchmark_core = benchmark
    for p in prefixes:
        if benchmark.startswith(p):
            benchmark_core = benchmark[len(p):]
            break
    if benchmark_core and benchmark_core != benchmark:
        for name in name_set:
            name_core = name
            for p in prefixes:
                if name.startswith(p):
                    name_core = name[len(p):]
                    break
            if benchmark_core == name_core:
                return name

    return None


def _format_diagnosis_display(diagnosis):
    """将结构化诊断 dict 转为前端展示文本，兼容旧格式 str"""
    if isinstance(diagnosis, str):
        return diagnosis
    if isinstance(diagnosis, dict):
        category = diagnosis.get('诊断类别', '')
        detail = diagnosis.get('诊断详情', '')
        coverage = diagnosis.get('转写覆盖度', 0)
        competitor = diagnosis.get('竞争意图', '')
        suggestions = diagnosis.get('修复建议', [])
        parts = [f'[{category}] {detail}']
        if coverage > 0:
            parts.append(f'覆盖度: {coverage:.0%}')
        if competitor:
            parts.append(f'竞争意图: {competitor}')
        if suggestions:
            sep = '、'
            parts.append(f'建议: {sep.join(suggestions)}')
        return ' | '.join(parts)
    return str(diagnosis)


def diagnose_mismatch(is_match, algo_intent, benchmark, top_intents, all_hit_words,
                       weights_intent_set, segmenter, calculator, domain, weights_data=None,
                       all_intents_unfiltered=None):
    """增强版诊断分析 — 返回结构化 dict
    
    返回格式:
        {
            '诊断类别': str,
            '诊断详情': str,
            '转写覆盖度': float,
            '竞争意图': str,
            '竞争得分差': float,
            '修复建议': list
        }
    """
    def _result(category, detail, coverage=0.0, competitor='', score_diff=0.0, suggestions=None):
        return {
            '诊断类别': category,
            '诊断详情': detail,
            '转写覆盖度': round(coverage, 4),
            '竞争意图': competitor,
            '竞争得分差': round(score_diff, 4),
            '修复建议': suggestions or []
        }
    
    if is_match == '✓':
        return _result('一致', '✓ 算法意图与标杆意图一致')
    if not benchmark:
        return _result('无标杆', '⚠ 无标杆意图，无法诊断')
    
    all_intent_names = [x['意图'] for x in top_intents]
    # 全量候选列表（无阈值过滤）用于更准确的诊断
    all_unfiltered_names = [x['意图'] for x in (all_intents_unfiltered or [])]
    competitor = top_intents[0]['意图'] if top_intents else ''
    competitor_score = top_intents[0]['得分'] if top_intents else 0
    
    # 计算覆盖度 (F8)
    coverage = 0.0
    benchmark_features_all = []
    if weights_data:
        layers = weights_data.get('意图映射表', {}).get(benchmark, {})
        if not layers:
            # 尝试模糊匹配
            bw = _find_benchmark_in_set(benchmark, weights_intent_set)
            if bw:
                layers = weights_data.get('意图映射表', {}).get(bw, {})
        for layer, words in layers.items():
            benchmark_features_all.extend(words)
        if benchmark_features_all:
            hit = all_hit_words.get(benchmark, set())
            if not hit:
                bw = _find_benchmark_in_set(benchmark, set(all_hit_words.keys()))
                if bw:
                    hit = all_hit_words.get(bw, set())
            coverage = len(hit & set(benchmark_features_all)) / len(benchmark_features_all) if benchmark_features_all else 0
    
    # Step 1a: 标杆意图是否在归一化过滤后的候选列表中？
    matched_candidate = _find_benchmark_in_set(benchmark, set(all_intent_names))
    if matched_candidate:
        matched_item = next((x for x in top_intents if x['意图'] == matched_candidate), None)
        score_info = f'（得分{matched_item["得分"]:.2f}）' if matched_item else ''
        benchmark_score = matched_item['得分'] if matched_item else 0
        return _result(
            '大模型筛选问题',
            f'标杆意图「{benchmark}」存在于候选列表{score_info}但未被AI选中，AI选择了「{algo_intent}」',
            coverage, competitor, competitor_score - benchmark_score,
            ['优化意图筛选 prompt', '检查意图名称相似度'])
    
    # Step 1b: 标杆意图是否在全量候选列表（无阈值过滤）中？
    matched_in_unfiltered = _find_benchmark_in_set(benchmark, set(all_unfiltered_names))
    if matched_in_unfiltered:
        matched_item = next((x for x in (all_intents_unfiltered or []) if x['意图'] == matched_in_unfiltered), None)
        score_info = f'（原始得分{matched_item["得分"]:.2f}）' if matched_item else ''
        benchmark_score = matched_item['得分'] if matched_item else 0
        return _result(
            '算法筛选问题',
            f'标杆意图「{benchmark}」在全量候选中{score_info}，但算法最终选择了「{algo_intent}」。可能是归一化阈值或AI筛选导致',
            coverage, competitor, competitor_score - benchmark_score if matched_item else competitor_score,
            ['检查归一化阈值是否过高', '优化AI筛选 prompt', '调整特征词权重'])
    
    # Step 2: 标杆意图是否在权重词表中？
    benchmark_weight_name = _find_benchmark_in_set(benchmark, weights_intent_set)
    if not benchmark_weight_name:
        return _result(
            '权重分表意图不全',
            f'标杆意图「{benchmark}」不在权重词表的意图映射中',
            coverage, competitor, competitor_score,
            [f'为标杆意图「{benchmark}」添加特征词'])
    
    # Step 3: 查找标杆意图的实际命中情况
    benchmark_hit_words = all_hit_words.get(benchmark_weight_name, set())
    benchmark_score = 0
    for item in top_intents:
        if item['意图'] == benchmark_weight_name:
            benchmark_score = item['得分']
            break
    
    if benchmark_score > 0:
        hit_str = '、'.join(sorted(benchmark_hit_words)) if benchmark_hit_words else '无'
        return _result(
            'topK取得不全',
            f'标杆意图「{benchmark}」有得分({benchmark_score:.2f})但未进入Top候选列表。命中词: {hit_str}',
            coverage, competitor, competitor_score - benchmark_score,
            ['增大 top_k 或调低阈值'])
    
    if benchmark_hit_words:
        hit_str = '、'.join(sorted(benchmark_hit_words))
        return _result(
            'topK取得不全',
            f'标杆意图「{benchmark}」命中了特征词（{hit_str}），但得分未进入Top候选列表',
            coverage, competitor, competitor_score,
            ['调整权重或补充高权重特征词'])
    
    # Step 3c: 特征词完全未命中
    benchmark_features = []
    if weights_data:
        layers = weights_data.get('意图映射表', {}).get(benchmark_weight_name, {})
        for layer, words in layers.items():
            benchmark_features.extend(words)
    
    if benchmark_features:
        feature_str = '、'.join(sorted(set(benchmark_features))[:10])
        return _result(
            '特征词未命中',
            f'标杆意图「{benchmark}」的特征词【{feature_str}】在转写结果中未出现，AC自动机未匹配',
            coverage, competitor, competitor_score,
            ['补充发散词/同义词', '优化转写 prompt 覆盖更多表述'])
    
    return _result(
        '特征词匹配不足',
        f'标杆意图「{benchmark}」在权重词表中存在但未命中有效特征词',
        coverage, competitor, competitor_score,
        ['检查特征词覆盖度'])


# ===== 后台任务 =====

def run_intent_match_task(task_id: str, file_path: str, domain: str, count: int,
                          weights_path: str, start: int = 0,
                          original_filename: str = ''):
    """后台执行意图匹配"""
    task = tasks[task_id]
    msg_queue = task['queue']

    def send(event, data):
        msg_queue.put({'event': event, 'data': data})

    try:
        send('status', {'phase': 'init', 'message': '初始化中...'})

        # 读取Excel
        df = pd.read_excel(file_path)
        df_subset = df.iloc[start:start + count]

        raw_col = '原始问' if '原始问' in df.columns else df.columns[0]
        benchmark_col = None
        for col in df.columns:
            if '意图' in col and '领域' not in col:
                benchmark_col = col
                break

        total = len(df_subset)
        start_display = start + 1  # 1-indexed for display
        end_display = start + total
        send('status', {
            'phase': 'loaded',
            'message': f'已加载第 {start_display}~{end_display} 行，共 {total} 条数据（列: {raw_col}）',
            'total': total,
            'raw_col': raw_col,
            'benchmark_col': benchmark_col or '(无)',
            'columns': list(df.columns)
        })

        # 初始化分词器
        file_manager = FileManager()
        config = ConfigManager()
        segmenter = QuerySegmenter(file_manager, config)
        segmenter.load_and_build(Path(weights_path))
        calculator = WeightCalculator(file_manager, config)

        # 加载权重JSON获取意图列表（用于诊断分析）
        weights_data = file_manager.load_json(Path(weights_path))
        weights_intent_set = set(weights_data.get('意图映射表', {}).keys())

        # 加载提示词
        rewrite_prompt = load_rewrite_prompt()
        intent_select_prompt = None
        try:
            intent_select_prompt = load_intent_select_prompt()
            send('status', {'phase': 'ready', 'message': '提示词加载完成，开始转写...'})
        except FileNotFoundError:
            send('status', {'phase': 'ready', 'message': '未找到意图筛选提示词，将仅使用算法Top-1'})

        # Step 1: 三维度转写
        questions = []
        for _, row in df_subset.iterrows():
            q = str(row[raw_col]) if pd.notna(row[raw_col]) else ''
            questions.append(q)

        rewrite_data = {}
        for i, question in enumerate(questions):
            if not question:
                continue
            send('progress', {
                'phase': 'rewrite',
                'current': i + 1,
                'total': total,
                'message': f'转写 [{i+1}/{total}]: {question[:30]}...'
            })

            result = call_llm_api_json(rewrite_prompt, question)
            if result and 'rewrite_results' in result:
                rr = result['rewrite_results']
                rewrite_data[question] = rr
            else:
                rewrite_data[question] = {
                    'scenario': '(转写失败)',
                    'plain_language': '(转写失败)',
                    'official_expression': '(转写失败)'
                }

            if i < len(questions) - 1:
                time.sleep(DEFAULT_INTERVAL)

        send('status', {'phase': 'match_start', 'message': f'转写完成 ({len(rewrite_data)}/{total})，开始意图匹配...'})

        # Step 2: AC匹配 + AI筛选
        results = []
        for i, row in df_subset.iterrows():
            idx = len(results)
            raw_query = str(row[raw_col]) if pd.notna(row[raw_col]) else ''
            benchmark = str(row[benchmark_col]) if benchmark_col and pd.notna(row[benchmark_col]) else ''

            rewrite_results = rewrite_data.get(raw_query, {})

            if rewrite_results and rewrite_results.get('scenario') != '(转写失败)':
                top_intents, all_hit_words, all_intents_unfiltered = match_4d(
                    segmenter, calculator, rewrite_results, raw_query, domain,
                    weights_data.get('意图映射表'))
                rewrite_display = format_rewrite_display(rewrite_results)
            else:
                rewrite_display = raw_query[:80]
                matched_words = segmenter.segment(raw_query, domain)
                # 全量模式：阈值压到最低
                top_intents = calculator.calculate_with_config(
                    matched_words, threshold=0, top_k=999, domain=domain
                ) if matched_words else []
                all_intents_unfiltered = top_intents
                all_hit_words = {}
                for m in matched_words:
                    all_hit_words.setdefault(m['意图'], set()).add(m['词'])



            if not top_intents and all_intents_unfiltered:
                # 归一化后无候选，但全量匹配有结果 → 回退到全量候选
                if intent_select_prompt:
                    send('progress', {
                        'phase': 'match',
                        'current': idx + 1,
                        'total': total,
                        'message': f'AI筛选(回退) [{idx+1}/{total}]: {raw_query[:30]}...'
                    })
                    algo_intent, _confidence = ai_select_intent(
                        raw_query, rewrite_display,
                        all_intents_unfiltered,
                        all_hit_words, intent_select_prompt
                    )
                    time.sleep(DEFAULT_INTERVAL)
                else:
                    algo_intent = all_intents_unfiltered[0]['意图']
            elif not top_intents:
                algo_intent = '(无匹配)'
            elif intent_select_prompt and (
                len(top_intents) >= 2 or
                (len(top_intents) == 1 and top_intents[0]['得分'] < 0.7)
            ):
                # 扩展AI筛选触发：多候选 或 单候选低置信度
                send('progress', {
                    'phase': 'match',
                    'current': idx + 1,
                    'total': total,
                    'message': f'AI筛选 [{idx+1}/{total}]: {raw_query[:30]}...'
                })
                algo_intent, _confidence = ai_select_intent(
                    raw_query, rewrite_display,
                    all_intents_unfiltered if all_intents_unfiltered else top_intents,
                    all_hit_words, intent_select_prompt
                )
                time.sleep(DEFAULT_INTERVAL)
            else:
                algo_intent = top_intents[0]['意图']

            send('progress', {
                'phase': 'match',
                'current': idx + 1,
                'total': total,
                'message': f'匹配 [{idx+1}/{total}]: {algo_intent}'
            })



            # 全量特征词定位（只要有命中就记录）
            feature_location_parts = []
            for item in (all_intents_unfiltered or []):
                name = item['意图']
                score = item['得分']
                words = all_hit_words.get(name, set())
                if words:
                    feature_location_parts.append(f"{name}({score:.4f})[{'、'.join(sorted(words))}]")
            feature_location = ' | '.join(feature_location_parts) if feature_location_parts else ''

            is_match = '✓' if benchmark and (
                algo_intent in benchmark or benchmark in algo_intent or
                any(x['意图'] in benchmark for x in top_intents)
            ) else '✗'

            # 诊断分析
            diagnosis = diagnose_mismatch(
                is_match, algo_intent, benchmark, top_intents, all_hit_words,
                weights_intent_set, segmenter, calculator, domain, weights_data,
                all_intents_unfiltered=all_intents_unfiltered
            )

            # 构建详情数据
            detail = {
                '原始问题_完整': raw_query,
                '转写结果': rewrite_display,
                '全量意图得分': [{'意图': x['意图'], '得分': x['得分'],
                              '命中词数': x.get('命中词数', 0)} for x in top_intents],
                '全量意图得分_无阈值': [{'意图': x['意图'], '得分': x['得分'],
                                    '命中词数': x.get('命中词数', 0)} for x in (all_intents_unfiltered or [])],
                '全量命中词': {k: list(v) for k, v in all_hit_words.items()},
                '诊断分析': diagnosis  # 完整结构化 dict 或旧格式 str
            }

            record = {
                '序号': idx + 1,
                '原始问题': raw_query[:80],
                '转写结果': rewrite_display,
                '算法意图': algo_intent,
                '标杆意图': benchmark,
                '全量特征词定位': feature_location,
                '分析结果': _format_diagnosis_display(diagnosis),
                '是否一致': is_match,
                '详情': detail
            }
            results.append(record)
            send('result', record)

        # 保存结果（文件名 = 源文件名_R起始行_C条数）
        output_dir = file_manager.get_benchmark_compare_dir(domain)
        src_stem = Path(original_filename).stem if original_filename else 'compare_results'
        actual_count = len(results)
        name_tag = f"{src_stem}_R{start + 1}_C{actual_count}"
        output_json = output_dir / f'{name_tag}.json'
        output_excel = output_dir / f'{name_tag}.xlsx'

        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        df_result = pd.DataFrame(results)
        df_result.to_excel(output_excel, index=False)

        match_count = sum(1 for r in results if r['是否一致'] == '✓')
        total_count = len(results)

        task['result_file'] = str(output_excel)
        task['status'] = 'done'

        send('done', {
            'message': f'完成！匹配率: {match_count}/{total_count} = {match_count/total_count*100:.1f}%' if total_count else '完成',
            'match_count': match_count,
            'total_count': total_count,
            'accuracy': round(match_count / total_count * 100, 1) if total_count else 0,
            'output_dir': str(output_dir),
            'results': results
        })

    except Exception as e:
        task['status'] = 'error'
        tb = traceback.format_exc()
        print(f"[任务错误] {task_id}: {e}\n{tb}")
        send('error', {
            'message': f'执行出错: {str(e)}',
            'traceback': tb
        })


# ===== Flask 路由 =====

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/domains', methods=['GET'])
def get_domains():
    """获取可用领域列表（含权重词表信息）"""
    result_dir = project_root / 'result'
    domains = []
    if result_dir.exists():
        for d in sorted(result_dir.iterdir()):
            if d.is_dir() and not d.name.startswith('.'):
                # 查找所有 weighted_words.json
                weights_files = []
                weighted_dir = d / 'weighted'
                if weighted_dir.exists():
                    # 根目录下的
                    root_weights = weighted_dir / 'weighted_words.json'
                    if root_weights.exists():
                        weights_files.append({
                            'path': str(root_weights),
                            'label': '最新词表'
                        })
                    # 日期子目录中的
                    for sub in sorted(weighted_dir.iterdir(), reverse=True):
                        if sub.is_dir():
                            sub_weights = sub / 'weighted_words.json'
                            if sub_weights.exists():
                                weights_files.append({
                                    'path': str(sub_weights),
                                    'label': f'词表 ({sub.name})'
                                })

                domains.append({
                    'name': d.name,
                    'has_weights': len(weights_files) > 0,
                    'weights_files': weights_files
                })

    return jsonify(domains)


@app.route('/api/test-post', methods=['POST'])
def test_post():
    """测试 POST 请求是否能到达服务器"""
    print(f"[测试] 收到 POST 请求, Content-Type={request.content_type}")
    return jsonify({'ok': True, 'message': 'POST 请求成功'})


@app.route('/api/upload-weights-json', methods=['POST'])
def upload_weights_json():
    """通过 JSON body 接收权重词表内容（客户端用 FileReader 读取后发送）"""
    try:
        body = request.get_json(force=True)
        if not body:
            return jsonify({'error': '请求体为空'}), 400

        filename = body.get('filename', 'uploaded_weights.json')
        content = body.get('content')
        if not content:
            return jsonify({'error': '缺少文件内容'}), 400

        # 解析 JSON 内容
        if isinstance(content, str):
            data = json.loads(content)
        else:
            data = content

        if '意图映射表' not in data and '词权重表' not in data:
            return jsonify({'error': '无效的权重词表格式（缺少 意图映射表 或 词权重表）'}), 400

        word_count = len(data.get('词权重表', {}))
        intent_count = len(data.get('意图映射表', {}))

        # 保存到文件
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = filename.replace(' ', '_')
        saved_path = UPLOAD_DIR / f'weights_{timestamp}_{safe_name}'
        with open(saved_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[上传权重] 已保存到: {saved_path} (意图:{intent_count}, 词:{word_count})")

        return jsonify({
            'path': str(saved_path),
            'word_count': word_count,
            'intent_count': intent_count,
            'filename': filename
        })

    except json.JSONDecodeError as e:
        return jsonify({'error': f'JSON 解析失败: {str(e)}'}), 400
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[上传权重错误] {e}\n{tb}")
        return jsonify({'error': f'上传处理失败: {str(e)}'}), 500


@app.route('/api/upload-weights', methods=['POST'])
def upload_weights():
    """上传权重词表文件"""
    try:
        print(f"[上传权重] 收到请求, files={list(request.files.keys())}")

        if 'file' not in request.files:
            return jsonify({'error': '请上传文件'}), 400

        file = request.files['file']
        if not file.filename:
            return jsonify({'error': '文件名为空'}), 400

        if not file.filename.endswith('.json'):
            return jsonify({'error': '仅支持 JSON 文件'}), 400

        # 保存到 uploads 目录
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = file.filename.replace(' ', '_')
        saved_path = UPLOAD_DIR / f'weights_{timestamp}_{safe_name}'
        file.save(str(saved_path))
        print(f"[上传权重] 已保存到: {saved_path}")

        # 验证是否为有效的权重词表
        with open(saved_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if '意图映射表' not in data and '词权重表' not in data:
            return jsonify({'error': '无效的权重词表格式（缺少 意图映射表 或 词权重表）'}), 400
        word_count = len(data.get('词权重表', {}))
        intent_count = len(data.get('意图映射表', {}))

        return jsonify({
            'path': str(saved_path),
            'word_count': word_count,
            'intent_count': intent_count,
            'filename': file.filename
        })

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[上传权重错误] {e}\n{tb}")
        return jsonify({'error': f'上传处理失败: {str(e)}'}), 500


@app.route('/api/start', methods=['POST'])
def start_task():
    """上传文件并启动任务"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': '请上传 Excel 文件'}), 400

        file = request.files['file']
        if not file.filename:
            return jsonify({'error': '文件名为空'}), 400

        if not file.filename.endswith(('.xlsx', '.xls')):
            return jsonify({'error': '仅支持 .xlsx / .xls 格式'}), 400

        domain = request.form.get('domain', '失业保险')
        count = int(request.form.get('count', 20))
        start = int(request.form.get('start', 0))
        weights_path = request.form.get('weights_path', '').strip()

        # 自动检测权重词表
        if not weights_path:
            auto_path = project_root / 'result' / domain / 'weighted' / 'weighted_words.json'
            if auto_path.exists():
                weights_path = str(auto_path)
            else:
                return jsonify({'error': f'未找到领域 "{domain}" 的权重词表，请手动上传'}), 400

        if not Path(weights_path).exists():
            return jsonify({'error': f'权重词表不存在: {weights_path}'}), 400

        # 保存上传文件
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = file.filename.replace(' ', '_')
        saved_path = UPLOAD_DIR / f'{timestamp}_{safe_name}'
        original_filename = file.filename  # 保留原始文件名
        file.save(str(saved_path))

        print(f"[启动任务] 文件: {saved_path}, 领域: {domain}, 数量: {count}, 权重: {weights_path}")

        # 创建任务
        task_id = str(uuid.uuid4())[:8]
        tasks[task_id] = {
            'id': task_id,
            'status': 'running',
            'queue': Queue(),
            'result_file': None,
            'created_at': datetime.now().isoformat()
        }

        # 启动后台线程
        thread = threading.Thread(
            target=run_intent_match_task,
            args=(task_id, str(saved_path), domain, count, weights_path, start,
                  original_filename),
            daemon=True
        )
        thread.start()

        return jsonify({'task_id': task_id, 'message': '任务已创建'})

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[启动错误] {e}\n{tb}")
        return jsonify({'error': f'启动失败: {str(e)}'}), 500


@app.route('/api/progress/<task_id>')
def task_progress(task_id):
    """SSE 实时推送任务进度"""
    if task_id not in tasks:
        return jsonify({'error': '任务不存在'}), 404

    def generate():
        task = tasks[task_id]
        q = task['queue']
        while True:
            try:
                msg = q.get(timeout=60)
                event = msg['event']
                data = json.dumps(msg['data'], ensure_ascii=False)
                yield f"event: {event}\ndata: {data}\n\n"
                if event in ('done', 'error'):
                    break
            except Exception:
                yield f"event: heartbeat\ndata: {{}}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={
                        'Cache-Control': 'no-cache',
                        'X-Accel-Buffering': 'no',
                        'Connection': 'keep-alive'
                    })


@app.route('/api/download/<task_id>')
def download_result(task_id):
    """下载结果文件"""
    if task_id not in tasks:
        return jsonify({'error': '任务不存在'}), 404
    task = tasks[task_id]
    if not task.get('result_file'):
        return jsonify({'error': '结果文件不存在'}), 404
    download_name = Path(task['result_file']).name
    return send_file(task['result_file'], as_attachment=True,
                     download_name=download_name)


@app.route('/api/history')
def list_history():
    """列出所有历史分析结果"""
    result_dir = project_root / 'result'
    history = []
    if not result_dir.exists():
        return jsonify(history)
    for domain_dir in sorted(result_dir.iterdir()):
        if not domain_dir.is_dir() or domain_dir.name.startswith('.'):
            continue
        compare_dir = domain_dir / 'benchmark_compare'
        if not compare_dir.exists():
            continue
        for date_dir in sorted(compare_dir.iterdir(), reverse=True):
            if not date_dir.is_dir():
                continue
            for batch_dir in sorted(date_dir.iterdir(), reverse=True):
                if not batch_dir.is_dir():
                    continue
                for jf in sorted(batch_dir.glob('*.json')):
                    try:
                        mtime = datetime.fromtimestamp(jf.stat().st_mtime)
                        data = json.loads(jf.read_text(encoding='utf-8'))
                        total = len(data)
                        match_count = sum(1 for r in data if r.get('是否一致') == '✓')
                        history.append({
                            'domain': domain_dir.name,
                            'date': date_dir.name,
                            'batch': batch_dir.name,
                            'filename': jf.name,
                            'path': str(jf),
                            'time': mtime.strftime('%H:%M'),
                            'total': total,
                            'match_count': match_count,
                            'accuracy': round(match_count / total * 100, 1) if total else 0
                        })
                    except Exception:
                        continue
    return jsonify(history)


@app.route('/api/history-detail')
def history_detail():
    """读取指定历史结果 JSON 文件"""
    file_path = request.args.get('path', '')
    if not file_path:
        return jsonify({'error': '缺少 path 参数'}), 400
    fp = Path(file_path)
    # 安全校验：必须在 result 目录下
    try:
        fp.resolve().relative_to((project_root / 'result').resolve())
    except ValueError:
        return jsonify({'error': '非法路径'}), 403
    if not fp.exists() or not fp.suffix == '.json':
        return jsonify({'error': '文件不存在'}), 404
    data = json.loads(fp.read_text(encoding='utf-8'))
    return jsonify(data)


@app.route('/api/intent-weights', methods=['POST'])
def get_intent_weights():
    """获取指定意图在权重词表中的全量特征词及权重分"""
    try:
        body = request.get_json(force=True)
        weights_path = body.get('weights_path', '')
        intent_name = body.get('intent_name', '')

        if not weights_path or not intent_name:
            return jsonify({'error': '缺少 weights_path 或 intent_name'}), 400

        wp = Path(weights_path)
        if not wp.exists():
            return jsonify({'error': f'权重词表不存在: {weights_path}'}), 404

        with open(wp, 'r', encoding='utf-8') as f:
            data = json.load(f)

        intent_map = data.get('意图映射表', {})
        weight_table = data.get('词权重表', {})

        # 查找意图（支持模糊匹配）
        target_intent = None
        if intent_name in intent_map:
            target_intent = intent_name
        else:
            for name in intent_map:
                if intent_name in name or name in intent_name:
                    target_intent = name
                    break

        if not target_intent:
            return jsonify({'error': f'意图 "{intent_name}" 不在权重词表中', 'features': []}), 200

        layers = intent_map[target_intent]
        features = []
        for layer, words in layers.items():
            for word in words:
                weight_info = weight_table.get(word, {})
                weight = weight_info.get('权重', 0.5) if isinstance(weight_info, dict) else 0.5
                features.append({
                    '词': word,
                    '层级': layer,
                    '权重': weight
                })

        # 按层级排序，同层级按权重降序
        layer_order = {'L1_事项词': 1, 'L2_动作词': 2, 'L3_场景词': 3}
        features.sort(key=lambda x: (layer_order.get(x['层级'], 99), -x['权重']))

        return jsonify({
            'intent_name': target_intent,
            'features': features,
            'total': len(features)
        })

    except Exception as e:
        return jsonify({'error': f'查询失败: {str(e)}'}), 500


# ===== 特征词管理 API =====

# 特征词提取任务存储
feature_extract_tasks = {}

@app.route('/api/feature-extract', methods=['POST'])
def start_feature_extract():
    """启动AI特征词提取"""
    from scripts.modules.feature_extractor import FeatureExtractor
    
    data = request.get_json(silent=True) or {}
    mode = request.form.get('mode', data.get('mode', 'intents'))  # 'intents' 或 'results'
    start = int(request.form.get('start', data.get('start', 0)))
    count = int(request.form.get('count', data.get('count', 9999)))
    intents = data.get('intents', [])   # 模式A: 意图名称列表
    results = data.get('results', [])   # 模式B: 匹配结果列表
    
    if not intents and not results:
        # 尝试从上传文件解析
        if 'file' in request.files:
            import pandas as pd
            f = request.files['file']
            df = pd.read_excel(f)
            if mode == 'intents' and ('意图' in df.columns or '意图名称' in df.columns):
                col = '意图' if '意图' in df.columns else '意图名称'
                all_intents = df[col].dropna().tolist()
                sliced = all_intents[start:start + count]
                # 去重（保持顺序）
                seen = set()
                intents = []
                for x in sliced:
                    if x not in seen:
                        seen.add(x)
                        intents.append(x)
                print(f"[特征词提取] 解析到 {len(all_intents)} 行，切片 {len(sliced)} 行，去重后 {len(intents)} 个唯一意图")
            elif '原始问题' in df.columns:
                all_results = df.to_dict('records')
                results = all_results[start:start + count]
                mode = 'results'
                print(f"[特征词提取] 解析到 {len(all_results)} 条结果，提取第 {start+1}~{start+len(results)} 行")
            else:
                return jsonify({'error': f'无法识别文件格式，列名: {list(df.columns)}'}), 400
        else:
            return jsonify({'error': '请提供意图列表或匹配结果'}), 400
    
    task_id = f'fe_{int(time.time())}'
    feature_extract_tasks[task_id] = {
        'status': 'running',
        'progress': [],
        'result': None
    }
    
    def run_extract():
        from scripts.modules.weight_scorer import WeightScorer
        extractor = FeatureExtractor(FileManager())
        
        def on_progress(current, total, message):
            feature_extract_tasks[task_id]['progress'].append({
                'current': current, 'total': total, 'message': message
            })
        
        try:
            # Step 1: 提取特征词
            if mode == 'intents':
                result = extractor.extract_from_intents(intents, on_progress)
            else:
                result = extractor.extract_from_match_results(results, on_progress)
            
            # Step 2: 自动AI打分
            intent_map = result.get('意图映射表', {})
            if intent_map:
                on_progress(0, 1, '开始AI权重打分...')
                scorer = WeightScorer()
                score_result = scorer.score_features(intent_map, list(intent_map.keys()), on_progress)
                result['词权重表'] = score_result.get('词权重表', {})
                on_progress(1, 1, f'打分完成，共 {len(result["词权重表"])} 个词获得权重')
            
            feature_extract_tasks[task_id]['result'] = result
            feature_extract_tasks[task_id]['status'] = 'done'
        except Exception as e:
            import traceback
            traceback.print_exc()
            feature_extract_tasks[task_id]['status'] = 'error'
            feature_extract_tasks[task_id]['error'] = str(e)
    
    import threading
    threading.Thread(target=run_extract, daemon=True).start()
    
    return jsonify({'task_id': task_id, 'message': '提取任务已启动'})


@app.route('/api/feature-extract/progress/<task_id>')
def feature_extract_progress(task_id):
    """特征词提取进度（SSE）"""
    def generate():
        last_idx = 0
        while True:
            task = feature_extract_tasks.get(task_id)
            if not task:
                yield f'data: {json.dumps({"error": "任务不存在"})}\n\n'
                break
            progress = task['progress']
            for p in progress[last_idx:]:
                yield f'data: {json.dumps({"type": "progress", "data": p})}\n\n'
            last_idx = len(progress)
            if task['status'] == 'done':
                yield f'data: {json.dumps({"type": "done", "data": task["result"]})}\n\n'
                break
            if task['status'] == 'error':
                yield f'data: {json.dumps({"type": "error", "data": task.get("error", "未知错误")})}\n\n'
                break
            time.sleep(1)
    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/feature-extract/merge', methods=['POST'])
def feature_extract_merge():
    """将提取结果合并到权重词表"""
    from scripts.modules.feature_extractor import FeatureExtractor
    
    data = request.get_json(force=True) or {}
    new_features = data.get('features', {})
    weights_path = data.get('weights_path', '')
    
    if not new_features or not weights_path:
        return jsonify({'error': '缺少参数'}), 400
    
    # 相对路径转绝对路径
    wp = Path(weights_path)
    if not wp.is_absolute():
        wp = project_root / wp
    weights_path = str(wp)
    
    try:
        extractor = FeatureExtractor(FileManager())
        result = extractor.merge_into_weights(new_features, weights_path)
        
        # 保存合并后的数据
        if data.get('confirm'):
            import json as json_mod
            wp.parent.mkdir(parents=True, exist_ok=True)
            with open(weights_path, 'w', encoding='utf-8') as f:
                json_mod.dump(result['merged_data'], f, ensure_ascii=False, indent=2)
            
            # 同步生成 Excel 格式
            try:
                from scripts.export_weights_excel import export_to_excel
                excel_path = str(wp.with_suffix('.xlsx'))
                export_to_excel(result['merged_data'], excel_path)
            except Exception as excel_err:
                print(f"[警告] Excel导出失败: {excel_err}")
            
            return jsonify({
                'message': '合并完成',
                'changelog': result['changelog'],
                'stats': result['stats']
            })
        else:
            # 预览模式
            return jsonify({
                'preview': True,
                'changelog': result['changelog'],
                'stats': result['stats']
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/weight-score', methods=['POST'])
def weight_score():
    """对特征词执行AI打分"""
    from scripts.modules.weight_scorer import WeightScorer
    
    data = request.json or {}
    intent_map = data.get('intent_map', {})
    all_intents = data.get('all_intents', [])
    
    if not intent_map:
        return jsonify({'error': '缺少意图映射表'}), 400
    
    try:
        scorer = WeightScorer(FileManager())
        result = scorer.score_features(intent_map, all_intents)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/weight-score/validate', methods=['POST'])
def weight_score_validate():
    """反向校验"""
    from scripts.modules.weight_scorer import WeightScorer
    
    data = request.json or {}
    weights_path = data.get('weights_path', '')
    benchmark_data = data.get('benchmark_data', [])
    
    if not weights_path or not benchmark_data:
        return jsonify({'error': '缺少参数'}), 400
    
    try:
        fm = FileManager()
        weights_data = fm.load_json(Path(weights_path))
        scorer = WeightScorer(fm)
        warnings = scorer.reverse_validate(weights_data, benchmark_data)
        return jsonify({'warnings': warnings, 'count': len(warnings)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print(f"=" * 50)
    print(f"  意图匹配 Web UI")
    print(f"  项目根目录: {project_root}")
    print(f"  访问地址:   http://localhost:5000")
    print(f"=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
