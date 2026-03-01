# Usage Guide

How to run a review in the Codex-native workflow.

## 1. Prepare Workspace (Deterministic Phase)

```bash
python scripts/codex_prepare_review.py [path/to/paper.pdf] --email you@example.com
```

If the path is omitted, `codex_prepare_review.py` auto-detects a single `.pdf` in the current directory and validates it before processing.

Optional flags:

- `--reviews-dir reviews_alt`
- `--name custom-paper-slug`
- `--skip-references`
- `--s2-api-key ...`
- `--force`

## 2. Inspect Generated Workspace

The command creates:

```text
reviews/<paper>_<YYYY-MM-DD>/
  input/
  verification/
  chunks/
  agent_outputs/
  output/
  NEXT_STEPS.md
```

Key files:

- `input/original_converted.md`
- `input/original_references.json`
- `verification/original_verification.json`
- `verification/reference_report.json`
- `chunks/chunk_map.json` (`total_chunks`, `chunks[]`, `dimension_assignments`)
- `output/review_EN.md`
- `output/manifest.json`

## 3. Complete Analysis Passes

Fill findings in:

- `agent_outputs/math-logic.md`
- `agent_outputs/notation.md`
- `agent_outputs/exposition.md`
- `agent_outputs/empirical.md`
- `agent_outputs/cross-section.md`
- `agent_outputs/econometrics.md`
- `agent_outputs/literature.md`
- `agent_outputs/references.md`
- `agent_outputs/language.md`

Guidelines:

- Ground every finding in text from `input/original_converted.md`
- Use severity: Critical, Major, Minor, Suggestion
- Assign confidence (0-100)
- Keep uncertain claims in a low-confidence appendix

## 4. Produce Final Report

Write synthesis into:

- `output/review_EN.md`
- Optional: `output/review_HU.md`

Render HTML:

```bash
python scripts/md_to_html.py reviews/<paper>_<YYYY-MM-DD>/output/review_EN.md
```

## 5. Interpretation of Verification Status

`verification/original_verification.json` status:

- `PASS`: safe to continue
- `WARN`: continue with caution
- `FAIL`: conversion quality is too low; use a better PDF or manual correction

Reference statuses in `verification/reference_report.json`:

- `verified`
- `suspicious`
- `unverifiable`

## 6. Reproducibility

To reproduce deterministic outputs, rerun on the same PDF and compare:

- conversion report
- reference report
- chunk map
- manifest metadata
