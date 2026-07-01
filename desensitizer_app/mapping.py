from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PLACEHOLDER_RE = re.compile(r"^<([A-Z0-9_]+)_(\d{3,})>$")


@dataclass
class MappingRecord:
    placeholder: str
    entity: str
    prefix: str
    value: str


class MappingStore:
    def __init__(self) -> None:
        self._records: list[MappingRecord] = []
        self._by_key: dict[tuple[str, str], MappingRecord] = {}
        self._by_placeholder: dict[str, MappingRecord] = {}
        self._counters: dict[str, int] = defaultdict(int)

    @classmethod
    def load(cls, path: Path) -> "MappingStore":
        store = cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data.get("records", []):
            record = MappingRecord(
                placeholder=item["placeholder"],
                entity=item.get("entity", item.get("prefix", "UNKNOWN")),
                prefix=item.get("prefix", item.get("entity", "UNKNOWN")),
                value=item["value"],
            )
            store._add_record(record)
        return store

    @property
    def records(self) -> list[MappingRecord]:
        return list(self._records)

    def get_or_add(self, value: str, entity: str, prefix: str) -> str:
        key = (entity, value)
        existing = self._by_key.get(key)
        if existing:
            return existing.placeholder
        self._counters[prefix] += 1
        placeholder = f"<{prefix}_{self._counters[prefix]:03d}>"
        while placeholder in self._by_placeholder:
            self._counters[prefix] += 1
            placeholder = f"<{prefix}_{self._counters[prefix]:03d}>"
        record = MappingRecord(
            placeholder=placeholder,
            entity=entity,
            prefix=prefix,
            value=value,
        )
        self._add_record(record)
        return placeholder

    def save(self, path: Path) -> None:
        data: dict[str, Any] = {
            "version": 1,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "records": [
                {
                    "placeholder": record.placeholder,
                    "entity": record.entity,
                    "prefix": record.prefix,
                    "value": record.value,
                }
                for record in self._records
            ],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def restore_text(self, text: str) -> str:
        restored = text
        for record in sorted(self._records, key=lambda item: len(item.placeholder), reverse=True):
            restored = restored.replace(record.placeholder, record.value)
        return restored

    def _add_record(self, record: MappingRecord) -> None:
        self._records.append(record)
        self._by_key[(record.entity, record.value)] = record
        self._by_placeholder[record.placeholder] = record
        match = PLACEHOLDER_RE.match(record.placeholder)
        if match:
            self._counters[record.prefix] = max(self._counters[record.prefix], int(match.group(2)))
