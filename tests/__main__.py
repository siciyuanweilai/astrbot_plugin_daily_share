"""运行完整、隔离的回归测试：python -m tests [tests.testhealth ...]。"""

import sys

from .runner import main

raise SystemExit(main(sys.argv[1:]))
