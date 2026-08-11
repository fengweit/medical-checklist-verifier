# 001 — Document Extractor and Semantic Role Selection

## Question

Given the four real files in `/Users/tian/Downloads/TD checklist`, which maintained external library can recover PDF and DOCX structure, tables, hierarchy, and provenance well enough to be the extraction boundary for `checklist-digester`? Can a generic multilingual embedding model safely replace deterministic table-role validation?

## Corpus

| File | SHA-256 | Format |
|---|---|---|
| BSI MD MDR Best Practice Documentation Submissions.pdf | `1868fcd5270e52a94a42a2db08a4ecf3b255ba64178c4eb0ed0f19e31da82872` | PDF |
| MHS MDR TD Submission Checklist.docx | `b97dee2e776770b0a5d58fe0e5a00ac1616ef4cea7b6dd8d0172e8df8d5b5511` | DOCX |
| P05 TÜV Rheinland MDR TD Guidance.pdf | `d25335808354000d8d9effda333ed5d93e9f4ac3441f96e6f379eeb254743106` | PDF |
| Team-NB Best Practice Guidance V3.docx | `bee566e433fbf8a8f405eb972159f44e4ec36b3c41481f33e6947d19a54a0aaa` | DOCX |

## Current library releases checked

The versions below were read from the PyPI JSON API during the spike.

| Library | Version | Declared scope |
|---|---:|---|
| Docling | 2.119.0 | Unified PDF, DOCX, HTML, and other document representation |
| Kreuzberg | 4.10.2 | Rust-backed extraction across PDF, Office, image, and other formats |
| Unstructured | 0.25.2 | Partition documents into downstream ML elements |
| marker-pdf | 2.0.0 | PDF-to-Markdown conversion |
| PyMuPDF4LLM | 1.28.2 | PDF utilities for LLM/RAG |

marker-pdf and PyMuPDF4LLM were eliminated as the primary boundary because neither is a unified PDF-and-DOCX structural parser for this module.

## Executed comparison

### Docling 2.119.0

| Source | Recovered structure |
|---|---|
| MHS DOCX | 70 tables, 639 typed text elements, 19 section headers plus title; semantic checklist tables preserved |
| Team-NB DOCX | 4 tables, 2,599 typed text elements, 75 section headers, 614 list items; nested heading/list tree preserved |
| TÜV PDF | 29 tables, 348 typed text elements, 28 section headers; page/bounding-box provenance preserved |
| BSI PDF | 26 tables, 413 typed text elements, 48 section headers; page/bounding-box provenance preserved |

Cold corpus conversion took about three minutes on CPU because PDF layout/OCR models were downloaded and initialized. Cached conversion reuses those artifacts. DOCX VML/WMF warnings were surfaced rather than treated as visual proof.

### Kreuzberg 4.10.2

| Source | Time | Recovered structure |
|---|---:|---|
| MHS DOCX | 0.01 s | 68 tables; 451 document nodes when structure output enabled |
| Team-NB DOCX | 0.04 s | 4 tables; 3,028 nodes including 75 headings and 600 list items |
| TÜV PDF | 0.12 s | 40 page-level paragraph nodes; 0 tables |
| BSI PDF | 0.49 s | 41 page-level paragraph nodes; 0 tables |

Kreuzberg is an excellent fast DOCX cross-check, but the tested PDF path flattened each page and lost the table/heading structure required by this module.

### Unstructured 0.25.2

`strategy="fast"` results:

| Source | Time | Elements | Tables | Notable issue |
|---|---:|---:|---:|---|
| MHS DOCX | 1.40 s | 429 | 68 | Good table recovery |
| Team-NB DOCX | 4.06 s | 2,253 | 4 | Useful categories and list items |
| TÜV PDF | 3.33 s | 1,213 | 0 | 553 elements classified as `Title` |
| BSI PDF | 61.29 s | 735 | 0 | Useful categories, but no PDF tables |

`strategy="hi_res"` was also attempted for both PDFs. It failed closed because the required Tesseract executable was not installed. Installing more system OCR tooling would not repair the `fast` path's lack of PDF table structure and would increase deployment complexity.

## Semantic-role experiment

`fastembed` 0.7+ with `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` was tested against six role descriptions (`section`, `item`, `requirements`, `location`, `outcome`, `reference`) and 14 real/representative English and Chinese headers.

It ranked the intended role first for 11 of 14 headers, but failed on decisive cases:

- `BSI Completeness Check ...` ranked as `requirements`, not reviewer `outcome`.
- `Subject / Reference to MDR Annex II ...` ranked as `reference`, not normative `item`.
- `Reference to TD document ...` ranked as legal `reference`, not applicant evidence `location`.
- `审核要求` had only a 0.014 margin over `item`.

A standalone embedding nearest-neighbor classifier is therefore unsafe. It may be used only as one signal in a table-level constrained assignment, with data-cell evidence, role uniqueness, confidence/margin thresholds, and fail-closed behavior.

## Verdict: DOCLING VALIDATED; SEMANTIC SCOPE BOUNDED

### Validated

Docling is the strongest primary extraction backend for this corpus because it is the only tested library that provides one typed representation across both formats while retaining PDF tables, hierarchy, and page/bounding-box provenance. Kreuzberg is a strong independent DOCX cross-check and performance reference.

The production implementation now includes the required safeguards:

1. Docling is isolated behind a versioned interpreter interface.
2. Table roles combine semantic headers, cell spans/flags, sample content, role uniqueness, and bounded adjacent-schema compatibility rather than filename mappings or fixed coordinates.
3. Requirement/guidance tables, numbered leaf tables, and submission checklists have distinct structural gates.
4. Unknown layouts fail closed or remain explicitly visible in diagnostics.
5. Excluded rows/cells/sections retain reasoned provenance.
6. A hash-pinned corpus manifest asserts exact counts, derivations, forbidden boilerplate, exclusions, and replayable references.
7. The same immutable bytes are hashed and converted, and only exact Docling `SUCCESS` is accepted.
8. The packaged JSON Schema is enforced at runtime alongside semantic checks.

### Deliberately not claimed

No external library tested identifies arbitrary domain semantics perfectly. Extraction libraries recover structure; they do not make final legal judgments. The interpreter therefore distinguishes `explicit_requirement` table cells from `normative_candidate` list/modal prose. Candidates and deterministic submission-cell segmentation remain review inputs for the later agent stage.

The implementation is evidence-backed for the hash-pinned corpus and tested structural families; it is not described as universal or perfect.
