# Chunking Strategy

This document describes the chunking implementation used by `scripts/codex_prepare_review.py`.

## Scope

Chunking in the Codex workflow is deterministic and lightweight. It does not perform model-driven semantic segmentation. Instead, it builds a stable structural map that downstream analysis passes can use as routing metadata.

## How Chunking Works

`codex_prepare_review.py` computes `chunks/chunk_map.json` in four steps:

1. Parse the converted markdown (`input/original_converted.md`)
2. Detect headings with regex `^(#{1,3})\s+(.+?)$`
3. Create one chunk per heading section using inclusive line ranges
4. Annotate each chunk with content tags:
   - `has_equations`
   - `has_tables`
   - `has_figures`
   - `is_references`
   - `is_abstract`

If no headings are found, a single `Document` chunk is created.

## Output Schema

`chunk_map.json` uses this structure:

```json
{
  "total_chunks": 3,
  "chunks": [
    {
      "id": "c1",
      "heading": "Introduction",
      "level": 2,
      "start_line": 12,
      "end_line": 78,
      "words": 1042,
      "has_equations": false,
      "has_tables": true,
      "has_figures": false,
      "is_references": false,
      "is_abstract": false
    }
  ],
  "dimension_assignments": {
    "math-logic": ["c2"],
    "notation": [["c1", "c2", "c3"]],
    "exposition": [["c1", "c2", "c3"]],
    "empirical": ["c1"],
    "cross-section": [["c1", "c3"]],
    "econometrics": ["c2"],
    "literature": [],
    "references": ["c3"],
    "language": [["c1", "c2", "c3"]]
  }
}
```

## Dimension Assignment Heuristics

Assignments are metadata-only and generated with deterministic rules:

- `math-logic`: chunks with `has_equations=true`
- `empirical`: chunks with tables or figures
- `references`: chunks tagged as references
- `literature`: heading keyword match (`literature`, `related work`, `background`, `irodalom`)
- `econometrics`: heading keyword match (`method`, `methodology`, `model`, `identification`, `estimation`, `regression`), fallback to `empirical` chunks
- `notation`, `exposition`, `language`: all chunks grouped in windows of 3
- `cross-section`: best-effort heading pairs (intro-results, methods-results, abstract-conclusion), fallback first-last

Heading keyword matching is diacritic-insensitive, so Hungarian headings match whether accents are present or omitted.

## Limits

- No token-budget optimization or overlap windows are applied
- No chapter-aware adaptive splitting is currently implemented
- Assignments are heuristic guidance, not guaranteed semantic routing

## Why This Design

The Codex app workflow prioritizes deterministic preprocessing and transparent artifacts. The chunk map is designed to be:

- reproducible across runs,
- easy to inspect,
- sufficient for manual or semi-automated analysis passes.
