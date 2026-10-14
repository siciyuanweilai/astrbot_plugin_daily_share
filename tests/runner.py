"""每个 unittest 模块使用独立解释器，隔离框架替身和导入缓存。"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_module(name: str) -> subprocess.CompletedProcess[str]:
    if not re.fullmatch(r"tests\.test\w+", name):
        raise ValueError(f"无效测试模块: {name}")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        (str(ROOT), str(ROOT.parent), env.get("PYTHONPATH", ""))
    )
    # 框架导入会初始化相对 data 目录，测试不得把配置写进插件源码目录。
    with TemporaryDirectory(prefix="daily-share-tests-") as workdir:
        env["ASTRBOT_ROOT"] = workdir
        return subprocess.run(
            [sys.executable, "-m", "unittest", "-q", name],
            cwd=workdir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )


def main(names: list[str] | None = None) -> int:
    modules = names or [
        f"tests.{path.stem}" for path in sorted((ROOT / "tests").glob("test*.py"))
    ]
    failed, total, completed = [], 0, 0
    for name in modules:
        try:
            result = run_module(name)
        except subprocess.TimeoutExpired as exc:
            failed.append(name)
            print(f"FAIL {name}: 超过 {exc.timeout} 秒", flush=True)
            continue
        counts = re.findall(r"Ran (\d+) tests? in", result.stdout)
        count = int(counts[-1]) if counts else 0
        total += count
        completed += 1
        if result.returncode or not count:
            failed.append(name)
            print(f"FAIL {name}\n{result.stdout}", flush=True)
        else:
            print(f"PASS {name}: {count} tests", flush=True)
    print(f"模块 {completed}/{len(modules)}，用例 {total}，失败模块 {len(failed)}")
    return int(bool(failed))
