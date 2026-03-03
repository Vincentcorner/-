# -*- coding: utf-8 -*-
"""
批量意图匹配脚本

支持三维度转写结果的并行 AC 匹配
"""

import pandas as pd
import json
import re
import sys
import time
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.common.file_manager import FileManager
from scripts.common.config import ConfigManager
from scripts.common.llm_api import call_llm_api, call_llm_api_json, DEFAULT_INTERVAL
from scripts.modules.query_segmenter import QuerySegmenter
from scripts.modules.weight_calculator import WeightCalculator


def match_3d(segmenter, calculator, rewrite_results: dict, domain: str) -> tuple:
    """对3个维度分别独立执行 AC匹配+得分汇总，最后合并意图结果
    
    每个维度独立完成完整流程（AC切词 → 得分汇总），
    然后将三轮的意图结果合并去重（同一意图取最高分）。
    
    Args:
        segmenter: AC自动机分词器实例
        calculator: 权重计算器实例
        rewrite_results: 三维度转写结果 {scenario, plain_language, official_expression}
        domain: 领域
        
    Returns:
        (top_intents, all_hit_words)
        - top_intents: 合并去重后的意图得分列表（按得分降序）
        - all_hit_words: {意图名: set(命中词)} 用于特征词标注
    """
    intent_best = {}  # {意图名: 最佳结果}
    all_hit_words = {}  # {意图名: set(命中词)}
    
    for dim in ['scenario', 'plain_language', 'official_expression']:
        text = rewrite_results.get(dim, '')
        if not text or text == '无具体情形':
            continue
        # 独立完成 AC匹配 → 得分汇总
        matched_words = segmenter.segment(text, domain)
        intent_scores = calculator.calculate(matched_words, domain)
        
        for item in intent_scores:
            name = item['意图']
            # 同一意图取最高分
            if name not in intent_best or item['得分'] > intent_best[name]['得分']:
                intent_best[name] = item
            # 收集所有命中词（用于特征词标注）
            for detail in item.get('命中详情', []):
                all_hit_words.setdefault(name, set()).add(detail['词'])
    
    # 按得分降序排序
    results = sorted(intent_best.values(), key=lambda x: x['得分'], reverse=True)
    return results, all_hit_words


def format_intent_features(all_hit_words: dict, top_intents: list) -> str:
    """格式化意图特征词标注
    
    格式：意图A（特征词1、特征词2）、意图B（特征词3）
    
    Args:
        all_hit_words: {意图名: set(命中词)} 来自 match_3d
        top_intents: 意图得分列表
    """
    parts = []
    for item in top_intents:
        name = item['意图']
        words = all_hit_words.get(name, set())
        if words:
            parts.append(f"{name}（{'、'.join(sorted(words))}）")
        else:
            parts.append(name)
    return '、'.join(parts)


def format_rewrite_display(rewrite_results: dict) -> str:
    """将三维度转写结果拼合为展示文本
    
    格式：[情形] xxx | [群众语言] xxx | [官方表达] xxx
    """
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


def load_rewrite_prompt() -> str:
    """加载三维度转写提示词"""
    prompt_path = Path(project_root) / "prompts" / "query_rewrite_3d_prompt.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"提示词文件不存在: {prompt_path}")
    
    with open(prompt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取代码块中的提示词内容
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
    prompt_path = Path(project_root) / "prompts" / "intent_select_prompt.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"提示词文件不存在: {prompt_path}")
    
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()


def auto_rewrite_questions(questions: list, domain: str, output_dir: Path = None) -> dict:
    """自动调用API对问题进行三维度转写
    
    Args:
        questions: 原始问题列表
        domain: 领域名称
        output_dir: 转写结果保存目录（可选）
        
    Returns:
        {原始问题: {scenario, plain_language, official_expression}}
    """
    system_prompt = load_rewrite_prompt()
    rewrite_data = {}
    results_list = []
    
    print(f"\n[自动转写] 开始三维度转写 {len(questions)} 个问题...")
    
    for i, question in enumerate(questions, 1):
        print(f"  [{i}/{len(questions)}] 转写: {question[:30]}...", end=" ")
        
        result = call_llm_api_json(system_prompt, question)
        
        if result and 'rewrite_results' in result:
            rr = result['rewrite_results']
            rewrite_data[question] = rr
            results_list.append({
                'original_question': question,
                'rewrite_results': rr
            })
            scenario = rr.get('scenario', '')[:20]
            print(f"✓ 情形: {scenario}...")
        else:
            # 构造失败占位
            fallback = {
                'scenario': '(转写失败)',
                'plain_language': '(转写失败)',
                'official_expression': '(转写失败)'
            }
            rewrite_data[question] = fallback
            results_list.append({
                'original_question': question,
                'rewrite_results': fallback
            })
            print("✗ 转写失败")
        
        # 限流
        if i < len(questions):
            time.sleep(DEFAULT_INTERVAL)
    
    # 保存转写结果
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        rewrite_path = output_dir / 'auto_rewrite_3d.json'
        with open(rewrite_path, 'w', encoding='utf-8') as f:
            json.dump(results_list, f, ensure_ascii=False, indent=2)
        print(f"[自动转写] 结果已保存: {rewrite_path}")
    
    print(f"[自动转写] 完成: {sum(1 for v in rewrite_data.values() if v.get('scenario') != '(转写失败)')}/{len(questions)} 成功")
    return rewrite_data


def ai_select_intent(question: str, rewrite_display: str, top_intents: list,
                     all_hit_words: dict, select_prompt: str) -> tuple:
    """AI筛选最终意图
    
    当有多个候选意图时，调用大模型从中选出最合适的。
    
    Args:
        question: 原始问题
        rewrite_display: 转写展示文本
        top_intents: 候选意图列表
        all_hit_words: {意图名: set(命中词)}
        select_prompt: 意图筛选系统提示词
        
    Returns:
        (选中的意图名, AI置信度) 或 (Top-1意图名, 算法置信度)
    """
    # 构造候选信息
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
        # 验证选中的意图确实在候选列表中
        valid_names = [item['意图'] for item in top_intents]
        if selected in valid_names:
            return selected, int(min(confidence * 100, 99))
        else:
            # 尝试模糊匹配
            for name in valid_names:
                if selected in name or name in selected:
                    return name, int(min(confidence * 100, 99))
    
    # AI筛选失败，回退到Top-1
    return top_intents[0]['意图'], int(min(80 + top_intents[0]['得分'] * 10, 99))


def run_batch_match(question_file: str, weighted_words_path: str, domain: str, 
                    count: int = 50, rewrite_file: str = None,
                    auto_rewrite: bool = False):
    """批量意图匹配
    
    Args:
        question_file: 问题Excel文件路径（包含原始问和意图列）
        weighted_words_path: 权重词文件路径
        domain: 领域名称
        count: 处理数量
        rewrite_file: 三维度转写结果JSON文件路径（可选）
        auto_rewrite: 自动调用API进行三维度转写
    """
    
    # 读取问题文件
    df = pd.read_excel(question_file)
    df_subset = df.head(count)
    
    # 初始化
    file_manager = FileManager()
    config = ConfigManager()
    
    segmenter = QuerySegmenter(file_manager, config)
    segmenter.load_and_build(Path(weighted_words_path))
    calculator = WeightCalculator(file_manager, config)
    
    # 确定列名
    raw_col = '原始问' if '原始问' in df.columns else df.columns[0]
    
    # 查找转写列（向后兼容）
    rewrite_col = None
    for col in df.columns:
        if '改写' in col or '转写' in col:
            rewrite_col = col
            break
    
    # 查找标杆意图列
    benchmark_col = None
    for col in df.columns:
        if '意图' in col and '领域' not in col:
            benchmark_col = col
            break
    
    print(f'原始问列: {raw_col}')
    print(f'转写列: {rewrite_col}')
    print(f'标杆意图列: {benchmark_col}')
    print(f'待处理数量: {len(df_subset)}')
    
    # 加载三维度转写结果（如果有）
    rewrite_data = {}
    if rewrite_file:
        rewrite_path = Path(rewrite_file)
        if rewrite_path.exists():
            with open(rewrite_path, 'r', encoding='utf-8') as f:
                rewrite_list = json.load(f)
            # 以原始问题为key建立索引
            for item in rewrite_list:
                orig = item.get('original_question', '')
                rewrite_data[orig] = item.get('rewrite_results', {})
            print(f'已加载三维度转写结果: {len(rewrite_data)} 条')
    
    # 自动转写模式：调用API对所有问题进行三维度转写
    if auto_rewrite and not rewrite_data:
        questions_to_rewrite = []
        for _, row in df_subset.iterrows():
            q = str(row[raw_col]) if pd.notna(row[raw_col]) else ''
            if q:
                questions_to_rewrite.append(q)
        
        # 确定输出目录
        compare_base = Path(f'result/{domain}/benchmark_compare')
        date_str = datetime.now().strftime("%Y%m%d")
        rewrite_output_dir = compare_base / date_str
        
        rewrite_data = auto_rewrite_questions(questions_to_rewrite, domain, rewrite_output_dir)
    
    # 加载AI意图筛选提示词（用于多候选时的AI筛选）
    intent_select_prompt = None
    try:
        intent_select_prompt = load_intent_select_prompt()
        print(f'已加载意图筛选提示词')
    except FileNotFoundError:
        print(f'[提示] 未找到意图筛选提示词，将仅使用算法Top-1')
    
    # 检查是否有已处理的结果，用于去重
    compare_base = Path(f'result/{domain}/benchmark_compare')
    date_str = datetime.now().strftime("%Y%m%d")
    date_dir = compare_base / date_str
    existing_questions = set()
    existing_results = []
    
    if date_dir.exists():
        existing_batches = [
            int(d.name) for d in date_dir.iterdir()
            if d.is_dir() and d.name.isdigit()
        ]
        if existing_batches:
            latest_batch = max(existing_batches)
            latest_results_file = date_dir / str(latest_batch) / 'compare_results.json'
            if latest_results_file.exists():
                try:
                    with open(latest_results_file, 'r', encoding='utf-8') as f:
                        existing_results = json.load(f)
                        existing_questions = {r['原始问题'] for r in existing_results}
                    print(f'已有记录（批次{latest_batch}）: {len(existing_questions)} 条')
                except Exception as e:
                    print(f'读取已有结果失败: {e}')
    
    print()
    
    new_results = []
    skipped_count = 0
    processed_count = 0
    
    for i, row in df_subset.iterrows():
        raw_query = str(row[raw_col]) if pd.notna(row[raw_col]) else ''
        raw_query_truncated = raw_query[:80]
        
        # 检查是否已处理过
        if raw_query_truncated in existing_questions:
            skipped_count += 1
            continue
        
        benchmark = str(row[benchmark_col]) if benchmark_col and pd.notna(row[benchmark_col]) else ''
        
        # 判断匹配模式：三维度 或 单文本
        rewrite_results = rewrite_data.get(raw_query, rewrite_data.get(raw_query_truncated, {}))
        
        if rewrite_results:
            # 三维度独立匹配：每个维度各自 AC匹配+得分汇总，然后意图结果合并去重
            top_intents, all_hit_words = match_3d(segmenter, calculator, rewrite_results, domain)
            rewrite_display = format_rewrite_display(rewrite_results)
            rewrite_source = 'AI三维度'
        else:
            # 回退：使用现有转写列或原始问题（单文本模式）
            rewrite = str(row[rewrite_col]) if rewrite_col and pd.notna(row[rewrite_col]) else raw_query
            matched_words = segmenter.segment(rewrite, domain)
            top_intents = calculator.calculate(matched_words, domain) if matched_words else []
            # 从匹配词构建 all_hit_words 以复用 format_intent_features
            all_hit_words = {}
            for m in matched_words:
                all_hit_words.setdefault(m['意图'], set()).add(m['词'])
            rewrite_display = rewrite[:80]
            rewrite_source = '文件' if rewrite_col else '原始'
        
        # 获取算法意图（多候选时进行AI筛选）
        all_intents = '、'.join([x['意图'] for x in top_intents]) if top_intents else ''
        
        if not top_intents:
            algo_intent = '(无匹配)'
            confidence = 0
        elif len(top_intents) >= 2 and intent_select_prompt:
            # 多候选：调用AI筛选
            algo_intent, confidence = ai_select_intent(
                raw_query, rewrite_display, top_intents,
                all_hit_words, intent_select_prompt
            )
            # AI筛选间隔
            time.sleep(DEFAULT_INTERVAL)
        else:
            # 单候选或无AI筛选提示词：直接取Top-1
            algo_intent = top_intents[0]['意图']
            confidence = int(min(80 + top_intents[0]['得分'] * 10, 99))
        
        # 特征词标注
        intent_features = format_intent_features(all_hit_words, top_intents) if top_intents else ''
        
        # 判断是否一致
        is_match = '✓' if benchmark and (
            algo_intent in benchmark or benchmark in algo_intent or 
            any(x['意图'] in benchmark for x in top_intents)
        ) else '✗'
        
        new_results.append({
            '序号': len(existing_results) + len(new_results) + 1,
            '原始问题': raw_query_truncated,
            '转写结果': rewrite_display,
            '转写来源': rewrite_source,
            '算法意图': algo_intent,
            '全量意图': all_intents,
            '意图特征词': intent_features,
            '置信分': confidence,
            '标杆意图': benchmark,
            '是否一致': is_match
        })
        processed_count += 1
        
        if processed_count % 10 == 0:
            print(f'已处理: {processed_count} 条 (跳过: {skipped_count} 条)')
    
    # 合并结果
    results = existing_results + new_results
    
    print(f'\n本次新增: {len(new_results)} 条, 跳过已有: {skipped_count} 条')
    print(f'总计: {len(results)} 条')
    
    # 统计
    if results:
        match_count = sum(1 for r in results if r['是否一致'] == '✓')
        print(f'匹配统计: {match_count}/{len(results)} = {match_count/len(results)*100:.1f}%')
    
    # 保存结果 - 使用批次子目录
    output_dir = file_manager.get_benchmark_compare_dir(domain)
    
    output_json = output_dir / 'compare_results.json'
    output_excel = output_dir / 'compare_results.xlsx'
    
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    df_result = pd.DataFrame(results)
    df_result.to_excel(output_excel, index=False)
    
    print(f'结果已保存: {output_dir}')
    print(f'  - compare_results.json')
    print(f'  - compare_results.xlsx')
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file', default=r'originalfile/失业保险/标杆意图.xlsx')
    parser.add_argument('-w', '--weights', default=r'result/失业保险/weighted/20260206/weighted_words.json')
    parser.add_argument('-d', '--domain', default='失业保险')
    parser.add_argument('-c', '--count', type=int, default=50)
    parser.add_argument('-r', '--rewrite', default=None, help='三维度转写结果JSON文件路径')
    parser.add_argument('-o', '--output', default=None, help='Output directory name suffix')
    parser.add_argument('--auto-rewrite', action='store_true', help='自动调用API进行三维度转写')
    args = parser.parse_args()
    
    run_batch_match(
        question_file=args.file,
        weighted_words_path=args.weights,
        domain=args.domain,
        count=args.count,
        rewrite_file=args.rewrite,
        auto_rewrite=args.auto_rewrite
    )
