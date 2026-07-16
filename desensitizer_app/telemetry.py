from __future__ import annotations

import json
import hashlib
import os
import platform
import sys
import threading
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


SETTINGS_FILE_NAME = "settings.json"
TELEMETRY_CONFIG_FILE_NAME = "telemetry.json"
TELEMETRY_LOCAL_CONFIG_FILE_NAME = "telemetry.local.json"
TELEMETRY_EXAMPLE_CONFIG_FILE_NAME = "telemetry.example.json"
TELEMETRY_OUTBOX_FILE_NAME = "telemetry-events.jsonl"
SETTINGS_SCHEMA_VERSION = 2


@dataclass
class TelemetrySettings:
    installation_id: str
    enabled: bool = True
    notice_seen: bool = False
    registered: bool = False


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
        self.outbox_path = app_home / TELEMETRY_OUTBOX_FILE_NAME
        self._outbox_lock = threading.Lock()
        self._flush_lock = threading.Lock()
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
        self._append_pending(payload)
        thread = threading.Thread(target=self._flush_pending, daemon=True)
        thread.start()

    def _append_pending(self, payload: dict[str, Any]) -> None:
        try:
            self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            with self._outbox_lock:
                with self.outbox_path.open("a", encoding="utf-8") as file:
                    file.write(line + "\n")
        except Exception:
            pass

    def _flush_pending(self) -> None:
        if not self._flush_lock.acquire(blocking=False):
            return
        try:
            with self._outbox_lock:
                pending = self._read_pending()
                self._write_pending([])
            if not pending:
                return

            remaining: list[dict[str, Any]] = []
            for payload in pending:
                if not self._post(payload):
                    remaining.append(payload)

            if remaining:
                with self._outbox_lock:
                    self._write_pending(remaining + self._read_pending())
        finally:
            self._flush_lock.release()

    def _read_pending(self) -> list[dict[str, Any]]:
        if not self.outbox_path.exists():
            return []
        pending: list[dict[str, Any]] = []
        try:
            for line in self.outbox_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                if isinstance(item, dict):
                    pending.append(item)
        except Exception:
            return []
        return pending

    def _write_pending(self, payloads: list[dict[str, Any]]) -> None:
        self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
        if not payloads:
            self.outbox_path.write_text("", encoding="utf-8")
            return
        lines = [json.dumps(payload, ensure_ascii=False, separators=(",", ":")) for payload in payloads]
        self.outbox_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _load_settings(self) -> TelemetrySettings:
        if self.settings_path.exists():
            try:
                data = json.loads(self.settings_path.read_text(encoding="utf-8"))
                machine_marker = str(data.get("machine_marker") or "")
                if int(data.get("settings_schema_version") or 0) >= SETTINGS_SCHEMA_VERSION and machine_marker == _current_machine_marker():
                    installation_id = str(data.get("installation_id") or "").strip() or str(uuid.uuid4())
                return TelemetrySettings(
                    installation_id=installation_id,
                    enabled=bool(data.get("telemetry_enabled", True)),
                    notice_seen=bool(data.get("telemetry_notice_seen", False)),
                    registered=bool(data.get("telemetry_registered", False)),
                )
            except Exception:
                pass
        settings = TelemetrySettings(installation_id=str(uuid.uuid4()))
        settings = TelemetrySettings(installation_id=str(uuid.uuid4()))
        self._write_settings(settings)
        return settings

    def _save_settings(self) -> None:
        self._write_settings(self.settings)

    def _write_settings(self, settings: TelemetrySettings) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "settings_schema_version": SETTINGS_SCHEMA_VERSION,
            "installation_id": settings.installation_id,
            "machine_marker": _current_machine_marker(),
            "telemetry_enabled": settings.enabled,
            "telemetry_notice_seen": settings.notice_seen,
            "telemetry_registered": settings.registered,
        }
        self.settings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _post(self, payload: dict[str, Any]) -> bool:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=4) as response:
                response.read()
            return True
        except Exception:
            return False


def _load_endpoint(app_home: Path) -> str:
    endpoint = os.environ.get("DESENSITIZER_TELEMETRY_ENDPOINT", "").strip()
    if endpoint:
        return endpoint
    for config_path in _telemetry_config_paths(app_home):
        endpoint = _load_endpoint_from_file(config_path)
        if endpoint:
            return endpoint
    return ""


def _telemetry_config_paths(app_home: Path) -> list[Path]:
    directories: list[Path] = [app_home]
    if getattr(sys, "frozen", False):
        directories.append(Path(sys.executable).resolve().parent)
    directories.append(Path(getattr(sys, "_MEIPASS", app_home)))

    paths: list[Path] = []
    seen: set[str] = set()
    for directory in directories:
        for filename in (TELEMETRY_CONFIG_FILE_NAME, TELEMETRY_LOCAL_CONFIG_FILE_NAME):
            path = directory / filename
            key = str(path.resolve()) if path.exists() else str(path)
            if key in seen:
                continue
            seen.add(key)
            paths.append(path)
    return paths


def _load_endpoint_from_file(config_path: Path) -> str:
    if not config_path.exists():
        return ""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return ""
    endpoint = str(data.get("endpoint") or "").strip()
    if not endpoint or "example.com" in endpoint or "本机IP" in endpoint:
        return ""
    return endpoint


def _current_machine_marker() -> str:
    raw = f"{platform.system()}|{platform.node()}|{uuid.getnode()}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:32]


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
