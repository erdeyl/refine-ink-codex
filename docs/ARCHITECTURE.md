# Architecture

`refine-ink-codex` has two layers:

1. Deterministic preprocessing scripts
2. Codex-driven qualitative analysis passes

## System Flow

```text
PDF input
  |
  v
[Phase 1] pdf_to_markdown.py
  -> original_converted.md
  -> original_references.json
  (or PDF-native extraction when `--pdf-native-only`)
  |
  v
[Phase 2] verify_conversion.py
  -> original_verification.json (PASS/WARN/FAIL)
  |
  v
[Phase 3] verify_references.py
  -> reference_report.json
  |
  v
[Phase 4] codex_prepare_review.py scaffolding
  -> chunks/chunk_map.json
     (total_chunks + chunks + dimension_assignments)
  -> agent_outputs/*.md stubs
  -> output/review_EN.md template
  -> output/manifest.json
  -> NEXT_STEPS.md
  |
  v
[Phase 5] Codex analysis passes
  -> math-logic, notation, exposition, empirical,
     cross-section, econometrics, literature,
     references, language
  |
  v
[Phase 6] Synthesis + HTML rendering
  -> output/review_EN.md(.html)
  -> optional review_HU.md(.html)
```

`codex_prepare_review.py` supports chunking strategies:

- `chunked`: heading-based markdown chunking
- `no-chunk`: single document chunk
- `pdf`: PDF-native page chunking

`run_joint_workflow_review.py` runs three process variants and generates:

- `workflow_comparison.json/.md`
- `joint_review.md`

## Deterministic Components

| Script | Role |
|---|---|
| `scripts/codex_prepare_review.py` | Main entry point; orchestrates setup, conversion, verification, scaffolding |
| `scripts/pdf_to_markdown.py` | PDF parsing and reference extraction |
| `scripts/verify_conversion.py` | Fidelity checks between PDF and Markdown |
| `scripts/verify_references.py` | API-based reference validation |
| `scripts/md_to_html.py` | Markdown -> styled, sanitized HTML |

## Workspace Contract

Each run creates `reviews/<slug>_<date>/`:

- `input/`: immutable source artifacts (`original.pdf`, converted markdown, extracted refs)
- `verification/`: conversion/reference verification JSON
- `chunks/`: structural chunk map for analysis targeting
- `agent_outputs/`: per-dimension findings files
- `output/`: final review artifacts (`review_EN.md`, optional HU, HTML, `manifest.json`)

## Analysis Dimensions

The qualitative review is organized into nine dimensions:

- math-logic
- notation
- exposition
- empirical
- cross-section
- econometrics
- literature
- references
- language

## Legacy Compatibility

Original Claude-specific assets are preserved under `legacy/claude/` for traceability and migration history.
