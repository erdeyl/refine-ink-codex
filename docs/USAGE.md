# Usage Guide

How to run a review in the Codex-native workflow.

## 1. Prepare Workspace (Deterministic Phase)

```bash
python scripts/codex_prepare_review.py [path/to/paper.pdf] --email you@example.com
```

If the path is omitted, `codex_prepare_review.py` auto-detects a single `.pdf` in the current directory and validates it before processing.

### Codex App Shortcut

In the Codex app, you can use:

- Upload PDF with the plus button
- Type `/review`

The agent should resolve the uploaded file and run `codex_prepare_review.py` automatically.

Optional flags:

- `--reviews-dir reviews_alt`
- `--name custom-paper-slug`
- `--skip-references`
- `--force`
- `--chunking chunked|no-chunk|pdf`
- `--pdf-native-only`

Set `S2_API_KEY` in the environment for Semantic Scholar authenticated access.

Three-mode orchestration (chunked + no-chunk + pdf-native/pdf-chunking):

```bash
python scripts/run_joint_workflow_review.py [path/to/paper.pdf] --force
```

## 2. Inspect Generated Workspace

The command creates:

```text
reviews/<paper>_<YYYY-MM-DD>/
  input/
  verification/
  chunks/
  agent_outputs/
  notebooklm/
  output/
  NEXT_STEPS.md
```

Key files:

- `input/original_converted.md`
- `input/original_references.json`
- `verification/original_verification.json`
- `verification/reference_report.json`
- `chunks/chunk_map.json` (`total_chunks`, `chunks[]`, `dimension_assignments`)
- `chunks/convolution_plan.md`
- `notebooklm/WORKFLOW.md`
- `notebooklm/QUESTION_LOG.md`
- `output/review_EN.md`
- `output/manifest.json`
- comparison runner outputs:
  - `reviews/<paper>-workflow-comparison_<YYYY-MM-DD>/workflow_comparison.md`
  - `reviews/<paper>-workflow-comparison_<YYYY-MM-DD>/joint_review.md`
  - `reviews/<paper>-workflow-comparison_<YYYY-MM-DD>/notebooklm/WORKFLOW.md`
  - `reviews/<paper>-workflow-comparison_<YYYY-MM-DD>/notebooklm/QUESTION_LOG.md`

## 3. Run NotebookLM Grounded QA

If your Codex environment has NotebookLM MCP configured, use the generated guidance before and during analysis:

- upload the workspace source pack listed in `notebooklm/WORKFLOW.md`
- ask NotebookLM for contradictions, unsupported claims, and section-to-section inconsistencies
- follow `chunks/convolution_plan.md` for workflow-specific overlap sweeps:
  - `chunked`: heading-chunk overlap
  - `no-chunk`: paragraph/span overlap
  - `pdf`: page overlap
- log material exchanges in `notebooklm/QUESTION_LOG.md`

NotebookLM is a grounded sidecar, not a substitute for quoting the source files directly in the review.

## 4. Complete Analysis Passes

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

Before closing each pass, use NotebookLM to challenge the draft against the uploaded source pack and record any material follow-up.

## 5. Produce Final Report

Write synthesis into:

- `output/review_EN.md`
- Optional: `output/review_HU.md`

Render HTML:

```bash
python scripts/md_to_html.py reviews/<paper>_<YYYY-MM-DD>/output/review_EN.md
```

If you ran the three-mode comparison, add `workflow_comparison.md` and `joint_review.md` to the notebook and follow the comparison-stage prompts in `reviews/<paper>-workflow-comparison_<YYYY-MM-DD>/notebooklm/WORKFLOW.md` before finalizing the joint review.

## 6. Interpretation of Verification Status

`verification/original_verification.json` status:

- `PASS`: safe to continue
- `WARN`: continue with caution
- `FAIL`: conversion quality is too low; use a better PDF or manual correction

`--force` reuses the target review directory name and refreshes the generated scaffold so stale deterministic artifacts are not mixed into the new run.

Reference statuses in `verification/reference_report.json`:

- `verified`
- `suspicious`
- `unverifiable`

## 7. Reproducibility

To reproduce deterministic outputs, rerun on the same PDF and compare:

- conversion report
- reference report
- chunk map
- manifest metadata
