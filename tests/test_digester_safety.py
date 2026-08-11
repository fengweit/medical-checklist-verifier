import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from docling.datamodel.base_models import ConversionStatus, DocumentStream

from medical_checklist_verifier.checklist_digester import digester


class FakeDocument:
    pass


def fake_digest(document: FakeDocument, source_hash: str) -> dict:
    assert isinstance(document, FakeDocument)
    reference = {
        "kind": "docling_text",
        "docling_ref": "#/texts/0",
    }
    return {
        "title": "Checklist",
        "compatible": True,
        "adapter_mode": "document_sections",
        "docling_schema_name": "DoclingDocument",
        "docling_schema_version": "1.10.0",
        "diagnostics": {
            "tables_total": 0,
            "section_headers_total": 1,
            "role_tables": [],
            "unknown_tables": [],
            "table_items_discarded": 0,
            "items_emitted": 1,
            "requirements_emitted": 1,
        },
        "exclusions": [],
        "warnings": ["NORMATIVE_CANDIDATES_REQUIRE_SEMANTIC_REVIEW"],
        "items": [
            {
                "id": "item-0001-0000000000",
                "label": "Identity",
                "section_title": None,
                "declared_reference": None,
                "declared_location": None,
                "source_reference": reference,
                "guidance": [],
                "requirements": [
                    {
                        "id": "item-0001-0000000000-requirement-001-0000000000",
                        "text": "Provide manufacturer identity",
                        "classification": "normative_candidate",
                        "derivation": "section_modal_candidate",
                        "source_reference": reference,
                    }
                ],
            }
        ],
    }


def test_hash_and_docling_conversion_use_same_immutable_bytes(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "input.docx"
    original = b"original-docx-bytes"
    source.write_bytes(original)

    class MutatingConverter:
        def convert(self, stream: DocumentStream, **kwargs):
            assert kwargs == {
                "max_file_size": digester.MAX_SOURCE_BYTES,
                "max_num_pages": digester.MAX_DOCUMENT_PAGES,
            }
            assert isinstance(stream, DocumentStream)
            assert stream.stream.getvalue() == original
            source.write_bytes(b"changed-after-read")
            return SimpleNamespace(
                status=ConversionStatus.SUCCESS,
                document=FakeDocument(),
            )

    monkeypatch.setattr(digester, "_document_converter", lambda: MutatingConverter())
    monkeypatch.setattr(digester, "digest_docling_document", fake_digest)

    payload = digester.digest_checklist(source)

    assert (
        payload["checklist"]["source"]["sha256"] == hashlib.sha256(original).hexdigest()
    )


def test_partial_docling_conversion_fails_closed(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "input.pdf"
    source.write_bytes(b"pdf")

    class PartialConverter:
        def convert(self, stream: DocumentStream, **kwargs):
            return SimpleNamespace(
                status=ConversionStatus.PARTIAL_SUCCESS,
                document=FakeDocument(),
            )

    monkeypatch.setattr(digester, "_document_converter", lambda: PartialConverter())

    with pytest.raises(digester.ChecklistParseError, match="partial_success"):
        digester.digest_checklist(source)


def test_oversized_source_is_rejected_before_docling(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "input.pdf"
    source.write_bytes(b"oversized")
    monkeypatch.setattr(digester, "MAX_SOURCE_BYTES", 3)

    def converter_must_not_run():
        raise AssertionError("Docling must not run for an oversized source")

    monkeypatch.setattr(digester, "_document_converter", converter_must_not_run)

    with pytest.raises(digester.ChecklistParseError, match="3-byte input limit"):
        digester.digest_checklist(source)


def test_manifest_hash_is_checked_on_the_same_bytes_before_docling(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "input.pdf"
    source.write_bytes(b"actual")

    def converter_must_not_run():
        raise AssertionError("Docling must not run after a manifest hash mismatch")

    monkeypatch.setattr(digester, "_document_converter", converter_must_not_run)

    with pytest.raises(digester.ChecklistParseError, match="approved manifest"):
        digester.digest_checklist(source, expected_sha256="0" * 64)
