"""
静默更新检查模块 - 软件启动时自动记录使用量并检查更新

每次启动自动写入本地日志（%APPDATA%），同时尝试向云端上报。
本地日志供统计查看器读取，无需服务端即可查看累计数据。
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import threading
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


_USAGE_DIR = Path(os.environ.get("APPDATA", Path.home())) / "DesensitizerTool"
_USAGE_FILE = _USAGE_DIR / "usage.jsonl"


def _machine_id() -> str:
    raw = f"{platform.system()}|{platform.node()}|{uuid.getnode()}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _log_locally(app_version: str) -> None:
    _USAGE_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": app_version,
        "machine_id": _machine_id(),
        "event": "check_update",
    }
    try:
        with open(_USAGE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def check_for_update(
    app_version: str,
    endpoint: str,
    on_update_available: Callable[[str, str], None] | None = None,
    timeout: int = 5,
) -> None:
    """
    静默检查更新（在后台线程中执行，不阻塞主线程）

    Args:
        app_version: 当前软件版本号
        endpoint: 云端服务地址，如 http://your-server:8766/check-update
        on_update_available: 发现新版本时的回调函数，参数为 (当前版本, 最新版本)
        timeout: 请求超时秒数
    """
    _log_locally(app_version)

    if not endpoint:
        return

    def _do_check():
        try:
            url = f"{endpoint}?version={app_version}&machine={_machine_id()}&event=check_update&t={datetime.now(timezone.utc).isoformat()}"
            request = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                data = json.loads(resp.read())
                if data.get("update_available") and on_update_available:
                    latest = data.get("latest_version", "")
                    if latest and latest != app_version:
                        on_update_available(app_version, latest)
        except Exception:
            pass

    thread = threading.Thread(target=_do_check, daemon=True)
    thread.start()
