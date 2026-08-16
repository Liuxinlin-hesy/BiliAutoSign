# -*- coding: utf-8 -*-
"""青龙面板入口脚本。

用法（青龙定时任务命令）：
  task BiliAutoSign/qinglong/entry.py
  或
  python3 /ql/scripts/BiliAutoSign/qinglong/entry.py

支持两种部署布局：
1. 仓库整体 clone 到青龙（推荐）：本文件位于项目 qinglong/ 下，自动定位项目根；
2. 仅复制本文件到 /ql/scripts：通过环境变量 BILI_ROOT 指定项目根。
"""
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.environ.get("BILI_ROOT", "").strip() or _PROJECT_ROOT
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

if __name__ == "__main__":
    from main import main

    main()
