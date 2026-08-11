from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from medical_checklist_verifier.checklist_digester import digest_checklist
from medical_checklist_verifier.checklist_digester.cli import validate_digest


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_case(case: dict[str, Any], source: Path, payload: dict[str, Any]) -> None:
    validate_digest(payload)
    require(
        payload["extraction"]["adapter_mode"] == case["adapter_mode"],
        f"adapter mode changed for {source.name}",
    )
    for field in (
        "item_count",
        "requirement_count",
        "explicit_requirement_count",
        "normative_candidate_count",
        "guidance_count",
    ):
        require(
            payload["statistics"][field] == case[field],
            f"{field} changed for {source.name}",
        )

    derivations = Counter(
        requirement["derivation"]
        for item in payload["items"]
        for requirement in item["requirements"]
    )
    require(
        dict(derivations) == case.get("expected_derivations", {}),
        f"requirement derivations changed for {source.name}",
    )
    for item in payload["items"]:
        require(
            item["source_reference"]["docling_ref"].startswith("#/"),
            f"invalid item reference in {source.name}",
        )
        for requirement in item["requirements"]:
            require(
                requirement["source_reference"]["docling_ref"].startswith("#/"),
                f"invalid requirement reference in {source.name}",
            )
        for guidance in item["guidance"]:
            require(
                guidance["source_reference"]["docling_ref"].startswith("#/"),
                f"invalid guidance reference in {source.name}",
            )

    labels = {item["label"] for item in payload["items"]}
    normalized_labels = {" ".join(label.split()) for label in labels}
    for required_fragment in case.get("required_label_substrings", []):
        require(
            any(required_fragment in label for label in normalized_labels),
            f"required label fragment missing: {required_fragment}",
        )
    for forbidden in case.get("forbidden_item_labels", []):
        require(forbidden not in labels, f"forbidden item emitted: {forbidden}")

    reasons = {item["reason"] for item in payload["exclusions"]}
    for required in case.get("required_exclusion_reasons", []):
        require(required in reasons, f"missing exclusion reason: {required}")

    diagnostics = payload["diagnostics"]
    require(
        len(diagnostics["role_tables"]) >= case.get("minimum_role_tables", 0),
        f"too few role tables for {source.name}",
    )
    require(
        diagnostics["section_headers_total"] >= case.get("minimum_section_headers", 0),
        f"too few section headers for {source.name}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the TD checklist corpus")
    parser.add_argument("corpus", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).parents[1] / "backtests" / "td-checklists.json",
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    summaries = []
    for case in manifest["cases"]:
        source = args.corpus / case["filename"]
        payload = digest_checklist(source, expected_sha256=case["sha256"])
        validate_case(case, source, payload)
        summaries.append(
            {
                "filename": source.name,
                "mode": payload["extraction"]["adapter_mode"],
                **payload["statistics"],
                "warnings": payload["warnings"],
                "exclusions": len(payload["exclusions"]),
            }
        )

    print(
        json.dumps({"passed": True, "cases": summaries}, ensure_ascii=False, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
