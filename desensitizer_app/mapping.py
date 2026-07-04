from __future__ import annotations

import base64
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


PLACEHOLDER_RE = re.compile(r"^<([A-Z0-9_]+)_(\d{3,})>$")
ENCRYPTED_MAPPING_FORMAT = "local-desensitizer-encrypted-mapping"
KDF_ITERATIONS = 390_000


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
    def load(cls, path: Path, password: str | None = None) -> "MappingStore":
        store = cls()
        data = _read_mapping_json(path, password)
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

    def add_explicit(self, value: str, entity: str, prefix: str, placeholder: str) -> None:
        if not value:
            raise ValueError("Mapping value cannot be empty.")
        if not placeholder:
            raise ValueError("Mapping placeholder cannot be empty.")
        existing_key = self._by_key.get((entity, value))
        if existing_key:
            if existing_key.placeholder != placeholder:
                raise ValueError(f"Conflicting replacement for value: {value}")
            return
        existing_placeholder = self._by_placeholder.get(placeholder)
        if existing_placeholder and existing_placeholder.value != value:
            raise ValueError(f"Replacement is already used: {placeholder}")
        self._add_record(
            MappingRecord(
                placeholder=placeholder,
                entity=entity,
                prefix=prefix,
                value=value,
            )
        )

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

    def save_encrypted(self, path: Path, password: str) -> None:
        if not password:
            raise ValueError("Encrypted mapping password cannot be empty.")
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
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        salt = os.urandom(16)
        token = Fernet(_derive_key(password, salt)).encrypt(payload)
        encrypted_data = {
            "format": ENCRYPTED_MAPPING_FORMAT,
            "version": 1,
            "kdf": "PBKDF2HMAC-SHA256",
            "iterations": KDF_ITERATIONS,
            "salt": base64.urlsafe_b64encode(salt).decode("ascii"),
            "payload": token.decode("ascii"),
        }
        path.write_text(json.dumps(encrypted_data, ensure_ascii=False, indent=2), encoding="utf-8")

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


def is_encrypted_mapping(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return path.suffix.lower() == ".enc"
    return data.get("format") == ENCRYPTED_MAPPING_FORMAT


def _read_mapping_json(path: Path, password: str | None) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != ENCRYPTED_MAPPING_FORMAT:
        return data
    if not password:
        raise ValueError("This mapping file is encrypted. Please enter the mapping password.")
    try:
        salt = base64.urlsafe_b64decode(data["salt"].encode("ascii"))
        token = data["payload"].encode("ascii")
        plaintext = Fernet(_derive_key(password, salt)).decrypt(token)
    except (InvalidToken, KeyError, ValueError) as exc:
        raise ValueError("Cannot decrypt mapping file. The password may be incorrect or the file may be damaged.") from exc
    return json.loads(plaintext.decode("utf-8"))


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))
