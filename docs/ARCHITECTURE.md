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
  -> chunks/convolution_plan.md
  -> agent_outputs/*.md stubs
  -> notebooklm/WORKFLOW.md
  -> notebooklm/QUESTION_LOG.md
  -> output/review_EN.md template
  -> output/manifest.json
  -> NEXT_STEPS.md
  |
  v
[Phase 5] NotebookLM grounded QA sidecar
  -> contradiction checks
  -> source-grounded questions
  -> synthesis challenge log
  |
  v
[Phase 6] Codex analysis passes
  -> math-logic, notation, exposition, empirical,
     cross-section, econometrics, literature,
     references, language
  |
  v
[Phase 7] Synthesis + HTML rendering
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
- `notebooklm/WORKFLOW.md`
- `notebooklm/QUESTION_LOG.md`

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
- `notebooklm/`: NotebookLM MCP prompts and analyst question log
- `output/`: final review artifacts (`review_EN.md`, optional HU, HTML, `manifest.json`)

## NotebookLM Integration

NotebookLM is treated as a grounded QA sidecar rather than a deterministic transformation step.

- After preparation: use `notebooklm/WORKFLOW.md` to ingest the PDF, converted markdown, verification JSON, and chunk map
- During analysis passes: use NotebookLM to surface contradictions, unsupported claims, and missing evidence before closing each pass file
- During synthesis: use NotebookLM to challenge draft reviewer claims against the source pack
- During three-mode comparison: use the comparison workspace `notebooklm/WORKFLOW.md` to compare chunked, no-chunk, and PDF-native outputs against the original PDF

The generated `notebooklm/QUESTION_LOG.md` provides a lightweight audit trail for material NotebookLM interactions.

## Convolution Review Layer

The workflow now adds a deterministic multi-scale overlap plan to every review workspace:

- `chunked` workflow: chunk-overlap windows across structural sections
- `no-chunk` workflow: paragraph/span-overlap windows inside the full document
- `pdf` workflow: page-overlap windows across PDF-native page chunks

This layer is written to `chunks/convolution_plan.md` and mirrored in `chunk_map.json` as `convolution_assignments`.

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
