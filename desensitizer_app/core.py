from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

from .candidates import ReplacementSpec
from .mapping import MappingStore
from .rules import find_sensitive_spans

ZWSP_MARKER = "\u2060"  # WORD JOINER — invisible; marks code boundaries


class DesensitizeError(Exception):
    """Raised when a file cannot be processed safely."""


class SkippedFile(DesensitizeError):
    """Raised when a file is intentionally skipped by current capabilities."""


def anonymize_text(
    text: str,
    mapping: MappingStore,
    custom_terms: Iterable[str] = (),
) -> tuple[str, Counter[str]]:
    findings = find_sensitive_spans(text, custom_terms)
    if not findings:
        return text, Counter()
    parts: list[str] = []
    last = 0
    counts: Counter[str] = Counter()
    for finding in findings:
        parts.append(text[last : finding.start])
        placeholder = mapping.get_or_add(finding.value, finding.entity, finding.prefix)
        parts.append(placeholder)
        counts[finding.entity] += 1
        last = finding.end
    parts.append(text[last:])
    return "".join(parts), counts


def apply_replacements_text(
    text: str,
    replacements: Iterable[ReplacementSpec],
) -> tuple[str, Counter[str]]:
    counts: Counter[str] = Counter()
    new_text = text
    unique_replacements = _dedupe_replacements(replacements)

    codes = {r.replacement for r in unique_replacements if r.value and r.value != r.replacement}
    conflicted = _prefix_conflict_codes(codes)

    for replacement in sorted(unique_replacements, key=lambda item: len(item.value), reverse=True):
        if not replacement.value or replacement.value == replacement.replacement:
            continue
        found = new_text.count(replacement.value)
        if not found:
            continue
        code = replacement.replacement
        if code in conflicted:
            new_text = new_text.replace(replacement.value, code + ZWSP_MARKER)
        else:
            new_text = new_text.replace(replacement.value, code)
        counts[replacement.entity] += found
    return new_text, counts


def _prefix_conflict_codes(codes: set[str]) -> set[str]:
    conflicted: set[str] = set()
    for code in codes:
        for other in codes:
            if code != other and other.startswith(code):
                conflicted.add(code)
                break
    return conflicted


def _dedupe_replacements(replacements: Iterable[ReplacementSpec]) -> list[ReplacementSpec]:
    by_value: dict[str, ReplacementSpec] = {}
    for replacement in replacements:
        if replacement.context_key:
            continue
        if not replacement.value:
            continue
        existing = by_value.get(replacement.value)
        if existing:
            continue
        by_value[replacement.value] = replacement
    return list(by_value.values())


def read_text_file(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise DesensitizeError(f"Cannot decode text file: {path}")


def write_text_file(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def write_report(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = ["file", "status", "output", "message", "counts"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
