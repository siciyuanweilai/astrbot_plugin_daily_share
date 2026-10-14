"""pytest 与 unittest 使用同一个按模块隔离的完整测试入口。"""

from pathlib import Path

import pytest

from tests.runner import run_module

_TESTS_DIR = Path(__file__).parent


class IsolatedTestModule(pytest.File):
    def collect(self):
        yield IsolatedUnitTests.from_parent(self, name=self.path.stem)


class IsolatedUnitTests(pytest.Item):
    def runtest(self):
        result = run_module(f"tests.{self.name}")
        if result.returncode or "Ran 0 tests" in result.stdout:
            pytest.fail(result.stdout, pytrace=False)


def pytest_configure(config: pytest.Config):
    config.addinivalue_line("python_files", "test*.py")


def pytest_collect_directory(path: Path, parent: pytest.Collector):
    # 测试由子进程导入；收集器不应先执行插件包的生产初始化入口。
    if path in (_TESTS_DIR, _TESTS_DIR.parent):
        return pytest.Dir.from_parent(parent, path=path)
    return None


def pytest_pycollect_makemodule(module_path: Path, parent: pytest.Collector):
    if (
        module_path.parent == _TESTS_DIR
        and module_path.suffix == ".py"
        and module_path.name.startswith("test")
    ):
        return IsolatedTestModule.from_parent(parent, path=module_path)
    return None
