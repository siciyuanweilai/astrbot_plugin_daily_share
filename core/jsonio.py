from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4


def write_json_atomic(path: Path, data) -> None:
    """在同一目录完成 JSON 原子替换，避免留下半写入文件。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = ["write_json_atomic"]
