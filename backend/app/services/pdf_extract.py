"""PDF page classification and multi-modal extraction for the knowledge base.

Text PDFs take the fast path (PyMuPDF text + tables + embedded images). Scanned PDFs
are rendered and OCR'd via Gemini vision so FitBot still gets searchable passages.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Below this average of extractable characters per page, treat the file as a scan.
SCAN_CHARS_PER_PAGE = 40
MIN_IMAGE_SIDE_PX = 64
MAX_OCR_PAGES = 40
TABLE_KIND = "table"
TEXT_KIND = "text"
IMAGE_SUMMARY_KIND = "image_summary"
IMAGE_DETAIL_KIND = "image_detail"


@dataclass(frozen=True)
class ExtractedPassage:
    text: str
    page: int
    kind: str


@dataclass(frozen=True)
class ExtractResult:
    passages: list[ExtractedPassage]
    ingest_mode: str  # "direct" | "ocr"


def is_scanned_pdf(document: pymupdf.Document) -> bool:
    """Heuristic: almost no selectable text across pages → scan / image-only PDF."""
    if document.page_count == 0:
        return True
    total = sum(len(page.get_text().strip()) for page in document)
    return (total / document.page_count) < SCAN_CHARS_PER_PAGE


def _table_to_markdown(table) -> str:
    """Keep row/column order; prefer PyMuPDF's markdown when available."""
    to_md = getattr(table, "to_markdown", None)
    if callable(to_md):
        try:
            rendered = to_md()
            if rendered and rendered.strip():
                return rendered.strip()
        except Exception:
            logger.debug("table.to_markdown failed; falling back to cells", exc_info=True)
    rows = table.extract()
    if not rows:
        return ""
    lines: list[str] = []
    for index, row in enumerate(rows):
        cells = [("" if cell is None else str(cell).strip().replace("\n", " ")) for cell in row]
        lines.append("| " + " | ".join(cells) + " |")
        if index == 0:
            lines.append("| " + " | ".join("---" for _ in cells) + " |")
    return "\n".join(lines)


def _chunk_plain(text: str, chunk_size: int = 1200, overlap: int = 180) -> list[str]:
    clean = " ".join(text.split())
    if not clean:
        return []
    step = max(chunk_size - overlap, 1)
    return [
        clean[i : i + chunk_size]
        for i in range(0, len(clean), step)
        if len(clean[i : i + chunk_size].strip()) >= 100
    ]


def _extract_tables(page: pymupdf.Page, page_number: int) -> list[ExtractedPassage]:
    passages: list[ExtractedPassage] = []
    finder = getattr(page, "find_tables", None)
    if not callable(finder):
        return passages
    try:
        found = finder()
    except Exception:
        logger.debug("find_tables failed on page %s", page_number, exc_info=True)
        return passages
    tables = getattr(found, "tables", found) or []
    for index, table in enumerate(tables, start=1):
        markdown = _table_to_markdown(table)
        if len(markdown.strip()) < 20:
            continue
        passages.append(
            ExtractedPassage(
                text=f"[TABLE {index}]\n{markdown}",
                page=page_number,
                kind=TABLE_KIND,
            )
        )
    return passages


def _page_pixmap_png(page: pymupdf.Page, zoom: float = 2.0) -> bytes:
    matrix = pymupdf.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    return pix.tobytes("png")


def _vision_generate(prompt: str, png_bytes: bytes) -> str:
    """Gemini multimodal call. Empty string when the key is missing or the call fails."""
    settings = get_settings()
    if not settings.gemini_api_key:
        return ""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Part.from_bytes(data=png_bytes, mime_type="image/png"),
                prompt,
            ],
            config={"temperature": 0.2, "max_output_tokens": 2048},
        )
        return (response.text or "").strip()
    except Exception:
        logger.exception("Gemini vision call failed")
        return ""


def _describe_image(png_bytes: bytes, page_number: int, index: int) -> list[ExtractedPassage]:
    """Two passages per figure: short summary (for ranking) + detailed description."""
    raw = _vision_generate(
        (
            "You are indexing a gym coaching PDF figure. Reply with exactly two sections:\n"
            "SUMMARY: one sentence describing what the image shows.\n"
            "DETAIL: form cues, equipment, labels, and any readable text in the image. "
            "Be concrete; do not invent content that is not visible."
        ),
        png_bytes,
    )
    if not raw:
        return []
    summary = ""
    detail = ""
    summary_match = re.search(
        r"SUMMARY:\s*(.+?)(?=\n\s*DETAIL:|\Z)", raw, re.IGNORECASE | re.DOTALL
    )
    detail_match = re.search(r"DETAIL:\s*(.+)\Z", raw, re.IGNORECASE | re.DOTALL)
    if summary_match:
        summary = " ".join(summary_match.group(1).split())
    if detail_match:
        detail = " ".join(detail_match.group(1).split())
    if not summary and not detail:
        summary = " ".join(raw.split())[:400]
        detail = " ".join(raw.split())
    passages: list[ExtractedPassage] = []
    label = f"Image {index} on page {page_number}"
    if summary:
        passages.append(
            ExtractedPassage(
                text=f"[IMAGE SUMMARY — {label}] {summary}",
                page=page_number,
                kind=IMAGE_SUMMARY_KIND,
            )
        )
    if detail:
        passages.append(
            ExtractedPassage(
                text=f"[IMAGE DETAIL — {label}] {detail}",
                page=page_number,
                kind=IMAGE_DETAIL_KIND,
            )
        )
    return passages


def _extract_embedded_images(
    document: pymupdf.Document, page: pymupdf.Page, page_number: int
) -> list[ExtractedPassage]:
    passages: list[ExtractedPassage] = []
    for index, info in enumerate(page.get_images(full=True), start=1):
        xref = info[0]
        try:
            pix = pymupdf.Pixmap(document, xref)
            if pix.n >= 5:  # CMYK etc.
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            if pix.width < MIN_IMAGE_SIDE_PX or pix.height < MIN_IMAGE_SIDE_PX:
                continue
            png = pix.tobytes("png")
        except Exception:
            logger.debug("skipping image xref=%s page=%s", xref, page_number, exc_info=True)
            continue
        passages.extend(_describe_image(png, page_number, index))
    return passages


def _split_ocr_structured(ocr_text: str, page_number: int) -> list[ExtractedPassage]:
    """Turn a structured OCR reply into text / table / image passages."""
    passages: list[ExtractedPassage] = []
    remaining = ocr_text

    # Markdown tables
    table_pattern = re.compile(
        r"((?:^\|.+\|\s*\n)+^\|\s*[-:| ]+\|\s*\n(?:^\|.+\|\s*\n?)*)",
        re.MULTILINE,
    )
    for index, match in enumerate(table_pattern.finditer(ocr_text), start=1):
        table = match.group(1).strip()
        if len(table) >= 20:
            passages.append(
                ExtractedPassage(
                    text=f"[TABLE {index}]\n{table}",
                    page=page_number,
                    kind=TABLE_KIND,
                )
            )
        remaining = remaining.replace(match.group(1), "\n")

    # Explicit [IMAGE] … blocks from the OCR prompt
    image_pattern = re.compile(
        r"\[IMAGE\]\s*(.+?)(?=\n\[IMAGE\]|\n\[TABLE\]|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    for index, match in enumerate(image_pattern.finditer(ocr_text), start=1):
        body = " ".join(match.group(1).split())
        if len(body) < 20:
            continue
        passages.append(
            ExtractedPassage(
                text=f"[IMAGE SUMMARY — OCR page {page_number} fig {index}] {body[:300]}",
                page=page_number,
                kind=IMAGE_SUMMARY_KIND,
            )
        )
        passages.append(
            ExtractedPassage(
                text=f"[IMAGE DETAIL — OCR page {page_number} fig {index}] {body}",
                page=page_number,
                kind=IMAGE_DETAIL_KIND,
            )
        )
        remaining = remaining.replace(match.group(0), "\n")

    leftover = " ".join(remaining.split())
    if len(leftover) >= 20:
        chunks = _chunk_plain(leftover) or ([leftover] if len(leftover) >= 20 else [])
        for chunk in chunks:
            if len(chunk.strip()) >= 20:
                passages.append(ExtractedPassage(text=chunk, page=page_number, kind=TEXT_KIND))
    return passages


def _ocr_page(page: pymupdf.Page, page_number: int) -> list[ExtractedPassage]:
    png = _page_pixmap_png(page)
    raw = _vision_generate(
        (
            "This page is from a scanned gym coaching PDF. Extract everything in reading order.\n"
            "1) Plain text as paragraphs.\n"
            "2) Tables as GitHub-flavored markdown tables (keep row and column order).\n"
            "3) For each significant figure/photo, a block starting with [IMAGE] then a "
            "short caption and a longer description of what it shows.\n"
            "Do not invent content. If a region is unreadable, skip it."
        ),
        png,
    )
    if not raw:
        return []
    return _split_ocr_structured(raw, page_number)


def extract_pdf(path: Path) -> ExtractResult:
    """Classify the PDF and return typed passages ready to embed."""
    document = pymupdf.open(path)
    try:
        scanned = is_scanned_pdf(document)
        passages: list[ExtractedPassage] = []

        if scanned:
            if not get_settings().gemini_api_key:
                raise RuntimeError(
                    "This PDF looks scanned (little selectable text). Set GEMINI_API_KEY "
                    "so pages can be OCR'd with vision."
                )
            page_count = min(document.page_count, MAX_OCR_PAGES)
            for page_number in range(1, page_count + 1):
                passages.extend(_ocr_page(document[page_number - 1], page_number))
            return ExtractResult(passages=passages, ingest_mode="ocr")

        for page_number, page in enumerate(document, start=1):
            for chunk in _chunk_plain(page.get_text()):
                passages.append(
                    ExtractedPassage(text=chunk, page=page_number, kind=TEXT_KIND)
                )
            passages.extend(_extract_tables(page, page_number))
            if get_settings().gemini_api_key:
                passages.extend(_extract_embedded_images(document, page, page_number))

        return ExtractResult(passages=passages, ingest_mode="direct")
    finally:
        document.close()
