# -*- coding: utf-8 -*-
"""
意图匹配分析平台 - 打包入口

解决 PyInstaller 打包后的资源路径问题。
双击运行后自动打开浏览器访问 http://localhost:5000
"""

import sys
import os
import webbrowser
import threading
from pathlib import Path


def get_base_path():
    """获取资源基础路径（兼容打包和开发模式）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后，资源在 _MEIPASS 临时目录
        return Path(sys._MEIPASS)
    else:
        return Path(__file__).parent


def main():
    base = get_base_path()

    # 设置工作目录为资源目录
    os.chdir(base)

    # 将项目根目录加入 sys.path
    sys.path.insert(0, str(base))

    # 延迟 1.5 秒后自动打开浏览器
    def open_browser():
        import time
        time.sleep(1.5)
        webbrowser.open("http://localhost:5000")

    threading.Thread(target=open_browser, daemon=True).start()

    # 导入并启动 Flask app
    from scripts.web_app import app
    print("=" * 50)
    print("  意图匹配分析平台")
    print("  访问地址: http://localhost:5000")
    print("  按 Ctrl+C 停止服务")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False)


if __name__ == '__main__':
    main()
