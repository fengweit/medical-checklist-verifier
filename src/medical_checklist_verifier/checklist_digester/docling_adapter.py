from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from docling_core.types.doc import (
    DocItemLabel,
    DoclingDocument,
    TableCell,
    TableItem,
    TextItem,
)

_HEADER_ALIASES = {
    "item": {"item", "checklist item", "subject", "检查项目", "项目"},
    "requirements": {"requirement", "requirements", "要求", "审核要求"},
    "reference": {"reference", "references", "standard reference", "法规引用", "参考"},
}
_CONTENTS_TITLES = {
    "contents",
    "table of contents",
    "目录",
    "scope of document",
    "abbreviations",
}


def _stable_suffix(*parts: object) -> str:
    value = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _section_exclusion_reason(label: str) -> str:
    return (
        "front_matter_section"
        if _normalize(label) in {"scope of document", "abbreviations"}
        else "contents_or_index_section"
    )


def _column_roles(cells: List[str]) -> Dict[str, int]:
    roles: Dict[str, int] = {}
    for index, cell in enumerate(cells):
        normalized = _normalize(cell)
        if (
            normalized in _HEADER_ALIASES["item"]
            or normalized.startswith("subject ")
            or ("section title" in normalized and "item" in normalized)
        ):
            roles["item"] = index
        elif (
            normalized in _HEADER_ALIASES["requirements"]
            or "requirement 要求" in normalized
            or normalized.startswith("requirement ")
        ):
            roles["requirements"] = index
        elif "additional guidance" in normalized or normalized.startswith(
            "referenced evidence"
        ):
            roles["guidance"] = index
        elif normalized in {"section", "section title"}:
            roles["section"] = index
        elif (
            normalized == "location"
            or "location of the requested information" in normalized
            or normalized.startswith("reference to td document")
            or normalized.startswith("page / section")
        ):
            roles["location"] = index
        elif (
            "completeness check" in normalized
            or normalized.startswith("submission check")
            or normalized.startswith("reviewer outcome")
            or normalized.startswith("check off")
        ):
            roles["outcome"] = index
        elif (
            normalized in _HEADER_ALIASES["reference"]
            or normalized.startswith("ref to mdr")
            or normalized.startswith("reference to mdr")
        ):
            roles["reference"] = index
    return roles


def _column_stats(text_rows: List[List[str]], column_index: int) -> Dict[str, float]:
    values = [
        row[column_index].strip()
        for row in text_rows[1:]
        if column_index < len(row) and row[column_index].strip()
    ]
    if not values:
        return {"average_length": 0.0, "unique_ratio": 0.0, "outcome_ratio": 0.0}
    outcome_pattern = re.compile(
        r"\b(?:yes|no|n/?a|pass|fail|compliant|noncompliant)\b|[☐☑✓✔]",
        re.IGNORECASE,
    )
    return {
        "average_length": sum(len(value) for value in values) / len(values),
        "unique_ratio": len(set(values)) / len(values),
        "outcome_ratio": sum(bool(outcome_pattern.search(value)) for value in values)
        / len(values),
    }


def _infer_table_roles(
    text_rows: List[List[str]],
) -> Tuple[Dict[str, int], str, float, Dict[str, Any]] | None:
    if not text_rows:
        return None
    headers = [_normalize(value) for value in text_rows[0]]
    header_signals = {
        "category",
        "chapter",
        "criterion",
        "decision",
        "deliverable",
        "document",
        "evidence",
        "item",
        "location",
        "outcome",
        "reference",
        "requirement",
        "result",
        "section",
        "status",
        "subject",
        "check",
        "项目",
        "要求",
        "位置",
        "结果",
        "引用",
    }
    header_signal_count = sum(
        any(signal in header for signal in header_signals) for header in headers
    )
    if header_signal_count < 2 and "item" not in _column_roles(text_rows[0]):
        return None

    roles = _column_roles(text_rows[0])
    if "item" not in roles and "requirements" in roles:
        roles["item"] = roles["requirements"]
    method = "header_semantic" if "item" in roles else "content_aware"
    scores: Dict[str, float] = {role: 1.0 for role in roles}
    available = set(range(len(headers))) - set(roles.values())
    stats = {index: _column_stats(text_rows, index) for index in range(len(headers))}

    if "outcome" not in roles and available:
        candidates = []
        for index in available:
            header = headers[index]
            header_score = (
                0.8
                if any(
                    token in header
                    for token in (
                        "decision",
                        "outcome",
                        "result",
                        "status",
                        "review",
                        "check",
                    )
                )
                else 0.0
            )
            score = max(header_score, stats[index]["outcome_ratio"])
            candidates.append((score, index))
        score, index = max(candidates)
        if score >= 0.75:
            roles["outcome"] = index
            scores["outcome"] = score
            available.remove(index)

    if "section" not in roles and available:
        candidates = []
        for index in available:
            header = headers[index]
            header_score = (
                0.9
                if any(
                    token in header
                    for token in ("category", "chapter", "group", "section", "area")
                )
                else 0.0
            )
            data_score = (
                0.75
                if stats[index]["unique_ratio"] <= 0.5
                and stats[index]["average_length"] <= 50
                else 0.0
            )
            candidates.append((max(header_score, data_score), index))
        score, index = max(candidates)
        if score >= 0.75:
            roles["section"] = index
            scores["section"] = score
            available.remove(index)

    if "location" not in roles and available:
        candidates = []
        for index in available:
            header = headers[index]
            header_score = (
                0.85
                if any(
                    token in header
                    for token in (
                        "evidence",
                        "location",
                        "document",
                        "response",
                        "source",
                        "where",
                    )
                )
                else 0.0
            )
            candidates.append((header_score, index))
        score, index = max(candidates)
        if score >= 0.8:
            roles["location"] = index
            scores["location"] = score
            available.remove(index)

    if "item" not in roles and available:
        candidates = []
        for index in available:
            header = headers[index]
            header_score = (
                0.9
                if any(
                    token in header
                    for token in (
                        "criterion",
                        "deliverable",
                        "expectation",
                        "item",
                        "question",
                        "requested",
                        "requirement",
                        "subject",
                    )
                )
                else 0.0
            )
            length_score = min(stats[index]["average_length"] / 60, 0.8)
            candidates.append((max(header_score, length_score), index))
        score, index = max(candidates)
        if score >= 0.65:
            roles["item"] = index
            scores["item"] = score
            available.remove(index)

    if "item" not in roles:
        return None
    if method == "content_aware" and ("outcome" not in roles or len(headers) < 3):
        return None
    confidence = min(scores.values()) if scores else 0.0
    return roles, method, confidence, {"headers": text_rows[0], "role_scores": scores}


def _row_matches_inherited_roles(row: List[str], roles: Dict[str, int]) -> bool:
    item_index = roles.get("item")
    if item_index is None or item_index >= len(row):
        return False
    item_text = row[item_index].strip()
    if not item_text or _is_administrative(item_text):
        return False
    outcome_index = roles.get("outcome")
    if outcome_index is None:
        return "guidance" in roles and bool(re.match(r"^\d+(?:\.\d+){2,}\b", item_text))
    location_index = roles.get("location")
    if (
        outcome_index >= len(row)
        or location_index is None
        or location_index >= len(row)
    ):
        return False
    location = _normalize(row[location_index])
    has_document_locator = bool(
        re.search(
            r"\b(?:document|doc|page|section|chapter|annex|url|n/?a)\b",
            location,
        )
    )
    has_item_evidence = (
        bool(re.match(r"^\d+(?:\.\d+)*(?:\s*\([a-z0-9]+\))?\b", item_text, re.I))
        or _is_normative_prose(item_text)
        or "if n/a" in location
    )
    return (
        has_document_locator
        and has_item_evidence
        and bool(
            re.search(
                r"\b(?:yes|no|n/?a|pass|fail|compliant|noncompliant)\b|[☐☑✓✔]",
                row[outcome_index],
                re.IGNORECASE,
            )
        )
    )


def _split_requirements(text: str) -> List[str]:
    parts = re.split(r"(?:\r?\n|;|；)+\s*", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _is_conclusion_row(cells: List[str]) -> bool:
    normalized = " | ".join(_normalize(cell) for cell in cells)
    return (
        "continue to formal technical documentation review" in normalized
        and "do not continue to formal technical documentation review" in normalized
    )


def _is_administrative(label: str) -> bool:
    normalized = _normalize(label).rstrip(":")
    return (
        normalized in {"date"}
        or normalized.endswith("comments")
        or bool(re.match(r"^name of (?:the )?.*reviewer\b", normalized))
        or normalized.startswith("rationale (required")
    )


def _is_corporate_heading(heading: str) -> bool:
    return bool(
        re.search(r"\b(?:inc\.?|ltd\.?|llc|gmbh|limited)$", _normalize(heading))
    )


def _is_contact_text(text: str) -> bool:
    return bool(
        re.match(r"^(?:t|f|e|tel|phone|fax|email)\s*:", text.strip(), re.I)
    ) or ("@" in text)


def _is_contact_footer(heading: str, requirements: List[Tuple[str, TextItem]]) -> bool:
    return _is_corporate_heading(heading) and any(
        _is_contact_text(text) for text, _ in requirements
    )


def _page_and_bbox(element: TextItem | TableItem) -> Tuple[Optional[int], Any]:
    provenance = element.prov
    if not provenance:
        return None, None
    pages = {entry.page_no for entry in provenance}
    page_number = next(iter(pages)) if len(pages) == 1 else None
    bbox = provenance[0].bbox.model_dump(mode="json") if len(provenance) == 1 else None
    return page_number, bbox


def _table_item_reference(table: TableItem, table_index: int) -> Dict[str, Any]:
    page_number, bbox = _page_and_bbox(table)
    reference: Dict[str, Any] = {
        "kind": "docling_table",
        "docling_ref": str(table.self_ref),
        "table_index": table_index,
    }
    if page_number is not None:
        reference["page_number"] = page_number
    if bbox is not None:
        reference["bbox"] = bbox
    return reference


def _table_reference(
    table: TableItem,
    table_index: int,
    row_index: int,
    cell_index: int,
    cell: TableCell,
) -> Dict[str, Any]:
    provenance_pages = {entry.page_no for entry in table.prov}
    page_number = next(iter(provenance_pages)) if len(provenance_pages) == 1 else None
    reference: Dict[str, Any] = {
        "kind": "docling_table_cell",
        "docling_ref": str(table.self_ref),
        "table_index": table_index,
        "row_index": row_index,
        "cell_index": cell_index,
    }
    if page_number is not None:
        reference["page_number"] = page_number
    if cell.bbox is not None:
        reference["bbox"] = cell.bbox.model_dump(mode="json")
    return reference


def _text_reference(element: TextItem) -> Dict[str, Any]:
    page_number, bbox = _page_and_bbox(element)
    reference: Dict[str, Any] = {
        "kind": "docling_text",
        "docling_ref": str(element.self_ref),
    }
    if page_number is not None:
        reference["page_number"] = page_number
    if bbox is not None:
        reference["bbox"] = bbox
    if len(element.prov) == 1:
        reference["charspan"] = list(element.prov[0].charspan)
    return reference


def _record_exclusion(
    diagnostics: Dict[str, Any],
    reason: str,
    text: str,
    source_reference: Dict[str, Any],
) -> None:
    reference_key = json.dumps(source_reference, sort_keys=True, separators=(",", ":"))
    key = (reason, reference_key, text)
    exclusion_keys = diagnostics.setdefault("_exclusion_keys", set())
    if key not in exclusion_keys:
        exclusion_keys.add(key)
        diagnostics["exclusions"].append(
            {
                "reason": reason,
                "text": text,
                "source_reference": source_reference,
            }
        )


def _digest_tables(
    document: DoclingDocument, source_hash: str, diagnostics: Dict[str, Any]
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    inherited_roles: Dict[int, Tuple[Dict[str, int], str, float, int]] = {}
    for table_index, table in enumerate(document.tables):
        rows = table.data.grid
        if not rows:
            inherited_roles.clear()
            _record_exclusion(
                diagnostics,
                "empty_table",
                "Empty table",
                _table_item_reference(table, table_index),
            )
            continue
        if table.label is DocItemLabel.DOCUMENT_INDEX:
            inherited_roles.clear()
            _record_exclusion(
                diagnostics,
                "document_index_table",
                "Document index / table of contents",
                _table_item_reference(table, table_index),
            )
            continue
        text_rows = [[cell.text.strip() for cell in row] for row in rows]
        width = len(text_rows[0])
        if _is_conclusion_row(text_rows[0]):
            _record_exclusion(
                diagnostics,
                "conclusion_or_signoff_table",
                " | ".join(text_rows[0]),
                _table_item_reference(table, table_index),
            )
            inherited_roles.clear()
            continue
        inferred = None
        header_row_index = 0
        for candidate_row_index in range(min(3, len(text_rows))):
            candidate = _infer_table_roles(text_rows[candidate_row_index:])
            if candidate is not None:
                inferred = candidate
                header_row_index = candidate_row_index
                break
        inherited = inherited_roles.get(width)
        if (
            inherited is not None
            and inferred is None
            and table_index - inherited[3] == 1
            and any(
                _row_matches_inherited_roles(row, inherited[0]) for row in text_rows[:3]
            )
        ):
            roles, inherited_method, confidence, _ = inherited
            role_origin = inherited_method
            roles = dict(roles)
            method = "inherited_schema"
            evidence = {"inherited_from": inherited_method, "headers": None}
            inherited_roles[width] = (
                dict(roles),
                inherited_method,
                confidence,
                table_index,
            )
            data_start = 0
        elif inferred is not None:
            roles, method, confidence, evidence = inferred
            role_origin = method
            inherited_roles[width] = (
                dict(roles),
                method,
                confidence,
                table_index,
            )
            data_start = header_row_index + 1
        else:
            inherited_roles.clear()
            continuation_attached = False
            if (
                items
                and items[-1]["source_reference"].get("table_index") == table_index - 1
            ):
                for candidate_row_index in range(min(3, len(text_rows))):
                    continuation_roles = _column_roles(text_rows[candidate_row_index])
                    if (
                        "guidance" in continuation_roles
                        and "item" not in continuation_roles
                        and "requirements" not in continuation_roles
                    ):
                        guidance_index = continuation_roles["guidance"]
                        for continuation_row_index in range(
                            candidate_row_index + 1, len(rows)
                        ):
                            guidance_text = text_rows[continuation_row_index][
                                guidance_index
                            ].strip()
                            if guidance_text:
                                items[-1]["guidance"].append(
                                    {
                                        "text": guidance_text,
                                        "source_reference": _table_reference(
                                            table,
                                            table_index,
                                            continuation_row_index,
                                            guidance_index,
                                            rows[continuation_row_index][
                                                guidance_index
                                            ],
                                        ),
                                    }
                                )
                                continuation_attached = True
                        break
            diagnostics["unknown_tables"].append(
                {
                    "docling_ref": str(table.self_ref),
                    "table_index": table_index,
                    "row_count": len(rows),
                    "column_count": width,
                    "first_row": text_rows[0],
                    "continuation_guidance_attached": continuation_attached,
                }
            )
            continue
        diagnostics["role_tables"].append(
            {
                "docling_ref": str(table.self_ref),
                "table_index": table_index,
                "roles": roles,
                "inference_method": method,
                "confidence": round(confidence, 3),
                "evidence": evidence,
            }
        )

        for row_index in range(data_start, len(rows)):
            cells = rows[row_index]
            values = text_rows[row_index]
            item_cell_index = roles["item"]
            label = values[item_cell_index]
            if not label:
                _record_exclusion(
                    diagnostics,
                    "blank_item_cell_row",
                    " | ".join(value for value in values if value) or "Blank table row",
                    _table_reference(
                        table,
                        table_index,
                        row_index,
                        item_cell_index,
                        cells[item_cell_index],
                    ),
                )
                continue
            if _is_administrative(label):
                _record_exclusion(
                    diagnostics,
                    "administrative_or_reviewer_row",
                    label,
                    _table_reference(
                        table,
                        table_index,
                        row_index,
                        item_cell_index,
                        cells[item_cell_index],
                    ),
                )
                continue
            if "section" in roles and values[roles["section"]] == label:
                _record_exclusion(
                    diagnostics,
                    "section_divider_row",
                    label,
                    _table_reference(
                        table,
                        table_index,
                        row_index,
                        item_cell_index,
                        cells[item_cell_index],
                    ),
                )
                continue

            is_guidance_table = "guidance" in roles
            is_numbered_guidance_table = (
                is_guidance_table
                and width == 2
                and "requirements" not in roles
                and "outcome" not in roles
            )
            if is_numbered_guidance_table and not re.match(
                r"^\d+(?:\.\d+){2,}\b", label
            ):
                _record_exclusion(
                    diagnostics,
                    "section_or_category_row",
                    label,
                    _table_reference(
                        table,
                        table_index,
                        row_index,
                        item_cell_index,
                        cells[item_cell_index],
                    ),
                )
                continue

            requirement_cell_index = roles.get("requirements", item_cell_index)
            requirement_cell = cells[requirement_cell_index]
            requirement_text = values[requirement_cell_index] or label
            duplicate_cell_count = sum(value == requirement_text for value in values)
            if (
                is_guidance_table
                and "requirements" in roles
                and (
                    requirement_cell.column_header
                    or requirement_cell.row_section
                    or requirement_cell.col_span > 1
                    or duplicate_cell_count > 1
                )
            ):
                _record_exclusion(
                    diagnostics,
                    "section_or_merged_context_cell",
                    requirement_text,
                    _table_reference(
                        table,
                        table_index,
                        row_index,
                        requirement_cell_index,
                        requirement_cell,
                    ),
                )
                continue

            if not is_guidance_table and "outcome" in roles and "location" in roles:
                location_value = values[roles["location"]].strip()
                outcome_value = values[roles["outcome"]].strip()
                if not location_value and not outcome_value:
                    _record_exclusion(
                        diagnostics,
                        "unfilled_template_context_row",
                        label,
                        _table_reference(
                            table,
                            table_index,
                            row_index,
                            item_cell_index,
                            cells[item_cell_index],
                        ),
                    )
                    continue

            requirement_values = (
                [requirement_text]
                if is_guidance_table
                else _split_requirements(requirement_text)
            )
            if not requirement_values:
                continue

            item_number = len(items) + 1
            item_id = (
                f"item-{item_number:04d}-"
                f"{_stable_suffix(source_hash, str(table.self_ref), row_index, label)}"
            )
            requirements = []
            for segment_index, value in enumerate(requirement_values):
                requirement_suffix = _stable_suffix(
                    source_hash,
                    str(table.self_ref),
                    row_index,
                    requirement_cell_index,
                    segment_index,
                    value,
                )
                requirement_reference = _table_reference(
                    table,
                    table_index,
                    row_index,
                    requirement_cell_index,
                    cells[requirement_cell_index],
                )
                requirement_reference["segment_index"] = segment_index
                requirements.append(
                    {
                        "id": (
                            f"{item_id}-requirement-{segment_index + 1:03d}-"
                            f"{requirement_suffix}"
                        ),
                        "text": value,
                        "classification": "explicit_requirement",
                        "derivation": (
                            "guidance_requirement_cell"
                            if is_guidance_table
                            else (
                                "explicit_requirement_cell_segment"
                                if "requirements" in roles
                                else "item_cell_segment"
                            )
                        ),
                        "source_reference": requirement_reference,
                    }
                )
            guidance = []
            if "guidance" in roles:
                guidance_index = roles["guidance"]
                guidance_text = values[guidance_index].strip()
                if guidance_text and guidance_text != requirement_text:
                    guidance.append(
                        {
                            "text": guidance_text,
                            "source_reference": _table_reference(
                                table,
                                table_index,
                                row_index,
                                guidance_index,
                                cells[guidance_index],
                            ),
                        }
                    )
            items.append(
                {
                    "id": item_id,
                    "_role_origin": role_origin,
                    "_semantic_roles": sorted(roles),
                    "_normative_item_evidence": (
                        _is_normative_prose(label)
                        or bool(re.match(r"^\d+(?:\.\d+)*\b", label))
                    ),
                    "label": label,
                    "section_title": values[roles["section"]]
                    if "section" in roles
                    else None,
                    "declared_reference": values[roles["reference"]]
                    if "reference" in roles
                    else None,
                    "declared_location": values[roles["location"]]
                    if "location" in roles
                    else None,
                    "source_reference": _table_reference(
                        table,
                        table_index,
                        row_index,
                        item_cell_index,
                        cells[item_cell_index],
                    ),
                    "guidance": guidance,
                    "requirements": requirements,
                }
            )
    return items


def _is_normative_prose(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:shall|must|should|required|"
            r"please\s+(?:provide|include|ensure|identify|submit|describe|document|justify)|"
            r"(?:recommended|beneficial)\s+to\s+(?:provide|include|ensure|identify|submit|describe|document|justify)|"
            r"needs?\s+to\s+be|expected\s+to|(?:is|are)\s+to\s+be\s+provided)\b",
            text,
            re.IGNORECASE,
        )
        or bool(
            re.match(
                r"^\s*(?:provide|include|ensure|identify|submit|describe|document|justify|clearly\s+identify)\b",
                text,
                re.IGNORECASE,
            )
        )
    )


def _digest_document_candidates(
    document: DoclingDocument, source_hash: str, diagnostics: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Use Docling's ordered traversal; only classify domain-level candidates."""
    sections: List[Tuple[TextItem, List[Tuple[str, TextItem]]]] = []
    current: Optional[Tuple[TextItem, List[Tuple[str, TextItem]]]] = None
    excluded_level: Optional[int] = None

    def finish_current() -> None:
        nonlocal current
        if current is None or not current[1]:
            return
        heading = current[0].text
        if _is_contact_footer(heading, current[1]):
            _record_exclusion(
                diagnostics,
                "corporate_contact_footer",
                heading,
                _text_reference(current[0]),
            )
        else:
            sections.append(current)

    for element, level in document.iterate_items(with_groups=False):
        if not isinstance(element, TextItem):
            continue
        label = element.label
        if label is DocItemLabel.SECTION_HEADER:
            if excluded_level is not None:
                if level > excluded_level:
                    continue
                excluded_level = None
            finish_current()
            heading = element.text.strip()
            if _normalize(heading) in _CONTENTS_TITLES:
                _record_exclusion(
                    diagnostics,
                    _section_exclusion_reason(heading),
                    heading,
                    _text_reference(element),
                )
                current = None
                excluded_level = level
            else:
                current = (element, [])
            continue
        if excluded_level is not None:
            continue
        if label in {
            DocItemLabel.PAGE_HEADER,
            DocItemLabel.PAGE_FOOTER,
            DocItemLabel.CAPTION,
        }:
            continue
        text = element.text.strip()
        if current is None:
            if text and (label is DocItemLabel.LIST_ITEM or _is_normative_prose(text)):
                _record_exclusion(
                    diagnostics,
                    "unowned_normative_candidate",
                    text,
                    _text_reference(element),
                )
            continue
        if text and (
            label is DocItemLabel.LIST_ITEM
            or _is_normative_prose(text)
            or (_is_corporate_heading(current[0].text) and _is_contact_text(text))
        ):
            current[1].append((text, element))
    finish_current()

    items: List[Dict[str, Any]] = []
    for item_number, (section, extracted) in enumerate(sections, start=1):
        heading = section.text.strip()
        item_id = (
            f"item-{item_number:04d}-"
            f"{_stable_suffix(source_hash, str(section.self_ref), heading)}"
        )
        requirements = []
        for requirement_index, (text, element) in enumerate(extracted, start=1):
            requirements.append(
                {
                    "id": (
                        f"{item_id}-requirement-{requirement_index:03d}-"
                        f"{_stable_suffix(source_hash, str(element.self_ref), text)}"
                    ),
                    "text": text,
                    "classification": "normative_candidate",
                    "derivation": (
                        "section_list_candidate"
                        if element.label is DocItemLabel.LIST_ITEM
                        else "section_modal_candidate"
                    ),
                    "source_reference": _text_reference(element),
                }
            )
        items.append(
            {
                "id": item_id,
                "label": heading,
                "section_title": None,
                "declared_reference": None,
                "declared_location": None,
                "source_reference": _text_reference(section),
                "guidance": [],
                "requirements": requirements,
            }
        )
    return items


def digest_docling_document(doc: DoclingDocument, source_hash: str) -> Dict[str, Any]:
    """Interpret Docling's native document model into checklist semantics."""
    title = next(
        (
            text.text.strip()
            for text in doc.texts
            if text.label in {DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER}
            and text.text.strip()
        ),
        doc.name or "Untitled checklist",
    )
    normalized_identity = _normalize(f"{title} {doc.name or ''}")
    likely_checklist = any(
        marker in normalized_identity
        for marker in ("checklist", "completeness check", "检查表", "清单")
    )
    diagnostics: Dict[str, Any] = {
        "tables_total": len(doc.tables),
        "section_headers_total": sum(
            text.label is DocItemLabel.SECTION_HEADER for text in doc.texts
        ),
        "role_tables": [],
        "unknown_tables": [],
        "exclusions": [],
    }
    all_table_items = _digest_tables(doc, source_hash, diagnostics)

    def has_authoritative_roles(item: Dict[str, Any]) -> bool:
        roles = set(item["_semantic_roles"])
        return (
            bool({"requirements", "guidance"} & roles)
            or {
                "item",
                "outcome",
                "location",
            }
            <= roles
        )

    def is_authoritative_item(item: Dict[str, Any]) -> bool:
        roles = set(item["_semantic_roles"])
        if item["_role_origin"] == "header_semantic":
            return has_authoritative_roles(item)
        return (
            likely_checklist
            and item["_role_origin"] == "content_aware"
            and {"item", "outcome", "location"} <= roles
            and "guidance" not in roles
            and item["_normative_item_evidence"]
        )

    table_items = [item for item in all_table_items if is_authoritative_item(item)]
    diagnostics["table_items_discarded"] = len(all_table_items) - len(table_items)
    selected_ids = {item["id"] for item in table_items}
    for discarded in all_table_items:
        if discarded["id"] not in selected_ids:
            _record_exclusion(
                diagnostics,
                "nonauthoritative_inferred_item",
                discarded["label"],
                discarded["source_reference"],
            )
    for item in table_items:
        item.pop("_role_origin", None)
        item.pop("_semantic_roles", None)
        item.pop("_normative_item_evidence", None)
    use_table_items = bool(table_items)
    items = table_items
    mode = "semantic_tables"
    if not items:
        items = _digest_document_candidates(doc, source_hash, diagnostics)
        mode = "document_sections"
    warnings = []
    if diagnostics["unknown_tables"]:
        warnings.append("UNRECOGNIZED_TABLES_RETAINED_IN_DIAGNOSTICS")
    if diagnostics["table_items_discarded"]:
        warnings.append("NONAUTHORITATIVE_TABLE_ITEMS_DISCARDED")
    if mode == "document_sections" and items:
        warnings.append("NORMATIVE_CANDIDATES_REQUIRE_SEMANTIC_REVIEW")
    elif any(
        requirement.get("derivation", "").endswith("_segment")
        for item in items
        for requirement in item["requirements"]
    ):
        warnings.append("SEGMENTED_REQUIREMENTS_REQUIRE_SEMANTIC_REVIEW")
    exclusions = diagnostics.pop("exclusions")
    diagnostics.pop("_exclusion_keys", None)
    diagnostics["items_emitted"] = len(items)
    diagnostics["requirements_emitted"] = sum(
        len(item["requirements"]) for item in items
    )
    compatible = not (
        likely_checklist and not use_table_items and bool(diagnostics["unknown_tables"])
    )
    if not compatible:
        warnings.append("UNKNOWN_CHECKLIST_TABLE_LAYOUT")
    return {
        "title": title,
        "items": items,
        "adapter_mode": mode,
        "compatible": compatible,
        "docling_schema_name": doc.schema_name,
        "docling_schema_version": doc.version,
        "diagnostics": diagnostics,
        "exclusions": exclusions,
        "warnings": warnings,
    }
