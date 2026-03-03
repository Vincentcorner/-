# -*- coding: utf-8 -*-
"""
词频统计脚本 - 带日志记录版
"""

import sys
import os

# 重定向输出到日志文件
log_file = r'D:\数字研究院工作\认知世界大模型\第三个路径\norelation\entity\result\processing_log.txt'
os.makedirs(os.path.dirname(log_file), exist_ok=True)
sys.stdout = open(log_file, 'w', encoding='utf-8')
sys.stderr = sys.stdout

print("Script started.")

try:
    import pandas as pd
    from docx import Document
    import re
    from collections import Counter
    print("Libraries imported successfully.")
except Exception as e:
    print(f"Error importing libraries: {e}")
    sys.exit(1)

def read_docx(file_path):
    """读取docx文件，返回全部文本内容"""
    try:
        doc = Document(file_path)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return '\n'.join(full_text)
    except Exception as e:
        print(f"Error reading docx: {e}")
        raise

def count_word_frequency(text, words):
    """统计每个词在文本中出现的次数"""
    results = []
    print(f"Counting frequency for {len(words)} words...")
    for i, word in enumerate(words):
        if pd.isna(word) or not word:
            continue
        word = str(word).strip()
        if not word:
            continue
        # 使用正则表达式精确匹配
        try:
            count = len(re.findall(re.escape(word), text))
            results.append({
                '词汇': word,
                '词频': count
            })
        except Exception as e:
            print(f"Error counting word '{word}': {e}")
            
        if i % 100 == 0:
            print(f"Processed {i} words...")
            
    return results

def main():
    try:
        # 文件路径
        vocab_path = r'D:\数字研究院工作\认知世界大模型\第三个路径\entity\entity\result\标准词库.xlsx'
        docx_path = r'D:\数字研究院工作\认知世界大模型\第三个路径\entity\entity\originalfile\广东省失业保险条例.docx'
        output_path = r'D:\数字研究院工作\认知世界大模型\第三个路径\norelation\entity\result\词频统计结果.xlsx'
        
        print("=" * 50)
        print("词频统计工具")
        print("=" * 50)
        
        # 检查文件是否存在
        print(f"\n1. 检查文件...")
        print(f"   标准词库: {os.path.exists(vocab_path)}")
        print(f"   原始文档: {os.path.exists(docx_path)}")
        
        if not os.path.exists(vocab_path):
            print(f"   错误：找不到标准词库文件: {vocab_path}")
            return
        
        if not os.path.exists(docx_path):
            print(f"   错误：找不到原始文档: {docx_path}")
            return
        
        # 读取标准词库
        print(f"\n2. 读取标准词库...")
        try:
            df_vocab = pd.read_excel(vocab_path)
            print(f"   列名: {df_vocab.columns.tolist()}")
            print(f"   词汇数量: {len(df_vocab)}")
        except Exception as e:
            print(f"Error reading excel: {e}")
            raise
        
        # 获取词汇列
        word_column = None
        for col in ['实体名', '词汇', '标准词', df_vocab.columns[0]]:
            if col in df_vocab.columns:
                word_column = col
                break
        
        if word_column is None:
            word_column = df_vocab.columns[0]
        
        print(f"   使用列: {word_column}")
        words = df_vocab[word_column].dropna().unique().tolist()
        print(f"   去重后词汇数: {len(words)}")
        
        # 读取原始文档
        print(f"\n3. 读取原始文档...")
        doc_text = read_docx(docx_path)
        print(f"   文档字符数: {len(doc_text)}")
        
        # 统计词频
        print(f"\n4. 统计词频...")
        results = count_word_frequency(doc_text, words)
        
        # 转换为DataFrame
        df_result = pd.DataFrame(results)
        df_result = df_result.sort_values('词频', ascending=False)
        
        # 统计信息
        total_words = len(df_result)
        words_with_freq = len(df_result[df_result['词频'] > 0])
        words_without_freq = len(df_result[df_result['词频'] == 0])
        
        print(f"\n5. 统计结果:")
        print(f"   总词汇数: {total_words}")
        print(f"   有词频的词汇数: {words_with_freq}")
        print(f"   无词频的词汇数: {words_without_freq}")
        
        # 保存结果
        print(f"\n6. 保存结果...")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df_result.to_excel(output_path, index=False)
        print(f"   已保存到: {output_path}")
        
        print("\n" + "=" * 50)
        print("统计完成!")
        print("=" * 50)
        
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
