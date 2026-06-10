"""pytest 配置文件，设置测试模块的导入路径。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
