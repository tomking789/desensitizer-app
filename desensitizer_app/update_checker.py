"""
静默更新检查模块 - 软件启动时自动向云端报告使用量并检查更新

无弹窗、无授权、用户无感知。
"""

from __future__ import annotations

import hashlib
import json
import platform
import threading
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


def _machine_id() -> str:
    raw = f"{platform.system()}|{platform.node()}|{uuid.getnode()}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


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
            pass  # 静默失败，不影响用户使用

    thread = threading.Thread(target=_do_check, daemon=True)
    thread.start()
