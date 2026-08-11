from __future__ import annotations

import hashlib
from functools import lru_cache
from importlib.metadata import version
from io import BytesIO
from pathlib import Path
from typing import Any, Dict

from docling.datamodel.base_models import ConversionStatus, DocumentStream
from docling.document_converter import DocumentConverter

from .docling_adapter import digest_docling_document


class ChecklistParseError(ValueError):
    """Raised when a supported document contains no detectable checklist items."""


MEDIA_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}
MAX_SOURCE_BYTES = 100 * 1024 * 1024
MAX_DOCUMENT_PAGES = 500
INTERPRETER_NAME = "docling-structural"
INTERPRETER_VERSION = "3.0.0"
DOCLING_VERSION = version("docling")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=1)
def _document_converter() -> DocumentConverter:
    """Reuse Docling models and pipeline objects across backtest inputs."""
    return DocumentConverter()


def digest_checklist(
    input_path: Path | str, *, expected_sha256: str | None = None
) -> Dict[str, Any]:
    """Convert one PDF or DOCX checklist into deterministic agent-ready JSON."""
    path = Path(input_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Checklist file does not exist: {path}")
    extension = path.suffix.lower()
    if extension not in MEDIA_TYPES:
        raise ValueError(f"Unsupported checklist format: {extension or '(none)'}")

    source_bytes = path.read_bytes()
    if len(source_bytes) > MAX_SOURCE_BYTES:
        raise ChecklistParseError(
            f"Checklist exceeds the {MAX_SOURCE_BYTES}-byte input limit"
        )
    source_hash = _sha256(source_bytes)
    if expected_sha256 is not None and source_hash != expected_sha256:
        raise ChecklistParseError(
            f"Checklist source hash does not match the approved manifest: {path.name}"
        )
    source_stream = DocumentStream(name=path.name, stream=BytesIO(source_bytes))
    conversion = _document_converter().convert(
        source_stream,
        max_file_size=MAX_SOURCE_BYTES,
        max_num_pages=MAX_DOCUMENT_PAGES,
    )
    if conversion.status is not ConversionStatus.SUCCESS:
        raise ChecklistParseError(
            "Docling conversion did not complete successfully: "
            f"{conversion.status.value}"
        )
    parsed = digest_docling_document(conversion.document, source_hash)
    if not parsed["compatible"]:
        unknown_count = len(parsed["diagnostics"]["unknown_tables"])
        raise ChecklistParseError(
            "Unknown checklist table layout; semantic interpretation failed closed "
            f"with {unknown_count} unrecognized table(s)"
        )
    if not parsed["items"]:
        raise ChecklistParseError(
            "No checklist items were detected in the Docling structure; inspect the "
            "document layout and extraction artifacts before review."
        )

    items = parsed["items"]
    statistics = {
        "item_count": len(items),
        "requirement_count": 0,
        "explicit_requirement_count": 0,
        "normative_candidate_count": 0,
        "guidance_count": 0,
    }
    for item in items:
        statistics["guidance_count"] += len(item["guidance"])
        for requirement in item["requirements"]:
            statistics["requirement_count"] += 1
            statistics[f"{requirement['classification']}_count"] += 1

    return {
        "schema_version": "checklist-digester.v1",
        "extraction": {
            "library": "docling",
            "library_version": DOCLING_VERSION,
            "conversion_status": conversion.status.value,
            "interpreter": {
                "name": INTERPRETER_NAME,
                "version": INTERPRETER_VERSION,
            },
            "adapter_mode": parsed["adapter_mode"],
            "docling_schema_name": parsed["docling_schema_name"],
            "docling_schema_version": parsed["docling_schema_version"],
        },
        "checklist": {
            "id": f"checklist-{source_hash[:16]}",
            "title": parsed["title"],
            "source": {
                "filename": path.name,
                "media_type": MEDIA_TYPES[extension],
                "sha256": source_hash,
            },
        },
        "items": items,
        "diagnostics": parsed["diagnostics"],
        "exclusions": parsed["exclusions"],
        "warnings": parsed["warnings"],
        "statistics": statistics,
    }
