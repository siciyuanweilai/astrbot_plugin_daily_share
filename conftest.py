"""保留既有测试文件名，并隔离测试运行时替身。"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).parent / "tests"
_RUNTIME_MODULE_PREFIXES = (
    "astrbot",
    "aiohttp",
    "aiofiles",
    "astrbot_plugin_daily_share",
)


def _is_runtime_module(name: str) -> bool:
    return any(
        name == prefix or name.startswith(f"{prefix}.")
        for prefix in _RUNTIME_MODULE_PREFIXES
    )


def pytest_collect_file(file_path: Path, parent: pytest.Collector):
    """收集沿用 ``testxxx.py`` 命名的 unittest 测试模块。"""
    if (
        file_path.parent == _TESTS_DIR
        and file_path.suffix == ".py"
        and file_path.name.startswith("test")
        and file_path.name != "__init__.py"
    ):
        return pytest.Module.from_parent(parent, path=file_path)
    return None


@pytest.fixture(autouse=True)
def restore_runtime_modules() -> Iterator[None]:
    """防止测试替身泄漏到后续模块。"""
    before = {
        name: module
        for name, module in sys.modules.items()
        if _is_runtime_module(name)
    }
    yield
    for name in [name for name in sys.modules if _is_runtime_module(name)]:
        if name not in before:
            sys.modules.pop(name, None)
    sys.modules.update(before)
