# -*- coding: utf-8 -*-
"""
统一工作流脚本：词表生成与权重打分

合并特征词提取和权重打分为一步工作流
输入：Excel文件（意图列 + 改写后问题列）
输出：全局词表（JSON + Excel）+ 修改日志
"""

import argparse
import time
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.common.file_manager import FileManager
from scripts.common.config import ConfigManager
from scripts.common.changelog_manager import ChangeLogManager
from scripts.common.llm_api import call_llm_api_json, DEFAULT_INTERVAL


class WordlistWorkflow:
    """统一词表工作流
    
    整合特征词提取和权重打分为一步流程
    """
    
    def __init__(self, file_manager: FileManager = None, config: ConfigManager = None):
        self.file_manager = file_manager or FileManager()
        self.config = config or ConfigManager()
    
    def load_excel_input(self, file_path: Path) -> Dict[str, List[str]]:
        """
        从Excel加载意图和改写后问题
        
        Args:
            file_path: Excel文件路径
            
        Returns:
            字典，key为意图，value为该意图关联的改写后问题列表
        """
        import pandas as pd
        
        df = pd.read_excel(file_path)
        
        # 查找意图列和改写后问题列
        intent_col = None
        question_col = None
        
        for col in df.columns:
            col_lower = str(col).lower()
            if '意图' in col_lower:
                intent_col = col
            elif '改写' in col_lower or '转写' in col_lower:
                question_col = col
        
        if not intent_col:
            raise ValueError("Excel文件缺少'意图'列")
        if not question_col:
            raise ValueError("Excel文件缺少'改写后问题'列")
        
        # 收集意图和对应的问题
        intent_questions: Dict[str, Set[str]] = {}
        
        for _, row in df.iterrows():
            intent_value = str(row[intent_col]) if pd.notna(row[intent_col]) else ""
            question = str(row[question_col]) if pd.notna(row[question_col]) else ""
            
            if not intent_value or intent_value == 'nan':
                continue
            
            # 处理逗号分隔的多意图
            intents = [i.strip() for i in intent_value.split(',') if i.strip()]
            
            for intent in intents:
                if intent not in intent_questions:
                    intent_questions[intent] = set()
                if question and question != 'nan':
                    intent_questions[intent].add(question)
        
        # 转换为列表
        return {k: list(v) for k, v in intent_questions.items()}
    
    def prepare_ai_prompt(self, intent_questions: Dict[str, List[str]], domain: str) -> str:
        """
        准备发送给AI的提示词
        
        Args:
            intent_questions: 意图到问题列表的映射
            domain: 领域名称
            
        Returns:
            格式化的提示词
        """
        # 加载提示词模板
        try:
            prompt_template = self.file_manager.load_prompt("wordlist_prompt")
        except FileNotFoundError:
            prompt_template = self._get_default_prompt()
        
        # 格式化意图列表
        intents_text = self._format_intents_with_questions(intent_questions)
        
        return f"""# 领域：{domain}

{prompt_template}

## 待分析的意图清单

共 {len(intent_questions)} 个意图：

{intents_text}
"""
    
    def _format_intents_with_questions(self, intent_questions: Dict[str, List[str]]) -> str:
        """格式化意图和问题"""
        lines = []
        for i, (intent, questions) in enumerate(intent_questions.items(), 1):
            lines.append(f"### {i}. {intent}")
            if questions:
                lines.append("示例问题：")
                for q in questions[:5]:  # 最多显示5个示例
                    lines.append(f"- {q}")
            lines.append("")
        return "\n".join(lines)
    
    def _get_default_prompt(self) -> str:
        """默认提示词"""
        return """## 任务说明

请为每个意图提取三层特征词，并为每个词打分：

### 层级定义

| 层级 | 说明 | 权重范围 |
|------|------|---------|
| L1_事项词 | 高区分度专业术语，只与该意图强相关 | 0.90-1.0 |
| L2_动作词 | 行为动词和常用表达 | 0.75-0.90 |
| L3_场景词 | 场景相关补充词汇 | 0.60-0.80 |

### 打分规则

| 权重范围 | 判断标准 |
|----------|----------|
| 0.95-1.0 | 专业术语，无歧义（如"失业保险金"） |
| 0.85-0.95 | 常用表达，歧义很小（如"失业金"） |
| 0.75-0.85 | 通用动作词，有一定歧义（如"申请"） |
| 0.60-0.75 | 宽泛表达，歧义较大（如"怎么办"） |

### 输出格式

请严格按以下JSON格式输出：

```json
{
  "意图映射表": {
    "意图名称1": {
      "L1_事项词": ["词1", "词2"],
      "L2_动作词": ["词1", "词2"],
      "L3_场景词": ["词1", "词2"]
    }
  },
  "词权重表": {
    "词1": {"权重": 0.95, "理由": "专业术语"},
    "词2": {"权重": 0.85, "理由": "常用表达"}
  }
}
```

### 注意事项

1. 同一个词在不同意图下使用相同权重
2. 参考示例问题理解用户表达习惯
3. 提取口语化表达作为L3场景词
"""
    
    def parse_ai_result(self, ai_output: str) -> Dict:
        """解析AI返回的JSON结果"""
        # 尝试提取JSON块
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', ai_output)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = ai_output
        
        try:
            result = json.loads(json_str)
            return self._normalize_result(result)
        except json.JSONDecodeError as e:
            raise ValueError(f"无法解析AI输出为JSON: {e}")
    
    def _normalize_result(self, result: Dict) -> Dict:
        """规范化结果格式"""
        normalized = {
            "意图映射表": {},
            "词权重表": {},
            "元信息": {
                "版本": "1.0",
                "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "生成方式": "AI自动提取"
            }
        }
        
        # 处理意图映射表
        intent_map = result.get("意图映射表", {})
        for intent, layers in intent_map.items():
            if isinstance(layers, dict):
                normalized["意图映射表"][intent] = {
                    "L1_事项词": layers.get("L1_事项词", layers.get("L1", [])),
                    "L2_动作词": layers.get("L2_动作词", layers.get("L2", [])),
                    "L3_场景词": layers.get("L3_场景词", layers.get("L3", []))
                }
        
        # 处理词权重表
        weight_table = result.get("词权重表", {})
        for word, info in weight_table.items():
            if isinstance(info, dict):
                normalized["词权重表"][word] = {
                    "权重": float(info.get("权重", info.get("weight", 0.5))),
                    "理由": info.get("理由", info.get("reason", ""))
                }
            elif isinstance(info, (int, float)):
                normalized["词权重表"][word] = {
                    "权重": float(info),
                    "理由": ""
                }
        
        return normalized
    
    def merge_with_existing(self, new_data: Dict, existing_data: Dict) -> Dict:
        """
        将新数据合并到现有词表
        
        Args:
            new_data: 新提取的数据
            existing_data: 现有词表数据
            
        Returns:
            合并后的数据
        """
        merged = {
            "意图映射表": dict(existing_data.get("意图映射表", {})),
            "词权重表": dict(existing_data.get("词权重表", {})),
            "元信息": {
                **existing_data.get("元信息", {}),
                "最后更新": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }
        
        # 合并意图映射表
        for intent, layers in new_data.get("意图映射表", {}).items():
            if intent in merged["意图映射表"]:
                # 合并每个层级的词汇
                for layer in ["L1_事项词", "L2_动作词", "L3_场景词"]:
                    existing_words = set(merged["意图映射表"][intent].get(layer, []))
                    new_words = set(layers.get(layer, []))
                    merged["意图映射表"][intent][layer] = list(existing_words | new_words)
            else:
                merged["意图映射表"][intent] = layers
        
        # 合并词权重表（新权重覆盖旧权重）
        merged["词权重表"].update(new_data.get("词权重表", {}))
        
        return merged
    
    def save_results(self, data: Dict, output_dir: Path, 
                     source_file: str = "", existing_data: Dict = None):
        """
        保存结果（JSON + Excel）并生成修改日志
        
        Args:
            data: 词表数据
            output_dir: 输出目录
            source_file: 来源文件路径
            existing_data: 现有词表数据（用于比较生成日志）
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存 JSON
        self.file_manager.save_json(data, output_dir / "weighted_words.json")
        
        # 保存 Excel
        excel_data = self._flatten_for_excel(data)
        self.file_manager.save_excel(excel_data, output_dir / "weighted_words.xlsx")
        
        # 生成修改日志
        if existing_data:
            changelog_mgr = ChangeLogManager(output_dir)
            changes = changelog_mgr.compare_wordlists(existing_data, data)
            changelog_mgr.save_history_snapshot(existing_data, changes)
            changelog_mgr.append_changelog(changes, source_file)
        else:
            # 首次创建，生成初始日志
            changelog_mgr = ChangeLogManager(output_dir)
            changes = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "new_intents": list(data.get("意图映射表", {}).keys()),
                "new_words": [
                    {"词汇": w, "权重": info.get("权重", 0.5), "层级": "", "关联意图": "", "理由": ""}
                    for w, info in data.get("词权重表", {}).items()
                ],
                "modified_words": [],
                "removed_words": [],
                "stats": {
                    "新增意图数": len(data.get("意图映射表", {})),
                    "新增词数": len(data.get("词权重表", {})),
                    "修改词数": 0,
                    "删除词数": 0
                }
            }
            changelog_mgr.append_changelog(changes, source_file)
        
        return data
    
    def _flatten_for_excel(self, data: Dict) -> List[Dict]:
        """将词表数据展平为Excel格式"""
        result = []
        intent_map = data.get("意图映射表", {})
        weight_table = data.get("词权重表", {})
        
        for intent, layers in intent_map.items():
            for layer, words in layers.items():
                for word in words:
                    weight_info = weight_table.get(word, {})
                    result.append({
                        "意图": intent,
                        "层级": layer,
                        "特征词": word,
                        "权重": weight_info.get("权重", 0.5),
                        "理由": weight_info.get("理由", "")
                    })
        
        return result


def load_progress(progress_file: Path) -> Dict:
    """加载进度文件"""
    if progress_file.exists():
        with open(progress_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def save_progress(progress_file: Path, progress: Dict):
    """保存进度文件"""
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    with open(progress_file, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="统一词表生成工作流（特征词提取 + 权重打分）"
    )
    parser.add_argument(
        "--domain", "-d",
        required=True,
        help="领域名称，如 '失业保险'"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="输入Excel文件路径（需包含'意图'和'改写后问题'列）"
    )
    parser.add_argument(
        "--output-dir", "-o",
        help="输出目录，默认为 result/{领域}/weighted/"
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="仅准备AI输入，不保存结果"
    )
    parser.add_argument(
        "--ai-output",
        help="AI分析结果文本或文件路径"
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int,
        default=15,
        help="每批处理的意图数量，默认15"
    )
    parser.add_argument(
        "--continue", "-c",
        dest="continue_",
        action="store_true",
        help="从上次中断处继续"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="重置进度，从头开始"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="显示当前进度状态"
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="自动模式：直接调用大模型API分析，无需手动交互"
    )
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    # 初始化
    file_manager = FileManager()
    workflow = WordlistWorkflow(file_manager)
    
    # 确定路径
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = file_manager.base_dir / input_path
    
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = file_manager.get_domain_dir(args.domain) / "weighted"
    
    progress_file = output_dir / ".progress.json"
    
    print(f"[词表工作流] 领域: {args.domain}")
    print(f"[词表工作流] 输入文件: {input_path}")
    print(f"[词表工作流] 输出目录: {output_dir}")
    print(f"[词表工作流] 批次大小: {args.batch_size}")
    
    # 加载所有意图
    all_intent_questions = workflow.load_excel_input(input_path)
    all_intents = list(all_intent_questions.keys())
    print(f"[词表工作流] 总意图数量: {len(all_intents)}")
    
    # 处理进度
    progress = load_progress(progress_file)
    
    if args.reset:
        progress = None
        print("[词表工作流] 进度已重置")
    
    if args.status:
        if progress:
            processed = progress.get("processed_intents", [])
            pending = progress.get("pending_intents", [])
            print(f"\n[进度状态]")
            print(f"  已处理: {len(processed)}/{len(all_intents)}")
            print(f"  待处理: {len(pending)}")
            print(f"  上次更新: {progress.get('last_updated', 'N/A')}")
            if pending:
                print(f"  下一批: {pending[:args.batch_size]}")
        else:
            print("[进度状态] 无进度记录，将从头开始")
        return
    
    # 初始化或恢复进度
    if progress is None or not args.continue_:
        progress = {
            "source_file": str(input_path.name),
            "total_intents": len(all_intents),
            "processed_intents": [],
            "pending_intents": all_intents,
            "batch_size": args.batch_size,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    
    pending_intents = progress.get("pending_intents", all_intents)
    processed_intents = progress.get("processed_intents", [])
    
    if not pending_intents:
        print("[词表工作流] 所有意图已处理完毕！")
        return
    
    # 获取当前批次
    current_batch = pending_intents[:args.batch_size]
    batch_intent_questions = {k: all_intent_questions[k] for k in current_batch if k in all_intent_questions}
    
    print(f"[词表工作流] 当前批次: {len(current_batch)} 个意图 (第 {len(processed_intents)+1}-{len(processed_intents)+len(current_batch)} 个)")
    
    if args.auto:
        # ===== 自动模式：循环调用大模型API处理所有批次 =====
        batch_num = 0
        system_prompt = "你是一名政务服务领域的特征词提取专家。请严格按照用户要求的JSON格式输出结果。"
        
        while pending_intents:
            batch_num += 1
            current_batch = pending_intents[:args.batch_size]
            batch_intent_questions = {k: all_intent_questions[k] for k in current_batch if k in all_intent_questions}
            
            print(f"\n{'='*60}")
            print(f"[自动模式] 批次 {batch_num}: {len(current_batch)} 个意图")
            print(f"  意图: {', '.join(current_batch[:5])}{'...' if len(current_batch) > 5 else ''}")
            print(f"{'='*60}")
            
            # 1. 准备提示词
            ai_prompt = workflow.prepare_ai_prompt(batch_intent_questions, args.domain)
            
            # 2. 调用API
            print(f"[API] 正在调用 Qwen 32B 分析...")
            result = call_llm_api_json(system_prompt, ai_prompt)
            
            if not result or '意图映射表' not in result:
                print(f"[错误] API 返回无效结果，跳过本批次")
                # 仍然更新进度以避免无限循环
                processed_intents.extend(current_batch)
                pending_intents = pending_intents[len(current_batch):]
                progress = {
                    "source_file": str(input_path.name),
                    "total_intents": len(all_intents),
                    "processed_intents": processed_intents,
                    "pending_intents": pending_intents,
                    "batch_size": args.batch_size,
                    "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                save_progress(progress_file, progress)
                if pending_intents:
                    time.sleep(DEFAULT_INTERVAL)
                continue
            
            # 3. 规范化结果
            new_data = workflow._normalize_result(result)
            print(f"[API] 解析意图数: {len(new_data.get('意图映射表', {}))}")
            print(f"[API] 解析词数: {len(new_data.get('词权重表', {}))}")
            
            # 4. 合并现有词表
            changelog_mgr = ChangeLogManager(output_dir)
            existing_data = changelog_mgr.get_latest_wordlist()
            
            if existing_data:
                merged_data = workflow.merge_with_existing(new_data, existing_data)
            else:
                merged_data = new_data
            
            # 5. 保存结果
            source_file = str(input_path.relative_to(file_manager.base_dir))
            workflow.save_results(merged_data, output_dir, source_file, existing_data)
            
            # 6. 更新进度
            processed_intents.extend(current_batch)
            pending_intents = pending_intents[len(current_batch):]
            progress = {
                "source_file": str(input_path.name),
                "total_intents": len(all_intents),
                "processed_intents": processed_intents,
                "pending_intents": pending_intents,
                "batch_size": args.batch_size,
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            save_progress(progress_file, progress)
            
            print(f"[批次完成] 已处理: {len(processed_intents)}/{len(all_intents)}, 待处理: {len(pending_intents)}")
            
            # 等待间隔
            if pending_intents:
                print(f"[等待] {DEFAULT_INTERVAL} 秒后处理下一批...")
                time.sleep(DEFAULT_INTERVAL)
        
        print(f"\n{'='*60}")
        print(f"[词表工作流] 全部完成！结果已保存到:")
        print(f"  - {output_dir / 'weighted_words.json'}")
        print(f"  - {output_dir / 'weighted_words.xlsx'}")
        print(f"  - {output_dir / 'change_log.md'}")
        print(f"{'='*60}")
    
    elif args.prepare_only:
        # 仅准备AI输入
        ai_prompt = workflow.prepare_ai_prompt(batch_intent_questions, args.domain)
        print("\n" + "="*60)
        print(f"请将以下内容发送给AI助手进行分析（批次 {len(processed_intents)//args.batch_size + 1}）：")
        print("="*60)
        print(ai_prompt)
        print("="*60)
        print(f"\n[提示] 还剩 {len(pending_intents) - len(current_batch)} 个意图待处理")
        
    elif args.ai_output:
        # 保存AI结果
        ai_output_path = Path(args.ai_output)
        if ai_output_path.exists():
            with open(ai_output_path, 'r', encoding='utf-8') as f:
                ai_output = f.read()
        else:
            ai_output = args.ai_output
        
        # 解析AI结果
        new_data = workflow.parse_ai_result(ai_output)
        print(f"[词表工作流] 解析意图数: {len(new_data.get('意图映射表', {}))}")
        print(f"[词表工作流] 解析词数: {len(new_data.get('词权重表', {}))}")
        
        # 检查是否存在现有词表
        changelog_mgr = ChangeLogManager(output_dir)
        existing_data = changelog_mgr.get_latest_wordlist()
        
        if existing_data:
            print(f"[词表工作流] 发现现有词表，将进行增量合并")
            merged_data = workflow.merge_with_existing(new_data, existing_data)
        else:
            print(f"[词表工作流] 创建新词表")
            merged_data = new_data
        
        # 保存结果
        source_file = str(input_path.relative_to(file_manager.base_dir))
        workflow.save_results(merged_data, output_dir, source_file, existing_data)
        
        # 更新进度
        processed_intents.extend(current_batch)
        remaining = pending_intents[len(current_batch):]
        progress = {
            "source_file": str(input_path.name),
            "total_intents": len(all_intents),
            "processed_intents": processed_intents,
            "pending_intents": remaining,
            "batch_size": args.batch_size,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_progress(progress_file, progress)
        
        print(f"\n[词表工作流] 批次完成！")
        print(f"  已处理: {len(processed_intents)}/{len(all_intents)}")
        print(f"  待处理: {len(remaining)}")
        
        if remaining:
            print(f"\n[提示] 使用 --continue 继续处理下一批")
        else:
            print(f"\n[词表工作流] 全部完成！结果已保存到:")
            print(f"  - {output_dir / 'weighted_words.json'}")
            print(f"  - {output_dir / 'weighted_words.xlsx'}")
            print(f"  - {output_dir / 'change_log.md'}")
        
    else:
        print("[错误] 请指定操作模式：")
        print("  --auto          自动调用API分析")
        print("  --prepare-only  准备AI输入")
        print("  --ai-output     保存AI分析结果")
        print("  --status        查看进度状态")
        sys.exit(1)


if __name__ == "__main__":
    main()

