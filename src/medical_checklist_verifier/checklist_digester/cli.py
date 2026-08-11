from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any, Dict, List, Optional

from docling.exceptions import BaseError as DoclingError
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from .digester import ChecklistParseError, digest_checklist


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    schema_path = files("medical_checklist_verifier.schemas").joinpath(
        "checklist-digester.v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validate_source_reference(reference: Dict[str, Any]) -> None:
    kind = reference.get("kind")
    pointer = reference.get("docling_ref", "")
    if kind == "docling_text":
        if re.fullmatch(r"#/texts/\d+", pointer) is None:
            raise ValueError("Docling text reference has an incoherent pointer")
        forbidden = {"table_index", "row_index", "cell_index", "segment_index"}
    elif kind in {"docling_table", "docling_table_cell"}:
        match = re.fullmatch(r"#/tables/(\d+)", pointer)
        if match is None or int(match.group(1)) != reference.get("table_index"):
            raise ValueError("Docling table reference index does not match its pointer")
        forbidden = {"charspan"}
        if kind == "docling_table":
            forbidden |= {"row_index", "cell_index", "segment_index"}
    else:
        raise ValueError("Unknown Docling source-reference kind")
    if forbidden & reference.keys():
        raise ValueError(f"{kind} reference contains incompatible locator fields")


def validate_digest(payload: Dict[str, Any]) -> None:
    """Fail closed if a generated digest violates the v1 handoff contract."""
    try:
        _schema_validator().validate(payload)
    except ValidationError as error:
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        raise ValueError(
            f"JSON Schema validation failed at {location}: {error.message}"
        ) from error
    if payload.get("schema_version") != "checklist-digester.v1":
        raise ValueError("Invalid or missing schema_version")
    extraction = payload.get("extraction")
    if (
        not isinstance(extraction, dict)
        or extraction.get("library") != "docling"
        or extraction.get("conversion_status") != "success"
    ):
        raise ValueError("Invalid or unsuccessful Docling extraction metadata")
    checklist = payload.get("checklist")
    if not isinstance(checklist, dict) or not checklist.get("id"):
        raise ValueError("Invalid or missing checklist identity")
    source = checklist.get("source")
    if not isinstance(source, dict) or len(source.get("sha256", "")) != 64:
        raise ValueError("Invalid or missing checklist source hash")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Digest must contain at least one checklist item")

    ids = set()
    requirement_count = 0
    explicit_requirement_count = 0
    normative_candidate_count = 0
    guidance_count = 0
    for item in items:
        if not item.get("id") or item["id"] in ids:
            raise ValueError("Checklist item IDs must be present and unique")
        ids.add(item["id"])
        if not item.get("label") or not item.get("source_reference", {}).get(
            "docling_ref"
        ):
            raise ValueError(f"Item {item['id']} lacks label or source reference")
        _validate_source_reference(item["source_reference"])
        guidance = item.get("guidance")
        if not isinstance(guidance, list) or any(
            not entry.get("text")
            or not entry.get("source_reference", {}).get("docling_ref")
            for entry in guidance
        ):
            raise ValueError(f"Item {item['id']} has malformed guidance")
        for entry in guidance:
            _validate_source_reference(entry["source_reference"])
        guidance_count += len(guidance)
        requirements = item.get("requirements")
        if not isinstance(requirements, list) or not requirements:
            raise ValueError(f"Item {item['id']} has no requirements")
        for requirement in requirements:
            if not requirement.get("id") or requirement["id"] in ids:
                raise ValueError("Requirement IDs must be present and unique")
            ids.add(requirement["id"])
            if not requirement.get("text") or not requirement.get(
                "source_reference", {}
            ).get("docling_ref"):
                raise ValueError(
                    f"Requirement {requirement['id']} lacks text or source reference"
                )
            _validate_source_reference(requirement["source_reference"])
            if requirement.get("derivation") not in {
                "explicit_requirement_cell_segment",
                "item_cell_segment",
                "guidance_requirement_cell",
                "section_list_candidate",
                "section_modal_candidate",
            }:
                raise ValueError(
                    f"Requirement {requirement['id']} has an invalid derivation"
                )
            classification = requirement.get("classification")
            if classification == "explicit_requirement":
                explicit_requirement_count += 1
            elif classification == "normative_candidate":
                normative_candidate_count += 1
            else:
                raise ValueError(
                    f"Requirement {requirement['id']} has an invalid classification"
                )
            requirement_count += 1

    expected = {
        "item_count": len(items),
        "requirement_count": requirement_count,
        "explicit_requirement_count": explicit_requirement_count,
        "normative_candidate_count": normative_candidate_count,
        "guidance_count": guidance_count,
    }
    if payload.get("statistics") != expected:
        raise ValueError("Digest statistics do not match item and requirement contents")
    diagnostics = payload.get("diagnostics")
    if not isinstance(diagnostics, dict) or (
        diagnostics.get("items_emitted") != expected["item_count"]
        or diagnostics.get("requirements_emitted") != expected["requirement_count"]
    ):
        raise ValueError("Digest diagnostics do not match emitted contents")
    for diagnostic in diagnostics.get("role_tables", []) + diagnostics.get(
        "unknown_tables", []
    ):
        _validate_source_reference(
            {
                "kind": "docling_table",
                "docling_ref": diagnostic.get("docling_ref"),
                "table_index": diagnostic.get("table_index"),
            }
        )
    exclusions = payload.get("exclusions")
    if not isinstance(exclusions, list) or any(
        not item.get("reason")
        or not item.get("text")
        or not item.get("source_reference", {}).get("docling_ref")
        for item in exclusions
    ):
        raise ValueError("Digest exclusion ledger is malformed")
    for item in exclusions:
        _validate_source_reference(item["source_reference"])
    warnings = payload.get("warnings")
    if not isinstance(warnings, list) or len(warnings) != len(set(warnings)):
        raise ValueError("Digest warnings must be a unique list")


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(rendered)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="checklist-digester",
        description=(
            "Convert one PDF or DOCX checklist into referenced items "
            "and requirements JSON."
        ),
    )
    parser.add_argument("input", type=Path, help="PDF or DOCX checklist")
    parser.add_argument(
        "-o", "--output", type=Path, help="Output JSON path; defaults to stdout"
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        input_path = args.input.expanduser().resolve()
        output_path = args.output.expanduser().resolve() if args.output else None
        if output_path == input_path:
            raise ValueError("Output path must differ from the input checklist path")
        payload = digest_checklist(input_path)
        validate_digest(payload)
        if output_path:
            _atomic_write_json(output_path, payload)
        else:
            json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
        return 0
    except (
        ChecklistParseError,
        DoclingError,
        FileNotFoundError,
        ValueError,
        OSError,
    ) as error:
        print(f"checklist-digester: error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
