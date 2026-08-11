# Checklist Digester Backtest

Corpus (kept outside Git):

```text
/Users/tian/Downloads/TD checklist
```

The corpus is hash-pinned in `backtests/td-checklists.json` and replayed with:

```bash
uv run python scripts/backtest_td_checklists.py \
  "/Users/tian/Downloads/TD checklist"
```

For each case, `digest_checklist` reads the source once into immutable bytes, checks the manifest SHA-256 against that exact buffer, and passes the same bytes to Docling through one `DocumentStream`. Conversion must return exact `ConversionStatus.SUCCESS`; the digest is then validated against the packaged Draft 2020-12 schema and semantic invariants. The runner prints its summary only after every case passes; it does not persist generated digests.

## Final corpus baseline

| Source | Format | Mode | Items | Explicit requirements | Normative candidates | Guidance entries | Key structural result |
|---|---:|---|---:|---:|---:|---:|---|
| MHS MDR TD Submission Checklist | DOCX | `semantic_tables` | 71 | 114 segments | 0 | 0 | 71 high-confidence submission rows; two unfilled context rows excluded |
| Team-NB Best Practice Guidance V3 | DOCX | `document_sections` | 63 sections | 0 | 836 | 0 | 604 non-empty list candidates plus 232 modal/action prose candidates |
| TÜV Rheinland bilingual MDR TD Guidance | PDF | `semantic_tables` | 86 | 86 | 0 | 87 | 86 leaf requirement cells; 22 merged/category cells excluded; final-page continuation guidance attached |
| BSI MDR Documentation Submissions | PDF | `semantic_tables` | 96 | 96 | 0 | 95 | 96 numbered leaf item cells; 27 section/category rows excluded |

`requirement_count` remains the sum of both classifications for contract compatibility. The output also publishes `explicit_requirement_count`, `normative_candidate_count`, and `guidance_count`, so downstream agents cannot confuse candidate guidance prose with verified obligations.

## Correction from the rejected baseline

An earlier section-based replay produced 41/197 for the BSI PDF and 11/124 for the TÜV PDF by treating headings and surrounding prose as checklist requirements. Independent review correctly rejected that behavior after reproducing title-page, footer, and marketing text as false requirements. Those counts are retired and are not release evidence.

The corrected interpreter now:

- treats Docling requirement/guidance tables as authoritative for both PDFs;
- selects TÜV requirement cells by semantic header, column offset, `column_header`, `row_section`, and `col_span` evidence;
- selects BSI numbered leaf rows while retaining one- and two-component numbered rows as excluded section/category context;
- keeps embedded guidance whole rather than exploding bullets/examples into obligations;
- classifies Team-NB lists and modal/action prose as `normative_candidate`, never as an asserted explicit requirement;
- excludes contents/document-index tables, scope/front matter, abbreviations, headers/footers, corporate contact blocks, merged rows, and unfilled template context with source references;
- bounds inherited table schemas by distance and row compatibility, with regression coverage for unrelated same-width tables;
- preserves every unknown table in diagnostics and records whether tightly bounded continuation guidance was attached;
- omits page numbers for multi-page tables when Docling has no cell-specific page instead of assigning the first table page.

## External-library evaluation

`spikes/001-document-extractor-selection/README.md` records executed comparisons against Kreuzberg 4.10.2 and Unstructured 0.25.2. Docling remained primary because it was the only tested backend that recovered both DOCX structure and PDF tables/provenance on this corpus. A multilingual embedding-only role classifier was rejected after material header misclassifications.

## Additional external template

The existing BSI completeness-check DOCX outside the corpus was replayed separately:

- 149 items;
- 152 deterministic explicit requirement segments;
- 32 referenced exclusions: 6 section dividers, 6 blank item-cell rows, 19 administrative/reviewer rows, and 1 sign-off table;
- no reviewer/sign-off content emitted as requirements.

## What this backtest proves

- Both PDFs are interpreted from Docling table cells rather than flattened prose or filename-specific coordinates.
- Both DOCX files use Docling's native Word structure and `DoclingDocument.iterate_items()` ordering; the earlier custom JSON reference-tree walkers were removed.
- Every item, requirement/candidate, guidance entry, and exclusion has a kind-compatible Docling pointer whose table index is checked against the pointer. Content-level replay still requires re-extracting the hash-pinned source with the recorded Docling package version and equivalent model artifacts.
- PDF cell references preserve bounding boxes and a page only when provenance is unambiguous.
- Repeated wording at distinct source locations is retained; IDs incorporate source hash and source locator.
- The real-corpus assertions include source hashes checked before conversion, exact counts, derivation counts, representative labels, forbidden boilerplate labels, required exclusion reasons, modes, structural minima, and source-pointer/index coherence.

## Deliberate limitations

1. Submission-table semicolon/newline splitting is deterministic segmentation, not expert atomic decomposition.
2. `normative_candidate` means a structured list or modal/action prose candidate that requires later agent review; it is not a final legal obligation.
3. DOCX conversions in this corpus lack page/bounding-box provenance. Their exact locator is source SHA-256 plus Docling pointer and table/row/cell or text-node reference.
4. Docling reported unavailable VML/WMF images in Team-NB. Text structure was recovered, but visual-image completeness is not claimed.
5. The first PDF run may download Docling/OCR models and is slower than cached runs. The digest records package versions but not model-artifact checksums, so model-level offline reproducibility is not claimed.
6. Inputs are capped at 100 MiB and 500 pages, but the CLI itself is not an OS sandbox or hard wall-clock limiter.
7. Counts are regression baselines for these exact source hashes, not universal expectations for similarly named documents.

Generated customer digests remain outside Git.
