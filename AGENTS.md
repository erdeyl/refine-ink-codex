# Codex Project Instructions

This repository is the Codex-native adaptation of refine-ink.

## Primary Goal

Produce rigorous, evidence-grounded referee reports for academic PDFs, with deterministic preprocessing and transparent audit outputs.

## Entry Point

When asked to review a paper, run:

```bash
python scripts/codex_prepare_review.py [path/to/paper.pdf] [--email you@example.com]
```

If no PDF path is provided, the script auto-detects a single `.pdf` in the current directory and performs preflight validation.

## Codex App `/review` Workflow

In the ChatGPT Codex app, treat `/review` as the review command:

1. User uploads a PDF with the plus button.
2. User types `/review` (optionally `/review /absolute/path/to/file.pdf`).
3. Resolve the PDF path:
   - If `/review <path>` is provided, use that path.
   - If only `/review` is provided and exactly one uploaded PDF is present, use it.
   - If multiple PDFs are available, ask the user to choose one.
4. Run:
   - `python scripts/codex_prepare_review.py "<resolved_pdf_path>"`
5. Continue with analysis passes from the generated review workspace.

This command performs setup and deterministic phases:

1. Create review workspace under `reviews/`
2. Convert PDF to Markdown (`pdf_to_markdown.py`)
3. Verify conversion fidelity (`verify_conversion.py` logic)
4. Run manuscript consistency lint (`review_consistency_lint.py`) for internal logic checks
5. Verify references via CrossRef/OpenAlex/Semantic Scholar (`verify_references.py`)
6. Generate scaffold outputs (`chunks/chunk_map.json` with dimension assignments, `agent_outputs/*.md`, `output/review_EN.md`, `output/manifest.json`, `NEXT_STEPS.md`)

## Manual Analysis Workflow (Codex)

After preparation, complete qualitative analysis in passes and save outputs:

- `agent_outputs/math-logic.md`
- `agent_outputs/notation.md`
- `agent_outputs/exposition.md`
- `agent_outputs/empirical.md`
- `agent_outputs/cross-section.md`
- `agent_outputs/econometrics.md`
- `agent_outputs/literature.md`
- `agent_outputs/references.md`
- `agent_outputs/language.md`

Then synthesize final report in `output/review_EN.md` (and `review_HU.md` if needed), and render HTML with:

```bash
python scripts/md_to_html.py reviews/<name>/output/review_EN.md
```

## Quality Rules

- Ground every finding in exact source text from the converted markdown.
- Distinguish internal evidence from external knowledge.
- Use severity labels: Critical, Major, Minor, Suggestion.
- Include confidence scores per finding (0-100).
- Avoid claims that cannot be traced to document text or verified external sources.

## Deterministic Artifacts

Each review directory should include:

- `input/original.pdf`
- `input/original_converted.md`
- `input/original_references.json`
- `verification/original_verification.json`
- `verification/consistency_lint_report.json`
- `verification/reference_report.json`
- `chunks/chunk_map.json`
- `agent_outputs/*.md`
- `output/review_EN.md`
- `output/manifest.json`
- `NEXT_STEPS.md`

## Legacy Claude Assets

Legacy Claude-specific orchestration files are preserved under `legacy/claude/` for reference only. They are not required for Codex operation.
