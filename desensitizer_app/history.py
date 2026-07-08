from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class HistoryRecord:
    id: str
    timestamp: str
    action: str
    file_count: int
    ok_count: int
    failed_count: int
    skipped_count: int = 0
    output_dir: str = ""
    mapping_file: str = ""
    report_file: str = ""
    input_files: list[str] | None = None


def load_history(path: Path) -> list[HistoryRecord]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    records: list[HistoryRecord] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        records.append(
            HistoryRecord(
                id=str(item.get("id") or ""),
                timestamp=str(item.get("timestamp") or ""),
                action=str(item.get("action") or ""),
                file_count=int(item.get("file_count") or 0),
                ok_count=int(item.get("ok_count") or 0),
                failed_count=int(item.get("failed_count") or 0),
                skipped_count=int(item.get("skipped_count") or 0),
                output_dir=str(item.get("output_dir") or ""),
                mapping_file=str(item.get("mapping_file") or ""),
                report_file=str(item.get("report_file") or ""),
                input_files=list(item.get("input_files") or []),
            )
        )
    return records


def save_history(path: Path, records: list[HistoryRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [asdict(record) for record in records]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def export_history_csv(path: Path, records: list[HistoryRecord]) -> None:
    fieldnames = [
        "timestamp",
        "action",
        "file_count",
        "ok_count",
        "failed_count",
        "skipped_count",
        "output_dir",
        "mapping_file",
        "report_file",
        "input_files",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row: dict[str, Any] = asdict(record)
            row["input_files"] = "; ".join(record.input_files or [])
            row.pop("id", None)
            writer.writerow(row)
