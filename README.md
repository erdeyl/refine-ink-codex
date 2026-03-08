# refine-ink-codex -- Scientific Paper Review Workflow for Codex

> Codex-native adaptation of [Refine.ink](https://refine.ink)-style academic paper review.

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![Status: Alpha](https://img.shields.io/badge/Status-Alpha-orange.svg)

## What This Repo Provides

- Deterministic preprocessing of academic PDFs (PDF -> Markdown + conversion checks)
- Rule-based manuscript consistency lint with generic and profile-aware checks
- Reference verification against CrossRef, OpenAlex, and Semantic Scholar
- Codex-ready review workspace scaffolding (`chunks`, `agent_outputs`, `output`)
- NotebookLM sidecar scaffolding for grounded contradiction checks and synthesis QA
- Structured report and manifest templates for reproducible audits
- Styled HTML rendering of final Markdown reports

## Quick Start

```bash
git clone https://github.com/erdeyl/refine-ink-codex.git
cd refine-ink-codex
python3 -m venv .venv
source .venv/bin/activate
pip install -r scripts/requirements.txt

python scripts/codex_prepare_review.py path/to/paper.pdf --email you@example.com
```

After preparation completes, use `notebooklm/WORKFLOW.md` during grounding, pass drafting, and synthesis, then finalize `output/review_EN.md`.

If no path is provided, the script auto-detects a single `.pdf` in the current directory.

## Codex App Workflow

1. Open the repository in the Codex app.
2. Use the plus button to upload a PDF.
3. Type `/review`.
4. The agent resolves the uploaded PDF and runs:
   - `python scripts/codex_prepare_review.py <resolved_pdf_path>`

## Review Workflow (Codex)

1. Run deterministic preparation:
   - `python scripts/codex_prepare_review.py [path/to/paper.pdf]`
2. Open `reviews/<paper>_<date>/NEXT_STEPS.md`
3. Use NotebookLM MCP with the generated source pack guidance in `notebooklm/WORKFLOW.md`
4. Fill analysis outputs under `agent_outputs/`:
   - `math-logic.md`, `notation.md`, `exposition.md`, `empirical.md`, `cross-section.md`, `econometrics.md`, `literature.md`, `references.md`, `language.md`
5. Synthesize the final report in `output/review_EN.md` (and `review_HU.md` when needed)
6. Render HTML:
   - `python scripts/md_to_html.py reviews/<paper>_<date>/output/review_EN.md`

## Workflow Variants

- Default (Markdown conversion + heading chunking):
  - `python scripts/codex_prepare_review.py paper.pdf`
- No-chunk scaffold:
  - `python scripts/codex_prepare_review.py paper.pdf --chunking no-chunk`
- PDF-native source mode (no PDF->MD conversion engine):
  - `python scripts/codex_prepare_review.py paper.pdf --pdf-native-only --chunking pdf`
- Run 3-mode comparison + joint review:
  - `python scripts/run_joint_workflow_review.py paper.pdf --force`
  - Comparison workspace also includes `notebooklm/WORKFLOW.md` for cross-mode QA

## Deterministic Outputs

Each prepared review contains:

- `input/original.pdf`
- `input/original_converted.md`
- `input/original_references.json`
- `verification/original_verification.json`
- `verification/consistency_lint_report.json`
- `verification/reference_report.json`
- `chunks/chunk_map.json` (`total_chunks`, `chunks[]`, `dimension_assignments`)
- `agent_outputs/*.md` (scaffolded)
- `notebooklm/WORKFLOW.md`
- `notebooklm/QUESTION_LOG.md`
- `output/review_EN.md`
- `output/manifest.json`
- `NEXT_STEPS.md`

Set `S2_API_KEY` in the environment if you want Semantic Scholar authenticated lookups; the workflow no longer accepts API keys on the command line.

## Repository Layout

```text
refine-ink-codex/
  AGENTS.md
  scripts/
    codex_prepare_review.py
    run_joint_workflow_review.py
    pdf_to_markdown.py
    verify_conversion.py
    verify_references.py
    md_to_html.py
    review_template.html
  docs/
    SETUP.md
    USAGE.md
    ARCHITECTURE.md
    AUDIT.md
    CHUNKING.md
    AGENTS.md
    NOTEBOOKLM.md
  legacy/
    claude/                 # Original Claude-specific assets retained for reference
```

## Documentation

- [docs/SETUP.md](docs/SETUP.md)
- [docs/USAGE.md](docs/USAGE.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/AUDIT.md](docs/AUDIT.md)
- [docs/CHUNKING.md](docs/CHUNKING.md)
- [docs/AGENTS.md](docs/AGENTS.md)
- [docs/NOTEBOOKLM.md](docs/NOTEBOOKLM.md)

## Legacy Claude Assets

Original orchestration assets from the upstream Claude workflow are preserved under `legacy/claude/`.

## License

MIT License. See [LICENSE](LICENSE).
