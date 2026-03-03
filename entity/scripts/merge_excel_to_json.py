"""
从 Excel 合并手动修改的权重和特征词到 weighted_words.json
Excel 表头: 意图, 层级, 特征词, 权重, 理由
"""
import json
import sys
import os
import openpyxl
from pathlib import Path

# 路径
BASE_DIR = Path(__file__).resolve().parent.parent / "result" / "global" / "weighted"
EXCEL_PATH = BASE_DIR / "weighted_words.xlsx"
JSON_PATH = BASE_DIR / "weighted_words.json"
BACKUP_PATH = BASE_DIR / "weighted_words.json.bak"


def load_excel(path):
    """读取 Excel，返回两个结构：
    1. intent_map: {意图: {层级: [特征词列表]}}
    2. weight_map: {特征词: {权重, 理由}}
    """
    wb = openpyxl.load_workbook(path)
    ws = wb.active

    intent_map = {}  # {意图名: {核心词: [], 发散词: [], 同义词: []}}
    weight_map = {}  # {特征词: {权重: float, 理由: str}}

    for row in ws.iter_rows(min_row=2, values_only=True):
        intent, level, word, weight, reason = row

        # 跳过空行
        if not word or not intent or not level:
            continue

        word = str(word).strip()
        intent = str(intent).strip()
        level = str(level).strip()

        # 构建意图映射
        if intent not in intent_map:
            intent_map[intent] = {}
        if level not in intent_map[intent]:
            intent_map[intent][level] = []
        if word not in intent_map[intent][level]:
            intent_map[intent][level].append(word)

        # 构建权重表（Excel 中的值优先）
        if weight is not None:
            try:
                w = float(weight)
            except (ValueError, TypeError):
                w = None

            if w is not None:
                reason_str = str(reason).strip() if reason else ""
                # 如果同一词出现多次，优先保留有理由的版本
                if word in weight_map:
                    if reason_str and not weight_map[word]["理由"]:
                        weight_map[word] = {"权重": w, "理由": reason_str}
                    elif w != weight_map[word]["权重"]:
                        # 权重不同时，取较新的（后出现的）
                        weight_map[word] = {"权重": w, "理由": reason_str}
                else:
                    weight_map[word] = {"权重": w, "理由": reason_str}

    return intent_map, weight_map


def merge(json_path, excel_intent_map, excel_weight_map):
    """将 Excel 内容合并到 JSON"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    old_intents = data.get("意图映射表", {})
    old_weights = data.get("词权重表", {})

    # --- 合并意图映射表 ---
    # Excel 中的意图结构 完全覆盖 JSON 中对应意图
    new_intents = dict(old_intents)  # 保留 JSON 中已有的
    for intent, levels in excel_intent_map.items():
        new_intents[intent] = {
            "核心词": levels.get("核心词", []),
            "发散词": levels.get("发散词", []),
            "同义词": levels.get("同义词", []),
        }

    # --- 合并词权重表 ---
    # Excel 中的权重 覆盖 JSON 中的同名词条
    new_weights = dict(old_weights)
    for word, info in excel_weight_map.items():
        new_weights[word] = info

    data["意图映射表"] = new_intents
    data["词权重表"] = new_weights
    return data


def main():
    print(f"Excel: {EXCEL_PATH}")
    print(f"JSON:  {JSON_PATH}")

    if not EXCEL_PATH.exists():
        print(f"❌ Excel 文件不存在: {EXCEL_PATH}")
        sys.exit(1)

    # 读取 Excel
    excel_intent_map, excel_weight_map = load_excel(EXCEL_PATH)
    print(f"\n📊 Excel 数据统计:")
    print(f"  意图数: {len(excel_intent_map)}")
    print(f"  词条数: {len(excel_weight_map)}")

    # 读取并比较 JSON
    if JSON_PATH.exists():
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            old_data = json.load(f)
        old_intents = old_data.get("意图映射表", {})
        old_weights = old_data.get("词权重表", {})
        print(f"\n📄 原 JSON 数据统计:")
        print(f"  意图数: {len(old_intents)}")
        print(f"  词条数: {len(old_weights)}")

        # 差异统计
        new_words = set(excel_weight_map.keys()) - set(old_weights.keys())
        changed_words = []
        for w in set(excel_weight_map.keys()) & set(old_weights.keys()):
            if excel_weight_map[w]["权重"] != old_weights[w]["权重"]:
                changed_words.append(
                    (w, old_weights[w]["权重"], excel_weight_map[w]["权重"])
                )

        if new_words:
            print(f"\n🆕 新增词条 ({len(new_words)}):")
            for w in sorted(new_words):
                print(f"  + {w} (权重: {excel_weight_map[w]['权重']})")

        if changed_words:
            print(f"\n✏️  权重变更 ({len(changed_words)}):")
            for w, old_w, new_w in sorted(changed_words):
                print(f"  {w}: {old_w} → {new_w}")

        if not new_words and not changed_words:
            # 检查意图映射变更
            intent_changes = False
            for intent in excel_intent_map:
                if intent not in old_intents:
                    intent_changes = True
                    break
                for level in ["核心词", "发散词", "同义词"]:
                    old_list = set(old_intents.get(intent, {}).get(level, []))
                    new_list = set(excel_intent_map.get(intent, {}).get(level, []))
                    if old_list != new_list:
                        intent_changes = True
                        break
            if not intent_changes:
                print("\n✅ 无变更，JSON 已是最新状态。")
                return
    else:
        old_data = {"意图映射表": {}, "词权重表": {}}

    # 备份
    if JSON_PATH.exists():
        import shutil
        shutil.copy2(JSON_PATH, BACKUP_PATH)
        print(f"\n💾 已备份原 JSON → {BACKUP_PATH.name}")

    # 合并
    merged = merge(JSON_PATH, excel_intent_map, excel_weight_map)
    new_intents = merged["意图映射表"]
    new_weights = merged["词权重表"]

    # 写入
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 合并完成！")
    print(f"  合并后意图数: {len(new_intents)}")
    print(f"  合并后词条数: {len(new_weights)}")


if __name__ == "__main__":
    main()
