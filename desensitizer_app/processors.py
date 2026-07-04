from __future__ import annotations

import shutil
from io import BytesIO
from collections import Counter
from pathlib import Path
from typing import Iterable

import fitz
import pdfplumber
from docx import Document
from openpyxl import load_workbook
from pptx import Presentation
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from .candidates import CandidateHit, ReplacementSpec
from .core import (
    DesensitizeError,
    SkippedFile,
    anonymize_text,
    apply_replacements_text,
    read_text_file,
    write_text_file,
)
from .mapping import MappingStore
from .rules import find_sensitive_spans


TEXT_SUFFIXES = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".html", ".htm"}
WORD_SUFFIXES = {".docx"}
EXCEL_SUFFIXES = {".xlsx"}
POWERPOINT_SUFFIXES = {".pptx"}
PDF_SUFFIXES = {".pdf"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
LEGACY_OFFICE_SUFFIXES = {".doc", ".xls"}
PROCESSABLE_SUFFIXES = TEXT_SUFFIXES | WORD_SUFFIXES | EXCEL_SUFFIXES | POWERPOINT_SUFFIXES | PDF_SUFFIXES
KNOWN_SUFFIXES = PROCESSABLE_SUFFIXES | IMAGE_SUFFIXES | LEGACY_OFFICE_SUFFIXES
PDF_RESTORE_FONT = "STSong-Light"


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
    if suffix in POWERPOINT_SUFFIXES:
        return _anonymize_pptx(input_path, output_dir, mapping, custom_terms)
    if suffix in PDF_SUFFIXES:
        return _anonymize_pdf_text(input_path, output_dir, mapping, custom_terms)
    if suffix in IMAGE_SUFFIXES:
        raise SkippedFile("图片文件需要 OCR。当前轻量版不做 OCR，请先转换为文字版 PDF、Word 或文本后再处理。")
    if suffix in LEGACY_OFFICE_SUFFIXES:
        raise SkippedFile("旧版 Office 格式请先用 Word/Excel/WPS 另存为 .docx 或 .xlsx 后再处理。")
    raise DesensitizeError(f"Unsupported file type: {suffix or '(no extension)'}")


def is_known_file(path: Path) -> bool:
    return path.suffix.lower() in KNOWN_SUFFIXES


def is_processable_file(path: Path) -> bool:
    return path.suffix.lower() in PROCESSABLE_SUFFIXES


def scan_file_candidates(
    input_path: Path,
    custom_terms: Iterable[str] = (),
) -> tuple[list[CandidateHit], str]:
    suffix = input_path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        raise SkippedFile("图片文件需要 OCR。当前轻量版不做 OCR，请先转换为文字版 PDF、Word 或文本后再处理。")
    if suffix in LEGACY_OFFICE_SUFFIXES:
        raise SkippedFile("旧版 Office 格式请先用 Word/Excel/WPS 另存为 .docx 或 .xlsx 后再处理。")
    if suffix not in PROCESSABLE_SUFFIXES:
        raise DesensitizeError(f"Unsupported file type: {suffix or '(no extension)'}")
    counts: Counter[tuple[str, str, str]] = Counter()
    for chunk in _extract_text_chunks(input_path):
        for finding in find_sensitive_spans(chunk, custom_terms):
            counts[(finding.entity, finding.prefix, finding.value)] += 1
    hits = [
        CandidateHit(
            entity=entity,
            prefix=prefix,
            value=value,
            count=count,
            file=input_path,
        )
        for (entity, prefix, value), count in counts.items()
    ]
    return hits, f"{len(hits)} unique candidate(s) found."


def anonymize_file_with_replacements(
    input_path: Path,
    output_dir: Path,
    replacements: Iterable[ReplacementSpec],
) -> tuple[Path, Counter[str], str]:
    suffix = input_path.suffix.lower()
    replacement_list = list(replacements)
    if suffix in TEXT_SUFFIXES:
        return _anonymize_text_file_with_replacements(input_path, output_dir, replacement_list)
    if suffix in WORD_SUFFIXES:
        return _anonymize_docx_with_replacements(input_path, output_dir, replacement_list)
    if suffix in EXCEL_SUFFIXES:
        return _anonymize_xlsx_with_replacements(input_path, output_dir, replacement_list)
    if suffix in POWERPOINT_SUFFIXES:
        return _anonymize_pptx_with_replacements(input_path, output_dir, replacement_list)
    if suffix in PDF_SUFFIXES:
        return _anonymize_pdf_text_with_replacements(input_path, output_dir, replacement_list)
    if suffix in IMAGE_SUFFIXES:
        raise SkippedFile("图片文件需要 OCR。当前轻量版不做 OCR，请先转换为文字版 PDF、Word 或文本后再处理。")
    if suffix in LEGACY_OFFICE_SUFFIXES:
        raise SkippedFile("旧版 Office 格式请先用 Word/Excel/WPS 另存为 .docx 或 .xlsx 后再处理。")
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
    if suffix in POWERPOINT_SUFFIXES:
        output_path = _output_path(input_path, output_dir, "restored", suffix)
        presentation = Presentation(str(input_path))
        _restore_pptx_deck(presentation, mapping)
        presentation.save(str(output_path))
        return output_path, "PowerPoint deck restored."
    if suffix in PDF_SUFFIXES:
        return _restore_pdf_text(input_path, output_dir, mapping)
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


def _anonymize_pptx(
    input_path: Path,
    output_dir: Path,
    mapping: MappingStore,
    custom_terms: Iterable[str],
) -> tuple[Path, Counter[str], str]:
    output_path = _output_path(input_path, output_dir, "desensitized", input_path.suffix)
    presentation = Presentation(str(input_path))
    counts = _replace_pptx_deck(presentation, mapping, custom_terms)
    presentation.save(str(output_path))
    return output_path, counts, "PowerPoint deck processed."


def _anonymize_pdf_text(
    input_path: Path,
    output_dir: Path,
    mapping: MappingStore,
    custom_terms: Iterable[str],
) -> tuple[Path, Counter[str], str]:
    replacements: list[ReplacementSpec] = []
    for chunk in _extract_pdf_text_chunks(input_path):
        for finding in find_sensitive_spans(chunk, custom_terms):
            placeholder = mapping.get_or_add(finding.value, finding.entity, finding.prefix)
            replacements.append(
                ReplacementSpec(
                    entity=finding.entity,
                    prefix=finding.prefix,
                    value=finding.value,
                    replacement=placeholder,
                )
            )
    if not replacements:
        output_path = _output_path(input_path, output_dir, "desensitized", input_path.suffix)
        shutil.copy2(input_path, output_path)
        return output_path, Counter(), "PDF contained extractable text but no approved sensitive value was found."
    return _redact_pdf_with_replacements(input_path, output_dir, replacements)


def _anonymize_text_file_with_replacements(
    input_path: Path,
    output_dir: Path,
    replacements: list[ReplacementSpec],
) -> tuple[Path, Counter[str], str]:
    text = read_text_file(input_path)
    new_text, counts = apply_replacements_text(text, replacements)
    output_path = _output_path(input_path, output_dir, "desensitized", input_path.suffix)
    write_text_file(output_path, new_text)
    return output_path, counts, "Text file processed with approved replacements."


def _anonymize_docx_with_replacements(
    input_path: Path,
    output_dir: Path,
    replacements: list[ReplacementSpec],
) -> tuple[Path, Counter[str], str]:
    output_path = _output_path(input_path, output_dir, "desensitized", input_path.suffix)
    document = Document(str(input_path))
    counts = Counter()
    counts.update(_apply_replacements_docx_document(document, replacements))
    document.save(str(output_path))
    return output_path, counts, "Word document processed with approved replacements."


def _anonymize_xlsx_with_replacements(
    input_path: Path,
    output_dir: Path,
    replacements: list[ReplacementSpec],
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
                new_value, cell_counts = apply_replacements_text(cell.value, replacements)
                cell.value = new_value
                counts.update(cell_counts)
    workbook.save(output_path)
    return output_path, counts, "Excel workbook processed with approved replacements."


def _anonymize_pptx_with_replacements(
    input_path: Path,
    output_dir: Path,
    replacements: list[ReplacementSpec],
) -> tuple[Path, Counter[str], str]:
    output_path = _output_path(input_path, output_dir, "desensitized", input_path.suffix)
    presentation = Presentation(str(input_path))
    counts = _apply_replacements_pptx_deck(presentation, replacements)
    presentation.save(str(output_path))
    return output_path, counts, "PowerPoint deck processed with approved replacements."


def _anonymize_pdf_text_with_replacements(
    input_path: Path,
    output_dir: Path,
    replacements: list[ReplacementSpec],
) -> tuple[Path, Counter[str], str]:
    _ensure_pdf_has_extractable_text(input_path)
    return _redact_pdf_with_replacements(input_path, output_dir, replacements)


def _replace_docx_document(
    document: Document,
    mapping: MappingStore,
    custom_terms: Iterable[str],
) -> Counter[str]:
    counts = Counter()
    for paragraph in document.paragraphs:
        counts.update(_replace_paragraph(paragraph, mapping, custom_terms))
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
                counts.update(_replace_paragraph(paragraph, mapping, custom_terms))
            for nested_table in cell.tables:
                counts.update(_replace_docx_table(nested_table, mapping, custom_terms))
    return counts


def _replace_header_footer(part, mapping: MappingStore, custom_terms: Iterable[str]) -> Counter[str]:
    counts = Counter()
    for paragraph in part.paragraphs:
        counts.update(_replace_paragraph(paragraph, mapping, custom_terms))
    for table in part.tables:
        counts.update(_replace_docx_table(table, mapping, custom_terms))
    return counts


def _apply_replacements_docx_document(
    document: Document,
    replacements: list[ReplacementSpec],
) -> Counter[str]:
    counts = Counter()
    for paragraph in document.paragraphs:
        counts.update(_apply_replacements_paragraph(paragraph, replacements))
    for table in document.tables:
        counts.update(_apply_replacements_docx_table(table, replacements))
    for section in document.sections:
        counts.update(_apply_replacements_header_footer(section.header, replacements))
        counts.update(_apply_replacements_header_footer(section.footer, replacements))
    return counts


def _apply_replacements_docx_table(table, replacements: list[ReplacementSpec]) -> Counter[str]:
    counts = Counter()
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                counts.update(_apply_replacements_paragraph(paragraph, replacements))
            for nested_table in cell.tables:
                counts.update(_apply_replacements_docx_table(nested_table, replacements))
    return counts


def _apply_replacements_header_footer(part, replacements: list[ReplacementSpec]) -> Counter[str]:
    counts = Counter()
    for paragraph in part.paragraphs:
        counts.update(_apply_replacements_paragraph(paragraph, replacements))
    for table in part.tables:
        counts.update(_apply_replacements_docx_table(table, replacements))
    return counts


def _replace_paragraph(paragraph, mapping: MappingStore, custom_terms: Iterable[str]) -> Counter[str]:
    if not paragraph.text:
        return Counter()
    new_text, counts = anonymize_text(paragraph.text, mapping, custom_terms)
    if counts:
        _set_paragraph_text(paragraph, new_text)
    return counts


def _apply_replacements_paragraph(paragraph, replacements: list[ReplacementSpec]) -> Counter[str]:
    if not paragraph.text:
        return Counter()
    new_text, counts = apply_replacements_text(paragraph.text, replacements)
    if counts:
        _set_paragraph_text(paragraph, new_text)
    return counts


def _set_paragraph_text(paragraph, text: str) -> None:
    # Replacing the whole paragraph catches sensitive text split across Word runs.
    # This may flatten mixed inline formatting in that paragraph, but prevents leaks.
    if not paragraph.runs:
        paragraph.add_run(text)
        return
    paragraph.runs[0].text = text
    for run in paragraph.runs[1:]:
        run.text = ""


def _apply_replacements_runs(runs, replacements: list[ReplacementSpec]) -> Counter[str]:
    counts = Counter()
    for run in runs:
        if not run.text:
            continue
        new_text, run_counts = apply_replacements_text(run.text, replacements)
        run.text = new_text
        counts.update(run_counts)
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


def _replace_pptx_deck(
    presentation,
    mapping: MappingStore,
    custom_terms: Iterable[str],
) -> Counter[str]:
    counts = Counter()
    for slide in presentation.slides:
        counts.update(_replace_pptx_shapes(slide.shapes, mapping, custom_terms))
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            counts.update(_replace_pptx_text_frame(slide.notes_slide.notes_text_frame, mapping, custom_terms))
    return counts


def _apply_replacements_pptx_deck(
    presentation,
    replacements: list[ReplacementSpec],
) -> Counter[str]:
    counts = Counter()
    for slide in presentation.slides:
        counts.update(_apply_replacements_pptx_shapes(slide.shapes, replacements))
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            counts.update(_apply_replacements_pptx_text_frame(slide.notes_slide.notes_text_frame, replacements))
    return counts


def _restore_pptx_deck(presentation, mapping: MappingStore) -> None:
    for slide in presentation.slides:
        _restore_pptx_shapes(slide.shapes, mapping)
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            _restore_pptx_text_frame(slide.notes_slide.notes_text_frame, mapping)


def _replace_pptx_shapes(shapes, mapping: MappingStore, custom_terms: Iterable[str]) -> Counter[str]:
    counts = Counter()
    for shape in shapes:
        if getattr(shape, "has_text_frame", False):
            counts.update(_replace_pptx_text_frame(shape.text_frame, mapping, custom_terms))
        if getattr(shape, "has_table", False):
            counts.update(_replace_pptx_table(shape.table, mapping, custom_terms))
        if hasattr(shape, "shapes"):
            counts.update(_replace_pptx_shapes(shape.shapes, mapping, custom_terms))
    return counts


def _apply_replacements_pptx_shapes(shapes, replacements: list[ReplacementSpec]) -> Counter[str]:
    counts = Counter()
    for shape in shapes:
        if getattr(shape, "has_text_frame", False):
            counts.update(_apply_replacements_pptx_text_frame(shape.text_frame, replacements))
        if getattr(shape, "has_table", False):
            counts.update(_apply_replacements_pptx_table(shape.table, replacements))
        if hasattr(shape, "shapes"):
            counts.update(_apply_replacements_pptx_shapes(shape.shapes, replacements))
    return counts


def _restore_pptx_shapes(shapes, mapping: MappingStore) -> None:
    for shape in shapes:
        if getattr(shape, "has_text_frame", False):
            _restore_pptx_text_frame(shape.text_frame, mapping)
        if getattr(shape, "has_table", False):
            _restore_pptx_table(shape.table, mapping)
        if hasattr(shape, "shapes"):
            _restore_pptx_shapes(shape.shapes, mapping)


def _replace_pptx_table(table, mapping: MappingStore, custom_terms: Iterable[str]) -> Counter[str]:
    counts = Counter()
    for row in table.rows:
        for cell in row.cells:
            counts.update(_replace_pptx_text_frame(cell.text_frame, mapping, custom_terms))
    return counts


def _apply_replacements_pptx_table(table, replacements: list[ReplacementSpec]) -> Counter[str]:
    counts = Counter()
    for row in table.rows:
        for cell in row.cells:
            counts.update(_apply_replacements_pptx_text_frame(cell.text_frame, replacements))
    return counts


def _restore_pptx_table(table, mapping: MappingStore) -> None:
    for row in table.rows:
        for cell in row.cells:
            _restore_pptx_text_frame(cell.text_frame, mapping)


def _replace_pptx_text_frame(text_frame, mapping: MappingStore, custom_terms: Iterable[str]) -> Counter[str]:
    if not text_frame.text:
        return Counter()
    new_text, counts = anonymize_text(text_frame.text, mapping, custom_terms)
    if counts:
        text_frame.text = new_text
    return counts


def _apply_replacements_pptx_text_frame(text_frame, replacements: list[ReplacementSpec]) -> Counter[str]:
    if not text_frame.text:
        return Counter()
    new_text, counts = apply_replacements_text(text_frame.text, replacements)
    if counts:
        text_frame.text = new_text
    return counts


def _restore_pptx_text_frame(text_frame, mapping: MappingStore) -> None:
    if text_frame.text:
        text_frame.text = mapping.restore_text(text_frame.text)


def _restore_pdf_text(input_path: Path, output_dir: Path, mapping: MappingStore) -> tuple[Path, str]:
    output_path = _output_path(input_path, output_dir, "restored", input_path.suffix)
    replacements = [
        ReplacementSpec(
            entity=record.entity,
            prefix=record.prefix,
            value=record.placeholder,
            replacement=record.value,
        )
        for record in mapping.records
        if record.placeholder and record.value
    ]
    if not replacements:
        shutil.copy2(input_path, output_path)
        return output_path, "PDF copied. The mapping file did not contain restore records."
    counts = _restore_pdf_with_replacements(input_path, output_path, replacements)
    if not counts:
        return output_path, "PDF copied. No mapping placeholders were found in the file."
    return output_path, "PDF restored in original layout with mapping placeholders."


def _restore_pdf_with_replacements(
    input_path: Path,
    output_path: Path,
    replacements: Iterable[ReplacementSpec],
) -> Counter[str]:
    _register_pdf_restore_font()
    counts: Counter[str] = Counter()
    overlay_items: dict[int, list[tuple[fitz.Rect, str, float]]] = {}
    replacement_list = sorted(
        _unique_replacements(replacements),
        key=lambda item: len(item.value),
        reverse=True,
    )
    document = fitz.open(str(input_path))
    try:
        for page_index, page in enumerate(document):
            page_items: list[tuple[fitz.Rect, str, float]] = []
            has_redactions = False
            for replacement in replacement_list:
                rectangles = page.search_for(replacement.value)
                if not rectangles:
                    continue
                for rectangle in rectangles:
                    restore_rect, font_size = _pdf_overlay_rect_and_font(page.rect, rectangle, replacement.replacement)
                    page.add_redact_annot(restore_rect, fill=(1, 1, 1), cross_out=False)
                    page_items.append((restore_rect, replacement.replacement, font_size))
                    counts[replacement.entity] += 1
                    has_redactions = True
            if has_redactions:
                page.apply_redactions()
                overlay_items[page_index] = page_items

        if not counts:
            shutil.copy2(input_path, output_path)
            return counts

        _apply_pdf_text_overlays(document, overlay_items)
        document.save(str(output_path), garbage=4, deflate=True, clean=True)
        return counts
    finally:
        document.close()


def _register_pdf_restore_font() -> None:
    try:
        pdfmetrics.getFont(PDF_RESTORE_FONT)
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont(PDF_RESTORE_FONT))


def _pdf_overlay_rect_and_font(page_rect: fitz.Rect, source_rect: fitz.Rect, text: str) -> tuple[fitz.Rect, float]:
    rect = fitz.Rect(source_rect)
    rect.y0 = max(page_rect.y0, rect.y0 - 1)
    rect.y1 = min(page_rect.y1, rect.y1 + 2)
    font_size = min(10.0, max(5.0, rect.height * 0.78))
    available_width = max(1.0, page_rect.x1 - rect.x0 - 2)
    text_width = pdfmetrics.stringWidth(text, PDF_RESTORE_FONT, font_size)
    while text_width > available_width and font_size > 5.0:
        font_size -= 0.5
        text_width = pdfmetrics.stringWidth(text, PDF_RESTORE_FONT, font_size)
    rect.x1 = min(page_rect.x1, max(rect.x1, rect.x0 + text_width + 4))
    return rect, font_size


def _apply_pdf_text_overlays(
    document: fitz.Document,
    overlay_items: dict[int, list[tuple[fitz.Rect, str, float]]],
) -> None:
    for page_index, items in overlay_items.items():
        if not items:
            continue
        page = document[page_index]
        overlay_pdf = _build_pdf_text_overlay(page.rect, items)
        overlay_document = fitz.open("pdf", overlay_pdf)
        try:
            page.show_pdf_page(page.rect, overlay_document, 0, overlay=True)
        finally:
            overlay_document.close()


def _build_pdf_text_overlay(
    page_rect: fitz.Rect,
    items: list[tuple[fitz.Rect, str, float]],
) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(page_rect.width, page_rect.height))
    pdf.setFillColorRGB(0, 0, 0)
    for rect, text, font_size in items:
        baseline = page_rect.height - rect.y1 + max(1.0, (rect.height - font_size) * 0.45)
        pdf.setFont(PDF_RESTORE_FONT, font_size)
        pdf.drawString(rect.x0, baseline, text)
    pdf.save()
    return buffer.getvalue()


def _redact_pdf_with_replacements(
    input_path: Path,
    output_dir: Path,
    replacements: Iterable[ReplacementSpec],
) -> tuple[Path, Counter[str], str]:
    output_path = _output_path(input_path, output_dir, "desensitized", input_path.suffix)
    _register_pdf_restore_font()
    counts: Counter[str] = Counter()
    overlay_items: dict[int, list[tuple[fitz.Rect, str, float]]] = {}
    replacement_list = sorted(
        _unique_replacements(replacements),
        key=lambda item: len(item.value),
        reverse=True,
    )
    document = fitz.open(str(input_path))
    try:
        for page in document:
            has_redactions = False
            for replacement in replacement_list:
                if not replacement.value:
                    continue
                rectangles = page.search_for(replacement.value)
                if not rectangles:
                    continue
                for rectangle in rectangles:
                    redact_rect, font_size = _pdf_overlay_rect_and_font(page.rect, rectangle, replacement.replacement)
                    page.add_redact_annot(redact_rect, fill=(1, 1, 1), cross_out=False)
                    overlay_items.setdefault(page.number, []).append((redact_rect, replacement.replacement, font_size))
                    counts[replacement.entity] += 1
                    has_redactions = True
            if has_redactions:
                page.apply_redactions()
        if not counts:
            shutil.copy2(input_path, output_path)
        else:
            _apply_pdf_text_overlays(document, overlay_items)
            document.save(str(output_path), garbage=4, deflate=True, clean=True)
    finally:
        document.close()
    return output_path, counts, "PDF redacted in original layout with approved replacements."


def _unique_replacements(replacements: Iterable[ReplacementSpec]) -> list[ReplacementSpec]:
    by_value: dict[str, ReplacementSpec] = {}
    for replacement in replacements:
        if replacement.value and replacement.value not in by_value:
            by_value[replacement.value] = replacement
    return list(by_value.values())


def _extract_text_chunks(input_path: Path) -> list[str]:
    suffix = input_path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return [read_text_file(input_path)]
    if suffix in WORD_SUFFIXES:
        document = Document(str(input_path))
        return _iter_docx_text_chunks(document)
    if suffix in EXCEL_SUFFIXES:
        workbook = load_workbook(input_path, data_only=False, read_only=True)
        chunks: list[str] = []
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str):
                        chunks.append(cell.value)
        workbook.close()
        return chunks
    if suffix in POWERPOINT_SUFFIXES:
        presentation = Presentation(str(input_path))
        return _iter_pptx_text_chunks(presentation)
    if suffix in PDF_SUFFIXES:
        return _extract_pdf_text_chunks(input_path)
    raise DesensitizeError(f"Unsupported file type: {suffix or '(no extension)'}")


def _extract_pdf_text_chunks(input_path: Path) -> list[str]:
    pages: list[str] = []
    with pdfplumber.open(input_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text)
    if not pages:
        raise SkippedFile("该 PDF 没有可提取文字，可能是扫描版。请先转换为文字版 PDF、Word 或文本后再处理。")
    return pages


def _ensure_pdf_has_extractable_text(input_path: Path) -> None:
    _extract_pdf_text_chunks(input_path)


def _iter_docx_text_chunks(document: Document) -> list[str]:
    chunks: list[str] = []
    chunks.extend(paragraph.text for paragraph in document.paragraphs if paragraph.text)
    for table in document.tables:
        chunks.extend(_iter_docx_table_text(table))
    for section in document.sections:
        chunks.extend(paragraph.text for paragraph in section.header.paragraphs if paragraph.text)
        chunks.extend(paragraph.text for paragraph in section.footer.paragraphs if paragraph.text)
        for table in section.header.tables:
            chunks.extend(_iter_docx_table_text(table))
        for table in section.footer.tables:
            chunks.extend(_iter_docx_table_text(table))
    return chunks


def _iter_docx_table_text(table) -> list[str]:
    chunks: list[str] = []
    for row in table.rows:
        for cell in row.cells:
            chunks.extend(paragraph.text for paragraph in cell.paragraphs if paragraph.text)
            for nested_table in cell.tables:
                chunks.extend(_iter_docx_table_text(nested_table))
    return chunks


def _iter_pptx_text_chunks(presentation) -> list[str]:
    chunks: list[str] = []
    for slide in presentation.slides:
        chunks.extend(_iter_pptx_shape_text_chunks(slide.shapes))
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            text = slide.notes_slide.notes_text_frame.text
            if text:
                chunks.append(text)
    return chunks


def _iter_pptx_shape_text_chunks(shapes) -> list[str]:
    chunks: list[str] = []
    for shape in shapes:
        if getattr(shape, "has_text_frame", False) and shape.text_frame.text:
            chunks.append(shape.text_frame.text)
        if getattr(shape, "has_table", False):
            for row in shape.table.rows:
                for cell in row.cells:
                    if cell.text:
                        chunks.append(cell.text)
        if hasattr(shape, "shapes"):
            chunks.extend(_iter_pptx_shape_text_chunks(shape.shapes))
    return chunks


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
