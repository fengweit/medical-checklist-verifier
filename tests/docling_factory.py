from __future__ import annotations

from typing import Any

from docling_core.types.doc import (
    BoundingBox,
    CoordOrigin,
    DocItemLabel,
    DoclingDocument,
    ProvenanceItem,
    TableCell,
    TableData,
)


def _bbox(value: dict[str, Any] | None) -> BoundingBox:
    value = value or {"l": 0, "t": 0, "r": 0, "b": 0}
    return BoundingBox(
        l=value["l"],
        t=value["t"],
        r=value["r"],
        b=value["b"],
        coord_origin=CoordOrigin(value.get("coord_origin", "TOPLEFT")),
    )


def _provenance(values: list[dict[str, Any]]) -> list[ProvenanceItem]:
    return [
        ProvenanceItem(
            page_no=value["page_no"],
            bbox=_bbox(value.get("bbox")),
            charspan=tuple(value.get("charspan", (0, 0))),
        )
        for value in values
    ]


def from_synthetic_dict(value: dict[str, Any]) -> DoclingDocument:
    """Build valid Docling objects for unit fixtures through Docling's public API."""
    document = DoclingDocument(name=value.get("name") or "Synthetic document")
    for element in value.get("texts", []):
        label = DocItemLabel(element["label"])
        text = element.get("text") or ""
        provenance = _provenance(element.get("prov") or [])
        prov = provenance[0] if provenance else None
        if label is DocItemLabel.SECTION_HEADER:
            item = document.add_heading(
                text=text,
                orig=element.get("orig", text),
                level=element.get("level", 1),
                prov=prov,
            )
        elif label is DocItemLabel.LIST_ITEM:
            list_parent = document.add_list_group()
            item = document.add_list_item(
                text=text,
                orig=element.get("orig", text),
                prov=prov,
                parent=list_parent,
            )
        elif label is DocItemLabel.TITLE:
            item = document.add_title(
                text=text,
                orig=element.get("orig", text),
                prov=prov,
            )
        else:
            item = document.add_text(
                label=label,
                text=text,
                orig=element.get("orig", text),
                prov=prov,
            )
        if len(provenance) > 1:
            item.prov = provenance

    for table in value.get("tables", []):
        grid = table.get("data", {}).get("grid") or []
        table_cells = []
        for row_index, row in enumerate(grid):
            for column_index, cell in enumerate(row):
                table_cells.append(
                    TableCell(
                        bbox=_bbox(cell["bbox"]) if cell.get("bbox") else None,
                        row_span=cell.get("row_span", 1),
                        col_span=cell.get("col_span", 1),
                        start_row_offset_idx=cell.get(
                            "start_row_offset_idx", row_index
                        ),
                        end_row_offset_idx=cell.get(
                            "end_row_offset_idx", row_index + 1
                        ),
                        start_col_offset_idx=cell.get(
                            "start_col_offset_idx", column_index
                        ),
                        end_col_offset_idx=cell.get(
                            "end_col_offset_idx", column_index + 1
                        ),
                        text=cell.get("text") or "",
                        column_header=cell.get("column_header", False),
                        row_header=cell.get("row_header", False),
                        row_section=cell.get("row_section", False),
                        fillable=cell.get("fillable", False),
                    )
                )
        data = TableData(
            table_cells=table_cells,
            num_rows=len(grid),
            num_cols=len(grid[0]) if grid else 0,
        )
        provenance = _provenance(table.get("prov") or [])
        item = document.add_table(
            data=data,
            prov=provenance[0] if provenance else None,
            label=DocItemLabel(table.get("label", "table")),
        )
        if len(provenance) > 1:
            item.prov = provenance
    return document
