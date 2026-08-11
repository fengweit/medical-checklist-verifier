from pathlib import Path

import pymupdf

from medical_checklist_verifier.checklist_digester import digest_checklist


def test_pdf_table_uses_docling_semantics_and_cell_references(tmp_path: Path) -> None:
    source = tmp_path / "table-checklist.pdf"
    document = pymupdf.open()
    page = document.new_page(width=700, height=500)
    xs = [40, 180, 380, 520, 660]
    ys = [40, 80, 120]
    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]))
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y))
    rows = [
        ["Section Title", "Item", "Location", "Completeness Check"],
        ["Overview", "Cover letter", "Document 1", "YES NO"],
    ]
    for row_index, row in enumerate(rows):
        for cell_index, text in enumerate(row):
            page.insert_text((xs[cell_index] + 4, ys[row_index] + 24), text, fontsize=8)
    document.save(source)
    document.close()

    result = digest_checklist(source)

    assert result["extraction"]["library"] == "docling"
    assert result["extraction"]["adapter_mode"] == "semantic_tables"
    assert result["checklist"]["source"]["media_type"] == "application/pdf"
    assert result["statistics"] == {
        "item_count": 1,
        "requirement_count": 1,
        "explicit_requirement_count": 1,
        "normative_candidate_count": 0,
        "guidance_count": 0,
    }
    item = result["items"][0]
    assert item["label"] == "Cover letter"
    assert item["section_title"] == "Overview"
    assert item["declared_location"] == "Document 1"
    assert item["requirements"][0]["text"] == "Cover letter"
    reference = item["source_reference"]
    assert reference["kind"] == "docling_table_cell"
    assert reference["docling_ref"].startswith("#/tables/")
    assert reference["page_number"] == 1
    assert reference["row_index"] == 1
    assert reference["cell_index"] == 1
    assert set(reference["bbox"]) >= {"l", "t", "r", "b"}
