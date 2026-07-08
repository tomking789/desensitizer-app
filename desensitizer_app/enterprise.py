from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EnterpriseTerm:
    value: str
    entity: str = "CUSTOM_TERM"
    category: str = ""
    note: str = ""


@dataclass
class EnterpriseProfile:
    enabled: bool = False
    customer_name: str = ""
    customer_short_name: str = ""
    product_name: str = ""
    edition_name: str = ""
    banner_text: str = ""
    logo_path: Path | None = None
    terms: list[EnterpriseTerm] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.customer_short_name or self.customer_name

    @property
    def app_title_suffix(self) -> str:
        if not self.enabled or not self.display_name:
            return ""
        return f"{self.display_name}专用"

    @property
    def term_values(self) -> list[str]:
        return [term.value for term in self.terms if term.value]


def load_enterprise_profile(base_dir: Path) -> EnterpriseProfile:
    profile_path = base_dir / "profile.json"
    if not profile_path.exists():
        return EnterpriseProfile()

    data = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    profile = EnterpriseProfile(
        enabled=bool(data.get("enabled", False)),
        customer_name=str(data.get("customer_name", "")).strip(),
        customer_short_name=str(data.get("customer_short_name", "")).strip(),
        product_name=str(data.get("product_name", "")).strip(),
        edition_name=str(data.get("edition_name", "")).strip(),
        banner_text=str(data.get("banner_text", "")).strip(),
        logo_path=_resolve_logo_path(base_dir, data.get("logo_path")),
    )
    profile.terms = _dedupe_terms(
        [
            *_terms_from_json(data.get("default_terms", [])),
            *load_terms_file(base_dir / "terms.csv"),
            *load_terms_file(base_dir / "terms.txt"),
        ]
    )
    return profile


def _resolve_logo_path(base_dir: Path, configured_path: object) -> Path | None:
    candidates: list[Path] = []
    if configured_path:
        path = Path(str(configured_path).strip())
        candidates.append(path if path.is_absolute() else base_dir / path)
    candidates.extend([base_dir / "logo.png", base_dir / "logo.gif"])
    for path in candidates:
        if path.exists():
            return path
    return None


def load_terms_file(path: Path) -> list[EnterpriseTerm]:
    if not path.exists():
        return []
    if path.suffix.lower() == ".csv":
        return _terms_from_csv(path)
    return _terms_from_text(path)


def _terms_from_json(items: Any) -> list[EnterpriseTerm]:
    terms: list[EnterpriseTerm] = []
    if not isinstance(items, list):
        return terms
    for item in items:
        if isinstance(item, str):
            value = item.strip()
            if value:
                terms.append(EnterpriseTerm(value=value))
            continue
        if not isinstance(item, dict):
            continue
        value = str(item.get("value", "")).strip()
        if not value:
            continue
        terms.append(
            EnterpriseTerm(
                value=value,
                entity=str(item.get("entity", "CUSTOM_TERM")).strip() or "CUSTOM_TERM",
                category=str(item.get("category", "")).strip(),
                note=str(item.get("note", "")).strip(),
            )
        )
    return terms


def _terms_from_csv(path: Path) -> list[EnterpriseTerm]:
    terms: list[EnterpriseTerm] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(2048)
        handle.seek(0)
        has_header = _csv_has_known_header(sample)
        if has_header:
            reader = csv.DictReader(handle)
            for row in reader:
                normalized_row = _normalize_csv_row(row)
                enabled = str(normalized_row.get("enabled", "1")).strip().lower()
                if enabled in {"0", "false", "no", "否", "停用"}:
                    continue
                value = str(normalized_row.get("value", "")).strip()
                if not value:
                    continue
                terms.append(
                    EnterpriseTerm(
                        value=value,
                        entity=str(normalized_row.get("entity", "CUSTOM_TERM")).strip() or "CUSTOM_TERM",
                        category=str(normalized_row.get("category", "")).strip(),
                        note=str(normalized_row.get("note", "")).strip(),
                    )
                )
        else:
            reader = csv.reader(handle)
            for row in reader:
                if not row:
                    continue
                value = row[0].strip()
                if value:
                    terms.append(EnterpriseTerm(value=value))
    return terms


def _csv_has_known_header(sample: str) -> bool:
    if not sample.strip():
        return False
    try:
        first_row = next(csv.reader(sample.splitlines()))
    except (StopIteration, csv.Error):
        return False
    normalized = {_normalize_csv_header(column) for column in first_row}
    return "value" in normalized


def _normalize_csv_row(row: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in row.items():
        normalized_key = _normalize_csv_header(key)
        if normalized_key:
            normalized[normalized_key] = value
    return normalized


def _normalize_csv_header(header: str | None) -> str:
    if not header:
        return ""
    value = str(header).strip().lstrip("\ufeff")
    if "(" in value and ")" in value:
        inside = value[value.find("(") + 1 : value.find(")")].strip()
        if inside:
            value = inside
    if "（" in value and "）" in value:
        inside = value[value.find("（") + 1 : value.find("）")].strip()
        if inside:
            value = inside
    value = value.strip().lower()
    aliases = {
        "词汇": "value",
        "原文": "value",
        "敏感词": "value",
        "企业词汇": "value",
        "value": "value",
        "类型": "entity",
        "实体类型": "entity",
        "entity": "entity",
        "分类": "category",
        "类别": "category",
        "category": "category",
        "备注": "note",
        "说明": "note",
        "note": "note",
        "启用": "enabled",
        "是否启用": "enabled",
        "enabled": "enabled",
    }
    return aliases.get(value, value)


def _terms_from_text(path: Path) -> list[EnterpriseTerm]:
    terms: list[EnterpriseTerm] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        terms.append(EnterpriseTerm(value=value))
    return terms


def _dedupe_terms(terms: list[EnterpriseTerm]) -> list[EnterpriseTerm]:
    seen: set[str] = set()
    result: list[EnterpriseTerm] = []
    for term in terms:
        key = term.value.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(term)
    return result
