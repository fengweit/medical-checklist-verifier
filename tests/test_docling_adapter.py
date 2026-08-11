from docling_factory import from_synthetic_dict

from medical_checklist_verifier.checklist_digester.docling_adapter import (
    digest_docling_document as _digest_docling_document,
)


def digest_docling_document(document: dict, source_hash: str) -> dict:
    return _digest_docling_document(from_synthetic_dict(document), source_hash)


def test_docling_semantic_table_maps_rows_with_docling_references() -> None:
    document = {
        "schema_name": "DoclingDocument",
        "version": "1.10.0",
        "name": "BSI Checklist",
        "body": {"self_ref": "#/body", "children": [{"$ref": "#/tables/0"}]},
        "groups": [],
        "texts": [],
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [
                    {
                        "page_no": 4,
                        "bbox": {
                            "l": 10,
                            "t": 100,
                            "r": 500,
                            "b": 20,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
                "data": {
                    "num_rows": 2,
                    "num_cols": 4,
                    "grid": [
                        [
                            {"text": "Section Title"},
                            {"text": "Item"},
                            {"text": "Location"},
                            {"text": "Completeness Check"},
                        ],
                        [
                            {"text": "Overview"},
                            {"text": "Cover letter"},
                            {"text": "Document 1"},
                            {"text": "YES NO"},
                        ],
                    ],
                },
            }
        ],
    }

    parsed = digest_docling_document(document, "a" * 64)

    assert parsed["title"] == "BSI Checklist"
    assert len(parsed["items"]) == 1
    item = parsed["items"][0]
    assert item["label"] == "Cover letter"
    assert item["section_title"] == "Overview"
    assert item["declared_location"] == "Document 1"
    assert item["requirements"][0]["text"] == "Cover letter"
    assert item["requirements"][0]["derivation"] == "item_cell_segment"
    assert item["source_reference"] == {
        "kind": "docling_table_cell",
        "docling_ref": "#/tables/0",
        "page_number": 4,
        "table_index": 0,
        "row_index": 1,
        "cell_index": 1,
    }


def test_docling_sections_become_items_with_direct_requirements() -> None:
    document = {
        "schema_name": "DoclingDocument",
        "version": "1.10.0",
        "name": "Team NB Guidance",
        "body": {"self_ref": "#/body", "children": [{"$ref": "#/texts/0"}]},
        "groups": [
            {
                "self_ref": "#/groups/0",
                "label": "list",
                "children": [{"$ref": "#/texts/2"}],
            }
        ],
        "tables": [],
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "Technical documentation submission",
                "level": 1,
                "prov": [{"page_no": 3, "bbox": {"l": 1, "t": 2, "r": 3, "b": 4}}],
                "children": [
                    {"$ref": "#/texts/1"},
                    {"$ref": "#/groups/0"},
                ],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": "Submit one complete and searchable package.",
                "prov": [{"page_no": 3, "bbox": {"l": 5, "t": 6, "r": 7, "b": 8}}],
                "children": [],
            },
            {
                "self_ref": "#/texts/2",
                "label": "list_item",
                "text": "Include a document index.",
                "prov": [{"page_no": 3, "bbox": {"l": 9, "t": 10, "r": 11, "b": 12}}],
                "children": [],
            },
        ],
    }

    parsed = digest_docling_document(document, "b" * 64)

    assert [item["label"] for item in parsed["items"]] == [
        "Technical documentation submission"
    ]
    assert [r["text"] for r in parsed["items"][0]["requirements"]] == [
        "Submit one complete and searchable package.",
        "Include a document index.",
    ]
    assert parsed["items"][0]["requirements"][1]["derivation"] == (
        "section_list_candidate"
    )
    assert parsed["items"][0]["requirements"][1]["source_reference"] == {
        "kind": "docling_text",
        "docling_ref": "#/texts/2",
        "page_number": 3,
        "bbox": {
            "l": 9.0,
            "t": 10.0,
            "r": 11.0,
            "b": 12.0,
            "coord_origin": "TOPLEFT",
        },
        "charspan": [0, 0],
    }


def test_docling_contents_section_is_not_emitted() -> None:
    document = {
        "schema_name": "DoclingDocument",
        "version": "1.10.0",
        "name": "Guidance",
        "body": {"self_ref": "#/body", "children": [{"$ref": "#/texts/0"}]},
        "groups": [],
        "tables": [],
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "Table of Contents",
                "children": [{"$ref": "#/texts/1"}],
                "prov": [{"page_no": 2}],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": "1 Introduction ........ 3",
                "children": [],
                "prov": [{"page_no": 2}],
            },
        ],
    }

    parsed = digest_docling_document(document, "c" * 64)

    assert parsed["items"] == []


def test_docling_sequential_pdf_sections_collect_following_body_text() -> None:
    document = {
        "schema_name": "DoclingDocument",
        "version": "1.10.0",
        "name": "PDF Guidance",
        "groups": [],
        "tables": [],
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "Contents",
                "children": [],
                "prov": [{"page_no": 2}],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": "1 Introduction ........ 3",
                "children": [],
                "prov": [{"page_no": 2}],
            },
            {
                "self_ref": "#/texts/2",
                "label": "section_header",
                "text": "2 Submission requirements",
                "children": [],
                "prov": [{"page_no": 4}],
            },
            {
                "self_ref": "#/texts/3",
                "label": "text",
                "text": "Provide a complete document index.",
                "children": [],
                "prov": [{"page_no": 4}],
            },
        ],
        "body": {
            "self_ref": "#/body",
            "children": [
                {"$ref": "#/texts/0"},
                {"$ref": "#/texts/1"},
                {"$ref": "#/texts/2"},
                {"$ref": "#/texts/3"},
            ],
        },
    }

    parsed = digest_docling_document(document, "e" * 64)

    assert [item["label"] for item in parsed["items"]] == ["2 Submission requirements"]
    assert parsed["items"][0]["requirements"][0]["text"] == (
        "Provide a complete document index."
    )
    assert parsed["items"][0]["requirements"][0]["source_reference"]["page_number"] == 4


def test_docling_corporate_contact_footer_is_not_a_checklist_item() -> None:
    document = {
        "schema_name": "DoclingDocument",
        "version": "1.10.0",
        "name": "Guidance",
        "groups": [],
        "tables": [],
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "Example Group America Inc.",
                "children": [],
                "prov": [{"page_no": 10}],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": "T: +1 555 0100",
                "children": [],
                "prov": [{"page_no": 10}],
            },
            {
                "self_ref": "#/texts/2",
                "label": "text",
                "text": "E: contact@example.com",
                "children": [],
                "prov": [{"page_no": 10}],
            },
        ],
        "body": {
            "self_ref": "#/body",
            "children": [
                {"$ref": "#/texts/0"},
                {"$ref": "#/texts/1"},
                {"$ref": "#/texts/2"},
            ],
        },
    }

    parsed = digest_docling_document(document, "f" * 64)

    assert parsed["items"] == []
    assert parsed["exclusions"] == [
        {
            "reason": "corporate_contact_footer",
            "text": "Example Group America Inc.",
            "source_reference": {
                "kind": "docling_text",
                "docling_ref": "#/texts/0",
                "page_number": 10,
                "bbox": {
                    "l": 0.0,
                    "t": 0.0,
                    "r": 0.0,
                    "b": 0.0,
                    "coord_origin": "TOPLEFT",
                },
                "charspan": [0, 0],
            },
        }
    ]


def test_table_roles_are_inferred_from_headers_and_column_content() -> None:
    document = {
        "schema_name": "DoclingDocument",
        "version": "1.10.0",
        "name": "Adaptive checklist",
        "body": {"self_ref": "#/body", "children": [{"$ref": "#/tables/0"}]},
        "groups": [],
        "texts": [],
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [{"page_no": 1}],
                "data": {
                    "num_rows": 3,
                    "num_cols": 4,
                    "grid": [
                        [
                            {"text": "Category"},
                            {"text": "Requested deliverable"},
                            {"text": "Applicant evidence"},
                            {"text": "Decision"},
                        ],
                        [
                            {"text": "Overview"},
                            {"text": "Provide the complete device description"},
                            {"text": "Document TD-001 section 2"},
                            {"text": "YES NO N/A"},
                        ],
                        [
                            {"text": "Overview"},
                            {"text": "Provide intended purpose and intended users"},
                            {"text": "Document TD-001 section 3"},
                            {"text": "YES NO N/A"},
                        ],
                    ],
                },
            }
        ],
    }

    parsed = digest_docling_document(document, "1" * 64)

    assert [item["label"] for item in parsed["items"]] == [
        "Provide the complete device description",
        "Provide intended purpose and intended users",
    ]
    assert parsed["items"][0]["section_title"] == "Overview"
    assert parsed["items"][0]["declared_location"] == ("Document TD-001 section 2")
    assert parsed["diagnostics"]["role_tables"][0]["inference_method"] == (
        "content_aware"
    )


def test_unknown_checklist_table_layout_fails_compatibility_gate() -> None:
    document = {
        "schema_name": "DoclingDocument",
        "version": "1.10.0",
        "name": "Unknown Checklist",
        "body": {"self_ref": "#/body", "children": [{"$ref": "#/tables/0"}]},
        "groups": [],
        "texts": [],
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [{"page_no": 1}],
                "data": {
                    "num_rows": 2,
                    "num_cols": 2,
                    "grid": [
                        [{"text": "Alpha"}, {"text": "Beta"}],
                        [{"text": "One"}, {"text": "Two"}],
                    ],
                },
            }
        ],
    }

    parsed = digest_docling_document(document, "2" * 64)

    assert parsed["compatible"] is False
    assert parsed["items"] == []
    assert parsed["warnings"] == [
        "UNRECOGNIZED_TABLES_RETAINED_IN_DIAGNOSTICS",
        "UNKNOWN_CHECKLIST_TABLE_LAYOUT",
    ]
    assert parsed["diagnostics"]["unknown_tables"][0]["docling_ref"] == ("#/tables/0")


def test_inherited_schema_does_not_jump_across_unrelated_table() -> None:
    def table(ref: str, rows: list[list[str]]) -> dict:
        return {
            "self_ref": ref,
            "label": "table",
            "prov": [],
            "data": {
                "num_rows": len(rows),
                "num_cols": len(rows[0]),
                "grid": [[{"text": value} for value in row] for row in rows],
            },
        }

    document = {
        "schema_name": "DoclingDocument",
        "version": "1.10.0",
        "name": "Boundary Checklist",
        "body": {"self_ref": "#/body", "children": []},
        "groups": [],
        "texts": [],
        "tables": [
            table(
                "#/tables/0",
                [
                    ["Item", "Location", "Submission check"],
                    ["Provide device description", "TD-001", "YES NO"],
                ],
            ),
            table(
                "#/tables/1",
                [
                    [
                        "Privacy survey question unrelated to technical documentation",
                        "Document HR-1",
                        "YES",
                    ]
                ],
            ),
        ],
    }

    parsed = digest_docling_document(document, "3" * 64)

    assert [item["label"] for item in parsed["items"]] == ["Provide device description"]
    assert {
        table["docling_ref"] for table in parsed["diagnostics"]["unknown_tables"]
    } == {"#/tables/1"}


def test_bilingual_requirement_table_uses_leaf_cells_and_preserves_guidance() -> None:
    document = {
        "schema_name": "DoclingDocument",
        "version": "1.10.0",
        "name": "Bilingual guidance",
        "groups": [],
        "texts": [],
        "body": {"self_ref": "#/body", "children": [{"$ref": "#/tables/0"}]},
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [{"page_no": 14}],
                "data": {
                    "num_rows": 4,
                    "num_cols": 5,
                    "grid": [
                        [
                            {"text": ""},
                            {"text": ""},
                            {"text": "Customer"},
                            {"text": "Customer"},
                            {"text": "Customer"},
                        ],
                        [
                            {"text": "Ref to MDR"},
                            {"text": "Requirement 要求"},
                            {"text": "Page / section or N/A"},
                            {"text": "Referenced evidence (Document Title & No.)"},
                            {"text": "Check off 核对"},
                        ],
                        [
                            {"text": "Section"},
                            {"text": "Category", "col_span": 4, "row_section": True},
                            {"text": "Category"},
                            {"text": "Category"},
                            {"text": "Category"},
                        ],
                        [
                            {"text": "Annex II 1"},
                            {"text": "Provide the device description", "col_span": 1},
                            {"text": ""},
                            {"text": "Include drawings and specifications"},
                            {"text": ""},
                        ],
                    ],
                },
            }
        ],
    }

    parsed = digest_docling_document(document, "4" * 64)

    assert [item["label"] for item in parsed["items"]] == [
        "Provide the device description"
    ]
    requirement = parsed["items"][0]["requirements"][0]
    assert requirement["classification"] == "explicit_requirement"
    assert requirement["derivation"] == "guidance_requirement_cell"
    assert parsed["items"][0]["declared_reference"] == "Annex II 1"
    assert parsed["items"][0]["guidance"][0]["text"] == (
        "Include drawings and specifications"
    )


def test_numbered_guidance_table_emits_only_leaf_requirements() -> None:
    document = {
        "schema_name": "DoclingDocument",
        "version": "1.10.0",
        "name": "Best practice guidance",
        "groups": [],
        "texts": [],
        "body": {"self_ref": "#/body", "children": [{"$ref": "#/tables/0"}]},
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [{"page_no": 11}],
                "data": {
                    "num_rows": 3,
                    "num_cols": 2,
                    "grid": [
                        [
                            {"text": "Section Title / Item"},
                            {"text": "Additional Guidance"},
                        ],
                        [
                            {"text": "1.1 Device Description"},
                            {"text": "1.1 Device Description"},
                        ],
                        [
                            {"text": "1.1.1 Device overview"},
                            {"text": "Provide a concise overview"},
                        ],
                    ],
                },
            }
        ],
    }

    parsed = digest_docling_document(document, "5" * 64)

    assert [item["label"] for item in parsed["items"]] == ["1.1.1 Device overview"]
    assert parsed["items"][0]["guidance"][0]["source_reference"] == {
        "kind": "docling_table_cell",
        "docling_ref": "#/tables/0",
        "table_index": 0,
        "row_index": 2,
        "cell_index": 1,
        "page_number": 11,
    }


def test_continuation_guidance_does_not_cross_unknown_table() -> None:
    def table(ref: str, rows: list[list[str]]) -> dict:
        return {
            "self_ref": ref,
            "label": "table",
            "prov": [],
            "data": {
                "num_rows": len(rows),
                "num_cols": len(rows[0]),
                "grid": [[{"text": value} for value in row] for row in rows],
            },
        }

    document = {
        "schema_name": "DoclingDocument",
        "version": "1.10.0",
        "name": "Guidance",
        "body": {"self_ref": "#/body", "children": []},
        "groups": [],
        "texts": [],
        "tables": [
            table(
                "#/tables/0",
                [
                    ["Section Title / Item", "Additional Guidance"],
                    ["1.1.1 Device overview", "Provide a concise overview"],
                ],
            ),
            table("#/tables/1", [["Alpha", "Beta"], ["One", "Two"]]),
            table(
                "#/tables/2",
                [["", "Additional Guidance"], ["", "Late unrelated guidance"]],
            ),
        ],
    }

    parsed = digest_docling_document(document, "b" * 64)

    assert [entry["text"] for entry in parsed["items"][0]["guidance"]] == [
        "Provide a concise overview"
    ]
    unknown = {
        entry["table_index"]: entry for entry in parsed["diagnostics"]["unknown_tables"]
    }
    assert unknown[2]["continuation_guidance_attached"] is False


def test_multi_page_table_reference_omits_ambiguous_page_number() -> None:
    document = {
        "schema_name": "DoclingDocument",
        "version": "1.10.0",
        "name": "Checklist",
        "groups": [],
        "texts": [],
        "body": {"self_ref": "#/body", "children": [{"$ref": "#/tables/0"}]},
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [{"page_no": 1}, {"page_no": 2}],
                "data": {
                    "num_rows": 2,
                    "num_cols": 2,
                    "grid": [
                        [{"text": "Item"}, {"text": "Requirements"}],
                        [{"text": "Identity"}, {"text": "Provide manufacturer name"}],
                    ],
                },
            }
        ],
    }

    parsed = digest_docling_document(document, "6" * 64)

    reference = parsed["items"][0]["requirements"][0]["source_reference"]
    assert "page_number" not in reference


def test_generic_operational_table_is_not_a_checklist() -> None:
    document = {
        "schema_name": "DoclingDocument",
        "version": "1.10.0",
        "name": "Asset Checklist",
        "groups": [],
        "texts": [],
        "body": {"self_ref": "#/body", "children": [{"$ref": "#/tables/0"}]},
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [],
                "data": {
                    "num_rows": 3,
                    "num_cols": 4,
                    "grid": [
                        [
                            {"text": "Category"},
                            {"text": "Description"},
                            {"text": "Location"},
                            {"text": "Status"},
                        ],
                        [
                            {"text": "Brochure"},
                            {"text": "Historical material retained for reference"},
                            {"text": "Archive"},
                            {"text": "Inactive"},
                        ],
                        [
                            {"text": "Poster"},
                            {"text": "Marketing material retained for reference"},
                            {"text": "Lobby"},
                            {"text": "Active"},
                        ],
                    ],
                },
            }
        ],
    }

    parsed = digest_docling_document(document, "7" * 64)

    assert parsed["items"] == []
    assert parsed["diagnostics"]["table_items_discarded"] == 2
    assert {item["reason"] for item in parsed["exclusions"]} == {
        "nonauthoritative_inferred_item"
    }


def test_empty_table_is_retained_in_exclusion_ledger() -> None:
    document = {
        "schema_name": "DoclingDocument",
        "version": "1.10.0",
        "name": "Empty document",
        "groups": [],
        "texts": [],
        "body": {"self_ref": "#/body", "children": [{"$ref": "#/tables/0"}]},
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [],
                "data": {"num_rows": 0, "num_cols": 0, "grid": []},
            }
        ],
    }

    parsed = digest_docling_document(document, "8" * 64)

    assert parsed["exclusions"][0]["reason"] == "empty_table"
    assert parsed["exclusions"][0]["source_reference"]["docling_ref"] == ("#/tables/0")


def test_blank_item_row_is_retained_in_exclusion_ledger() -> None:
    document = {
        "schema_name": "DoclingDocument",
        "version": "1.10.0",
        "name": "Checklist",
        "groups": [],
        "texts": [],
        "body": {"self_ref": "#/body", "children": [{"$ref": "#/tables/0"}]},
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [],
                "data": {
                    "num_rows": 3,
                    "num_cols": 2,
                    "grid": [
                        [{"text": "Item"}, {"text": "Requirements"}],
                        [{"text": ""}, {"text": "Unowned table detail"}],
                        [{"text": "Identity"}, {"text": "Provide manufacturer name"}],
                    ],
                },
            }
        ],
    }

    parsed = digest_docling_document(document, "9" * 64)

    blank = next(
        item for item in parsed["exclusions"] if item["reason"] == "blank_item_cell_row"
    )
    assert blank["text"] == "Unowned table detail"
    assert blank["source_reference"]["row_index"] == 1


def test_unowned_normative_text_is_retained_in_exclusion_ledger() -> None:
    document = {
        "schema_name": "DoclingDocument",
        "version": "1.10.0",
        "name": "Guidance",
        "groups": [],
        "tables": [],
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "text",
                "text": "Provide the application before review.",
                "children": [],
                "prov": [],
            },
            {
                "self_ref": "#/texts/1",
                "label": "section_header",
                "text": "Identity",
                "level": 1,
                "children": [],
                "prov": [],
            },
            {
                "self_ref": "#/texts/2",
                "label": "list_item",
                "text": "Include manufacturer identity.",
                "children": [],
                "prov": [],
            },
        ],
        "body": {"self_ref": "#/body", "children": []},
    }

    parsed = digest_docling_document(document, "a" * 64)

    assert parsed["items"][0]["label"] == "Identity"
    assert parsed["exclusions"][0]["reason"] == "unowned_normative_candidate"
