"""PDF classification, table formatting, and hybrid (RRF) retrieval helpers."""

from types import SimpleNamespace

import pymupdf

from app.services import pdf_extract
from app.services.pdf_extract import _chunk_plain, _split_ocr_structured, _table_to_markdown
from app.services.rag import KnowledgeBase


def _text_pdf(path, pages: list[str]):
    doc = pymupdf.open()
    for body in pages:
        page = doc.new_page()
        page.insert_text((72, 72), body)
    doc.save(path)
    doc.close()


def test_selectable_text_pdf_is_not_scanned(tmp_path):
    path = tmp_path / "form.pdf"
    _text_pdf(
        path,
        [
            "Squat depth cues: sit between the hips until the thighs are parallel to the floor. "
            "Keep the chest up and the bar over mid-foot throughout the lift."
        ],
    )
    document = pymupdf.open(path)
    try:
        assert pdf_extract.is_scanned_pdf(document) is False
    finally:
        document.close()


def test_image_only_pdf_is_scanned(tmp_path):
    path = tmp_path / "scan.pdf"
    doc = pymupdf.open()
    doc.new_page()  # blank page → no selectable text
    doc.save(path)
    doc.close()
    document = pymupdf.open(path)
    try:
        assert pdf_extract.is_scanned_pdf(document) is True
    finally:
        document.close()


def test_table_markdown_keeps_row_order():
    table = SimpleNamespace(
        extract=lambda: [
            ["Exercise", "Sets", "Reps"],
            ["Squat", "3", "5"],
            ["Bench", "3", "8"],
        ]
    )
    markdown = _table_to_markdown(table)
    assert markdown.splitlines()[0].startswith("| Exercise")
    assert "Squat" in markdown
    assert markdown.index("Squat") < markdown.index("Bench")


def test_ocr_structured_split_emits_table_and_image_kinds():
    raw = """
Warm-up notes for members.

| Move | Seconds |
| --- | --- |
| Jump rope | 60 |
| Hip openers | 45 |

[IMAGE] Athlete in the bottom of a goblet squat with elbows inside the knees.
"""
    passages = _split_ocr_structured(raw, page_number=2)
    kinds = {passage.kind for passage in passages}
    assert "table" in kinds
    assert "image_summary" in kinds
    assert "image_detail" in kinds
    assert any(passage.kind == "text" for passage in passages)


def test_chunk_plain_respects_minimum_length():
    assert _chunk_plain("too short") == []
    long = "word " * 40
    assert len(_chunk_plain(long)[0]) >= 100


def test_rrf_fuse_prefers_items_high_in_both_lists():
    a = SimpleNamespace(id="a", content="a")
    b = SimpleNamespace(id="b", content="b")
    c = SimpleNamespace(id="c", content="c")
    fused = KnowledgeBase._rrf_fuse([[b, a, c], [b, c, a]], limit=2)
    assert [row.id for row in fused][0] == "b"


def test_query_tokens_drop_short_noise():
    assert KnowledgeBase._query_tokens("Improve squat depth at the gym") == [
        "improve",
        "squat",
        "depth",
        "the",
        "gym",
    ]
