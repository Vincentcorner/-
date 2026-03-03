# -*- coding: utf-8 -*-
"""
共享大模型 API 调用模块

使用 SiliconFlow OpenAI 兼容 API 调用 Qwen 2.5 32B 模型。
提供文本和 JSON 两种返回格式。
"""

import json
import re
import time
import sys
import io
from pathlib import Path

# Windows 终端编码修复
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ========== 默认配置 ==========
def _get_config_path():
    """获取 api_keys.json 路径（兼容打包和开发模式）"""
    import os
    # 打包模式：优先查找 exe 所在目录旁的 config/
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        p = exe_dir / "config" / "api_keys.json"
        if p.exists():
            return p
    # 开发模式：项目根目录的 config/
    return Path(__file__).parent.parent.parent / "config" / "api_keys.json"

def _load_api_key():
    """从配置文件或环境变量读取 API Key"""
    import os
    # 优先从环境变量读取
    env_key = os.environ.get("SILICONFLOW_API_KEY")
    if env_key:
        return env_key
    # 从配置文件读取
    config_path = _get_config_path()
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            key = config.get("siliconflow", {}).get("api_key", "")
            if key and not key.startswith("在此填入"):
                return key
        except Exception:
            pass
    print("=" * 60)
    print("⚠ 未配置 API Key！请通过以下方式之一配置：")
    print("  1. 编辑 config/api_keys.json 填入 api_key")
    print("  2. 设置环境变量 SILICONFLOW_API_KEY")
    print("=" * 60)
    return ""

def _load_api_config():
    """从配置文件读取 API 配置（base_url, model）"""
    config_path = _get_config_path()
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            sf = config.get("siliconflow", {})
            return sf.get("api_base", "https://api.siliconflow.cn/v1"), sf.get("model", "Qwen/Qwen2.5-32B-Instruct")
        except Exception:
            pass
    return "https://api.siliconflow.cn/v1", "Qwen/Qwen2.5-32B-Instruct"

DEFAULT_API_KEY = _load_api_key()
DEFAULT_API_BASE, DEFAULT_MODEL = _load_api_config()
DEFAULT_INTERVAL = 5  # 调用间隔（秒）
MAX_RETRIES = 2  # 最大重试次数


def call_llm_api(system_prompt: str, user_content: str,
                 api_key: str = DEFAULT_API_KEY,
                 model: str = DEFAULT_MODEL,
                 api_base: str = DEFAULT_API_BASE,
                 temperature: float = 0.7,
                 max_tokens: int = 4096) -> str:
    """
    调用大模型 API，返回原始文本

    Args:
        system_prompt: 系统提示词
        user_content: 用户输入内容
        api_key: API Key
        model: 模型名称
        api_base: API 基础地址
        temperature: 温度参数
        max_tokens: 最大输出 token 数

    Returns:
        模型返回的原始文本，失败返回空字符串
    """
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=api_base)

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )

            content = response.choices[0].message.content
            if content:
                return content.strip()
            else:
                print(f"  [警告] API 返回空内容 (尝试 {attempt + 1}/{MAX_RETRIES + 1})")

        except Exception as e:
            print(f"  [错误] API 调用失败 (尝试 {attempt + 1}/{MAX_RETRIES + 1}): {type(e).__name__}: {e}")

        if attempt < MAX_RETRIES:
            wait = 3 * (attempt + 1)
            print(f"  [重试] {wait} 秒后重试...")
            time.sleep(wait)

    return ""


def call_llm_api_json(system_prompt: str, user_content: str, **kwargs) -> dict:
    """
    调用大模型 API，解析并返回 JSON

    Args:
        system_prompt: 系统提示词
        user_content: 用户输入内容
        **kwargs: 传递给 call_llm_api 的其他参数

    Returns:
        解析后的 dict，失败返回空 dict
    """
    raw = call_llm_api(system_prompt, user_content, **kwargs)
    if not raw:
        return {}

    # 尝试提取 JSON 块
    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', raw)
    if json_match:
        json_str = json_match.group(1)
    else:
        # 尝试直接匹配 JSON 对象
        json_match = re.search(r'\{[\s\S]*\}', raw)
        if json_match:
            json_str = json_match.group()
        else:
            print(f"  [警告] 未找到 JSON 内容: {raw[:200]}...")
            return {}

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"  [警告] JSON 解析失败: {e}")
        print(f"  [原文] {json_str[:200]}...")
        return {}
