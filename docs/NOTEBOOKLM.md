# NotebookLM Integration

NotebookLM is integrated as a grounded analysis sidecar across the Codex workflow. It is useful for contradiction detection, statement checking, section-to-section comparisons, and targeted questions against the uploaded source pack.

## Role In The Workflow

NotebookLM is not a replacement for deterministic preprocessing or for quoting evidence directly in the final review.

- deterministic scripts still produce the source artifacts
- NotebookLM is used to interrogate those artifacts
- final findings still need exact source citations and analyst judgment

## Review Workspace Phase Map

After `python scripts/codex_prepare_review.py ...`, use:

- `notebooklm/WORKFLOW.md`
- `notebooklm/QUESTION_LOG.md`

Recommended sequence:

1. Preparation grounding
2. Per-pass contradiction and support checks
3. Synthesis QA against draft reviewer claims
4. Final audit of unresolved uncertainties

## Source Pack

The standard review workspace NotebookLM source pack should include:

1. `input/original.pdf`
2. `input/original_converted.md`
3. `verification/original_verification.json`
4. `verification/consistency_lint_report.json`
5. `verification/reference_report.json`
6. `chunks/chunk_map.json`
7. `chunks/convolution_plan.md`
8. `agent_outputs/*.md` once pass drafts exist

## Workflow-Specific Convolution Strategies

NotebookLM should use the overlap strategy generated for the active workflow:

- `chunked`: section/chunk overlap to catch local argument drift and section-to-section contradictions
- `no-chunk`: paragraph/span overlap to retain coverage even when the main analysis works on the full document
- `pdf`: page overlap to compare claims against the PDF-native extraction path

The current strategy is declared in `chunk_map.json` under `convolution_assignments.strategy` and summarized in `chunks/convolution_plan.md`.

## Three-Mode Comparison Phase

If you run:

```bash
python scripts/run_joint_workflow_review.py paper.pdf --force
```

the comparison workspace also includes:

- `workflow_comparison.md`
- `joint_review.md`
- `notebooklm/WORKFLOW.md`
- `notebooklm/QUESTION_LOG.md`

Use that comparison-stage NotebookLM workflow to:

- compare chunked, no-chunk, and PDF-native outputs against the original PDF
- identify claims that appear in one mode but not another
- choose the safest primary workflow for the final review

## Logging Discipline

Record material NotebookLM interactions in `notebooklm/QUESTION_LOG.md`:

- phase
- question asked
- concise answer summary
- cited source passages or files
- follow-up action taken in the review

Only log interactions that materially affect analysis, reviewer claims, or workflow selection.

## Guardrails

- treat NotebookLM as grounded QA, not automatic truth
- do not copy unsupported NotebookLM phrasing into the report
- confirm all important claims against the underlying files
- keep conversion warnings explicit when the source pack is imperfect
