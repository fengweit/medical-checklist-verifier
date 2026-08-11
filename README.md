# medical-checklist-verifier

Provenance-first tools for turning medical and regulatory checklists into structured data that later review agents can consume.

## Module 1: checklist-digester

`checklist-digester` accepts exactly one PDF or DOCX and emits deterministic JSON containing:

- checklist identity and source SHA-256;
- the Docling extraction/library versions;
- checklist items;
- explicit table-cell requirements and separately labeled section-derived normative candidates;
- source references for every item, requirement/candidate, guidance entry, and exclusion;
- declared document location/reference columns and guidance cells when present; and
- explicit/candidate/guidance counts, role-inference diagnostics, warnings, and a referenced exclusion ledger for backtesting.

The document-understanding layer uses [Docling](https://github.com/docling-project/docling), including its PDF layout, table, OCR, native `DoclingDocument`, and ordered `iterate_items()` traversal APIs. No separate PDF/DOCX parser or custom reference-tree walker is maintained in this repository. The extraction choice was tested against Kreuzberg and Unstructured on the four-file corpus; see [`spikes/001-document-extractor-selection`](spikes/001-document-extractor-selection/README.md). This repository supplies only the versioned domain-semantic interpreter and agent handoff contract that Docling does not provide.

## Install

Python 3.10+ is required.

```bash
uv sync --extra dev
```

Docling downloads its layout/OCR model artifacts on the first PDF conversion. Subsequent local conversions reuse the model cache.

## Single-entry conversion

Write JSON to a file:

```bash
uv run checklist-digester checklist.pdf --output digest.json
uv run checklist-digester checklist.docx -o digest.json
```

Or emit JSON to stdout:

```bash
uv run checklist-digester checklist.docx
```

The command returns exit code `0` only after validating against the packaged Draft 2020-12 JSON Schema and checking global ID uniqueness, references, classification/derivation consistency, exclusion provenance, and count consistency. Unsupported, partial, or structurally unrecognized conversions return exit code `2` and do not produce a successful digest. The input is read once into immutable bytes; that same byte stream is both SHA-256 hashed and passed to Docling.

Inputs are limited to 100 MiB and 500 pages through both a pre-conversion byte check and Docling's native `max_file_size`/`max_num_pages` limits. This CLI does not provide an OS sandbox or hard wall-clock timeout; process genuinely untrusted documents in a separately resource-limited worker/container.

## Backtest a corpus

The entry point intentionally converts one file per invocation, so a corpus can be replayed transparently:

```bash
mkdir -p backtest-output
for source in /path/to/checklists/*; do
  uv run checklist-digester "$source" \
    --output "backtest-output/$(basename "$source").json"
done
```

The hash-pinned development corpus has a stricter replay command:

```bash
uv run python scripts/backtest_td_checklists.py \
  "/Users/tian/Downloads/TD checklist"
```

Example corpus used during development:

```text
/Users/tian/Downloads/TD checklist/
├── MHS MDR TD Submission Checklist.docx
├── Team-NB-PositionPaper-...updated.docx
├── P05 tuv-rheinland-...MDR检查表.pdf
└── BSI MD MDR Best Practice Documentation Submissions.pdf
```

No source documents or generated customer digests are committed to this repository. The verified corpus results and limitations are recorded in [`docs/BACKTEST.md`](docs/BACKTEST.md).

## Output contract

The published JSON Schema is:

```text
schemas/checklist-digester.v1.schema.json
```

Two interpreter modes are explicit in every output:

- `semantic_tables`: table roles are inferred at table scope from high-confidence semantic headers, cell flags/spans, sample-column behavior, outcome values, role uniqueness, and bounded adjacent schemas. It supports submission checklists, bilingual requirement/evidence tables, and numbered item/guidance tables. Merged/category cells and outcome columns are never treated as requirements.
- `document_sections`: section headings group only non-empty list candidates and prose with explicit modal/action constructions. These records are classified `normative_candidate`, not asserted as final legal requirements. Contents, scope/front matter, abbreviations, headers/footers, and corporate contact blocks are excluded.

Every requirement record has an explicit `classification`:

- `explicit_requirement`: selected from a high-confidence checklist/requirement table cell;
- `normative_candidate`: selected from structured list content or modal/action prose and requiring later semantic review.

The parser is not allowed to hide uncertain structure:

- `diagnostics.role_tables` records every selected role map, inference method, confidence, and evidence;
- `diagnostics.unknown_tables` preserves every unrecognized table and records whether tightly bounded continuation guidance was attached;
- `exclusions` records document indexes, empty tables, blank item-cell rows, merged/category cells, unfilled template context, non-authoritative inferred rows, unowned normative candidates, front matter, section dividers, reviewer rows, sign-off tables, and contact footers with Docling references;
- `warnings` states when normative candidates or deterministic segmentation still requires semantic review.

Exact header aliases are high-confidence hints, not file-specific column numbers and not the only inference path. A tested multilingual embedding model was rejected as the sole classifier because it misclassified material real headers; the evidence is in the extractor-selection spike.

Requirement derivation is never hidden:

- `explicit_requirement_cell_segment`
- `item_cell_segment`
- `guidance_requirement_cell`
- `section_list_candidate`
- `section_modal_candidate`

Only submission-table cells are segmented on semicolon/newline boundaries. Requirement/guidance tables remain whole-cell to avoid turning embedded examples into independent obligations. Segmentation and all `normative_candidate` records require later semantic review while preserving the original source reference.

## Source references

Every source reference includes a stable Docling JSON pointer:

```json
{
  "kind": "docling_table_cell",
  "docling_ref": "#/tables/3",
  "table_index": 3,
  "row_index": 1,
  "cell_index": 0
}
```

PDF references also include a cell bounding box and page number when Docling provides an unambiguous single-page table provenance. For a table spanning multiple pages without cell-level page metadata, the page number is deliberately omitted rather than guessed. DOCX references remain replayable through the source SHA-256, pinned Docling version, Docling element pointer, and table/row/cell coordinates.

## Development

```bash
uv run pytest -q
```

The tests cover submission checklists, bilingual requirement/evidence tables, numbered guidance tables, bounded inherited schemas, unrelated same-width tables, merged/category rows, administrative exclusions, normative-candidate filtering, continuation guidance, ambiguous multi-page provenance, deterministic IDs, immutable source streams, CLI behavior, packaged-schema parity, and JSON Schema conformance.
