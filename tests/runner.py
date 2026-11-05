"""每个 unittest 模块使用独立解释器，隔离框架替身和导入缓存。"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent


def result_counts(output: str) -> tuple[int, int]:
    counts = re.findall(r"(?m)^Ran (\d+) tests? in ", output)
    skipped = re.findall(r"(?m)^(?:OK|FAILED) \(.*?skipped=(\d+)", output)
    return (int(counts[-1]) if counts else 0, int(skipped[-1]) if skipped else 0)


def run_module(name: str) -> subprocess.CompletedProcess[str]:
    if not re.fullmatch(r"tests\.test\w+", name):
        raise ValueError(f"无效测试模块: {name}")
    if not (ROOT / "tests" / (name.split(".")[-1] + ".py")).is_file():
        raise ValueError(f"测试模块不存在: {name}")
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
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
    failed, total, completed, skipped = [], 0, 0, 0
    for name in modules:
        try:
            result = run_module(name)
        except subprocess.TimeoutExpired as exc:
            failed.append(name)
            print(f"FAIL {name}: 超过 {exc.timeout} 秒", flush=True)
            continue
        count, skipped_count = result_counts(result.stdout)
        skipped += skipped_count
        total += count
        completed += 1
        if result.returncode or not count:
            failed.append(name)
            print(f"FAIL {name}\n{result.stdout}", flush=True)
        else:
            suffix = f", {skipped_count} skipped" if skipped_count else ""
            print(f"PASS {name}: {count} tests{suffix}", flush=True)
    print(
        f"模块 {completed}/{len(modules)}，用例 {total}，跳过 {skipped}，失败模块 {len(failed)}"
    )
    return int(bool(failed))
