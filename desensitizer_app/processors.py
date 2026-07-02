from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path
from typing import Iterable

import pdfplumber
from docx import Document
from openpyxl import load_workbook

from .core import DesensitizeError, anonymize_text, read_text_file, write_text_file
from .mapping import MappingStore


TEXT_SUFFIXES = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".html", ".htm"}
WORD_SUFFIXES = {".docx"}
EXCEL_SUFFIXES = {".xlsx"}
PDF_SUFFIXES = {".pdf"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def anonymize_file(
    input_path: Path,
    output_dir: Path,
    mapping: MappingStore,
    custom_terms: Iterable[str] = (),
) -> tuple[Path, Counter[str], str]:
    suffix = input_path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return _anonymize_text_file(input_path, output_dir, mapping, custom_terms)
    if suffix in WORD_SUFFIXES:
        return _anonymize_docx(input_path, output_dir, mapping, custom_terms)
    if suffix in EXCEL_SUFFIXES:
        return _anonymize_xlsx(input_path, output_dir, mapping, custom_terms)
    if suffix in PDF_SUFFIXES:
        return _anonymize_pdf_text(input_path, output_dir, mapping, custom_terms)
    if suffix in IMAGE_SUFFIXES:
        raise DesensitizeError("Image OCR/redaction is not enabled in this first version.")
    raise DesensitizeError(f"Unsupported file type: {suffix or '(no extension)'}")


def restore_file(input_path: Path, output_dir: Path, mapping: MappingStore) -> tuple[Path, str]:
    suffix = input_path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        text = read_text_file(input_path)
        output_path = _output_path(input_path, output_dir, "restored", suffix)
        write_text_file(output_path, mapping.restore_text(text))
        return output_path, "Text restored."
    if suffix in WORD_SUFFIXES:
        output_path = _output_path(input_path, output_dir, "restored", suffix)
        document = Document(str(input_path))
        _restore_docx_document(document, mapping)
        document.save(str(output_path))
        return output_path, "Word document restored."
    if suffix in EXCEL_SUFFIXES:
        output_path = _output_path(input_path, output_dir, "restored", suffix)
        workbook = load_workbook(input_path)
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str):
                        cell.value = mapping.restore_text(cell.value)
        workbook.save(output_path)
        return output_path, "Excel workbook restored."
    raise DesensitizeError("This file type cannot be restored by the current version.")


def _anonymize_text_file(
    input_path: Path,
    output_dir: Path,
    mapping: MappingStore,
    custom_terms: Iterable[str],
) -> tuple[Path, Counter[str], str]:
    text = read_text_file(input_path)
    new_text, counts = anonymize_text(text, mapping, custom_terms)
    output_path = _output_path(input_path, output_dir, "desensitized", input_path.suffix)
    write_text_file(output_path, new_text)
    return output_path, counts, "Text file processed."


def _anonymize_docx(
    input_path: Path,
    output_dir: Path,
    mapping: MappingStore,
    custom_terms: Iterable[str],
) -> tuple[Path, Counter[str], str]:
    output_path = _output_path(input_path, output_dir, "desensitized", input_path.suffix)
    document = Document(str(input_path))
    counts = Counter()
    counts.update(_replace_docx_document(document, mapping, custom_terms))
    document.save(str(output_path))
    return output_path, counts, "Word document processed. Text split across runs may need manual review."


def _anonymize_xlsx(
    input_path: Path,
    output_dir: Path,
    mapping: MappingStore,
    custom_terms: Iterable[str],
) -> tuple[Path, Counter[str], str]:
    output_path = _output_path(input_path, output_dir, "desensitized", input_path.suffix)
    workbook = load_workbook(input_path)
    counts = Counter()
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if not isinstance(cell.value, str):
                    continue
                if cell.data_type == "f":
                    continue
                new_value, cell_counts = anonymize_text(cell.value, mapping, custom_terms)
                cell.value = new_value
                counts.update(cell_counts)
    workbook.save(output_path)
    return output_path, counts, "Excel workbook processed."


def _anonymize_pdf_text(
    input_path: Path,
    output_dir: Path,
    mapping: MappingStore,
    custom_terms: Iterable[str],
) -> tuple[Path, Counter[str], str]:
    pages: list[str] = []
    with pdfplumber.open(input_path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"--- Page {index} ---\n{text}")
    if not pages:
        raise DesensitizeError("No extractable text found. This may be a scanned PDF and needs OCR.")
    text = "\n\n".join(pages)
    new_text, counts = anonymize_text(text, mapping, custom_terms)
    output_path = _output_path(input_path, output_dir, "desensitized_pdf_text", ".txt")
    write_text_file(output_path, new_text)
    return output_path, counts, "PDF text extracted to TXT. Original PDF layout is not preserved in this version."


def _replace_docx_document(
    document: Document,
    mapping: MappingStore,
    custom_terms: Iterable[str],
) -> Counter[str]:
    counts = Counter()
    for paragraph in document.paragraphs:
        counts.update(_replace_runs(paragraph.runs, mapping, custom_terms))
    for table in document.tables:
        counts.update(_replace_docx_table(table, mapping, custom_terms))
    for section in document.sections:
        counts.update(_replace_header_footer(section.header, mapping, custom_terms))
        counts.update(_replace_header_footer(section.footer, mapping, custom_terms))
    return counts


def _replace_docx_table(table, mapping: MappingStore, custom_terms: Iterable[str]) -> Counter[str]:
    counts = Counter()
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                counts.update(_replace_runs(paragraph.runs, mapping, custom_terms))
            for nested_table in cell.tables:
                counts.update(_replace_docx_table(nested_table, mapping, custom_terms))
    return counts


def _replace_header_footer(part, mapping: MappingStore, custom_terms: Iterable[str]) -> Counter[str]:
    counts = Counter()
    for paragraph in part.paragraphs:
        counts.update(_replace_runs(paragraph.runs, mapping, custom_terms))
    for table in part.tables:
        counts.update(_replace_docx_table(table, mapping, custom_terms))
    return counts


def _replace_runs(runs, mapping: MappingStore, custom_terms: Iterable[str]) -> Counter[str]:
    counts = Counter()
    for run in runs:
        if not run.text:
            continue
        new_text, run_counts = anonymize_text(run.text, mapping, custom_terms)
        run.text = new_text
        counts.update(run_counts)
    return counts


def _restore_docx_document(document: Document, mapping: MappingStore) -> None:
    for paragraph in document.paragraphs:
        for run in paragraph.runs:
            if run.text:
                run.text = mapping.restore_text(run.text)
    for table in document.tables:
        _restore_docx_table(table, mapping)
    for section in document.sections:
        _restore_docx_part(section.header, mapping)
        _restore_docx_part(section.footer, mapping)


def _restore_docx_table(table, mapping: MappingStore) -> None:
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    if run.text:
                        run.text = mapping.restore_text(run.text)
            for nested_table in cell.tables:
                _restore_docx_table(nested_table, mapping)


def _restore_docx_part(part, mapping: MappingStore) -> None:
    for paragraph in part.paragraphs:
        for run in paragraph.runs:
            if run.text:
                run.text = mapping.restore_text(run.text)
    for table in part.tables:
        _restore_docx_table(table, mapping)


def _output_path(input_path: Path, output_dir: Path, label: str, suffix: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    candidate = output_dir / f"{stem}_{label}{suffix}"
    index = 2
    while candidate.exists():
        candidate = output_dir / f"{stem}_{label}_{index}{suffix}"
        index += 1
    return candidate


def copy_unsupported(input_path: Path, output_dir: Path) -> Path:
    output_path = _output_path(input_path, output_dir, "copy", input_path.suffix)
    shutil.copy2(input_path, output_path)
    return output_path
