from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class CandidateItem:
    id: str
    enabled: bool
    entity: str
    prefix: str
    value: str
    replacement: str
    context_key: str | None = None
    context_label: str = ""
    count: int = 0
    files: set[str] = field(default_factory=set)
    source: str = "auto"


@dataclass(frozen=True)
class CandidateHit:
    entity: str
    prefix: str
    value: str
    count: int
    file: Path
    context_key: str | None = None
    context_label: str = ""
    source: str = "auto"


@dataclass(frozen=True)
class ReplacementSpec:
    entity: str
    prefix: str
    value: str
    replacement: str
    context_key: str | None = None
    context_label: str = ""


ENTITY_PREFIXES: dict[str, str] = {
    "PERSON": "PERSON",
    "ORGANIZATION": "ORG",
    "CUSTOM_TERM": "CUSTOM",
    "CN_PHONE": "PHONE",
    "CN_ID_CARD": "ID",
    "EMAIL": "EMAIL",
    "BANK_CARD": "CARD",
    "CN_SOCIAL_CREDIT_CODE": "USCC",
    "IP_ADDRESS": "IP",
    "URL": "URL",
    "DOCUMENT_ID": "DOCID",
    "SECRET": "SECRET",
}


def prefix_for_entity(entity: str) -> str:
    return ENTITY_PREFIXES.get(entity, _sanitize_prefix(entity))


def next_placeholder(prefix: str, existing: Iterable[str]) -> str:
    used = set(existing)
    index = 1
    while True:
        placeholder = f"<{prefix}_{index:03d}>"
        if placeholder not in used:
            return placeholder
        index += 1


def _sanitize_prefix(value: str) -> str:
    prefix = "".join(char for char in value.upper() if char.isalnum() or char == "_")
    return prefix or "CUSTOM"
