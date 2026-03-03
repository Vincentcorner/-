#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
变更日志生成工具
"""

import os
import sys
from datetime import datetime
from pathlib import Path


def get_next_sequence(changelog_dir: str) -> int:
    """获取当天的下一个序号"""
    today = datetime.now().strftime("%Y-%m-%d")
    existing = list(Path(changelog_dir).glob(f"{today}_*.md"))
    if not existing:
        return 1
    sequences = []
    for f in existing:
        try:
            seq = int(f.stem.split("_")[1])
            sequences.append(seq)
        except (IndexError, ValueError):
            pass
    return max(sequences, default=0) + 1


def create_changelog(
    change_type: str,
    description: str,
    affected_files: list = None,
    changelog_dir: str = "changelog"
):
    """
    创建变更日志
    
    Args:
        change_type: 变更类型（如：新增实体、修改报告格式、调整分类规则）
        description: 变更描述
        affected_files: 受影响的文件列表
        changelog_dir: 变更日志目录
    """
    Path(changelog_dir).mkdir(parents=True, exist_ok=True)
    
    today = datetime.now().strftime("%Y-%m-%d")
    seq = get_next_sequence(changelog_dir)
    
    # 生成文件名
    short_desc = description[:20].replace(" ", "_").replace("/", "-")
    filename = f"{today}_{seq:03d}_{short_desc}.md"
    filepath = Path(changelog_dir) / filename
    
    # 生成内容
    content = f"""# 变更记录 {today}_{seq:03d}

## 变更类型
{change_type}

## 变更内容
{description}

## 影响范围
"""
    
    if affected_files:
        for f in affected_files:
            content += f"- {f}\n"
    else:
        content += "- 待确认\n"
    
    content += f"""
## 创建时间
{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 验证状态
- [ ] 待验证
"""
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"变更日志已创建: {filepath}")
    return str(filepath)


def main():
    if len(sys.argv) < 3:
        print("用法: python create_changelog.py <变更类型> <描述> [文件1 文件2 ...]")
        print("示例: python create_changelog.py '修改报告格式' '新增关系总结列' generate_excel.py")
        return
    
    change_type = sys.argv[1]
    description = sys.argv[2]
    affected_files = sys.argv[3:] if len(sys.argv) > 3 else None
    
    create_changelog(change_type, description, affected_files)


if __name__ == "__main__":
    main()
