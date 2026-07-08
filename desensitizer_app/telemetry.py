from __future__ import annotations

import json
import os
import platform
import threading
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


SETTINGS_FILE_NAME = "settings.json"
TELEMETRY_CONFIG_FILE_NAME = "telemetry.json"


@dataclass
class TelemetrySettings:
    installation_id: str
    enabled: bool = True
    notice_seen: bool = False


class AnonymousTelemetry:
    def __init__(
        self,
        app_home: Path,
        app_version: str,
        edition_provider: Callable[[], str],
    ) -> None:
        self.app_home = app_home
        self.app_version = app_version
        self.edition_provider = edition_provider
        self.settings_path = app_home / SETTINGS_FILE_NAME
        self.endpoint = _load_endpoint(app_home)
        self.settings = self._load_settings()

    def is_enabled(self) -> bool:
        return bool(self.settings.enabled)

    def has_endpoint(self) -> bool:
        return bool(self.endpoint)

    def set_enabled(self, enabled: bool) -> None:
        self.settings.enabled = bool(enabled)
        self._save_settings()

    def notice_seen(self) -> bool:
        return bool(self.settings.notice_seen)

    def mark_notice_seen(self) -> None:
        self.settings.notice_seen = True
        self._save_settings()

    def track(self, event_name: str, properties: dict[str, Any] | None = None) -> None:
        if not self.settings.enabled or not self.endpoint:
            return
        payload = {
            "event": event_name,
            "installation_id": self.settings.installation_id,
            "app_version": self.app_version,
            "edition": self.edition_provider(),
            "os": platform.system(),
            "os_version": platform.release(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "properties": _safe_properties(properties or {}),
        }
        thread = threading.Thread(target=self._post, args=(payload,), daemon=True)
        thread.start()

    def _load_settings(self) -> TelemetrySettings:
        if self.settings_path.exists():
            try:
                data = json.loads(self.settings_path.read_text(encoding="utf-8"))
                installation_id = str(data.get("installation_id") or "").strip() or str(uuid.uuid4())
                return TelemetrySettings(
                    installation_id=installation_id,
                    enabled=bool(data.get("telemetry_enabled", True)),
                    notice_seen=bool(data.get("telemetry_notice_seen", False)),
                )
            except Exception:
                pass
        settings = TelemetrySettings(installation_id=str(uuid.uuid4()))
        self._write_settings(settings)
        return settings

    def _save_settings(self) -> None:
        self._write_settings(self.settings)

    def _write_settings(self, settings: TelemetrySettings) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "installation_id": settings.installation_id,
            "telemetry_enabled": settings.enabled,
            "telemetry_notice_seen": settings.notice_seen,
        }
        self.settings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _post(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=4):
                pass
        except Exception:
            pass


def _load_endpoint(app_home: Path) -> str:
    endpoint = os.environ.get("DESENSITIZER_TELEMETRY_ENDPOINT", "").strip()
    if endpoint:
        return endpoint
    config_path = app_home / TELEMETRY_CONFIG_FILE_NAME
    if not config_path.exists():
        return ""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return ""
    return str(data.get("endpoint") or "").strip()


def _safe_properties(properties: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in properties.items():
        key_text = str(key)
        safe_value = _safe_value(key_text, value)
        if safe_value is not _SKIP:
            safe[key_text] = safe_value
    return safe


_SKIP = object()
_DENIED_PROPERTY_KEYS = {"path", "file", "filename", "content", "text", "term", "mapping"}


def _safe_value(key: str, value: Any) -> Any:
    if key.lower() in _DENIED_PROPERTY_KEYS:
        return _SKIP
    allowed_types = (str, int, float, bool)
    if isinstance(value, allowed_types) or value is None:
        return value
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        nested: dict[str, Any] = {}
        for item_key, item_value in value.items():
            nested_value = _safe_value(str(item_key), item_value)
            if nested_value is _SKIP:
                continue
            nested[str(item_key)] = nested_value
        return nested
    return _SKIP
